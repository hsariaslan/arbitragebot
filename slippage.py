"""
Order book depth-based slippage simulation.

Walks the order book to compute the effective fill price for a given
trade size, then reports the slippage percentage versus the best price.

Pure utility module with no dependencies on bot internals.
"""

from dataclasses import dataclass


@dataclass
class SlippageResult:
    """Result of a slippage calculation."""

    effective_price: float  # Volume-weighted average fill price
    slippage_pct: float  # Percentage worse than best price (always >= 0)
    levels_consumed: int  # How many book levels were needed
    total_depth_usd: float  # Total available depth in USD
    sufficient_depth: bool  # False = couldn't fill the entire order


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
    return _walk_book(bids, trade_size_usd, is_buy=False)


def _walk_book(
    levels: list[tuple[str, str]],
    trade_size_usd: float,
    is_buy: bool,
) -> SlippageResult:
    """Walk order book levels and compute volume-weighted average fill price.

    For buys: walks asks (ascending price) — each level is progressively worse.
    For sells: walks bids (descending price) — each level is progressively worse.
    """
    remaining_usd = trade_size_usd
    total_cost = 0.0  # Total USD spent (buy) or received (sell)
    total_qty = 0.0
    total_depth_usd = 0.0
    levels_consumed = 0
    best_price = 0.0

    for i, (price_str, qty_str) in enumerate(levels):
        try:
            price = float(price_str)
            qty = float(qty_str)
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
