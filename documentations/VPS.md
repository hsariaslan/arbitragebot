# VPS Infrastructure & Deployment Strategy

Optimal VPS placement for minimizing latency across 9 exchanges, accounting for geo-restrictions and cost.

## Exchange Server Locations

| Exchange | Server Location | Cloud Provider |
|----------|----------------|:--------------:|
| Binance | **Tokyo, Japan** | AWS ap-northeast-1 |
| OKX | **Hong Kong** | Alibaba Cloud / AWS HK |
| Bybit | **Singapore** | AWS ap-southeast-1 |
| Bitget | **Singapore** | AWS ap-southeast-1 |
| KuCoin | **Singapore** | AWS |
| Gate.io | **Singapore** | AWS ap-southeast-1 |
| MEXC | **Singapore** | AWS ap-southeast-1 |
| Pionex | **Virginia, USA** (likely) | AWS us-east-1 (via Cloudflare) |
| Bitfinex | **Zug, Switzerland** | Bare-metal (Market Synergy) |

## Full Latency Matrix (RTT in ms)

| Exchange | Tokyo | Bangkok | Singapore | Frankfurt | Virginia |
|----------|:-----:|:-------:|:---------:|:---------:|:--------:|
| Binance | **<1** | ~90 | ~68 | ~245 | ~170 |
| OKX | ~35 | ~60 | ~35 | ~150 | ~200 |
| Bybit | ~68 | ~25 | **<1** | ~160 | ~230 |
| Bitget | ~68 | ~25 | **<1** | ~160 | ~230 |
| KuCoin | ~68 | ~25 | **<1** | ~160 | ~230 |
| Gate.io | ~68 | ~25 | **<1** | ~160 | ~230 |
| MEXC | ~68 | ~25 | **<1** | ~160 | ~230 |
| Pionex | ~160 | ~200 | ~230 | ~90 | **~5** |
| Bitfinex | ~250 | ~220 | ~180 | **~5** | ~80 |

## Geo-Restriction Matrix

Exchanges blocked from each VPS location (X = blocked, ! = risky):

| Exchange | Tokyo | Bangkok | Singapore | Frankfurt | Virginia |
|----------|:-----:|:-------:|:---------:|:---------:|:--------:|
| Binance | OK | OK | OK | OK | **X** (US) |
| OKX | OK | OK | OK | OK | **X** (US) |
| Bybit | **!** (exiting JP 2026) | OK | **X** | OK | **X** (US) |
| Bitget | OK | OK | **X** | OK | **X** (US) |
| KuCoin | OK | OK | **X** | OK | **X** (US) |
| Gate.io | OK | OK | OK | OK | **X** (US) |
| MEXC | **!** (FSA risk) | OK | **X** | OK | **X** (US) |
| Pionex | **X** (KYC-blocked) | OK | **X** | OK (monitor EU) | **X** (US) |
| Bitfinex | **!** (FSA warnings) | OK | OK | OK | **X** (US) |

**Summary of blocked locations**:
- **Tokyo**: Pionex KYC-blocked. MEXC/Bybit/Bitfinex at regulatory risk from Japan FSA.
- **Bangkok**: All 9 exchanges accessible. No restrictions.
- **Singapore**: Bybit, Bitget, KuCoin, MEXC, Pionex all blocked. Only 4/9 accessible.
- **Frankfurt**: All 9 accessible. Germany not on any exchange's restricted list. Monitor EU MiCA for Pionex.
- **Virginia**: All exchanges blocked (US).

## VPS Combinations

### Option A: 2 VPS — Practical Minimum (~$15/mo)

| VPS | Location | Exchanges | Worst Latency | Cost |
|-----|----------|-----------|:-------------:|:----:|
| 1 | **Tokyo** | Binance (<1ms), OKX (35ms), Bybit (68ms), Bitget (68ms), KuCoin (68ms), Gate.io (68ms) | 68ms | ~$7.50 |
| 2 | **Bangkok** | MEXC (25ms), Pionex (~200ms), Bitfinex (~220ms) + **Orchestrator** | ~220ms | ~$7.50 |

**Pros**: Cheapest option. Handles all geo-restrictions. 6 exchanges at <68ms.
**Cons**: Bitfinex at ~220ms and Pionex at ~200ms from Bangkok. Inter-VPS latency Bangkok→Tokyo: ~90ms.

**Architecture**: Bangkok orchestrator collects prices from all VPS, detects arbitrage, dispatches orders. Tokyo VPS runs 6 exchange fetchers + order execution for those exchanges.

### Option B: 3 VPS — Balanced (~$22.50/mo) ★ Recommended

| VPS | Location | Exchanges | Worst Latency | Cost |
|-----|----------|-----------|:-------------:|:----:|
| 1 | **Tokyo** | Binance (<1ms), OKX (35ms) | 35ms | ~$7.50 |
| 2 | **Bangkok** | Bybit (25ms), Bitget (25ms), KuCoin (25ms), Gate.io (25ms), MEXC (25ms), Pionex (~200ms) + **Orchestrator** | ~200ms | ~$7.50 |
| 3 | **Frankfurt** | Bitfinex (~5ms) | ~5ms | ~$7.50 |

**Pros**: Bitfinex latency drops from ~220ms to ~5ms (50x improvement). 8/9 exchanges under 68ms. Bitfinex is the most valuable exchange (0% fees) — deserves dedicated low-latency connection.
**Cons**: Pionex still ~200ms from Bangkok. Inter-VPS latency: Frankfurt→Bangkok ~180ms, Tokyo→Bangkok ~90ms.

**Why this is recommended**: Bitfinex at 0% fees is the #1 exchange for arbitrage profit. Every Bitfinex-involving pair saves 0.05-0.10% in fees compared to any other pair. Reducing Bitfinex latency from ~220ms to ~5ms significantly increases the chance of capturing these opportunities before they close.

### Option C: 4 VPS — Optimal (~$30/mo)

| VPS | Location | Exchanges | Worst Latency | Cost |
|-----|----------|-----------|:-------------:|:----:|
| 1 | **Tokyo** | Binance (<1ms) | <1ms | ~$7.50 |
| 2 | **Singapore** | Bybit (<1ms), Bitget (<1ms), KuCoin (<1ms), Gate.io (<1ms), OKX (35ms) | 35ms | ~$7.50 |
| 3 | **Bangkok** | MEXC (25ms), Pionex (~200ms) + **Orchestrator** | ~200ms | ~$7.50 |
| 4 | **Frankfurt** | Bitfinex (~5ms) | ~5ms | ~$7.50 |

**Pros**: Every exchange except Pionex is <35ms from its VPS. Singapore gets 5 exchanges at <1ms (vs 25ms from Bangkok). Cleanest separation.
**Cons**: Singapore can't run MEXC or Pionex (blocked). OKX slightly better from Hong Kong but 35ms from Singapore is fine. Extra $7.50/mo for marginal improvement over Option B.

**Note**: Singapore VPS cannot run MEXC (blocked) or Pionex (blocked). Only use it for Bybit, Bitget, KuCoin, Gate.io, and optionally OKX.

### Option D: 5 VPS — Maximum (~$37.50/mo)

| VPS | Location | Exchanges | Worst Latency | Cost |
|-----|----------|-----------|:-------------:|:----:|
| 1 | **Tokyo** | Binance (<1ms) | <1ms | ~$7.50 |
| 2 | **Singapore** | Bybit (<1ms), Bitget (<1ms), KuCoin (<1ms), Gate.io (<1ms), OKX (35ms) | 35ms | ~$7.50 |
| 3 | **Bangkok** | MEXC (25ms) + **Orchestrator** | 25ms | ~$7.50 |
| 4 | **Frankfurt** | Bitfinex (~5ms) | ~5ms | ~$7.50 |
| 5 | **Virginia** | Pionex (~5ms) | ~5ms | ~$7.50 |

**Pros**: Every single exchange at <35ms. Pionex drops from ~200ms to ~5ms.
**Cons**: Pionex at 0.05% fee with shared Binance order book doesn't justify a dedicated $7.50/mo VPS. Virginia VPS would only serve one exchange. Overkill.

## Inter-VPS Communication Latency

For multi-VPS setups, the orchestrator needs to communicate with all VPS nodes.

| From → To | RTT (ms) | Notes |
|-----------|:--------:|-------|
| Bangkok → Tokyo | ~90ms | |
| Bangkok → Singapore | ~25ms | |
| Bangkok → Frankfurt | ~180ms | |
| Bangkok → Virginia | ~250ms | |
| Tokyo → Singapore | ~68ms | |
| Tokyo → Frankfurt | ~245ms | |
| Frankfurt → Virginia | ~90ms | |

**Bangkok is the best orchestrator location** for Options A-D:
- Total aggregate RTT to all other VPS is lowest from Bangkok
- Handles MEXC (geo-blocked elsewhere) and Pionex (geo-blocked from Tokyo/Singapore)
- ~90ms to Tokyo, ~25ms to Singapore, ~180ms to Frankfurt

## Orchestrator Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  Tokyo VPS  │     │ Bangkok VPS  │     │ Frankfurt VPS │
│             │     │ (Orchestrator)│     │               │
│  Binance    │◄───►│  MEXC        │◄───►│  Bitfinex     │
│  OKX        │     │  Pionex      │     │               │
│             │     │              │     │               │
│  Fetcher +  │     │  Fetcher +   │     │  Fetcher +    │
│  Executor   │     │  Executor +  │     │  Executor     │
│             │     │  Monitor +   │     │               │
│             │     │  Dashboard   │     │               │
└─────────────┘     └──────────────┘     └───────────────┘
       ~90ms              Hub               ~180ms
```

Each VPS runs:
- **Fetcher**: WebSocket connections to assigned exchanges, streams price data to orchestrator
- **Executor**: Receives order commands from orchestrator, executes on local exchanges (lowest latency)

Orchestrator (Bangkok) runs:
- **Monitor**: Aggregates all prices, detects arbitrage opportunities
- **Balance Tracker**: Manages capital across all exchanges
- **Optimizer**: Symbol scoring, rotation, dominant pair detection
- **Dashboard**: WebSocket server for the React dashboard
- **State Manager**: Persistence, periodic saves

## Recommended Deployment Phases

### Phase 1: Test (Current) — 1 VPS, $0

| VPS | Location | Exchanges | Purpose |
|-----|----------|-----------|---------|
| 1 | **Kamatera Tokyo** (30-day free trial) | All 9 from single location | Testing with demo API keys |

Latency: <1ms to Binance, ~68ms to SG exchanges, ~160ms to Pionex, ~250ms to Bitfinex.
Good enough for simulation and demo testing.

### Phase 2: Production Start — 2 VPS, ~$15/mo (Option A)

| VPS | Location | Provider | Exchanges |
|-----|----------|----------|-----------|
| 1 | **Tokyo** | Contabo (4 vCPU, 8GB, $7.50) | Binance, OKX, Bybit, Bitget, KuCoin, Gate.io |
| 2 | **Bangkok** | Contabo (4 vCPU, 8GB, $7.50) | MEXC, Pionex, Bitfinex + Orchestrator |

Start here. Measure Bitfinex performance. If Bitfinex pairs are profitable but latency-limited, upgrade.

### Phase 3: Bitfinex Optimization — 3 VPS, ~$22.50/mo (Option B) ★

| VPS | Location | Provider | Exchanges |
|-----|----------|----------|-----------|
| 1 | **Tokyo** | Contabo | Binance, OKX |
| 2 | **Bangkok** | Contabo | Bybit, Bitget, KuCoin, Gate.io, MEXC, Pionex + Orchestrator |
| 3 | **Frankfurt** | Contabo | Bitfinex |

Add Frankfurt VPS when data shows Bitfinex opportunities are being missed due to latency.

### Phase 4: Full Optimization — 4 VPS, ~$30/mo (Option C)

| VPS | Location | Provider | Exchanges |
|-----|----------|----------|-----------|
| 1 | **Tokyo** | Contabo | Binance |
| 2 | **Singapore** | Contabo | Bybit, Bitget, KuCoin, Gate.io, OKX |
| 3 | **Bangkok** | Contabo | MEXC, Pionex + Orchestrator |
| 4 | **Frankfurt** | Contabo | Bitfinex |

Add Singapore VPS when data shows SG-exchange latency matters (25ms vs 68ms from Bangkok).

## Hardware Requirements

| Resource | Requirement | Notes |
|----------|:-----------:|-------|
| **RAM** | 2 GB sufficient | 6 WS connections ~200MB + dashboard build ~500MB peak |
| **CPU** | 1 vCPU fine | WebSocket parsing is not CPU-bound |
| **Storage** | 40+ GB | Logs, CSV snapshots, node_modules, dashboard build |
| **Bandwidth** | ~0.9 TB/mo | 9 exchanges × 60 symbols × ~1KB/update × 1/sec |

### VPS Provider Comparison (Tokyo)

| Provider | vCPU | RAM | Storage | Bandwidth | Price/mo |
|----------|:----:|:---:|---------|-----------|:--------:|
| **Contabo** | 4 | 8 GB | 75 GB NVMe | Unlimited (200Mbps) | ~$7.50 |
| Kamatera | 2 | 2 GB | 30 GB NVMe | Included | ~$6 |
| Vultr | 1 | 2 GB | 55 GB | 2 TB | $10 |
| AWS Lightsail | 2 | 2 GB | 60 GB SSD | 3 TB | $12 |
| Vultr High Perf | 1 | 2 GB | 50 GB NVMe | 3 TB | $12 |

**Contabo** is the best value: 4× the RAM needed, unlimited bandwidth for all WebSocket streams, available in Tokyo/Singapore/multiple locations.

## Latency Impact on Arbitrage

### How Latency Affects Profit

Arbitrage opportunities typically persist for **1-10 seconds**. One-way latency determines how "stale" your price data is:

| RTT | One-Way Delay | Impact |
|:---:|:------------:|--------|
| <1ms | <0.5ms | Near real-time. Maximum opportunity capture. |
| ~35ms | ~17ms | Negligible impact. |
| ~68ms | ~34ms | Minimal impact. Most opportunities captured. |
| ~160ms | ~80ms | Some narrow-spread opportunities missed. |
| ~250ms | ~125ms | Wide spreads only. Co-located traders capture tight spreads first. |

### Bitfinex Latency Calculus

Despite ~250ms RTT from Tokyo, Bitfinex is still highly profitable because:

1. **0% fee advantage**: Bitfinex↔Binance = 0.075% total cost (vs 0.15% for Binance↔OKX). This means Bitfinex pairs profit from spreads that would be losses on other pairs.

2. **Wider spread tolerance**: A 0.15% spread with Bitfinex = 0.075% profit. Same spread with two 0.10% exchanges = -0.05% loss.

3. **Opportunity persistence**: Most real arbitrage spreads last 1-10 seconds. Even at 250ms RTT, you're seeing prices from ~125ms ago — well within the opportunity window.

4. **Frankfurt VPS solution**: If needed, a Frankfurt VPS reduces Bitfinex RTT to ~5ms, recovering almost all latency-sensitive opportunities.

### Pionex Latency Calculus

Pionex at ~160ms from Tokyo or ~200ms from Bangkok is acceptable because:

1. **0.05% fee** — same as MEXC, but shares Binance's order book (near-zero Pionex↔Binance spread)
2. Real value is in Pionex↔OKX, Pionex↔KuCoin, Pionex↔Gate.io pairs
3. These cross-exchange spreads are typically wider and persist longer
4. A dedicated Virginia VPS ($7.50/mo) for one 0.05% exchange is not justified

## Measured Latency Data (Kamatera Tokyo VPS)

Real-world measurements from the Phase 1 test VPS (Kamatera Tokyo, 2 vCPU, 2 GB RAM). Data captured 2026-02-27.

### First Data After Connect

Time from WebSocket connection to first usable price update:

| Exchange | First Data (ms) | Notes |
|----------|:--------------:|-------|
| KuCoin | **22** | REST token + WS connect, fastest overall |
| Gate.io | **31** | Instant — subscribe-on-connect |
| Binance | **37** | URL-param streams, near-instant |
| OKX | **64** | Post-connect subscribe |
| Bitget | **85** | Post-connect subscribe |
| Bybit | **88** | Post-connect subscribe (orderbook + tickers) |
| Bitfinex | **1,312** | 2 connections × 30 symbols, Zug origin (~250ms RTT) |
| Pionex | **5,891** | 3 connections staggered 5s apart, 250ms throttle per symbol |

Pionex's 5.9s is dominated by the stagger delay (5s between sub-connections) and per-symbol subscription throttle (250ms × 20 symbols = 5s). Actual network RTT is ~160ms.

### Processing Latency (Per Message)

Time to parse a WebSocket message and update internal state. Sub-millisecond across all exchanges — CPU is never the bottleneck.

| Exchange | Avg (ms) | Min (ms) | Max (ms) | Messages/min |
|----------|:--------:|:--------:|:--------:|:------------:|
| Bitget | 0.01 | 0.01 | 0.16 | ~12,900 |
| KuCoin | 0.01 | 0.00 | 0.08 | ~17,200 |
| Gate.io | 0.01 | 0.01 | 0.12 | ~2,600 |
| OKX | 0.01 | 0.01 | 0.20 | ~9,700 |
| Bybit | 0.01 | 0.00 | 0.23 | ~23,200 |
| Pionex | 0.01 | 0.00 | 1.92 | ~4,400 |
| Binance | 0.02 | 0.01 | 0.15 | ~3,600 |
| Bitfinex | 0.02 | 0.00 | 0.03 | ~120 |

**Bybit** has the highest message volume (~23k/min) due to separate orderbook + ticker streams. **Bitfinex** has the lowest (~120/min) due to fewer UST pairs and lower update frequency.

### Data Freshness (Price Staleness)

The most important metric for arbitrage: how old is the price data when a tick fires? This reflects **exchange-side update frequency**, not network latency.

| Exchange | Avg Age (ms) | Max Age (ms) | Symbols | Verdict |
|----------|:----------:|:----------:|:-------:|---------|
| Bitget | **66** | 311 | 60/60 | Excellent — sub-100ms average |
| Bybit | **401** | 1,293 | 59/60 | Good — under 500ms |
| KuCoin | **677** | 4,979 | 60/60 | Good — some symbols update slowly |
| Pionex | **827** | 5,336 | 58/60 | Acceptable — DEPTH topic updates are batched |
| OKX | **1,037** | 7,132 | 60/60 | Fair — some symbols >1s stale |
| Binance | **1,334** | 11,562 | 59/60 | Fair — surprisingly high for co-located |
| Gate.io | **5,854** | 28,933 | 60/60 | Poor — exchange pushes updates infrequently |
| Bitfinex | **20,298** | 118,683 | 36/60 | Poor — only 36/60 UST pairs, very low frequency |

**Key observations:**
- **Bitget** is the freshest exchange at 66ms avg — its WebSocket pushes rapid ticker updates.
- **Binance** freshness (1.3s avg) is higher than expected for a Tokyo-hosted exchange. This is because Binance uses combined streams (URL-param) that batch updates, not per-symbol push.
- **Gate.io** at 5.9s avg is an exchange-side issue — the `spot.tickers` channel has low update frequency for many alt pairs.
- **Bitfinex** at 20.3s avg with only 36/60 symbols reflects both the limited UST pair coverage (~40-50 of 60 symbols) and very low trade frequency on available pairs. Not a network issue — Bitfinex simply doesn't generate frequent updates for most alts.
- **Pionex** freshness (827ms) is better than expected given the ~160ms RTT, because the DEPTH topic pushes snapshots frequently for actively traded pairs.

### Latency Summary by Exchange Tier

| Tier | Exchanges | Freshness | Trading Impact |
|------|-----------|-----------|---------------|
| **Tier 1** (Real-time) | Bitget, Bybit | <500ms avg | Captures all opportunities including fast-closing ones |
| **Tier 2** (Near-real-time) | KuCoin, Pionex, OKX | 500ms-1.1s avg | Captures most opportunities; may miss sub-second spreads |
| **Tier 3** (Delayed) | Binance | ~1.3s avg | Fair for majors, some opportunities stale by arrival |
| **Tier 4** (Slow) | Gate.io, Bitfinex | 5.9s-20.3s avg | Only captures persistent wide spreads |

**Tier 4 mitigation:**
- Gate.io: Still profitable due to zero-fee BTC/USDT pair and wider spreads on alts. Consider Gate.io `spot.order_book` channel for per-symbol depth updates (higher frequency but more bandwidth).
- Bitfinex: 0% fee advantage compensates for staleness — any Bitfinex pair only needs 1 side's fee (the other exchange). Persistent spreads of 0.05%+ are common enough to be profitable despite 20s average staleness.

## Network Topology Notes

### Cloudflare-Proxied Exchanges

Both Bitfinex and Pionex route through Cloudflare's anycast CDN:

```
Your VPS → Cloudflare edge (local POP) → Cloudflare backbone → Origin server
```

- Cloudflare has POPs in Tokyo (AT Tokyo CC1, Equinix TY2), Bangkok, Singapore, Frankfurt
- TLS handshake and WebSocket upgrade happen at the local Cloudflare POP (fast)
- Every subsequent WebSocket message traverses the full path to origin (adds latency)
- Cloudflare adds ~5-10ms overhead per hop for WebSocket proxying

### Direct-Connection Exchanges

Binance, OKX, Bybit, Bitget, KuCoin, Gate.io, MEXC all use direct WebSocket connections (no CDN proxy). Latency is purely network distance.

### Plasma Network for Rebalancing

For USDT transfers between exchanges, Plasma offers sub-second finality at near-zero cost:
- Protocol-level paymaster subsidizes gas
- No need to hold XPL token
- Confirmed support: Binance ($0.01), Bybit (~$0), Bitget ($0.001), KuCoin ($0.40)
- Not yet widely supported — BEP20 remains the universal fallback
