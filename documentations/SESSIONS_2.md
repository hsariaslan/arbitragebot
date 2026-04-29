# Session History & Analysis (Volume 2)

Continuation of `SESSIONS.md` (Sessions #1–#20). New sessions go here from #21 onward to keep individual files manageable.

## Key Metrics Definitions

| Metric | Description |
|--------|-------------|
| **Net Profit** | Trading PnL − Transfer Fees + Credited Cashback |
| **$/hr** | Net Profit / Session Duration |
| **Trade Frequency** | Trades per hour at peak |
| **Avg Net%** | Average net profit percentage per trade (after fees) |
| **Capital** | Total configured capital at session start |
| **Active Symbols** | Symbols that traded during the session |

---

## Session Log

### Session #21 — 2026-04-28 → 2026-04-29 (v0.28.0-beta, First Hedging Session)

**Date**: 2026-04-28 13:30 UTC → 2026-04-29 03:30 UTC (~14h elapsed; **9h41m of active accounting** before the bot drifted into extended-discovery idle for the final 4h+)
**Capital**: $1,000 ($40 per trade, 4%)
**Version**: v0.28.0-beta — first session running the spot-futures hedging stack (Phases A–F: funding-aware scoring + shadow hedging + dashboard observability)
**VPS**: LightNode Bangkok + Oracle Zurich (Bitfinex proxy)
**Execution Mode**: Demo (Binance/OKX/Bybit testnet)
**Hedge Execution Mode**: `simulation` (shadow only, no testnet futures orders)
**Active Exchanges**: 6 (Binance, Bitfinex, Bitget, Bybit, MEXC, OKX) — Gate.io / KuCoin / Pionex disabled.

#### Settings (from `[Settings] SESSION_START`)

| Group | Values |
|---|---|
| Sizing | `trade_amount=$40 (4% of $1000)`, `adaptive=on`, `net_pct_sizing=on cap=2.5` |
| Symbols | `max=5 min=2`, `scoring_window=1800s`, `eval_interval=120s`, `min_net_pct=0.01%` |
| Thresholds | `trading=0.005`, `strong=0.1`, `very_strong=0.3`, `fee_threshold_mult=0.5` |
| Anomaly | `cb=$-5/900s`, `dd=15%/2× emergency`, `streak=4/300s` |
| Bitfinex | `reserve=30% ($300)`, `hard_floor=5% ($50)` |
| Realism | `phantom=1 tick`, `evd_penalty=0.02`, `one_leg=0.02`, `max_pos_mult=2.0×` |
| **Funding-aware scoring (NEW)** | `enabled=on`, `skip_4h=−0.05%`, `skip_8h=−0.05%`, `factor=[0.30, 1.50]`, `poll=60s` |
| **Hedging (NEW)** | `enabled=on`, `mode=simulation`, `dust=$20`, `eval=300s`, `margin_buffer=20%`, `adjust=10%` |

#### Final Aggregate (last `[Session]` line at 23:11:41, 9h41m active)

| Metric | Value |
|---|---|
| Trades | 92 |
| Trading PnL | +$1.52 |
| Transfer fees | $1.36 |
| Cashback (credited / pending) | $0.31 / $0.17 |
| **Net** | **+$0.47** |
| **$/hr** | **$0.05** |
| Portfolio | $1,001 → $999 (−$2 raw) |
| sz0 | 866 |
| pos_cap skips | 265 |
| Anomaly | 0p / 0w / 0sb |
| Phantom spreads | 140 |
| EVD seller penalties | 8,290 (10 demoted winners) |
| One-leg sims | 2 / $0.01 unwind |

After 23:11:41 the bot stayed in extended discovery (no new activation candidates passing the fee-adjusted threshold) until log cutoff. Net stayed at $0.47.

#### Phase A (Funding-Aware Scoring) — WORKED

- `[Funding] Monitor started — polling every 60s (60 symbols, scoring=on)` at 13:30:04. **149 successful polls**, zero failures.
- 3,384 `[Funding]` log lines total. Sample boost: `BNBUSDT ann=+5.02%/yr factor=1.050`. Sample penalty: `SOLUSDT ann=−7.57%/yr factor=0.924`.
- **169 SKIP events across 4 unique symbols** permanently penalized at `factor=0.30`: **APEUSDT, COMPUSDT, TRUMPUSDT, WLDUSDT**. None of these activated despite occasionally appearing on top of spread lists — the funding penalty correctly suppressed them.
- Throttling worked: per-symbol logs limited to one per 10 min as designed.

#### Phase C (Shadow Hedging) — WORKED

- 4 `WOULD_OPEN` / 6 `WOULD_ADJUST` / 4 `WOULD_CLOSE` events. ~107 eval cycles logged (1 per 5 min). Zero executor errors (`errors=0` in every Eval cycle line).
- Lifecycle traced cleanly across 4 hedge cycles:

| # | Symbol | Open notional | Funding rate | Adjusts | Held | Cumulative funding P&L |
|---|---|---|---|---|---|---|
| 1 | TONUSDT | $350 | −9.32%/yr | 2 (→$241 →$167) | 0.8h | **−$0.0032** |
| 2 | ARUSDT | $350 | +10.95%/yr | 0 | 0.7h | **+$0.0029** |
| 3 | SNXUSDT | $350 | +10.95%/yr | 4 (→$591 →$169) | 0.9h | **+$0.0048** |
| 4 | ARUSDT | $350 | +9.23%/yr | 0 | 0.7h | **+$0.0050** |

**Net shadow funding P&L: +$0.0095** across all four positions (~3.1 hours total notional-time). The negative TON funding bled $-0.003 but was offset by three positive-funding shorts.

`Eval cycle … total_notional=$350` matched spot inventory each tick — adjusts triggered correctly when drift exceeded 10%.

#### Discovery & Symbol Lifecycle

| Time (UTC) | Event |
|---|---|
| 13:30:04 | Bot starts. Discovery begins. |
| 14:27:46 | Discovery completes — **TONUSDT activated** (only symbol passing 0.005 threshold). |
| 15:16 | TONUSDT demoted (49 min, score-below-threshold for 900s) |
| 15:16 → 19:31 | Extended discovery (~4h) — no candidate clears fee-adjusted threshold |
| 19:31 | **ARUSDT activated** |
| 20:11 | ARUSDT demoted (40 min) |
| 20:41 | **SNXUSDT activated** |
| 21:37 | SNXUSDT demoted (56 min) |
| 22:30 | **ARUSDT re-activated** |
| 23:12 | ARUSDT demoted again (42 min) |
| 23:12 → 03:30 | Extended discovery for the rest of the session — no activation. RENDERUSDT was top scorer at 0.0078 vs threshold 0.0369. |

- **187 `AUTO_EXPAND triggered`** events while `active=1/2`. Feature 6 fired ~once per minute as designed but never found a 2nd qualifying candidate to activate. The fee-aware threshold (0.0369–0.05%) is unreachable for non-Bitfinex pairs in current market conditions.

#### Per-Symbol Performance

| Symbol | Trades | Sim PnL | Time active | Notes |
|---|---|---|---|---|
| TONUSDT | 57 | +$0.949 | 49 min | Negative funding (cost $-0.003 on hedge) |
| SNXUSDT | 25 | +$0.398 | 56 min | Positive funding (income +$0.005) |
| ARUSDT | 12 (across 2 cycles) | +$0.231 | 40 + 42 min | Positive funding (income +$0.008 combined) |

Crypto liquidation at demotion freed sequentially **$216.40 / $351.65 / $169.02 / $335.51** with fees of $0.11 / $0.21 / $0.12 / $0.22.

#### Anomaly Events

**Zero pauses, zero warnings, zero symbol-blocks.** Only 4 `[Anomaly] PEAK_RESET` events — correctly fired after each demotion liquidated all crypto, breaking the drawdown deadlock as designed (post-v0.27.0 fix). No emergency, no drawdown threshold breached.

#### Capital Flow

| Stage | Binance | Bitfinex | Bitget | Bybit | MEXC | OKX | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| First snapshot 14:33 | $0 | $551 | $157 | $0 | $293 | $0 | **$1,001** |
| Mid 21:04 | $145 | $300 | $172 | $80 | $107 | $201 | **$1,005** |
| Final 22:54 | $27 | $300 | $284 | $0 | $269 | $120 | **$999** |

- **Bitfinex reserve held its 30% target** ($300) by end. Initial overshoot ($551) was redistributed via 5 `BFX over-target redistribute` operations totaling **$522.85** at zero fee.
- **Zero `[Inventory]` periodic rebalance events** — first rebalance fires 6h after activation; the longest active period was 56 min, so this is expected.
- **80 `[Momentum]` log lines**, all on JUPUSDT (+11–12% over 24h, factor ≈ 1.12). JUP was never traded, so momentum had no scoring effect this session.

#### Issues Identified

| # | Severity | Issue |
|---|---|---|
| 1 | MEDIUM | **6 unhandled `Task exception was never retrieved` warnings** (16:44–17:51), no traceback. Coincided with OKX reconnect (`Connection error: no close frame received`) and Pionex sub-connection cycling. Likely fire-and-forget tasks (demo executor or proxy) silently failing. Fix: add `task.add_done_callback(_log_exc)` wrapper. |
| 2 | LOW | **Activation churn — 4-of-5 demotions on the same 2 symbols** (TON, AR×2, SNX, AR). Fee-adjusted threshold (0.0369–0.05%) is hard to clear with only Bitfinex+MEXC available cheaply (Bitfinex covers ~half the symbol universe). 187 expand-attempts found no second candidate. Consider lowering `fee_threshold_multiplier` (currently 0.5) or `trading_score_threshold` for understaff scenarios. |
| 3 | LOW | **Startup balance reconcile mismatch**: `[Reconcile] Bybit USDT sim=$33.33 actual=$5.20 diff=$-28.13`. Pre-existing demo testnet drift, not session-related. |

#### Lessons / Conclusions

- **Phases A and C ship clean.** Funding monitor, factor application, skip threshold (4 symbols correctly disqualified by funding alone), shadow hedge open/adjust/close lifecycle, eval-cycle bookkeeping, cumulative funding P&L — all working as designed. Zero executor errors over 9h41m of live cycles.
- **Hedge math validated**: net shadow funding P&L was **+$0.0095** on $350 notional held ~3.1 hours total — directionally consistent with the funding-monitor preferentially activating positive-funding candidates.
- **The session bottleneck was activation, not hedging.** With $1.52 gross / $0.47 net over 9.7h ($0.05/hr) and ~85% of runtime spent in single-symbol mode or idle, S21 reproduces the Session #20 understaff pattern despite Feature 6 (auto-expand). The new hedging features had no measurable cost on the bottom line — funding income/cost was effectively zero on this small-notional, short-hold session.
- **What to validate next**:
  1. A session where **2+ symbols stay active simultaneously** to exercise the hedge-on-multiple-symbols + parallel-adjust paths.
  2. **Flip `hedge_execution_mode=testnet`** to exercise Phase D (`_open` / `_adjust` / `_close` against the live testnet API, plus `reconcile_with_executor` after restart).
  3. **Add the missing task-exception logger** before the next deploy to surface what's currently silent (Issue #1).
  4. **Tune the activation gates** for the understaff / fee-aware-threshold problem (Issue #2) — possibly add a "diversification floor" that lowers the threshold by 0.7× when `active < min_active_symbols`. This was already noted in CLAUDE.md "Pending Improvements" before v0.27 but deferred. Session #21 confirms it's still relevant.
