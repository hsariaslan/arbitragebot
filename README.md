# CoirnaBot

**v0.22.0-alpha** — Cross-exchange crypto arbitrage bot with real-time dashboard, demo order execution, and comprehensive fee/transfer management.

Monitors real-time prices across 9 crypto exchanges via WebSocket, detects price discrepancies, and executes simultaneous buy/sell orders to profit from the spread. Deployed on Bangkok VPS with auto-deploy via GitHub Actions. Supports simulation mode and demo/testnet execution with automatic discrepancy detection.

## Features

- **9 exchanges**: Bitfinex (0% fees), Binance, OKX, Bybit, MEXC, Bitget, KuCoin, Gate.io, Pionex (all via WebSocket)
- **60 symbols**: Tiered from BTC/ETH majors to volatile alts, all USDT pairs
- **Adaptive trading**: Dynamic trade sizing, smart rebalancing, dominant exchange detection
- **Symbol optimizer**: Auto-discovery, scoring, rotation, promotion/demotion with strong-only trading
- **Demo order execution**: Places real market orders on Binance/OKX/Bybit testnets in parallel, compares actual fill data with sim expectations
- **20 discrepancy types**: Automated detection of slippage, partial fills, order rejections, one-legged trades, latency, fee mismatches, and more
- **Exchange trading rules**: Lot size rounding, min notional validation, tick size correction, fee rate validation, withdrawal fee validation at startup
- **Real-time dashboard**: React/TypeScript SPA with URL routing (HashRouter), live portfolio, rankings with P&L charts (recharts), trade history, XLSX + markdown export, settings tooltips, fully responsive mobile UI
- **Demo/testnet comparison**: Fetches real portfolio from Binance/OKX/Bybit demo APIs, baseline-adjusted comparison with discrepancy detection
- **Comprehensive fee management**: Per-exchange fee configs with token discounts, referral cashbacks, zero-fee pairs, sim/real mode toggle, hot-apply from dashboard
- **Transfer fee management**: Per-exchange per-network withdrawal fees (flat/percentage/conditional), preferred network selection, hot-apply from dashboard
- **Anomaly protection**: 3-layer safety system — circuit breaker (rolling P&L), drawdown protection (peak-to-trough), per-symbol loss streak blocking. Manual stop/start, hard stop (convert all to USDT), distribute from Bitfinex
- **Zurich WebSocket proxy**: Oracle Cloud free-tier VPS in Zurich for low-latency Bitfinex data (0.7ms vs 1,200ms direct)
- **Dashboard security**: Login authentication, rate limiting, reCAPTCHA v2, IP whitelist, email alerts, auth logging

## Prerequisites

- Python 3.12+
- Node.js 18+ (for dashboard build)

## Setup

### 1. Clone and install Python dependencies

```bash
git clone <repo-url> coirnabot
cd coirnabot
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Required — generate hash: python -c "import bcrypt; print(bcrypt.hashpw(b'YOUR_PASSWORD', bcrypt.gensalt()).decode())"
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD_HASH=$2b$12$YOUR_BCRYPT_HASH_HERE

# Optional: Email notifications (Gmail SMTP)
SMTP_EMAIL=your-email@gmail.com
SMTP_APP_PASSWORD=your-app-password
NOTIFICATION_EMAIL=your-email@gmail.com

# Optional: reCAPTCHA v2 (appears after 3 failed login attempts)
RECAPTCHA_SITE_KEY=your-recaptcha-site-key
RECAPTCHA_SECRET_KEY=your-recaptcha-secret-key

# Optional: Security hardening
TRUSTED_PROXIES=127.0.0.1,::1
ALLOWED_ORIGINS=https://your-domain.com
DASHBOARD_BIND_HOST=127.0.0.1
```

**Gmail App Password**: Google Account > Security > 2-Step Verification > App Passwords

**reCAPTCHA v2 keys**: https://www.google.com/recaptcha/admin — choose "I'm not a robot" Checkbox, add your domain(s) and `localhost`

### 3. Build the dashboard

```bash
cd dashboard
npm install
npm run build
cd ..
```

### 4. Run

```bash
python run.py
```

Open `http://localhost:5173` (dev) or the built dashboard URL to access the dashboard.

Press `Ctrl+C` to stop gracefully.

## Project Structure

```
coirnabot/
  run.py                  # Entry point — starts all fetchers, monitor, optimizer, dashboard
  config.py               # All configuration constants (symbols, exchanges, fees, thresholds)
  fee_manager.py          # FeeManager — token discounts, referral cashbacks, zero-fee pairs
  transfer_fee_manager.py # TransferFeeManager — per-network withdrawal fees
  settings.py             # Runtime settings loader (settings.json)
  monitor.py              # ArbitrageMonitor — detects opportunities, executes simulated trades
  optimizer.py            # SymbolOptimizer — discovery, scoring, rotation, dominant pairs
  balance.py              # BalanceTracker — simulated capital management, rebalancing
  demo_fetcher.py         # Demo/testnet portfolio fetcher — REST API clients, baseline snapshots
  dashboard_server.py     # WebSocket server — auth, state broadcast, settings handler
  email_notifier.py       # Gmail SMTP notifications (login alerts, IP block alerts)
  state_manager.py        # Session state persistence — atomic save/load, periodic saves
  read_xlsx.py            # CLI tool to read exported XLSX files
  fetchers/
    base.py               # BaseFetcher abstract class
    binance.py            # Binance WebSocket fetcher
    okx.py                # OKX WebSocket fetcher
    bybit.py              # Bybit WebSocket fetcher
    mexc.py               # MEXC WebSocket fetcher
    bitget.py             # Bitget WebSocket fetcher
    kucoin.py             # KuCoin WebSocket fetcher (REST token + WS)
    gateio.py             # Gate.io WebSocket fetcher
    pionex.py             # Pionex WebSocket fetcher (aggregated from Binance)
    bitfinex.py           # Bitfinex WebSocket fetcher (0% fees, dual-connection)
  dashboard/
    src/
      App.tsx             # Main layout, HashRouter routing, restart reconnection
      types.ts            # TypeScript interfaces
      hooks/useWebSocket.ts  # WebSocket connection, auth flow, restart handling
      components/         # LoginPage, Header, SymbolRankings, RankingPage, PerformanceCharts, SettingsPage, Tooltip, etc.
      utils/exportXlsx.ts # XLSX export (21 sheets)
      utils/exportMarkdown.ts # Markdown table export for clipboard
```

## Dashboard Pages

| Page | Description |
|------|-------------|
| **Dashboard** (`/#/`) | Live portfolio P&L (sim + demo), demo exchange status, symbol rankings with Cur Net%, balance table, price grid, demo comparison, recent trades/transfers |
| **Rankings** (`/#/rankings`) | Rolling/historical rankings, performance charts (P&L, exchange profit), top-10 charts, exchange analysis, XLSX + markdown export |
| **Settings** (`/#/settings`) | General (trade amount, capital, optimizer parameters, adaptive mode, IP whitelist) + Fee Management + Transfer Fees. All settings have `?` tooltip descriptions |
| **Logs** | Unified log viewer: Bot Logs (real-time, filterable) and Auth Logs (login events, IP blocks) with export |

## Configuration

Runtime settings are in `settings.json` (auto-created on first run). Can be modified from the Settings page in the dashboard.

Key settings:
- `trade_amount_usd` — Base trade size per opportunity (default: $100)
- `total_capital` — Total simulated capital across exchanges (default: $1800)
- `adaptive_mode` — Dynamic trade sizing and smart rebalancing (default: true)
- `auto_rotate` — Automatic symbol discovery and rotation (default: true)
- `min_net_profit_pct` — Minimum net spread % to execute a trade (default: 0.02)

## License

Private — All rights reserved.
