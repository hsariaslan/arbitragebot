# Future Plans & Implementation Notes

## Net%-Based Dynamic Trade Sizing

### Problem

The bot currently sizes trades based on **symbol score** (a rolling average metric). Score determines `trade_multiplier` (0.5x–4.0x), which is the same for every tick of that symbol regardless of whether the current tick has a 0.02% or 0.30% net spread.

This means:
- Fat spreads (0.20%+) get the same trade size as thin spreads (0.03%)
- The bot leaves money on the table during rare high-profit opportunities
- Thin-margin ticks risk the same capital as high-margin ones

### Solution: Tick-Level Net% Multiplier

Add a **second multiplier** based on the current tick's `net_pct`. This multiplies with the existing score-based `trade_multiplier`:

```
final_size = trade_amount × score_multiplier × net_pct_multiplier × tick_quality_factor
```

### Net% Multiplier Tiers

| Net % Range | Multiplier | Rationale |
|-------------|:----------:|-----------|
| < 0.03% | 0.5x | Thin margin — minimize exposure, fees eat most of the profit |
| 0.03% – 0.08% | 1.0x | Normal baseline — standard profitable tick |
| 0.08% – 0.15% | 1.5x | Good spread — worth committing extra capital |
| 0.15% – 0.25% | 2.0x | Strong opportunity — rare, capture aggressively |
| > 0.25% | 2.5x | Exceptional fat spread — maximum capture |

### Combined Multiplier Examples

| Symbol Tier | Score Mult | Net% | Net Mult | Combined | Trade ($30 base) |
|-------------|:----------:|:----:|:--------:|:--------:|:----------------:|
| Normal | 1.0x | 0.04% | 1.0x | 1.0x | $30 |
| Normal | 1.0x | 0.20% | 2.0x | 2.0x | $60 |
| Strong | 2.5x | 0.04% | 1.0x | 2.5x | $75 |
| Strong | 2.5x | 0.20% | 2.0x | 5.0x | $150 |
| Very Strong | 3.5x | 0.04% | 1.0x | 3.5x | $105 |
| Very Strong | 3.5x | 0.30% | 2.5x | 8.75x | $262 |

Final size is always capped by available balance (dynamic buffer: 80-95% of available).

### Latency Considerations

**Zero additional latency** — the net% multiplier is pure local computation inside `_tick()`:

1. Price data arrives at orchestrator (already happened)
2. `_tick()` computes `net_pct` from bid/ask across exchanges (nanoseconds)
3. Net% multiplier lookup (nanoseconds)
4. Order sent to exchange (same latency as before)

The distributed VPS architecture (Option C in VPS.md) doesn't change anything about this feature. Whether monolithic Bangkok or 4-VPS distributed, the sizing decision happens on the orchestrator at detection time.

### Distributed VPS Architecture Impact

From VPS.md Option C (recommended):

| VPS | Location | Exchanges | Latency to Exchange | Relay to Bangkok |
|-----|----------|-----------|:-------------------:|:----------------:|
| Bangkok | LightNode | MEXC | 25ms | local |
| Singapore | Vultr | OKX, Bybit, Bitget, KuCoin, Gate.io | <1–35ms | 25ms |
| Tokyo | Kamatera | Binance, Pionex | <1–160ms | 70ms |
| Zurich | Oracle | Bitfinex | <1ms | 250ms |

**Execution round-trip** (detect opportunity → order placed on exchange):
- Orchestrator detects spread → sends execute command to fetcher node → fetcher places order locally
- Singapore exchanges: ~50ms round trip (25ms each way)
- Binance: ~140ms round trip (70ms each way)
- Bitfinex: ~500ms round trip (250ms each way)
- MEXC: ~50ms (local Bangkok → Singapore exchange servers)

All well within the 1–10 second opportunity window for typical arbitrage spreads.

### Real Trading Concerns

#### Slippage Risk (Implemented)

**Order book depth-based slippage simulation is now active.** All 9 exchange fetchers collect multi-level order book data (up to 5 levels). `slippage.py` walks the book to compute volume-weighted average fill prices. Both scoring (`optimizer.py`) and execution (`monitor.py`) deduct slippage from net profit.

**Remaining considerations for real trading:**
1. Cap maximum net% multiplier at 2.0x or 2.5x (not higher)
2. Set absolute max trade size cap (e.g., `trade_amount × 3` regardless of multipliers)
3. Use limit orders at the detected price instead of market orders for large sizes
4. Monitor actual slippage in demo mode vs simulated slippage, calibrate if needed

#### Stale Data Risk

Exchanges with high data staleness (Gate.io ~5.9s, Bitfinex ~20.3s) may show spreads that have already closed:

| Exchange | Avg Freshness | Risk Level |
|----------|:------------:|:----------:|
| Bitget | 66ms | Very Low |
| Bybit | 401ms | Low |
| KuCoin | 677ms | Low |
| Pionex | 827ms | Medium |
| OKX | 1,037ms | Medium |
| Binance | 1,334ms | Medium |
| Gate.io | 5,854ms | High |
| Bitfinex | 20,298ms | High |

For Gate.io/Bitfinex ticks showing very wide spreads (>0.25%), the spread may be an artifact of stale data. Consider:
- Capping net% multiplier for Tier 4 freshness exchanges
- Using `data_age_ms` from `SimulatedTrade` to discount multiplier for stale data
- Only applying aggressive multipliers when BOTH exchanges have fresh data (<2s)

### Simulation vs Real Mode Differences

| Aspect | Simulation | Real Trading |
|--------|-----------|-------------|
| Slippage | Modeled via order book depth (5 levels) | Real order book impact (may differ from 5-level estimate) |
| Fill speed | Instant | 10–500ms per leg |
| Partial fills | Never | Possible on thin books |
| Net% accuracy | Good (depth-adjusted) | May still differ due to book changes between detection and fill |
| Max multiplier | 2.5x (aggressive OK) | Consider 2.0x cap initially |
| Data freshness | Ignored | Should gate multiplier |

### Configuration

Settings (configurable via dashboard, hot-applied):

| Setting | Default | Range | Description |
|---------|:-------:|:-----:|-------------|
| `net_pct_sizing_enabled` | true | bool | Enable/disable net%-based sizing |
| `net_pct_multiplier_cap` | 2.5 | 1.0–5.0 | Maximum net% multiplier |

Tier thresholds are hardcoded initially (0.03/0.08/0.15/0.25%) since they're derived from fee structure and shouldn't need frequent adjustment.

### Expected Impact

Based on log analysis (bot-logs-2026-03-01):
- 121 trades, median net% = 0.022%, most in the 0.01–0.05% range
- ~10% of ticks had net% > 0.08% — these would get 1.5x+ sizing
- ~2% of ticks had net% > 0.15% — these would get 2.0x+ sizing
- Estimated profit increase: 15–30% from better capital allocation on high-quality ticks

The improvement compounds: more profit per fat tick → better net P&L → rotation/rebalance gates stay open → more trading activity.

## Incremental Symbol Activation

### Problem

Currently, when `_complete_discovery()` activates new symbols after a demotion→discovery cycle, it calls `balance.reconfigure()` and `monitor.reconfigure()` which reset USDT/crypto balances and re-initialize everything from scratch with new allocations. This is a shortcut that treats activation as a "wipe and rebuild" operation.

This has several drawbacks:
- Capital movements during activation are invisible — balances are teleported, not transferred
- Transfer fees from activation are not counted in net P&L (hidden costs)
- Rebalance gates (ROI, worthiness, hourly cap) are bypassed during activation
- The `reconfigure()` code path is a special case that diverges from normal trading/transfer logic
- Simulation does not reflect what real trading would look like (you cannot magically move money between exchanges)

### Solution: Incremental Activation via Normal Pipelines

Instead of wiping balances and rebuilding from scratch, activation should work incrementally using the existing trade and transfer pipelines:

1. **Demotion sells all crypto back to USDT** — this already works. After demotion, all capital is USDT spread across exchanges.
2. **New symbols activate without balance reset** — just update the active symbol list and dominant pairs.
3. **Normal rebalance logic moves USDT** — the rebalance loop detects that buyer exchanges need USDT and transfers it from exchanges with excess.
4. **Normal trading loop buys crypto** — seller exchanges acquire crypto organically through arbitrage trades (buying on buyer exchange, selling on seller exchange).
5. **No special `reconfigure()` path needed** — everything flows through the same trade/transfer pipeline used during normal operation.

### Example Flow

```
Session starts:
  DYDXUSDT active, capital on Binance ($100 USDT) + MEXC ($100 crypto)

DYDX demoted:
  Crypto sold on MEXC → $100 USDT on Binance, $99.96 USDT on MEXC (after taker fee)

Discovery finds AXSUSDT:
  Dominant pair = KuCoin (buy) → Bybit (sell)

Instead of reconfigure():
  Bot sets AXSUSDT as active symbol, sets dominant pairs
  ↓
  Normal rebalance loop:
    Detects KuCoin needs USDT → transfers from Binance ($0.01 BEP20 fee)
    Detects Bybit needs USDT → transfers from MEXC ($0.00 Arbitrum fee)
  ↓
  Normal trading loop:
    First few ticks: buys AXS on KuCoin, sells AXS on Bybit
    Crypto positions build up organically on seller exchanges
  ↓
  All movements tracked as normal transfers/trades with real fees
```

### Benefits

| Aspect | Current (`reconfigure()`) | Incremental |
|--------|--------------------------|-------------|
| Capital movement visibility | Hidden (instant teleport) | Full audit trail in XLSX + dashboard |
| Transfer fees in P&L | Not counted | Counted as normal transfer fees |
| Rebalance gate compliance | Bypassed | ROI, worthiness, hourly cap all apply |
| Code complexity | Special `reconfigure()` path | Removed — uses existing pipelines |
| Simulation realism | Unrealistic (instant move) | Matches real trading behavior |
| Multi-symbol activation | Atomic (all at once) | Sequential (may need coordination) |

### Challenges

#### Slower Activation

Activation would take minutes instead of being instant. The rebalance loop runs every tick but has cooldowns (60s per exchange/direction). During the transition period, the bot might miss trading opportunities while capital is still moving to the right exchanges.

**Mitigation**: Could temporarily reduce rebalance cooldowns during post-activation phase, or add an "urgent rebalance" mode that runs transfers back-to-back until capital is positioned.

#### Multi-Symbol Activation

The current system activates multiple symbols atomically via `reconfigure()`. With incremental activation, multiple symbols competing for the same USDT pool could cause thrashing (transfer to KuCoin for symbol A, then transfer away from KuCoin for symbol B).

**Mitigation**: Activate symbols sequentially with a brief settling period between each. Or compute the aggregate capital needs across all new symbols first, then execute a single round of transfers.

#### `initialize_crypto()` Replacement

`initialize_crypto()` currently converts USDT to crypto instantly on seller exchanges. With incremental activation, the initial crypto positions would need to be established through actual market buy orders (internal buys), which incur taker fees and slippage.

**Mitigation**: Use the existing internal buy rebalance path (`[Balance] Internal buy`) which already handles this. The first few trades might have reduced position sizes until crypto builds up on seller exchanges.

#### Capital Fragmentation

After demotion, USDT may be scattered across many exchanges in small amounts. The rebalance logic might not consolidate efficiently if individual amounts fall below transfer minimums.

**Mitigation**: Run `consolidate_to_bitfinex()` after demotion (already implemented via `_redistribute_post_demotion()`), then distribute from Bitfinex hub at $0 withdrawal fee.

### Implementation Sketch

```python
# In optimizer.py: _complete_discovery()

# Current approach (to be replaced):
#   balance.reconfigure(new_symbols, dominant_pairs, allocations)
#   monitor.reconfigure(new_symbols)

# Incremental approach:
def _complete_discovery_incremental(self):
    # 1. Update active symbols and dominant pairs (no balance changes)
    self._active_symbols = new_symbols
    self._dominant_pairs = dominant_pairs

    # 2. Notify monitor of new symbols (no balance reset)
    self._monitor.update_active_symbols(new_symbols)

    # 3. Normal rebalance loop handles capital positioning
    #    - _rebalance_usdt() moves USDT to buyer exchanges
    #    - _rebalance_crypto() handles seller exchanges via internal buy
    #    - All transfers go through normal gates and fee tracking
```

### Priority

**Low** — the current `reconfigure()` approach is functional and sufficient for simulation and demo modes. This improvement becomes more important when transitioning to live trading, where every dollar movement must be auditable and transfer fees are real costs. It is primarily a polish/realism improvement that also simplifies the codebase by removing a special-case code path.
