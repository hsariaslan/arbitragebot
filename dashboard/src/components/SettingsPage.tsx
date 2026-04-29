import { useState, useEffect } from 'react';
import { NavLink, useParams } from 'react-router-dom';
import type { Settings, ExchangeFeeConfig, ExchangeTransferConfig, FeeStats, AnomalyProtectionState, ExchangeBalance } from '../types';
import FeeManagementTab from './FeeManagementTab';
import TransferFeeManagementTab from './TransferFeeManagementTab';
import Tooltip from './Tooltip';

interface SettingsPageProps {
  currentSettings: Settings;
  onSave: (settings: Settings) => void;
  onApply: (settings: Settings) => void;
  onSendMessage: (msg: object) => void;
  onSendWithCallback: (msg: object, callback: (data: any) => void) => void;
  feeConfigs?: Record<string, ExchangeFeeConfig>;
  feeRealMode?: boolean;
  feeStats?: FeeStats;
  transferConfigs?: Record<string, ExchangeTransferConfig>;
  anomalyProtection?: AnomalyProtectionState;
  manualStopped?: boolean;
  balances?: Record<string, ExchangeBalance>;
  distributeEnabled?: boolean;
}

type SettingsSubTab = 'general' | 'fees' | 'transfers';

export default function SettingsPage({ currentSettings, onSave, onApply, onSendMessage, onSendWithCallback, feeConfigs, feeRealMode, feeStats, transferConfigs, anomalyProtection, manualStopped, balances, distributeEnabled }: SettingsPageProps) {
  const { subTab } = useParams<{ subTab?: string }>();
  const activeSubTab: SettingsSubTab = subTab === 'fees' ? 'fees' : subTab === 'transfers' ? 'transfers' : 'general';
  const [tradeAmount, setTradeAmount] = useState(currentSettings.trade_amount_usd);
  const [tradeAmountPct, setTradeAmountPct] = useState(currentSettings.trade_amount_pct ?? 0);
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
  const [discoveryDuration, setDiscoveryDuration] = useState(currentSettings.discovery_duration ?? 300);
  const [minRebalanceScore, setMinRebalanceScore] = useState(currentSettings.min_rebalance_score ?? 0.0001);
  const [confirmationPeriod, setConfirmationPeriod] = useState(currentSettings.confirmation_period ?? 300);
  const [scoreStabilitySeconds, setScoreStabilitySeconds] = useState(currentSettings.score_stability_seconds ?? 120);
  const [scoreStabilityFactor, setScoreStabilityFactor] = useState(currentSettings.score_stability_factor ?? 0.5);
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
  const [bitfinexReservePct, setBitfinexReservePct] = useState(currentSettings.bitfinex_reserve_pct ?? 0.15);
  const [bitfinexReserveHardFloor, setBitfinexReserveHardFloor] = useState(currentSettings.bitfinex_reserve_hard_floor ?? 0.05);
  const [netPctSizingEnabled, setNetPctSizingEnabled] = useState(currentSettings.net_pct_sizing_enabled ?? true);
  const [netPctMultiplierCap, setNetPctMultiplierCap] = useState(currentSettings.net_pct_multiplier_cap ?? 2.5);
  const [tradingScoreThreshold, setTradingScoreThreshold] = useState(currentSettings.trading_score_threshold ?? 0.01);
  const [feeThresholdMultiplier, setFeeThresholdMultiplier] = useState(currentSettings.fee_threshold_multiplier ?? 0.5);
  const [strongScoreThreshold, setStrongScoreThreshold] = useState(currentSettings.strong_score_threshold ?? 0.1);
  const [veryStrongScoreThreshold, setVeryStrongScoreThreshold] = useState(currentSettings.very_strong_score_threshold ?? 0.3);
  const [netPnlGateWarmupTrades, setNetPnlGateWarmupTrades] = useState(currentSettings.net_pnl_gate_warmup_trades ?? 10);
  const [netPnlGateGraceSeconds, setNetPnlGateGraceSeconds] = useState(currentSettings.net_pnl_gate_grace_seconds ?? 1800);
  const [rebalanceRoiDivisor, setRebalanceRoiDivisor] = useState(currentSettings.rebalance_roi_divisor ?? 3);
  const [adaptiveMode, setAdaptiveMode] = useState(currentSettings.adaptive_mode ?? true);
  const [executionMode, setExecutionMode] = useState(currentSettings.execution_mode ?? 'simulation');
  const [ipWhitelistEnabled, setIpWhitelistEnabled] = useState(currentSettings.ip_whitelist_enabled ?? false);
  const [ipWhitelist, setIpWhitelist] = useState((currentSettings.ip_whitelist ?? []).join(', '));
  const [spreadPersistenceTicks, setSpreadPersistenceTicks] = useState(currentSettings.spread_persistence_ticks ?? 1);
  const [evdSellerPenalty, setEvdSellerPenalty] = useState(currentSettings.event_driven_seller_penalty_pct ?? 0.05);
  const [oneLegFailureRate, setOneLegFailureRate] = useState(currentSettings.one_leg_failure_rate ?? 0.02);
  const [oneLegUnwindSlippageMult, setOneLegUnwindSlippageMult] = useState(currentSettings.one_leg_unwind_slippage_mult ?? 1.5);
  const [maxPositionMultiplier, setMaxPositionMultiplier] = useState(currentSettings.max_position_multiplier ?? 5.0);
  // Funding-aware scoring (Phase A)
  const [diversificationFloorEnabled, setDiversificationFloorEnabled] = useState(currentSettings.diversification_floor_enabled ?? true);
  const [diversificationFloorMultiplier, setDiversificationFloorMultiplier] = useState(currentSettings.diversification_floor_multiplier ?? 0.7);
  const [fundingAwareEnabled, setFundingAwareEnabled] = useState(currentSettings.funding_aware_scoring_enabled ?? true);
  const [fundingSkip4h, setFundingSkip4h] = useState(currentSettings.funding_skip_threshold_4h_pct ?? -0.05);
  const [fundingSkip8h, setFundingSkip8h] = useState(currentSettings.funding_skip_threshold_8h_pct ?? -0.05);
  const [fundingScoreMin, setFundingScoreMin] = useState(currentSettings.funding_score_min_factor ?? 0.3);
  const [fundingScoreMax, setFundingScoreMax] = useState(currentSettings.funding_score_max_factor ?? 1.5);
  const [fundingPollInterval, setFundingPollInterval] = useState(currentSettings.funding_poll_interval_seconds ?? 60.0);
  // Hedging (Phase C+ — shadow mode in C, live in D)
  const [hedgingEnabled, setHedgingEnabled] = useState(currentSettings.hedging_enabled ?? true);
  const [hedgeExecutionMode, setHedgeExecutionMode] = useState(currentSettings.hedge_execution_mode ?? 'simulation');
  const [hedgeDustThreshold, setHedgeDustThreshold] = useState(currentSettings.hedge_dust_threshold_usd ?? 20.0);
  const [hedgeEvalInterval, setHedgeEvalInterval] = useState(currentSettings.hedge_evaluation_interval_seconds ?? 300.0);
  const [hedgeMarginBuffer, setHedgeMarginBuffer] = useState(currentSettings.hedge_margin_buffer_pct ?? 0.20);
  const [hedgeAdjustThreshold, setHedgeAdjustThreshold] = useState(currentSettings.hedge_adjust_threshold_pct ?? 0.10);
  const [anomalyEnabled, setAnomalyEnabled] = useState(currentSettings.anomaly_protection_enabled ?? true);
  const [cbWindow, setCbWindow] = useState(currentSettings.circuit_breaker_window ?? 900);
  const [cbThreshold, setCbThreshold] = useState(currentSettings.circuit_breaker_threshold ?? -5.0);
  const [cbResumePct, setCbResumePct] = useState(currentSettings.circuit_breaker_resume_pct ?? 0.5);
  const [cbCooldown, setCbCooldown] = useState(currentSettings.circuit_breaker_cooldown ?? 300);
  const [ddThreshold, setDdThreshold] = useState(currentSettings.drawdown_threshold_pct ?? 5.0);
  const [ddResumePct, setDdResumePct] = useState(currentSettings.drawdown_resume_pct ?? 3.0);
  const [ddEmergencyMult, setDdEmergencyMult] = useState(currentSettings.drawdown_emergency_mult ?? 2.0);
  const [lsThreshold, setLsThreshold] = useState(currentSettings.symbol_loss_streak_threshold ?? 4);
  const [lsCooldown, setLsCooldown] = useState(currentSettings.symbol_loss_streak_cooldown ?? 300);
  const [warningPnlPct, setWarningPnlPct] = useState(currentSettings.warning_pnl_pct ?? 0.5);
  const [showStopConfirm, setShowStopConfirm] = useState(false);
  const [securityStatus, setSecurityStatus] = useState<string | null>(null);
  const [showRestartConfirm, setShowRestartConfirm] = useState(false);
  const [showHardStop, setShowHardStop] = useState(false);
  const [hardStopBitfinex, setHardStopBitfinex] = useState(true);
  const [hardStopConfirmText, setHardStopConfirmText] = useState('');
  const [hardStopResult, setHardStopResult] = useState<{ positions_sold: number; total_gross: number; total_fees: number; total_net: number; sells: { exchange: string; symbol: string; qty: number; price: number; gross: number; fee: number; net: number; path: string }[] } | null>(null);
  const [showDistribute, setShowDistribute] = useState(false);
  const [distributeConfirmText, setDistributeConfirmText] = useState('');
  const [distributeResult, setDistributeResult] = useState<{ distributed: number; transfers: { exchange: string; amount: number }[]; strategy: string } | null>(null);

  // Sync from server when not dirty
  const settingsKey = JSON.stringify(currentSettings);
  useEffect(() => {
    if (!dirty) {
      setTradeAmount(currentSettings.trade_amount_usd);
      setTradeAmountPct(currentSettings.trade_amount_pct ?? 0);
      setTotalCapital(currentSettings.total_capital ?? 1800);
      setAutoRotate(currentSettings.auto_rotate ?? true);
      setNumActiveSymbols(currentSettings.num_active_symbols ?? 3);
      setMaxActiveSymbols(currentSettings.max_active_symbols ?? 8);
      setScoringWindow(currentSettings.scoring_window ?? 1800);
      setEvaluationInterval(currentSettings.evaluation_interval ?? 300);
      setSafetyMultiplier(currentSettings.safety_multiplier ?? 2.0);
      setDiscoveryDuration(currentSettings.discovery_duration ?? 300);
      setMinRebalanceScore(currentSettings.min_rebalance_score ?? 0.0001);
      setConfirmationPeriod(currentSettings.confirmation_period ?? 300);
      setScoreStabilitySeconds(currentSettings.score_stability_seconds ?? 120);
      setScoreStabilityFactor(currentSettings.score_stability_factor ?? 0.5);
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
      setBitfinexReservePct(currentSettings.bitfinex_reserve_pct ?? 0.15);
      setBitfinexReserveHardFloor(currentSettings.bitfinex_reserve_hard_floor ?? 0.05);
      setNetPctSizingEnabled(currentSettings.net_pct_sizing_enabled ?? true);
      setNetPctMultiplierCap(currentSettings.net_pct_multiplier_cap ?? 2.5);
      setTradingScoreThreshold(currentSettings.trading_score_threshold ?? 0.01);
      setFeeThresholdMultiplier(currentSettings.fee_threshold_multiplier ?? 0.5);
      setStrongScoreThreshold(currentSettings.strong_score_threshold ?? 0.1);
      setVeryStrongScoreThreshold(currentSettings.very_strong_score_threshold ?? 0.3);
      setNetPnlGateWarmupTrades(currentSettings.net_pnl_gate_warmup_trades ?? 10);
      setNetPnlGateGraceSeconds(currentSettings.net_pnl_gate_grace_seconds ?? 1800);
      setRebalanceRoiDivisor(currentSettings.rebalance_roi_divisor ?? 3);
      setAdaptiveMode(currentSettings.adaptive_mode ?? true);
      setExecutionMode(currentSettings.execution_mode ?? 'simulation');
      setSpreadPersistenceTicks(currentSettings.spread_persistence_ticks ?? 1);
      setEvdSellerPenalty(currentSettings.event_driven_seller_penalty_pct ?? 0.05);
      setOneLegFailureRate(currentSettings.one_leg_failure_rate ?? 0.02);
      setOneLegUnwindSlippageMult(currentSettings.one_leg_unwind_slippage_mult ?? 1.5);
      setMaxPositionMultiplier(currentSettings.max_position_multiplier ?? 5.0);
      setDiversificationFloorEnabled(currentSettings.diversification_floor_enabled ?? true);
      setDiversificationFloorMultiplier(currentSettings.diversification_floor_multiplier ?? 0.7);
      setFundingAwareEnabled(currentSettings.funding_aware_scoring_enabled ?? true);
      setFundingSkip4h(currentSettings.funding_skip_threshold_4h_pct ?? -0.05);
      setFundingSkip8h(currentSettings.funding_skip_threshold_8h_pct ?? -0.05);
      setFundingScoreMin(currentSettings.funding_score_min_factor ?? 0.3);
      setFundingScoreMax(currentSettings.funding_score_max_factor ?? 1.5);
      setFundingPollInterval(currentSettings.funding_poll_interval_seconds ?? 60.0);
      setHedgingEnabled(currentSettings.hedging_enabled ?? true);
      setHedgeExecutionMode(currentSettings.hedge_execution_mode ?? 'simulation');
      setHedgeDustThreshold(currentSettings.hedge_dust_threshold_usd ?? 20.0);
      setHedgeEvalInterval(currentSettings.hedge_evaluation_interval_seconds ?? 300.0);
      setHedgeMarginBuffer(currentSettings.hedge_margin_buffer_pct ?? 0.20);
      setHedgeAdjustThreshold(currentSettings.hedge_adjust_threshold_pct ?? 0.10);
      setIpWhitelistEnabled(currentSettings.ip_whitelist_enabled ?? false);
      setIpWhitelist((currentSettings.ip_whitelist ?? []).join(', '));
      setAnomalyEnabled(currentSettings.anomaly_protection_enabled ?? true);
      setCbWindow(currentSettings.circuit_breaker_window ?? 900);
      setCbThreshold(currentSettings.circuit_breaker_threshold ?? -5.0);
      setCbResumePct(currentSettings.circuit_breaker_resume_pct ?? 0.5);
      setCbCooldown(currentSettings.circuit_breaker_cooldown ?? 300);
      setDdThreshold(currentSettings.drawdown_threshold_pct ?? 5.0);
      setDdResumePct(currentSettings.drawdown_resume_pct ?? 3.0);
      setDdEmergencyMult(currentSettings.drawdown_emergency_mult ?? 2.0);
      setLsThreshold(currentSettings.symbol_loss_streak_threshold ?? 4);
      setLsCooldown(currentSettings.symbol_loss_streak_cooldown ?? 300);
      setWarningPnlPct(currentSettings.warning_pnl_pct ?? 0.5);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settingsKey]);

  const buildSettings = (): Settings => ({
    trade_amount_usd: tradeAmount,
    trade_amount_pct: tradeAmountPct,
    total_capital: totalCapital,
    auto_rotate: autoRotate,
    num_active_symbols: numActiveSymbols,
    max_active_symbols: maxActiveSymbols,
    scoring_window: scoringWindow,
    evaluation_interval: evaluationInterval,
    safety_multiplier: safetyMultiplier,
    discovery_duration: discoveryDuration,
    min_rebalance_score: minRebalanceScore,
    confirmation_period: confirmationPeriod,
    score_stability_seconds: scoreStabilitySeconds,
    score_stability_factor: scoreStabilityFactor,
    promotion_threshold: promotionThreshold,
    demotion_threshold: demotionThreshold,
    demotion_period: demotionPeriod,
    min_net_profit_pct: minNetProfitPct,
    rebalance_cooldown: rebalanceCooldown,
    min_misses_before_rebalance: minMissesBeforeRebalance,
    rebalance_roi_horizon: rebalanceRoiHorizon,
    trading_score_threshold: tradingScoreThreshold,
    fee_threshold_multiplier: feeThresholdMultiplier,
    strong_score_threshold: strongScoreThreshold,
    very_strong_score_threshold: veryStrongScoreThreshold,
    net_pnl_gate_warmup_trades: netPnlGateWarmupTrades,
    net_pnl_gate_grace_seconds: netPnlGateGraceSeconds,
    rebalance_roi_divisor: rebalanceRoiDivisor,
    reallocation_cost_horizon: reallocationCostHorizon,
    demotion_cooldown_multiplier: demotionCooldownMultiplier,
    hourly_external_transfer_cap: hourlyExternalTransferCap,
    bitfinex_reserve_pct: bitfinexReservePct,
    bitfinex_reserve_hard_floor: bitfinexReserveHardFloor,
    net_pct_sizing_enabled: netPctSizingEnabled,
    net_pct_multiplier_cap: netPctMultiplierCap,
    adaptive_mode: adaptiveMode,
    execution_mode: executionMode,
    spread_persistence_ticks: spreadPersistenceTicks,
    event_driven_seller_penalty_pct: evdSellerPenalty,
    one_leg_failure_rate: oneLegFailureRate,
    one_leg_unwind_slippage_mult: oneLegUnwindSlippageMult,
    max_position_multiplier: maxPositionMultiplier,
    diversification_floor_enabled: diversificationFloorEnabled,
    diversification_floor_multiplier: diversificationFloorMultiplier,
    funding_aware_scoring_enabled: fundingAwareEnabled,
    funding_skip_threshold_4h_pct: fundingSkip4h,
    funding_skip_threshold_8h_pct: fundingSkip8h,
    funding_score_min_factor: fundingScoreMin,
    funding_score_max_factor: fundingScoreMax,
    funding_poll_interval_seconds: fundingPollInterval,
    hedging_enabled: hedgingEnabled,
    hedge_execution_mode: hedgeExecutionMode,
    hedge_dust_threshold_usd: hedgeDustThreshold,
    hedge_evaluation_interval_seconds: hedgeEvalInterval,
    hedge_margin_buffer_pct: hedgeMarginBuffer,
    hedge_adjust_threshold_pct: hedgeAdjustThreshold,
    anomaly_protection_enabled: anomalyEnabled,
    circuit_breaker_window: cbWindow,
    circuit_breaker_threshold: cbThreshold,
    circuit_breaker_resume_pct: cbResumePct,
    circuit_breaker_cooldown: cbCooldown,
    drawdown_threshold_pct: ddThreshold,
    drawdown_resume_pct: ddResumePct,
    drawdown_emergency_mult: ddEmergencyMult,
    symbol_loss_streak_threshold: lsThreshold,
    symbol_loss_streak_cooldown: lsCooldown,
    warning_pnl_pct: warningPnlPct,
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
    (e: React.ChangeEvent<HTMLInputElement>) => { const v = Number(e.target.value); setDirty(true); fn(Number.isNaN(v) ? fallback : v); };

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
              <Tooltip text="Total USD capital distributed across all exchanges. Used for per-symbol allocation and adaptive trade sizing. Default: $1800. Config key: total_capital" />
            </label>
            <input type="number" value={totalCapital} min={100} onChange={d(setTotalCapital, 1800)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Trade Amount
              <Tooltip text="Base USD amount per trade before multipliers. 'Fixed $' sets a static amount. '% of Capital' auto-scales with total capital (e.g., 1% of $3000 = $30). With adaptive mode: actual size = trade_amount x symbol_multiplier x net%_factor. Config key: trade_amount_usd / trade_amount_pct" />
            </label>
            {/* Mode toggle */}
            <div className="flex items-center gap-1 mb-2">
              <button onClick={() => { setDirty(true); setTradeAmountPct(0); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  tradeAmountPct === 0 ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                }`}>
                Fixed $
              </button>
              <button onClick={() => { setDirty(true); if (tradeAmountPct === 0) setTradeAmountPct(0.01); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  tradeAmountPct > 0 ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                }`}>
                % of Capital
              </button>
            </div>
            {tradeAmountPct > 0 ? (
              <>
                <div className="flex items-center gap-2">
                  {[0.005, 0.01, 0.02, 0.05].map(pct => (
                    <button key={pct} onClick={() => { setDirty(true); setTradeAmountPct(pct); }}
                      className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                        tradeAmountPct === pct ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                      }`}>
                      {(pct * 100).toFixed(1)}%
                    </button>
                  ))}
                </div>
                <input type="number" value={Math.round(tradeAmountPct * 10000) / 100} min={0.1} max={50} step={0.1}
                  onChange={e => { setDirty(true); setTradeAmountPct(Math.max(0.001, (Number(e.target.value) || 1) / 100)); }}
                  className="w-full mt-2 bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                <div className="text-xs text-slate-400 mt-1">
                  = <span className="text-green-400 font-medium">${(totalCapital * tradeAmountPct).toFixed(2)}</span> per trade ({(tradeAmountPct * 100).toFixed(1)}% of ${totalCapital.toLocaleString()})
                </div>
              </>
            ) : (
              <>
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
              </>
            )}
          </div>
        </div>
        <div className="mt-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={adaptiveMode}
              onChange={e => { setDirty(true); setAdaptiveMode(e.target.checked); }}
              className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500" />
            <span className="text-sm text-slate-300">Enable Adaptive Mode</span>
            <Tooltip text="Dynamically adjusts trade sizes, rebalance amounts, and thresholds based on real-time market conditions and available capital. Recommended for small capital (<$5k). Default: enabled. Config key: adaptive_mode" />
          </label>
        </div>
        <div className="mt-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={netPctSizingEnabled}
              onChange={e => { setDirty(true); setNetPctSizingEnabled(e.target.checked); }}
              className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500" />
            <span className="text-sm text-slate-300">Enable Net% Sizing</span>
            <Tooltip text="Scale trade size based on current tick's net profitability. Higher net% spreads get larger trades (up to cap). Tiers: <0.03%=0.5x, 0.03-0.08%=1.0x, 0.08-0.15%=1.5x, 0.15-0.25%=2.0x, >0.25%=2.5x. Multiplies with score-based multiplier. Default: enabled. Config key: net_pct_sizing_enabled" />
          </label>
        </div>
        <div className="mt-4">
          <label className="flex items-center text-xs text-slate-500 mb-1">
            Net% Multiplier Cap
            <Tooltip text="Maximum net%-based trade size multiplier. Caps the upside of net% scaling to prevent over-concentration on single ticks. Combined with score multiplier, final size is still limited by available balance. Range: 1.0-10.0. Default: 2.5. Config key: net_pct_multiplier_cap" />
          </label>
          <input type="number" value={netPctMultiplierCap} min={1.0} max={10.0} step={0.1}
            onChange={d(setNetPctMultiplierCap, 2.5)}
            className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <div className="mt-4">
          <label className="flex items-center text-sm text-slate-300 mb-1">
            Execution Mode
            <Tooltip text="Simulation: no real orders (default). Demo + Simulation: places real orders on Binance/OKX/Bybit testnets alongside simulation on all 9 exchanges — useful for broad market coverage with partial demo validation. Demo Only: restricts trading to only Binance/OKX/Bybit (the 3 demo-capable exchanges) — every trade gets demo orders for comprehensive sim-vs-demo comparison. Requires API keys in .env. Restart required to take effect. Config key: execution_mode" />
          </label>
          <select value={executionMode}
            onChange={e => { setDirty(true); setExecutionMode(e.target.value); }}
            className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
            <option value="simulation">Simulation</option>
            <option value="demo">Demo + Simulation</option>
            <option value="demo_only">Demo Only (Binance/OKX/Bybit)</option>
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
            <Tooltip text="When enabled, the optimizer automatically swaps underperforming symbols for better candidates. When disabled, only the initial symbol set is traded. Default: enabled. Config key: auto_rotate" />
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label className="flex items-center text-xs text-slate-500 mb-1">
                Min Active Symbols
                <Tooltip text="Starting number of active symbols after discovery. More symbols spread capital thinner but increase diversification. Default: 3. Config key: num_active_symbols" />
              </label>
              <input type="number" value={numActiveSymbols} min={1} max={20} onChange={d(setNumActiveSymbols, 3)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="flex items-center text-xs text-slate-500 mb-1">
                Max Active Symbols
                <Tooltip text="Maximum symbols that can be active simultaneously. Expansion happens when strong candidates appear. Higher values need more capital. Default: 8. Config key: max_active_symbols" />
              </label>
              <input type="number" value={maxActiveSymbols} min={1} max={30} onChange={d(setMaxActiveSymbols, 8)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="flex items-center text-xs text-slate-500 mb-1">
                Scoring Window (s)
                <Tooltip text="Rolling time window (in seconds) for scoring symbol profitability. Longer windows are more stable but slower to react. Default: 1800s (30 min). Config key: scoring_window" />
              </label>
              <input type="number" value={scoringWindow} min={60} onChange={d(setScoringWindow, 1800)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="flex items-center text-xs text-slate-500 mb-1">
                Eval Interval (s)
                <Tooltip text="How often the optimizer evaluates rotations, expansions, and demotions. Shorter intervals react faster but cause more churn. Default: 300s (5 min). Config key: evaluation_interval" />
              </label>
              <input type="number" value={evaluationInterval} min={30} onChange={d(setEvaluationInterval, 300)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="flex items-center text-xs text-slate-500 mb-1">
                Discovery Duration (s)
                <Tooltip text="Base duration of the discovery phase where the bot scans all symbols for opportunities before activating. Auto-extends up to 3600s if no symbols qualify. Early exit after 60s if any symbol reaches trading threshold. Default: 300s (5 min). Config key: discovery_duration" />
              </label>
              <input type="number" value={discoveryDuration} min={30} max={3600} onChange={d(setDiscoveryDuration, 300)}
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
              <Tooltip text="For rotation: estimated hourly gain of new symbol must exceed safety_multiplier x switching cost. Higher values prevent frequent rotations. Default: 2.0. Config key: safety_multiplier" />
            </label>
            <input type="number" value={safetyMultiplier} min={1} step={0.5} onChange={d(setSafetyMultiplier, 2.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Min Rebalance Score
              <Tooltip text="Symbols below this score won't trigger rebalancing. Prevents wasting transfer fees on low-performing symbols. Default: 0.0001. Config key: min_rebalance_score" />
            </label>
            <input type="number" value={minRebalanceScore} min={0} step={0.0001}
              onChange={d(setMinRebalanceScore, 0.0001)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Confirmation Period (s)
              <Tooltip text="How long a candidate symbol must sustain a high score before it's eligible for activation. Prevents short-lived spikes from triggering rotations. Default: 300s (5 min). Config key: confirmation_period" />
            </label>
            <input type="number" value={confirmationPeriod} min={0} onChange={d(setConfirmationPeriod, 300)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Score Stability (s)
              <Tooltip text="Minimum observation time before a candidate can be confirmed. Even very strong symbols must wait this long. Tracks score trend for cliff drops and declining patterns. Set to 0 to disable. Default: 120s. Config key: score_stability_seconds" />
            </label>
            <input type="number" value={scoreStabilitySeconds} min={0} max={3600} onChange={d(setScoreStabilitySeconds, 120)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Stability Factor
              <Tooltip text="Reject candidate if current score drops below peak score x this factor (cliff drop detection). E.g., 0.5 means reject if score fell more than 50% from its peak. Set to 0 to disable cliff drop check. Default: 0.5. Config key: score_stability_factor" />
            </label>
            <input type="number" value={scoreStabilityFactor} min={0} max={1} step={0.01} onChange={d(setScoreStabilityFactor, 0.5)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Promotion Threshold
              <Tooltip text="Minimum score for a symbol to enter the watchlist as a candidate. Symbols below this are ignored for promotion. Default: 0.0001. Config key: promotion_threshold" />
            </label>
            <input type="number" value={promotionThreshold} min={0} step={0.0001}
              onChange={d(setPromotionThreshold, 0.0001)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Demotion Threshold
              <Tooltip text="Score below which the demotion timer starts. A symbol must stay below this for the full demotion period to be removed. Set to 0 to only demote at exactly zero. Default: 0.0. Config key: demotion_threshold" />
            </label>
            <input type="number" value={demotionThreshold} min={0} step={0.0001}
              onChange={d(setDemotionThreshold, 0.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Demotion Period (s)
              <Tooltip text="How long a symbol must stay below demotion threshold before being deactivated. Tiered: weaker scores are demoted faster. Default: 600s (10 min). Config key: demotion_period" />
            </label>
            <input type="number" value={demotionPeriod} min={0} onChange={d(setDemotionPeriod, 600)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Min Net Profit %
              <Tooltip text="Minimum net spread (after fees) required to execute a trade. Higher values skip marginal opportunities. Set lower for high-frequency, low-spread strategies. Default: 0.02%. Config key: min_net_profit_pct" />
            </label>
            <input type="number" value={minNetProfitPct} min={0} step={0.01}
              onChange={d(setMinNetProfitPct, 0.02)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Rebalance Cooldown (s)
              <Tooltip text="Minimum seconds between rebalances for the same exchange/direction pair. Prevents rapid-fire transfers. Default: 30s. Config key: rebalance_cooldown" />
            </label>
            <input type="number" value={rebalanceCooldown} min={0} onChange={d(setRebalanceCooldown, 30)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Miss Streak Before Rebalance
              <Tooltip text="Consecutive missed trades (due to insufficient balance) before triggering a rebalance. Dynamic in adaptive mode: adjusts 10-30 based on trade frequency. Default: 15. Config key: min_misses_before_rebalance" />
            </label>
            <input type="number" value={minMissesBeforeRebalance} min={1} max={100} step={1}
              onChange={d(setMinMissesBeforeRebalance, 15)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Rebalance ROI Horizon (s)
              <Tooltip text="Maximum time to recoup the cost of a rebalance transfer. If estimated recovery time exceeds this, the rebalance is blocked. Default: 1800s (30 min). Config key: rebalance_roi_horizon" />
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
              <Tooltip text="Minimum score to allow trading and rebalancing for a symbol. Below this, the symbol gets trade_multiplier = 0 (no trading). Default: 0.01. Config key: trading_score_threshold" />
            </label>
            <input type="number" value={tradingScoreThreshold} min={0.001} max={0.5} step={0.001}
              onChange={d(setTradingScoreThreshold, 0.01)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Fee Threshold Multiplier
              <Tooltip text="Scales activation threshold based on exchange pair fees. Higher values make expensive pairs (non-Bitfinex) harder to activate. Formula: threshold = base + (pair_fee - cheapest_fee) × multiplier. 0 = disabled (all pairs use base threshold). Default: 0.5. Config key: fee_threshold_multiplier" />
            </label>
            <input type="number" value={feeThresholdMultiplier} min={0} max={5.0} step={0.1}
              onChange={d(setFeeThresholdMultiplier, 0.5)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Strong Threshold
              <Tooltip text="Score for the Strong tier. Strong symbols get 2-3x trade multiplier and up to 2 exchanges per direction. Default: 0.1. Config key: strong_score_threshold" />
            </label>
            <input type="number" value={strongScoreThreshold} min={0.01} max={1.0} step={0.01}
              onChange={d(setStrongScoreThreshold, 0.1)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Very Strong Threshold
              <Tooltip text="Score for the Very Strong tier. Very Strong symbols get 3-4x trade multiplier and up to 3 exchanges per direction. Default: 0.3. Config key: very_strong_score_threshold" />
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
              <Tooltip text="Number of trades before the net P&L gate activates. During warmup, rebalancing is always allowed. Prevents premature blocking from a few early bad trades. Default: 10. Config key: net_pnl_gate_warmup_trades" />
            </label>
            <input type="number" value={netPnlGateWarmupTrades} min={1} max={200} step={1}
              onChange={d(setNetPnlGateWarmupTrades, 10)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Grace Period (s)
              <Tooltip text="Time after bot start before the net P&L gate activates. During grace period, rebalancing is always allowed regardless of profitability. Default: 1800s (30 min). Config key: net_pnl_gate_grace_seconds" />
            </label>
            <input type="number" value={netPnlGateGraceSeconds} min={60} max={7200} step={60}
              onChange={d(setNetPnlGateGraceSeconds, 1800)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              ROI Gate Divisor
              <Tooltip text="Controls rebalancing sensitivity. ROI threshold = fee_rate / divisor. Higher values (5-10) allow rebalancing at lower expected profit, good for small capital. Default: 3. Config key: rebalance_roi_divisor" />
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
              <Tooltip text="Hours of estimated profit a symbol must generate to justify the cost of switching its dominant exchange pair. Higher values prevent expensive re-allocations for marginal improvements. Default: 2.0. Config key: reallocation_cost_horizon" />
            </label>
            <input type="number" value={reallocationCostHorizon} min={0.5} max={24} step={0.5}
              onChange={d(setReallocationCostHorizon, 2.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Demotion Cooldown Multiplier
              <Tooltip text="Cooldown after demotion = demotion_period x this multiplier. Higher values prevent symbols from churning in and out. With default 5.0 and 600s period: 50 min cooldown. Default: 5.0. Config key: demotion_cooldown_multiplier" />
            </label>
            <input type="number" value={demotionCooldownMultiplier} min={1} max={20} step={0.5}
              onChange={d(setDemotionCooldownMultiplier, 5.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Hourly External Transfer Cap ($)
              <Tooltip text="Maximum USD spent on external withdrawal fees per rolling hour. Internal rebalances (crypto sell/buy on same exchange) are not limited. Set to 0 to disable. Default: $2.00. Config key: hourly_external_transfer_cap" />
            </label>
            <input type="number" value={hourlyExternalTransferCap} min={0} max={100} step={0.5}
              onChange={d(setHourlyExternalTransferCap, 2.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
        </div>

        {/* Bitfinex Hub */}
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mt-6 mb-3">Bitfinex Capital Hub</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Bitfinex Reserve %
              <Tooltip text="Percentage of total capital to keep as USDT on Bitfinex. Bitfinex has $0 withdrawal fees, making it ideal as a capital hub. Capital is consolidated here during idle time and distributed for free. Set to 0 to disable. Default: 15%. Config key: bitfinex_reserve_pct" />
            </label>
            <input type="number" value={bitfinexReservePct} min={0} max={0.5} step={0.01}
              onChange={d(setBitfinexReservePct, 0.15)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Reserve Hard Floor %
              <Tooltip text="Minimum Bitfinex reserve that emergency draws cannot drain below. For $3000 capital with 5% floor = $150 minimum remaining. Prevents complete depletion during capital death spirals. Default: 5%. Config key: bitfinex_reserve_hard_floor" />
            </label>
            <input type="number" value={bitfinexReserveHardFloor} min={0} max={0.20} step={0.01}
              onChange={d(setBitfinexReserveHardFloor, 0.05)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
        </div>
      </div>

      {/* Simulation Realism */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Simulation Realism</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Spread Persistence Ticks
              <Tooltip text="Number of consecutive ticks a spread must persist before executing. Simulates execution latency — real orders take ~1s to reach exchanges. 0 = instant (legacy), 1 = spread must exist on 2 consecutive ticks (~1s), 2 = 3 ticks (~2s). Range: 0-5. Default: 1. Config key: spread_persistence_ticks" />
            </label>
            <input type="number" value={spreadPersistenceTicks} min={0} max={5} step={1}
              onChange={d(setSpreadPersistenceTicks, 1)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Event-Driven Seller Penalty %
              <Tooltip text="Scoring penalty applied when event-driven exchanges (e.g. Bitfinex) are sellers. Their bids update every 10-20s (vs ~100ms for streaming exchanges), so the bid may be stale by the time your order arrives. This deprioritizes event-driven sellers unless their bid is meaningfully better. 0 = disabled. Default: 0.05%. Config key: event_driven_seller_penalty_pct" />
            </label>
            <input type="number" value={evdSellerPenalty} min={0} max={1.0} step={0.01}
              onChange={d(setEvdSellerPenalty, 0.05)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              One-Leg Failure Rate
              <Tooltip text="Probability of simulated one-legged failure per trade. When triggered, one leg of the arbitrage fails and the unwind cost (taker fee + slippage) is deducted from profit. Simulates real-world partial execution failures. 0 = disabled. Default: 0.02 (2%). Config key: one_leg_failure_rate" />
            </label>
            <input type="number" value={oneLegFailureRate} min={0} max={0.20} step={0.01}
              onChange={d(setOneLegFailureRate, 0.02)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Unwind Slippage Multiplier
              <Tooltip text="Multiplier on estimated slippage for emergency unwind trades after a one-legged failure. Higher values simulate the urgency premium of unwinding a naked position quickly. Range: 1.0-5.0. Default: 1.5. Config key: one_leg_unwind_slippage_mult" />
            </label>
            <input type="number" value={oneLegUnwindSlippageMult} min={1.0} max={5.0} step={0.1}
              onChange={d(setOneLegUnwindSlippageMult, 1.5)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Max Position Multiplier
              <Tooltip text="Maximum accumulated crypto value per symbol per buyer exchange, as a multiple of trade_amount. Prevents flash-crash exposure from large accumulated positions. 0 = unlimited. For $30 trades with 5x cap: max $150 of any symbol on any buyer exchange. Range: 0-50. Default: 5.0. Config key: max_position_multiplier" />
            </label>
            <input type="number" value={maxPositionMultiplier} min={0} max={50} step={0.5}
              onChange={d(setMaxPositionMultiplier, 5.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
        </div>
      </div>

      {/* Diversification Floor (S21 follow-up — relax activation when understaffed) */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Diversification Floor</h2>
        <p className="text-xs text-slate-500 mb-3">
          When the bot is understaffed (active symbols below the configured minimum), multiply the activation threshold by this multiplier so a 2nd or 3rd marginal candidate can clear the gate. Pair with the momentum filter to avoid activating bleeders. Session #21 produced 187 unsuccessful auto-expand attempts — this addresses that.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <label className="flex items-center cursor-pointer">
              <input type="checkbox" checked={diversificationFloorEnabled}
                onChange={e => setDiversificationFloorEnabled(e.target.checked)}
                className="w-4 h-4 mr-2 rounded bg-slate-700 border-slate-600" />
              <span className="text-sm text-slate-300">Enable Diversification Floor</span>
            </label>
            <Tooltip text="When active < num_active_symbols, the activation threshold is multiplied by the floor multiplier (default 0.7×). Default: enabled. Config key: diversification_floor_enabled" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Floor Multiplier
              <Tooltip text="Multiplier applied to the activation threshold when active count is below minimum. Default: 0.7 (= 30% easier to clear). Lower = more aggressive activation. Range: 0.1-1.0. Config key: diversification_floor_multiplier" />
            </label>
            <input type="number" value={diversificationFloorMultiplier} min={0.1} max={1.0} step={0.05}
              onChange={d(setDiversificationFloorMultiplier, 0.7)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
        </div>
      </div>

      {/* Funding-Aware Scoring (Phase A — read-only foundation for spot-futures hedging) */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Funding-Aware Scoring</h2>
        <p className="text-xs text-slate-500 mb-3">
          Phase A. Live Binance Futures funding rates boost scores for symbols with positive funding (short hedge would earn) and penalize symbols with negative funding (short hedge would pay). Read-only — no positions opened.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="flex items-center gap-2 sm:col-span-2 lg:col-span-3">
            <label className="flex items-center cursor-pointer">
              <input type="checkbox" checked={fundingAwareEnabled}
                onChange={e => setFundingAwareEnabled(e.target.checked)}
                className="w-4 h-4 mr-2 rounded bg-slate-700 border-slate-600" />
              <span className="text-sm text-slate-300">Enable Funding-Aware Scoring</span>
            </label>
            <Tooltip text="When enabled, each symbol's score is multiplied by a funding-aware factor: clamp(1.0 + annualized_short_pct/100, min_factor, max_factor). Positive funding → boost (short hedge earns), negative → penalty. When funding is below the skip threshold, the multiplier is floored at min_factor (effectively disqualifies the symbol). Default: enabled. Config key: funding_aware_scoring_enabled" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Skip Threshold 4h Symbols (% per period)
              <Tooltip text="When the live funding rate for a 4h-funding symbol is worse than this threshold, the score multiplier is floored at min_factor — effectively disqualifying the symbol from activation/expansion until funding recovers. Default: -0.05% (= -0.30%/day, ~-110%/yr cost as short). Config key: funding_skip_threshold_4h_pct" />
            </label>
            <input type="number" value={fundingSkip4h} min={-1.0} max={1.0} step={0.01}
              onChange={d(setFundingSkip4h, -0.05)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Skip Threshold 8h Symbols (% per period)
              <Tooltip text="When the live funding rate for an 8h-funding symbol is worse than this threshold, the score multiplier is floored at min_factor. Default: -0.05% (= -0.15%/day, ~-55%/yr cost as short). Config key: funding_skip_threshold_8h_pct" />
            </label>
            <input type="number" value={fundingSkip8h} min={-1.0} max={1.0} step={0.01}
              onChange={d(setFundingSkip8h, -0.05)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Score Min Factor
              <Tooltip text="Floor for the funding score multiplier. When funding is severely negative or below the skip threshold, the multiplier is clamped to this value. Lower values = more aggressive penalty for bad-funding symbols. Range: 0.05-1.0. Default: 0.3 (= 70% score cut). Config key: funding_score_min_factor" />
            </label>
            <input type="number" value={fundingScoreMin} min={0.05} max={1.0} step={0.05}
              onChange={d(setFundingScoreMin, 0.3)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Score Max Factor
              <Tooltip text="Ceiling for the funding score multiplier. When funding is strongly positive (short would earn), the multiplier is capped to this value. Higher = more aggressive boost for good-funding symbols. Range: 1.0-5.0. Default: 1.5 (= 50% score boost). Config key: funding_score_max_factor" />
            </label>
            <input type="number" value={fundingScoreMax} min={1.0} max={5.0} step={0.05}
              onChange={d(setFundingScoreMax, 1.5)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Poll Interval (seconds)
              <Tooltip text="How often the bot polls Binance Futures /premiumIndex for live funding rates. One API call covers all 60 symbols (rate-limit weight 10, no key required). Default: 60s. Range: 30-600. Config key: funding_poll_interval_seconds" />
            </label>
            <input type="number" value={fundingPollInterval} min={30} max={600} step={10}
              onChange={d(setFundingPollInterval, 60.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
        </div>
      </div>

      {/* Spot-Futures Hedging (Phase C: shadow mode; Phase D: testnet; Phase G: live) */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Spot-Futures Hedging</h2>
        <p className="text-xs text-slate-500 mb-3">
          Phase C — shadow mode. Bot computes target hedge size from spot inventory and logs decisions, but does not place real futures orders. Phase D wires the Binance Futures executor.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="flex items-center gap-2 sm:col-span-2 lg:col-span-3">
            <label className="flex items-center cursor-pointer">
              <input type="checkbox" checked={hedgingEnabled}
                onChange={e => setHedgingEnabled(e.target.checked)}
                className="w-4 h-4 mr-2 rounded bg-slate-700 border-slate-600" />
              <span className="text-sm text-slate-300">Enable Hedging</span>
            </label>
            <Tooltip text="When enabled, the hedge manager evaluates target hedge sizes and (in testnet/live modes) places futures orders. Phase C: shadow only — no real orders regardless of execution mode. Default: enabled. Config key: hedging_enabled" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Execution Mode
              <Tooltip text="simulation = shadow only (Phase C, current); testnet = Binance Futures testnet (Phase D); live = mainnet (Phase G, post-30-day validation). Changing requires restart in v1. Default: simulation. Config key: hedge_execution_mode" />
            </label>
            <select value={hedgeExecutionMode}
              onChange={e => setHedgeExecutionMode(e.target.value as 'simulation' | 'testnet' | 'live')}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
              <option value="simulation">Simulation (shadow)</option>
              <option value="testnet">Testnet</option>
              <option value="live">Live (mainnet)</option>
            </select>
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Dust Threshold (USD)
              <Tooltip text="Minimum spot inventory notional to bother opening a hedge. Below this threshold, the funding/fees would exceed the price-protection benefit. Default: $20. Range: $1–$10,000. Config key: hedge_dust_threshold_usd" />
            </label>
            <input type="number" value={hedgeDustThreshold} min={1} max={10000} step={1}
              onChange={d(setHedgeDustThreshold, 20.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Evaluation Interval (s)
              <Tooltip text="How often the hedge manager evaluates target hedge sizes. Lower = more responsive but more API calls. Default: 300s (5 min). Range: 30–7200s. Config key: hedge_evaluation_interval_seconds" />
            </label>
            <input type="number" value={hedgeEvalInterval} min={30} max={7200} step={30}
              onChange={d(setHedgeEvalInterval, 300.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Margin Buffer
              <Tooltip text="Required free margin as a fraction of position size, even at 1× leverage. Prevents liquidation from brief mark-price spikes. Default: 0.20 (= 20% buffer; $500 margin can hedge max $400 position). Config key: hedge_margin_buffer_pct" />
            </label>
            <input type="number" value={hedgeMarginBuffer} min={0} max={1.0} step={0.05}
              onChange={d(setHedgeMarginBuffer, 0.20)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="flex items-center text-xs text-slate-500 mb-1">
              Adjust Threshold
              <Tooltip text="Drift between current hedge size and target before triggering an adjustment. Lower = more frequent re-balancing (more fees). Default: 0.10 (= 10% drift). Range: 0.01–1.0. Config key: hedge_adjust_threshold_pct" />
            </label>
            <input type="number" value={hedgeAdjustThreshold} min={0.01} max={1.0} step={0.01}
              onChange={d(setHedgeAdjustThreshold, 0.10)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
          </div>
        </div>
      </div>

      {/* Anomaly Protection */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Anomaly Protection</h2>

        {/* Status banner */}
        {anomalyProtection?.paused && (
          <div className="mb-4 p-3 bg-red-950/50 border border-red-900/50 rounded-lg">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-red-400 font-medium text-sm">Trading Paused</span>
                <span className="text-slate-400 text-xs ml-2">({anomalyProtection.pause_layer})</span>
                <p className="text-slate-400 text-xs mt-1">{anomalyProtection.pause_reason}</p>
              </div>
              <button onClick={() => onSendMessage({ type: 'anomaly_resume' })}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition-colors">
                Resume Trading
              </button>
            </div>
          </div>
        )}
        {anomalyProtection?.warning_active && !anomalyProtection?.paused && (
          <div className="mb-4 p-3 bg-amber-950/30 border border-amber-900/50 rounded-lg">
            <span className="text-amber-400 font-medium text-sm">Warning Active</span>
            <span className="text-slate-400 text-xs ml-2">(trade size x0.5)</span>
            <p className="text-slate-400 text-xs mt-1">{anomalyProtection.warning_reason}</p>
          </div>
        )}

        {/* Live stats */}
        {anomalyProtection && (
          <div className="mb-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="bg-slate-700/50 rounded-lg p-2">
              <div className="text-slate-500">Rolling P&L</div>
              <div className={`font-mono font-medium ${anomalyProtection.rolling_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                ${anomalyProtection.rolling_pnl.toFixed(2)}
              </div>
            </div>
            <div className="bg-slate-700/50 rounded-lg p-2">
              <div className="text-slate-500">Drawdown</div>
              <div className={`font-mono font-medium ${anomalyProtection.current_drawdown_pct > 2 ? 'text-amber-400' : 'text-slate-300'}`}>
                {anomalyProtection.current_drawdown_pct.toFixed(2)}%
              </div>
            </div>
            <div className="bg-slate-700/50 rounded-lg p-2">
              <div className="text-slate-500">Pauses / Warnings</div>
              <div className="text-slate-300 font-mono">{anomalyProtection.total_pauses}p / {anomalyProtection.total_warnings}w</div>
            </div>
            <div className="bg-slate-700/50 rounded-lg p-2">
              <div className="text-slate-500">Symbol Blocks</div>
              <div className="text-slate-300 font-mono">{anomalyProtection.total_symbol_blocks}</div>
            </div>
          </div>
        )}

        {/* Blocked symbols */}
        {anomalyProtection && Object.keys(anomalyProtection.symbol_blocks).length > 0 && (
          <div className="mb-4 p-3 bg-slate-700/30 rounded-lg">
            <div className="text-xs text-slate-500 mb-1">Blocked Symbols</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(anomalyProtection.symbol_blocks).map(([sym, until]) => (
                <span key={sym} className="px-2 py-0.5 bg-red-950/50 border border-red-900/50 rounded text-xs text-red-400">
                  {sym} <span className="text-slate-500">({Math.max(0, Math.round((until - Date.now() / 1000)))}s)</span>
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={anomalyEnabled}
              onChange={e => { setDirty(true); setAnomalyEnabled(e.target.checked); }}
              className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500" />
            <span className="text-sm text-slate-300">Enable Anomaly Protection</span>
            <Tooltip text="Master toggle for the 3-layer anomaly protection system: circuit breaker (rolling P&L), drawdown protection (peak-to-trough), and per-symbol loss streak detection. When disabled, no anomaly checks run. Default: enabled. Config key: anomaly_protection_enabled" />
          </label>

          {anomalyEnabled && (
            <>
            {/* Layer 1: Circuit Breaker */}
            <div className="border-l-2 border-blue-600/50 pl-4 space-y-3">
              <h3 className="text-xs font-semibold text-blue-400 uppercase tracking-wider">Layer 1: Circuit Breaker (Rolling P&L)</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="flex items-center text-xs text-slate-500 mb-1">
                    Window (seconds)
                    <Tooltip text="Rolling time window for P&L tracking. Only trades within this window count toward the threshold. Shorter windows react faster but may false-trigger. Range: 60-7200. Default: 900 (15 min). Config key: circuit_breaker_window" />
                  </label>
                  <input type="number" value={cbWindow} min={60} max={7200} step={60}
                    onChange={d(setCbWindow, 900)}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="flex items-center text-xs text-slate-500 mb-1">
                    Threshold ($)
                    <Tooltip text="If rolling P&L drops below this value, all trading is paused. For $1000 capital, -$5 means -0.5% loss in the window. Must be negative. Range: -1000 to 0. Default: -$5.00. Config key: circuit_breaker_threshold" />
                  </label>
                  <input type="number" value={cbThreshold} min={-1000} max={0} step={0.5}
                    onChange={d(setCbThreshold, -5.0)}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="flex items-center text-xs text-slate-500 mb-1">
                    Resume %
                    <Tooltip text="Auto-resume when rolling P&L recovers above threshold x resume%. At 0.5 with -$5 threshold, resumes when P&L > -$2.50. Range: 0.1-1.0. Default: 0.5. Config key: circuit_breaker_resume_pct" />
                  </label>
                  <input type="number" value={cbResumePct} min={0.1} max={1.0} step={0.1}
                    onChange={d(setCbResumePct, 0.5)}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="flex items-center text-xs text-slate-500 mb-1">
                    Cooldown (seconds)
                    <Tooltip text="Minimum wait time before auto-resuming after circuit breaker triggers. Even if P&L recovers quickly, trading won't resume until cooldown expires. Range: 30-3600. Default: 300 (5 min). Config key: circuit_breaker_cooldown" />
                  </label>
                  <input type="number" value={cbCooldown} min={30} max={3600} step={30}
                    onChange={d(setCbCooldown, 300)}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
              </div>
            </div>

            {/* Layer 2: Drawdown */}
            <div className="border-l-2 border-amber-600/50 pl-4 space-y-3">
              <h3 className="text-xs font-semibold text-amber-400 uppercase tracking-wider">Layer 2: Drawdown Protection (Peak-to-Trough)</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <div>
                  <label className="flex items-center text-xs text-slate-500 mb-1">
                    Threshold (%)
                    <Tooltip text="If portfolio drops this % from session peak, all trading is paused. For $1000 capital at 5%: pause at -$50. Accounts for crypto positions' market value. Range: 0.5-20.0. Default: 5.0%. Config key: drawdown_threshold_pct" />
                  </label>
                  <input type="number" value={ddThreshold} min={0.5} max={20.0} step={0.5}
                    onChange={d(setDdThreshold, 5.0)}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="flex items-center text-xs text-slate-500 mb-1">
                    Resume (%)
                    <Tooltip text="Auto-resume when drawdown recovers below this %. Must be lower than threshold. Range: 0.1-10.0. Default: 3.0%. Config key: drawdown_resume_pct" />
                  </label>
                  <input type="number" value={ddResumePct} min={0.1} max={10.0} step={0.5}
                    onChange={d(setDdResumePct, 3.0)}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="flex items-center text-xs text-slate-500 mb-1">
                    Emergency Multiplier
                    <Tooltip text="At threshold x multiplier drawdown, triggers EMERGENCY sell-all. With 5% threshold and 2.0x mult: emergency at 10%. Sells all crypto positions immediately. Requires manual resume. Range: 1.5-5.0. Default: 2.0. Config key: drawdown_emergency_mult" />
                  </label>
                  <input type="number" value={ddEmergencyMult} min={1.5} max={5.0} step={0.5}
                    onChange={d(setDdEmergencyMult, 2.0)}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
              </div>
            </div>

            {/* Layer 3: Per-Symbol Loss Streak */}
            <div className="border-l-2 border-purple-600/50 pl-4 space-y-3">
              <h3 className="text-xs font-semibold text-purple-400 uppercase tracking-wider">Layer 3: Per-Symbol Loss Streak</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="flex items-center text-xs text-slate-500 mb-1">
                    Streak Threshold
                    <Tooltip text="Number of consecutive losing trades on the SAME symbol before blocking it. Only that symbol is blocked — other symbols keep trading. Resets on a profitable trade. Range: 2-20. Default: 4. Config key: symbol_loss_streak_threshold" />
                  </label>
                  <input type="number" value={lsThreshold} min={2} max={20} step={1}
                    onChange={d(setLsThreshold, 4)}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="flex items-center text-xs text-slate-500 mb-1">
                    Block Cooldown (seconds)
                    <Tooltip text="How long a symbol stays blocked after hitting the loss streak threshold. After cooldown, the streak resets and the symbol can trade again. Range: 60-3600. Default: 300 (5 min). Config key: symbol_loss_streak_cooldown" />
                  </label>
                  <input type="number" value={lsCooldown} min={60} max={3600} step={30}
                    onChange={d(setLsCooldown, 300)}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
              </div>
            </div>

            {/* Warning */}
            <div className="border-l-2 border-slate-600/50 pl-4 space-y-3">
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Warning (Pre-Pause Trade Size Reduction)</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="flex items-center text-xs text-slate-500 mb-1">
                    Warning P&L %
                    <Tooltip text="When rolling P&L drops below threshold x warning%, trade size is reduced to 0.5x as a precaution. At 0.5 with -$5 threshold: warning at -$2.50. Early defensive measure before full pause. Range: 0.1-1.0. Default: 0.5. Config key: warning_pnl_pct" />
                  </label>
                  <input type="number" value={warningPnlPct} min={0.1} max={1.0} step={0.1}
                    onChange={d(setWarningPnlPct, 0.5)}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
                </div>
              </div>
            </div>
            </>
          )}
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
            <Tooltip text="Restrict dashboard access to specific IP addresses. When enabled, connections from non-whitelisted IPs are immediately denied. Leave the list empty to allow all. Config key: ip_whitelist_enabled" />
          </label>
          {ipWhitelistEnabled && (
            <div>
              <label className="flex items-center text-xs text-slate-500 mb-1">
                Allowed IPs (comma-separated)
                <Tooltip text="Enter IPv4 or IPv6 addresses separated by commas. Changes take effect immediately after saving. Example: 212.253.218.204, 10.0.0.1. Config key: ip_whitelist" />
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
        <div className="space-y-4">
          {/* Manual Stop/Start */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <p className="text-sm text-slate-300">Manual Trading Control</p>
              <p className="text-xs mt-0.5">
                {manualStopped
                  ? <span className="text-red-400">Trading is STOPPED</span>
                  : <span className="text-emerald-400">Trading is ACTIVE</span>
                }
              </p>
            </div>
            {manualStopped ? (
              <button onClick={() => onSendMessage({ type: 'manual_start' })}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors">
                Start Trading
              </button>
            ) : (
              <button onClick={() => setShowStopConfirm(true)}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors">
                Stop Trading
              </button>
            )}
          </div>
          <div className="border-t border-red-900/30" />
          {/* Hard Stop */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <p className="text-sm text-slate-300">Hard Stop — Convert All Crypto to USDT</p>
              <p className="text-xs text-slate-500 mt-0.5">Sell all crypto positions across all exchanges. Stops trading automatically.</p>
            </div>
            <button onClick={() => { setShowHardStop(true); setHardStopConfirmText(''); setHardStopResult(null); }}
              className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors whitespace-nowrap">
              Hard Stop
            </button>
          </div>
          <div className="border-t border-red-900/30" />
          {/* Distribute from Bitfinex */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <p className="text-sm text-slate-300">Distribute USDT from Bitfinex</p>
              <p className="text-xs text-slate-500 mt-0.5">
                {distributeEnabled
                  ? 'Distribute Bitfinex USDT to exchanges based on symbol profitability.'
                  : 'Enabled after Hard Stop with Transfer to Bitfinex, or switching to live mode.'}
              </p>
            </div>
            <button
              onClick={() => { setShowDistribute(true); setDistributeConfirmText(''); setDistributeResult(null); }}
              disabled={!distributeEnabled}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                distributeEnabled
                  ? 'bg-red-600 hover:bg-red-500 text-white'
                  : 'bg-slate-700 text-slate-500 cursor-not-allowed'
              }`}>
              Distribute USDT
            </button>
          </div>
          <div className="border-t border-red-900/30" />
          {/* Restart Bot */}
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

      {/* Stop Trading Confirmation Modal */}
      {showStopConfirm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl p-6 max-w-md w-full mx-4 border border-red-900/50">
            <h3 className="text-lg font-semibold text-white mb-2">Stop Trading?</h3>
            <p className="text-slate-400 text-sm mb-4">
              Are you sure you want to stop all trading? The bot will remain running but will not execute any trades until you start it again.
            </p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setShowStopConfirm(false)}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm">
                Cancel
              </button>
              <button onClick={() => {
                onSendMessage({ type: 'manual_stop' });
                setShowStopConfirm(false);
              }}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm font-medium">
                Stop Trading
              </button>
            </div>
          </div>
        </div>
      )}

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

      {/* Hard Stop Modal */}
      {showHardStop && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl max-w-lg w-full mx-4 border border-red-900/50 overflow-hidden">
            <div className="bg-red-900/60 px-6 py-3">
              <h3 className="text-lg font-semibold text-red-200">Hard Stop — Convert All Crypto to USDT</h3>
            </div>
            <div className="p-6">
              {hardStopResult ? (
                <div>
                  <p className="text-emerald-400 font-medium mb-3">Hard Stop Complete</p>
                  <div className="text-sm text-slate-300 space-y-1">
                    <div>Positions sold: <span className="text-white font-mono">{hardStopResult.positions_sold}</span></div>
                    <div>Total gross: <span className="text-white font-mono">${hardStopResult.total_gross.toFixed(2)}</span></div>
                    <div>Total fees: <span className="text-amber-400 font-mono">${hardStopResult.total_fees.toFixed(4)}</span></div>
                    <div>Total net: <span className="text-emerald-400 font-mono">${hardStopResult.total_net.toFixed(2)}</span></div>
                  </div>
                  {hardStopResult.sells?.length > 0 && (
                    <div className="mt-3 max-h-48 overflow-y-auto border border-slate-700/50 rounded-lg">
                      <table className="w-full text-xs">
                        <thead className="bg-slate-900/80 sticky top-0">
                          <tr className="text-slate-500">
                            <th className="text-left px-2 py-1">Exchange</th>
                            <th className="text-left px-2 py-1">Symbol</th>
                            <th className="text-right px-2 py-1">Gross</th>
                            <th className="text-right px-2 py-1">Fee</th>
                            <th className="text-left px-2 py-1">Path</th>
                          </tr>
                        </thead>
                        <tbody>
                          {hardStopResult.sells.map((s, i) => (
                            <tr key={i} className="border-t border-slate-700/30">
                              <td className="px-2 py-1 text-slate-300">{s.exchange}</td>
                              <td className="px-2 py-1 text-white">{s.symbol}</td>
                              <td className="px-2 py-1 text-right font-mono text-white">${s.gross.toFixed(2)}</td>
                              <td className="px-2 py-1 text-right font-mono text-amber-400">${s.fee.toFixed(4)}</td>
                              <td className="px-2 py-1 text-slate-400">{s.path}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <div className="flex gap-3 justify-end mt-4">
                    <button onClick={() => setShowHardStop(false)}
                      className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm">
                      Close
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="mb-4">
                    <label className="flex items-center gap-2 cursor-pointer mb-3">
                      <input type="checkbox" checked={hardStopBitfinex} onChange={e => setHardStopBitfinex(e.target.checked)}
                        className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-500" />
                      <span className="text-sm text-slate-300">Transfer to Bitfinex (0% taker fee)</span>
                    </label>
                    <p className="text-xs text-slate-500">
                      {hardStopBitfinex
                        ? 'Crypto will be transferred to Bitfinex and sold at 0% taker. Symbols not available on Bitfinex are sold locally.'
                        : 'All crypto will be sold locally on each exchange (pays taker fee per exchange).'}
                    </p>
                  </div>
                  {/* Fee estimate */}
                  {balances && feeConfigs && (
                    <div className="bg-slate-900/50 rounded-lg p-3 mb-4 text-xs">
                      <div className="text-slate-500 font-medium mb-2">Fee Estimate</div>
                      {(() => {
                        let totalCrypto = 0;
                        let estFees = 0;
                        let localFees = 0;
                        const perExchange: { exchange: string; crypto: number; fee: number; localFee: number; positions: number }[] = [];
                        Object.entries(balances).forEach(([ex, bal]) => {
                          let exCrypto = 0;
                          let exFee = 0;
                          let exLocalFee = 0;
                          let positions = 0;
                          Object.values(bal.crypto || {}).forEach(c => {
                            if (c.value > 0) {
                              exCrypto += c.value;
                              positions++;
                              const feeRate = feeConfigs[ex]?.base_taker_rate ?? 0.001;
                              const discount = feeConfigs[ex]?.token_discount_enabled ? (feeConfigs[ex]?.token_discount_pct ?? 0) : 0;
                              const localFeeAmt = c.value * feeRate * (1 - discount);
                              exLocalFee += localFeeAmt;
                              if (!hardStopBitfinex || ex === 'Bitfinex') {
                                exFee += localFeeAmt;
                              }
                              // With Bitfinex transfer: 0% taker (no fee for non-Bitfinex exchanges)
                            }
                          });
                          if (positions > 0) {
                            totalCrypto += exCrypto;
                            estFees += exFee;
                            localFees += exLocalFee;
                            perExchange.push({ exchange: ex, crypto: exCrypto, fee: exFee, localFee: exLocalFee, positions });
                          }
                        });
                        return (
                          <div className="space-y-2 text-slate-300">
                            <div>Total crypto value: <span className="text-white font-mono">${totalCrypto.toFixed(2)}</span> ({perExchange.reduce((s, e) => s + e.positions, 0)} positions)</div>
                            {perExchange.length > 0 && (
                              <div className="border-t border-slate-700/50 pt-1.5 space-y-0.5">
                                {perExchange.map(e => (
                                  <div key={e.exchange} className="flex justify-between">
                                    <span className="text-slate-400">{e.exchange} <span className="text-slate-600">({e.positions} pos, ${e.crypto.toFixed(2)})</span></span>
                                    <span className="font-mono">
                                      {hardStopBitfinex && e.exchange !== 'Bitfinex'
                                        ? <span className="text-emerald-400">$0.0000</span>
                                        : <span className="text-amber-400">${e.fee.toFixed(4)}</span>}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                            <div className="border-t border-slate-700/50 pt-1.5">
                              <div className="flex justify-between font-medium">
                                <span>Total estimated fees:</span>
                                <span className="text-amber-400 font-mono">${estFees.toFixed(4)}</span>
                              </div>
                              {hardStopBitfinex && (
                                <div className="text-emerald-400 mt-0.5">Savings vs local sell: ~${(localFees - estFees).toFixed(4)}</div>
                              )}
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  )}
                  <div className="mb-4">
                    <label className="block text-xs text-slate-500 mb-1">Type <span className="text-red-400 font-mono">hard stop</span> to confirm:</label>
                    <input type="text" value={hardStopConfirmText} onChange={e => setHardStopConfirmText(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600"
                      placeholder="hard stop" autoFocus />
                  </div>
                  <div className="flex gap-3 justify-end">
                    <button onClick={() => setShowHardStop(false)}
                      className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm">
                      Cancel
                    </button>
                    <button
                      disabled={hardStopConfirmText !== 'hard stop'}
                      onClick={() => {
                        onSendWithCallback(
                          { type: 'hard_stop', transfer_to_bitfinex: hardStopBitfinex },
                          (data) => setHardStopResult(data),
                        );
                        setHardStopConfirmText('');
                      }}
                      className={`px-4 py-2 rounded-lg text-sm font-medium ${
                        hardStopConfirmText === 'hard stop'
                          ? 'bg-red-600 hover:bg-red-500 text-white'
                          : 'bg-slate-700 text-slate-500 cursor-not-allowed'
                      }`}>
                      Confirm Hard Stop
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Distribute USDT from Bitfinex Modal */}
      {showDistribute && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl max-w-lg w-full mx-4 border border-red-900/50 overflow-hidden">
            <div className="bg-red-900/60 px-6 py-3">
              <h3 className="text-lg font-semibold text-red-200">Distribute USDT from Bitfinex</h3>
            </div>
            <div className="p-6">
              {distributeResult ? (
                <div>
                  <p className="text-emerald-400 font-medium mb-3">Distribution Complete ({distributeResult.strategy})</p>
                  <div className="text-sm text-slate-300 space-y-1">
                    <div>Total distributed: <span className="text-white font-mono">${distributeResult.distributed.toFixed(2)}</span></div>
                    {distributeResult.transfers.map((t, i) => (
                      <div key={i} className="text-xs text-slate-400">Bitfinex → {t.exchange}: <span className="font-mono text-white">${t.amount.toFixed(2)}</span></div>
                    ))}
                  </div>
                  <div className="flex gap-3 justify-end mt-4">
                    <button onClick={() => setShowDistribute(false)}
                      className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm">
                      Close
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  {balances?.Bitfinex && (
                    <div className="bg-slate-900/50 rounded-lg p-3 mb-4 text-xs">
                      <div className="text-slate-500 font-medium mb-2">Bitfinex Balance</div>
                      <div className="space-y-1 text-slate-300">
                        <div>USDT: <span className="text-white font-mono">${balances.Bitfinex.usdt.toFixed(2)}</span></div>
                        <div>Reserve: <span className="text-amber-400 font-mono">~${(Number(currentSettings.total_capital ?? 1800) * Number(currentSettings.bitfinex_reserve_pct ?? 0.15)).toFixed(2)}</span></div>
                        <div>Available: <span className="text-emerald-400 font-mono">${Math.max(0, balances.Bitfinex.usdt - Number(currentSettings.total_capital ?? 1800) * Number(currentSettings.bitfinex_reserve_pct ?? 0.15)).toFixed(2)}</span></div>
                      </div>
                      <div className="mt-2 text-slate-500">Distribution: score-weighted to profitable exchanges (free transfer)</div>
                    </div>
                  )}
                  <div className="mb-4">
                    <label className="block text-xs text-slate-500 mb-1">Type <span className="text-red-400 font-mono">distribute usdt</span> to confirm:</label>
                    <input type="text" value={distributeConfirmText} onChange={e => setDistributeConfirmText(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600"
                      placeholder="distribute usdt" autoFocus />
                  </div>
                  <div className="flex gap-3 justify-end">
                    <button onClick={() => setShowDistribute(false)}
                      className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm">
                      Cancel
                    </button>
                    <button
                      disabled={distributeConfirmText !== 'distribute usdt'}
                      onClick={() => {
                        onSendWithCallback(
                          { type: 'distribute_from_bitfinex' },
                          (data) => {
                            if (data.type === 'distribute_error') {
                              setDistributeResult({ distributed: 0, transfers: [], strategy: data.error ?? 'Error' });
                            } else {
                              setDistributeResult(data);
                            }
                          },
                        );
                        setDistributeConfirmText('');
                      }}
                      className={`px-4 py-2 rounded-lg text-sm font-medium ${
                        distributeConfirmText === 'distribute usdt'
                          ? 'bg-red-600 hover:bg-red-500 text-white'
                          : 'bg-slate-700 text-slate-500 cursor-not-allowed'
                      }`}>
                      Distribute
                    </button>
                  </div>
                </>
              )}
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
