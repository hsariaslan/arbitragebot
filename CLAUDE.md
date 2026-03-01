# CoirnaBot - Cross-Exchange Crypto Arbitrage Bot

## Project Start Date
2026-02-22

## Instructions
- Never run `git checkout` or `git commit` commands without my confirmation.
- Always use `read_xlsx.py` when reading a xlsx output file.
- Check the latest log file under `logs` folder.

## Project Goal

Build an AI-powered cross-exchange crypto arbitrage bot that monitors real-time prices of selected symbols across multiple crypto exchanges, identifies price discrepancies, and executes simultaneous buy/sell orders to profit from the spread.

## Core Strategy

**Cross-exchange spatial arbitrage with pre-funded parallel execution:**

1. Keep capital pre-deposited on all supported exchanges simultaneously.
2. Monitor real-time prices of all configured symbols across all exchanges via WebSocket feeds.
3. When a price gap is detected that exceeds total fees + minimum profit threshold:
   - Simultaneously BUY on the cheapest exchange and SELL on the most expensive exchange.
   - No crypto transfer needed for the trade itself.
4. Periodically rebalance funds across exchanges (not time-critical) using cheap networks (BEP20, Plasma, or Arbitrum).

**Why NOT "buy-transfer-sell":** Transferring crypto between exchanges takes minutes to hours. By the time funds arrive, the price gap has closed. Pre-funded parallel execution eliminates this problem entirely.

## Supported Exchanges (9 Active)

All 9 exchanges have working WebSocket fetchers implemented.

| Rank | Exchange | Taker Fee (w/ Discount) | Discount Token | WebSocket | Symbols |
|------|----------|------------------------|----------------|-----------|---------|
| 1 | **Bitfinex** | 0.00% | None needed (permanent 0%) | Post-connect JSON (arrays) | ~40-50/60 |
| 2 | **Binance** | 0.075% | BNB (25% off) | URL-param streams | 58/60 (no HYPEUSDT) |
| 3 | **OKX** | 0.10% | OKB (requires 500 OKB ~$25k) | Post-connect JSON | 60/60 |
| 4 | **Bybit** | 0.075% | MNT/BIT (25% off) | Post-connect JSON | 58/60 (no ZECUSDT) |
| 5 | **MEXC** | 0.05% | None needed (already lowest) | Post-connect JSON | 60/60 |
| 6 | **Bitget** | 0.08% | BGB (20% off) | Post-connect JSON | 60/60 |
| 7 | **KuCoin** | 0.08% | KCS (20% off) | REST token + WS | 60/60 |
| 8 | **Gate.io** | 0.09% | GT (10% off, enabled) | Post-connect JSON | 60/60 |
| 9 | **Pionex** | 0.05% | None (VIP tiers only, volume-gated) | Post-connect JSON | 60/60 |

**MEXC note:** Accessible from Bangkok VPS. 0.05% taker fee (lowest after Bitfinex), no discount token needed. Uses protobuf binary WS messages. 30 sub limit per connection — uses 2 connections for 60 symbols.
**Pionex note:** Aggregates ~50-60% of order book from Binance (per CTO statement) — Pionex↔Binance arbitrage will be near-zero. Value is in Pionex vs OKX/KuCoin/Gate.io/Bybit/Bitget pairs.
**Bitfinex note:** 0% taker/maker fees permanent since Dec 17, 2025. Free USDT withdrawals on 14 networks. Uses `tBTCUST` symbol format (UST not USDT). 30 sub limit per WS connection — uses 2 connections for 60 symbols. No BEP20 support. ~40-50 of 60 symbols available as UST pairs.

### Dropped Exchanges

| Exchange | Reason |
|----------|--------|
| **HTX (Huobi)** | 0.20%/0.20% base fees — too expensive for arbitrage. 25% HT discount still yields 0.15%. Also uses gzip-compressed binary WS messages. |
| **Kraken** | 0.25%/0.40% base fees — way too expensive. Only ~11/20 original USDT pairs available. |
| **Crypto.com** | No Plasma support, missing symbols, poor fit for strategy. |
| **Deepcoin** | Scam/near-scam. ScamAdviser 0/10, claimed 0% fees are actually 0.10%/0.10%, advance-fee withdrawal scam patterns. |
| **WEEX** | 0.10%/0.10% spot fees (no advantage), Trustpilot 2.4/5, Georgia cease-and-desist order, account freezing complaints, opaque withdrawal fees. |

## Fee Considerations

For arbitrage, fees are critical. A typical opportunity is 0.1-0.3%. Fee math:
- Buy fee + Sell fee = total cost
- If total cost >= price gap, no profit
- **MEXC/Pionex (0.05% taker)** and **Binance/Bybit (0.075% with token discount)** are the most cost-effective pairs

### How to Claim Fee Discounts

| Exchange | What to Do | Discount |
|----------|-----------|----------|
| **Binance** | Buy BNB, enable "Pay fees with BNB" in Settings > Fee | 25% off (0.10% → 0.075%) |
| **Bybit** | Hold MNT or BIT tokens on Bybit | 25% off (0.10% → 0.075%) |
| **Bitget** | Buy BGB, enable "Pay fees with BGB" | 20% off (0.10% → 0.08%) |
| **KuCoin** | Buy KCS, enable "Pay fees with KCS" | 20% off (0.10% → 0.08%) |
| **OKX** | Hold 500+ OKB (~$25k investment) | Tiered discount (not practical at start) |
| **Gate.io** | Buy GT, enable "Pay fees with GT" | 10% off at VIP 0 (0.10% → 0.09%) |

### Binance FDUSD 0% Maker Fees

BUSD was discontinued in December 2023. Its replacement is **FDUSD**, which offers **0% maker fees** on these 7 pairs:
- BTC/FDUSD, ETH/FDUSD, BNB/FDUSD, SOL/FDUSD, XRP/FDUSD, DOGE/FDUSD, LINK/FDUSD

This is a significant advantage for limit orders on high-volume majors. Consider using FDUSD pairs on Binance alongside USDT pairs for reduced costs.

## Trading Symbols (60 Symbols in 4 Tiers)

All symbols use **/USDT** quote currency exclusively for simplicity and cheap rebalancing.

### Tier 1 - High Liquidity Majors (7 symbols)

Tightest spreads (0.01-0.05%), highest execution reliability. Small profits, high frequency.

BTC, ETH, SOL, XRP, BNB, DOGE, ADA

### Tier 2 - Strong Alts (8 symbols)

Moderate spreads (0.05-0.2%), reasonable volume. Main profit source.

AVAX, LINK, POL, DOT, NEAR, SUI, APT, TRX

### Tier 3 - Volatile Alts (5 symbols)

Wider spreads (0.1-0.5%+), lower volume, higher slippage risk. Opportunistic.

ARB, OP, FIL, ATOM, INJ

### Tier 4 - High Volume Additions (40 symbols)

Sorted by ~24h volume. 38/40 available on all 9 exchanges.

AAVE, BCH, PEPE, ZEC (6/7, not Bybit), LTC, HYPE (6/7, not Binance), XLM, UNI, ENA, SNX, TON, SHIB, ICP, ETC, TRUMP, HBAR, CHZ, AXS, PENGU, WLD, WIF, RENDER, ONDO, STRK, CRV, AR, FET, LDO, ALGO, EIGEN, PENDLE, APE, TIA, FLOKI, W, GRT, ORDI, JUP, COMP, DYDX

## Rebalancing Strategy

### Transfer Fee Structure

**All exchange withdrawal fees are STATIC (fixed USDT amounts), NOT percentage-based.** The fee is the same whether you withdraw $10 or $10,000 worth of USDT.

### Best Networks for USDT Rebalancing (Ranked)

| Rank | Network | On-Chain Fee | Speed | Best For |
|------|---------|-------------|-------|----------|
| 1 | **BEP20 (BSC)** | ~$0.02 | ~3s | Universal support, cheapest on Binance ($0.01) |
| 2 | **Plasma** | $0.00 (gasless) | Sub-second | Cheapest possible, but limited exchange support |
| 3 | **Arbitrum One** | ~$0.01-0.10 | ~0.3s L2 | Free on MEXC, $0.10 on Binance |
| 4 | **Optimism** | ~$0.01-0.05 | ~2s L2 | $0.04 on Binance |
| 5 | **Polygon PoS** | ~$0.0007 | ~2-5s | $0.07 on Binance |
| 6 | **Solana (SPL)** | <$0.01 | ~0.4s | Occasional network outages |
| 7 | **TRC20 (TRON)** | ~$1.85-3.87 | ~3-5s | **Surprisingly expensive!** $1.00 on Binance, free on Gate.io only |
| 8 | **Ethereum (ERC20)** | $0.50-$30+ | ~12s | Avoid — always expensive |

**Key insight:** TRC20 (TRON) is NOT cheap. Its reputation is outdated. BEP20, Arbitrum, and Optimism are all significantly cheaper.

### USDT Withdrawal Fees Per Exchange

| Network | Binance | OKX | Bybit | MEXC | Bitget | KuCoin | Gate.io | Pionex | Bitfinex |
|---------|---------|-----|-------|------|--------|--------|---------|--------|----------|
| **BEP20** | $0.01 | <$0.50 | ~$0.20 | $0 (promo) | ~$0.30-0.50 | ~$0.50-1.00 | $0 (promo) | $0.80 | — |
| **Plasma** | $0.01 | Likely yes | ~$0 | Unconfirmed | Partial | Unconfirmed | Unconfirmed | — | — |
| **Arbitrum** | $0.10 | <$0.50 | ~$1.00 | **$0 (FREE)** | ~$0 (promo) | ~$0.50-1.00 | ~$0.50 | $0.20 | **$0 (FREE)** |
| **Optimism** | $0.04 | <$0.50 | ~$1.00 | Low | Low (promo) | Unconfirmed | Low | $0.20 | **$0 (FREE)** |
| **Polygon** | $0.07 | Low | ~$1.00 | Low | Low | Low | Low | — | **$0 (FREE)** |
| **Solana** | $0.30 | Low | ~$1.00 | Near-zero | $0 (promo) | ~$0.50-1.00 | Low | $1.00 | **$0 (FREE)** |
| **TRC20** | $1.00 | ~$0.10-2.30 | ~$0.10-1.60 | $1.00 | ~$1.00 | $1.50 | **$0 (FREE)** | $1.00 | **$0 (FREE)** |
| **ERC20** | $0.80 | >$3.00 | ~$3.00 | Higher | ~$0.50 | $5.50 | Higher | $10.00 | ~$0.50 |

### Cheapest Rebalancing Routes

| From → To | Best Network | Fee | Speed |
|-----------|-------------|-----|-------|
| Binance → anywhere | BEP20 | $0.01 | ~3s |
| MEXC → anywhere | Arbitrum | $0 (free) | ~0.3s |
| Gate.io → anywhere | TRC20 | $0 (free) | ~3-5s |
| Gate.io → anywhere | BEP20 | $0 (promo) | ~3s |
| Bybit → anywhere | Plasma | ~$0 | Sub-second |
| Pionex → anywhere | Arbitrum | $0.20 | ~0.3s |
| Bitfinex → anywhere | TRC20/Arbitrum/Optimism | $0 (free) | ~0.3-5s |
| Anyone → Binance | BEP20 | Varies by sender | ~3s |

### Plasma Network Details

- **On-chain fee:** Truly $0 — protocol-level paymaster subsidizes gas for USDT transfers
- **Speed:** Sub-second finality (PlasmaBFT consensus)
- **No need to hold XPL** token to send USDT
- **Confirmed exchange support:** Binance ($0.01), Bybit (~$0), Kraken (USDT0)
- **Likely supported:** OKX (deep partnership content)
- **Not yet confirmed:** MEXC, Bitget (wallet only), KuCoin, Gate.io
- **Verdict:** Best option once all exchanges support it. For now, BEP20 is more practical due to universal support.

### For Native Coins

Transfer each coin on its own native chain (e.g., SOL on Solana, XRP on XRP Ledger, etc.) for the cheapest and fastest transfers.

## WebSocket Implementation Details

| Aspect | Binance | OKX | Bybit | MEXC | Bitget | KuCoin | Gate.io | Pionex | Bitfinex |
|--------|---------|-----|-------|------|--------|--------|---------|--------|----------|
| Subscribe | URL params | Post-connect | Post-connect | Post-connect | Post-connect | Post-connect | Post-connect | Post-connect | Post-connect |
| Symbol format | `btcusdt` | `BTC-USDT` | `BTCUSDT` | `BTCUSDT` | `BTCUSDT` | `BTC-USDT` | `BTC_USDT` | `BTC_USDT` | `tBTCUST` |
| Ping type | WS-level (lib) | String `"ping"` | JSON `{"op":"ping"}` | JSON `{"method":"PING"}` | String `"ping"` | JSON `{"type":"ping"}` | JSON `{"channel":"spot.ping"}` | JSON `{"op":"PING"}` | JSON `{"event":"ping"}` |
| Ping interval | 20s (auto) | 15s | 18s | 15s | 25s | 18s | 15s | 15s | 15s |
| Has last_price | Yes | Yes | Yes | No | Yes | Yes | No | Yes (TRADE topic) | Yes |
| Has volume | Yes | Yes | Yes | No | Yes | No | No | No | Yes |
| Special | — | — | Delta merging | 30 sub limit | — | REST token first | Per-symbol subscribe | DEPTH+TRADE topics | Array data, 30 sub limit, 2 connections |

## Key Technical Requirements

### Real-Time Data

- Use **WebSocket** connections to all exchanges for live price feeds (not REST polling)
- Sub-second price updates required for competitive arbitrage
- Track both bid and ask prices (not just last price) to calculate real spread

### Execution

- Simultaneous order placement on two exchanges when opportunity detected
- Use **limit orders** (maker) when possible to minimize fees
- Fall back to **market orders** (taker) when speed is critical
- Handle partial fills gracefully

### Risk Management

- Maximum position size per trade
- Maximum exposure per exchange
- Circuit breaker if too many failed trades
- Monitor exchange API health and latency
- Track all open positions and P&L in real-time

### Capital Management

- 60 symbols x 9 exchanges = many balance positions to manage
- Automated rebalancing triggers when imbalances exceed threshold
- Track withdrawal limits and cooldowns per exchange

## Critical Warnings

1. **Competition is brutal** - HFT firms with co-located servers operate at sub-millisecond latency
2. **Fees eat margins** - A 0.1% spread with 0.1% fees on each side = net loss
3. **Slippage** - Prices move between detection and execution
4. **Exchange risk** - Exchanges can go down, get hacked, or freeze withdrawals
5. **API rate limits** - Exceeding limits gets you temporarily banned
6. **Regulatory risk** - KYC/AML requirements on all exchanges
7. **Capital locked** - Most capital sits idle across exchanges, not earning

## Strong-Only Trading

The bot only trades and transfers for **strong** (score ≥ 0.1) and **very strong** (score ≥ 0.3) symbols. All other symbols are scored but not traded. Thresholds are configurable via dashboard Settings: `TRADING_SCORE_THRESHOLD` (0.01), `STRONG_SCORE_THRESHOLD` (0.1), `VERY_STRONG_SCORE_THRESHOLD` (0.3) — stored as instance variables `_trading_threshold`, `_strong_threshold`, `_very_strong_threshold` in `optimizer.py`.

### Rules

- **Discovery**: Activates symbols with score ≥ 0.01. Extends discovery duration (up to 3600s) if none qualify.
- **Early discovery exit**: If any symbol reaches score ≥ 0.01 during discovery (after 60s minimum), discovery ends immediately and trading starts.
- **Trading**: Normal tier (0.01–0.1) gets `trade_multiplier = 0.5–1.5×`. Weak symbols (< 0.01) get `trade_multiplier = 0`.
- **Rebalancing**: `should_allow_rebalance()` requires score ≥ 0.01 (`TRADING_SCORE_THRESHOLD`). ROI gate, net P&L gate, and transfer worthiness checks protect against unprofitable transfers.
- **Expansion/Rotation**: Only strong/very_strong candidates can be activated or replace existing symbols.
- **Faster activation**: Watchlist confirmation period is score-dependent: very strong (≥0.3) confirmed in `confirmation_period × 0.1` (30s default), strong (≥0.1) in `× 0.4` (120s), normal in full period (300s). Strong candidates shouldn't sit idle.
- **Demotion**: Symbols dropping below 0.1 are demoted on a tiered schedule (faster for weaker scores). All held crypto is **sold immediately** on demotion (internal sell → USDT) to eliminate market exposure risk. Cooldown = `demotion_period × demotion_cooldown_multiplier` (default 5.0 = 3000s/50 min). No minimum active count protection — better idle than bleeding money on transfers.
- **Elevated re-activation**: `_get_activation_threshold(symbol)` raises the required score for frequently-demoted symbols. Each demotion adds 50% of base threshold, capped at `strong_threshold`. A symbol demoted 3 times needs score ≥ 0.025 instead of 0.01.

### Focus Tiers & Trade Multipliers

| Tier | Score | Trade Multiplier | Exchange Count |
|------|-------|-----------------|----------------|
| Very Strong | ≥ 0.3 | 3.0×–4.0× | Up to 3 per direction (6 max) |
| Strong | ≥ 0.1 | 2.0×–3.0× | Up to 2 per direction (4 max) |
| Normal | 0.01–0.1 | 0.5×–1.5× | Up to 2 per direction (4 max) |
| Weak | < 0.01 | 0× (no trading) | — |

### Historical Tracking

The bot tracks strong/very_strong transitions in `HistoricalSymbolStats`:
- `times_became_strong` / `times_became_very_strong` — how many times a symbol entered each tier
- `total_strong_duration` / `total_very_strong_duration` — cumulative seconds spent in each tier
- Visible in Rankings page historical table and exported in XLSX

## Exchange & Symbol Concentration

Instead of spreading capital uniformly across all exchanges, the bot concentrates on the **dominant exchange pair** per symbol — the 1-2 exchanges where the symbol actually profits.

### Dominant Pair Detection

`_compute_dominant_pairs(symbol, max_per_direction)` analyzes rolling tick data:
- Weights each exchange's buyer/seller score by `best_net_pct` (profitability)
- **Fee-weighted tie-breaking**: Lower-fee exchanges get weight boost in `_select_top()`. Bitfinex (0%) gets ~2× boost vs Bybit (0.10%). Large profitability differences still dominate.
- **Seller withdrawal-fee penalty**: Seller exchanges with withdrawal fee > $0.20 get weight reduced by up to 50%. Prevents USDT accumulation on expensive-withdrawal exchanges (e.g., Gate.io $0.50, KuCoin $0.40).
- Selects top N exchanges per direction (buy/sell), ignoring < 2% weight
- `max_per_direction` is tier-based: 2 for default/strong, 3 for very_strong
- Falls back to historical `buy_exchange_counts` / `sell_exchange_counts` if insufficient rolling data

### Capital Allocation

After discovery, capital is allocated per-symbol to dominant exchanges:
- **Bitfinex reserve carved out first**: `total_capital × bitfinex_reserve_pct` (default 15%) kept as USDT on Bitfinex before symbol allocation
- Remaining capital: USDT → buyer exchanges (proportional to buyer weight)
- Crypto → seller exchanges (proportional to seller weight)
- 50/50 split between buy side and sell side per symbol
- Score-weighted across symbols: higher-scoring symbols get more capital

### Dynamic Re-evaluation

`_reevaluate_dominant_pairs()` runs every evaluation cycle for active symbols. If dominant exchanges shift (buyer or seller changed), capital is reallocated via `_reallocate_symbol()`. Gated by rotation budget and cooldown (3× evaluation_interval). `_reallocate_symbol()` has a **cost estimation gate**: estimates sell+buy taker fees and compares against `est_hourly_profit × reallocation_cost_horizon` (default 2h). Skips if cost exceeds benefit.

### Dashboard Display

The "Exchanges" column in Symbol Rankings shows dominant pairs as `BIN→KUC` (buyer→seller). The Buy-Sell Distribution sheet in XLSX shows per-exchange tick counts.

## Bitfinex USDT Reserve

Bitfinex has $0 withdrawal fees on 14/15 networks, making it the ideal capital safety net. The reserve prevents "death spirals" where the net P&L gate blocks rebalancing, capital gets stuck on wrong exchanges, and trading stalls.

### Configuration

- `BITFINEX_RESERVE_PCT` (default 0.15 = 15%) in `config.py`, configurable via Settings
- Reserve target = `total_capital × reserve_pct` (e.g., $270 for $1800 capital)

### How It Works

1. **Carve-out at discovery**: Before allocating capital to symbols, `reserve_amount` is set aside as USDT on Bitfinex
2. **Protection during rebalancing**: Normal rebalance source selection uses `_available_usdt_for_rebalance()` which excludes the reserve from Bitfinex's available balance
3. **Protection during trading**: `available_usdt_for_trading()` prevents trades from spending Bitfinex USDT below the reserve target. Used in both `_compute_trade_size()` and `can_execute()`. Without this, Bitfinex as a buyer exchange drains the reserve through normal trading, triggering expensive replenishment cycles.
4. **Emergency draw**: When net P&L gate blocks rebalancing AND miss streak ≥ 2× threshold, `emergency_reserve_draw()` transfers USDT from Bitfinex to the starved exchange — **bypasses all gates** (net P&L, hourly cap, transfer worthiness). Fee = $0.
5. **Periodic replenishment**: Every evaluation cycle (when net profit is positive), `replenish_reserve()` tops up from free/near-free exchanges only (fee ≤ $0.01: MEXC, Bybit, Binance, Bitget). Minimum transfer $50 or `trade_amount × 5`. 10-minute cooldown per source. Respects hourly budget.

### Key Methods

| Method | File | Purpose |
|--------|------|---------|
| `available_usdt_for_trading(ex)` | `balance.py` | Returns USDT minus reserve if Bitfinex (for trade sizing/execution) |
| `_available_usdt_for_rebalance(ex)` | `balance.py` | Returns USDT minus reserve if Bitfinex (for rebalance source selection) |
| `emergency_reserve_draw(target, amount)` | `balance.py` | Emergency $0-fee transfer from reserve |
| `replenish_reserve()` | `balance.py` | Top up reserve from free exchanges (fee ≤ $0.01) |

## Adaptive Trading System

The bot has a capital-aware adaptive trading system controlled by the **Adaptive Mode** toggle (enabled by default in settings).

### Per-Symbol Trade Sizing

Each active symbol gets a **trade multiplier** based on its focus tier (see Strong-Only Trading above). Only strong/very_strong symbols receive non-zero multipliers.

- `allocated_trade_size = trade_amount × multiplier × tick_quality_factor`
- Tick quality factor: 1.0 (net ≥ 0.10%), 0.90 (≥ 0.05%), 0.85 (< 0.05%)
- **Dynamic buffer**: Trade size capped by 95% of available balance when balance < 2× min_trade (small positions), 80% otherwise. Prevents wasting $2-8 on tiny positions.
- Minimum trade: `max($5, total_capital × 0.003)` — computed before buffer to enable dynamic sizing

### Transfer Fee Awareness

Each exchange has different USDT withdrawal fees per network, managed by `TransferFeeManager` in `transfer_fee_manager.py`. Default configs are in `config.py: DEFAULT_TRANSFER_CONFIGS` with full per-network data (8-17 networks per exchange). Three fee types: flat, percentage (KuCoin ERC20: max($5.50, amount × 0.2%)), and conditional (Gate.io TRC20: free if ≥ 2,020 USDT). Effective fees (with "auto" preferred network):

| Exchange | Cheapest Network | Effective Fee |
|----------|-----------------|---------------|
| Bitget   | Plasma          | $0.001 |
| Binance  | BEP20           | $0.01 |
| MEXC     | Arbitrum        | $0.00 |
| Bybit    | Aptos           | $0.00 |
| OKX      | Polygon         | $0.10 |
| KuCoin   | Plasma          | $0.40 |
| Gate.io  | BEP20           | $0.50 |
| Pionex   | Arbitrum        | $0.20 |
| Bitfinex | TRC20/Arb/Opt   | $0.00 |

Before executing an external USDT transfer, the bot checks **transfer worthiness**: if `withdrawal_fee / estimated_profit_per_trade > 50`, the transfer is skipped (not worth the cost). This prevents expensive transfers unless highly profitable. Configurable per-exchange via the Transfer Fees tab in Settings.

### Adaptive Rebalance Amounts

Instead of a static rebalance amount, the bot targets **3× trade_amount** to cover multiple upcoming trades. Capped at `trade_amount × 4`.

### Smart Capital Allocation

After discovery, capital is allocated via the Exchange & Symbol Concentration system (see above). Each symbol's capital goes only to its dominant buyer/seller exchanges, weighted by profitability scores.

### Rebalance Guards

Multiple gates prevent unprofitable rebalancing:

1. **Tradeable gate**: `should_allow_rebalance()` requires `score >= 0.01` (`TRADING_SCORE_THRESHOLD`). Weak symbols (< 0.01) never trigger rebalances.
2. **ROI gate**: `_should_rebalance()` in monitor.py estimates rebalance cost. Threshold = `fee_rate / rebalance_roi_divisor` (configurable, default 3, recommended 5-10 for small capital). Blocks when amortized cost exceeds per-trade profit.
3. **Net P&L gate**: After `net_pnl_gate_warmup_trades` (default 10) trades AND `net_pnl_gate_grace_seconds` (default 1800s) elapsed, if `trading_pnl + cashback < external_transfer_fees` (net negative using external-only fees), all rebalancing is blocked. All three params configurable via Settings.
4. **Dynamic miss-streak threshold**: `_get_miss_threshold(buy_ex, sell_ex)` returns lower threshold for cheap exchanges. Free transfers (both ≤ $0.01): `base // 3` (min 3). Cheap (either < $0.20): `base // 2` (min 5). Otherwise: full `min_misses_before_rebalance`. Streak only resets to 0 when `try_rebalance()` returns actual transfers — failed attempts preserve the streak so it keeps growing.
5. **Transfer worthiness**: External transfers blocked if `withdrawal_fee / estimated_profit > 50`.
6. **Hourly external transfer budget**: Rolling 1-hour window caps total external withdrawal fees at `hourly_external_transfer_cap` (default $2.00/hr). Internal rebalances (sell/buy on same exchange) are not limited. Persisted across restarts. 0 = disabled.
7. **Cooldown**: 60s between rebalances per exchange/direction.
8. **Dynamic rebalance buffer**: Eligibility threshold for rebalance sources scales with trade amount (`trade_amount × 2`) instead of the fixed $50. For $10 trades, source needs $20 buffer (not $50), making internal sells and external transfers viable for smaller positions. Logged as `[Balance] USDT/Crypto rebalance FAILED` with diagnostics when all options exhausted.

### Rebalance Order

In `try_rebalance()`, crypto rebalance runs BEFORE USDT rebalance. This ensures external crypto transfer (e.g., Bitget→KuCoin $0.10) uses accumulated crypto on the buyer before internal sell would consume it. Saves ~$0.14 per cycle vs the reverse order.

### Net Profit Awareness

The optimizer tracks whether net profit (trading P&L - **external** transfer fees + credited cashback) is positive. Uses external-only fees (withdrawal fees) not total transfer fees (which includes internal taker fees). Supports grace period: `update_profit_state(net_profit, hourly_rate, grace_active)` — during grace period, rotation gate stays open. Logs transitions: `[Optimizer] Rotation gate CLOSED/OPENED`. When in deficit (after grace):
- Rotations, expansions, AND rebalancing are blocked
- Demotions still run to remove dead symbols
- Updated by dashboard server every state broadcast via `update_profit_state()`

### Configuration History

Every configuration change is tracked with a `ConfigSnapshot` (timestamp, reason, all parameters). Snapshots are recorded:
- On startup ("initial")
- When settings are applied from dashboard ("settings_applied")
- Periodically in adaptive mode every 300 ticks ("adaptive_update")

All snapshots are exported in the XLSX "Configurations" sheet.

### Key Files

| File | Responsibility |
|------|---------------|
| `monitor.py` | `_compute_trade_size()` — per-symbol adaptive sizing; `_tick()` — trade execution with threshold checks, ROI gate, miss streak tracking; `ConfigSnapshot` dataclass |
| `balance.py` | `compute_rebalance_amount()` — adaptive rebalance; transfer worthiness check in `_rebalance_usdt()`/`_rebalance_crypto()` |
| `optimizer.py` | `_compute_scores()` — focus tiers + trade multipliers; `_complete_discovery()` — strong-only activation + concentrated allocation; `_compute_dominant_pairs()` — per-symbol exchange detection; `_evaluate_demotions()` — strong threshold gating; `_track_candidate_transitions()` — strong/very_strong historical tracking |
| `config.py` | `DEFAULT_FEE_CONFIGS`, `DEFAULT_TRANSFER_CONFIGS`, `ADAPTIVE_MODE` |
| `fee_manager.py` | `FeeManager` — centralized fee computation, token discounts, referral cashbacks, zero-fee pairs, real mode |
| `transfer_fee_manager.py` | `TransferFeeManager` — per-exchange per-network withdrawal fees (flat/percentage/conditional), preferred network selection |
| `settings.json` | Runtime settings including `adaptive_mode`, `min_net_profit_pct`, `trade_amount_usd`, `total_capital`, `fee_configs`, `transfer_configs`, `reallocation_cost_horizon`, `demotion_cooldown_multiplier`, `hourly_external_transfer_cap` |

## Dashboard

React/TypeScript SPA served by the Python backend via WebSocket. Uses `HashRouter` for client-side URL routing (no nginx config needed). Full-width layout optimized for 1920px screens.

### Pages

All pages have their own URL routes (`/#/`, `/#/rankings`, `/#/settings`, `/#/logs`). Sub-tabs also have routes (e.g., `/#/settings/fees`, `/#/logs/auth`, `/#/rankings/historical`). Browser back/forward and refresh work correctly.

- **Dashboard** — Real-time overview: portfolio P&L (sim + demo), trade/transfer stats, demo exchange status, symbol rankings with dominant exchange pairs (e.g. `BIN→KUC`) and live Cur Net% column, balance table, price grid, demo portfolio comparison, recent trades/transfers, rotation log. Fully responsive: 2×2 stats grid, horizontal-scroll tables, bottom tab nav on mobile.
- **Rankings** — Deep analysis: full rolling rankings table with Mult/Trade $ columns, top-10 charts (by score, frequency, $/hr), historical session stats with Strong/V.Strong columns and duration, lifecycle funnel, exchange rankings, pair analysis, trend analysis, watchlist. Performance charts section (cumulative P&L, hourly P&L, exchange profit contribution) using recharts. Markdown export ("Copy MD") for sharing data with Claude. All tables horizontal-scroll on mobile.
- **Settings** — Three sub-tabs (routed: `/settings`, `/settings/fees`, `/settings/transfers`). Each setting has a `?` tooltip icon with detailed description (hover on desktop, tap on mobile):
  - **General**: Configure all parameters: trade amount, capital, min net profit %, rebalance cooldown, ROI horizon, adaptive mode toggle, auto-rotate, symbol limits, IP whitelist. **Danger Zone**: "Restart Bot" button clears saved state and starts fresh with configured capital. Form grids stack single-column on mobile.
  - **Fee Management**: Per-exchange fee configuration — **enable/disable checkbox** per exchange (disabled = excluded from trading/rebalancing, hot-applied), base taker rate, token discount toggle+%, fee model (received/spent/token), mechanism (instant/rebate/tier), referral cashback toggle+%+settlement delay, zero-fee pairs. Shows computed effective rates with formula breakdown. Cashback stats (pending/credited). Real mode banner. Save button with 5s cooldown. Hot-applied without restart.
  - **Transfer Fees**: Per-exchange withdrawal fee configuration — per-network fees (flat/percentage/conditional), preferred network selector (auto=cheapest), enable/disable individual networks. Shows effective fee and cheapest network per exchange. Save button with 5s cooldown. Hot-applied without restart.
- **Logs** — Unified log viewer with two sub-tabs:
  - **Bot Logs**: Real-time terminal-style log viewer (font-mono, auto-scroll). Filters: level (INFO/WARNING/ERROR), component (Monitor/Optimizer/Balance/exchanges/Dashboard/Auth/Email/Settings/Fee), text search. Export to `.log` file.
  - **Auth Logs**: Authentication event log (login success/failure, blocked IPs, reconnections, IP denials). Filterable by event type with search by IP/username/browser/OS. Export to `.csv` file.
  - **Export**: Presets (1 Hour, 6 Hours, Today, 1 Day, Current Session, All, Custom UTC datetime picker). "Apply current filters" checkbox auto-checks when UI filters are active. Reads from disk log files for cross-day ranges.

### Dashboard Authentication

Full authentication system for the WebSocket dashboard:

- **Login**: Username + bcrypt-hashed password. Set `DASHBOARD_PASSWORD_HASH` in `.env` (preferred) or legacy `DASHBOARD_PASSWORD` (auto-hashed at runtime with deprecation warning). Default password `changeme` is rejected at startup.
- **Sessions**: Token-based with remember-me support. Remember-me → localStorage (30-day absolute expiry). Non-remember → sessionStorage (24h idle / 48h absolute expiry). All sessions have `created_at` for absolute lifetime enforcement.
- **Rate limiting**: 10 attempts per IP, 1-hour block after exhaustion. State persisted to `logs/auth/rate_limits.json` (survives restarts). CAPTCHA failures also count toward rate limit.
- **IP whitelist**: Optional, configurable from Settings page. Validated with `ipaddress` module.
- **reCAPTCHA v2**: "I'm not a robot" checkbox appears after 3 failed attempts (requires Google reCAPTCHA v2 keys in `.env`). Warning logged at startup if keys not configured.
- **Email notifications**: Gmail SMTP alerts on successful login and IP block (requires Gmail App Password in `.env`). All user-controlled values HTML-escaped. Email suppressed during 30s grace period after bot restart (prevents spam from auto-reconnection).
- **Auth log**: All auth events persisted to `logs/auth/auth_events.jsonl` (5MB rotation, 2 backup files), loaded on startup (500 max), viewable in Logs → Auth Logs tab. Passwords masked (first 2 chars + asterisks). Legacy plaintext passwords stripped on load.
- **Dedicated auth logger**: Human-readable log at `logs/auth/auth.log`
- **X-Forwarded-For**: Only trusted from IPs in `TRUSTED_PROXIES` (default: `127.0.0.1,::1`). Prevents IP spoofing to bypass rate limits/whitelist.
- **Origin validation**: When `ALLOWED_ORIGINS` is set, WebSocket connections from unknown origins are rejected (CSRF protection).
- **Settings validation**: All settings validated against schema (type, min/max ranges). Unknown keys rejected. IP whitelist entries validated. 5s cooldown between settings saves.
- **Bind host**: Default `127.0.0.1` (behind nginx). Override with `DASHBOARD_BIND_HOST=0.0.0.0` for direct access.
- **IP denied priority**: Denied IPs see nothing rendered (blank screen) until `auth_denied` arrives, then immediately the "You are not allowed here" page. No spinner, no loading text — `wsInitialized` gate ensures zero UI leakage.

### Bot Logging

- **Format**: UTC timestamps via `time.gmtime` converter: `YYYY-MM-DD HH:MM:SS [LEVEL] [Component] message`
- **Daily rotation**: `TimedRotatingFileHandler` rotates at 00:00 UTC, keeps 30 days. Files: `logs/coirnabot.log` (current), `logs/coirnabot.log.YYYY-MM-DD` (rotated).
- **DashboardLogHandler**: Custom `logging.Handler` in `dashboard_server.py`. Captures entries in-memory (`deque` for live broadcast, `list` for session export). Parses `[Component]` prefix from log messages.
- **Latency logging**: `[Latency]` component prefix. Every 60s logs per-exchange: processing time (avg/min/max ms), message rate (msgs/s), data freshness (avg/max age ms) with active/dormant symbol separation (>2min = dormant). Also logs first-data-after-connect timing. Filterable in Bot Logs tab.
- **Diagnostic logging** (added v0.13.5): Six production-level log lines for self-sufficient diagnostics:
  - `[Config]` — All key config values at startup (trade_amount, capital, adaptive, min_net, max_symbols, execution_mode)
  - `[Trade]` — Per-trade execution: symbol, exchanges, buy/sell prices, qty, size, profit, net%
  - `[Monitor] SIZE_ZERO` — Why trade_size=0: which constraint hit (usdt_avail/crypto_val/base < min_trade). Throttled: first per symbol, then every 30th.
  - `[Rebalance] BLOCKED` — Why rebalancing was blocked: which gate rejected (score_gate/net_pnl_gate/roi_gate) with values. Throttled per miss_key.
  - `[Balance] Snapshot` — Every 5 min: per-exchange total value (USDT + crypto USD), portfolio total, fee breakdown (total vs external-only)
  - `[Session]` — Every 5 min: aggregate trades, pnl, transfer fees, cashback (credited/pending), net, $/hr, SIZE_ZERO count (sz0=), rebalance blocked count (rebal_blocked=)
- **Disk export**: `_read_bot_logs_from_disk()` reads rotated + current log files for cross-day export ranges. `_read_auth_logs_from_disk()` reads JSONL files. Both use `asyncio.to_thread()` for non-blocking I/O.

### State Persistence

Session state survives restarts (including deploys via `systemctl restart`). `StateManager` in `state_manager.py` coordinates save/load.

**What's persisted:**
- **BalanceTracker**: USDT/crypto balances, transfers, fees, initialization state
- **ArbitrageMonitor**: Trade history, config snapshots, tick count, session statistics
- **SymbolOptimizer**: Active symbols, rotations, historical stats, discovery state, dominant pairs
- **DemoPortfolioFetcher**: Baseline snapshots per exchange (first-fetch balances for delta computation)
- **FeeManager**: Pending referral cashbacks and total credited cashback amount

**How it works:**
- Each component implements `to_state_dict()` / `from_state_dict()` for JSON serialization
- Atomic writes: temp file + `os.replace()` to prevent corruption on crash
- Backup: `.bak` file kept as fallback if primary is corrupt
- Periodic saves every 60s + save on shutdown (SIGINT/SIGTERM)
- State stored in `state/session.json` (gitignored)
- `run()` methods guard timestamps (`_start_time`, `_discovery_start`) to avoid overwriting restored values

**Restart button:** Settings → Danger Zone → "Restart Bot" clears saved state and restarts the process via `os.execv()`. Starts fresh with configured capital. Works both locally and under systemd. On restart: writes `state/restart_marker` file, client receives `restart_ack` → preserves auth state and shows stale data with yellow "Reconnecting..." indicator in header, auto-reconnects in ~2-5s without re-login. Email notifications suppressed during 30s grace period after restart.

### XLSX Export

Click "Export XLSX" on the Rankings page. 18 sheets: Summary, Rolling Rankings, Historical Rankings (includes Times Strong/Very Strong, Strong/Very Strong Duration columns), Exchange (Rolling/Historical), Exchange Pairs, Watchlist, Rotation History, Tier Analysis, Trade History, Transfer History, Transfer Summary, Trend Analysis, Buy-Sell Distribution, Configurations, Fee Configuration, Transfer Configuration, Discrepancies.

### Markdown Export

Click "Copy MD" on the Rankings page to copy markdown tables to clipboard (for sharing with Claude). Sections: Session Summary, Rolling Rankings, Historical Rankings, Exchange Rankings, Recent Trades (last 50), Recent Transfers (last 20). Generated by `exportMarkdown.ts`.

### Key Dashboard Files

| File | Purpose |
|------|---------|
| `dashboard/src/App.tsx` | Main layout, HashRouter routing, WebSocket state, IP-denied priority gate, restart reconnection |
| `dashboard/src/types.ts` | All TypeScript interfaces (Trade, SymbolRanking, AdaptiveConfig, ConfigSnapshot, AuthLogEntry, BotLogEntry, DemoComparisonState, etc.) |
| `dashboard/src/hooks/useWebSocket.ts` | WebSocket connection, auth flow, state management, restart_ack handling, wsInitialized gate, export callbacks |
| `dashboard/src/components/LoginPage.tsx` | Login form with reCAPTCHA integration |
| `dashboard/src/components/LogsPage.tsx` | Unified Logs page container with Bot Logs / Auth Logs sub-tabs |
| `dashboard/src/components/BotLogsTab.tsx` | Terminal-style real-time bot log viewer with filters and auto-scroll |
| `dashboard/src/components/AuthLogPage.tsx` | Auth event log with filtering/search and CSV export |
| `dashboard/src/components/ExportLogsModal.tsx` | Reusable export modal with time presets, custom UTC picker, filter toggle |
| `dashboard/src/components/SymbolRankings.tsx` | Main page ranking card with Cur Net% column |
| `dashboard/src/components/RankingPage.tsx` | Full ranking analysis page with performance charts and markdown export |
| `dashboard/src/components/PerformanceCharts.tsx` | Recharts: cumulative P&L, hourly P&L, exchange profit contribution |
| `dashboard/src/components/Tooltip.tsx` | Reusable `?` icon tooltip (hover/tap) for settings descriptions |
| `dashboard/src/components/DemoComparison.tsx` | Per-exchange demo vs sim comparison cards with discrepancy log |
| `dashboard/src/components/SettingsPage.tsx` | Settings form with General/Fee Management/Transfer Fees sub-tabs, adaptive mode toggle, IP whitelist, restart button |
| `dashboard/src/components/FeeManagementTab.tsx` | Per-exchange fee configuration UI — discounts, referral cashback, zero-fee pairs |
| `dashboard/src/components/TransferFeeManagementTab.tsx` | Per-exchange transfer fee configuration UI — per-network fees, preferred network, enable/disable |
| `dashboard/src/utils/exportXlsx.ts` | XLSX export with all 18 sheets |
| `dashboard/src/utils/exportMarkdown.ts` | Markdown table export for clipboard (rankings, trades, transfers) |
| `dashboard_server.py` | Python WebSocket server, auth system, builds state, handles settings, log export from disk, restart handler |
| `demo_fetcher.py` | Demo/testnet portfolio fetcher: REST API clients for Binance/OKX/Bybit, baseline snapshots, discrepancy detection |
| `state_manager.py` | Session state persistence: atomic save/load, periodic saves, clear for fresh restart |
| `email_notifier.py` | Gmail SMTP email notifications (login alerts, IP block alerts) |

## Tools

### XLSX Reader

Use `read_xlsx.py` — CLI tool to read exported XLSX files without the dashboard:

```
python read_xlsx.py                          # latest file in xlsx/, all sheets (20 rows max)
python read_xlsx.py xlsx/some_file.xlsx      # specific file
python read_xlsx.py -s "Rolling Rankings"    # specific sheet
python read_xlsx.py -s Summary               # summary in key-value format
python read_xlsx.py --list                   # list sheet names and row counts
python read_xlsx.py -r 50                    # show up to 50 rows per sheet
```

## Demo/Testnet Portfolio Comparison

Fetches real portfolio balances from exchange demo/testnet APIs and displays them alongside the simulation to validate accuracy. Prepares for Phase 2 (actual demo order execution).

### Supported Demo Exchanges

| Exchange | API Endpoint | Auth Method |
|----------|-------------|-------------|
| Binance | `https://testnet.binance.vision/api/v3/account` | HMAC-SHA256, header `X-MBX-APIKEY` |
| OKX | `https://www.okx.com/api/v5/account/balance` | HMAC-SHA256 + passphrase, header `x-simulated-trading: 1` |
| Bybit | `https://api-demo.bybit.com/v5/account/wallet-balance` | HMAC-SHA256 |

Gate.io, Bitget, KuCoin, MEXC continue simulation-only (no demo/testnet APIs available).

### Baseline Snapshot System

Pre-funded testnet balances (Binance ~$10k, OKX ~$5k, Bybit ~$50k) are subtracted so only bot-caused activity is visible:

- **Baseline** = snapshot captured on first successful fetch per exchange (persisted across restarts)
- **Delta** = `current_balance - baseline` (change since baseline)
- **Displayed demo value** = `sim_value + delta` (mirrors sim, diverges only when real trades happen)
- When no demo trades executed: delta = 0, displayed = sim, diff = 0

### Discrepancy Detection

Comprehensive sim-vs-demo validation system. See `DISCREPANCIES.md` for the full list of 20 discrepancy types (D-01 through D-20).

**Runtime detection** runs after each poll (15s interval). Compares baseline-adjusted demo values against simulation:
- USDT balance mismatch (threshold: $1 or 1%)
- Crypto position mismatches (qty delta vs sim qty)
- Fee rate mismatches (D-04: actual exchange fees vs configured)
- Root cause classification: fee difference, slippage, missing/extra position, stale data

**Exchange trading rules** (`exchange_info.py`) fetched at startup to validate:
- D-01: Lot size rounding — quantities rounded DOWN to exchange lot_size_step using Decimal
- D-02: Min notional — trades below exchange minimum order value are rejected
- D-03: Price tick size — prices rounded to tick_size
- D-07: Stale price detection — data age tracked per trade in `SimulatedTrade.data_age_ms`

**Fee rate validation** (D-04): On first successful demo fetch per exchange, actual fee rates are queried from exchange APIs (Binance: from `/api/v3/account` commissionRates, OKX: `/api/v5/account/trade-fee`, Bybit: `/v5/account/fee-rate`). If actual rate differs from the FeeManager production config, a WARNING is logged. Simulation keeps the production rate for realistic P&L; in Real Mode, actual API rates override config via `FeeManager.set_real_rate()`.

**Quantity rounding** in `balance.py:execute_trade()`: When `exchange_info` is available, buy and sell quantities are rounded DOWN to lot_size_step. Unspent USDT stays in balance (realistic behavior). Returns an adjustment dict with raw/rounded quantities and rounding impact.

**Trade metadata**: `SimulatedTrade` includes `buy_qty_raw`, `buy_qty_rounded`, `sell_qty_raw`, `sell_qty_rounded`, `rounding_impact_usd`, `data_age_ms` fields for sim validation.

### Dashboard Integration

- **Stats cards**: Card 1 shows sim + demo portfolio P&L with delta. Card 2 shows trade count + demo exchange status. Card 3 shows trade profit + cashback (credited/pending). Card 4 shows net $/hr + demo $/hr + sim accuracy %.
- **Demo Portfolio Comparison section**: Per-exchange cards (sim vs demo columns for USDT, crypto, total) with color-coded diffs
- **Discrepancy log**: Scrollable table of recent mismatches with time, exchange, type, values, root cause
- **XLSX export**: 16th sheet "Discrepancies" with timestamp, exchange, type, symbol, sim/demo values, diff, root cause

### Key Files

| File | Responsibility |
|------|---------------|
| `DISCREPANCIES.md` | All 20 discrepancy types documented with priority, status, detection, fix |
| `exchange_info.py` | `ExchangeInfoManager` — fetches lot sizes, tick sizes, min notionals from all 6 exchanges at startup |
| `demo_fetcher.py` | `DemoPortfolioFetcher` — REST API clients, baseline management, delta computation, discrepancy detection, fee rate validation |
| `config.py` | Demo API key constants, `DEFAULT_FEE_CONFIGS` (7 exchanges, 10 fields each) |
| `balance.py` | `execute_trade()` — quantity rounding via exchange rules, returns adjustment dict |
| `monitor.py` | `_compute_trade_size()` — min notional/qty validation; `SimulatedTrade` — rounding/age metadata |
| `dashboard_server.py` | `_build_demo_state()` — builds baseline-adjusted per-exchange comparison data for dashboard |
| `state_manager.py` | Persists demo_fetcher baselines via `to_state_dict()` / `from_state_dict()` |

## Phase 2: Demo/Testnet Order Execution (Implemented)

When `execution_mode=demo`, the simulation continues as baseline while real market orders are placed on exchange testnets in parallel. Actual fill data (price, qty, fees, latency) is compared with sim expectations to detect discrepancies D-05, D-08 through D-14, D-17, D-19, D-20.

### Execution Mode

Set in `settings.json`: `"execution_mode": "simulation"` (default) or `"demo"`. Dashboard Settings page has a selector. Requires restart to take effect.

### Architecture

```
Monitor._tick() detects opportunity
  ├─ balance.execute_trade()          ← sim (always runs)
  ├─ SimulatedTrade created + appended
  └─ asyncio.create_task(_execute_demo_trade())   ← demo (fire-and-forget)
       └─ DemoExecutor.execute_arbitrage()
            ├─ asyncio.gather(buy_executor, sell_executor)
            ├─ One-legged recovery if needed (D-11)
            ├─ _record_demo_comparison() → updates SimulatedTrade.demo_* fields
            └─ state_mgr.save() → immediate crash safety
```

### Key Files

| File | Purpose |
|------|---------|
| `executor.py` | `TradeResult`, `ArbitrageResult`, `RateLimiter`, `ExecutionEngine` base, `DemoExecutor` coordinator |
| `executors/__init__.py` | Package init |
| `executors/binance_exec.py` | Binance testnet: `https://testnet.binance.vision`, HMAC-SHA256, rate limit 100/60s |
| `executors/okx_exec.py` | OKX demo: `https://www.okx.com` + `x-simulated-trading: 1`, HMAC+passphrase, rate limit 50/2s |
| `executors/bybit_exec.py` | Bybit demo: `https://api-demo.bybit.com`, X-BAPI headers, rate limit 15/1s |

### TradeResult Fields

`success`, `order_id`, `client_order_id`, `exchange`, `symbol`, `side`, `requested_qty`, `filled_qty`, `requested_price`, `actual_avg_price`, `actual_fee`, `fee_rate`, `fee_currency`, `is_maker`, `latency_ms`, `error`, `raw_response`, `timestamp`. Computed properties: `fill_ratio`, `is_partial`, `slippage_pct`.

### SimulatedTrade Demo Fields

`demo_buy_price`, `demo_sell_price`, `demo_buy_qty`, `demo_sell_qty`, `demo_profit_usd`, `demo_latency_ms`, `demo_slippage_pct`, `demo_status` (filled/partial/rejected/one_legged/unknown).

### Discrepancy Detection

`_record_demo_comparison()` runs after each demo trade. Compares sim vs actual:
- **D-05**: Fee currency mismatch (unexpected currency)
- **D-08**: Slippage > 0.01% (avg across legs)
- **D-09**: Partial fill (fill_ratio < 0.99)
- **D-10**: Order rejected (error reason)
- **D-11**: One-legged (one success, one fail) → auto-unwind
- **D-12**: High latency > 500ms
- **D-13**: Maker fill (unexpected for market orders)

### Fee Model (D-05)

`balance.py:execute_trade()` accepts `buy_fee_model`/`sell_fee_model`:
- `"received"` (default): fee from received asset
- `"spent"`: fee added to spent amount
- `"token"`: fee from discount token (BNB/BGB/KCS)

Per-exchange config via `FeeManager.get_fee_model(exchange)`. Configured in Fee Management tab.

### In-Transit Tracking (D-17)

In demo mode, external USDT transfers use `InTransitFund` with estimated network delay (BEP20: 30s). Funds deducted from source immediately, credited to destination on `deliver_in_transit()` (called each tick). Simulation mode keeps instant transfers.

### Crash Safety

1. **Immediate save**: `_execute_demo_trade()` calls `state_mgr.save()` after each demo result
2. **Pending orders**: Client order IDs persisted in state before submission. On crash recovery, queried via `recover_pending_orders()`
3. **Startup reconciliation**: `reconcile_balances()` queries exchange balances, compares with BalanceTracker, logs discrepancies
4. **Idempotent IDs**: Format `coirna-{base}-{side}-{ts}-{uuid6}` (e.g., `coirna-BTC-buy-1740000000000-a1b2c3`)

### What Demo Testing Reveals (vs Simulation)

| Aspect | Simulation | Demo Reality |
|--------|-----------|-------------|
| Fill price | Assumes ticker price | May differ (slippage) |
| Fill time | Instant | 10-500ms latency |
| Partial fills | Never | Can happen on thin orderbooks |
| Rate limits | Not modeled | Real API throttling |
| Order rejection | Never | Insufficient balance, invalid params |
| Fee calculation | Config constants | Exchange may charge differently |
| Fee currency | Always received asset | May be discount token (BNB/BGB/KCS) |
| Transfer speed | Instant | 10-60s+ network transit |

### VPS Deployment Plan

| Phase | Setup | Cost |
|-------|-------|------|
| Current | LightNode Bangkok (monolithic, all 9 exchanges) | $7.70/mo |
| Phase 2 | + Oracle Zurich (free, Bitfinex <1ms) | $7.70/mo |
| Phase 3 | + Vultr Singapore (OKX/Bybit/Bitget/KuCoin/Gate.io) | $12.70/mo |
| Phase 4 | + Tokyo VPS (Binance <1ms, Pionex) | ~$20/mo |

## Fee Management

Comprehensive fee system replacing the flat `EXCHANGE_TAKER_FEES` dict. Managed by `FeeManager` in `fee_manager.py`, configurable from the dashboard Fee Management tab.

### Fee Structure Per Exchange

| Exchange | Base Rate | Token Discount | Effective Rate | Referral Cashback | Settlement | Mechanism | Fee Model |
|----------|-----------|---------------|---------------|-------------------|------------|-----------|-----------|
| Binance | 0.10% | BNB 25% (enabled) | 0.075% | 20% | 60 min (hourly) | instant | token |
| OKX | 0.10% | OKB (disabled) | 0.10% | 20% | 90 min | tier | received |
| Bybit | 0.10% | MNT/BIT (disabled) | 0.10% | 20% | 1440 min (daily) | tier | received |
| MEXC | 0.05% | MX (disabled) | 0.05% | 20% | 1440 min (daily) | instant | received |
| Bitget | 0.10% | BGB 20% (enabled) | 0.08% | 20% | 0 min (instant) | instant | token |
| KuCoin | 0.10% | KCS 20% (enabled) | 0.08% | 20% | 1440 min (daily) | rebate | token |
| Gate.io | 0.10% | GT 10% (enabled) | 0.09% | 20% | 1440 min (daily) | instant | token |
| Pionex | 0.05% | None (VIP tiers only) | 0.05% | 20% | 60 min (hourly) | instant | received |
| Bitfinex | 0.00% | None (permanent 0%) | 0.00% | Disabled | — | instant | received |

### Features

- **Exchange enable/disable**: Each exchange has an `enabled` checkbox in the Fee Management tab. Disabled exchanges are excluded from `_active_exchanges` (monitor/optimizer) and `_exchanges` (balance) — stops all trading and rebalancing on that exchange immediately. WebSocket fetchers still run for scoring data. Re-enabling adds the exchange back. Hot-applied without restart via `_apply_enabled_exchanges()`.
- **Token discounts**: Per-exchange toggle with configurable %. Effective rate = base × (1 - discount%). Gate.io GT gives 10% at VIP 0. Pionex has no discount token (only volume-based VIP tiers).
- **Referral cashbacks**: Enabled for all exchanges except Bitfinex (0% fees already). Tracked as `PendingCashback` with exchange-specific settlement times: instant (Bitget, 0 min), hourly (Binance/Pionex, 60 min), ~90 min (OKX), or daily (Bybit/MEXC/KuCoin/Gate.io, 1440 min). Credited cashback is added to USDT balance and included in net profit calculations (`net_profit = trading_pnl - transfer_fees + credited_cashback`). Displayed in Trade Profit card (credited + pending).
- **Zero-fee pairs**: Override list per exchange (e.g., Gate.io BTC/USDT → 0% fee). Checked before all other rate computation.
- **Fee mechanisms**: `instant` (discount applied immediately), `rebate` (KCS — credited back), `tier` (volume-based, OKX/Bybit). **Note**: Stored as metadata only — no code branches on mechanism type. All mechanisms are treated as instant rate reductions via `effective_taker_rate`.
- **Fee models**: `received` (fee from received asset), `spent` (added to cost), `token` (from discount token balance). **Actively used** in `balance.execute_trade()` — controls how balances change per trade. The `token` model means full crypto/USDT received (fee from discount token), which compounds favorably over hundreds of trades.
- **Sim/Real mode**: Simulation uses configured rates. Real mode overrides with API-queried rates from `DemoPortfolioFetcher`.
- **Hot-apply**: Fee settings changed in dashboard are applied instantly without restart. Exchange enable/disable updates propagate to all components.
- **State persistence**: Pending cashbacks survive restarts via `StateManager`.
- **Scoring fee**: `get_scoring_fee()` returns time-weighted fee including referral cashback for scoring/selection/threshold decisions. Instant cashback (0 min) = 100% weight, hourly (≤120 min) = 75%, daily (>120 min) = 50%. Makes the bot prefer exchanges with fast cashback (e.g., Bitget instant at 0.064% scoring fee vs KuCoin daily at 0.072%). `get_taker_fee()` remains for actual trade execution and cashback recording (no double-counting).
- **Profit integration**: Credited cashbacks are added to `net_profit` in `get_net_profit_stats()` and considered in rebalance gates (`_should_rebalance()`). This means cashback income offsets transfer fees in profitability calculations.
- **[Fee] logging**: Every trade logs fee details and referral cashback amounts. Filterable in Bot Logs.

### Key Files

| File | Responsibility |
|------|---------------|
| `fee_manager.py` | `FeeManager` class, `ExchangeFeeConfig` dataclass (incl. `enabled`), `is_exchange_enabled()`, `get_enabled_exchanges()`, `PendingCashback` tracking, settings serialization, broadcast dict |
| `config.py` | `DEFAULT_FEE_CONFIGS` — 9 exchanges × 11 fields (base rates, discounts, mechanisms, models, referral, zero-fee, enabled) |
| `dashboard_server.py` | `save_fee_settings` handler with validation schema, `_apply_enabled_exchanges()` hot-apply, broadcast via `to_broadcast_dict()` |
| `dashboard/src/components/FeeManagementTab.tsx` | Per-exchange fee config UI with enable/disable checkbox and computed effective rates |

## VPS Infrastructure

### Current: LightNode Bangkok (Production)

- **Provider**: LightNode — $7.70/mo (2 vCPU, 2 GB RAM, 50 GB SSD)
- **Location**: Bangkok, Thailand
- **OS**: Ubuntu 22.04
- **Purpose**: Production monolithic deployment — all 9 exchanges from single VPS. MEXC accessible (Thailand not geo-blocked). Auto-deploy via GitHub Actions on push to master.

### Exchange Server Locations & Latency from Bangkok

| Exchange | Server Location | Cloud | Latency from Bangkok |
|----------|----------------|-------|:--------------------:|
| Binance | Tokyo, Japan | AWS ap-northeast-1 | ~4ms |
| OKX | Hong Kong | Alibaba Cloud / AWS HK | ~63ms |
| Bybit | Singapore | AWS ap-southeast-1 | ~90ms |
| Bitget | Singapore | AWS ap-southeast-1 | ~106ms |
| KuCoin | Singapore | AWS | ~25ms |
| Gate.io | Singapore | AWS ap-southeast-1 | ~161ms |
| MEXC | Singapore | AWS ap-southeast-1 | ~25ms |
| Pionex | Virginia, USA (likely) | AWS us-east-1 (via Cloudflare) | ~5.8s (slow) |
| Bitfinex | Zug, Switzerland | Bare-metal (Market Synergy) | ~1.2s |

### Pionex Geo-Restrictions

Pionex is **blocked** in: US, Singapore, China, Canada, UK, Netherlands, Spain, Cuba, Iran, North Korea, and others.
Pionex is **KYC-blocked in Japan** (confirmed — Japan phone code 81 is on the official unsupported list).
Pionex is **accessible** in: Turkey, Thailand, Germany (monitor EU MiCA for Pionex).

### Bitfinex Geo-Restrictions

Bitfinex is **blocked** in: US, Canada, Cuba, Iran, North Korea, Syria, Crimea, and other sanctioned regions.
Bitfinex is **not blocked** in: Japan (FSA warnings but no IP block), Thailand, Germany, Turkey, Singapore.

### MEXC Geo-Restrictions

MEXC is **fully banned** in: Singapore, Hong Kong, US, Canada, China, North Korea, Iran, Cuba.
MEXC is **partially restricted** in: Japan (API works, but bot crackdown risk), Turkey (use mexc.fm domain).
MEXC is **fully accessible** in: Thailand, Vietnam, most of Europe.

Bangkok VPS: MEXC fully accessible from Thailand. No geo-restrictions.

### Distributed Plan: 4 VPS (~$20/mo)

| VPS | Location | Provider | Exchanges | Cost |
|-----|----------|----------|-----------|:----:|
| VPS 1 | Bangkok | LightNode | MEXC + **Orchestrator** | $7.70 |
| VPS 2 | Singapore | Vultr | OKX, Bybit, Bitget, KuCoin, Gate.io | $5.00 |
| VPS 3 | Tokyo | TBD | Binance (<1ms), Pionex | ~$7.50 |
| VPS 4 | Zurich | Oracle (free) | Bitfinex (<1ms) | $0 |

Bangkok is the orchestrator (all 9 exchanges accessible, MEXC requires Thailand). Bitfinex at 0% fees benefits from dedicated low-latency VPS in Zurich (<1ms vs ~1.2s from Bangkok).

See `documentations/VPS.md` for full latency matrix, geo-restriction matrix, and 4 VPS configuration options (2-5 VPS).

### VPS Provider Comparison (Tokyo)

| Provider | vCPU | RAM | Storage | Bandwidth | Price/mo |
|----------|:----:|:---:|---------|-----------|:--------:|
| **Contabo** | 4 | 8 GB | 75 GB NVMe | Unlimited (200Mbps) | ~$7.50 |
| Kamatera | 2 | 2 GB | 30 GB NVMe | Included | ~$6 |
| Vultr | 1 | 2 GB | 55 GB | 2 TB | $10 |
| AWS Lightsail | 2 | 2 GB | 60 GB SSD | 3 TB | $12 |
| Vultr High Perf | 1 | 2 GB | 50 GB NVMe | 3 TB | $12 |

### Hardware Requirements

- **RAM**: 2 GB sufficient (6 WS connections ~200MB + dashboard build ~500MB peak)
- **CPU**: 1 vCPU fine — WebSocket parsing is not CPU-bound
- **Storage**: 40+ GB needed for logs, CSV, node_modules, dashboard build
- **Bandwidth**: ~0.9 TB/mo estimated (9 exchanges × 60 symbols × ~1KB/update × 1/sec)

## Documentation

Detailed reference documents in `documentations/`:

| File | Contents |
|------|----------|
| `documentations/EXCHANGES.md` | All 9 exchanges: fees, discounts, server locations, latencies, WebSocket details, withdrawal fees per network, geo-restrictions, dropped exchanges |
| `documentations/VPS.md` | VPS deployment strategy: latency matrix (9 exchanges × 5 locations), geo-restriction matrix, 4 VPS options (A-D), inter-VPS communication, orchestrator architecture, phased deployment plan |
| `documentations/BOT_DECISION_MAKING.md` | Complete decision reference: fee computation (scoring vs taker), discovery, scoring, focus tiers, pair selection, threshold, trade sizing, execution, dominant pairs, capital allocation, rebalancing (6 gates), symbol lifecycle, net profit awareness, flow diagrams |

## Technology Stack

- **Language:** Python 3.12+
- **Async:** asyncio + websockets library
- **Dashboard:** React 18 + TypeScript + Vite + Tailwind CSS + react-router-dom (HashRouter) + recharts
- **Data:** CSV snapshots per exchange per symbol (1s intervals)
- **Architecture:** BaseFetcher with exchange-specific subclasses, ArbitrageMonitor reads all fetcher states, SymbolOptimizer handles symbol discovery/rotation/scoring, BalanceTracker simulates capital management
- **Output:** Real-time dashboard + XLSX export + console arbitrage table
