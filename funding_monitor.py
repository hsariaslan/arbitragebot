"""
Live funding-rate monitor for Binance USDⓈ-M perpetual futures.

Polls /fapi/v1/premiumIndex every 60s for all 60 trading symbols in one
API call (rate-limit weight 10, no API key). Exposes per-symbol funding
rate, funding interval, and a multiplier suitable for use in symbol
scoring (Phase A) and hedge skip-threshold gating (Phase D).

Symbol mapping: PEPE/SHIB/FLOKI use Binance's `1000X` contract on
futures because their unit prices are too small. The mapping table is
the single source of truth — referenced by both this monitor and
later by the futures executor.

Companion to `state/funding_history.json` (produced by
`scripts/analyze_funding_history.py`) — that file provides static
historical context (avg, p95, worst spike); this monitor provides
live current rates.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# Spot symbol → (futures symbol, contract multiplier)
# A spot quantity of N units maps to N/multiplier contracts on the
# 1000X futures market. Used everywhere we cross the spot↔futures boundary.
FUTURES_SYMBOL_OVERRIDE: dict[str, tuple[str, int]] = {
    "PEPEUSDT":  ("1000PEPEUSDT",  1000),
    "SHIBUSDT":  ("1000SHIBUSDT",  1000),
    "FLOKIUSDT": ("1000FLOKIUSDT", 1000),
}

PREMIUM_INDEX_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
DEFAULT_POLL_INTERVAL_SECONDS = 60.0


def get_futures_symbol(spot_symbol: str) -> tuple[str, int]:
    """Return (futures_symbol, contract_multiplier) for a spot symbol.

    For symbols without an override, returns (spot_symbol, 1).
    """
    return FUTURES_SYMBOL_OVERRIDE.get(spot_symbol, (spot_symbol, 1))


class FundingMonitor:
    """Polls Binance Futures /premiumIndex every 60s, caches rates per symbol.

    Exposes:
      - get_funding_rate(symbol): latest rate as decimal (e.g. 0.0001 = 0.01%)
      - get_funding_interval_hours(symbol): 4 or 8 (auto-detected from history)
      - get_annualized_short_pct(symbol): annualized return % for a SHORT position
      - get_funding_factor(symbol): score multiplier (capped, with skip-gate)
      - should_skip_hedge(symbol): True when funding is below skip threshold

    Loads `state/funding_history.json` at startup for historical context
    (used to detect funding interval per symbol before the first live poll).
    """

    def __init__(
        self,
        symbols: list[str],
        history_path: str = "state/funding_history.json",
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        # Phase A scoring/skip parameters (hot-applied via dashboard)
        scoring_enabled: bool = True,
        skip_threshold_4h_pct: float = -0.05,
        skip_threshold_8h_pct: float = -0.05,
        score_min_factor: float = 0.3,
        score_max_factor: float = 1.5,
    ) -> None:
        # Spot symbols the bot trades. Convert to futures symbols for API calls.
        self._spot_symbols: list[str] = list(symbols)
        self._futures_to_spot: dict[str, str] = {
            get_futures_symbol(s)[0]: s for s in symbols
        }
        self._history_path = Path(history_path)
        self._poll_interval = poll_interval_seconds

        # Live state (per-spot-symbol)
        self._rates: dict[str, float] = {}            # latest funding rate (decimal)
        self._mark_prices: dict[str, float] = {}      # latest mark price
        self._next_funding_times: dict[str, int] = {} # ms UTC of next settlement
        self._intervals_h: dict[str, int] = {}        # 4 or 8
        self._last_poll_ts: float = 0.0
        self._poll_count: int = 0
        self._poll_errors: int = 0

        # Tunable scoring parameters (hot-applied)
        self._scoring_enabled: bool = scoring_enabled
        self._skip_threshold_4h_pct: float = skip_threshold_4h_pct
        self._skip_threshold_8h_pct: float = skip_threshold_8h_pct
        self._score_min_factor: float = score_min_factor
        self._score_max_factor: float = score_max_factor

        # Throttled logging — at most one log per (symbol, kind) per 10 min
        self._last_log_ts: dict[str, float] = {}

        # Run flag
        self._running: bool = False

        # Load history for funding interval bootstrap
        self._load_history()

    # ── Lifecycle ─────────────────────────────────────────────────────

    def _load_history(self) -> None:
        """Load static historical context if available. Used to seed
        `_intervals_h` so we know whether a symbol is 4h or 8h funding
        before the first live poll lands."""
        if not self._history_path.exists():
            logger.info(f"[Funding] history file {self._history_path} not found — will populate intervals after first poll")
            return
        try:
            data = json.loads(self._history_path.read_text())
            symbols_data = data.get("symbols", {})
            for sym, stats in symbols_data.items():
                interval = stats.get("interval_hours")
                if interval in (4, 8):
                    self._intervals_h[sym] = int(interval)
            logger.info(
                f"[Funding] Loaded interval map for {len(self._intervals_h)} symbols "
                f"from {self._history_path} (window={data.get('days_window', '?')}d)"
            )
        except Exception as e:
            logger.warning(f"[Funding] Failed to load {self._history_path}: {e}")

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        """Main poll loop. One API call per cycle covers all symbols."""
        self._running = True
        logger.info(
            f"[Funding] Monitor started — polling every {self._poll_interval:.0f}s "
            f"({len(self._spot_symbols)} symbols, scoring={'on' if self._scoring_enabled else 'off'}, "
            f"skip_threshold 4h={self._skip_threshold_4h_pct}% 8h={self._skip_threshold_8h_pct}%)"
        )
        # First poll immediately, then on interval
        while self._running:
            try:
                await asyncio.to_thread(self._poll_once)
            except Exception as e:
                self._poll_errors += 1
                logger.warning(f"[Funding] Poll failed (err {self._poll_errors}): {e}")
            for _ in range(int(self._poll_interval)):
                if not self._running:
                    break
                await asyncio.sleep(1.0)

    def _poll_once(self) -> None:
        """One synchronous fetch of all-symbols /premiumIndex."""
        req = urllib.request.Request(
            PREMIUM_INDEX_URL,
            headers={"User-Agent": "ArbitrageBot-Funding/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(f"premiumIndex fetch error: {e}")
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected response shape: {type(payload)}")

        now = time.time()
        updated = 0
        for entry in payload:
            futures_sym = entry.get("symbol")
            spot_sym = self._futures_to_spot.get(futures_sym)
            if spot_sym is None:
                continue  # Not a symbol we care about
            try:
                rate = float(entry.get("lastFundingRate", 0.0))
                mark = float(entry.get("markPrice", 0.0))
                next_ms = int(entry.get("nextFundingTime", 0))
            except (TypeError, ValueError):
                continue
            self._rates[spot_sym] = rate
            self._mark_prices[spot_sym] = mark
            if next_ms > 0:
                self._next_funding_times[spot_sym] = next_ms
            updated += 1

        self._last_poll_ts = now
        self._poll_count += 1

        # Throttled summary log every 5 minutes
        if self._poll_count == 1 or self._poll_count % 5 == 0:
            n_pos = sum(1 for r in self._rates.values() if r > 0)
            n_neg = sum(1 for r in self._rates.values() if r < 0)
            logger.info(
                f"[Funding] Poll #{self._poll_count}: updated {updated}/{len(self._spot_symbols)} symbols "
                f"({n_pos} positive, {n_neg} negative)"
            )

    # ── Public accessors (used by optimizer and later by hedge_manager) ──

    def get_funding_rate(self, spot_symbol: str) -> float | None:
        """Latest funding rate as decimal (0.0001 = 0.01% per period)."""
        return self._rates.get(spot_symbol)

    def get_funding_interval_hours(self, spot_symbol: str) -> int:
        """Funding interval in hours. Falls back to 8 if unknown."""
        return self._intervals_h.get(spot_symbol, 8)

    def get_next_funding_time_ms(self, spot_symbol: str) -> int | None:
        return self._next_funding_times.get(spot_symbol)

    def get_mark_price(self, spot_symbol: str) -> float | None:
        """Latest Binance Futures mark price, scaled to spot-equivalent.

        For 1000X contracts (PEPE/SHIB/FLOKI), Binance Futures' markPrice is
        per-1000-contract. We divide by the multiplier so callers can do
        `(spot_entry - mark) × spot_qty` directly without unit-mismatch.

        Returns None when no fresh poll data is available — caller should
        fall back to spot mid in that case.
        """
        raw = self._mark_prices.get(spot_symbol)
        if raw is None or raw <= 0:
            return None
        _, multiplier = get_futures_symbol(spot_symbol)
        return raw / multiplier if multiplier > 1 else raw

    def get_annualized_short_pct(self, spot_symbol: str) -> float | None:
        """Annualized funding income/cost % for a short position.

        Positive = short receives. Negative = short pays.
        """
        rate = self._rates.get(spot_symbol)
        if rate is None:
            return None
        interval_h = self.get_funding_interval_hours(spot_symbol)
        periods_per_year = (24 / interval_h) * 365
        return rate * periods_per_year * 100

    def should_skip_hedge(self, spot_symbol: str) -> bool:
        """True when funding rate is worse than the per-interval skip
        threshold. The bot should not open a hedge for this symbol; the
        symbol should be deboosted heavily and ideally demoted.
        """
        rate = self._rates.get(spot_symbol)
        if rate is None:
            return False  # No data yet — don't gate on missing data
        interval_h = self.get_funding_interval_hours(spot_symbol)
        rate_pct = rate * 100  # convert to percent
        threshold = (
            self._skip_threshold_4h_pct
            if interval_h == 4
            else self._skip_threshold_8h_pct
        )
        return rate_pct < threshold

    def get_funding_factor(self, spot_symbol: str) -> float:
        """Score multiplier for the optimizer.

        Formula: clamp(1.0 + annualized_short_pct/100, min, max).

          - Positive funding (short earns)  → factor > 1.0 (boost)
          - Negative funding (short pays)   → factor < 1.0 (penalty)
          - Below skip threshold            → factor = min_factor (heavy penalty)

        Returns 1.0 if scoring is disabled or no data yet.
        """
        if not self._scoring_enabled:
            return 1.0
        ann_pct = self.get_annualized_short_pct(spot_symbol)
        if ann_pct is None:
            return 1.0  # No data yet — don't penalize

        # Hard skip-threshold gate: floor the multiplier
        if self.should_skip_hedge(spot_symbol):
            self._maybe_log_skip(spot_symbol)
            return self._score_min_factor

        raw_factor = 1.0 + (ann_pct / 100.0)
        factor = max(self._score_min_factor, min(self._score_max_factor, raw_factor))
        self._maybe_log_factor(spot_symbol, factor, ann_pct)
        return factor

    # ── Logging helpers ─────────────────────────────────────────

    def _maybe_log_skip(self, spot_symbol: str) -> None:
        key = f"{spot_symbol}:skip"
        now = time.time()
        if now - self._last_log_ts.get(key, 0.0) < 600:
            return
        self._last_log_ts[key] = now
        rate = self._rates.get(spot_symbol, 0.0)
        interval_h = self.get_funding_interval_hours(spot_symbol)
        threshold = (
            self._skip_threshold_4h_pct if interval_h == 4 else self._skip_threshold_8h_pct
        )
        logger.info(
            f"[Funding] SKIP {spot_symbol}: rate={rate * 100:+.4f}%/{interval_h}h "
            f"< threshold {threshold:+.4f}% — score factor = {self._score_min_factor}"
        )

    def _maybe_log_factor(self, spot_symbol: str, factor: float, ann_pct: float) -> None:
        # Only log when factor deviates meaningfully from 1.0
        if abs(factor - 1.0) < 0.05:
            return
        key = f"{spot_symbol}:factor"
        now = time.time()
        if now - self._last_log_ts.get(key, 0.0) < 600:
            return
        self._last_log_ts[key] = now
        logger.info(
            f"[Funding] {spot_symbol}: ann={ann_pct:+.2f}%/yr factor={factor:.3f} "
            f"({'boost' if factor > 1.0 else 'penalty'})"
        )

    # ── Hot-apply for settings ─────────────────────────────────

    def update_settings(
        self,
        scoring_enabled: bool | None = None,
        skip_threshold_4h_pct: float | None = None,
        skip_threshold_8h_pct: float | None = None,
        score_min_factor: float | None = None,
        score_max_factor: float | None = None,
    ) -> None:
        if scoring_enabled is not None:
            self._scoring_enabled = bool(scoring_enabled)
        if skip_threshold_4h_pct is not None:
            self._skip_threshold_4h_pct = float(skip_threshold_4h_pct)
        if skip_threshold_8h_pct is not None:
            self._skip_threshold_8h_pct = float(skip_threshold_8h_pct)
        if score_min_factor is not None:
            self._score_min_factor = float(score_min_factor)
        if score_max_factor is not None:
            self._score_max_factor = float(score_max_factor)

    # ── Live snapshot for dashboard ───────────────────────────

    def get_all_rates(self) -> dict[str, dict]:
        """Return live funding info for all tracked symbols.

        Each entry: {rate, rate_pct, interval_hours, annualized_short_pct,
        mark_price, next_funding_time_ms, factor, skip}.

        Computes the factor inline (no log side-effects, unlike
        get_funding_factor which is called from the optimizer scoring loop).
        """
        out: dict[str, dict] = {}
        for sym in self._spot_symbols:
            rate = self._rates.get(sym)
            if rate is None:
                continue
            interval_h = self.get_funding_interval_hours(sym)
            ann = rate * (24 / interval_h) * 365 * 100  # annualized short %
            skip = self.should_skip_hedge(sym)
            if not self._scoring_enabled:
                factor = 1.0
            elif skip:
                factor = self._score_min_factor
            else:
                raw = 1.0 + (ann / 100.0)
                factor = max(self._score_min_factor, min(self._score_max_factor, raw))
            out[sym] = {
                "rate": rate,
                "rate_pct": rate * 100,
                "interval_hours": interval_h,
                "annualized_short_pct": ann,
                "mark_price": self._mark_prices.get(sym, 0.0),
                "next_funding_time_ms": self._next_funding_times.get(sym, 0),
                "factor": factor,
                "skip": skip,
            }
        return out

    # ── Debug snapshot ─────────────────────────────────────────

    def get_debug_state(self) -> dict:
        """Snapshot used by dashboard and Bot Logs for diagnostics."""
        return {
            "poll_count": self._poll_count,
            "poll_errors": self._poll_errors,
            "last_poll_ts": self._last_poll_ts,
            "tracked_symbols": len(self._rates),
            "scoring_enabled": self._scoring_enabled,
            "skip_threshold_4h_pct": self._skip_threshold_4h_pct,
            "skip_threshold_8h_pct": self._skip_threshold_8h_pct,
            "score_min_factor": self._score_min_factor,
            "score_max_factor": self._score_max_factor,
        }
