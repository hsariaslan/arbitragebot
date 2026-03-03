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
**Version**: v0.15.2-alpha → v0.15.3-alpha (pre-slippage simulation)
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

## Pattern Tracking

### Confirmed Profitable Patterns

| Pattern | First Seen | Sessions | Avg $/hr | Notes |
|---------|-----------|----------|----------|-------|
| Bitfinex buyer + altcoin strong/very_strong | Session #1 | 1 | $81.91 | STRK. Persistent structural spread. 16h+ sustained. |

### Exchange Performance Summary

| Exchange | Role | Sessions as Top Role | Notes |
|----------|------|---------------------|-------|
| Bitfinex | Buyer | 1/1 | 0% fee + $0 withdrawals = dominant buyer (89% of trades, 99.7% of profit) |
| OKX | Seller | 1/1 | Most trades as seller (1,348), highest total profit ($426) |
| MEXC | Seller/Buyer | 1/1 | Highest avg profit as seller ($0.3683), also secondary buyer (11%) |
| Bybit | Seller | 1/1 | 3rd most trades (760), solid avg profit ($0.3327) |
| Bitget | Seller | 1/1 | 4th most trades (496), consistent ($0.3185/trade) |
| KuCoin | Seller | 1/1 | Moderate volume (344), $0.40 withdrawal fee |
| Gate.io | Seller | 1/1 | Limited by $5/hr transfer cap, good avg ($0.3201) |
| Binance | Minimal | 1/1 | Only 19 trades, rarely has STRK advantage |
| Pionex | Not seen | 0/1 | Not in any trades this session |

### Symbol Performance History

| Symbol | Sessions Active | Best $/hr | Avg $/hr | Typical Tier | Best Buyer | Notes |
|--------|----------------|-----------|----------|-------------|------------|-------|
| STRKUSDT | 1 | $81.91 | $81.91 | very_strong | Bitfinex | Persistent structural spread, 16h+ sustained |

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
