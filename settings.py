"""
Settings manager for ArbitrageBot.

Loads/saves runtime configuration from settings.json.
Falls back to config.py defaults when settings.json is missing or incomplete.

v0.31.0-beta: schema v2 multi-config support. The on-disk format is now
{schema_version: 2, shared: {...}, groups: [{configs: [{settings: {...}}]}]}.
`load_settings()` continues to return a flat dict (the default config's
view) for backwards compatibility; `load_registry()` returns the full
ConfigRegistry for code that needs the multi-config view.
"""

import json
import logging
from pathlib import Path

from config_registry import (
    SCHEMA_VERSION,
    SHARED_KEYS,
    STRIP_FROM_PER_CONFIG,
    Config,
    ConfigGroup,
    ConfigRegistry,
    _new_id,
)

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
    FAST_TRACK_DISCOVERY_ENABLED,
    FAST_TRACK_AGGRESSIVENESS,
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
    HEDGE_LEVERAGE,
    HEDGE_MARGIN_BUFFER_PCT,
    HEDGE_ADJUST_THRESHOLD_PCT,
    BINANCE_FUTURES_TAKER_FEE_RATE,
    BINANCE_FUTURES_BNB_DISCOUNT_ENABLED,
    BINANCE_FUTURES_BNB_DISCOUNT_PCT,
    BINANCE_FUTURES_REFERRAL_CASHBACK_ENABLED,
    BINANCE_FUTURES_REFERRAL_CASHBACK_PCT,
    BINANCE_FUTURES_BNB_AUTO_TOPUP_ENABLED,
    BINANCE_FUTURES_BNB_MIN_USD,
    BINANCE_FUTURES_BNB_TARGET_PCT,
    BINANCE_FUTURES_BNB_TRANSFER_MIN_USD,
    BINANCE_SPOT_BNB_MIN_USD,
    BINANCE_SPOT_BNB_AUTO_BUY_ENABLED,
    BINANCE_SPOT_BNB_TARGET_PCT,
    BINANCE_SPOT_BNB_BUY_MIN_USD,
    FUTURES_CAPITAL_TARGET_PCT,
    FUTURES_CAPITAL_TOPUP_PCT,
    FUTURES_CAPITAL_EMERGENCY_PCT,
    FUTURES_CAPITAL_OVERFLOW_PCT,
    FUTURES_CAPITAL_TRANSFER_MIN_USD,
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
    STRICT_SLIPPAGE_GUARDS_ENABLED,
    REQUIRE_ORDER_BOOK_DEPTH,
    ORDER_BOOK_DEPTH_BUFFER_MULTIPLIER,
    MISSING_ORDER_BOOK_PENALTY_PCT,
    MAX_LEG_SLIPPAGE_PCT,
    MAX_TOTAL_SLIPPAGE_PCT,
    SLIPPAGE_SAFETY_MULTIPLIER,
    SLIPPAGE_LATENCY_BUFFER_PCT,
    BOOK_AGE_GUARD_ENABLED,
    MAX_BOOK_AGE_SECONDS,
    EVENT_DRIVEN_MAX_BOOK_AGE_SECONDS,
    DEPTH_AWARE_TRADE_SIZE_SHRINK_ENABLED,
    MIN_DEPTH_SHRINK_RATIO,
    SPOT_EXECUTION_ORDER_MODE,
    MARKETABLE_LIMIT_PRICE_BUFFER_PCT,
    DEMO_ONE_LEG_DRILL_ENABLED,
    DEMO_ONE_LEG_DRILL_EVERY_N,
    DEMO_ONE_LEG_DRILL_SIDE,
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
    "min_misses_before_rebalance": 3,
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
    "strict_slippage_guards_enabled": STRICT_SLIPPAGE_GUARDS_ENABLED,
    "require_order_book_depth": REQUIRE_ORDER_BOOK_DEPTH,
    "order_book_depth_buffer_multiplier": ORDER_BOOK_DEPTH_BUFFER_MULTIPLIER,
    "missing_order_book_penalty_pct": MISSING_ORDER_BOOK_PENALTY_PCT,
    "max_leg_slippage_pct": MAX_LEG_SLIPPAGE_PCT,
    "max_total_slippage_pct": MAX_TOTAL_SLIPPAGE_PCT,
    "slippage_safety_multiplier": SLIPPAGE_SAFETY_MULTIPLIER,
    "slippage_latency_buffer_pct": SLIPPAGE_LATENCY_BUFFER_PCT,
    "book_age_guard_enabled": BOOK_AGE_GUARD_ENABLED,
    "max_book_age_seconds": MAX_BOOK_AGE_SECONDS,
    "event_driven_max_book_age_seconds": EVENT_DRIVEN_MAX_BOOK_AGE_SECONDS,
    "depth_aware_trade_size_shrink_enabled": DEPTH_AWARE_TRADE_SIZE_SHRINK_ENABLED,
    "min_depth_shrink_ratio": MIN_DEPTH_SHRINK_RATIO,
    "spot_execution_order_mode": SPOT_EXECUTION_ORDER_MODE,
    "marketable_limit_price_buffer_pct": MARKETABLE_LIMIT_PRICE_BUFFER_PCT,
    "demo_one_leg_drill_enabled": DEMO_ONE_LEG_DRILL_ENABLED,
    "demo_one_leg_drill_every_n": DEMO_ONE_LEG_DRILL_EVERY_N,
    "demo_one_leg_drill_side": DEMO_ONE_LEG_DRILL_SIDE,
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
    "regime_gating_enabled": False,
    "regime_strong_hours": [7, 15, 20, 21, 22],
    "regime_neutral_hours": [0, 1, 5, 6, 8, 9, 11],
    "regime_weak_min_net_multiplier": 2.0,
    "regime_weak_disable_rebalance": True,  # legacy alias; policy key below is authoritative
    "regime_weak_rebalance_policy": "refill_only",
    "regime_weak_refill_max_fee_usd": 0.10,
    "regime_weak_disable_demote": True,
    "regime_weak_disable_expand": True,
    "demotion_freq_scaling_enabled": True,
    "quiet_period_pause_minutes": 0.0,
    "activation_profit_horizon_multiplier": 2.0,
    "diversification_floor_enabled": DIVERSIFICATION_FLOOR_ENABLED,
    "auto_disable_volume_enabled": AUTO_DISABLE_VOLUME_ENABLED,
    "auto_disable_volume_threshold_usd": AUTO_DISABLE_VOLUME_THRESHOLD_USD,
    "diversification_floor_multiplier": DIVERSIFICATION_FLOOR_MULTIPLIER,
    "fast_track_discovery_enabled": FAST_TRACK_DISCOVERY_ENABLED,
    "fast_track_aggressiveness": FAST_TRACK_AGGRESSIVENESS,
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
    "hedge_leverage": HEDGE_LEVERAGE,
    "hedge_margin_buffer_pct": HEDGE_MARGIN_BUFFER_PCT,
    "hedge_adjust_threshold_pct": HEDGE_ADJUST_THRESHOLD_PCT,
    "binance_futures_taker_fee_rate": BINANCE_FUTURES_TAKER_FEE_RATE,
    "binance_futures_bnb_discount_enabled": BINANCE_FUTURES_BNB_DISCOUNT_ENABLED,
    "binance_futures_bnb_discount_pct": BINANCE_FUTURES_BNB_DISCOUNT_PCT,
    "binance_futures_referral_cashback_enabled": BINANCE_FUTURES_REFERRAL_CASHBACK_ENABLED,
    "binance_futures_referral_cashback_pct": BINANCE_FUTURES_REFERRAL_CASHBACK_PCT,
    "binance_futures_bnb_auto_topup_enabled": BINANCE_FUTURES_BNB_AUTO_TOPUP_ENABLED,
    "binance_futures_bnb_min_usd": BINANCE_FUTURES_BNB_MIN_USD,
    "binance_futures_bnb_target_pct": BINANCE_FUTURES_BNB_TARGET_PCT,
    "binance_futures_bnb_transfer_min_usd": BINANCE_FUTURES_BNB_TRANSFER_MIN_USD,
    "binance_spot_bnb_min_usd": BINANCE_SPOT_BNB_MIN_USD,
    "binance_spot_bnb_auto_buy_enabled": BINANCE_SPOT_BNB_AUTO_BUY_ENABLED,
    "binance_spot_bnb_target_pct": BINANCE_SPOT_BNB_TARGET_PCT,
    "binance_spot_bnb_buy_min_usd": BINANCE_SPOT_BNB_BUY_MIN_USD,
    "futures_capital_target_pct": FUTURES_CAPITAL_TARGET_PCT,
    "futures_capital_topup_pct": FUTURES_CAPITAL_TOPUP_PCT,
    "futures_capital_emergency_pct": FUTURES_CAPITAL_EMERGENCY_PCT,
    "futures_capital_overflow_pct": FUTURES_CAPITAL_OVERFLOW_PCT,
    "futures_capital_transfer_min_usd": FUTURES_CAPITAL_TRANSFER_MIN_USD,
    "anomaly_protection_enabled": ANOMALY_PROTECTION_ENABLED,
    "circuit_breaker_window": CIRCUIT_BREAKER_WINDOW,
    "circuit_breaker_threshold": CIRCUIT_BREAKER_THRESHOLD,
    "circuit_breaker_resume_pct": CIRCUIT_BREAKER_RESUME_PCT,
    "circuit_breaker_cooldown": CIRCUIT_BREAKER_COOLDOWN,
    "drawdown_threshold_pct": DRAWDOWN_THRESHOLD_PCT,
    "drawdown_resume_pct": DRAWDOWN_RESUME_PCT,
    "drawdown_emergency_mult": DRAWDOWN_EMERGENCY_MULT,
    # v0.31.0-beta+: two-layer emergency gate (eliminates phantom drawdowns)
    "realized_drawdown_emergency_pct": 15.0,
    "combined_drawdown_emergency_pct": 25.0,
    "combined_drawdown_sustained_seconds": 300.0,
    "emergency_auto_liquidate": False,
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


def _coerce_types(settings: dict) -> dict:
    """Coerce numeric settings saved as strings to their default type."""
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


def _merge_with_defaults(settings: dict) -> dict:
    """Add missing keys from DEFAULT_SETTINGS, deep-merge dict configs."""
    for key, default in DEFAULT_SETTINGS.items():
        if key not in settings:
            settings[key] = default if not isinstance(default, dict) else dict(default)
        elif isinstance(default, dict) and isinstance(settings[key], dict):
            for sub_key, sub_val in default.items():
                if sub_key not in settings[key]:
                    settings[key][sub_key] = sub_val
    return settings


def _migrate_v1_to_v2(raw: dict) -> dict:
    """v0.31 migration: flat single-config schema → multi-config schema.

    Idempotent: only runs if `schema_version != 2`. Preserves the existing
    config as Group 1 / Config 1 (primary + default + super-primary).
    Lifts shared keys (execution_mode, ip_whitelist, transfer_configs, etc.)
    into the `shared` section.
    """
    if raw.get("schema_version") == SCHEMA_VERSION:
        return raw

    # Apply v0.30 capital architecture migration first if needed
    raw = _migrate_capital_architecture(raw)
    # Fill in any missing v0.30 keys + coerce types so the per-config
    # blob has everything the components expect
    raw = _merge_with_defaults(raw)
    raw = _coerce_types(raw)

    # Build the shared section from legacy keys
    shared: dict = {
        "execution_mode": raw.get("execution_mode", "simulation"),
        "hedge_execution_mode": raw.get("hedge_execution_mode", "simulation"),
        "ip_whitelist_enabled": raw.get("ip_whitelist_enabled", False),
        "ip_whitelist": list(raw.get("ip_whitelist", [])),
        "transfer_configs": dict(raw.get("transfer_configs", {})),
    }

    # Build the per-config settings blob — strip out shared keys + group capital
    per_config_settings = {
        k: v for k, v in raw.items()
        if k not in STRIP_FROM_PER_CONFIG and k != "schema_version"
    }

    config_id = _new_id()
    group_id = _new_id()
    capital = float(raw.get("total_capital", 1000.0))

    shared["super_primary_config_id"] = config_id

    migrated = {
        "schema_version": SCHEMA_VERSION,
        "shared": shared,
        "groups": [
            {
                "id": group_id,
                "name": "Group 1",
                "initial_capital": capital,
                "order": 0,
                "configs": [
                    {
                        "id": config_id,
                        "name": "Config 1",
                        "description": "Migrated from v0.30 single-config setup",
                        "is_primary": True,
                        "is_default": True,
                        "order": 0,
                        "settings": per_config_settings,
                    }
                ],
            }
        ],
    }

    logger.warning(
        f"[Migration] v0.31 multi-config: lifted single config into "
        f"Group 1 / Config 1 (group_id={group_id[:8]}…, config_id={config_id[:8]}…), "
        f"capital=${capital:.0f}, super-primary={config_id[:8]}…"
    )
    return migrated


def load_registry() -> ConfigRegistry:
    """Load the full multi-config registry from disk. Migrates v1 → v2 if needed.
    Always writes the migrated form back so subsequent loads are no-op.
    """
    path = Path(SETTINGS_FILE)
    raw: dict = {}

    if path.exists():
        try:
            with open(path) as f:
                raw = json.load(f)
            logger.info(f"[Settings] Loaded from {SETTINGS_FILE}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[Settings] Failed to load {SETTINGS_FILE}: {e}, using defaults")
            raw = {}

    needs_migration = raw.get("schema_version") != SCHEMA_VERSION

    if not raw:
        # Bootstrap from defaults — single config / single group
        raw = dict(DEFAULT_SETTINGS)
        needs_migration = True

    if needs_migration:
        v2 = _migrate_v1_to_v2(raw)
    else:
        v2 = raw

    # Merge per-config settings with current defaults (covers new keys
    # added in subsequent versions). The shared section is left as-is.
    for group in v2.get("groups", []):
        for cfg in group.get("configs", []):
            cfg.setdefault("settings", {})
            for k, default in DEFAULT_SETTINGS.items():
                if k in STRIP_FROM_PER_CONFIG:
                    continue
                if k not in cfg["settings"]:
                    cfg["settings"][k] = (
                        dict(default) if isinstance(default, dict) else default
                    )
                elif isinstance(default, dict) and isinstance(cfg["settings"][k], dict):
                    for sub_k, sub_v in default.items():
                        if sub_k not in cfg["settings"][k]:
                            cfg["settings"][k][sub_k] = sub_v

    # Ensure shared has its expected keys
    shared = v2.setdefault("shared", {})
    shared.setdefault("execution_mode", "simulation")
    shared.setdefault("hedge_execution_mode", "simulation")
    shared.setdefault("ip_whitelist_enabled", False)
    shared.setdefault("ip_whitelist", [])
    shared.setdefault("transfer_configs", dict(DEFAULT_SETTINGS["transfer_configs"]))
    # Deep-merge transfer_configs against defaults to pick up new networks
    for ex, ex_cfg in DEFAULT_SETTINGS["transfer_configs"].items():
        if ex not in shared["transfer_configs"]:
            shared["transfer_configs"][ex] = dict(ex_cfg)
        elif isinstance(ex_cfg, dict) and isinstance(shared["transfer_configs"][ex], dict):
            for sub_k, sub_v in ex_cfg.items():
                if sub_k not in shared["transfer_configs"][ex]:
                    shared["transfer_configs"][ex][sub_k] = sub_v

    registry = ConfigRegistry.from_settings_dict(v2)

    if needs_migration:
        save_registry(registry)
        logger.info(f"[Settings] Persisted v{SCHEMA_VERSION} schema after migration")

    return registry


def save_registry(registry: ConfigRegistry) -> None:
    """Persist the full registry to settings.json."""
    path = Path(SETTINGS_FILE)
    payload = registry.to_settings_dict()
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"[Settings] Saved registry to {SETTINGS_FILE}")


def load_settings() -> dict:
    """Backwards-compat: return a flat dict view of the default config + shared.

    Existing code that hasn't been refactored to use ConfigRegistry directly
    can keep calling load_settings() — it gets the default config's settings
    blob merged with shared keys (execution_mode, ip_whitelist, transfer_configs).
    """
    registry = load_registry()
    default = registry.default_config
    if default is None:
        # No configs at all — return defaults
        flat = dict(DEFAULT_SETTINGS)
    else:
        flat = dict(default.settings)

    # Lift shared keys back into the flat view so legacy callers see them
    flat["execution_mode"] = registry.shared.get("execution_mode", "simulation")
    flat["hedge_execution_mode"] = registry.shared.get(
        "hedge_execution_mode", "simulation"
    )
    flat["ip_whitelist_enabled"] = registry.shared.get("ip_whitelist_enabled", False)
    flat["ip_whitelist"] = list(registry.shared.get("ip_whitelist", []))
    flat["transfer_configs"] = dict(registry.shared.get("transfer_configs", {}))
    # Group capital → top-level total_capital
    flat["total_capital"] = (
        registry.find_group_for_config(default.id).initial_capital
        if default else DEFAULT_SETTINGS["total_capital"]
    )
    return _coerce_types(_merge_with_defaults(flat))


def save_settings(settings: dict) -> None:
    """Backwards-compat: save flat-dict updates by writing them through to
    the default config's settings blob (and shared keys to shared)."""
    registry = load_registry()
    default = registry.default_config
    if default is None:
        # Nothing to update against; just write the flat settings as-is for
        # diagnostic (will be re-migrated on next load).
        path = Path(SETTINGS_FILE)
        with open(path, "w") as f:
            json.dump(settings, f, indent=2)
        return

    # Split incoming flat dict into shared vs per-config buckets
    for k, v in settings.items():
        if k == "total_capital":
            g = registry.find_group_for_config(default.id)
            if g:
                g.initial_capital = float(v)
        elif k in SHARED_KEYS:
            registry.shared[k] = v
        elif k == "schema_version":
            continue
        else:
            default.settings[k] = v
    save_registry(registry)
