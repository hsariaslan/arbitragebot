"""
Configuration for the CoirnaBot real-time crypto price fetcher.

All symbols, exchange settings, and operational parameters.
"""

import os

# Trading symbols (Spot, USDT pairs) - 60 symbols sorted by 24h volume
# All available on 7/7 exchanges unless noted
SYMBOLS: list[str] = [
    # Tier 1 - High liquidity majors
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "BNBUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    # Tier 2 - Strong alts
    "AVAXUSDT",
    "LINKUSDT",
    "POLUSDT",
    "DOTUSDT",
    "NEARUSDT",
    "SUIUSDT",
    "APTUSDT",
    "TRXUSDT",
    # Tier 3 - Volatile alts
    "ARBUSDT",
    "OPUSDT",
    "FILUSDT",
    "ATOMUSDT",
    "INJUSDT",
    # Tier 4 - High volume additions (sorted by ~24h volume)
    "AAVEUSDT",
    "BCHUSDT",
    "PEPEUSDT",
    "ZECUSDT",       # 6/7 (not on Bybit)
    "LTCUSDT",
    "HYPEUSDT",      # 6/7 (not on Binance)
    "XLMUSDT",
    "UNIUSDT",
    "ENAUSDT",
    "SNXUSDT",
    "TONUSDT",
    "SHIBUSDT",
    "ICPUSDT",
    "ETCUSDT",
    "TRUMPUSDT",
    "HBARUSDT",
    "CHZUSDT",
    "AXSUSDT",
    "PENGUUSDT",
    "WLDUSDT",
    "WIFUSDT",
    "RENDERUSDT",
    "ONDOUSDT",
    "STRKUSDT",
    "CRVUSDT",
    "ARUSDT",
    "FETUSDT",
    "LDOUSDT",
    "ALGOUSDT",
    "EIGENUSDT",
    "PENDLEUSDT",
    "APEUSDT",
    "TIAUSDT",
    "FLOKIUSDT",
    "WUSDT",
    "GRTUSDT",
    "ORDIUSDT",
    "JUPUSDT",
    "COMPUSDT",
    "DYDXUSDT",
]

# Snapshot interval - how often to write CSV rows and print to console
SNAPSHOT_INTERVAL_SECONDS: float = 1.0

# Maximum age (seconds) before exchange data is considered stale and skipped
MAX_DATA_AGE_SECONDS: float = 10.0

# Base output directory for CSV data
DATA_DIR: str = "data"

# Binance Spot WebSocket
BINANCE_WS_BASE_URL: str = "wss://stream.binance.com:9443/stream"
BINANCE_EXCHANGE_NAME: str = "Binance"

# OKX Spot WebSocket
OKX_WS_URL: str = "wss://ws.okx.com:8443/ws/v5/public"
OKX_EXCHANGE_NAME: str = "OKX"

# Bybit Spot WebSocket
BYBIT_WS_URL: str = "wss://stream.bybit.com/v5/public/spot"
BYBIT_EXCHANGE_NAME: str = "Bybit"

# MEXC Spot WebSocket
MEXC_WS_URL: str = "wss://wbs-api.mexc.com/ws"
MEXC_EXCHANGE_NAME: str = "MEXC"

# Bitget Spot WebSocket (v2 API)
BITGET_WS_URL: str = "wss://ws.bitget.com/v2/ws/public"
BITGET_EXCHANGE_NAME: str = "Bitget"

# KuCoin Spot WebSocket (requires REST token first)
KUCOIN_TOKEN_URL: str = "https://api.kucoin.com/api/v1/bullet-public"
KUCOIN_EXCHANGE_NAME: str = "KuCoin"

# Gate.io Spot WebSocket (v4 API)
GATEIO_WS_URL: str = "wss://api.gateio.ws/ws/v4/"
GATEIO_EXCHANGE_NAME: str = "Gate.io"

# Arbitrage monitor refresh interval
MONITOR_INTERVAL_SECONDS: float = 1.0

# Simulation settings
TRADE_AMOUNT_USD: float = 100.0  # Simulated trade size

# Exchange taker fees (used for both buy and sell in simulation)
# Rates reflect available token-based discounts where applicable
EXCHANGE_TAKER_FEES: dict[str, float] = {
    "Binance": 0.00075,  # 0.075% (base 0.10%, 25% discount paying fees in BNB)
    "OKX": 0.0010,       # 0.10% (base tier, OKB discount requires 500 OKB ~$25k)
    "Bybit": 0.0010,     # 0.10% (MNT/BIT discount NOT available for API users)
    "MEXC": 0.0005,      # 0.05% (base tier, already lowest)
    "Bitget": 0.0008,    # 0.08% (base 0.10%, 20% discount paying fees in BGB)
    "KuCoin": 0.0008,    # 0.08% (base 0.10%, 20% discount paying fees in KCS)
    "Gate.io": 0.0010,   # 0.10% (base tier, GT discount is minimal ~10%)
}

# All available exchanges and symbols (used by settings page)
ALL_EXCHANGES: list[str] = ["Binance", "OKX", "Bybit", "MEXC", "Bitget", "KuCoin", "Gate.io"]

# Active trading configuration (balance-tracked symbols/exchanges) — defaults
ACTIVE_EXCHANGES: list[str] = ["Binance", "OKX", "Bybit", "Bitget", "KuCoin"]
ACTIVE_SYMBOLS: list[str] = ["SNXUSDT", "DYDXUSDT", "PENDLEUSDT", "AXSUSDT"]

# Settings file path
SETTINGS_FILE: str = "settings.json"

# Symbol optimizer (auto-rotation)
NUM_ACTIVE_SYMBOLS: int = 3
SCORING_WINDOW_SECONDS: int = 1800        # 30-minute rolling window
EVALUATION_INTERVAL_SECONDS: int = 300    # Check rotation every 5 minutes
MIN_WARMUP_TICKS: int = 30               # Wait 30s before first evaluation
ROTATION_SAFETY_MULTIPLIER: float = 2.0  # Hourly gain must exceed 2× switching cost
AUTO_ROTATE: bool = True
DISCOVERY_DURATION_SECONDS: int = 300    # 5-minute discovery stage at startup
MAX_ACTIVE_SYMBOLS: int = 8             # Upper bound for dynamic expansion
MIN_REBALANCE_SCORE: float = 0.0001     # Min score to justify transfer fees
CONFIRMATION_PERIOD_SECONDS: int = 300   # How long a candidate must sustain high score
PROMOTION_THRESHOLD: float = 0.0001      # Min score to enter watchlist
DEMOTION_THRESHOLD: float = 0.0          # Score below which demotion timer starts
DEMOTION_PERIOD_SECONDS: int = 600       # How long below threshold before demotion
MIN_NET_PROFIT_PCT: float = 0.02         # Min net% to execute a trade (filter marginal)
REBALANCE_COOLDOWN_SECONDS: float = 30   # Seconds between rebalances per exchange/direction
REBALANCE_ROI_HORIZON: int = 1800        # Max seconds to recoup rebalance cost
ADAPTIVE_MODE: bool = True               # Enable adaptive trade sizing and smart rebalancing

# Balance management
TOTAL_CAPITAL: float = 1800.0               # Total capital across all exchanges
INITIAL_BALANCE_PER_SYMBOL: float = 160.0  # $160 per symbol per exchange (split 50/50)
REBALANCE_AMOUNT: float = 200.0            # Transfer $200 when rebalancing (2× trade size)
REBALANCE_THRESHOLD: float = 50.0          # Trigger rebalance when below $50 buffer

# USDT withdrawal fees (cheapest available network per exchange)
# Binance: BEP20 $0.01 | OKX: Arbitrum ~$0.004 | Bybit: Aptos $0 promo or BEP20 $0.20
# MEXC: Polygon $0.007 | Bitget: Arbitrum ~$0.10 | KuCoin: Polygon $0.80 (expensive!)
# Gate.io: Arbitrum/Polygon $0.05
USDT_WITHDRAWAL_FEES: dict[str, float] = {
    "Binance": 0.01,       # BEP20
    "OKX": 0.01,           # Arbitrum (~$0.004 on-chain)
    "Bybit": 0.20,         # BEP20 (Aptos $0 promo available but may expire)
    "MEXC": 0.01,          # Polygon ($0.007) or BEP20 ($0.01)
    "Bitget": 0.10,        # Arbitrum (~$0.001 on-chain, Bitget markup ~$0.10)
    "KuCoin": 0.80,        # Polygon (cheapest KuCoin option, still expensive)
    "Gate.io": 0.05,       # Arbitrum/Polygon
}

# Dashboard WebSocket server
DASHBOARD_WS_PORT: int = 8765

# Dashboard authentication (loaded from .env)
DASHBOARD_USERNAME: str = os.environ.get("DASHBOARD_USERNAME", "admin")
DASHBOARD_PASSWORD: str = os.environ.get("DASHBOARD_PASSWORD", "changeme")

# Email notifications (loaded from .env)
SMTP_EMAIL: str = os.environ.get("SMTP_EMAIL", "")
SMTP_APP_PASSWORD: str = os.environ.get("SMTP_APP_PASSWORD", "")
NOTIFICATION_EMAIL: str = os.environ.get("NOTIFICATION_EMAIL", "")

# reCAPTCHA v2 (loaded from .env)
RECAPTCHA_SITE_KEY: str = os.environ.get("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY: str = os.environ.get("RECAPTCHA_SECRET_KEY", "")

# Reconnection settings (exponential backoff)
RECONNECT_INITIAL_DELAY: float = 1.0
RECONNECT_MAX_DELAY: float = 60.0
RECONNECT_BACKOFF_FACTOR: float = 2.0

# CSV output columns
CSV_COLUMNS: list[str] = [
    "timestamp",
    "bid",
    "ask",
    "bid_qty",
    "ask_qty",
    "last_price",
    "volume",
]
