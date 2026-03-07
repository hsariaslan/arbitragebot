# Bot Decision Making

Complete reference for how CoirnaBot makes every trading, scoring, allocation, and rebalancing decision.

---

## Table of Contents

1. [Decision Pipeline Overview](#1-decision-pipeline-overview)
2. [Fee Computation](#2-fee-computation)
3. [Discovery Phase](#3-discovery-phase)
4. [Symbol Scoring](#4-symbol-scoring)
5. [Focus Tiers & Trade Multipliers](#5-focus-tiers--trade-multipliers)
6. [Pair Selection (Which Exchange to Buy/Sell)](#6-pair-selection-which-exchange-to-buysell)
7. [Threshold Check (Should We Trade?)](#7-threshold-check-should-we-trade)
8. [Trade Sizing](#8-trade-sizing)
9. [Trade Execution](#9-trade-execution)
10. [Dominant Exchange Pairs](#10-dominant-exchange-pairs)
11. [Capital Allocation](#11-capital-allocation)
12. [Rebalancing](#12-rebalancing)
13. [Symbol Lifecycle (Demotion, Rotation, Expansion)](#13-symbol-lifecycle-demotion-rotation-expansion)
14. [Net Profit Awareness](#14-net-profit-awareness)
15. [Decision Flow Diagram](#15-decision-flow-diagram)

---

## 1. Decision Pipeline Overview

Every second, the bot runs this pipeline for each active symbol:

```
WebSocket tick arrives (price update)
  │
  ├─ optimizer.run_tick()           ← Score all 60 symbols across all exchanges
  │    ├─ Find best cross-exchange spread per symbol (using scoring_fee)
  │    ├─ Record SymbolTick
  │    ├─ _compute_scores()         ← Rank symbols, assign focus tiers
  │    └─ Periodically: evaluate rotations/demotions/expansions
  │
  └─ monitor._tick()                ← Trade execution for active symbols only
       ├─ Find best exchange pair per symbol (using scoring_fee for selection)
       ├─ Threshold check (scoring_net > 0 AND scoring_net >= min_net_profit_pct)
       ├─ Compute trade size (adaptive: multiplier × tick_factor × balance cap)
       ├─ Balance check (can_execute)
       ├─ Rebalance if needed (miss-streak >= 15)
       └─ Execute trade (using taker_fee for actual profit/cashback)
```

**Key principle**: Two separate fee functions drive different decisions:
- **`get_scoring_fee()`** — for all *selection* decisions (which pair, which symbol, whether to trade)
- **`get_taker_fee()`** — for all *execution* decisions (actual profit, cashback recording, SimulatedTrade)

---

## 2. Fee Computation

### 2.1 Taker Fee (`get_taker_fee`)

The actual fee charged per trade. Used for execution and profit calculation.

```
taker_fee = base_taker_rate × (1 - token_discount_pct)    [if discount enabled]
taker_fee = base_taker_rate                                [if discount disabled]
```

**Special cases:**
- Zero-fee pairs (e.g., Gate.io BTC/USDT) → returns `0.0`
- Real mode → returns API-queried rate instead of config
- Unknown exchange → returns `0.001` (0.10%) as safe fallback

**Where used:** `monitor._tick()` trade execution (lines 833-834), `balance.execute_trade()`, `record_referral_cashback()`, rebalance cost estimation, SimulatedTrade profit.

### 2.2 Scoring Fee (`get_scoring_fee`)

A time-weighted fee that factors in referral cashback for scoring decisions.

```
scoring_fee = taker_fee × (1 - cashback_pct × time_weight)
```

**Time weights** (based on `referral_settlement_minutes`):

| Settlement Time | Weight | Rationale |
|:---------------:|:------:|-----------|
| 0 min (instant) | 1.00 | Immediate fee reduction — effectively cheaper |
| ≤ 120 min (hourly) | 0.75 | Fast capital return, high confidence |
| > 120 min (daily) | 0.50 | Eventual income, discounted for delay |

**Where used:** `optimizer.run_tick()` SymbolTick creation (lines 427-428), `monitor._tick()` pair selection (lines 736-738), threshold check (line 763), trade sizing (line 770).

### 2.3 Effective Fee Table (All 9 Exchanges)

| Exchange | Base Rate | Token Discount | Taker Fee | Cashback | Settlement | Scoring Fee | Reduction |
|----------|:---------:|:--------------:|:---------:|:--------:|:----------:|:-----------:|:---------:|
| Bitfinex | 0.000% | None | 0.000% | Disabled | — | 0.000% | — |
| Pionex | 0.050% | None | 0.050% | 20% | 60 min | 0.0425% | -15% |
| MEXC | 0.050% | None | 0.050% | 20% | 1440 min | 0.045% | -10% |
| Binance | 0.100% | BNB 25% | 0.075% | 20% | 60 min | 0.0638% | -15% |
| Bitget | 0.100% | BGB 20% | 0.080% | 20% | 0 min | 0.0640% | -20% |
| KuCoin | 0.100% | KCS 20% | 0.080% | 20% | 1440 min | 0.072% | -10% |
| Gate.io | 0.100% | GT 10% | 0.090% | 20% | 1440 min | 0.081% | -10% |
| OKX | 0.100% | None | 0.100% | 20% | 90 min | 0.085% | -15% |
| Bybit | 0.100% | None | 0.100% | 20% | 1440 min | 0.090% | -10% |

**Why Bitget ranks well despite higher taker fee than MEXC**: Bitget's instant cashback (0 min) gets 100% time weight, making its scoring fee (0.064%) competitive with Binance (0.0638%). The bot naturally prefers exchanges where cashback arrives faster.

### 2.4 Token Discounts — Fully Calculated

Token discounts are factored into **every** decision. The `effective_taker_rate` property in `ExchangeFeeConfig` applies them:

```
effective_taker_rate = base_taker_rate × (1 - token_discount_pct)    [if discount enabled]
effective_taker_rate = base_taker_rate                                [if discount disabled]
```

Both `get_taker_fee()` and `get_scoring_fee()` use `effective_taker_rate` as their starting point. So if Binance has BNB 25% discount enabled, every scoring decision and every trade execution sees 0.075% instead of 0.10%.

| Exchange | Base Rate | Discount Token | Discount % | Effective Rate |
|----------|:---------:|:--------------:|:----------:|:--------------:|
| Binance | 0.100% | BNB | 25% | 0.075% |
| Bitget | 0.100% | BGB | 20% | 0.080% |
| KuCoin | 0.100% | KCS | 20% | 0.080% |
| Gate.io | 0.100% | GT | 10% | 0.090% |
| OKX | 0.100% | OKB | Disabled (needs 500 OKB ~$25k) | 0.100% |
| Bybit | 0.100% | MNT/BIT | Disabled | 0.100% |
| MEXC | 0.050% | MX | Disabled | 0.050% |
| Pionex | 0.050% | None | — | 0.050% |
| Bitfinex | 0.000% | None | — | 0.000% |

### 2.5 Fee Model — Actively Used in Trade Execution

Fee model controls **where the fee is physically deducted** during `balance.execute_trade()`. This is actively used and affects how balances change per trade.

| Model | Buy Side | Sell Side | Exchanges |
|-------|----------|-----------|-----------|
| `received` | Fee deducted from **received crypto** — you get less coins | Fee deducted from **received USDT** — you get less money | OKX, Bybit, MEXC, Pionex, Bitfinex |
| `token` | **Full crypto** received, fee taken from BNB/BGB/KCS/GT balance separately | **Full USDT** received, fee taken from token balance separately | Binance, Bitget, KuCoin, Gate.io |
| `spent` | Fee **added to USDT cost** — you spend more | Fee charged in **extra crypto** — you sell more | None currently |

#### Concrete Example: Buying $50 of BTC at $100,000 (0.075% fee)

| Model | USDT Spent | BTC Received | Fee Paid From |
|-------|:----------:|:------------:|---------------|
| `received` | $50.00 | 0.000499625 BTC (0.075% less) | Received BTC |
| `token` | $50.00 | 0.000500000 BTC (full amount) | BNB token balance |
| `spent` | $50.0375 (0.075% more) | 0.000500000 BTC (full amount) | Extra USDT |

**Why this matters for simulation accuracy**: The `token` model means you accumulate slightly more crypto per trade (no fee skimming from the received asset). Over hundreds of trades, this compounds — the bot's balance tracker models this correctly per exchange.

#### Implementation in `balance.execute_trade()`

The fee model is passed from `monitor._tick()` via `fee_manager.get_fee_model()`:

```python
# monitor.py (trade execution)
buy_fee_model = self._fee_manager.get_fee_model(buy_ex)   # e.g., "token" for Binance
sell_fee_model = self._fee_manager.get_fee_model(sell_ex)  # e.g., "received" for OKX
trade_adj = self._balance.execute_trade(
    buy_ex, sell_ex, sym, trade_size,
    ask_p, bid_p, buy_fee_rate, sell_fee_rate,
    buy_fee_model=buy_fee_model,
    sell_fee_model=sell_fee_model,
)
```

Inside `execute_trade()`, each side branches on the model:
- **Buy side**: `received` → `coins * (1 - fee)`, `spent` → `usdt * (1 + fee)`, `token` → full coins, full usdt
- **Sell side**: `received` → `usdt * (1 - fee)`, `spent` → `crypto * (1 + fee)`, `token` → full usdt, full crypto
- Quantities are also rounded to exchange lot size (D-01) when exchange rules are available

### 2.6 Fee Mechanism — Stored but NOT Used in Logic

`fee_mechanism` is stored in config and displayed in the dashboard, but **no code anywhere branches on it**:

| Mechanism | Intended Behavior | Exchanges | Used in Decisions? |
|-----------|-------------------|-----------|:------------------:|
| `instant` | Discount applied at trade time | Binance, MEXC, Bitget, Gate.io, Pionex, Bitfinex | No |
| `rebate` | Discount credited back later (KCS) | KuCoin | No |
| `tier` | Volume-based tiers determine rate | OKX, Bybit | No |

The bot treats all mechanisms identically — as an instant rate reduction via `effective_taker_rate`. For KuCoin's `rebate` mechanism (KCS discount credited back, not applied instantly), the simulation doesn't model the delay of that rebate. It applies 20% off immediately.

**Where it exists in code**: Defined in `ExchangeFeeConfig.fee_mechanism` (fee_manager.py:27), serialized to/from settings.json, validated in dashboard settings schema (dashboard_server.py:814). Never read for any decision.

**Practical impact**: Negligible for simulation — KuCoin's KCS rebate settles within seconds on the real exchange. Would only matter in real-money execution where you'd need enough KCS balance to cover fees before the rebate arrives.

### 2.7 Referral Cashback Lifecycle

```
Trade executes
  → record_referral_cashback() computes: cashback_usd = trade_amount × taker_fee × cashback_pct
  → PendingCashback created with expected_credit_at = now + settlement_minutes × 60
  → credit_due_cashbacks() called each tick
  → When now >= expected_credit_at: cashback credited to total, included in net_profit
```

### 2.8 Referrer Commission (Display-Only)

Separate from invitee kickback. Tracks how much the referrer's personal account earns per trade. Configured via `referrer_commission_pct` per exchange.

```
Trade executes
  → record_referrer_commission() computes: commission_usd = trade_amount × taker_fee × referrer_commission_pct
  → Accumulated in _total_referrer_earnings and _referrer_earnings_per_exchange
  → Broadcast to dashboard as fee_stats.referrer_earnings_total
  → NEVER touches: balance, net_profit, scoring_fee, taker_fee, rebalance gates, or any decision
```

**Why display-only**: The referrer commission goes to the user's personal account (not the trading account). The bot has no API access to that account. It's tracked purely for visibility — "how much is my personal account earning from the bot's trades?"

---

## 3. Discovery Phase

On startup, the bot enters discovery mode to scan all 60 symbols across all exchanges before committing capital.

### 3.1 Duration

- Default: configurable (typically 120-300 seconds)
- Extended: if no tradeable symbols found (score ≥ 0.01), duration doubles up to 3600s max
- Early exit: requires `scoring_window / 2` elapsed time AND `scoring_window / 2` total ticks per symbol (default 900s/900 ticks with 1800s window). Prevents inflated scores from thin windows after restart — frequency needs time to normalize

### 3.2 What Happens During Discovery

1. All 60 symbols scored on all active exchanges (no capital needed)
2. SymbolTicks recorded using `get_scoring_fee()` for fee calculation
3. Per-exchange profitability tracked (`_exchange_profit_ticks`, `_exchange_buy_ticks`, `_exchange_sell_ticks`)
4. Scores computed every tick via `_compute_scores()`
5. Debug logging every 30s (exchange data, top 5 spreads) and 60s (score rankings, fee pairs)

### 3.3 Discovery Completion

When discovery ends (`_complete_discovery()`):

1. **Symbol selection**: All symbols with score ≥ `TRADING_SCORE_THRESHOLD` (0.01) are selected, capped at `max_active_symbols`
2. **Dominant pair computation**: For each selected symbol, `_compute_dominant_pairs()` identifies the best buyer/seller exchanges (see Section 10)
3. **Capital allocation**: Score-weighted distribution to dominant exchanges (see Section 11)
4. **Balance reset**: BalanceTracker re-initialized with concentrated allocations
5. **Monitor reset**: ArbitrageMonitor configured with selected symbols and exchanges
6. **Trading starts**: `_discovery_mode = False`, monitor unpaused

---

## 4. Symbol Scoring

Scoring runs every tick in `_compute_scores()` using a rolling window of SymbolTick observations.

### 4.1 Score Formula

```
score = avg_profitable_net × frequency
```

Where:
- `avg_profitable_net` = average `best_net_pct` across only profitable ticks (net > 0)
- `frequency` = profitable_ticks / total_ticks (0.0 to 1.0)
- `best_net_pct` in each tick = `spread_pct - (scoring_fee_buy + scoring_fee_sell) × 100 - slippage_pct - evd_penalty`
- `evd_penalty` = `event_driven_seller_penalty_pct` (default 0.05%) when seller is event-driven (e.g., Bitfinex), 0 otherwise

**Note**: Because scoring uses `get_scoring_fee()`, symbols that trade on exchanges with fast cashback (Bitget instant) will have higher `best_net_pct` in their ticks, leading to higher scores. The EVD penalty in scoring prevents symbols from being inflated during discovery when their best pair involves an event-driven seller whose stale bids make the spread appear wider than reality.

### 4.2 Rolling Window

- Ticks older than `_scoring_window` seconds are pruned each cycle
- Only ticks within the window contribute to scores
- This means scores reflect recent market conditions, not historical averages

### 4.3 Estimated Hourly Profit

```
ticks_per_hour = frequency × 3600
profit_per_tick = (trade_amount × trade_multiplier) × (avg_profitable_net / 100)
est_hourly_profit = ticks_per_hour × profit_per_tick
```

Used for rotation and expansion decisions (see Section 13).

---

## 5. Focus Tiers & Trade Multipliers

After scoring, active symbols are assigned to focus tiers that control trade sizing.

### 5.1 Tier Assignment

```python
raw = symbol_score / mean_active_score

if score >= 0.3:       # very_strong
    multiplier = clamp(raw × 2.0, min=3.0, max=4.0)
elif score >= 0.1:     # strong
    multiplier = clamp(raw × 1.5, min=2.0, max=3.0)
elif score >= 0.01:    # normal
    multiplier = clamp(raw, min=0.5, max=1.5)
else:                  # weak
    multiplier = 0.0   # no trading allowed
```

### 5.2 Tier Summary

| Tier | Score Range | Multiplier Range | Max Exchanges/Direction | Can Trade | Can Rebalance |
|------|:----------:|:----------------:|:-----------------------:|:---------:|:-------------:|
| Very Strong | ≥ 0.30 | 3.0× – 4.0× | 3 (6 total) | Yes | Yes |
| Strong | ≥ 0.10 | 2.0× – 3.0× | 2 (4 total) | Yes | Yes |
| Normal | ≥ 0.01 | 0.5× – 1.5× | 2 (4 total) | Yes | Yes |
| Weak | < 0.01 | 0.0× | — | No | No |

### 5.3 Impact

- **Trade sizing**: `trade_amount × multiplier` determines base trade size
- **Dominant pairs**: More exchanges per direction for higher tiers → better spread capture
- **Capital allocation**: Higher-scoring symbols get proportionally more capital (score-weighted)

---

## 6. Pair Selection (Which Exchange to Buy/Sell)

For each active symbol, every tick, the monitor finds the best exchange pair.

### 6.1 Algorithm (`monitor._tick()`, lines 719-750)

```
For each symbol with ≥ 2 exchanges reporting prices:
    best_scoring_net = -infinity
    best_row = None

    For each pair (buy_exchange, sell_exchange) where buy ≠ sell:
        1. Depth check: skip if ask_depth or bid_depth < min_depth
           min_depth = max($5, total_capital × 0.003) in adaptive mode
           min_depth = trade_amount in static mode

        2. Compute spread:
           spread_pct = (bid_sell - ask_buy) / ask_buy × 100

        3. Compute slippage estimate (from order book depth):
           buy_slip = compute_buy_slippage(asks, trade_amount)
           sell_slip = compute_sell_slippage(bids, trade_amount)
           slippage_pct = buy_slip.slippage_pct + sell_slip.slippage_pct

        4. Compute scoring net (for pair SELECTION):
           scoring_net = spread_pct - (scoring_fee_buy + scoring_fee_sell) × 100 - slippage_pct

        5. Compute taker net (for profit CALCULATION):
           fee_pct = (taker_fee_buy + taker_fee_sell) × 100
           net_pct = spread_pct - fee_pct - slippage_pct
           profit_usd = trade_amount × (net_pct / 100)

        5. Pick best pair by scoring_net:
           if scoring_net > best_scoring_net:
               best_scoring_net = scoring_net
               best_row = (symbol, buy_ex, ask, sell_ex, bid,
                           spread_pct, fee_pct, net_pct, profit_usd)
```

### 6.2 Why Dual Fee Computation Matters

**Scoring fee** determines *which* pair is selected — it accounts for cashback, preferring exchanges like Bitget (instant cashback → lower scoring fee).

**Taker fee** determines *actual profit* stored in `SimulatedTrade` — no cashback subtracted here because cashback is tracked separately via `PendingCashback`.

**Example**: Bitfinex (0% fee) + Binance (0.075% taker, 0.0638% scoring):
- `scoring_net = spread - (0 + 0.0638)%` ← used to decide if this pair wins
- `net_pct = spread - (0 + 0.075)%` ← used for actual profit recording
- The cashback difference (0.075 - 0.0638 = 0.0112%) will arrive as `PendingCashback` after 60 min

This prevents double-counting: profit is recorded conservatively, cashback arrives later.

---

## 7. Threshold Check (Should We Trade?)

After selecting the best pair, two conditions must be met:

```python
if best_scoring_net > 0 and best_scoring_net >= pair_min_net:
    # Proceed to trade sizing
```

### 7.1 Conditions

1. **`best_scoring_net > 0`**: The spread must exceed the combined scoring fees. Even a 0.001% net is tradeable.
2. **`best_scoring_net >= pair_min_net`**: Must meet the minimum net profit percentage configured in settings (`min_net_profit_pct`).

### 7.2 Why Scoring Fee for Threshold

Using `scoring_fee` instead of `taker_fee` for the threshold means the bot activates on more opportunities — it recognizes that some of the fee will come back as cashback. Without this, the bot would skip trades that are actually profitable after cashback.

---

## 8. Trade Sizing

### 8.1 Adaptive Mode (`_compute_trade_size()`)

```python
# 1. Symbol multiplier from optimizer (tier-based)
symbol_mult = sym_score.trade_multiplier  # 0.0 to 4.0

# 2. Net%-based multiplier (scales trade size by current tick's profitability)
#    Enabled via net_pct_sizing_enabled (default true)
#    < 0.03% → 0.5×, 0.03-0.08% → 1.0×, 0.08-0.15% → 1.5×,
#    0.15-0.25% → 2.0×, > 0.25% → 2.5×
#    Capped by net_pct_multiplier_cap (default 2.5)
net_pct_mult = lookup_net_pct_multiplier(net_pct)

# 3. Available balance caps (dynamic buffer: 95% if small position, 80% otherwise)
max_by_usdt = usdt_available × buffer_pct
max_by_crypto = crypto_value × buffer_pct

# 4. Capital-proportional floor
min_trade = max($5, total_capital × 0.003)

# 5. Compute and cap
base = trade_amount × symbol_mult × net_pct_mult
trade_size = min(max_by_usdt, max_by_crypto, base)

# 6. Below minimum → skip (returns 0)
if trade_size < min_trade: return 0.0
```

### 8.2 Exchange Rules Validation (D-02)

If `exchange_info` is available, trade size is validated against:
- **Min notional**: Trade value must meet exchange minimum order value
- **Min quantity**: Quantity must meet exchange minimum lot size
- **Lot size rounding**: Quantities rounded DOWN to exchange `lot_size_step`

### 8.3 Static Mode

When adaptive mode is off: `trade_size = trade_amount` (fixed amount from settings).

---

## 9. Trade Execution

Once trade_size > 0 and balance is sufficient:

### 9.1 Balance Check

```python
has_usdt, has_crypto = balance.can_execute(buy_ex, sell_ex, symbol, trade_size, bid_price)
```

- `has_usdt`: buy_exchange has enough USDT for the trade
- `has_crypto`: sell_exchange has enough crypto (at current price) for the trade

### 9.2 Execute Trade (`balance.execute_trade()`)

```
Buy side:  deduct USDT from buy_exchange, add crypto (minus fee based on fee_model)
Sell side: deduct crypto from sell_exchange, add USDT (minus fee based on fee_model)
```

Uses `get_taker_fee()` and `get_fee_model()` for actual execution — NOT scoring fee.

### 9.3 Referral Cashback Recording

```python
buy_cashback = fee_manager.record_referral_cashback(buy_ex, symbol, trade_size, buy_fee_rate)
sell_cashback = fee_manager.record_referral_cashback(sell_ex, symbol, trade_size, sell_fee_rate)
```

Creates `PendingCashback` entries that will be credited after settlement delay.

### 9.4 Slippage Recomputation at Actual Trade Size

```python
# Recompute slippage with actual trade_size (may differ from initial estimate)
buy_slip = compute_buy_slippage(asks, trade_size)
sell_slip = compute_sell_slippage(bids, trade_size)
actual_slippage = buy_slip.slippage_pct + sell_slip.slippage_pct
net_adjusted = spread - fee - actual_slippage
actual_profit = trade_size × (net_adjusted / 100)
```

### 9.5 SimulatedTrade Record

```python
SimulatedTrade(
    profit_usd = trade_size × (net_adjusted / 100),  # taker + slippage adjusted
    fee_pct = (taker_fee_buy + taker_fee_sell) × 100,
    net_pct = spread_pct - fee_pct - actual_slippage,
    sim_slippage_pct = actual_slippage,
    sim_buy_slippage_pct = buy_slip.slippage_pct,
    sim_sell_slippage_pct = sell_slip.slippage_pct,
    # + rounding metadata, data age, exchange info
)
```

---

## 10. Dominant Exchange Pairs

Instead of spreading capital across all 9 exchanges, the bot concentrates on the 1-3 exchanges where each symbol actually profits.

### 10.1 Detection (`_compute_dominant_pairs()`)

**Input**: Rolling tick data for a symbol (profitable ticks only).

**Algorithm**:

```
1. Accumulate scores per exchange per direction:
   For each profitable tick:
     buy_scores[tick.buy_exchange] += tick.best_net_pct
     sell_scores[tick.sell_exchange] += tick.best_net_pct

2. Fallback (if < 30 profitable ticks):
   Use historical buy_exchange_counts / sell_exchange_counts

3. Select top N per direction:
   - Sort by weight (score / total)
   - Take top max_per_direction exchanges
   - Ignore exchanges with < 2% weight (noise)

4. max_per_direction is tier-based:
   - very_strong (≥ 0.3): 3 per direction (up to 6 exchanges)
   - strong (≥ 0.1): 2 per direction (up to 4 exchanges)
   - normal (≥ 0.01): 2 per direction (up to 4 exchanges)
```

**Output**: `{"buyers": [(ex, weight), ...], "sellers": [(ex, weight), ...], "num_exchanges": N}`

### 10.2 Dynamic Re-evaluation (`_reevaluate_dominant_pairs()`)

Runs every evaluation cycle for active symbols:
- Compares old vs new buyer/seller sets
- If dominant exchanges shifted → `_reallocate_symbol()` moves capital
- `_reallocate_symbol()` returns `bool` — `True` if capital was moved, `False` if skipped (price=0, no change, or cost gate)
- `_dominant_pairs` is only updated when `_reallocate_symbol()` returns `True` — prevents consolidation from reading stale/unmigrated pairs
- Gated by cooldown (3× evaluation_interval) and rotation budget

### 10.3 Why Scoring Fee Cascades Here

Because `optimizer.run_tick()` uses `get_scoring_fee()` when creating SymbolTicks, the `best_net_pct` in each tick already reflects cashback weighting. When `_compute_dominant_pairs()` accumulates `best_net_pct` per exchange, exchanges with fast/large cashback naturally get higher weights → more capital allocated to them.

---

## 11. Capital Allocation

### 11.1 After Discovery

Capital is distributed to dominant exchanges, weighted by symbol score:

```
For each symbol:
    sym_weight = max(min_weight, symbol_score / total_score)
    sym_capital = total_capital × sym_weight

    USDT → buyer exchanges (proportional to buyer weight)
    Crypto → seller exchanges (proportional to seller weight)
    50/50 split between buy side and sell side
```

Where `min_weight = 0.1 / num_symbols` prevents any symbol from getting zero capital.

### 11.2 Balance Model

```
USDT:   per exchange (shared pool, fungible across symbols)
Crypto: per (exchange, symbol) in quantity units
```

Initial crypto quantities set via `initialize_crypto()` using first available prices.

### 11.3 Reallocation on Dominant Pair Shift

When `_reevaluate_dominant_pairs()` detects a change:
1. Sell crypto on old seller exchanges
2. Buy crypto on new seller exchanges
3. Transfer USDT between buyer exchanges if needed
4. Fees charged for each operation

---

## 12. Rebalancing

When a trade can't execute due to insufficient balance, the bot may rebalance.

### 12.1 Trigger: Miss Streak

```
Trade skipped (no balance) → miss_streak[symbol:buy_ex:sell_ex] += 1

if miss_streak >= min_misses_before_rebalance (15):
    Check all gates → if passed, try_rebalance()
    Reset miss_streak to 0
    Retry trade after rebalancing
```

### 12.2 Rebalance Gates (6 layers)

All gates must pass before rebalancing is allowed:

| # | Gate | Check | Location |
|:-:|------|-------|----------|
| 1 | **Tradeable** | `optimizer.should_allow_rebalance(symbol)` requires score ≥ 0.01 | optimizer.py |
| 2 | **ROI** | `est_profit > est_cost × 1.5` where cost = 2× internal transfer fees on 3× trade_amount | monitor.py `_should_rebalance()` |
| 3 | **Net P&L** | After 10+ trades: `trading_pnl + credited_cashback ≥ total_transfer_fees` | monitor.py `_should_rebalance()` |
| 4 | **Miss Streak** | ≥ 15 consecutive missed ticks required | monitor.py `_tick()` |
| 5 | **Transfer Worthiness** | `withdrawal_fee / estimated_profit_per_trade ≤ 50` (external only) | balance.py `_rebalance_usdt()` |
| 6 | **Cooldown** | 60s between rebalances per exchange/direction | balance.py |

### 12.3 Rebalance Amount

```python
# Adaptive mode
target = trade_amount × 3              # enough for ~3 upcoming trades
rebalance_amount = min(target, trade_amount × 4)  # cap at 4×

# Static mode
rebalance_amount = REBALANCE_AMOUNT    # from config
```

### 12.4 Rebalance Priority Order

**Crypto rebalance runs BEFORE USDT rebalance** in `try_rebalance()`.

Reason: The buy exchange accumulates crypto (from buying), while the sell exchange depletes it. By running crypto rebalance first, external crypto transfer (e.g., $0.10 withdrawal) can use accumulated crypto on the buyer before an internal sell would consume it. Saves ~$0.14 per cycle vs reverse order.

### 12.5 USDT Rebalance Options (cheapest wins)

| Option | Cost | When Used |
|--------|------|-----------|
| External USDT transfer | Flat withdrawal fee (e.g., $0.01 BEP20 from Binance) | When cheaper than internal sell |
| Internal sell (sell crypto for USDT) | `rebalance_amount × taker_fee` (percentage) | When cheaper than external transfer |

Selection: `min(external_cost, internal_cost)`.

For external, source exchange is chosen by cheapest withdrawal fee among those with sufficient balance.

### 12.6 Crypto Rebalance Options (cheapest wins)

| Option | Cost | When Used |
|--------|------|-----------|
| External crypto transfer | Flat withdrawal fee on token's native network | When another exchange has excess crypto |
| Internal buy (buy crypto with USDT) | `rebalance_amount × taker_fee` (percentage) | When no external source available |
| External USDT + buy | Withdrawal fee + taker fee | Last resort |

---

## 13. Symbol Lifecycle (Demotion, Rotation, Expansion)

### 13.1 Demotion

Active symbols that underperform are removed.

**Trigger**: Score drops below `TRADING_SCORE_THRESHOLD` (0.01).

**Speed** (tiered):
- Score ≤ demotion_threshold (near-zero): `demotion_period / 4` (very fast)
- Score < 0.005 (half of threshold): `demotion_period / 2` (fast)
- Score < 0.01 (below threshold): `demotion_period` (normal)
- Instant: if `trade_multiplier = 0` and score < 0.01 for 30s+

**What happens**:
- Symbol removed from active set
- All held crypto is **sold immediately** on demotion (internal sell → USDT) to eliminate market exposure risk
- Demotion sell via Bitfinex: crypto transferred to Bitfinex and sold at 0% taker (saves source exchange taker fee). Falls back to local sell for symbols not available on Bitfinex
- Post-demotion: freed USDT redistributed from Bitfinex to starved buyer exchanges of remaining active symbols
- Demotion cooldown prevents immediate re-activation (anti-churning). Cooldown = `demotion_period × demotion_cooldown_multiplier` (default 5.0)
- If ALL symbols demoted → re-enter discovery mode

**No minimum active count protection** — better to be idle than bleed money on transfers for dead symbols.

### 13.2 Rotation

Replace a weak active symbol with a stronger candidate.

**Requirements**:
1. Candidate must be on the **confirmed watchlist** (sustained performance for `confirmation_period`)
2. Candidate score ≥ `TRADING_SCORE_THRESHOLD` (0.01)
3. Candidate score > worst active score × 3 (significant improvement)
4. `hourly_improvement > switching_cost × safety_multiplier`
5. **Pair fee viability gate**: dominant pair's combined taker fees (`buy_fee + sell_fee`) must be < `avg_profitable_net × 0.8`. Same gate as expansion — blocks rotation when pair fees would make every trade negative. Logged as `ROTATE_BLOCKED ... pair_fee_exceeds_net`.
6. Net profit must be positive (`_rotation_budget_ok`)

**Switching cost**:
```
switching_cost = trade_amount × (old_exchange_count + new_exchange_count) × avg_fee_rate × 1.5
```

**Watchlist confirmation**: Symbol must maintain score above threshold for `confirmation_period` seconds. Prevents premature rotations with unstable symbols.

### 13.3 Expansion

Add a new symbol when there's room in the active set.

**Requirements** (less strict than rotation — low risk, just adding):
1. Active symbol count < `max_active_symbols`
2. Score ≥ `TRADING_SCORE_THRESHOLD` (0.01)
3. ≥ 30 total ticks (minimum data)
4. Score stability checks pass (min observation time, no cliff drop, no declining trend)
5. **Cost gate**: `est_hourly_profit × reallocation_cost_horizon > setup_cost`
6. **Pair fee viability gate**: dominant pair's combined taker fees (`buy_fee + sell_fee`) must be < `avg_profitable_net × 0.8`. Blocks expansion when pair fees would consume most of the spread (e.g., 0.17% combined fees on 0.12% avg net → blocked as `pair_fee_exceeds_net`)
7. Net profit must be positive
8. Does NOT require watchlist confirmation (but creates watchlist entry for stability tracking)

**What happens**:
1. Dominant pairs computed for new symbol
2. Crypto bought on dominant seller exchanges using local USDT
3. Symbol added to active set
4. Monitor and balance tracker updated

### 13.4 Lifecycle Diagram

```
All 60 Symbols (scored continuously)
    │
    ├─ score < 0.01 ──→ Weak (no trading, no rebalancing)
    │
    ├─ score ≥ 0.01 ──→ Tradeable
    │   │
    │   ├─ Expansion eligible (under max, enough data, profitable)
    │   │   └─→ Activated (added to active set)
    │   │
    │   └─ Watchlist (score above threshold, tracked for confirmation)
    │       └─ Confirmed (sustained performance)
    │           └─→ Rotation candidate (can replace worst active)
    │
    └─ Active Symbols
        ├─ score ≥ 0.30 → Very Strong (3-4× multiplier, 3 exchanges/dir)
        ├─ score ≥ 0.10 → Strong (2-3× multiplier, 2 exchanges/dir)
        ├─ score ≥ 0.01 → Normal (0.5-1.5× multiplier, 2 exchanges/dir)
        └─ score < 0.01 → Demotion tracking starts
            └─→ Demoted (removed, cooldown, crypto kept)
                └─→ Cooldown expires → eligible for re-activation
```

---

## 14. Net Profit Awareness

The bot tracks whether it's making money overall and adjusts behavior accordingly.

### 14.1 Net Profit Formula

```
net_profit = trading_pnl - transfer_fees + credited_cashback
```

Where:
- `trading_pnl` = sum of all SimulatedTrade.profit_usd
- `transfer_fees` = sum of all Transfer.fee_usd (internal sells + external transfers)
- `credited_cashback` = total referral cashbacks whose settlement time has passed

### 14.2 When Net Profit Is Negative

The following are **blocked**:
- Rotations (replacing symbols)
- Expansions (adding symbols)
- Rebalancing (any transfer, as per gate #3)
- Dominant pair re-evaluation

The following **still run**:
- Demotions (removing dead symbols is always allowed)
- Trading (existing active symbols continue trading)
- Scoring (all 60 symbols continuously scored)

### 14.3 Profit State Updates

`update_profit_state()` is called by the dashboard server every state broadcast. Sets `_rotation_budget_ok` flag in the optimizer based on current net profit.

---

## 15. Decision Flow Diagram

Complete flow for a single tick on a single symbol:

```
Price Update Received
│
├─ Optimizer: Score Update
│   ├─ Get prices from all exchanges for this symbol
│   ├─ For each exchange pair:
│   │   ├─ spread = (bid_sell - ask_buy) / ask_buy
│   │   ├─ fee = scoring_fee(buy) + scoring_fee(sell)    ← SCORING FEE
│   │   └─ net = spread - fee
│   ├─ Record SymbolTick with best net
│   ├─ Recompute score = avg_profitable_net × frequency
│   ├─ Assign focus tier and trade multiplier
│   └─ Periodically: evaluate demotions/rotations/expansions
│
├─ Monitor: Trade Decision
│   ├─ Get prices + depth from all exchanges
│   ├─ For each exchange pair:
│   │   ├─ Check depth ≥ min_depth
│   │   ├─ scoring_net = spread - scoring_fees             ← SCORING FEE (selection)
│   │   ├─ taker_net = spread - taker_fees                 ← TAKER FEE (profit calc)
│   │   └─ Track best by scoring_net
│   │
│   ├─ Threshold: scoring_net > 0 AND ≥ min_net_pct?
│   │   ├─ No → skip (record observation only)
│   │   └─ Yes ↓
│   │
│   ├─ Compute trade_size:
│   │   ├─ base = trade_amount × symbol_mult × tick_factor
│   │   ├─ cap by 80% available USDT / crypto
│   │   ├─ floor = max($5, total_capital × 0.003)
│   │   └─ validate against exchange rules (D-02)
│   │
│   ├─ trade_size = 0? → skip, increment miss_streak
│   │
│   ├─ Balance check: can_execute()?
│   │   ├─ No → increment miss_streak
│   │   │   └─ miss_streak ≥ 15?
│   │   │       ├─ No → skip
│   │   │       └─ Yes → check rebalance gates (6 layers)
│   │   │           ├─ All pass → try_rebalance() → retry trade
│   │   │           └─ Any fail → skip
│   │   └─ Yes ↓
│   │
│   ├─ Execute trade:
│   │   ├─ balance.execute_trade(taker_fee, fee_model)     ← TAKER FEE (execution)
│   │   ├─ Log fee details
│   │   └─ record_referral_cashback(taker_fee)             ← TAKER FEE (cashback)
│   │
│   ├─ Record SimulatedTrade:
│   │   ├─ profit_usd = trade_size × (taker_net / 100)    ← TAKER FEE (profit)
│   │   └─ Include rounding/age metadata
│   │
│   └─ If demo mode: fire-and-forget _execute_demo_trade()
│       ├─ Both legs have executors → execute_arbitrage() (paired + D-11 recovery)
│       └─ One leg has executor → place_market_order() on that leg only
│
├─ Demo setup (one-shot, after initialize_crypto):
│   └─ _run_demo_setup() → execute_setup_orders()
│       ├─ Mirrors sim's virtual crypto allocations with real demo buy orders
│       ├─ Sequential per exchange (rate limit safety)
│       └─ _demo_setup_complete persisted in state
│
└─ Credit due cashbacks (PendingCashback → credited)
```

---

## Key Files Reference

| File | Decision Responsibility |
|------|------------------------|
| `fee_manager.py` | `get_scoring_fee()`, `get_taker_fee()`, `get_fee_model()`, referral cashback tracking, `record_referrer_commission()` (display-only) |
| `monitor.py` | Pair selection (dual fee), threshold check, trade sizing, trade execution, rebalance gates (ROI + net P&L) |
| `optimizer.py` | SymbolTick creation (scoring fee), `_compute_scores()`, focus tiers, dominant pairs, discovery, rotation/demotion/expansion |
| `balance.py` | `execute_trade()`, `can_execute()`, `try_rebalance()`, transfer worthiness, rebalance priority |
| `config.py` | `DEFAULT_FEE_CONFIGS`, thresholds, exchange lists |
| `transfer_fee_manager.py` | Per-exchange per-network withdrawal fees, preferred network selection |
