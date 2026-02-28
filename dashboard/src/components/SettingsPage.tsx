import { useState, useEffect } from 'react';
import { NavLink, useParams } from 'react-router-dom';
import type { Settings, ExchangeFeeConfig, ExchangeTransferConfig, FeeStats } from '../types';
import FeeManagementTab from './FeeManagementTab';
import TransferFeeManagementTab from './TransferFeeManagementTab';
import Tooltip from './Tooltip';

interface SettingsPageProps {
  currentSettings: Settings;
  onSave: (settings: Settings) => void;
  onApply: (settings: Settings) => void;
  onSendMessage: (msg: object) => void;
  feeConfigs?: Record<string, ExchangeFeeConfig>;
  feeRealMode?: boolean;
  feeStats?: FeeStats;
  transferConfigs?: Record<string, ExchangeTransferConfig>;
}

type SettingsSubTab = 'general' | 'fees' | 'transfers';

export default function SettingsPage({ currentSettings, onSave, onApply, onSendMessage, feeConfigs, feeRealMode, feeStats, transferConfigs }: SettingsPageProps) {
  const { subTab } = useParams<{ subTab?: string }>();
  const activeSubTab: SettingsSubTab = subTab === 'fees' ? 'fees' : subTab === 'transfers' ? 'transfers' : 'general';
  const [tradeAmount, setTradeAmount] = useState(currentSettings.trade_amount_usd);
  const [totalCapital, setTotalCapital] = useState(currentSettings.total_capital ?? 1800);
  const [showConfirm, setShowConfirm] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [autoRotate, setAutoRotate] = useState(currentSettings.auto_rotate ?? true);
  const [numActiveSymbols, setNumActiveSymbols] = useState(currentSettings.num_active_symbols ?? 3);
  const [maxActiveSymbols, setMaxActiveSymbols] = useState(currentSettings.max_active_symbols ?? 8);
  const [scoringWindow, setScoringWindow] = useState(currentSettings.scoring_window ?? 1800);
  const [evaluationInterval, setEvaluationInterval] = useState(currentSettings.evaluation_interval ?? 300);
  const [safetyMultiplier, setSafetyMultiplier] = useState(currentSettings.safety_multiplier ?? 2.0);
  const [minRebalanceScore, setMinRebalanceScore] = useState(currentSettings.min_rebalance_score ?? 0.0001);
  const [confirmationPeriod, setConfirmationPeriod] = useState(currentSettings.confirmation_period ?? 300);
  const [promotionThreshold, setPromotionThreshold] = useState(currentSettings.promotion_threshold ?? 0.0001);
  const [demotionThreshold, setDemotionThreshold] = useState(currentSettings.demotion_threshold ?? 0.0);
  const [demotionPeriod, setDemotionPeriod] = useState(currentSettings.demotion_period ?? 600);
  const [minNetProfitPct, setMinNetProfitPct] = useState(currentSettings.min_net_profit_pct ?? 0.02);
  const [rebalanceCooldown, setRebalanceCooldown] = useState(currentSettings.rebalance_cooldown ?? 30);
  const [minMissesBeforeRebalance, setMinMissesBeforeRebalance] = useState(currentSettings.min_misses_before_rebalance ?? 15);
  const [rebalanceRoiHorizon, setRebalanceRoiHorizon] = useState(currentSettings.rebalance_roi_horizon ?? 1800);
  const [reallocationCostHorizon, setReallocationCostHorizon] = useState(currentSettings.reallocation_cost_horizon ?? 2.0);
  const [demotionCooldownMultiplier, setDemotionCooldownMultiplier] = useState(currentSettings.demotion_cooldown_multiplier ?? 5.0);
  const [hourlyExternalTransferCap, setHourlyExternalTransferCap] = useState(currentSettings.hourly_external_transfer_cap ?? 2.0);
  const [tradingScoreThreshold, setTradingScoreThreshold] = useState(currentSettings.trading_score_threshold ?? 0.01);
  const [strongScoreThreshold, setStrongScoreThreshold] = useState(currentSettings.strong_score_threshold ?? 0.1);
  const [veryStrongScoreThreshold, setVeryStrongScoreThreshold] = useState(currentSettings.very_strong_score_threshold ?? 0.3);
  const [netPnlGateWarmupTrades, setNetPnlGateWarmupTrades] = useState(currentSettings.net_pnl_gate_warmup_trades ?? 10);
  const [netPnlGateGraceSeconds, setNetPnlGateGraceSeconds] = useState(currentSettings.net_pnl_gate_grace_seconds ?? 1800);
  const [rebalanceRoiDivisor, setRebalanceRoiDivisor] = useState(currentSettings.rebalance_roi_divisor ?? 3);
  const [adaptiveMode, setAdaptiveMode] = useState(currentSettings.adaptive_mode ?? true);
  const [executionMode, setExecutionMode] = useState(currentSettings.execution_mode ?? 'simulation');
  const [ipWhitelistEnabled, setIpWhitelistEnabled] = useState(currentSettings.ip_whitelist_enabled ?? false);
  const [ipWhitelist, setIpWhitelist] = useState((currentSettings.ip_whitelist ?? []).join(', '));
  const [securityStatus, setSecurityStatus] = useState<string | null>(null);
  const [showRestartConfirm, setShowRestartConfirm] = useState(false);

  // Sync from server when not dirty
  const settingsKey = JSON.stringify(currentSettings);
  useEffect(() => {
    if (!dirty) {
      setTradeAmount(currentSettings.trade_amount_usd);
      setTotalCapital(currentSettings.total_capital ?? 1800);
      setAutoRotate(currentSettings.auto_rotate ?? true);
      setNumActiveSymbols(currentSettings.num_active_symbols ?? 3);
      setMaxActiveSymbols(currentSettings.max_active_symbols ?? 8);
      setScoringWindow(currentSettings.scoring_window ?? 1800);
      setEvaluationInterval(currentSettings.evaluation_interval ?? 300);
      setSafetyMultiplier(currentSettings.safety_multiplier ?? 2.0);
      setMinRebalanceScore(currentSettings.min_rebalance_score ?? 0.0001);
      setConfirmationPeriod(currentSettings.confirmation_period ?? 300);
      setPromotionThreshold(currentSettings.promotion_threshold ?? 0.0001);
      setDemotionThreshold(currentSettings.demotion_threshold ?? 0.0);
      setDemotionPeriod(currentSettings.demotion_period ?? 600);
      setMinNetProfitPct(currentSettings.min_net_profit_pct ?? 0.02);
      setRebalanceCooldown(currentSettings.rebalance_cooldown ?? 30);
      setMinMissesBeforeRebalance(currentSettings.min_misses_before_rebalance ?? 15);
      setRebalanceRoiHorizon(currentSettings.rebalance_roi_horizon ?? 1800);
      setReallocationCostHorizon(currentSettings.reallocation_cost_horizon ?? 2.0);
      setDemotionCooldownMultiplier(currentSettings.demotion_cooldown_multiplier ?? 5.0);
      setHourlyExternalTransferCap(currentSettings.hourly_external_transfer_cap ?? 2.0);
      setTradingScoreThreshold(currentSettings.trading_score_threshold ?? 0.01);
      setStrongScoreThreshold(currentSettings.strong_score_threshold ?? 0.1);
      setVeryStrongScoreThreshold(currentSettings.very_strong_score_threshold ?? 0.3);
      setNetPnlGateWarmupTrades(currentSettings.net_pnl_gate_warmup_trades ?? 10);
      setNetPnlGateGraceSeconds(currentSettings.net_pnl_gate_grace_seconds ?? 1800);
      setRebalanceRoiDivisor(currentSettings.rebalance_roi_divisor ?? 3);
      setAdaptiveMode(currentSettings.adaptive_mode ?? true);
      setExecutionMode(currentSettings.execution_mode ?? 'simulation');
      setIpWhitelistEnabled(currentSettings.ip_whitelist_enabled ?? false);
      setIpWhitelist((currentSettings.ip_whitelist ?? []).join(', '));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settingsKey]);

  const buildSettings = (): Settings => ({
    trade_amount_usd: tradeAmount,
    total_capital: totalCapital,
    auto_rotate: autoRotate,
    num_active_symbols: numActiveSymbols,
    max_active_symbols: maxActiveSymbols,
    scoring_window: scoringWindow,
    evaluation_interval: evaluationInterval,
    safety_multiplier: safetyMultiplier,
    min_rebalance_score: minRebalanceScore,
    confirmation_period: confirmationPeriod,
    promotion_threshold: promotionThreshold,
    demotion_threshold: demotionThreshold,
    demotion_period: demotionPeriod,
    min_net_profit_pct: minNetProfitPct,
    rebalance_cooldown: rebalanceCooldown,
    min_misses_before_rebalance: minMissesBeforeRebalance,
    rebalance_roi_horizon: rebalanceRoiHorizon,
    trading_score_threshold: tradingScoreThreshold,
    strong_score_threshold: strongScoreThreshold,
    very_strong_score_threshold: veryStrongScoreThreshold,
    net_pnl_gate_warmup_trades: netPnlGateWarmupTrades,
    net_pnl_gate_grace_seconds: netPnlGateGraceSeconds,
    rebalance_roi_divisor: rebalanceRoiDivisor,
    reallocation_cost_horizon: reallocationCostHorizon,
    demotion_cooldown_multiplier: demotionCooldownMultiplier,
    hourly_external_transfer_cap: hourlyExternalTransferCap,
    adaptive_mode: adaptiveMode,
    execution_mode: executionMode,
  });

  const handleSave = () => {
    onSave(buildSettings());
    setDirty(false);
    setSaveStatus('Saved!');
    setTimeout(() => setSaveStatus(null), 2000);
  };

  const handleApply = () => {
    onApply(buildSettings());
    setDirty(false);
    setShowConfirm(false);
    setSaveStatus('Applied!');
    setTimeout(() => setSaveStatus(null), 2000);
  };

  const d = (fn: (v: number) => void, fallback: number) =>
    (e: React.ChangeEvent<HTMLInputElement>) => { setDirty(true); fn(Number(e.target.value) || fallback); };

  return (
    <div className="space-y-4 sm:space-y-6 max-w-3xl">
      {/* Sub-tab navigation */}
      <div className="flex gap-1 bg-slate-800/50 rounded-lg p-1">
        {([
          ['/settings', 'General'],
          ['/settings/fees', 'Fee Management'],
          ['/settings/transfers', 'Transfer Fees'],
        ] as const).map(([to, label]) => (
          <NavLink key={to} to={to} end
            className={({ isActive }) => `flex-1 px-4 py-2 rounded-md text-sm font-medium transition-colors text-center ${
              isActive
                ? 'bg-slate-700 text-white'
                : 'text-slate-400 hover:text-slate-300 hover:bg-slate-700/50'
            }`}>
            {label}
          </NavLink>
        ))}
      </div>

      {activeSubTab === 'fees' ? (
        <FeeManagementTab
          feeConfigs={feeConfigs}
          feeRealMode={feeRealMode}
          feeStats={feeStats}
          onSendMessage={onSendMessage}
        />
      ) : activeSubTab === 'transfers' ? (
        <TransferFeeManagementTab
          transferConfigs={transferConfigs}
          onSendMessage={onSendMessage}
        />
      ) : (
      <>
      {/* Capital */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Capital</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Total Capital ($)
              <Tooltip text="Total USD capital distributed across all exchanges. Used for per-symbol allocation and adaptive trade sizing. Default: $1800" />
            </label>
            <input type="number" value={totalCapital} min={100} onChange={d(setTotalCapital, 1800)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Trade Amount ($)
              <Tooltip text="Base USD amount per trade before multipliers. With adaptive mode: actual size = trade_amount x symbol_multiplier x tick_quality_factor. Lower values ($10-20) work better with limited capital. Default: $20" />
            </label>
            <div className="flex items-center gap-2">
              {[10, 50, 100, 200].map(amt => (
                <button key={amt} onClick={() => { setDirty(true); setTradeAmount(amt); }}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    tradeAmount === amt ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                  }`}>
                  ${amt}
                </button>
              ))}
            </div>
            <input type="number" value={tradeAmount} min={1} onChange={d(setTradeAmount, 10)}
              className="w-full mt-2 bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
        </div>
        <div className="mt-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={adaptiveMode}
              onChange={e => { setDirty(true); setAdaptiveMode(e.target.checked); }}
              className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500" />
            <span className="text-sm text-slate-300">Enable Adaptive Mode</span>
            <Tooltip text="Dynamically adjusts trade sizes, rebalance amounts, and thresholds based on real-time market conditions and available capital. Recommended for small capital (<$5k). Default: enabled" />
          </label>
        </div>
        <div className="mt-4">
          <label className="flex items-center text-sm text-slate-300 mb-1">
            Execution Mode
            <Tooltip text="Simulation: no real orders (default). Demo: places real orders on exchange testnets alongside simulation. Requires API keys in .env. Restart required to take effect." />
          </label>
          <select value={executionMode}
            onChange={e => { setDirty(true); setExecutionMode(e.target.value); }}
            className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
            <option value="simulation">Simulation</option>
            <option value="demo">Demo (Testnet)</option>
          </select>
        </div>
      </div>

      {/* Auto-Rotation */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Auto-Rotation</h2>
        <div className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={autoRotate}
              onChange={e => { setDirty(true); setAutoRotate(e.target.checked); }}
              className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500" />
            <span className="text-sm text-slate-300">Enable automatic symbol rotation</span>
            <Tooltip text="When enabled, the optimizer automatically swaps underperforming symbols for better candidates. When disabled, only the initial symbol set is traded. Default: enabled" />
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label className="flex items-center text-xs text-slate-500 mb-1">
                Min Active Symbols
                <Tooltip text="Starting number of active symbols after discovery. More symbols spread capital thinner but increase diversification. Default: 3" />
              </label>
              <input type="number" value={numActiveSymbols} min={1} max={20} onChange={d(setNumActiveSymbols, 3)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="flex items-center text-xs text-slate-500 mb-1">
                Max Active Symbols
                <Tooltip text="Maximum symbols that can be active simultaneously. Expansion happens when strong candidates appear. Higher values need more capital. Default: 8" />
              </label>
              <input type="number" value={maxActiveSymbols} min={1} max={30} onChange={d(setMaxActiveSymbols, 8)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="flex items-center text-xs text-slate-500 mb-1">
                Scoring Window (s)
                <Tooltip text="Rolling time window (in seconds) for scoring symbol profitability. Longer windows are more stable but slower to react. Default: 1800s (30 min)" />
              </label>
              <input type="number" value={scoringWindow} min={60} onChange={d(setScoringWindow, 1800)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="flex items-center text-xs text-slate-500 mb-1">
                Eval Interval (s)
                <Tooltip text="How often the optimizer evaluates rotations, expansions, and demotions. Shorter intervals react faster but cause more churn. Default: 300s (5 min)" />
              </label>
              <input type="number" value={evaluationInterval} min={30} onChange={d(setEvaluationInterval, 300)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
          </div>
        </div>
      </div>

      {/* Advanced Optimizer */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Advanced Optimizer</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Safety Multiplier
              <Tooltip text="For rotation: estimated hourly gain of new symbol must exceed safety_multiplier x switching cost. Higher values prevent frequent rotations. Default: 2.0" />
            </label>
            <input type="number" value={safetyMultiplier} min={1} step={0.5} onChange={d(setSafetyMultiplier, 2.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Min Rebalance Score
              <Tooltip text="Symbols below this score won't trigger rebalancing. Prevents wasting transfer fees on low-performing symbols. Default: 0.0001" />
            </label>
            <input type="number" value={minRebalanceScore} min={0} step={0.0001}
              onChange={d(setMinRebalanceScore, 0.0001)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Confirmation Period (s)
              <Tooltip text="How long a candidate symbol must sustain a high score before it's eligible for activation. Prevents short-lived spikes from triggering rotations. Default: 300s (5 min)" />
            </label>
            <input type="number" value={confirmationPeriod} min={0} onChange={d(setConfirmationPeriod, 300)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Promotion Threshold
              <Tooltip text="Minimum score for a symbol to enter the watchlist as a candidate. Symbols below this are ignored for promotion. Default: 0.0001" />
            </label>
            <input type="number" value={promotionThreshold} min={0} step={0.0001}
              onChange={d(setPromotionThreshold, 0.0001)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Demotion Threshold
              <Tooltip text="Score below which the demotion timer starts. A symbol must stay below this for the full demotion period to be removed. Set to 0 to only demote at exactly zero. Default: 0.0" />
            </label>
            <input type="number" value={demotionThreshold} min={0} step={0.0001}
              onChange={d(setDemotionThreshold, 0.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Demotion Period (s)
              <Tooltip text="How long a symbol must stay below demotion threshold before being deactivated. Tiered: weaker scores are demoted faster. Default: 600s (10 min)" />
            </label>
            <input type="number" value={demotionPeriod} min={0} onChange={d(setDemotionPeriod, 600)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Min Net Profit %
              <Tooltip text="Minimum net spread (after fees) required to execute a trade. Higher values skip marginal opportunities. Set lower for high-frequency, low-spread strategies. Default: 0.02%" />
            </label>
            <input type="number" value={minNetProfitPct} min={0} step={0.01}
              onChange={d(setMinNetProfitPct, 0.02)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Rebalance Cooldown (s)
              <Tooltip text="Minimum seconds between rebalances for the same exchange/direction pair. Prevents rapid-fire transfers. Default: 30s" />
            </label>
            <input type="number" value={rebalanceCooldown} min={0} onChange={d(setRebalanceCooldown, 30)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Miss Streak Before Rebalance
              <Tooltip text="Consecutive missed trades (due to insufficient balance) before triggering a rebalance. Dynamic in adaptive mode: adjusts 10-30 based on trade frequency. Default: 15" />
            </label>
            <input type="number" value={minMissesBeforeRebalance} min={1} max={100} step={1}
              onChange={d(setMinMissesBeforeRebalance, 15)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Rebalance ROI Horizon (s)
              <Tooltip text="Maximum time to recoup the cost of a rebalance transfer. If estimated recovery time exceeds this, the rebalance is blocked. Default: 1800s (30 min)" />
            </label>
            <input type="number" value={rebalanceRoiHorizon} min={0} onChange={d(setRebalanceRoiHorizon, 1800)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
        </div>

        {/* Score Thresholds */}
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mt-6 mb-3">Score Thresholds</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Trading Threshold
              <Tooltip text="Minimum score to allow trading and rebalancing for a symbol. Below this, the symbol gets trade_multiplier = 0 (no trading). Default: 0.01" />
            </label>
            <input type="number" value={tradingScoreThreshold} min={0.001} max={0.5} step={0.001}
              onChange={d(setTradingScoreThreshold, 0.01)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Strong Threshold
              <Tooltip text="Score for the Strong tier. Strong symbols get 2-3x trade multiplier and up to 2 exchanges per direction. Default: 0.1" />
            </label>
            <input type="number" value={strongScoreThreshold} min={0.01} max={1.0} step={0.01}
              onChange={d(setStrongScoreThreshold, 0.1)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Very Strong Threshold
              <Tooltip text="Score for the Very Strong tier. Very Strong symbols get 3-4x trade multiplier and up to 3 exchanges per direction. Default: 0.3" />
            </label>
            <input type="number" value={veryStrongScoreThreshold} min={0.05} max={2.0} step={0.05}
              onChange={d(setVeryStrongScoreThreshold, 0.3)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
        </div>

        {/* Net P&L Gate */}
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mt-6 mb-3">Net P&L Gate</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Warmup Trades
              <Tooltip text="Number of trades before the net P&L gate activates. During warmup, rebalancing is always allowed. Prevents premature blocking from a few early bad trades. Default: 10" />
            </label>
            <input type="number" value={netPnlGateWarmupTrades} min={1} max={200} step={1}
              onChange={d(setNetPnlGateWarmupTrades, 10)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Grace Period (s)
              <Tooltip text="Time after bot start before the net P&L gate activates. During grace period, rebalancing is always allowed regardless of profitability. Default: 1800s (30 min)" />
            </label>
            <input type="number" value={netPnlGateGraceSeconds} min={60} max={7200} step={60}
              onChange={d(setNetPnlGateGraceSeconds, 1800)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              ROI Gate Divisor
              <Tooltip text="Controls rebalancing sensitivity. ROI threshold = fee_rate / divisor. Higher values (5-10) allow rebalancing at lower expected profit, good for small capital. Default: 3" />
            </label>
            <input type="number" value={rebalanceRoiDivisor} min={2} max={20} step={1}
              onChange={d(setRebalanceRoiDivisor, 3)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
        </div>

        {/* Profitability Controls */}
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mt-6 mb-3">Profitability Controls</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Reallocation Cost Horizon (h)
              <Tooltip text="Hours of estimated profit a symbol must generate to justify the cost of switching its dominant exchange pair. Higher values prevent expensive re-allocations for marginal improvements. Default: 2.0" />
            </label>
            <input type="number" value={reallocationCostHorizon} min={0.5} max={24} step={0.5}
              onChange={d(setReallocationCostHorizon, 2.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Demotion Cooldown Multiplier
              <Tooltip text="Cooldown after demotion = demotion_period × this multiplier. Higher values prevent symbols from churning in and out. With default 5.0 and 600s period: 50 min cooldown. Default: 5.0" />
            </label>
            <input type="number" value={demotionCooldownMultiplier} min={1} max={20} step={0.5}
              onChange={d(setDemotionCooldownMultiplier, 5.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Hourly External Transfer Cap ($)
              <Tooltip text="Maximum USD spent on external withdrawal fees per rolling hour. Internal rebalances (crypto sell/buy on same exchange) are not limited. Set to 0 to disable. Default: $2.00" />
            </label>
            <input type="number" value={hourlyExternalTransferCap} min={0} max={100} step={0.5}
              onChange={d(setHourlyExternalTransferCap, 2.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
        </div>
      </div>

      {/* Security */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Security</h2>
        <div className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={ipWhitelistEnabled}
              onChange={e => setIpWhitelistEnabled(e.target.checked)}
              className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500" />
            <span className="text-sm text-slate-300">Enable IP Whitelist</span>
            <Tooltip text="Restrict dashboard access to specific IP addresses. When enabled, connections from non-whitelisted IPs are immediately denied. Leave the list empty to allow all." />
          </label>
          {ipWhitelistEnabled && (
            <div>
              <label className="flex items-center text-xs text-slate-500 mb-1">
                Allowed IPs (comma-separated)
                <Tooltip text="Enter IPv4 or IPv6 addresses separated by commas. Changes take effect immediately after saving. Example: 212.253.218.204, 10.0.0.1" />
              </label>
              <input type="text" value={ipWhitelist}
                onChange={e => setIpWhitelist(e.target.value)}
                placeholder="e.g. 212.253.218.204, 10.0.0.1"
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500 placeholder-slate-500" />
            </div>
          )}
          <div className="flex items-center gap-3">
            <button onClick={() => {
              const ips = ipWhitelist.split(',').map(s => s.trim()).filter(Boolean);
              onSendMessage({
                type: 'save_security_settings',
                settings: { ip_whitelist_enabled: ipWhitelistEnabled, ip_whitelist: ips },
              });
              setSecurityStatus('Saved!');
              setTimeout(() => setSecurityStatus(null), 2000);
            }}
              className="px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm font-medium transition-colors">
              Save Security
            </button>
            {securityStatus && (
              <span className="text-emerald-400 text-sm font-medium">{securityStatus}</span>
            )}
          </div>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="bg-red-950/30 border border-red-900/50 rounded-lg p-3 sm:p-5">
        <h2 className="text-sm font-semibold text-red-400 uppercase tracking-wider mb-3">Danger Zone</h2>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <p className="text-sm text-slate-300">Restart Bot</p>
            <p className="text-xs text-slate-500 mt-0.5">Discard all session data and start fresh with ${totalCapital}.</p>
          </div>
          <button onClick={() => setShowRestartConfirm(true)}
            className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors">
            Restart Bot
          </button>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap items-center gap-3 sm:gap-4">
        <button onClick={handleSave}
          className="px-6 py-2.5 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm font-medium transition-colors">
          Save for Next Restart
        </button>
        <button onClick={() => setShowConfirm(true)}
          className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors">
          Apply Now
        </button>
        {saveStatus && (
          <span className="text-emerald-400 text-sm font-medium">{saveStatus}</span>
        )}
      </div>

      {/* Restart Confirmation Modal */}
      {showRestartConfirm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl p-6 max-w-md w-full mx-4 border border-red-900/50">
            <h3 className="text-lg font-semibold text-white mb-2">Restart Bot?</h3>
            <p className="text-slate-400 text-sm mb-4">
              Are you sure? This will discard all current session data and start fresh with ${totalCapital}.
            </p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setShowRestartConfirm(false)}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm">
                Cancel
              </button>
              <button onClick={() => {
                onSendMessage({ type: 'restart' });
                setShowRestartConfirm(false);
              }}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm font-medium">
                Restart
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Modal */}
      {showConfirm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl p-6 max-w-md w-full mx-4 border border-slate-700">
            <h3 className="text-lg font-semibold text-white mb-2">Reset Simulation?</h3>
            <p className="text-slate-400 text-sm mb-4">
              This will save settings and restart discovery with the new configuration.
              All current trade history and balances will be reset. Historical stats are preserved.
            </p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setShowConfirm(false)}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm">
                Cancel
              </button>
              <button onClick={handleApply}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium">
                Apply & Reset
              </button>
            </div>
          </div>
        </div>
      )}
      </>
      )}
    </div>
  );
}
