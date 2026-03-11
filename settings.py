"""
Settings manager for ArbitrageBot.

Loads/saves runtime configuration from settings.json.
Falls back to config.py defaults when settings.json is missing or incomplete.
"""

import json
import logging
from pathlib import Path

from config import (
    ADAPTIVE_MODE,
    ANOMALY_PROTECTION_ENABLED,
    AUTO_ROTATE,
    CIRCUIT_BREAKER_COOLDOWN,
    CIRCUIT_BREAKER_RESUME_PCT,
    CIRCUIT_BREAKER_THRESHOLD,
    CIRCUIT_BREAKER_WINDOW,
    CONFIRMATION_PERIOD_SECONDS,
    SCORE_STABILITY_FACTOR,
    SCORE_STABILITY_SECONDS,
    DEFAULT_FEE_CONFIGS,
    DEFAULT_TRANSFER_CONFIGS,
    DEMOTION_COOLDOWN_MULTIPLIER,
    DEMOTION_PERIOD_SECONDS,
    DEMOTION_THRESHOLD,
    DISCOVERY_DURATION_SECONDS,
    DRAWDOWN_EMERGENCY_MULT,
    DRAWDOWN_RESUME_PCT,
    DRAWDOWN_THRESHOLD_PCT,
    EVALUATION_INTERVAL_SECONDS,
    EVENT_DRIVEN_SELLER_PENALTY_PCT,
    FEE_THRESHOLD_MULTIPLIER,
    BITFINEX_RESERVE_HARD_FLOOR,
    BITFINEX_RESERVE_PCT,
    HOURLY_EXTERNAL_TRANSFER_CAP,
    MAX_ACTIVE_SYMBOLS,
    MAX_POSITION_MULTIPLIER,
    NET_PCT_MULTIPLIER_CAP,
    NET_PCT_SIZING_ENABLED,
    MIN_NET_PROFIT_PCT,
    MIN_REBALANCE_SCORE,
    NET_PNL_GATE_GRACE_SECONDS,
    NET_PNL_GATE_WARMUP_TRADES,
    REALLOCATION_COST_HORIZON,
    REBALANCE_ROI_DIVISOR,
    NUM_ACTIVE_SYMBOLS,
    ONE_LEG_FAILURE_RATE,
    ONE_LEG_UNWIND_SLIPPAGE_MULT,
    PROMOTION_THRESHOLD,
    REBALANCE_COOLDOWN_SECONDS,
    REBALANCE_ROI_HORIZON,
    ROTATION_SAFETY_MULTIPLIER,
    SCORING_WINDOW_SECONDS,
    SETTINGS_FILE,
    SPREAD_PERSISTENCE_TICKS,
    STRONG_SCORE_THRESHOLD,
    SYMBOL_LOSS_STREAK_COOLDOWN,
    SYMBOL_LOSS_STREAK_THRESHOLD,
    TOTAL_CAPITAL,
    TRADE_AMOUNT_PCT,
    TRADE_AMOUNT_USD,
    TRADING_SCORE_THRESHOLD,
    VERY_STRONG_SCORE_THRESHOLD,
    WARNING_PNL_PCT,
)

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS: dict = {
    "trade_amount_usd": TRADE_AMOUNT_USD,
    "trade_amount_pct": TRADE_AMOUNT_PCT,
    "total_capital": TOTAL_CAPITAL,
    "auto_rotate": AUTO_ROTATE,
    "num_active_symbols": NUM_ACTIVE_SYMBOLS,
    "max_active_symbols": MAX_ACTIVE_SYMBOLS,
    "scoring_window": SCORING_WINDOW_SECONDS,
    "evaluation_interval": EVALUATION_INTERVAL_SECONDS,
    "safety_multiplier": ROTATION_SAFETY_MULTIPLIER,
    "discovery_duration": DISCOVERY_DURATION_SECONDS,
    "min_rebalance_score": MIN_REBALANCE_SCORE,
    "confirmation_period": CONFIRMATION_PERIOD_SECONDS,
    "score_stability_seconds": SCORE_STABILITY_SECONDS,
    "score_stability_factor": SCORE_STABILITY_FACTOR,
    "promotion_threshold": PROMOTION_THRESHOLD,
    "demotion_threshold": DEMOTION_THRESHOLD,
    "demotion_period": DEMOTION_PERIOD_SECONDS,
    "min_net_profit_pct": MIN_NET_PROFIT_PCT,
    "rebalance_cooldown": REBALANCE_COOLDOWN_SECONDS,
    "min_misses_before_rebalance": 15,
    "rebalance_roi_horizon": REBALANCE_ROI_HORIZON,
    "adaptive_mode": ADAPTIVE_MODE,
    "trading_score_threshold": TRADING_SCORE_THRESHOLD,
    "strong_score_threshold": STRONG_SCORE_THRESHOLD,
    "very_strong_score_threshold": VERY_STRONG_SCORE_THRESHOLD,
    "fee_threshold_multiplier": FEE_THRESHOLD_MULTIPLIER,
    "net_pnl_gate_warmup_trades": NET_PNL_GATE_WARMUP_TRADES,
    "net_pnl_gate_grace_seconds": NET_PNL_GATE_GRACE_SECONDS,
    "rebalance_roi_divisor": REBALANCE_ROI_DIVISOR,
    "reallocation_cost_horizon": REALLOCATION_COST_HORIZON,
    "demotion_cooldown_multiplier": DEMOTION_COOLDOWN_MULTIPLIER,
    "hourly_external_transfer_cap": HOURLY_EXTERNAL_TRANSFER_CAP,
    "bitfinex_reserve_pct": BITFINEX_RESERVE_PCT,
    "bitfinex_reserve_hard_floor": BITFINEX_RESERVE_HARD_FLOOR,
    "net_pct_sizing_enabled": NET_PCT_SIZING_ENABLED,
    "net_pct_multiplier_cap": NET_PCT_MULTIPLIER_CAP,
    "spread_persistence_ticks": SPREAD_PERSISTENCE_TICKS,
    "event_driven_seller_penalty_pct": EVENT_DRIVEN_SELLER_PENALTY_PCT,
    "one_leg_failure_rate": ONE_LEG_FAILURE_RATE,
    "one_leg_unwind_slippage_mult": ONE_LEG_UNWIND_SLIPPAGE_MULT,
    "max_position_multiplier": MAX_POSITION_MULTIPLIER,
    "anomaly_protection_enabled": ANOMALY_PROTECTION_ENABLED,
    "circuit_breaker_window": CIRCUIT_BREAKER_WINDOW,
    "circuit_breaker_threshold": CIRCUIT_BREAKER_THRESHOLD,
    "circuit_breaker_resume_pct": CIRCUIT_BREAKER_RESUME_PCT,
    "circuit_breaker_cooldown": CIRCUIT_BREAKER_COOLDOWN,
    "drawdown_threshold_pct": DRAWDOWN_THRESHOLD_PCT,
    "drawdown_resume_pct": DRAWDOWN_RESUME_PCT,
    "drawdown_emergency_mult": DRAWDOWN_EMERGENCY_MULT,
    "symbol_loss_streak_threshold": SYMBOL_LOSS_STREAK_THRESHOLD,
    "symbol_loss_streak_cooldown": SYMBOL_LOSS_STREAK_COOLDOWN,
    "warning_pnl_pct": WARNING_PNL_PCT,
    "ip_whitelist_enabled": False,
    "ip_whitelist": [],
    "fee_configs": DEFAULT_FEE_CONFIGS,
    "fee_real_mode": False,
    "transfer_configs": DEFAULT_TRANSFER_CONFIGS,
}


def load_settings() -> dict:
    """Load settings from JSON file, creating defaults if missing."""
    path = Path(SETTINGS_FILE)
    if path.exists():
        try:
            with open(path) as f:
                settings = json.load(f)
            logger.info(f"[Settings] Loaded from {SETTINGS_FILE}")
            # Merge with defaults for any missing keys
            for key, default in DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = default
                elif isinstance(default, dict) and isinstance(settings[key], dict):
                    # Deep merge dict configs — add new exchanges/keys from defaults
                    for sub_key, sub_val in default.items():
                        if sub_key not in settings[key]:
                            settings[key][sub_key] = sub_val
            # Enforce types: coerce numeric settings that may have been
            # saved as strings (e.g. from manual edits or older code)
            for key, default in DEFAULT_SETTINGS.items():
                if key not in settings:
                    continue
                val = settings[key]
                if isinstance(default, int) and not isinstance(default, bool):
                    if not isinstance(val, int) or isinstance(val, bool):
                        try:
                            settings[key] = int(val)
                            logger.warning(f"[Settings] Coerced {key} from {type(val).__name__} to int")
                        except (ValueError, TypeError):
                            settings[key] = default
                elif isinstance(default, float):
                    if not isinstance(val, (int, float)) or isinstance(val, bool):
                        try:
                            settings[key] = float(val)
                            logger.warning(f"[Settings] Coerced {key} from {type(val).__name__} to float")
                        except (ValueError, TypeError):
                            settings[key] = default
                elif isinstance(default, bool):
                    if not isinstance(val, bool):
                        settings[key] = default
                        logger.warning(f"[Settings] Reset {key} to default (was {type(val).__name__})")
            return settings
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[Settings] Failed to load {SETTINGS_FILE}: {e}, using defaults")

    settings = DEFAULT_SETTINGS.copy()
    save_settings(settings)
    logger.info(f"[Settings] Created default {SETTINGS_FILE}")
    return settings


def save_settings(settings: dict) -> None:
    """Save settings to JSON file."""
    path = Path(SETTINGS_FILE)
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)
    logger.info(f"[Settings] Saved to {SETTINGS_FILE}")
