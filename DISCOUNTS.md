# Exchange Fee Discounts — Complete Guide

> **Last updated:** 2026-02-26
> **Status:** Researched and fact-checked. Some items marked ambiguous where official sources are unclear (e.g., Bybit zero-fee promo, OKB post-restructuring).

---

## TL;DR — What You Actually Pay (Taker)

Your bot uses **market orders (taker)**. This is what matters:

| # | Exchange | You Pay | Action Needed | Cost |
|---|----------|---------|---------------|------|
| 1 | **MEXC** | **0.05%** (or 0.04% with MX) | Enable "MX Deduction" in settings | ~$5 MX |
| 2 | **Binance** | **0.075%** | Buy BNB + enable "Pay fees with BNB" | ~$10 BNB |
| 3 | **Bitget** | **0.08%** | Buy BGB + enable "BGB Fee Discount" | ~$10 BGB |
| 4 | **KuCoin** | **~0.08%** | Buy KCS + enable "Pay Fees with KCS" | ~$10 KCS |
| 5 | **Gate.io** | **0.09%** | Buy GT + enable GT fee payment | ~$10 GT |
| 6 | **OKX** | **0.10%** | No cheap discount (100 OKB = $5,000) | — |
| 7 | **Bybit** | **0.10%** | No discount for API bots | — |

**Total investment: ~$45** for all token discounts (excluding OKX/Bybit).

**Only zero-fee non-stablecoin USDT pair for the bot:** Gate.io BTC/USDT (0% maker + 0% taker). Stablecoin pairs (FDUSD/USDT, USDC/USDT on Binance; DAI/USDT, USDC/USDT on OKX) are also zero-fee but not relevant to the bot's arbitrage strategy.

### What Does NOT Work for Your Bot

| Exchange | Discount | Why Not |
|----------|----------|---------|
| Bybit | MNT 25% off | Explicitly excluded for API users |
| Bitget | Zero maker promo | Explicitly excluded for API users |
| MEXC | 500 MX = 50% off | Suspended since Feb 9, 2026 |
| KuCoin | BTC/ETH zero-fee | Expired (was 2022 promo) |

### Instant vs Rebate

| Type | Exchanges | How It Works |
|------|-----------|-------------|
| **Instant** | Binance, Bitget, Gate.io, MEXC | Fee charged in token at discounted rate. You pay less at trade time. |
| **Rebate** | KuCoin | Full fee charged first → refunded → KCS charged at 80%. Net ~20% savings. |
| **Holding tier** | OKX | Holding OKB changes your fee tier. No token spent per trade. |

---

## Quick Summary — Bot (API) Taker Fees (Detailed)

**IMPORTANT:** Some discounts explicitly exclude API users. The table below shows what YOUR BOT actually pays as a **taker**.

| Exchange | Base Taker | Best Achievable (Bot/API) | How | Investment | Config Now |
|----------|-----------|--------------------------|-----|------------|------------|
| **Binance** | 0.10% | **0.075%** | BNB 25% off (instant) | ~$10 BNB | 0.075% ✓ |
| **OKX** | 0.10% | **0.090%** | 100 OKB holding | ~$5,000 | 0.10% (update if buy OKB) |
| **Bybit** | 0.10% | **0.100%** | ~~MNT~~ NOT for API! | — | **0.10% ✓** |
| **MEXC** | 0.05% | **0.040%** | MX Deduction 20% off | Small MX balance | **0.05% ✓** (update if enable MX Deduction) |
| **Bitget** | 0.10% | **0.080%** | BGB 20% off (instant) | ~$10 BGB | 0.08% ✓ |
| **KuCoin** | 0.10% | **~0.080%** | KCS 20% rebate (not instant) | ~$10 KCS | 0.08% ✓ |
| **Gate.io** | 0.10% | **0.090%** | GT ~10% off (instant) | ~$10 GT | **fix→0.09%** |

### Zero-Fee Pairs (per-symbol overrides)

| Exchange | Pair | Maker | Taker | Status |
|----------|------|-------|-------|--------|
| **Gate.io** | BTC/USDT | 0% | 0% | Active ("until further notice") — confirmed |
| **Binance** | FDUSD pairs (7) | 0% | Standard | Maker only (changed Jan 29, 2026) |
| **Binance** | Stablecoin pairs | 0% | 0% | FDUSD/USDT, USDC/USDT, etc. |
| ~~KuCoin~~ | ~~BTC/USDT, ETH/USDT~~ | — | — | **EXPIRED** — was 2022 anniversary promo |

---

## Per-Exchange Details

---

### 1. Binance

#### Available NOW (cheap/free)

| Discount | Effect | Cost | API Compatible? |
|----------|--------|------|:---:|
| **BNB fee payment** | 25% off spot (0.10%→0.075%) | ~$10 in BNB | ✓ Yes |
| **FDUSD 0% maker** | 0% maker on BTC/ETH/BNB/SOL/XRP/DOGE/LINK FDUSD pairs | $0 | ✓ Yes |
| **Stablecoin 0%** | 0% maker+taker on FDUSD/USDT, USDC/USDT | $0 | ✓ Yes |
| **U pairs 0% maker** | 0% maker on U/USDT, ADA/U, DOGE/U, PEPE/U | $0 | ✓ Yes |
| **Fee rebate vouchers** | 100% fee rebate until voucher depleted | Free (from promos) | ✓ Yes |
| **Binance Points** | Redeem for fee rebate vouchers | Free (earned by activity) | ✓ Yes |

**How to claim BNB discount:**
1. Buy ~$10 BNB on Binance
2. **Profile → Settings → Trade → Fee Deduction** → toggle "Use BNB to pay fees"
3. Keep BNB topped up (each $100 trade costs ~$0.075 in BNB)

**Mechanism:** Instant deduction — fees are paid in BNB at the discounted rate at trade time. Not a cashback.

**FDUSD update (Jan 29, 2026):** Taker fee on FDUSD pairs is NO LONGER zero — only maker is 0%. Volume now counts toward VIP tier.

**United Stables (U) — new Jan 13, 2026:** New stablecoin with zero maker fees. ADA/U, DOGE/U, PEPE/U launched Feb 25, 2026.

#### Available FUTURE (expensive/volume-based)

| Discount | Effect | Cost | Notes |
|----------|--------|------|-------|
| **VIP 1** | Maker 0.09%, Taker 0.10% | $1M/mo volume + 25 BNB (~$15k) | FDUSD volume now counts |
| **VIP 3** | Maker 0.042%, Taker 0.054% | $20M/mo + 250 BNB (~$150k) | 40% off tier starts here |
| **VIP 9** | Maker 0.011%, Taker 0.023% | $4B/mo + 5,500 BNB (~$3.3M) | Absurd |
| **SLP (Market Maker)** | 0% to -0.008% maker (paid!) | VIP 3+ maker volume | Professional tier |
| **Altcoin LiquidityBoost** | -0.005% to -0.010% maker rebate | ≥0.5% of pair's maker volume | More accessible than SLP |
| **Referral 20% kickback** | Effective 0.060% (with BNB) | N/A — too late for your account | Cashback, not instant |

#### Ramadan 2026

- New user: up to $10 in token vouchers (5 tasks before March 18)
- Sharia Earn campaign: subscribe to share 15 BNB
- No direct fee reduction

---

### 2. Bybit

#### CRITICAL: MNT Discount Does NOT Work for API Users

From Bybit's official FAQ page ("FAQ — Paying Trading Fees with MNT"):

> "Trading via API is excluded from the MNT fee discount program."

Full exclusion list: **Market Makers, institutional users, Pro users, API users, Trading Bots, Copy Trading, RFQ, and liquidation orders.**

Since your bot trades via API, the MNT 25% discount **does not apply**. Your bot pays the full 0.10% taker fee.

#### Available NOW (for bot)

| Discount | Effect | Cost | API Compatible? |
|----------|--------|------|:---:|
| **MNT 25% off** | 0.10%→0.075% | ~$10 MNT | ❌ **NOT for API** |
| **Zero-fee spot promo** | 0% on all 280+ pairs | $0 | ❌ **Status ambiguous** — landing page live but 2026 reviews don't list Bybit as zero-fee. Verify with test trade. |
| **MNT Pass** | 1.5x VIP asset multiplier | Hold MNT+USDT | ✓ Helps VIP progression |
| **Rewards Hub vouchers** | Fee Savers (deducted from fees) | Free (from tasks) | ✓ Yes |

**Your bot's rate: 0.10% taker (no discount available for API at VIP 0).**

#### Available FUTURE

| Discount | Effect | Cost | Notes |
|----------|--------|------|-------|
| **Pro 1 tier** | Maker 0.04%, Taker 0.06% | **$10M 30-day volume** + API volume >20% | Both conditions required |
| **Pro 2 tier** | Maker 0.03%, Taker 0.05% | $25M 30-day volume | Higher volume |
| **Pro 3 tier** | Maker 0.02%, Taker 0.04% | $100M 30-day volume | Best realistic API rate |
| **Pro 6 tier** | Maker 0.005%, Taker 0.015% | $1B 30-day volume | Extreme |
| **VIP 1** | Maker 0.068%, Taker 0.08% | $100k assets OR $1M spot volume | Asset path more accessible |

**Key insight:** Bybit has a separate **Pro tier** track for API-heavy traders. When your API volume exceeds 20% of monthly activity AND you meet the volume threshold, you enter Pro tiers. Pro 1 requires $10M/month — achievable with sufficient capital. Your bot is 100% API so the 20% threshold is trivially satisfied.

#### Ramadan 2026

- P2P exclusive promotion (not spot fee related)

---

### 3. MEXC

#### Base Fees: 0% Maker / 0.05% Taker (for API/bot users)

MEXC has **0% maker** (permanent) but **0.05% taker** (base) for API users. MEXC also has a separate zero-fee program for eligible manual users, but API traders are excluded from that program.

#### CRITICAL: 500 MX = 50% Off Has Been SUSPENDED

Per official MEXC announcement ("Updates to the MX Fee Discount Structure"):

> Effective **February 9, 2026, at 8:00 UTC**, the MX Holder Discount (previously providing a 50% trading fee reduction for users holding 500 MX or more) will be **temporarily suspended**. The resumption date will be announced separately.

#### Available NOW

| Discount | Effect | Cost | API Compatible? |
|----------|--------|------|:---:|
| **Base rate** | 0% maker, 0.05% taker | $0 | ✓ Yes |
| **MX Deduction (20% off)** | 0.05%→**0.04% taker** | Small MX balance | ✓ Yes |
| ~~**500 MX holding (50% off)**~~ | ~~0.05%→0.025% taker~~ | ~~$1,500-2,000~~ | ❌ **SUSPENDED since Feb 9, 2026** |

**How MX Deduction works:**
1. Enable "MX Deduction" (aka "Use MX for Fees") in account settings
2. Fees are paid from your MX balance at 20% discount
3. If MX balance insufficient, reverts to standard rate (no discount)
4. API confirmed: `discountRatio: 0.8` in API responses

**Note:** 500 MX holding and MX Deduction did NOT stack (highest discount applied). Since 500 MX is suspended, MX Deduction 20% is the only option.

**Geo-blocked** from your location. Available on VPS.

#### Current Promotions (Feb-Mar 2026)

| Event | Details | Dates |
|-------|---------|-------|
| **Commodity Zero-Fee Gala** | 0% fees on XAUT, PAXG, SLVON, etc. + $1M rewards | Feb 5 - Mar 7 |
| **HYPE Fever** | $300,000 prize pool | Feb 10 - Mar 3 |
| **0-Fee Fest** | 0% on DUSK, SKR futures | Feb 14+ |

#### Available FUTURE

| Discount | Effect | Cost | Notes |
|----------|--------|------|-------|
| **500 MX holding (if resumed)** | 0.05%→0.025% taker | ~$1,500-2,000 | Currently suspended, watch for announcement |
| **VIP Experience Card** | 0.01% taker for 30 days | Proof of $10M/mo volume on any exchange | Email vip@mexc.com |
| **Super VIP** | 0.005% taker | $5B cumulative futures during card period | Extreme |
| **Kickstarter airdrops** | Free tokens (66.5% cumulative APY) | Hold 5+ MX, do 1 futures trade | Not fee-related but free money |

---

### 4. Bitget

#### Available NOW

| Discount | Effect | Cost | API Compatible? |
|----------|--------|------|:---:|
| **BGB 20% off** | 0.10%→0.08% maker+taker | ~$10 BGB | ✓ Yes (not for Market Maker accounts) |
| **Zero maker fee promo** | 0% maker on all spot | $0 | ❌ **NOT for API** (confirmed in promo terms) |
| **USDC/USDT 0% exception** | 0% maker+taker on USDC/USDT specifically | $0 | ✓ Yes (API included for this pair only) |
| **Points rewards** | Redeem for fee rebates | Free (daily tasks) | ✓ Yes |
| **Fee rebate vouchers** | 10-50% off (from promos) | Free | ✓ Yes |

**How to claim BGB discount:**
1. Buy ~$10 BGB on Bitget
2. **Profile → click VIP symbol → toggle "BGB Fee Discount"**
3. Wait ~5 minutes for activation

**Mechanism:** Instant deduction — fees are paid in BGB at the discounted rate at trade time. Applies to both maker and taker. Must have sufficient BGB in spot account; if insufficient, full fee charged in traded currency with no discount.

#### Current Promotions (Feb 2026)

| Event | Details |
|-------|---------|
| **Trading Club Championship Phase 32** | 63,000 BGB airdrop, up to 800 BGB/person |
| **Trade futures for gold** | Up to $2,000 XAUT |
| **Zero maker fees on stock/metal perps** | Feb 10 - Apr 30, 2026 |

#### Available FUTURE

| Discount | Effect | Cost | Notes |
|----------|--------|------|-------|
| **VIP 7** | Maker 0%, Taker 0.024% (with BGB) | Very high volume/assets | Top tier |
| **Market Maker** | Custom rates, maker rebates | Application + volume proof | Not compatible with BGB discount |

---

### 5. KuCoin

#### CORRECTION: BTC/USDT & ETH/USDT Zero-Fee Has EXPIRED

The zero-fee promotion was KuCoin's **5th anniversary** event (October 2022). It covered 9 pairs (BTC/USDT, ETH/USDT, etc.) with 0% maker+taker. The promo ended in late 2022 and has NOT been renewed. The landing page is still accessible but the promo is no longer active. 2026 reviews from Coin Bureau and LiquidityFinder confirm KuCoin does not offer zero-fee trading on these pairs.

**Current fee for BTC/USDT and ETH/USDT:** Standard 0.10% maker / 0.10% taker (or ~0.08% effective with KCS).

#### KCS Mechanism: REBATE, Not Instant Deduction

The KCS "20% discount" works via a **rebate mechanism**:
1. Full fee (e.g., 1.00 USDT) is charged from your trade
2. 0.80 USDT worth of KCS is deducted from your KCS balance
3. The original 1.00 USDT is refunded back to you

**Net effect:** ~20% savings, but with a 5% KCS price buffer built in, so effective discount is **slightly less than 20%**.

**Formula:** `KCS charged = (fee × 80%) / (KCS_price × 0.95)`

#### Available NOW

| Discount | Effect | Cost | API Compatible? |
|----------|--------|------|:---:|
| **KCS 20% rebate** | 0.10%→~0.08% effective | ~$10 KCS | ✓ Yes (for external API; NOT for KuCoin's built-in bots) |
| **KCS daily dividend** | 50% of exchange fee revenue shared | Hold 6+ KCS (~$50) | Passive income |
| **Spot fee coupons** | Various % off from Bonus Center | Free (promos/tasks) | ✓ Yes |

**How to claim KCS discount:**
1. Buy ~$10 KCS on KuCoin
2. **Avatar → User Profile** → enable "Pay Fees with KCS"
3. KCS must be in Funding, Trading, or staked account
4. No minimum holding required

**KCS daily dividend:** Hold 6+ KCS and receive a share of 50% of KuCoin's daily fee revenue. Estimated 3-30% annual yield depending on platform volume.

#### Ramadan 2026

- 100,000 USDT reward pool for new spot users (registered after Feb 20, 2025)

#### Available FUTURE

| Discount | Effect | Cost | Notes |
|----------|--------|------|-------|
| **VIP (1,000 KCS)** | Tiered fee reductions | ~$8,500 | Entry VIP tier |
| **Market Maker** | Maker rebates up to -0.012% | $30M+ volume on any exchange | Email institutional@kucoin.com |

---

### 6. OKX

#### Nov 2025 Fee Restructuring

OKX significantly restructured fees on **November 25, 2025**. The old OKB-based "Levels" (Lv1-Lv5) appear to have been merged into a unified VIP system based on assets/volume. OKB holding may still provide additional discounts on top, but the exact post-restructuring mechanism is unclear from public sources.

#### Post-Restructuring VIP Tiers (Nov 2025)

Pairs are now grouped (Group 1 = top 10 pairs, lower fees):

**Group 1 pairs (updated Feb 12, 2026):** ADA-USDT, BTC-USDT, DOGE-USDT, ETH-USDT, LTC-USDT, PEPE-USDT, PUMP-USDT, SOL-USDT, SUI-USDT, XRP-USDT

| Tier | Assets (USD) | 30d Volume | Gr.1 Maker | Gr.1 Taker | Gr.2 Maker | Gr.2 Taker |
|------|-------------|-----------|-----------|-----------|-----------|-----------|
| Regular | <$100k | <$1M | 0.080% | 0.100% | 0.080% | 0.100% |
| VIP 1 | ≥$100k | ≥$1M | 0.0675% | 0.080% | 0.0675% | 0.080% |
| VIP 2 | ≥$250k | ≥$5M | 0.060% | 0.070% | 0.060% | 0.070% |
| VIP 3 | ≥$500k | ≥$10M | 0.055% | 0.065% | 0.055% | 0.065% |
| VIP 4 | ≥$2M | ≥$20M | 0.030% | 0.045% | 0.030% | 0.050% |

**Zero-Fee Pairs on OKX:** DAI-USDT, PYUSD-USDT, USDC-USDT, USDG-USDT, USDT-USD (stablecoin conversions only)

#### OKB Holding Discounts (pre-restructuring reference)

These rates were documented before Nov 2025. They may still apply as an additional layer, but this is unverified post-restructuring:

| OKB Holding | Approx Taker | Cost (at ~$50/OKB) |
|-------------|-------------|---------------------|
| < 100 | 0.100% | $0 |
| **100+ OKB** | **~0.090%** | **~$5,000** |
| 500+ OKB | ~0.070% | ~$25,000 |
| 1,000+ OKB | ~0.060% | ~$50,000 |

**Note:** Post-Nov 2025, the official framework documentation does NOT mention OKB in tier qualification criteria. Multiple third-party sources still reference OKB discounts as active. Treat these rates as approximate until verified via API.

#### Available NOW

| Discount | Effect | Cost | API Compatible? |
|----------|--------|------|:---:|
| **OKB holding (if still active)** | ~10% off per tier | From ~$5,000 | ✓ Yes (account-level) |
| **VIP 1 (asset path)** | 0.080% taker | $100k assets | ✓ Yes |
| **Tradeback vouchers** | Fee rebate (from promos) | Free | ✓ Yes |
| **New user rebate cards** | Up to 2,000 USDT total rebate (20×$100) | Free | ✓ Yes (if new) |

#### Ramadan 2026

- **"Ramadan Weekly Hunt"** (Feb 17 - Mar 19): complete weekly tasks for 30+ rewards

#### Available FUTURE

| Discount | Effect | Cost | Notes |
|----------|--------|------|-------|
| **500 OKB** | ~0.070% taker | ~$25,000 | If OKB tiers still active |
| **VIP 4** | 0.045% taker (Gr.1) / 0.050% (Gr.2) | $2M assets or $20M volume | Major savings |
| **VIP 7+** | 0.025% taker + maker rebates | $500M+ volume | Institutional |

---

### 7. Gate.io

#### CORRECTION: GT Discount is ~10% Off (Not 25%)

Gate.io's marketing says "25% additional discount" but the **actual fee reduction** at VIP 0 is:
- Base: 0.10% → With GT: **0.09%** (a 10% reduction in the rate)

The "25%" in marketing refers to a different calculation method. What matters for your bot is the actual rate: **0.09% taker with GT enabled**.

**Mechanism:** Instant deduction — fees are paid in GT at the discounted rate. Not a cashback.

#### Available NOW

| Discount | Effect | Cost | API Compatible? |
|----------|--------|------|:---:|
| **GT fee payment** | 0.10%→**0.09%** taker | ~$10 GT | ✓ Yes (account-level) |
| **BTC/USDT zero-fee** | 0% maker+taker | $0 | ✓ Yes — confirmed active since Sep 2022 |
| **All /USD pairs zero-fee** | 0% maker+taker (50+ pairs) | $0 | ✓ Yes — but irrelevant (bot uses /USDT only) |
| **All /BTC pairs zero-fee** | 0% maker+taker | $0 | ✓ Yes — but irrelevant (bot uses /USDT only) |
| **All /ETH pairs zero-fee** | 0% maker+taker | $0 | ✓ Yes — but irrelevant (bot uses /USDT only) |
| **Point Card** | 1 Point = 1 USDT fee deduction | Buy or earn | ✓ Yes |

**How to claim GT discount:**
1. Buy ~$10 GT on Gate.io
2. Enable GT fee payment in settings
3. All spot trades now 0.09% instead of 0.10%

**BTC/USDT zero-fee** — Announced Sep 2022, confirmed still active in Dec 2022 update. No cancellation announcement found. BTC/USDT is Gate.io's highest-volume pair (~$837M daily).

**Note on /USD, /BTC, /ETH zero-fee:** These are real and still active, but your bot exclusively trades /USDT pairs, so only BTC/USDT benefits from the zero-fee policy on Gate.io.

#### Available FUTURE

| Discount | Effect | Cost | Notes |
|----------|--------|------|-------|
| **VIP 1** | 0.099% (0.089% with GT) | $1M volume or 1,000 GT (~$7k) | Marginal improvement |
| **VIP 10+** | 0% maker, low taker | $100M+ volume | Far future |
| **Market Maker** | Rebates up to -0.015% | $50M+ volume proof | Email mm@gate.io |

---

## Referral Codes

Referral gives 20-30% fee **cashback** (delayed, not instant). Stacks multiplicatively with token discounts.

### Your Situation

Accounts created 2026-02-25. Grace periods:

| Exchange | Window | Action | Potential Effective Rate |
|----------|--------|--------|------------------------|
| **Bybit** | 14 days | Add affiliate code via Help Center | Still 0.10% (MNT won't help API) |
| **Bitget** | 7 days | Contact Support → "Referral Code" | 0.064% effective (BGB + cashback) |
| **MEXC** | 72 hours | Contact support | 0.032% effective (MX deduction + cashback) |
| **KuCoin** | None | — | ~0.08% (KCS only) |
| **OKX** | None (30-day delete+recreate) | Low priority | 0.08% effective (ref cashback) |
| **Binance** | None | No path available | 0.075% (BNB only) |
| **Gate.io** | No account yet | Use referral at signup | 0.063% effective (ref 30% + GT ~10%) |

### Savings Analysis ($100/trade, across all exchanges)

| Daily Trades | Without Referral Fees/Day | With Referral Fees/Day | **Daily Savings** | **Yearly Savings** |
|-------------|--------------------------|----------------------|-------------------|-------------------|
| 100 | $9.15 | $7.42 | $1.73 | $632 |
| 500 | $45.75 | $37.10 | $8.65 | $3,157 |
| 1,000 | $91.50 | $74.20 | $17.30 | $6,315 |
| 5,000 | $457.50 | $371.00 | $86.50 | $31,573 |

### Referral Cashback Timing

Referral cashback is NOT instant — it's credited on a delay. This matters for accurate P&L tracking.

| Exchange | Settlement Speed | When Exactly | Paid In | Avg Delay for Sim |
|----------|-----------------|-------------|---------|:-----------------:|
| **Gate.io** | **Real-time** | As trades happen | Same asset as fee | ~0 min |
| **Binance** | **Hourly** | Rolling hourly batches | Same asset as fee (e.g., BNB if paying with BNB) | ~30 min |
| **OKX** | **1-2 hours** | Within 1-2h of trade | Same token as fee | ~90 min |
| **Bybit** | **Daily** | ~02:00-04:00 UTC | USDT | ~12 hours |
| **MEXC** | **Daily (T+1)** | Spot: ~00:00 UTC next day | Same as trade currency | ~12 hours |
| **Bitget** | **Daily (T+1)** | ~07:30 UTC next day | USDT | ~18 hours |
| **KuCoin** | **Daily (T+1)** | Next day (time unspecified) | Same currency as fee | ~18 hours |

**Key points:**
- No exchange has a lock period on referral trading commissions (immediately withdrawable once credited)
- Gate.io, Binance, and OKX are near-instant — cashback arrives within the same trading session
- Bybit, MEXC, Bitget, KuCoin are T+1 daily — cashback from today's trades arrives tomorrow
- OKX has a 14-day lock on one-time referral *bonuses* (separate from ongoing trade commissions)

---

## Zero-Fee Pairs — Full List

These override per-exchange taker fees for specific symbols. Configure as per-symbol overrides in the bot.

| Exchange | Pairs | Fee | Status |
|----------|-------|-----|--------|
| **Gate.io** | BTC/USDT | 0%/0% | Active since Sep 2022 ("until further notice") |
| **Gate.io** | All /USD, /BTC, /ETH pairs | 0%/0% | Active but irrelevant (bot uses /USDT only) |
| **Binance** | 7 FDUSD pairs | 0% maker only | Taker is standard (changed Jan 29, 2026) |
| **Binance** | FDUSD/USDT, USDC/USDT, USDP/USDT, TUSD/USDT | 0%/0% | Stablecoin pairs |
| **Binance** | U/USDT, U/USDC, ADA/U, DOGE/U, PEPE/U | 0% maker | New (Jan-Feb 2026) |
| **OKX** | DAI-USDT, PYUSD-USDT, USDC-USDT, USDG-USDT | 0%/0% | Stablecoin pairs only |
| ~~**KuCoin**~~ | ~~BTC/USDT, ETH/USDT~~ | — | **EXPIRED** — 2022 anniversary promo, ended Nov 2022 |
| ~~**Bybit**~~ | ~~All 280+ spot pairs~~ | — | **Ambiguous** — promo page live but may have ended. Verify. |

---

## Config Changes Needed

### Immediate fixes (based on verified research)

```python
EXCHANGE_TAKER_FEES = {
    "Binance": 0.00075,   # 0.075% (BNB 25% off)                ← correct
    "OKX":     0.001,     # 0.10% (no OKB)                       ← correct
    "Bybit":   0.001,     # 0.10% (MNT NOT for API!)             ← correct
    "MEXC":    0.0005,    # 0.05% (0% maker, 0.05% taker)        ← correct
    "Bitget":  0.0008,    # 0.08% (BGB 20% off, instant)         ← correct
    "KuCoin":  0.0008,    # ~0.08% (KCS 20% rebate, ~18-20%)     ← correct
    "Gate.io": 0.0009,    # 0.09% (GT ~10% off, instant)         ← CHANGE from 0.001
}
```

**Only Gate.io needs a config change** (0.001 → 0.0009 after buying GT).

### After buying tokens / enabling features

| When | Change |
|------|--------|
| Buy GT + enable on Gate.io | Gate.io → 0.0009 (0.09%) |
| Enable MX Deduction on MEXC | MEXC → 0.0004 (0.04%) |
| Buy 100 OKB | OKX → 0.0009 (0.090%) — verify post-Nov 2025 restructuring |
| Bot reaches Pro 1 on Bybit ($10M/mo) | Bybit → 0.0006 (0.060%) |

### Per-symbol zero-fee overrides (implement in bot)

```python
# Symbols with 0% fees on specific exchanges (override EXCHANGE_TAKER_FEES)
ZERO_FEE_PAIRS = {
    "Gate.io": ["BTCUSDT"],   # confirmed active since Sep 2022
}
# KuCoin BTC/USDT & ETH/USDT zero-fee EXPIRED (was 2022 promo)
```

---

## Shopping List

### Immediate (~$30-40, do today)

| Exchange | Token | Amount | Cost | Effect |
|----------|-------|--------|------|--------|
| Binance | BNB | ~0.02 | ~$10 | 0.10%→0.075% (instant) |
| Bitget | BGB | ~4 | ~$10 | 0.10%→0.08% (instant) |
| KuCoin | KCS | ~1.2 | ~$10 | 0.10%→~0.08% (rebate) |
| Gate.io | GT | ~1.5 | ~$10 | 0.10%→0.09% (instant) |
| **Total** | | | **~$40** | |

Also: Enable **MX Deduction** on MEXC (requires small MX balance) → 0.05%→0.04%

**Do NOT buy:**
- MNT on Bybit — won't help your bot (API excluded)
- 500 MX on MEXC — discount is suspended since Feb 9, 2026

### Future (when scaling up)

| Exchange | Token | Amount | Cost | Effect | Notes |
|----------|-------|--------|------|--------|-------|
| OKX | OKB | 100 | ~$5,000 | 0.10%→~0.09% | Verify post-Nov 2025 |
| OKX | OKB | 500 | ~$25,000 | 0.10%→~0.07% | Significant |
| MEXC | MX | 500 | ~$1,500-2,000 | 0.05%→0.025% | Only when/if suspension lifted |

### Absurd (aspirational)

| Exchange | What | Cost | Effect |
|----------|------|------|--------|
| OKX | 1,000 OKB | ~$50,000 | ~0.06% taker |
| Binance | VIP 3 | $20M/mo volume + 250 BNB | 0.054% taker |
| Bybit | Pro 1 | $10M/mo volume (all API) | 0.06% taker |
| Gate.io | Market Maker | $50M+ volume | Maker rebates (get paid!) |

---

## VIP Tier Reference

### Binance
| VIP | 30d Volume | BNB | Maker | Taker | +BNB 25% |
|-----|-----------|-----|-------|-------|----------|
| 0 | < $1M | — | 0.100% | 0.100% | 0.075% / 0.075% |
| 1 | ≥ $1M | 25 | 0.090% | 0.100% | 0.068% / 0.075% |
| 2 | ≥ $5M | 100 | 0.080% | 0.100% | 0.060% / 0.075% |
| 3 | ≥ $20M | 250 | 0.070% | 0.080% | 0.053% / 0.060% |

### OKX (Post-Nov 2025 Restructuring)

**Group 1** (ADA, BTC, DOGE, ETH, LTC, PEPE, PUMP, SOL, SUI, XRP):

| Tier | Assets | Volume | Maker | Taker |
|------|--------|--------|-------|-------|
| Regular | <$100k | <$1M | 0.080% | 0.100% |
| VIP 1 | ≥$100k | ≥$1M | 0.0675% | 0.080% |
| VIP 2 | ≥$250k | ≥$5M | 0.060% | 0.070% |
| VIP 3 | ≥$500k | ≥$10M | 0.055% | 0.065% |
| VIP 4 | ≥$2M | ≥$20M | 0.030% | 0.045% |

OKB holding may provide additional discounts on top (unverified post-restructuring).

### Bybit (Pro tiers — relevant for API bots)
| Tier | 30d Volume | Maker | Taker |
|------|-----------|-------|-------|
| VIP 0 | — | 0.100% | 0.100% |
| Pro 1 | $10M | 0.040% | 0.060% |
| Pro 2 | $25M | 0.030% | 0.050% |
| Pro 3 | $100M | 0.020% | 0.040% |
| Pro 4 | $200M | 0.015% | 0.030% |
| Pro 5 | $500M | 0.010% | 0.020% |
| Pro 6 | $1B | 0.005% | 0.015% |

All Pro tiers require API volume >20% of monthly (trivial for bots).

### MEXC
| Tier | Maker | Taker | Notes |
|------|-------|-------|-------|
| Regular | 0.00% | 0.05% | Base (permanent) |
| + MX Deduction | 0.00% | 0.04% | 20% off taker (active) |
| ~~+ 500 MX held~~ | ~~0.00%~~ | ~~0.025%~~ | ~~50% off~~ **SUSPENDED Feb 9, 2026** |
| VIP Experience Card | 0.00% | 0.01% | $10M/mo proof from any exchange |

### KuCoin
| Tier | Maker | Taker | +KCS ~20% rebate |
|------|-------|-------|----------|
| Lv0 | 0.100% | 0.100% | ~0.080% / ~0.080% |
| Lv1 (1,000 KCS) | Lower | Lower | +~20% rebate |

No zero-fee pairs available (2022 promo expired).

### Gate.io
| Tier | Maker | Taker | +GT ~10% |
|------|-------|-------|---------|
| VIP 0 | 0.100% | 0.100% | 0.090% / 0.090% |
| VIP 1 ($1M vol) | 0.099% | 0.099% | 0.089% / 0.089% |
| Zero-fee | 0% | 0% | BTC/USDT only (for /USDT pairs) |

### Bitget
| Tier | Maker | Taker | +BGB 20% |
|------|-------|-------|----------|
| VIP 0 | 0.100% | 0.100% | 0.080% / 0.080% |
| VIP 7 | 0.000% | 0.030% | 0.000% / 0.024% |

---

## Token Discount Mechanisms

Understanding how each discount works is important for accurate fee modeling:

| Exchange | Token | Mechanism | Delay |
|----------|-------|-----------|-------|
| **Binance** | BNB | **Instant deduction** — fee paid in BNB at discounted rate | None |
| **Bitget** | BGB | **Instant deduction** — fee paid in BGB at discounted rate | None |
| **Gate.io** | GT | **Instant deduction** — fee paid in GT at discounted rate | None |
| **KuCoin** | KCS | **Rebate** — full fee charged, then refunded, KCS charged at 80% | Immediate but 3-step process |
| **MEXC** | MX | **Instant deduction** — fee paid in MX at discounted rate | None |
| **OKX** | OKB | **Account-level tier** — holding OKB changes your fee tier | None |
| **Bybit** | MNT | **NOT for API** — excluded from bot trading entirely | N/A |

---

## Active Promotions & Ramadan 2026

### Ramadan Events (Feb 17 — Mar 19, 2026)

| Exchange | Event | What |
|----------|-------|------|
| **MEXC** | Commodity Zero-Fee Gala | 0% on gold/silver tokens + $1M rewards (through Mar 7) |
| **OKX** | Ramadan Weekly Hunt | 30+ rewards from weekly tasks |
| **KuCoin** | Spot Ramadan | 100,000 USDT pool for new spot users |
| **Bybit** | P2P Ramadan | Trade more, unlock rewards (P2P only) |
| **Binance** | Sharia Earn + Ramadan | Token vouchers, 15 BNB pool |
| **Bitget** | None found yet | May announce closer to Ramadan |
| **Gate.io** | None found | — |

### Other Active Promotions

| Exchange | Event | Dates |
|----------|-------|-------|
| **Binance** | Trading Upgrade Challenge | Jan 28 - Feb 26 |
| **Binance** | ADA/U, DOGE/U, PEPE/U zero maker | Feb 25+ |
| **MEXC** | HYPE Fever $300k | Feb 10 - Mar 3 |
| **Bitget** | Trading Club Championship | Feb 2026 (63,000 BGB) |
| **Bitget** | Zero maker fees on stock/metal perps | Feb 10 - Apr 30 |
| **KuCoin** | Trade the Volatility | Up to 100% fee deduction |
| **Bybit** | Boost Battle Championship | Through Mar 15 ($1M USDT) |

