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
  total_capital?: number;
  auto_rotate?: boolean;
  num_active_symbols?: number;
  max_active_symbols?: number;
  scoring_window?: number;
  evaluation_interval?: number;
  safety_multiplier?: number;
  min_rebalance_score?: number;
  confirmation_period?: number;
  promotion_threshold?: number;
  demotion_threshold?: number;
  demotion_period?: number;
  min_net_profit_pct?: number;
  rebalance_cooldown?: number;
  rebalance_roi_horizon?: number;
  adaptive_mode?: boolean;
  // Security
  ip_whitelist_enabled?: boolean;
  ip_whitelist?: string[];
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
  exchange_transfer_status: Record<string, ExchangeTransferStatus>;
}

export interface ConfigSnapshot {
  timestamp: number;
  reason: string;
  trade_amount: number;
  adaptive_mode: boolean;
  min_net_profit_pct: number;
  rebalance_cooldown: number;
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
  is_profitable: boolean;
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

export interface DashboardState {
  timestamp: number;
  uptime_seconds: number;
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
  settings: Settings;
  all_exchanges: string[];
  all_symbols: string[];
  optimizer: OptimizerState;
  adaptive_config: AdaptiveConfig;
  all_config_history: ConfigSnapshot[];
  profit_stats: ProfitStats;
  auth_logs?: AuthLogEntry[];
}
