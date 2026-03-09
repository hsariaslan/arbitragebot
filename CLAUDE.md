# CoirnaBot - Cross-Exchange Crypto Arbitrage Bot

## Project Start Date
2026-02-22

## Instructions
- Never run `git checkout` or `git commit` commands without my confirmation.
- Always use `read_xlsx.py` when reading a xlsx output file.
- Check the latest log file under `logs` folder.
- **IMPORTANT**: `settings.json` on local machine differs from VPS. The VPS has its own runtime settings (e.g., `hourly_external_transfer_cap=$5` on VPS vs `$2` default locally). When analyzing logs, trust the `[Settings]` log entries for actual runtime values, not the local `settings.json` file.

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
| 5 | **MEXC** | 0.04% | MX Deduction (20% off 0.05%) | Post-connect JSON | 60/60 |
| 6 | **Bitget** | 0.08% | BGB (20% off) | Post-connect JSON | 60/60 |
| 7 | **KuCoin** | 0.08% | KCS (20% off) | REST token + WS | 60/60 |
| 8 | **Gate.io** | 0.09% | GT (10% off, enabled) | Post-connect JSON | 60/60 |
| 9 | **Pionex** | 0.05% | None (VIP tiers only, volume-gated) | Post-connect JSON | 60/60 |

**MEXC note:** Accessible from Bangkok VPS. 0.04% effective taker fee with MX Deduction (20% off 0.05% base). Enable "Use MX for Fees" — requires small MX balance. The 500 MX holding discount (50% off) was suspended Feb 9, 2026. Uses protobuf binary WS messages. 30 sub limit per connection — uses 2 connections for 60 symbols.
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
- **MEXC (0.04% with MX)/Pionex (0.05% taker)** and **Binance/Bybit (0.075% with token discount)** are the most cost-effective pairs

### How to Claim Fee Discounts

| Exchange | What to Do | Discount |
|----------|-----------|----------|
| **Binance** | Buy BNB, enable "Pay fees with BNB" in Settings > Fee | 25% off (0.10% → 0.075%) |
| **Bybit** | Hold MNT or BIT tokens on Bybit | 25% off (0.10% → 0.075%) |
| **Bitget** | Buy BGB, enable "Pay fees with BGB" | 20% off (0.10% → 0.08%) |
| **KuCoin** | Buy KCS, enable "Pay fees with KCS" | 20% off (0.10% → 0.08%) |
| **OKX** | Hold 500+ OKB (~$25k investment) | Tiered discount (not practical at start) |
| **MEXC** | Enable "Use MX for Fees", hold small MX balance | 20% off (0.05% → 0.04%) |
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
| Order book depth | @depth5@100ms | books5 channel | orderbook.1 | N/A (REST) | books5 channel | level5 topic | spot.order_book_update | — | Array book channel |
| Special | — | — | Delta merging | 30 sub limit, protobuf | — | REST token first | Per-symbol subscribe | DEPTH+TRADE topics | Array data, 30 sub limit, 2 connections |

## Order Book Depth & Slippage Simulation

All 9 exchange fetchers subscribe to multi-level order book data (up to 5 levels) alongside ticker data. `PriceState` stores `bids` (descending) and `asks` (ascending) as `list[tuple[str, str]]`.

### How It Works

1. **Fetchers** populate `PriceState.bids`/`PriceState.asks` from exchange-specific depth channels (see WebSocket table above)
2. **`slippage.py`** walks the order book to compute volume-weighted average fill price for a given trade size
3. **Scoring** (`optimizer.py:_score_tick()`) deducts estimated slippage from `net_pct` — symbols with thin books score lower
4. **Execution** (`monitor.py:_tick()`) recomputes slippage with actual `trade_size` (after adaptive sizing), deducts from profit
5. **Trade log** includes `sim_slippage_pct`, `sim_buy_slippage_pct`, `sim_sell_slippage_pct` fields

### Key Functions

| Function | File | Purpose |
|----------|------|---------|
| `compute_buy_slippage(asks, trade_size_usd)` | `slippage.py` | Walk ask book upward, return `SlippageResult` |
| `compute_sell_slippage(bids, trade_size_usd)` | `slippage.py` | Walk bid book downward, return `SlippageResult` |

`SlippageResult` fields: `effective_price`, `slippage_pct`, `levels_consumed`, `total_depth_usd`, `sufficient_depth`.

### Exchange-Specific Depth Sources

| Exchange | Channel | Levels | Update Rate | Notes |
|----------|---------|--------|-------------|-------|
| Binance | `@depth5@100ms` | 5 | 100ms | Snapshot per push |
| OKX | `books5` | 5 | ~100ms | Snapshot per push |
| Bybit | `orderbook.50` | 50 (top 5 used) | 20ms | Valid depths: 1, 50, 200, 1000 |
| MEXC | REST `/api/v3/depth?limit=5` | 5 | 3s poll | No WS depth available, uses async REST polling |
| Bitget | `books5` | 5 | ~100ms | Snapshot per push |
| KuCoin | `/spotMarket/level5` | 5 | ~100ms | Uses WS token auth |
| Gate.io | `spot.order_book_update` | 5 | 100ms | Requires snapshot + delta merging |
| Pionex | DEPTH topic (limit=5) | 5 | ~100ms | Multi-level bids/asks from DEPTH subscription |
| Bitfinex | Book channel (array) | 5 | ~100ms | Sorted in-memory, `_BitfinexBookSubFetcher` |

## WebSocket Proxy (Zurich VPS)

Transparent WebSocket proxy on Oracle Cloud free-tier VPS in Zurich for low-latency Bitfinex data. Bitfinex servers are in Zug, Switzerland (~0.7ms from Zurich vs ~1,200ms from Bangkok).

### Architecture

```
Bangkok (BitfinexFetcher)  ──200ms──>  Zurich (ws_proxy)  ──0.7ms──>  Bitfinex
                           <──200ms──                     <──0.7ms──
Total: ~201ms (vs 1,200ms direct)
```

### Configuration

- `BITFINEX_WS_URL` in `config.py` — env-overridable, defaults to direct Bitfinex URL
- Bangkok `.env`: `BITFINEX_WS_URL=ws://<ZURICH_IP>:9000`
- Proxy is stateless — forwards raw WS frames bidirectionally, no message parsing
- `ping_interval=None` on both sides — Bitfinex uses application-level JSON pings

### Key Files

| File | Purpose |
|------|---------|
| `proxy/ws_proxy.py` | Generic WebSocket proxy (~110 lines), reusable for any exchange |
| `proxy/requirements.txt` | `websockets>=13.0` |
| `scripts/ws-proxy.service` | systemd service for Zurich VPS |

### Security

- Oracle Cloud Security List restricts port 9000 to Bangkok VPS IP only
- No TLS on proxy link (IP-restricted); Zurich→Bitfinex remains `wss://`
- Fallback: revert `BITFINEX_WS_URL` in `.env` to direct URL and restart
- **Monitoring**: Bangkok tracks proxy health via Bitfinex fetcher connection state. See "Proxy (Zurich VPS) Monitoring" section under Dashboard.

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

- **Discovery**: Activates symbols with score ≥ 0.01. Extends discovery duration (up to 3600s) if none qualify. At activation, symbols are filtered by two checks: (1) **recent frequency gate** — recent ticks must have ≥5% profitable frequency (rejects transient spikes that already closed). Uses adaptive window: **60s** for symbols involving event-driven exchanges (Bitfinex updates every 10-20s, so a short window misses update cycles) and **15s** for streaming exchanges. Detects event-driven involvement by checking the last 30 profitable ticks for exchange membership. (2) **score trajectory** — last 5 scores all declining with >10% drop OR cliff drop (current < peak × `score_stability_factor`). Candidates are tracked in watchlist from first tick for trend analysis. **Note**: The `pair_fee_exceeds_net` gate is intentionally NOT applied in discovery — discovery has zero switching cost, and being idle is always worse than trading on a marginal pair. The demotion system handles bad symbols within 15-30 min. The gate remains active for expansion/rotation where switching has a cost.
- **Early discovery exit**: Requires `scoring_window / 2` elapsed time AND `scoring_window / 2` total ticks per symbol before trusting scores (default: 900s/900 ticks with 1800s window). Prevents inflated scores from thin windows after restart — frequency needs time to normalize (e.g., 100% from 60 ticks vs real 55% from 900 ticks).
- **Trading**: Normal tier (0.01–0.1) gets `trade_multiplier = 0.5–1.5×`. Weak symbols (< 0.01) get `trade_multiplier = 0`, **except active symbols** which get a 1.0× floor — score threshold controls activation/demotion, not execution for already-deployed capital.
- **Rebalancing**: `should_allow_rebalance()` requires score ≥ 0.01 (`TRADING_SCORE_THRESHOLD`). ROI gate, net P&L gate, and transfer worthiness checks protect against unprofitable transfers.
- **Expansion/Rotation**: Only strong/very_strong candidates can be activated or replace existing symbols. Both expansion and rotation share a **pair fee viability gate** — computes dominant pair's combined taker fees (`buy_fee + sell_fee`) and blocks if `combined_fee > avg_profitable_net × 0.8` (pair fees would consume most of the spread). Expansion logs as `EXPAND_BLOCKED ... pair_fee_exceeds_net`, rotation logs as `ROTATE_BLOCKED ... pair_fee_exceeds_net`. Expansion additionally has a **cost gate** — `_estimate_expansion_cost()` computes the total setup fee and blocks if cost > `est_hourly_profit × reallocation_cost_horizon` (`EXPAND_BLOCKED` log). **Bitfinex-available symbols are preferred**: non-Bitfinex candidates receive a 0.7× score penalty in expansion ranking (deprioritized, not blocked). `_is_symbol_on_bitfinex()` checks live price data. `bfx=yes/no` logged in EXPAND_READY.
- **Faster activation**: Watchlist confirmation period is score-dependent: very strong (≥0.3) confirmed in `confirmation_period × 0.1` (30s default), strong (≥0.1) in `× 0.4` (120s), normal in full period (300s). Strong candidates shouldn't sit idle. All candidates must also pass **score stability checks** before confirmation (see below).
- **Score stability**: Before confirmation or expansion, candidates must pass three checks: (1) minimum observation time (`score_stability_seconds`, default 120s), (2) cliff drop detection — reject if current score < `peak_score × score_stability_factor` (default 0.5), (3) declining trend — reject if last 3 consecutive samples are all decreasing. `WatchlistEntry` tracks `peak_score` and `score_samples` for trend analysis. Expansion candidates that bypass watchlist now create a watchlist entry on first sight and must pass stability checks before activation. Both settings configurable via dashboard Settings and hot-applied.
- **Demotion**: Symbols dropping below 0.1 are demoted on a tiered schedule (faster for weaker scores). All held crypto is **sold immediately** on demotion (internal sell → USDT) to eliminate market exposure risk. Cooldown = `demotion_period × demotion_cooldown_multiplier` (default 5.0 = 3000s/50 min). No minimum active count protection — better idle than bleeding money on transfers. **Post-demotion redistribution**: `_redistribute_post_demotion()` immediately pushes freed USDT from Bitfinex to starved buyer exchanges of remaining active symbols. Targets exchanges below `trade_amount × 2`, sends up to `trade_amount × 3` per exchange, keeps 20% buffer on Bitfinex. Uses $0-fee Bitfinex transfers (bypass hourly cap via zero-fee exemption).
- **Fee-aware activation threshold**: `_get_activation_threshold(symbol)` computes a per-symbol minimum score that scales with the dominant pair's combined taker fees. Cheap pairs (Bitfinex involved, ~0.04% combined) get the base threshold. Expensive pairs (no Bitfinex, ~0.14%+) need proportionally higher scores. Formula: `threshold = base + (pair_fee - cheapest_fee) × fee_threshold_multiplier + demotion_penalty`. With `fee_threshold_multiplier=0.5` and base=0.05: Bitfinex+MEXC=0.05, MEXC+OKX=0.10, Binance+OKX=0.12. Demotion penalty adds 50% of base per demotion. Capped at `strong_threshold`. Configurable via `fee_threshold_multiplier` in dashboard Settings (0=disabled, higher=stricter for expensive pairs).

### Focus Tiers & Trade Multipliers

| Tier | Score | Trade Multiplier | Exchange Count |
|------|-------|-----------------|----------------|
| Very Strong | ≥ 0.3 | 3.0×–4.0× | Up to 3 per direction (6 max) |
| Strong | ≥ 0.1 | 2.0×–3.0× | Up to 2 per direction (4 max) |
| Normal | 0.01–0.1 | 0.5×–1.5× | Up to 2 per direction (4 max) |
| Weak (active) | < 0.01 | 1.0× (floor) | Keeps trading until demoted |
| Weak (inactive) | < 0.01 | 0× (no trading) | — |

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
- **Seller withdrawal-fee penalty**: Seller exchanges with withdrawal fee > $0.05 get weight reduced by up to 50%. Prevents USDT accumulation on expensive-withdrawal exchanges (e.g., OKX $0.10, Gate.io $0.50, KuCoin $0.40).
- Selects top N exchanges per direction (buy/sell), ignoring < 2% weight
- `max_per_direction` is tier-based: 2 for default/strong, 3 for very_strong
- Falls back to historical `buy_exchange_counts` / `sell_exchange_counts` if insufficient rolling data

### Capital Allocation

After discovery, capital is allocated per-symbol to dominant exchanges:
- **Bitfinex reserve carved out first**: `total_capital × bitfinex_reserve_pct` (default 15%) kept as USDT on Bitfinex before symbol allocation
- Remaining capital: USDT → buyer exchanges (proportional to buyer weight)
- Crypto → seller exchanges (proportional to seller weight)
- **Dynamic buy/sell ratio** per symbol based on exchange concentration: the side with fewer exchanges gets proportionally more capital to delay per-exchange depletion (e.g., 2 buyers + 1 seller → 35%/65% buy/sell). Clamped to [35%, 65%]. Equal exchange counts stay at 50/50.
- Score-weighted across symbols: higher-scoring symbols get more capital

### Dynamic Re-evaluation

`_reevaluate_dominant_pairs()` runs every evaluation cycle for active symbols. If dominant exchanges shift (buyer or seller changed), capital is reallocated via `_reallocate_symbol()`. Gated by rotation budget and cooldown (3× evaluation_interval). `_reallocate_symbol()` returns `bool` — `True` if capital was actually moved, `False` if skipped (price=0, no change, or cost gate). `_dominant_pairs` is only updated when `_reallocate_symbol()` returns `True`, preventing consolidation from reading stale pairs. Has a **cost estimation gate**: estimates sell+buy taker fees and compares against `est_hourly_profit × reallocation_cost_horizon` (default 2h). Skips if cost exceeds benefit.

### Dashboard Display

The "Exchanges" column in Symbol Rankings shows dominant pairs as `BIN→KUC` (buyer→seller). The Buy-Sell Distribution sheet in XLSX shows per-exchange tick counts.

## Bitfinex Capital Hub

Bitfinex has $0 withdrawal fees on 14/15 networks and 0% taker fees, making it the ideal capital hub. The system prevents "death spirals" where the net P&L gate blocks rebalancing, capital gets stuck on wrong exchanges, and trading stalls.

### Configuration

- `BITFINEX_RESERVE_PCT` (default 0.15 = 15%) in `config.py`, configurable via Settings
- `BITFINEX_RESERVE_HARD_FLOOR` (default 0.05 = 5%) — emergency draws cannot drain below this. For $3000 capital: hard floor = $150.
- Reserve target = `total_capital × reserve_pct` (e.g., $270 for $1800 capital)

### How It Works

1. **Carve-out at discovery**: Before allocating capital to symbols, `reserve_amount` is set aside as USDT on Bitfinex
2. **Protection during rebalancing**: Normal rebalance source selection uses `_available_usdt_for_rebalance()` which excludes the reserve from Bitfinex's available balance
3. **Protection during trading**: `available_usdt_for_trading()` prevents trades from spending Bitfinex USDT below the reserve target. Used in both `_compute_trade_size()` and `can_execute()`. Without this, Bitfinex as a buyer exchange drains the reserve through normal trading, triggering expensive replenishment cycles.
4. **Emergency draw**: When net P&L gate blocks rebalancing AND miss streak ≥ 2× threshold, `emergency_reserve_draw()` transfers USDT from Bitfinex to the starved exchange — **bypasses all gates** (net P&L, hourly cap, transfer worthiness). Fee = $0. Hard floor enforced: draw cannot reduce Bitfinex below `total_capital × hard_floor`.
5. **Periodic replenishment**: Every evaluation cycle, `replenish_reserve()` tops up from ALL exchanges sorted by withdrawal fee (cheapest first). Not gated by net profit — reserve replenishment is always beneficial. Minimum transfer `max($20, trade_amount × 2)`. 10-minute cooldown per source. Respects hourly budget.
6. **USDT consolidation**: `consolidate_to_bitfinex()` moves idle capital to Bitfinex hub. Active buyer exchanges keep a buffer unless idle for 30+ minutes (based on `last_trade_time`, updated by both trades and rebalance operations). Non-active exchanges are fully consolidated. Runs during eval cycles and discovery. **Bitfinex availability gate**: Post-discovery consolidation is skipped when no active symbol is tradeable on Bitfinex (`_any_active_on_bitfinex()` check) — prevents circular waste of paying withdrawal fees to park USDT on Bitfinex when it can't be used. Discovery consolidation is ungated (no symbols active yet). Logged as `[Optimizer] ... consolidation SKIPPED` (throttled to every 5 min on regular eval cycle).
7. **Idle seller crypto consolidation**: `_consolidate_idle_seller_crypto()` transfers crypto from seller exchanges idle 30+ minutes directly to Bitfinex, selling at 0% taker. Only for symbols available on Bitfinex (~40-50 of 60). Uses USDT withdrawal fees as proxy for crypto transfer fees.
8. **Demotion sell via Bitfinex**: On demotion, crypto is transferred directly to Bitfinex and sold at 0% taker (saves source exchange taker fee). Falls back to local sell for symbols not available on Bitfinex. Post-demotion USDT consolidation runs automatically.
9. **Withdrawal fee preference**: `_rebalance_usdt()` prefers cheap rebalance sources (fee ≤ $0.10) before falling back to expensive ones. Avoids KuCoin ($0.40) and Gate.io ($0.50) when cheaper alternatives exist.

### Key Methods

| Method | File | Purpose |
|--------|------|---------|
| `available_usdt_for_trading(ex)` | `balance.py` | Returns USDT minus reserve if Bitfinex (for trade sizing/execution) |
| `_available_usdt_for_rebalance(ex)` | `balance.py` | Returns USDT minus reserve if Bitfinex (for rebalance source selection) |
| `emergency_reserve_draw(target, amount)` | `balance.py` | Emergency $0-fee transfer from reserve (hard floor enforced) |
| `replenish_reserve()` | `balance.py` | Top up reserve from all exchanges (sorted by fee) |
| `consolidate_to_bitfinex(active_buyers, idle_threshold)` | `balance.py` | Move idle USDT to Bitfinex hub |
| `sell_crypto_via_bitfinex(source, symbol, qty, bid)` | `balance.py` | Transfer crypto to Bitfinex + sell at 0% |
| `_consolidate_idle_seller_crypto(idle_threshold)` | `optimizer.py` | Consolidate crypto from idle seller exchanges |
| `_execute_demotion()` | `optimizer.py` | Demotion with Bitfinex-first crypto transfer |
| `_redistribute_post_demotion()` | `optimizer.py` | Push freed Bitfinex USDT to starved buyer exchanges after demotion |
| `_is_symbol_on_bitfinex(symbol)` | `optimizer.py` | Check if symbol has live Bitfinex price (used for expansion preference) |
| `_any_active_on_bitfinex()` | `optimizer.py` | Check if any active symbol is tradeable on Bitfinex (gates consolidation) |

## Adaptive Trading System

The bot has a capital-aware adaptive trading system controlled by the **Adaptive Mode** toggle (enabled by default in settings).

### Per-Symbol Trade Sizing

Each active symbol gets a **trade multiplier** based on its focus tier (see Strong-Only Trading above). Active symbols always receive non-zero multipliers (1.0× floor for weak tier).

- **Auto-scaling trade amount**: `trade_amount_pct` (default 0 = disabled). When > 0, `trade_amount = total_capital × trade_amount_pct` — auto-scales as capital grows. E.g., 1% of $3,000 = $30; capital grows to $5,000 → auto-updates to $50. Configurable via Settings UI ("Fixed $" / "% of Capital" toggle). When disabled (0), uses manual `trade_amount_usd`.
- `allocated_trade_size = trade_amount × multiplier × net_pct_multiplier`
- **Net%-based sizing** (`net_pct_sizing_enabled`, default true): scales trade size by current tick's net profitability. Tiers: <0.03%=0.5×, 0.03–0.08%=1.0×, 0.08–0.15%=1.5×, 0.15–0.25%=2.0×, >0.25%=2.5×. Capped by `net_pct_multiplier_cap` (default 2.5). Fat spreads get bigger trades; thin margins get smaller ones.
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
6. **Hourly external transfer budget**: Rolling 1-hour window caps total external withdrawal fees at `hourly_external_transfer_cap` (default $2.00/hr). Internal rebalances (sell/buy on same exchange) are not limited. Persisted across restarts. 0 = disabled. **Zero/near-zero fee transfers (≤ $0.01) bypass the hourly cap entirely** — prevents $0-fee Bitfinex/MEXC/Bybit transfers from being blocked when the cap is exhausted by earlier expensive transfers.
7. **Cooldown**: 60s between rebalances per exchange/direction.
9. **EMPTY backoff**: When `try_rebalance()` returns no viable transfers, exponential backoff delays the next attempt (30s→60s→120s→240s→300s cap). Prevents flooding logs with identical failed rebalance attempts. Cleared on successful rebalance or substantial trade (≥50% of trade_amount).
8. **Dynamic rebalance buffer**: Eligibility threshold for rebalance sources scales with trade amount (`trade_amount × 2`) instead of the fixed $50. For $10 trades, source needs $20 buffer (not $50), making internal sells and external transfers viable for smaller positions. All successful rebalance transfers logged at INFO level (`[Balance] External USDT`, `[Balance] Internal sell`, `[Balance] External crypto`, `[Balance] Internal buy`, `[Balance] External+buy`). Failures logged as `[Balance] USDT/Crypto rebalance FAILED` with diagnostics.

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
| `monitor.py` | `_compute_trade_size()` — per-symbol adaptive sizing; `_tick()` — trade execution with slippage simulation, threshold checks, ROI gate, miss streak tracking; `_record_trade_pnl()` — hourly/daily P&L buckets; `ConfigSnapshot` dataclass |
| `slippage.py` | `compute_buy_slippage()`, `compute_sell_slippage()` — order book depth-based slippage simulation |
| `balance.py` | `compute_rebalance_amount()` — adaptive rebalance; transfer worthiness check in `_rebalance_usdt()`/`_rebalance_crypto()` |
| `optimizer.py` | `_compute_scores()` — focus tiers + trade multipliers; `_complete_discovery()` — strong-only activation + dynamic buy/sell allocation; `_compute_dominant_pairs()` — per-symbol exchange detection; `_evaluate_demotions()` — strong threshold gating; `_track_candidate_transitions()` — strong/very_strong historical tracking; `_is_score_stable()` — candidate trend analysis (cliff drop, declining trend, min observation); `_update_watchlist()` — `[Candidate]` lifecycle logging |
| `config.py` | `__version__`, `DEFAULT_FEE_CONFIGS`, `DEFAULT_TRANSFER_CONFIGS`, `ADAPTIVE_MODE` |
| `fee_manager.py` | `FeeManager` — centralized fee computation, token discounts, referral cashbacks, zero-fee pairs, real mode |
| `transfer_fee_manager.py` | `TransferFeeManager` — per-exchange per-network withdrawal fees (flat/percentage/conditional), preferred network selection |
| `settings.json` | Runtime settings including `adaptive_mode`, `min_net_profit_pct`, `trade_amount_usd`, `trade_amount_pct`, `total_capital`, `fee_configs`, `transfer_configs`, `reallocation_cost_horizon`, `demotion_cooldown_multiplier`, `hourly_external_transfer_cap`, `fee_threshold_multiplier` |

## Simulation Realism

Four features that close the gap between simulation and live trading $/hr. All configurable via dashboard Settings → "Simulation Realism" section. Hot-applied without restart.

### Feature 1: Spread Persistence

Only executes trades when the spread persists across consecutive ticks (~1s each), filtering "phantom spreads" that would close before real orders arrive.

- **Setting**: `spread_persistence_ticks` (int, default 1, range 0-5)
- 0 = disabled (instant execution, legacy behavior)
- 1 = spread must exist on 2 consecutive ticks (~1s latency simulation)
- Tracked in `_pending_opportunities` dict (resets on restart)
- Counter: `_phantom_spread_count` — logged in `[Session]` summary as `phantom=X`

### Feature 2: Event-Driven Seller Penalty

Deprioritizes event-driven exchanges (e.g., Bitfinex) as sellers during pair selection. Their bids update every 10-20s (vs ~100ms for streaming exchanges), so the bid may be stale.

- **Setting**: `event_driven_seller_penalty_pct` (float, default 0.05, range 0.0-1.0)
- Applied at **both** discovery scoring (`optimizer._score_tick()`: `net_pct -= penalty`) and execution time (`monitor._tick()`: `scoring_net -= penalty`) when seller has `IS_EVENT_DRIVEN = True`
- Both `optimizer` and `monitor` build `_event_driven_exchanges` set from fetcher flags at init (no hardcoded exchange names). Setting synced to both via dashboard hot-apply.
- Counters: `_event_driven_seller_penalties` (total applications), `_event_driven_seller_demoted` (winner changed)
- Logging: `[Monitor] EVD_SELLER` (throttled), `[Monitor] EVD_DEMOTED` (throttled to 1 per symbol per 5 min)
- Session summary: `evd_sell=X/demoted=X`

### Feature 3: One-Legged Failure Simulation

Simulates random trade execution failures where one leg succeeds but the other fails, deducting unwind costs from profit.

- **Settings**: `one_leg_failure_rate` (float, default 0.02 = 2%), `one_leg_unwind_slippage_mult` (float, default 1.5)
- After trade executes: roll `random.random()` against failure rate
- If triggered: compute unwind cost (taker fee + slippage × multiplier), deduct from profit
- `SimulatedTrade.one_leg_simulated` field marks affected trades
- Logging: `[Trade] ONE_LEG_SIM` with details
- Session summary: `one_leg=X/$Y.YY`

### Feature 4: Max Position Accumulation Cap

Limits accumulated crypto value per symbol on buyer exchanges, preventing excessive flash-crash exposure.

- **Setting**: `max_position_multiplier` (float, default 5.0, range 0-50)
- 0 = disabled (no cap)
- Before trade execution: checks `crypto_value + trade_size > trade_amount × multiplier`
- If at cap: trade_size set to 0 (skipped). If near cap: trade_size reduced.
- Per-exchange, per-symbol (not global)
- Counter: `_position_cap_skips` — session summary: `pos_cap=X`

### State Persistence

All counters (`_phantom_spread_count`, `_event_driven_seller_penalties`, `_event_driven_seller_demoted`, `_one_leg_sim_count`, `_one_leg_sim_cost`, `_position_cap_skips`) are persisted via `to_state_dict()` / `from_state_dict()`. `_pending_opportunities` resets on restart (stateless — fresh detection).

## Anomaly Protection

3-layer trading safety system that detects performance decline and takes targeted action. Per-symbol blocking for isolated issues, global pause only for systemic problems. All settings configurable via dashboard Settings, hot-applied without restart. Separate `AnomalyProtection` class in `anomaly_protection.py`.

### Layer 1: Circuit Breaker (Rolling P&L) — Global

Detects systemic P&L decline across all symbols using a rolling window of `(timestamp, profit)` tuples.

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `circuit_breaker_window` | 900 (15min) | 60–7200 | Rolling window in seconds |
| `circuit_breaker_threshold` | -5.0 ($) | -1000–0 | Pause threshold (for $1000 capital: -0.5%) |
| `circuit_breaker_resume_pct` | 0.5 | 0.1–1.0 | Resume when P&L > threshold × resume_pct |
| `circuit_breaker_cooldown` | 300 (5min) | 30–3600 | Min wait before auto-resume |

### Layer 2: Drawdown Protection (Peak-to-Trough) — Per-Symbol + Emergency

Tracks portfolio value vs session peak. Blocks declining symbols on threshold breach, emergency sell-all on severe decline.

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `drawdown_threshold_pct` | 5.0% | 0.5–20.0 | Per-symbol block threshold ($50 on $1000) |
| `drawdown_resume_pct` | 3.0% | 0.1–10.0 | Auto-resume when recovered |
| `drawdown_emergency_mult` | 2.0 | 1.5–5.0 | Emergency sell at threshold × mult (10%) |

**Non-emergency drawdown** (≥ threshold): Instead of global pause, blocks only symbols with crypto exposure (the ones causing the drawdown). Other symbols continue trading. Uses per-symbol blocking mechanism (`_symbol_blocked_until`). Falls back to global pause only if `crypto_symbols` context is unavailable.

**Emergency drawdown** (≥ threshold × mult): Global pause + sell-all crypto positions. Sends email notification. Requires manual resume from dashboard.

**Peak reset after liquidation**: When all crypto is sold (emergency sell or demotion), `reset_peak_if_no_crypto()` resets `_peak_portfolio_value` to current portfolio value. Breaks the deadlock where drawdown stays permanently above resume threshold after crypto is liquidated. Called from `monitor._tick()` (after emergency sell) and `optimizer._evaluate_demotions()` (after demotion sells all crypto).

### Layer 3: Per-Symbol Loss Streak — Targeted

Blocks individual symbols after consecutive losses. Other profitable symbols keep trading.

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `symbol_loss_streak_threshold` | 4 | 2–20 | Consecutive losses to trigger block |
| `symbol_loss_streak_cooldown` | 300 (5min) | 60–3600 | Block duration (streak resets after) |

### Warning Level (Pre-Pause)

Before circuit breaker triggers full pause, reduces trade size to 0.5× when rolling P&L approaches threshold.

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `warning_pnl_pct` | 0.5 | 0.1–1.0 | Warning at threshold × pct (-$2.50 default) |

Master toggle: `anomaly_protection_enabled` (bool, default true).

### Manual Stop/Start

Operator toggle in Settings → Danger Zone, independent from anomaly protection. Persisted in state (survives deploys). "Stop Trading" button with confirmation prompt, "Start Trading" button to resume. Logged as `[Monitor] MANUAL_STOP/MANUAL_START by operator`. `_manual_stop_timestamp` tracks when trading was stopped (used for duration display in header tooltip).

### Hard Stop (Convert All Crypto to USDT)

One-click operator action in Danger Zone to liquidate all crypto positions across all exchanges. Two modes:
- **Transfer to Bitfinex ON** (default): Crypto transferred to Bitfinex and sold at 0% taker. Symbols not available on Bitfinex sold locally. USDT accumulates on Bitfinex. Enables Distribute button.
- **Transfer to Bitfinex OFF**: Sell all crypto locally on each exchange (pays taker fee per exchange).

Red confirmation modal with text input — must type "hard stop" exactly to enable confirm button. Result displayed in modal (positions sold, gross, fees, net). Backend: `_hard_stop_all()` in `dashboard_server.py`, uses `force_sell_crypto_via_bitfinex()` in `balance.py` (bypasses cooldowns/budget). Logged as `[Monitor] HARD_STOP_SELL`.

### Distribute USDT from Bitfinex

Score-weighted distribution of Bitfinex USDT to profitable exchanges. **Contextually enabled/disabled** via `_distribute_enabled` flag:
- **Enabled when**: execution mode changed to "live", or Hard Stop completes with Transfer to Bitfinex ON
- **Disabled when**: distribution completes, or bot restarts (one-shot)
- **Disabled by default**: button greyed out until a trigger enables it

Distribution strategy: uses optimizer's active symbols and dominant buyer/seller exchanges for score-weighted allocation. Falls back to even split if no active symbols. Respects Bitfinex reserve. Free transfer ($0 Bitfinex withdrawal). Red confirmation modal — must type "distribute usdt" to confirm. Backend: `_distribute_from_bitfinex()` in `dashboard_server.py`. Logged as `[Monitor] DISTRIBUTE`.

### Settings Sync at Startup

`_sync_settings_on_startup()` in `dashboard_server.py:run()` applies all persisted `settings.json` values to components (BalanceTracker, Monitor, Optimizer, AnomalyProtection) before the main loop starts. This ensures settings changed via dashboard in previous sessions are applied — `run.py` only passes a subset of settings to constructors. Targeted method: no optimizer reset or discovery restart.

### Smart Settings Apply (No Unnecessary Discovery Restart)

`_apply_settings()` only triggers discovery restart when **scoring fundamentals** change (`scoring_window`, `num_active_symbols`, `auto_rotate`). All other settings are hot-applied without wiping tick windows, preserving 15+ minutes of collected scoring data. Fee settings (`save_fee_settings`, `save_transfer_settings`) are separate handlers and never trigger discovery restart.

| Setting Category | Discovery Restart? | Examples |
|-----------------|-------------------|---------|
| Scoring fundamentals | Yes | `scoring_window`, `num_active_symbols`, `auto_rotate` |
| Thresholds & gates | No (hot-apply) | `trading_score_threshold`, `fee_threshold_multiplier`, `min_net_profit_pct` |
| Trade sizing & rebalance | No (hot-apply) | `trade_amount`, `rebalance_cooldown`, `hourly_external_transfer_cap` |
| Simulation realism & anomaly | No (hot-apply) | `spread_persistence_ticks`, `circuit_breaker_threshold` |
| Fee & transfer configs | No (separate handler) | Taker rates, discounts, withdrawal fees, enable/disable exchange |

### Comprehensive Settings Logging

`_log_all_settings(reason, old_settings=None)` in `dashboard_server.py` logs ALL settings with `[Settings]` component prefix:
- **Session start**: Called 10s after WebSocket server starts via `call_later()` in `dashboard_server.py:run()` (ensures log handler is ready for disk export). Version (`[Config] version=vX.Y.Z`) is logged immediately before settings.
- **Settings change**: Called at end of `_apply_settings()` with before/after diff

Each setting is logged as a separate `logger.info()` call (one per line) so every line gets its own timestamp and is individually filterable in Bot Logs. Covers: trade amount, adaptive mode, symbol limits, scoring params, rebalance gates, net P&L gate, simulation realism, anomaly thresholds, Bitfinex reserve, fee configs (per-exchange effective rates), execution mode, and changed values diff.

### Diagnostic Logging

All events use `[Anomaly]` component prefix. Every trigger includes multi-line state snapshots: rolling P&L, loss rate, top losers/winners, portfolio breakdown, crypto exposure, per-symbol recent trades. Events stored in deque (maxlen=100), persisted in state, viewable in dashboard. Session summary: `anomaly=Xp/Xw/Xsb` (pauses/warnings/symbol-blocks).

### Anomaly State on Restart

When anomaly `_paused` is restored from state after a restart, `_pause_timestamp` is reset to now. This restarts the cooldown timer so `_check_recovery()` can properly evaluate with fresh data. Circuit breaker auto-resumes after cooldown (stale rolling P&L entries pruned). Drawdown auto-resumes when portfolio recovers. Emergency stays paused (manual resume required). Logged as WARNING: `[Anomaly] Restored paused state on startup`.

### Emergency Email Notification

On emergency sell-all, an email is sent via `notify_emergency()` in `email_notifier.py` with: trigger reason, drawdown % and $ amount, current portfolio value, full liquidated positions table (exchange/symbol/qty/price/gross/fee/net sorted by value), and per-exchange USDT breakdown. Sent as fire-and-forget async task.

### Integration Points

- **monitor.py**: `_anomaly` instance, `_anomaly_paused` and `_manual_stopped` flags. Main loop checks `should_block_trading`. `_tick()` checks `should_emergency_sell` and `is_symbol_blocked(sym)`. `_compute_trade_size()` applies `trade_size_multiplier`. `record_trade()` called after each trade.
- **dashboard_server.py**: `update_portfolio_value()` called in `_build_state()`. Hot-apply for all 11 settings. Message handlers: `anomaly_resume`, `manual_stop`, `manual_start`, `hard_stop`, `distribute_from_bitfinex`. `_log_all_settings()` for comprehensive logging.
- **Dashboard**: Header shows anomaly indicators (STOPPED/EMERGENCY/PAUSED/WARNING/Protected) with rich hover tooltips showing diagnostics (rolling P&L, thresholds, loss rate, blocked symbols, session counters). Settings page has live stats, blocked symbols display, all 11 configurable inputs, and Danger Zone (Hard Stop, Distribute, Stop/Start, Restart).

### Key Files

| File | Purpose |
|------|---------|
| `anomaly_protection.py` | `AnomalyProtection` class — all 3 layers, state persistence, diagnostic logging |
| `config.py` | 11 anomaly protection constants |
| `settings.py` | Default settings for anomaly protection |
| `monitor.py` | Integration: pause checks, emergency sell + email notification, per-symbol blocking, trade recording |
| `dashboard_server.py` | Hot-apply, portfolio update, message handlers, `_hard_stop_all()`, `_distribute_from_bitfinex()`, `_log_all_settings()` |
| `balance.py` | `force_sell_crypto_via_bitfinex()` — bypasses cooldowns/budget for Hard Stop |
| `email_notifier.py` | `notify_emergency()` — email with drawdown info, liquidated positions, USDT breakdown |
| `dashboard/src/components/Header.tsx` | Anomaly status indicators with rich hover tooltips (desktop) + tappable badge popups (mobile) |
| `dashboard/src/components/SettingsPage.tsx` | Anomaly protection settings UI, Danger Zone (Hard Stop, Distribute, Stop/Start, Restart) |

## Dashboard

React/TypeScript SPA served by the Python backend via WebSocket. Uses `HashRouter` for client-side URL routing (no nginx config needed). Full-width layout optimized for 1920px screens.

### Pages

All pages have their own URL routes (`/#/`, `/#/rankings`, `/#/settings`, `/#/logs`). Sub-tabs also have routes (e.g., `/#/settings/fees`, `/#/logs/auth`, `/#/rankings/historical`). Browser back/forward and refresh work correctly.

- **Dashboard** — Real-time overview: header with persistent uptime (hover for downtime log), stats bar (portfolio, trades, profit, fees, transfers). Portfolio P&L (sim + demo), trade/transfer stats, demo exchange status, symbol rankings with dominant exchange pairs (e.g. `BIN→KUC`) and live Cur Net% column, balance table, price grid, demo portfolio comparison, recent trades/transfers, rotation log. Fully responsive: 2×2 stats grid, horizontal-scroll tables, bottom tab nav on mobile.
- **Rankings** — Deep analysis: full rolling rankings table with Mult/Trade $ columns, top-10 charts (by score, frequency, $/hr), historical session stats with Strong/V.Strong columns and duration, lifecycle funnel, exchange rankings, pair analysis, trend analysis, watchlist. Performance charts section (cumulative P&L, hourly P&L, exchange profit contribution) using recharts. Markdown export ("Copy MD") for sharing data with Claude. All tables horizontal-scroll on mobile.
- **Settings** — Three sub-tabs (routed: `/settings`, `/settings/fees`, `/settings/transfers`). Each setting has a `?` tooltip icon with detailed description (hover on desktop, tap on mobile):
  - **General**: Configure all parameters: trade amount (fixed $ or % of capital with auto-scaling), capital, min net profit %, rebalance cooldown, ROI horizon, adaptive mode toggle, auto-rotate, symbol limits, IP whitelist. **Danger Zone**: Stop/Start Trading toggle, "Hard Stop" (convert all crypto to USDT with Bitfinex optimization), "Distribute USDT from Bitfinex" (contextually enabled, score-weighted allocation), "Restart Bot" (clears state, fresh start). Hard Stop and Distribute require typing confirmation phrase. Form grids stack single-column on mobile.
  - **Fee Management**: Per-exchange fee configuration — **enable/disable checkbox** per exchange (disabled = excluded from trading/rebalancing, hot-applied), base taker rate, token discount toggle+%, fee model (received/spent/token), mechanism (instant/rebate/tier), referral cashback toggle+%+settlement delay, zero-fee pairs. Shows computed effective rates with formula breakdown. Cashback stats (pending/credited). Real mode banner. Save button with 5s cooldown. Hot-applied without restart.
  - **Transfer Fees**: Per-exchange withdrawal fee configuration — per-network fees (flat/percentage/conditional), preferred network selector (auto=cheapest), enable/disable individual networks. Shows effective fee and cheapest network per exchange. Save button with 5s cooldown. Hot-applied without restart.
- **Logs** — Unified log viewer with two sub-tabs:
  - **Bot Logs**: Real-time terminal-style log viewer (font-mono, auto-scroll). Filters: level (INFO/WARNING/ERROR), component (27 base components + dynamic discovery from log entries), text search. When filter is active, fetches ALL session logs from server (not just the 2000-entry broadcast buffer). Export to `.log` file.
  - **Auth Logs**: Authentication event log (login success/failure, blocked IPs, reconnections, IP denials). Filterable by event type with search by IP/username/browser/OS. Export to `.csv` file.
  - **Export**: Presets (1 Hour, 6 Hours, Today, 1 Day, Current Session, All, Custom UTC datetime picker). "Apply current filters" checkbox auto-checks when UI filters are active. Reads from disk log files for cross-day ranges.

### Dashboard Authentication

Full authentication system for the WebSocket dashboard:

- **Login**: Username + bcrypt-hashed password. Set `DASHBOARD_PASSWORD_HASH` in `.env` (preferred) or legacy `DASHBOARD_PASSWORD` (auto-hashed at runtime with deprecation warning). Default password `changeme` is rejected at startup.
- **Sessions**: Token-based with remember-me support. Remember-me → localStorage (30-day absolute expiry). Non-remember → sessionStorage (24h idle / 48h absolute expiry). All sessions have `created_at` for absolute lifetime enforcement. Sessions persisted to `logs/auth/sessions.json` — survive restarts (deploy and "Restart Bot"). On restart, client reconnects with stored token → no re-login, no email notification.
- **Rate limiting**: 10 attempts per IP, 1-hour block after exhaustion. State persisted to `logs/auth/rate_limits.json` (survives restarts). CAPTCHA failures also count toward rate limit.
- **IP whitelist**: Optional, configurable from Settings page. Validated with `ipaddress` module.
- **reCAPTCHA v2**: "I'm not a robot" checkbox appears after 3 failed attempts (requires Google reCAPTCHA v2 keys in `.env`). Warning logged at startup if keys not configured.
- **Email notifications**: Gmail SMTP alerts on successful login and IP block (requires Gmail App Password in `.env`). All user-controlled values HTML-escaped. Email suppressed during 30s grace period after bot restart (prevents spam from auto-reconnection).
- **Auth log**: All auth events persisted to `logs/auth/auth_events.jsonl` (5MB rotation, 2 backup files), loaded on startup (500 max), viewable in Logs → Auth Logs tab. Passwords masked (first 2 chars + asterisks). Legacy plaintext passwords stripped on load.
- **Dedicated auth logger**: Human-readable log at `logs/auth/auth.log`
- **X-Forwarded-For**: Only trusted from IPs in `TRUSTED_PROXIES` (default: `127.0.0.1,::1`). Prevents IP spoofing to bypass rate limits/whitelist.
- **Origin validation**: When `ALLOWED_ORIGINS` is set, WebSocket connections from unknown origins are rejected (CSRF protection).
- **Settings validation**: All settings validated against schema (type, min/max ranges). Unknown keys rejected. IP whitelist entries validated. 5s cooldown between settings saves. Type enforcement on load: `load_settings()` coerces mistyped values (e.g. string `"300"` → int `300`) with warning log, falls back to default on failure. Hot-apply uses explicit `int()`/`float()` casts for all numeric settings.
- **Bind host**: Default `127.0.0.1` (behind nginx). Override with `DASHBOARD_BIND_HOST=0.0.0.0` for direct access.
- **IP denied priority**: Denied IPs see nothing rendered (blank screen) until `auth_denied` arrives, then immediately the "You are not allowed here" page. No spinner, no loading text — `wsInitialized` gate ensures zero UI leakage.

### Bot Logging

- **Format**: UTC timestamps via `time.gmtime` converter: `YYYY-MM-DD HH:MM:SS [LEVEL] [Component] message`
- **Daily rotation**: `TimedRotatingFileHandler` rotates at 00:00 UTC, keeps 30 days. Files: `logs/coirnabot.log` (current), `logs/coirnabot.log.YYYY-MM-DD` (rotated).
- **DashboardLogHandler**: Custom `logging.Handler` in `dashboard_server.py`. Captures entries in-memory (`deque(maxlen=2000)` for live broadcast, `list` for full session export). Parses `[Component]` prefix from log messages using `[\w.]+` regex (supports `Gate.io`). Exposes `get_all()` for filtered views and `total_count()` for UI display. Dashboard fetches full session logs via `request_all_bot_logs` WebSocket message when filters are active.
- **Latency logging**: `[Latency]` component prefix. Every 60s logs per-exchange: processing time (avg/min/max ms), message rate (msgs/s), data freshness (avg/max age ms) with active/dormant symbol separation (>2min = dormant). Also logs first-data-after-connect timing. Filterable in Bot Logs tab.
- **Diagnostic logging** (added v0.13.5): Six production-level log lines for self-sufficient diagnostics:
  - `[Config]` — Version (`__version__` from `config.py`) and all key config values at startup (trade_amount, capital, adaptive, min_net, max_symbols, execution_mode). Logged 10s after server start to ensure log handler is ready for disk export.
  - `[Trade]` — Per-trade execution: symbol, exchanges, buy/sell prices, qty, size, profit, net%
  - `[Monitor] SIZE_ZERO` — Why trade_size=0: which constraint hit (usdt_avail/crypto_val/base < min_trade). Throttled: first per symbol, then every 30th.
  - `[Rebalance] BLOCKED` — Why rebalancing was blocked: which gate rejected (score_gate/net_pnl_gate/roi_gate) with values. Throttled per miss_key.
  - `[Balance] Snapshot` — Every 5 min: per-exchange total value (USDT + crypto USD), portfolio total, fee breakdown (total vs external-only)
  - `[Session]` — Every 5 min: aggregate trades, pnl, transfer fees, cashback (credited/pending), net, $/hr, SIZE_ZERO count (sz0=), rebalance blocked count (rebal_blocked=). In demo/demo_only modes: includes demo accuracy stats (fill/reject/partial/one-leg counts, profit drift, avg slippage, fee mismatches, avg latency)
  - `[DemoTrade]` — Per-trade demo comparison: symbol, exchanges, status, sim/demo profit+diff, sim/demo slippage, buy/sell prices (sim→actual), fill ratios, fees with currency, latency, data age. D-04b fee rate validation per trade.
  - `[Candidate]` — Candidate lifecycle logged every tick during discovery (with `phase=discovery`, score/peak/drop%/tier/trend) and every eval cycle post-discovery. States: NEW (entered watchlist), WATCH (tracked with score/trend/block reason), CONFIRMED (passed all gates), DROPPED (score fell below threshold), REJECTED (unstable at activation — declining, cliff drop, or fading), EXPAND_TRACK (first seen for expansion), EXPAND_WAIT (unstable), EXPAND_BLOCKED (setup cost exceeds benefit), EXPAND_READY (activating). Filterable in Bot Logs tab.
- **Fatal error traceback**: `run.py` logs full `traceback.format_exc()` on fatal errors (not just the exception message), enabling root-cause analysis from systemd journal logs.
- **Disk export**: `_read_bot_logs_from_disk()` reads rotated + current log files for cross-day export ranges. `_read_auth_logs_from_disk()` reads JSONL files. Both use `asyncio.to_thread()` for non-blocking I/O.

### Uptime Tracking

Persistent uptime that survives VPS crashes and reboots. Stored separately from session state in `state/uptime.json`.

- **True uptime**: `(now - first_start) - sum(downtime_durations)`. Excludes periods when the VPS was down.
- **Downtime detection**: On startup, compares `now` vs `last_heartbeat` from `state/uptime.json`. Gap > 90s = downtime event recorded with `{start, end, duration}`. Last 50 events kept.
- **Heartbeat**: `_save_uptime_heartbeat()` writes `last_heartbeat` to `state/uptime.json` every 60s (in the broadcast loop).
- **Intentional restart resets everything**: "Restart Bot" button deletes `state/uptime.json` before `os.execv()` — next startup begins fresh with no downtime history.
- **VPS crash/reboot**: No restart marker (only `_trigger_restart()` writes one, not `stop()`) → `state/uptime.json` exists → gap detected → downtime recorded → uptime continues from original `first_start`.
- **Header display**: Uptime shown in header (desktop only). Hover tooltip shows: "Running since" (UTC), "Total downtime" with restart count, and scrollable downtime log with timestamps and durations.
- **All times in UTC**: Consistent with bot logs and performance charts.

### Proxy (Zurich VPS) Monitoring

Tracks Bitfinex fetcher's WebSocket connection state as a proxy for Zurich VPS health. When the Zurich proxy is down, the Bitfinex fetcher disconnects and `connected_exchanges` count drops automatically (e.g., 8/8 → 7/8). Sub-fetchers (`_BitfinexSubFetcher`, `_BitfinexBookSubFetcher`) set `_parent._ws_connected = True` on connect and `False` in `finally` blocks on disconnect, ensuring the proxy tracker detects outages.

- **Real-time state tracking**: `_track_proxy_state()` runs every broadcast cycle (~1s). Detects connected→disconnected and disconnected→connected transitions.
- **Downtime threshold**: 30s. Brief reconnections (< 30s) are filtered as noise.
- **Persistence**: `state/proxy_uptime.json` stores `first_connected`, `last_heartbeat`, and up to 50 downtime events. Heartbeat saved every 60s.
- **Header display**: "Exchanges: X/Y" has a hover tooltip showing: Zurich Proxy status (green/amber dot), "Running since" (UTC), "Total downtime" with outage count, and scrollable outage log.
- **Connection indicator**: When Zurich proxy is down but Bangkok is up, header shows "Disconnected (Zurich)" with amber pulsing dot instead of "Connected".
- **Intentional restart**: "Restart Bot" deletes `state/proxy_uptime.json` (fresh session, same as Bangkok uptime).
- **Startup behavior**: Tracking begins after the Bitfinex fetcher first connects. No downtime inferred during Bangkok startup delay.

### State Persistence

Session state survives restarts (including deploys via `systemctl restart`). `StateManager` in `state_manager.py` coordinates save/load.

**What's persisted:**
- **BalanceTracker**: USDT/crypto balances, transfers, fees, initialization state
- **ArbitrageMonitor**: Trade history, config snapshots, tick count, session statistics, hourly/daily P&L buckets
- **SymbolOptimizer**: Active symbols, rotations, historical stats, discovery state, dominant pairs
- **DemoPortfolioFetcher**: Baseline snapshots per exchange (first-fetch balances for delta computation)
- **FeeManager**: Pending referral cashbacks and total credited cashback amount
- **Uptime tracking**: First start timestamp, last heartbeat, downtime events — persisted to `state/uptime.json` (separate from `session.json`, deleted explicitly by restart handler)
- **Proxy uptime tracking**: Zurich VPS connection state, first connected timestamp, outage events — persisted to `state/proxy_uptime.json` (deleted on restart)

**How it works:**
- Each component implements `to_state_dict()` / `from_state_dict()` for JSON serialization
- Atomic writes: temp file + `os.replace()` to prevent corruption on crash
- Backup: `.bak` file kept as fallback if primary is corrupt
- Periodic saves every 60s + save on shutdown (SIGINT/SIGTERM)
- State stored in `state/session.json` (gitignored)
- `run()` methods guard timestamps (`_start_time`, `_discovery_start`) to avoid overwriting restored values
- **Cumulative state across demotion cycles**: `_complete_discovery()` calls `balance.reconfigure()` and `monitor.reconfigure()` (not nuclear `reset()`) — preserves trades, transfer fees, P&L buckets, tick count, start time, simulation realism counters, demo accuracy stats, and anomaly protection across demotion→discovery→activation cycles. Only per-cycle operational state (observations, miss streaks, stale tracking) is reset.

**Restart button:** Settings → Danger Zone → "Restart Bot" clears saved state, deletes `state/uptime.json` (resets uptime and downtime history), and restarts the process via `os.execv()`. Starts fresh with configured capital. Works both locally and under systemd. On restart: writes `state/restart_marker` file, client receives `restart_ack` → preserves auth state and shows stale data with yellow "Reconnecting..." indicator in header, auto-reconnects in ~2-5s without re-login. Email notifications suppressed during 30s grace period after restart.

### XLSX Export

Click "Export XLSX" on the Rankings page. 21 sheets: Summary (with lifecycle funnel), Rolling Rankings (with Focus Tier/Dominant Buyers/Sellers/Cur Net%), Historical Rankings (includes Times Strong/Very Strong, Strong/Very Strong Duration columns), Exchange Rolling (with Buy%/Sell%), Exchange Historical (with Buy%/Sell%), Exchange Pairs, Watchlist, Rotation History, Tier Analysis, Trade History (with Sim Slippage %), Transfer History, Transfer Summary, Trend Analysis, Buy-Sell Distribution, Configurations, Fee Configuration, Transfer Configuration, Discrepancies, Hourly P&L, Daily P&L, Exchange Profit.

### Markdown Export

Click "Copy MD" on the Rankings page to copy markdown tables to clipboard (for sharing with Claude). Sections: Session Summary, Rolling Rankings, Historical Rankings, Exchange Rankings, Recent Trades (last 50), Recent Transfers (last 20). Generated by `exportMarkdown.ts`.

### Key Dashboard Files

| File | Purpose |
|------|---------|
| `dashboard/src/App.tsx` | Main layout, HashRouter routing, WebSocket state, IP-denied priority gate, restart reconnection |
| `dashboard/src/types.ts` | All TypeScript interfaces (Trade, SymbolRanking, AdaptiveConfig, ConfigSnapshot, AuthLogEntry, BotLogEntry, DemoComparisonState, etc.) |
| `dashboard/src/hooks/useWebSocket.ts` | WebSocket connection, auth flow, state management, restart_ack handling, wsInitialized gate, export callbacks |
| `dashboard/src/components/Header.tsx` | Header with nav tabs, uptime display (hover tooltip with downtime log), exchanges count (hover tooltip with Zurich proxy status/outage log), connection status ("Disconnected (Zurich)" when proxy down), stats bar, logout (icon on mobile). Mobile: tappable badge row (connection, exchanges, anomaly, uptime) with popup overlays |
| `dashboard/src/components/LoginPage.tsx` | Login form with reCAPTCHA integration |
| `dashboard/src/components/LogsPage.tsx` | Unified Logs page container with Bot Logs / Auth Logs sub-tabs |
| `dashboard/src/components/BotLogsTab.tsx` | Terminal-style real-time bot log viewer with level/component/search filters, full session log fetch on filter, dynamic component discovery, auto-scroll |
| `dashboard/src/components/AuthLogPage.tsx` | Auth event log with filtering/search and CSV export |
| `dashboard/src/components/ExportLogsModal.tsx` | Reusable export modal with time presets, custom UTC picker, filter toggle |
| `dashboard/src/components/SymbolRankings.tsx` | Main page ranking card with Cur Net% column |
| `dashboard/src/components/RankingPage.tsx` | Full ranking analysis page with performance charts and markdown export |
| `dashboard/src/components/PerformanceCharts.tsx` | Recharts: cumulative P&L, hourly P&L (48h, persisted), daily P&L (7d, persisted), exchange profit contribution |
| `dashboard/src/components/Tooltip.tsx` | Reusable `?` icon tooltip (hover/tap) for settings descriptions |
| `dashboard/src/components/DemoComparison.tsx` | Per-exchange demo vs sim comparison cards with discrepancy log |
| `dashboard/src/components/SettingsPage.tsx` | Settings form with General/Fee Management/Transfer Fees sub-tabs, adaptive mode toggle, IP whitelist, restart button |
| `dashboard/src/components/FeeManagementTab.tsx` | Per-exchange fee configuration UI — discounts, referral cashback, zero-fee pairs |
| `dashboard/src/components/TransferFeeManagementTab.tsx` | Per-exchange transfer fee configuration UI — per-network fees, preferred network, enable/disable |
| `dashboard/src/utils/exportXlsx.ts` | XLSX export with all 21 sheets |
| `dashboard/src/utils/exportMarkdown.ts` | Markdown table export for clipboard (rankings, trades, transfers) |
| `dashboard_server.py` | Python WebSocket server, auth system, builds state, handles settings, log export from disk, restart handler, uptime tracking (`_load_uptime_data`, `_save_uptime_heartbeat`, `_get_uptime_info`), proxy monitoring (`_load_proxy_uptime_data`, `_track_proxy_state`, `_get_proxy_uptime_info`) |
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
- Root cause classification: fee difference, slippage, missing/extra position, stale data, missing_position_no_executor (for exchanges without demo API in Demo+Sim mode)
- **Log throttling**: Repeated discrepancies throttled to every 5 min per exchange+symbol+type. Re-logs immediately on >50% value change. Periodic summary every 5 min. `Discrepancy` objects always created for dashboard — only `logger.info()` calls throttled.

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

## IMPORTANT: Before Going Live

**When transitioning to real trading, you MUST read `documentations/RISKS.md` first.** It contains 16 documented risks (3 critical, 4 high, 5 medium, 4 low), a capital deployment strategy (Bitfinex hub → distribute at $0 cost), and a pre-live checklist. The document was written during Session #2 analysis when all risks were fresh. Do not skip it.

## Phase 2: Demo/Testnet Order Execution (Implemented)

When `execution_mode=demo` or `demo_only`, the simulation continues as baseline while real market orders are placed on exchange testnets in parallel. Actual fill data (price, qty, fees, latency) is compared with sim expectations to detect discrepancies D-05, D-08 through D-14, D-17, D-19, D-20.

### Execution Mode

Set in `settings.json`: `"execution_mode"` with three options. Dashboard Settings page has a selector. Requires restart to take effect.

| Mode | Label in UI | Active Exchanges | Demo Orders | Description |
|------|-------------|-----------------|-------------|-------------|
| `simulation` | Simulation | All 9 | No | Pure simulation, no real orders |
| `demo` | Demo + Simulation | All 9 | Yes (any leg with executor) | Sim runs on all 9, demo orders on any leg touching Binance/OKX/Bybit. Single-leg execution when only one exchange has executor (e.g., Buy Binance demo + Sell KuCoin sim-only). |
| `demo_only` | Demo Only (Binance/OKX/Bybit) | 3 (Binance, OKX, Bybit) | Yes (all trades) | Restricts `active_exchanges` to demo-capable exchanges only. Every trade gets both sim and demo execution — eliminates `missing_position_no_executor` discrepancy noise. Ideal for pre-live validation. |

`demo_only` mode restricts exchanges early in `run.py` before component initialization, so `BalanceTracker`, `ArbitrageMonitor`, and `SymbolOptimizer` only see 3 exchanges. Header shows `3/3` exchanges.

### Architecture

```
Monitor._tick() detects opportunity
  ├─ balance.execute_trade()          ← sim (always runs)
  ├─ SimulatedTrade created + appended
  └─ asyncio.create_task(_execute_demo_trade())   ← demo (fire-and-forget)
       ├─ Both legs have executors:
       │    └─ DemoExecutor.execute_arbitrage()
       │         ├─ asyncio.gather(buy_executor, sell_executor)
       │         ├─ One-legged recovery if needed (D-11)
       │         └─ _record_demo_comparison()
       └─ Single leg has executor:
            └─ place_market_order() on available leg only
                 └─ _record_single_leg_comparison()
```

### Demo Position Establishment

On first `initialize_crypto()`, `_run_demo_setup()` fires as `asyncio.create_task()` to place market buy orders on demo/testnet exchanges, mirroring the sim's virtual crypto allocations. Sequential per exchange (rate limit safety). **Depth-aware sizing**: before each order, `compute_buy_slippage()` checks order book depth — if insufficient, qty is capped to 90% of available depth (`DEPTH_CAP` log). Warns on >1% estimated slippage (`HIGH_SLIPPAGE`). Skips if zero depth. Per-order logging with `[DemoSetup]` prefix includes latency, fee, sim vs demo cost diff, `setup_delay_ms` from sim init, and `depth_capped` when applicable. One-shot: `_demo_setup_complete` persisted in state. Cleared by "Restart Bot".

### Demo Position Tracking

`DemoExecutor._demo_positions` (`{exchange: {symbol: qty}}`) tracks actual crypto held on demo/testnet accounts. Updated on: setup order fills, arbitrage fills, single-leg fills. Before placing a demo sell order, `cap_sell_qty()` checks available position — returns 0 (skip) if empty, reduces qty if partial. Sell qty is then rounded via `exchange_info.round_quantity()` to match exchange lot_size_step. Prevents `Insufficient balance` and `too many decimals` rejections. Persisted in state via `to_state_dict()`.

### Demo Instrument Skip Pairs

`_demo_skip_pairs: set[str]` in `monitor.py` permanently tracks `exchange:symbol:side` combos that fail with "instrument not found" type errors (e.g., OKX DYDX-USDT spot doesn't exist on demo). Populated automatically from D-10 rejections. Before each demo trade, both buy and sell legs are checked against skip pairs — skipped combos set `has_buy`/`has_sell` to `False`. Counter `_demo_skip_count` tracks total skipped trades. Logged in `[Session]` summary as `demo_skipped=X` with full `demo_skip_pairs=[...]` list. Persisted in state, cleared on "Restart Bot".

### Key Files

| File | Purpose |
|------|---------|
| `executor.py` | `TradeResult`, `ArbitrageResult`, `RateLimiter`, `ExecutionEngine` base, `DemoExecutor` coordinator, `execute_setup_orders()` |
| `executors/__init__.py` | Package init |
| `executors/binance_exec.py` | Binance testnet: `https://testnet.binance.vision`, HMAC-SHA256, rate limit 100/60s |
| `executors/okx_exec.py` | OKX demo: `https://www.okx.com` + `x-simulated-trading: 1`, HMAC+passphrase, rate limit 50/2s |
| `executors/bybit_exec.py` | Bybit demo: `https://api-demo.bybit.com`, X-BAPI headers, rate limit 15/1s |

### TradeResult Fields

`success`, `order_id`, `client_order_id`, `exchange`, `symbol`, `side`, `requested_qty`, `filled_qty`, `requested_price`, `actual_avg_price`, `actual_fee`, `fee_rate`, `fee_currency`, `is_maker`, `latency_ms`, `error`, `raw_response`, `timestamp`. Computed properties: `fill_ratio`, `is_partial`, `slippage_pct`.

### SimulatedTrade Slippage Fields

`sim_slippage_pct` (total buy+sell), `sim_buy_slippage_pct`, `sim_sell_slippage_pct` — computed from order book depth at actual trade size.

### SimulatedTrade Demo Fields

`demo_buy_price`, `demo_sell_price`, `demo_buy_qty`, `demo_sell_qty`, `demo_profit_usd`, `demo_latency_ms`, `demo_slippage_pct`, `demo_status` (filled/partial/rejected/one_legged/unknown).

### Discrepancy Detection

`_record_demo_comparison()` runs after each demo trade. Compares sim vs actual:
- **D-05**: Fee currency mismatch (unexpected currency)
- **D-04b**: Per-trade fee rate validation (actual vs configured rate, WARNING if >0.001% diff)
- **D-08**: Slippage > 0.01% (avg across legs) + slippage model accuracy check (sim vs actual)
- **D-09**: Partial fill (fill_ratio < 0.99)
- **D-10**: Order rejected (error reason) — throttled: first per exchange:symbol:side logs, second logs "suppressing", 3rd+ silent. Executor-level dedup: `_rejected_symbols` dict tracks per-symbol rejection count, logs first + suppresses repeats. **Instrument skip**: If rejection error contains "instrument"/"doesn't exist"/"not exist", the `exchange:symbol:side` combo is permanently added to `_demo_skip_pairs` — future demo orders for that combo are silently skipped. Logged as `[DemoTrade] Permanently skipping...`. Persisted in state, cleared on "Restart Bot".
- **D-11**: One-legged (one success, one fail) → auto-unwind
- **D-12**: High latency > 500ms
- **D-13**: Maker fill (unexpected for market orders)

### Per-Trade Demo Logging (`[DemoTrade]`)

Comprehensive per-trade log with `[DemoTrade]` component prefix. Includes: symbol, exchanges, demo status, sim/demo profit (with diff), sim/demo slippage, buy/sell prices (sim→actual), fill ratios, actual fees with currency, latency, data age. Filterable in Bot Logs tab.

### Demo Accuracy Stats

Running counters tracked in `monitor.py` and persisted via state:
- `_demo_trade_count`, `_demo_fill_count`, `_demo_reject_count`, `_demo_partial_count`, `_demo_one_legged_count`
- `_demo_total_sim_profit` vs `_demo_total_actual_profit` (profit drift)
- `_demo_total_sim_slippage` vs `_demo_total_actual_slippage` (slippage model accuracy)
- `_demo_total_latency_ms`, `_demo_fee_mismatches`

Logged in `[Session]` 5-minute summary: fill/reject/partial/one-leg counts, profit drift, avg slippage comparison, fee mismatches, avg latency, `demo_skipped` count, `demo_skip_pairs` list.

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
4. **Idempotent IDs**: Format `cb{base}{side}{ts}{uuid6}` — alphanumeric only, starts with letter, max 32 chars (e.g., `cbBTCb1740000000a1b2c3`). OKX requires no hyphens.

### What Demo Testing Reveals (vs Simulation)

| Aspect | Simulation | Demo Reality |
|--------|-----------|-------------|
| Fill price | Order book depth slippage simulation | May differ (actual slippage) |
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
| Current | LightNode Bangkok + Oracle Zurich (Bitfinex proxy) | $7.70/mo |
| Phase 2 | (deployed — Zurich WS proxy live) | $7.70/mo |
| Phase 3 | + Vultr Singapore (OKX/Bybit/Bitget/KuCoin/Gate.io) | $12.70/mo |
| Phase 4 | + Tokyo VPS (Binance <1ms, Pionex) | ~$20/mo |

## Fee Management

Comprehensive fee system replacing the flat `EXCHANGE_TAKER_FEES` dict. Managed by `FeeManager` in `fee_manager.py`, configurable from the dashboard Fee Management tab.

### Fee Structure Per Exchange

| Exchange | Base Rate | Token Discount | Effective Rate | Invitee Kickback | Referrer Commission | Settlement | Mechanism | Fee Model |
|----------|-----------|---------------|---------------|:---:|:---:|------------|-----------|-----------|
| Binance | 0.10% | BNB 25% (enabled) | 0.075% | 10% | 10% | 60 min (hourly) | instant | token |
| OKX | 0.10% | OKB (disabled) | 0.10% | 20% | 10% | 90 min | tier | received |
| Bybit | 0.10% | MNT/BIT (disabled) | 0.10% | 20% (90 days) | 20% | 1440 min (daily) | tier | received |
| MEXC | 0.05% | MX 20% (enabled) | 0.04% | 10% | 40% | 1440 min (daily) | instant | received |
| Bitget | 0.10% | BGB 20% (enabled) | 0.08% | 20% | 20% | 0 min (instant) | instant | token |
| KuCoin | 0.10% | KCS 20% (enabled) | 0.08% | 20% | 0% | 1440 min (daily) | rebate | token |
| Gate.io | 0.10% | GT 10% (enabled) | 0.09% | 30% | 10% | 1440 min (daily) | instant | token |
| Pionex | 0.05% | None (VIP tiers only) | 0.05% | 20% | 0% | 60 min (hourly) | instant | received |
| Bitfinex | 0.00% | None (permanent 0%) | 0.00% | Disabled | Disabled | — | instant | received |

**Invitee Kickback** = fee rebate credited to the trading account (sister's account where bot runs). Configured via `referral_cashback_pct`. Affects scoring, net P&L, and rebalance gates.
**Referrer Commission** = fee earned by the referrer's personal account. Configured via `referrer_commission_pct`. **Display-only** — never touches balance, P&L, $/hr, scoring, or gating. Purple-themed in dashboard.
On shared-pool exchanges (Binance, OKX, KuCoin, Gate.io, Pionex), invitee + referrer = total pool. On independent exchanges (Bybit, MEXC), they are separate.

### Features

- **Exchange enable/disable**: Each exchange has an `enabled` checkbox in the Fee Management tab. Disabled exchanges are excluded from `_active_exchanges` (monitor/optimizer) and `_exchanges` (balance) — stops all trading and rebalancing on that exchange immediately. WebSocket fetchers still run for scoring data. Re-enabling adds the exchange back. Hot-applied without restart via `_apply_enabled_exchanges()`. Persisted in `settings.json` — survives restarts. At startup, `run.py` filters `active_exchanges` via `fee_manager.get_enabled_exchanges()` and `DashboardServer.run()` calls `_apply_enabled_exchanges()`. Header shows `X/X` (enabled only, not 9).
- **Token discounts**: Per-exchange toggle with configurable %. Effective rate = base × (1 - discount%). Gate.io GT gives 10% at VIP 0. Pionex has no discount token (only volume-based VIP tiers).
- **Referral cashbacks** (invitee kickback): Fee rebate credited to the trading account. Enabled for all exchanges except Bitfinex (0% fees already). Tracked as `PendingCashback` with exchange-specific settlement times: instant (Bitget, 0 min), hourly (Binance/Pionex, 60 min), ~90 min (OKX), or daily (Bybit/MEXC/KuCoin/Gate.io, 1440 min). Credited cashback is added to USDT balance and included in net profit calculations (`net_profit = trading_pnl - transfer_fees + credited_cashback`). Displayed in Trade Profit card (credited + pending).
- **Referrer commission tracking**: Tracks how much the referrer's personal account earns from each trade. Configured via `referrer_commission_pct` per exchange. **Display-only** — never added to balance, net profit, $/hr, scoring, or any gating decisions. Tracked in `FeeManager._total_referrer_earnings` and `_referrer_earnings_per_exchange`. Displayed in Trade Profit card (purple) and Fee Management tab with per-exchange breakdown. Shows "$10 transfer" reminder when any exchange accumulates ≥$10. Persisted via state. Logged as `[Fee] Referrer commission` per trade and `ref_earn=` in session summary.
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
| `fee_manager.py` | `FeeManager` class, `ExchangeFeeConfig` dataclass (incl. `enabled`, `referrer_commission_pct`), `is_exchange_enabled()`, `get_enabled_exchanges()`, `PendingCashback` tracking, `record_referrer_commission()`, settings serialization, broadcast dict |
| `config.py` | `DEFAULT_FEE_CONFIGS` — 9 exchanges × 12 fields (base rates, discounts, mechanisms, models, referral cashback, referrer commission, zero-fee, enabled) |
| `dashboard_server.py` | `save_fee_settings` handler with validation schema, `_apply_enabled_exchanges()` hot-apply, broadcast via `to_broadcast_dict()` |
| `dashboard/src/components/FeeManagementTab.tsx` | Per-exchange fee config UI with enable/disable checkbox and computed effective rates |

## VPS Infrastructure

### Current: LightNode Bangkok (Production)

- **Provider**: LightNode — $7.70/mo (2 vCPU, 2 GB RAM, 50 GB SSD)
- **Location**: Bangkok, Thailand
- **OS**: Ubuntu 22.04
- **Purpose**: Production monolithic deployment — all 9 exchanges from single VPS. MEXC accessible (Thailand not geo-blocked). Auto-deploy via GitHub Actions on push to master.

### Current: Oracle Zurich (Bitfinex Proxy)

- **Provider**: Oracle Cloud — Free tier (1/8 OCPU AMD, 1 GB RAM, 47 GB boot volume)
- **Location**: Zurich, Switzerland
- **OS**: Ubuntu 24.04 (Python 3.12)
- **Shape**: VM.Standard.E2.1.Micro (AMD)
- **Purpose**: WebSocket proxy for Bitfinex — 0.7ms to Bitfinex (vs 1,200ms from Bangkok). Runs `proxy/ws_proxy.py` as systemd service on port 9000.
- **Network**: Port 9000 restricted to Bangkok VPS IP via Oracle Security List + iptables.

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
| Bitfinex | Zug, Switzerland | Bare-metal (Market Synergy) | ~200ms (via Zurich proxy, was ~1.2s direct) |

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
| VPS 4 | Zurich | Oracle (free) | Bitfinex WS proxy (<1ms) | $0 |

Bangkok is the orchestrator (all 9 exchanges accessible, MEXC requires Thailand). VPS 4 (Zurich) is **deployed** — runs WebSocket proxy for Bitfinex data (0.7ms to Bitfinex, ~200ms total via Bangkok).

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
| `documentations/FUTURE_PLANS.md` | Net%-based dynamic trade sizing design: multiplier tiers, distributed VPS latency analysis, slippage/stale data risks, simulation vs real trading considerations |
| `documentations/SESSIONS.md` | Session history & analysis: per-session performance metrics, exchange pair breakdowns, pattern tracking, decision log |
| `documentations/RISKS.md` | **READ BEFORE GOING LIVE.** Complete risk assessment for live trading: 16 risks sorted by severity (critical/high/medium/low) with probability, capital deployment strategy (Bitfinex hub), pre-live checklist |

## Technology Stack

- **Language:** Python 3.12+
- **Async:** asyncio + websockets library
- **Dashboard:** React 18 + TypeScript + Vite + Tailwind CSS + react-router-dom (HashRouter) + recharts
- **Data:** CSV snapshots per exchange per symbol (1s intervals)
- **Architecture:** BaseFetcher with exchange-specific subclasses, ArbitrageMonitor reads all fetcher states, SymbolOptimizer handles symbol discovery/rotation/scoring, BalanceTracker simulates capital management
- **Output:** Real-time dashboard + XLSX export + console arbitrage table
