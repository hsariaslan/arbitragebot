# Transfer & Trading Fees — Comprehensive Research

**Last updated:** 2026-02-26
**Researched by:** Claude Code (web research from official exchange pages, fee aggregators, and announcements)

This document covers all fee-related findings for ArbitrageBot's 6 active exchanges plus MEXC (future). Includes USDT withdrawal fees per network, internal trading fees (spot taker/maker), alternative transfer methods, and fee reduction strategies.

---

## Table of Contents

1. [USDT Withdrawal Fees Per Exchange](#1-usdt-withdrawal-fees-per-exchange)
2. [Internal Trading Fees (Spot Taker/Maker)](#2-internal-trading-fees-spot-takermaker)
3. [Convert/Swap Features](#3-convertswap-features)
4. [Zero-Fee Trading Pairs](#4-zero-fee-trading-pairs)
5. [Cross-Exchange Transfer via Crypto (Buy-Transfer-Sell)](#5-cross-exchange-transfer-via-crypto-buy-transfer-sell)
6. [Cheapest Transfer Routes Between Exchanges](#6-cheapest-transfer-routes-between-exchanges)
7. [Fee Reduction Methods](#7-fee-reduction-methods)
8. [Referral Programs](#8-referral-programs)
9. [Plasma Network Status](#9-plasma-network-status)
10. [Bot Config vs Research — Discrepancies](#10-bot-config-vs-research--discrepancies)
11. [Recommendations](#11-recommendations)
12. [Sources](#12-sources)

---

## 1. USDT Withdrawal Fees Per Exchange

Most exchanges charge a **flat fee per withdrawal** (same fee for $10 or $10,000). **Exception:** KuCoin's ERC20 USDT withdrawal uses a percentage-based fee (0.2% rate, $5.50 minimum). All deposits are **free** on all exchanges on all networks.

### Binance

Binance publishes exact fees. Most transparent of all exchanges. 17 networks supported for USDT.

| Network | Withdrawal Fee | Min Withdrawal | Speed |
|---------|:---:|:---:|:---:|
| **BNB Smart Chain (BEP20)** | **$0.01** | 10 USDT | ~3s |
| **Plasma** | $0.012 | 10 USDT | <1s |
| **opBNB** | $0.015 | 10 USDT | ~1s |
| **Aptos** | $0.02 | 10 USDT | ~1s |
| **Kaia** | $0.02 | 10 USDT | ~2s |
| **Avalanche C-Chain** | $0.04 | 10 USDT | ~2s |
| **Optimism** | $0.04 | 10 USDT | ~2s |
| **Celo** | $0.05 | 10 USDT | ~5s |
| **Polygon PoS** | $0.07 | 10 USDT | ~2-5s |
| **Tezos** | $0.10 | 10 USDT | ~30s |
| **Scroll** | $0.10 | 10 USDT | ~2s |
| **Arbitrum One** | $0.10 | 10 USDT | ~0.3s |
| **Kava** | $0.20 | 10 USDT | ~6s |
| **Near Protocol** | $0.20 | 10 USDT | ~1s |
| **Solana** | $0.30 | 10 USDT | ~0.4s |
| **Ethereum (ERC20)** | $0.50 | 10 USDT | ~12s |
| **TRON (TRC20)** | $1.00 | 10 USDT | ~3-5s |

**Bot config: $0.01 (BEP20) — CORRECT.**

**Notes:**
- BEP20 is the cheapest and has universal exchange support. Best default for Binance withdrawals.
- Plasma is almost as cheap ($0.012) but has limited exchange support (see Section 9).
- opBNB ($0.015) is a newer option, very cheap but check destination exchange support.
- TRC20 is surprisingly expensive at $1.00. Its "cheap" reputation is outdated.
- Free transfers to other Binance users via Binance Pay or internal transfer (by email/UID/phone).

### OKX

OKX uses **dynamic fees** that adjust based on real-time network conditions. Exact fees fluctuate and are not published as fixed values. These are estimates from multiple sources.

| Network | Estimated Fee | Notes |
|---------|:---:|---|
| **Polygon PoS** | ~$0.01-0.10 | Very cheap per OKX documentation |
| **Solana** | ~$0.01-0.10 | Low fee |
| **TRC20 (TRON)** | ~$0.10-2.30 | Conflicting data: OKX says ~$0.10, TradingFinder says $2.30. May depend on network congestion. |
| **BEP20 (BSC)** | ~$0.20-0.50 | Dynamic, estimated from general range |
| **Arbitrum One** | <$0.50 | "A fraction of Ethereum" per OKX docs |
| **Optimism** | <$0.50 | Similar to Arbitrum |
| **Avalanche C-Chain** | ~$0.10-0.50 | Estimated |
| **Ethereum (ERC20)** | >$3.00 | Can exceed $3 per OKX documentation |

**Bot config: $0.01 (Arbitrum) — LIKELY TOO LOW.** OKX's dynamic fees make Arbitrum probably $0.20-0.50, not $0.01. The on-chain cost may be $0.004 but OKX adds significant markup. Recommend updating to **$0.30**.

**Notes:**
- OKX does NOT publish fixed withdrawal fees. All values are estimates.
- Fees vary by time of day and network congestion.
- Free internal transfers between OKX users via UID, email, or phone number (explicitly confirmed as fee-free).
- Dynamic fee model means the bot cannot rely on a fixed value. The configured value should be a conservative estimate.

### Bybit

Bybit also uses **dynamic fees** adjusted in real-time. Limited published data.

| Network | Estimated Fee | Notes |
|---------|:---:|---|
| **Aptos** | **$0.00 (promo)** | Zero-fee USDT withdrawal promotion. Check if still active. |
| **BEP20 (BSC)** | ~$0.20-0.50 | Estimated; not officially published |
| **Arbitrum One** | ~$0.50-1.00 | Estimated |
| **Optimism** | ~$0.50-1.00 | Estimated |
| **Polygon PoS** | ~$0.50-1.00 | Estimated |
| **Solana** | ~$0.50-1.00 | Estimated |
| **Plasma** | ~$0.00 | If supported (confirmed partnership) |
| **TRC20 (TRON)** | **$1.60** | Confirmed by TradingFinder |
| **Ethereum (ERC20)** | ~$3.00 | Estimated from industry average |

**Bot config: $0.20 (BEP20) — APPROXIMATELY CORRECT.** BEP20 is likely $0.20-0.50. TRC20 is confirmed at $1.60 (much higher).

**Notes:**
- Aptos zero-fee USDT withdrawal promotion was announced in 2025. Check current status on Bybit.
- Bybit has confirmed Plasma partnership — may support Plasma USDT transfers.
- Free internal transfers between Bybit accounts.
- MNT/BIT token discounts apply to TRADING fees only, NOT withdrawal fees.

### Bitget

Bitget publishes exact per-chain withdrawal fees via their public API. No additional processing fee (`extraWithdrawFee = 0` for all USDT chains).

| Network | Withdrawal Fee | Min Withdrawal | Source |
|---------|:---:|:---:|---|
| **Plasma** | **$0.001** | 10 USDT | Bitget API (cheapest!) |
| **Aptos** | **$0.03** | 10 USDT | Bitget API |
| **Morph** | $0.10 | 10 USDT | Bitget API |
| **AVAX C-Chain** | $0.11 | 10 USDT | Bitget API |
| **BEP20 (BSC)** | $0.15 | 10 USDT | Bitget API |
| **Arbitrum One** | $0.15 | 10 USDT | Bitget API |
| **Optimism** | $0.15 | 10 USDT | Bitget API |
| **TON** | $0.15 | 10 USDT | Bitget API |
| **Polygon PoS** | $0.20 | 10 USDT | Bitget API |
| **Solana** | $1.00 | 10 USDT | Bitget API |
| **TRC20 (TRON)** | $1.50 | 10 USDT | Bitget API |
| **Ethereum (ERC20)** | $1.60 | 10 USDT | Bitget API |

**Bot config: $0.10 (Arbitrum) — CLOSE BUT SLIGHTLY LOW.** Arbitrum is actually $0.15. However, Plasma ($0.001) and Aptos ($0.03) are much cheaper. Recommend updating to **$0.001 (Plasma)** or **$0.03 (Aptos)** if those networks are used.

**Notes:**
- Bitget supports Plasma at just $0.001 — cheapest withdrawal option of any exchange.
- Aptos at $0.03 is the second cheapest option.
- BGB token discount applies to TRADING fees only (20% off), NOT withdrawal fees.
- All fees verified from `https://api.bitget.com/api/v2/spot/public/coins?coin=USDT` (Feb 2026).

### KuCoin

KuCoin is consistently the **most expensive** for withdrawals among these 6 exchanges. Fees verified from their public API.

| Network | Withdrawal Fee | Min Withdrawal | Source |
|---------|:---:|:---:|---|
| **Plasma** | **$0.40** | 5 USDT | KuCoin API |
| **KCC (KuCoin Chain)** | $0.50 | 1 USDT | KuCoin API |
| **Aptos** | $0.50 | 1 USDT | KuCoin API |
| **NEAR** | $0.50 | 3 USDT | KuCoin API |
| **TON** | $0.50 | 1 USDT | KuCoin API |
| **Polygon PoS** | $0.80 | 1.6 USDT | KuCoin API |
| **BEP20 (BSC)** | **$1.00** | 10 USDT | KuCoin API |
| **Arbitrum One** | $1.00 | 5 USDT | KuCoin API |
| **Optimism** | $1.00 | 3 USDT | KuCoin API |
| **AVAX C-Chain** | $1.00 | 2 USDT | KuCoin API |
| **KAVA EVM** | $1.00 | 3 USDT | KuCoin API |
| **Asset Hub (Polkadot)** | $1.00 | 10 USDT | KuCoin API |
| **Tezos (XTZ)** | $1.00 | 2 USDT | KuCoin API |
| **Solana** | **$1.50** | 3 USDT | KuCoin API |
| **TRC20 (TRON)** | $1.50 | 3 USDT | KuCoin API |
| **ERC20 (Ethereum)** | **$5.50 + 0.2% rate** | 30 USDT | KuCoin API (percentage-based!) |

**Bot config: $0.80 (Polygon) — CORRECT for Polygon.** But Plasma ($0.40) and KCC ($0.50) are cheaper options.

**Notes:**
- KuCoin's cheapest option is now Plasma at $0.40 (if destination supports it), then KCC at $0.50.
- BEP20 is $1.00 — significantly more expensive than the $0.50-0.80 previously estimated.
- ERC20 is the only network with a percentage-based fee (0.2% rate, $5.50 minimum). For large withdrawals (> $2,750), the 0.2% rate exceeds the $5.50 flat portion.
- KCS token discount applies to TRADING fees only (up to 60% off), NOT withdrawal fees.
- Free internal transfers between KuCoin users.
- Periodic zero-fee promos (BEP20 in late 2024). Watch for future promotions.
- All fees verified from `https://api.kucoin.com/api/v3/currencies/USDT` (Feb 2026).

### Gate.io

Gate.io has a unique advantage: **permanently free TRC20 USDT withdrawals** (subsidized ~$10M/year by Gate.io).

| Network | Estimated Fee | Notes |
|---------|:---:|---|
| **TRC20 (TRON)** | **$0.00 (FREE)** | **Permanent.** Gate.io subsidizes the network fee. Min: 2,020 USDT. Max: 1M per tx, $2M/day. |
| **BEP20 (BSC)** | ~$0.50 or **$0.00 (promo)** | Zero-fee promo for amounts >= 20 USDT ran Jan 1 - Mar 31, 2025. **Likely expired** as of Feb 2026. |
| **Arbitrum One** | ~$0.50 | Estimated |
| **Optimism** | ~$0.50 | Estimated |
| **Polygon PoS** | ~$0.50 | Estimated |
| **Solana** | ~$0.50 | Estimated |
| **Avalanche C-Chain** | ~$0.50 | Estimated |
| **Ethereum (ERC20)** | ~$3-5 | Estimated from industry standard |

**Bot config: $0.05 (Arbitrum/Polygon) — TOO LOW if BEP20 promo expired.** Non-TRC20 networks are likely ~$0.50. TRC20 is free but requires 2,020 USDT minimum withdrawal.

**Notes:**
- The TRC20 free withdrawal is a permanent program, not a limited promotion. Gate.io committed to subsidizing TRON gas fees indefinitely.
- The 2,020 USDT minimum for free TRC20 is significant — the bot's rebalancing amounts ($200-400) are below this threshold.
- For amounts below 2,020 USDT, other networks cost ~$0.50.
- GT token discount applies to TRADING fees only (~10% off), NOT withdrawal fees.
- BEP20 zero-fee promo was Q1 2025 only. No evidence of extension.

### MEXC (Future — Currently Geo-Blocked)

MEXC offers some of the cheapest withdrawal options. Currently disabled in the bot due to Japan geo-restrictions.

| Network | Estimated Fee | Notes |
|---------|:---:|---|
| **Arbitrum One** | **$0.00 (FREE)** | Permanent free promotion |
| **Polygon PoS** | ~$0.007 | Very cheap |
| **BEP20 (BSC)** | **$0.00 (promo)** | Periodic zero-fee promotion |
| **Solana** | Near-zero | Very cheap |
| **TRC20 (TRON)** | $1.00 | Standard |
| **Ethereum (ERC20)** | Higher | Estimated |

**Bot config: $0.01 (Polygon, commented out) — APPROXIMATELY CORRECT.** MEXC is genuinely cheap. Arbitrum is free.

---

## 2. Internal Trading Fees (Spot Taker/Maker)

"Internal trading" means buying or selling crypto for USDT on the **same exchange** (e.g., selling accumulated AXS for USDT on Bitget to recover capital). This is a regular spot market trade — the only cost is the spot trading fee.

### Spot Fee Comparison (VIP0 / Standard Tier)

| Exchange | Maker Fee | Taker Fee | With Token Discount (Maker/Taker) | Discount Token |
|----------|:---:|:---:|:---:|:---:|
| **Binance** | 0.10% | 0.10% | 0.075% / 0.075% | BNB (25% off) |
| **OKX** | 0.08% | 0.10% | N/A at VIP0 | OKB (requires 500 OKB ~$25k) |
| **Bybit** | **0.00%** | **0.00%** | N/A (already free) | Zero-fee promo active |
| **MEXC** | **0.00%** | 0.05% | N/A (already cheapest) | None needed |
| **Bitget** | 0.10% | 0.10% | 0.08% / 0.08% | BGB (20% off) |
| **KuCoin** | 0.10% | 0.12% | 0.08% / 0.096% | KCS (20% rebate) |
| **Gate.io** | 0.10% | 0.10% | 0.09% / 0.09% | GT (10% off) |

### Key Findings

**Bybit zero-fee promotion:** As of Feb 2026, Bybit reportedly has 0% maker AND taker fees on ALL spot pairs. This is a "limited time" promotion — it could end at any time. If active, Bybit is the cheapest exchange for all trading. Standard rates revert to 0.10%/0.10% when the promo ends.

**MEXC 0% maker (permanent):** Since Dec 2025, MEXC has 0% maker fee on ALL spot pairs permanently. Their taker fee is 0.05%. They also periodically run 0% taker events. This is not a promotion — it is their permanent fee structure.

**Gate.io matches OKX/Bybit/Binance:** 0.10%/0.10% base rate is the industry standard. With GT discount (10% off), effective rate is 0.09%/0.09%.

**Maker vs Taker for rebalancing:** Using limit orders (maker) instead of market orders (taker) saves 0-0.02% on most exchanges. Not significant enough to justify the execution complexity for rebalancing, where fill certainty matters.

### Internal Rebalance Cost per $100 Trade

| Exchange | Taker Cost | Maker Cost | Notes |
|----------|:---:|:---:|---|
| Bybit (promo) | $0.00 | $0.00 | Zero-fee promo — verify if still active |
| MEXC | $0.05 | $0.00 | 0% maker permanent |
| Binance (BNB) | $0.075 | $0.075 | With BNB discount |
| OKX | $0.10 | $0.08 | Maker is cheaper |
| Bitget (BGB) | $0.08 | $0.08 | With BGB discount |
| KuCoin (KCS) | $0.096 | $0.08 | With KCS discount |
| Gate.io | $0.10 | $0.10 | Standard; 0.09% with GT |

---

## 3. Convert/Swap Features

Every major exchange offers a "Convert" or "Quick Swap" feature that advertises zero fees. The cost is hidden in the spread between their quoted price and the actual market price.

| Exchange | Feature Name | API Available? | Explicit Fee | Hidden Spread | Max Per Trade |
|----------|---|:---:|:---:|:---:|:---:|
| **Binance** | Binance Convert | Yes (`/sapi/v1/convert/getQuote`) | 0% | ~0.05-0.20% | Varies |
| **OKX** | Easy Convert | Deprecated → replaced | 0% | ~0.10-0.30% | Varies |
| **Bybit** | Convert | Yes (`/v5/asset/convert/`) | 0% | ~0.10-0.30% | Varies |
| **MEXC** | Convert | Likely | 0% | Unknown | Varies |
| **Bitget** | Convert (upgraded Mar 2025) | Yes | 0%, "zero slippage" claimed | ~0.05-0.20% real spread | $300K |
| **KuCoin** | Convert | Yes (`/api/v1/convert/`) | 0% | ~0.10-0.30% | Varies |
| **Gate.io** | Flash Swap | Unknown | 0% | "Slight price difference from spot" | Varies |

### Verdict: NOT Recommended for Bot

- The spread is unpredictable and not transparent.
- For major pairs (BTC/USDT, ETH/USDT), spread is ~0.05-0.10% — roughly equivalent to taker fees.
- For smaller-cap pairs, spread widens to 0.20-0.50% — MORE expensive than spot trading.
- Spot market orders are more predictable and auditable.

**Exception:** None significant. Gate.io's taker fee is 0.10% (not 0.20% as previously reported), making spot trading competitive with Convert on all exchanges.

---

## 4. Zero-Fee Trading Pairs

| Exchange | Zero-Fee Pairs | Type | Details |
|----------|---|:---:|---|
| **Binance** | BTC/FDUSD, ETH/FDUSD, BNB/FDUSD, SOL/FDUSD, XRP/FDUSD, DOGE/FDUSD, LINK/FDUSD | 0% maker only | Active as of Jan 29, 2026. Taker fee still applies. Requires holding FDUSD (different stablecoin from USDT). |
| **Bybit** | **ALL spot pairs** | 0% maker + taker | Limited-time promotion, still active Feb 2026. Could end at any time. |
| **MEXC** | **ALL spot pairs** | 0% maker | Permanent since Dec 2025. Taker is 0.05%. Occasionally 0% taker during events. |
| **Gate.io** | BTC/USDT (historically) | Promotional | Gate.io has run zero-fee promotions on select major pairs. Not permanent. |
| **OKX** | DAI-USDT, PYUSD-USDT, USDC-USDT, USDG-USDT | 0% maker + taker | Available to all users (VIP0+). USDT-USDS ended Dec 23, 2025. |
| **Bitget** | None at VIP0 | — | VIP7+ gets 0% maker |
| **KuCoin** | None at VIP0 | — | VIP5+ gets 0% maker |

### Binance FDUSD Detail

The zero maker fee on FDUSD pairs requires:
1. Holding FDUSD (not USDT) — you need to convert USDT → FDUSD first (costs a spread).
2. Using LIMIT orders (maker) — market orders still pay taker fee.
3. Only 7 pairs: BTC, ETH, BNB, SOL, XRP, DOGE, LINK.

Not practical for the arbitrage bot since it primarily uses USDT pairs and market orders.

---

## 5. Cross-Exchange Transfer via Crypto (Buy-Transfer-Sell)

Instead of sending USDT directly, the bot could:
1. Buy a cheap-to-transfer crypto on Exchange A
2. Send it to Exchange B (paying the crypto's withdrawal fee)
3. Sell it for USDT on Exchange B

### Crypto Withdrawal Fees Across Exchanges

| Crypto | Network | Speed | Binance | OKX | Bybit | Bitget | KuCoin | Gate.io |
|--------|---------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **XLM** | Stellar | 3-5s | $0.001 | $0.000008 | $0.004 | $0.004 | **$0.48** | $0.06 |
| **ALGO** | Algorand | 4s | $0.001 | $0.0004 | $0.001 | $0.001 | **$0.37** | $0.07 |
| **LTC** | Litecoin | 2.5min | $0.007 | $0.07 | $0.007 | $0.07 | **$0.43** | ~$0.07 |
| **POL** | Polygon | 2-5s | ~$0.02 | $0.01 | $0.02 | $0.02 | ~$0.50 | ~$0.05 |
| **NANO/XNO** | Nano | <1s | $0.03 | N/A | N/A | $0.007 | **$0.48** | N/A |
| **SOL** | Solana | 2.5s | $0.13 | $0.05 | **$1.07** | **$0.80** | **$1.07** | $0.08 |
| **XRP** | XRP Ledger | 3-5s | $0.40 | ~$0.15 | $0.40 | $0.40 | ~$0.40 | $0.07 |
| **TRX** | TRON | 3-5s | $0.47 | $0.37 | $0.31 | $0.34 | $0.31 | $0.47 |

N/A = Not confirmed available for withdrawal on that exchange.

**Best candidates:** XLM and ALGO have the cheapest withdrawal fees on most exchanges (sub-cent). But KuCoin charges ~$0.37-0.48 even for these.

### Total Round-Trip Cost Analysis ($500 Transfer)

The total cost of buy-transfer-sell includes: buy taker fee + withdrawal fee + sell taker fee + slippage + volatility risk.

#### XLM (Best Crypto Candidate): Binance → OKX

| Component | Cost |
|---|:---:|
| Buy XLM on Binance (0.075% taker) | $0.375 |
| Withdraw XLM from Binance | $0.001 |
| Sell XLM on OKX (0.10% taker) | $0.500 |
| Estimated slippage (2 × ~0.01%) | $0.100 |
| Volatility risk (5s transfer, ~0.005%) | $0.025 |
| **Total** | **$1.00** |

**vs. USDT direct from Binance: $0.01**

#### ALGO: Binance → OKX

| Component | Cost |
|---|:---:|
| Buy ALGO on Binance (0.075% taker) | $0.375 |
| Withdraw ALGO from Binance | $0.001 |
| Sell ALGO on OKX (0.10% taker) | $0.500 |
| Estimated slippage (2 × ~0.02%) | $0.200 |
| Volatility risk (4s transfer, ~0.005%) | $0.025 |
| **Total** | **$1.10** |

**vs. USDT direct from Binance: $0.01**

#### XLM: KuCoin → Binance (Most Favorable Scenario)

KuCoin has the most expensive USDT withdrawal ($0.80), so crypto transfer might help most here.

| Component | Cost |
|---|:---:|
| Sell USDT for XLM on KuCoin (0.096% taker w/ KCS) | $0.480 |
| Withdraw XLM from KuCoin | $0.480 |
| Buy USDT with XLM on Binance (0.075% taker) | $0.375 |
| Estimated slippage (2 × ~0.01%) | $0.100 |
| Volatility risk (5s transfer, ~0.005%) | $0.025 |
| **Total** | **$1.46** |

**vs. USDT direct from KuCoin: $0.80** — USDT is still cheaper.

### Verdict: USDT Direct Transfer Always Wins

The **trading fees on both ends** (buy + sell = 0.155-0.200% = $0.78-1.00 on $500) overwhelm any savings from cheaper crypto withdrawal fees. Even with the cheapest crypto (XLM at $0.001 withdrawal), the round trip costs ~$1.00 vs $0.01-0.80 for USDT.

**The only theoretical exception** would be if both exchanges have 0% trading fees (e.g., MEXC 0% maker on both sides + Bybit 0% promo). Even then, taker fees on at least one side make it uneconomical.

---

## 6. Cheapest Transfer Routes Between Exchanges

Sticking with USDT transfers (always cheaper than crypto transfers):

### Cheapest Outbound USDT Transfer Per Exchange

| From | Best Network | Fee | Speed | Notes |
|------|---|:---:|:---:|---|
| **Binance** | BEP20 | **$0.01** | ~3s | Cheapest outbound of all exchanges |
| **OKX** | Polygon/Solana (est.) | ~$0.10-0.30 | ~2-5s | Dynamic; verify on withdrawal page |
| **Bybit** | Aptos (promo) / BEP20 | $0.00 / ~$0.20 | ~1s / ~3s | Aptos promo may have ended |
| **MEXC** | Arbitrum | **$0.00** | ~0.3s | Free! But geo-blocked from Japan. |
| **Bitget** | Plasma / Aptos | **$0.001** / $0.03 | <1s / ~1s | Verified from Bitget API |
| **KuCoin** | Plasma / KCC | $0.40 / $0.50 | <1s / ~3s | Always expensive; BEP20 is $1.00 |
| **Gate.io** | TRC20 (>2020 USDT) / BEP20 | $0.00 / ~$0.50 | ~5s / ~3s | Free TRC20 requires min 2,020 USDT |

### Best Routes for Common Transfer Pairs

| Route | Network | Fee | Notes |
|-------|---|:---:|---|
| Binance → anywhere | BEP20 | $0.01 | Always cheapest |
| MEXC → anywhere | Arbitrum | $0.00 | Free (when available) |
| Gate.io → anywhere (large) | TRC20 | $0.00 | Only if >= 2,020 USDT |
| Bybit → anywhere | Aptos/BEP20 | $0.00-0.20 | Check Aptos promo status |
| Bitget → anywhere | Plasma / Aptos | $0.001 / $0.03 | Verified from API |
| OKX → anywhere | Polygon/Solana | ~$0.10-0.30 | Dynamic fees |
| KuCoin → anywhere | Plasma / KCC | $0.40 / $0.50 | Always expensive; BEP20 is $1.00 |

### Deposit Networks

All exchanges accept deposits on BEP20, TRC20, and most L2s. **All deposits are free** — the only cost is the withdrawal fee at the sending exchange. Ensure the receiving exchange supports the network you're sending on.

---

## 7. Fee Reduction Methods

### Trading Fee Discounts

| Method | Exchanges | Impact | Practical? |
|--------|-----------|--------|:---:|
| **Token discounts** | BNB (25%), BGB (20%), KCS (20%), GT (10%) | Reduces spot trading fees | Yes (already enabled for Binance, Bitget, KuCoin) |
| **Bybit zero-fee promo** | Bybit | 0% maker + taker on all spot | Yes — **verify if still active** |
| **MEXC 0% maker** | MEXC | 0% maker permanent, 0.05% taker | Yes (when geo-accessible) |
| **VIP tiers** | All exchanges | Lower fees at high 30-day volume. VIP1 usually $1M+ | No (impractical at current scale) |
| **Market maker programs** | Binance, OKX, Bybit | Negative maker fees (rebates) | No (requires massive volume) |
| **Referral discounts** | All (registration-time only) | 10-30% off trading fees | No (cannot apply retroactively) |

### Withdrawal Fee Discounts

| Method | Exchanges | Impact | Practical? |
|--------|-----------|--------|:---:|
| **VIP tiers** | None | No exchange reduces withdrawal fees for VIP | No |
| **Token holdings** | None | No exchange reduces withdrawal fees for holding tokens | No |
| **Zero-fee promos** | Bitget (SOL/BEP20), Bybit (Aptos), Gate.io (TRC20), KuCoin (BEP20 periodic) | Occasional free withdrawals | Monitor announcements |
| **Internal transfers** | All exchanges | Free transfers between users on same exchange | Not applicable (bot transfers between different exchanges) |

**Key insight:** There is NO way to reduce withdrawal fees through VIP tiers, token holdings, or any permanent mechanism. Withdrawal fees are fixed per network and same for all users. The only reductions come from temporary promotions.

---

## 8. Referral Programs

### Can Referral Codes Be Applied to Existing Accounts?

| Exchange | Retroactive? | Workaround | Referee Discount |
|----------|:---:|---|:---:|
| **Binance** | No | Create new account (new email, re-KYC) | 10-20% off trading fees |
| **OKX** | No | Close account, re-create | Up to 20% off |
| **Bybit** | No | Affiliate codes only within 14 days of registration | Up to 30% off |
| **Bitget** | No | Create new account | Up to 20% off |
| **KuCoin** | No | Create new account | Up to 10% off |
| **Gate.io** | No | Create new account | Up to 30% off + sign-up bonuses |

**Bottom line:** Since the bot operator already has accounts on all exchanges, referral discounts are not available. Creating entirely new accounts requires new email, re-KYC, and transferring all funds. Not worth the 10-30% trading fee discount for the current trading volume.

---

## 9. Plasma Network Status

Plasma (formerly Polygon Plasma) offers truly gasless USDT transfers — the protocol's paymaster subsidizes gas. Transfer speed is sub-second (PlasmaBFT consensus). No need to hold XPL tokens.

### Exchange Support

| Exchange | Plasma USDT Support | Withdrawal Fee | Status |
|----------|:---:|:---:|---|
| **Binance** | Yes | $0.012 | Confirmed. Listed as a withdrawal network for USDT. |
| **Bybit** | Likely | ~$0.00 | Deep partnership content with Plasma. Not explicitly confirmed. |
| **OKX** | Unconfirmed | Unknown | No explicit listing found in research. |
| **Bitget** | **Yes** | **$0.001** | Confirmed via Bitget API. Cheapest withdrawal on any exchange! |
| **KuCoin** | **Yes** | $0.40 | Confirmed via KuCoin API. KuCoin's cheapest option. |
| **Gate.io** | Unconfirmed | Unknown | No data found. |

**Verdict:** Plasma is now confirmed on **4 exchanges**: Binance ($0.012), Bitget ($0.001), KuCoin ($0.40), and likely Bybit (~$0.00). This makes Plasma a viable transfer network for Binance↔Bitget routes at $0.001-0.012. KuCoin's $0.40 Plasma fee is still expensive but cheaper than their BEP20 ($1.00).

**Key routes via Plasma:**
- Bitget → Binance: $0.001 (vs $0.15 BEP20) — **150x cheaper**
- Binance → Bitget: $0.012 (vs $0.01 BEP20) — slightly more expensive than BEP20
- KuCoin → anywhere: $0.40 (vs $1.00 BEP20) — 60% cheaper

---

## 10. Bot Config vs Research — Discrepancies

### USDT Withdrawal Fees (`config.py: USDT_WITHDRAWAL_FEES`)

| Exchange | Bot Config | Research Estimate | Discrepancy | Action Needed |
|----------|:---:|:---:|:---:|---|
| **Binance** | $0.01 | $0.01 | None | Correct |
| **OKX** | $0.01 | ~$0.20-0.50 | **$0.01 is too low** | Update to $0.30 |
| **Bybit** | $0.20 | ~$0.20-0.50 | Minor | Could increase to $0.30 |
| **Bitget** | $0.10 | $0.001 (Plasma) / $0.03 (Aptos) / $0.15 (BEP20/Arb) | **$0.10 is too high if using Plasma** | Update to $0.001 (Plasma) or $0.03 (Aptos) |
| **KuCoin** | $0.80 | $0.40 (Plasma) / $0.50 (KCC) / $1.00 (BEP20) | **$0.80 OK for Polygon, but Plasma is cheaper** | Could update to $0.40 (Plasma) |
| **Gate.io** | $0.05 | ~$0.50 (non-TRC20) or $0.00 (TRC20 >2020 USDT) | **$0.05 is too low** | Update to $0.50 |

### Trading Fees (`fee_manager.py / FeeManagement tab`)

| Exchange | Bot Config | Research Finds | Action Needed |
|----------|:---:|---|---|
| **Binance** | 0.075% | 0.075% (BNB 25% off) | Correct |
| **OKX** | 0.10% | 0.10% (0.08% maker) | Correct |
| **Bybit** | 0.10% | **0.00% (zero-fee promo!)** | **Verify and update if active** |
| **MEXC** | 0.05% | 0.05% taker / 0% maker | Correct |
| **Bitget** | 0.08% | 0.08% (BGB 20% off) | Correct |
| **KuCoin** | 0.08% | 0.08% (KCS 20% off), note: standard taker is 0.12% not 0.10% | Verify KCS discount |
| **Gate.io** | 0.10% | 0.10% base (0.09% with GT 10% off) | Correct — matches bot config |

---

## 11. Recommendations

### Immediate Actions

1. **Verify Bybit zero-fee promo** — Log into Bybit, check the fee schedule page or place a small test trade. If 0% is confirmed, update Bybit fee from 0.10% to 0.00% in the Fee Management tab. This would halve the minimum profitable spread for Bybit pairs (from 0.175% to 0.075%).

2. **Gate.io taker fee is correct** — Gate.io VIP0 is 0.10%/0.10% (confirmed). With GT discount (10% off) it's 0.09%/0.09%. The bot's 0.10% config is correct for the no-GT case.

3. **Update OKX withdrawal fee** — Change from $0.01 to $0.30 in `config.py`. The $0.01 assumption is clearly wrong.

4. **Update Gate.io withdrawal fee** — Change from $0.05 to $0.50 in `config.py` (unless you specifically use TRC20 with >= 2,020 USDT transfers, which is unlikely for rebalancing amounts).

### Medium-Term

5. **Add MEXC via VPS** — MEXC's 0% maker + 0.05% taker + $0.00 Arbitrum withdrawals make it the most cost-effective exchange by far. Deploy on a VPS in Thailand or Vietnam to bypass geo-restrictions.

6. **Bybit MNT/BIT discount does NOT work for API bots** — Bybit's MNT fee discount explicitly excludes API trading. If the zero-fee promo ends, Bybit reverts to 0.10%/0.10% with no discount available for the bot.

7. **Monitor Plasma adoption** — Once 3+ exchanges support Plasma USDT, it becomes the cheapest transfer method at ~$0.00 with sub-second speed.

### Not Recommended

- **Crypto buy-transfer-sell** — Always more expensive than direct USDT transfer due to double trading fees.
- **Convert/Swap features** — Hidden spread makes them unpredictable and generally not cheaper than spot taker.
- **Creating new accounts for referral codes** — Not worth the hassle for 10-30% trading fee discount at current volume.

---

## 12. Sources

### Official Exchange Fee Pages
- [Binance Crypto Withdrawal Fees](https://www.binance.com/en/fee/cryptoFee)
- [Binance Spot Fee Schedule](https://www.binance.com/en/fee/schedule)
- [OKX Withdrawal Fees](https://www.okx.com/en-us/fees/withdrawal-info)
- [OKX Fee Rules FAQ](https://www.okx.com/en-us/help/trading-fee-rules-faq)
- [Bybit Trading Fee Structure](https://www.bybit.com/en/help-center/article/Trading-Fee-Structure)
- [Bybit Fees Overview](https://www.bybit.com/en/help-center/article/Bybit-Fees-You-Need-to-Know)
- [Bitget Fee Page](https://www.bitget.com/fee)
- [Bitget Spot Trading Fees](https://www.bitget.com/support/articles/12560603820584)
- [MEXC Trading Fees](https://www.mexc.com/fee)
- [Gate.io Fees (TradersUnion)](https://tradersunion.com/brokers/crypto/view/gate.io/fees/)

### Fee Comparison & Aggregator Sites
- [WithdrawalFees.com — Binance](https://withdrawalfees.com/exchanges/binance)
- [WithdrawalFees.com — Bybit](https://withdrawalfees.com/exchanges/bybit)
- [WithdrawalFees.com — Stellar](https://withdrawalfees.com/coins/stellar)
- [WithdrawalFees.com — Algorand](https://withdrawalfees.com/coins/algorand)
- [WithdrawalFees.com — Litecoin](https://withdrawalfees.com/coins/litecoin)
- [WithdrawalFees.com — Solana](https://withdrawalfees.com/coins/solana)
- [WithdrawalFees.com — XRP](https://withdrawalfees.com/chains/xrp)
- [WithdrawalFees.com — TRON](https://withdrawalfees.com/coins/tron)
- [WithdrawalFees.com — Nano](https://withdrawalfees.com/coins/nano)
- [CoinMarketFees — Tether](https://coinmarketfees.com/tether)
- [CoinMarketFees — KuCoin](https://coinmarketfees.com/exchange/kucoin)
- [Gas Fees Now](https://gasfeesnow.com/)

### Exchange Announcements & Articles
- [Binance FDUSD Zero-Fee (Jan 2026)](https://www.binance.com/en/support/announcement/detail/4856a6d4e4014d4e8a5a29ec5fb44857)
- [Binance Convert Feature](https://www.cryptoninjas.net/exchange/binance-convert/)
- [Bybit Zero Fees on All Spot Pairs](https://www.bybit.com/en-us/promo/global/zero-fees-spot)
- [Bybit Aptos Zero-Fee Announcement](https://announcements.bybit.com/article/tether-usdt-on-the-aptos-blockchain-now-supported-on-bybit-enjoy-zero-fees-on-usdt-withdrawals-blt1d9500133f494e5c/)
- [Bybit Convert API Docs](https://bybit-exchange.github.io/docs/v5/asset/convert/guideline)
- [Bitget BEP20 Fee Adjustment](https://www.bitget.com/support/articles/12560603815826)
- [Bitget SOL Fee Adjustment](https://www.bitget.com/support/articles/12560603816279)
- [Bitget ERC20 Fee Reduction](https://www.bitget.com/support/articles/12560603814907)
- [Bitget Convert Upgrade (Mar 2025)](https://chainwire.org/2025/03/11/bitget-enhances-convert-feature-with-zero-fees-and-no-slippage/)
- [KuCoin Zero BEP20 Promo](https://www.kucoin.com/announcement/en-kucoin-introduces-zero-gas-fee-for-usdt-withdrawals-on-bnb-chain)
- [KuCoin KCS 20% Discount](https://www.kucoin.com/support/30380295503769)
- [Gate.io Free TRC20 USDT](https://www.gate.com/announcements/article/20731)
- [Gate.io Zero Fee BEP20 Promo](https://www.gate.com/announcements/article/42260)
- [Gate.io TRC20 Zero Fee (Medium)](https://gateio.medium.com/gate-io-supports-tron-usdt-zero-fee-withdrawal-3653268f4bae)
- [MEXC Zero-Fee Strategy 2025 Report](https://blog.mexc.fm/zero-fee-strategy-2025-report/)
- [MEXC 0-Fee All Pairs (Dec 2025)](https://invezz.com/news/2025/12/22/mexc-upgrades-0-fee-spot-trading-to-cover-all-pairs/)

### Analysis & Guides
- [OKX Withdrawal Fees Explained (Gate.io article)](https://www.gate.com/learn/articles/okx-withdrawal-fees-explained-what-youre-really-paying-for/10589)
- [OKX TRC20 Withdrawal — TradingFinder](https://tradingfinder.com/exchanges/okx/tether-trc20-withdrawal/)
- [Bybit TRC20 Withdrawal — TradingFinder](https://tradingfinder.com/exchanges/bybit/tether-trc20-withdrawal/)
- [KuCoin ERC20 Withdrawal — TradingFinder](https://tradingfinder.com/exchanges/kucoin/tether-erc20-withdrawal/)
- [KuCoin TRC20 Withdrawal — TradingFinder](https://tradingfinder.com/exchanges/kucoin/tether-trc20-withdrawal/)
- [Cheapest Crypto to Transfer (Exolix)](https://exolix.com/blog/top-10-cheapest-crypto-to-transfer-in-2025)
- [Cheapest Crypto to Transfer (CoinWire)](https://coinwire.com/cheapest-crypto-to-transfer/)
- [Lowest Fee Exchanges (WhalePortal)](https://whaleportal.com/blog/which-crypto-exchange-has-the-lowest-fees/)
- [VIP Programme Comparison (ForkLog)](https://forklog.com/en/how-to-save-up-to-3000-a-month-on-fees-comparing-the-vip-programmes-of-okx-bybit-bitget-htx-and-mexc/)
- [Plasma Network](https://www.plasma.to/)
- [Plasma + Binance USDT Yield](https://www.coindesk.com/markets/2025/08/20/plasma-s-usd250m-usdt-yield-program-on-binance-filled-in-less-than-an-hour/)
- [Binance Referral FAQ](https://support.binance.us/en/articles/9843323-binance-us-referral-program-frequently-asked-questions)
- [Hedera Fees](https://hedera.com/fees)

### Official Exchange APIs (Verified Feb 2026)
- [Bitget USDT Chain Info API](https://api.bitget.com/api/v2/spot/public/coins?coin=USDT)
- [KuCoin USDT Currency API](https://api.kucoin.com/api/v3/currencies/USDT)
- [Gate.io Fee Calculator (ExchangeFees.io)](https://www.exchangefees.io/fees-calculator/gateio)
- [OKX Zero-Fee Pairs Changes](https://www.okx.com/help/zero-fee-pairs-changes)
- [Bybit MNT Fee Discount FAQ](https://www.bybit.com/en/help-center/article/FAQ-Paying-Trading-Fees-with-MNT)
- [Bybit MNT Fee Discount Guide](https://learn.bybit.com/en/bybit-guide/mnt-fee-discount-bybit)
