"""
Order book depth-based slippage simulation.

Walks the order book to compute the effective fill price for a given
trade size, then reports the slippage percentage versus the best price.

Pure utility module with no dependencies on bot internals.

v0.31.0-beta+: per-sweep memoization. The orchestrator runs every config
on the same fetcher snapshot within a 1-second sweep. If 48 configs all
call `compute_buy_slippage(MEXC's asks, $40)`, that's 48× the same walk
on the same list. With `begin_sweep()` / `end_sweep()` the orchestrator
clears a module-level cache around the per-tick fan-out so repeated calls
within one sweep return the cached `SlippageResult`. Cache key is
`(id(levels), round(trade_size_usd, 2))` — id() works because the fetcher
keeps the same list object until the next WebSocket update and orchestrator
sweeps are atomic w.r.t. fetcher updates.
"""

from dataclasses import dataclass


@dataclass(slots=True)
class SlippageResult:
    """Result of a slippage calculation.

    `slots=True`: SlippageResult is allocated heavily inside the per-pair
    loop in `optimizer._score_tick` (2 calls per pair × ~70 pairs per
    symbol × 60 symbols × 48 configs = ~400K calls/sweep). Cache hits
    return existing instances, but cache misses still allocate. Slots
    reduce per-instance memory + GC overhead.
    """

    effective_price: float  # Volume-weighted average fill price
    slippage_pct: float  # Percentage worse than best price (always >= 0)
    levels_consumed: int  # How many book levels were needed
    total_depth_usd: float  # Total available depth in USD
    sufficient_depth: bool  # False = couldn't fill the entire order


# Module-level per-sweep cache. None when caching is disabled (e.g.
# single-config legacy path). The orchestrator manages lifetime via
# begin_sweep() / end_sweep().
_SWEEP_CACHE: dict[tuple, SlippageResult] | None = None
# Diagnostic counters (cleared on each begin_sweep)
_cache_hits: int = 0
_cache_misses: int = 0


def begin_sweep() -> None:
    """Start a per-sweep slippage cache. Call before iterating configs.

    Slippage results computed during this sweep are memoized by
    (id(levels), trade_size_rounded). All cache lookups during the sweep
    return memoized values when keys match; cache is fully invalidated
    on `end_sweep()` so the next sweep recomputes against fresh book state.
    """
    global _SWEEP_CACHE, _cache_hits, _cache_misses
    _SWEEP_CACHE = {}
    _cache_hits = 0
    _cache_misses = 0


def end_sweep() -> tuple[int, int]:
    """Tear down the per-sweep cache. Returns (hits, misses) for telemetry."""
    global _SWEEP_CACHE
    h, m = _cache_hits, _cache_misses
    _SWEEP_CACHE = None
    return h, m


def cache_stats() -> tuple[int, int]:
    """Returns (hits, misses) for the in-progress sweep."""
    return _cache_hits, _cache_misses


def compute_buy_slippage(
    asks: list[tuple[str, str]] | None,
    trade_size_usd: float,
) -> SlippageResult:
    """Compute slippage for a market buy by walking the ask book upward.

    Args:
        asks: List of (price_str, qty_str) ascending by price, or None.
        trade_size_usd: Amount in USD to buy.

    Returns:
        SlippageResult. Returns zero slippage if asks is None (backward compat).
    """
    if not asks or trade_size_usd <= 0:
        return SlippageResult(
            effective_price=0.0,
            slippage_pct=0.0,
            levels_consumed=0,
            total_depth_usd=0.0,
            sufficient_depth=True,
        )
    global _cache_hits, _cache_misses
    if _SWEEP_CACHE is not None:
        key = (id(asks), 1, round(trade_size_usd, 2))
        cached = _SWEEP_CACHE.get(key)
        if cached is not None:
            _cache_hits += 1
            return cached
        result = _walk_book(asks, trade_size_usd, is_buy=True)
        _SWEEP_CACHE[key] = result
        _cache_misses += 1
        return result
    return _walk_book(asks, trade_size_usd, is_buy=True)


def compute_sell_slippage(
    bids: list[tuple[str, str]] | None,
    trade_size_usd: float,
) -> SlippageResult:
    """Compute slippage for a market sell by walking the bid book downward.

    Args:
        bids: List of (price_str, qty_str) descending by price, or None.
        trade_size_usd: Amount in USD to sell.

    Returns:
        SlippageResult. Returns zero slippage if bids is None (backward compat).
    """
    if not bids or trade_size_usd <= 0:
        return SlippageResult(
            effective_price=0.0,
            slippage_pct=0.0,
            levels_consumed=0,
            total_depth_usd=0.0,
            sufficient_depth=True,
        )
    global _cache_hits, _cache_misses
    if _SWEEP_CACHE is not None:
        key = (id(bids), 0, round(trade_size_usd, 2))
        cached = _SWEEP_CACHE.get(key)
        if cached is not None:
            _cache_hits += 1
            return cached
        result = _walk_book(bids, trade_size_usd, is_buy=False)
        _SWEEP_CACHE[key] = result
        _cache_misses += 1
        return result
    return _walk_book(bids, trade_size_usd, is_buy=False)


def _walk_book(
    levels: list,
    trade_size_usd: float,
    is_buy: bool,
) -> SlippageResult:
    """Walk order book levels and compute volume-weighted average fill price.

    For buys: walks asks (ascending price) — each level is progressively worse.
    For sells: walks bids (descending price) — each level is progressively worse.

    Accepts levels as either:
      - `list[tuple[str, str]]` — legacy fetcher format, parsed lazily here
      - `list[tuple[float, float]]` — pre-parsed by `tick_cache.build_sweep_prices`,
        skips the per-level string→float conversion (saves ~10 parses per call;
        compounds at 40+ configs).
    """
    remaining_usd = trade_size_usd
    total_cost = 0.0  # Total USD spent (buy) or received (sell)
    total_qty = 0.0
    total_depth_usd = 0.0
    levels_consumed = 0
    best_price = 0.0

    # Detect format once: if first level's price is already numeric, skip the
    # try/except float() conversion in the inner loop. The fetchers store
    # strings, but the orchestrator pre-parses to floats for the shared
    # sweep cache.
    pre_parsed = bool(levels) and isinstance(levels[0][0], (int, float))

    for i, level in enumerate(levels):
        if pre_parsed:
            price = level[0]
            qty = level[1]
        else:
            try:
                price = float(level[0])
                qty = float(level[1])
            except (ValueError, TypeError):
                continue

        if price <= 0 or qty <= 0:
            continue

        if i == 0:
            best_price = price

        level_usd = price * qty
        total_depth_usd += level_usd
        levels_consumed = i + 1

        if level_usd >= remaining_usd:
            # Partial fill of this level completes the order
            fill_qty = remaining_usd / price
            total_cost += remaining_usd
            total_qty += fill_qty
            remaining_usd = 0.0
            break
        else:
            # Consume entire level
            total_cost += level_usd
            total_qty += qty
            remaining_usd -= level_usd

    sufficient = remaining_usd <= 0
    if total_qty <= 0 or best_price <= 0:
        return SlippageResult(
            effective_price=0.0,
            slippage_pct=0.0,
            levels_consumed=levels_consumed,
            total_depth_usd=total_depth_usd,
            sufficient_depth=False,
        )

    effective_price = total_cost / total_qty

    # Slippage: how much worse is the effective price vs best price
    if is_buy:
        # Buying: effective > best is worse (paying more)
        slippage_pct = (effective_price - best_price) / best_price * 100
    else:
        # Selling: effective < best is worse (receiving less)
        slippage_pct = (best_price - effective_price) / best_price * 100

    # Clamp to non-negative (shouldn't happen but be safe)
    slippage_pct = max(0.0, slippage_pct)

    return SlippageResult(
        effective_price=effective_price,
        slippage_pct=slippage_pct,
        levels_consumed=levels_consumed,
        total_depth_usd=total_depth_usd,
        sufficient_depth=sufficient,
    )
