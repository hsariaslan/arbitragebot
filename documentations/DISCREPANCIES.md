# CoirnaBot — Sim vs Demo/Real Discrepancy Reference

This document catalogs every known way the simulation can diverge from real exchange behavior. Each discrepancy is tracked with its fix status so we can methodically validate the sim before going live.

## Phase 1 Discrepancies (Fixable Without Demo Orders)

### D-01: Lot Size / Quantity Precision

| Field | Value |
|-------|-------|
| **Priority** | CRITICAL |
| **Status** | DONE |
| **Sim assumes** | Any floating-point quantity is valid (e.g., `trade_amount / price = 1.2310748...`) |
| **Reality** | Each symbol on each exchange has a `lot_size_step` (e.g., 0.01). Orders must be multiples of this step. Non-conforming quantities are rejected. |
| **Impact** | Every simulated trade has a slightly wrong quantity. Over hundreds of trades, crypto balances diverge from what a real exchange would hold. |
| **Detection** | Compare `raw_qty` vs `rounded_qty` per trade. Log `rounding_loss_usd`. |
| **Fix** | Fetch `SymbolRules` from exchange REST APIs at startup. Round all quantities in `balance.py:execute_trade()` using `ROUND_DOWN` to `lot_size_step`. Keep unspent USDT in balance. |
| **Files** | `exchange_info.py` (new), `balance.py`, `monitor.py` |
| **How it works** | `execute_trade()` computes raw qty then rounds DOWN via `ExchangeInfoManager.round_quantity()` using `Decimal`. **Buy side**: after rounding, back-calculates actual USDT spent (`rounded_qty / (1 - fee) * price`); the unspent remainder stays in USDT balance. **Sell side**: rounds `coins_to_sell` down; we sell fewer coins and receive proportionally less USDT; the un-sold fraction stays in crypto balance. Both sides properly account for the rounding remainder. Returns an `adjustment` dict with `buy_qty_raw/rounded`, `sell_qty_raw/rounded`, `rounding_impact_usd` for audit. See `balance.py:595-650`. |

### D-02: Min Notional Violation

| Field | Value |
|-------|-------|
| **Priority** | CRITICAL |
| **Status** | DONE |
| **Sim assumes** | Any trade size above `max($5, capital × 0.003)` is valid |
| **Reality** | Each exchange has a `min_notional` per symbol (e.g., Binance $5-$10, OKX $1, Bybit $1). Orders below this are rejected silently or with an error. |
| **Impact** | Sim may execute trades that a real exchange would reject, inflating trade count and PnL. |
| **Detection** | Before each trade, check `trade_size >= min_notional`. Track `notional_skip_count`. |
| **Fix** | In `monitor.py:_compute_trade_size()`, validate against `ExchangeInfoManager.check_min_notional()`. Return 0.0 if below threshold for either exchange. |
| **Files** | `exchange_info.py`, `monitor.py` |
| **How it works** | After computing `trade_size`, converts to `Decimal` and checks both buy and sell sides against exchange `min_notional` (qty × price) and `min_qty` (absolute minimum order quantity). If either side fails, the trade is rejected (returns 0.0). Tracks `_notional_skips` counter; logged in periodic status summary. Uses sell price as proxy for buy price — acceptable since `notional = trade_size / price × price = trade_size` (price-independent for notional check). See `monitor.py:278-328`. |

### D-03: Price Tick Size

| Field | Value |
|-------|-------|
| **Priority** | HIGH |
| **Status** | DONE |
| **Sim assumes** | Any price value from the WebSocket feed is exact and tradeable |
| **Reality** | Exchanges enforce price tick sizes (e.g., 0.01 USDT increments for BTC). Limit orders must conform; market orders fill at the orderbook's actual prices which are already tick-aligned. |
| **Impact** | Minimal for market orders (our primary strategy). Matters for limit orders and precise PnL tracking. |
| **Detection** | Log when WebSocket price doesn't align with tick size. |
| **Fix** | Round prices in spread calculations via `ExchangeInfoManager.round_price()`. |
| **Files** | `exchange_info.py`, `monitor.py` |
| **How it works** | When building `exchange_prices` in `_tick()`, bid and ask are converted to `Decimal` and rounded to the exchange's `tick_size` via `round_price()` (ROUND_DOWN). This corrects float imprecision from WebSocket data (e.g., `81.00000000001` → `81.00`) before spread calculations. No behavioral change for market orders (orderbook prices are already tick-aligned), but ensures PnL tracking uses consistent precision. See `monitor.py:474-486`. |

### D-04: Fee Rate Mismatch

| Field | Value |
|-------|-------|
| **Priority** | CRITICAL |
| **Status** | DONE |
| **Sim assumes** | Static hardcoded fees in `config.py:EXCHANGE_TAKER_FEES` (e.g., Binance 0.075%, OKX 0.10%) |
| **Reality** | Actual fees depend on: VIP tier, whether fee discount token is held and enabled, promotions, maker vs taker execution. Fees can change without notice. |
| **Impact** | If our configured fee is 0.075% but actual is 0.10%, every trade's profit calculation is wrong by 0.025%. Over hundreds of trades, this accumulates. A "profitable" strategy might actually be losing money. |
| **Detection** | At startup, query actual fee rates from exchange APIs. Log WARNING + override if mismatch. New discrepancy type: `fee_rate_mismatch`. |
| **Fix** | `demo_fetcher.py:_validate_fee_rates()` queries demo APIs, compares with config, overrides at runtime. Warn + override behavior. |
| **Files** | `demo_fetcher.py`, `config.py`, `monitor.py` |
| **How it works** | On first successful demo fetch per exchange, queries actual taker fee rates from authenticated APIs. **Binance**: extracts `commissionRates.taker` from the already-fetched `/api/v3/account` response (no extra call). **OKX**: separate call to `/api/v5/account/trade-fee?instType=SPOT&instId=BTC-USDT`. **Bybit**: separate call to `/v5/account/fee-rate?category=spot&symbol=BTCUSDT`. Compares with `config.py:EXCHANGE_TAKER_FEES`; if mismatch, logs WARNING and overrides the dict value in-place so all subsequent profit calculations use the real rate. Records a `fee_rate_mismatch` discrepancy. See `demo_fetcher.py:390-478`. |

### D-05: Fee Currency Mismatch

| Field | Value |
|-------|-------|
| **Priority** | HIGH |
| **Status** | DONE |
| **Sim assumes** | Buy fee deducted from received coins: `coins_after_fee = coins × (1 - fee)`. Sell fee deducted from received USDT: `usdt_received = amount × (1 - fee)`. |
| **Reality** | Varies by exchange and settings: (a) fee from received asset (sim's model), (b) fee from spent asset, (c) fee from discount token (BNB, BGB, KCS). When paying with BNB, you receive full coins but BNB balance decreases — sim doesn't model this at all. |
| **Impact** | Crypto balances drift because the sim's fee deduction point differs from reality. With BNB payment, sim receives fewer coins than reality (sim deducts from coins, exchange deducts from BNB). |
| **Detection** | Phase 2: `_record_demo_comparison()` checks `TradeResult.fee_currency` against expected; logs `[D-05]` warning for unexpected currency. |
| **Fix** | Added `buy_fee_model` / `sell_fee_model` params to `execute_trade()`. Three models: `"received"` (deduct from received), `"spent"` (add to spent), `"token"` (full qty, fee from discount token). Per-exchange config in `EXCHANGE_FEE_MODELS`. |
| **Files** | `balance.py`, `config.py`, `monitor.py` |
| **How it works** | `execute_trade()` now accepts `buy_fee_model` and `sell_fee_model` params (default `"received"` for backward compat). **"received"**: current behavior — fee deducted from received asset. **"spent"**: fee added to spent amount (buy: spend more USDT; sell: full USDT received). **"token"**: full qty received, fee tracked separately from discount token balance. `config.py:EXCHANGE_FEE_MODELS` maps each exchange to its fee model (Binance/Bitget/KuCoin use `"token"`, others use `"received"`). Monitor passes the per-exchange model via `EXCHANGE_FEE_MODELS.get(exchange, "received")`. Demo comparison in `_record_demo_comparison()` detects unexpected fee currencies from `TradeResult`. See `balance.py:595-755`, `config.py:EXCHANGE_FEE_MODELS`. |

### D-06: Rounding Accumulation (Float Precision)

| Field | Value |
|-------|-------|
| **Priority** | MEDIUM |
| **Status** | DONE |
| **Sim assumes** | Python `float` (64-bit IEEE 754 double) is precise enough |
| **Reality** | `0.1 + 0.2 = 0.30000000000000004`. After thousands of trades, accumulated float errors can reach measurable amounts. Exchanges use fixed decimal precision. |
| **Impact** | Small: ~1e-15 per operation, ~0.001 USD over 1000 trades. But can cause `can_execute()` to fail on rounding edge cases (e.g., balance shows $99.99999999 when it should be $100.00). |
| **Detection** | Periodic comparison of sim balances vs exchange-precision-rounded equivalents. |
| **Fix** | Use `Decimal` for intermediate calculations in `execute_trade()` and rebalance methods. Store as `float` (JSON compat) but compute with `Decimal`. |
| **Files** | `balance.py` |
| **How it works** | Addressed as a side effect of D-01. `execute_trade()` now converts quantities to `Decimal(str(...))` for rounding calculations, then stores results as `float`. The `Decimal` intermediate step eliminates float drift during the rounding math. Balances remain `float` for JSON serialization, but the critical qty × price arithmetic uses exact decimal. See `balance.py:599-604`. |

### D-07: Stale Price Data

| Field | Value |
|-------|-------|
| **Priority** | HIGH |
| **Status** | DONE |
| **Sim assumes** | WebSocket prices are live. Skips data older than `MAX_DATA_AGE_SECONDS = 10.0`. |
| **Reality** | WS connections can silently disconnect (no close frame). Price might be 5s stale but within the 10s threshold. A 5s-old price at ~$81 might be $81.50 now — 0.6% difference, larger than most arbitrage spreads. |
| **Impact** | Sim executes trades at stale prices. Real orders would fill at the current (different) price. False positives in arbitrage detection. |
| **Detection** | Track `data_age_ms` at trade time. Log trades where `data_age > 3s`. |
| **Fix** | Add `data_age_ms` to `SimulatedTrade`. Log warning when trading on data >3s old. Consider tighter threshold for high-value trades. |
| **Files** | `monitor.py` |
| **How it works** | In `_tick()`, builds a `symbol_ex_age` dict mapping each exchange to `now - ps.received_at` for the current symbol. When a trade executes, stores `max(buy_age, sell_age) * 1000` as `data_age_ms` in the `SimulatedTrade`. Pure observability metadata — no trade rejection based on age (the existing `MAX_DATA_AGE_SECONDS = 10.0` staleness gate handles that). Enables post-hoc analysis of how stale prices were at trade time. See `monitor.py:435-436, 630-634`. |

## Phase 2 Discrepancies (Require Demo Order Execution)

### D-08: Fill Price Slippage

| Field | Value |
|-------|-------|
| **Priority** | CRITICAL |
| **Status** | DONE |
| **Sim assumes** | Fill at exact ticker bid/ask price |
| **Reality** | Market orders eat into the orderbook. If best ask is $81.00 with 0.5 qty, and you buy 1.0 qty, you fill 0.5 at $81.00 and 0.5 at $81.05 (next level). Average fill: $81.025. |
| **Impact** | Sim overestimates profit. A 0.05% spread with 0.03% slippage per leg leaves only −0.01% net. |
| **Detection** | `_record_demo_comparison()` computes `slippage_pct` per leg from `TradeResult.actual_avg_price` vs sim expected. Logs `[D-08]` when avg slippage > 0.01%. |
| **Fix** | `TradeResult` has `actual_avg_price`, `requested_price`, and computed `slippage_pct` property. `ArbitrageResult.avg_slippage_pct` aggregates both legs. `SimulatedTrade.demo_slippage_pct` tracks per trade. |
| **Files** | `executor.py`, `monitor.py` |
| **How it works** | `TradeResult.slippage_pct` property: `(actual - expected) / expected * 100` when `requested_price > 0`. Each per-exchange executor parses weighted avg fill price from order response (Binance: `fills[]` array, OKX: `avgPx`, Bybit: `avgPrice`). `_record_demo_comparison()` updates `sim_trade.demo_slippage_pct = result.avg_slippage_pct` and logs when significant. See `executor.py:74-78`, `monitor.py:460-464`. |

### D-09: Partial Fills

| Field | Value |
|-------|-------|
| **Priority** | CRITICAL |
| **Status** | DONE |
| **Sim assumes** | 100% fill, always. `coins_bought = trade_amount / price` is fully received. |
| **Reality** | On thin orderbooks, only a fraction fills. You request 1.0 BTC but only get 0.6 BTC. The remainder either expires or sits in the book. |
| **Impact** | Position size mismatch between legs. If buy fills 100% but sell fills 60%, you have 40% unhedged directional exposure. |
| **Detection** | `_record_demo_comparison()` checks `TradeResult.is_partial` (fill_ratio < 0.99). Logs `[D-09]` with requested/filled qty and ratio. |
| **Fix** | `TradeResult` tracks `requested_qty`, `filled_qty`, computed `fill_ratio` and `is_partial` properties. `DemoExecutor` counts partial fills in `_partial_fill_count`. |
| **Files** | `executor.py`, `monitor.py` |
| **How it works** | `TradeResult.fill_ratio` property: `filled_qty / requested_qty`. `is_partial` is True when `0 < fill_ratio < 0.99`. Each executor parses actual filled quantity from exchange response (Binance: sum of `fills[].qty`, OKX: `fillSz`/`accFillSz`, Bybit: `cumExecQty`). `_record_demo_comparison()` logs per-leg partial fill warnings. `SimulatedTrade.demo_buy_qty`/`demo_sell_qty` record actual filled amounts. See `executor.py:80-92`, `monitor.py:467-478`. |

### D-10: Order Rejection

| Field | Value |
|-------|-------|
| **Priority** | CRITICAL |
| **Status** | DONE |
| **Sim assumes** | Orders never fail. If `can_execute()` passes, the trade succeeds. |
| **Reality** | Orders can be rejected for: insufficient balance (rounding), symbol in maintenance/halted, API rate limit exceeded, invalid parameters, exchange downtime. |
| **Impact** | Sim records a trade that never happened. Balances diverge. |
| **Detection** | `_record_demo_comparison()` checks `TradeResult.success`. Logs `[D-10]` with exchange and error reason for each failed leg. |
| **Fix** | Each executor parses exchange-specific error codes. `TradeResult.error` captures rejection reason. `DemoExecutor` counts rejections. Rate limiter pre-checks prevent 429s. |
| **Files** | `executor.py`, `executors/binance_exec.py`, `executors/okx_exec.py`, `executors/bybit_exec.py`, `monitor.py` |
| **How it works** | Each executor wraps order placement in try/except and parses exchange error responses: **Binance**: HTTP status + `msg` field, **OKX**: `sCode` + `sMsg`, **Bybit**: `retCode` + `retMsg`. On failure, creates `TradeResult(success=False, error="...")`. `_record_demo_comparison()` logs per-leg rejections. `DemoExecutor._rejection_count` tracks total. `RateLimiter.acquire()` returns False before submitting if rate would be exceeded. **Instrument skip**: When rejection error contains "instrument"/"doesn't exist"/"not exist" (e.g., OKX DYDX-USDT spot not available on demo), the `exchange:symbol:side` combo is permanently added to `_demo_skip_pairs` in `monitor.py`. Future demo orders for that combo are silently skipped before execution. Counter `_demo_skip_count` logged in `[Session]` summary. Persisted in state, cleared on "Restart Bot". See `executors/*_exec.py` error handling, `monitor.py`. |

### D-11: One-Legged Trades

| Field | Value |
|-------|-------|
| **Priority** | CRITICAL |
| **Status** | DONE |
| **Sim assumes** | Both buy and sell legs always execute simultaneously and successfully |
| **Reality** | Buy fills on Exchange A, sell rejected on Exchange B (or vice versa). Now you have unhedged directional exposure — the most dangerous scenario in arbitrage. |
| **Impact** | Can cause significant losses if the price moves against the open leg. |
| **Detection** | `DemoExecutor.execute_arbitrage()` checks `buy_result.success != sell_result.success`. `_record_demo_comparison()` logs `[D-11]` with severity=error. |
| **Fix** | `DemoExecutor._handle_one_legged()` immediately unwinds the successful leg by placing a reverse order on the same exchange. Recovery result tracked in `ArbitrageResult.recovery_result`. |
| **Files** | `executor.py`, `monitor.py` |
| **How it works** | After `asyncio.gather()` completes both legs, checks for one-legged condition. If buy filled but sell failed: sells the bought crypto on the buy exchange. If sell filled but buy failed: buys back crypto on the sell exchange. Uses a new client order ID with `rcv-` prefix. Recovery failure triggers `MANUAL INTERVENTION NEEDED` error log. `DemoExecutor._one_legged_count` tracks occurrences. `SimulatedTrade.demo_status = "one_legged"` tags the trade. See `executor.py:429-498`, `monitor.py:491-497`. |

### D-12: Execution Latency

| Field | Value |
|-------|-------|
| **Priority** | HIGH |
| **Status** | DONE |
| **Sim assumes** | Both legs execute instantly at the detected price |
| **Reality** | Detection → order submit: 1-10ms. Submit → exchange ack: 10-100ms. Ack → fill: 1-500ms. Total: 50-500ms+. During this time, prices move. |
| **Impact** | The price at fill time differs from detection time. For fast-moving assets, this can flip profitable trades to losses. |
| **Detection** | `_record_demo_comparison()` logs `[D-12]` when `total_latency_ms > 500ms`. Per-leg latency from `TradeResult.latency_ms`. |
| **Fix** | `TradeResult.latency_ms` tracks submit-to-fill per leg. `ArbitrageResult.total_latency_ms` tracks end-to-end. `SimulatedTrade.demo_latency_ms` exposed in dashboard/XLSX. |
| **Files** | `executor.py`, `monitor.py` |
| **How it works** | Each executor measures `(time.time() - t0) * 1000` from order submit to response/fill query completion. For OKX/Bybit which need a follow-up fill query, latency includes the query retry wait. `DemoExecutor.execute_arbitrage()` measures total `(time.time() - t0) * 1000` for both legs in parallel. `_record_demo_comparison()` stores in `sim_trade.demo_latency_ms` and logs high-latency warnings. Dashboard and XLSX show latency per trade. See `executor.py:315,358`, `monitor.py:501-505`. |

### D-13: Maker vs Taker Fee

| Field | Value |
|-------|-------|
| **Priority** | MEDIUM |
| **Status** | DONE |
| **Sim assumes** | Always taker fee (market orders) |
| **Reality** | If a limit order is used and the orderbook moves, the order might fill as maker (lower fee). Or, if the price moves away, the limit order doesn't fill at all. |
| **Impact** | Minor if we only use market orders. Significant if we add limit order support (maker fees are 2-10x lower). |
| **Detection** | `_record_demo_comparison()` checks `TradeResult.is_maker`. Logs `[D-13]` when a market order unexpectedly fills as maker. |
| **Fix** | `TradeResult.is_maker` boolean parsed from fill response. `TradeResult.fee_rate` computed from actual fee/value. |
| **Files** | `executor.py`, `monitor.py` |
| **How it works** | Each executor parses maker/taker status from fill response where available (Binance: `isMaker` in fills, OKX: `execType`, Bybit: defaults to `False` for market orders). `_record_demo_comparison()` logs info when `is_maker` is True (unexpected for market orders). Currently all executors use `orderType=Market`, so maker fills should be rare. `TradeResult.fee_rate` provides actual fee percentage for comparison with configured rates. See `executor.py:60-63`, `monitor.py:508-511`. |

### D-14: Rate Limit Throttling

| Field | Value |
|-------|-------|
| **Priority** | HIGH |
| **Status** | DONE |
| **Sim assumes** | Unlimited order rate. No API constraints. |
| **Reality** | Binance: 1200 weight/min, each order ~1 weight. OKX: 60 orders/2s. Bybit: 20 orders/s. Exceeding limits → 429 response, temp ban (minutes to hours). |
| **Impact** | Orders rejected when rate limited. Missed opportunities. If banning occurs, ALL trading stops for that exchange. |
| **Detection** | `RateLimiter.acquire()` returns False when rate would be exceeded. Logs `rate_limited` in `TradeResult.error`. `RateLimiter.blocked_count` tracks total blocks. |
| **Fix** | `RateLimiter` class with per-exchange sliding window. Each executor has its own limiter with exchange-specific limits. Pre-checks before order submission. |
| **Files** | `executor.py`, `executors/binance_exec.py`, `executors/okx_exec.py`, `executors/bybit_exec.py` |
| **How it works** | `RateLimiter(max_requests, window_seconds)` uses a `deque` of timestamps. `acquire()` evicts expired entries, returns False if at capacity (increments `blocked_count`), otherwise appends current time. Per-exchange limits: **Binance**: 100/60s (conservative vs 1200 weight/min), **OKX**: 50/2s, **Bybit**: 15/1s. Each `place_market_order()` calls `acquire()` first; if blocked, returns `_failed_result(error="rate_limited")`. See `executor.py:108-146`. |

### D-15: Self-Trade Prevention

| Field | Value |
|-------|-------|
| **Priority** | LOW |
| **Status** | N/A |
| **Sim assumes** | Any trade between exchanges is valid |
| **Reality** | Some exchanges prevent trading against your own open orders on the same book. Unlikely with market orders on different exchanges, but possible if we add same-exchange strategies. |
| **Impact** | Minimal for cross-exchange arbitrage. Only relevant for same-exchange strategies. |
| **Detection** | Monitor for self-trade rejection error codes. |
| **Fix** | N/A for cross-exchange arbitrage — we never trade on the same orderbook. Both buy and sell legs are always on different exchanges. Would only matter if adding same-exchange strategies (use different sub-accounts). |

### D-16: Withdrawal Fee Changes

| Field | Value |
|-------|-------|
| **Priority** | HIGH |
| **Status** | DONE (Phase 1: validate at startup for OKX/Bitget/KuCoin) |
| **Sim assumes** | Static fees in `config.py:USDT_WITHDRAWAL_FEES` (e.g., KuCoin $0.80, Binance $0.01) |
| **Reality** | Exchanges change withdrawal fees without notice. Network congestion can temporarily increase fees. Promotional zero-fee periods end. |
| **Impact** | Transfer cost calculations wrong. A "profitable" rebalance might cost more than expected. |
| **Detection** | Query actual withdrawal fees from exchange APIs at startup. Compare with config. |
| **Fix** | Phase 1: fetch and compare at startup. Phase 2: check before each real transfer. |
| **How it works** | `ExchangeInfoManager.validate_withdrawal_fees()` runs at startup after `fetch_all()`. Queries public (no-auth) APIs: **OKX** (`/api/v5/asset/currencies?ccy=USDT`), **Bitget** (`/api/v2/spot/public/coins?coin=USDT`), **KuCoin** (`/api/v1/currencies/USDT`). For each, iterates all chains to find the cheapest withdrawable network fee. Compares with `config.py:USDT_WITHDRAWAL_FEES`; if mismatch, logs WARNING and overrides in-place. Binance and Bybit skipped (their withdrawal fee endpoints require authentication — validated via `demo_fetcher` if keys are available). See `exchange_info.py:544-716`, wired in `run.py`. |

### D-17: Network/Transfer Delays

| Field | Value |
|-------|-------|
| **Priority** | HIGH |
| **Status** | DONE |
| **Sim assumes** | Rebalancing transfers are instant. Capital is immediately available after transfer. |
| **Reality** | BEP20: ~3s + exchange processing (~1-30min). Arbitrum: ~0.3s + processing. Some chains: hours. During this time, the transferred capital is unavailable. |
| **Impact** | Sim trades with capital that hasn't arrived yet. Overestimates available balance on receiving exchange. |
| **Detection** | `InTransitFund` dataclass tracks each in-transit transfer with `sent_at` and `eta`. `deliver_in_transit()` checks and credits arrived funds. |
| **Fix** | In demo mode, external USDT transfers go through `_in_transit` list. Funds deducted from source immediately but credited to destination only after estimated network transit time. Simulation mode keeps instant transfers (backward compat). |
| **Files** | `balance.py`, `monitor.py`, `run.py` |
| **How it works** | `InTransitFund` dataclass: `amount`, `asset`, `sent_at`, `eta`, `from_exchange`, `to_exchange`. When `_execution_mode == "demo"`, `_rebalance_usdt()` adds an `InTransitFund` instead of instant credit, with `eta = now + _NETWORK_DELAYS["BEP20"]` (30s). `deliver_in_transit()` is called every tick in `_tick()`: iterates `_in_transit`, credits arrived funds to destination balance, removes from list. `in_transit_total(exchange, asset)` queries pending amounts. State persisted via `to_state_dict()`/`from_state_dict()`. In simulation mode: unchanged instant transfer behavior. See `balance.py:213-260`, `monitor.py:612-614`. |

### D-18: Balance Sync Timing

| Field | Value |
|-------|-------|
| **Priority** | MEDIUM |
| **Status** | DONE |
| **Sim assumes** | Balance updates are instant and atomic. `execute_trade()` immediately mutates `BalanceTracker`. |
| **Reality** | Demo balance API is polled every 15s. A trade that fills at T=0 won't show in the next poll at T=7 if exchange processing takes >7s. This creates temporary "false discrepancies". |
| **Impact** | Noisy discrepancy logs from timing mismatches, not real errors. |
| **Detection** | Correlate discrepancies with recent trades. If a trade executed <15s ago, flag as `recent_trade_settling`. |
| **Fix** | After each demo trade, add a grace period (skip comparison for 15-30s per exchange). Track `last_trade_time` per exchange. |
| **How it works** | Two parts. **BalanceTracker** (`balance.py:636-639`): `execute_trade()` records `last_trade_time[exchange] = time.time()` for both buy and sell exchanges. Persisted in state dict, survives restarts. **DemoPortfolioFetcher** (`demo_fetcher.py:522-525`): at the top of `_detect_discrepancies()`, checks if `now - last_trade_time[exchange] < 30s`. If settling: discrepancy type gets a `_settling` suffix (e.g., `balance_mismatch_settling`) and root cause is prefixed with `[Settling Xs ago]`. This preserves the discrepancy in logs for audit but clearly tags it as timing noise rather than a real divergence. |

### D-19: Missing Position (Sim-Only Trades)

| Field | Value |
|-------|-------|
| **Priority** | INFO (Phase 1), CRITICAL (Phase 2) |
| **Status** | DONE |
| **Sim assumes** | N/A — this is the discrepancy itself |
| **Reality** | In Phase 1 (simulation mode), the sim holds crypto positions but no demo orders are placed. `demo_delta = 0` for all crypto. Every simulated trade creates this discrepancy. |
| **Impact** | Phase 1: Expected, informational. Phase 2: If this occurs, it means the demo executor failed to place an order that the sim thought it did — critical desync. |
| **Detection** | Phase 1: existing `missing_position` type in `demo_fetcher.py`. Phase 2: `DemoExecutor.reconcile_balances()` queries exchange balances at startup and compares with `BalanceTracker`. |
| **Fix** | Startup reconciliation detects sim-tracker positions with no exchange-side equivalent. Logs WARNING with sim/actual values and diff. |
| **Files** | `executor.py`, `demo_fetcher.py`, `run.py` |
| **How it works** | `DemoExecutor.reconcile_balances(balance_tracker)` runs at startup when `execution_mode=demo`. For each exchange executor: queries USDT balance and crypto positions via `get_balance()`. Compares with `BalanceTracker.usdt` and `BalanceTracker.crypto`. USDT diff threshold: $1. Crypto diff threshold: 1%. Logs per-asset discrepancies. Returns dict of all mismatches. Called in `run.py` after state restore and executor creation. Also recovers pending orders from pre-crash state via `recover_pending_orders()`. See `executor.py:500-567`, `run.py:239-248`. |

### D-20: Extra Position (Demo-Only Trades)

| Field | Value |
|-------|-------|
| **Priority** | CRITICAL (if detected) |
| **Status** | DONE |
| **Sim assumes** | N/A — this is the discrepancy itself |
| **Reality** | Demo exchange holds a crypto position that the sim doesn't know about. Could happen from: manual demo trades, duplicate order execution, exchange-side fill that sim missed (crash before save). |
| **Impact** | Unknown exposure. Capital is allocated to a position the bot doesn't track. |
| **Detection** | Existing `extra_position` type in `demo_fetcher.py`. `reconcile_balances()` also detects positive exchange balances not in sim. |
| **Fix** | Startup reconciliation logs discrepancy for manual review. Pending order recovery (`recover_pending_orders()`) checks if crashed orders filled on exchange, preventing missed state updates. |
| **Files** | `executor.py`, `demo_fetcher.py`, `run.py` |
| **How it works** | Same reconciliation system as D-19. `recover_pending_orders()` queries exchange for any pending client order IDs from pre-crash state. If orders filled on exchange but weren't saved to state, the recovery detects and logs them. Full position reconciliation enables manual correction. Idempotent client order IDs (`coirna-{base}-{side}-{ts}-{uuid6}`) ensure orders can be uniquely identified post-crash. See `executor.py:569-604`. |

## Summary Table

| ID | Name | Priority | Phase | Status |
|----|------|----------|-------|--------|
| D-01 | Lot Size / Quantity Precision | CRITICAL | 1 | DONE |
| D-02 | Min Notional Violation | CRITICAL | 1 | DONE |
| D-03 | Price Tick Size | HIGH | 1 | DONE |
| D-04 | Fee Rate Mismatch | CRITICAL | 1 | DONE |
| D-05 | Fee Currency Mismatch | HIGH | 2 | DONE |
| D-06 | Rounding Accumulation | MEDIUM | 1 | DONE |
| D-07 | Stale Price Data | HIGH | 1 | DONE |
| D-08 | Fill Price Slippage | CRITICAL | 2 | DONE |
| D-09 | Partial Fills | CRITICAL | 2 | DONE |
| D-10 | Order Rejection | CRITICAL | 2 | DONE |
| D-11 | One-Legged Trades | CRITICAL | 2 | DONE |
| D-12 | Execution Latency | HIGH | 2 | DONE |
| D-13 | Maker vs Taker Fee | MEDIUM | 2 | DONE |
| D-14 | Rate Limit Throttling | HIGH | 2 | DONE |
| D-15 | Self-Trade Prevention | LOW | — | N/A |
| D-16 | Withdrawal Fee Changes | HIGH | 1+2 | DONE (Phase 1) |
| D-17 | Network/Transfer Delays | HIGH | 2 | DONE |
| D-18 | Balance Sync Timing | MEDIUM | 1 | DONE |
| D-19 | Missing Position | INFO/CRIT | 2 | DONE |
| D-20 | Extra Position | CRITICAL | 2 | DONE |
