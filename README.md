# CoirnaBot

**v0.1.0-alpha** — Cross-exchange crypto arbitrage bot with real-time dashboard.

Monitors real-time prices across multiple crypto exchanges via WebSocket, detects price discrepancies, and simulates simultaneous buy/sell orders to profit from the spread.

## Features

- **5 exchanges**: Binance, OKX, Bybit, Bitget, KuCoin (all via WebSocket)
- **60 symbols**: Tiered from BTC/ETH majors to volatile alts, all USDT pairs
- **Adaptive trading**: Dynamic trade sizing, smart rebalancing, dominant exchange detection
- **Symbol optimizer**: Auto-discovery, scoring, rotation, promotion/demotion with strong-only trading
- **Real-time dashboard**: React/TypeScript SPA with live portfolio, rankings, trade history, XLSX export
- **Dashboard security**: Login authentication, rate limiting, reCAPTCHA v2, IP whitelist, email alerts, auth logging

## Prerequisites

- Python 3.12+
- Node.js 18+ (for dashboard build)

## Setup

### 1. Clone and install Python dependencies

```bash
git clone <repo-url> coirnabot
cd coirnabot
pip install websockets
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Required
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=your-secure-password

# Optional: Email notifications (Gmail SMTP)
SMTP_EMAIL=your-email@gmail.com
SMTP_APP_PASSWORD=your-app-password
NOTIFICATION_EMAIL=your-email@gmail.com

# Optional: reCAPTCHA v2 (appears after 3 failed login attempts)
RECAPTCHA_SITE_KEY=your-recaptcha-site-key
RECAPTCHA_SECRET_KEY=your-recaptcha-secret-key
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
  settings.py             # Runtime settings loader (settings.json)
  monitor.py              # ArbitrageMonitor — detects opportunities, executes simulated trades
  optimizer.py            # SymbolOptimizer — discovery, scoring, rotation, dominant pairs
  balance.py              # BalanceTracker — simulated capital management, rebalancing
  dashboard_server.py     # WebSocket server — auth, state broadcast, settings handler
  email_notifier.py       # Gmail SMTP notifications (login alerts, IP block alerts)
  read_xlsx.py            # CLI tool to read exported XLSX files
  fetchers/
    base.py               # BaseFetcher abstract class
    binance.py            # Binance WebSocket fetcher
    okx.py                # OKX WebSocket fetcher
    bybit.py              # Bybit WebSocket fetcher
    bitget.py             # Bitget WebSocket fetcher
    kucoin.py             # KuCoin WebSocket fetcher (REST token + WS)
  dashboard/
    src/
      App.tsx             # Main layout, tab routing
      types.ts            # TypeScript interfaces
      hooks/useWebSocket.ts  # WebSocket connection and auth flow
      components/         # LoginPage, Header, SymbolRankings, RankingPage, SettingsPage, AuthLogPage, etc.
      utils/exportXlsx.ts # XLSX export (15 sheets)
```

## Dashboard Pages

| Page | Description |
|------|-------------|
| **Dashboard** | Live portfolio P&L, symbol rankings, balance table, price grid, recent trades/transfers |
| **Rankings** | Rolling/historical rankings, top-10 charts, lifecycle funnel, exchange analysis, XLSX export |
| **Settings** | Trade amount, capital, optimizer parameters, adaptive mode, IP whitelist |
| **Auth Log** | Authentication events: logins, failures, blocks, reconnections (filterable) |

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
