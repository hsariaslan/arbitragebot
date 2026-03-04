# Exchange Details

Comprehensive reference for all 9 supported exchanges — fees, discounts, server infrastructure, geo-restrictions, WebSocket implementation, and withdrawal fees.

## Exchange Summary

| Rank | Exchange | Effective Taker Fee | Server Location | Cloud Provider | Latency from Tokyo |
|:----:|----------|:-------------------:|-----------------|:--------------:|:------------------:|
| 1 | **Bitfinex** | 0.00% | Zug, Switzerland | Bare-metal (Market Synergy) | ~250ms |
| 2 | **MEXC** | 0.05% | Singapore | AWS ap-southeast-1 | ~68ms |
| 3 | **Pionex** | 0.05% | Likely Virginia, USA | AWS (via Cloudflare) | ~160ms |
| 4 | **Binance** | 0.075% | Tokyo, Japan | AWS ap-northeast-1 | <1ms |
| 5 | **Bybit** | 0.075% | Singapore | AWS ap-southeast-1 | ~68ms |
| 6 | **Bitget** | 0.08% | Singapore | AWS ap-southeast-1 | ~68ms |
| 7 | **KuCoin** | 0.08% | Singapore | AWS | ~68ms |
| 8 | **OKX** | 0.10% | Hong Kong | Alibaba Cloud / AWS HK | ~35ms |
| 9 | **Gate.io** | 0.09% | Singapore | AWS ap-southeast-1 | ~68ms |

---

## 1. Bitfinex

### Overview

| Field | Value |
|-------|-------|
| **Headquarters** | British Virgin Islands (iFinex Inc) |
| **Founded** | 2012 |
| **Base taker fee** | 0.00% (permanent since Dec 17, 2025) |
| **Base maker fee** | 0.00% |
| **Effective taker fee** | 0.00% |
| **Discount token** | None needed |
| **Fee model** | received |
| **Fee mechanism** | instant |
| **Demo/Testnet API** | No |

### Server Infrastructure

- **Location**: Zug, Switzerland (bare-metal dedicated servers)
- **Provider**: Self-designed servers, managed by Market Synergy GmbH
- **CDN**: Cloudflare (all public endpoints proxied through anycast network)
- **Migration history**: Moved from AWS to bare-metal in January 2019 (2x performance improvement per CTO Paolo Ardoino). Doubled server capacity in October 2021.
- **Co-location**: Available via Market Synergy for institutional clients (~100 HFT firms)
- **Market Synergy POPs**: ZH4 (Zurich/Equinix), LD4 (London/Equinix), NY4 (New York/Equinix) — no Asian POP
- **FIX feed**: Available via Connamara collaboration for institutional access

**DNS Resolution**: `api-pub.bitfinex.com` → Cloudflare IPs (104.16.164-168.90). WebSocket connects to Cloudflare Tokyo edge (~1-5ms), then proxied to Zurich origin (~230-250ms).

### Latency from Key Locations

| From | Estimated RTT | Notes |
|------|:------------:|-------|
| Tokyo | ~240-260ms | Via Cloudflare Tokyo → Zurich origin |
| Bangkok | ~220-240ms | Via Cloudflare Bangkok → Zurich origin |
| Singapore | ~180-200ms | Via Cloudflare Singapore → Zurich origin |
| Frankfurt | ~5-10ms | Direct to Zurich |
| London | ~15-20ms | Via LD4 POP |
| New York | ~80-100ms | Via NY4 POP |

### Geo-Restrictions

**Fully banned**: US, Canada, Cuba, Iran, North Korea, Syria, Bangladesh, Bolivia, Ecuador, Kyrgyzstan, BVI, Crimea, Donetsk, Luhansk, Kherson, Zaporizhzhia.

**Partially restricted** (securities/derivatives only, spot OK): UK, Spain, Austria, Italy.

**VPS location assessment**:

| Location | Access | Risk |
|----------|--------|------|
| Japan | Likely works (no IP block) | Medium — FSA warnings, app store removal |
| Thailand | Fully accessible | Low |
| Vietnam | Fully accessible | Low |
| Singapore | Fully accessible | Low |
| Germany | Fully accessible (6.8% user base) | Very Low |
| Turkey | Fully accessible (TRY fiat supported) | Very Low |

No VPS/datacenter IP blocking — Bitfinex supports co-location for institutional traders.

### WebSocket Details

| Field | Value |
|-------|-------|
| **Endpoint** | `wss://api-pub.bitfinex.com/ws/2` |
| **Subscribe** | Post-connect JSON |
| **Symbol format** | `tBTCUST` (t-prefix, UST not USDT) |
| **Ping type** | JSON `{"event":"ping"}` |
| **Ping interval** | 15s |
| **Sub limit** | 30 channels per connection |
| **Connections used** | 2 (dual-connection for 60 symbols) |
| **Data format** | Arrays (not JSON objects) — channel ID mapping from subscribed events |
| **Has last_price** | Yes |
| **Has volume** | Yes |

### USDT Withdrawal Fees

Bitfinex offers **free withdrawals on 14 networks**. Only ERC20 has a fee.

| Network | Fee | Type | Notes |
|---------|:----|:----:|-------|
| TRC20 | $0.00 | flat | Free |
| Arbitrum | $0.00 | flat | Free |
| Optimism | $0.00 | flat | Free |
| Polygon | $0.00 | flat | Free |
| Solana | $0.00 | flat | Free |
| AVAX C-Chain | $0.00 | flat | Free |
| NEAR | $0.00 | flat | Free |
| Tezos | $0.00 | flat | Free |
| Algorand | $0.00 | flat | Free |
| Stellar | $0.00 | flat | Free |
| Kava | $0.00 | flat | Free |
| Liquid | $0.00 | flat | Free |
| EOS | $0.00 | flat | Free |
| Lightning | $0.00 | flat | Free |
| ERC20 | ~$0.50 | flat | Only paid network |

**No BEP20 support.** Preferred rebalancing: TRC20, Arbitrum, or Optimism (all free).

### Key Notes

- 0% taker/maker fees are permanent since December 17, 2025 — not a promotion.
- ~40-50 of 60 configured symbols available as UST pairs (not all symbols listed).
- Uses `tBTCUST` format (UST suffix, not USDT). Symbol conversion handled in fetcher.
- 30 subscription limit per WS connection requires 2 connections for 60 symbols.
- Despite highest latency from Asia, 0% fees make it the most cost-effective exchange for arbitrage.

---

## 2. Binance

### Overview

| Field | Value |
|-------|-------|
| **Headquarters** | Cayman Islands (officially), global operations |
| **Founded** | 2017 |
| **Base taker fee** | 0.10% |
| **Token discount** | BNB 25% off → **0.075%** |
| **Effective taker fee** | 0.075% |
| **How to claim** | Buy BNB, enable "Pay fees with BNB" in Settings > Fee |
| **Fee model** | token |
| **Fee mechanism** | instant |
| **Demo/Testnet API** | Yes — `https://testnet.binance.vision` |

### Server Infrastructure

- **Location**: Tokyo, Japan
- **Provider**: AWS ap-northeast-1
- **CDN**: None (direct connection)
- **Matching engine**: Co-located with API servers in Tokyo

### Latency from Key Locations

| From | Estimated RTT | Notes |
|------|:------------:|-------|
| **Tokyo** | **<1ms** | Same AWS region |
| Bangkok | ~90ms | Cross-region |
| Singapore | ~68ms | ap-southeast-1 → ap-northeast-1 |
| Frankfurt | ~245ms | Cross-continent |

### Geo-Restrictions

**Fully banned**: US (use Binance.US), Ontario (Canada), Cuba, Iran, North Korea, Syria, Crimea.

**VPS location assessment**: Accessible from Japan, Thailand, Vietnam, Singapore, Germany, Turkey. No VPS/datacenter IP blocking for non-sanctioned countries.

### WebSocket Details

| Field | Value |
|-------|-------|
| **Endpoint** | `wss://stream.binance.com:9443/stream?streams=...` |
| **Subscribe** | URL parameter streams (combined stream) |
| **Symbol format** | `btcusdt` (lowercase) |
| **Ping type** | WS-level (library handles, 20s auto) |
| **Ping interval** | 20s (automatic) |
| **Sub limit** | 1024 streams per connection |
| **Data format** | JSON objects |
| **Has last_price** | Yes |
| **Has volume** | Yes |

### USDT Withdrawal Fees

| Network | Fee | Type | Min Withdrawal | Speed |
|---------|:----|:----:|:--------------:|:-----:|
| BEP20 | $0.01 | flat | $10 | ~3s |
| Plasma | $0.012 | flat | $10 | ~1s |
| opBNB | $0.015 | flat | $10 | ~1s |
| Aptos | $0.02 | flat | $10 | ~1s |
| Kaia | $0.02 | flat | $10 | ~2s |
| AVAX C-Chain | $0.04 | flat | $10 | ~2s |
| Optimism | $0.04 | flat | $10 | ~2s |
| Celo | $0.05 | flat | $10 | ~5s |
| Polygon | $0.07 | flat | $10 | ~3s |
| Tezos | $0.10 | flat | $10 | ~30s |
| Scroll | $0.10 | flat | $10 | ~2s |
| Arbitrum | $0.10 | flat | $10 | ~1s |
| Kava | $0.20 | flat | $10 | ~6s |
| NEAR | $0.20 | flat | $10 | ~1s |
| Solana | $0.30 | flat | $10 | ~1s |
| ERC20 | $0.50 | flat | $10 | ~12s |
| TRC20 | $1.00 | flat | $10 | ~5s |

**17 networks available.** Cheapest: BEP20 at $0.01.

### Key Notes

- Largest crypto exchange by volume. Highest execution reliability.
- FDUSD 0% maker fees on 7 pairs: BTC, ETH, BNB, SOL, XRP, DOGE, LINK.
- 58/60 configured symbols available (missing: HYPEUSDT).
- Server in Tokyo gives <1ms advantage — ideal for the primary VPS location.

---

## 3. OKX

### Overview

| Field | Value |
|-------|-------|
| **Headquarters** | Seychelles |
| **Founded** | 2017 |
| **Base taker fee** | 0.10% |
| **Token discount** | OKB (requires 500 OKB ~$25k, not practical) |
| **Effective taker fee** | 0.10% |
| **Fee model** | received |
| **Fee mechanism** | tier |
| **Demo/Testnet API** | Yes — `https://www.okx.com` + `x-simulated-trading: 1` header |

### Server Infrastructure

- **Location**: Hong Kong
- **Provider**: Alibaba Cloud / AWS HK region

### Latency from Key Locations

| From | Estimated RTT | Notes |
|------|:------------:|-------|
| Tokyo | ~35ms | |
| Bangkok | ~60ms | |
| Singapore | ~35ms | |
| Frankfurt | ~150ms | |

### Geo-Restrictions

**Fully banned**: US, Cuba, Iran, North Korea, Syria, Crimea.

**VPS location assessment**: Accessible from Japan, Thailand, Vietnam, Singapore, Germany, Turkey.

### WebSocket Details

| Field | Value |
|-------|-------|
| **Endpoint** | `wss://ws.okx.com:8443/ws/v5/public` |
| **Subscribe** | Post-connect JSON |
| **Symbol format** | `BTC-USDT` (dash-separated) |
| **Ping type** | String `"ping"` |
| **Ping interval** | 15s |
| **Data format** | JSON objects |
| **Has last_price** | Yes |
| **Has volume** | Yes |

### USDT Withdrawal Fees

All OKX fees are **dynamic** — these are conservative estimates.

| Network | Fee | Type | Notes |
|---------|:----|:----:|-------|
| Polygon | $0.10 | flat | Dynamic $0.01-0.10 |
| Solana | $0.10 | flat | Dynamic |
| BEP20 | $0.30 | flat | Dynamic $0.20-0.50 |
| AVAX C-Chain | $0.30 | flat | Dynamic |
| Arbitrum | $0.50 | flat | Dynamic |
| Optimism | $0.50 | flat | Dynamic |
| TRC20 | $1.00 | flat | Dynamic $0.10-2.30 |
| ERC20 | $3.00 | flat | Dynamic |

**8 networks available.** Cheapest: Polygon at ~$0.10.

### Key Notes

- 60/60 configured symbols available.
- OKB discount requires 500 OKB (~$25k) — not worth it at startup.
- Dynamic withdrawal fees make pre-configuration approximate.

---

## 4. Bybit

### Overview

| Field | Value |
|-------|-------|
| **Headquarters** | Dubai, UAE |
| **Founded** | 2018 |
| **Base taker fee** | 0.10% |
| **Token discount** | MNT/BIT 25% off → **0.075%** |
| **Effective taker fee** | 0.075% (with discount disabled currently) → 0.10% |
| **How to claim** | Hold MNT or BIT tokens on Bybit |
| **Fee model** | received |
| **Fee mechanism** | tier |
| **Demo/Testnet API** | Yes — `https://api-demo.bybit.com` |

### Server Infrastructure

- **Location**: Singapore
- **Provider**: AWS ap-southeast-1

### Latency from Key Locations

| From | Estimated RTT | Notes |
|------|:------------:|-------|
| Tokyo | ~68ms | |
| Bangkok | ~25ms | |
| Singapore | <1ms | Same region |
| Frankfurt | ~160ms | |

### Geo-Restrictions

**Fully banned**: US, UK, Singapore (exiting), Cuba, Iran, North Korea, Syria, Crimea.

**Note**: Bybit is exiting Japan entirely in 2026 due to FSA regulatory pressure.

**VPS location assessment**: Accessible from Thailand, Vietnam, Germany, Turkey. Japan currently works but at risk. Singapore blocked.

### WebSocket Details

| Field | Value |
|-------|-------|
| **Endpoint** | `wss://stream.bybit.com/v5/public/spot` |
| **Subscribe** | Post-connect JSON |
| **Symbol format** | `BTCUSDT` (uppercase, no separator) |
| **Ping type** | JSON `{"op":"ping"}` |
| **Ping interval** | 18s |
| **Special** | Delta merging for order book updates |
| **Has last_price** | Yes |
| **Has volume** | Yes |

### USDT Withdrawal Fees

All Bybit fees are **dynamic** — these are conservative estimates.

| Network | Fee | Type | Notes |
|---------|:----|:----:|-------|
| Aptos | $0.00 | flat | Promo, may expire |
| Plasma | $0.00 | flat | Likely supported |
| BEP20 | $0.20 | flat | Dynamic $0.20-0.50 |
| Arbitrum | $0.50 | flat | Dynamic |
| Optimism | $0.50 | flat | Dynamic |
| Polygon | $0.50 | flat | Dynamic |
| Solana | $0.50 | flat | Dynamic |
| TRC20 | $1.60 | flat | Confirmed |
| ERC20 | $3.00 | flat | Estimated |

**9 networks available.** Cheapest: Aptos at $0.00 (promo).

### Key Notes

- 58/60 configured symbols available (missing: ZECUSDT).
- MNT/BIT token discount not currently enabled in fee config.
- Exiting Japan in 2026 — plan accordingly for Tokyo VPS.

---

## 5. MEXC

### Overview

| Field | Value |
|-------|-------|
| **Headquarters** | Seychelles |
| **Founded** | 2018 |
| **Base taker fee** | 0.05% |
| **Token discount** | None needed (already lowest tier) |
| **Effective taker fee** | 0.05% |
| **Fee model** | received |
| **Fee mechanism** | instant |
| **Demo/Testnet API** | No |

### Server Infrastructure

- **Location**: Singapore
- **Provider**: AWS ap-southeast-1

### Latency from Key Locations

| From | Estimated RTT | Notes |
|------|:------------:|-------|
| Tokyo | ~68ms | |
| Bangkok | ~25ms | |
| Singapore | <1ms | Same region |
| Frankfurt | ~160ms | |

### Geo-Restrictions

**Fully banned**: Singapore, Hong Kong, US, Canada, China, North Korea, Iran, Cuba.

**Partially restricted**: Japan (API works but bot crackdown risk), Turkey (use `mexc.fm` domain as fallback).

**VPS location assessment**:

| Location | Access | Risk |
|----------|--------|------|
| Japan | Works currently | Medium — enforcement could escalate |
| Thailand | Fully accessible | Low |
| Vietnam | Fully accessible | Low |
| Singapore | **Blocked** | — |
| Germany | Accessible | Low |
| Turkey | Accessible (use mexc.fm) | Low |

### WebSocket Details

| Field | Value |
|-------|-------|
| **Endpoint** | `wss://wbs.mexc.com/ws` |
| **Subscribe** | Post-connect JSON |
| **Symbol format** | `BTCUSDT` (uppercase, no separator) |
| **Ping type** | JSON `{"method":"PING"}` |
| **Ping interval** | 15s |
| **Sub limit** | 30 subscriptions per connection |
| **Has last_price** | No |
| **Has volume** | No |

### USDT Withdrawal Fees

| Network | Fee | Type | Notes |
|---------|:----|:----:|-------|
| Arbitrum | $0.00 | flat | Permanent free |
| Polygon | $0.007 | flat | Very cheap |
| BEP20 | $0.00 | flat | Promo |
| Solana | $0.01 | flat | Near-zero |
| TRC20 | $1.00 | flat | Standard |
| ERC20 | $3.00 | flat | Estimated |

**6 networks available.** Cheapest: Arbitrum at $0.00 (permanent free).

### Key Notes

- 60/60 configured symbols available.
- Fully accessible from Bangkok VPS (Thailand not geo-blocked).
- 0.05% taker fee with no token requirement — excellent for arbitrage.
- No demo/testnet API — simulation only.
- 30 subscription limit per WS connection.

---

## 6. Bitget

### Overview

| Field | Value |
|-------|-------|
| **Headquarters** | Singapore |
| **Founded** | 2018 |
| **Base taker fee** | 0.10% |
| **Token discount** | BGB 20% off → **0.08%** |
| **Effective taker fee** | 0.08% |
| **How to claim** | Buy BGB, enable "Pay fees with BGB" |
| **Fee model** | token |
| **Fee mechanism** | instant |
| **Demo/Testnet API** | No |

### Server Infrastructure

- **Location**: Singapore
- **Provider**: AWS ap-southeast-1

### Latency from Key Locations

| From | Estimated RTT | Notes |
|------|:------------:|-------|
| Tokyo | ~68ms | |
| Bangkok | ~25ms | |
| Singapore | <1ms | Same region |
| Frankfurt | ~160ms | |

### Geo-Restrictions

**Fully banned**: US, Singapore (despite being HQ'd there), Cuba, Iran, North Korea, Syria, Crimea.

**VPS location assessment**: Accessible from Japan, Thailand, Vietnam, Germany, Turkey.

### WebSocket Details

| Field | Value |
|-------|-------|
| **Endpoint** | `wss://ws.bitget.com/v2/ws/public` |
| **Subscribe** | Post-connect JSON |
| **Symbol format** | `BTCUSDT` (uppercase, no separator) |
| **Ping type** | String `"ping"` |
| **Ping interval** | 25s |
| **Has last_price** | Yes |
| **Has volume** | Yes |

### USDT Withdrawal Fees (API-verified)

| Network | Fee | Type | Notes |
|---------|:----|:----:|-------|
| Plasma | $0.001 | flat | Verified — cheapest across all exchanges |
| Aptos | $0.03 | flat | Verified |
| Morph | $0.10 | flat | Verified |
| AVAX C-Chain | $0.11 | flat | Verified |
| BEP20 | $0.15 | flat | Verified |
| Arbitrum | $0.15 | flat | Verified |
| Optimism | $0.15 | flat | Verified |
| TON | $0.15 | flat | Verified |
| Polygon | $0.20 | flat | Verified |
| Solana | $1.00 | flat | Verified |
| TRC20 | $1.50 | flat | Verified |
| ERC20 | $1.60 | flat | Verified |

**12 networks available.** Cheapest: Plasma at $0.001 — the cheapest withdrawal fee across ALL exchanges.

### Key Notes

- 60/60 configured symbols available.
- Plasma at $0.001 makes Bitget the best source exchange for rebalancing.
- BGB discount is enabled in current fee config.

---

## 7. KuCoin

### Overview

| Field | Value |
|-------|-------|
| **Headquarters** | Seychelles |
| **Founded** | 2017 |
| **Base taker fee** | 0.10% |
| **Token discount** | KCS 20% off → **0.08%** |
| **Effective taker fee** | 0.08% |
| **How to claim** | Buy KCS, enable "Pay fees with KCS" |
| **Fee model** | token (rebate mechanism) |
| **Fee mechanism** | rebate |
| **Demo/Testnet API** | No |

### Server Infrastructure

- **Location**: Singapore
- **Provider**: AWS

### Latency from Key Locations

| From | Estimated RTT | Notes |
|------|:------------:|-------|
| Tokyo | ~68ms | |
| Bangkok | ~25ms | |
| Singapore | <1ms | Same region |
| Frankfurt | ~160ms | |

### Geo-Restrictions

**Fully banned**: US, Singapore, Cuba, Iran, North Korea, Syria, Crimea.

**VPS location assessment**: Accessible from Japan, Thailand, Vietnam, Germany, Turkey.

### WebSocket Details

| Field | Value |
|-------|-------|
| **Endpoint** | Dynamic (REST token first, then WS) |
| **Subscribe** | Post-connect JSON |
| **Symbol format** | `BTC-USDT` (dash-separated) |
| **Ping type** | JSON `{"type":"ping"}` |
| **Ping interval** | 18s |
| **Special** | Requires REST API call to get WS token + endpoint before connecting |
| **Has last_price** | Yes |
| **Has volume** | No |

### USDT Withdrawal Fees (API-verified)

| Network | Fee | Type | % Rate | % Min | Notes |
|---------|:----|:----:|:------:|:-----:|-------|
| Plasma | $0.40 | flat | — | — | Verified |
| KCC | $0.50 | flat | — | — | Verified |
| Aptos | $0.50 | flat | — | — | Verified |
| NEAR | $0.50 | flat | — | — | Verified |
| TON | $0.50 | flat | — | — | Verified |
| Polygon | $0.80 | flat | — | — | Verified |
| BEP20 | $1.00 | flat | — | — | Verified |
| Arbitrum | $1.00 | flat | — | — | Verified |
| Optimism | $1.00 | flat | — | — | Verified |
| AVAX C-Chain | $1.00 | flat | — | — | Verified |
| KAVA EVM | $1.00 | flat | — | — | Verified |
| Polkadot | $1.00 | flat | — | — | Verified |
| Tezos | $1.00 | flat | — | — | Verified |
| Solana | $1.50 | flat | — | — | Verified |
| TRC20 | $1.50 | flat | — | — | Verified |
| ERC20 | $5.50 | **percentage** | 0.2% | $5.50 | `max($5.50, amount × 0.2%)` |

**16 networks available.** Cheapest: Plasma at $0.40. **ERC20 is percentage-based** — the only percentage fee across all exchanges.

### Key Notes

- 60/60 configured symbols available.
- Unique REST-token-then-WS connection pattern.
- KCS rebate mechanism: fee is charged normally, KCS rebate credited back (not instant).
- ERC20 percentage fee: for $10,000 withdrawal = max($5.50, $20.00) = **$20.00**. Avoid ERC20 on KuCoin.

---

## 8. Gate.io

### Overview

| Field | Value |
|-------|-------|
| **Headquarters** | Cayman Islands |
| **Founded** | 2013 |
| **Base taker fee** | 0.10% |
| **Token discount** | GT 10% off → **0.09%** |
| **Effective taker fee** | 0.09% |
| **Fee model** | token |
| **Fee mechanism** | instant |
| **Demo/Testnet API** | No |

### Server Infrastructure

- **Location**: Singapore
- **Provider**: AWS ap-southeast-1

### Latency from Key Locations

| From | Estimated RTT | Notes |
|------|:------------:|-------|
| Tokyo | ~68ms | |
| Bangkok | ~25ms | |
| Singapore | <1ms | Same region |
| Frankfurt | ~160ms | |

### Geo-Restrictions

**Fully banned**: US, Canada, Cuba, Iran, North Korea, Syria, Crimea.

**VPS location assessment**: Accessible from Japan, Thailand, Vietnam, Singapore, Germany, Turkey.

### WebSocket Details

| Field | Value |
|-------|-------|
| **Endpoint** | `wss://api.gateio.ws/ws/v4/` |
| **Subscribe** | Post-connect JSON (per-symbol subscribe) |
| **Symbol format** | `BTC_USDT` (underscore-separated) |
| **Ping type** | JSON `{"channel":"spot.ping"}` |
| **Ping interval** | 15s |
| **Has last_price** | No |
| **Has volume** | No |

### USDT Withdrawal Fees

| Network | Fee | Type | Min Withdrawal | Notes |
|---------|:----|:----:|:--------------:|-------|
| TRC20 | $0.00 | **conditional** | 2,020 USDT | Free if ≥ 2,020 USDT, otherwise unavailable |
| BEP20 | $0.50 | flat | $10 | Promo rate, may have expired |
| Arbitrum | $0.50 | flat | $10 | Estimated |
| Optimism | $0.50 | flat | $10 | Estimated |
| Polygon | $0.50 | flat | $10 | Estimated |
| Solana | $0.50 | flat | $10 | Estimated |
| AVAX C-Chain | $0.50 | flat | $10 | Estimated |
| ERC20 | $4.00 | flat | $10 | Estimated |

**8 networks available.** Cheapest: TRC20 at $0.00 (conditional — requires ≥ 2,020 USDT withdrawal). Otherwise BEP20 at $0.50.

### Key Notes

- 60/60 configured symbols available.
- GT token discount is minimal (~10%) — not worth purchasing.
- TRC20 conditional free tier is unique: free only for large withdrawals (≥ $2,020).
- No last_price or volume from WebSocket — limited data compared to other exchanges.

---

## 9. Pionex

### Overview

| Field | Value |
|-------|-------|
| **Headquarters** | Singapore (WEBOT PTE. LTD. / BitUniverse) |
| **Founded** | 2019 |
| **Base taker fee** | 0.05% |
| **Token discount** | None (flat rate, no VIP tiers) |
| **Effective taker fee** | 0.05% |
| **Fee model** | received |
| **Fee mechanism** | instant |
| **Demo/Testnet API** | No |

### Server Infrastructure

- **Location**: Likely US East (Virginia) — based on 2021 incident where Binance blocked "Eastern United States" IP from Pionex's broker connection
- **Provider**: AWS (confirmed by case study: Aurora, DynamoDB, Kinesis, Redshift)
- **CDN**: Cloudflare (all public endpoints proxied through anycast network)
- **DNS**: `ws.pionex.com` → `cf-cdn.pionex.com` → Cloudflare IPs (104.18.2-3.190)
- **Dev environment**: AWS CloudFront (`*.pionexdev.com`)
- **S3 buckets**: us-west-2 (Oregon) for dev/user files

**Important**: Pionex aggregates ~50-60% of order book from Binance (per CTO statement). Pionex↔Binance arbitrage will be near-zero. Value is in Pionex vs other exchanges (OKX, KuCoin, Gate.io, Bybit, Bitget).

### Latency from Key Locations

| From | Estimated RTT | Notes |
|------|:------------:|-------|
| Tokyo | ~150-170ms | If origin in Virginia (via Cloudflare) |
| Bangkok | ~180-200ms | If origin in Virginia |
| Singapore | ~220-240ms | If origin in Virginia |
| Frankfurt | ~80-100ms | Closer to US East |

If Pionex has migrated to Singapore (possible but unconfirmed):

| From | Estimated RTT | Notes |
|------|:------------:|-------|
| Tokyo | ~65-75ms | Via Cloudflare |
| Bangkok | ~30-40ms | Via Cloudflare |
| Singapore | ~5-15ms | Via Cloudflare |

### Geo-Restrictions

**Fully banned**: US, Canada, UK, France, Netherlands, Austria, China, Hong Kong, **Singapore** (despite being HQ'd there), **Japan**, Cuba, Iran, North Korea, Syria, Afghanistan, Lebanon, Libya, Somalia, South Sudan, Sudan, Venezuela, Yemen, Zimbabwe, Congo DR.

**CRITICAL**: Japan (phone code 81) is on the **official KYC unsupported list**. This is confirmed, not uncertain.

**VPS location assessment**:

| Location | Access | Risk |
|----------|--------|------|
| **Japan** | **KYC-blocked** | **HIGH** — Public WS may work, trading API risky |
| **Singapore** | **Fully blocked** | — |
| Thailand | Not restricted | Low |
| Vietnam | Not restricted | Low |
| Germany | Not restricted | Medium — France/Netherlands/Austria ARE blocked, EU MiCA risk |
| Turkey | Not restricted | Low |

### WebSocket Details

| Field | Value |
|-------|-------|
| **Endpoint** | `wss://ws.pionex.com/wsPub` |
| **Subscribe** | Post-connect JSON |
| **Symbol format** | `BTC_USDT` (underscore-separated, uppercase) |
| **Ping type** | JSON `{"op":"PING"}` (server sends, client replies `{"op":"PONG"}`) |
| **Ping interval** | 15s |
| **Sub limit** | Undocumented — use 20 symbols × 2 topics = 40 per connection |
| **Connections used** | 3 (multi-connection for 60 symbols, max 10 per IP) |
| **Topics** | DEPTH (bid/ask) + TRADE (last price) — separate subscriptions |
| **Has last_price** | Yes (via TRADE topic) |
| **Has volume** | No |

### USDT Withdrawal Fees

| Network | Fee | Type | Notes |
|---------|:----|:----:|-------|
| Arbitrum | $0.20 | flat | Cheapest on Pionex |
| Optimism | $0.20 | flat | |
| BEP20 | $0.80 | flat | |
| Solana | $1.00 | flat | |
| TRC20 | $1.00 | flat | |
| ERC20 | $10.00 | flat | Very expensive — avoid |

**6 networks available.** Cheapest: Arbitrum/Optimism at $0.20.

### Key Notes

- 60/60 configured symbols available.
- Aggregates 50-60% from Binance — Pionex↔Binance pairs will have near-zero spread.
- Undocumented WS topic limit caused reconnect loop with single connection — fixed with multi-connection architecture (3 connections × 20 symbols).
- DEPTH subscription supports `"limit": 1` parameter (only returns best bid/ask).
- Max 10 WebSocket connections per IP.
- No VIP tiers, no token discount — flat 0.05% for everyone.
- Japan KYC-blocked but public WebSocket (market data) likely works from any IP.

---

## Fee Comparison Matrix

### Effective Taker Fees (with all discounts applied)

| Exchange | Base Rate | Discount | Effective Rate |
|----------|:---------:|:--------:|:--------------:|
| **Bitfinex** | 0.00% | — | **0.00%** |
| **MEXC** | 0.05% | — | **0.05%** |
| **Pionex** | 0.05% | — | **0.05%** |
| **Binance** | 0.10% | BNB 25% | **0.075%** |
| **Bybit** | 0.10% | MNT/BIT 25% | **0.075%** |
| **Bitget** | 0.10% | BGB 20% | **0.08%** |
| **KuCoin** | 0.10% | KCS 20% | **0.08%** |
| **OKX** | 0.10% | OKB (impractical) | **0.10%** |
| **Gate.io** | 0.10% | GT 10% | **0.09%** |

### Best Exchange Pairs for Arbitrage (by total fee cost)

| Pair | Buy Fee | Sell Fee | Total Cost | Notes |
|------|:-------:|:--------:|:----------:|-------|
| Bitfinex ↔ any | 0.00% | varies | 0.00-0.10% | Best possible — Bitfinex side is free |
| MEXC ↔ Pionex | 0.05% | 0.05% | 0.10% | Cheapest non-Bitfinex pair |
| MEXC ↔ Binance | 0.05% | 0.075% | 0.125% | |
| Pionex ↔ Binance | 0.05% | 0.075% | 0.125% | Near-zero spread (shared order book) |
| Binance ↔ Bybit | 0.075% | 0.075% | 0.15% | |
| MEXC ↔ Bitget | 0.05% | 0.08% | 0.13% | |

### Cheapest Withdrawal Fee Per Exchange

| Exchange | Cheapest Network | Fee | Notes |
|----------|:----------------:|:---:|-------|
| **Bitfinex** | TRC20/Arb/Opt/etc | $0.00 | 14 free networks |
| **MEXC** | Arbitrum | $0.00 | Permanent free |
| **Bybit** | Aptos | $0.00 | Promo, may expire |
| **Bitget** | Plasma | $0.001 | Verified — cheapest non-zero fee |
| **Binance** | BEP20 | $0.01 | 17 networks available |
| **OKX** | Polygon | $0.10 | Dynamic fees |
| **Pionex** | Arbitrum | $0.20 | |
| **KuCoin** | Plasma | $0.40 | |
| **Gate.io** | TRC20 | $0.00 | Conditional: requires ≥ 2,020 USDT |
| **Gate.io** | BEP20 | $0.50 | Unconditional cheapest |

---

## WebSocket Implementation Comparison

| Aspect | Binance | OKX | Bybit | MEXC | Bitget | KuCoin | Gate.io | Pionex | Bitfinex |
|--------|:-------:|:---:|:-----:|:----:|:------:|:------:|:-------:|:------:|:--------:|
| Subscribe | URL params | Post-connect | Post-connect | Post-connect | Post-connect | Post-connect | Post-connect | Post-connect | Post-connect |
| Symbol format | `btcusdt` | `BTC-USDT` | `BTCUSDT` | `BTCUSDT` | `BTCUSDT` | `BTC-USDT` | `BTC_USDT` | `BTC_USDT` | `tBTCUST` |
| Ping type | WS-level | `"ping"` | `{"op":"ping"}` | `{"method":"PING"}` | `"ping"` | `{"type":"ping"}` | `{"channel":"spot.ping"}` | `{"op":"PING"}` | `{"event":"ping"}` |
| Ping interval | 20s | 15s | 18s | 15s | 25s | 18s | 15s | 15s | 15s |
| Has last_price | Yes | Yes | Yes | No | Yes | Yes | No | Yes (TRADE) | Yes |
| Has volume | Yes | Yes | Yes | No | Yes | No | No | No | Yes |
| Sub limit | 1024 | — | — | 30 | — | — | — | ~40/conn | 30/conn |
| Connections | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 3 | 2 |
| Special | — | — | Delta merge | 30 sub limit | — | REST token | Per-symbol sub | DEPTH+TRADE | Array data |

---

## Referral & Affiliate Programs

### Overview

Two types of referral programs exist on crypto exchanges:

- **Referral Program** (standard): Any registered user can generate a code instantly — no application, no followers, no approval needed. Just go to the exchange's referral page and create one. Lower commission (10-20%). Invitee kickback limited. Code must be entered at registration — cannot bind existing accounts.
- **Affiliate Program** (formal): Partnership requiring application and approval. Higher commission (30-60%). Can often bind existing users. Requires audience/community proof (followers, website, etc.). **Not practical unless you have a social media presence.**

For the sister's new accounts strategy, the **standard referral program** (zero requirements) is all you need. The affiliate program is only relevant for binding existing accounts.

### Per-Exchange Referral Details

#### Bitfinex
- **Not applicable** — 0% fees already. No referral benefit possible.

#### Binance
- **Referral** (any user): Create up to 20 codes. Base commission 20% (40% with ≥500 BNB). Invitee kickback: 0-10% (base) or 0-20% (500 BNB holder).
- **Affiliate** (requires 5k+ followers or 500+ community): Apply at [binance.com/en/events/affiliate](https://www.binance.com/en/events/affiliate). Up to 40% commission.
- **Existing account binding**: Only via affiliate "Recall Program" — requires invitee account >180 days old AND inactive for 180 days. Pre-KYC accounts can still add a code. **Effectively impossible for active accounts.**

#### OKX
- **Referral** (any user): Default 30% commission, settled hourly in USDT. Invitee gets 0-20% fee discount (set by referrer when creating code).
- **Affiliate** (requires 10 active referrals first): 5-month protection period on commission rate.
- **Existing account binding**: Yes — affiliate portal has "Invite existing OKX users" link. No time limit. Invitee opens link while logged in → clicks "Bind Now". Requires affiliate status.

#### Bybit
- **Referral** (any user): Commission up to 30%. Lifetime commissions.
- **Affiliate** (requires audience/community proof): Apply at [affiliates.bybit.com](https://affiliates.bybit.com). Up to 50% lifetime commission. Dedicated account manager.
- **Existing account binding**: Affiliate/invitation code can be added within **14 days** of registration (no referrer already bound). After 14 days, not accepted.

#### MEXC
- **Referral** (any user): Up to 40% commission on Spot and Futures.
- **Affiliate** (requires 2k+ MX tokens + 5 referees, or 20k+ MX): Higher tiers available.
- **Existing account binding**: Not officially supported. Accounts may already be silently bound (with 0% kickback). Contact support to request unbind/rebind.

#### Bitget
- **Referral** (any user): Standard referral program available to all users.
- **Affiliate** (requires 100+ followers): Simple application form.
- **Existing account binding**: Not officially supported. Contact support, or watch for occasional "Apply a Referral Code" promotions.

#### KuCoin
- **Referral** (any user): Standard referral available to all users.
- **Affiliate** (requires 5k+ followers or 500+ community): Apply at [kucoin.com/affiliate](https://www.kucoin.com/affiliate). Up to 60%+ commission.
- **Existing account binding**: Not supported. New account only.

#### Gate.io
- **Referral** (any user): Standard referral program. Commission 30-50% depending on tier.
- **Affiliate** (no strict requirement): Apply via [gate.com/questionnaire/723](https://www.gate.com/questionnaire/723). Up to 60% commission.
- **Existing account binding**: Not officially documented. Contact support.

#### Pionex
- **Referral** (any user): Fixed 20% spot / 15% futures commission. Can share portion as invitee rebate.
- **Affiliate** (invite-only): Email service@pionex.com. Requires 100+ active traders, or 500+ YouTube views, or 10+ referrals.
- **Existing account binding**: Not documented. Contact support.

### Summary Table

| Exchange | Referral (any user) | Affiliate Requirement | Bind Existing? | Max Commission |
|----------|:-------------------:|----------------------|:--------------:|:--------------:|
| Bitfinex | N/A (0% fees) | — | N/A | N/A |
| Binance | 20% commission | 5k followers | Recall (180d inactive) | 40% |
| OKX | 30% commission | 10 active referrals | **Yes** (affiliate link) | 30% |
| Bybit | 30% commission | Audience proof | **14 days** after registration | 50% |
| MEXC | 40% commission | 2k MX tokens | Support ticket | 40% |
| Bitget | Standard | 100 followers | Support ticket | ~30% |
| KuCoin | Standard | 5k followers | No | 60% |
| Gate.io | 30-50% commission | No strict requirement | Support ticket | 60% |
| Pionex | 20% spot / 15% futures | Invite-only | Support ticket | 50% |

### Referrer vs Invitee Split (Bot Config)

When maximizing invitee kickback to reduce bot trading costs:

| Exchange | Pool Type | Total Pool | Invitee Kickback | Referrer Commission | Invitee Duration | Referrer Duration |
|----------|-----------|:---:|:---:|:---:|---|---|
| Bitfinex | N/A | — | — | — | — | — |
| Binance | Shared | 20% | 10% (max at base) | 10% | Permanent | Permanent |
| OKX | Shared | 30% | 20% (max) | 10% | Permanent | Permanent |
| Bybit | Independent | — | 20% (fixed) | 20% (separate) | **90 days only** | 365 days |
| MEXC | Independent | — | 10% (fixed) | 40% (separate) | Lifetime | 1,080 days |
| Bitget | Unknown | — | ~20% (est.) | ~20% (est.) | Unknown | Unknown |
| KuCoin | Shared | 20% | 20% (max) | 0% | 365 days | 365 days |
| Gate.io | Shared | 40% | 30% (max) | 10% | 1 year | 1 year |
| Pionex | Shared | 20% | 20% (max) | 0% | Ongoing | Ongoing |

**Shared pool**: Invitee + referrer percentages add up to the total pool. Giving more to invitee means referrer earns less.
**Independent**: Invitee kickback and referrer commission are separate — both are the full advertised rate.

**Time limit note**: Bybit invitee kickback expires after 90 days — set `referral_cashback_pct` to 0 in Fee Management after expiry.

### Recommended Strategy

**Chosen approach: Sister's new accounts with referral codes (win-win).**

Why not retro-active codes on existing accounts? Exchanges use referral codes as customer acquisition tools — they incentivize bringing *new* users. Once registered, you're already their customer. Retro-active binding would let existing users shop for kickbacks without the exchange gaining anyone new. Only OKX allows it (aggressive market share strategy). The others either reject it outright or require impossible conditions (Binance: 180 days inactive).

**Plan:**
1. Generate a **standard referral code** on each of the 8 exchanges (instant, zero requirements).
2. Sister signs up on each exchange using your code, completes KYC.
3. Sister generates API keys → bot uses her accounts for real trading.
4. You deposit the capital on her accounts (she doesn't invest anything).
5. Set maximum invitee kickback % — reduces her effective taker fees (bot pays less).

**Win-win:**
- **Sister wins**: Lower trading fees via invitee kickback (fee discount on every trade). No capital risk — you deposit and manage everything.
- **You win**: Referrer commission on every trade the bot executes (passive income). Plus, the invitee kickback directly reduces bot trading costs since the bot operates on her accounts.

**No ban risk**: Sister is a real person with her own identity and KYC. Using a referral code at registration is exactly how the system is designed. API key delegation for third-party trading is a standard use case (API keys exist for this purpose). No self-referral, no fake accounts, no ToS violation.

**For existing accounts** (lower priority, optional):
1. **OKX** — Find an affiliate online, use their "invite existing users" link. Immediate binding, no time limit.
2. **Bybit** — If account <14 days old, add affiliate code in settings. Otherwise, support ticket.
3. **MEXC** — Contact support to unbind 0% referral and rebind to a better one.
4. **Others** — Contact support, ask to bind a referral retroactively. Worst case: they say no.

---

## Dropped Exchanges

| Exchange | Base Fee | Reason for Dropping |
|----------|:--------:|---------------------|
| **HTX (Huobi)** | 0.20%/0.20% | Too expensive. 25% HT discount still yields 0.15%. Gzip-compressed binary WS messages. |
| **Kraken** | 0.25%/0.40% | Way too expensive. Only ~11/20 original USDT pairs available. |
| **Crypto.com** | — | No Plasma support, missing symbols, poor fit. |
| **Deepcoin** | 0.10%/0.10% | Scam. ScamAdviser 0/10, claimed 0% fees actually 0.10%, advance-fee withdrawal scam. |
| **WEEX** | 0.10%/0.10% | No fee advantage, Trustpilot 2.4/5, Georgia cease-and-desist, account freezing. |
| **Phemex** | 0.10% | PT token 20% discount NOT available for API trades (dealbreaker). $73M hack Jan 2025, Trustpilot 2.3-2.6/5. |
| **Toobit** | 0.10% | No token discount, 20x volume inflation, dynamic withdrawal fees, no testnet, Trustpilot 2.8/5. |
| **BingX** | 0.10% | No fee advantage over existing exchanges. |
| **WhiteBIT** | — | EU-focused, limited USDT pairs, no significant advantage. |

See [ALTERNATIVE_EXCHANGES_SCREENING.md](ALTERNATIVE_EXCHANGES_SCREENING.md) for detailed screening of all evaluated exchanges.
