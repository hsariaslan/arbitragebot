export interface CryptoBalance {
  qty: number;
  value: number;
  price: number;
}

export interface ExchangeBalance {
  usdt: number;
  crypto: Record<string, CryptoBalance>;
  total: number;
}

export interface PriceEntry {
  bid: number;
  ask: number;
  age: number;
}

export interface DowntimeEvent {
  start: number;
  end: number;
  duration: number;
}

export interface UptimeInfo {
  first_start: number;
  true_uptime_seconds: number;
  total_downtime: number;
  restart_count: number;
  downtimes: DowntimeEvent[];
}

export interface ProxyUptimeInfo {
  is_connected: boolean;
  first_connected: number;
  true_uptime_seconds: number;
  total_downtime: number;
  outage_count: number;
  downtimes: DowntimeEvent[];
}

export interface Portfolio {
  total_value: number;
  initial_investment: number;
  net_pnl: number;
  trading_pnl: number;
  transfer_fees: number;
  price_pnl: number;
}

export interface Simulation {
  total_trades: number;
  skipped_trades: number;
  total_transfers: number;
  trades_per_minute: number;
  low_profit_skips: number;
  avg_trade_size: number;
  min_trade_size: number;
  max_trade_size: number;
  configured_trade_amount: number;
}

export interface Trade {
  timestamp: number;
  symbol: string;
  buy_exchange: string;
  sell_exchange: string;
  buy_price: number;
  sell_price: number;
  spread_pct: number;
  fee_pct: number;
  net_pct: number;
  profit_usd: number;
  trade_amount: number;
  // Simulated slippage (from order book depth)
  sim_slippage_pct?: number;
  // Demo execution results (Phase 2, present when execution_mode=demo)
  demo_buy_price?: number;
  demo_sell_price?: number;
  demo_buy_qty?: number;
  demo_sell_qty?: number;
  demo_profit_usd?: number;
  demo_latency_ms?: number;
  demo_slippage_pct?: number;
  demo_status?: string;
}

export interface Transfer {
  timestamp: number;
  type: string;
  from_exchange: string;
  to_exchange: string;
  symbol: string;
  amount_usd: number;
  fee_usd: number;
}

export interface AllocationEntry {
  usdt: number;
  crypto: Record<string, number>;
}

export interface Settings {
  trade_amount_usd: number;
  trade_amount_pct?: number;
  total_capital?: number;
  auto_rotate?: boolean;
  num_active_symbols?: number;
  max_active_symbols?: number;
  scoring_window?: number;
  evaluation_interval?: number;
  safety_multiplier?: number;
  discovery_duration?: number;
  min_rebalance_score?: number;
  confirmation_period?: number;
  score_stability_seconds?: number;
  score_stability_factor?: number;
  promotion_threshold?: number;
  demotion_threshold?: number;
  demotion_period?: number;
  min_net_profit_pct?: number;
  rebalance_cooldown?: number;
  min_misses_before_rebalance?: number;
  rebalance_roi_horizon?: number;
  adaptive_mode?: boolean;
  execution_mode?: string;
  // Profitability controls
  reallocation_cost_horizon?: number;
  demotion_cooldown_multiplier?: number;
  hourly_external_transfer_cap?: number;
  // v0.30+: capital architecture (custody hub + trading float)
  custody_hub_exchange?: string;
  custody_hub_network?: string;
  trading_float_multiplier?: number;
  trading_float_replenish_trigger?: number;
  trading_float_overflow_multiplier?: number;
  // Deprecated v0.30 (kept for migration / type compat)
  bitfinex_reserve_pct?: number;
  bitfinex_reserve_hard_floor?: number;
  net_pct_sizing_enabled?: boolean;
  net_pct_multiplier_cap?: number;
  // Score thresholds
  trading_score_threshold?: number;
  fee_threshold_multiplier?: number;
  strong_score_threshold?: number;
  very_strong_score_threshold?: number;
  // Net P&L gate params
  net_pnl_gate_warmup_trades?: number;
  net_pnl_gate_grace_seconds?: number;
  rebalance_roi_divisor?: number;
  // Simulation realism
  spread_persistence_ticks?: number;
  event_driven_seller_penalty_pct?: number;
  one_leg_failure_rate?: number;
  one_leg_unwind_slippage_mult?: number;
  max_position_multiplier?: number;
  // Diversification floor (S21 follow-up)
  diversification_floor_enabled?: boolean;
  diversification_floor_multiplier?: number;
  // Fast-track discovery exit (S29 follow-up)
  fast_track_discovery_enabled?: boolean;
  fast_track_aggressiveness?: number;
  auto_disable_volume_enabled?: boolean;
  auto_disable_volume_threshold_usd?: number;
  // Funding-aware scoring (Phase A)
  funding_aware_scoring_enabled?: boolean;
  funding_skip_threshold_4h_pct?: number;
  funding_skip_threshold_8h_pct?: number;
  funding_score_min_factor?: number;
  funding_score_max_factor?: number;
  funding_poll_interval_seconds?: number;
  // Spot-futures hedging (Phase C+)
  hedging_enabled?: boolean;
  hedge_execution_mode?: 'simulation' | 'testnet' | 'live';
  hedge_dust_threshold_usd?: number;
  hedge_evaluation_interval_seconds?: number;
  hedge_margin_buffer_pct?: number;
  hedge_adjust_threshold_pct?: number;
  // Anomaly protection
  anomaly_protection_enabled?: boolean;
  circuit_breaker_window?: number;
  circuit_breaker_threshold?: number;
  circuit_breaker_resume_pct?: number;
  circuit_breaker_cooldown?: number;
  drawdown_threshold_pct?: number;
  drawdown_resume_pct?: number;
  drawdown_emergency_mult?: number;
  // Two-layer emergency gate (v0.31)
  realized_drawdown_emergency_pct?: number;
  combined_drawdown_emergency_pct?: number;
  combined_drawdown_sustained_seconds?: number;
  emergency_auto_liquidate?: boolean;
  symbol_loss_streak_threshold?: number;
  symbol_loss_streak_cooldown?: number;
  warning_pnl_pct?: number;
  // Security
  ip_whitelist_enabled?: boolean;
  ip_whitelist?: string[];
  // Fee management
  fee_configs?: Record<string, ExchangeFeeConfig>;
  fee_real_mode?: boolean;
  // Legacy fields (may be present in old settings)
  active_exchanges?: string[];
  active_symbols?: string[];
  allocations?: Record<string, AllocationEntry>;
}

export interface ExchangeRanking {
  exchange: string;
  as_buyer: number;
  as_seller: number;
  total_involvement: number;
  profit_sum: number;
  fee_pct: number;
}

export interface PairRanking {
  buy_exchange: string;
  sell_exchange: string;
  trades: number;
  profit_sum: number;
}

export interface SymbolRanking {
  rank: number;
  symbol: string;
  score: number;
  avg_net_pct: number;
  avg_profitable_net: number;
  profitable_ticks: number;
  total_ticks: number;
  frequency: number;
  best_net_pct: number;
  est_hourly_profit: number;
  is_active: boolean;
  trade_multiplier: number;
  allocated_trade_size: number;
  cooldown_remaining: number;
  focus_tier: string;
  dominant_buyers: string[];
  dominant_sellers: string[];
  exchange_view?: {
    buyers: { exchange: string; weight: number; blocked: boolean }[];
    sellers: { exchange: string; weight: number; blocked: boolean }[];
  };
  diagnostic?: {
    status: string;
    tier: string;
    trajectory: string;
    reasons: string[];
    score_formula: string;
    threshold_breakdown: string;
    watchlist: {
      entered_seconds_ago?: number;
      samples?: number;
      peak_score?: number;
      confirmed?: boolean;
    };
  };
  current_net_pct: number;
}

export interface RotationEvent {
  timestamp: number;
  old_symbol: string;
  new_symbol: string;
  old_score: number;
  new_score: number;
  switching_cost_usd: number;
  est_hourly_improvement_usd: number;
}

export interface HistoricalSymbolStats {
  symbol: string;
  all_time_score: number;
  rolling_score: number;
  trend: number;
  total_profitable_ticks: number;
  total_ticks: number;
  overall_frequency: number;
  avg_net_pct: number;
  avg_profitable_net: number;
  best_net_pct: number;
  worst_net_pct: number;
  est_total_profit: number;
  est_hourly_rate: number;
  longest_profitable_streak: number;
  longest_unprofitable_streak: number;
  times_became_candidate: number;
  times_entered_watchlist: number;
  times_confirmed: number;
  times_activated: number;
  times_demoted: number;
  total_active_duration: number;
  times_became_strong: number;
  times_became_very_strong: number;
  total_strong_duration: number;
  total_very_strong_duration: number;
  is_active: boolean;
  buy_exchange_counts: Record<string, number>;
  sell_exchange_counts: Record<string, number>;
}

export interface HistoricalExchangeStats {
  exchange: string;
  total_buy_ticks: number;
  total_sell_ticks: number;
  total_profit_sum: number;
  total_involvement: number;
}

export interface WatchlistEntry {
  symbol: string;
  watching_since: number;
  elapsed: number;
  progress: number;
  confirmed: boolean;
  avg_score: number;
}

export interface OptimizerState {
  rankings: SymbolRanking[];
  exchange_rankings: ExchangeRanking[];
  pair_rankings: PairRanking[];
  rotations: RotationEvent[];
  historical_rankings: HistoricalSymbolStats[];
  historical_exchange_rankings: HistoricalExchangeStats[];
  watchlist: WatchlistEntry[];
  auto_rotate: boolean;
  active_symbols: string[];
  min_active_symbols: number;
  max_active_symbols: number;
  scoring_window: number;
  evaluation_interval: number;
  tick_count: number;
  warmup_remaining: number;
  discovery_mode: boolean;
  discovery_remaining: number;
  session_start: number;
}

// Phase F — hedge state from backend
export interface OpenHedge {
  symbol: string;
  side: 'SHORT' | 'LONG';
  qty: number;
  entry_price: number;
  mark_price: number;
  notional_usd: number;
  target_qty?: number;
  target_notional_usd?: number;
  quantity_gap?: number;
  quantity_gap_pct?: number;
  notional_gap_usd?: number;
  unrealized_pnl_usd: number;
  opened_at: number;
  held_seconds: number;
  accumulated_funding_usd: number;
  funding_rate: number | null;
  annualized_short_pct: number | null;
  open_count: number;
  adjust_count: number;
}

export interface HedgeEvent {
  symbol: string;
  open_count: number;
  close_count: number;
  adjust_count: number;
  accumulated_funding_usd: number;
  current_qty: number;
  current_entry_price: number;
  opened_at: number;
  last_adjusted_at: number;
}

export interface UnhedgedTarget {
  symbol: string;
  target_qty: number;
  target_notional_usd: number;
  mark_price: number;
  mark_source: 'futures' | 'spot';
  reason: string;
}

export interface HedgeState {
  enabled: boolean;
  execution_mode: 'simulation' | 'testnet' | 'live';
  safety_paused: boolean;
  dust_threshold_usd: number;
  evaluation_interval_seconds: number;
  margin_buffer_pct: number;
  adjust_threshold_pct: number;
  open_count: number;
  open_hedges: OpenHedge[];
  unhedged_targets?: UnhedgedTarget[];
  total_notional_usd: number;
  total_target_notional_usd?: number;
  total_hedge_gap_usd?: number;
  total_unrealized_pnl_usd: number;
  cumulative_funding_usd: number;
  total_opens: number;
  total_closes: number;
  total_adjusts: number;
  total_executor_errors: number;
  reconciled: boolean;
  last_evaluation_ts: number;
  recent_events: HedgeEvent[];
}

export interface FundingRateInfo {
  rate: number;                       // decimal per period
  rate_pct: number;                   // % per period
  interval_hours: number;             // 4 or 8
  annualized_short_pct: number;       // % per year for SHORT position
  mark_price: number;
  next_funding_time_ms: number;
  factor: number;                     // score multiplier
  skip: boolean;                      // skip-hedge flag
}

export interface ExchangeTransferStatus {
  withdrawal_fee: number;
  trades_to_recoup: number;
  transfer_allowed: boolean;
}

export interface AdaptiveConfig {
  adaptive_mode: boolean;
  configured_trade_amount: number;
  avg_trade_size: number;
  min_trade_size: number;
  max_trade_size: number;
  min_net_profit_pct: number;
  estimated_profit_per_trade: number;
  total_capital: number;
  net_pct_sizing_enabled: boolean;
  net_pct_multiplier_cap: number;
  exchange_transfer_status: Record<string, ExchangeTransferStatus>;
}

export interface ConfigSnapshot {
  timestamp: number;
  reason: string;
  trade_amount: number;
  adaptive_mode: boolean;
  min_net_profit_pct: number;
  rebalance_cooldown: number;
  min_misses_before_rebalance: number;
  rebalance_roi_horizon: number;
  total_capital: number;
  num_active_symbols: number;
  max_active_symbols: number;
  avg_trade_size: number;
  estimated_profit_per_trade: number;
}

export interface ProfitStats {
  net_profit: number;
  hourly_net: number;
  session_hourly_rate: number;
  trading_pnl: number;
  transfer_fees: number;
  credited_cashback: number;
  pending_cashback: number;
  is_profitable: boolean;
  referrer_earnings_total: number;
}

export interface AuthLogEntry {
  timestamp: number;
  event: string;
  ip: string;
  username: string;
  password: string;
  browser: string;
  os: string;
  details: string;
}

export interface BotLogEntry {
  timestamp: number;
  level: string;
  component: string;
  message: string;
  // v0.31.0-beta: multi-config tagging (null/undefined for shared subsystems)
  config_group_id?: string | null;
  config_id?: string | null;
  config_group_name?: string | null;
  config_name?: string | null;
}

// ── Demo/Testnet Comparison ──────────────────────────────────────────

export interface DemoCryptoPosition {
  qty: number;
  value: number;
}

export interface DemoExchangeSnapshot {
  usdt: number;
  crypto: Record<string, DemoCryptoPosition>;
  total: number;
  error?: string | null;
  fetched_at?: number;
}

export interface DemoExchangeComparison {
  sim: DemoExchangeSnapshot;
  demo: DemoExchangeSnapshot;
  diff_usdt: number;
  diff_total: number;
  diff_total_pct: number;
}

export interface DemoDiscrepancy {
  timestamp: number;
  exchange: string;
  type: string;
  symbol: string;
  sim_value: number;
  demo_value: number;
  diff_abs: number;
  diff_pct: number;
  root_cause: string;
}

export interface DemoComparisonState {
  enabled: boolean;
  exchanges: Record<string, DemoExchangeComparison>;
  recent_discrepancies: DemoDiscrepancy[];
  total_discrepancies: number;
  last_fetch_time: number;
  configured_exchanges: string[];
  demo_portfolio_total: number;  // demo exchanges + sim fallback for non-demo exchanges
}

// ── Anomaly Protection ─────────────────────────────────────────────

export interface AnomalyEvent {
  timestamp: number;
  layer: string;
  level: string;
  reason: string;
}

export interface AnomalyProtectionState {
  enabled: boolean;
  paused: boolean;
  pause_reason: string;
  pause_layer: string;
  pause_timestamp: number;
  warning_active: boolean;
  warning_reason: string;
  trade_size_multiplier: number;
  emergency_triggered: boolean;
  rolling_pnl: number;
  rolling_pnl_window: number;
  trades_in_window: number;
  loss_rate: number;
  peak_portfolio: number;
  current_drawdown_pct: number;
  symbol_blocks: Record<string, number>;
  symbol_losses: Record<string, number>;
  total_pauses: number;
  total_warnings: number;
  total_emergency_sells: number;
  total_symbol_blocks: number;
  circuit_breaker_threshold: number;
  drawdown_threshold_pct: number;
  symbol_loss_streak_threshold: number;
  events: AnomalyEvent[];
}

// ── Fee Management ──────────────────────────────────────────────────

export interface ExchangeFeeConfig {
  base_taker_rate: number;
  token_discount_enabled: boolean;
  token_discount_pct: number;
  effective_taker_rate: number;
  effective_rate_after_referral: number;
  fee_mechanism: 'instant' | 'rebate' | 'tier';
  fee_model: 'received' | 'spent' | 'token';
  referral_enabled: boolean;
  referral_cashback_pct: number;
  referral_settlement_minutes: number;
  referral_paid_in: 'same_as_fee' | 'USDT';
  referrer_commission_pct: number;
  zero_fee_pairs: string[];
  enabled: boolean;
  as_buyer?: boolean;
  as_seller?: boolean;
  disabled_symbols?: string[];
  auto_disabled_symbols?: string[];
  buyer_boost?: number;
  seller_boost?: number;
}

export interface FeeStats {
  pending_cashback_total: number;
  credited_cashback_total: number;
  pending_count: number;
  referrer_earnings_total: number;
  referrer_earnings_per_exchange: Record<string, number>;
}

// Daily auto-disable scheduler state + manual-fetch tracking (broadcast each tick).
// Both timestamps come from the backend so they survive component remount, WS
// reconnect, browser refresh, and bot restart (persisted in state/auto_disable_volumes.json).
export interface AutoDisableState {
  last_run_date_utc: string;        // "YYYY-MM-DD" or "" if auto-task never ran
  last_run_ts: number;              // unix epoch seconds — auto-task last completion
  last_manual_fetch_ts: number;     // unix epoch seconds — operator's last "Fetch 24h Volumes" click
  threshold_used_usd: number;       // current setting (live, not snapshot)
  enabled: boolean;
  /** Cached 24h volumes from the last fetch (manual or daily cron). */
  cached_volumes?: Record<string, Record<string, number>>;
}

// ── Transfer Fee Management ─────────────────────────────────────────

export interface NetworkFeeConfig {
  network: string;
  fee: number;
  fee_type: 'flat' | 'percentage' | 'conditional';
  percentage_rate: number;
  percentage_min: number;
  min_withdrawal: number;
  speed_seconds: number;
  enabled: boolean;
  notes: string;
}

export interface ExchangeTransferConfig {
  preferred_network: string;
  networks: NetworkFeeConfig[];
  effective_fee: number;
  cheapest_network: string;
  cheapest_fee: number;
}

// ── P&L History (persisted) ──────────────────────────────────────────

export interface HourlyPnlEntry {
  hour: string;     // "YYYY-MM-DD_HH"
  pnl: number;      // trading P&L
  fees: number;     // transfer fees
  net: number;      // pnl - fees
  trades: number;
}

export interface DailyPnlEntry {
  date: string;     // "YYYY-MM-DD"
  pnl: number;
  fees: number;
  net: number;
  trades: number;
}

// ── Main Dashboard State ────────────────────────────────────────────

export interface DashboardState {
  timestamp: number;
  uptime_seconds: number;
  uptime_info?: UptimeInfo;
  proxy_uptime_info?: ProxyUptimeInfo;
  connected_exchanges: number;
  total_exchanges: number;
  portfolio: Portfolio;
  balances: Record<string, ExchangeBalance>;
  prices: Record<string, Record<string, PriceEntry>>;
  simulation: Simulation;
  recent_trades: Trade[];
  recent_transfers: Transfer[];
  all_trades: Trade[];
  all_transfers: Transfer[];
  hourly_pnl: HourlyPnlEntry[];
  daily_pnl: DailyPnlEntry[];
  settings: Settings;
  all_exchanges: string[];
  all_symbols: string[];
  optimizer: OptimizerState;
  hedges?: HedgeState;
  funding_rates?: Record<string, FundingRateInfo>;
  adaptive_config: AdaptiveConfig;
  all_config_history: ConfigSnapshot[];
  profit_stats: ProfitStats;
  auth_logs?: AuthLogEntry[];
  bot_logs?: BotLogEntry[];
  bot_logs_total?: number;
  demo_comparison?: DemoComparisonState | null;
  // Fee management
  fee_configs?: Record<string, ExchangeFeeConfig>;
  fee_real_mode?: boolean;
  fee_stats?: FeeStats;
  auto_disable_state?: AutoDisableState;
  // Transfer fee management
  transfer_configs?: Record<string, ExchangeTransferConfig>;
  // Anomaly protection
  anomaly_protection?: AnomalyProtectionState;
  manual_stopped?: boolean;
  manual_stop_timestamp?: number;
  distribute_enabled?: boolean;
  custody_hub_exchange?: string;
  custody_hub_network?: string;
  // ── Multi-config (v0.31.0-beta) ───────────────────────────────────
  registry?: RegistryView;
  configs_lite?: ConfigLite[];
  configs_anomaly?: ConfigAnomaly[];
  selected_config_id?: string | null;
  capacity?: CapacitySnapshot;
}

export interface ConfigAnomaly extends AnomalyProtectionState {
  config_id: string;
  group_id: string;
  name: string;
  group_name: string;
  is_super_primary: boolean;
  is_primary: boolean;
  is_default: boolean;
  manual_stopped: boolean;
}

// ── Multi-config types (v0.31.0-beta) ─────────────────────────────────

export interface ConfigMeta {
  id: string;
  name: string;
  description: string;
  is_primary: boolean;
  is_default: boolean;
  is_super_primary: boolean;
  order: number;
}

export interface GroupMeta {
  id: string;
  name: string;
  initial_capital: number;
  order: number;
  configs: ConfigMeta[];
}

export interface RegistryView {
  groups: GroupMeta[];
  super_primary_config_id: string | null;
  default_config_id: string | null;
  shared: {
    execution_mode: string;
    hedge_execution_mode: string;
  };
}

export interface ConfigLite {
  id: string;
  group_id: string;
  name: string;
  group_name: string;
  is_primary: boolean;
  is_default: boolean;
  is_super_primary: boolean;
  execution_mode: string;
  hedge_mode: string;
  portfolio_value: number;
  initial_capital: number;
  net_pnl: number;
  hourly_rate: number;
  session_hourly_rate: number;
  drawdown_pct: number;
  trades_count: number;
  trades_per_minute: number;
  total_transfers: number;
  skipped_trades: number;
  trading_pnl: number;
  transfer_fees: number;
  credited_cashback: number;
  hedge_enabled: boolean;
  hedge_open_count: number;
  hedge_total_notional_usd: number;
  hedge_total_unrealized_pnl_usd: number;
  hedge_cumulative_funding_usd: number;
  hedge_executor_errors: number;
  hedge_safety_paused: boolean;
  anomaly_paused: boolean;
  manual_stopped: boolean;
}

export interface CapacitySnapshot {
  avg_sweep_ms: number;
  p95_sweep_ms: number;
  last_sweep_ms: number;
  config_count: number;
  over_budget: boolean;
  severity: "ok" | "warn" | "critical";
  budget_ms: number;
}
