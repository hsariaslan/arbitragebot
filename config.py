"""
Configuration for the CoirnaBot real-time crypto price fetcher.

All symbols, exchange settings, and operational parameters.
"""

import os

__version__ = "0.23.1-alpha"

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

# Pionex Spot WebSocket (public stream)
PIONEX_WS_URL: str = "wss://ws.pionex.com/wsPub"
PIONEX_EXCHANGE_NAME: str = "Pionex"

# Bitfinex Spot WebSocket (v2 public API)
BITFINEX_WS_URL: str = os.environ.get("BITFINEX_WS_URL", "wss://api-pub.bitfinex.com/ws/2")
BITFINEX_EXCHANGE_NAME: str = "Bitfinex"

# Arbitrage monitor refresh interval
MONITOR_INTERVAL_SECONDS: float = 1.0

# Simulation settings
TRADE_AMOUNT_USD: float = 100.0  # Simulated trade size
TRADE_AMOUNT_PCT: float = 0.0  # 0 = disabled, >0 = fraction of total_capital (e.g. 0.01 = 1%)

# Exchange taker fees (used for both buy and sell in simulation)
# Rates reflect available token-based discounts where applicable
EXCHANGE_TAKER_FEES: dict[str, float] = {
    "Binance": 0.00075,  # 0.075% (base 0.10%, 25% discount paying fees in BNB)
    "OKX": 0.0010,       # 0.10% (base tier, OKB discount requires 500 OKB ~$25k)
    "Bybit": 0.0010,     # 0.10% (MNT/BIT discount NOT available for API users)
    "MEXC": 0.0005,      # 0.05% (no discount token needed, already lowest tier)
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
    "Gate.io": "token",      # GT debit enabled → fee from GT balance
}

# Comprehensive fee configs for FeeManager (replaces flat dicts above)
DEFAULT_FEE_CONFIGS: dict[str, dict] = {
    "Binance": {
        "base_taker_rate": 0.001,
        "token_discount_enabled": True,
        "token_discount_pct": 0.25,
        "fee_mechanism": "instant",
        "fee_model": "token",
        "referral_enabled": True,
        "referral_cashback_pct": 0.20,  # 20% cashback, hourly settlement
        "referral_settlement_minutes": 60,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": [],
        "enabled": True,
    },
    "OKX": {
        "base_taker_rate": 0.001,
        "token_discount_enabled": False,
        "token_discount_pct": 0.0,
        "fee_mechanism": "tier",
        "fee_model": "received",
        "referral_enabled": True,
        "referral_cashback_pct": 0.20,  # 20% cashback, ~90min settlement
        "referral_settlement_minutes": 90,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": [],
        "enabled": True,
    },
    "Bybit": {
        "base_taker_rate": 0.001,
        "token_discount_enabled": False,
        "token_discount_pct": 0.0,
        "fee_mechanism": "tier",
        "fee_model": "received",
        "referral_enabled": True,
        "referral_cashback_pct": 0.20,  # 20% cashback, daily settlement
        "referral_settlement_minutes": 1440,
        "referral_paid_in": "USDT",
        "zero_fee_pairs": [],
        "enabled": True,
    },
    "MEXC": {
        "base_taker_rate": 0.0005,
        "token_discount_enabled": False,
        "token_discount_pct": 0.20,
        "fee_mechanism": "instant",
        "fee_model": "received",
        "referral_enabled": True,
        "referral_cashback_pct": 0.20,  # 20% cashback, daily settlement
        "referral_settlement_minutes": 1440,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": [],
        "enabled": True,
    },
    "Bitget": {
        "base_taker_rate": 0.001,
        "token_discount_enabled": True,
        "token_discount_pct": 0.20,
        "fee_mechanism": "instant",
        "fee_model": "token",
        "referral_enabled": True,
        "referral_cashback_pct": 0.20,  # 20% instant fee discount
        "referral_settlement_minutes": 0,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": [],
        "enabled": True,
    },
    "KuCoin": {
        "base_taker_rate": 0.001,
        "token_discount_enabled": True,
        "token_discount_pct": 0.20,
        "fee_mechanism": "rebate",
        "fee_model": "token",
        "referral_enabled": True,
        "referral_cashback_pct": 0.20,  # 20% cashback, daily settlement
        "referral_settlement_minutes": 1440,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": [],
        "enabled": True,
    },
    "Gate.io": {
        "base_taker_rate": 0.001,
        "token_discount_enabled": True,  # GT token 10% discount at VIP 0
        "token_discount_pct": 0.10,
        "fee_mechanism": "instant",
        "fee_model": "token",  # GT debit: fee paid from GT balance
        "referral_enabled": True,
        "referral_cashback_pct": 0.20,  # 20% cashback, daily settlement
        "referral_settlement_minutes": 1440,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": ["BTCUSDT"],
        "enabled": True,
    },
    "Pionex": {
        "base_taker_rate": 0.0005,  # 0.05% base (VIP tiers exist but volume-gated)
        "token_discount_enabled": False,  # No native discount token
        "token_discount_pct": 0.0,
        "fee_mechanism": "instant",
        "fee_model": "received",
        "referral_enabled": True,
        "referral_cashback_pct": 0.20,  # 20% cashback, hourly settlement
        "referral_settlement_minutes": 60,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": [],
        "enabled": True,
    },
    "Bitfinex": {
        "base_taker_rate": 0.0,  # 0.00% permanent since Dec 17, 2025
        "token_discount_enabled": False,
        "token_discount_pct": 0.0,
        "fee_mechanism": "instant",
        "fee_model": "received",
        "referral_enabled": False,  # 0% fees, no cashback needed
        "referral_cashback_pct": 0.0,
        "referral_settlement_minutes": 0,
        "referral_paid_in": "same_as_fee",
        "zero_fee_pairs": [],
        "enabled": True,
    },
}

# All available exchanges and symbols (used by settings page)
ALL_EXCHANGES: list[str] = ["Binance", "OKX", "Bybit", "MEXC", "Bitget", "KuCoin", "Gate.io", "Pionex", "Bitfinex"]

# Active trading configuration (balance-tracked symbols/exchanges) — defaults
ACTIVE_EXCHANGES: list[str] = ["Binance", "OKX", "Bybit", "MEXC", "Bitget", "KuCoin", "Gate.io", "Pionex", "Bitfinex"]
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
SCORE_STABILITY_SECONDS: int = 120      # Min observation time before activation
SCORE_STABILITY_FACTOR: float = 0.5     # Reject if current < peak × this
PROMOTION_THRESHOLD: float = 0.0001      # Min score to enter watchlist
DEMOTION_THRESHOLD: float = 0.0          # Score below which demotion timer starts
DEMOTION_PERIOD_SECONDS: int = 600       # How long below threshold before demotion
MIN_NET_PROFIT_PCT: float = 0.02         # Min net% to execute a trade (filter marginal)
REBALANCE_COOLDOWN_SECONDS: float = 30   # Seconds between rebalances per exchange/direction
REBALANCE_ROI_HORIZON: int = 1800        # Max seconds to recoup rebalance cost
ADAPTIVE_MODE: bool = True               # Enable adaptive trade sizing and smart rebalancing
NET_PCT_SIZING_ENABLED: bool = True      # Scale trade size based on current tick net%
NET_PCT_MULTIPLIER_CAP: float = 2.5      # Max net%-based trade size multiplier

# Score thresholds (configurable via settings page)
TRADING_SCORE_THRESHOLD: float = 0.01    # Min score to trade/rebalance
STRONG_SCORE_THRESHOLD: float = 0.1      # Strong tier threshold
VERY_STRONG_SCORE_THRESHOLD: float = 0.3 # Very strong tier threshold

# Net P&L gate params (configurable via settings page)
NET_PNL_GATE_WARMUP_TRADES: int = 10     # Min trades before net P&L gate activates
NET_PNL_GATE_GRACE_SECONDS: int = 1800   # Grace period (seconds) before gate activates
REBALANCE_ROI_DIVISOR: int = 3           # ROI threshold = fee_rate / divisor (higher = easier rebalance)

# Profitability controls (configurable via settings page)
REALLOCATION_COST_HORIZON: float = 2.0    # Hours of profit to justify reallocation cost
DEMOTION_COOLDOWN_MULTIPLIER: float = 5.0 # Cooldown after demotion = period × multiplier
HOURLY_EXTERNAL_TRANSFER_CAP: float = 2.0 # Max external withdrawal fees per hour ($), 0=disabled
BITFINEX_RESERVE_PCT: float = 0.15        # Keep 15% of capital as USDT on Bitfinex (free withdrawals)
BITFINEX_RESERVE_HARD_FLOOR: float = 0.05 # Never drain below 5% in emergency draws

# Simulation realism (configurable via settings page)
SPREAD_PERSISTENCE_TICKS: int = 1           # Consecutive ticks spread must persist before executing (0=instant)
EVENT_DRIVEN_SELLER_PENALTY_PCT: float = 0.05  # Scoring penalty % when event-driven exchange is seller
ONE_LEG_FAILURE_RATE: float = 0.02          # Probability of simulated one-legged failure per trade (0=disabled)
ONE_LEG_UNWIND_SLIPPAGE_MULT: float = 1.5   # Slippage multiplier for emergency unwind trades
MAX_POSITION_MULTIPLIER: float = 5.0        # Max accumulated crypto per symbol per buyer exchange (× trade_amount, 0=unlimited)

# Anomaly protection (configurable via settings page)
ANOMALY_PROTECTION_ENABLED: bool = True
CIRCUIT_BREAKER_WINDOW: int = 900            # Rolling P&L window in seconds (15min)
CIRCUIT_BREAKER_THRESHOLD: float = -5.0      # Global pause if rolling P&L < -$5
CIRCUIT_BREAKER_RESUME_PCT: float = 0.5      # Auto-resume at 50% of threshold
CIRCUIT_BREAKER_COOLDOWN: int = 300          # Min seconds before auto-resume (5min)
DRAWDOWN_THRESHOLD_PCT: float = 5.0          # Global pause at 5% drawdown from peak
DRAWDOWN_RESUME_PCT: float = 3.0             # Auto-resume when drawdown recovers to 3%
DRAWDOWN_EMERGENCY_MULT: float = 2.0         # Emergency sell-all at 2× threshold (10%)
SYMBOL_LOSS_STREAK_THRESHOLD: int = 4        # Block symbol after 4 consecutive losses
SYMBOL_LOSS_STREAK_COOLDOWN: int = 300       # Per-symbol block duration (5min)
WARNING_PNL_PCT: float = 0.5                 # Warning (trade size ×0.5) at 50% of CB threshold

# Execution mode: "simulation" (default), "demo" (testnet orders)
EXECUTION_MODE: str = "simulation"

# Balance management
TOTAL_CAPITAL: float = 1800.0               # Total capital across all exchanges
INITIAL_BALANCE_PER_SYMBOL: float = 160.0  # $160 per symbol per exchange (split 50/50)
REBALANCE_AMOUNT: float = 200.0            # Transfer $200 when rebalancing (2× trade size)
REBALANCE_THRESHOLD: float = 50.0          # Trigger rebalance when below $50 buffer

# DEPRECATED: Use TransferFeeManager via DEFAULT_TRANSFER_CONFIGS instead.
# Kept for backward compatibility reference only.
USDT_WITHDRAWAL_FEES: dict[str, float] = {
    "Binance": 0.01, "OKX": 0.30, "Bybit": 0.20,
    "Bitget": 0.001, "KuCoin": 0.40, "Gate.io": 0.50,
}

# ── Per-exchange per-network USDT withdrawal fee configs ──────────────
# Verified Feb 2026 from official APIs. See TRANSFER_FEES.md for full details.
# Each exchange has multiple networks with different fees/speeds/conditions.
# fee_type: "flat" (fixed USD), "percentage" (rate + min), "conditional" (free if >= min_withdrawal)
#
# Network shorthand: _n(network, fee, speed, min_w, fee_type, pct_rate, pct_min, notes)
def _n(
    network: str, fee: float, speed: float = 3.0, min_w: float = 10.0,
    fee_type: str = "flat", pct_rate: float = 0.0, pct_min: float = 0.0,
    notes: str = "",
) -> dict:
    return {
        "network": network, "fee": fee, "fee_type": fee_type,
        "percentage_rate": pct_rate, "percentage_min": pct_min,
        "min_withdrawal": min_w, "speed_seconds": speed,
        "enabled": True, "notes": notes,
    }

DEFAULT_TRANSFER_CONFIGS: dict[str, dict] = {
    # ── Binance (17 networks, confirmed) ──
    "Binance": {
        "preferred_network": "auto",
        "networks": [
            _n("BEP20", 0.01, 3),
            _n("Plasma", 0.012, 1),
            _n("opBNB", 0.015, 1),
            _n("Aptos", 0.02, 1),
            _n("Kaia", 0.02, 2),
            _n("AVAX C-Chain", 0.04, 2),
            _n("Optimism", 0.04, 2),
            _n("Celo", 0.05, 5),
            _n("Polygon", 0.07, 3),
            _n("Tezos", 0.10, 30),
            _n("Scroll", 0.10, 2),
            _n("Arbitrum", 0.10, 1),
            _n("Kava", 0.20, 6),
            _n("NEAR", 0.20, 1),
            _n("Solana", 0.30, 1),
            _n("ERC20", 0.50, 12),
            _n("TRC20", 1.00, 5),
        ],
    },
    # ── OKX (8 networks, dynamic fees — conservative estimates) ──
    "OKX": {
        "preferred_network": "auto",
        "networks": [
            _n("Polygon", 0.10, 3, notes="dynamic $0.01-0.10"),
            _n("Solana", 0.10, 1, notes="dynamic"),
            _n("BEP20", 0.30, 3, notes="dynamic $0.20-0.50"),
            _n("AVAX C-Chain", 0.30, 2, notes="dynamic"),
            _n("Arbitrum", 0.50, 1, notes="dynamic"),
            _n("Optimism", 0.50, 2, notes="dynamic"),
            _n("TRC20", 1.00, 5, notes="dynamic $0.10-2.30"),
            _n("ERC20", 3.00, 12, notes="dynamic"),
        ],
    },
    # ── Bybit (9 networks, dynamic fees) ──
    "Bybit": {
        "preferred_network": "auto",
        "networks": [
            _n("Aptos", 0.00, 1, notes="promo, may expire"),
            _n("Plasma", 0.00, 1, notes="likely supported"),
            _n("BEP20", 0.20, 3, notes="dynamic $0.20-0.50"),
            _n("Arbitrum", 0.50, 1, notes="dynamic"),
            _n("Optimism", 0.50, 2, notes="dynamic"),
            _n("Polygon", 0.50, 3, notes="dynamic"),
            _n("Solana", 0.50, 1, notes="dynamic"),
            _n("TRC20", 1.60, 5, notes="confirmed"),
            _n("ERC20", 3.00, 12, notes="estimated"),
        ],
    },
    # ── MEXC (6 networks, geo-blocked) ──
    "MEXC": {
        "preferred_network": "auto",
        "networks": [
            _n("Arbitrum", 0.00, 1, notes="permanent free"),
            _n("Polygon", 0.007, 3, notes="very cheap"),
            _n("BEP20", 0.00, 3, notes="promo"),
            _n("Solana", 0.01, 1, notes="near-zero"),
            _n("TRC20", 1.00, 5),
            _n("ERC20", 3.00, 12, notes="estimated"),
        ],
    },
    # ── Bitget (12 networks, API-verified) ──
    "Bitget": {
        "preferred_network": "auto",
        "networks": [
            _n("Plasma", 0.001, 1, notes="verified, cheapest"),
            _n("Aptos", 0.03, 1, notes="verified"),
            _n("Morph", 0.10, 2, notes="verified"),
            _n("AVAX C-Chain", 0.11, 2, notes="verified"),
            _n("BEP20", 0.15, 3, notes="verified"),
            _n("Arbitrum", 0.15, 1, notes="verified"),
            _n("Optimism", 0.15, 2, notes="verified"),
            _n("TON", 0.15, 2, notes="verified"),
            _n("Polygon", 0.20, 3, notes="verified"),
            _n("Solana", 1.00, 1, notes="verified"),
            _n("TRC20", 1.50, 5, notes="verified"),
            _n("ERC20", 1.60, 12, notes="verified"),
        ],
    },
    # ── KuCoin (16 networks, API-verified) ──
    "KuCoin": {
        "preferred_network": "auto",
        "networks": [
            _n("Plasma", 0.40, 1, 5, notes="verified"),
            _n("KCC", 0.50, 3, 1, notes="verified"),
            _n("Aptos", 0.50, 1, 1, notes="verified"),
            _n("NEAR", 0.50, 1, 3, notes="verified"),
            _n("TON", 0.50, 2, 1, notes="verified"),
            _n("Polygon", 0.80, 3, 1.6, notes="verified"),
            _n("BEP20", 1.00, 3, notes="verified"),
            _n("Arbitrum", 1.00, 1, 5, notes="verified"),
            _n("Optimism", 1.00, 2, 3, notes="verified"),
            _n("AVAX C-Chain", 1.00, 2, 2, notes="verified"),
            _n("KAVA EVM", 1.00, 3, 3, notes="verified"),
            _n("Polkadot", 1.00, 5, 10, notes="verified"),
            _n("Tezos", 1.00, 30, 2, notes="verified"),
            _n("Solana", 1.50, 1, 3, notes="verified"),
            _n("TRC20", 1.50, 5, 3, notes="verified"),
            _n("ERC20", 5.50, 12, 30, "percentage", 0.002, 5.50, "verified, 0.2% rate"),
        ],
    },
    # ── Gate.io (8 networks) ──
    "Gate.io": {
        "preferred_network": "auto",
        "networks": [
            _n("TRC20", 0.00, 5, 2020, "conditional", notes="free if >= 2,020 USDT"),
            _n("BEP20", 0.50, 3, notes="promo may have expired"),
            _n("Arbitrum", 0.50, 1, notes="estimated"),
            _n("Optimism", 0.50, 2, notes="estimated"),
            _n("Polygon", 0.50, 3, notes="estimated"),
            _n("Solana", 0.50, 1, notes="estimated"),
            _n("AVAX C-Chain", 0.50, 2, notes="estimated"),
            _n("ERC20", 4.00, 12, notes="estimated"),
        ],
    },
    # ── Pionex (6 networks, estimated) ──
    "Pionex": {
        "preferred_network": "auto",
        "networks": [
            _n("Arbitrum", 0.20, 1, notes="estimated <$0.20"),
            _n("Optimism", 0.20, 2, notes="estimated <$0.20"),
            _n("BEP20", 0.80, 3, notes="confirmed"),
            _n("TRC20", 1.00, 5, notes="confirmed"),
            _n("Solana", 1.00, 1, notes="estimated"),
            _n("ERC20", 10.00, 12, notes="confirmed, avoid"),
        ],
    },
    # ── Bitfinex (15 networks, most free via USDT0) ──
    "Bitfinex": {
        "preferred_network": "auto",
        "networks": [
            _n("TRC20", 0.00, 5, notes="free"),
            _n("Arbitrum", 0.00, 1, notes="free via USDT0"),
            _n("Optimism", 0.00, 1, notes="free via USDT0"),
            _n("Polygon", 0.00, 3, notes="free via USDT0"),
            _n("Avalanche", 0.00, 2, notes="free"),
            _n("TON", 0.00, 2, notes="free"),
            _n("Aptos", 0.00, 2, notes="free"),
            _n("Near", 0.00, 2, notes="free"),
            _n("Solana", 0.00, 1, notes="free, some sources say $0.50"),
            _n("Cosmos", 0.00, 3, notes="free"),
            _n("Tezos", 0.00, 3, notes="free"),
            _n("Polkadot", 0.00, 3, notes="free"),
            _n("Celo", 0.00, 3, notes="free"),
            _n("Kava", 0.00, 3, notes="free"),
            _n("ERC20", 0.50, 12, notes="dynamic, ~$0.50, only network with fee"),
        ],
    },
}

# Clean up helper from module namespace
del _n

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
