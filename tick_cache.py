"""Per-sweep tick caches shared across configs in the orchestrator's sweep loop.

Two caches:

1. **Pre-built `exchange_prices`** — once per orchestrator sweep, build the
   per-symbol list of `(exchange, bid, ask, bids_f, asks_f, received_at)`
   tuples. Order book levels are pre-parsed to `list[tuple[float, float]]`
   so slippage walkers don't re-parse strings on every call. Each config's
   `_score_tick` and monitor's `_tick` filter this shared dict by their
   `_active_exchanges` instead of re-iterating fetchers.

   Without this, 48 configs × 60 symbols × 9 fetchers = 25,920 redundant
   `fetcher.get_state()` calls per sweep. Sharing cuts to 540.

2. **Slippage memoization** lives in `slippage.py` (separate module so
   the slippage utility stays self-contained and importable for tests
   that don't run the orchestrator).

The orchestrator owns the lifetime of these caches. It builds the prices
dict via `build_sweep_prices()` before fanning out per-config ticks, and
clears via `clear_sweep_prices()` after. Configs read via
`get_sweep_prices()` which returns None when the orchestrator isn't
managing a sweep (e.g., legacy single-config path or unit tests).
"""

from __future__ import annotations

import time
from typing import Any

# Imported lazily where needed to avoid circular deps on bot internals.

# Module-level cache. None when no sweep is in progress.
_SWEEP_PRICES: dict[str, list[tuple]] | None = None

# Configurable in tests; production reads from config.MAX_DATA_AGE_SECONDS
_MAX_DATA_AGE_SECONDS_DEFAULT = 30.0


def set_sweep_prices(d: dict[str, list[tuple]]) -> None:
    global _SWEEP_PRICES
    _SWEEP_PRICES = d


def get_sweep_prices() -> dict[str, list[tuple]] | None:
    return _SWEEP_PRICES


def clear_sweep_prices() -> None:
    global _SWEEP_PRICES
    _SWEEP_PRICES = None


def _parse_levels(levels: list[tuple[str, str]] | None) -> list[tuple[float, float]] | None:
    """Pre-parse `[(price_str, qty_str), ...]` to `[(price_f, qty_f), ...]`.

    Skips invalid entries silently. Returns None if input is None.
    Saves ~10 string→float parses per slippage walk; with 95% cache hit
    rate that's amortized but the cold path still benefits.
    """
    if levels is None:
        return None
    out: list[tuple[float, float]] = []
    for level in levels:
        try:
            price = float(level[0])
            qty = float(level[1])
            if price > 0 and qty > 0:
                out.append((price, qty))
        except (ValueError, TypeError, IndexError):
            continue
    return out


def build_sweep_prices(
    fetchers: list,
    all_symbols: list[str],
    max_data_age_seconds: float = _MAX_DATA_AGE_SECONDS_DEFAULT,
    globally_allowed: dict[str, set[str]] | None = None,
) -> dict[str, list[tuple]]:
    """Build the shared per-symbol exchange_prices dict for one sweep.

    Output format (per symbol):
      [(exchange_name, bid_f, ask_f, bid_qty_f, ask_qty_f,
        bids_pre_parsed, asks_pre_parsed, received_at), ...]

    Filters applied uniformly:
    - bid + ask both present and > 0
    - data not staler than `max_data_age_seconds`
    - if `globally_allowed` is provided: skip a (symbol, exchange) when
      no config in the registry can use it as either buyer or seller.
      Saves the per-fetcher state lookup AND the float/order-book
      parsing for entries that every config's `_score_tick` would
      filter out anyway. At 48 configs with ~12 globally-blocked
      Bitfinex symbols + similar on other exchanges, this skips the
      slowest part of the sweep (multi-level book parsing) for ~10-15%
      of (symbol, exchange) cells.

    Per-config filters (active_exchanges, can_buy/can_sell) are still
    applied later in each config's tick — `globally_allowed` only
    drops entries where ALL configs would reject. Per-config narrowing
    happens via `filter_for_config` / `filter_for_config_full`.
    """
    now = time.time()
    out: dict[str, list[tuple]] = {}
    for symbol in all_symbols:
        # Globally-blocked symbol: no config can do anything with it.
        sym_allowed = globally_allowed.get(symbol) if globally_allowed is not None else None
        if globally_allowed is not None and not sym_allowed:
            continue
        entries: list[tuple] = []
        for fetcher in fetchers:
            # Skip exchanges no config can use for this symbol.
            if sym_allowed is not None and fetcher.exchange_name not in sym_allowed:
                continue
            try:
                state = fetcher.get_state()
            except Exception:
                continue
            ps = state.get(symbol)
            if ps is None or not ps.bid or not ps.ask:
                continue
            if ps.received_at > 0 and (now - ps.received_at) > max_data_age_seconds:
                continue
            try:
                bid_f = float(ps.bid)
                ask_f = float(ps.ask)
            except (ValueError, TypeError):
                continue
            if bid_f <= 0 or ask_f <= 0:
                continue
            try:
                bid_qty_f = float(ps.bid_qty) if ps.bid_qty else 0.0
                ask_qty_f = float(ps.ask_qty) if ps.ask_qty else 0.0
            except (ValueError, TypeError):
                bid_qty_f = 0.0
                ask_qty_f = 0.0
            bids_f = _parse_levels(ps.bids) if ps.bids else None
            asks_f = _parse_levels(ps.asks) if ps.asks else None
            entries.append(
                (
                    fetcher.exchange_name,
                    bid_f,
                    ask_f,
                    bid_qty_f,
                    ask_qty_f,
                    bids_f,
                    asks_f,
                    ps.received_at,
                )
            )
        if entries:
            out[symbol] = entries
    return out


def filter_for_config(
    sweep_prices: dict[str, list[tuple]],
    symbol: str,
    active_exchanges: set[str] | list[str],
) -> list[tuple[str, float, float, list, list]]:
    """Return per-config exchange_prices subset for the optimizer's `_score_tick`.

    Returns 5-tuples `(ex, bid, ask, bids_f, asks_f)` — drops the qty + recv_at
    columns since `_score_tick` doesn't use them. The shape matches the
    legacy `exchange_prices` list so the call site only swaps its source.
    """
    active = set(active_exchanges) if not isinstance(active_exchanges, set) else active_exchanges
    entries = sweep_prices.get(symbol, [])
    return [
        (ex, bid_f, ask_f, bids_f, asks_f)
        for ex, bid_f, ask_f, _bq, _aq, bids_f, asks_f, _recvd in entries
        if ex in active
    ]


def filter_for_config_full(
    sweep_prices: dict[str, list[tuple]],
    symbol: str,
    active_exchanges: set[str] | list[str],
) -> list[tuple]:
    """Full 8-tuple per-config view for `monitor._tick`.

    Returns `(ex, bid, ask, bid_qty, ask_qty, bids_f, asks_f, received_at)` —
    monitor needs depth qtys for the depth gate and received_at for the
    per-tick freshness/age stats.
    """
    active = set(active_exchanges) if not isinstance(active_exchanges, set) else active_exchanges
    entries = sweep_prices.get(symbol, [])
    return [e for e in entries if e[0] in active]
