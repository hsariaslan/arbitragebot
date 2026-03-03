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

| Exchange | Tokyo | Bangkok | Singapore | Zurich | Frankfurt | Virginia |
|----------|:-----:|:-------:|:---------:|:------:|:---------:|:--------:|
| Binance | **<1** | ~70 | ~68 | ~240 | ~245 | ~170 |
| OKX | ~35 | ~60 | ~35 | ~150 | ~150 | ~200 |
| Bybit | ~68 | ~25 | **<1** | ~180 | ~160 | ~230 |
| Bitget | ~68 | ~25 | **<1** | ~180 | ~160 | ~230 |
| KuCoin | ~68 | ~25 | **<1** | ~180 | ~160 | ~230 |
| Gate.io | ~68 | ~25 | **<1** | ~180 | ~160 | ~230 |
| MEXC | ~68 | ~25 | **<1** | ~180 | ~160 | ~230 |
| Pionex | ~160 | ~200 | ~230 | ~90 | ~90 | **~5** |
| Bitfinex | ~250 | ~250 | ~180 | **<1** | **~5** | ~80 |

**Zurich vs Frankfurt for Bitfinex**: Bitfinex is in Zug, Switzerland — ~30km from Zurich. RTT from Zurich is <1ms vs ~5ms from Frankfurt. Zurich is the optimal location for Bitfinex.

## Geo-Restriction Matrix

Exchanges blocked from each VPS location (X = blocked, ! = risky):

| Exchange | Tokyo | Bangkok | Singapore | Zurich | Frankfurt | Virginia |
|----------|:-----:|:-------:|:---------:|:------:|:---------:|:--------:|
| Binance | OK | OK | OK | OK | OK | **X** (US) |
| OKX | OK | OK | OK | OK | OK | **X** (US) |
| Bybit | **!** (exiting JP 2026) | OK | **X** | OK | OK | **X** (US) |
| Bitget | OK | OK | **X** | OK | OK | **X** (US) |
| KuCoin | OK | OK | **X** | OK | OK | **X** (US) |
| Gate.io | OK | OK | OK | OK | OK | **X** (US) |
| MEXC | **!** (FSA risk) | OK | **X** | OK | OK | **X** (US) |
| Pionex | **X** (KYC-blocked) | OK | **X** | OK (monitor EU) | OK (monitor EU) | **X** (US) |
| Bitfinex | **!** (FSA warnings) | OK | OK | OK | OK | **X** (US) |

**Summary of blocked locations**:
- **Tokyo**: Pionex KYC-blocked. MEXC/Bybit/Bitfinex at regulatory risk from Japan FSA.
- **Bangkok**: All 9 exchanges accessible. No restrictions. Best for orchestrator.
- **Singapore**: Bybit, Bitget, KuCoin, MEXC, Pionex all blocked. Only 4/9 accessible (Binance, OKX, Gate.io, Bitfinex).
- **Zurich/Frankfurt**: All 9 accessible. Monitor EU MiCA for Pionex.
- **Virginia**: All exchanges blocked (US).

## Current Infrastructure

### Active VPS Providers

| VPS | Location | Provider | Cost | Specs | Expiry |
|-----|----------|----------|:----:|-------|--------|
| 1 | **Bangkok** | LightNode | $7.70/mo | 1 vCPU, 2 GB RAM, 50 GB NVMe | Ongoing (hourly billing) |
| 2 | **Tokyo** | Kamatera | $0 (trial) | 2 vCPU, 2 GB RAM, 30 GB NVMe | ~30 days from creation |
| 3 | **Singapore** | Vultr | $5 credit | Not yet deployed | $5 credit available |
| 4 | **Zurich** | Oracle Cloud | $0 (always free) | 1/8 OCPU AMD, 1 GB RAM (E2.1.Micro) | Never (always free tier) |

**Status**: Bangkok VPS active (production). Oracle Zurich **deployed** (WebSocket proxy for Bitfinex, 0.7ms latency). Tokyo VPS on free trial. Vultr Singapore paid ($5) but not deployed.

### VPS Provider Notes

**LightNode (Bangkok)**:
- Confirmed Bangkok datacenter (ASN AS138915, Kaopu Cloud HK Limited)
- Verified via traceroute and IP geolocation — real Bangkok, not Singapore proxy
- Speed test: lightnode.com/speed/tha-bangkok-1
- Hourly billing — can upgrade/downgrade anytime
- ~$15 signup credit covers first ~2 months
- 4.9/5 reliability rating on HostAdvice

**Kamatera (Tokyo)**:
- 30-day free trial (up to $100 credit)
- Good for testing, not long-term (limited free tier)

**Vultr (Singapore)**:
- $5 account activation already paid
- Has Singapore datacenter (confirmed)
- Does NOT have Bangkok datacenter (only Tokyo, Osaka, Seoul, Singapore, Mumbai, Bangalore, Delhi in Asia)
- Cheapest plan: $5/mo (1 vCPU, 1 GB RAM, 25 GB SSD, 1 TB bandwidth)

**Oracle Cloud (Zurich)** — **DEPLOYED**:
- Shape: VM.Standard.E2.1.Micro (AMD, 1/8 OCPU, 1 GB RAM, 47 GB boot volume)
- ARM shapes (A1.Flex) had capacity issues; AMD Micro works fine for WS proxy
- Runs `proxy/ws_proxy.py` as systemd service on port 9000
- Measured latency: **0.71ms avg** to api.bitfinex.com (vs ~1,200ms from Bangkok)
- Port 9000 restricted to Bangkok VPS IP via Oracle Security List + iptables
- Ubuntu 24.04, Python 3.12

### Bangkok VPS Provider Comparison

| # | Provider | Price/mo | vCPU | RAM | Storage | Bangkok DC? |
|---|----------|:--------:|:----:|:---:|---------|:-----------:|
| 1 | **LightNode** | **$7.70** | 1 | 2 GB | 50 GB NVMe | **Yes** (verified) |
| 2 | **VinaHost** | **$9.45** | 2 | 2 GB | 30 GB SSD | **Yes** (Tier 3) |
| 3 | **AplusHosting** | **$12.90** | 1 | 2 GB | 40 GB SSD | **Yes** |
| 4 | **VPSThai** | **$79** | 1 | 4 GB | 200 GB | **Yes** (UIH IDC) |

**Not in Bangkok**: Vultr (no Bangkok DC), IONOS (no Asia DCs), Cloudzy (uses Singapore DC).

## VPS Combinations

### Option A: 2 VPS — Current Setup (~$7.70/mo)

| VPS | Location | Provider | Exchanges | Worst Latency | Cost |
|-----|----------|----------|-----------|:-------------:|:----:|
| 1 | **Bangkok** | LightNode | All 9 exchanges + **Orchestrator** | ~250ms (Bitfinex) | $7.70 |
| 2 | **Tokyo** | Kamatera | (backup/testing) | — | $0 (trial) |

**Monolithic**: Entire bot runs on Bangkok VPS. All 9 exchanges connect directly.

### Option B: 3 VPS — Balanced (~$7.70/mo + free)

| VPS | Location | Provider | Exchanges | Worst Latency | Cost |
|-----|----------|----------|-----------|:-------------:|:----:|
| 1 | **Bangkok** | LightNode | MEXC (25ms) + **Orchestrator** | 25ms | $7.70 |
| 2 | **Tokyo** | Kamatera | Binance (<1ms), Pionex (~160ms) | ~160ms | $0 |
| 3 | **Zurich** | Oracle Cloud | Bitfinex (<1ms) | <1ms | $0 |

**Requires**: Distributed relay architecture (see below).

### Option C: 4 VPS — Optimal (~$12.70/mo) ★ Recommended

| VPS | Location | Provider | Exchanges | Worst Latency | Cost |
|-----|----------|----------|-----------|:-------------:|:----:|
| 1 | **Bangkok** | LightNode | MEXC (25ms) + **Orchestrator** | 25ms | $7.70 |
| 2 | **Singapore** | Vultr | OKX (<35ms), Bybit (<1ms), Bitget (<1ms), KuCoin (<1ms), Gate.io (<1ms) | ~35ms | $5 |
| 3 | **Tokyo** | Kamatera | Binance (<1ms), Pionex (~160ms) | ~160ms | $0 |
| 4 | **Zurich** | Oracle Cloud | Bitfinex (<1ms) | <1ms | $0 |

**Requires**: Distributed relay architecture.

**Why this is recommended**: Every exchange connects from its optimal geographic location. Total cost $12.70/mo ($7.70 LightNode + $5 Vultr). Tokyo and Zurich are free. All 9 exchanges accessible (MEXC in Bangkok, not blocked). 7/9 exchanges at <35ms from their fetcher node.

**Note on Singapore geo-restrictions**: Bybit, Bitget, KuCoin, MEXC, Pionex are listed as blocked in Singapore. However, these restrictions are typically KYC/account-level (not IP-level). WebSocket data feeds (read-only, no authentication) may work from Singapore even for "blocked" exchanges. **Must verify** by testing WebSocket connections from the Vultr Singapore VPS before committing to this architecture. If blocked at IP level, fall back to Option B (move those exchanges to Bangkok).

### Option D: 5 VPS — Maximum (~$12.70/mo + $7.50)

| VPS | Location | Provider | Exchanges | Worst Latency | Cost |
|-----|----------|----------|-----------|:-------------:|:----:|
| 1 | **Bangkok** | LightNode | MEXC (25ms) + **Orchestrator** | 25ms | $7.70 |
| 2 | **Singapore** | Vultr | Bybit (<1ms), Bitget (<1ms), KuCoin (<1ms), Gate.io (<1ms), OKX (~35ms) | ~35ms | $5 |
| 3 | **Tokyo** | Contabo | Binance (<1ms), Pionex (~160ms) | ~160ms | ~$7.50 |
| 4 | **Zurich** | Oracle Cloud | Bitfinex (<1ms) | <1ms | $0 |
| 5 | **Virginia** | Any | Pionex (~5ms) | ~5ms | ~$7.50 |

**Same as Option C** but with a paid Tokyo VPS (when Kamatera trial expires) and an optional Virginia VPS for Pionex. The Virginia VPS for a single 0.05% exchange is not justified — skip it.

**Post-trial plan**: When Kamatera Tokyo expires, either pay for a Tokyo VPS (~$7.50/mo Contabo) or move Binance/Pionex to Bangkok (70ms/200ms — acceptable for monolithic fallback).

## Inter-VPS Communication Latency

For the distributed architecture, the orchestrator (Bangkok) communicates with all fetcher nodes:

| From → To | RTT (ms) | Notes |
|-----------|:--------:|-------|
| Bangkok → Singapore | ~25ms | Excellent — 5 SG exchanges |
| Bangkok → Tokyo | ~70ms | Good — Binance |
| Bangkok → Zurich | ~250ms | High — but Bitfinex data is inherently slow |
| Tokyo → Singapore | ~68ms | |
| Tokyo → Zurich | ~240ms | |
| Singapore → Zurich | ~180ms | |

**Bangkok is the best orchestrator location**:
- Only location where all 9 exchanges are accessible (no geo-restrictions)
- ~25ms to Singapore fetcher node (5 exchanges)
- ~70ms to Tokyo fetcher node (Binance)
- Handles MEXC locally (geo-blocked in Singapore/Tokyo-risky)

## Distributed Relay Architecture

### Why Distributed?

The monolithic bot connects to all exchanges from a single location. The distributed architecture places fetcher nodes close to exchanges for better **WebSocket connection quality** (stability, fewer reconnections, lower jitter).

**Key insight**: Distributed does NOT make the orchestrator see prices faster — the relay adds the same delay as a direct connection. The real benefits are:

1. **WebSocket connection stability**: A fetcher <1ms from its exchange has rock-solid connections. From 250ms away, you get more jitter, packet loss, and reconnections. For a 24/7 bot, this compounds.
2. **Accurate timestamps**: Local fetcher timestamps data at capture time, before relay delay. The orchestrator knows the TRUE age of each price.
3. **Resilience**: If one VPS goes down briefly, other fetcher nodes keep collecting data. Orchestrator reconnects and catches up.
4. **Clean separation**: Each node handles its geographic cluster. Easy to add/remove exchanges.

### Latency Comparison: Monolithic vs Distributed

| Exchange | Monolithic (Bangkok) | Distributed (capture + relay) | Net Difference |
|----------|:-------------------:|:-----------------------------:|:--------------:|
| OKX, Bybit, Bitget, KuCoin, Gate.io | 25ms direct | <1ms + 25ms relay = 26ms | ~0 (same) |
| Binance | ~70ms direct | <1ms + 70ms relay = 71ms | ~0 (same) |
| MEXC | ~25ms direct | 25ms local | 0 (same) |
| Pionex | ~200ms direct | ~160ms + 70ms relay = 230ms | +30ms (worse) |
| Bitfinex | ~250ms direct | <1ms + 250ms relay = 251ms | ~0 (same) |

**Detection latency is the same**. The orchestrator sees prices at roughly the same speed. The benefit is connection quality, not speed.

### Architecture Diagram (Option C — 4 VPS)

```
Zurich (Oracle, Free)          Tokyo (Kamatera, Free)
  Bitfinex <1ms                  Binance <1ms
  Fetcher + Executor             Pionex ~160ms
       │                         Fetcher + Executor
       │                              │
       └──── relay (~250ms) ──────────┤
                                      │
                               Bangkok (LightNode, $7.70)
                                 MEXC ~25ms (local)
                                 Orchestrator:
                                   Monitor + Optimizer
                                   Balance + Dashboard
                                   State Manager
                                      │
                                      │
       ┌──── relay (~25ms) ───────────┘
       │
Singapore (Vultr, $5)
  OKX ~35ms
  Bybit <1ms
  Bitget <1ms
  KuCoin <1ms
  Gate.io <1ms
  Fetcher + Executor
```

### Relay Protocol

Each fetcher node runs a lightweight WebSocket relay server that streams price data to the orchestrator:

**Fetcher Node → Orchestrator (price relay)**:
```json
{
  "type": "price_update",
  "exchange": "binance",
  "symbol": "BTCUSDT",
  "bid": "84250.50",
  "ask": "84251.00",
  "bid_qty": "1.5",
  "ask_qty": "2.0",
  "last_price": "84250.75",
  "volume": "12345.6",
  "captured_at": 1709136000.123,
  "node": "tokyo"
}
```

**Orchestrator → Fetcher Node (execution command)**:
```json
{
  "type": "execute_trade",
  "exchange": "binance",
  "symbol": "BTCUSDT",
  "side": "buy",
  "quantity": "0.001",
  "price": "84251.00",
  "order_type": "market",
  "client_order_id": "coirna-BTC-buy-1709136000-a1b2c3"
}
```

### Components

Each fetcher node runs:
- **Exchange Fetchers**: WebSocket connections to assigned exchanges (existing code)
- **Relay Server**: Streams `PriceState` updates to orchestrator via authenticated WebSocket
- **Executor**: Receives trade commands from orchestrator, executes on local exchanges

Orchestrator (Bangkok) runs:
- **Relay Client**: Connects to all fetcher nodes, populates local `_state` dicts (acts like a virtual fetcher)
- **Local Fetchers**: MEXC connects directly (local to Bangkok)
- **Monitor**: Aggregates all prices, detects arbitrage opportunities
- **Optimizer**: Symbol scoring, rotation, dominant pair detection
- **Balance Tracker**: Capital management across all exchanges
- **Dashboard**: WebSocket server for the React dashboard
- **State Manager**: Persistence, periodic saves

### Execution Routing

When the orchestrator detects an opportunity (e.g., buy on Binance, sell on Bitget):
1. Orchestrator sends `execute_trade` command to **Tokyo node** (buy on Binance)
2. Orchestrator sends `execute_trade` command to **Singapore node** (sell on Bitget)
3. Both execute locally with <1ms to their exchanges
4. Both report `TradeResult` back to orchestrator
5. Orchestrator records the trade, updates balance tracker

**MEXC trades**: Executed directly by the orchestrator (MEXC is local to Bangkok, ~25ms to SG servers).

### Security

- Relay connections authenticated with pre-shared API key (not exchange keys — just inter-node auth)
- Relay WebSocket uses WSS (TLS) for encrypted transit
- Fetcher nodes never expose exchange API keys to the orchestrator
- Each node stores only the exchange API keys it needs

## Recommended Deployment Phases

### Phase 1: Monolithic Bangkok (Current) — $7.70/mo

| VPS | Location | Provider | Exchanges | Purpose |
|-----|----------|----------|-----------|---------|
| 1 | **Bangkok** | LightNode | All 9 from single location | 24/7 production, all exchanges |
| 2 | **Tokyo** | Kamatera (trial) | — | Backup/testing |

Deploy the monolithic bot to Bangkok. Measure actual latencies and data freshness. All 9 exchanges accessible. ~25ms to SG exchanges, ~70ms to Binance, ~200ms to Pionex, ~250ms to Bitfinex.

**Immediate goal**: Get 24/7 uptime. Replace running from local PC.

### Phase 2: Add Bitfinex Node — $7.70/mo + free (**DEPLOYED**)

| VPS | Location | Provider | Exchanges | Purpose |
|-----|----------|----------|-----------|---------|
| 1 | **Bangkok** | LightNode | 8 exchanges + Orchestrator | Main bot |
| 2 | **Zurich** | Oracle Cloud (free) | Bitfinex (<1ms) | WebSocket proxy (`proxy/ws_proxy.py`) |

**Deployed 2026-03-03.** Uses transparent WebSocket proxy (Option A) instead of remote fetcher. Bangkok's BitfinexFetcher connects to `ws://zurich-ip:9000` which relays to `wss://api-pub.bitfinex.com/ws/2`. Bitfinex data latency: ~200ms total (was ~1,200ms direct).

### Phase 3: Distribute to Singapore — $12.70/mo + free

| VPS | Location | Provider | Exchanges | Purpose |
|-----|----------|----------|-----------|---------|
| 1 | **Bangkok** | LightNode | MEXC + Orchestrator | Hub |
| 2 | **Singapore** | Vultr ($5) | OKX, Bybit, Bitget, KuCoin, Gate.io | SG fetcher + executor |
| 3 | **Tokyo** | Kamatera (free) | Binance, Pionex | JP fetcher + executor |
| 4 | **Zurich** | Oracle Cloud (free) | Bitfinex | CH fetcher + executor |

Full distributed architecture (Option C). Verify Singapore geo-restrictions first — test WebSocket connections from Vultr SG VPS. If SG exchanges block Vultr IPs, move those exchanges back to Bangkok.

### Phase 4: Post-Trial — ~$20/mo

When Kamatera Tokyo trial expires:
- **Option A**: Pay for Tokyo VPS (~$7.50/mo Contabo) — keeps Binance at <1ms
- **Option B**: Move Binance/Pionex to Bangkok — saves $7.50/mo, Binance at ~70ms (acceptable)
- **Option C**: Move Binance to Singapore node — ~68ms from SG (acceptable, saves Tokyo VPS)

## Hardware Requirements

| Resource | Orchestrator | Fetcher Node | Notes |
|----------|:----------:|:------------:|-------|
| **RAM** | 2 GB | 1 GB | Orchestrator needs more for dashboard + optimizer |
| **CPU** | 1 vCPU | 1 vCPU | WebSocket parsing is not CPU-bound |
| **Storage** | 40+ GB | 10 GB | Logs, CSV, state on orchestrator; minimal on fetchers |
| **Bandwidth** | ~0.5 TB/mo | ~0.2-0.4 TB/mo | Fetcher nodes relay to orchestrator |

**2 GB RAM is sufficient** for the orchestrator (Bangkok). Dashboard is built on GitHub Actions runners (16 GB RAM), not on the VPS. VPS only serves pre-built static files (~2-5 MB).

| Component | RAM Usage |
|-----------|:---------:|
| OS (Ubuntu) | ~200-300 MB |
| Python + WebSocket fetchers | ~200 MB |
| Monitor + Optimizer + Balance | ~100 MB |
| Dashboard server (runtime) | ~50 MB |
| **Total runtime** | **~550-650 MB** |

### VPS Provider Comparison

| Provider | Location | vCPU | RAM | Storage | Bandwidth | Price/mo |
|----------|----------|:----:|:---:|---------|-----------|:--------:|
| **LightNode** | Bangkok | 1 | 2 GB | 50 GB NVMe | 1 TB | $7.70 |
| **Vultr** | Singapore | 1 | 1 GB | 25 GB SSD | 1 TB | $5 |
| **Kamatera** | Tokyo | 2 | 2 GB | 30 GB NVMe | Included | Free (trial) |
| **Oracle Cloud** | Zurich | 4 ARM | 24 GB | 200 GB | 10 TB | Free (always) |
| **Contabo** | Tokyo/SG | 4 | 8 GB | 75 GB NVMe | Unlimited | ~$7.50 |

**Contabo** is the best value for long-term paid VPS: 4x RAM, unlimited bandwidth, available in Tokyo/Singapore.

## Auto-Deployment with GitHub Actions

Deployment is automated via GitHub Actions. Push to master triggers build + deploy to all VPS nodes.

### How It Works

```
Developer PC → git push → GitHub Actions (16 GB runner)
                              ├─ npm install + vite build (dashboard)
                              ├─ SSH to Bangkok → git pull + restart bot
                              ├─ SSH to Singapore → git pull + restart fetcher
                              ├─ SSH to Tokyo → git pull + restart fetcher
                              └─ SSH to Zurich → git pull + restart fetcher
```

The GitHub runner handles the heavy dashboard build (~1.5 GB RAM). VPSes only receive built files and Python code.

### Required GitHub Secrets

| Secret | Value |
|--------|-------|
| `BANGKOK_HOST` | LightNode IP |
| `SINGAPORE_HOST` | Vultr IP |
| `TOKYO_HOST` | Kamatera IP |
| `ZURICH_HOST` | Oracle IP |
| `SSH_PRIVATE_KEY` | Shared deploy key |
| `SSH_USER` | e.g. `ubuntu` |

### Deployment Process Per VPS

1. SSH into VPS
2. `git pull origin master`
3. `pip install -r requirements.txt` (if changed)
4. Copy pre-built `dashboard/dist/` from GitHub artifact
5. `systemctl restart coirnabot` (or equivalent)

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

### Connection Quality vs Raw Latency

For a 24/7 bot, **WebSocket connection stability** matters more than raw latency savings:

| Metric | <1ms Connection | ~25ms Connection | ~250ms Connection |
|--------|:--------------:|:----------------:|:-----------------:|
| Reconnection frequency | Very rare | Occasional | More frequent |
| Packet jitter | <1ms | 1-5ms | 10-50ms |
| Data gaps | None | Rare | Occasional |
| Heartbeat reliability | Perfect | Good | May timeout |

A fetcher <1ms from its exchange has rock-solid WebSocket connections — fewer reconnections, less jitter, no data gaps. At 250ms, the connection is functional but experiences more instability over hours/days of continuous operation.

This is the primary justification for the distributed architecture: not faster detection, but **healthier, more reliable connections** that produce better quality data over time.

### Bitfinex Latency Calculus

Despite ~250ms RTT from Bangkok, Bitfinex is still highly profitable because:

1. **0% fee advantage**: Bitfinex + any exchange = only the other exchange's fee. This means Bitfinex pairs profit from spreads that would be losses on other pairs.
2. **Wider spread tolerance**: A 0.15% spread with Bitfinex = 0.075% profit (if other side is Binance). Same spread with two 0.10% exchanges = -0.05% loss.
3. **Opportunity persistence**: Most real arbitrage spreads last 1-10 seconds. Even at 250ms RTT, you're seeing prices from ~125ms ago — well within the opportunity window.
4. **Zurich VPS solution**: Oracle Cloud Zurich (free) reduces Bitfinex RTT to <1ms.

### Pionex Latency Calculus

Pionex at ~160ms from Tokyo or ~200ms from Bangkok is acceptable because:

1. **0.05% fee** — same as MEXC, but shares Binance's order book (near-zero Pionex<->Binance spread)
2. Real value is in Pionex<->OKX, Pionex<->KuCoin, Pionex<->Gate.io pairs
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
| Bitfinex | **1,312** | 2 connections x 30 symbols, Zug origin (~250ms RTT) |
| Pionex | **5,891** | 3 connections staggered 5s apart, 250ms throttle per symbol |

Pionex's 5.9s is dominated by the stagger delay (5s between sub-connections) and per-symbol subscription throttle (250ms x 20 symbols = 5s). Actual network RTT is ~160ms.

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
Your VPS -> Cloudflare edge (local POP) -> Cloudflare backbone -> Origin server
```

- Cloudflare has POPs in Tokyo (AT Tokyo CC1, Equinix TY2), Bangkok, Singapore, Zurich, Frankfurt
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
