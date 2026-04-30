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
    MOMENTUM_FILTER_ENABLED,
    MOMENTUM_LOOKBACK_HOURS,
    MOMENTUM_SAMPLE_INTERVAL_MINUTES,
    MOMENTUM_MIN_FACTOR,
    MOMENTUM_MAX_FACTOR,
    INVENTORY_REBALANCE_ENABLED,
    INVENTORY_REBALANCE_INTERVAL_HOURS,
    INVENTORY_DRIFT_THRESHOLD,
    BITFINEX_OVER_TARGET_ENABLED,
    BITFINEX_OVER_TARGET_MULTIPLIER,
    AUTO_EXPAND_ON_UNDERSTAFF,
    DIVERSIFICATION_FLOOR_ENABLED,
    DIVERSIFICATION_FLOOR_MULTIPLIER,
    AUTO_DISABLE_VOLUME_ENABLED,
    AUTO_DISABLE_VOLUME_THRESHOLD_USD,
    CUSTODY_HUB_EXCHANGE,
    CUSTODY_HUB_NETWORK,
    TRADING_FLOAT_MULTIPLIER,
    TRADING_FLOAT_REPLENISH_TRIGGER,
    TRADING_FLOAT_OVERFLOW_MULTIPLIER,
    FUNDING_AWARE_SCORING_ENABLED,
    FUNDING_SKIP_THRESHOLD_4H_PCT,
    FUNDING_SKIP_THRESHOLD_8H_PCT,
    FUNDING_SCORE_MIN_FACTOR,
    FUNDING_SCORE_MAX_FACTOR,
    FUNDING_POLL_INTERVAL_SECONDS,
    HEDGING_ENABLED,
    HEDGE_EXECUTION_MODE,
    HEDGE_DUST_THRESHOLD_USD,
    HEDGE_EVALUATION_INTERVAL_SECONDS,
    HEDGE_MARGIN_BUFFER_PCT,
    HEDGE_ADJUST_THRESHOLD_PCT,
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
    # v0.30+: capital architecture (Bybit custody / Bitfinex trading float)
    "custody_hub_exchange": CUSTODY_HUB_EXCHANGE,
    "custody_hub_network": CUSTODY_HUB_NETWORK,
    "trading_float_multiplier": TRADING_FLOAT_MULTIPLIER,
    "trading_float_replenish_trigger": TRADING_FLOAT_REPLENISH_TRIGGER,
    "trading_float_overflow_multiplier": TRADING_FLOAT_OVERFLOW_MULTIPLIER,
    # Deprecated (kept for migration; removed on first save in v0.30)
    "bitfinex_reserve_pct": BITFINEX_RESERVE_PCT,
    "bitfinex_reserve_hard_floor": BITFINEX_RESERVE_HARD_FLOOR,
    "net_pct_sizing_enabled": NET_PCT_SIZING_ENABLED,
    "net_pct_multiplier_cap": NET_PCT_MULTIPLIER_CAP,
    "spread_persistence_ticks": SPREAD_PERSISTENCE_TICKS,
    "event_driven_seller_penalty_pct": EVENT_DRIVEN_SELLER_PENALTY_PCT,
    "one_leg_failure_rate": ONE_LEG_FAILURE_RATE,
    "one_leg_unwind_slippage_mult": ONE_LEG_UNWIND_SLIPPAGE_MULT,
    "max_position_multiplier": MAX_POSITION_MULTIPLIER,
    "momentum_filter_enabled": MOMENTUM_FILTER_ENABLED,
    "momentum_lookback_hours": MOMENTUM_LOOKBACK_HOURS,
    "momentum_sample_interval_minutes": MOMENTUM_SAMPLE_INTERVAL_MINUTES,
    "momentum_min_factor": MOMENTUM_MIN_FACTOR,
    "momentum_max_factor": MOMENTUM_MAX_FACTOR,
    "inventory_rebalance_enabled": INVENTORY_REBALANCE_ENABLED,
    "inventory_rebalance_interval_hours": INVENTORY_REBALANCE_INTERVAL_HOURS,
    "inventory_drift_threshold": INVENTORY_DRIFT_THRESHOLD,
    "bitfinex_over_target_enabled": BITFINEX_OVER_TARGET_ENABLED,
    "bitfinex_over_target_multiplier": BITFINEX_OVER_TARGET_MULTIPLIER,
    "auto_expand_on_understaff": AUTO_EXPAND_ON_UNDERSTAFF,
    "diversification_floor_enabled": DIVERSIFICATION_FLOOR_ENABLED,
    "auto_disable_volume_enabled": AUTO_DISABLE_VOLUME_ENABLED,
    "auto_disable_volume_threshold_usd": AUTO_DISABLE_VOLUME_THRESHOLD_USD,
    "diversification_floor_multiplier": DIVERSIFICATION_FLOOR_MULTIPLIER,
    "funding_aware_scoring_enabled": FUNDING_AWARE_SCORING_ENABLED,
    "funding_skip_threshold_4h_pct": FUNDING_SKIP_THRESHOLD_4H_PCT,
    "funding_skip_threshold_8h_pct": FUNDING_SKIP_THRESHOLD_8H_PCT,
    "funding_score_min_factor": FUNDING_SCORE_MIN_FACTOR,
    "funding_score_max_factor": FUNDING_SCORE_MAX_FACTOR,
    "funding_poll_interval_seconds": FUNDING_POLL_INTERVAL_SECONDS,
    "hedging_enabled": HEDGING_ENABLED,
    "hedge_execution_mode": HEDGE_EXECUTION_MODE,
    "hedge_dust_threshold_usd": HEDGE_DUST_THRESHOLD_USD,
    "hedge_evaluation_interval_seconds": HEDGE_EVALUATION_INTERVAL_SECONDS,
    "hedge_margin_buffer_pct": HEDGE_MARGIN_BUFFER_PCT,
    "hedge_adjust_threshold_pct": HEDGE_ADJUST_THRESHOLD_PCT,
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


def _migrate_capital_architecture(settings: dict) -> dict:
    """v0.30 migration: switch from `bitfinex_reserve_pct` (% of capital) to
    `trading_float_multiplier` (× trade_amount).

    Idempotent: only runs if old key is present. Logs the conversion once.
    Safe to leave in place indefinitely — the function is a no-op once the
    old key is cleared.
    """
    if "bitfinex_reserve_pct" not in settings:
        return settings  # already migrated

    old_pct = float(settings.pop("bitfinex_reserve_pct", BITFINEX_RESERVE_PCT))
    capital = float(settings.get("total_capital", 1000.0))
    trade_amount = float(settings.get("trade_amount_usd", 40.0))
    if trade_amount <= 0:
        trade_amount = 40.0

    # Reverse-engineer multiplier from old reserve dollars
    old_reserve_dollar = capital * old_pct
    new_multiplier = old_reserve_dollar / trade_amount
    new_multiplier = max(2.0, min(50.0, new_multiplier))

    # Only override if user hasn't already explicitly set the new key
    if "trading_float_multiplier" not in settings or settings.get(
        "trading_float_multiplier"
    ) == TRADING_FLOAT_MULTIPLIER:
        settings["trading_float_multiplier"] = round(new_multiplier, 1)

    # Drop other deprecated keys
    settings.pop("bitfinex_reserve_hard_floor", None)
    settings.pop("bitfinex_over_target_enabled", None)
    if "bitfinex_over_target_multiplier" in settings:
        # Rename — same semantics, new name
        settings.setdefault(
            "trading_float_overflow_multiplier",
            settings.pop("bitfinex_over_target_multiplier"),
        )
    else:
        settings.pop("bitfinex_over_target_multiplier", None)

    # Ensure new keys exist with sane defaults
    settings.setdefault("custody_hub_exchange", CUSTODY_HUB_EXCHANGE)
    settings.setdefault("custody_hub_network", CUSTODY_HUB_NETWORK)
    settings.setdefault(
        "trading_float_replenish_trigger", TRADING_FLOAT_REPLENISH_TRIGGER
    )
    settings.setdefault(
        "trading_float_overflow_multiplier", TRADING_FLOAT_OVERFLOW_MULTIPLIER
    )

    logger.warning(
        f"[Migration] v0.30 capital architecture: "
        f"bitfinex_reserve_pct={old_pct} (capital ${capital:.0f} × {old_pct} = ${old_reserve_dollar:.0f}) "
        f"→ trading_float_multiplier={settings['trading_float_multiplier']} "
        f"(× trade_amount ${trade_amount:.0f}). "
        f"Custody hub = {settings['custody_hub_exchange']} via {settings['custody_hub_network']}."
    )
    return settings


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
            # v0.30 migration: bitfinex_reserve_pct → trading_float_multiplier
            settings = _migrate_capital_architecture(settings)
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
