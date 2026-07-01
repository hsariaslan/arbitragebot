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

### Session #22 — 2026-04-29 (v0.28.1-beta, Diversification-Floor Bug)

**Date**: 2026-04-29 04:07 UTC → 11:39 UTC (~7h 32m elapsed; **6h 46m of active accounting** before the bot drifted into extended discovery rejecting WIFUSDT for the final ~45 min)
**Capital**: $1,000 ($40 per trade, 4%)
**Version**: v0.28.1-beta — first session running the silent-task-exception fixes + diversification floor (S21 follow-ups)
**Execution Mode**: Demo
**Hedge Execution Mode**: `simulation` (shadow only)
**Active Exchanges**: 6

#### Settings (from `[Settings] SESSION_START`)

Notable changes vs S21 (operator tuning):
- `fee_threshold_multiplier=0.3` (was 0.5) — relaxes per-symbol fee penalty
- `num_active_symbols=3` (was 2)
- `diversification_floor: enabled=True, multiplier=0.7x`
- All other settings unchanged from S21

#### Final Aggregate (last `[Session]` line at 10:54:02, 6h46m active)

| Metric | Value |
|---|---|
| Trades | 81 |
| Trading PnL | +$3.49 |
| Transfer fees | $0.57 |
| Cashback (credited / pending) | $0.05 / $0.24 |
| **Net** | **+$2.97** |
| **$/hr** | **$0.44** (9× S21's $0.05/hr) |
| Portfolio | $1,000 → $1,006 (+$6) |
| sz0 | 1,304 |
| pos_cap skips | 743 |
| EVD seller penalties / demoted | 22,514 / 393 |
| Anomaly | 0p / 0w / 0sb |
| AUTO_EXPAND triggered | 230 |

After 10:54:02 the bot demoted the last 2 active symbols (DOGE, PEPE) at 10:50/10:57 and entered extended discovery — never activated again before log cutoff at 11:39 despite WIFUSDT scoring 0.022-0.024 (well above the 0.005 base trading threshold).

#### Phase A & C — Continued working as designed

- 6 hedge cycles: STRK, AR, DOGE×2, APT, PEPE. Cumulative shadow funding **+$0.0099** (positive). Zero hedge errors over 6h46m.
- Funding monitor: identified 4-5 toxic-funding symbols and floored them at 0.3 (same set as S21).
- Symbols traded: STRK, AR, DOGE (×2 cycles), APT, PEPE — all activated cleanly.

#### THE BUG — Diversification floor disabled during re-discovery

After PEPE+DOGE both demoted at 10:57, bot dropped to 0/3 active symbols. Re-entered discovery (per `optimizer.py:1827-1836` when "All symbols demoted"). During the next 45 minutes:

| Time | WIF Score | WIF Threshold (logged) | Active | Discovery? |
|---|---|---|---|---|
| 11:02:27 | 0.008 | 0.0320 (fee_adj=+0.0270) | 0 | extending |
| 11:12:27 | 0.014 | 0.0320 | 0 | extending |
| 11:32:28 | 0.024 | 0.0320 | 0 | extending |
| 11:39 (cutoff) | 0.022 | 0.0320 | 0 | extending |

WIFUSDT had **freq=44.5%, avg_net=0.049%** — clearly profitable spread with high frequency. But it was being rejected because:

1. **WIFUSDT is not on Bitfinex** (`Subscribe failed: WIFUSDT — symbol: invalid`). Cheapest pair must use other exchanges.
2. **Fee-aware threshold**: cheapest pair (Bitfinex+MEXC = ~0.04%) vs WIF's pair (~0.13%) → `fee_adj = (0.13 - 0.04) × 0.3 = +0.0270`
3. Total threshold: `0.005 base + 0.027 fee_adj = 0.032`
4. WIF score 0.022 < threshold 0.032 → REJECTED

**The diversification floor SHOULD have relaxed the threshold to `0.032 × 0.7 = 0.0224`**, which would have activated WIF (0.022 ≈ 0.0224, eligible by 11:32 at score 0.024).

**Root cause** (in `_get_activation_threshold()`):
```python
if (
    self._diversification_floor_enabled
    and self._discovery_complete            # ← THIS BLOCKED IT
    and len(self._active_symbols) < self._min_active_symbols
):
    threshold *= self._diversification_floor_multiplier
```

When all symbols demote, the bot resets `_discovery_complete = False` (per `optimizer.py:1832`) and re-enters discovery. The `_discovery_complete=True` gate I added in v0.28.1-beta intended to skip the floor during initial bootstrap, but it also silently disabled it during the most-needed scenario: **0 active symbols + fresh re-discovery after total demotion**.

**Fix shipped in v0.28.2-beta**: removed the `_discovery_complete` gate. Floor now applies whenever `len(active_symbols) < min_active_symbols`, regardless of discovery phase.

#### Capital Flow

| Stage | Binance | Bitfinex | Bitget | Bybit | MEXC | OKX | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| End 10:54 | $120 | $715 | $0 | $0 | $171 | $0 | **$1,006** |

Bitfinex held $715 (71% of capital) at end after PEPE/DOGE demotions — the BFX over-target redistribution was prevented from running because the bot had no active symbols (loop guard correctly prevented sending USDT to "active" exchanges that didn't exist).

#### Issues Identified

| # | Severity | Issue |
|---|---|---|
| 1 | **HIGH** | **Diversification floor silently disabled after total demotion** — the `_discovery_complete=True` gate prevented relaxation during fresh re-discovery, the exact scenario the floor was designed for. WIFUSDT (0.022 score, 44.5% freq) sat in extended discovery for 45+ min instead of activating. **FIXED in v0.28.2-beta**. |
| 2 | LOW | **Bitfinex over-concentration during 0-active-symbol periods** — $715/71% of capital sat on Bitfinex after demotions because the redistribution logic targets active-symbol exchanges. With no active symbols, no redistribution. Acceptable behavior (capital is safe), but worth noting for future eval. |

#### Lessons / Conclusions

- **Profit improved 9× vs S21** ($0.05/hr → $0.44/hr) due to the operator's settings tuning (`fee_threshold_mult=0.3`, `num_active=3`) and the diversification floor working in MOST scenarios. 81 trades in 6.7h of active accounting, vs 92 trades in 9.7h for S21.
- **Hedge math validated again**: shadow funding +$0.0099 over 6 hedges, all in lock-step with spot inventory.
- **The bug is a one-line fix** — pure logic error in the gate condition, not a design flaw. Floor logic itself is correct; gate was too restrictive.
- **Pre-fix workaround during a session**: operator could manually demote the bot to single-symbol or below by lowering `num_active_symbols` to 1, which would force `_discovery_complete=True` to remain set on a non-zero-active state. Not needed post-fix.

### Session #23 — 2026-04-29 (v0.28.2-beta, Drawdown Peak-Inflation Bug)

**Date**: 2026-04-29 12:16 UTC → 15:56 UTC (~3h 40m)
**Capital**: $1,000 ($40 per trade, 4%)
**Version**: v0.28.2-beta — first session with diversification floor fixed (S22 follow-up) and operator's new aggressive settings (`fee_threshold_mult=0.2`, `max_pos_mult=3.0`, `diversification_floor_multiplier=0.5`, `bitfinex_reserve=20%`, `dust=$10`)
**Execution Mode**: Demo
**Hedge Execution Mode**: `simulation` (still shadow only)
**Active Exchanges**: 6

#### Final Aggregate (last `[Session]` line at 15:55:29, 3h39m active)

| Metric | Value |
|---|---|
| Trades | 142 |
| Trading PnL | +$1.45 |
| Transfer fees | $0.24 |
| Cashback (credited / pending) | $0.32 / $0.22 |
| **Net** | **+$1.53** |
| **$/hr** | **$0.42** (consistent with S22's $0.44/hr) |
| Portfolio | $1,000 → $1,002 (+$2) |
| sz0 | 1,154 |
| pos_cap skips | **74** (down from S22's 743 — `max_pos_mult=3.0` worked) |
| Anomaly | 0p / 0w / **4sb** (new — false drawdown blocks) |

#### Discovery & Symbol Lifecycle

| Time (UTC) | Event |
|---|---|
| 12:16:20 | Bot starts (intentional restart). State restored, 4 symbols pre-loaded. |
| 12:31:21 | Discovery completes — DOGEUSDT only |
| 13:10:22 | DOGEUSDT demoted; PEAK_RESET fires (peak → ~$1000) |
| 13:55:25 | Discovery activates **3 symbols simultaneously**: AR, GRT, WIF. **Diversification + lower thresholds working**. |
| 14:25:08 | ARUSDT demoted (30 min) |
| 15:05:28 | WIFUSDT demoted (1h10m) |
| 15:13:34 | PEPEUSDT EXPAND_READY (auto-expand fired correctly) |

The diversification floor fix from v0.28.2-beta visibly worked — discovery activated 3 symbols simultaneously where S21/S22 only managed 1.

#### THE BUG — Drawdown peak inflated by ~30% with no real price movement

Two distinct DRAWDOWN_BLOCK events fired with stable spot prices:

| Time | Drawdown reported | Portfolio (snapshot) | Implied peak | Symbols blocked |
|---|---:|---:|---:|---|
| 14:27:20 (1m of repeats) | **22.72%** | $1,002 | **$1,297** | 2 |
| 15:55:36 (1m of repeats) | **16.22%** | ~$1,003 | ~$1,197 | 2 |

Real spot prices during those windows were rock-stable:
- WIFUSDT: $0.1786–$0.1797 (0.6% range)
- GRTUSDT: $0.0246–$0.0248 (~1% range)
- ARUSDT: $1.8630–$1.8660 (0.2% range)

Yet peak portfolio_value got recorded at **$1,297** between PEAK_RESET (13:10) and the first alarm (14:27). That requires a transient ~30% spike on the bot's $400 of crypto exposure — most likely a **flash quote / stale price tick** from one of the exchange feeds inflating `prices[symbol]` for one tick. The single-tick max in `update_portfolio_value` ratchets peak up and never lets it down.

#### Root cause

`AnomalyProtection.update_portfolio_value()` used a naive single-tick max:

```python
if value > self._peak_portfolio_value:
    self._peak_portfolio_value = value
```

Any single bad tick poisons peak indefinitely (until next PEAK_RESET).

#### Fix shipped in v0.28.3-beta (two layers)

1. **Cap peak growth per tick** (`anomaly_protection.py`): introduced `PEAK_MAX_GROWTH_PER_TICK_PCT = 5.0`. Real sustained gains still compound (5% per ~1Hz update is a 18,000%/hr theoretical ceiling — never reached); single-tick spikes are filtered. **Would have prevented every false drawdown in this session.**
2. **Include hedge unrealized PnL in portfolio_value** (`balance.py` + `dashboard_server.py`): `get_portfolio_value(prices, hedge_pnl_usd=0.0)`. With hedging, real price moves are offset by opposing futures PnL → drawdown represents net spot+futures economic exposure instead of single-side noise. Currently passes shadow PnL (educational); becomes real PnL once `hedge_execution_mode=testnet`.

#### Phase A & C — Continued working as designed

- 142 trades with new aggressive settings — biggest activation diversity yet (3 symbols simultaneously)
- Hedge cycles correctly tracked AR/GRT/WIF concurrent positions, total_notional=$400 matched spot inventory each tick
- pos_cap=74 (down 90% from S22's 743) — `max_pos_mult=3.0` removed the throttling

#### Issues Identified

| # | Severity | Issue |
|---|---|---|
| 1 | **HIGH** | **Drawdown peak inflated by ~30%** by transient bad price tick — symbol-blocks fired 30+ times despite stable spot prices and flat portfolio. **FIXED in v0.28.3-beta** (peak-growth cap + hedge PnL in portfolio_value). |
| 2 | LOW | **Bitfinex over-target log spam** — at 12:36 the over-target redistribute logged once per second when no non-Bitfinex active exchange existed. Throttling exists but not for the "skip" path. Cosmetic; doesn't impact bot behavior. |

#### Lessons / Conclusions

- **Aggressive settings (S23) match S22 efficiency at $0.42/hr** while activating 3 symbols simultaneously instead of 1. The diversification-floor fix is providing the diversification it was designed for.
- **`max_pos_mult=3.0` was the right call** — pos_cap dropped 10× without any visible inventory blow-up.
- **Drawdown protection is now robust** — the peak-growth cap means a single bad tick can no longer poison subsequent measurements.
- **Hedge-PnL in portfolio_value** sets up Phase D (testnet) cleanly: when real shorts are active, drawdown will represent actual net economic exposure, with spot price moves offset by opposing futures PnL.
- **3 sessions × ~25h aggregate of clean shadow-mode hedging** (zero executor errors, all hedge lifecycle paths exercised, demote-driven closes working, S22 bug fixed and S23 false-positives now fixed) — sufficient validation to flip `hedge_execution_mode` to `testnet` for Session #24.

### Session #24 — 2026-04-29 (v0.28.3-beta, First Testnet Hedge + AR Dislocation Capture)

**Date**: 2026-04-29 16:29 UTC → 19:26 UTC (~2h 55m of active accounting)
**Capital**: $1,000 ($40 per trade, 4%)
**Version**: v0.28.3-beta — first session with `hedge_execution_mode=testnet` (Phase D live on Binance USDⓈ-M testnet). Note: v0.28.3-beta was committed locally but **never pushed/deployed** — issues found in this session feed directly into v0.29.0-beta without ever shipping to production VPS.
**VPS**: LightNode Bangkok + Oracle Zurich (Bitfinex proxy)
**Hedge mode**: testnet (real testnet futures orders against `testnet.binancefuture.com`)
**Active exchanges**: 6 (Binance, OKX, Bybit, MEXC, Bitget, Bitfinex)
**Disabled exchanges**: 3 (Gate.io, KuCoin, Pionex — `enabled=False` in fee config)

#### Headline Result — Best $/hr of Any Session by ~50×

| Metric | Value |
|---|---:|
| Trades | 436 |
| Trading P&L | $174.84 |
| Transfer fees | $21.47 |
| Cashback (credited) | $0.74 (pending $4.03) |
| **Net** | **$154.11** |
| **$/hr** | **$52.72** |
| Anomaly | 0 pauses / 0 warnings / **1 symbol-block** |
| Phantom spreads filtered | 469 |
| Pos cap throttles | 1,525 |
| sz0 (capital exhaustion) | 2,092 |
| One-leg failures | 8 (cost $0.33) |

**+15.4% on $1,000 capital in 2h 55m.** The previous 3 sessions combined returned $0.05–0.44/hr. This session ran into a real **AR/MEXC structural dislocation** and captured ~$112 of the ~$154 net from that single symbol pair across two distinct events.

#### Settings (logged at session start)

| Category | Value |
|---|---|
| Adaptive | `True`, `auto_rotate=True`, `min_net_pct=0.01%` |
| Symbol limits | `max_symbols=6`, `min_symbols=4`, `scoring_window=1800s`, `eval_interval=120s` |
| Thresholds | `trading=0.003` (very aggressive), `strong=0.1`, `very_strong=0.3` |
| Demotion | `period=1800s`, `cooldown_mult=7`, `realloc_horizon=4h` |
| Sim realism | `spread_persistence=1`, `evd_penalty=0.02`, `one_leg_rate=0.02`, `max_pos_mult=3` |
| Fee threshold mult | `0.2` (very aggressive — small spreads accepted on cheap pairs) |
| Bitfinex reserve | 20% ($200), hard floor 5% ($50) |
| Hourly transfer cap | $5.00 |
| Stability | `factor=0.5`, `min_seconds=180s` |
| Anomaly | enabled, `dd_threshold=15%`, `dd_emergency=2.0×` (30%), `streak=4`, cooldown=300s |
| Diversification floor | enabled, `multiplier=0.5×` |
| Hedging | enabled, **mode=testnet**, `dust=$10`, `eval_interval=300s`, `margin_buffer=20%`, `adjust_threshold=10%` |
| Funding-aware | enabled, skip thresholds at `-0.05%/period`, factor `[0.30, 1.50]` |

#### Timeline

| Time (UTC) | Event |
|---|---|
| 16:29:41 | Session start, 60 symbols subscribed across 6 exchanges |
| 16:34:42 | Hedge **RECONCILE_DONE** (testnet — clean state, no orphans) |
| 16:34:43 | Hedge **OPEN FILUSDT** short, qty=445.19, fill=$0.8985, notional=$400.00, funding=-25.96%/yr, latency=112ms |
| 16:35:12 | Trade #1 FIL Bitfinex→MEXC at +0.03% net (quiet baseline) |
| 16:35–17:34 | ~1h of FIL trading (114 trades) at avg net ~+0.05% — quiet $0.20/hr regime |
| 17:34:33 | **ROTATE FILUSDT → ARUSDT** (AR score 0.37, est improvement $527/hr) — emerging spike detected |
| 17:34:37 | Trade #116: AR OKX→MEXC, **net=+12.81%**, profit=$8.28 (spike begins) |
| 17:34:49 | Hedge CLOSE FIL (1h held, funding=-$0.02), Hedge **OPEN ARUSDT** short qty=110.95, $204.70 notional |
| 17:35:20–17:36:12 | Trades #120–#125: avg net +9–12%, 9 more spike trades, $24 profit |
| **17:36:30** | **DRAWDOWN_BLOCK** ARUSDT — Drawdown **21.91%** ≥ 15% threshold → ARUSDT blocked for 5 min cooldown. **Fires 12 times** between 17:36:30 and 17:36:42 (cooldown lock then takes over). Bot now sidelined on AR mid-spike. |
| 17:36:30–17:41:30 | **5-minute symbol-block window — bot misses heart of the AR spike**. No AR trades during this period. |
| 17:39:49 | Hedge ADJUST AR +72 qty (responding to spot accumulation prior to the block) — testnet adjustment fires fine despite anomaly block |
| 17:41:30 | SYMBOL_UNBLOCKED ARUSDT (cooldown expired). Bot resumes; spike is still partially active (~last 2 min) |
| 17:41:33 | Trade #127: AR OKX→MEXC, profit $10.35 at +11.6% net — bot recaptures the tail |
| 17:42–17:43 | Spike fades; trades #128–#137 close at $1–4 each, +12% net trailing off |
| 17:43–18:04 | Quiet phase: AR settles, ~70 trades at +0.07% net (post-spike crumbs) |
| 18:05–18:46 | **Second AR opportunity**: sustained ~1.3% spread emerges, runs for ~40 min. ~115 trades, +$36 net at avg +1.0% net. Realized ~$157/hr during this window. |
| 17:44–18:24 | Hedge ADJUSTs ARUSDT through 110→183→369→411→362→416 qty as bot accumulates/sells spot |
| 18:46–19:13 | Spread closes again. 2 final trades at +0.03% net (#435–#436 MEXC→Bitget reversed direction) |
| 19:25:05 | Final session summary: net=$154.11, $/hr=$52.72 |

#### AR Pair Concentration (from trade-by-pair counts)

| Pair | Trades |
|---|---:|
| ARUSDT OKX→MEXC | 288 |
| FILUSDT Bitfinex→MEXC | 114 |
| ARUSDT Binance→MEXC | 15 |
| ARUSDT Bybit→MEXC | 12 |
| ARUSDT Bitget→MEXC | 4 |
| ARUSDT MEXC→Bitget | 2 (post-spread reversal) |
| FILUSDT Bitget→MEXC | 1 |

**Every meaningful trade today routed through MEXC as seller.** The OKX→MEXC and Bybit→MEXC AR pairs were where the dislocation lived.

#### Phase D — Testnet Hedge Validated

Aggregate hedge activity over the session:

| Counter | Value |
|---|---:|
| Opens | 2 (FIL, AR) |
| Adjusts | 5 (all on AR, tracking spot accumulation) |
| Closes | 1 (FIL on demote) |
| **Errors** | **0** |
| Final state | 1 AR hedge open, qty=416.19, notional=$767.87 |
| Cumulative funding | -$0.054 |

All hedge lifecycle paths fired cleanly against the live testnet:
- **OPEN with margin check** (110 qty AR @ $1.8450 — order placed and filled in 105ms)
- **ADJUST** in both directions (5× — bot grew the AR short from 110 → 416 as spot inventory accumulated, and pared back once on a transient spot drop)
- **CLOSE on `symbol_demoted`** when FIL rotated out (1h held, funding paid)
- **RECONCILE_DONE** at startup — exchange state matched shadow state on first eval (clean handoff from S23 shadow mode)

This is the first session with real testnet executor side effects, and it ran error-free for ~3h, including across an anomaly-block event. **Phase D is operationally validated.**

#### Observation: Drawdown Still Triggers During Profitable Spikes (Pre-Deploy Finding)

This was caught in local testing before v0.28.3-beta was deployed — the 1%/tick peak-growth cap is in committed code but never reached production. The session exposes that **the cap alone is insufficient** and motivates a second-layer fix bundled into v0.29.0-beta below.

**What happened**: at 17:36:30, just 113 seconds into the AR spike (during which the bot had captured $29 of profit in 11 trades), drawdown reported **21.91%** and ARUSDT was symbol-blocked for 5 min. The block fell exactly on the most profitable phase of the spike — bot resumed trading at 17:41:30 with only the tail end of the dislocation left.

| Window | Trades | Profit | Avg net% |
|---|---:|---:|---:|
| Spike pre-block (17:34:37 – 17:36:12) | 11 | $29.32 | +9.5% |
| **Block window (17:36:30 – 17:41:30)** | **0** | **$0.00** | (sidelined) |
| Spike post-block (17:41:30 – 17:43) | ~13 | ~$33 | +11.5% |

The 5-minute block cost the bot ~$30–50 of additional spike capture. Since v0.28.3-beta never reached production VPS, **no live capital was affected** — but the next deployed release must address this before any real-money trading.

**Why the 1%/tick cap alone is not enough**: `PEAK_MAX_GROWTH_PER_TICK_PCT = 1.0%` caps single-tick peak growth at 1%, but over the 113-second spike window (~113 ticks), the cap allows compound growth up to `1.01^113 ≈ 3.07×`. If even a fraction of those ticks pushed peak up by ~1%, peak could legitimately ratchet from $1,000 to $1,200+ during the spike. When prices then dipped marginally on a single tick, the apparent drawdown crossed the 15% threshold against the inflated peak. The cap slows peak inflation but does not prevent it over many ticks.

The economic reality: the bot's portfolio was UP during the entire spike (it was earning real profit). There was no real drawdown — only a peak that grew faster than the realized P&L because intermediate ticks marked accumulating crypto inventory at slightly elevated prices.

**Fix candidates for v0.29.0-beta** (any one or combination):

1. **Tie peak to realized capital, not mark-to-market**: peak should grow only when `cash_pnl_realized` increases, not on every favorable price tick. Mark-to-market gains on held inventory don't count toward peak until they're locked in via a sell.
2. **Drawdown should subtract held-inventory MTM volatility** during active arbitrage windows. When the bot is actively round-tripping a symbol, transient inventory MTM swings are noise, not signal.
3. **Increase `dd_threshold` when active hedge offsets the symbol's spot exposure**. With 416 qty AR short notional $767 and roughly equivalent AR spot inventory, real net exposure is ~zero — drawdown threshold should reflect that.
4. **Cooldown reduction**: 5-min symbol-block on a 2-min real spike means the cooldown outlasts the opportunity. Either tier the cooldown by drawdown severity, or unblock automatically when drawdown recovers below threshold instead of waiting for 5 min wall-clock.

#### Issue: Capital Distribution Asymmetry

`sz0=2092` — over 2,000 SIZE_ZERO events because USDT keeps depleting on the buyer side (OKX) while crypto piles up there. With every AR trade buying $20–100 on OKX, OKX USDT drains in ~30 trades. Then internal sell + internal buy round-trip costs ~$0.16 per cycle (OKX 0.10% sell + MEXC 0.04% buy). At +12% net during spike, the round-trip is trivial. At +0.07% net post-spike, the round-trip eats the margin (the issue analyzed in S24 mid-session).

`pos_cap=1525` blocks were `max_pos_mult=3.0` saving the bot from over-accumulating AR on buyer exchanges. Without this cap (which `max_pos_mult=5.0` default in earlier sessions allowed), the bot would have piled up 5× the trade_amount = $200 of AR per buyer exchange × 4 buyer exchanges = $800+ of AR exposure on a $1,000 portfolio. The 3.0 setting is correctly tuned for spike capture without runaway accumulation.

#### Issue: Bitfinex Over-Target Log Spam (Minor)

`[Optimizer] BFX over-target $XXX > $300, but no non-Bitfinex active exchange needs USDT` fired hundreds of times per second during periods when Bitfinex's accumulated USDT exceeded the redistribution target but no eligible recipient existed. Cosmetic — the optimizer correctly did nothing — but the log spam pollutes diagnostics. Same issue noted in S23. Throttle the no-recipient skip path.

#### Other Observations

- **Hedge funding accrual**: AR hedge cost $0.054 in cumulative funding over ~1.5h held — annualized rate around -8%/yr (consistent with the live `-9.39%/yr` reading at open). Negligible vs the $112 captured from the dislocation.
- **Demo divergence**: 0/19 demo trades filled, 179 trades skipped (OKX:ARUSDT permanently skipped — instrument missing on testnet). All AR sim trades have no demo counterpart for the buy leg. Sim accumulated ~$629 of AR positions across OKX/Binance/Bybit that demo couldn't replicate. Demo lagged sim by ~$14 by session end (price drift on phantom positions).
- **Bitfinex 0% taker** kept 114 FILUSDT round-trips clean — FIL leg-1 saw zero taker fees on the buy side, all profit from the spread minus MEXC's 0.04%.

#### Symbol Activity

| Symbol | Times Active | Notes |
|---|---:|---|
| FILUSDT | 1 (16:30 → 17:34, ~1h) | Quiet baseline; rotated out for AR |
| ARUSDT | 1 (17:34 → 19:25, ~2h) | Captured 2 distinct dislocations + post-spread crumbs |

Only 2 symbols traded the whole session. The bot found AR was so productive it stuck with it for the remaining 2 hours. Diversification floor (`0.5×` multiplier) didn't trigger meaningfully because AR alone exceeded the activation threshold without help.

#### Lessons / Conclusions

- **First testnet hedge session ran error-free for ~3h** — Phase D is operationally validated. Real testnet `OPEN` / `ADJUST` / `CLOSE` / `RECONCILE` all worked. Cumulative funding tracked accurately. No reconciliation drift.
- **MEXC-as-seller dominance**: 421 of 436 trades (96.6%) used MEXC as the seller leg. Every meaningful profit window of the session lived in MEXC's order book inefficiency. **This empirically validates the v0.29.0-beta `seller_boost=5.0` for MEXC** that was designed mid-session in response to this observation.
- **Drawdown protection needs second-layer fix before deploy**: the v0.28.3-beta peak-cap (1%/tick) was caught insufficient in this local-only session — peak still inflated over many ticks during the spike, triggering a false symbol-block at 21.91% drawdown. Since v0.28.3-beta never reached the VPS, this is a finding that must be addressed in v0.29.0-beta before push (peak should track realized P&L, not mark-to-market).
- **AR/MEXC is structurally inefficient**: two distinct dislocations in the same session (12% spike at 17:34, sustained 1.3% spread from 18:05) is empirical evidence that this pair recurs. Worth permanent capital allocation and high seller_boost on MEXC.
- **Aggressive settings (`fee_threshold_mult=0.2`, `trading=0.003`, `max_pos_mult=3`) work** when paired with cheap exchanges. The session captured 50× the previous-best $/hr without any runaway position accumulation.
- **The 5-min symbol-block cost the bot ~$30–50 in missed spike capture**. Even in a $154-net session, the false drawdown was the largest single P&L hit. **Fixing the drawdown metric is a tier-1 priority for v0.29.0-beta or v0.28.5-beta.**

#### v0.29.0-beta Features Designed In Response

The session was heavily analyzed mid-flight (the user observed the AR opportunity in real time), and the following features were scoped + implemented in the same context (uncommitted at session end):

1. **Per-symbol blocklist** (`disabled_symbols` per exchange) + **role flags** (`as_buyer`/`as_seller`) — surface in Fee Management UI
2. **On-demand 24h volume fetcher** (button in Fee Management tab) — pull live volumes from all 9 exchanges to inform blocklist decisions
3. **Buyer/seller boost multipliers** (`buyer_boost`/`seller_boost`) — soft preference layer; defaults set to **Bitfinex.buyer_boost=5.0** and **MEXC.seller_boost=5.0** based on this session's data
4. **Hourly + on-discovery `trade_amount` auto-rescale** — when `trade_amount_pct > 0`, recompute trade size from current portfolio every hour and at every discovery transition, so trade size grows with capital instead of staying pegged to configured `total_capital`
5. **3 new symbols** added to `SYMBOLS` list: XMRUSDT, ZROUSDT, NEOUSDT (Bitfinex+MEXC pairs verified as on Binance Futures for hedgability)
6. **Comprehensive `[Settings]` logging** of role boosts, role restrictions, symbol blocklists per exchange — for post-session diagnostics

These were not active during the live session — they will be exercised in Session #25 onward.

### Session #25 — 2026-04-29 → 2026-04-30 (v0.29.0-beta, First Live Run with v0.29 Features)

**Date**: 2026-04-29 20:58 UTC → 2026-04-30 06:48 UTC (~9h 49m active accounting)
**Capital**: $1,000 ($40 per trade, 4%)
**Version**: v0.29.0-beta — first session running the new feature stack: role boosts (Bitfinex.buyer=5x + MEXC.seller=5x), per-symbol blocklist + daily auto-disable scheduler, on-demand volume fetcher, hourly trade_amount auto-rescale. v0.29.0-beta committed locally but **never pushed/deployed** — same as v0.28.3 in S24.
**VPS**: LightNode Bangkok + Oracle Zurich (Bitfinex proxy)
**Hedge mode**: testnet (real testnet futures)
**Active exchanges**: 6 (Binance, OKX, Bybit, MEXC, Bitget, Bitfinex)
**Disabled exchanges**: 3 (Gate.io, KuCoin, Pionex)

#### Headline Result — Quiet Grind, No Spike

| Metric | Value |
|---|---:|
| Trades | 110 |
| Trading P&L | +$2.61 |
| Transfer fees | $0.44 |
| Cashback (credited / pending) | $0.11 / $0.30 |
| **Net** | **+$2.27** |
| **$/hr** | **+$0.23** |
| Final portfolio | $1,005 (started $1,000, +0.5% raw) |
| sz0 (capital exhaustion) | 1,901 |
| Phantom spreads filtered | 175 |
| Pos-cap throttles | 308 |
| Rebalance blocked | 36 |
| EVD seller penalties / demoted | 22,655 / **71** |
| One-leg sims | 1 / $0.00 |
| Anomaly | 0 pauses / 0 warnings / **2 symbol-blocks** |

A "back to normal" session compared to S24's $52.72/hr AR-spike capture. No structural dislocation, no fat spreads — just slow accumulation on tight Bitfinex+MEXC majors.

#### Settings (logged at session start)

Same aggressive settings as S24 plus the new v0.29 features:

| Category | Value |
|---|---|
| Sizing | `trade_amount=$40 (4%)`, `adaptive=on`, `net_pct_sizing=on cap=2.5` |
| Symbols | `max=6 min=4`, `scoring_window=1800s`, `eval_interval=120s`, `min_net_pct=0.01%` |
| Thresholds | `trading=0.003`, `strong=0.1`, `very_strong=0.3`, `fee_threshold_mult=0.2` |
| Demotion | `period=1800s`, `cooldown_mult=7` (12,600s = 3.5h), `realloc_horizon=4h` |
| **Role boosts (NEW v0.29)** | `BFX(buy=5.0x,sell=1.0x) MEX(buy=1.0x,sell=5.0x)` |
| **Auto-disable (NEW v0.29)** | `enabled=true, threshold=$10,000/24h` |
| **Trade-amount auto-rescale (NEW v0.29)** | `pct=4%`, hourly + on-discovery |
| Bitfinex reserve | 20% ($200), hard floor 5% ($50) |
| Hedging | `enabled=true, mode=testnet` |
| Anomaly | `dd_threshold=15%, dd_emergency=2.0×` (carryover settings, drawdown bug NOT fixed in v0.29) |

#### Timeline

| Time (UTC) | Event |
|---|---|
| 20:58:56 | Session start. Discovery begins. |
| 23:35 | Discovery completes; **DOGEUSDT activated** (only candidate clearing threshold). |
| 00:01:01 | **`[AutoDisable]` daily run** — fetched 24h volumes for all 6 enabled exchanges. Bitfinex got 5 symbols auto-blocked (EIGEN, ENA, HYPE, JUP, LDO — all <$10K/24h). Other exchanges: zero adds. **Settings persisted automatically.** |
| 00:41:13 | First Bitfinex over-target redistribute attempt (BFX=$440 > target $300, but no non-BFX active exchange needs USDT yet → skip log) |
| 00:41:14 | Hedge **OPEN DOGEUSDT** short on testnet, $400 notional, funding -3.88%/yr |
| 00:41:26 | First trade: DOGE Bitfinex→MEXC, +0.016% net |
| 01:05:57 | First successful BFX over-target redistribute: Bitfinex→MEXC $79.77 (free) |
| 02:15:20 | DOGEUSDT demoted (1.6h held, score below threshold). Hedge CLOSE. Re-discovery. |
| 03:00:23 | DOGEUSDT re-activated. Hedge OPEN #2. |
| 03:16:04 | DOGEUSDT demoted again (0.3h held — couldn't sustain even after re-activation). |
| 04:21:42 | **CHZUSDT activated**. Hedge OPEN. |
| 04:43:43 | CHZUSDT demoted (0.4h held). Hedge CLOSE. |
| 04:58:46 | **GRTUSDT activated**. Hedge OPEN. |
| **04:59:09** | **DRAWDOWN_BLOCK on GRTUSDT @ 21.99%** drawdown — 1st false-positive event |
| 05:20:46 | SYMBOL_UNBLOCKED GRTUSDT (5-min cooldown expired) |
| **05:26:16** | **DRAWDOWN_BLOCK on GRTUSDT @ 22.93%** — 2nd false-positive event |
| 05:31:32 | SYMBOL_UNBLOCKED GRTUSDT |
| 06:03:54 | Hedge ADJUST GRTUSDT -4937 qty (spot drift) |
| 06:08:13 | GRTUSDT demoted (1.2h held). Hedge CLOSE. |
| 06:38:17 | **FETUSDT activated**. Hedge OPEN. |
| 06:48:24 | Final session line. FETUSDT still active, hedged. |

#### Per-Symbol Performance

| Symbol | Trades | Gross profit | Notes |
|---|---:|---:|---|
| DOGEUSDT | 86 | +$2.01 | Bitfinex+MEXC pair (boost-driven). 78% of all session trades. ~$0.024 avg/trade. |
| GRTUSDT | 19 | +$0.48 | MEXC→Bitget mostly (Bitfinex doesn't have GRT). ~$0.025 avg/trade. |
| FETUSDT | 5 | +$0.12 | MEXC→Binance. Just activated. |

#### v0.29 Feature Validation

##### 1. Role Boosts Working (Bitfinex+MEXC dominance)

**86 of 110 trades (78%)** routed through Bitfinex↔MEXC for DOGEUSDT — the most concentrated single-pair session yet. This is the boost succeeding at concentration:

| Pair | Trades | Symbol coverage |
|---|---:|---|
| **DOGEUSDT Bitfinex→MEXC** | 62 | Boosted route, 0% buy + 0.04% sell = 0.04% total |
| **DOGEUSDT MEXC→Bitfinex** | 24 | Boosted reverse — also 0% on the buy leg (Bitfinex sell at 0%) |
| GRTUSDT MEXC→Bitget | 15 | GRT not on Bitfinex; MEXC.seller_boost=5 still wins seller |
| FETUSDT MEXC→Binance | 5 | FET not on Bitfinex |
| GRTUSDT Binance→Bitget | 4 | One non-MEXC seller pair |

**~96% of all session trades** had MEXC on one side, validating the seller boost. **86% had Bitfinex on the other side**, validating the buyer boost. The 25× preference factor concentrated capital on the structurally cheapest route.

##### 2. Daily Auto-Disable Scheduler Ran Cleanly

`[AutoDisable] Daily run @ 2026-04-30 00:01:00 UTC`:
- Threshold: $10,000/24h
- Total auto-blocked: 5 pairs across 6 exchanges
- **Bitfinex: blocked 5 ([EIGEN, ENA, HYPE, JUP, LDO])** — exactly matched the analysis we did before deploy
- All other 5 exchanges: 0 added (all bot symbols had >$10K/24h)
- State file persisted; settings.json updated automatically
- Single fetch cycle, 0 errors, 0 retries

##### 3. Trade-Amount Hourly Auto-Rescale Working

8 rescale events fired (6 hourly_tick + 2 discovery transitions):

| Time | Reason | Trade amount | Capital |
|---|---|---:|---:|
| 00:43:42 | hourly_tick | $40.00 → $40.00 | $1000.00 → $1000.02 |
| 01:43:42 | hourly_tick | $40.00 → $40.07 | $1000.02 → $1001.85 |
| 02:15:21 | discovery_started | $40.07 → $40.06 | $1001.85 → $1001.55 |
| 03:16:05 | hourly_tick | $40.06 → $40.15 | $1001.55 → $1003.74 |
| 04:30:21 | hourly_tick | $40.15 → $40.14 | $1003.74 → $1003.61 |
| 04:43:44 | discovery_started | $40.14 → $40.12 | $1003.61 → $1003.07 |
| 05:43:45 | hourly_tick | $40.12 → $40.18 | $1003.07 → $1004.42 |
| 06:08:14 | discovery_started | $40.18 → $40.22 | $1004.42 → $1005.43 |

Trade amount tracked capital growth correctly. Discovery transitions fired as designed. Total trade-size growth across the session: 0.55% — matching capital growth almost exactly.

##### 4. Phase D Hedge Testnet — Continued Clean Operation

| Counter | Value |
|---|---:|
| Opens | 4 (DOGE × 2, CHZ, GRT, FET) |
| Adjusts | 1 (GRT spot drift) |
| Closes | 4 (all on demote) |
| Errors | **0** |
| Cumulative funding | -$0.005 (DOGE -$0.005, others slightly positive) |

All four hedge cycles closed cleanly on demotion. RECONCILE_DONE on startup verified. Funding accrual tracked correctly.

#### Issues Identified

| # | Severity | Issue |
|---|---|---|
| 1 | **HIGH** | **Drawdown still triggers at 21.99% / 22.93% during GRTUSDT activity** — same insufficient-cap bug noted pre-deploy in S24. v0.29.0-beta didn't ship a fix. The 1%/tick cap allows compound growth over many ticks; peak ratchets up during minor wins, then a small dip reads as 22% drawdown. **Must be addressed in v0.30.** |
| 2 | MEDIUM | **`[Optimizer] BFX over-target ... but no non-Bitfinex active exchange needs USDT` log spam** — 3,955 events in one session, mostly the no-recipient skip path. Throttling exists for active redistribute paths but not the skip path. Same issue noted in S20/S21/S23 — still not fixed. |
| 3 | MEDIUM | **`AUTO_EXPAND triggered: active=1/4` fired hundreds of times** — only 1 active symbol for long stretches because the fee-adjusted threshold is too high for non-Bitfinex+MEXC pairs even with the diversification floor (0.5×). Activations clustered around DOGE/GRT/CHZ/FET — all with very tight margins. |
| 4 | LOW | **demoted=71 EVD seller demotions** — high count of EVD penalty flips. Suggests the EVD penalty (0.02) may be too aggressive given how often Bitfinex's event-driven feed competes with streaming exchanges as seller in the boost-preferred pair. Worth reviewing. |
| 5 | LOW | **Multiple DOGE re-activate→demote cycles** in 3 hours (DOGE active twice, demoted twice). The score barely clears the activation threshold then sags below — churn-prone behavior. Demotion cooldown of 12,600s (3.5h) prevented further immediate re-activations. |

#### Capital Flow

Final balances:
| Exchange | USDT | Notes |
|---|---:|---|
| Binance | $368 | Accumulated from BFX over-target redistributes |
| **Bitfinex** | **$201** | Settled near reserve target ($200) — boost worked |
| Bitget | $0 | All routed out via demotion sweeps |
| Bybit | $0 | Boost flag disabled? — 0 trades on Bybit (but enabled in fee_configs). All trades flowed through other 5 exchanges. |
| MEXC | $436 | Accumulating from sell side (boost driving MEXC as seller) |
| OKX | $0 | All routed out |
| **Total** | **$1,005** | ~Flat (slight positive) |

**Bitfinex over-target redistributes successful**: ~10 redistribute events sent ~$925 of excess Bitfinex USDT to MEXC/Binance/Bitget/OKX over the session, all at $0 fee. The boost-driven concentration on Bitfinex+MEXC kept the trading float utilized.

#### Lessons / Conclusions

- **v0.29 role boosts work as designed**. 78% of trades routed through the preferred Bitfinex+MEXC pair (DOGE) when symbol availability + boost combined. The 25× preference factor concentrated capital correctly without blocking diversification entirely.
- **Auto-disable scheduler ran cleanly on its first live execution**. Five Bitfinex symbols (EIGEN/ENA/HYPE/JUP/LDO) correctly auto-blocked at 00:01 UTC matching pre-deploy analysis.
- **Trade-amount auto-rescale tracked capital growth accurately** with 8 firings (hourly + discovery transitions). No anomalies.
- **Hedge testnet remains rock-solid** — 4 cycles, 0 errors. Demotion-driven closes work consistently.
- **Drawdown false-positive bug still ships** in v0.29 — caught in S24 pre-deploy testing, not fixed for v0.29. Must be the headline fix in v0.30.
- **DOGEUSDT/GRTUSDT/FETUSDT/CHZUSDT cycle pattern is the new normal** when there's no AR-style spike. Quiet sessions average ~$0.20-0.30/hr at this capital scale. The v0.29 features stabilize the routing but can't manufacture spread that doesn't exist in the market.
- **Bybit had zero trades despite being enabled** — all routes preferred Bitfinex/MEXC due to boost OR routed to Binance/Bitget/OKX as second-tier alternatives. Bybit's role as buyer/seller never fired. Worth checking if Bybit's `as_buyer`/`as_seller` flags are correctly enabled in fee_configs.

#### Set-Up for v0.30.0-beta (Capital Architecture Refactor)

The architecture refactor implemented after S25 directly addresses three observations from this session:

1. **Bitfinex still grew to $440+ multiple times** during the session before redistributing (target was $200, threshold was $300). At $1k capital this is fine; at $10k it would be $4,400+ on a self-attested PoR exchange. v0.30 caps the trading float by `trade_amount × 8 = $320` regardless of capital.
2. **Bitfinex over-target redistributions went to whichever active exchange needed USDT** (8 events total, $925 distributed). v0.30 routes overflow to a single custody hub (Bybit) — single destination, simpler, and the bulk-USDT custody risk moves to the third-party PoR audited exchange.
3. **Demotion sweeps stayed on Bitfinex** (visible in the post-demotion balances). v0.30 explicitly sweeps demotion proceeds to Bybit via Aptos $0.

These changes don't fix the drawdown bug (#1 above) — that's still a separate v0.30 priority.

### Session #26 — 2026-04-30 (v0.30.0-beta, First Live Run with Capital Architecture Refactor)

**Date**: 2026-04-30 07:07 UTC → 14:05 UTC (~6h 58m active accounting)
**Capital**: $1,000 ($40 per trade, 4%)
**Version**: v0.30.0-beta — first session with the Bybit custody hub + Bitfinex trading float architecture. v0.30.0-beta committed locally but **never pushed/deployed** — same as v0.28.3/v0.29.0.
**VPS**: LightNode Bangkok + Oracle Zurich (Bitfinex proxy)
**Hedge mode**: testnet
**Active exchanges**: 6 (Binance, OKX, Bybit, MEXC, Bitget, Bitfinex)
**Disabled exchanges**: 3 (Gate.io, KuCoin, Pionex)

#### Headline Result — Deficit, Mostly From Activation-Then-Unwind Cycles

| Metric | Value |
|---|---:|
| Trades | 22 |
| Trading P&L | +$0.30 |
| Transfer fees | $1.05 |
| Cashback (credited / pending) | $0.07 / $0.05 |
| **Net** | **-$0.69** |
| **$/hr** | **-$0.10** |
| Final portfolio | $1,001 (started $1,000, +0.1% raw — slight crypto MTM gain) |
| sz0 | 753 |
| Phantom spreads filtered | 78 |
| Pos-cap throttles | 35 |
| Rebalance blocked | 50 |
| EVD seller penalties / demoted | 10,117 / **102** |
| Anomaly | 0 pauses / 0 warnings / **3 symbol-blocks** |

A loss session, mostly because the bot activated 5 symbols (SNXUSDT → DOGEUSDT → APTUSDT → ZROUSDT → HYPEUSDT → JUPUSDT) but only managed to execute 22 trades total. Each activation-then-demotion cycle paid setup + unwind fees.

#### v0.30 Migration Worked

- `[Settings] Startup sync: trading_float_mult: 8.0x -> 6.7x (target=$268)` — migration from v0.29's `bitfinex_reserve_pct=0.20` × $1000 / $40 = **6.7×** (clamped). Idempotent on subsequent restarts.
- `[Capital] Trading float: $268 on Bitfinex (trade_amount $40 × 6.7x), custody hub = Bybit` — confirmed at every discovery completion.
- All `[Capital]` log component lines populated correctly: trading float overflow, custody consolidation, custody sweep, post-demotion sweep, idle-sell-via-Bitfinex+sweep.

Capital flow worked exactly as designed:
- Bitfinex held ~$268 (trading float) for the entire session
- Bybit accumulated to $733 (final) — bulk USDT custody
- Other exchanges cycled to ~$0 between activations

#### Headline Issue: $0.30 in OKX→Bybit Aptos Fees Were Actually Polygon Fees

The bot's `_get_withdrawal_fee(exchange)` returns each exchange's preferred-network fee, not the configured `custody_hub_network` fee. The log line says "via Aptos" but the actual withdrawal uses each source exchange's preferred network:

| Source → Bybit "via Aptos" | Actual fee | Reason |
|---|---:|---|
| MEXC → Bybit | **$0.0000** ✓ | MEXC's preferred is Arbitrum (genuinely free) |
| Bitget → Bybit | $0.0010 ✓ | Bitget's preferred is Plasma/Arbitrum (~free) |
| **OKX → Bybit** | **$0.1000 ✗** | **OKX's preferred is Polygon — NOT Aptos!** |
| Bitfinex → Bybit | $0.0000 ✓ | Bitfinex has 14 free networks |

**3 OKX consolidations × $0.10 = $0.30** in unintended fees during the session — that's 32% of the total $0.95 transfer fees.

The architecture spec said "Aptos $0 universal" but the code uses the existing per-exchange `preferred_network` setting, which for OKX is Polygon. Need to either (a) add `network` parameter to `_get_withdrawal_fee()`, or (b) override `preferred_network` to `Aptos` for all enabled exchanges at custody-hub-flow time.

#### Drawdown False-Positives Continue (Pre-Fix-C)

3 SYMBOL_BLOCKs fired:

| Time | Drawdown reported | Real portfolio | Implied peak |
|---|---:|---:|---:|
| 07:33:09 | 15.96% | $960 | $1,142 |
| 08:59:50 | 15.52% | ~$1,001 | ~$1,184 |
| (later) | — | — | — |

Same v0.28.3 cap-insufficiency bug carried forward. Diagnosed in this session: the 1%/tick cap doesn't fix the actual mechanism, which is **MTM noise getting baked into peak**. Three contributing factors identified:

1. **Spot crypto held on multiple exchanges, each with its own slightly-different price** — bot uses ONE price (first fetcher) for all exchanges' crypto MTM. Cross-exchange spread = persistent MTM noise.
2. **Hedge unrealized PnL uses spot mid as proxy for futures close-out price** — spot ≠ futures (basis spread). Hedge doesn't perfectly offset spot crypto MTM moves.
3. **Symbol-rotation windows where spot inventory and hedge are out of sync** — e.g., FET inventory still on Bitget after rotating to SNX hedge → unhedged FET MTM moves contribute pure noise.

Fixes designed and implemented post-session (v0.30.1-beta):
- **Fix C**: peak ratchets only on **realized capital** (USDT + locked-in P&L + credited cashback), not MTM. Eliminates the entire phantom-drawdown class. **Reproduced S26 scenario: peak goes from $1,142 → $1,000.10, drawdown from 15.96% → 4.01%, no SYMBOL_BLOCK.**
- **Fix A**: per-exchange spot pricing for crypto MTM. Each exchange's crypto is marked at THAT exchange's actual price.
- **Fix B**: hedge unrealized uses Binance Futures markPrice (already polled by `funding_monitor`, 1000X-scaled for PEPE/SHIB/FLOKI).

#### Session Timeline

| Time | Event |
|---|---|
| 07:07:18 | Session start. v0.30 migration: `bitfinex_reserve_pct=0.20 → trading_float_multiplier=6.7×` |
| 07:22:20 | First activation FETUSDT, hedge OPEN, demoted 2s later |
| 07:22:22 | Hedge OPEN SNXUSDT |
| 07:32:40 | First trade (SNX OKX→Bitget) |
| 07:33:09 | **DRAWDOWN_BLOCK 15.96%** (false positive, peak inflated by FET inventory MTM during rotation) |
| 08:23:29 | SNX demoted; first post-demotion sweep $692 → Bybit (paid $0.10 OKX fee — Fix-needed signal) |
| 08:28:30 | DOGEUSDT activated, hedge OPEN |
| 08:44:11 | DOGE demoted (held 0.3h) |
| 08:59:13 | APTUSDT activated, hedge OPEN |
| 08:59:50 | **DRAWDOWN_BLOCK 15.52%** (2nd false positive) |
| 09:31:08 | Rotation APT→ZRO ($10/hr improvement estimate) |
| 10:00:32 | ZRO demoted (held 0.4h) |
| 10:05:34 | HYPEUSDT activated, hedge OPEN |
| 12:59:16 | HYPEUSDT demoted, no replacement found |
| 13:04:17 | **JUPUSDT activated** (only candidate) — but Bitfinex doesn't list JUP → boost preference can't fire |
| 13:04 → 13:34 | **Zero JUP trades** for 30 min |
| 13:34:25 | Idle-crypto consolidation: sold $368 of unused JUP via Bitfinex 0%, swept to Bybit, paid $0.001 in unwind fees |
| 13:34 → 14:05 | Idle, no further activity |
| 14:05:55 | Final session line: net=-$0.69 |

#### Per-Symbol Performance

| Symbol | Trades | Profit | Hedge held | Notes |
|---|---:|---:|---:|---|
| SNXUSDT | 2 | +$0.026 | 1.0h | Demoted before generating real spread |
| APTUSDT | 11 | +$0.272 | 0.6h | Best performer, half went via Bitfinex (boost worked) |
| HYPEUSDT | 9 | +$0.014 | 0.7h | All Bitget→MEXC, 0% net% by end (spread closed) |
| DOGEUSDT | 0 | $0 | 0.3h × 2 | Activated twice, demoted twice without trading |
| ZROUSDT | 0 | $0 | 0.4h | Activated, demoted, never traded |
| JUPUSDT | 0 | $0 | not hedged | Activated but Bitfinex didn't list — boost couldn't fire |

#### Issues Identified

| # | Severity | Issue |
|---|---|---|
| 1 | **HIGH** | **OKX preferred-network fee leaks** — v0.30 architecture said "Aptos universal $0", but code uses each exchange's `preferred_network` setting. OKX's is Polygon ($0.10). Three OKX→Bybit consolidations cost $0.30 (32% of total session fees). Fix: add `network` param to `_get_withdrawal_fee()` OR override `preferred_network` for custody-hub flows. |
| 2 | **HIGH** | **Drawdown false positives still firing** — Fix C designed and implemented after session ends. |
| 3 | MEDIUM | **JUPUSDT activation futile** — Bitfinex doesn't list JUP, so boost-preferred Bitfinex+MEXC route can't form. Bot allocated, sat 30 min, unwound at small loss. Should expansion ranking deprioritize symbols not on Bitfinex even harder than the current 0.7× penalty? |
| 4 | LOW | **5 distinct symbols cycled in 6h with only 22 trades total** — average 4.4 trades per activation. Most activations were unprofitable churn. The market is offering near-zero spread on the bot's preferred Bitfinex+MEXC pairs. |

#### Capital Flow

Final balances: `Binance=$0 Bitfinex=$268 Bitget=$0 Bybit=$733 MEXC=$0 OKX=$0` = **$1,001 total**.

The v0.30 architecture worked exactly as designed:
- Bitfinex stayed at trading float target ($268) all session
- Bybit absorbed the rest as custody (~$733)
- Other exchanges cycled to ~$0 between active periods
- Trading float overflow fired 3× ($244 + $366 + $179 = $789 swept BFX→Bybit at $0)
- Demotion sweeps to Bybit fired 4× (one per demotion)
- Idle crypto sold via Bitfinex 0% → swept to Bybit (preserved 0% taker advantage)

#### Lessons / Conclusions

- **v0.30 architecture is structurally correct.** Capital flows match the design exactly. The custody/trading-float split works.
- **OKX consolidation cost is the priority fix.** $0.30 of the $1.05 transfer fees came from OKX→Bybit "Aptos" routes that actually used Polygon. Fix: network-aware withdrawal fee lookup, OR temporarily override `preferred_network` during custody-hub flows.
- **Drawdown false positives are now diagnosed and fixed** (Fix C implemented post-session). Reproduced S26 scenario, confirmed peak $1,142 → $1,000, drawdown 15.96% → 4.01%.
- **Activation churn dominates losses** at this market regime. 5 symbols cycled in 6h with 22 trades. The boost-preferred Bitfinex+MEXC pair only fired meaningfully on APTUSDT for ~30 min. This isn't a bug — it's the market not offering spread.
- **JUPUSDT activation was a textbook example** of "symbol activated despite not being on Bitfinex" → boost preference can't fire → trades don't happen → unwound. Expansion preference should harshly penalize non-Bitfinex symbols when other candidates exist, not just apply a 0.7× factor.
- **Hedge testnet remained perfect** (continuing the trend from S22-S25). 6 OPENs, 6 CLOSEs, 0 errors. Cumulative funding -$0.005.

#### Set-Up for v0.30.1-beta (Drawdown Fixes + Network-Aware Fees)

After session end, three drawdown fixes were implemented:
- **Fix C** (peak from realized capital, not MTM) — eliminates phantom drawdown class entirely
- **Fix A** (per-exchange crypto MTM) — reduces dispersion error
- **Fix B** (Binance Futures markPrice for hedge unrealized) — eliminates spot/futures basis error

The OKX network-fee leak is **not yet fixed**. That's the highest-priority operational issue for v0.30.1.

### Patches v0.30.1-beta → v0.30.6-beta (between S26 and S27)

Six patch releases were shipped during the S26→S27 gap, addressing drawdown false-positives, activation-logic gaps, observability, and UI polish. Summarized inline so the next session post-mortem doesn't have to re-derive context from git.

#### v0.30.1-beta — Phantom Drawdown Fixes
- **Fix C — peak ratchets on realized capital**, not MTM. `BalanceTracker.get_realized_capital()` returns `initial + trading_pnl + credited_cashback − external_fees` (no spot/hedge MTM). `AnomalyProtection.update_portfolio_value(realized_value=…)` uses this for peak tracking; drawdown is still measured against MTM `portfolio_value`. Eliminates the entire phantom-drawdown class from MTM oscillation.
- **Fix A — per-exchange spot prices for crypto MTM**. Crypto on each exchange is marked at THAT exchange's actual price. New `monitor._get_per_exchange_prices()` helper; `BalanceTracker.get_portfolio_value(prices_per_exchange=…)`.
- **Fix B — Binance Futures markPrice for hedge unrealized PnL**. `HedgeManager.get_debug_state()` prefers `funding_monitor.get_mark_price()` (1000X-scaled) over spot mid. Each hedge entry tags `mark_source: "futures"|"spot"`.
- **Boost-aware activation gate (initial)** — set non-preferred-route activation floor to `very_strong × non_preferred_score_multiplier` (default 0.3 × 2.0 = 0.6). *This part was reverted in v0.30.4 — see below.*

#### v0.30.2-beta — Boost-aware Floor Rebase
- After S27 (now-renumbered S27, observed as JUPUSDT @ 0.191) showed legitimate strong-tier candidates being blocked at 0.6 floor, rebased the formula to `strong_threshold × multiplier` (= 0.1 × 2.0 = 0.2). Multiplier semantics became: 1.0 = strong tier, 2.0 = very-strong-ish, 3.0+ = exceptional only. *Also reverted in v0.30.4.*

#### v0.30.3-beta — Block-aware Scoring + Per-symbol Exchange View
- **Block-aware scoring**. `_score_tick()` now skips `(buyer, seller)` pairs where either leg is blocked for the symbol via `fee_manager.can_buy/can_sell`. Without this, the score reflected opportunities through blocked exchanges that the allocator couldn't actually use — observed when JUPUSDT scored 0.27 while Bitfinex was auto-disabled for JUP, leaving the bot allocated to a zero-edge Bybit↔MEXC pair.
- **Per-symbol exchange view in rankings UI**. New `SymbolOptimizer.get_symbol_exchange_view(symbol)` returns sorted `buyers` and `sellers` lists for any symbol (not just active ones), each entry tagged with `weight` and `blocked`. Mirrors `_compute_dominant_pairs._select_top` math. Surfaced in `get_rankings()` as `exchange_view`. Symbol Rankings table renders for **all 20 ranked symbols** — best buyer (cyan, bold) → best seller (fuchsia, bold), secondary entries dimmer, **blocked exchanges in rose strikethrough**.

#### v0.30.4-beta — Drop Boost-aware Gate; Trajectory-aware Fast-track + Hover Tooltip
- **Boost-aware activation gate REMOVED**. Per operator: the gate was *deboosting* non-preferred routes via a hard score floor — contradicting the multiplicative-only design intent. The 25× boost in pair selection (`monitor._tick`, `optimizer._select_top`) is sufficient. Removed: `_is_boost_preferred_route`, `boost_aware_activation_enabled`, `non_preferred_score_multiplier`, `route=` log fields, UI section. Boost multipliers in pair selection unchanged.
- **Fast-track discovery exit**. Trajectory-aware early-exit replaces the simple `scoring_window // 6` rule:
  - `_classify_trajectory(samples_or_entry)` compares `mean(last-15)` vs `mean(prior-15)` with peak-resilience clause (`current ≥ peak × 0.85` overrides averages-based decline).
  - Tier × trajectory matrix: `strong+ rising = 30s`, `strong+ stable = 60s`, `normal rising = 240s`, `normal stable = 300s`, `any + declining = full standard`.
  - Strong-tier candidates additionally need a tier-confirmation gate (last N samples all ≥ strong_threshold) to prevent activating on single-tick spikes.
  - Settings: `fast_track_discovery_enabled` (default true), `fast_track_aggressiveness` (float, default 1.0).
- **Per-symbol diagnostic + hover tooltip**. `optimizer._build_symbol_diagnostic()` produces structured `{status, tier, trajectory, reasons[], score_formula, threshold_breakdown, watchlist}` per ranking entry. Symbol Rankings table renders a sticky hover popover with status pill, tier color, trajectory icon, bulleted reasons, score/threshold breakdowns. Updates with each broadcast tick.

#### v0.30.5-beta — Trajectory Fix + Deficit-trade Gate + Restart Orphan Close-out
- **Trajectory bug for active symbols**. S30 showed GRT 0.066 → 0.049 over 5 min (clearly declining) with tooltip reporting "rising" because `_classify_trajectory` was reading `WatchlistEntry.score_samples` — only populated during discovery + watchlist confirmation. After activation the watchlist entry was popped and samples froze. Added `SymbolOptimizer._score_history: dict[str, deque[float]]` (maxlen 120) updated for ALL symbols at the end of every `_compute_scores()` tick. `_classify_trajectory` now accepts a list/deque or `WatchlistEntry`.
- **Deficit-trade gate**. S30 had multiple PENDLE Bitget→Binance trades print `net=-0.0055%`. Root cause: the threshold check uses `scoring_net` which has cashback discount baked in via `get_scoring_fee` → scoring_net positive while raw_net negative. Fix: `monitor._tick()` now also requires `raw_net_pct > 0` before executing. Cashback IS real but delayed (1-24h); the bot shouldn't trade at immediate raw deficit on the *promise* of cashback.
- **Restart orphan close-out**. S30's $215 phantom drawdown was caused by a -273 PENDLE futures short adopted as orphan from a previous session at $1.3357 entry — when Fix B switched to markPrice, the inherited entry vs current testnet markPrice gap produced fictitious unrealized loss that hedging cannot offset (it's pre-existing, not new exposure). New `HedgeManager.close_all_real_positions(reason)` queries the executor for ALL real positions (not just shadow-tracked) and closes every one. Wired into the dashboard "Restart Bot" handler — runs BEFORE state clear. Shadow-only mode just wipes shadow.
- **UI: column always uses exchange_view**. Removed the `dominant_buyers/dominant_sellers` fallback path. Column is now consistent with the hover tooltip.

#### v0.30.6-beta — Tooltip Bitget/Bitfinex Collision + Cursor-following Popover
- **Tooltip Bitget/Bitfinex collision**. Popover was rendering exchange names via `name.slice(0, 3).toUpperCase()`, collapsing both "Bitget" AND "Bitfinex" to "BIT". The column used `shortEx()` with the EX_SHORT lookup (Bitget→BGT). Same data, two render paths, reported as "column shows BGT, tooltip shows BIT" inconsistency. Added Bitfinex→BFX and Pionex→PNX to EX_SHORT; popover now uses `shortEx()` for both buyer and seller lists.
- **Cursor-following popover**. Tooltip follows the mouse cursor with a 16px margin instead of being pinned to the viewport's bottom-right. Auto-flips to the left of the cursor if it would overflow the right edge; auto-flips above if it would overflow the bottom. Animation shortened from 120ms → 80ms.

### Session #27 — 2026-04-30/05-01 (v0.30.6-beta, ~8h14m, ended in deficit)

#### Headline Result — Deficit despite all v0.30.1-6 fixes

| Metric | Value |
|---|---:|
| Duration | 8h14m (17:09 UTC → 01:23 UTC next day) |
| Trades | 14 (1.7 trades/hour) |
| Trading P&L | +$0.13 |
| External transfer fees | $0.29 |
| Cashback (credited / pending) | $0.03 / $0.03 |
| **Net** | **−$0.12** ($/hr = −$0.01) |
| Final portfolio value | ~$999 (≈ flat from $1,000 start) |
| Symbols cycled | 4 (NEAR → PENDLE → EIGEN → DOGE) |
| Hedge OPENs / CLOSEs / errors | 4 / 3 / 0 |
| Cumulative funding (hedge) | +$0.005 |
| Anomaly events | 0 pauses, 0 warnings, 0 symbol blocks |
| sz0 / rebal_blocked / phantom / pos_cap | 912 / 309 / 79 / 35 |
| evd_seller penalties applied | 11,914 (53 demoted) |

**This is the cleanest session yet** — zero anomalies, zero errors, hedge testnet still flawless, no phantom drawdowns (Fix C did its job), no deficit trades after the v0.30.5 raw-net gate, no orphan position issues (none carried over from S26→S27 since the user clicked Restart Bot which now closes all real positions). And yet the bot still ended slightly negative.

#### Why the Deficit (root cause, single sentence)

**Demotion-sell taker fees ($0.28) consumed the trading P&L ($0.13).** Specifically:
- PENDLE demotion at 19:56:58 sold $361.09 of crypto on MEXC (NOT routed via Bitfinex 0%) → fees $0.181
- EIGEN demotion at 00:10:10 sold $42.94 on Bitget → fees $0.101
- NEAR demotion was correctly routed via Bitfinex 0% → fees $0.000 (saved $0.017 taker)

The $0.28 in demotion-sell fees is the dominant cost. Trade execution itself was profitable — every recorded trade had a positive net% (no deficit-trade events fired the v0.30.5 raw-net gate, confirming it works).

#### Why So Few Trades (14 in 8 hours)

| Cause | Count | Effect |
|---|---:|---|
| Size-zero skips | 912 | Most ticks couldn't generate a meaningful trade size — likely due to inventory drift |
| Rebalance blocked | 309 | Various rebalance gates rejected |
| Position-cap skips | 35 | Crypto inventory hit the `max_position_multiplier × trade_amount` cap |
| Phantom-spread filtered | 79 | Spread didn't persist across consecutive ticks |
| EVD-seller penalty | 11,914 | Bitfinex-as-seller score-time penalty applied (does NOT block, just deprioritizes) |
| Demoted candidates | 53 | Most candidates declined and were demoted before activation |

The bot was *working as designed* — it just spent most of the session waiting for a tradeable opportunity, and the few times it found one (3-4 trades per active symbol) the spreads were thin and inventory imbalances quickly forced size-zero skips.

#### Per-symbol Performance

| Symbol | Trades | Net profit | Held | Notes |
|---|---:|---:|---:|---|
| NEARUSDT | 4 | +$0.021 | 0.5h | Bitfinex→MEXC (preferred route worked). Demoted at 17:43, no replacement for ~1h. |
| PENDLEUSDT | 2 | −$0.017 | 1.2h | Bitget→MEXC (non-preferred). Trade #5 printed -$0.0195 profit despite +0.0272% net% — suspicious; quantity rounding cost. Demoted with $0.18 fee. |
| EIGENUSDT | 4 | +$0.102 | 0.6h | OKX→Bitget once, MEXC→Bitget thrice. Best-performing activation. Demoted with $0.10 fee. |
| DOGEUSDT | 4 | +$0.027 | 0.7h+ | Bitfinex→MEXC (preferred). Still active at session end. |
| **Total** | **14** | **+$0.133** | | Trade execution was net positive; demotion fees (-$0.28) flipped the session negative. |

#### v0.30.1-6 Feature Validation — All Working

| Feature | Verdict | Evidence |
|---|---|---|
| Fix C (realized-capital peak) | ✓ working | Zero false-positive DRAWDOWN_BLOCK events. PEAK_RESET fired correctly on hedge open/close basis changes (00:40:13/14) and on full crypto liquidation (00:10:10). |
| Fix A (per-exchange MTM) | ✓ working | No spot/dispersion noise observed. |
| Fix B (futures markPrice) | ✓ working | Hedge unrealized stayed reasonable. |
| Block-aware scoring | ✓ working | No phantom JUPUSDT-style activations. |
| Trajectory classifier (live) | ✓ working | Active symbols' trajectory updates each tick now. |
| Raw-net gate | ✓ working | Zero deficit-trade events recorded; every executed trade was raw-positive. |
| Restart orphan close-out | ✓ working | No orphans inherited from previous session. |
| Fast-track discovery | ✓ working | NEAR activated at 257s (fast_track), faster than the 900s standard would have been. |
| Cursor-following tooltip | ✓ working | (operator-confirmed in S30 follow-up before session end). |

#### Hedge Activity (testnet)

| Time | Event | Symbol | Notional | Funding |
|---|---|---|---:|---:|
| 17:13:26 | OPEN | NEAR | $366 | +7.26%/yr |
| 17:43:33 | CLOSE | NEAR (demoted) | — | accrued +$0.0017 |
| 18:45:35 | OPEN | PENDLE | $366 | +10.95%/yr |
| 19:56:58 | CLOSE | PENDLE (demoted) | — | accrued +$0.0053 |
| 23:31:19 | OPEN | EIGEN | $364 | -3.34%/yr |
| 00:06:23 | ADJUST | EIGEN (qty 2014→237) | $43 | — |
| 00:10:11 | CLOSE | EIGEN (demoted) | — | accrued -$0.0015 |
| 00:40:14 | OPEN | DOGE | $364 | -0.21%/yr |

Hedge testnet remains flawless — 4 OPENs, 3 CLOSEs, 1 ADJUST, **0 errors**, cumulative funding +$0.005.

#### Capital Flow

Final per-exchange balances roughly: `Bitfinex ≈ $268 (trading float target, exact)`, `Bybit ≈ $720+ (custody hub, all overflows landed here)`, `MEXC ≈ $40 (one trade in flight)`, others near $0.

Capital flows matched v0.30 architecture perfectly:
- Trading float overflow fired 3× ($244 + $406 + $213 = $863 swept Bitfinex→Bybit at $0)
- Post-demotion sweep fired (PENDLE: $725 freed, swept to Bybit, $0.001 fees)
- Custody consolidation fired 4× from Bitget ($91+$99+$100+$120 = $410, fees $0.004)
- Idle-sell sweep fired once (EIGEN $321 idle 1839s, sold via Bitfinex 0%, swept to Bybit at $0)
- Custody hub on Aptos: zero fees

#### Issues Identified

| # | Severity | Issue |
|---|---|---|
| 1 | **HIGH** | **Demotion-sell route doesn't always go through Bitfinex 0%.** PENDLE demotion at 19:56:58 sold $361 of crypto on MEXC at 0.04% taker = $0.18 fee. EIGEN demotion sold $43 on Bitget at 0.08% = $0.03, plus a $0.07 fee elsewhere. NEAR demotion correctly routed via Bitfinex 0%. The decision logic for "sell here vs route via Bitfinex" needs tightening — it should ALWAYS prefer Bitfinex when the symbol is listed there and crypto can be transferred for free. |
| 2 | MEDIUM | **Trade #5 PENDLE Bitget→MEXC printed profit=−$0.0195 despite net=+0.0272%.** Quantity rounding likely cost more than expected. Worth investigating quantity-rounding precision in `BalanceTracker.execute_trade()` for `LOT_SIZE_STEP`. |
| 3 | MEDIUM | **53 demoted candidates over 8 hours.** Most candidates didn't reach activation. Some symbols (e.g., NEAR/DOGE) cycled multiple times. Each demotion costs cooldown time + setup fees. Could benefit from a "soft demote" for symbols that are profitable but just below threshold — keep them inventoried, lower the trade multiplier, instead of full liquidation. |
| 4 | LOW | **Activation gap — 1h between PENDLE demotion (19:56:58) and EIGEN activation (23:31:18).** Bot sat idle for 3.5h with all-USDT portfolio. Either the candidate set was genuinely thin, or the discovery extension is too patient. |

#### Capital Flow

Final balance: ~$999 portfolio value (≈ flat from $1,000 start).
- Trading P&L: +$0.13
- Transfer fees: −$0.29 (mostly demotion-sell taker fees, see issue #1)
- Cashback credited: +$0.03 (referral cashback)
- Net: −$0.12

#### Lessons / Conclusions

- **All v0.30.1-6 fixes work as intended.** Zero anomalies, zero deficit trades, zero phantom drawdowns, zero orphan-position issues. The infrastructure is solid.
- **Demotion-sell fee leak is the new operational priority.** $0.28 in demotion fees consumed all $0.13 of trading P&L. Fix: the demotion logic should ALWAYS route via Bitfinex 0% when the symbol is listed there, regardless of the symbol's most recent dominant pair.
- **Trade frequency is the structural bottleneck.** 14 trades in 8h is too few to overcome any operational cost. The market wasn't offering edge on the bot's preferred Bitfinex+MEXC pairs for most of the session — when it did (NEAR for ~30 min, EIGEN for ~30 min, DOGE at session end), trades printed reliably.
- **Hedge testnet is production-ready.** Five sessions of clean operation (S22-S27 except for the orphan-adoption issue, now fixed in v0.30.5).
- **Tooltip + exchange_view UI feedback is now consistent.** Column and popover render the same data via the same `shortEx()` helper.

#### Set-Up for v0.30.7-beta (Demotion-sell Routing Fix)

The single highest-value fix for v0.30.7 is forcing demotion sells through Bitfinex 0% whenever the symbol is listed there, instead of selling locally on the buyer exchange. Saved $0.20+ in S27 alone.

Lower priority:
- Quantity-rounding investigation (PENDLE Trade #5 anomaly)
- Optional: "soft demote" for marginally-failing strong candidates instead of full liquidation
- Optional: tighten discovery extension when candidate set is thin (1h+ idle gaps are wasteful)

### Session #29 — 2026-06-28 (v0.32.3-beta, multi-config simulation hedge audit)

#### Context

This session documents the investigation around `logs/bot-logs-2026-06-28-13-40-48.log`, plus the operator discussion immediately after it:

- Wallet page showed portfolios materially above/below `initial capital + realized net P&L`.
- Example: `Group 3: $3k — Discovery & Scoring Tuning / Aggressive (Permissive Scoring)` showed about `$3,126` portfolio against `$78.92` net P&L, where accounting equity should be around `$3,078.92`.
- Bitfinex was confirmed as spot-only for this bot; futures hedging is only via Binance USD-M Futures.
- The wallets page showed total trades capped at `10,000` while total net P&L kept moving.
- Before adding live futures capital allocation, the latest log was re-audited and all issues were recorded here.

#### Latest Log Summary

| Metric | Value |
|---|---:|
| Log file | `logs/bot-logs-2026-06-28-13-40-48.log` |
| Runtime window | 2026-06-28 07:44:44 -> 13:40:29 |
| Version | `v0.32.3-beta` |
| Configs with session lines | 46 |
| Execution mode | `simulation` for all configs |
| Hedge mode | `simulation` for all hedged configs |
| Real Binance Futures orders | 0 |
| Positive / negative net configs | 37 / 9 |
| Summed trading P&L | +$740.13 |
| Summed transfer fees | $287.24 |
| Summed net P&L | +$580.63 |
| Summed trades reported | exactly 10,000 (capped counter bug) |
| Log warnings / errors | 1,465 warnings / 0 errors |
| Anomaly pauses / warnings / symbol blocks | 0 / 0 / 0 |
| Hedge eval errors | 0 |
| No-space / connection errors | 0 / 0 |

The aggregate P&L is a parameter-grid aggregate, not one real portfolio result. It sums all 46 simulated configs.

#### Best/Worst Configs By Realized Net

| Config | Net | Trading P&L | Fees | Trades | Final wallet total | Drift vs `initial + net` |
|---|---:|---:|---:|---:|---:|---:|
| G3 Aggressive (Permissive Scoring) | +$78.92 | +$82.50 | $16.59 | 469 | $3,126 | +$47.08 |
| G3 Short Scoring Window (10min) | +$41.49 | +$45.52 | $12.91 | 341 | $3,076 | +$34.51 |
| G4 Wide (8 active) | +$36.05 | +$38.26 | $11.53 | 282 | $4,077 | +$40.95 |
| G5 Aggressive (Rapid Shifts) | +$28.55 | +$36.78 | $11.71 | 330 | $5,048 | +$19.45 |
| G4 Maximize Profits | +$25.94 | +$29.01 | $7.01 | 484 | $4,028 | +$2.06 |
| G1 All 8 Exchanges | -$1.52 | +$3.63 | $5.60 | 114 | $1,001 | +$2.52 |
| G1 + Gate.io | -$1.51 | +$3.70 | $5.66 | 121 | $998 | -$0.49 |
| G1 + KuCoin | -$1.24 | +$3.40 | $5.13 | 122 | $1,001 | +$2.24 |
| G5 No BFX Buyer Boost | -$0.94 | +$0.45 | $1.38 | 33 | $5,012 | +$12.94 |
| G5 Maximize Profits | -$0.07 | +$0.00 | $0.07 | 0 | $5,015 | +$15.07 |

#### Main Finding: Hedge Display Was Real, But In Simulation Mode

All relevant configs in this log were running:

`hedging: enabled=True, mode=simulation, dust=$10, eval_interval=60s, margin_buffer=20%, adjust_threshold=1%`

So the reported wallet mismatch was not a failed real Binance Futures hedge. No real futures positions existed. The dashboard/wallet accounting was mixing:

- raw spot mark-to-market wallet value, with
- realized trade P&L accounting, while
- simulation hedge offsets were not treated as accounting equity for wallet totals.

That is why configs could show large portfolio gains/losses unrelated to realized net P&L.

Largest observed portfolio drifts:

| Config | Wallet total | Expected `initial + net` | Drift | Hedge notional |
|---|---:|---:|---:|---:|
| G3 Aggressive (Permissive Scoring) | $3,126 | $3,078.92 | +$47.08 | $1,568.90 |
| G4 Wide (8 active) | $4,077 | $4,036.05 | +$40.95 | $1,556.70 |
| G3 Short Scoring Window | $3,076 | $3,041.49 | +$34.51 | $831.32 |
| G4 No Auto-Expand | $4,046 | $4,018.74 | +$27.26 | $1,172.54 |
| G4 Neutral (4 active) | $4,045 | $4,018.33 | +$26.67 | $1,172.29 |
| G5 Conservative (Sticky) | $4,978 | $5,000.13 | -$22.13 | $2,515.88 |
| G5 No Boosts (Pure Score) | $4,989 | $5,007.26 | -$18.26 | $2,468.28 |
| G5 Loose Inventory Drift | $4,992 | $5,003.45 | -$11.45 | $2,793.87 |

This confirms the operator's concern: the positive cases were in our favor in this run, but the same accounting path can understate equity when spot moves against the simulated portfolio.

#### Post-Log Fixes Implemented In Working Tree

The following fixes were implemented after reading this log and are intentionally not committed until operator confirmation:

- Dashboard portfolio value for simulation-hedged configs now uses accounting equity (`initial + realized net P&L` plus the hedge funding/cashback/fee components) instead of raw spot MTM, unless there are material unhedged targets.
- Dashboard selected config `net_pnl` now uses realized `net_profit`; `price_pnl` carries the residual price effect.
- `monitor.py` balance snapshots now log hedged/accounting/drift diagnostics so future logs expose this class directly.
- Hedge target sizing now includes in-transit crypto, because in-transit crypto is still price exposure.
- Total trade count now uses `_cumulative_trade_count` instead of `len(_trades)`.
- Orchestrator dirty/change detection now also uses `_cumulative_trade_count`; previously once `_trades` hit its maxlen, new trades might not wake hedge reconciliation/state save.
- Wallets UI now formats large trade counts without implying a 10k hard stop.

Validation already run:

- `python3 -m py_compile dashboard_server.py monitor.py orchestrator.py hedge_manager.py`
- `git diff --check`
- `npm --prefix dashboard run build`
- Smoke tests for simulation hedge accounting fallback and in-transit hedge sizing.

#### Trade Counter Cap

The log shows the cap clearly:

`[Capacity] ... configs=46 dirty=0 trades=10000 transfers=9378 ...`

The parsed last session lines across all configs also sum to exactly `10,000` trades. This was not a real stop in trading. It was a reporting/data-structure bug: `_trades` is a bounded deque (`maxlen=5000` per monitor), but dashboard/capacity code used `len(_trades)` as if it were the lifetime total. P&L continued moving because `_cumulative_pnl` was separate.

#### Operational Issues Found In The Log

| Severity | Issue | Evidence |
|---|---|---|
| HIGH | Wallet/portfolio value was not hedge-accounting aware in simulation hedge mode | Large drift between wallet totals and `initial + realized net`, e.g. G3 Aggressive +$47.08 drift |
| HIGH | Trade totals were capped at 10,000 | Capacity logs repeatedly printed `trades=10000`; aggregate parsed session trades exactly 10,000 |
| HIGH | Live mode has no Binance Futures capital allocator yet | Current code only checks futures available margin before placing a hedge; no reserve, no auto-transfer, no spot/futures split |
| HIGH | Bybit fee validation key is expired | 1,363 warnings: `Bybit fee rate query failed: Your api key has expired.` Fee assumptions may become stale. |
| MEDIUM | Bitfinex subscription set still includes unsupported symbols | 56 warnings across 28 symbols, including `GRTUSDT`, `WIFUSDT`, `FETUSDT`, `PENDLEUSDT`, `SNXUSDT`, and Bitfinex-formatted `tARUST/tWUST/tOPUST`. Symbol availability filtering should be stricter. |
| MEDIUM | Many configs were effectively inventory-starved | 15,827 `SIZE_ZERO` lines and 11,757 `SKIP ... trade_size=0` lines; mostly `GRTUSDT`. |
| MEDIUM | Rebalance gating blocked many opportunities during weak regime | 9,406 exact `regime_weak` rebalance blocks. This reduced churn but also left many profitable-looking opportunities unfilled. |
| MEDIUM | Negative-net rotation suppression fired heavily | 1,955 `Rotation suppressed: net profit is negative` lines. This confirms the deficit guard was active and can trap weak configs in stale states. |
| MEDIUM | Discovery often had no tradeable symbols | 34 `Discovery: NO tradeable symbols` warnings and 12 `All symbols demoted` warnings. |
| LOW | DemoCompare is noisy in simulation | 264 `missing_position` messages. This is expected when sim inventory is compared to demo exchange balances with no demo order placement, but it can hide real mismatches. |
| LOW | Maximize Profits variants are not reliably maximizing | G5 Maximize had 0 trades, -$0.07 net, and +$15.07 portfolio drift; G4 Maximize performed well, but other "maximize" configs were constrained by fees/guarding/discovery. |

#### Live Futures Capital Design Decision

Current code:

- Uses Binance USD-M Futures as the only real futures executor.
- Does not use Bitfinex futures.
- Does not transfer funds between Binance Spot and Binance Futures.
- Does not reserve any portion of total capital for futures margin.
- Uses 1x isolated margin and a 20% margin buffer in the current hedge manager.

Recommended live design before real money:

| Parameter | Recommendation |
|---|---:|
| Futures venue | Binance USD-M Futures only |
| Initial live leverage | 2x isolated |
| Hedge notional | Equal to spot crypto exposure, never larger |
| Binance Futures target reserve | 40% of total capital |
| Auto top-up threshold | 35% |
| Stop-new-trades threshold | 30% |
| 1x alternative | 52-55% futures reserve |
| 3-5x leverage | Not recommended for first live version |

Reasoning:

- Leverage does not change hedge dollar P&L if hedge notional remains equal to spot exposure. A `$1,000` spot gain/loss offset requires a `$1,000` short hedge regardless of 1x/2x/5x.
- Leverage only reduces collateral requirement and increases liquidation sensitivity.
- At 1x + 20% buffer, the bot needs roughly 52-55% of total capital in Binance Futures to support hedges for 60% spot capital.
- At 2x, 40% futures reserve is a better first live compromise: capital-efficient enough, but not overly close to liquidation for volatile alts.

#### Implementation Requirements For The Next Feature

Before live hedging is enabled:

1. Add explicit futures capital settings:
   - `hedge_leverage`
   - `futures_capital_target_pct`
   - `futures_capital_topup_pct`
   - `futures_capital_emergency_pct`
   - `futures_capital_overflow_pct`
   - `futures_capital_transfer_min_usd`
2. Make allocation reserve Binance Futures capital first, then distribute remaining spot capital across spot exchanges.
3. Add Binance Spot <-> USD-M Futures auto-transfer support using Binance universal transfer types:
   - `MAIN_UMFUTURE`
   - `UMFUTURE_MAIN`
4. Block new spot buys if futures available margin is below emergency reserve.
5. Surface Binance Futures wallet/reserve status in the wallets page.
6. Log expected hedge notional, futures collateral, margin usage, free margin, and liquidation buffer.
7. Keep `arbitragebot-configs.json` synchronized if config defaults/settings change, and remind the operator to import it to the VPS.

#### Conclusion

For this log, the hedge problem visible in wallets was primarily an accounting/display bug because hedging was simulation-only. The deeper live-readiness issue is real: the bot cannot safely go live with hedge execution until it manages Binance Futures collateral as part of total capital. The next feature should be a capital allocator/reserve manager, not just a hedge-order change.

#### Follow-Up Implementation: Weak-Regime Refill Policy

The inventory-starvation issue should not be solved by fully disabling the weak-regime guard. The implemented policy splits weak-hour rebalance behavior into three modes:

- `strict`: block all weak-hour rebalances, matching the legacy `regime_weak_disable_rebalance=true` behavior.
- `refill_only`: allow local/internal refills and near-free external refills while keeping expensive rebalances blocked.
- `off`: ignore the weak-regime rebalance gate and use normal ROI/net-P&L/fee-cap gates.

New settings:

- `regime_weak_rebalance_policy` default `refill_only`
- `regime_weak_refill_max_fee_usd` default `$0.10`

This lets profitable routes recover from inventory starvation during weak hours without reopening the expensive transfer churn that the original strict gate was trying to prevent.

#### Follow-Up Fix: Reserve-Aware Portfolio Basis

The `logs/bot-logs-2026-06-28-17-24-24.log` run exposed a v0.33.0 regression in the new futures-reserve model:

- `$5k` configs logged `Auto trade amount: $200.0 (4.0% of $5000.0)` even though 40% of capital was reserved for Binance Futures. Correct spot sizing is `4% of $3000 = $120`.
- Optimizer discovery logged `Symmetric 50/50 allocation, $5000 total`, then `BalanceTracker` added the `$2000` Binance Futures reserve, initializing `$7000 total`.
- Periodic snapshots showed the actual spot/hedged wallet value around `$5000`, while accounting stayed around `$7000`, producing `drift=$-2000`.

Implemented fix:

- Optimizer post-discovery allocation now subtracts `binance_futures_usdt` first and allocates only spot capital.
- Dashboard hot-apply, hourly rescale, per-config rescale, and settings logs now use reserve-aware spot capital for percentage trade sizing.
- Dashboard portfolio accounting clamps stale over-inflated `_initial_investment` basis created by the bad v0.33.0 run, while keeping normal `initial + realized P&L` behavior intact.

Validation:

- `python3 -m py_compile optimizer.py dashboard_server.py orchestrator.py balance.py`
- `./.venv/bin/python -m py_compile optimizer.py dashboard_server.py orchestrator.py balance.py`
- `git diff --check`

### Session #30 — 2026-06-29 (v0.33.1-beta, Binance Futures testnet hedge parser fix)

#### Context

This session documents the investigation around `logs/bot-logs-2026-06-29-02-45-32.log`.

The operator confirmed the previous reserve-aware portfolio fix was finally working: `$5k` configs were no longer initialized around `$7k`, and trade sizing was based on spot capital after reserving Binance Futures collateral.

Examples from the log:

- `version=v0.33.1-beta`
- `Group 1 / Neutral (Baseline)`: `trade_amount=$24.0 (4.0% of $600 spot, $400 futures, $1000 total)`
- `Group 5 / Neutral (Baseline)`: `trade_amount=$120.0 (4.0% of $3000 spot, $2000 futures, $5000 total)`
- All hedged configs logged the intended futures reserve policy: `target=40%, topup=35%, emergency=30%, overflow=45%, transfer_min=$10`

So the old wrong-portfolio basis issue was not the active failure in this run.

#### Log Summary

| Metric | Value |
|---|---:|
| Log file | `logs/bot-logs-2026-06-29-02-45-32.log` |
| Runtime window | 2026-06-28 19:02:43 -> 2026-06-29 02:44:34 |
| Version | `v0.33.1-beta` |
| Total warnings | 1,872 |
| Total errors | 4,504 |
| Config with real/testnet hedge mode | `Group 1: $1k — Architecture & Exchange Ablations / Neutral (Baseline)` |
| Testnet hedge mode line | `hedging: enabled=True, mode=testnet, dust=$10, eval_interval=60s, leverage=2x, margin_buffer=20%, adjust_threshold=1%` |
| `hedge_evaluate` parser errors | 458 |
| `hedge_reserve_refresh_before_trade` parser errors | 4,032 |
| `futures_reserve_unknown` trade blocks | 38 |
| `futures_reserve_unavailable` trade blocks | 30 |

#### Main Failure

The repeated failure was:

`ValueError("could not convert string to float: ''")`

It appeared in two async monitor tasks:

- `hedge_evaluate`
- `hedge_reserve_refresh_before_trade`

The first error arrived immediately after the testnet config started:

- Settings line: `mode=testnet`
- First error: `Async hedge_evaluate failed: ValueError("could not convert string to float: ''")`
- First reserve block: `SPOT_TRADE_BLOCKED ... futures_reserve_unknown`

The same error was still present at the end of the log:

`2026-06-29 02:44:34 ... Async hedge_reserve_refresh_before_trade failed: ValueError("could not convert string to float: ''")`

#### Root Cause

The failure was not hedge sizing, not the futures-reserve percentage, and not the portfolio display fix.

Root cause: `executors/binance_futures_exec.py` directly parsed Binance Futures API fields with `float(...)` / `int(...)`. Binance Futures testnet can return empty strings for numeric response fields, especially in account/position payloads when no value is available. Known risky fields included:

- Account: `totalWalletBalance`, `totalUnrealizedProfit`, `totalMarginBalance`, `availableBalance`, `maxWithdrawAmount`
- Position: `entryPrice`, `markPrice`, `unRealizedProfit`, `isolatedWallet`, `liquidationPrice`, `leverage`
- Balance: `availableBalance`
- Order response: `executedQty`, `cumQuote`

Any blank string in those fields crashed the async hedge task before the hedge manager could classify reserve health. That left the config in `futures_reserve_unknown` / `futures_reserve_unavailable`, which then blocked spot trades that required a hedge.

#### Fix Implemented In Working Tree

Files changed:

- `executors/binance_futures_exec.py`
- `hedge_manager.py`

Executor changes:

- Added `_to_float`, `_to_int`, and `_number_with_fallback` helpers.
- Replaced direct Binance response parsing with safe coercion.
- `get_account_info()` now falls back to the USDT asset row when top-level futures account fields are blank.
- `get_position()` and `get_all_positions()` now safely parse blank position fields, including blank `liquidationPrice`.
- Position dictionaries now include both `size` and `positionAmt` for compatibility.
- `get_balance()` and order response parsing now tolerate blank numeric fields.
- Exchange filter parsing now tolerates blank/invalid precision and filter values.

Hedge manager changes:

- Added local `_to_float` and `_reserve_numbers` helpers so reserve status parsing remains robust even if a mock/future executor returns strings.
- `refresh_reserve_status()` now consumes reserve numbers through the helper instead of direct `float(...)`.
- Reconciliation now safely reads real position `size`, `entry_price`, and `mark_price`.
- `close_all_real_positions()` now reads executor `size` as well as legacy `positionAmt`; this fixes an adjacent cleanup bug where orphan futures positions could be missed because the executor returns `size`.

#### Validation

Commands run:

- `python3 -m py_compile executors/binance_futures_exec.py hedge_manager.py`
- `.venv/bin/python -m py_compile executors/binance_futures_exec.py hedge_manager.py`
- `git diff --check`
- Mocked Binance Futures account response with empty strings for all top-level account fields and valid USDT asset fallback.
- Mocked Binance Futures position response with blank `entryPrice`, `unRealizedProfit`, `leverage`, `isolatedWallet`, and `liquidationPrice`.
- Direct parser assertions for `""`, whitespace, `None`, normal floats, and normal ints.

The mocked test confirmed:

- Blank account fields no longer raise.
- USDT asset fallback works.
- Blank position fields no longer raise.
- Blank leverage defaults to `1`.
- Blank liquidation price defaults to `0.0`.

Not run:

- `scripts/test_futures_executor.py`

Reason: that script places a real Binance Futures testnet market order and then closes it. It should only be run deliberately after confirming testnet credentials and intended test order size.

#### Binance Futures Testnet Credentials

For `hedge_execution_mode=testnet`, yes, Binance Futures testnet credentials are required:

- `BINANCE_FUTURES_TESTNET_API_KEY`
- `BINANCE_FUTURES_TESTNET_API_SECRET`

Without those, the testnet futures executor cannot read futures account balance, position risk, set leverage/margin type, or place/close testnet hedge orders. Simulation hedge mode does not need these credentials because it never calls Binance Futures.

Local `.env` status checked during this session without printing secret values:

| Key | Status |
|---|---|
| `BINANCE_FUTURES_TESTNET_API_KEY` | set |
| `BINANCE_FUTURES_TESTNET_API_SECRET` | set |
| `BINANCE_FUTURES_API_KEY` | empty |
| `BINANCE_FUTURES_API_SECRET` | empty |

Interpretation:

- Local testnet futures mode has credentials available.
- Local live futures mode is not configured.
- If the VPS does not have the two `BINANCE_FUTURES_TESTNET_*` keys, testnet hedge mode will not work correctly there.
- If using live futures later, separate Binance mainnet futures/API permissions are required; testnet keys do not work on mainnet.

#### Operational Conclusion

The portfolio basis/futures-reserve bug from v0.33.0 was fixed in this run. The active issue was a Binance Futures testnet API parser robustness bug.

After this fix, the next run should no longer produce:

- `Async hedge_evaluate failed: ValueError("could not convert string to float: ''")`
- `Async hedge_reserve_refresh_before_trade failed: ValueError("could not convert string to float: ''")`

If the VPS still has no Binance Futures testnet credentials, the expected next failure mode should be a structured `credentials not configured` / reserve unavailable state, not a parser crash. Add the testnet futures credentials to the VPS `.env` before expecting real testnet hedge orders.

#### Working Tree State

No commit was made in this session, following `CODEX.md`.

Uncommitted changes after Session #30:

- `executors/binance_futures_exec.py`
- `hedge_manager.py`
- `documentations/SESSIONS_2.md`

### Session #31 — 2026-06-29 (v0.34.0-beta, live-realism slippage/execution hardening)

#### Purpose

This session addressed the live-trading concern that simulation could overstate profitability by treating visible top-of-book prices as fully executable. The main risk was that a route could look profitable in simulation but lose money live because of stale order-book depth, insufficient depth, partial fills, or unbounded market-order slippage.

#### Implemented Changes

Strict slippage/depth policy:

- Added `SlippagePolicyResult` and `evaluate_slippage_policy()` in `slippage.py`.
- Missing books, insufficient visible depth, excessive per-leg slippage, and excessive total slippage now fail a structured policy gate.
- The slippage walker now sums all visible book depth even after the requested fill size is satisfied. This allows depth buffers such as `1.25x` to work correctly.
- Scoring and execution both use the same strict policy, so discovery no longer promotes symbols whose edge only exists because book depth is missing/thin.

Book-age guard:

- Added `book_received_at` to `PriceState`.
- Book-depth fetcher messages now stamp book freshness separately from ticker freshness.
- The shared tick cache carries `book_received_at` so all configs can evaluate book age without re-reading fetcher state.
- New defaults:
  - `book_age_guard_enabled=true`
  - `max_book_age_seconds=2.0`
  - `event_driven_max_book_age_seconds=15.0`
- Monitor and optimizer reject stale/missing book-depth routes before scoring/executing.

Depth-aware size shrink:

- Added `depth_aware_trade_size_shrink_enabled=true`.
- When adaptive sizing picks a size too large for visible depth, monitor can shrink the trade to the largest depth-safe size instead of skipping the opportunity outright.
- `min_depth_shrink_ratio=0.5` prevents shrinking normal trades into dust.
- Shrink events are logged as throttled `[Trade] DEPTH_SHRINK ...` entries and summarized in session/dashboard counters.

Marketable-limit execution:

- Normal demo/testnet spot legs now default to `spot_execution_order_mode=marketable_limit_fok`.
- Binance, OKX, and Bybit demo executors support capped marketable limit IOC/FOK orders.
- Buy caps are rounded up to exchange tick size; sell floors are rounded down. This avoids false buy rejects caused by rounding a buy cap below the observed ask.
- Emergency one-leg recovery still uses market orders because getting flat is more important than price-capping an emergency unwind.

Controlled one-leg drill:

- Added disabled-by-default demo/testnet drill settings:
  - `demo_one_leg_drill_enabled=false`
  - `demo_one_leg_drill_every_n=0`
  - `demo_one_leg_drill_side=alternate`
- When deliberately enabled, DemoExecutor forces exactly one leg to fail at the configured cadence, allowing the existing one-leg recovery path to be tested before live trading.
- Drill events log as `[ExecutorDrill] ...`.

Post-fill reconciliation/logging:

- Demo comparison now warns when actual buy/sell filled quantities differ materially, catching hidden inventory drift from partial fills or rounding.
- Existing demo logs already record slippage, latency, fee mismatch, rejection, partial fill, one-legged status, and profit drift.
- New guard logs are throttled by reason class, not by every symbol/route, to avoid startup floods across 46 configs.

Dashboard/config wiring:

- Added settings schema validation, hot-apply, startup sync, settings snapshot logging, TypeScript types, config editor fields, dashboard payload counters, and XLSX export fields for the new guards.
- Updated `settings.json` and gitignored `arbitragebot-configs.json` across all 46 configs.
- Operator action required: import the updated `arbitragebot-configs.json` to the VPS before expecting the VPS to use the new settings.

#### New Runtime Diagnostics

Per-route logs are throttled; aggregate counters are exact.

- `[Trade] SLIPPAGE_GUARD_SKIP reason=... sample=... count=...`
- `[Trade] BOOK_AGE_SKIP reason=... sample=... count=...`
- `[Trade] DEPTH_SHRINK ...`
- `[Session] realism_diag: slippage_top=[...] book_age_top=[...] depth_shrink_top=[...] settings=...`
- `[ExecutorDrill] Forcing ... leg failure ...`
- `[DemoCompare] ... fill quantity mismatch ...`
- `[Session] ... slip_guard=... book_age=... depth_shrink=...`
- `[Hedge] BNB_RESERVE_STATUS ...`
- `[Balance] BNB_RESERVE_SELL_BLOCK ...`
- `[DemoTrade] PROTECTED_SELL_CAP ...`

BNB-specific diagnostics added after the first pass:

- Binance `BNBUSDT` sell capacity now protects the configured Spot BNB fee floor.
- The hedge manager logs Spot/Futures BNB reserve health on status changes and then at most every five minutes.
- The monitor persists representative slippage/book-age/depth-shrink samples and emits a five-minute `realism_diag` aggregate line.
- Dashboard payload and XLSX export now include top slippage/book-age/depth diagnostics.

#### Follow-up Robustness Fixes

After reviewing the full uncommitted live-realism work set, several edge cases were tightened before handing the branch back:

- Real/testnet spot trades now block on stale hedge-reserve status and schedule a throttled refresh instead of trusting an old futures reserve snapshot.
- `topup_needed` in real/testnet futures reserve status now blocks new spot exposure. The bot should not keep opening spot inventory when Binance Futures needs more collateral.
- Demo one-leg recovery now updates demo inventory after the emergency unwind and includes recovery cashflow in `actual_profit_usd`.
- Demo/testnet fee accounting now uses USD-valued token fees, including Binance BNB fee deductions, so reported actual P&L is not optimistic when fees are paid outside USDT.
- Binance token-fee discount now falls back to the non-token taker fee model when the BNB reserve is insufficient to pay the fee.
- BNB reserve protection was extended beyond normal arbitrage sells to automatic USDT refill, crypto refill, inventory-drift rebalance, and idle consolidation paths.
- The hedge reserve refresh scheduling is throttled to avoid spawning duplicate refresh tasks when many profitable routes are evaluated in the same tick.

#### Remaining Caveats

- Full live spot execution is still not implemented for all nine exchanges. The project currently has demo/testnet spot executors for Binance, OKX, and Bybit only.
- FOK reduces partial-fill risk but increases rejects. IOC can be selected if the operator wants fewer rejects at the cost of possible partial fills.
- Book age is now measured from depth messages, but exchange-side latency and matching-engine queue movement can still make the book worse after order submission.
- Two-leg arbitrage is not atomic. One-leg failure remains a real live risk even with FOK.
- Event-driven exchange book age uses a looser default because quiet books can be valid; this is safer than treating ticker freshness as book freshness, but still needs calibration from demo/live observations.

#### Validation

Commands run:

- `python3 -m py_compile config.py settings.py slippage.py monitor.py optimizer.py executor.py tick_cache.py dashboard_server.py orchestrator.py run.py balance.py hedge_manager.py fetchers/base.py fetchers/binance.py fetchers/okx.py fetchers/bybit.py fetchers/bitget.py fetchers/kucoin.py fetchers/gateio.py fetchers/pionex.py fetchers/mexc.py fetchers/bitfinex.py executors/binance_exec.py executors/binance_futures_exec.py executors/okx_exec.py executors/bybit_exec.py`
- `npm run build`
- `git diff --check`
- BNB reserve smoke test: Binance `BNBUSDT` sells are blocked when they would consume the configured Spot BNB reserve.
- Token-fee fallback smoke test: Binance BNB-fee model falls back to non-token fees when available BNB cannot cover the token fee.
- Executor cashflow smoke test: non-USDT token fees are converted into USD-valued cashflow for actual P&L.
- Structured JSON validation confirmed all 46 configs in `settings.json` and `arbitragebot-configs.json` contain the new strict slippage, FOK execution, book-age, depth-shrink, and disabled one-leg drill settings.

Result:

- Python compilation passed.
- Dashboard production build passed.
- `git diff --check` passed; it only reported Git's existing CRLF warning for `slippage.py`.
- Targeted BNB reserve, fee fallback, and executor cashflow smoke tests passed.
- Config export validation passed.

#### Working Tree State

Released as `v0.34.0-beta` after the operator explicitly requested commits and tagging.

### Session #32 — 2026-07-01 (v0.34.1-beta, 30-config realism-guard audit)

#### Purpose

This session audited `logs/bot-logs-2026-07-01-02-04-46.log` after the v0.34.x live-realism work and the later v0.34.1 transfer-fee/P&L fixes. The main question was whether the new 30-config set was behaving normally, and whether the log showed remaining issues before the next tuning/fix pass.

The log covered approximately:

- Start: `2026-06-30 02:48:30`
- End: `2026-07-01 02:04:14`
- Duration: about 23h16m
- Config count: 30
- No `No space left on device` errors
- No Python traceback

#### Aggregate Result

Latest session aggregate across the 30 configs:

- Trades: 374
- Gross simulated trade P&L: `+$14.21`
- Transfer fees: `$31.97`
- Net after transfer fees: `-$13.94`
- `sz0` skips: 8,344,704
- Rebalance blocked: 305,663
- Phantom blocked: 75,342
- Slippage guard skips: 3,928,107
- Book-age skips: 4,320,066

Trade concentration was very high:

- `GRTUSDT`: 358 trades
- `ALGOUSDT`: 10 trades
- `ORDIUSDT`: 6 trades

This means the current profitable-opportunity surface is narrow. The bot is mostly trading one symbol and rejecting most other routes under the stricter book/slippage realism rules.

#### Positive Configs

Only a small set of configs ended net-positive after transfer fees:

| Config | Trades | P&L | Fees | Net |
|---|---:|---:|---:|---:|
| Group 1 / Conservative | 38 | `$1.14` | `$0.85` | `+$0.44` |
| Group 2 / Small | 62 | `$2.29` | `$1.91` | `+$0.79` |
| Group 2 / Medium-Neutral | 56 | `$3.01` | `$1.73` | `+$1.80` |
| Group 5 / Aggressive Rapid Shifts | 60 | `$3.88` | `$2.61` | `+$3.18` |

Several configs had zero or very few trades but still ended negative because transfer/rebalance fees were charged without enough realized trading edge to pay them back.

Worst examples:

| Config | Trades | P&L | Fees | Net |
|---|---:|---:|---:|---:|
| Group 3 / Short Scoring Window | 2 | `$0.03` | `$2.85` | `-$2.79` |
| Group 4 / Diverse | 0 | `$0.00` | `$2.54` | `-$2.54` |
| Group 3 / Loose Stability | 0 | `$0.00` | `$2.54` | `-$2.54` |
| Group 3 / Aggressive Scoring | 0 | `$0.00` | `$2.38` | `-$2.38` |

#### Main Issues Found

Strict realism guards are dominating the run.

- `SLIPPAGE_GUARD_SKIP`: 41,835 log groups, 3.9M aggregate skips in session counters.
- `BOOK_AGE_SKIP`: 4.3M aggregate skips.
- This is expected after v0.34.0 in the sense that bad/slippery/stale opportunities are now rejected instead of being counted as fake profit.
- However, the practical result is very low opportunity density and symbol concentration. The strategy currently depends heavily on a few symbols, mostly `GRTUSDT`.

Binance Futures account polling still hit a rate-limit ban.

- The log contains Binance Futures `Way too many requests` / IP banned behavior.
- The hedge reserve/account-info path backed off for about 1,449 seconds after the rate limit.
- This means account-info polling is still too aggressive or not globally shared enough across configs.
- This must be fixed before live mode; hedge reserve state should be cached/throttled globally and refreshed via a single owner rather than repeatedly per config.

Demo comparison is still active and noisy during forced simulation.

- `DemoCompare` appeared 880 times.
- Discrepancy categories included active discrepancies, balance mismatches, and extra demo positions.
- Example near the end: Binance demo held a `GRTUSDT` position of roughly `$232`, while the simulation did not reflect that position.
- If the current run is meant to be pure forced simulation, demo setup/comparison should be disabled or strictly separated from simulation metrics.
- The previous dashboard-only demo-mode cleanup did not fully cover this monitor/demo comparison path.

Bitfinex symbol handling is still noisy.

- 172 Bitfinex invalid-subscription warnings appeared.
- Many currently selected symbols are not valid on Bitfinex or still have mapping/support problems.
- This wastes setup work and creates noisy logs. Bitfinex should pre-filter unsupported symbols before websocket subscription and before route scoring.

Sweep capacity is borderline.

- 90 capacity warnings appeared.
- Latest capacity line near the end: average sweep `1574ms`, p95 `1831ms`, budget `1500ms`.
- Max observed average sweep was about `2017ms`; max p95 was about `2396ms`.
- Heap was high but not a disk issue: latest heap around `1575MB`, with about `1.88M` `SymbolTick` objects.
- Current 1 vCPU / 2 GB VPS can run this but is close to the edge for 30 configs with strict book/depth processing.

Discovery and inventory still struggle.

- `NO tradeable symbols`: 491 occurrences.
- `All symbols demoted`: 84 occurrences.
- `rebalance FAILED`: 21 occurrences, mostly OKX, Binance, and Bybit.
- `REALIZED_NET_SKIP`: 71 occurrences, which means the new realized-net guard is working.
- These point to the same practical issue: strict realism rules protect against fake profit, but the current thresholds and inventory/rebalance regime leave many configs unable to trade.

BNB auto-reserve top-up needs better wallet-awareness.

- `SIM_SPOT_BNB_BUY_FAILED ... binance_usdt_unavailable` appeared 6 times.
- This means the BNB auto-buy/top-up logic can still try to buy BNB in configs where Binance has no local USDT available.
- The top-up path should either reserve/route USDT to Binance first or skip cleanly with a clearer reason and no repeated attempts.

Rotation budget still appears inconsistent in logs/code.

- The log still includes `Rotation gate CLOSED ... using ext-only fees`.
- The v0.34.1 rebalance/P&L direction was to use all transfer fees for realized profitability, not only external fees.
- Rotation/consolidation gating should be audited to ensure it uses `total_transfer_fees`, or the log text should be corrected if the implementation is already using the right value.

One-leg drill/simulation was active.

- `ONE_LEG_SIM` appeared 7 times.
- This is useful when deliberately testing one-leg recovery.
- It adds noise if the operator is trying to measure normal profitability.

Transient exchange websocket/API errors appeared.

- 27 error lines were found, mostly exchange websocket/opening-handshake failures.
- Bybit had transient connection errors, including HTTP 502.
- OKX, Bitget, KuCoin, MEXC, and Pionex also had smaller transient fetcher/task failures.
- These did not crash the bot and looked recoverable, but they contribute to stale books and guard skips.

#### Operational Interpretation

The v0.34.x realism work is doing its job: the bot is no longer accepting routes that only look profitable because of missing depth, stale books, or ignored slippage.

The downside is now visible: once the fake opportunities are removed, the remaining strategy has low edge density. It traded 374 times in roughly 23 hours across 30 configs, produced only `$14.21` gross simulated P&L, and lost money after transfer fees. This is a better and more honest failure mode than fake profit, but it means the current configuration set is not ready for live trading.

This log does not show the old disk-full problem, nor the old portfolio-display hedge inflation problem. The active blockers are now profitability quality, account-info rate limiting, Bitfinex symbol filtering, demo/simulation separation, and transfer/rebalance cost control.

#### Recommended Next Fixes

Priority fixes before another serious run:

1. Add a single global Binance Futures reserve/account-info cache with strict request throttling and shared state across all configs.
2. Disable or isolate DemoCompare during forced simulation so simulation metrics are not polluted by old demo positions.
3. Pre-filter Bitfinex unsupported symbols before subscription/scoring.
4. Audit rotation/consolidation budget logic and align it with `total_transfer_fees`.
5. Tune configs around the actually positive families: Group 1 Conservative, Group 2 Small/Medium-Neutral, and Group 5 Aggressive Rapid Shifts.
6. Reduce transfer/rebalance churn for configs that are not producing enough realized edge.
7. Add BNB top-up wallet-awareness so Binance BNB buying does not repeatedly fail when local Binance USDT is unavailable.

#### Follow-Up Fixes Implemented

Implemented after the log audit as `v0.34.2-beta`:

- Fixed Bybit v5 depth handling to preserve snapshot state and merge deltas.
- Increased Binance depth from 5 to 20 levels and fixed MEXC sub-fetcher depth-state propagation.
- Split realism diagnostics so true slippage, missing books, visible-depth insufficiency, and stale books are counted separately.
- Added depth-aware trade-size shrinking before rejecting routes for insufficient visible depth.
- Added a short Binance Futures account-info cache to reduce account-summary rate-limit pressure.
- Disabled demo comparison polling/output during multi-config forced simulation.
- Filtered Bitfinex subscriptions to exchange-info supported symbols and fixed Bitfinex two-character base formatting.
- Changed rotation gating to use all transfer fees, matching the displayed net P&L basis.
- Made simulated BNB spot reserve buying skip cleanly when Binance spot USDT is unavailable.
- Throttled repeated unstable-candidate rejection logs.

#### Working Tree State

The audit notes were written first, then the follow-up fixes above were implemented and prepared for release as `v0.34.2-beta`.
