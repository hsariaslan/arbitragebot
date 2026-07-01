"""
Binance USDⓈ-M Futures executor (Phase B).

Standalone executor for spot-futures delta-neutral hedging. Operates on
Binance Futures testnet by default (https://testnet.binancefuture.com)
or mainnet (https://fapi.binance.com) when `mode='live'`.

Authentication is HMAC-SHA256 over the URL-encoded query string. The
testnet uses a SEPARATE credential set from spot testnet — sign up at
https://testnet.binancefuture.com.

Methods:
  place_market_order(symbol, side, qty)  → TradeResult
  close_position(symbol)                 → TradeResult (auto-detects current side)
  get_position(symbol)                   → dict (size, entry_price, unrealized_pnl, …)
  get_all_positions()                    → list[dict]   (used by recovery on restart)
  get_account_info()                     → dict (totalWalletBalance, availableBalance, …)
  set_leverage(symbol, leverage)         → bool
  set_margin_type(symbol, isolated)      → bool
  get_balance(asset)                     → float (futures wallet)

Symbol mapping for 1000X contracts (PEPE/SHIB/FLOKI) is centralized in
`funding_monitor.FUTURES_SYMBOL_OVERRIDE` and applied by the caller.
This executor speaks the futures symbol directly (e.g. `1000PEPEUSDT`).

Phase B is standalone — no bot integration yet. Use the companion test
script `scripts/test_futures_executor.py` for verification.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import time
from decimal import Decimal, ROUND_DOWN
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import aiohttp

from config import (
    BINANCE_FUTURES_API_KEY,
    BINANCE_FUTURES_API_SECRET,
    BINANCE_FUTURES_TESTNET_API_KEY,
    BINANCE_FUTURES_TESTNET_API_SECRET,
)
from executor import ExecutionEngine, RateLimiter, TradeResult

if TYPE_CHECKING:
    from exchange_info import ExchangeInfoManager

logger = logging.getLogger(__name__)

_TESTNET_BASE_URL = "https://testnet.binancefuture.com"
_LIVE_BASE_URL = "https://fapi.binance.com"
_SPOT_LIVE_BASE_URL = "https://api.binance.com"
_ACCOUNT_INFO_PATH = "/fapi/v2/account"
_BAN_UNTIL_RE = re.compile(r"banned until\s+(\d{10,13})", re.IGNORECASE)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _to_float(value: Any, default: float = 0.0) -> float:
    if _is_blank(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    if _is_blank(value):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        return max(0.0, float(value))
    rounded = (
        Decimal(str(max(0.0, float(value))))
        / Decimal(str(step))
    ).to_integral_value(rounding=ROUND_DOWN) * Decimal(str(step))
    return float(rounded)


def _fmt_decimal(value: float) -> str:
    d = Decimal(str(max(0.0, float(value)))).normalize()
    s = format(d, "f").rstrip("0").rstrip(".")
    return s if s else "0"


def _number_with_fallback(primary: Any, fallback: Any, default: float = 0.0) -> float:
    if _is_blank(primary):
        return _to_float(fallback, default)
    return _to_float(primary, default)


class BinanceFuturesExecutor(ExecutionEngine):
    """Binance USDⓈ-M Futures executor — testnet (default) or mainnet."""

    def __init__(
        self,
        exchange_info: "ExchangeInfoManager | None" = None,
        mode: str = "testnet",
    ) -> None:
        super().__init__("BinanceFutures", exchange_info)
        self._mode = mode
        if mode == "live":
            self._base_url = _LIVE_BASE_URL
            self._api_key = BINANCE_FUTURES_API_KEY
            self._api_secret = BINANCE_FUTURES_API_SECRET
        else:
            self._base_url = _TESTNET_BASE_URL
            self._api_key = BINANCE_FUTURES_TESTNET_API_KEY
            self._api_secret = BINANCE_FUTURES_TESTNET_API_SECRET
        self._session: aiohttp.ClientSession | None = None
        # Binance enforces 2400 weight/min on futures REST; most order/account
        # calls cost weight 1-5. Conservative cap at 1500/min for safety.
        self._rate_limiter = RateLimiter(max_requests=1500, window_seconds=60)
        # Cache of leverage/margin-type already set, to avoid redundant API calls
        self._leverage_set: dict[str, int] = {}
        self._margin_isolated_set: set[str] = set()
        # Per-symbol exchange filters: {symbol: {step, tick, min_qty, min_notional}}
        # Loaded lazily on first need from /fapi/v1/exchangeInfo.
        self._symbol_filters: dict[str, dict] = {}
        self._spot_symbol_filters: dict[str, dict] = {}
        self._exchange_info_loaded: bool = False
        self._sapi_base_url = _SPOT_LIVE_BASE_URL
        self._account_info_backoff_until: float = 0.0
        self._account_info_backoff_reason: str = ""
        self._account_info_backoff_logged: bool = False
        self._account_info_cache: dict = {}
        self._account_info_cache_ts: float = 0.0
        self._account_info_ttl_seconds: float = 10.0

    # ── Internal helpers ──────────────────────────────────────────────

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    def _sign(self, params: dict) -> str:
        """HMAC-SHA256 signature appended to URL-encoded query string."""
        query = urlencode(params)
        sig = hmac.new(
            self._api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{query}&signature={sig}"

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self._api_key}

    def _credentials_ok(self) -> bool:
        return bool(self._api_key and self._api_secret)

    def format_symbol(self, symbol: str) -> str:
        """Binance Futures uses BTCUSDT format. 1000X contracts kept verbatim."""
        return symbol

    def _account_info_backoff_remaining(self) -> float:
        return max(0.0, self._account_info_backoff_until - time.time())

    def _record_account_info_backoff(self, status: int, data: dict) -> None:
        """Respect Binance rate-limit bans on the expensive account summary call."""
        code = data.get("code") if isinstance(data, dict) else None
        if status not in (418, 429) and code != -1003:
            return

        msg = str(data.get("msg") or data.get("error") or data)
        now = time.time()
        until = now + 60.0
        match = _BAN_UNTIL_RE.search(msg)
        if match:
            raw_ts = int(match.group(1))
            ban_ts = raw_ts / 1000.0 if raw_ts > 10_000_000_000 else float(raw_ts)
            until = max(until, ban_ts + 2.0)

        self._account_info_backoff_until = max(self._account_info_backoff_until, until)
        self._account_info_backoff_reason = msg
        self._account_info_backoff_logged = False

    def _maybe_clear_account_info_backoff(self, path: str, status: int) -> None:
        if path == _ACCOUNT_INFO_PATH and status == 200:
            self._account_info_backoff_until = 0.0
            self._account_info_backoff_reason = ""
            self._account_info_backoff_logged = False

    def _clear_account_info_cache(self) -> None:
        self._account_info_cache = {}
        self._account_info_cache_ts = 0.0

    async def _signed_request(
        self,
        method: str,
        path: str,
        params: dict,
        recv_window: int = 5000,
    ) -> tuple[int, dict]:
        """Make a signed REST request. Returns (http_status, response_json)."""
        if not self._credentials_ok():
            return (0, {"error": "credentials not configured"})
        if path == _ACCOUNT_INFO_PATH:
            remaining = self._account_info_backoff_remaining()
            if remaining > 0:
                if not self._account_info_backoff_logged:
                    logger.warning(
                        f"[BinanceFutures] account-info backoff active for "
                        f"{remaining:.0f}s after rate-limit response: "
                        f"{self._account_info_backoff_reason}"
                    )
                    self._account_info_backoff_logged = True
                return (
                    0,
                    {
                        "error": "account_info_backoff",
                        "retry_after_seconds": round(remaining, 1),
                        "reason": self._account_info_backoff_reason,
                    },
                )
        if not await self._rate_limiter.acquire():
            return (0, {"error": "rate_limited"})

        session = await self._ensure_session()
        params = dict(params)
        params["timestamp"] = str(int(time.time() * 1000))
        params["recvWindow"] = str(recv_window)
        signed = self._sign(params)
        url = f"{self._base_url}{path}?{signed}"

        try:
            async with session.request(method, url, headers=self._headers()) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"raw": await resp.text()}
                data = data if isinstance(data, dict) else {"data": data}
                if path == _ACCOUNT_INFO_PATH:
                    self._maybe_clear_account_info_backoff(path, resp.status)
                    self._record_account_info_backoff(resp.status, data)
                return (resp.status, data)
        except Exception as e:
            return (0, {"error": f"request_exception: {e}"})

    async def _sapi_signed_request(
        self,
        method: str,
        path: str,
        params: dict,
        recv_window: int = 5000,
    ) -> tuple[int, dict]:
        """Make a signed Binance Spot/SAPI request using the live REST host."""
        if self._mode != "live":
            return (0, {"error": "sapi_universal_transfer_requires_live_mode"})
        if not self._credentials_ok():
            return (0, {"error": "credentials not configured"})
        if not await self._rate_limiter.acquire():
            return (0, {"error": "rate_limited"})

        session = await self._ensure_session()
        params = dict(params)
        params["timestamp"] = str(int(time.time() * 1000))
        params["recvWindow"] = str(recv_window)
        signed = self._sign(params)
        url = f"{self._sapi_base_url}{path}?{signed}"

        try:
            async with session.request(method, url, headers=self._headers()) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"raw": await resp.text()}
                return (resp.status, data if isinstance(data, dict) else {"data": data})
        except Exception as e:
            return (0, {"error": f"request_exception: {e}"})

    async def _spot_signed_request(
        self,
        method: str,
        path: str,
        params: dict,
        recv_window: int = 5000,
    ) -> tuple[int, dict]:
        """Make a signed Binance Spot REST request using the live REST host."""
        if self._mode != "live":
            return (0, {"error": "spot_account_requires_live_mode"})
        if not self._credentials_ok():
            return (0, {"error": "credentials not configured"})
        if not await self._rate_limiter.acquire():
            return (0, {"error": "rate_limited"})

        session = await self._ensure_session()
        params = dict(params)
        params["timestamp"] = str(int(time.time() * 1000))
        params["recvWindow"] = str(recv_window)
        signed = self._sign(params)
        url = f"{self._sapi_base_url}{path}?{signed}"

        try:
            async with session.request(method, url, headers=self._headers()) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"raw": await resp.text()}
                return (resp.status, data if isinstance(data, dict) else {"data": data})
        except Exception as e:
            return (0, {"error": f"request_exception: {e}"})

    async def get_ticker_price(self, symbol: str) -> float:
        """Return a public Binance Futures ticker price."""
        session = await self._ensure_session()
        url = f"{self._base_url}/fapi/v1/ticker/price?symbol={symbol}"
        try:
            async with session.get(url) as resp:
                data = await resp.json(content_type=None)
            if isinstance(data, dict):
                return _to_float(data.get("price"))
        except Exception as e:
            logger.warning(f"[BinanceFutures] ticker price fetch failed: {symbol}: {e}")
        return 0.0

    async def get_spot_ticker_price(self, symbol: str = "BNBUSDT") -> float:
        """Return a public Binance Spot ticker price."""
        session = await self._ensure_session()
        url = f"{self._sapi_base_url}/api/v3/ticker/price?symbol={symbol}"
        try:
            async with session.get(url) as resp:
                data = await resp.json(content_type=None)
            if isinstance(data, dict):
                return _to_float(data.get("price"))
        except Exception as e:
            logger.warning(f"[BinanceFutures] spot ticker price fetch failed: {symbol}: {e}")
        return 0.0

    # ── Exchange filters (LOT_SIZE, MIN_NOTIONAL, PRICE_FILTER) ───────

    async def _load_exchange_info(self) -> None:
        """Fetch /fapi/v1/exchangeInfo once and cache per-symbol filters.

        Public endpoint, no auth. Weight ~1. Caches: step (qty granularity),
        tick (price granularity), min_qty, min_notional, qty_precision.
        """
        if self._exchange_info_loaded:
            return
        session = await self._ensure_session()
        url = f"{self._base_url}/fapi/v1/exchangeInfo"
        try:
            async with session.get(url) as resp:
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.warning(f"[BinanceFutures] exchangeInfo fetch failed: {e}")
            return
        symbols = data.get("symbols", []) if isinstance(data, dict) else []
        for sym_info in symbols:
            sym = sym_info.get("symbol")
            if not sym:
                continue
            step = 0.0
            tick = 0.0
            min_qty = 0.0
            min_notional = 0.0
            for f in sym_info.get("filters", []):
                t = f.get("filterType")
                if t == "LOT_SIZE":
                    step = _to_float(f.get("stepSize"))
                    min_qty = _to_float(f.get("minQty"))
                elif t == "PRICE_FILTER":
                    tick = _to_float(f.get("tickSize"))
                elif t in ("MIN_NOTIONAL", "NOTIONAL"):
                    min_notional = _to_float(f.get("notional", f.get("minNotional")))
            self._symbol_filters[sym] = {
                "step": step,
                "tick": tick,
                "min_qty": min_qty,
                "min_notional": min_notional,
                "qty_precision": _to_int(sym_info.get("quantityPrecision")),
                "price_precision": _to_int(sym_info.get("pricePrecision")),
            }
        self._exchange_info_loaded = True
        logger.info(
            f"[BinanceFutures] Loaded exchangeInfo: {len(self._symbol_filters)} symbols "
            f"({self._mode})"
        )

    async def get_symbol_filters(self, symbol: str) -> dict | None:
        """Return the cached LOT_SIZE/PRICE_FILTER/min_notional for a symbol.

        Lazily loads exchangeInfo on first call.
        """
        if not self._exchange_info_loaded:
            await self._load_exchange_info()
        return self._symbol_filters.get(symbol)

    async def get_spot_symbol_filters(self, symbol: str) -> dict | None:
        """Return cached Binance Spot filters for a symbol."""
        if symbol in self._spot_symbol_filters:
            return self._spot_symbol_filters[symbol]

        session = await self._ensure_session()
        url = f"{self._sapi_base_url}/api/v3/exchangeInfo?symbol={symbol}"
        try:
            async with session.get(url) as resp:
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.warning(f"[BinanceFutures] spot exchangeInfo fetch failed: {symbol}: {e}")
            return None

        symbols = data.get("symbols", []) if isinstance(data, dict) else []
        if not symbols:
            logger.warning(f"[BinanceFutures] spot exchangeInfo empty for {symbol}: {data}")
            return None

        sym_info = symbols[0]
        step = 0.0
        tick = 0.0
        min_qty = 0.0
        min_notional = 0.0
        for filt in sym_info.get("filters", []):
            filt_type = filt.get("filterType")
            if filt_type == "LOT_SIZE":
                step = _to_float(filt.get("stepSize"))
                min_qty = _to_float(filt.get("minQty"))
            elif filt_type == "PRICE_FILTER":
                tick = _to_float(filt.get("tickSize"))
            elif filt_type in ("MIN_NOTIONAL", "NOTIONAL"):
                min_notional = _to_float(filt.get("minNotional", filt.get("notional")))

        filters = {
            "step": step,
            "tick": tick,
            "min_qty": min_qty,
            "min_notional": min_notional,
            "base_precision": _to_int(sym_info.get("baseAssetPrecision"), 8),
            "quote_precision": _to_int(sym_info.get("quoteAssetPrecision"), 8),
        }
        self._spot_symbol_filters[symbol] = filters
        return filters

    async def round_quantity(self, symbol: str, qty: float) -> float:
        """Round qty DOWN to the symbol's LOT_SIZE step (truncate-toward-zero).

        Returns 0 if the rounded qty falls below min_qty.
        """
        filters = await self.get_symbol_filters(symbol)
        if not filters:
            return qty  # No filter info — pass through
        step = filters.get("step", 0)
        min_qty = filters.get("min_qty", 0)
        if step > 0:
            # Round down to nearest multiple of step
            rounded = (int(qty / step)) * step
            # Avoid float drift — re-quantize with precision
            precision = filters.get("qty_precision", 8)
            rounded = float(f"{rounded:.{precision}f}")
        else:
            rounded = qty
        if rounded < min_qty:
            return 0.0
        return rounded

    async def place_spot_market_buy_bnb(
        self,
        quote_usd: float,
        client_order_id: str = "",
    ) -> dict:
        """Buy BNB on Binance Spot with a market order by quote amount."""
        if self._mode != "live":
            return {"success": False, "error": "spot_bnb_buy_requires_live_mode"}
        quote = max(0.0, float(quote_usd))
        if quote <= 0:
            return {"success": False, "error": "quote_usd_must_be_positive"}

        symbol = "BNBUSDT"
        filters = await self.get_spot_symbol_filters(symbol)
        if not filters:
            return {"success": False, "error": "spot_symbol_filters_unavailable"}

        min_notional = float(filters.get("min_notional", 0.0) or 0.0)
        if min_notional > 0 and quote < min_notional:
            return {
                "success": False,
                "error": f"bnb_quote_below_min_notional ${quote:.2f} < ${min_notional:.2f}",
            }

        params: dict = {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": _fmt_decimal(quote),
            "newOrderRespType": "FULL",
        }
        if client_order_id:
            params["newClientOrderId"] = client_order_id[:36]

        status, data = await self._spot_signed_request("POST", "/api/v3/order", params)
        if status != 200 or "orderId" not in data:
            error = data.get("msg", data.get("error", str(data)))
            logger.warning(
                f"[BinanceFutures] Spot BNB market buy failed: "
                f"quote=${quote:.2f} status={status} resp={data}"
            )
            return {"success": False, "status": status, "error": error, "raw": data}

        order_id = str(data.get("orderId", ""))
        executed_qty = _to_float(data.get("executedQty"))
        quote_spent = _to_float(data.get("cummulativeQuoteQty"))
        fees: dict[str, float] = {}
        for fill in data.get("fills", []) if isinstance(data, dict) else []:
            if not isinstance(fill, dict):
                continue
            asset = str(fill.get("commissionAsset") or "")
            commission = _to_float(fill.get("commission"))
            if asset and commission > 0:
                fees[asset] = fees.get(asset, 0.0) + commission

        fee_bnb = fees.get("BNB", 0.0)
        fee_usdt = fees.get("USDT", 0.0)
        estimated_fee_bnb = 0.0
        if executed_qty > 0 and not data.get("fills"):
            estimated_fee_bnb = executed_qty * 0.001
        net_qty = max(0.0, executed_qty - fee_bnb)
        if estimated_fee_bnb > 0:
            net_qty = max(0.0, net_qty - estimated_fee_bnb)
            fees["BNB_ESTIMATED"] = estimated_fee_bnb
        avg_price = quote_spent / executed_qty if executed_qty > 0 else 0.0
        if net_qty <= 0:
            return {
                "success": False,
                "status": data.get("status"),
                "order_id": order_id,
                "error": "spot_bnb_market_buy_not_filled",
                "requested_usd": quote,
                "filled_qty": executed_qty,
                "spent_usdt": quote_spent + fee_usdt,
                "raw": data,
            }

        return {
            "success": True,
            "symbol": symbol,
            "order_id": order_id,
            "status": data.get("status"),
            "requested_usd": quote,
            "filled_qty": executed_qty,
            "net_qty": net_qty,
            "spent_usdt": quote_spent + fee_usdt,
            "avg_price": avg_price,
            "fee_bnb": fee_bnb,
            "estimated_fee_bnb": estimated_fee_bnb,
            "fee_usdt": fee_usdt,
            "fees": fees,
            "raw": data,
        }

    # ── Configuration (one-time per symbol) ───────────────────────────

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol (Phase B: always 1× per design)."""
        if self._leverage_set.get(symbol) == leverage:
            return True  # Already set — skip API call
        status, data = await self._signed_request(
            "POST", "/fapi/v1/leverage",
            {"symbol": symbol, "leverage": int(leverage)},
        )
        if status == 200 and _to_int(data.get("leverage")) == leverage:
            self._leverage_set[symbol] = leverage
            logger.info(f"[BinanceFutures] Leverage set: {symbol}={leverage}x ({self._mode})")
            return True
        logger.warning(
            f"[BinanceFutures] set_leverage failed: {symbol}={leverage}x "
            f"status={status} resp={data}"
        )
        return False

    async def set_margin_type(self, symbol: str, isolated: bool = True) -> bool:
        """Set margin type to ISOLATED (default) or CROSSED.

        Binance returns code -4046 ("No need to change margin type") if it's
        already that mode — we treat that as success.
        """
        target = "ISOLATED" if isolated else "CROSSED"
        if isolated and symbol in self._margin_isolated_set:
            return True  # Already set
        status, data = await self._signed_request(
            "POST", "/fapi/v1/marginType",
            {"symbol": symbol, "marginType": target},
        )
        if status == 200 or data.get("code") == -4046:
            if isolated:
                self._margin_isolated_set.add(symbol)
            logger.info(f"[BinanceFutures] Margin type set: {symbol}={target} ({self._mode})")
            return True
        logger.warning(
            f"[BinanceFutures] set_margin_type failed: {symbol}={target} "
            f"status={status} resp={data}"
        )
        return False

    # ── Orders ────────────────────────────────────────────────────────

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        client_order_id: str = "",
        expected_price: float = 0.0,
        reduce_only: bool = False,
    ) -> TradeResult:
        """Place a futures market order.

        side: "BUY" (open long / close short) or "SELL" (open short / close long).
        For Phase B hedging: opening a short hedge = SELL with reduce_only=False.
        Closing the hedge = BUY with reduce_only=True.

        Quantity is rounded DOWN to the symbol's LOT_SIZE step. If the rounded
        qty is below min_qty, the order is rejected locally without API call.
        """
        # Round to LOT_SIZE step. Binance returns:
        #   -1111 when precision exceeds quantityPrecision
        #   -2010/-4164 when qty < min_qty or notional < min_notional
        # We pre-check both locally to avoid burning rate-limit weight on
        # guaranteed-rejected orders.
        rounded_qty = await self.round_quantity(symbol, qty)
        filters = await self.get_symbol_filters(symbol)
        if rounded_qty <= 0:
            min_qty = filters.get("min_qty", 0) if filters else 0
            return self._failed_result(
                symbol, side, qty, expected_price,
                f"qty {qty} below min_qty {min_qty} after LOT_SIZE rounding",
                client_order_id,
            )
        # min_notional check (skip for reduce_only — Binance allows undersized closes)
        if not reduce_only and filters and expected_price > 0:
            min_notional = filters.get("min_notional", 0)
            if min_notional > 0:
                est_notional = rounded_qty * expected_price
                if est_notional < min_notional:
                    return self._failed_result(
                        symbol, side, qty, expected_price,
                        f"notional ${est_notional:.2f} below min_notional ${min_notional:.2f}",
                        client_order_id,
                    )

        t0 = time.time()
        params: dict = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": _fmt_qty(rounded_qty),
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        if client_order_id:
            params["newClientOrderId"] = client_order_id

        status, data = await self._signed_request("POST", "/fapi/v1/order", params)
        latency = (time.time() - t0) * 1000.0

        if status != 200 or "orderId" not in data:
            error = data.get("msg", str(data))
            code = data.get("code", status)
            count = self._rejected_symbols.get(symbol, 0) + 1
            self._rejected_symbols[symbol] = count
            if count == 1:
                logger.warning(
                    f"[BinanceFutures] Order rejected: {symbol} {side} qty={qty} "
                    f"reduce_only={reduce_only} — {code}: {error}"
                )
            return self._failed_result(symbol, side, qty, expected_price, f"{code}: {error}", client_order_id)

        result = self._parse_order_response(
            data, symbol, side, rounded_qty, expected_price, client_order_id, latency
        )
        await self._populate_order_fees(result)
        return result

    async def close_position(self, symbol: str) -> TradeResult | None:
        """Close any open position for a symbol via market order with reduceOnly.

        Returns None if there's no open position. Auto-detects side: if we're
        short (positionAmt < 0), we BUY to close; if long, we SELL.
        """
        pos = await self.get_position(symbol)
        if pos is None or abs(pos.get("size", 0.0)) == 0.0:
            return None
        size = pos["size"]
        side = "BUY" if size < 0 else "SELL"
        qty = abs(size)
        cid = f"close{int(time.time() * 1000) % 1_000_000_000}"
        return await self.place_market_order(
            symbol, side, qty, client_order_id=cid, reduce_only=True,
        )

    async def get_order_status(self, symbol: str, order_id: str) -> TradeResult:
        """Query an existing order's status."""
        params = {"symbol": symbol, "orderId": str(order_id)}
        status, data = await self._signed_request("GET", "/fapi/v1/order", params)
        if status != 200 or "orderId" not in data:
            return self._failed_result(symbol, "?", 0.0, 0.0, str(data), str(order_id))
        result = self._parse_order_response(
            data, symbol, data.get("side", "?"), 0.0, 0.0, str(order_id), 0.0
        )
        await self._populate_order_fees(result)
        return result

    # ── Positions / account ───────────────────────────────────────────

    async def get_position(self, symbol: str) -> dict | None:
        """Return current position info for a symbol, or None if flat."""
        status, data = await self._signed_request(
            "GET", "/fapi/v2/positionRisk", {"symbol": symbol},
        )
        if status != 200:
            logger.warning(f"[BinanceFutures] get_position failed: {symbol} resp={data}")
            return None
        # API returns a list of one dict in one-way mode (no hedge mode)
        rows = data.get("data") if isinstance(data, dict) and "data" in data else data
        if isinstance(rows, dict):  # single object response
            rows = [rows]
        if not isinstance(rows, list) or not rows:
            return None
        row = rows[0]
        if not isinstance(row, dict):
            return None
        size = _to_float(row.get("positionAmt"))
        return {
            "symbol": symbol,
            "positionAmt": size,
            "size": size,                                  # signed: negative=short, positive=long
            "entry_price": _to_float(row.get("entryPrice")),
            "mark_price": _to_float(row.get("markPrice")),
            "unrealized_pnl": _to_float(row.get("unRealizedProfit")),
            "leverage": _to_int(row.get("leverage"), 1),
            "margin_type": str(row.get("marginType", "")).lower(),
            "isolated_wallet": _to_float(row.get("isolatedWallet")),
            "liquidation_price": _to_float(row.get("liquidationPrice")),
        }

    async def get_all_positions(self) -> list[dict]:
        """Return all non-zero positions. Used for restart reconciliation."""
        status, data = await self._signed_request("GET", "/fapi/v2/positionRisk", {})
        if status != 200:
            logger.warning(f"[BinanceFutures] get_all_positions failed: resp={data}")
            return []
        rows = data.get("data") if isinstance(data, dict) and "data" in data else data
        if not isinstance(rows, list):
            return []
        result = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            size = _to_float(row.get("positionAmt"))
            if size == 0.0:
                continue
            result.append({
                "symbol": row.get("symbol"),
                "positionAmt": size,
                "size": size,
                "entry_price": _to_float(row.get("entryPrice")),
                "mark_price": _to_float(row.get("markPrice")),
                "unrealized_pnl": _to_float(row.get("unRealizedProfit")),
                "leverage": _to_int(row.get("leverage"), 1),
                "margin_type": str(row.get("marginType", "")).lower(),
            })
        return result

    async def get_account_info(self) -> dict:
        """Return wallet/margin balance summary."""
        now = time.time()
        if (
            self._account_info_cache
            and now - self._account_info_cache_ts <= self._account_info_ttl_seconds
        ):
            return dict(self._account_info_cache)

        status, data = await self._signed_request("GET", _ACCOUNT_INFO_PATH, {})
        if status != 200:
            if data.get("error") != "account_info_backoff":
                logger.warning(f"[BinanceFutures] get_account_info failed: resp={data}")
            return {}
        assets = data.get("assets", []) if isinstance(data, dict) else []
        usdt_asset = next(
            (
                row for row in assets
                if isinstance(row, dict) and row.get("asset") == "USDT"
            ),
            {},
        )
        parsed = {
            "total_wallet_balance": _number_with_fallback(
                data.get("totalWalletBalance"),
                usdt_asset.get("walletBalance"),
            ),
            "total_unrealized_pnl": _number_with_fallback(
                data.get("totalUnrealizedProfit"),
                usdt_asset.get("unrealizedProfit"),
            ),
            "total_margin_balance": _number_with_fallback(
                data.get("totalMarginBalance"),
                usdt_asset.get("marginBalance"),
            ),
            "available_balance": _number_with_fallback(
                data.get("availableBalance"),
                usdt_asset.get("availableBalance"),
            ),
            "max_withdraw_amount": _number_with_fallback(
                data.get("maxWithdrawAmount"),
                usdt_asset.get("maxWithdrawAmount"),
            ),
        }
        self._account_info_cache = dict(parsed)
        self._account_info_cache_ts = now
        return parsed

    async def get_balance(self, asset: str = "USDT") -> float:
        """Return available balance for an asset (default USDT)."""
        status, data = await self._signed_request("GET", "/fapi/v2/balance", {})
        if status != 200:
            return 0.0
        rows = data.get("data") if isinstance(data, dict) and "data" in data else data
        if not isinstance(rows, list):
            return 0.0
        for row in rows:
            if isinstance(row, dict) and row.get("asset") == asset:
                return _to_float(row.get("availableBalance"))
        return 0.0

    async def _populate_order_fees(self, result: TradeResult) -> None:
        """Populate actual futures commission from user trades when available."""
        if not result.success or not result.order_id or not result.symbol:
            return
        params = {"symbol": result.symbol, "orderId": result.order_id}
        trades: list[dict] = []
        for attempt in range(2):
            status, data = await self._signed_request("GET", "/fapi/v1/userTrades", params)
            rows = data.get("data") if isinstance(data, dict) and "data" in data else data
            if status == 200 and isinstance(rows, list):
                trades = [row for row in rows if isinstance(row, dict)]
                if trades:
                    break
            if attempt == 0:
                await asyncio.sleep(0.15)
        if not trades:
            return

        commissions: dict[str, float] = {}
        quote_qty = 0.0
        qty = 0.0
        for trade in trades:
            asset = str(trade.get("commissionAsset") or "")
            commission = _to_float(trade.get("commission"))
            if asset and commission > 0:
                commissions[asset] = commissions.get(asset, 0.0) + commission
            quote_qty += _to_float(trade.get("quoteQty"))
            qty += _to_float(trade.get("qty"))

        if quote_qty > 0 and qty > 0:
            result.actual_avg_price = quote_qty / qty
            result.filled_qty = qty
        if not commissions:
            return

        result.raw_response["commissions"] = commissions
        if len(commissions) == 1:
            asset, amount = next(iter(commissions.items()))
            result.actual_fee = amount
            result.fee_currency = asset
            notional = result.filled_qty * result.actual_avg_price
            result.actual_fee_usd = amount if asset == "USDT" else 0.0
            result.fee_rate = result.actual_fee_usd / notional if notional > 0 else 0.0
        else:
            result.actual_fee = sum(commissions.values())
            result.fee_currency = "MIXED"
            result.actual_fee_usd = commissions.get("USDT", 0.0)
            result.fee_rate = 0.0

    async def get_spot_balance(self, asset: str = "BNB") -> float:
        """Return Spot wallet free+locked balance for an asset (live mode only)."""
        status, data = await self._spot_signed_request("GET", "/api/v3/account", {})
        if status != 200:
            logger.warning(f"[BinanceFutures] spot balance fetch failed: {asset} resp={data}")
            return 0.0
        for row in data.get("balances", []) if isinstance(data, dict) else []:
            if isinstance(row, dict) and row.get("asset") == asset:
                return _to_float(row.get("free")) + _to_float(row.get("locked"))
        return 0.0

    async def transfer_spot_to_futures(
        self,
        amount_usdt: float,
        asset: str = "USDT",
    ) -> dict:
        """Move funds from Binance Spot wallet to USD-M Futures wallet.

        Uses Binance Universal Transfer (`MAIN_UMFUTURE`). The live API key
        needs the Universal Transfer permission. Testnet has no equivalent
        SAPI universal-transfer environment, so this method returns a
        structured failure outside live mode.
        """
        amount = float(amount_usdt)
        if amount <= 0:
            return {"success": False, "error": "amount_must_be_positive"}
        status, data = await self._sapi_signed_request(
            "POST",
            "/sapi/v1/asset/transfer",
            {
                "type": "MAIN_UMFUTURE",
                "asset": asset,
                "amount": f"{amount:.8f}",
            },
        )
        if status == 200 and ("tranId" in data or "data" in data):
            self._clear_account_info_cache()
            return {"success": True, "direction": "spot_to_futures", "asset": asset, **data}
        logger.warning(
            f"[BinanceFutures] spot→futures transfer failed: "
            f"amount={amount:.8f} {asset} resp={data}"
        )
        return {"success": False, "direction": "spot_to_futures", "status": status, "error": data}

    async def transfer_futures_to_spot(
        self,
        amount_usdt: float,
        asset: str = "USDT",
    ) -> dict:
        """Move idle funds from USD-M Futures wallet back to Binance Spot."""
        amount = float(amount_usdt)
        if amount <= 0:
            return {"success": False, "error": "amount_must_be_positive"}
        status, data = await self._sapi_signed_request(
            "POST",
            "/sapi/v1/asset/transfer",
            {
                "type": "UMFUTURE_MAIN",
                "asset": asset,
                "amount": f"{amount:.8f}",
            },
        )
        if status == 200 and ("tranId" in data or "data" in data):
            self._clear_account_info_cache()
            return {"success": True, "direction": "futures_to_spot", **data}
        logger.warning(
            f"[BinanceFutures] futures→spot transfer failed: "
            f"amount={amount:.2f} resp={data}"
        )
        return {"success": False, "direction": "futures_to_spot", "status": status, "error": data}

    # ── Cleanup ───────────────────────────────────────────────────────

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ── Response parser ───────────────────────────────────────────────

    def _parse_order_response(
        self,
        data: dict,
        symbol: str,
        side: str,
        qty: float,
        expected_price: float,
        client_order_id: str,
        latency: float,
    ) -> TradeResult:
        """Parse Binance Futures order response into TradeResult."""
        order_id = str(data.get("orderId", ""))
        executed_qty = _to_float(data.get("executedQty"))
        cum_quote = _to_float(data.get("cumQuote"))     # USD value filled
        avg_price = cum_quote / executed_qty if executed_qty > 0 else 0.0
        # Binance Futures market orders settle in USDT margin; commission asset
        # is USDT in the response. We don't get fills array here unless we
        # query trades separately — for v1 that's fine, the funding-cost track
        # is what we care about.
        return TradeResult(
            success=True,
            order_id=order_id,
            client_order_id=client_order_id,
            exchange=self.exchange_name,
            symbol=symbol,
            side=side.upper(),
            requested_qty=qty,
            filled_qty=executed_qty,
            requested_price=expected_price,
            actual_avg_price=avg_price,
            actual_fee=0.0,            # populated via /userTrades if needed
            fee_rate=0.0,
            fee_currency="USDT",
            is_maker=False,
            latency_ms=latency,
            raw_response=data,
            timestamp=time.time(),
        )


def _fmt_qty(qty: float) -> str:
    """Format quantity for Binance — drop trailing zeros, max 8 decimals."""
    s = f"{qty:.8f}".rstrip("0").rstrip(".")
    return s if s else "0"
