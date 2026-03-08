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

### Status (as of Session #15, 2026-03-07)

**Still relevant but lower urgency than initially written.** The core problem (hidden activation costs not counted in P&L) is real — Session #15 showed $2.10 in rotation fees that were tracked but still caught users off guard. However, the `reconfigure()` path now uses `balance.reconfigure()` (not nuclear `reset()`), which preserves trades, transfer fees, P&L buckets, and cumulative state. The bigger problem observed in practice is **rotation churn** (7 rotations in 5h, 62% of gross eaten by fees) — incremental activation would make rotation slower but wouldn't prevent bad rotations. The newly added `pair_fee_exceeds_net` gate on rotations addresses the root cause more directly.

**Recommendation**: Defer until live trading preparation. The simulation already tracks rotation fees accurately. The value of this feature is in real-mode auditability, not simulation accuracy.

## Time-of-Day Adaptive Trading

### Problem

Arbitrage profitability varies significantly by hour. Analysis of Session #15 (24h, 506 trades, 6 active exchanges) reveals that some hours produce 10-50x more profit than others, with some hours producing zero or near-zero returns.

### Session #15 Hourly Analysis (Mar 6-7, 2026)

| Rank | Hour (UTC) | Trades | PNL | Neg% | Avg Net% | Best Net% | Symbol(s) | Condition |
|:----:|------------|:------:|----:|:----:|:--------:|:---------:|-----------|-----------|
| 1 | 10:00 | 56 | +$0.99 | 0% | +0.088% | +0.198% | SNX, DYDX | Excellent — wide spreads, zero losers |
| 2 | 03:00 | 106 | +$0.79 | 0% | +0.044% | +0.068% | ORDI | Very good — high frequency, all profitable |
| 3 | 23:00 | 73 | +$0.49 | 4% | +0.060% | +0.138% | DYDX | Good — strong spread, few losers |
| 4 | 14:00 | 63 | +$0.32 | 14% | +0.033% | +0.045% | EIGEN, PENDLE | Moderate — volume but thin margins |
| 5 | 00:00 | 47 | +$0.18 | 17% | +0.038% | +0.137% | DYDX | Moderate — decent spread, some losers |
| 6 | 15:00 | 25 | +$0.16 | 0% | +0.039% | +0.045% | PENDLE | Moderate — clean but low frequency |
| 7 | 22:00 | 28 | +$0.13 | 4% | +0.034% | +0.079% | DYDX | Moderate — steady, thin margins |
| 8 | 05:00 | 20 | +$0.08 | 0% | +0.033% | +0.068% | ORDI | Thin — all profitable but low volume |
| 9 | 07:00 | 2 | +$0.06 | 0% | +0.102% | +0.102% | DYDX | Sparse — only 2 trades but wide spread |
| 10 | 12:00 | 14 | +$0.04 | 64% | +0.015% | +0.106% | W | Poor — 64% losers, barely positive |
| 11 | 11:00 | 7 | +$0.04 | 0% | +0.032% | +0.071% | SNX | Thin — low volume, decent margins |
| 12 | 21:00 | 48 | +$0.02 | 0% | +0.007% | +0.033% | SNX | Very thin — high volume but $0.0004/trade |
| 13 | 01:00 | 7 | +$0.01 | 14% | +0.021% | +0.021% | DYDX | Very thin — barely profitable |
| 14 | 13:00 | 11 | +$0.01 | 45% | +0.009% | +0.028% | EIGEN, ORDI | Near-zero — 45% losers, break-even |
| — | 15-20:00* | 0 | — | — | — | — | — | Discovery (6h scoring) |
| — | 02,04,06,08-09 | 0 | — | — | — | — | — | Rotation churn / gate closures / discovery |

*Mar 6 hours. All other hours are Mar 7.

### Session #16 Hourly Analysis (Mar 7-8, 2026)

24h34m session, 821 trades, 10 symbols. Saturday (Mar 7 is a Friday evening → Saturday).

| Rank | Hour (UTC) | Trades | PNL | Neg% | Avg Net% | Best Net% | Symbol(s) | Condition |
|:----:|------------|:------:|----:|:----:|:--------:|:---------:|-----------|-----------|
| 1 | Mar 8 10:00 | 146 | +$1.87 | 1% | +0.068% | +0.131% | STRK | Excellent — $0.013/trade avg |
| 2 | Mar 8 09:00 | 152 | +$0.47 | 1% | +0.019% | +0.091% | STRK | Excellent — high frequency |
| 3 | Mar 8 01:00 | 34 | +$0.34 | 35% | +0.053% | +0.144% | DYDX | Moderate — high neg rate |
| 4 | Mar 7 19:00 | 55 | +$0.32 | 18% | +0.031% | +0.122% | AXS, SNX | Good |
| 5 | Mar 8 11:00 | 60 | +$0.28 | 2% | +0.033% | +0.157% | STRK | Very good |
| 6 | Mar 7 20:00 | 42 | +$0.25 | 5% | +0.041% | +0.092% | STRK | Very good |
| 7 | Mar 8 15:00 | 74 | +$0.20 | 15% | +0.017% | +0.059% | STRK | Good |
| 8 | Mar 8 16:00 | 59 | +$0.18 | 10% | +0.021% | +0.084% | STRK | Good |
| 9 | Mar 8 03:00 | 20 | +$0.11 | 30% | +0.027% | +0.074% | COMP, DYDX | Moderate — COMP all negative |
| 10 | Mar 8 14:00 | 11 | +$0.10 | 0% | +0.051% | +0.085% | STRK | Good — zero losers |
| 11 | Mar 8 00:00 | 23 | +$0.10 | 9% | +0.024% | +0.097% | DYDX | Moderate |
| 12 | Mar 7 16:00 | 14 | +$0.08 | 29% | +0.027% | +0.040% | DYDX | Moderate |
| 13 | Mar 7 17:00 | 62 | +$0.07 | 3% | +0.011% | +0.068% | PEPE | Moderate — razor-thin margins |
| 14 | Mar 8 02:00 | 5 | +$0.05 | 40% | +0.046% | +0.084% | DYDX | Thin — high neg rate |
| 15 | Mar 7 18:00 | 6 | +$0.03 | 0% | +0.040% | +0.083% | PEPE | Thin |
| 16 | Mar 7 23:00 | 24 | +$0.02 | 17% | +0.008% | +0.034% | DYDX | Thin — razor-thin margins |
| 17 | Mar 8 13:00 | 12 | +$0.02 | 0% | +0.008% | +0.029% | STRK | Thin |
| 18 | Mar 8 12:00 | 4 | +$0.01 | 0% | +0.016% | +0.056% | STRK | Near-zero — only 4 trades |
| 19 | Mar 8 04:00 | 1 | +$0.00 | 0% | +0.021% | +0.021% | DYDX | Near-zero |
| 20 | Mar 7 22:00 | 1 | +$0.00 | 0% | +0.009% | +0.009% | DYDX | Near-zero — just activated |
| 21 | Mar 7 21:00 | 16 | -$0.01 | 100% | -0.008% | -0.007% | W | Negative — 100% losers |
| — | 05-08:00 | 0 | — | — | — | — | — | Discovery / no tradeable symbols |

### Cross-Session Comparison (S15 vs S16)

Hours where both sessions had trading data, sorted by average PNL:

| Hour | S15 PNL | S15 Sym | S16 PNL | S16 Sym | Avg PNL | Consistency |
|:----:|--------:|---------|--------:|---------|--------:|:-----------:|
| **10:00** | **$0.99** | SNX,DYDX | **$1.87** | STRK | **$1.43** | **High — different symbols, same result** |
| 03:00 | $0.79 | ORDI | $0.11 | COMP,DYDX | $0.45 | Medium — S16 had COMP drag |
| 14:00 | $0.32 | EIGEN,PENDLE | $0.10 | STRK | $0.21 | Medium — both positive |
| 15:00 | $0.16 | PENDLE | $0.20 | STRK | $0.18 | Medium — both positive |
| 01:00 | $0.01 | DYDX | $0.34 | DYDX | $0.18 | Low — large difference |
| 00:00 | $0.18 | DYDX | $0.10 | DYDX | $0.14 | Medium — both positive |
| 11:00 | $0.04 | SNX | $0.28 | STRK | $0.16 | Low — large difference |
| 22:00 | $0.13 | DYDX | $0.00 | DYDX | $0.07 | Low — S16 just activated |
| 23:00 | $0.49 | DYDX | $0.02 | DYDX | $0.26 | Low — large difference |
| 12:00 | $0.04 | W | $0.01 | STRK | $0.03 | Medium — both weak |
| **13:00** | **$0.01** | EIGEN,ORDI | **$0.02** | STRK | **$0.01** | **High — consistently weak** |
| **21:00** | **$0.02** | SNX | **-$0.01** | W | **$0.01** | **High — consistently weak** |

### Observed Patterns

**Updated after 2 sessions (S15: Mar 6-7, S16: Mar 7-8):**

1. **10:00 UTC is the standout hour** — $0.99 and $1.87 across two sessions with *different symbols* (SNX/DYDX vs STRK). This strongly suggests a market-structure effect, not a symbol effect. Corresponds to 5PM BKK / 7PM JST — Asian evening, European morning overlap. Cross-exchange price discrepancies appear widest during this window.

2. **09:00-11:00 UTC block is consistently strong** — Combined $1.07 (S15, limited data) and $2.62 (S16). The morning UTC hours benefit from Asian market activity before European HFT competition tightens spreads.

3. **12:00-13:00 UTC is consistently weak** — Both sessions show near-zero PNL with high neg rates. European midday when co-located HFT firms dominate.

4. **21:00 UTC is consistently weak** — $0.02 and -$0.01. Pre-Asian, post-European dead zone.

5. **Overnight 23:00-03:00 is inconsistent** — S15 had $1.46 (best period), S16 only $0.62. Likely symbol-dependent: S15 had ORDI (best=+0.068%), S16 had DYDX (mixed) and COMP (all negative). More data needed to separate time vs symbol effect.

6. **Trading uptime improved** — S15: 56% trading time, S16: 80%. The pair fee gate reduced some churn, and STRK's 7h47m run was the longest ever. Higher uptime correlates with better $/hr even though individual trade margins were thinner.

### Proposed Feature: Time-of-Day Adaptive Mode

**Concept**: Use historical hourly profitability data to adjust trading behavior by time of day. During consistently profitable hours, be more aggressive (larger trades, lower thresholds). During consistently poor hours, be more conservative (smaller trades, higher thresholds, or pause entirely).

**Possible adaptive behaviors:**

| Behavior | Profitable Hours | Poor Hours |
|----------|-----------------|------------|
| Trade size multiplier | 1.5-2.0x | 0.5-0.75x |
| min_net_profit_pct | Lower (more trades) | Higher (filter losers) |
| Rotation willingness | Higher (capture opportunities) | Lower (avoid churn costs) |
| Position cap | Relaxed | Tighter |
| Rebalance aggressiveness | Higher | Conservative |

### Data Requirements

**One day is not enough.** Session #15 had too many confounding factors:
- 6h initial discovery (no trading data for those hours)
- Rotation churn created artificial gaps
- Different symbols active at different hours (SNX was great at 10:00, but was it the hour or the symbol?)
- Gate closures distorted some hours (04:00 had zero trades due to net_pnl_gate, not market conditions)

**What we need before implementing:**
- **Minimum 5-7 sessions** (5-7 days) of continuous 24h data
- **Consistent configuration** across sessions (same exchanges, similar settings) to isolate time-of-day effects from config changes
- **Per-hour averages across days** to identify statistically reliable patterns vs one-off noise
- **Separate symbol effects from time effects** — is 10:00 UTC always good, or was it just because SNX happened to be active?
- **Day-of-week analysis** — weekday vs weekend crypto market behavior differs (lower institutional volume on weekends)

### Data Collection Plan

Each session should log or export (already available in XLSX hourly P&L sheet):
- Per-hour: trade count, gross PNL, avg net%, % losers, active symbols
- Per-hour-per-symbol: to separate symbol quality from time quality

After 5+ sessions, aggregate into:

```
Hour (UTC) | Avg Trades | Avg PNL | Avg Net% | % Sessions Profitable | Confidence
10:00      |    45      |  $0.50  |  0.08%   |        80%           |   High
03:00      |    80      |  $0.40  |  0.04%   |        60%           |   Medium
12:00      |    10      |  $0.02  |  0.01%   |        40%           |   Low
```

### Implementation Sketch (Deferred)

```python
# In monitor.py or optimizer.py
class TimeOfDayProfile:
    """Tracks hourly profitability across sessions."""
    def __init__(self):
        self._hourly_stats: dict[int, HourlyStats] = {}  # hour (0-23) -> stats
        self._min_sessions: int = 5  # minimum sessions before acting

    def get_hour_multiplier(self, hour_utc: int) -> float:
        """Returns trade size multiplier for current hour."""
        stats = self._hourly_stats.get(hour_utc)
        if not stats or stats.session_count < self._min_sessions:
            return 1.0  # default, no adjustment
        # Scale based on historical avg PNL relative to session average
        ratio = stats.avg_pnl / self._overall_avg_pnl
        return max(0.5, min(2.0, ratio))
```

### Priority

**Low — data collection phase.** Cannot implement until we have 5+ days of consistent data. For now, focus on collecting clean hourly data across sessions. The feature itself is a multiplier on existing profitability — it only helps if the bot is already net-positive.

### Next Steps

1. Run 5+ sessions with stable configs (v0.25.6+ with rotation pair fee gate)
2. After each session, log the hourly table in SESSIONS.md
3. After 5 sessions, compare hourly patterns across days
4. If consistent patterns emerge (e.g., 22:00-03:00 UTC is always 3x better), implement the adaptive mode
5. Start conservative: only adjust trade size multiplier (0.75x-1.5x range), no pausing

## Plan Status Summary (as of Session #16)

| Plan | Priority | Status | Recommendation |
|------|----------|--------|----------------|
| Net%-Based Dynamic Trade Sizing | — | **Implemented** (v0.22.0) | Already live as `net_pct_sizing_enabled`. Working well — fat spreads get bigger trades. |
| Incremental Symbol Activation | Low | Deferred | Root cause (rotation churn) better addressed by pair fee gate. Defer until live trading prep. |
| Time-of-Day Adaptive Trading | Low | Data collection (2/5 sessions) | 10:00 UTC confirmed as best hour across 2 sessions. Need 3 more for implementation. |
