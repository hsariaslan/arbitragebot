"""
Demo/testnet portfolio fetcher for Binance, OKX, and Bybit.

Periodically polls exchange REST APIs to fetch real demo/testnet balances,
compares them against the simulation's BalanceTracker, and logs discrepancies
with root cause analysis.
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlencode

import aiohttp

from config import (
    BINANCE_TESTNET_API_KEY,
    BINANCE_TESTNET_API_SECRET,
    BYBIT_DEMO_API_KEY,
    BYBIT_DEMO_API_SECRET,
    OKX_DEMO_API_KEY,
    OKX_DEMO_API_SECRET,
    OKX_DEMO_PASSPHRASE,
    SYMBOLS,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fee_manager import FeeManager

logger = logging.getLogger(__name__)

# All known USDT trading symbols → coin name mapping
_SYMBOL_TO_COIN: dict[str, str] = {}
_COIN_TO_SYMBOL: dict[str, str] = {}
for _sym in SYMBOLS:
    _coin = _sym.replace("USDT", "")
    _SYMBOL_TO_COIN[_sym] = _coin
    _COIN_TO_SYMBOL[_coin] = _sym


@dataclass
class DemoBalance:
    """Snapshot of a single exchange's demo/testnet portfolio."""

    exchange: str
    usdt: float = 0.0
    crypto: dict[str, float] = field(default_factory=dict)  # symbol -> quantity
    total_value_usd: float = 0.0
    fetched_at: float = 0.0
    error: str | None = None


@dataclass
class Discrepancy:
    """A detected mismatch between simulation and demo."""

    timestamp: float
    exchange: str
    discrepancy_type: str
    symbol: str  # "USDT" or e.g. "BTCUSDT"
    sim_value: float
    demo_value: float
    diff_abs: float
    diff_pct: float
    root_cause: str


class DemoPortfolioFetcher:
    """
    Periodically polls demo/testnet REST APIs for real portfolio data
    and compares against the simulation's BalanceTracker.
    """

    def __init__(
        self,
        balance_tracker: "BalanceTracker",
        fetchers: list,
        poll_interval: float = 15.0,
        max_discrepancies: int = 200,
        fee_manager: "FeeManager | None" = None,
    ) -> None:
        from balance import BalanceTracker

        self._balance: BalanceTracker = balance_tracker
        self._fee_manager = fee_manager
        self._fetchers = fetchers
        self._poll_interval = poll_interval
        self._max_discrepancies = max_discrepancies
        self._running = False

        # State
        self.latest_balances: dict[str, DemoBalance] = {}
        self.recent_discrepancies: list[Discrepancy] = []
        self.total_discrepancy_count: int = 0
        self.last_fetch_time: float = 0.0

        # Baseline snapshots: first-fetch balances per exchange.
        # Used to compute deltas (current - baseline) so pre-funded
        # testnet money is subtracted and only bot activity is measured.
        self._baselines: dict[str, DemoBalance] = {}

        # Per-exchange backoff (for rate limiting)
        self._backoff: dict[str, float] = {}

        # Set of exchanges that have demo executors (set by run.py)
        self._demo_exchanges: set[str] = set()

        # Fee rate validation: track which exchanges have been validated (D-04)
        self._fee_validated: dict[str, bool] = {}
        # Actual demo/testnet fee rates (may differ from production config)
        self._demo_fee_rates: dict[str, float] = {}

        # Determine which exchanges have keys configured
        self._configured: dict[str, bool] = {
            "Binance": bool(BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET),
            "OKX": bool(OKX_DEMO_API_KEY and OKX_DEMO_API_SECRET and OKX_DEMO_PASSPHRASE),
            "Bybit": bool(BYBIT_DEMO_API_KEY and BYBIT_DEMO_API_SECRET),
        }

        configured_list = [ex for ex, ok in self._configured.items() if ok]
        if configured_list:
            logger.info(f"[DemoCompare] Configured for: {', '.join(configured_list)}")

    def set_demo_exchanges(self, exchanges: set[str]) -> None:
        """Set which exchanges have active demo executors."""
        self._demo_exchanges = exchanges

    @property
    def enabled(self) -> bool:
        return any(self._configured.values())

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        """Main polling loop."""
        if not self.enabled:
            return
        self._running = True
        logger.info(f"[DemoCompare] Starting demo portfolio polling (every {self._poll_interval}s)")
        while self._running:
            try:
                await self._poll_all()
            except Exception as e:
                logger.error(f"[DemoCompare] Poll error: {e}")
            await asyncio.sleep(self._poll_interval)

    async def _poll_all(self) -> None:
        """Fetch all configured demo exchanges in parallel."""
        now = time.time()
        prices = self._get_prices()
        tasks = []

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if self._configured["Binance"] and now >= self._backoff.get("Binance", 0):
                tasks.append(self._fetch_binance(session))
            if self._configured["OKX"] and now >= self._backoff.get("OKX", 0):
                tasks.append(self._fetch_okx(session))
            if self._configured["Bybit"] and now >= self._backoff.get("Bybit", 0):
                tasks.append(self._fetch_bybit(session))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # D-04: Fetch fee rates (one-time per exchange, after first successful balance fetch)
            fee_tasks = []
            if self._configured["OKX"] and not self._fee_validated.get("OKX"):
                fee_tasks.append(self._fetch_okx_fee_rate(session))
            if self._configured["Bybit"] and not self._fee_validated.get("Bybit"):
                fee_tasks.append(self._fetch_bybit_fee_rate(session))
            if fee_tasks:
                await asyncio.gather(*fee_tasks, return_exceptions=True)

        # Only count symbols the simulation actually holds (qty > 0).
        # Don't include active symbols with 0 holdings — their demo crypto
        # is pre-loaded testnet coins, not from our bot's trades.
        sim_held = set()
        for ex_crypto in self._balance.crypto.values():
            for sym, qty in ex_crypto.items():
                if qty > 0:
                    sim_held.add(sym)

        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"[DemoCompare] Fetch exception: {result}")
                continue
            if isinstance(result, DemoBalance):
                # Capture baseline on first successful fetch per exchange.
                # This records the pre-funded testnet balances so we can
                # compute deltas (current - baseline) = bot's actual activity.
                if result.exchange not in self._baselines and not result.error:
                    self._baselines[result.exchange] = DemoBalance(
                        exchange=result.exchange,
                        usdt=result.usdt,
                        crypto=dict(result.crypto),
                        fetched_at=result.fetched_at,
                    )
                    crypto_count = len(result.crypto)
                    crypto_usd = sum(
                        qty * prices.get(sym, 0.0)
                        for sym, qty in result.crypto.items()
                    )
                    logger.info(
                        f"[DemoCompare] Baseline captured for {result.exchange}: "
                        f"USDT=${result.usdt:,.2f}, {crypto_count} crypto "
                        f"positions (~${crypto_usd:,.0f})"
                    )

                # Compute total USD value as delta from baseline.
                # delta = (current - baseline) priced at current market prices.
                # This way pre-funded amounts are subtracted and only bot
                # activity is measured. Falls back to 0 if no baseline yet.
                result.total_value_usd = self.get_exchange_delta(
                    result.exchange, prices
                )

                self.latest_balances[result.exchange] = result
                self.last_fetch_time = now

                # Detect discrepancies
                discs = self._detect_discrepancies(result.exchange, result, prices)
                if discs:
                    self.recent_discrepancies.extend(discs)
                    self.total_discrepancy_count += len(discs)
                    # Trim to max
                    if len(self.recent_discrepancies) > self._max_discrepancies:
                        self.recent_discrepancies = self.recent_discrepancies[-self._max_discrepancies:]

    def _get_prices(self) -> dict[str, float]:
        """Get mid prices from WebSocket fetchers for all symbols."""
        prices: dict[str, float] = {}
        for sym in SYMBOLS:
            for fetcher in self._fetchers:
                state = fetcher.get_state()
                ps = state.get(sym)
                if ps and ps.bid and ps.ask:
                    try:
                        mid = (float(ps.bid) + float(ps.ask)) / 2.0
                        if mid > 0:
                            prices[sym] = mid
                            break
                    except (ValueError, TypeError):
                        continue
        return prices

    # ── Binance Testnet ──────────────────────────────────────────────────

    async def _fetch_binance(self, session: aiohttp.ClientSession) -> DemoBalance:
        """Fetch Binance testnet account balances."""
        try:
            ts = str(int(time.time() * 1000))
            params = {"timestamp": ts}
            query = urlencode(params)
            signature = hmac.new(
                BINANCE_TESTNET_API_SECRET.encode(), query.encode(), hashlib.sha256
            ).hexdigest()
            query += f"&signature={signature}"

            url = f"https://testnet.binance.vision/api/v3/account?{query}"
            headers = {"X-MBX-APIKEY": BINANCE_TESTNET_API_KEY}

            async with session.get(url, headers=headers) as resp:
                if resp.status == 429:
                    self._apply_backoff("Binance")
                    return DemoBalance(exchange="Binance", error="Rate limited", fetched_at=time.time())
                data = await resp.json()

            if "balances" not in data:
                error = data.get("msg", str(data))
                return DemoBalance(exchange="Binance", error=error, fetched_at=time.time())

            bal = DemoBalance(exchange="Binance", fetched_at=time.time())
            for item in data["balances"]:
                asset = item["asset"]
                free = float(item["free"])
                locked = float(item["locked"])
                total = free + locked
                if total <= 0:
                    continue
                if asset == "USDT":
                    bal.usdt = total
                elif asset in _COIN_TO_SYMBOL:
                    bal.crypto[_COIN_TO_SYMBOL[asset]] = total

            # D-04: Extract fee rate from account response (one-time validation)
            if not self._fee_validated.get("Binance"):
                commission_rates = data.get("commissionRates", {})
                taker_str = commission_rates.get("taker")
                if taker_str:
                    self._validate_fee_rate("Binance", float(taker_str))

            return bal

        except Exception as e:
            return DemoBalance(exchange="Binance", error=str(e), fetched_at=time.time())

    # ── OKX Demo ─────────────────────────────────────────────────────────

    async def _fetch_okx(self, session: aiohttp.ClientSession) -> DemoBalance:
        """Fetch OKX demo trading account balances."""
        try:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
                 f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
            method = "GET"
            path = "/api/v5/account/balance"
            sign_str = ts + method + path
            signature = base64.b64encode(
                hmac.new(
                    OKX_DEMO_API_SECRET.encode(), sign_str.encode(), hashlib.sha256
                ).digest()
            ).decode()

            headers = {
                "OK-ACCESS-KEY": OKX_DEMO_API_KEY,
                "OK-ACCESS-SIGN": signature,
                "OK-ACCESS-TIMESTAMP": ts,
                "OK-ACCESS-PASSPHRASE": OKX_DEMO_PASSPHRASE,
                "x-simulated-trading": "1",
            }

            url = f"https://www.okx.com{path}"
            async with session.get(url, headers=headers) as resp:
                if resp.status == 429:
                    self._apply_backoff("OKX")
                    return DemoBalance(exchange="OKX", error="Rate limited", fetched_at=time.time())
                data = await resp.json()

            if data.get("code") != "0":
                error = data.get("msg", str(data))
                return DemoBalance(exchange="OKX", error=error, fetched_at=time.time())

            bal = DemoBalance(exchange="OKX", fetched_at=time.time())
            details = data.get("data", [{}])[0].get("details", [])
            for item in details:
                ccy = item.get("ccy", "")
                avail = float(item.get("availBal", 0) or 0)
                frozen = float(item.get("frozenBal", 0) or 0)
                total = avail + frozen
                if total <= 0:
                    continue
                if ccy == "USDT":
                    bal.usdt = total
                elif ccy in _COIN_TO_SYMBOL:
                    bal.crypto[_COIN_TO_SYMBOL[ccy]] = total

            return bal

        except Exception as e:
            return DemoBalance(exchange="OKX", error=str(e), fetched_at=time.time())

    # ── Bybit Demo ───────────────────────────────────────────────────────

    async def _fetch_bybit(self, session: aiohttp.ClientSession) -> DemoBalance:
        """Fetch Bybit demo trading account balances."""
        try:
            ts = str(int(time.time() * 1000))
            recv_window = "5000"
            params = "accountType=UNIFIED"
            sign_str = f"{ts}{BYBIT_DEMO_API_KEY}{recv_window}{params}"
            signature = hmac.new(
                BYBIT_DEMO_API_SECRET.encode(), sign_str.encode(), hashlib.sha256
            ).hexdigest()

            headers = {
                "X-BAPI-API-KEY": BYBIT_DEMO_API_KEY,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-SIGN": signature,
                "X-BAPI-RECV-WINDOW": recv_window,
            }

            url = f"https://api-demo.bybit.com/v5/account/wallet-balance?{params}"
            async with session.get(url, headers=headers) as resp:
                if resp.status == 429:
                    self._apply_backoff("Bybit")
                    return DemoBalance(exchange="Bybit", error="Rate limited", fetched_at=time.time())
                data = await resp.json()

            if data.get("retCode") != 0:
                error = data.get("retMsg", str(data))
                return DemoBalance(exchange="Bybit", error=error, fetched_at=time.time())

            bal = DemoBalance(exchange="Bybit", fetched_at=time.time())
            coins = data.get("result", {}).get("list", [{}])[0].get("coin", [])
            for item in coins:
                coin = item.get("coin", "")
                wallet_bal = float(item.get("walletBalance", 0) or 0)
                if wallet_bal <= 0:
                    continue
                if coin == "USDT":
                    bal.usdt = wallet_bal
                elif coin in _COIN_TO_SYMBOL:
                    bal.crypto[_COIN_TO_SYMBOL[coin]] = wallet_bal

            return bal

        except Exception as e:
            return DemoBalance(exchange="Bybit", error=str(e), fetched_at=time.time())

    # ── Rate limit backoff ───────────────────────────────────────────────

    # ── Fee rate validation (D-04) ──────────────────────────────────────

    def _validate_fee_rate(self, exchange: str, actual_rate: float) -> None:
        """Compare actual demo/testnet fee rate with configured production rate.

        IMPORTANT: Demo/testnet fee rates often differ from production (e.g.,
        Binance testnet = 0%, OKX demo returns negative notation). We log the
        mismatch but NEVER override config — the simulation must use production
        rates to produce realistic profit estimates. However, in real mode,
        we feed actual rates to FeeManager.
        """
        self._fee_validated[exchange] = True
        # Some exchanges (OKX) return fee rates as negative values
        # (convention: negative = fee charged). Normalize to positive.
        actual_rate = abs(actual_rate)
        configured = self._fee_manager.get_taker_fee(exchange) if self._fee_manager else 0.001

        # Store demo rate separately (for demo execution cost estimation)
        self._demo_fee_rates[exchange] = actual_rate

        if abs(actual_rate - configured) < 1e-7:
            logger.info(
                f"[FeeValidation] {exchange}: configured={configured*100:.4f}%, "
                f"demo={actual_rate*100:.4f}% — OK (matches production)"
            )
            return

        # Mismatch: demo rate differs from production — log but do NOT override
        logger.warning(
            f"[FeeValidation] {exchange}: production={configured*100:.4f}%, "
            f"demo={actual_rate*100:.4f}% — MISMATCH (simulation keeps production rate)"
        )

        # Record as discrepancy
        self.recent_discrepancies.append(Discrepancy(
            timestamp=time.time(),
            exchange=exchange,
            discrepancy_type="fee_rate_mismatch",
            symbol="ALL",
            sim_value=configured * 100,
            demo_value=actual_rate * 100,
            diff_abs=abs(actual_rate - configured) * 100,
            diff_pct=((actual_rate - configured) / configured) * 100 if configured else 0,
            root_cause=f"Demo/testnet taker fee ({actual_rate*100:.4f}%) differs from "
                       f"production config ({configured*100:.4f}%). Simulation uses production rate.",
        ))
        self.total_discrepancy_count += 1

        # In real mode, feed actual API rate to FeeManager
        if self._fee_manager and self._fee_manager.real_mode:
            self._fee_manager.set_real_rate(exchange, actual_rate)

    async def _fetch_okx_fee_rate(self, session: aiohttp.ClientSession) -> None:
        """Fetch OKX actual taker fee rate (one-time after first successful balance fetch)."""
        if self._fee_validated.get("OKX"):
            return
        try:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
                 f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
            method = "GET"
            path = "/api/v5/account/trade-fee?instType=SPOT&instId=BTC-USDT"
            sign_str = ts + method + path
            signature = base64.b64encode(
                hmac.new(
                    OKX_DEMO_API_SECRET.encode(), sign_str.encode(), hashlib.sha256
                ).digest()
            ).decode()

            headers = {
                "OK-ACCESS-KEY": OKX_DEMO_API_KEY,
                "OK-ACCESS-SIGN": signature,
                "OK-ACCESS-TIMESTAMP": ts,
                "OK-ACCESS-PASSPHRASE": OKX_DEMO_PASSPHRASE,
                "x-simulated-trading": "1",
            }

            url = f"https://www.okx.com{path}"
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()

            if data.get("code") == "0" and data.get("data"):
                taker_str = data["data"][0].get("taker")
                if taker_str:
                    self._validate_fee_rate("OKX", float(taker_str))
            else:
                logger.warning(f"[FeeValidation] OKX fee rate query failed: {data.get('msg', data)}")
        except Exception as e:
            logger.warning(f"[FeeValidation] OKX fee rate query error: {e}")

    async def _fetch_bybit_fee_rate(self, session: aiohttp.ClientSession) -> None:
        """Fetch Bybit actual taker fee rate (one-time after first successful balance fetch)."""
        if self._fee_validated.get("Bybit"):
            return
        try:
            ts = str(int(time.time() * 1000))
            recv_window = "5000"
            params = "category=spot&symbol=BTCUSDT"
            sign_str = f"{ts}{BYBIT_DEMO_API_KEY}{recv_window}{params}"
            signature = hmac.new(
                BYBIT_DEMO_API_SECRET.encode(), sign_str.encode(), hashlib.sha256
            ).hexdigest()

            headers = {
                "X-BAPI-API-KEY": BYBIT_DEMO_API_KEY,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-SIGN": signature,
                "X-BAPI-RECV-WINDOW": recv_window,
            }

            url = f"https://api-demo.bybit.com/v5/account/fee-rate?{params}"
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()

            if data.get("retCode") == 0:
                fee_list = data.get("result", {}).get("list", [])
                if fee_list:
                    taker_str = fee_list[0].get("takerFeeRate")
                    if taker_str:
                        self._validate_fee_rate("Bybit", float(taker_str))
            else:
                logger.warning(f"[FeeValidation] Bybit fee rate query failed: {data.get('retMsg', data)}")
        except Exception as e:
            logger.warning(f"[FeeValidation] Bybit fee rate query error: {e}")

    # ── Rate limit backoff ───────────────────────────────────────────────

    def _apply_backoff(self, exchange: str) -> None:
        """Double the backoff for an exchange (max 120s)."""
        current = self._backoff.get(exchange, 0)
        delay = min(self._poll_interval * 2, 120.0) if current == 0 else min(current * 2, 120.0)
        self._backoff[exchange] = time.time() + delay
        logger.warning(f"[DemoCompare] {exchange} rate limited, backing off {delay:.0f}s")

    # ── Discrepancy detection ────────────────────────────────────────────

    # D-18: Grace period after sim trades to avoid false discrepancies
    _TRADE_GRACE_PERIOD: float = 30.0  # seconds

    def _detect_discrepancies(
        self, exchange: str, demo: DemoBalance, prices: dict[str, float]
    ) -> list[Discrepancy]:
        """Compare simulation vs baseline-adjusted demo balances.

        Uses baseline snapshots to subtract pre-funded testnet amounts.
        Only flags differences caused by actual trading activity divergence
        (slippage, fee differences, partial fills, etc.).
        Without a baseline, no discrepancies are reported.

        D-18: If a sim trade touched this exchange within the grace period,
        discrepancies are tagged as settling (root cause updated) to avoid
        false alarms from balance sync timing.
        """
        if demo.error:
            return []

        baseline = self._baselines.get(exchange)
        if not baseline:
            return []  # can't compare without baseline

        now = time.time()
        discrepancies: list[Discrepancy] = []

        # D-18: Check if a sim trade recently touched this exchange
        last_trade = self._balance.last_trade_time.get(exchange, 0.0)
        settling = (now - last_trade) < self._TRADE_GRACE_PERIOD if last_trade > 0 else False

        # 1. USDT balance — compare delta from baseline
        # demo_usdt_delta = what the bot changed on demo
        # If sim_usdt changed by the same amount, no discrepancy.
        demo_usdt_delta = demo.usdt - baseline.usdt
        sim_usdt = self._balance.usdt.get(exchange, 0.0)
        # adjusted = what demo USDT "should be" if it started at sim_usdt
        adjusted_demo_usdt = sim_usdt + demo_usdt_delta
        usdt_diff = abs(sim_usdt - adjusted_demo_usdt)
        if usdt_diff > 1.0:
            diff_pct = (sim_usdt - adjusted_demo_usdt) / max(abs(adjusted_demo_usdt), 1) * 100
            root = self._classify_root_cause(exchange, "USDT", sim_usdt, adjusted_demo_usdt, diff_pct)
            dtype = "balance_mismatch"
            if settling:
                dtype = "balance_mismatch_settling"
                settle_age = now - last_trade
                root = f"[Settling {settle_age:.0f}s ago] {root}"
            disc = Discrepancy(
                timestamp=now,
                exchange=exchange,
                discrepancy_type=dtype,
                symbol="USDT",
                sim_value=sim_usdt,
                demo_value=adjusted_demo_usdt,
                diff_abs=usdt_diff,
                diff_pct=diff_pct,
                root_cause=root,
            )
            discrepancies.append(disc)
            logger.info(
                f"[DemoCompare] {exchange} USDT {dtype}: "
                f"sim=${sim_usdt:.2f} adjusted_demo=${adjusted_demo_usdt:.2f} "
                f"diff=${usdt_diff:.2f} ({diff_pct:+.2f}%) — {root}"
            )

        # 2. Crypto positions — compare qty deltas from baseline
        # Check symbols where sim holds qty > 0 OR demo has a non-zero
        # delta from baseline. This catches both desync directions:
        # sim holds position but demo doesn't (executor failed / sim-only)
        # and demo holds position but sim doesn't (unexpected fill).
        sim_crypto = self._balance.crypto.get(exchange, {})
        check_syms: set[str] = set()
        for sym, qty in sim_crypto.items():
            if qty > 0:
                check_syms.add(sym)
        for sym in set(demo.crypto) | set(baseline.crypto):
            demo_delta = demo.crypto.get(sym, 0.0) - baseline.crypto.get(sym, 0.0)
            if abs(demo_delta) > 0.0001:
                check_syms.add(sym)

        for sym in check_syms:
            sim_qty = sim_crypto.get(sym, 0.0)
            demo_qty_delta = demo.crypto.get(sym, 0.0) - baseline.crypto.get(sym, 0.0)
            # adjusted = what demo qty "should be" if it started at 0
            # (sim_qty represents what the bot should hold; demo_qty_delta
            # represents what the bot actually caused on demo)
            price = prices.get(sym, 0.0)
            sim_val = sim_qty * price
            adjusted_demo_val = demo_qty_delta * price
            val_diff = abs(sim_val - adjusted_demo_val)

            if val_diff > 1.0:
                diff_pct = (sim_val - adjusted_demo_val) / max(abs(adjusted_demo_val), 1) * 100

                if sim_qty > 0.0001 and abs(demo_qty_delta) < 0.0001:
                    # Distinguish: no executor for this exchange vs real missing position
                    if self._demo_exchanges and exchange not in self._demo_exchanges:
                        dtype = "missing_position_no_executor"
                    else:
                        dtype = "missing_position"
                elif sim_qty < 0.0001 and abs(demo_qty_delta) > 0.0001:
                    dtype = "extra_position"
                else:
                    dtype = "balance_mismatch"

                root = self._classify_root_cause(exchange, sym, sim_val, adjusted_demo_val, diff_pct)

                # D-18: Tag as settling if trade recently touched this exchange
                if settling:
                    dtype = f"{dtype}_settling"
                    settle_age = now - last_trade
                    root = f"[Settling {settle_age:.0f}s ago] {root}"

                disc = Discrepancy(
                    timestamp=now,
                    exchange=exchange,
                    discrepancy_type=dtype,
                    symbol=sym,
                    sim_value=sim_val,
                    demo_value=adjusted_demo_val,
                    diff_abs=val_diff,
                    diff_pct=diff_pct,
                    root_cause=root,
                )
                discrepancies.append(disc)
                logger.info(
                    f"[DemoCompare] {exchange} {sym} {dtype}: "
                    f"sim=${sim_val:.2f} demo_delta=${adjusted_demo_val:.2f} "
                    f"diff=${val_diff:.2f} ({diff_pct:+.2f}%) — {root}"
                )

        return discrepancies

    def _classify_root_cause(
        self, exchange: str, symbol: str, sim_val: float, demo_val: float, diff_pct: float
    ) -> str:
        """Determine the likely root cause of a discrepancy."""
        if abs(diff_pct) > 50:
            if sim_val > demo_val:
                if self._demo_exchanges and exchange not in self._demo_exchanges:
                    return (
                        f"No demo executor for {exchange} — sim-only position "
                        f"(expected in Demo+Sim mode)"
                    )
                return "Simulation holds position not executed on demo (no demo order placement)"
            return "Demo holds position not reflected in simulation"

        if abs(diff_pct) < 5:
            return "Minor drift: likely fee calculation difference or rounding"

        # Check if the difference is roughly a fee amount
        fee_rate = self._fee_manager.get_taker_fee(exchange) if self._fee_manager else 0.001
        expected_fee_impact = max(sim_val, demo_val) * fee_rate * 100
        if abs(abs(diff_pct) - expected_fee_impact) < expected_fee_impact * 0.5:
            return f"Fee difference: exchange may charge different rate than configured {fee_rate*100:.3f}%"

        if sim_val > demo_val:
            return "Simulation overestimates: possible slippage on demo fills"
        return "Simulation underestimates: demo received better fills or different fee tier"

    # ── Baseline delta computation ────────────────────────────────────

    def get_exchange_delta(self, exchange: str, prices: dict[str, float]) -> float:
        """
        Compute USD delta (current - baseline) for a demo exchange.

        Returns the net USD change since the baseline was captured.
        Positive = bot gained value, negative = bot lost value.
        When no trades have been executed, delta is ~0.
        """
        baseline = self._baselines.get(exchange)
        current = self.latest_balances.get(exchange)
        if not baseline or not current or current.error:
            return 0.0

        delta_usdt = current.usdt - baseline.usdt
        delta_crypto = 0.0
        all_syms = set(current.crypto) | set(baseline.crypto)
        for sym in all_syms:
            qty_diff = current.crypto.get(sym, 0.0) - baseline.crypto.get(sym, 0.0)
            delta_crypto += qty_diff * prices.get(sym, 0.0)

        return delta_usdt + delta_crypto

    def get_total_delta(self, prices: dict[str, float]) -> float:
        """Sum of deltas across all demo exchanges."""
        total = 0.0
        for exchange in self._baselines:
            total += self.get_exchange_delta(exchange, prices)
        return total

    @property
    def baselines(self) -> dict[str, "DemoBalance"]:
        return self._baselines

    # ── State persistence ─────────────────────────────────────────────

    def to_state_dict(self) -> dict:
        """Serialize baseline snapshots for state persistence."""
        return {
            "baselines": {
                ex: {
                    "usdt": bl.usdt,
                    "crypto": bl.crypto,
                    "fetched_at": bl.fetched_at,
                }
                for ex, bl in self._baselines.items()
            },
        }

    def from_state_dict(self, data: dict) -> None:
        """Restore baseline snapshots from saved state."""
        baselines = data.get("baselines", {})
        for ex, bl_data in baselines.items():
            self._baselines[ex] = DemoBalance(
                exchange=ex,
                usdt=bl_data.get("usdt", 0.0),
                crypto=bl_data.get("crypto", {}),
                fetched_at=bl_data.get("fetched_at", 0.0),
            )
        if self._baselines:
            exchanges = ", ".join(self._baselines.keys())
            logger.info(f"[DemoCompare] Restored baselines for: {exchanges}")
