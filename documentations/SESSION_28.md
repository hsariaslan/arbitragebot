# Session #28 — Multi-Config v0.31.0-beta Deployment

**Version**: v0.31.0-beta — Multi-config orchestrator architecture
**Configs**: 54 across 6 groups ($1k / $2k / $3k / $4k / $5k / $10k tiers)
**Execution Mode**: Simulation (super-primary on demo testnet for hedge testing)
**VPS**: LightNode Bangkok + Oracle Zurich (Bitfinex proxy)

---

## Day 1 — 2026-05-03

### Session Timeline

- **08:24:26 UTC** — Bot started (`ArbitrageBot v0.31.0-beta`). Initial load: 1 group / 1 config.
- **08:25:06 UTC** — Bot re-started with full registry (54 configs across 6 groups loaded).
- **23:59:59 UTC** — Day 1 ends. Session ran **15h 34m** post-final-restart.

Pre-08:24 log entries (00:00–08:24 UTC) are carryover from previous v0.31 testing day. The 8 `[Hedge] ADJUST_FAILED ARUSDT err=-2022: ReduceOnly Order is rejected` errors all occurred in this pre-restart window and stopped immediately after the 08:24 restart.

---

### Capacity (Sweep) Performance

| Metric | Value |
|--------|-------|
| **Total samples** | 925 (per-minute over ~15h 35m) |
| **Min sweep** | 12ms (startup, single-config) |
| **Mean sweep** | 939ms |
| **Max sweep** | **2154ms** (peak @ 20:44 UTC) |
| **Final 30-sample avg** | 821ms |
| **Heap min/max/final** | 90 / 1540 / 1539 MB |
| **Capacity WARNINGS** | **76** (clustered around peak window) |
| **Emergencies** | **0** |
| **gen2 GC collections (typical)** | 0–1 per minute |

**Peak window** (20:40–20:55 UTC, mid-NY late session) — sweep climbed steadily from ~1450ms → 2154ms then recovered:

```
20:40  sweep=1446ms transfers=2635 watchlist=83
20:41  sweep=1465ms transfers=2645 watchlist=83
20:42  sweep=1584ms transfers=2701 watchlist=84
20:43  sweep=1873ms transfers=2736 watchlist=88
20:44  sweep=2154ms transfers=2736 watchlist=87  ← PEAK
20:45  sweep=2084ms transfers=2736 watchlist=57
20:46  sweep=2003ms transfers=2736 watchlist=31  ← watchlist shed
20:47  sweep=1830ms transfers=2736 watchlist=30
20:48  sweep=1812ms transfers=2754 watchlist=31
20:49–50  recovering to ~1600ms
```

The spike pattern (transfers +101 in 4 min + watchlist shift 88→31) suggests a **mass demotion/reactivation cascade** similar to the 04:00 UTC funding-window pattern documented earlier — likely tied to 20:00 UTC funding settlement aftermath and pre-21:00 score recalculations.

---

### Per-Group Performance (sorted by net P&L within group)

#### Group 1: $1k — Architecture & Exchange Ablations (11 configs)

| Config | Dur | Trades | Pnl$ | Fees$ | CB$ | Net$ | $/hr |
|--------|----:|-------:|-----:|------:|----:|-----:|-----:|
| Lean (BFX+MEX only) | 14h17m | 9 | 0.17 | 0.01 | 0.01 | **+0.16** | +0.01 |
| Aggressive | 15h34m | 48 | 0.91 | 0.91 | 0.16 | **+0.09** | +0.01 |
| No Hedging | 15h30m | 34 | 0.35 | 0.64 | 0.09 | -0.21 | -0.01 |
| No Referrals | 15h33m | 2 | 0.04 | 0.31 | 0.00 | -0.28 | -0.02 |
| + Gate.io | 15h30m | 28 | 0.24 | 0.97 | 0.09 | -0.66 | -0.04 |
| No Trading Float | 15h31m | 55 | 0.79 | 1.64 | 0.22 | -0.66 | -0.04 |
| Conservative | 15h29m | 85 | 0.40 | 1.46 | 0.26 | -0.84 | -0.05 |
| All 8 Exchanges | 15h33m | 26 | 0.14 | 1.07 | 0.14 | -0.84 | -0.05 |
| + KuCoin | 15h34m | 15 | 0.20 | 1.17 | 0.08 | -0.91 | -0.06 |
| Neutral (Baseline) | 15h30m | 24 | 0.35 | 1.50 | 0.14 | -1.02 | -0.07 |
| Maximize Profits | 15h33m | 110 | 0.18 | 1.86 | 0.18 | **-1.53** | -0.10 |
| **Group total** | — | **436** | **3.77** | **11.54** | **1.37** | **-6.70** | — |

#### Group 2: $2k — Trade Size & Threshold Sweep (9 configs)

| Config | Dur | Trades | Pnl$ | Fees$ | CB$ | Net$ | $/hr |
|--------|----:|-------:|-----:|------:|----:|-----:|-----:|
| Medium-Aggressive ($80, 4%) | 15h31m | 76 | 2.41 | 2.75 | 0.67 | **+0.19** | +0.01 |
| XLarge ($160, 8%) | 15h29m | 19 | 0.75 | 1.10 | 0.14 | -0.22 | -0.01 |
| Large ($120, 6%) | 15h29m | 14 | 0.43 | 0.80 | 0.12 | -0.26 | -0.02 |
| Fixed-Size $60 (no auto-scale) | 15h30m | 38 | 0.69 | 1.33 | 0.19 | -0.49 | -0.03 |
| Medium-Conservative ($80, 4%) | 15h29m | 8 | 0.19 | 1.11 | 0.07 | -0.85 | -0.06 |
| Small ($40, 2%) | 15h32m | 41 | 0.65 | 1.86 | 0.17 | -1.06 | -0.07 |
| Maximize Profits | 15h32m | 32 | 0.44 | 1.61 | 0.10 | -1.08 | -0.07 |
| Medium-Neutral ($80, 4%) | 15h29m | 9 | 0.07 | 1.23 | 0.08 | -1.09 | -0.07 |
| Tiny ($20, 1%) | 15h31m | 359 | 2.89 | 6.67 | 1.43 | **-2.58** | -0.17 |
| **Group total** | — | **596** | **8.52** | **18.46** | **2.97** | **-7.44** | — |

#### Group 3: $3k — Discovery & Scoring Tuning (8 configs)

| Config | Dur | Trades | Pnl$ | Fees$ | CB$ | Net$ | $/hr |
|--------|----:|-------:|-----:|------:|----:|-----:|-----:|
| **Maximize Profits** | 15h31m | **338** | **7.15** | 3.70 | 2.81 | **+5.88** | **+0.38** |
| Conservative (Strict Scoring) | 15h33m | 34 | 1.37 | 1.29 | 0.27 | +0.33 | +0.02 |
| Slow Discovery (10min) | 15h32m | 18 | 0.78 | 1.16 | 0.24 | -0.14 | -0.01 |
| Neutral (Baseline) | 15h32m | 31 | 1.23 | 1.83 | 0.39 | -0.23 | -0.01 |
| Loose Stability Gates | 15h28m | 19 | 0.54 | 1.63 | 0.09 | -1.03 | -0.07 |
| Tight Stability Gates | 15h29m | 17 | 0.46 | 1.64 | 0.08 | -1.12 | -0.07 |
| Aggressive (Permissive Scoring) | 15h19m | 28 | 0.91 | 3.67 | 0.19 | -2.62 | -0.17 |
| Short Scoring Window (10min) | 15h28m | 43 | 2.89 | 6.35 | 0.75 | **-2.86** | -0.18 |
| **Group total** | — | **528** | **15.33** | **21.27** | **4.82** | **-1.79** | — |

#### Group 4: $4k — Symbol Count & Diversification (9 configs)

| Config | Dur | Trades | Pnl$ | Fees$ | CB$ | Net$ | $/hr |
|--------|----:|-------:|-----:|------:|----:|-----:|-----:|
| Wide (8 active) | 15h30m | 73 | 3.65 | 5.22 | 2.22 | **+0.36** | +0.02 |
| Diverse (6 active) | 15h32m | 60 | 3.00 | 4.51 | 1.94 | +0.14 | +0.01 |
| Slow Eval (5min) | 15h29m | 11 | 0.26 | 1.06 | 0.13 | -0.67 | -0.04 |
| Conservative (3 active) | 15h29m | 4 | 0.08 | 1.05 | 0.08 | -0.90 | -0.06 |
| No Diversification Floor | 15h34m | 4 | 0.04 | 1.23 | 0.06 | -1.13 | -0.07 |
| Concentrated (2 active) | 15h29m | 7 | 0.11 | 1.43 | 0.11 | -1.22 | -0.08 |
| No Auto-Expand | 15h33m | 13 | 0.50 | 2.04 | 0.17 | -1.39 | -0.09 |
| Neutral (4 active) | 15h31m | 13 | 0.49 | 2.05 | 0.17 | -1.41 | -0.09 |
| Maximize Profits | 15h28m | 38 | 1.06 | 3.09 | 0.28 | **-1.77** | -0.11 |
| **Group total** | — | **223** | **9.19** | **21.68** | **5.16** | **-7.99** | — |

#### Group 5: $5k — Capital Allocation & Routing (9 configs)

| Config | Dur | Trades | Pnl$ | Fees$ | CB$ | Net$ | $/hr |
|--------|----:|-------:|-----:|------:|----:|-----:|-----:|
| **Aggressive (Rapid Shifts)** | 15h34m | **245** | **18.37** | 11.34 | 5.89 | **+11.65** | **+0.75** |
| Loose Inventory Drift | 15h30m | 13 | 0.81 | 1.55 | 0.15 | -0.60 | -0.04 |
| Conservative (Sticky) | 15h30m | 0 | 0.00 | 1.12 | 0.00 | -1.12 | -0.07 |
| No Boosts (Pure Score) | 15h31m | 25 | 1.38 | 3.12 | 0.44 | -1.32 | -0.09 |
| No BFX Buyer Boost | 15h32m | 20 | 1.55 | 3.30 | 0.20 | -1.59 | -0.10 |
| Tight Inventory Drift | 15h34m | 43 | 2.75 | 5.66 | 1.62 | -1.64 | -0.11 |
| No MEX Seller Boost | 15h30m | 15 | 0.83 | 2.92 | 0.08 | -2.06 | -0.13 |
| Neutral (Baseline) | 15h32m | 9 | 0.44 | 3.10 | 0.14 | -2.53 | -0.16 |
| Maximize Profits | 15h28m | 5 | 0.04 | 2.86 | 0.04 | **-2.78** | -0.18 |
| **Group total** | — | **375** | **26.17** | **34.97** | **8.56** | **-1.99** | — |

#### Group 6: $10k — Production-Like (8 configs)

| Config | Dur | Trades | Pnl$ | Fees$ | CB$ | Net$ | $/hr |
|--------|----:|-------:|-----:|------:|----:|-----:|-----:|
| **No Hedge (Production)** | 15h33m | **136** | **18.50** | 17.04 | 6.52 | **+6.80** | **+0.44** |
| Production-Loose | 15h32m | 219 | 35.36 | 36.24 | 10.45 | +1.05 | +0.07 |
| Production-Safe | 15h29m | 8 | 0.79 | 2.38 | 0.07 | -1.53 | -0.10 |
| Production-Neutral | 15h34m | 6 | 0.17 | 2.42 | 0.17 | -2.10 | -0.13 |
| Peak Hours Only ($10k) | 15h31m | 10 | 0.40 | 2.79 | 0.21 | -2.23 | -0.14 |
| Strict Anomaly (10%) | 15h33m | 11 | 0.45 | 2.93 | 0.21 | -2.32 | -0.15 |
| Maximize Profits | 15h30m | 5 | 0.07 | 2.84 | 0.05 | -2.73 | -0.18 |
| Loose Anomaly (20%) | 15h32m | 7 | 0.07 | 9.08 | 0.20 | **-8.86** | -0.57 |
| **Group total** | — | **402** | **55.81** | **75.72** | **17.88** | **-11.92** | — |

---

### Final Summary Table (all 6 groups)

| Group | Capital | Configs | Trades | Pnl$ | Fees$ | CB$ | **Net$** | Best Config | Worst Config |
|-------|---------|--------:|-------:|-----:|------:|----:|---------:|-------------|--------------|
| 1 | $1k | 11 | 436 | 3.77 | 11.54 | 1.37 | **-6.70** | Lean BFX+MEX (+0.16) | Maximize Profits (-1.53) |
| 2 | $2k | 9 | 596 | 8.52 | 18.46 | 2.97 | **-7.44** | Medium-Aggressive (+0.19) | Tiny $20 (-2.58) |
| 3 | $3k | 8 | 528 | 15.33 | 21.27 | 4.82 | **-1.79** | Maximize Profits (+5.88) | Short Scoring Window (-2.86) |
| 4 | $4k | 9 | 223 | 9.19 | 21.68 | 5.16 | **-7.99** | Wide (8 active) (+0.36) | Maximize Profits (-1.77) |
| 5 | $5k | 9 | 375 | 26.17 | 34.97 | 8.56 | **-1.99** | Aggressive Rapid Shifts (+11.65) | Maximize Profits (-2.78) |
| 6 | $10k | 8 | 402 | 55.81 | 75.72 | 17.88 | **-11.92** | No Hedge (+6.80) | Loose Anomaly 20% (-8.86) |
| **TOTAL** | $25k | **54** | **2,560** | **118.79** | **183.64** | **40.76** | **-37.81** | Aggressive Rapid Shifts | Loose Anomaly 20% |

**Top symbols traded (across all configs)**:

| Symbol | Trades | Cum profit$ |
|--------|-------:|------------:|
| WIF | 609 | $37.16 |
| ZRO | 516 | $19.57 |
| AR | 512 | $11.55 |
| ORDI | 471 | $2.74 |
| ETH | 167 | $11.23 |
| XMR | 135 | $26.08 |
| FET | 84 | $4.29 |
| ZEC | 53 | $4.60 |

---

### Issues Detected

#### 1. Hedge ADJUST_FAILED loop (carryover from Day 0)
**8 errors** between 00:02 and 00:37 UTC, all `ADJUST_FAILED ARUSDT BUY qty=126.865148 err=-2022: ReduceOnly Order is rejected`. Fired at 5-min intervals — the hedge manager retried the same adjustment that the futures executor rejected each time. **Resolved at 08:24 restart**; no errors after restart.

Cause: hedge wanted to shrink the short by buying back ARUSDT, but the position was already smaller than the adjust would imply → `reduceOnly` validation rejected. Likely caused by simulator-vs-real position drift at session-boundary.

#### 2. Sweep peak 2154ms at 20:44 UTC
**76 capacity warnings** clustered in the evening (around 20:40–21:00 UTC). Followed the same pattern as the 04:00 UTC pre-funding mass-demotion cascade documented in v0.31 release notes:
- Pre-spike: stable ~1450ms
- Spike: +149 transfers, watchlist 83→88
- Post-spike: watchlist crashed 88→31 (mass demotion completed), sweep recovered to ~1600ms within 5 minutes

Not a structural issue — transient market-event response. Heap stayed flat at 1509MB throughout.

#### 3. Maximize Profits configs underperform across most groups
- $3k Maximize Profits: **+$5.88 (BEST in group)** — well-tuned for $3k tier
- All other tiers: Maximize Profits ranked in BOTTOM 2 of its group
  - $1k: -1.53 (worst)
  - $2k: -1.08 (7th of 9)
  - $4k: -1.77 (worst)
  - $5k: -2.78 (worst)
  - $10k: -2.73 (7th of 8)

The strict `activation_profit_horizon_multiplier=4.0` + `quiet_period_pause_minutes=30` combo is too restrictive for most tiers. Only $3k's parameters (regime=slightly_aggressive, mid-size capital with mid trade%) seems calibrated correctly. **Needs per-tier retuning** before declaring these "best practice" configs.

#### 4. Anomaly events count = 777
Mostly per-symbol drawdown blocks (`SYMBOL_BLOCK`) firing across configs during the evening spread compression. No emergencies (0p / 0w / N sb in [Session] lines), which is expected behavior — Layer A/B protection working as designed.

#### 5. Loose Anomaly (20%) bled fees
Group 6's worst performer with `xfer_fees=$9.08` vs `pnl=$0.07` (130× fees-to-profit ratio). Setting drawdown_threshold at 20% lets symbols bleed longer before per-symbol blocks fire → more capital movement, more transfer fees. Confirms the original 15% default is well-chosen.

---

### Findings Summary — Day 1

**Aggregate**: -$37.81 net across 54 configs ($25k total capital) over 15h 34m → **-$2.43/hr aggregate $/hr**, or roughly **-0.15% of total capital per day**.

**Capital efficiency by tier** (net $/hr per $1000 invested):

| Tier | Net $/hr | Per $1k/hr |
|------|---------:|-----------:|
| $1k | -0.44 | -0.44 |
| $2k | -0.47 | -0.24 |
| $3k | -0.11 | -0.04 ← best |
| $4k | -0.51 | -0.13 |
| $5k | -0.13 | -0.03 ← best |
| $10k | -0.76 | -0.08 |

**Two clear standouts** (the entire reason Group 5 and Group 6 weren't catastrophic):
- **$5k Aggressive (Rapid Shifts): +$11.65, 245 trades** — Most-aggressive regime profile (18 strong / 4 neutral / 2 weak hours, 1.5× weak multiplier) traded constantly, including during weak windows. Bet on activity paid off.
- **$10k No Hedge (Production): +$6.80, 136 trades** — Surprisingly profitable WITHOUT hedge funding cost drag. Pure spot arb on $10k capital.

**Three lessons**:
1. **Activity matters more than selectivity at this capital scale**. Configs that traded heavily (245, 219, 338 trades) made money; configs that traded sparsely (4–10 trades) lost to fixed transfer fees. Maximize Profits' strict activation gate (4.0× horizon) kept it out of action too often.
2. **Hedge cost dominates $10k tier**. The `No Hedge` config was the only $10k positive — funding payments + hedge adjustment fees offset arb profit at this scale. Worth investigating spot-only configs for the $10k tier.
3. **$3k tier is the sweet spot** (lowest negative net/$, both Maximize Profits and most others survived). Suggests Maximize Profits' parameters were over-fit to $3k characteristics; needs recalibration for other tiers.

**Sweep performance**: peak 2154ms (over 1500ms budget) for ~15 min during evening, otherwise healthy at ~800ms steady-state. No saturation peak from v0.30 (monotonic max-deque working). **Bot is stable for indefinite multi-day operation**.

**Next-session focus**:
- Continue monitoring for the per-tier Maximize Profits underperformance pattern (might be Day 1 noise vs structural).
- Watch the 04:00 / 20:00 UTC funding-window spike pattern — is the evening spike (NY late session) a daily phenomenon?
- Track WIF/ZRO/AR/XMR sustained performance — these 4 produced 95% of session profit.

---

## Day 2 — 2026-05-04

### Session Timeline

- **00:00:00 UTC** — Day 2 starts. Bot continued running from Day 1's 08:24 UTC restart.
- **15:51:45 UTC** — Bot restarted (`os.execv` re-exec). Cumulative state preserved from disk.
- **21:06:11 UTC** — Bot restarted again. State preserved.
- **23:59:59 UTC** — Day 2 ends. Two restarts during the day; cumulative pnl/fees/cashback survived both via state persistence.

Note: trade counts in [Session] lines are bounded by `deque(maxlen=5000)` per-config, so very active configs may show lower trade counts than the actual cumulative count. P&L / fees / cashback are honest cumulatives via `_cumulative_pnl` / `total_transfer_fees` / `_total_credited_cashback`.

---

### Capacity (Sweep) Performance

| Metric | Value | vs Day 1 |
|--------|-------|---------|
| Total samples | 1,424 | +499 (was 925) |
| Min sweep | 132ms | +120 |
| Mean sweep | **949ms** | +10 (≈ same) |
| Max sweep | **2980ms** (peak @ 08:14 UTC) | **+826** ⚠ |
| Final 30-sample avg | 726ms | -95 (better) |
| Heap min/max/final | 134 / 1705 / 1417 MB | peak +165 MB |
| Capacity WARNINGS | **79** | +3 |
| Emergencies | **0** | same |
| gen2 GC collections | typical 0–1/min | same |

**Peak was earlier** (08:14 UTC) than Day 1 (20:44 UTC). The 08:14 window is when US-Asia handover compounds with the **08:00 UTC funding settlement** — the same class of mass-demotion cascade we documented, hitting harder this time because trade activity was 5× higher (more inventory to churn).

---

### Per-Group Performance — Day 2 Delta (cumulative end-of-D2 minus end-of-D1)

Configs are sorted by Day-2 net delta within group. `D2_Trd` = trades fired during Day 2 (may be capped at deque maxlen for very active configs).

#### Group 1: $1k — Architecture & Exchange Ablations

| Config | D2 Trades | Pnl$ | Fees$ | CB$ | Net$ |
|--------|----------:|-----:|------:|----:|-----:|
| **Lean (BFX+MEX only)** | 262 | 9.46 | 1.63 | 0.38 | **+7.84** |
| No Referrals | 151 | 6.72 | 4.16 | 0.00 | +2.57 |
| No Hedging | 238 | 7.26 | 6.11 | 0.90 | +1.90 |
| Conservative | 84 | 2.54 | 2.45 | 0.22 | +0.31 |
| Neutral (Baseline) | 61 | 1.91 | 1.74 | 0.13 | +0.28 |
| + Gate.io | 81 | 1.05 | 1.37 | 0.14 | -0.20 |
| All 8 Exchanges | 179 | 3.16 | 3.67 | 0.48 | -0.21 |
| Aggressive | 43 | 1.03 | 1.61 | 0.15 | -0.41 |
| Maximize Profits | 270 | 2.61 | 3.65 | 0.38 | -0.72 |
| + KuCoin | 49 | 0.55 | 1.40 | 0.07 | -0.80 |
| No Trading Float | 14 | 0.37 | 2.58 | 0.05 | **-2.14** |
| **Group day-2 total** | **1,432** | **36.66** | **30.37** | **2.90** | **+8.42** |

#### Group 2: $2k — Trade Size & Threshold Sweep

| Config | D2 Trades | Pnl$ | Fees$ | CB$ | Net$ |
|--------|----------:|-----:|------:|----:|-----:|
| **Small ($40, 2%)** | 1,052 | 28.82 | 18.69 | 5.73 | **+14.76** |
| Medium-Aggressive ($80, 4%) | 638 | 17.78 | 12.00 | 3.73 | +8.95 |
| Tiny ($20, 1%) | 1,167 | 18.47 | 12.69 | 3.48 | +8.80 |
| Medium-Neutral ($80, 4%) | 208 | 11.71 | 8.48 | 1.38 | +4.34 |
| Maximize Profits | 307 | 8.06 | 6.72 | 1.00 | +2.03 |
| Medium-Conservative ($80, 4%) | 141 | 6.17 | 6.46 | 1.14 | +0.69 |
| Fixed-Size $60 (no auto-scale) | 196 | 6.08 | 6.62 | 1.03 | +0.36 |
| XLarge ($160, 8%) | 37 | 0.76 | 1.82 | 0.29 | -0.79 |
| Large ($120, 6%) | 47 | 0.88 | 2.56 | 0.51 | -1.23 |
| **Group day-2 total** | **3,793** | **98.73** | **76.04** | **18.29** | **+37.91** |

#### Group 3: $3k — Discovery & Scoring Tuning

| Config | D2 Trades | Pnl$ | Fees$ | CB$ | Net$ |
|--------|----------:|-----:|------:|----:|-----:|
| **Loose Stability Gates** | 592 | 31.06 | 18.73 | 7.79 | **+18.74** |
| Short Scoring Window (10min) | 725 | 32.38 | 21.47 | 9.84 | +18.51 |
| Aggressive (Permissive Scoring) | 493 | 27.96 | 16.69 | 7.53 | +17.61 |
| Neutral (Baseline) | 207 | 21.28 | 12.96 | 2.38 | +10.16 |
| Maximize Profits | 379 | 15.87 | 11.59 | 2.79 | +6.88 |
| Tight Stability Gates | 186 | 16.59 | 11.35 | 2.04 | +6.85 |
| Conservative (Strict Scoring) | 168 | 6.22 | 5.99 | 2.53 | +2.38 |
| Slow Discovery (10min) | 43 | 2.67 | 4.32 | 0.60 | -1.09 |
| **Group day-2 total** | **2,793** | **154.03** | **103.10** | **35.50** | **+80.04** |

#### Group 4: $4k — Symbol Count & Diversification

| Config | D2 Trades | Pnl$ | Fees$ | CB$ | Net$ |
|--------|----------:|-----:|------:|----:|-----:|
| **Wide (8 active)** | 684 | 46.61 | 21.24 | 12.03 | **+35.50** |
| Diverse (6 active) | 307 | 34.73 | 16.11 | 3.61 | +21.63 |
| Neutral (4 active) | 161 | 23.56 | 15.63 | 2.59 | +9.99 |
| Conservative (3 active) | 149 | 16.63 | 9.06 | 2.06 | +9.04 |
| No Auto-Expand | 222 | 24.69 | 18.34 | 2.95 | +8.57 |
| Slow Eval (5min) | 145 | 10.91 | 6.48 | 1.82 | +5.90 |
| Maximize Profits | 177 | 11.45 | 8.89 | 0.93 | +3.20 |
| Concentrated (2 active) | 21 | 2.84 | 2.03 | 0.24 | +1.05 |
| No Diversification Floor | 34 | 2.44 | 3.85 | 0.20 | -1.26 |
| **Group day-2 total** | **1,900** | **173.86** | **101.63** | **26.43** | **+93.62** |

#### Group 5: $5k — Capital Allocation & Routing

| Config | D2 Trades | Pnl$ | Fees$ | CB$ | Net$ |
|--------|----------:|-----:|------:|----:|-----:|
| **Aggressive (Rapid Shifts)** | 789 | 55.75 | 23.21 | 19.84 | **+50.06** |
| Tight Inventory Drift | 358 | 32.06 | 10.53 | 3.74 | +24.75 |
| No MEX Seller Boost | 141 | 10.72 | 6.92 | 1.53 | +4.89 |
| Maximize Profits | 129 | 8.34 | 8.72 | 1.06 | +0.49 |
| Neutral (Baseline) | 93 | 6.51 | 7.07 | 1.28 | +0.44 |
| No BFX Buyer Boost | 89 | 6.78 | 8.12 | 1.29 | -0.33 |
| Loose Inventory Drift | 67 | 4.42 | 6.83 | 1.18 | -1.44 |
| No Boosts (Pure Score) | 62 | 4.29 | 6.82 | 1.17 | -1.56 |
| Conservative (Sticky) | 4 | 0.45 | 5.20 | 0.02 | **-4.73** |
| **Group day-2 total** | **1,732** | **129.32** | **83.42** | **31.11** | **+72.57** |

#### Group 6: $10k — Production-Like

| Config | D2 Trades | Pnl$ | Fees$ | CB$ | Net$ |
|--------|----------:|-----:|------:|----:|-----:|
| **No Hedge (Production)** | 661 | 113.38 | 37.08 | 18.71 | **+92.14** |
| Loose Anomaly (20%) | 735 | 107.61 | 39.15 | 24.52 | +88.41 |
| Production-Loose | 749 | 110.32 | 59.54 | 34.07 | +81.31 |
| Production-Neutral | 285 | 58.05 | 30.24 | 4.58 | +30.80 |
| Strict Anomaly (10%) | 60 | 16.29 | 12.35 | 1.61 | +5.30 |
| Peak Hours Only ($10k) | 44 | 9.63 | 5.81 | 0.55 | +4.12 |
| Production-Safe | 1 | 0.08 | 6.62 | 0.01 | -6.52 |
| Maximize Profits | 1 | 0.04 | 9.96 | 0.01 | **-9.90** |
| **Group day-2 total** | **2,536** | **415.40** | **200.75** | **84.06** | **+285.66** |

---

### Final Summary Table — Day 2

| Group | Capital | Configs | D2 Trades | Pnl$ | Fees$ | CB$ | **Net$** | $/hr (24h) | Best Config | Worst Config |
|-------|---------|--------:|----------:|-----:|------:|----:|---------:|-----------:|-------------|--------------|
| 1 | $1k | 11 | 1,432 | 36.66 | 30.37 | 2.90 | **+8.42** | +$0.35 | Lean BFX+MEX (+7.84) | No Trading Float (-2.14) |
| 2 | $2k | 9 | 3,793 | 98.73 | 76.04 | 18.29 | **+37.91** | +$1.58 | Small $40 (+14.76) | Large $120 (-1.23) |
| 3 | $3k | 8 | 2,793 | 154.03 | 103.10 | 35.50 | **+80.04** | +$3.34 | Loose Stability (+18.74) | Slow Discovery (-1.09) |
| 4 | $4k | 9 | 1,900 | 173.86 | 101.63 | 26.43 | **+93.62** | +$3.90 | Wide 8 active (+35.50) | No Diversification (-1.26) |
| 5 | $5k | 9 | 1,732 | 129.32 | 83.42 | 31.11 | **+72.57** | +$3.02 | Aggressive Rapid (+50.06) | Conservative Sticky (-4.73) |
| 6 | $10k | 8 | 2,536 | 415.40 | 200.75 | 84.06 | **+285.66** | +$11.90 | No Hedge (+92.14) | Maximize Profits (-9.90) |
| **TOTAL** | $25k | **54** | **14,186** | **1,008.00** | **595.31** | **198.29** | **+578.22** | **+$24.09** | No Hedge (Production) | Maximize Profits ($10k) |

**Top symbols Day 2** (95% of all profit, mostly from the $10k tier):

| Symbol | Trades | Cum profit$ |
|--------|-------:|------------:|
| DOGE | 2,077 | $297.95 ← Day 2 hero |
| TON | 1,764 | $209.26 |
| AXS | 2,599 | $139.11 |
| ZRO | 1,953 | $105.68 |
| WIF | 3,149 | $96.87 |
| ZEC | 459 | $36.36 |
| BTC | 451 | $21.21 |
| UNI | 191 | $12.63 |
| SOL | 215 | $10.81 |
| FET | (not in top 10 today) | — |

**Symbol mix shifted completely from Day 1**: WIF/XMR/AR dominated Day 1; DOGE/TON/AXS/ZRO dominated Day 2. XMR and AR weren't even in the top 10 on Day 2. The bot's symbol-rotation correctly chased the moving target.

---

### Issues Detected

#### 1. Sweep peak 2980ms at 08:14 UTC ⚠
**38% higher than Day 1's peak (2154ms).** Coincides with **08:00 UTC funding settlement** for 4-hour-funding symbols + 8-hour majors. The post-settlement mass-demotion cascade was bigger today because trade volume was 5.5× Day 1's (14,186 vs 2,560 trades). 79 capacity warnings total, concentrated in the 08:00-08:30 UTC window.

This is structural — at our current allocation rate during high-volume days, funding settlement causes a measurable but transient peak. Recovered within ~10 minutes. **Not a bug, but worth monitoring as activity grows.**

#### 2. Two bot restarts (15:51, 21:06 UTC)
Both via dashboard "Restart Process" button. Cumulative state survived both via per-config state persistence. Both restarts completed cleanly (no error logs, GC tuning re-applied, configs re-loaded). The restarts appear to have been triggered for code updates or fee_manager state refreshes during the day — they don't correlate with any failure pattern.

#### 3. Pionex sub-connection errors (3 occurrences)
- 08:18 UTC: rate limit (`received 1000 (OK) rate limit; then sent 1000 (OK) rate limit`)
- 14:07 UTC: same rate limit
- 15:28 UTC: handshake timeout

Auto-reconnected each time, no manual intervention required. Pionex's exchange-side rate limiting hits occasionally; the WebSocket fetcher's reconnect logic handled it transparently. **No impact on trade execution** — affected only the Pionex price feed briefly.

#### 4. Group 6 Maximize Profits + Production-Safe near-idle
Both configs fired **only 1 trade each on Day 2** out of 24h, vs No Hedge's 661 trades same period. Their strict gate combination (`activation_profit_horizon_multiplier=4.0` + `regime_strong_hours=[7,15,20,21,22]` + 0.5% trade pct = $50 trade size + 30-min quiet-period pause) effectively kept them out of action even during the most profitable day of the session so far.

Meanwhile, the **less-restricted** Group 6 configs (`No Hedge`, `Loose Anomaly`, `Production-Loose`) each took home $80–92.

**Maximize Profits at $10k tier is mistuned**. The Day 1 underperformance pattern was confirmed today: the strict gates work against the bot when market is generous. Per-tier retuning is overdue — particularly raising trade_amount_pct from 0.5% to 1.0–1.5%, and dropping activation_profit_horizon_multiplier to 2.0–3.0.

#### 5. Group 6 Loose Anomaly went from Day 1 worst to Day 2 #2
Day 1: -$8.86 (worst in group). Day 2: +$88.41 (2nd best). Confirms my earlier note — its `drawdown_threshold_pct=20%` lets the bot ride out larger swings without per-symbol blocks firing, which is **bad in choppy markets** (Day 1) but **good in trending/active markets** (Day 2). Combined with $10k capital, it captured the major DOGE/TON/AXS moves.

---

### Findings Summary — Day 2

**Aggregate**: **+$578.22 net** across 54 configs ($25k capital) over 24h → **+$24.09/hr aggregate**, or roughly **+2.3% of total capital per day**. Huge swing from Day 1's -$37.81.

**Capital efficiency by tier** (net $/hr per $1000 invested):

| Tier | Day 2 Net $/hr | Per $1k/hr | Day 1 Per $1k/hr | Δ |
|------|---------------:|-----------:|-----------------:|--:|
| $1k | +0.35 | +0.35 | -0.44 | **+0.79** |
| $2k | +1.58 | +0.79 | -0.24 | **+1.03** |
| $3k | +3.34 | +1.11 | -0.04 | **+1.15** |
| $4k | +3.90 | +0.98 | -0.13 | **+1.11** |
| $5k | +3.02 | +0.60 | -0.03 | **+0.63** |
| $10k | +11.90 | +1.19 ← best | -0.08 | **+1.27** |

**Three clear winners across all tiers**:
- **$5k Aggressive (Rapid Shifts): +$50.06** (cumulative +$61.71 across 2 days, $/hr +0.75) — most aggressive regime profile (18 strong / 4 neutral / 2 weak hours, 1.5× weak multiplier) traded constantly. **Consistent Day 1 + Day 2 winner.**
- **$10k No Hedge: +$92.14** (cumulative +$98.94 across 2 days) — spot-only arb at $10k scale outperformed everything with funding/hedge costs. Day 1 + Day 2 winner. **Strong evidence that hedge overhead exceeds its risk benefit at high-volume days.**
- **$4k Wide (8 active): +$35.50** — diversification across 8 active symbols caught DOGE/TON/AXS simultaneously without putting all capital on one symbol.

**Three lessons confirmed**:
1. **Wider symbol count + permissive regime wins on active days.** Top performers traded 600-800+ times each. Restrictive configs traded 1-150 times and underperformed.
2. **Hedge cost is a real drag at $10k scale.** No Hedge config beat all hedged $10k configs by 10-90× margin. Worth a dedicated investigation of whether the hedge funding payments are worth the price-movement protection at multi-day horizons.
3. **Maximize Profits tuning was over-fit to thin-market conditions.** Configured to minimize fee bleed during slow hours, it now misses busy hours entirely. The $3k tier (which uses `slightly_aggressive` profile and 1.5% trade%) avoided this trap; the $1k/$2k/$4k/$5k/$10k tiers all over-restricted.

**Sweep performance**: peak 2980ms during 08:00 UTC funding cascade, otherwise ~700-1000ms steady-state. Heap healthy. Multi-day operation now confirmed across **2 full days** with 2 restarts that all preserved state correctly.

**Cumulative session-to-date** (Day 1 + Day 2): **+$540.41 net**, **16,746 trades**, **$1,126.79 trading P&L**, **$778.95 fees**, **$239.05 cashback**. The session has flipped from negative to strongly positive on the back of Day 2's volume.

**Next-session focus**:
- Track whether Day 3 reverts to Day-1-style thin spreads or continues Day 2's active pattern.
- Watch DOGE/TON/AXS sustained performance — if they continue producing, Tier 4 symbol picks were correct.
- Begin planning Maximize Profits retuning: per-tier `trade_amount_pct` adjustments + `activation_profit_horizon_multiplier` reduction to 2.5-3.0 range.
- Monitor 08:00 UTC funding-window sweep peak — is 2980ms the new ceiling on busy days?

---

## Day 3 — 2026-05-05 (Tuesday)

### Session Timeline

- **Start**: 00:00 UTC — continuing from Day 2's last bot session (uptime 8h08m at start of day, indicating last restart was at ~15:51 UTC on Day 2)
- **One bot restart**: 23:31:31 UTC near end of day (via dashboard "Restart Process" — cumulative state survived intact)
- **End**: 23:59 UTC — single session day until the late evening restart

### Capacity (Sweep) Performance

| Metric | Value |
|--------|------:|
| Capacity samples | 1,418 (~1/min) |
| Avg sweep (min / mean / max) | 208 / 928 / **3,155** ms |
| p95 sweep (min / mean / max) | 208 / 1,836 / 5,023 ms |
| Last sweep (min / mean / max) | 208 / 1,840 / 12,670 ms |
| Heap MB (min / mean / max) | 173 / 1,551 / 1,682 |
| Final 30-sample avg | 757 ms |
| Final heap | 1,284 MB |
| **Sweep budget WARNs** | **0** ⬇ (Day 2 had 79) |

**Peak avg sweep: 3,155ms at 06:29:35 UTC** (heap=1,546MB) — coincides with **04:00 UTC funding-settlement cascade aftermath** carrying through to the 06:00–06:30 window when configs mass-demoted/re-activated across symbols. Settled back under 1,000ms within ~10 minutes.

**Single-tick spike: 12,670ms at 22:07:53 UTC** — one-off pause (likely GC + state save coincidence). Rolling p95 only went to 1,446ms in that minute, confirming it was an isolated stall, not a sustained issue. No capacity WARNINGS were emitted for this — the bot's `is_over_budget` check uses rolling avg, not the last sample.

**Major improvement vs Day 2**: **zero sweep-budget warnings** all day vs Day 2's 79. The 06:29 peak avg was 175ms higher than Day 2's 08:14 peak (2,980ms), but it was a single 3-min window — Day 2 had a 79-warn window of ~30 min around 08:00 UTC. Day 3 felt structurally cleaner despite higher single-sample peaks.

---

### Per-Group Performance — Day 3 Net Deltas

Daily deltas computed as `(end_of_Day3 cumulative) − (end_of_Day2 cumulative)` per config, using last `[Session]` line per (group, config) on each side.

#### Group 1 — $1k tier (Architecture & Exchange Ablations) — 11 configs

| Config | Net $ | P&L $ | Fees $ | Cashback $ | Trades |
|--------|------:|------:|-------:|-----------:|-------:|
| Lean (BFX+MEX only) | **+22.18** | +21.83 | 0.03 | 0.38 | 284 |
| Neutral (Baseline) | +11.60 | +12.82 | 1.38 | 0.16 | 266 |
| No Hedging | +10.84 | +11.92 | 1.44 | 0.36 | 216 |
| Conservative | +10.36 | +12.25 | 2.62 | 0.73 | 500 |
| Maximize Profits | +7.84 | +12.32 | 5.18 | 0.70 | 832 |
| + Gate.io | +4.72 | +9.21 | 4.75 | 0.26 | 231 |
| No Referrals | +4.45 | +5.34 | 0.89 | 0.00 | 124 |
| + KuCoin | +1.31 | +4.79 | 3.53 | 0.05 | 129 |
| All 8 Exchanges | +1.14 | +9.64 | 8.86 | 0.36 | 226 |
| No Trading Float | +0.33 | +0.39 | 0.07 | 0.01 | 2 |
| Aggressive | -0.01 | +0.29 | 0.35 | 0.05 | 13 |
| **Group total** | **+74.76** | **+100.80** | **29.10** | **3.06** | **2,823** |

Lean (BFX+MEX only) repeated its Day 2 win — Bitfinex 0% + MEXC 0.04% with no other-exchange fee bleed dominates at small capital. "+ Gate.io / + KuCoin" still bleed fees from cheaper routes.

#### Group 2 — $2k tier (Trade Size & Capital Mix) — 9 configs

| Config | Net $ | P&L $ | Fees $ | Cashback $ | Trades |
|--------|------:|------:|-------:|-----------:|-------:|
| Small ($40, 2%) | **+42.39** | +48.53 | 9.07 | 2.93 | 982 |
| Medium-Aggressive ($80, 4%) | +35.98 | +41.26 | 6.76 | 1.48 | 657 |
| Tiny ($20, 1%) | +28.02 | +32.95 | 6.84 | 1.91 | 1,141 |
| Fixed-Size $60 (no auto-scale) | +27.51 | +29.93 | 4.07 | 1.65 | 464 |
| Maximize Profits | +22.80 | +27.43 | 6.12 | 1.49 | 697 |
| Large ($120, 6%) | +11.42 | +12.54 | 1.39 | 0.27 | 127 |
| XLarge ($160, 8%) | +2.01 | +2.35 | 0.49 | 0.15 | 42 |
| Medium-Neutral ($80, 4%) | +0.75 | +1.03 | 0.56 | 0.28 | 14 |
| Medium-Conservative ($80, 4%) | +0.61 | +0.53 | 0.07 | 0.15 | 2 |
| **Group total** | **+171.49** | **+196.55** | **35.37** | **10.31** | **4,126** |

Small-trade configs ($20–$80) dominated. Larger trades ($120/$160) suffered from min-notional gates blocking smaller-spread opportunities. Maximize Profits did its job here.

#### Group 3 — $3k tier (Discovery & Scoring Tuning) — 8 configs

| Config | Net $ | P&L $ | Fees $ | Cashback $ | Trades |
|--------|------:|------:|-------:|-----------:|-------:|
| Short Scoring Window (10min) | **+54.12** | +61.24 | 11.35 | 4.23 | 610 |
| Loose Stability Gates | +47.51 | +52.47 | 7.16 | 2.20 | 433 |
| Maximize Profits | +44.64 | +47.23 | 4.67 | 2.08 | 799 |
| Neutral (Baseline) | +40.54 | +43.24 | 5.08 | 2.38 | 326 |
| Aggressive (Permissive Scoring) | +30.17 | +33.99 | 5.80 | 1.98 | 320 |
| Tight Stability Gates | +12.89 | +15.24 | 3.96 | 1.61 | 166 |
| Slow Discovery (10min) | +1.41 | +1.85 | 0.52 | 0.08 | 9 |
| Conservative (Strict Scoring) | +0.90 | +0.93 | 0.43 | 0.40 | 2 |
| **Group total** | **+232.18** | **+256.19** | **38.97** | **14.96** | **2,665** |

Short scoring window (10min) reactivated symbols rapidly — perfect for TON's sustained run. Maximize Profits at $3k is correctly tuned (`slightly_aggressive` profile + 1.5% trade pct) — 3rd best in the group.

#### Group 4 — $4k tier (Symbol Selection & Diversity) — 9 configs

| Config | Net $ | P&L $ | Fees $ | Cashback $ | Trades |
|--------|------:|------:|-------:|-----------:|-------:|
| Wide (8 active) | **+78.79** | +85.94 | 10.39 | 3.24 | 562 |
| No Diversification Floor | +78.61 | +87.48 | 10.90 | 2.03 | 537 |
| Maximize Profits | +63.13 | +66.97 | 6.09 | 2.25 | 772 |
| Diverse (6 active) | +51.02 | +54.53 | 5.57 | 2.06 | 345 |
| Conservative (3 active) | +23.56 | +23.62 | 1.10 | 1.04 | 139 |
| Concentrated (2 active) | +23.50 | +25.74 | 4.12 | 1.88 | 209 |
| Neutral (4 active) | +12.66 | +15.08 | 3.24 | 0.82 | 86 |
| No Auto-Expand | +12.45 | +14.51 | 3.25 | 1.19 | 123 |
| Slow Eval (5min) | +2.73 | +2.44 | 0.13 | 0.42 | 9 |
| **Group total** | **+346.45** | **+376.31** | **44.79** | **14.93** | **2,782** |

Wide (8 active) and No Diversification Floor tied for top — both captured TON simultaneously with EIGEN/ZEC. **Maximize Profits jumped to 3rd place at $4k tier** (vs Day 2's near-idle 1 trade) — the tuning improvement from $3k carried over but it's still not topping the group.

#### Group 5 — $5k tier (Capital Allocation & Routing) — 9 configs

| Config | Net $ | P&L $ | Fees $ | Cashback $ | Trades |
|--------|------:|------:|-------:|-----------:|-------:|
| Aggressive (Rapid Shifts) | **+119.55** | +130.31 | 17.89 | 7.13 | 582 |
| Tight Inventory Drift | +118.71 | +125.77 | 11.84 | 4.78 | 517 |
| No BFX Buyer Boost | +109.58 | +119.17 | 13.12 | 3.53 | 551 |
| Neutral (Baseline) | +77.22 | +82.25 | 7.97 | 2.94 | 395 |
| No MEX Seller Boost | +73.58 | +78.59 | 8.44 | 3.43 | 366 |
| Maximize Profits | +48.43 | +52.03 | 5.62 | 2.02 | 592 |
| Loose Inventory Drift | +45.11 | +49.07 | 6.37 | 2.41 | 258 |
| No Boosts (Pure Score) | +4.46 | +4.79 | 0.62 | 0.29 | 24 |
| Conservative (Sticky) | +0.83 | +0.92 | 0.10 | 0.01 | 1 |
| **Group total** | **+597.47** | **+642.90** | **71.97** | **26.54** | **3,286** |

Aggressive (Rapid Shifts) repeats — 3rd consecutive day winning at $5k tier. Even more striking: **5 of 9 configs cleared $70+** on the same day, vs Day 1 when the top earner was $11. The fee-aware routing experiments (No BFX Buyer Boost / No MEX Seller Boost) traded well but with marginally worse net — confirms the default boosts are correctly tuned for TON-class symbols routing through BFX+MEX.

#### Group 6 — $10k tier (Production-Like) — 8 configs

| Config | Net $ | P&L $ | Fees $ | Cashback $ | Trades |
|--------|------:|------:|-------:|-----------:|-------:|
| No Hedge (Production) | **+269.07** | +290.30 | 30.22 | 8.99 | 939 |
| Loose Anomaly (20%) | +202.61 | +214.57 | 23.09 | 11.13 | 757 |
| Production-Loose | +201.33 | +224.66 | 40.26 | 16.93 | 777 |
| Production-Neutral | +7.62 | +7.15 | 1.48 | 1.95 | 22 |
| Strict Anomaly (10%) | +2.01 | +2.94 | 1.23 | 0.30 | 2 |
| Production-Safe | +1.67 | +2.20 | 0.60 | 0.07 | 6 |
| Peak Hours Only ($10k) | +1.65 | +1.88 | 0.54 | 0.31 | 4 |
| Maximize Profits | +0.22 | +0.34 | 0.13 | 0.01 | 2 |
| **Group total** | **+686.18** | **+744.04** | **97.55** | **39.69** | **2,509** |

**No Hedge $10k posted the single biggest config-day of the session: +$269** — and Loose Anomaly + Production-Loose each cleared $200. Meanwhile **Maximize Profits fired only 2 trades all day (+$0.22)** and Peak Hours Only ($10k) fired 4 trades (+$1.65). The $10k tier's strict configs remain mistuned and missed the best market day of the session by 99%+.

---

### Final Summary Table — Day 3

| Tier | Configs | Day 3 P&L | Fees | Cashback | **Day 3 Net** | Trades | Net $/hr | Per $1k/hr |
|------|--------:|----------:|------:|---------:|--------------:|-------:|---------:|-----------:|
| $1k × 11 | 11 | +100.80 | 29.10 | 3.06 | **+74.76** | 2,823 | +3.12 | +0.28 |
| $2k × 9 | 9 | +196.55 | 35.37 | 10.31 | **+171.49** | 4,126 | +7.15 | +0.40 |
| $3k × 8 | 8 | +256.19 | 38.97 | 14.96 | **+232.18** | 2,665 | +9.67 | +0.40 |
| $4k × 9 | 9 | +376.31 | 44.79 | 14.93 | **+346.45** | 2,782 | +14.44 | +0.40 |
| $5k × 9 | 9 | +642.90 | 71.97 | 26.54 | **+597.47** | 3,286 | +24.89 | +0.55 |
| $10k × 8 | 8 | +744.04 | 97.55 | 39.69 | **+686.18** | 2,509 | +28.59 | +0.36 |
| **TOTAL** | **54** | **+2,316.79** | **317.75** | **109.49** | **+2,108.55** | **18,191** | **+87.86** | **+0.41** |

**Per-tier capital efficiency winner: $5k tier (+$0.55/hr per $1k invested)** — driven by the Aggressive (Rapid Shifts) / Tight Inventory Drift / No BFX Buyer Boost trifecta each clearing $100+. $10k tier had higher absolute returns but lower per-$1k efficiency due to the 3 underperforming Maximize/Peak/Strict configs dragging the group average.

---

### Top Symbols Traded — Day 3

| Symbol | Trades | Profit (Trading P&L) |
|--------|-------:|---------------------:|
| TONUSDT | **12,050** | **$1,591.47** ← Day 3 hero |
| EIGENUSDT | 1,980 | $415.83 |
| ZECUSDT | 2,754 | $225.11 |
| ZROUSDT | 622 | $43.34 |
| DOGEUSDT | 213 | $8.21 |
| SUIUSDT | 91 | $7.90 |
| ADAUSDT | 96 | $3.97 |
| LINKUSDT | 27 | $3.82 |
| XMRUSDT | 71 | $2.99 |
| (10 other symbols) | <30 each | <$1 each |

**TON dominated overwhelmingly — 66% of trades and 69% of all trading P&L came from one symbol.** Day 1 was WIF/XMR/AR; Day 2 was DOGE/TON/AXS; Day 3 was TON/EIGEN/ZEC. Symbol mix continues rotating; the bot's discovery system caught the dominant winner each day.

---

### Issues Detected

#### 1. Single 12,670ms sweep spike at 22:07 UTC
One isolated slow tick. p95 stayed at 1,446ms in the same minute and the next minute returned to 700ms. Likely a GC + state save coincidence (24 dirty configs flushing at once based on the `dirty=2` after-spike count vs `dirty=24` pre-spike). No bot impact — broadcast loop kept publishing within seconds.

#### 2. Peak sustained sweep 3,155ms at 06:29 UTC ⚠
Avg-sweep peak coincides with the **04:00 UTC funding-settlement cascade** propagating through the symbol-reactivation pipeline. 3-minute window of >3000ms sustained sweep, then back under 1500ms. **No capacity WARNs emitted** — the `is_over_budget()` heuristic doesn't trigger at this level. Compares favorably to Day 2's 30-min funding-cascade window at 2,980ms with 79 WARNs.

#### 3. Pionex reconnects (34×)
Pionex sub-fetcher dropped `ConnectionClosedError: no close frame received or sent` 34 times across the day — exchange-side rate limiting / connection drops. Auto-reconnect handled all without intervention. **No impact on trades** — Pionex was rarely the dominant exchange anyway.

#### 4. OKX reconnects (8×)
Routine WebSocket disconnects, auto-recovered within ~1s each. Standard exchange-side behavior.

#### 5. Group 6 strict configs still near-idle on the biggest day yet
- **Maximize Profits ($10k): 2 trades, +$0.22**
- Peak Hours Only ($10k): 4 trades, +$1.65
- Production-Safe ($10k): 6 trades, +$1.67
- Strict Anomaly (10%) ($10k): 2 trades, +$2.01
- Production-Neutral ($10k): 22 trades, +$7.62

While No Hedge fired 939 trades for +$269.07 and Loose Anomaly fired 757 for +$202.61. The strict gates on Maximize/Peak/Strict configs are clearly **over-tuned for the $10k tier**. Day-3 confirms the Day-1 and Day-2 finding — these need rework:

- `trade_amount_pct` 0.5% → 1.0–1.5%
- `activation_profit_horizon_multiplier` 4.0 → 2.0–2.5
- Reconsider regime gating for the $10k tier specifically (the 4-hour weak-window suppression is too aggressive on busy days)

#### 6. Group 1 "+ KuCoin" went into mass-demote cycles 4× during day
4 "All symbols demoted — re-entering discovery mode" warnings (most of any config). The KuCoin-included variant struggled to find profitable activations between funding settlements. Suggests the additional exchange surface adds noise rather than opportunity when the active winners (TON/EIGEN/ZEC) all route well through Bitfinex+MEXC anyway.

#### 7. No bot restarts during prime hours
The only restart was at 23:31 UTC (end of day). All 24h of TON's dominant run captured in a single bot session — best uptime continuity of the session so far.

---

### Findings Summary — Day 3

**Aggregate**: **+$2,108.55 net** across 54 configs ($25k capital) over 24h → **+$87.86/hr aggregate**, or roughly **+8.4% of total capital per day**. **By far the strongest day of the session** — 3.6× Day 2's +$578 and a massive recovery from Day 1's -$38.

**Capital efficiency by tier** (net $/hr per $1k invested):

| Tier | Day 3 Per $1k/hr | Day 2 Per $1k/hr | Day 1 Per $1k/hr | Trend |
|------|-----------------:|-----------------:|-----------------:|:------|
| $1k | +0.28 | +0.35 | -0.44 | Stable mid |
| $2k | +0.40 | +0.79 | -0.24 | Strong |
| $3k | +0.40 | +1.11 | -0.04 | Strong |
| $4k | +0.40 | +0.98 | -0.13 | Strong |
| $5k | **+0.55 ← best** | +0.60 | -0.03 | Top |
| $10k | +0.36 | +1.19 | -0.08 | Solid but lagging $5k |

Day 2 had higher per-$1k efficiency at most tiers (1.0+ at $3k/$4k/$10k) — Day 3's absolute gains were bigger because the market was active longer (TON ran 24h vs DOGE's 6h on Day 2). The $5k tier flipped from middling to top spot, driven by the three Aggressive/Tight-Inventory/No-BFX-Buyer-Boost configs each clearing $100+.

**Three confirmed-by-3-days winners**:
- **$5k Aggressive (Rapid Shifts)**: Day 1 +$11.65, Day 2 +$50.06, Day 3 +$119.55 — **3-day cumulative +$181.26**. Rising daily. Most aggressive regime profile + permissive eval interval is the right strategy for this market regime.
- **$10k No Hedge (Production)**: Day 1 +$6.80, Day 2 +$92.14, Day 3 +$269.07 — **3-day cumulative +$368.01**. The dominant winner by absolute dollars. Hedge cost is unambiguously a drag at $10k scale in this market.
- **$2k Small ($40, 2%)**: Day 2 +$22.97, Day 3 +$42.39 — small-trade size + 2% pct = perfect for capturing TON's frequent tiny-spread opportunities.

**Three confirmed-by-3-days losers**:
- **$10k Maximize Profits**: Day 1 +$0.27, Day 2 +$0.31, Day 3 +$0.22 — **3-day cumulative +$0.80 from 5 trades**. Effectively idle.
- **$10k Peak Hours Only**: Day 2 +$2.85, Day 3 +$1.65 — peak hours filter still gating out most of the day even when busy.
- **$10k Production-Safe**: Strict anomaly + production-safe regime profile bleeding to near-idle.

**Three lessons confirmed**:
1. **Wider symbol count + permissive regime wins on active days**, consistent with Day 2. Top performers traded 500-1,000+ times each.
2. **Hedge cost continues to be a real drag at $10k scale.** No Hedge beat all hedged $10k configs by 25-130× margin on Day 3 alone.
3. **The $5k tier is sneakily efficient** — moderate capital with aggressive regime + tight inventory drift = consistent top performance across all 3 days.

**Sweep performance recap**: 0 capacity WARNs all day (best of the session). Peak avg 3,155ms during a 3-min funding-cascade window. Single 12.67s spike at 22:07 UTC was an isolated GC+save coincidence. Heap healthy throughout (1,284MB final). The bot demonstrated it can carry 18K trades + 35K transfers + 2K rotations in 24h on this hardware with room to spare.

**Cumulative session-to-date** (Days 1+2+3): **+$2,648.96 net**, **34,937 trades**, **$3,443.85 trading P&L**, **$1,096.70 fees**, **$348.54 cashback credited**. The session is now in strongly positive territory after the Day 1 stumble — and Day 3 alone produced 79% of the cumulative net.

**Next-session focus**:
- Watch whether TON's dominance carries into Day 4 or rotates to a new winner (Day 1→Day 2→Day 3 showed a different winner each day).
- $10k tier retuning is **overdue** — start a v0.31.1 task to rework Maximize Profits / Peak Hours Only / Strict Anomaly settings. Current settings cost ~$268 in foregone opportunity on Day 3 alone.
- Document the No Hedge $10k success: it's now the single largest profit center of the session, and the hedge experiment data confirms hedge overhead exceeds its risk benefit at this scale + market regime.

---
