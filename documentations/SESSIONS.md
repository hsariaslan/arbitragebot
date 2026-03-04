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
**Capital**: $1,000 (reduced from $3,000 — testing smaller capital)
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
| Bitfinex buyer + altcoin strong/very_strong | Session #1 | 3 | $66.97 | STRK. S1: 16h/$81.91/hr ($3k), S2: 18m/$107.95/hr ($3k), S3: 1h38m/$11.06/hr ($1k) |

### Exchange Performance Summary

| Exchange | Role | Sessions as Top Role | Notes |
|----------|------|---------------------|-------|
| Bitfinex | Buyer | 3/3 | 0% fee + $0 withdrawals = dominant buyer. S1: 89%, S2: STRK buyer, S3: 68.6% |
| OKX | Seller | 3/3 | S1: most trades (1,348). S2: secondary STRK seller. S3: primary STRK seller (165 trades) |
| MEXC | Seller/Buyer | 3/3 | S1: highest avg ($0.3683). S2: primary STRK seller. S3: secondary STRK buyer+seller |
| Bybit | Seller/Fixed | 1/3 | S1: 760 trades, $252.86. S2: DEAD (Bug #1). S3: **Fixed, healthy**, but not in dominant pairs |
| Bitget | Seller | 1/3 | S1: 496 trades. S2-S3: $0 allocated (not in dominant pairs) |
| KuCoin | Seller | 1/3 | S1: 344 trades. S2-S3: minimal/no allocation |
| Gate.io | Seller | 2/3 | S1: limited by cap. S2: AXS seller. S3: AXS seller (before demotion) |
| Binance | Minimal | 1/3 | S1: 19 trades. S2-S3: $0 allocated |
| Pionex | Not seen | 0/3 | Disabled in Fee Management. Never traded across all sessions |

### Symbol Performance History

| Symbol | Sessions Active | Best $/hr | Avg $/hr | Typical Tier | Best Buyer | Notes |
|--------|----------------|-----------|----------|-------------|------------|-------|
| STRKUSDT | 3 | $107.95 | $66.97 | strong-very_strong | Bitfinex | Persistent structural spread. S1: 16h, S2: 18m, S3: 1h37m. $1k capital bottlenecks at ~30min |
| AXSUSDT | 2 | $107.95* | — | normal | MEXC/Gate.io | Thin margins (0.04% avg net). Demoted both sessions. *$/hr shared with STRK |
| DOTUSDT | 1 | — | — | normal | Bitfinex | S3: Expanded then demoted after 24m, 0 trades. Score faded. |

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
