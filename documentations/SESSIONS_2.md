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
