# Alternative Exchange Screening (Fees, Transfers, Trust)

**Last updated:** 2026-02-26  
**Scope:** Exchanges shown in `screenshots/2.png` and `screenshots/3.png` (`Pionex`, `Deepcoin`, `WhiteBIT`, `WEEX`, `Phemex`, `Toobit`, `BingX`, `CoinEx`, `XT.com`, `AscendEX`, `LBank`, `DigiFinex`, `ProBit`, `BitMart`, `BTSE`, `BloFin`, `HTX`)

## Goal

Screen non-core exchanges for possible CoirnaBot integration using:

- Spot taker fees (bot uses taker orders)
- Fee discounts (token deduction / VIP / referral)
- USDT transfer costs and supported cheap networks (especially `Plasma`)
- Reliability and liquidity (public trust/volume proxies)

## Methodology and Caveats

- Prioritized official exchange sources (fee pages, support pages, public APIs).
- Used CoinGecko exchange API as a public proxy for trust/liquidity (`trust_score`, `trust_rank`, 24h BTC volume).
- Withdrawal fees are dynamic on some exchanges and often only visible in the withdrawal UI or authenticated API.
- "Plasma support" means evidence that the exchange supports USDT deposits/withdrawals on the Plasma network. If only an Academy/education page exists, that is marked as weaker evidence.
- This is not a solvency audit. Even exchanges with strong volume/trust scores should be treated as counterparty risk.

## Decision Rules Used

- `Eliminate (too expensive)`:
  - Base taker fee is `0.20%` and no clearly verifiable path reduces it to `<= 0.10%` without heavy volume/subscription requirements.
- `Eliminate (no clear edge)`:
  - Base taker is `0.10%`, but there is no clear advantage vs your current stack (`0.075%` to `0.10%`), and transfer-fee transparency / trust / liquidity does not provide a compelling reason to integrate.
- `Keep / Shortlist`:
  - Has a real fee edge, or
  - Has strong transfer-cost advantage, or
  - Has meaningful liquidity/trust with acceptable fees.

## Executive Summary

### Best practical additions to evaluate first

1. **BingX** - Can reach about `0.075%` taker with BINGX token deduction (same level as Binance/Bybit discounted fees), strong CoinGecko trust/rank. Exact withdrawal fee matrix is not publicly transparent.
2. **BitMart** - Standard `0.10%` taker, but public API shows many `USDT` low-cost routes (`0.1 USDT`) and good public liquidity/trust proxy.
3. **Pionex** - `0.05%` spot fee and official referral fee discount for invitees, but likely liquidity overlap with Binance and weak public withdrawal-fee transparency.
4. **WhiteBIT** - Standard `0.10%`, decent trust/liquidity proxy, and many cheap USDT networks supported (no public exact fee matrix found).

### Test-only / caution candidates

- **Deepcoin** - Official page currently shows `0%` spot fees, but liquidity/trust proxy is much weaker and withdrawal-fee transparency is poor.
- **Toobit**, **Phemex**, **WEEX** - Reasonable trust/liquidity proxies and standard `0.10%` fees, but no clear fee edge over your current exchanges and incomplete public withdrawal-fee transparency (except WEEX, which is transparent and mostly `1 USDT` on cheap networks).

### Eliminate (too expensive at base)

`CoinEx`, `XT.com`, `DigiFinex`, `ProBit`, `BTSE`, `HTX`

## Full Screening Table

Legend:

- `Plasma`: `Yes`, `No`, `Likely` (weaker evidence), `Unknown`
- `WD`: USDT withdrawal (transfer out)
- `CG`: CoinGecko

| Exchange | Base Spot Taker | Discount(s) (publicly verified) | Referee Fee Discount via Referral | Plasma Support (USDT) | Cheapest Verified/Public Cheap Alternative | Reliability / Liquidity Proxy (CG) | Decision |
|---|---:|---|---|---|---|---|---|
| **Pionex** | `0.05%` | VIP tiers (no simple fee-token deduction verified) | **Yes** - `10%` trading fee discount for invitee for 1 year (official referral page) | **Unknown** (no public network fee matrix found) | Exact USDT WD fees not publicly verifiable; official blog says network-dependent and changeable | Score `7`, Rank `51`, ~`69,801` BTC/24h | **Keep (special case)** |
| **Deepcoin** | `0.00%` (official current fee announcement) | N/A while zero-fee spot remains active | No fixed referee fee discount verified | **Unknown** | Exact USDT WD fee/network matrix not publicly verifiable | Score `6`, Rank `99`, ~`4,854` BTC/24h | **Test-only (high risk)** |
| **WhiteBIT** | `0.10%` | VIP tiers / market maker programs | No fixed referee fee discount verified | **No** (not in public USDT network list from API) | Supports many cheap USDT networks (`ARB`, `APT`, `BASE`, `MATIC`, `OP`, `SOL`, `TON`, `TRX` etc.); exact fees not public in accessible API | Score `8`, Rank `31`, ~`23,164` BTC/24h | **Keep (watchlist)** |
| **WEEX** | `0.10%` | VIP tiers (no simple token deduction verified) | No fixed referee fee discount verified (inviter commission program exists) | **No** (not listed in official WEEX USDT WD fee article) | Official article lists `1 USDT` on `BSC`, `TRC20`, `Polygon`, `Arbitrum`, `Optimism`, `TON`, `Aptos` | Score `8`, Rank `27`, ~`29,966` BTC/24h | **Watchlist (no fee edge)** |
| **Phemex** | `0.10%` | VIP / Premium / volume-based programs | No fixed referee fee discount verified | **Unknown** (Academy content exists about Plasma, but no verified network support page found) | Exact USDT WD fees not publicly verifiable from reviewed sources | Score `8`, Rank `33`, ~`10,299` BTC/24h | **Watchlist** |
| **Toobit** | `0.10%` | VIP tiers | Public pages reviewed mention referral/kickback, but no clearly documented fixed referee trading-fee discount | **Unknown** | Exact USDT WD fees not publicly verifiable from reviewed sources | Score `8`, Rank `26`, ~`29,834` BTC/24h | **Watchlist** |
| **BingX** | `0.10%` | **BINGX token deduction `25%` off** (effective about `0.075%`) | No fixed referee fee discount verified (inviter rebates/rewards) | **Likely** (official BingX Academy article says USDT can be deposited/withdrawn on Plasma on BingX; verify in UI) | Exact USDT WD fee matrix not public (UI / authenticated API path) | Score `9`, Rank `12`, ~`20,872` BTC/24h | **Shortlist** |
| **AscendEX** | `0.10%` (cash account) | VIP tiers | No fixed referee fee discount verified | **Unknown** | Official support says WD fees are dynamic / shown at confirmation | Score `7`, Rank `59`, ~`19,975` BTC/24h (`bitmax`) | **Eliminate (no clear edge)** |
| **LBank** | `0.10%` | VIP tiers | No fixed referee fee discount verified | **Unknown** | Public fee page says WD fees vary by token/network; no public USDT matrix found | Score `8`, Rank `22`, ~`52,805` BTC/24h | **Eliminate (no clear edge)** |
| **DigiFinex** | `0.20%` | DFT holder pricing can reduce spot taker to `0.10%` | No fixed referee fee discount verified | **Unknown** | USDT WD fee matrix not publicly verified in reviewed sources | Score `8`, Rank `29`, ~`29,060` BTC/24h | **Eliminate (too expensive at base)** |
| **BitMart** | `0.10%` | VIP tiers (BMX-related benefits exist, but no simple public pay-fee token deduction verified) | No fixed referee fee discount verified | **No** (not in public API USDT networks list) | Public API shows multiple `0.1 USDT` routes (`ARB`, `APT`, `BASE`, `BSC`, `MATIC`, `OP`, `SOL`, `TON`) | Score `8`, Rank `23`, ~`52,378` BTC/24h | **Shortlist** |
| **CoinEx** | `0.20%` | **CET deduction `20%` off** (effective about `0.16%`) | No fixed referee fee discount verified | **No** (not in public asset page list reviewed) | Public page shows `USDT(TON) 0.5`, `USDT(BSC) 0.6`, `USDT(TRON) 1`, `USDT(ERC20) 3.6` | Score `8`, Rank `36`, ~`2,280` BTC/24h | **Eliminate (too expensive)** |
| **XT.com** | `0.20%` | VIP tiers | No fixed referee fee discount verified | **Unknown** | No public exact USDT WD matrix verified from reviewed pages | Score `7`, Rank `53`, ~`40,697` BTC/24h | **Eliminate (too expensive)** |
| **ProBit** | `0.20%` | VIP memberships / volume discounts | No fixed referee fee discount verified | **No** (public page only `ERC20` and `BEP20` listed for USDT) | Public page shows `USDT(BEP20) 0.8`, `USDT(ERC20) 4.6` | Score `7`, Rank `58`, ~`684` BTC/24h | **Eliminate (too expensive + low liquidity)** |
| **BTSE** | `0.20%` | VIP / market maker pricing | No fixed referee fee discount verified (inviter rebate program exists) | **No** (not found in official transfer-fee article reviewed) | Official article lists `USDT Aptos 0.2`, `ARB 0.3`, `Polygon 0.3`, `BSC 0.4`, `TRON 0.4` | Score `7`, Rank `66`, ~`4,999` BTC/24h | **Eliminate (too expensive)** |
| **BloFin** | `0.10%` | VIP tiers | No fixed referee fee discount verified (inviter commission program exists) | **No** (not found in official support article reviewed) | Official article lists `USDT BSC 0.3`, many L2s/TRON/TON at `1`, `ERC20 3` | CG spot profile not available (CoinGecko shows `BloFin (Futures)` only, trust score `4`) | **Eliminate (trust/transparency caution, no fee edge)** |
| **HTX** | `0.20%` | **HT deduction `12%` off** spot (effective about `0.176%`) | No fixed referee fee discount verified (inviter commission program exists) | **Yes**, but public API response can show `PLASMA` status as `prohibited` | Public API shows cheap allowed alternatives (examples seen: `Arbitrum 0.001`, `BSC 0.05`), but statuses vary | Score `9`, Rank `13`, ~`19,516` BTC/24h | **Eliminate (too expensive despite network options)** |

## Exchanges Eliminated as Too Expensive

These are the clearest eliminations if your goal is to beat or match your current effective taker costs (`0.075%` to `0.10%`):

| Exchange | Base Taker | Best Publicly Verified Non-VIP Discount Path | Why Eliminated |
|---|---:|---:|---|
| CoinEx | `0.20%` | about `0.16%` with CET deduction | Still materially worse than current discounted stack |
| XT.com | `0.20%` | No simple public discount path verified | No fee edge |
| DigiFinex | `0.20%` | about `0.10%` for DFT holders | Only matches standard `0.10%`, no clear net advantage |
| ProBit | `0.20%` | VIP membership required for better pricing | Too expensive at base and weak public spot volume proxy |
| BTSE | `0.20%` | VIP/MM programs | No fee edge despite cheap transfer routes |
| HTX | `0.20%` | about `0.176%` with HT deduction | Still too expensive for bot taker strategy |

## Shortlist and Watchlist (Detailed Notes)

### 1. BingX (Shortlist)

**Why it makes the shortlist**

- Official spot taker is `0.10%`.
- Official `BINGX` token deduction offers `25%` fee reduction, giving an effective taker around `0.075%`.
- CoinGecko trust/liquidity proxy is strong (`trust_score 9`, `rank 12`).

**Transfers**

- I did not find a publicly exposed official USDT per-network withdrawal fee matrix.
- BingX has an official Academy article describing `USDT` deposits and withdrawals on the `Plasma` network on BingX. This is useful signal, but you should still verify in the withdrawal UI before integrating.

**Referral**

- Official referral pages emphasize inviter rebates/rewards.
- I did not verify a fixed invitee/referee trading-fee discount.

**Trust / reliability take**

- Stronger than most alternatives in this list by public trust/rank metrics.
- Still an offshore CEX risk. Test withdrawals and API stability first.

### 2. BitMart (Shortlist)

**Why it makes the shortlist**

- Standard spot taker `0.10%`.
- Good public liquidity/trust proxy (`trust_score 8`, `rank 23`, high 24h BTC volume).
- Public API provides exact per-network `USDT` withdrawal fees (strong transparency).

**Transfers (verified via public API)**

- `Plasma`: not present in the public `USDT` network list reviewed.
- Very cheap verified alternatives exist:
  - `Arbitrum` `0.1 USDT`
  - `Aptos` `0.1 USDT`
  - `Base` `0.1 USDT`
  - `BSC` `0.1 USDT`
  - `Polygon` `0.1 USDT`
  - `Optimism` `0.1 USDT`
  - `Solana` `0.1 USDT`
  - `TON` `0.1 USDT`

**Referral**

- Referral program exists.
- I did not verify a fixed invitee/referee trading-fee discount.

**Trust / reliability take**

- Reasonable candidate if you want transparent transfer fee data and many cheap L2 routes.
- No fee edge on taker vs your existing discounted exchanges, so the case for integration is mostly symbol coverage / transfer flexibility.

### 3. Pionex (Keep, but special-case)

**Why it is still interesting**

- Officially documented spot fee is `0.05%`, which is very competitive.
- Official referral page states invitees can get a `10%` trading fee discount for 1 year (potentially `0.045%` if applicable).

**Main caveat**

- Pionex liquidity is heavily aggregated and often overlaps with Binance liquidity.
- If your current stack already includes Binance and other majors, incremental arbitrage opportunity can be limited.

**Transfers**

- I did not find a public official USDT per-network fee table from sources accessible in this pass.
- Pionex official withdrawal fee guide confirms fees vary by network and can change.
- `Plasma` support was not publicly verified.

**Trust / reliability take**

- Mid-tier trust proxy by CoinGecko (`score 7`, `rank 51`) but good reported volume.
- Worth testing with small size if you want to validate whether Pionex adds unique fills beyond Binance overlap.

### 4. WhiteBIT (Keep / watchlist)

**Why it is interesting**

- Standard spot taker `0.10%`.
- Good public trust/liquidity proxy (`score 8`, `rank 31`).
- Public API exposes supported networks and confirms many cheap USDT routes are available.

**Transfers (public API network support verified)**

- `Plasma`: not present in public `USDT` network list.
- Supported cheap alternatives include multiple low-cost networks:
  - `Arbitrum`
  - `Aptos`
  - `Base`
  - `Polygon`
  - `Optimism`
  - `Solana`
  - `TON`
  - `TRON`
- Exact USDT withdrawal fees were not publicly visible in the accessible API response I used.

**Referral**

- Invite/referral page exists.
- I did not verify a fixed invitee/referee trading-fee discount.

**Trust / reliability take**

- Reasonable watchlist candidate.
- Before integration, confirm actual withdrawal fees in UI and API rate limits/stability.

### 5. WEEX (Watchlist, no fee edge)

**Why it is not eliminated outright**

- Standard `0.10%` spot taker and decent public trust/liquidity proxy (`score 8`, `rank 27`).
- Official support article publishes a transparent USDT withdrawal-fee table.

**Transfers (official support article)**

- `Plasma`: not listed in the reviewed USDT fee article.
- Cheap alternatives are clearly published:
  - `BSC` `1 USDT`
  - `TRC20` `1 USDT`
  - `Polygon` `1 USDT`
  - `Arbitrum` `1 USDT`
  - `Optimism` `1 USDT`
  - `TON` `1 USDT`
  - `Aptos` `1 USDT`
  - `Solana` `2 USDT`
  - `ERC20` `15 USDT`

**Referral**

- Referral program pages emphasize inviter commission (up to high percentages).
- No fixed invitee/referee trading-fee discount verified.

**Trust / reliability take**

- Viable only if you need symbols/liquidity not available on your current exchanges.
- No taker-fee advantage over current discounted venues.

### 6. Toobit (Watchlist)

**Why it remains a watchlist candidate**

- Official fee policy page shows `0.10%` spot maker/taker at base level.
- CoinGecko public trust/liquidity proxy is relatively strong (`score 8`, `rank 26`).

**Transfers**

- I could not verify a public official USDT per-network withdrawal fee matrix in this pass.
- `Plasma` support could not be verified from reviewed official pages.

**Referral**

- Public pages reviewed reference referral/kickback.
- I did not verify a clearly documented fixed invitee/referee trading-fee discount.

**Trust / reliability take**

- Potentially usable, but transparency on transfer fees/networks is a gap.
- Requires manual UI verification before serious consideration.

### 7. Phemex (Watchlist)

**Why it remains a watchlist candidate**

- Official support page shows standard spot maker/taker `0.10%`.
- Good public trust/liquidity proxy (`score 8`, `rank 33`).

**Transfers**

- I could not verify a public official USDT per-network withdrawal fee matrix in this pass.
- Phemex has educational content about `Plasma`, but I did not verify a support/fee page proving active USDT-Plasma withdrawal support.

**Referral**

- Referral program exists.
- I did not verify a fixed invitee/referee trading-fee discount.

**Trust / reliability take**

- Reasonable mid-tier candidate, but transfer-fee transparency is weaker than BitMart / WEEX / HTX.

### 8. Deepcoin (Test-only, high caution)

**Why it is interesting**

- Official fee announcement page currently shows `0%` spot trading fees.

**Why it is high risk**

- Lowest trust/liquidity proxy among the potentially interesting low-fee names here (`CG score 6`, `rank 99`, much lower volume than other candidates).
- I could not verify a public USDT per-network withdrawal-fee matrix.
- `Plasma` support not verified.

**Recommendation**

- If you test it, treat it as a small-size experiment only and validate actual fill quality and withdrawal reliability first.

## Reliability and "Can I Trust These Exchanges?"

Short answer: **some are usable for bot trading, but none should be treated like a bank account**.

### Better public trust/liquidity proxies in this list

- `BingX` (`CG score 9`, rank 12)
- `BitMart` (`CG score 8`, rank 23)
- `LBank` (`CG score 8`, rank 22) - but no fee edge and weaker public transfer transparency for your use case
- `WhiteBIT` (`CG score 8`, rank 31)
- `WEEX` (`CG score 8`, rank 27)
- `Toobit` (`CG score 8`, rank 26)
- `Phemex` (`CG score 8`, rank 33)
- `HTX` (`CG score 9`, rank 13) - but fee is too high for your strategy

### Weaker / higher caution names for your use case

- `Deepcoin` (`CG score 6`, rank 99) - low volume and trust proxy
- `ProBit` (`CG score 7`, rank 58, low public spot volume proxy)
- `BTSE` (`CG score 7`, rank 66, modest volume proxy)
- `BloFin` - CoinGecko spot profile not available in the data used here (only a futures profile appeared, with low score), plus no fee edge

### Practical trust policy (recommended)

- Keep only working balances on these exchanges.
- Do a real withdrawal test before integration (small `USDT` on your intended network).
- Monitor deposit/withdraw disable events and chain maintenance announcements.
- Track API stability (HTTP errors, websocket disconnects, stale order books).
- Prefer exchanges with public fee transparency or public APIs for network fees.

## Plasma Support Summary (What I Found)

| Exchange | Plasma Status | Confidence | Notes |
|---|---|---|---|
| BingX | **Likely supported** | Medium | Official BingX Academy article describes USDT deposit/withdraw on Plasma via BingX; verify in UI before relying on it |
| HTX | **Supported in API, but can be unavailable** | High | HTX public API includes a `PLASMA` chain entry for USDT (`xrc20usdt`), but the sampled response showed `withdrawStatus=prohibited` |
| BitMart | **No** (not in public USDT network list) | High | Verified via BitMart public currencies API |
| WhiteBIT | **No** (not in public USDT network list) | High | Verified via WhiteBIT public assets API |
| WEEX | **Not listed** in official USDT fee article | Medium | Could change; re-check if WEEX adds it |
| CoinEx | **Not found** in public asset fee page reviewed | Medium | Public page lists many USDT chains, no Plasma seen |
| ProBit | **No** (USDT only ERC20/BEP20 shown on public page) | High | Verified on public deposit/withdraw fee page |
| BTSE | **Not found** in official transfer fee article reviewed | Medium | Official article lists multiple cheap chains, no Plasma seen |
| BloFin | **Not found** in official support article reviewed | Medium | Official article lists multiple cheap chains, no Plasma seen |
| Pionex / Deepcoin / Phemex / Toobit / AscendEX / LBank / XT / DigiFinex | **Unknown** | Low | I did not find a verifiable public network fee table/support page proving current USDT-Plasma support |

## Suggested Integration Priority (if you want to add new exchanges)

This is based on taker-fee competitiveness + transfer practicality + trust proxy:

1. **BingX** - Best fee upside (`~0.075%` with token) among alternatives, strong trust/liquidity proxy.
2. **BitMart** - Excellent USDT transfer fee transparency and many cheap routes (`0.1 USDT`), decent trust/liquidity proxy.
3. **Pionex** - Very low fees, but test whether it adds real arbitrage edge beyond Binance-overlap liquidity.
4. **WhiteBIT** - Many cheap network options and decent trust/liquidity proxy, but confirm exact withdrawal fees.
5. **WEEX** - Transparent transfer fees, but no taker-fee edge.
6. **Toobit** / **Phemex** - Acceptable watchlist names, but transfer-fee transparency gaps.
7. **Deepcoin** - Test-only due low trust/liquidity proxy despite `0%` spot fee.

## Data Gaps / Manual Verification Still Needed Before Production

These items were not publicly verifiable from the reviewed sources and should be checked manually in each exchange withdrawal UI (or authenticated API):

- Exact current `USDT` per-network withdrawal fees for: `Pionex`, `Deepcoin`, `Phemex`, `Toobit`, `BingX`, `WhiteBIT`, `AscendEX`, `LBank`, `XT.com`, `DigiFinex`
- Whether `Plasma` is currently enabled for those same exchanges (except where noted as verified)
- Any region-specific restrictions affecting your account (KYC country / IP / VPS region)

## Sources (Official and Primary)

### Fee and referral sources

- Pionex fees (official blog): `https://www.pionex.com/blog/what-is-fee-and-how-its-calculated/`
- Pionex referral (official blog): `https://www.pionex.com/blog/referral-program/`
- Pionex withdrawal fee guide (official blog): `https://www.pionex.com/blog/pionex-withdrawal-fee-guide/`

- WEEX fee rate page: `https://www.weex.com/fee-rate`
- WEEX USDT withdrawal fee article: `https://www.weex.com/help-center/articles/18690508074265`
- WEEX referral page: `https://www.weex.com/campaign/referral_program`

- BingX costs page: `https://bingx.com/en/support/costs/`
- BingX referral invitee benefits: `https://bingx.com/en/referral/inviteeBenefits`
- BingX referral program page: `https://bingx.com/en/referral-program/`
- BingX Academy Plasma article (support signal only, verify in UI): `https://bingx.com/en/learn/article/how-to-transfer-usdt-on-plasma-network`

- WhiteBIT trading fees article: `https://help.whitebit.com/en/articles/114970-how-are-trading-fees-calculated`
- WhiteBIT public assets API (network support inspection): `https://whitebit.com/api/v4/public/assets`
- WhiteBIT invite page: `https://whitebit.com/invite`

- Phemex spot fee page (support): `https://phemex.com/help-center/how-are-trading-fees-calculated`
- Phemex referral page: `https://phemex.com/referral-program`
- Phemex Academy Plasma article (not proof of support): `https://phemex.com/academy/what-is-plasma-network`

- Toobit fee policy page: `https://www.toobit.com/en-US/support/fee-rate-policy`
- Toobit support center home (referral/kickback mention): `https://support.toobit.com/en-US/support/home`

- Deepcoin spot fee announcement: `https://www.deepcoin.com/en/Annoucement/article/43409307709517`

- AscendEX transaction fees: `https://ascendex.com/en/transactionfee`
- AscendEX withdrawal fee policy note (dynamic): `https://answers.ascendex.com/en/articles/3636024-how-much-are-the-deposit-and-withdrawal-fees`
- AscendEX referrals: `https://ascendex.com/en/rewards-hub/referrals`

- LBank rate info: `https://www.lbank.com/vi-VN/rateInfo`
- LBank referral rules: `https://www.lbank.com/hc/en-gb/articles/40672376417433-LBank-Bonus-Referral-Rules`

- DigiFinex spot trading FAQ (base fee and DFT tier notes): `https://support.digifinex.com/hc/en-us/articles/900000455166-Spot-trading-FAQ`

- BitMart spot trading fee article: `https://support.bitmart.com/hc/en-us/articles/115006268648-Spot-Trading-Fee`
- BitMart referral page: `https://www.bitmart.com/referral/en`
- BitMart public currencies API (USDT network fees): `https://api-cloud.bitmart.com/spot/v1/currencies`

- CoinEx fees: `https://www.coinex.com/fees`
- CoinEx asset info page (USDT network fees): `https://www.coinex.com/asset/info?type=deposit`
- CoinEx referral article: `https://www.coinex.com/en/blog/6394-a-users-guide-to-coinex-referral-program-and-how-to-claim-rewards`

- XT.com rates: `https://www.xt.com/en/rate`

- ProBit fee info: `https://www.probit.com/en-us/fee-info`
- ProBit deposit/withdraw fee page: `https://www.probit.com/en-us/deposit-withdrawal-fee`
- ProBit referral page: `https://www.probit.com/en-us/referral`

- BTSE fee article: `https://support.btse.com/en/support/solutions/articles/43000505307-what-fees-are-charged-by-btse-`
- BTSE transfer fee article: `https://support.btse.com/en/support/solutions/articles/43000505324-what-are-the-fees-for-crypto-transfers-`
- BTSE referral page: `https://www.btse.com/en/referral`

- BloFin fee schedule: `https://blofin.com/fee_schedule`
- BloFin withdrawal/deposit fees article: `https://support.blofin.com/hc/en-us/articles/9529711626511-Withdrawals-Deposit-Fees-and-Minimums`
- BloFin referral page: `https://blofin.com/referral`

- HTX spot fee announcement / structure support page: `https://www.htx.com/support/90426919230116`
- HTX referral rules/support page: `https://www.htx.com/support/66867477782139`
- HTX public currencies API (USDT networks and fees): `https://api.htx.com/v2/reference/currencies?currency=usdt`

## Corrections

*Final revision 2026-02-27 - re-verified against official sources, public APIs, and local code. Time-sensitive numbers are marked as snapshots.*

### 1. Deepcoin: 0% fee was a past promo, current base is 0.10%/0.10%

The main table line using `0.00%` as current is outdated.

- Deepcoin had an older `0%` spot-fee promo announcement.
- Deepcoin later announced spot fees returned to `0.10% maker / 0.10% taker`.
- Correction for the main table: base spot taker should be `0.10%` with a note that `0%` was historical/promo.

### 2. Deepcoin: high-risk reputation signals, but avoid over-precise permanent score claims

- ScamAdviser displays a trust score of **0 out of 100** for deepcoin.com, with the label `Caution Recommended` and a Gridinsoft "possibly harmful" warning (snapshot Feb 2026; score is prominently displayed as a number on the page).
- Trustpilot snapshot (2026-02-27): `3.2/5` from `14` reviews with `64%` 1-star (low sample size, time-sensitive).
- Deepcoin has an official phishing advisory about clone/impersonation sites.
- This supports a high-risk label for operational policy, but does not by itself prove a legal scam determination.

### 3. WEEX: major risk signals are verified, inference is separated

**a) Public review profile is weak (snapshot Feb 2026)**
- Trustpilot: **2.3–2.4/5**, labeled `Poor`. Reviews document account freezing after profitable trades, unauthorized balance transfers, and demands for "anti money laundering" payments.
- Reviews.io: **2.1/5** from 288 reviews, only 23% recommend.

**b) Regulatory action is verified**
- Georgia Department of Banking and Finance issued a cease-and-desist against WEEX International Exchange LTD d/b/a WEEX; final order date is 2025-03-27.

**c) Account-freeze complaints are documented**
- Multiple user reviews report freezes/withdrawal friction.
- WEEX has an official help page for frozen/locked accounts.
- On March 5, 2025, WEEX experienced an ETH/USDT trading anomaly and paid **$6.12M (6,123,393 USDT)** to compensate **5,022 affected users**. This is from WEEX's own support page, not a third-party claim. [Source: weexsupport.zendesk.com/hc/en-us/articles/44145612187673]

**d) WEEX API is Bitget V1-compatible (not "Bitget-like" — identical)**
- WEEX uses the `_SPBL` symbol suffix — Bitget's internal V1 naming convention. No other exchange uses this.
- Endpoint paths are **character-for-character identical** between WEEX and Bitget V1 (e.g., `GET /api/spot/v1/public/products`, `POST /api/spot/v1/trade/orders` — 17+ endpoints match exactly).
- Authentication uses the same four headers (`ACCESS-KEY`, `ACCESS-SIGN`, `ACCESS-TIMESTAMP`, `ACCESS-PASSPHRASE`) with the same HMAC-SHA256 signature scheme — not an industry standard format.
- WEEX's V2 migration tracks Bitget's V2 structure (`/v2/ws/public`, `/v2/ws/private`).
- The `force` parameter (values: `normal`, `postOnly`, `fok`, `ioc`) is a distinctive Bitget convention — most exchanges call this `timeInForce`.
- Neither company has publicly confirmed a white-label or licensing arrangement, but the degree of compatibility (identical paths, auth, parameter names, response codes) goes far beyond coincidence. "Bitget V1-compatible" is the most precise verifiable term.

**e) Withdrawal-fee visibility is semi-opaque**
- WEEX says users pay network withdrawal fees.
- WEEX `support/rate` withdrawal tab does not provide a stable static fee table in page HTML.
- Exact per-network USDT withdrawal fees are not reliably exposed as a stable public table for automation.

**Corrected decision:** `DO NOT USE` - no taker-fee edge (`0.10%`) plus regulatory/reputation/transparency concerns.

### 4. Pionex VIP tiers exist, but do not reduce spot taker fees

- Pionex has VIP levels and market-maker programs.
- Official Pionex fee materials show spot taker remains `0.05%` across VIP levels.
- Since CoirnaBot uses taker orders, VIP progression does not lower taker fee for this strategy.

### 5. Pionex transfer fees are partially confirmed and partially estimated

`config.py` still marks part of Pionex transfer config as estimated:

- `Arbitrum` (`config.py:436`) - estimated
- `Optimism` (`config.py:437`) - estimated
- `Solana` (`config.py:440`) - estimated

BEP20/TRC20/ERC20 are treated as confirmed in local config notes; UI verification is still recommended before production assumptions.

### 6. Pionex geo restrictions: two different restriction lists exist

Pionex has **two separate restriction articles** that should not be conflated:

**General restricted countries** (full platform access blocked): US, Singapore, China, Canada, UK, Netherlands, Spain, Cuba, Iran, North Korea, Afghanistan, and others. Japan is **NOT on this list**. [Source: cryptowinrate.com/pionex-restricted-and-supported-countries-2026/]

**KYC/phone verification unsupported** (article #5929910517273): Includes additional jurisdictions such as Japan. Users in these countries cannot complete KYC verification but may not be fully IP-blocked.

**Key implications:**
- "Accessible in most of Europe" is wrong — UK, Netherlands, Spain are fully restricted.
- Japan's status is **uncertain** — not on the general restricted list, but KYC-restricted. A Tokyo VPS might access the public WebSocket feed but KYC for trading would be blocked.
- Turkey and Thailand are not on either list, so likely accessible (but absence from a list is not a guarantee).

### 7. Pionex CoinGecko trust-score snapshot

- CoinGecko API currently returns `trust_score = 7` and `trust_score_rank = 52` for Pionex.
- Treat these as snapshots, not permanent values.

### 8. Pionex implementation in this repo is confirmed (core runtime)

Verified in local codebase:
- `fetchers/pionex.py` exists.
- `run.py` imports and starts `PionexFetcher`.
- `config.py` includes Pionex in fee/transfer/default exchange config.
- Dashboard exchange-order arrays include `Pionex` in fee/transfer tabs.

Caveat:
- Pionex's CTO has stated they aggregate **50–60% of orders from Binance and Huobi** (source: Coinmonks/Medium Pionex Review). This means Pionex↔Binance arbitrage will be near-zero. Value is in Pionex vs OKX/KuCoin/Gate.io/Bybit/Bitget pairs.

### Updated decisions summary

| Exchange | Original Decision | Corrected Decision | Basis |
|----------|------------------|--------------------|-------|
| Deepcoin | Test-only (high risk) | **DO NOT USE (high-risk, no fee advantage)** | Current fee is `0.10%` (no advantage), ScamAdviser 0/100, Trustpilot 3.2/5 (64% 1-star), clone-site phishing risk |
| WEEX | Watchlist (no fee edge) | **DO NOT USE** | `0.10%` taker (no advantage), GA DBF cease-and-desist (2025-03-27), Trustpilot 2.3/5 ("Poor"), $6.12M trading anomaly compensation, account-freeze pattern, Bitget V1-compatible API, semi-opaque withdrawal fees |
| Pionex | Keep (special case) | **Implemented** | `0.05%` flat taker, confirmed in current runtime/config |

### Sources

- Deepcoin 0-fee spot announcement (older): `https://support.deepcoin.online/hc/en-us/articles/12517056046235`
- Deepcoin spot fee adjustment (0.10%): `https://support.deepcoin.online/hc/en-001/articles/52713927580057-Notice-on-Deepcoin-Spot-Trading-Fee-Adjustment`
- Deepcoin phishing advisory: `https://support.deepcoin.online/hc/en-001/articles/41252511670937`
- ScamAdviser deepcoin.com: `https://www.scamadviser.com/check-website/deepcoin.com`
- Trustpilot deepcoin.com: `https://www.trustpilot.com/review/www.deepcoin.com`
- Trustpilot WEEX: `https://www.trustpilot.com/review/www.weex.com`
- Reviews.io WEEX: `https://www.reviews.io/company-reviews/store/weex-com`
- Georgia DBF cease-and-desist (WEEX): `https://dbf.georgia.gov/press-releases/2025-03-27/order-cease-and-desist-issued-weex-international-exchange-ltd-dba-weex`
- WEEX account frozen help page: `https://www.weex.com/wiki/article/what-should-i-do-if-my-weex-account-is-frozen-or-locked-2653`
- WEEX withdrawal fee page: `https://www.weex.com/wiki/article/what-are-the-withdrawal-fees-on-weex-2664`
- WEEX rate page: `https://www.weex.com/support/rate`
- WEEX API intro: `https://blog.weex.com/interviews/api-introduction`
- WEEX API signature docs: `https://www.weex.com/api-doc/spot/QuickStart/Signature`
- Bitget V1 spot API docs: `https://bitgetlimited.github.io/apidoc/en/spot/`
- Bitget V1 API deprecation notice: `https://www.bitget.com/support/articles/12560603838361`
- Pionex VIP fee update page: `https://support.pionex.com/hc/en-us/articles/24972845418649`
- Pionex VIP tier system update: `https://support.pionex.com/hc/en-us/articles/51746121935641`
- Pionex unsupported countries/regions (KYC): `https://support.pionex.com/hc/en-us/articles/5929910517273-Unsupported-Countries-and-Regions-for-KYC-Verified-Users`
- Pionex restricted countries 2026 (general access compilation): `https://www.cryptowinrate.com/pionex-restricted-and-supported-countries-2026/`
- Pionex Binance/Huobi aggregation (CTO statement): `https://medium.com/coinmonks/pionex-review-exchange-with-crypto-trading-bot-1e459d0191ea`
- WEEX ETH/USDT compensation announcement (primary source): `https://weexsupport.zendesk.com/hc/en-us/articles/44145612187673`
- U.Today WEEX $6M compensation: `https://u.today/weex-crypto-exchange-mitigates-tech-issues-in-minutes-pays-out-6-million-to-users`
- CoinGecko Pionex API: `https://api.coingecko.com/api/v3/exchanges/pionex`

## Expand options

*Snapshot date: 2026-02-27*

| Exchange | Spot taker fee (base) | Trust/liquidity snapshot | Verdict |
|----------|------------------------|--------------------------|---------|
| Bitfinex | `0.00%` (since 2025-12-17) | CoinGecko trust score `9/10` | **Best expansion candidate** (if jurisdiction allows) |
| WhiteBIT | `0.10%` | CoinGecko trust score `8/10` | **Good add** (second tier) |
| BingX | `0.10%` | CoinGecko trust score `9/10`; weak Trustpilot profile | **Add with caution** |
| Phemex | `0.10%` | CoinGecko trust score `9/10`; mixed user-reputation signal | **Test-only add** |
| Toobit | `0.10%` taker (`0.075%` maker) | CoinGecko trust score `8/10`; newer venue | **Test-only add** |
| CoinEx | `0.20%` (`0.16%` with CET) | CoinGecko trust score `8/10` | **Skip (too expensive)** |
| HTX | `0.20%` at Prime0 | CoinGecko trust score `9/10` | **Skip unless deep fee tier** |
| Kraken | up to `0.40%` taker (tiered) | High trust, but expensive for taker arb | **Skip for profitability** |
