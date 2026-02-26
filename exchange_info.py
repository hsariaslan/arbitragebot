"""
Exchange trading rules fetcher and cache.

Fetches lot sizes, tick sizes, min notionals, and precision info from
all exchange REST APIs at startup. Provides rounding utilities used by
balance.py and monitor.py to make the simulation match real exchange
behavior.

Addresses discrepancies: D-01 (Lot Size), D-02 (Min Notional), D-03 (Tick Size).
See DISCREPANCIES.md for details.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from pathlib import Path

import aiohttp

from config import (
    SYMBOLS,
    BINANCE_EXCHANGE_NAME,
    OKX_EXCHANGE_NAME,
    BYBIT_EXCHANGE_NAME,
    BITGET_EXCHANGE_NAME,
    KUCOIN_EXCHANGE_NAME,
    GATEIO_EXCHANGE_NAME,
)

logger = logging.getLogger(__name__)

# REST API base URLs for fetching symbol info (public, no auth)
_API_URLS = {
    BINANCE_EXCHANGE_NAME: "https://api.binance.com/api/v3/exchangeInfo",
    OKX_EXCHANGE_NAME: "https://www.okx.com/api/v5/public/instruments",
    BYBIT_EXCHANGE_NAME: "https://api.bybit.com/v5/market/instruments-info",
    BITGET_EXCHANGE_NAME: "https://api.bitget.com/api/v2/spot/public/symbols",
    KUCOIN_EXCHANGE_NAME: "https://api.kucoin.com/api/v1/symbols",
    GATEIO_EXCHANGE_NAME: "https://api.gateio.ws/api/v4/spot/currency_pairs",
}

# Persist cache here as fallback if API calls fail
_CACHE_PATH = Path("state/exchange_info.json")

# Refresh interval (24 hours — rules rarely change)
_REFRESH_INTERVAL = 86400.0


@dataclass
class SymbolRules:
    """Trading rules for a symbol on a specific exchange."""

    symbol: str                     # e.g. "BTCUSDT"
    exchange: str                   # e.g. "Binance"
    lot_size_step: Decimal          # qty step (e.g., Decimal("0.00001"))
    min_qty: Decimal                # minimum order qty in base
    tick_size: Decimal              # price step (e.g., Decimal("0.01"))
    min_notional: Decimal           # min order value in USDT
    base_precision: int             # decimal places for qty
    quote_precision: int            # decimal places for price

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "lot_size_step": str(self.lot_size_step),
            "min_qty": str(self.min_qty),
            "tick_size": str(self.tick_size),
            "min_notional": str(self.min_notional),
            "base_precision": self.base_precision,
            "quote_precision": self.quote_precision,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SymbolRules:
        return cls(
            symbol=d["symbol"],
            exchange=d["exchange"],
            lot_size_step=Decimal(d["lot_size_step"]),
            min_qty=Decimal(d["min_qty"]),
            tick_size=Decimal(d["tick_size"]),
            min_notional=Decimal(d["min_notional"]),
            base_precision=d["base_precision"],
            quote_precision=d["quote_precision"],
        )


def _decimal_places(step: Decimal) -> int:
    """Count decimal places from a step size like Decimal('0.001') -> 3."""
    if step >= 1:
        return 0
    sign, digits, exponent = step.as_tuple()
    return max(0, -exponent)


class ExchangeInfoManager:
    """Fetches and caches trading rules from all active exchanges."""

    def __init__(self, exchanges: list[str] | None = None) -> None:
        # Only fetch for exchanges we actually use
        self._exchanges = exchanges or list(_API_URLS.keys())
        self._rules: dict[str, SymbolRules] = {}  # key: "Exchange:SYMBOL"
        self._last_fetch: float = 0.0
        self._fetch_count: int = 0

    # ─── Public API ──────────────────────────────────────────────

    async def fetch_all(self) -> None:
        """Fetch trading rules from all configured exchanges.

        Called at startup before optimizer discovery begins.
        Falls back to cached state/exchange_info.json if APIs fail.
        """
        t0 = time.time()
        logger.info("[ExchangeInfo] Fetching trading rules from %d exchanges...",
                     len(self._exchanges))

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = []
            for ex in self._exchanges:
                if ex in _API_URLS:
                    tasks.append(self._fetch_exchange(session, ex))
            results = await asyncio.gather(*tasks, return_exceptions=True)

        fetched = 0
        failed_exchanges: list[str] = []
        for ex, result in zip(self._exchanges, results):
            if isinstance(result, Exception):
                logger.warning("[ExchangeInfo] %s fetch failed: %s", ex, result)
                failed_exchanges.append(ex)
            elif isinstance(result, int):
                fetched += result

        # Load cache for failed exchanges
        if failed_exchanges:
            cached = self._load_cache()
            restored = 0
            for key, rules in cached.items():
                if rules.exchange in failed_exchanges and key not in self._rules:
                    self._rules[key] = rules
                    restored += 1
            if restored:
                logger.info("[ExchangeInfo] Restored %d rules from cache for: %s",
                            restored, ", ".join(failed_exchanges))

        elapsed = time.time() - t0
        self._last_fetch = time.time()
        self._fetch_count += 1

        # Save to cache
        self._save_cache()

        # Log summary
        exchange_counts: dict[str, int] = {}
        for rules in self._rules.values():
            exchange_counts[rules.exchange] = exchange_counts.get(rules.exchange, 0) + 1

        summary = ", ".join(f"{ex}={cnt}" for ex, cnt in sorted(exchange_counts.items()))
        logger.info(
            "[ExchangeInfo] Loaded %d rules in %.1fs (%s). "
            "Coverage: %d/%d symbols across %d exchanges.",
            len(self._rules), elapsed, summary,
            len(self._get_covered_symbols()), len(SYMBOLS),
            len(exchange_counts),
        )

        # Warn about missing symbols
        covered = self._get_covered_symbols()
        missing = set(SYMBOLS) - covered
        if missing:
            logger.warning(
                "[ExchangeInfo] Missing rules for %d symbols: %s",
                len(missing),
                ", ".join(sorted(s.replace("USDT", "") for s in missing)),
            )

    def get_rules(self, exchange: str, symbol: str) -> SymbolRules | None:
        """Get trading rules for a symbol on a specific exchange."""
        return self._rules.get(f"{exchange}:{symbol}")

    def round_quantity(self, exchange: str, symbol: str, qty: Decimal) -> Decimal:
        """Round a quantity DOWN to the exchange's lot size step.

        Uses ROUND_DOWN (truncation) because exchanges reject quantities
        that exceed the step precision, and we can't buy more than we
        have USDT for.
        """
        rules = self.get_rules(exchange, symbol)
        if not rules or rules.lot_size_step <= 0:
            return qty

        # Truncate to lot_size_step: floor(qty / step) * step
        step = rules.lot_size_step
        rounded = (qty / step).to_integral_value(rounding=ROUND_DOWN) * step
        return rounded

    def round_price(self, exchange: str, symbol: str, price: Decimal) -> Decimal:
        """Round a price to the exchange's tick size."""
        rules = self.get_rules(exchange, symbol)
        if not rules or rules.tick_size <= 0:
            return price

        step = rules.tick_size
        rounded = (price / step).to_integral_value(rounding=ROUND_DOWN) * step
        return rounded

    def check_min_notional(self, exchange: str, symbol: str,
                           qty: Decimal, price: Decimal) -> bool:
        """Check if qty × price meets the exchange's min notional requirement.

        Returns True if the order meets the minimum, False if it would be rejected.
        """
        rules = self.get_rules(exchange, symbol)
        if not rules:
            return True  # no rules = assume ok

        notional = qty * price
        return notional >= rules.min_notional

    def check_min_qty(self, exchange: str, symbol: str, qty: Decimal) -> bool:
        """Check if qty meets the exchange's minimum order quantity."""
        rules = self.get_rules(exchange, symbol)
        if not rules:
            return True
        return qty >= rules.min_qty

    @property
    def rules_count(self) -> int:
        return len(self._rules)

    @property
    def last_fetch_time(self) -> float:
        return self._last_fetch

    def needs_refresh(self) -> bool:
        return time.time() - self._last_fetch > _REFRESH_INTERVAL

    async def refresh_if_needed(self) -> None:
        """Background refresh — call periodically (e.g., from optimizer loop)."""
        if self.needs_refresh():
            logger.info("[ExchangeInfo] Refreshing trading rules (24h interval)...")
            await self.fetch_all()

    # ─── Per-Exchange Fetchers ───────────────────────────────────

    async def _fetch_exchange(self, session: aiohttp.ClientSession,
                              exchange: str) -> int:
        """Fetch rules for one exchange. Returns count of symbols loaded."""
        try:
            if exchange == BINANCE_EXCHANGE_NAME:
                return await self._fetch_binance(session)
            elif exchange == OKX_EXCHANGE_NAME:
                return await self._fetch_okx(session)
            elif exchange == BYBIT_EXCHANGE_NAME:
                return await self._fetch_bybit(session)
            elif exchange == BITGET_EXCHANGE_NAME:
                return await self._fetch_bitget(session)
            elif exchange == KUCOIN_EXCHANGE_NAME:
                return await self._fetch_kucoin(session)
            elif exchange == GATEIO_EXCHANGE_NAME:
                return await self._fetch_gateio(session)
            else:
                logger.debug("[ExchangeInfo] No fetcher for %s", exchange)
                return 0
        except Exception as e:
            logger.warning("[ExchangeInfo] %s fetch error: %s", exchange, e)
            raise

    async def _fetch_binance(self, session: aiohttp.ClientSession) -> int:
        """Binance: GET /api/v3/exchangeInfo — returns all symbols at once."""
        url = _API_URLS[BINANCE_EXCHANGE_NAME]
        async with session.get(url) as resp:
            data = await resp.json()

        target_symbols = set(SYMBOLS)
        count = 0

        for sym_info in data.get("symbols", []):
            symbol = sym_info.get("symbol", "")
            if symbol not in target_symbols:
                continue

            lot_step = Decimal("1")
            min_qty = Decimal("0")
            tick_size = Decimal("1")
            min_notional = Decimal("5")  # Binance default

            for f in sym_info.get("filters", []):
                ft = f.get("filterType", "")
                if ft == "LOT_SIZE":
                    lot_step = Decimal(f.get("stepSize", "1"))
                    min_qty = Decimal(f.get("minQty", "0"))
                elif ft == "PRICE_FILTER":
                    tick_size = Decimal(f.get("tickSize", "1"))
                elif ft in ("NOTIONAL", "MIN_NOTIONAL"):
                    min_notional = Decimal(f.get("minNotional", "5"))

            rules = SymbolRules(
                symbol=symbol,
                exchange=BINANCE_EXCHANGE_NAME,
                lot_size_step=lot_step,
                min_qty=min_qty,
                tick_size=tick_size,
                min_notional=min_notional,
                base_precision=_decimal_places(lot_step),
                quote_precision=_decimal_places(tick_size),
            )
            self._rules[f"{BINANCE_EXCHANGE_NAME}:{symbol}"] = rules
            count += 1

        logger.info("[ExchangeInfo] Binance: loaded %d/%d symbols", count, len(target_symbols))
        return count

    async def _fetch_okx(self, session: aiohttp.ClientSession) -> int:
        """OKX: GET /api/v5/public/instruments?instType=SPOT — returns all spot instruments."""
        url = f"{_API_URLS[OKX_EXCHANGE_NAME]}?instType=SPOT"
        async with session.get(url) as resp:
            data = await resp.json()

        if data.get("code") != "0":
            logger.warning("[ExchangeInfo] OKX API error: %s", data.get("msg"))
            return 0

        # Map OKX instId format (BTC-USDT) to our format (BTCUSDT)
        target_map: dict[str, str] = {}
        for sym in SYMBOLS:
            base = sym.replace("USDT", "")
            okx_id = f"{base}-USDT"
            target_map[okx_id] = sym

        count = 0
        for inst in data.get("data", []):
            inst_id = inst.get("instId", "")
            symbol = target_map.get(inst_id)
            if not symbol:
                continue

            lot_sz = Decimal(inst.get("lotSz", "1"))
            tick_sz = Decimal(inst.get("tickSz", "1"))
            min_sz = Decimal(inst.get("minSz", "0"))

            # OKX doesn't have a direct min_notional field.
            # Approximate: min_sz * typical_price, or use a safe default.
            # We'll use min_sz as min_qty and set a conservative min_notional.
            min_notional = Decimal("1")  # OKX general minimum

            rules = SymbolRules(
                symbol=symbol,
                exchange=OKX_EXCHANGE_NAME,
                lot_size_step=lot_sz,
                min_qty=min_sz,
                tick_size=tick_sz,
                min_notional=min_notional,
                base_precision=_decimal_places(lot_sz),
                quote_precision=_decimal_places(tick_sz),
            )
            self._rules[f"{OKX_EXCHANGE_NAME}:{symbol}"] = rules
            count += 1

        logger.info("[ExchangeInfo] OKX: loaded %d/%d symbols", count, len(SYMBOLS))
        return count

    async def _fetch_bybit(self, session: aiohttp.ClientSession) -> int:
        """Bybit: GET /v5/market/instruments-info?category=spot — all spot instruments."""
        url = f"{_API_URLS[BYBIT_EXCHANGE_NAME]}?category=spot"
        async with session.get(url) as resp:
            data = await resp.json()

        if data.get("retCode") != 0:
            logger.warning("[ExchangeInfo] Bybit API error: %s", data.get("retMsg"))
            return 0

        target_symbols = set(SYMBOLS)
        count = 0

        for item in data.get("result", {}).get("list", []):
            symbol = item.get("symbol", "")
            if symbol not in target_symbols:
                continue

            lot_filter = item.get("lotSizeFilter", {})
            price_filter = item.get("priceFilter", {})

            # basePrecision serves as the qty step on Bybit
            lot_step = Decimal(lot_filter.get("basePrecision", "1"))
            min_qty = Decimal(lot_filter.get("minOrderQty", "0"))
            min_order_amt = Decimal(lot_filter.get("minOrderAmt", "1"))
            tick_size = Decimal(price_filter.get("tickSize", "1"))

            rules = SymbolRules(
                symbol=symbol,
                exchange=BYBIT_EXCHANGE_NAME,
                lot_size_step=lot_step,
                min_qty=min_qty,
                tick_size=tick_size,
                min_notional=min_order_amt,
                base_precision=_decimal_places(lot_step),
                quote_precision=_decimal_places(tick_size),
            )
            self._rules[f"{BYBIT_EXCHANGE_NAME}:{symbol}"] = rules
            count += 1

        logger.info("[ExchangeInfo] Bybit: loaded %d/%d symbols", count, len(target_symbols))
        return count

    async def _fetch_bitget(self, session: aiohttp.ClientSession) -> int:
        """Bitget: GET /api/v2/spot/public/symbols — all spot symbols."""
        url = _API_URLS[BITGET_EXCHANGE_NAME]
        async with session.get(url) as resp:
            data = await resp.json()

        if data.get("code") != "00000":
            logger.warning("[ExchangeInfo] Bitget API error: %s", data.get("msg"))
            return 0

        target_symbols = set(SYMBOLS)
        count = 0

        for sym_info in data.get("data", []):
            # Bitget symbol format: "BTCUSDT" (same as ours)
            symbol = sym_info.get("symbol", "")
            if symbol not in target_symbols:
                continue

            # Bitget gives precision as integers (decimal places)
            qty_prec = int(sym_info.get("quantityPrecision", "0"))
            price_prec = int(sym_info.get("pricePrecision", "0"))
            lot_step = Decimal(10) ** Decimal(-qty_prec)
            tick_size = Decimal(10) ** Decimal(-price_prec)

            min_trade_amount = sym_info.get("minTradeAmount", "0")
            min_trade_usdt = sym_info.get("minTradeUSDT", "1")

            # min_qty from minTradeAmount (base currency)
            try:
                min_qty = Decimal(min_trade_amount) if min_trade_amount != "0" else Decimal("0")
            except InvalidOperation:
                min_qty = Decimal("0")

            # min_notional from minTradeUSDT
            try:
                min_notional = Decimal(min_trade_usdt)
            except InvalidOperation:
                min_notional = Decimal("1")

            rules = SymbolRules(
                symbol=symbol,
                exchange=BITGET_EXCHANGE_NAME,
                lot_size_step=lot_step,
                min_qty=min_qty,
                tick_size=tick_size,
                min_notional=min_notional,
                base_precision=qty_prec,
                quote_precision=price_prec,
            )
            self._rules[f"{BITGET_EXCHANGE_NAME}:{symbol}"] = rules
            count += 1

        logger.info("[ExchangeInfo] Bitget: loaded %d/%d symbols", count, len(target_symbols))
        return count

    async def _fetch_kucoin(self, session: aiohttp.ClientSession) -> int:
        """KuCoin: GET /api/v1/symbols — returns all symbols at once."""
        url = _API_URLS[KUCOIN_EXCHANGE_NAME]
        async with session.get(url) as resp:
            data = await resp.json()

        if data.get("code") != "200000":
            logger.warning("[ExchangeInfo] KuCoin API error: %s", data.get("msg"))
            return 0

        # KuCoin symbol format: "BTC-USDT" -> map to "BTCUSDT"
        target_map: dict[str, str] = {}
        for sym in SYMBOLS:
            base = sym.replace("USDT", "")
            kucoin_id = f"{base}-USDT"
            target_map[kucoin_id] = sym

        count = 0
        for sym_info in data.get("data", []):
            kucoin_sym = sym_info.get("symbol", "")
            symbol = target_map.get(kucoin_sym)
            if not symbol:
                continue

            lot_step = Decimal(sym_info.get("baseIncrement", "1"))
            tick_size = Decimal(sym_info.get("priceIncrement", "1"))
            min_qty = Decimal(sym_info.get("baseMinSize", "0"))
            min_notional = Decimal(sym_info.get("quoteMinSize", "0.1"))

            rules = SymbolRules(
                symbol=symbol,
                exchange=KUCOIN_EXCHANGE_NAME,
                lot_size_step=lot_step,
                min_qty=min_qty,
                tick_size=tick_size,
                min_notional=min_notional,
                base_precision=_decimal_places(lot_step),
                quote_precision=_decimal_places(tick_size),
            )
            self._rules[f"{KUCOIN_EXCHANGE_NAME}:{symbol}"] = rules
            count += 1

        logger.info("[ExchangeInfo] KuCoin: loaded %d/%d symbols", count, len(SYMBOLS))
        return count

    async def _fetch_gateio(self, session: aiohttp.ClientSession) -> int:
        """Gate.io: GET /api/v4/spot/currency_pairs — returns all spot pairs."""
        url = _API_URLS[GATEIO_EXCHANGE_NAME]
        async with session.get(url) as resp:
            data = await resp.json()

        # Gate.io symbol format: "BTC_USDT" -> map to "BTCUSDT"
        target_map: dict[str, str] = {}
        for sym in SYMBOLS:
            base = sym.replace("USDT", "")
            gate_id = f"{base}_USDT"
            target_map[gate_id] = sym

        count = 0
        for pair_info in data:
            pair_id = pair_info.get("id", "")
            symbol = target_map.get(pair_id)
            if not symbol:
                continue

            # amount_precision/precision are integer decimal places (like Bitget)
            qty_prec = int(pair_info.get("amount_precision", 0))
            price_prec = int(pair_info.get("precision", 0))
            lot_step = Decimal(10) ** Decimal(-qty_prec)
            tick_size = Decimal(10) ** Decimal(-price_prec)

            try:
                min_qty = Decimal(pair_info.get("min_base_amount", "0"))
            except InvalidOperation:
                min_qty = Decimal("0")

            try:
                min_notional = Decimal(pair_info.get("min_quote_amount", "1"))
            except InvalidOperation:
                min_notional = Decimal("1")

            rules = SymbolRules(
                symbol=symbol,
                exchange=GATEIO_EXCHANGE_NAME,
                lot_size_step=lot_step,
                min_qty=min_qty,
                tick_size=tick_size,
                min_notional=min_notional,
                base_precision=qty_prec,
                quote_precision=price_prec,
            )
            self._rules[f"{GATEIO_EXCHANGE_NAME}:{symbol}"] = rules
            count += 1

        logger.info("[ExchangeInfo] Gate.io: loaded %d/%d symbols", count, len(SYMBOLS))
        return count

    # ─── Cache Persistence ───────────────────────────────────────

    def _save_cache(self) -> None:
        """Persist rules to disk as JSON fallback."""
        try:
            _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            cache = {
                "fetched_at": self._last_fetch,
                "rules": {k: v.to_dict() for k, v in self._rules.items()},
            }
            tmp = _CACHE_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(cache, indent=2))
            tmp.replace(_CACHE_PATH)
        except Exception as e:
            logger.warning("[ExchangeInfo] Cache save failed: %s", e)

    def _load_cache(self) -> dict[str, SymbolRules]:
        """Load rules from disk cache."""
        if not _CACHE_PATH.exists():
            return {}
        try:
            raw = json.loads(_CACHE_PATH.read_text())
            rules = {}
            for key, d in raw.get("rules", {}).items():
                rules[key] = SymbolRules.from_dict(d)
            age = time.time() - raw.get("fetched_at", 0)
            logger.info("[ExchangeInfo] Loaded %d cached rules (age: %.0fh)",
                        len(rules), age / 3600)
            return rules
        except Exception as e:
            logger.warning("[ExchangeInfo] Cache load failed: %s", e)
            return {}

    # ─── D-16: Withdrawal Fee Validation ────────────────────────

    async def validate_withdrawal_fees(self, transfer_fee_mgr=None) -> None:
        """Fetch actual USDT withdrawal fees from exchanges and compare with config.

        Queries public APIs for OKX, Bitget, KuCoin. Binance and Bybit require
        auth — skipped here (validated in demo_fetcher if keys are available).
        Logs mismatches but does NOT override configured rates — production
        config rates are used for simulation to ensure realistic cost estimates.
        """
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = []
            exchange_names = []

            if OKX_EXCHANGE_NAME in self._exchanges:
                tasks.append(self._fetch_okx_withdrawal_fee(session))
                exchange_names.append(OKX_EXCHANGE_NAME)
            if BITGET_EXCHANGE_NAME in self._exchanges:
                tasks.append(self._fetch_bitget_withdrawal_fee(session))
                exchange_names.append(BITGET_EXCHANGE_NAME)
            if KUCOIN_EXCHANGE_NAME in self._exchanges:
                tasks.append(self._fetch_kucoin_withdrawal_fee(session))
                exchange_names.append(KUCOIN_EXCHANGE_NAME)

            results = await asyncio.gather(*tasks, return_exceptions=True)

        for ex, result in zip(exchange_names, results):
            if isinstance(result, Exception):
                logger.warning("[WithdrawalFees] %s fee query failed: %s", ex, result)
                continue
            if result is None:
                continue

            actual_fee = result
            configured = transfer_fee_mgr.get_withdrawal_fee(ex) if transfer_fee_mgr else 0.0

            if abs(actual_fee - configured) < 0.001:
                logger.info(
                    "[WithdrawalFees] %s: configured=$%.3f, actual=$%.3f — OK",
                    ex, configured, actual_fee,
                )
            else:
                logger.warning(
                    "[WithdrawalFees] %s: production=$%.3f, actual=$%.3f — "
                    "MISMATCH (simulation keeps production rate)",
                    ex, configured, actual_fee,
                )

        # Log exchanges we can't validate
        skip = []
        for ex in (BINANCE_EXCHANGE_NAME, BYBIT_EXCHANGE_NAME, GATEIO_EXCHANGE_NAME):
            if ex in self._exchanges:
                skip.append(ex)
        if skip:
            logger.info(
                "[WithdrawalFees] Skipped %s (requires auth — "
                "validated via demo_fetcher if keys available)",
                ", ".join(skip),
            )

    async def _fetch_okx_withdrawal_fee(
        self, session: aiohttp.ClientSession
    ) -> float | None:
        """OKX: GET /api/v5/asset/currencies — public endpoint."""
        try:
            url = "https://www.okx.com/api/v5/asset/currencies?ccy=USDT"
            async with session.get(url) as resp:
                data = await resp.json()

            if data.get("code") != "0":
                logger.warning("[WithdrawalFees] OKX: %s", data.get("msg", data))
                return None

            # Find cheapest withdrawal fee across all chains
            best_fee = float("inf")
            best_chain = ""
            for chain_info in data.get("data", []):
                if chain_info.get("ccy") != "USDT":
                    continue
                can_wd = chain_info.get("canWd", False)
                if not can_wd and can_wd != "true":
                    continue
                fee_str = chain_info.get("minFee", "")
                if fee_str:
                    fee = float(fee_str)
                    chain = chain_info.get("chain", "unknown")
                    if fee < best_fee:
                        best_fee = fee
                        best_chain = chain

            if best_fee < float("inf"):
                logger.info("[WithdrawalFees] OKX cheapest: $%.4f (%s)", best_fee, best_chain)
                return best_fee
            return None
        except Exception as e:
            logger.warning("[WithdrawalFees] OKX query error: %s", e)
            return None

    async def _fetch_bitget_withdrawal_fee(
        self, session: aiohttp.ClientSession
    ) -> float | None:
        """Bitget: GET /api/v2/spot/public/coins — public endpoint."""
        try:
            url = "https://api.bitget.com/api/v2/spot/public/coins?coin=USDT"
            async with session.get(url) as resp:
                data = await resp.json()

            if data.get("code") != "00000":
                logger.warning("[WithdrawalFees] Bitget: %s", data.get("msg", data))
                return None

            best_fee = float("inf")
            best_chain = ""
            for coin_info in data.get("data", []):
                if coin_info.get("coin") != "USDT":
                    continue
                for chain in coin_info.get("chains", []):
                    withdrawable = chain.get("withdrawable", "")
                    if withdrawable != "true" and withdrawable is not True:
                        continue
                    fee_str = chain.get("withdrawFee", "")
                    if fee_str:
                        fee = float(fee_str)
                        chain_name = chain.get("chain", "unknown")
                        if fee < best_fee:
                            best_fee = fee
                            best_chain = chain_name

            if best_fee < float("inf"):
                logger.info("[WithdrawalFees] Bitget cheapest: $%.4f (%s)", best_fee, best_chain)
                return best_fee
            return None
        except Exception as e:
            logger.warning("[WithdrawalFees] Bitget query error: %s", e)
            return None

    async def _fetch_kucoin_withdrawal_fee(
        self, session: aiohttp.ClientSession
    ) -> float | None:
        """KuCoin: GET /api/v1/currencies/USDT — public endpoint."""
        try:
            url = "https://api.kucoin.com/api/v1/currencies/USDT"
            async with session.get(url) as resp:
                data = await resp.json()

            if data.get("code") != "200000":
                logger.warning("[WithdrawalFees] KuCoin: %s", data.get("msg", data))
                return None

            coin_data = data.get("data", {})
            best_fee = float("inf")
            best_chain = ""
            for chain in coin_data.get("chains", []):
                is_withdraw = chain.get("isWithdrawEnabled", False)
                if not is_withdraw:
                    continue
                fee_str = chain.get("withdrawalMinFee", "")
                if fee_str:
                    fee = float(fee_str)
                    chain_name = chain.get("chainName", "unknown")
                    if fee < best_fee:
                        best_fee = fee
                        best_chain = chain_name

            if best_fee < float("inf"):
                logger.info("[WithdrawalFees] KuCoin cheapest: $%.4f (%s)", best_fee, best_chain)
                return best_fee
            return None
        except Exception as e:
            logger.warning("[WithdrawalFees] KuCoin query error: %s", e)
            return None

    # ─── Helpers ─────────────────────────────────────────────────

    def _get_covered_symbols(self) -> set[str]:
        """Return set of symbols that have rules on at least one exchange."""
        covered: set[str] = set()
        for rules in self._rules.values():
            covered.add(rules.symbol)
        return covered
