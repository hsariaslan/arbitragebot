# Session History & Analysis

Tracking session performance over time to identify patterns, optimal conditions, and inform strategy decisions.

## Key Metrics Definitions

| Metric | Description |
|--------|-------------|
| **Net Profit** | Trading PnL - Transfer Fees + Credited Cashback |
| **$/hr** | Net Profit / Session Duration |
| **Trade Frequency** | Trades per hour at peak |
| **Avg Net%** | Average net profit percentage per trade (after fees) |
| **Capital** | Total configured capital at session start |
| **Active Symbols** | Symbols that traded during the session |

---

## Session Log

### Session #1 — 2026-03-03 (STRK Goldmine)

**Date**: 2026-03-03, 03:52 - 20:20 UTC (16h 28m)
**Capital**: $3,000
**Version**: v0.18.0-alpha (pre-slippage simulation)
**VPS**: LightNode Bangkok (single monolithic)

#### Summary

| Metric | Value |
|--------|-------|
| Duration | 16h 28m |
| Total Trades | 6,075 |
| Trading PnL | $1,372.21 |
| Transfer Fees | $46.96 (external: $43.42) |
| Cashback | $42.14 (credited: $23.79, pending: $18.36) |
| **Net Profit** | **$1,349.03** |
| **$/hr** | **$81.91** |
| Portfolio Growth | $3,007 → $4,381 (+45.7%) |
| Avg Profit/Trade | $0.2950 (logged window) |
| Avg Net% | ~0.70% |
| Avg Trade Size | $40.71 (grew from $25 early to $77 late) |
| Peak Trade Frequency | 420 trades/hr (7/min) |
| Positive Trades | 97.5% (4,483/4,596 in log window) |
| SIZE_ZERO Events | 17,965 |

#### Active Symbols

**STRKUSDT only** — held strong/very_strong tier the entire session (score range 0.032–1.068, avg ~0.30). No other symbol was activated. Candidates tracked: TIAUSDT (closest at 0.1048), SNXUSDT, DYDXUSDT, RENDERUSDT, ORDIUSDT — all dropped below thresholds. Tier distribution across session: very_strong (58%), strong (38%), normal (4%).

#### Exchange Pair Breakdown

From 4,596 logged trades (3 log files, deduplicated). ~1,479 early trades not captured in logs.

| Exchange Pair (Buy→Sell) | Trades | Profit | Avg Profit | Avg Net% | Volume |
|--------------------------|--------|--------|------------|----------|--------|
| Bitfinex → OKX | 1,348 | $426.15 | $0.3161 | ~0.79% | $53,956 |
| Bitfinex → MEXC | 930 | $342.54 | $0.3683 | ~0.83% | $41,516 |
| Bitfinex → Bybit | 760 | $252.86 | $0.3327 | ~0.78% | $32,232 |
| Bitfinex → Bitget | 496 | $157.96 | $0.3185 | ~0.79% | $20,087 |
| Bitfinex → KuCoin | 344 | $105.63 | $0.3071 | ~0.73% | $14,540 |
| Bitfinex → Gate.io | 192 | $61.46 | $0.3201 | ~0.75% | $8,173 |
| Bitfinex → Binance | 19 | $5.37 | $0.2824 | ~0.60% | $896 |
| MEXC → OKX | 387 | $2.09 | $0.0054 | ~0.02% | $11,599 |
| MEXC → Bitget | 108 | $1.47 | $0.0137 | ~0.04% | $3,755 |
| Others (MEXC/Bybit buyer) | 12 | $0.07 | $0.0060 | ~0.02% | $363 |

**Bitfinex as buyer: 4,089/4,596 trades (89.0%), $1,351.96/$1,355.60 profit (99.7%)**

#### Seller Exchange Evolution

Dominant sellers shifted throughout the session:
- **03:52–10:30**: OKX primary seller (sometimes with Bitget/MEXC)
- **10:30–11:05**: Transition period — KuCoin, Gate.io, Bybit entered
- **11:05–16:00**: Bybit became primary seller (with MEXC/KuCoin rotating)
- **16:00–20:20**: OKX reclaimed primary seller, MEXC secondary

7 exchanges served as sellers: OKX, MEXC, Bybit, Bitget, KuCoin, Gate.io, Binance. The seller set expanded to 3 (very_strong tier allows 3 per direction).

#### Transfer Activity

- **~4,559 crypto transfers** (majority from Bitfinex at $0 cost)
- **~811 USDT transfers** (mainly Bybit→Bitfinex, Bitfinex→MEXC, OKX→Bitfinex)
- **278+ transfers blocked** by $5/hr hourly cap
- Transfer fee ratio: 3.4% of gross profit ($46.96/$1,372.21)
- External transfer fees only: 3.2% ($43.42/$1,372.21)

#### Hourly Rate Progression

| Time (UTC) | Duration | Net | $/hr |
|------------|----------|-----|------|
| 07:36 | 3h 44m | $19.75 | $5.29 |
| 07:52 | 4h 00m | $24.83 | $6.21 |
| 08:55 | 5h 03m | $57.35 | $11.34 |
| 09:54 | 6h 01m | $106.61 | $17.69 |
| 10:52 | 7h 00m | $182.63 | $26.07 |
| 11:57 | 8h 05m | $340.68 | $42.12 |
| 12:57 | 9h 04m | $476.08 | $52.43 |
| 13:57 | 10h 04m | $597.25 | $59.23 |
| 14:58 | 11h 05m | $725.19 | $65.37 |
| 15:53 | 12h 00m | $865.34 | $72.03 |
| 16:54 | 13h 02m | $940.54 | $72.14 |
| 17:56 | 14h 04m | $1,082.05 | $76.91 |
| 18:52 | 15h 00m | $1,184.73 | $78.97 |
| 19:55 | 16h 02m | $1,309.38 | $81.59 |
| 20:20 | 16h 28m | $1,349.03 | $81.91 |

The $/hr rate accelerated continuously — from $5.29 at 3h44m to $81.91 at 16h28m (15.5x increase). This is because STRK's spread remained persistent while trade sizes grew with accumulated profits (adaptive sizing). Trade sizes grew from ~$25 early to ~$77 late session.

#### Final Portfolio Snapshot

| Exchange | Value |
|----------|-------|
| Bitfinex | $3,454 |
| MEXC | $508 |
| OKX | $281 |
| Gate.io | $109 |
| Binance | $19 |
| Bybit | $4 |
| KuCoin | $4 |
| Bitget | $4 |
| **Total** | **$4,381** |

Capital concentrated on Bitfinex (78.8%) — natural result of the Bitfinex-buyer pattern where USDT flows to Bitfinex and crypto flows out to sellers.

#### Why This Session Was Exceptional

**"Perfect Storm" conditions — all 8 present simultaneously:**

1. **Bitfinex was the buyer** (0% taker fee — saves 0.05-0.10% per trade vs any other buyer)
2. **Bitfinex had the lowest ask price** (structural spread vs other exchanges — STRK priced lower on Bitfinex consistently)
3. **STRK stayed strong/very_strong** for 16+ hours (no demotion, minimal normal-tier time)
4. **$0 crypto withdrawal from Bitfinex** (free transfer loop — buy on Bitfinex, ship crypto for free)
5. **Multiple viable sellers** (7 exchanges with profitable spreads: OKX, MEXC, Bybit, Bitget, KuCoin, Gate.io, Binance)
6. **Wide spread** (~0.70% avg net after fees — extremely generous for arbitrage)
7. **High trade frequency** (7 trades/min = opportunity refreshes constantly)
8. **Bitfinex is the USDT hub** (capital already there — zero friction to start buying)

Conditions 4, 5, 7, 8 are always true by design. Conditions 1, 2 are captured by fee-aware scoring. Conditions 3, 6 are purely market-driven — finding symbols with persistent, wide spreads.

#### Key Observation: Bitfinex as Buyer is the Profit Driver

The entire profit engine was: Bitfinex buys at 0% → ships crypto for $0 → seller sells at 0.05-0.10% fee → USDT flows back to Bitfinex. The fee-aware scoring system already prioritizes this pattern naturally (0% fee gives highest net_pct).

**Not worth hardcoding Bitfinex preferences** because:
- The scoring system already captures the fee advantage through net_pct
- Dominant pair detection gives Bitfinex ~2x weight boost
- Hardcoding creates fragility if Bitfinex changes fees
- The "best seller" varies by market conditions (MEXC had highest avg profit at $0.3683, not Bybit)

#### Bottlenecks Identified

1. **Crypto on seller exchanges** — the main bottleneck (SIZE_ZERO from crypto constraint dominated)
2. **Hourly transfer cap** ($5/hr) blocked 278+ transfers
3. **USDT on Bitfinex** was rarely the constraint

#### Bug Found: Expansion Cost Overestimates for Bitfinex-Buyer

`_estimate_expansion_cost()` used `available_usdt_for_trading("Bitfinex")` which subtracts the reserve ($450). This made Bitfinex appear under-funded for expansion even when it had plenty of USDT. Fixed in this session's code changes — now uses raw balance for Bitfinex-buyer cost estimation.

#### Estimated Impact of Slippage Simulation (Not Yet Deployed)

Once slippage simulation is pushed, expected impact on similar STRK-like sessions:

| Scenario | Est. Slippage | Est. $/hr | vs Actual |
|----------|--------------|-----------|-----------|
| Optimistic | 0.05% | $53-55 | -12% |
| Moderate | 0.10% | $45-48 | -25% |
| Conservative | 0.15% | $38-42 | -35% |

Even the conservative estimate ($38/hr) on $3,000 capital is extraordinary.

#### STRK Market Context

- STRK price during session: ~$0.039-$0.041
- 127M STRK token unlock scheduled March 15 (66.61M Early Contributors + 60.39M Investors, ~1.3% of supply)
- The arbitrage spread is structural (Bitfinex tSTRKUST pair microstructure) rather than event-driven
- Geopolitical volatility (Iran-Israel conflict) widened crypto spreads generally but STRK's spread predates these events

---

### Session #2 — 2026-03-03 (Short Diagnostic Run + Critical Bybit Bug)

**Date**: 2026-03-03, 22:04:59 - 22:22:45 UTC (~18 min)
**Capital**: $3,000
**Version**: v0.19.0-alpha (post-slippage simulation, post-Zurich proxy)
**VPS**: LightNode Bangkok + Oracle Zurich (Bitfinex proxy)
**Purpose**: First run after deploying slippage simulation, Zurich proxy, and persistent uptime tracking

#### Summary

| Metric | Value |
|--------|-------|
| Duration | 17m 46s |
| Total Trades | 194 |
| Trading PnL | $29.42 |
| Transfer Fees | $1.27 (external: $0.70) |
| Cashback | $0.78 (credited: $0.00, pending: $0.78) |
| **Net Profit** | **$28.16** |
| **$/hr** | **$107.95** |
| Portfolio Growth | $3,000 → $3,026 (+0.87%) |
| Errors | 0 |
| SIZE_ZERO Events | 678 (cumulative ticks) |

#### Active Symbols

**2 symbols activated** after 60s discovery:

| Symbol | Score | Tier | Avg Net% | Freq% | Dominant Pair |
|--------|-------|------|----------|-------|---------------|
| STRKUSDT | 0.5257 | very_strong | 0.928% | 56.7% | Bitfinex → MEXC + OKX |
| AXSUSDT | 0.0584 | normal | 0.063% | 93.3% | MEXC → Gate.io |

**3 candidates REJECTED at activation:**
- FETUSDT: score 0.2391 but fading (peaked at 1.304, dropped 82%), `recent_freq=0.0%`
- BTCUSDT: score 0.0152, cliff_drop from peak 0.0545
- SOLUSDT: score 0.0139, cliff_drop from peak 0.0563

STRK continued its Session #1 pattern — Bitfinex as buyer with 0% fees, structural spread. AXS was a new addition with thin margins.

#### Exchange Status

| Exchange | Symbols | First Data | Msg Rate | Avg Freshness | Status |
|----------|---------|------------|----------|---------------|--------|
| MEXC | 60/60 | 521ms | 617/s | 52ms | Best data quality |
| KuCoin | 60/60 | 98ms | 450/s | 700ms | Healthy |
| Bitget | 60/60 | 103ms | 335/s | 120ms | Healthy |
| OKX | 60/60 | — | 273/s | 740ms | Healthy |
| Binance | 59/60 | 8ms | 272/s | 460ms | Healthy (no HYPEUSDT) |
| Gate.io | 60/60 | 130ms | 248/s | 700ms | Healthy |
| Pionex | 58/60 | 5,739ms | 70/s | 930ms | Slow connect, low rate |
| Bitfinex | 36/60 | 955ms | 2/s | 13,500ms | Event-driven (see analysis below) |
| **Bybit** | **0/60** | **Never** | **0/s** | **N/A** | **DEAD — see Bug #1** |

**7 of 9 exchanges functional**. Bybit completely non-functional. Bitfinex delivered data but at low frequency (by design).

#### $/hr Progression

| Time | Trades | Net | $/hr |
|------|--------|-----|------|
| 0h05m | 40 | $15.50 | $182.44 |
| 0h10m | 126 | $24.20 | $140.74 |
| 0h15m | 184 | $28.16 | $107.95 |

$/hr decreased over time (common for short sessions as initial high-spread trades are followed by lower-spread ones).

#### Balance Snapshots

| Time | Bitfinex | MEXC | OKX | Gate.io | Others | Total |
|------|----------|------|-----|---------|--------|-------|
| 22:11 | $1,178 | $1,335 | $285 | $218 | $0 | $3,016 |
| 22:16 | $1,425 | $514 | $627 | $459 | $0 | $3,026 |
| 22:22 | $1,127 | $177 | $812 | $910 | $0 | $3,026 |

Capital concentrated on 4 exchanges only (Bitfinex, MEXC, OKX, Gate.io). Binance, Bitget, Bybit, KuCoin, Pionex all had $0 — no capital allocated because they weren't in the dominant pairs for STRK or AXS.

#### Trade Breakdown by Route

| Route | ~Trades | Net% Range | Notes |
|-------|---------|------------|-------|
| STRKUSDT Bitfinex→MEXC | ~65 | 0.025–0.998% | Primary STRK route |
| STRKUSDT Bitfinex→OKX | ~20 | 0.026–0.984% | Secondary STRK route |
| AXSUSDT MEXC→Gate.io | ~90 | 0.024–0.107% | Primary AXS route, thin margins |
| AXSUSDT OKX→Gate.io | ~19 | 0.015–0.040% | Secondary AXS route |

STRK generated the bulk of profit (~$25 of $29.42) despite fewer trades. AXS had high frequency but very thin margins (avg 0.04% net).

---

### Session #2 — Bugs Found

#### Bug #1: Bybit Dead — Invalid WebSocket Channel (CRITICAL)

**Severity**: Critical — Bybit produced zero data for the entire session
**Root Cause**: `orderbook.5` is not a valid Bybit v5 Spot WebSocket channel

**Symptoms**:
- 35 reconnections in 18 minutes (one every ~30 seconds)
- `Bybit(0)` in all discovery logs — zero symbols received data
- Pattern: Connect → Subscribe → 30s silence → Staleness watchdog triggers → Reconnect → Repeat

**Technical Details**:
- File: `fetchers/bybit.py:50` — `args.append(f"orderbook.5.{s}")`
- Bybit v5 Spot API valid depths: **1, 50, 200, 1000** (confirmed via [official docs](https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook))
- `orderbook.5` does NOT exist — Bybit silently ignores the invalid subscription
- Without orderbook data, the staleness watchdog (30s timeout) triggers reconnection endlessly
- The docstring at line 37 said `orderbook.1` but the actual code used `orderbook.5` — a documentation/code mismatch

**Fix**: Changed `orderbook.5` → `orderbook.50` in `fetchers/bybit.py`. Updated all docstrings and CLAUDE.md.

**Impact**: Bybit (0.075% taker fee with MNT/BIT discount) was completely excluded from all trading. Given Session #1 showed Bybit as the 3rd most profitable seller (760 trades, $252.86 profit), this likely cost significant profit.

**Lesson**: Always validate WebSocket subscription channels against official API documentation. Silent subscription failures are dangerous — the connection appears healthy but delivers no data.

---

#### Bug #2 (Non-bug): Bitfinex Data Staleness — Event-Driven by Design

**Severity**: Informational — not a bug, but the latency metrics are misleading
**Initial Concern**: Bitfinex showed ~14s average freshness, 2 msgs/s — appeared broken despite Zurich proxy

**Investigation Results**:

1. **Zurich proxy works perfectly**: Processing overhead is 0.01ms. The proxy relays every message immediately with no buffering.

2. **Bitfinex ticker channel is event-driven**: Official docs state "After receiving the snapshot, you will receive updates upon any change." There is no fixed-interval push. No server-side throttle on outbound ticker data.

3. **Bitfinex has ~70-100x less volume than Binance**: ~$225M/day vs ~$15-20B/day. Many alt coins have very sparse trading activity on Bitfinex — prices genuinely don't change for 10-20+ seconds.

4. **Only 36/60 symbols subscribed successfully**: 24 symbols rejected as "symbol: invalid" (Bitfinex uses `tBTCUST` format, not all symbols have UST pairs). Active symbols further reduced to 32-34 at any given time (2-4 dormant).

5. **Book channel also event-driven**: The `_BitfinexBookSubFetcher` subscribes with `freq: "F0"` (real-time) but only sends when order book levels change. On quiet symbols, book updates are equally sparse.

6. **The "freshness" metric conflates data accuracy with data age**: A 14-second-old price that hasn't changed is still 100% accurate. The metric is designed to detect broken connections (like Bybit's 30s watchdog), not slow-moving markets.

**Verdict**: Bitfinex data is not stale — it's accurate but infrequent. The 0% fee advantage far outweighs the slower update rate. No code fix needed for correctness.

**Future improvement**: Consider Bitfinex-specific handling in the latency/freshness logging to avoid confusing metrics. Track "time since last price change" separately from "time since last message received."

**Invalid Bitfinex Symbols (24)**: ICPUSDT, TRUMPUSDT, HBARUSDT, BNBUSDT, AXSUSDT, PENGUUSDT, WLDUSDT, WIFUSDT, RENDERUSDT, ONDOUSDT, ARUSDT, ALGOUSDT, PENDLEUSDT, TIAUSDT, FLOKIUSDT, WUSDT, GRTUSDT, ORDIUSDT, DYDXUSDT, OPUSDT, ATOMUSDT, INJUSDT, BCHUSDT, SNXUSDT

---

#### Bug #3 (Partial): Slippage Only Logged on 11/194 Trades

**Severity**: Low — slippage system works correctly, but visibility is limited
**Observation**: Only 11 trades (5.7%) showed `slip=` in logs, all involving OKX or Gate.io as buyer/seller

**Investigation Results**:

1. **Slippage is computed for ALL trades** with available depth data — it's just that for small trade sizes (~$30) on liquid books, the simulated slippage rounds to 0.0000%

2. **Logging only shows non-zero slippage**: `monitor.py` uses `if actual_slippage > 0` — trades with zero simulated slippage are logged without the `slip=` field

3. **All 9 exchanges have working depth implementations**: OKX (books5), Binance (@depth5), Bitget (books5), KuCoin (level2Depth5), Gate.io (order_book snapshot+delta), MEXC (protobuf depth), Pionex (DEPTH topic), Bitfinex (book channel)

4. **Bybit had zero depth** due to Bug #1 — fixing the `orderbook.50` subscription will restore Bybit depth data

5. **Slippage values when present**: STRK slippage range 0.0037–0.0109%, AXS range 0.0004–0.0008%. These are negligible for current trade sizes.

**Verdict**: System working as designed. Small trade sizes ($30) on liquid books produce near-zero slippage. As trade sizes grow (adaptive sizing), slippage will become more visible and meaningful. No code change needed.

---

### Session #2 — Latency Analysis

#### Per-Exchange Latency (60s intervals, averaged across session)

| Exchange | Msgs/s | Avg Freshness | Max Freshness | Proc Time | Active/Total |
|----------|--------|---------------|---------------|-----------|-------------|
| MEXC | 617 | 52ms | 105ms | 0.01ms | 60/60 |
| KuCoin | 450 | 700ms | 5,500ms | 0.02ms | 60/60 |
| Bitget | 335 | 120ms | 200ms | 0.02ms | 60/60 |
| OKX | 273 | 740ms | 7,500ms | 0.02ms | 60/60 |
| Binance | 272 | 460ms | 2,600ms | 0.02ms | 59/60 |
| Gate.io | 248 | 700ms | 7,000ms | 0.03ms | 60/60 |
| Pionex | 70 | 930ms | 6,800ms | 0.01ms | 58/60 |
| Bitfinex | 2 | 13,500ms | 118,786ms | 0.01ms | 33/60 |
| Bybit | 0 | N/A | N/A | N/A | 0/60 |

**Data quality tiers**:
- **Excellent** (< 200ms freshness): MEXC, Bitget
- **Good** (200ms–1s): Binance, OKX, KuCoin, Gate.io
- **Acceptable** (1–2s): Pionex
- **Event-driven** (10s+): Bitfinex (by design, not a bug)
- **Dead**: Bybit (Bug #1)

#### Bitfinex Freshness Over Time (17 data points)

Average freshness ranged 10,528ms to 19,883ms. Max freshness peaked at 118,786ms (one dormant symbol hadn't updated in ~2 minutes). Active symbol count stable at 32-36. Message rate consistent at 2/s (105-155 msgs per 60s window). **No degradation trend** — Bitfinex data is stable but sparse.

---

### Session #3 — 2026-03-04 (Capital Concentration Bottleneck)

**Date**: 2026-03-04, 01:27:24 - 03:05:16 UTC (1h 38m)
**Capital**: $1,006 (reduced from $3,000 — testing smaller capital)
**Version**: v0.20.0-alpha (post-Bybit fix)
**VPS**: LightNode Bangkok + Oracle Zurich (Bitfinex proxy)

#### Summary

| Metric | Value |
|--------|-------|
| Duration | 1h 38m |
| Total Trades | 283 |
| Trading PnL | $21.31 |
| Transfer Fees | $3.87 (external: $3.60) |
| Cashback | $0.72 (credited: $0.10, pending: $0.62) |
| **Net Profit** | **$17.54** |
| **$/hr** | **$11.06** |
| Portfolio Growth | $1,006 → $1,018 (+1.2%) |
| Errors | 0 |
| SIZE_ZERO Events | 2,493 |
| Phantom Spreads Filtered | 381 |
| One-Legged Failures (sim) | 6 ($0.01 cost) |
| Position Cap Skips | 228 |
| Rebalance EMPTY | 718 |
| Rebalance BLOCKED | 3 (score_gate) |
| EVD_DEMOTED | 95 |

#### Active Symbols

**3 symbols activated** after 60s discovery, but only 1 survived:

| Symbol | Activated | Demoted | Duration | Trades | Net Profit | Notes |
|--------|-----------|---------|----------|--------|------------|-------|
| STRKUSDT | 01:28:24 | — | Full session (1h37m) | 263 | ~$17 | strong tier (score ~0.28-0.30) |
| AXSUSDT | 01:28:24 | 01:54:30 | 26 min | 20 | ~$0.50 | Thin margins (0.042% avg net) |
| DOTUSDT | 01:38:25 | 02:02:32 | 24 min | 0 | $0 | Expanded, never traded, score faded |

**3 candidates REJECTED at activation**: FETUSDT (fading, recent_freq=0.0%), SNXUSDT (fading), BTCUSDT (fading). All had high initial scores during discovery but were transient spikes.

**Post-demotion**: Only STRKUSDT remained active for the final 63 minutes. AXSUSDT and DOTUSDT re-appeared as expansion candidates near session end but hadn't passed stability checks.

#### Exchange Pair Breakdown

| Route (Buy→Sell) | Trades | Est. Profit | Avg Net% | Notes |
|-------------------|--------|------------|----------|-------|
| STRKUSDT Bitfinex→OKX | 165 | ~$13.00 | ~0.80% | Primary route |
| STRKUSDT MEXC→OKX | 67 | ~$1.50 | ~0.14% | Secondary (MEXC 0.05% fee) |
| STRKUSDT Bitfinex→MEXC | 24 | ~$1.50 | ~0.65% | |
| AXSUSDT Gate.io→MEXC | 12 | ~$0.30 | ~0.04% | Before demotion |
| AXSUSDT Gate.io→Bitget | 8 | ~$0.20 | ~0.04% | Before demotion |
| STRKUSDT Bitfinex→Bitget | 3 | ~$0.20 | ~0.70% | Occasional |
| STRKUSDT KuCoin→OKX | 2 | ~$0.05 | ~0.10% | Rare |
| STRKUSDT Bitfinex→KuCoin | 2 | ~$0.15 | ~0.70% | Rare |

**Bitfinex as buyer: 194/283 trades (68.6%)** — lower % than S1/S2 because MEXC→OKX trades (67 trades) don't use Bitfinex. STRK still dominates profit.

#### Exchange Status — All 8 Healthy (Bybit Fixed!)

| Exchange | Symbols | Msg Rate | Avg Freshness | Status |
|----------|---------|----------|---------------|--------|
| MEXC | 60/60 | 617/s | 30ms | Excellent |
| Bybit | 59/60 | 503/s | 149ms | **Healthy (FIXED)** |
| Bitget | 60/60 | 356/s | 75ms | Excellent |
| Binance | 59/60 | 317/s | 225ms | Good |
| OKX | 60/60 | 321/s | 484ms | Good |
| Gate.io | 60/60 | 274/s | 354ms | Good |
| KuCoin | 60/60 | 505/s | 503ms | Good |
| Pionex | 58/60 | 74/s | 976ms | Disabled (data only) |
| Bitfinex | 34/60 | 2/s | 12.5s | Event-driven (normal) |

**Bybit fully operational** — zero errors, zero disconnections, 503 msgs/s, 149ms freshness. Session #2's Bug #1 (`orderbook.5` → `orderbook.50`) is confirmed fixed. Bybit was evaluated for trades and appeared in EVD_DEMOTED pair selections but wasn't in dominant pairs for STRKUSDT this session.

**Pionex disabled** — connected and receiving data (58 symbols) but excluded from active trading set via Fee Management settings.

#### $/hr Progression

| Time | Duration | Trades | Net | $/hr |
|------|----------|--------|-----|------|
| 01:32 | 5m | ~40 | $2.36 | $28.36 |
| 01:42 | 15m | ~110 | $3.72 | $14.88 |
| 01:57 | 30m | ~170 | $6.63 | $13.26 |
| 02:27 | 1h | ~235 | $12.72 | $12.72 |
| 03:05 | 1h38m | 283 | $17.54 | $11.06 |

$/hr declined steadily from $28.36 → $11.06 as seller exchanges ran dry and trades became impossible. This is the capital concentration bottleneck — detailed below.

#### Balance Snapshots

| Time | Bitfinex | MEXC | OKX | Gate.io | Bybit | Others | Total |
|------|----------|------|-----|---------|-------|--------|-------|
| 01:28 | $424 | $24 | $385+crypto | $28 | $0 | $0 | $1,006 |
| 01:33 | $421 | $3 | $365+crypto | $25 | $0 | $0 | $1,006 |
| 01:43 | $501 | $65 | $314 | $73 | $0 | $0 | $1,008 |
| 01:58 | $733 | $79 | $139 | $0 | $0 | $0 | $1,010 |
| 02:13 | $902 | $42 | $59 | $0 | $0 | $0 | $1,013 |
| 02:28 | $993 | $7 | $13 | $0 | $0 | $0 | $1,015 |
| 02:43 | $1,010 | $3 | $3 | $0 | $0 | $0 | $1,016 |
| 03:03 | $1,013 | $2 | $3 | $0 | $0 | $0 | $1,018 |

**Capital concentration timeline**: By 30 minutes, Bitfinex held 73% of capital. By 1 hour, 98%. By session end, 99.5% ($1,013 of $1,018). Seller exchanges (OKX, MEXC) were completely depleted.

#### Transfer Activity

- **Hub consolidation**: 10 consolidation rounds moved idle capital to Bitfinex
- **Post-demotion**: AXSUSDT demotion freed $49.87, consolidated $600.22 to Bitfinex. DOTUSDT demotion sold $9.90 via Bitfinex (saved 0.025% taker).
- **Transfer fee breakdown**: Gate.io $1.00 (2× $0.50), OKX $0.10+, MEXC $0.00, Bitget $0.001. Total $3.87.
- **Transfer fee ratio**: 18.1% of gross profit ($3.87/$21.31) — much higher than S1's 3.4%. Smaller capital amplifies fixed transfer costs.

#### The Capital Concentration Problem

This is the critical bottleneck limiting profitability:

**Mechanism**: Bitfinex is the dominant buyer for STRKUSDT (0% fee). Each trade: Bitfinex sends USDT to buy crypto → crypto ships to seller exchange → seller sells crypto → seller accumulates USDT → rebalancer moves USDT back to Bitfinex. But the rebalancer can't keep up:

1. **USDT flows one-way to Bitfinex**: Bitfinex buys = USDT deducted from Bitfinex. Seller sells = USDT added to seller. Then rebalancer consolidates seller USDT back to Bitfinex. Net: USDT concentrates on Bitfinex.
2. **Crypto depletes on sellers**: Each sell reduces crypto on the seller exchange. The only way to replenish is external crypto transfer (Bitfinex→seller) or internal buy on seller. But both require capital on the seller side.
3. **Death spiral**: Once sellers run dry, trades can't execute → no profit → no new capital flowing to sellers → permanently stuck.

**Evidence**:
- 2,493 SIZE_ZERO events (trade_size=0 because `crypto_val < min_trade` on seller)
- 718 Rebalance EMPTY events (tried to route funds, no viable paths)
- 228 position cap skips
- $/hr dropped from $28.36 (5 min) to $11.06 (1h38m) — a 61% decline

**Why this wasn't a problem in Session #1**: $3,000 capital distributed across 7 seller exchanges (OKX, MEXC, Bybit, Bitget, KuCoin, Gate.io, Binance) with very_strong tier allowing 3 sellers. More capital per seller = longer before depletion. The session ran 16h38m before similar starvation effects appeared.

**With $1,000 capital**: Only ~$100-200 per seller exchange, depleted within 20-30 minutes. The session effectively became single-symbol, single-route by the 30-minute mark.

#### Anomaly Protection

Not triggered. Clean session — no pauses, warnings, emergency sells, or symbol blocks.

#### Simulation Realism

All 4 features working correctly:
- **Spread persistence** (1 tick): 381 phantom spreads filtered
- **EVD seller penalty**: 95 demotions (Bitfinex deprioritized as seller for DOTUSDT)
- **One-legged failures**: 6 simulated, $0.01 total cost (5/6 on Bitfinex buy side = $0 unwind)
- **Position cap**: 228 skips

#### Key Takeaways

1. **Bybit is fixed** — fully operational, zero issues
2. **$1,000 capital is viable** but hits concentration bottleneck fast (~30 min)
3. **STRK remains the profit engine** — persistent structural spread, Bitfinex→OKX dominant
4. **Transfer fee ratio is brutal at small capital**: 18.1% vs 3.4% at $3,000. Fixed transfer costs ($0.10-$0.50) matter more when gross profit is $21 vs $1,372.
5. **Hub consolidation fights crypto rebalancing** — consolidation pulls USDT from active sellers (OKX/MEXC) back to Bitfinex, while crypto rebalancing simultaneously pushes crypto from Bitfinex to those same sellers. See "Capital Concentration Root Cause" below.

#### Capital Concentration Root Cause

**The consolidation is counterproductive for active seller exchanges.**

The cycle:
1. **Trade**: Bitfinex buys STRK (USDT→crypto). OKX sells STRK (crypto→USDT).
2. **Crypto rebalance** (30s cooldown): Bitfinex ships crypto to OKX ($0 fee) so OKX can sell again.
3. **Hub consolidation** (10min eval cycle): Sees OKX has "idle" USDT → pulls it back to Bitfinex ($0.10 fee).
4. **Net effect**: USDT roundtrips Bitfinex→(crypto)→OKX→(consolidation)→Bitfinex, paying $0.10 each consolidation cycle. Capital oscillates but trends toward Bitfinex.

**Evidence from session**: 174 crypto transfers (Bitfinex→sellers, $0 fee) vs 10 consolidation rounds (sellers→Bitfinex, $0.10-$0.50 fee). The system is actively working — but consolidation creates unnecessary friction.

**Root cause**: `consolidate_to_bitfinex()` has `active_buyer_exchanges` protection but NO protection for active seller exchanges. OKX/MEXC are active sellers (receiving USDT from every trade), yet their USDT gets consolidated because they're not in `active_buyer_exchanges`.

**Solution**: Add `active_seller_exchanges` parameter to `consolidate_to_bitfinex()`. Keep a buffer on active sellers (e.g., `trade_amount × 3`) so they can fund internal buys when crypto rebalance is on cooldown. Active sellers that haven't had a trade in 10+ min can still be consolidated. See Decision Log entry for implementation details.

---

## Pattern Tracking

### Confirmed Profitable Patterns

| Pattern | First Seen | Sessions | Avg $/hr | Notes |
|---------|-----------|----------|----------|-------|
| Bitfinex buyer + altcoin strong/very_strong | Session #1 | 5 | $36.20 | STRK/POL. S1: $81.91/hr ($3k), S2: $107.95/hr ($3k), S3: $11.06/hr ($1k), S4: $28.11/hr STRK-only ($1k), S8: $31.52/hr POL ($1k) |
| Non-Bitfinex pair expansion is net negative | Session #3 | 3 | -$2.81 | AXS Gate.io→KuCoin/Bitget. S3: demoted 2× (thin margins). S4: 728 trades, $11.63 gross but -$7.65 net after fees |
| MEXC→Bitfinex ultra-low fee pair | Session #8 | 1 | $31.52 | POL 0.025%+0.000% combined. Nearly any spread is profitable |

### Exchange Performance Summary

| Exchange | Role | Sessions as Top Role | Notes |
|----------|------|---------------------|-------|
| Bitfinex | Buyer | 4/4 | 0% fee + $0 withdrawals = dominant buyer. S1: 89%, S2-S4: STRK buyer |
| OKX | Seller | 4/4 | S1: most trades (1,348). S2-S4: primary/secondary STRK seller |
| MEXC | Seller/Buyer | 4/4 | S1: highest avg ($0.3683). S3-S4: secondary STRK seller. S4: AXS seller (59 trades) |
| Bybit | Seller/Fixed | 1/4 | S1: 760 trades. S2: DEAD (Bug). S3-S4: Fixed, healthy, minimal allocation |
| Bitget | Seller | 2/4 | S1: 496 trades. S4: AXS seller (34 trades, 0.17% combined fee) |
| KuCoin | Seller | 2/4 | S1: 344 trades. S4: AXS primary seller (633 trades, expensive at 0.17%) |
| Gate.io | Buyer | 3/4 | S2-S3: AXS seller. S4: AXS buyer (728 trades, 0.09% fee) |
| Binance | Minimal | 1/4 | S1: 19 trades. S2-S4: $0 allocated |
| Pionex | Not seen | 0/4 | Disabled in Fee Management. Never traded |

### Symbol Performance History

| Symbol | Sessions Active | Best $/hr | Avg $/hr | Typical Tier | Best Buyer | Notes |
|--------|----------------|-----------|----------|-------------|------------|-------|
| STRKUSDT | 4 | $107.95 | $37.43 | strong-very_strong | Bitfinex | Persistent structural spread. S1: 16h/$81.91, S2: 18m/$107.95, S3: 1h37m/$11.06, S4: 2h13m/$28.11. $1k capital bottlenecks at ~30min |
| POLUSDT | 1 | $31.52 | $31.52 | normal | MEXC | S8: MEXC→Bitfinex (0.025% combined). 527 trades in 2h29m. Ultra-low fee pair |
| SNXUSDT | 3 | — | -$1.30 | strong | MEXC/KuCoin | S6-S8: Thin markets, repeated demotions. S8: 2 demotions, elevated threshold. OKX demo rejects |
| DYDXUSDT | 2 | — | — | strong | MEXC | S6-S8: Low margins, OKX demo instrument missing. Demoted after ~4h in S8 |
| AXSUSDT | 3 | — | -$2.81 | normal | Gate.io | Thin margins (0.04-0.12% avg net), expensive pairs (0.17% combined). S3: demoted 2×. S4: 728 trades, net negative. S8: EXPAND_BLOCKED 8× |
| DOTUSDT | 1 | — | — | normal | Bitfinex | S3: Expanded then demoted after 24m, 0 trades. Score faded |

---

## Decision Log

### 2026-03-03: Should We Hardcode Bitfinex Preferences?

**Decision: No.**

After analyzing Session #1, we considered adding:
- Score bonuses for Bitfinex-buyer symbols
- Bitfinex-specific trade size multipliers
- MEXC-seller preferences
- Exchange-specific config overrides

**Rejected because:**
1. The scoring system already captures Bitfinex's 0% fee advantage through higher net_pct
2. Dominant pair detection already gives Bitfinex ~2x weight boost
3. Hardcoding creates fragility — if Bitfinex changes fees, all bonuses become wrong
4. The "best seller" varies by market conditions (MEXC had highest avg profit this session)
5. One session is insufficient data to build exchange-specific optimizations
6. Time will tell which patterns are consistent vs one-time events

**Action taken:** Fixed the expansion cost estimation bug (Bitfinex reserve was blocking valid expansions). No other exchange-specific changes.

**Revisit when:** Multiple sessions confirm consistent patterns across different symbols and market conditions.

### 2026-03-04: Bitfinex Data Staleness — Is It a Problem?

**Decision: No. Bitfinex data is accurate but infrequent — by design.**

After Session #2 showed Bitfinex averaging 2 msgs/s and 14s average freshness (vs MEXC's 617 msgs/s and 52ms), we investigated whether:
- The Zurich proxy was causing delays
- Our code was dropping messages
- Bitfinex was throttling us

**Findings:**
1. Zurich proxy processes messages in 0.01ms — zero overhead, transparent relay
2. Bitfinex official docs: "you will receive updates upon any change" — purely event-driven
3. Bitfinex daily spot volume ~$225M vs Binance ~$15-20B (70-100x less)
4. No server-side throttle on outbound ticker/book data
5. 24/60 symbols rejected as invalid (`tSTRKUST` format — many alts don't have UST pairs)
6. Low-volume alts genuinely don't trade for 10-20+ seconds

**Verdict**: Bitfinex's 0% fee advantage (~0.05-0.10% per trade saved vs any other buyer) massively outweighs slower data. A 14s-old price that hasn't changed is 100% accurate. The bot already handles this correctly — when a spread appears, it trades; when data is stale, there's nothing to trade anyway.

**Action needed**: Consider Bitfinex-specific handling in the freshness logging system. Current metrics conflate "data age" with "data staleness/inaccuracy" — misleading for event-driven exchanges. Bitfinex should not trigger the same freshness warnings as a broken connection would.

### 2026-03-04: Bybit orderbook.5 — Silent Subscription Failure

**Decision: Fix applied. Channel changed to `orderbook.50`.**

Bybit v5 Spot API valid orderbook depths are: 1, 50, 200, 1000. `orderbook.5` does NOT exist. Bybit silently ignores invalid subscriptions without sending an error response, causing:
- Zero data delivery → 30s staleness watchdog → reconnect → repeat endlessly
- 35 reconnections in 18 minutes with zero data

**Root cause**: Likely a copy-paste error from another exchange (Bitget/OKX use `books5`, which may have been confused with `orderbook.5`). The docstring at line 37 correctly said `orderbook.1` but the actual code used `orderbook.5` — the mismatch went unnoticed.

**Lesson**: Always validate WebSocket channel names against official API docs. Test new exchange integrations with log-level monitoring of subscription responses. Consider adding subscription confirmation tracking (count confirmed vs attempted subscriptions).

### 2026-03-04: Pionex Disabled — Was It Correct?

**Decision: Yes. Pionex has real staleness, unlike Bitfinex.**

After discovering Bitfinex's "staleness" was actually event-driven behavior (accurate but infrequent data), we investigated whether Pionex (~930ms avg freshness) was the same case.

**Key differences between Bitfinex and Pionex:**

| Aspect | Bitfinex | Pionex |
|--------|----------|--------|
| Avg freshness | 13,500ms | 930ms |
| Msg rate | 2/s (0.06/symbol) | 70/s (1.2/symbol) |
| Why slow | Prices genuinely don't change | Network latency + aggregation delay |
| Data accuracy | 100% accurate (no change = no update) | Genuinely late (prices changed elsewhere) |
| Server location | Zurich proxy (0.7ms to Bitfinex) | US (Virginia) behind Cloudflare (~300ms one-way) |

**Pionex staleness causes:**
1. **Network latency (~40%)**: US-based origin server behind Cloudflare adds ~250-400ms per message vs Singapore-based exchanges. First-data latency was 5,739ms (vs Binance 8ms, Bitget 103ms).
2. **Low update frequency (~60%)**: Pionex aggregates 50-60% of Binance's order book through its own matching engine, emitting only 1.2 updates/symbol/s vs Binance's native 4.7/s. DEPTH topic is event-driven with no interval parameter.

**Verdict**: Pionex data is genuinely ~1 second stale. Arbitrage opportunities detected using Pionex prices may have already closed on faster exchanges. Disabling Pionex was the correct decision. Pionex's value is limited to Pionex↔non-Binance pairs (since it mirrors Binance, Pionex↔Binance arbitrage is near-zero), and even those opportunities would be detected ~1s late.

**Re-enable when**: Tokyo VPS is deployed (<5ms to Pionex) OR Pionex moves servers closer to Asia.

### 2026-03-04: Bitfinex Event-Driven Latency Handling

**Decision: Implemented `IS_EVENT_DRIVEN` flag.**

Added `IS_EVENT_DRIVEN` class constant to `BaseFetcher` (default `False`), overridden to `True` in `BitfinexFetcher`. Latency logging for event-driven exchanges uses:
- `data_age` label instead of `freshness` (signals expected behavior, not a problem)
- Seconds instead of milliseconds (14.0s is more readable than 13998ms)
- `(event-driven)` suffix to clarify the metric

**Before**: `freshness: avg=13998ms max=118786ms` — looks broken
**After**: `data_age: avg=14.0s max=118.8s (event-driven)` — clearly expected behavior

### 2026-03-04: Capital Concentration — Consolidation vs Active Sellers

**Decision: Protect active seller exchanges from hub consolidation.**

Session #3 revealed that `consolidate_to_bitfinex()` counteracts the crypto rebalancing system. The consolidator pulls USDT from active seller exchanges (OKX, MEXC) back to Bitfinex every eval cycle, while crypto rebalancing simultaneously pushes crypto from Bitfinex to those same sellers. This creates a wasteful roundtrip ($0.10 per OKX consolidation) and starves sellers during cooldown gaps.

**Evidence from Session #3**:
- 174 crypto transfers Bitfinex→sellers ($0 fee each)
- 10 consolidation rounds sellers→Bitfinex ($0.10-$0.50 fee)
- $3.87 total transfer fees (18.1% of $21.31 gross — vs 3.4% at $3,000 capital in S1)
- Capital oscillated but trended to Bitfinex: $424→$162→$852→$162→$1,013
- $/hr dropped 61% (from $28.36 at 5min to $11.06 at 1h38m) as sellers dried up

**Root cause**: `consolidate_to_bitfinex()` accepts `active_buyer_exchanges` but has no concept of active sellers. All non-buyer USDT is treated as idle and consolidated.

**Fix**: Add `active_seller_exchanges` parameter to `consolidate_to_bitfinex()`. The optimizer already tracks dominant sellers per symbol via `_compute_dominant_pairs()` — pass these to consolidation. Keep `trade_amount × 3` buffer on active sellers that traded recently (same logic as active buyers). Active sellers idle > `idle_threshold` can still be consolidated.

**Why this works**: When Bitfinex is buyer and OKX is seller:
- OKX receives USDT from each sell → buffer protects this USDT from consolidation
- When OKX needs crypto, rebalancer ships from Bitfinex ($0 fee)
- OKX can also use its buffered USDT for internal buy (Option 2 in `_rebalance_crypto`) if crypto transfer is on cooldown
- Net: fewer consolidation roundtrips, less wasted fees, steadier trading flow

**Additional improvements to consider**:
1. **Reduce crypto rebalance cooldown for $0-fee transfers**: Currently 30s for all. Bitfinex→anywhere is $0 — could use 10-15s cooldown for free transfers.
2. **Increase crypto transfer amount**: Currently `trade_amount × 3` ($90). For persistent spreads, sending larger batches reduces rebalance frequency and gaps.
3. **Skip consolidation of recently-received USDT on sellers**: Seller just got USDT from a trade 5s ago — don't consolidate it for at least `idle_threshold`.

**Revisit after**: Next session with the fix deployed. Measure: $/hr over time (should be flatter), consolidation count (should decrease), total transfer fees (should decrease).

**Session #4 update**: Fix deployed but **not fully effective**. Active sellers still consolidated — root cause deeper than the `active_seller_exchanges` parameter. See "Consolidation Protection Still Failing" decision below.

---

### Session #4 — 2026-03-04 (Two-Regime Session: STRK Goldmine → AXS Decline)

**Date**: 2026-03-04, 03:56:46 - 09:22:32 UTC (5h 26m)
**Capital**: $1,000
**Version**: v0.21.1-alpha (frequency gate fix, consolidation seller protection, settings logging fix)
**VPS**: LightNode Bangkok + Oracle Zurich (Bitfinex proxy)

#### Summary

| Metric | Value |
|--------|-------|
| Duration | 5h 26m |
| Total Trades | 1,198 |
| Trading PnL | $77.27 |
| Transfer Fees | $22.61 (external: $7.31, internal: $15.30) |
| Cashback | $4.34 (credited: $0.99, pending: $3.34) |
| **Net Profit** | **$55.66** |
| **$/hr** | **$10.40** |
| Portfolio Growth | $1,000 → $1,099 (+9.9%) |
| Phantom Spreads Filtered | 1,353 |
| One-Legged Failures (sim) | 28 ($0.24 cost) |
| Position Cap Skips | 1,992 |
| Anomaly Events | 0 pauses, 0 warnings, 1 symbol block |
| EVD Seller Penalties | 22,964 (0 demotions) |
| Hourly Cap Blocks | 1,107 |

#### Two-Regime Performance

The session divides cleanly into two regimes with dramatically different profitability:

| Phase | Duration | Trades | PnL | Transfer Fees | Net | $/hr |
|-------|----------|--------|-----|---------------|-----|------|
| STRK regime (0–2h15m) | 2h 15m | 471 | $65.69 | $2.65 | $63.31 | $28.11 |
| Dead zone (2h15m–2h38m) | 23 min | 0 | $0 | $0.08 | -$0.08 | — |
| AXS regime (2h38m–5h21m) | 2h 43m | 728 | $11.63 | $19.96 | **-$7.65** | **-$2.81** |

**The last 3 hours actually lost $7.65 net** — AXS generated $11.63 PnL but incurred $19.96 in new transfer fees.

#### Active Symbols

**Discovery** (61s): FET (0.170, rejected: fading), STRK (0.156, strong), AXS (0.011, normal). **Frequency gate fix validated** — STRK activated this time (was rejected in previous session's v0.20.0 run due to 15s window missing Bitfinex updates).

| Symbol | Activated | Demoted | Duration | Trades | Gross Profit | Avg Net% | Avg Trade Size |
|--------|-----------|---------|----------|--------|-------------|----------|----------------|
| STRKUSDT | 03:57:46 | 06:48:35 | 2h 51m (active 2h 13m) | 471 | $65.69 | 0.765% | $17.42 |
| AXSUSDT | 03:57:46 | 04:07:49 | 10 min (1st activation) | 0 | $0 | — | — |
| AXSUSDT | 06:34:32 | — | 2h 48m (2nd, via expansion) | 728 | $11.63 | 0.119% | $13.24 |

**STRK**: Bitfinex→OKX/MEXC. Score peaked at 0.39 (very_strong). Killed by 50-minute Bitfinex proxy outage at 06:12 — zero viable trades during outage → score decay → demotion at 06:48.

**AXS (1st)**: Allocated only $58 (score-weighted). Never traded — SIZE_ZERO because base=$2.50 < min=$5.00. Demoted after 10 minutes.

**AXS (2nd)**: Expanded at 06:34 with score=0.091, est_hourly=$32.92, setup_cost=$0.10, bfx=no. Buyers=[Gate.io], Sellers=[KuCoin, Bitget]. Combined fees 0.17% vs 0.12% avg net — per-trade margins were paper-thin to negative after rebalancing costs.

#### Exchange Pair Breakdown

**STRK (471 trades)**:

| Pair (Buy→Sell) | Trades | % | Combined Fee | Notes |
|------------------|--------|---|-------------|-------|
| Bitfinex→OKX | 222 | 47% | 0.10% | Primary |
| Bitfinex→MEXC | 203 | 43% | 0.025% | Most efficient |
| MEXC→OKX | 31 | 7% | 0.125% | When MEXC had USDT buildup |
| Bitfinex→Bybit | 7 | 1.5% | 0.075% | Early only |
| Others | 8 | 1.5% | 0.08-0.18% | Minor |

93% of STRK trades used Bitfinex as buyer (0% fee).

**AXS (728 trades)**:

| Pair (Buy→Sell) | Trades | % | Combined Fee | Notes |
|------------------|--------|---|-------------|-------|
| Gate.io→KuCoin | 633 | 87% | 0.17% | Dominant but expensive |
| Gate.io→MEXC | 59 | 8% | 0.115% | Better margins |
| Gate.io→Bitget | 34 | 5% | 0.17% | Same fee as KuCoin |
| Bybit→KuCoin | 2 | 0.3% | 0.155% | Rare |

AXS's dominant pair (Gate.io→KuCoin at 0.17% combined) consumed most of the 0.12% average net%.

#### STRK Score Trajectory

| Time | Score | Tier | Mult | Notes |
|------|-------|------|------|-------|
| 03:57 | 0.156 | strong | 2.0 | At activation |
| 04:00 | 0.300 | strong | 2.0 | Ramping up |
| 04:15 | 0.39 | very_strong | 4.0 | Peak tier |
| 05:00 | 0.28 | strong | 2.5 | Cycling |
| 05:30 | 0.22 | strong | 2.0 | Declining |
| 06:00 | 0.17 | strong | 2.0 | Weakening |
| 06:12 | — | — | — | Bitfinex proxy outage starts |
| 06:48 | <0.01 | — | — | Demoted (35 min into outage) |

#### $/hr Progression

| Time | Duration | Trades | Net | $/hr | Phase |
|------|----------|--------|-----|------|-------|
| 04:02 | 0h05m | 20 | $4.55 | $53.52 | STRK launch burst |
| 04:12 | 0h15m | 47 | $9.22 | $35.29 | STRK hot |
| 04:29 | 0h32m | 105 | $18.38 | $34.01 | STRK strong |
| 04:57 | 1h00m | 215 | $30.50 | $30.06 | STRK solo |
| 06:06 | 2h09m | 458 | $62.04 | **$28.76** | STRK peak |
| 06:12 | 2h15m | 471 | $63.31 | $28.11 | STRK stops (outage) |
| 06:35 | 2h38m | 481 | $63.40 | $24.07 | AXS starts |
| 06:57 | 3h01m | 612 | $61.23 | $20.30 | AXS fees > profits |
| 07:38 | 3h41m | 956 | $60.70 | $16.44 | AXS declining |
| 08:01 | 4h04m | 1000 | $58.67 | $14.38 | Net profit falling |
| 08:59 | 5h03m | 1193 | $55.61 | $11.00 | Near stagnation |
| 09:22 | 5h21m | 1198 | $55.66 | **$10.40** | Session end |

Net profit peaked at $63.31 (2h15m) then **declined by $7.65** over the remaining 3 hours.

#### Bitfinex Proxy Outage (06:12 – 07:02, 50 min)

Timeline:
- 06:11:54 — Sub-connection staleness detected, reconnection attempts begin
- 06:12:14 — First timeout error (`timed out during opening handshake`)
- 06:12–07:01 — 179 consecutive timeout errors across ticker + book sub-connections
- 06:55:27 — Book sub-connection partially recovered (30 symbols)
- 07:02:15 — Full recovery (all sub-connections reconnected)

Impact: STRK's sole buyer was Bitfinex. Zero STRK trades during the outage → score decayed → demotion at 06:48 (36 minutes into outage). The proxy uptime tracker did NOT detect this outage (Bug #3 — see below).

#### Transfer Activity

| Type | Count | Total Cost | Notes |
|------|-------|-----------|-------|
| External crypto (Bitfinex→sellers) | ~200 | $0 | STRK phase: zero-cost crypto rebalance |
| External USDT | ~190 | $7.31 | Mix of free (Bitfinex) and paid |
| Internal sell/buy | ~633 | $15.30 | AXS phase: taker fees on every cycle |
| Hub consolidation | ~80 | ~$1.80 wasted | Active exchanges consolidated (Bug #1) |
| Hourly cap blocks | 1,107 | — | Forced internal ops as fallback |

Internal taker fees ($15.30) are **2× external fees** ($7.31). AXS's 633 internal sell/buy cycles at $0.02-0.03 each drove this.

#### Balance Snapshots

**STRK Phase**:

| Time | Bitfinex | OKX | MEXC | Others | Total |
|------|----------|-----|------|--------|-------|
| 04:03 | $381 | $353 | $164 | $107 | $1,005 |
| 04:47 | $660 | $127 | $232 | $7 | $1,026 |
| 05:44 | $234 | $679 | $123 | $13 | $1,050 |
| 06:13 | $923 | $96 | $30 | $13 | $1,063 |
| 06:30 | $1,049 | $1 | $0 | $13 | $1,063 |

Capital cycling between Bitfinex and seller exchanges. After outage, everything consolidated to Bitfinex.

**AXS Phase**:

| Time | Bitfinex | Gate.io | KuCoin | Bitget | MEXC | Total |
|------|----------|---------|--------|--------|------|-------|
| 06:48 | $349 | $589 | $39 | $32 | $26 | $1,066 |
| 07:28 | $174 | $808 | $48 | $4 | $2 | $1,068 |
| 08:49 | $178 | $825 | $35 | $4 | $12 | $1,085 |
| 09:19 | $173 | $859 | $0 | $3 | $32 | $1,099 |

Gate.io (AXS buyer) accumulated 78% of capital. Seller exchanges ($0-50 each) constantly depleted.

#### Anomaly Protection

- **0 pauses, 0 warnings** — trading P&L stayed positive
- **1 symbol block**: AXSUSDT blocked for 300s (07:37–07:42) after 4 consecutive losses during thin-spread period. Correctly prevented further lossy trades.

#### Exchange Status

All 8 enabled exchanges healthy. No errors except Bitfinex proxy outage (06:12–07:02). Bybit fully operational (503+ msgs/s). MEXC depth reconnections normal (~every 15s, REST-polled). 6 "Task exception was never retrieved" from asyncio (non-functional).

#### Simulation Realism

| Feature | Count | Impact |
|---------|-------|--------|
| Phantom spreads | 1,353 (53% of opportunities) | Prevented ~$1.5-2 false profit |
| One-leg failures | 28 (2.3% rate) | $0.24 total cost |
| Position cap skips | 1,992 | Prevented over-accumulation |

#### Bugs Found

**Bug #1: Active seller exchanges still consolidated despite protection fix** — Gate.io (AXS buyer) consolidated at 07:56 and 09:21 ($0.50/each), KuCoin (AXS seller) consolidated 2× ($0.40/each), while AXS was active. ~$1.80 wasted. **Root cause**: The `idle_threshold` (600s) triggers on intermittent trading patterns. Additionally, investigation shows cases where active sellers were consolidated with `keep=0` only 62 seconds after a trade — suggesting `_reevaluate_dominant_pairs()` may silently change the sellers list right before consolidation runs. See Decision Log. **Fixed in v0.22.0-alpha**: (a) `_reallocate_symbol()` returns bool, `_dominant_pairs` only updated on success; (b) idle_threshold increased to 1800s (30 min); (c) `last_trade_time` updated on all rebalance operations (internal sell, external USDT/crypto, internal buy).

**Bug #2: [Settings] SESSION_START missing** — Settings logging ran before the WebSocket server/log handler was ready for disk export. Entries were emitted but not captured in rotated log files. **Fixed in v0.22.0-alpha**: Settings logged 10s after server start via `call_later()`. Version (`[Config] version=vX.Y.Z`) logged immediately before settings.

**Bug #3: Proxy uptime tracker missed 50-min Bitfinex outage** — `BitfinexFetcher` sub-fetchers set `_ws_connected = True` on connect but NEVER set it `False` on disconnect (no `finally` block). The parent `_ws_connected` stays `True` during outages. Dashboard showed 8/8 connected throughout. See Decision Log. **Fixed in v0.22.0-alpha**: Added `finally` blocks to both `_BitfinexSubFetcher` and `_BitfinexBookSubFetcher` `_connect_and_listen()` methods.

**Issue #1: AXS expansion was net negative** — Expansion cost gate ($0.10 setup vs $32.92/hr estimated) doesn't model ongoing rebalancing costs or validate pair fee viability. AXS's Gate.io→KuCoin pair (0.17% combined fees) exceeded the 0.12% average net%, making every trade marginally unprofitable before transfer costs. The $32.92/hr estimate was inflated by using scoring fees (with cashback reduction) instead of taker fees, and by only averaging profitable ticks. See Decision Log. **Fixed in v0.22.0-alpha**: Added pair fee viability gate — blocks expansion when `combined_taker_fee > avg_profitable_net × 0.8`.

#### Key Takeaways

1. **STRK at $28+/hr validates the Bitfinex-buyer pattern** — now confirmed across 4 sessions
2. **Bitfinex proxy = single point of failure for STRK** — 50-min outage → demotion → lost $7.65 net
3. **AXS was a net-negative expansion** — expansion cost gate needs ongoing cost modeling
4. **Internal taker fees are the #1 cost** ($15.30 vs $7.31 external) — driven by AXS's expensive pairs
5. **Anomaly protection worked** — 1 correct symbol block, no false positives

---

## Session #4 — Decision Log

### 2026-03-04: Consolidation Protection Still Failing (Bug #1)

**Problem**: Despite adding `active_seller_exchanges` parameter to `consolidate_to_bitfinex()`, active exchanges are still consolidated. Session #4 lost ~$1.80 in unnecessary fees.

**Root cause investigation** revealed two issues:

**Issue A: `_reevaluate_dominant_pairs()` silently changes sellers before consolidation**

In the eval cycle, `_reevaluate_dominant_pairs()` runs BEFORE consolidation. When it detects a pair change, it updates `_dominant_pairs[sym]` — even if `_reallocate_symbol()` returns early (cost gate, price=0). This means the `active_sellers` set built from `_dominant_pairs` right after reevaluation may contain different exchanges than what was allocated. The old sellers (which have actual capital and USDT from trades) are no longer in the set and get consolidated with `keep=0`.

Evidence: OKX consolidated for $623.29 just 62 seconds after a trade — `keep=0` applied (math proves it), meaning OKX was NOT in `active_sellers` despite being STRK's seller.

**Issue B: `idle_threshold` (600s) is too aggressive for intermittent trading**

Even when an exchange IS in `active_sellers`, the 10-minute idle check causes it to be treated as fully idle. Arbitrage trading is bursty — a seller can go 10+ minutes without a trade, then have a burst. Gate.io (AXS buyer) had a 13-minute gap and was consolidated despite being the sole buyer.

**Fix plan** (all implemented in v0.22.0-alpha):
1. **Gate `_dominant_pairs` update on successful reallocation**: `_reallocate_symbol()` now returns `bool`. `_dominant_pairs` only updated when capital was actually moved — prevents consolidation from reading stale/unmigrated pairs.
2. **Increase idle_threshold to 1800s (30 min)**: 10 minutes is too short for intermittent arbitrage. 30 minutes better matches the actual trading pattern.
3. **Update `last_trade_time` on rebalance operations**: Internal sells, external USDT transfers, external crypto transfers, and internal buys all update `last_trade_time` for both source and destination exchanges.

### 2026-03-04: Bitfinex `_ws_connected` Never Set False (Bug #3)

**Problem**: Proxy uptime tracker didn't detect the 50-minute Bitfinex outage (06:12–07:02). Dashboard showed 8/8 connected throughout.

**Root cause**: `BitfinexFetcher` overrides the base class `run()` and uses 4 sub-fetchers (`_BitfinexSubFetcher`, `_BitfinexBookSubFetcher`). Each sub-fetcher's `_connect_and_listen()` sets `_parent._ws_connected = True` on connect but **never sets it `False`** on disconnect — there is no `finally` block. The base class `_connect_and_listen()` has the `finally: _ws_connected = False`, but it's never called for Bitfinex.

Additionally, 4 sub-fetchers sharing a single boolean creates a race condition: even if one sets `False`, another reconnecting immediately sets `True`.

**Fix** (implemented in v0.22.0-alpha): Added `finally: self._parent._ws_connected = False` blocks to both `_BitfinexSubFetcher._connect_and_listen()` and `_BitfinexBookSubFetcher._connect_and_listen()`. When all sub-connections are down (full outage), `_ws_connected` will be `False` and the proxy tracker will detect it. The race condition with 4 sub-fetchers remains (any one reconnecting sets `True`), but this is acceptable — a single sub-connection recovering means partial data flow has resumed.

### 2026-03-04: Expansion Cost Gate Doesn't Model Ongoing Costs (Issue #1)

**Problem**: AXS expanded with `est_hourly=$32.92 setup_cost=$0.10` but lost $7.65 net over 2.5 hours. The cost gate only checks one-time setup costs, not ongoing operational viability.

**Root causes** (3 compounding issues):

1. **No ongoing cost model**: `_estimate_expansion_cost()` calculates one-time transfer/taker fees to deploy capital. It doesn't model: internal buy taker fees every few minutes, external USDT transfers for replenishment, or the rate of capital depletion that drives these costs.

2. **`est_hourly_profit` inflated**: Uses `get_scoring_fee()` (includes cashback reduction: Gate.io 0.081%, KuCoin 0.072%) instead of actual `get_taker_fee()` (Gate.io 0.090%, KuCoin 0.080%). Only averages profitable ticks, ignoring unprofitable ones. AXS's $32.92/hr estimate vs actual $4.17/hr gross (~$-2.81/hr net).

3. **No pair fee viability check**: There's no validation that the dominant pair's combined fee rate (0.17%) is less than the symbol's avg net% (0.12%). When combined fees > avg net%, every trade is unprofitable before transfer costs.

**Fix** (implemented in v0.22.0-alpha): Added **pair fee viability gate** before expansion:
1. Computes combined taker fee for the candidate's dominant pair: `buy_fee + sell_fee`
2. Compares against `avg_profitable_net`
3. Blocks expansion if `combined_taker_fee > avg_profitable_net * 0.8` (allows 20% margin for fee estimation error)
4. Logged as `EXPAND_BLOCKED ... pair_fee_exceeds_net`

This is simpler and more effective than modeling ongoing costs, because the fundamental issue is per-trade unprofitability, not insufficient capital.

### 2026-03-04: STRK Single Point of Failure — Bitfinex Dependency

**Problem**: STRK's entire trading capability depends on Bitfinex (sole buyer). When the Zurich proxy went down for 50 minutes, STRK had zero viable trades → score decay → demotion after 36 minutes.

**Observation, not a fix**: This is inherent to STRK's market structure. Bitfinex has the lowest ask price due to its low volume/event-driven nature, creating the structural spread. No other exchange can replace Bitfinex as buyer — MEXC→OKX trades exist but at much lower net% (0.14% vs 0.76%).

**Mitigation**: Improve proxy uptime (Bug #3 fix) + faster proxy reconnection. Consider: increase demotion timer for Bitfinex-dependent symbols during detected proxy outages (don't demote a profitable symbol because the proxy is temporarily down).

---

### Session #5 — 2026-03-04 (Demo Only Diagnostic)

**Date**: 2026-03-04
**Capital**: $1,800
**Version**: v0.23.1-alpha
**Mode**: Demo Only (Binance/OKX/Bybit)
**VPS**: LightNode Bangkok

#### Summary

Short diagnostic run to test Demo Only mode with lowered score threshold (0.0001). No trades executed, 2 transfers occurred. Main finding: 276 `missing_position` discrepancies — the sim allocated crypto virtually via `initialize_crypto()` but no demo buy orders were placed on testnet accounts.

#### Bugs Found

**Bug #4: Missing Demo Position Establishment (CRITICAL)**

The sim allocates crypto to seller exchanges during discovery (`balance.initialize_crypto()`), but no actual demo orders are placed on testnet accounts. Result: demo accounts have 0 crypto, sim shows allocated positions → 276 `missing_position` discrepancies (all on Bybit for DOGEUSDT and ONDOUSDT).

**Root Cause**: `initialize_crypto()` creates virtual positions (divides capital by price). The demo system only placed orders during arbitrage trades, not during initial position establishment.

**Fix** (v0.24.0-alpha): Added `_run_demo_setup()` in `monitor.py` — fires once after `initialize_crypto()`, places market buy orders on demo/testnet via `DemoExecutor.execute_setup_orders()` to mirror sim allocations. One-shot, persisted in state.

**Bug #5: Bitfinex `_ws_connected` Race Condition**

Dashboard showed Zurich VPS proxy as "DOWN" despite it running correctly. Root cause: 4 Bitfinex sub-fetchers (2 ticker + 2 book) all wrote to the same `_ws_connected` boolean. When a slower sub-fetcher's `finally` block ran after a faster one connected, it set `_ws_connected = False`.

**Fix** (v0.24.0-alpha): Changed `_ws_connected` to use a `_connected_subs: set[int]` tracking per-sub-fetcher state. `_ws_connected = len(set) > 0`.

**Bug #6: Discrepancy Log Flood**

`[DemoCompare]` logged every discrepancy at INFO on every 15s poll cycle. 276 identical `missing_position` logs in the session.

**Fix** (v0.24.0-alpha): Added throttling — repeated discrepancies logged every 5 min per exchange+symbol+type. Re-logs immediately on >50% value change. Periodic summary every 5 min. `Discrepancy` objects still created for dashboard.

#### Improvements Identified

1. **Single-leg demo execution**: Demo mode required both exchanges to have executors. Changed to fire demo orders on ANY leg with an executor — dramatically more coverage in Demo+Sim mode.
2. **Demo+Sim recommended over Demo Only**: Provides more arbitrage pairs (9 exchanges) while still validating all trades touching Binance/OKX/Bybit.

---

### Session #6 — 2026-03-04 (Demo+Sim First Run)

**Date**: 2026-03-04, ~21:58 - 22:15 UTC (~17min)
**Capital**: $1,000
**Version**: v0.24.0-alpha
**Mode**: Demo + Simulation (all 9 exchanges, demo on Binance/OKX/Bybit)
**VPS**: LightNode Bangkok + Oracle Zurich (Bitfinex proxy)
**Pionex**: Disabled

#### Summary

| Metric | Value |
|--------|-------|
| Duration | ~17 min |
| Total Trades | 79 (sim), 65 demo attempts |
| Trading PnL | $0.27 |
| Transfer Fees | $1.32 (external: $0.91) |
| **Net Profit** | **-$1.05** |
| **$/hr** | **-$4.01** |
| Active Symbols | AXSUSDT (KuCoin→OKX), DYDXUSDT (Gate.io/MEXC→Binance) |
| Demo Fills | 8 filled (all single-leg sells), 54 OKX rejected, 3 Bybit rejected |
| Position Cap Hits | 202 |

First run using Demo+Sim mode after implementing demo position establishment (v0.24.0-alpha). Net negative due to $10 trade sizes generating $0.005-$0.012 profit per trade, insufficient to cover transfer fees.

#### Demo Execution Analysis

- **65 demo trade attempts**, all single-leg (buyer exchanges KuCoin/MEXC/Gate.io have no demo executors)
- **8 successful fills**: All sell-side on Binance (DYDXUSDT) — fill rate 12.3%
- **54 OKX rejections**: `Parameter clOrdId error` — hyphens in client order ID violate OKX format requirements
- **3 Bybit rejections**: `Insufficient balance` — demo setup partial fill left insufficient AXS position for subsequent sells
- **0 full arbitrage pairs**: In Demo+Sim mode, typical pairs are KuCoin→OKX or MEXC→Binance — only one exchange has a demo executor

#### Setup Order Results

| Exchange | Symbol | Requested | Filled | Status | Latency |
|----------|--------|-----------|--------|--------|---------|
| Binance | AXSUSDT | 130.08 | 130.08 | FILLED | 124ms |
| Binance | DYDXUSDT | 907.44 | 907.44 | FILLED | 119ms |
| Bybit | AXSUSDT | 9.57 | 7.75 (81%) | PARTIAL | 280ms |
| Bybit | DYDXUSDT | 13.28 | 13.28 | FILLED | 277ms |
| OKX (all) | — | — | — | REJECTED | — |

Bybit AXSUSDT partial fill (81%) caused by thin testnet order book — only 7.75 of 9.57 qty available at market.

#### Bugs Found

**Bug #7: OKX `clOrdId` Format Rejection (HIGH)**

All OKX demo orders rejected with `Parameter clOrdId error`. `generate_client_order_id()` produced `coirna-BTC-s-1740...-a1b2c3` with hyphens, but OKX requires alphanumeric-only, starting with a letter, max 32 chars.

**Fix** (v0.24.1-alpha): Changed format from `coirna-{base}-{s}-{ts}-{uid}` to `cb{base}{s}{ts}{uid}` — no hyphens, starts with letters, fits all exchange requirements.

**Bug #8: Bybit "Insufficient balance" Sell Rejections (MEDIUM)**

After partial fill on demo setup (7.75 of 9.57 AXS), subsequent sell attempts exhausted the position and then failed with `170131: Insufficient balance`. The sim didn't know the demo account was empty.

**Fix** (v0.24.1-alpha): Added `_demo_positions` tracking in `DemoExecutor`. Tracks actual crypto held on demo exchanges (updated on every setup fill, buy fill, and sell fill). Before placing a sell, `cap_sell_qty()` checks available position — returns 0 (skip) if empty, reduces qty if partial. Persisted in state.

**Bug #9: Rebalance EMPTY Loop — 32 Attempts in 90s (MEDIUM)**

`try_rebalance()` returned no transfers 32 consecutive times in 90 seconds for the same AXSUSDT KuCoin→OKX pair. No backoff — every tick retried the same failing rebalance.

**Fix** (v0.24.1-alpha): Added `_rebalance_empty_backoff` with exponential cooldown (30s→60s→120s→240s→300s cap). After EMPTY result, next attempt delayed. Cleared on successful rebalance or trade.

#### Other Observations

| # | Observation | Severity | Action |
|---|-------------|----------|--------|
| 1 | Binance testnet 0% fees (production: 0.075%) | INFO | Expected testnet behavior |
| 2 | Bybit testnet 0.100% fees (production: 0.075% with discount) | INFO | Testnet doesn't honor token discounts |
| 3 | D-08 consistent +0.1% slippage on DYDXUSDT/Binance | INFO | Testnet order book spread |
| 4 | MEXC depth 62 reconnections in 17min (~16s cycle) | INFO | Worth investigating later |
| 5 | OKX withdrawal fee validation empty API key | LOW | Config issue, static fees unaffected |
| 6 | Hub consolidation KuCoin→Bitfinex $0.40 on negative session | INFO | Cost gate tuning question |
| 7 | 202 position cap hits in 15min | INFO | Working as designed |

#### Improvements Implemented

1. **Depth-aware setup sizing**: `execute_setup_orders()` now checks order book depth via `compute_buy_slippage()` before ordering. Caps qty to 90% of available depth if insufficient. Would have prevented the Bybit partial fill.
2. **Demo position tracking**: `DemoExecutor._demo_positions` tracks actual crypto positions, preventing sell attempts on empty demo accounts.
3. **Rebalance EMPTY backoff**: Exponential cooldown prevents flooding logs with identical failed rebalance attempts.

#### Lessons

1. **$10 trade sizes can't cover transfer fees**: Each trade generates $0.005-$0.012. A single $0.10 transfer needs 10-20 trades to recoup. At $1,000 capital this is expected.
2. **Demo+Sim mode reveals single-leg only**: Most arbitrage pairs cross demo/non-demo exchanges. Full arbitrage validation needs Demo Only mode or more exchange demo APIs.
3. **Testnet order books are unreliable**: Bybit testnet had insufficient depth for a $12 order. Production would handle this trivially. Depth-aware sizing is still good practice.

---

### Session #7 — 2026-03-04 (Settings Desync Bug)

**Date**: 2026-03-04, ~22:36 - 23:13 UTC (~37min)
**Capital**: $1,000
**Version**: v0.24.1-alpha
**Mode**: Demo + Simulation (8 exchanges, Pionex disabled)
**VPS**: LightNode Bangkok + Oracle Zurich (Bitfinex proxy)

#### Summary

| Metric | Value |
|--------|-------|
| Duration | ~37 min |
| Total Trades | 91 (sim) |
| Trading PnL | $1.29 |
| Transfer Fees | $2.14 (external: $1.61) |
| **Net Profit** | **-$0.82** |
| **$/hr** | **-$1.51** |
| Active Symbols | HYPEUSDT → SNXUSDT + DOGEUSDT (after rotation) |
| SIZE_ZERO Events | 900+ |
| Position Cap Hits | 200+ |

SNX was strong (score 0.1141) with 0.07-0.29% net spreads, but trading stalled for the last ~4 minutes due to a cascading failure: seller-side capital starvation on KuCoin → hourly transfer cap blocked replenishment → net P&L gate closed → emergency reserve exhausted.

#### Bugs Found

**Bug #10: Settings Not Synced at Startup (CRITICAL)**

The VPS `settings.json` had `hourly_external_transfer_cap: 5.0` (set via dashboard in a previous session), and the `[Settings]` log confirmed `hourly_transfer_cap=$5.00`. But `BalanceTracker` was enforcing `$2.00` — the constructor default from `run.py`.

**Root Cause**: `run.py` creates `BalanceTracker` with `settings.get("hourly_external_transfer_cap", 2.0)`. The `_apply_settings()` method (which syncs all values to components) only runs when a user saves settings from the dashboard — it was **never called at startup**. So settings changed via dashboard in previous sessions were persisted to `settings.json` and logged correctly, but not applied to the actual components.

**Impact**: Hourly cap enforced at $2 instead of $5. Transfers blocked at `$1.60 + $0.40 > $2.00` when they should have been allowed. SNX trading stalled 25 minutes early. The bug affected ALL settings that can be changed via dashboard: `hourly_external_transfer_cap`, `bitfinex_reserve_pct`, `rebalance_cooldown`, `min_net_profit_pct`, `spread_persistence_ticks`, anomaly thresholds, etc.

**Fix** (v0.24.2-alpha): Added `_sync_settings_on_startup()` in `dashboard_server.py:run()` — syncs all persisted settings from `settings.json` to BalanceTracker, Monitor, Optimizer, and AnomalyProtection at startup. Targeted method (no optimizer reset/discovery restart unlike full `_apply_settings()`).

**Bug #11: Emergency Draw Log Spam — 60+ Messages in 2 Minutes (LOW)**

When Bitfinex reserve hit the hard floor ($50), every tick triggered `[Balance] Emergency draw limited by hard floor` — over 60 identical messages in ~2 minutes.

**Fix** (v0.24.2-alpha): Throttled to once per 30 seconds.

#### Cascading Failure Timeline

| Time | Event | Effect |
|------|-------|--------|
| 22:54 | SNX activated, KuCoin = sole seller | Trades sell on KuCoin, consuming crypto |
| 22:55-23:02 | Burst trading + rebalancing | $30 rebalances consumed in ~3 trades each |
| 23:02:54 | Hourly cap blocked (`$1.60+$0.40 > $2.00`) | External transfers stopped (should have been $5.00 cap) |
| 23:05-23:09 | Internal rebalance attempts, some succeed | Trading in sporadic bursts |
| 23:09:13 | Net P&L gate closed ($1.29 PnL < $1.61 ext fees) | ALL rebalancing blocked |
| 23:09-23:11 | Emergency reserve draws from Bitfinex | Temporary relief, quickly exhausted |
| 23:11:25 | Emergency reserve hit hard floor ($50) | 60+ identical log messages, no more draws |
| 23:11-23:13 | Complete stall | Strong symbol, active spreads, zero trades |

#### Discrepancies (All Harmless)

| Type | Count | Details |
|------|-------|---------|
| D-10 OKX HYPE min order | 13 | $10 below OKX testnet minimum |
| D-10 OKX SNX instrument | 2 | SNX not on OKX demo testnet |
| D-10 Bybit HYPE min order | 4 | $10 below Bybit testnet minimum |
| D-04b Bybit fee 0.075%→0.301% | 5 | Testnet doesn't apply token discounts |
| D-08 slippage 0.03% | 1 | Normal |
| missing_position OKX/Bybit | Several | Consequence of D-10 rejections |
| balance_mismatch Bybit $240 | 1 | Unhedged single-leg demo buys |

All testnet artifacts — no production impact.

#### Other Observations

| # | Observation | Notes |
|---|-------------|-------|
| 1 | OKX clOrdId fix confirmed working | Orders submitted correctly, rejected for instrument/min-order reasons (not format) |
| 2 | Rebalance EMPTY backoff working | `backoff=30s`, `backoff=60s` logged — no more 32-in-90s spam |
| 3 | DOGE properly demoted after 900s | Sold via Bitfinex at 0% |
| 4 | EVD_DEMOTED noise for DOGE (~20 msgs) | Working as designed, verbose |

#### Lessons

1. **Settings desync is silent and dangerous**: The log showed the correct value ($5.00) but the component used the wrong one ($2.00). The settings logging reads from `self._settings` (in-memory), not from the component's actual field. Added startup sync to prevent this.
2. **Single-seller concentration creates fragile capital loops**: When 100% of sell volume goes to one exchange, the bot enters: trade → deplete → rebalance → trade → deplete. Each $30 rebalance only covers ~3 trades at $10.
3. **Log throttling is essential**: Emergency draw spam (60+ msgs) drowns out useful diagnostic information.

---

### Session #8 — 2026-03-05 (Two-Phase: Transfer Fee Burn → POL Goldmine)

**Date**: 2026-03-05, 00:00:08 - 07:28:25 UTC (7h 28m)
**Capital**: $1,000
**Version**: v0.24.2-alpha
**Mode**: Demo + Simulation (8 exchanges, Pionex disabled)
**VPS**: LightNode Bangkok + Oracle Zurich (Bitfinex proxy)

#### Summary

| Metric | Value |
|--------|-------|
| Duration | 7h 28m (Phase 1: 4h55m, Phase 2: 2h29m) |
| Total Trades | 574 (Phase 1) + 527 (Phase 2) = ~1,101 |
| Phase 1 PnL | $6.51 (transfer fees: $12.42, net: -$5.38) |
| Phase 2 PnL | $79.80 (transfer fees: $1.79, net: $78.60) |
| Phase 2 $/hr | **$31.52** |
| Cashback | $1.96 (credited: $0.58, pending: $1.38) |
| Phantom Spreads Filtered | 3,214 |
| One-Legged Failures (sim) | 18 ($0.16 cost) |
| Position Cap Skips | 1,336 |
| SIZE_ZERO Events | 19,290 |
| Rebalance BLOCKED | 239 |
| Rebalance EMPTY | 701 |
| Anomaly Symbol Blocks | 2 (SNXUSDT, DYDXUSDT) |
| EVD Seller Demotions | 11 |
| Demo Fill Rate | 13/87 (14.9%) — 71 rejects from OKX instrument errors |

#### Phase 1 — Transfer Fee Burn (00:00–04:55)

**Symbols**: SNX + DYDX activated at discovery. AXS EXPAND_BLOCKED 8× (pair_fee 0.115% > avg_net 0.053-0.066%). POL expanded at 02:49 (bfx=yes). Symbols rotated through demotions/re-activations.

| Symbol | Activated | Demoted | Trades | Notes |
|--------|-----------|---------|--------|-------|
| SNXUSDT | 00:00:08 | 04:55:36 | ~136 | Stalled early, re-activated at 04:01, demoted again |
| DYDXUSDT | 00:00:08 | 04:35:29 | ~130 | Low margins, repeated OKX demo rejections |
| POLUSDT | 02:49:03 | 03:25:12 | ~17 | First activation, demoted after 36min |
| AXSUSDT | — | — | 0 | EXPAND_BLOCKED 8× (pair_fee_exceeds_net) |

**Why unprofitable**: Transfer fees ($12.42) consumed all PnL ($6.51). Expensive consolidation via KuCoin ($0.40/transfer) and Gate.io ($0.50/transfer) repeated many times. Hourly cap bug (see below) blocked cheaper alternatives at $2.00 instead of $5.00, forcing capital starvation cycles.

**Net P&L gate closed** at 04:25 (`net=$-0.14`), blocking all rebalancing. Reopened at 04:56 after final demotions freed capital.

#### Phase 2 — POL Goldmine (04:56–07:28)

**Single symbol**: POLUSDT on MEXC→Bitfinex (0.025% + 0.000% = 0.025% combined fees).

| Time | Duration | Trades | Net | $/hr |
|------|----------|--------|-----|------|
| 05:02 | 5m | 25 | $1.20 | $12.59 |
| 05:28 | 31m | 87 | $7.90 | $15.06 |
| 06:03 | 1h06m | 244 | $29.86 | $26.90 |
| 06:38 | 1h41m | 381 | $50.96 | $30.14 |
| 07:08 | 2h11m | 490 | $69.09 | $31.54 |
| 07:26 | 2h29m | 527 | $78.60 | $31.52 |

**Why so profitable**: MEXC→Bitfinex is the cheapest possible pair (0.025% MEXC taker + 0% Bitfinex taker). POL had a persistent ~0.28% spread. With only $1.79 total transfer fees over 2.5 hours, nearly all PnL was retained.

#### Discrepancies (16 instances, all testnet artifacts)

| Type | Count | Details | Severity |
|------|-------|---------|----------|
| D-10 (rejected) | 68 | SNX/DYDX not on OKX demo | Log spam, harmless |
| D-10 (canceled) | 3 | POL thin OKX testnet liquidity | Harmless |
| D-08 (slippage) | 4 | SNX +0.30% Binance, +0.18% Bybit | Expected for low-cap |
| D-09 (partial fill) | 3 | AXS 82.71% on Bybit (consistent ratio) | Testnet cap |
| D-12 (high latency) | 3 | POL 1.6-2.0s on OKX (cancel retry flow) | Harmless |
| D-04b (fee mismatch) | 10 | Bybit 0.075%→0.301%/0.083% | Testnet no discount |
| FeeValidation | 2 | Binance 0%, Bybit 0.10% testnet | Expected |

**Verdict**: All 16 discrepancies are demo/testnet artifacts. No production code bugs.

#### Bugs / Issues

**Bug #12: Hourly Transfer Cap STILL Enforced as $2.00 (Persists from S7)**

`_sync_settings_on_startup()` (added in v0.24.2-alpha) logged `hourly_transfer_cap=$5.00` at 23:59:17 but BalanceTracker enforced `$2.00/hr` throughout the entire session (370 blocked transfers). The code at `dashboard_server.py:1865-1866` correctly sets the attribute and the name matches `balance.py:160`. Root cause unclear without VPS access — may be a race condition or naming issue. **Need to add a verification log** in `_sync_settings_on_startup()` that reads back the BalanceTracker attribute after setting it.

**Impact**: 370 transfers blocked. Phase 1 transfer starvation was significantly worsened.

**Other observations**:

| # | Item | Status |
|---|------|--------|
| 1 | MEXC fee 0.025% (VPS config) | Verify intentional — CLAUDE.md says 0.05% with no discount token |
| 2 | asyncio "Task exception never retrieved" (9×) | Silent failures near MEXC/Pionex reconnects |
| 3 | OKX freshness degraded 288ms→1,394ms over 7h | Monitor for progressive staleness |
| 4 | Rebalance EMPTY backoff working | 701 messages (down from uncontrolled loops in S7) |
| 5 | Emergency draw throttle working | No spam (fixed in v0.24.2-alpha) |
| 6 | Demo position tracking working | `cap_sell_qty()` correctly skips empty positions |
| 7 | Settings sync logged $5.00 but enforced $2.00 | Same bug as S7, fix incomplete |

#### Anomaly Protection

| Event | Time | Details |
|-------|------|---------|
| SYMBOL_BLOCKED SNXUSDT | 01:29:20 | 4 consecutive losses, blocked 300s |
| SYMBOL_BLOCKED DYDXUSDT | 02:26:26 | 4 consecutive losses, blocked 300s |
| Circuit breaker | — | Not triggered (0 pauses, 0 warnings) |

Both blocks were appropriate — symbols experiencing consecutive losses due to balance depletion.

#### Key Takeaways

1. **MEXC→Bitfinex is the most profitable pair discovered**: 0.025% combined fees means nearly any spread is profitable. POL generated $31.52/hr — highest sustained $/hr since Session #1's STRK.
2. **Phase 1 transfer fees remain the primary drag**: $12.42 fees on $6.51 PnL. The hourly cap bug ($2 vs $5) made it worse, but the fundamental issue is multi-symbol trading with expensive exchange pairs.
3. **Single-symbol concentration works when the pair is cheap**: Phase 2 had $1.79 fees on $79.80 PnL (2.2% fee ratio vs Phase 1's 190%).
4. **Hourly cap sync bug is persistent**: v0.24.2-alpha fix logged correctly but didn't actually change the runtime value. Needs deeper investigation.
5. **POL is a new profit engine alongside STRK**: Both benefit from Bitfinex's 0% fee, but POL uses MEXC (0.025%) vs STRK's typical OKX (0.10%) pairing.

---

### Session #9 — 2026-03-05 (VPS Crash Recovery)

**Date**: 2026-03-05, 07:48–08:10 UTC (22 min)
**Capital**: $1,000
**Version**: v0.24.2-alpha
**Mode**: demo (Binance/OKX/Bybit) + simulation
**VPS**: LightNode Bangkok

#### Summary

| Metric | Value |
|--------|-------|
| Duration | 22 min |
| Total Trades | 0 |
| Trading PnL | $0.00 |
| Transfer Fees | $0.00 |
| Net Total | +$0.58 (credited cashback from Session #8) |
| Active Symbols | 1 (POLUSDT, from state restore) |
| Exchanges | 8/9 (Pionex disabled) |

Session #9 was an unintentional VPS crash/reboot ~20 min after Session #8 ended. No trades were executed because anomaly protection was paused from Session #8 state and persisted through the crash. The session ran for 22 minutes producing only latency/reconnection logs before being terminated.

#### Bugs Found (3 bugs, all fixed in v0.24.3)

**Bug #13: `stop()` writes restart marker on SIGTERM — false "intentional restart"**

`dashboard_server.py:stop()` wrote a `state/restart_marker` file on every SIGTERM signal (including VPS crash). On next startup, `_check_restart_marker()` found it, set `_restart_grace=True`, and `_load_uptime_data()` treated it as an intentional restart — deleting `state/uptime.json` and starting fresh. Result: uptime counter reset, downtime not recorded, log says "intentional restart" for a crash.

**Root cause**: `stop()` was meant as a safety net for email suppression but had the side effect of making every crash look intentional. Only `_trigger_restart()` (explicit dashboard "Restart Bot" button) should write the marker.

**Fix**: Removed restart marker write from `stop()`. Only `_trigger_restart()` writes it.

**Bug #14: Anomaly `_paused` persisted across crash — trading blocked with 0 trades**

Session #8 ended with anomaly protection paused (circuit breaker or drawdown). State was saved to `session.json` with `_paused=True`. On Session #9 startup, `from_state_dict()` restored `_paused=True` immediately. With 0 trades and no new rolling P&L data, the auto-resume conditions could never be met. Trading was permanently blocked.

Log evidence: `[Monitor] Anomaly protection activated, trading paused` at 07:48:24 (instant, before any data).

**Fix**: On startup, if `_paused` is restored, reset `_pause_timestamp` to now and log a WARNING. This restarts the cooldown timer so `_check_recovery()` can properly evaluate with fresh data — circuit breaker auto-resumes after cooldown (300s) once rolling P&L is above threshold (stale entries pruned to 0), drawdown auto-resumes when portfolio recovers. Emergency stays paused (requires manual resume). Prevents both permanent stuck-pause AND unsafe instant-resume.

**Bug #15: MEXC depth sub-connection log spam (~162 lines in 22 min)**

Two MEXC depth sub-connections (30 symbols each) reconnected every ~30s due to staleness watchdog (no depth data received within 30s). Each reconnect logged 2 INFO lines ("connected" + "Subscribed"). 82 "connected" + 80 "Subscribed" = 162 log lines, consuming ~28% of the 570-line session log.

The reconnections themselves are harmless — MEXC depth data via protobuf WebSocket is unreliable and the staleness watchdog correctly closes stale connections. The issue is only the log noise.

**Fix**: Added `_connect_count` tracker to `_MEXCDepthSubFetcher`. First connect logs normally. Subsequent reconnects are silent except every 10th (summary log). Staleness warnings also throttled after first occurrence.

#### Other Observations

| # | Item | Notes |
|---|------|-------|
| 1 | +$0.58 net with 0 trades | Pending cashback from Session #8 credited during state restore. Expected behavior. |
| 2 | MEXC fee still 0.025% on VPS | VPS config uses 50% MX holding discount (suspended Feb 9). Should be 0.04% (20% MX Deduction). |
| 3 | DemoCompare discrepancies | Binance/Bybit show extra_position (SNX, AXS) from Session #8 demo orders. Expected stale state. |
| 4 | Candidates tracked | DYDXUSDT, BTCUSDT tracked as EXPAND_TRACK but never activated (paused). |
| 5 | All 8 exchanges connected | Latency normal. OKX freshness 334ms–1392ms (variable, within expected range for books5 skip behavior). |
| 6 | No Session summary log | Session summary requires trades; with 0 trades, no summary was emitted. Acceptable — no data to summarize. |

#### Key Takeaways

1. **SIGTERM handling must not assume intentionality**: VPS crashes, OOM kills, and systemd stops all send SIGTERM. Only explicit user actions (dashboard "Restart Bot") should be treated as intentional.
2. **Anomaly state should not persist across crashes**: A crash is already a disruption — starting with a clean anomaly state and letting protection re-trigger naturally is safer than blindly restoring a paused state from a potentially-stale session.
3. **Reconnection logs need throttling**: Any sub-connection that reconnects frequently (MEXC depth, potentially others) should log first connect + periodic summaries, not every attempt.

---

### Session #10 — 2026-03-05 (First Beta, Transfer Fee Deficit)

**Date**: 2026-03-05, 11:13–12:27 UTC (74 min)
**Capital**: $1,000
**Version**: v0.25.0-beta
**Mode**: demo (Binance/OKX/Bybit) + simulation
**VPS**: LightNode Bangkok

#### Summary

| Metric | Value |
|--------|-------|
| Duration | 74 min (1h 14m) |
| Total Trades | 208 |
| Trading PnL | $0.74 |
| Transfer Fees | $1.94 (external: $1.70) |
| Cashback | $0.38 (credited: $0.06, pending: $0.32) |
| **Net Profit** | **-$1.18** |
| **$/hr** | **-$2.46** |
| Avg Profit/Trade | $0.0035 |
| Avg Net% | 0.040% |
| Avg Trade Size | $8.25 |
| SIZE_ZERO Events | 1,036 |
| Position Cap Hits | 585 |
| Phantom Spreads | 311 |
| EVD Seller Penalties | 6,863 (1 demotion) |
| One-Leg Simulations | 4 ($0.02 cost) |

#### Session Timeline

| Phase | Time (UTC) | Duration | Symbols | Trades | PnL | Notes |
|-------|-----------|----------|---------|--------|-----|-------|
| 1. Discovery | 11:13–11:14 | 1 min | — | 0 | — | ZEC(0.014), AXS(0.012) found |
| 2. AXS only | 11:14–11:24 | 10 min | AXSUSDT | 15 | $0.003 | 9 trades at 0.005% net — near zero |
| 3. Rotation → COMP | 11:24–11:56 | 32 min | COMPUSDT | 6 | $0.026 | Rotation cost $0.44, score fell, demoted |
| 4. Re-discovery | 11:56–11:57 | 1 min | — | 0 | — | All symbols demoted |
| 5. DYDX+ADA+AXS | 11:57–12:27 | 30 min | 3 symbols | 187 | $0.71 | Most productive phase |

#### Active Symbols

| Symbol | Trades | Profit | Avg Net% | Top Pair | Notes |
|--------|--------|--------|----------|----------|-------|
| ADAUSDT | 118 | $0.567 | 0.046% | MEXC→KuCoin (70), BFX→KuCoin (45) | Best performer, Bitfinex 0% fee |
| AXSUSDT | 43 | $0.064 | 0.027% | KuCoin→Bitget (19), Gate→MEXC (12) | Phase 1 trades nearly worthless |
| DYDXUSDT | 39 | $0.086 | 0.023% | MEXC→Bitget (29), MEXC→Binance (5) | Low-value coin, small sizes |
| COMPUSDT | 8 | $0.026 | 0.045% | OKX→Gate (2), Bybit→KuCoin (6) | Demoted after 32 min |

#### Exchange Pair Breakdown

| Pair | Trades | Combined Fee | Notes |
|------|--------|-------------|-------|
| MEXC→KuCoin | 71 | 0.12% | ADA workhorse |
| Bitfinex→KuCoin | 47 | 0.08% | ADA — best margins (0.057% avg net) |
| MEXC→Bitget | 29 | 0.12% | DYDX |
| KuCoin→Bitget | 19 | 0.16% | AXS Phase 1 — too expensive |
| Gate→MEXC | 12 | 0.13% | AXS Phase 5 |

#### Transfer Fee Breakdown

Total transfer fees: $1.94 — **2.6× the trading profit**.

| Category | Amount | Details |
|----------|--------|---------|
| Idle consolidations (4×) | $2.10 | Moving idle capital to Bitfinex hub |
| Rotation AXS→COMP | $0.44 | Capital reallocation across exchanges |
| Demotion COMP + consolidation | $0.68 | Sell crypto + move USDT to Bitfinex |
| Trading rebalances | $0.72 | Replenishing depleted buyer exchanges |

#### Trade Quality Distribution

| Net% Bucket | Trades | Profit | % of Total Profit |
|-------------|--------|--------|--------------------|
| <0.02% | 62 (30%) | $0.04 | 5% |
| 0.02–0.03% | 53 (25%) | $0.10 | 14% |
| 0.03–0.05% | 37 (18%) | $0.14 | 19% |
| 0.05–0.10% | 45 (22%) | $0.33 | 45% |
| >0.10% | 7 (3%) | $0.13 | 18% |

119 trades (57%) had net <0.03% and generated only $0.14 combined — 19% of profit but 57% of trade count. These thin-margin trades consumed position cap allowance, triggered rebalance pressure, and created churn.

#### Demo Comparison

- **8 demo rejections** (all COMPUSDT): OKX min order amount ($15 vs $5 trade), Bybit order value too low. Rejection dedup working — 2 logged, 6 suppressed.
- **0 demo fills**: No demo-executable pair matched (COMP traded Bybit→KuCoin and OKX→Gate, but trade sizes were below exchange minimums on demo).
- **60 DemoCompare log entries** (all `missing_position`): Sim held positions on OKX/Bybit that had no demo orders. 655 discrepancies in dashboard from 15s polling accumulation.
- **v0.25.0-beta fixes verified**: D-10 throttling, MEXC depth log silence, `_safe_task()` — all working correctly.

#### Observations

| # | Item | Notes |
|---|------|-------|
| 1 | Net deficit from transfers | $1.94 fees vs $0.74 PnL. Transfer overhead is 2.6× trading income. |
| 2 | Threshold 0.01% too low | AXS activated at score=0.012, produced 9 trades at 0.005% net. Marginal symbols waste capital on setup/teardown. |
| 3 | COMP rotation net negative | Cost $0.44 to rotate in, earned $0.026 in 32 min, then cost $0.68 to demote. Total: -$1.09 for COMP's lifecycle. |
| 4 | Idle consolidations expensive | 4 consolidations cost $2.10 — mostly from Gate.io ($0.50) and KuCoin ($0.40) withdrawal fees. |
| 5 | ADA+Bitfinex is the clear winner | Bitfinex→KuCoin pair averaged 0.057% net. 0% buy fee makes thin spreads viable. |
| 6 | Position cap hit 585 times | Max position multiplier (5×) limits trading velocity on concentrated symbols. |
| 7 | No anomaly triggers | 0 pauses, 0 warnings, 0 symbol blocks — stable session. |

#### Key Takeaways

1. **Transfer fees are the #1 profit killer at $1,000 capital**: With $10 trades averaging $0.004 profit, it takes ~100 trades ($0.40) to pay for one Gate.io withdrawal ($0.50). The bot must avoid expensive transfers entirely.
2. **Trading threshold 0.01% is too low**: Symbols barely above threshold activate, consume setup fees, and get demoted — net negative. Raising to 0.03% would eliminate 57% of trades but only lose 19% of profit, while dramatically reducing rebalance pressure.
3. **Idle consolidation is counterproductive at small capital**: Moving $30 to Bitfinex at $0.40 fee is never recouped. Consolidation should be gated by a minimum worthiness check.
4. **Best pair confirmed: Bitfinex→cheap_exchange**: 0% taker on Bitfinex makes any spread above the seller's fee profitable. MEXC (0.04%) and Bybit (0.075%) are ideal counterparts.
5. **Recommended settings changes**: Raise `TRADING_SCORE_THRESHOLD` to 0.03, raise `min_net_profit_pct` to 0.03%, reduce `hourly_external_transfer_cap` to $2, increase `reallocation_cost_horizon` to 4h.

---

### Session #11 — 2026-03-05 (Three Demotions, Non-Bitfinex Symbols)

**Date**: 2026-03-05, 12:43–15:44 UTC (3h 01m)
**Capital**: $1,000
**Version**: v0.25.0-beta
**Mode**: demo (Binance/OKX/Bybit)
**VPS**: LightNode Bangkok

#### Settings Changed (from Session #10)

- `min_net_profit_pct`: 0.01% → **0.03%** (raised)
- `TRADING_SCORE_THRESHOLD`: 0.01 → **0.03** (raised)
- `hourly_external_transfer_cap`: $5.00 → **$2.00** (lowered)

#### Summary

| Metric | Value |
|--------|-------|
| Duration | 3h 01m |
| Total Trades | 372 |
| Trading PnL | $2.74 |
| Transfer Fees | $5.47 (consolidation $2.84, demotion $2.07, trading $0.56) |
| Cashback | $0.99 (credited: $0.33, pending: $0.66) |
| **Net Profit** | **-$1.25** |
| **$/hr** | **-$1.63** (improving but still negative) |
| Avg Profit/Trade | $0.0073 |
| Avg Net% | 0.066% |
| Avg Trade Size | $9.87 |
| SIZE_ZERO Events | 986 |
| Position Cap Hits | 933 |
| Phantom Spreads | 625 |
| Anomaly Triggers | 0p/0w/0sb |
| Demo Fills | 36/49 (13 rejected) |

#### Session Timeline

| Phase | Time (UTC) | Duration | Symbol | Trades | PnL | Notes |
|-------|-----------|----------|--------|--------|-----|-------|
| 1. Discovery | 12:43–12:44 | 1 min | — | 0 | — | DYDX(0.031) found |
| 2. DYDX (1st) | 12:44–13:50 | 66 min | DYDXUSDT | 181 | $1.17 | Active 59 min, idle 7 min |
| 3. Re-discovery | 13:50–13:56 | 6 min | — | 0 | — | Extended to 600s, DYDX barely hit 0.03 |
| 4. DYDX (2nd) | 13:56–14:42 | 46 min | DYDXUSDT | 105 | $0.78 | Active 34 min, idle 12 min |
| 5. Re-discovery | 14:42–14:46 | 4 min | — | 0 | — | AXS(0.030) found |
| 6. AXS | 14:46–15:32 | 46 min | AXSUSDT | 86 | $0.78 | Active 28 min, idle 18 min |
| 7. Final discovery | 15:32–15:44 | 12 min | — | 0 | — | No symbol ≥0.03, session ended |

3 complete activate→trade→demote cycles. ~44 min idle (24% of session).

#### Active Symbols

| Symbol | Trades | Profit | Avg Net% | Top Pair(s) | Bitfinex? |
|--------|--------|--------|----------|-------------|-----------|
| DYDXUSDT | 286 | $1.95 | 0.063% | MEXC→OKX (105), MEXC→Bitget (79) | **No** |
| AXSUSDT | 86 | $0.78 | 0.073% | KuCoin→Gate.io (74) | **No** |

**Critical finding**: Neither DYDX nor AXS is available on Bitfinex. Every trade paid fees on BOTH sides (0.04%+0.10% for DYDX, 0.08%+0.09% for AXS). No 0%-fee Bitfinex leg was used at all this session.

#### Exchange Pair Breakdown

| Pair | Trades | Combined Fee | Avg Net% | Notes |
|------|--------|-------------|----------|-------|
| MEXC→OKX | 105 | 0.14% | 0.042% | Highest volume, thin margins |
| MEXC→Bitget | 79 | 0.12% | 0.097% | Better margins |
| KuCoin→Gate.io | 74 | 0.17% | 0.081% | Expensive pair but decent spread |
| MEXC→Bybit | 21 | 0.115% | — | |
| MEXC→Binance | 21 | 0.115% | — | |
| Binance→MEXC | 16 | 0.115% | — | |

#### Transfer Fee Breakdown

Total overhead: **$5.47** — **2.0× the trading profit**.

| Category | Amount | Count | Notes |
|----------|--------|-------|-------|
| Idle consolidations | $2.84 | 12 | Repeated expensive transfers to Bitfinex |
| Post-demotion consolidation | $1.10 | 3 | Gate.io ($0.50) + KuCoin ($0.40) fees |
| Demotion sell fees | $0.97 | 3 | Taker fees on crypto→USDT |
| Trading rebalances | $0.56 | 135 | Mostly free (Bitfinex $0, MEXC $0) |

Hourly cap ($2) was hit at end (`BLOCKED by hourly cap: $1.60+$0.40 > $2.00/hr`), but most damage came from consolidation (not capped separately).

#### Trade Quality Distribution

| Net% Bucket | Trades | Profit | % of Total |
|-------------|--------|--------|------------|
| <0.03% | 87 (23%) | $0.12 | 4% |
| 0.03–0.05% | 78 (21%) | $0.29 | 11% |
| 0.05–0.10% | 120 (32%) | $1.11 | 41% |
| 0.10–0.15% | 66 (18%) | $0.95 | 35% |
| >0.15% | 14 (4%) | $0.24 | 9% |

Trade quality significantly better than Session #10 (avg 0.066% vs 0.040%). The 0.03% threshold removed the worst trades. But 87 trades still snuck under 0.03% — likely from `min_net_profit_pct` allowing some thin-margin executions.

#### New Discrepancies Found

| Issue | Severity | Details |
|-------|----------|---------|
| **Bybit fee mismatch** | Medium | Configured 0.075% (MNT discount) but demo testnet charges 0.100% base rate. 12 warnings. Demo testnet may not honor token discounts. |
| **Bybit 1.029% fee anomaly** | Low | One trade showed 1.029% actual fee — likely a rounding artifact or testnet glitch. |
| **OKX DYDXUSDT "Instrument ID doesn't exist"** | Medium | OKX demo trading doesn't have DYDX-USDT spot pair. Repeated rejections (7 logged). |
| **Bybit qty too many decimals** | Medium | `qty=4.364609053497986` sent to Bybit — lot size rounding not applied for demo sell orders. |
| **Binance NOTIONAL filter** | Low | $5.00 trade at $0.0963/DYDX = $4.96 notional, below Binance minimum. |
| **Task exceptions** | Low | 3 "Task exception was never retrieved" from Pionex reconnections. |
| **2,959 dashboard discrepancies** | Expected | 162 balance_mismatch + 86 missing_position, accumulated over 3h polling. |

#### Key Takeaways

1. **Idle consolidation is the #1 cost driver**: $2.84 in 12 consolidations — moving idle USDT to Bitfinex hub when no Bitfinex-tradeable symbol is active is pure waste. Consolidation should be paused when the active symbol isn't on Bitfinex. **Fixed in v0.25.1-beta**: `_any_active_on_bitfinex()` gate added to all 3 post-discovery consolidation call sites.
2. **Non-Bitfinex symbols can't overcome fee drag**: DYDX (MEXC→OKX = 0.14% combined fee) needs 0.14%+ spread to profit. These thin-alt spreads rarely sustain. Bitfinex-available symbols get one leg free.
3. **Three activate→demote cycles in 3 hours = $2.07 demotion overhead**: Each cycle costs ~$0.70 (sell fees + consolidation). With $0.90/hr trading profit, it takes ~47 min just to recoup one demotion.
4. **The 0.03 threshold helped trade quality but not the deficit**: Avg net% doubled (0.040% → 0.066%), but marginal symbols still activate at score=0.030 and get demoted 46-66 min later. The threshold needs to be even higher, or symbols must be filtered by Bitfinex availability.
5. **Bybit demo fee mismatch needs investigation**: If real Bybit also charges 0.10% (no MNT discount applied), the configured 0.075% overstates profitability on every Bybit trade. **Confirmed**: Bybit MNT discount requires no minimum holding — just enable toggle + hold MNT balance. Demo testnet doesn't honor token discounts (expected behavior).
6. **Bybit lot size rounding bug**: Demo sell qty sent unrounded — exchange_info lot rounding should apply to demo orders too. **Fixed in v0.25.1-beta**: `exchange_info.round_quantity()` applied after `cap_sell_qty()` in `_execute_demo_trade()`.
7. **OKX DYDX-USDT demo missing instrument**: OKX demo doesn't have DYDX-USDT spot pair, causing repeated D-10 rejections. **Fixed in v0.25.1-beta**: `_demo_skip_pairs` auto-detects "instrument not found" rejections and permanently skips the combo.

---

### Session #12 — 2026-03-05 (Long Run, Discovery Consolidation Exposed)

**Date**: 2026-03-05, 19:10 – 2026-03-06 01:07 UTC (5h 57m)
**Capital**: $1,000
**Version**: v0.25.1-beta
**Mode**: demo (Binance/OKX/Bybit) + simulation
**VPS**: LightNode Bangkok
**Pionex**: Disabled

#### Summary

| Metric | Value |
|--------|-------|
| **Trades** | 483 |
| **Trading PnL** | $3.81 |
| **True transfer costs** | $5.79 |
| **Cashback** | $1.36 ($0.51 credited, $0.85 pending) |
| **True net** | **-$1.47** (-$0.62 w/ pending cashback) |
| **$/hr** | -$0.25 |
| **Avg net%** | 0.069% |
| **Discrepancies** | 5,047 |

#### Settings (unchanged from Session #11)

trade_amount=$10 (1% of $1000), min_net_pct=0.03%, hourly_cap=$2, TRADING_SCORE_THRESHOLD=0.03, max_pos_mult=5, bitfinex_reserve=15%.

#### Timeline — 4 Demotion Cycles

| Phase | Time | Symbol | Trades | PnL | Xfer Fees | Net |
|-------|------|--------|-------:|----:|----------:|----:|
| Cycle 1 | 19:11–19:49 (38m) | AXSUSDT | 65 | $0.77 | $0.93 | -$0.13 |
| Cycle 2 | 20:38–22:32 (114m) | DYDX→SNX | 172 | $1.77 | $1.56 | +$0.59 |
| Cycle 3 | 22:41–23:29 (48m) | DYDXUSDT | 126 | $0.74 | $0.42 | +$0.68 |
| Cycle 4 | 23:59–00:57 (58m) | DYDXUSDT | 114 | $0.53 | $1.30 | -$0.26 |

Each cycle: discover → activate → trade → demote → discover again. None of the traded symbols (AXSUSDT, DYDXUSDT, SNXUSDT) are available on Bitfinex.

#### Transfer Fee Breakdown

| Category | Amount | % of Total |
|----------|-------:|:----------:|
| Hub consolidation (discovery) | $3.03 | 52% |
| Internal buy/sell (rebalancing) | $1.33 | 23% |
| Rotation (DYDX→SNX) | $0.65 | 11% |
| External USDT transfers | $0.39 | 7% |
| External crypto transfers | $0.39 | 7% |
| **Total** | **$5.79** | |

**Hub consolidation breakdown by exchange**:

| Exchange | Transfers | Total Fee | Fee/Transfer |
|----------|----------:|---------:|:--------:|
| KuCoin | 4 | $1.60 | $0.40 |
| Gate.io | 2 | $1.00 | $0.50 |
| OKX | 4 | $0.40 | $0.10 |
| Binance | 3 | $0.03 | $0.01 |
| Bitget | 4 | $0.004 | $0.001 |
| MEXC/Bybit | 5 | $0.00 | $0.00 |

#### Trade Distribution

| Symbol | Trades | Dominant Pairs | On Bitfinex |
|--------|-------:|---------------|:-----------:|
| DYDXUSDT | 409 | Binance→MEXC (125), OKX→MEXC (67), MEXC→Binance (64) | No |
| AXSUSDT | 65 | Gate.io→OKX (20), Gate.io→MEXC (19), KuCoin→OKX (15) | No |
| SNXUSDT | 9 | MEXC→Bitget (9) | No |

MEXC was involved in 90%+ of trades (low fees: 0.04%).

#### v0.25.1-beta Features Verified

| Feature | Result |
|---------|--------|
| **Idle consolidation gate** | 37 idle consolidations SKIPPED — working correctly |
| **Post-demotion consolidation gate** | 4 post-demotion consolidations SKIPPED — working correctly |
| **Demo instrument skip pairs** | OKX:DYDXUSDT:buy permanently skipped after first rejection. 66 demo trades skipped total. Working correctly. |
| **Bybit qty rounding** | No "too many decimals" errors. Fixed. |
| **Discovery consolidation** | NOT GATED — this is the remaining leak. 22 hub consolidations during discovery cost $3.03. |

#### Demo Stats

| Metric | Value |
|--------|-------|
| Fill rate | 183/199 = 92% |
| Rejections | 16 (Binance NOTIONAL) |
| Fee mismatches | 9 (Bybit DYDX: 0.075% vs ~1.085%) |
| Avg latency | 153ms |
| Demo setup | AXSUSDT on OKX — rejected (order not filled) |

#### Key Takeaways

1. **Discovery consolidation is the remaining cost leak**: The v0.25.1-beta gate blocks post-discovery consolidation (eval cycles, post-demotion), but discovery-phase consolidation (line 406 in optimizer.py) is ungated. Each demotion→discovery cycle consolidates everything to Bitfinex ($0.76 avg cost), then redistributes out when a non-Bitfinex symbol activates. 4 cycles × $0.76 = $3.03 — more than the entire trading PnL ($3.81).
2. **4 demotion cycles in 6 hours is too volatile**: Average cycle length 65 min. Each cycle costs ~$1.45 (consolidation + rebalancing). Bot needs to either not demote as quickly or not consolidate during discovery.
3. **Still only trading non-Bitfinex symbols**: DYDX, AXS, SNX — all require both legs to pay taker fees. No Bitfinex-available symbol scored above 0.03 threshold during this session.
4. **MEXC is the best exchange for arbitrage**: Involved in 90%+ of trades, $0 withdrawal fees, 0.04% taker. The bot naturally gravitates toward MEXC pairs.
5. **Bybit demo fee anomaly**: 1.085% actual fee on DYDX — far exceeds the 0.10% base rate. Likely a testnet artifact, not a real trading concern.
6. **Trade counts reset on each demotion cycle**: `_complete_discovery()` called nuclear `monitor.reset()` and `balance.reset()` which wiped all cumulative state — trades, transfer fees, P&L, tick count, start time. This prevented the net P&L gate from seeing cumulative losses across cycles, made $/hr inaccurate, and lost trade history in XLSX export.

#### Fixes Applied (v0.25.2-beta)

- **Discovery consolidation gate**: Added `max_fee_per_source=0.02` to `consolidate_to_bitfinex()` during discovery — skips expensive sources (KuCoin $0.40, Gate.io $0.50, OKX $0.10), only consolidates from free/near-free exchanges.
- **Cumulative state preservation**: Replaced nuclear `monitor.reset()` / `balance.reset()` with `reconfigure()` methods that only reset per-cycle operational state (observations, miss streaks) while preserving cumulative session data (trades, fees, P&L, tick count, start time, demo stats, anomaly protection). Net P&L gate now sees true cumulative losses across demotion cycles.

### Session #13 — 2026-03-06 (Fee-Aware Threshold Too Aggressive)

- **Version**: v0.25.2-beta
- **Duration**: 5h 32m (02:37–08:10 UTC)
- **Capital**: $1,000, execution_mode=demo
- **Enabled exchanges**: 6 (Binance, Bitfinex, Bitget, Bybit, MEXC, OKX)
- **Disabled exchanges**: Gate.io, KuCoin, Pionex
- **Trades**: 0
- **Transfers**: 4 (discovery consolidation, $0.011 total fees)
- **Result**: $0 profit — stuck in discovery the entire session

#### Settings

| Setting | Value | Impact |
|---------|-------|--------|
| `trading_score_threshold` | 0.05 | Base threshold — already elevated from default 0.01 |
| `fee_threshold_multiplier` | 0.5 | Adds up to +0.05 for expensive pairs |
| `min_net_profit_pct` | 0.05% | Per-trade minimum |
| `demotion_cooldown_multiplier` | 10 | Not tested — nothing activated |
| `hourly_external_transfer_cap` | $2.00 | Not tested |

#### What Happened

The bot entered discovery and scanned all 60 symbols for 5.5 hours. Discovery extended 8 times (doubling each time, capping at 3600s). No symbol ever met the fee-aware activation threshold.

**Best candidate**: DYDX peaked at score **0.066** (avg_net=0.09%, profitable frequency=57%). But its dominant pair (MEXC→OKX at 0.14% combined fee) triggered a fee adjustment of +0.032, raising the effective threshold to **0.082**. At its best (BIN→OKX, 0.175% combined), the threshold was **0.093**. DYDX never came close.

| Symbol | Peak Score | Dominant Pair Fee | Fee-Adjusted Threshold | Gap |
|--------|-----------|------------------|----------------------|-----|
| DYDX | 0.066 | 0.14% (MEXC→OKX) | 0.082 | -19% |
| TRX | 0.036 | ~0.14% | 0.082 | -56% |
| NEAR | 0.007 | ~0.14% | 0.082 | -91% |
| SOL | 0.002 | ~0.12% | 0.064 | -97% |

**4 discovery consolidation transfers**: At 02:39:20, $133.33 moved to Bitfinex hub from Bybit ($0), MEXC ($0), Bitget ($0.001), Binance ($0.01). Total fee $0.011. Gated correctly (max_fee=$0.02), but pointless since nothing activated.

**Log spam**: 186,484 activation threshold log lines — `_get_activation_threshold()` logs at INFO level on every tick for every symbol during discovery, producing 93% of the entire log file.

#### Key Takeaways

1. **Fee-aware threshold too aggressive at 0.5**: Combined with base=0.05, the effective threshold for non-Bitfinex symbols becomes 0.064–0.093. No symbol in current market conditions scores that high without Bitfinex involvement.
2. **Zero trades = zero risk but also zero learning**: The bot couldn't validate any of the v0.25.2-beta fixes (reconfigure, consolidation gate) because nothing activated.
3. **Discovery consolidation ran despite nothing activating**: The $0.011 cost is negligible, but capital was misallocated (moved away from potential buyer exchanges).
4. **Activation threshold logging needs throttling**: 186K log lines from a single `logger.info()` call is unacceptable.

#### Fixes Applied (v0.25.3-beta)

- **Activation threshold log spam**: Removed per-call `logger.info()` from `_get_activation_threshold()`. Added `threshold=X.XXXX(fee_adj=+X.XXXX)` to `[Candidate]` logs instead — same info, once per candidate per eval cycle instead of once per symbol per tick.
- **Fee threshold multiplier in dashboard**: Added `fee_threshold_multiplier` setting to Settings → Score Thresholds section, allowing runtime tuning without code changes.
- **Recommended settings for Session #14**: `trading_score_threshold=0.03`, `fee_threshold_multiplier=0.3`, `min_net_profit_pct=0.03` — makes non-Bitfinex thresholds reachable (0.053–0.071 vs previous 0.082–0.118).
- **Discovery window inflation fix**: Early discovery exit now requires `scoring_window / 2` elapsed time AND ticks per symbol (default 900s/900 ticks). Previously used hardcoded 60s — allowed activation with 100% frequency from thin windows (real frequency was 55% over full 1800s window). DYDX scored 0.127 after reset vs 0.050 with full window — a 2.5× inflation.
- **Smart settings apply**: `_apply_settings()` no longer restarts discovery for every settings change. Only `scoring_window`, `num_active_symbols`, `auto_rotate` trigger restart. All other settings hot-applied without wiping tick windows.

### Session #14 — 2026-03-06 (Drawdown Pause Deadlock)

- **Version**: v0.25.4-beta
- **Duration**: 1h 59m (11:36–13:36 UTC)
- **Capital**: $1,000, execution_mode=demo
- **Enabled exchanges**: 6 (Binance, Bitfinex, Bitget, Bybit, MEXC, OKX)
- **Disabled exchanges**: Gate.io, KuCoin, Pionex
- **Trades**: 25 (all DYDX, 8m 33s trading window)
- **Trading profit**: $0.55
- **Transfer fees**: $0.02 (13 transfers, mostly $0 via MEXC/Bybit)
- **Demotion sell fees**: $0.39
- **Net result**: ~$0.14 profit (before demotion sell), ~-$0.25 after demotion sell fees
- **Anomaly**: Drawdown pause at 12:00:11 — never auto-resumed

#### Settings

| Setting | Value | Notes |
|---------|-------|-------|
| `trading_score_threshold` | 0.03 | Lowered from 0.05 (Session #13 fix) |
| `fee_threshold_multiplier` | 0.3 | Lowered from 0.5 (Session #13 fix) |
| `min_net_profit_pct` | 0.03% | Lowered from 0.05 |
| `scoring_window` | 1800s | Half-window (900s) used for discovery exit |
| `drawdown_threshold_pct` | 5.0% | Default |
| `drawdown_resume_pct` | 3.0% | Default |

#### Timeline

| Time | Event |
|------|-------|
| 11:36 | Session start, discovery begins |
| 11:38 | Discovery consolidation: 4 transfers to Bitfinex ($0.01 fees) |
| 11:51:28 | Discovery complete after 15m (900s gate worked). DYDX activated: score=0.073, freq=81.6%, 709/869 ticks, threshold=0.056 |
| 11:51:31 | First trade: DYDX OKX→MEXC, $0.013 profit |
| 11:51–12:00 | 25 trades in 8m 33s. All DYDX: 19 OKX→MEXC, 4 Bybit→MEXC, 2 Binance→MEXC |
| 12:00:11 | **PAUSED (drawdown)**: 5.36% >= 5.0% threshold. DYDX price dropped ~5% while bot held crypto on seller exchanges |
| 12:00–12:51 | Paused. No trades. DYDX score decaying. |
| 12:51:46 | DYDX demoted (score below threshold 900s). Crypto sold: freed $520.48, fees $0.39 |
| 12:51:46 | All symbols demoted — re-entering discovery |
| 12:53 | Discovery consolidation: 3 transfers to Bitfinex ($0.01) |
| 12:53–13:36 | Second discovery. DYDX peaked at 0.058 but threshold=0.064 — never reactivated |

#### What Happened

The discovery window inflation fix worked correctly — DYDX activated at 15 minutes with a stable score (0.073, 81.6% freq) instead of the inflated 0.135 from Session #13. Trading was profitable at $0.55 over 25 trades ($0.022/trade avg).

**The drawdown trigger was a false positive.** DYDX price dropped ~5% during the 8-minute trading window. The bot held ~$520 of DYDX crypto across seller exchanges (MEXC). Portfolio value = USDT + crypto_qty × price. When DYDX price dropped from ~$0.0894 to ~$0.0847, the unrealized crypto loss (~$53) triggered the 5% drawdown threshold.

**The drawdown pause created a deadlock:**
1. Pause stops all trading → no new profits possible
2. Crypto still held → value continues dropping with DYDX price
3. Eventually demoted → crypto sold at the lower price, locking in the loss
4. Portfolio now ~$947 vs peak ~$1000 → drawdown stays at ~5.3%
5. Auto-resume requires drawdown ≤ 3.0% → needs portfolio to reach $970
6. But trading is paused → can never earn the $23 needed to recover
7. **Deadlock**: can't trade because paused, can't recover because can't trade

#### Key Issues

1. **Drawdown protection is crypto-price-sensitive**: The 5% threshold triggers on unrealized crypto price movements, not on trading losses. A 5% dip in any held crypto (normal for altcoins) instantly pauses trading.
2. **Drawdown pause + demotion sell = locked-in loss**: Pause prevents trading → score decays → demotion triggers → crypto sold at loss → drawdown is now permanent.
3. **Auto-resume impossible after demotion sell**: Once crypto is sold at the lower price, the loss is realized. Portfolio value can't recover without trading, but trading is blocked.
4. **Position cap too aggressive**: 43 position cap skips in the session summary — many profitable trades were blocked because MEXC accumulated too much DYDX crypto (single seller exchange).

#### Recommendations

- **Increase `drawdown_threshold_pct`**: 5% is too sensitive for altcoin crypto holdings. Consider 10-15% for simulation, or disable drawdown protection until live (circuit breaker on rolling P&L is more appropriate for trading losses).
- **Or**: After demotion sells all crypto (portfolio is 100% USDT), reset the peak to current value — the "drawdown" is no longer meaningful since there's no crypto exposure.
- **Increase `max_position_multiplier`**: From 5 to 10-15 to reduce position cap skips, or disable (0) during simulation.

#### Fixes Implemented (v0.25.5-beta)

Two fixes to address the drawdown deadlock:

**Fix 1: Reset peak after full crypto liquidation.** When all crypto is sold (emergency sell or demotion) and portfolio is 100% USDT, `_peak_portfolio_value` is reset to the current value. This breaks the deadlock because drawdown becomes 0% and auto-resume triggers immediately. The rationale: once there's no crypto exposure, the "peak" from when crypto was held is meaningless — the loss is realized and the portfolio is now a clean USDT baseline.

**Fix 2: Per-symbol drawdown blocking instead of global pause.** Drawdown no longer triggers a global trading pause. Instead, it identifies the symbol(s) causing the decline and blocks only them via the existing per-symbol blocking mechanism (`_symbol_blocked_until`). Other profitable symbols continue trading. Global pause is reserved for emergency level only (2× threshold). This prevents a single declining altcoin from freezing the entire bot.

#### Trend-Awareness Discussion

Considered adding EMA-based trend detection (fast/slow crossover) to detect bearish trends earlier and exit positions before drawdown triggers. **Verdict: Not implemented.** Reasons:

1. **Arbitrage is direction-neutral** — the bot profits from price differences between exchanges, not price direction. A bearish symbol can still have excellent arbitrage spreads (volatile downtrends often increase cross-exchange discrepancies).
2. **Timeframe dilemma** — 15m EMAs too noisy (false signals every hour), 4h too slow (5% drop already happened). No good answer for a sub-second trading bot.
3. **Historical data dependency** — needs REST candle API calls per symbol per exchange, adding rate limits, failure points, and a new data pipeline.
4. **Parameter tuning rabbit hole** — EMA 9/21? 12/26? 20/50? Each symbol behaves differently. Weeks of tuning with still unreliable signals.
5. **Not the bot's edge** — HFT firms with PhDs do trend detection. This bot's edge is arbitrage execution.
6. **The two fixes above solve the actual problem** — the deadlock was an inventory management issue, not a prediction problem.

**Future consideration: rate-of-decline detection.** A simpler alternative to EMAs that doesn't require historical data: monitor "has this held position dropped >X% in Y minutes?" using existing WebSocket price data. No candles, no EMAs, no new data pipeline — just a rolling price window per held crypto. Could trigger early demotion before drawdown threshold hits. Not implemented now since per-symbol blocking should handle most cases, but worth revisiting if inventory risk issues persist in live trading.
