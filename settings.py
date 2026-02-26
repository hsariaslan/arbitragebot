"""
Settings manager for CoirnaBot.

Loads/saves runtime configuration from settings.json.
Falls back to config.py defaults when settings.json is missing or incomplete.
"""

import json
import logging
from pathlib import Path

from config import (
    ADAPTIVE_MODE,
    AUTO_ROTATE,
    CONFIRMATION_PERIOD_SECONDS,
    DEFAULT_FEE_CONFIGS,
    DEFAULT_TRANSFER_CONFIGS,
    DEMOTION_PERIOD_SECONDS,
    DEMOTION_THRESHOLD,
    DISCOVERY_DURATION_SECONDS,
    EVALUATION_INTERVAL_SECONDS,
    MAX_ACTIVE_SYMBOLS,
    MIN_NET_PROFIT_PCT,
    MIN_REBALANCE_SCORE,
    NUM_ACTIVE_SYMBOLS,
    PROMOTION_THRESHOLD,
    REBALANCE_COOLDOWN_SECONDS,
    REBALANCE_ROI_HORIZON,
    ROTATION_SAFETY_MULTIPLIER,
    SCORING_WINDOW_SECONDS,
    SETTINGS_FILE,
    TOTAL_CAPITAL,
    TRADE_AMOUNT_USD,
)

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS: dict = {
    "trade_amount_usd": TRADE_AMOUNT_USD,
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
    "promotion_threshold": PROMOTION_THRESHOLD,
    "demotion_threshold": DEMOTION_THRESHOLD,
    "demotion_period": DEMOTION_PERIOD_SECONDS,
    "min_net_profit_pct": MIN_NET_PROFIT_PCT,
    "rebalance_cooldown": REBALANCE_COOLDOWN_SECONDS,
    "rebalance_roi_horizon": REBALANCE_ROI_HORIZON,
    "adaptive_mode": ADAPTIVE_MODE,
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
