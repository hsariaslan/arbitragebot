"""
OKX demo trading executor.

Places spot market orders on https://www.okx.com with the
x-simulated-trading: 1 header. Uses the same HMAC-SHA256 + passphrase
auth pattern as demo_fetcher._fetch_okx().

Endpoints:
  POST /api/v5/trade/order — place market order
  GET  /api/v5/trade/order — query order details (fill price, fees)
  GET  /api/v5/account/balance — query balances
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiohttp

from config import OKX_DEMO_API_KEY, OKX_DEMO_API_SECRET, OKX_DEMO_PASSPHRASE
from executor import ExecutionEngine, RateLimiter, TradeResult

if TYPE_CHECKING:
    from exchange_info import ExchangeInfoManager

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.okx.com"


class OKXExecutor(ExecutionEngine):
    """OKX demo trading spot market order executor."""

    def __init__(self, exchange_info: ExchangeInfoManager | None = None) -> None:
        super().__init__("OKX", exchange_info)
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter = RateLimiter(max_requests=50, window_seconds=2)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    def _sign_headers(self, method: str, path: str, body: str = "") -> dict:
        """Create OKX auth headers with HMAC-SHA256 signature."""
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
        sign_str = ts + method.upper() + path + body
        signature = base64.b64encode(
            hmac.new(
                OKX_DEMO_API_SECRET.encode(),
                sign_str.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()

        return {
            "OK-ACCESS-KEY": OKX_DEMO_API_KEY,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": OKX_DEMO_PASSPHRASE,
            "x-simulated-trading": "1",
            "Content-Type": "application/json",
        }

    def format_symbol(self, symbol: str) -> str:
        """Convert BTCUSDT → BTC-USDT."""
        base = symbol.replace("USDT", "")
        return f"{base}-USDT"

    async def place_market_order(
        self, symbol: str, side: str, qty: float, client_order_id: str,
        expected_price: float = 0.0,
    ) -> TradeResult:
        """Place a spot market order on OKX demo."""
        if not await self._rate_limiter.acquire():
            return self._failed_result(
                symbol, side, qty, expected_price,
                "rate_limited", client_order_id,
            )

        session = await self._ensure_session()
        t0 = time.time()

        inst_id = self.format_symbol(symbol)
        body_dict = {
            "instId": inst_id,
            "tdMode": "cash",
            "side": side.lower(),
            "ordType": "market",
            "sz": f"{qty:.8f}".rstrip("0").rstrip("."),
            "clOrdId": client_order_id[:32],  # OKX max 32 chars
        }
        body = json.dumps(body_dict)

        path = "/api/v5/trade/order"
        headers = self._sign_headers("POST", path, body)
        url = f"{_BASE_URL}{path}"

        try:
            async with session.post(url, headers=headers, data=body) as resp:
                data = await resp.json()

            latency_submit = (time.time() - t0) * 1000.0

            if data.get("code") != "0":
                error = data.get("msg", "")
                sdata = data.get("data", [{}])
                if sdata:
                    error = sdata[0].get("sMsg", error) or error
                count = self._rejected_symbols.get(symbol, 0) + 1
                self._rejected_symbols[symbol] = count
                if count == 1:
                    logger.warning(
                        f"[OKXExec] Order rejected: {symbol} {side} "
                        f"qty={qty} — {error}"
                    )
                elif count == 2:
                    logger.info(
                        f"[OKXExec] {symbol} rejection repeated — "
                        f"suppressing further logs"
                    )
                return self._failed_result(
                    symbol, side, qty, expected_price,
                    error, client_order_id,
                )

            # OKX returns ordId in response — need separate query for fill details
            order_data = data.get("data", [{}])[0]
            ord_id = order_data.get("ordId", "")

            if not ord_id:
                return self._failed_result(
                    symbol, side, qty, expected_price,
                    "no ordId in response", client_order_id,
                )

            # Query fill details (small delay for settlement)
            await asyncio.sleep(0.2)
            fill_result = await self._query_order(inst_id, ord_id, symbol, side,
                                                   qty, expected_price, client_order_id)
            fill_result.latency_ms = (time.time() - t0) * 1000.0
            return fill_result

        except Exception as e:
            logger.error(f"[OKXExec] Order exception: {symbol} {side} — {e}")
            return self._failed_result(
                symbol, side, qty, expected_price,
                f"exception: {e}", client_order_id,
            )

    async def _query_order(
        self, inst_id: str, ord_id: str, symbol: str, side: str,
        qty: float, expected_price: float, client_order_id: str,
        *, use_client_id: bool = False,
    ) -> TradeResult:
        """Query OKX order details for fill information."""
        session = await self._ensure_session()
        if use_client_id:
            path = f"/api/v5/trade/order?instId={inst_id}&clOrdId={ord_id[:32]}"
        else:
            path = f"/api/v5/trade/order?instId={inst_id}&ordId={ord_id}"
        headers = self._sign_headers("GET", path)
        url = f"{_BASE_URL}{path}"

        # Retry up to 3 times (order may not settle instantly)
        for attempt in range(3):
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()

            if data.get("code") != "0":
                if attempt < 2:
                    await asyncio.sleep(0.5)
                    continue
                return self._failed_result(
                    symbol, side, qty, expected_price,
                    f"order query failed: {data.get('msg', data)}",
                    client_order_id,
                )

            order = data.get("data", [{}])[0]
            state = order.get("state", "")

            if state in ("filled", "partially_filled"):
                avg_px = float(order.get("avgPx", "0") or "0")
                fill_sz = float(order.get("fillSz", "0") or "0")
                fee = float(order.get("fee", "0") or "0")
                fee_ccy = order.get("feeCcy", "")

                # OKX fee is negative (deduction), take absolute
                fee = abs(fee)

                # Determine fee rate
                notional = fill_sz * avg_px if avg_px > 0 else 0
                fee_rate = fee / notional if notional > 0 and fee_ccy == "USDT" else 0

                return TradeResult(
                    success=True,
                    order_id=ord_id,
                    client_order_id=client_order_id,
                    exchange=self.exchange_name,
                    symbol=symbol,
                    side=side,
                    requested_qty=qty,
                    filled_qty=fill_sz,
                    requested_price=expected_price,
                    actual_avg_price=avg_px,
                    actual_fee=fee,
                    fee_rate=fee_rate,
                    fee_currency=fee_ccy,
                    is_maker=False,
                    raw_response=order,
                    timestamp=time.time(),
                )

            if attempt < 2:
                await asyncio.sleep(0.5)

        return self._failed_result(
            symbol, side, qty, expected_price,
            f"order not filled after retries (state={state})",
            client_order_id,
        )

    async def get_order_status(self, symbol: str, order_id: str) -> TradeResult:
        """Query order by client order ID or exchange order ID."""
        inst_id = self.format_symbol(symbol)
        is_client_id = order_id.startswith("coirna-")

        return await self._query_order(
            inst_id, order_id, symbol, "", 0, 0, order_id,
            use_client_id=is_client_id,
        )

    async def get_balance(self, asset: str) -> float:
        """Get available balance for an asset."""
        session = await self._ensure_session()

        path = "/api/v5/account/balance"
        headers = self._sign_headers("GET", path)
        url = f"{_BASE_URL}{path}"

        async with session.get(url, headers=headers) as resp:
            data = await resp.json()

        if data.get("code") != "0":
            return 0.0

        for detail in data.get("data", [{}])[0].get("details", []):
            if detail.get("ccy") == asset:
                return float(detail.get("availBal", "0") or "0")

        return 0.0

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
