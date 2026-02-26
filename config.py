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

# MEXC Spot WebSocket — disabled (geo-blocked in Japan, re-add in Phase 2)
# MEXC_WS_URL: str = "wss://wbs-api.mexc.com/ws"
# MEXC_EXCHANGE_NAME: str = "MEXC"

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
    # "MEXC": 0.0005,    # 0.05% — disabled (geo-blocked in Japan)
    "Bitget": 0.0008,    # 0.08% (base 0.10%, 20% discount paying fees in BGB)
    "KuCoin": 0.0008,    # 0.08% (base 0.10%, 20% discount paying fees in KCS)
    "Gate.io": 0.0010,   # 0.10% (base tier, GT discount is minimal ~10%)
}

# Per-exchange fee model (D-05): where the exchange charges the taker fee
# "received" = fee deducted from received asset (most exchanges default)
# "spent" = fee added to spent amount
# "token" = fee from discount token (BNB, BGB, KCS) — full qty received
EXCHANGE_FEE_MODELS: dict[str, str] = {
    "Binance": "token",     # BNB fee payment enabled → fee from BNB balance
    "OKX": "received",      # Default: fee from received asset
    "Bybit": "received",    # Default: fee from received asset
    "Bitget": "token",      # BGB fee payment enabled → fee from BGB balance
    "KuCoin": "token",      # KCS fee payment enabled → fee from KCS balance
    "Gate.io": "received",  # GT discount is minimal, use default model
}

# Comprehensive fee configs for FeeManager (replaces flat dicts above)
DEFAULT_FEE_CONFIGS: dict[str, dict] = {
    "Binance": {
        "base_taker_rate": 0.001,
        "token_discount_enabled": True,
        "token_discount_pct": 0.25,
        "fee_mechanism": "instant",
        "fee_model": "token",
        "referral_enabled": False,
        "referral_cashback_pct": 0.0,
        "referral_settlement_minutes": 30,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": [],
    },
    "OKX": {
        "base_taker_rate": 0.001,
        "token_discount_enabled": False,
        "token_discount_pct": 0.0,
        "fee_mechanism": "tier",
        "fee_model": "received",
        "referral_enabled": False,
        "referral_cashback_pct": 0.0,
        "referral_settlement_minutes": 90,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": [],
    },
    "Bybit": {
        "base_taker_rate": 0.001,
        "token_discount_enabled": False,
        "token_discount_pct": 0.0,
        "fee_mechanism": "tier",
        "fee_model": "received",
        "referral_enabled": False,
        "referral_cashback_pct": 0.0,
        "referral_settlement_minutes": 720,
        "referral_paid_in": "USDT",
        "zero_fee_pairs": [],
    },
    "MEXC": {
        "base_taker_rate": 0.0005,
        "token_discount_enabled": False,
        "token_discount_pct": 0.20,
        "fee_mechanism": "instant",
        "fee_model": "received",
        "referral_enabled": False,
        "referral_cashback_pct": 0.0,
        "referral_settlement_minutes": 720,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": [],
    },
    "Bitget": {
        "base_taker_rate": 0.001,
        "token_discount_enabled": True,
        "token_discount_pct": 0.20,
        "fee_mechanism": "instant",
        "fee_model": "token",
        "referral_enabled": False,
        "referral_cashback_pct": 0.0,
        "referral_settlement_minutes": 1080,
        "referral_paid_in": "USDT",
        "zero_fee_pairs": [],
    },
    "KuCoin": {
        "base_taker_rate": 0.001,
        "token_discount_enabled": True,
        "token_discount_pct": 0.20,
        "fee_mechanism": "rebate",
        "fee_model": "token",
        "referral_enabled": False,
        "referral_cashback_pct": 0.0,
        "referral_settlement_minutes": 1080,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": [],
    },
    "Gate.io": {
        "base_taker_rate": 0.001,
        "token_discount_enabled": False,
        "token_discount_pct": 0.10,
        "fee_mechanism": "instant",
        "fee_model": "received",
        "referral_enabled": False,
        "referral_cashback_pct": 0.0,
        "referral_settlement_minutes": 0,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": ["BTCUSDT"],
    },
}

# All available exchanges and symbols (used by settings page)
ALL_EXCHANGES: list[str] = ["Binance", "OKX", "Bybit", "Bitget", "KuCoin", "Gate.io"]  # MEXC removed (geo-blocked)

# Active trading configuration (balance-tracked symbols/exchanges) — defaults
ACTIVE_EXCHANGES: list[str] = ["Binance", "OKX", "Bybit", "Bitget", "KuCoin", "Gate.io"]
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

# Execution mode: "simulation" (default), "demo" (testnet orders)
EXECUTION_MODE: str = "simulation"

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
    # "MEXC": 0.01,        # Polygon — disabled (geo-blocked in Japan)
    "Bitget": 0.10,        # Arbitrum (~$0.001 on-chain, Bitget markup ~$0.10)
    "KuCoin": 0.80,        # Polygon (cheapest KuCoin option, still expensive)
    "Gate.io": 0.05,       # Arbitrum/Polygon
}

# Dashboard WebSocket server
DASHBOARD_WS_PORT: int = 8765

# Dashboard authentication (loaded from .env)
import sys as _sys

import bcrypt as _bcrypt

DASHBOARD_USERNAME: str = os.environ.get("DASHBOARD_USERNAME", "admin")

# Password: prefer DASHBOARD_PASSWORD_HASH (bcrypt), fall back to legacy plaintext
_password_hash_env = os.environ.get("DASHBOARD_PASSWORD_HASH", "")
_password_plain_env = os.environ.get("DASHBOARD_PASSWORD", "")

if _password_hash_env:
    DASHBOARD_PASSWORD_HASH: bytes = _password_hash_env.encode("utf-8")
elif _password_plain_env:
    if _password_plain_env == "changeme":
        print(
            "SECURITY ERROR: Default password 'changeme' is not allowed.\n"
            "Set DASHBOARD_PASSWORD_HASH in .env. Generate with:\n"
            '  python -c "import bcrypt; print(bcrypt.hashpw(b\'YOUR_PASSWORD\', bcrypt.gensalt()).decode())"',
            file=_sys.stderr,
        )
        _sys.exit(1)
    print(
        "WARNING: DASHBOARD_PASSWORD is deprecated. Use DASHBOARD_PASSWORD_HASH instead.\n"
        "Generate hash: "
        'python -c "import bcrypt; print(bcrypt.hashpw(b\'YOUR_PASSWORD\', bcrypt.gensalt()).decode())"',
        file=_sys.stderr,
    )
    DASHBOARD_PASSWORD_HASH = _bcrypt.hashpw(
        _password_plain_env.encode("utf-8"), _bcrypt.gensalt()
    )
else:
    print(
        "SECURITY ERROR: No dashboard password configured.\n"
        "Set DASHBOARD_PASSWORD_HASH in .env.",
        file=_sys.stderr,
    )
    _sys.exit(1)


def verify_dashboard_password(password: str) -> bool:
    """Check a plaintext password against the stored bcrypt hash."""
    return _bcrypt.checkpw(password.encode("utf-8"), DASHBOARD_PASSWORD_HASH)

# Email notifications (loaded from .env)
SMTP_EMAIL: str = os.environ.get("SMTP_EMAIL", "")
SMTP_APP_PASSWORD: str = os.environ.get("SMTP_APP_PASSWORD", "")
NOTIFICATION_EMAIL: str = os.environ.get("NOTIFICATION_EMAIL", "")

# reCAPTCHA v2 (loaded from .env)
RECAPTCHA_SITE_KEY: str = os.environ.get("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY: str = os.environ.get("RECAPTCHA_SECRET_KEY", "")

# Trusted reverse proxy IPs (only trust X-Forwarded-For from these)
TRUSTED_PROXIES: list[str] = [
    p.strip()
    for p in os.environ.get("TRUSTED_PROXIES", "127.0.0.1,::1").split(",")
    if p.strip()
]

# Allowed WebSocket origins (CSRF protection)
_origins_env = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS: list[str] = (
    [o.strip() for o in _origins_env.split(",") if o.strip()] if _origins_env else []
)

# Dashboard bind host (default localhost — use 0.0.0.0 to expose directly)
DASHBOARD_BIND_HOST: str = os.environ.get("DASHBOARD_BIND_HOST", "127.0.0.1")

# Demo/testnet API keys (for portfolio comparison + Phase 2 order execution)
BINANCE_TESTNET_API_KEY: str = os.environ.get("BINANCE_TESTNET_API_KEY", "")
BINANCE_TESTNET_API_SECRET: str = os.environ.get("BINANCE_TESTNET_API_SECRET", "")
OKX_DEMO_API_KEY: str = os.environ.get("OKX_DEMO_API_KEY", "")
OKX_DEMO_API_SECRET: str = os.environ.get("OKX_DEMO_API_SECRET", "")
OKX_DEMO_PASSPHRASE: str = os.environ.get("OKX_DEMO_PASSPHRASE", "")
BYBIT_DEMO_API_KEY: str = os.environ.get("BYBIT_DEMO_API_KEY", "")
BYBIT_DEMO_API_SECRET: str = os.environ.get("BYBIT_DEMO_API_SECRET", "")

# Bitget demo API keys
BITGET_DEMO_API_KEY: str = os.environ.get("BITGET_DEMO_API_KEY", "")
BITGET_DEMO_API_SECRET: str = os.environ.get("BITGET_DEMO_API_SECRET", "")
BITGET_DEMO_PASSPHRASE: str = os.environ.get("BITGET_DEMO_PASSPHRASE", "")

# KuCoin sandbox API keys
KUCOIN_SANDBOX_API_KEY: str = os.environ.get("KUCOIN_SANDBOX_API_KEY", "")
KUCOIN_SANDBOX_API_SECRET: str = os.environ.get("KUCOIN_SANDBOX_API_SECRET", "")
KUCOIN_SANDBOX_PASSPHRASE: str = os.environ.get("KUCOIN_SANDBOX_PASSPHRASE", "")

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
