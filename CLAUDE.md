# CoirnaBot - Cross-Exchange Crypto Arbitrage Bot

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

## Supported Exchanges (7 Active)

All 7 exchanges have working WebSocket fetchers implemented.

| Rank | Exchange | Taker Fee (w/ Discount) | Discount Token | WebSocket | Symbols |
|------|----------|------------------------|----------------|-----------|---------|
| 1 | **Binance** | 0.075% | BNB (25% off) | URL-param streams | 58/60 (no HYPEUSDT) |
| 2 | **OKX** | 0.10% | OKB (requires 500 OKB ~$25k) | Post-connect JSON | 60/60 |
| 3 | **Bybit** | 0.075% | MNT/BIT (25% off) | Post-connect JSON | 58/60 (no ZECUSDT) |
| 4 | **MEXC** | 0.05% | None needed (already lowest) | Post-connect JSON | 60/60 |
| 5 | **Bitget** | 0.08% | BGB (20% off) | Post-connect JSON | 60/60 |
| 6 | **KuCoin** | 0.08% | KCS (20% off) | REST token + WS | 60/60 |
| 7 | **Gate.io** | 0.10% | GT (~10% off, minimal) | Post-connect JSON | 60/60 |

**MEXC note:** Currently geo-blocked from user's location. Will use with future VPS deployment.

### Dropped Exchanges

| Exchange | Reason |
|----------|--------|
| **HTX (Huobi)** | 0.20%/0.20% base fees — too expensive for arbitrage. 25% HT discount still yields 0.15%. Also uses gzip-compressed binary WS messages. |
| **Kraken** | 0.25%/0.40% base fees — way too expensive. Only ~11/20 original USDT pairs available. |
| **Crypto.com** | No Plasma support, missing symbols, poor fit for strategy. |

## Fee Considerations

For arbitrage, fees are critical. A typical opportunity is 0.1-0.3%. Fee math:
- Buy fee + Sell fee = total cost
- If total cost >= price gap, no profit
- **MEXC (0.05% taker)** and **Binance/Bybit (0.075% with token discount)** are the most cost-effective pairs

### How to Claim Fee Discounts

| Exchange | What to Do | Discount |
|----------|-----------|----------|
| **Binance** | Buy BNB, enable "Pay fees with BNB" in Settings > Fee | 25% off (0.10% → 0.075%) |
| **Bybit** | Hold MNT or BIT tokens on Bybit | 25% off (0.10% → 0.075%) |
| **Bitget** | Buy BGB, enable "Pay fees with BGB" | 20% off (0.10% → 0.08%) |
| **KuCoin** | Buy KCS, enable "Pay fees with KCS" | 20% off (0.10% → 0.08%) |
| **OKX** | Hold 500+ OKB (~$25k investment) | Tiered discount (not practical at start) |
| **Gate.io** | Hold GT tokens | ~10% off (minimal, not worth prioritizing) |

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

Sorted by ~24h volume. 38/40 available on all 7 exchanges.

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

| Network | Binance | OKX | Bybit | MEXC | Bitget | KuCoin | Gate.io |
|---------|---------|-----|-------|------|--------|--------|---------|
| **BEP20** | $0.01 | <$0.50 | ~$0.20 | $0 (promo) | ~$0.30-0.50 | ~$0.50-1.00 | $0 (promo) |
| **Plasma** | $0.01 | Likely yes | ~$0 | Unconfirmed | Partial | Unconfirmed | Unconfirmed |
| **Arbitrum** | $0.10 | <$0.50 | ~$1.00 | **$0 (FREE)** | ~$0 (promo) | ~$0.50-1.00 | ~$0.50 |
| **Optimism** | $0.04 | <$0.50 | ~$1.00 | Low | Low (promo) | Unconfirmed | Low |
| **Polygon** | $0.07 | Low | ~$1.00 | Low | Low | Low | Low |
| **Solana** | $0.30 | Low | ~$1.00 | Near-zero | $0 (promo) | ~$0.50-1.00 | Low |
| **TRC20** | $1.00 | ~$0.10-2.30 | ~$0.10-1.60 | $1.00 | ~$1.00 | $1.50 | **$0 (FREE)** |
| **ERC20** | $0.80 | >$3.00 | ~$3.00 | Higher | ~$0.50 | $5.50 | Higher |

### Cheapest Rebalancing Routes

| From → To | Best Network | Fee | Speed |
|-----------|-------------|-----|-------|
| Binance → anywhere | BEP20 | $0.01 | ~3s |
| MEXC → anywhere | Arbitrum | $0 (free) | ~0.3s |
| Gate.io → anywhere | TRC20 | $0 (free) | ~3-5s |
| Gate.io → anywhere | BEP20 | $0 (promo) | ~3s |
| Bybit → anywhere | Plasma | ~$0 | Sub-second |
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

| Aspect | Binance | OKX | Bybit | MEXC | Bitget | KuCoin | Gate.io |
|--------|---------|-----|-------|------|--------|--------|---------|
| Subscribe | URL params | Post-connect | Post-connect | Post-connect | Post-connect | Post-connect | Post-connect |
| Symbol format | `btcusdt` | `BTC-USDT` | `BTCUSDT` | `BTCUSDT` | `BTCUSDT` | `BTC-USDT` | `BTC_USDT` |
| Ping type | WS-level (lib) | String `"ping"` | JSON `{"op":"ping"}` | JSON `{"method":"PING"}` | String `"ping"` | JSON `{"type":"ping"}` | JSON `{"channel":"spot.ping"}` |
| Ping interval | 20s (auto) | 15s | 18s | 15s | 25s | 18s | 15s |
| Has last_price | Yes | Yes | Yes | No | Yes | Yes | No |
| Has volume | Yes | Yes | Yes | No | Yes | No | No |
| Special | — | — | Delta merging | 30 sub limit | — | REST token first | Per-symbol subscribe |

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

- 60 symbols x 7 exchanges = many balance positions to manage
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

The bot only trades and transfers for **strong** (score ≥ 0.1) and **very strong** (score ≥ 0.3) symbols. All other symbols are scored but not traded. This is defined by `STRONG_SCORE_THRESHOLD = 0.1` in `optimizer.py`.

### Rules

- **Discovery**: Only activates symbols with score ≥ 0.1. Falls back to top 1 if nothing qualifies.
- **Early discovery exit**: If any symbol reaches score ≥ 0.1 during discovery (before the full duration), discovery ends immediately and trading starts.
- **Trading**: Non-strong active symbols get `trade_multiplier = 0` — the monitor skips them entirely.
- **Rebalancing**: `should_allow_rebalance()` requires score ≥ 0.1. No transfers for weak symbols.
- **Expansion/Rotation**: Only strong/very_strong candidates can be activated or replace existing symbols.
- **Demotion**: Symbols dropping below 0.1 are demoted on a tiered schedule (faster for weaker scores). No minimum active count protection — better idle than bleeding money on transfers.

### Focus Tiers & Trade Multipliers

| Tier | Score | Trade Multiplier | Exchange Count |
|------|-------|-----------------|----------------|
| Very Strong | ≥ 0.3 | 3.0×–4.0× | Up to 3 per direction (6 max) |
| Strong | ≥ 0.1 | 2.0×–3.0× | Up to 2 per direction (4 max) |
| Normal | 0.01–0.1 | 0× (no trading) | — |
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
- Selects top N exchanges per direction (buy/sell), ignoring < 2% weight
- `max_per_direction` is tier-based: 1 for default, 2 for strong, 3 for very_strong
- Falls back to historical `buy_exchange_counts` / `sell_exchange_counts` if insufficient rolling data

### Capital Allocation

After discovery, capital is allocated per-symbol to dominant exchanges:
- USDT → buyer exchanges (proportional to buyer weight)
- Crypto → seller exchanges (proportional to seller weight)
- 50/50 split between buy side and sell side per symbol
- Score-weighted across symbols: higher-scoring symbols get more capital

### Dynamic Re-evaluation

`_reevaluate_dominant_pairs()` runs every evaluation cycle for active symbols. If dominant exchanges shift (buyer or seller changed), capital is reallocated via `_reallocate_symbol()`. Gated by rotation budget and cooldown (2× evaluation_interval).

### Dashboard Display

The "Exchanges" column in Symbol Rankings shows dominant pairs as `BIN→KUC` (buyer→seller). The Buy-Sell Distribution sheet in XLSX shows per-exchange tick counts.

## Adaptive Trading System

The bot has a capital-aware adaptive trading system controlled by the **Adaptive Mode** toggle (enabled by default in settings).

### Per-Symbol Trade Sizing

Each active symbol gets a **trade multiplier** based on its focus tier (see Strong-Only Trading above). Only strong/very_strong symbols receive non-zero multipliers.

- `allocated_trade_size = trade_amount × multiplier × tick_quality_factor`
- Tick quality factor: 1.0 (net ≥ 0.10%), 0.90 (≥ 0.05%), 0.85 (< 0.05%)
- Trade size capped by 80% of available USDT (buy side) and 80% of available crypto (sell side)
- Minimum trade: `max($5, total_capital × 0.003)`

### Transfer Fee Awareness

Each exchange has different USDT withdrawal fees (defined in `config.py: USDT_WITHDRAWAL_FEES`):

| Exchange | Withdrawal Fee |
|----------|---------------|
| Binance  | $0.01 |
| OKX      | $0.01 |
| MEXC     | $0.01 |
| Gate.io  | $0.05 |
| Bitget   | $0.10 |
| Bybit    | $0.20 |
| KuCoin   | $0.80 |

Before executing an external USDT transfer, the bot checks **transfer worthiness**: if `withdrawal_fee / estimated_profit_per_trade > 50`, the transfer is skipped (not worth the cost). This prevents expensive KuCoin transfers unless highly profitable.

### Adaptive Rebalance Amounts

Instead of a static rebalance amount, the bot targets **3× trade_amount** to cover multiple upcoming trades. Capped at `trade_amount × 4`.

### Smart Capital Allocation

After discovery, capital is allocated via the Exchange & Symbol Concentration system (see above). Each symbol's capital goes only to its dominant buyer/seller exchanges, weighted by profitability scores.

### Rebalance Guards

Multiple gates prevent unprofitable rebalancing:

1. **Strong-only gate**: `should_allow_rebalance()` requires `score >= 0.1` (`STRONG_SCORE_THRESHOLD`). Normal/weak symbols (< 0.1) never trigger rebalances.
2. **ROI gate**: `_should_rebalance()` in monitor.py estimates rebalance cost (2× internal transfer fees on 3× trade_amount) and requires `expected_profit > cost × 1.5`. Blocks rebalances when amortized transfer cost exceeds per-trade profit.
3. **Net P&L gate**: After 10+ trades, if `trading_pnl < total_transfer_fees` (net negative), all rebalancing is blocked. Prevents loss spirals.
4. **Miss-streak threshold**: 15 consecutive missed ticks required before rebalancing triggers (was 5, increased to reduce frequency).
5. **Transfer worthiness**: External transfers blocked if `withdrawal_fee / estimated_profit > 50`.
6. **Cooldown**: 60s between rebalances per exchange/direction.

### Rebalance Order

In `try_rebalance()`, crypto rebalance runs BEFORE USDT rebalance. This ensures external crypto transfer (e.g., Bitget→KuCoin $0.10) uses accumulated crypto on the buyer before internal sell would consume it. Saves ~$0.14 per cycle vs the reverse order.

### Net Profit Awareness

The optimizer tracks whether net profit (trading P&L minus transfer fees) is positive. When in deficit:
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
| `config.py` | `EXCHANGE_TAKER_FEES`, `USDT_WITHDRAWAL_FEES`, `ADAPTIVE_MODE` |
| `settings.json` | Runtime settings including `adaptive_mode`, `min_net_profit_pct`, `trade_amount_usd`, `total_capital` |

## Dashboard

React/TypeScript SPA served by the Python backend via WebSocket.

### Pages

- **Dashboard** — Real-time overview: portfolio P&L (sim + demo), trade/transfer stats, demo exchange status, symbol rankings with dominant exchange pairs (e.g. `BIN→KUC`), balance table, price grid, demo portfolio comparison, recent trades/transfers, rotation log
- **Rankings** — Deep analysis: full rolling rankings table with Mult/Trade $ columns, top-10 charts (by score, frequency, $/hr), historical session stats with Strong/V.Strong columns and duration, lifecycle funnel, exchange rankings, pair analysis, trend analysis, watchlist
- **Settings** — Configure all parameters: trade amount, capital, min net profit %, rebalance cooldown, ROI horizon, adaptive mode toggle, auto-rotate, symbol limits, IP whitelist. **Danger Zone**: "Restart Bot" button clears saved state and starts fresh with configured capital.
- **Logs** — Unified log viewer with two sub-tabs:
  - **Bot Logs**: Real-time terminal-style log viewer (font-mono, auto-scroll). Filters: level (INFO/WARNING/ERROR), component (Monitor/Optimizer/Balance/exchanges/Dashboard/Auth/Email/Settings), text search. Export to `.log` file.
  - **Auth Logs**: Authentication event log (login success/failure, blocked IPs, reconnections, IP denials). Filterable by event type with search by IP/username/browser/OS. Export to `.csv` file.
  - **Export**: Presets (1 Hour, 6 Hours, Today, 1 Day, Current Session, All, Custom UTC datetime picker). "Apply current filters" checkbox auto-checks when UI filters are active. Reads from disk log files for cross-day ranges.

### Dashboard Authentication

Full authentication system for the WebSocket dashboard:

- **Login**: Username + bcrypt-hashed password. Set `DASHBOARD_PASSWORD_HASH` in `.env` (preferred) or legacy `DASHBOARD_PASSWORD` (auto-hashed at runtime with deprecation warning). Default password `changeme` is rejected at startup.
- **Sessions**: Token-based with remember-me support. Remember-me → localStorage (30-day absolute expiry). Non-remember → sessionStorage (24h idle / 48h absolute expiry). All sessions have `created_at` for absolute lifetime enforcement.
- **Rate limiting**: 10 attempts per IP, 1-hour block after exhaustion. State persisted to `logs/auth/rate_limits.json` (survives restarts). CAPTCHA failures also count toward rate limit.
- **IP whitelist**: Optional, configurable from Settings page. Validated with `ipaddress` module.
- **reCAPTCHA v2**: "I'm not a robot" checkbox appears after 3 failed attempts (requires Google reCAPTCHA v2 keys in `.env`). Warning logged at startup if keys not configured.
- **Email notifications**: Gmail SMTP alerts on successful login and IP block (requires Gmail App Password in `.env`). All user-controlled values HTML-escaped.
- **Auth log**: All auth events persisted to `logs/auth/auth_events.jsonl` (5MB rotation, 2 backup files), loaded on startup (500 max), viewable in Logs → Auth Logs tab. Passwords masked (first 2 chars + asterisks). Legacy plaintext passwords stripped on load.
- **Dedicated auth logger**: Human-readable log at `logs/auth/auth.log`
- **X-Forwarded-For**: Only trusted from IPs in `TRUSTED_PROXIES` (default: `127.0.0.1,::1`). Prevents IP spoofing to bypass rate limits/whitelist.
- **Origin validation**: When `ALLOWED_ORIGINS` is set, WebSocket connections from unknown origins are rejected (CSRF protection).
- **Settings validation**: All settings validated against schema (type, min/max ranges). Unknown keys rejected. IP whitelist entries validated. 5s cooldown between settings saves.
- **Bind host**: Default `127.0.0.1` (behind nginx). Override with `DASHBOARD_BIND_HOST=0.0.0.0` for direct access.
- **IP denied flash prevention**: Connecting screen text is delayed 1.5s so IP-denied users see only a spinner before the "You are not allowed here" page.

### Bot Logging

- **Format**: UTC timestamps via `time.gmtime` converter: `YYYY-MM-DD HH:MM:SS [LEVEL] [Component] message`
- **Daily rotation**: `TimedRotatingFileHandler` rotates at 00:00 UTC, keeps 30 days. Files: `logs/coirnabot.log` (current), `logs/coirnabot.log.YYYY-MM-DD` (rotated).
- **DashboardLogHandler**: Custom `logging.Handler` in `dashboard_server.py`. Captures entries in-memory (`deque` for live broadcast, `list` for session export). Parses `[Component]` prefix from log messages.
- **Disk export**: `_read_bot_logs_from_disk()` reads rotated + current log files for cross-day export ranges. `_read_auth_logs_from_disk()` reads JSONL files. Both use `asyncio.to_thread()` for non-blocking I/O.

### State Persistence

Session state survives restarts (including deploys via `systemctl restart`). `StateManager` in `state_manager.py` coordinates save/load.

**What's persisted:**
- **BalanceTracker**: USDT/crypto balances, transfers, fees, initialization state
- **ArbitrageMonitor**: Trade history, config snapshots, tick count, session statistics
- **SymbolOptimizer**: Active symbols, rotations, historical stats, discovery state, dominant pairs
- **DemoPortfolioFetcher**: Baseline snapshots per exchange (first-fetch balances for delta computation)

**How it works:**
- Each component implements `to_state_dict()` / `from_state_dict()` for JSON serialization
- Atomic writes: temp file + `os.replace()` to prevent corruption on crash
- Backup: `.bak` file kept as fallback if primary is corrupt
- Periodic saves every 60s + save on shutdown (SIGINT/SIGTERM)
- State stored in `state/session.json` (gitignored)
- `run()` methods guard timestamps (`_start_time`, `_discovery_start`) to avoid overwriting restored values

**Restart button:** Settings → Danger Zone → "Restart Bot" clears saved state and restarts the process via `os.execv()`. Starts fresh with configured capital. Works both locally and under systemd.

### XLSX Export

Click "Export XLSX" on the Rankings page. 15 sheets: Summary, Rolling Rankings, Historical Rankings (includes Times Strong/Very Strong, Strong/Very Strong Duration columns), Exchange (Rolling/Historical), Exchange Pairs, Watchlist, Rotation History, Tier Analysis, Trade History, Transfer History, Transfer Summary, Trend Analysis, Buy-Sell Distribution, Configurations.

### Key Dashboard Files

| File | Purpose |
|------|---------|
| `dashboard/src/App.tsx` | Main layout, tab routing, WebSocket state, IP-denied flash prevention |
| `dashboard/src/types.ts` | All TypeScript interfaces (Trade, SymbolRanking, AdaptiveConfig, ConfigSnapshot, AuthLogEntry, BotLogEntry, DemoComparisonState, etc.) |
| `dashboard/src/hooks/useWebSocket.ts` | WebSocket connection, auth flow, state management, export callbacks |
| `dashboard/src/components/LoginPage.tsx` | Login form with reCAPTCHA integration |
| `dashboard/src/components/LogsPage.tsx` | Unified Logs page container with Bot Logs / Auth Logs sub-tabs |
| `dashboard/src/components/BotLogsTab.tsx` | Terminal-style real-time bot log viewer with filters and auto-scroll |
| `dashboard/src/components/AuthLogPage.tsx` | Auth event log with filtering/search and CSV export |
| `dashboard/src/components/ExportLogsModal.tsx` | Reusable export modal with time presets, custom UTC picker, filter toggle |
| `dashboard/src/components/SymbolRankings.tsx` | Main page ranking card |
| `dashboard/src/components/RankingPage.tsx` | Full ranking analysis page |
| `dashboard/src/components/DemoComparison.tsx` | Per-exchange demo vs sim comparison cards with discrepancy log |
| `dashboard/src/components/SettingsPage.tsx` | Settings form with adaptive mode toggle, IP whitelist, restart button |
| `dashboard/src/utils/exportXlsx.ts` | XLSX export with all 15 sheets |
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

Gate.io excluded entirely. Bitget, KuCoin, MEXC continue simulation-only.

### Baseline Snapshot System

Pre-funded testnet balances (Binance ~$10k, OKX ~$5k, Bybit ~$50k) are subtracted so only bot-caused activity is visible:

- **Baseline** = snapshot captured on first successful fetch per exchange (persisted across restarts)
- **Delta** = `current_balance - baseline` (change since baseline)
- **Displayed demo value** = `sim_value + delta` (mirrors sim, diverges only when real trades happen)
- When no demo trades executed: delta = 0, displayed = sim, diff = 0

### Discrepancy Detection

Runs after each poll (15s interval). Compares baseline-adjusted demo values against simulation:
- USDT balance mismatch (threshold: $1 or 1%)
- Crypto position mismatches (qty delta vs sim qty)
- Root cause classification: fee difference, slippage, missing/extra position, stale data

### Dashboard Integration

- **Stats cards**: Cards 2-4 show demo exchange status, demo P&L, discrepancy count, demo $/hr, sim accuracy %
- **Demo Portfolio Comparison section**: Per-exchange cards (sim vs demo columns for USDT, crypto, total) with color-coded diffs
- **Discrepancy log**: Scrollable table of recent mismatches with time, exchange, type, values, root cause

### Key Files

| File | Responsibility |
|------|---------------|
| `demo_fetcher.py` | `DemoPortfolioFetcher` — REST API clients, baseline management, delta computation, discrepancy detection |
| `config.py` | Demo API key constants (`BINANCE_TESTNET_API_KEY`, `OKX_DEMO_API_KEY`, `BYBIT_DEMO_API_KEY`, etc.) |
| `dashboard_server.py` | `_build_demo_state()` — builds baseline-adjusted per-exchange comparison data for dashboard |
| `state_manager.py` | Persists demo_fetcher baselines via `to_state_dict()` / `from_state_dict()` |

## Phase 2: Demo/Testnet Order Execution (Planned)

Move from simulation-only to actual order execution on exchange testnet/demo APIs. This validates the simulation against real exchange behavior before live trading.

### Goal

Run the bot against all 6 exchange demo accounts with $1800 total capital ($300/exchange), placing real orders on testnets. Compare actual results (fills, latency, slippage) with what the simulation predicts.

### Exchange Testnet Endpoints

| Exchange | Type | Base URL | Auth |
|----------|------|----------|------|
| Binance | Spot Testnet | `https://testnet.binance.vision` | Separate testnet API key from [testnet.binance.vision](https://testnet.binance.vision/) |
| OKX | Demo Trading | Same base URL | Add header `x-simulated-trading: 1`, create Demo Trading API key |
| Bybit | Testnet | `https://api-testnet.bybit.com` | Separate testnet account at [testnet.bybit.com](https://testnet.bybit.com/) |
| Bitget | Demo Trading | Demo-specific endpoints | KYC required, demo API key |
| KuCoin | Sandbox | `https://openapi-sandbox.kucoin.com` | Separate sandbox API key |
| MEXC | Futures demo only | Limited | Spot testnet not available — use simulation mode for MEXC |

### Architecture

```
┌─────────────────────────────────────────────┐
│  run.py  (mode: "simulation" | "demo" | "live")  │
├─────────────────────────────────────────────┤
│  Monitor detects opportunity                      │
│    ↓                                              │
│  ExecutionEngine.execute(buy_ex, sell_ex, ...)    │
│    ├─ SimulationExecutor (current behavior)       │
│    ├─ DemoExecutor (testnet REST APIs)            │
│    └─ LiveExecutor (real REST APIs, future)       │
├─────────────────────────────────────────────┤
│  BalanceTracker                                   │
│    ├─ Simulation: internal math (current)         │
│    └─ Demo/Live: reconcile with exchange API      │
└─────────────────────────────────────────────┘
```

### New Files

| File | Purpose |
|------|---------|
| `executor.py` | `ExecutionEngine` base class + `SimulationExecutor` (wraps current `balance.execute_trade()`) |
| `executors/binance_exec.py` | Binance testnet/live order placement via REST API |
| `executors/okx_exec.py` | OKX demo/live order placement |
| `executors/bybit_exec.py` | Bybit testnet/live order placement |
| `executors/bitget_exec.py` | Bitget demo/live order placement |
| `executors/kucoin_exec.py` | KuCoin sandbox/live order placement |
| `executors/mexc_exec.py` | MEXC live order placement (no spot testnet) |
| `api_keys.json` | Per-exchange API keys (gitignored). Separate sections for `demo` and `live` keys |

### Implementation Steps

1. **ExecutionEngine interface** — `execute_trade(buy_ex, sell_ex, symbol, amount, buy_price, sell_price)` returns `TradeResult` with actual fill price, qty, fees, latency_ms, partial_fill flag
2. **Per-exchange executors** — Each implements REST API order placement (market order), order status polling, and balance querying
3. **Balance reconciliation** — After each trade, query actual exchange balances and compare with BalanceTracker. Log discrepancies. Option to sync BalanceTracker from exchange state.
4. **API key config** — `api_keys.json` with `{"binance": {"demo": {"key": "...", "secret": "..."}, "live": {...}}, ...}`. Loaded based on execution mode.
5. **Mode selection** — `settings.json` gets `execution_mode: "simulation" | "demo" | "live"`. Dashboard Settings page gets a mode selector.
6. **Slippage tracking** — Compare expected fill price (from WebSocket ticker) with actual fill price. Track as new metric in dashboard.
7. **Latency tracking** — Measure time from order send to fill confirmation. Display in dashboard.
8. **Capital enforcement** — In demo mode, ignore exchange's large demo balance. Use BalanceTracker's `total_capital` as the limit. Reject orders that would exceed it.

### What Demo Testing Reveals (vs Simulation)

| Aspect | Simulation | Demo Reality |
|--------|-----------|-------------|
| Fill price | Assumes ticker price | May differ (slippage) |
| Fill time | Instant | 10-500ms latency |
| Partial fills | Never | Can happen on thin orderbooks |
| Rate limits | Not modeled | Real API throttling |
| Order rejection | Never | Insufficient balance, invalid params |
| Fee calculation | Config constants | Exchange may charge differently |

### VPS Deployment Plan

| Phase | Setup | Cost |
|-------|-------|------|
| Test | Kamatera Tokyo (30-day free trial) with demo API keys | $0 |
| Production | Contabo Tokyo with real API keys | ~$7.50/mo |
| Optimized | 3 VPS: Tokyo (Binance) + Singapore (Bybit/Bitget/KuCoin/OKX) + Bangkok (MEXC + orchestrator) | ~$22.50/mo |

## VPS Infrastructure

### Current: Kamatera Tokyo (Test Phase)

- **Provider**: Kamatera — 30-day free trial (up to $100 credit)
- **Location**: Tokyo, Japan
- **OS**: Ubuntu
- **Purpose**: Testing with demo/testnet API keys only. No real API keys on free VPS.

### Exchange Server Locations & Latency from Tokyo

| Exchange | Server Location | Cloud | Latency from Tokyo |
|----------|----------------|-------|:------------------:|
| Binance | Tokyo, Japan | AWS ap-northeast-1 | **<1ms** |
| OKX | Hong Kong | Alibaba Cloud / AWS HK | ~35ms |
| Bybit | Singapore | AWS ap-southeast-1 | ~68ms |
| Bitget | Singapore | AWS ap-southeast-1 | ~68ms |
| KuCoin | Singapore | AWS | ~68ms |
| MEXC | Singapore | AWS | ~68ms |

### MEXC Geo-Restrictions

MEXC is **fully banned** in: Singapore, Hong Kong, US, Canada, China, North Korea, Iran, Cuba.
MEXC is **partially restricted** in: Japan (API works, but bot crackdown risk), Turkey (use mexc.fm domain).
MEXC is **fully accessible** in: Thailand, Vietnam, most of Europe.

Tokyo VPS: MEXC API access works but monitor for enforcement. Use `mexc.fm` domain as fallback.

### Production Plan: Contabo Tokyo (~$7.50/mo)

- **Specs**: 4 vCPU, 8 GB RAM, 75 GB NVMe, unlimited traffic (200Mbps)
- **Why**: Best value — 4× RAM needed, unlimited bandwidth for 6 WebSocket streams (~0.9 TB/mo)
- **Location**: Tokyo — <1ms to Binance, ~68ms to SG exchanges

### Optimized Plan: 3 VPS (~$22.50/mo)

| VPS | Location | Exchanges | Latency | Cost |
|-----|----------|-----------|---------|:----:|
| VPS 1 | Tokyo | Binance | <1ms | ~$7.50 |
| VPS 2 | Singapore | Bybit, Bitget, KuCoin, OKX | <1ms | ~$7.50 |
| VPS 3 | Bangkok | MEXC + **Orchestrator** | 25ms to SG, 91ms to Tokyo | ~$7.50 |

Bangkok orchestrator has lowest aggregate latency to all VPS locations (116ms total vs 159ms for Tokyo).

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
- **Bandwidth**: ~0.9 TB/mo estimated (6 exchanges × 60 symbols × ~1KB/update × 1/sec)

## Technology Stack

- **Language:** Python 3.12+
- **Async:** asyncio + websockets library
- **Dashboard:** React 18 + TypeScript + Vite + Tailwind CSS
- **Data:** CSV snapshots per exchange per symbol (1s intervals)
- **Architecture:** BaseFetcher with exchange-specific subclasses, ArbitrageMonitor reads all fetcher states, SymbolOptimizer handles symbol discovery/rotation/scoring, BalanceTracker simulates capital management
- **Output:** Real-time dashboard + XLSX export + console arbitrage table
