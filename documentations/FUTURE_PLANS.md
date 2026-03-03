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
