import { useState, useEffect } from 'react';
import { NavLink, useParams } from 'react-router-dom';
import type { Settings, ExchangeFeeConfig, ExchangeTransferConfig, ExchangeBalance, RegistryView, ConfigLite } from '../types';
import TransferFeeManagementTab from './TransferFeeManagementTab';
import ConfigGroupsTab from './ConfigGroupsTab';
import ConfirmModal from './ConfirmModal';
import Tooltip from './Tooltip';
import { useToast } from './ToastContext';

interface SettingsPageProps {
  currentSettings: Settings;
  onSave: (settings: Settings) => void;
  onApply: (settings: Settings) => void;
  onSendMessage: (msg: object) => void;
  onSendWithCallback: (msg: object, callback: (data: any) => void) => void;
  feeConfigs?: Record<string, ExchangeFeeConfig>;
  transferConfigs?: Record<string, ExchangeTransferConfig>;
  autoDisableState?: import('../types').AutoDisableState;
  manualStopped?: boolean;
  balances?: Record<string, ExchangeBalance>;
  distributeEnabled?: boolean;
  registry?: RegistryView;
  configsLite?: ConfigLite[];
  selectedConfigId?: string | null;
}

type SettingsSubTab = 'config-groups' | 'general' | 'transfers';

function ExecutionModeSection({
  registry,
  configsLite,
  onSendMessage,
}: {
  registry: RegistryView;
  configsLite?: ConfigLite[];
  onSendMessage: (msg: object) => void;
}) {
  const toast = useToast();
  const sharedExec = registry.shared.execution_mode;
  const sharedHedge = registry.shared.hedge_execution_mode;
  const superPrimary = configsLite?.find((l) => l.is_super_primary);

  const save = (execMode?: string, hedgeMode?: string) => {
    onSendMessage({
      type: 'save_shared_execution_mode',
      execution_mode: execMode ?? sharedExec,
      hedge_execution_mode: hedgeMode ?? sharedHedge,
    });
    toast.show('Execution mode updated', 'success');
  };

  return (
    <div className="bg-slate-800/50 rounded-lg p-4 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-1">
          Execution Mode (super-primary only)
        </h3>
        <p className="text-xs text-slate-500">
          These settings apply <span className="text-amber-400">only to the super-primary config</span>:{' '}
          <span className="text-amber-300 font-medium">
            {superPrimary ? `${superPrimary.group_name} / ${superPrimary.name}` : '(none)'}
          </span>. Every other config is force-locked to{' '}
          <span className="font-mono">simulation</span> regardless of these values.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="flex items-center text-xs text-slate-500 mb-1">
            <span>Spot execution mode</span>
            <span className="ml-1.5 text-slate-600 font-mono text-[10px]">(execution_mode)</span>
            <Tooltip text="Spot trade execution mode for the super-primary config. simulation = no real orders. demo = real demo/testnet orders alongside simulation. demo_only = only demo orders (skips simulation). live = real mainnet orders (post-validation only). Multi-config force-locks others to simulation. Config key: shared.execution_mode" />
          </label>
          <select
            value={sharedExec}
            onChange={(e) => save(e.target.value, undefined)}
            className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="simulation">simulation</option>
            <option value="demo">demo (sim + demo orders)</option>
            <option value="demo_only">demo_only (skip sim)</option>
            <option value="live">live (real mainnet)</option>
          </select>
          <p className="text-xs text-slate-500 mt-1 italic">
            Currently active for super-primary:{' '}
            <span className="text-slate-300 font-mono">{superPrimary?.execution_mode ?? sharedExec}</span>
          </p>
        </div>
        <div>
          <label className="flex items-center text-xs text-slate-500 mb-1">
            <span>Hedge execution mode</span>
            <span className="ml-1.5 text-slate-600 font-mono text-[10px]">(hedge_execution_mode)</span>
            <Tooltip text="Binance Futures hedge execution mode for the super-primary config. simulation = shadow tracking only. testnet = real Binance Futures testnet positions. live = real mainnet Futures (real margin/liquidation risk). Multi-config force-locks others to simulation. Config key: shared.hedge_execution_mode" />
          </label>
          <select
            value={sharedHedge}
            onChange={(e) => save(undefined, e.target.value)}
            className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="simulation">simulation (shadow)</option>
            <option value="testnet">testnet (real testnet positions)</option>
            <option value="live">live (real mainnet)</option>
          </select>
          <p className="text-xs text-slate-500 mt-1 italic">
            Currently active for super-primary:{' '}
            <span className="text-slate-300 font-mono">{superPrimary?.hedge_mode ?? sharedHedge}</span>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage({ currentSettings, onSave, onApply, onSendMessage, onSendWithCallback, feeConfigs, transferConfigs, autoDisableState, balances, distributeEnabled, registry, configsLite, selectedConfigId }: SettingsPageProps) {
  const { subTab } = useParams<{ subTab?: string }>();
  // v0.31: Config Groups is the default landing tab. /settings → config-groups.
  // Per-config General + Fee Mgmt are now edited inside the per-config modal.
  // /settings/general remains as a legacy editor for the default config.
  const activeSubTab: SettingsSubTab =
    subTab === 'general' ? 'general'
    : subTab === 'transfers' ? 'transfers'
    : 'config-groups';
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
  // v0.30+: capital architecture
  const [custodyHubExchange, setCustodyHubExchange] = useState(currentSettings.custody_hub_exchange ?? 'Bybit');
  const [custodyHubNetwork, setCustodyHubNetwork] = useState(currentSettings.custody_hub_network ?? 'Aptos');
  const [tradingFloatMultiplier, setTradingFloatMultiplier] = useState(currentSettings.trading_float_multiplier ?? 8.0);
  const [tradingFloatReplenishTrigger, setTradingFloatReplenishTrigger] = useState(currentSettings.trading_float_replenish_trigger ?? 3.0);
  const [tradingFloatOverflowMultiplier, setTradingFloatOverflowMultiplier] = useState(currentSettings.trading_float_overflow_multiplier ?? 1.5);
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
  const [fastTrackDiscoveryEnabled, setFastTrackDiscoveryEnabled] = useState(currentSettings.fast_track_discovery_enabled ?? true);
  const [fastTrackAggressiveness, setFastTrackAggressiveness] = useState(currentSettings.fast_track_aggressiveness ?? 1.0);
  const [autoDisableVolumeEnabled, setAutoDisableVolumeEnabled] = useState(currentSettings.auto_disable_volume_enabled ?? true);
  const [autoDisableVolumeThreshold, setAutoDisableVolumeThreshold] = useState(currentSettings.auto_disable_volume_threshold_usd ?? 10000);
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
  // v0.31.0-beta+: two-layer emergency gate
  const [realizedDdEmergencyPct, setRealizedDdEmergencyPct] = useState(
    currentSettings.realized_drawdown_emergency_pct ?? 15.0,
  );
  const [combinedDdEmergencyPct, setCombinedDdEmergencyPct] = useState(
    currentSettings.combined_drawdown_emergency_pct ?? 25.0,
  );
  const [combinedDdSustainedSec, setCombinedDdSustainedSec] = useState(
    currentSettings.combined_drawdown_sustained_seconds ?? 300,
  );
  const [emergencyAutoLiquidate, setEmergencyAutoLiquidate] = useState(
    currentSettings.emergency_auto_liquidate ?? false,
  );
  const [lsThreshold, setLsThreshold] = useState(currentSettings.symbol_loss_streak_threshold ?? 4);
  const [lsCooldown, setLsCooldown] = useState(currentSettings.symbol_loss_streak_cooldown ?? 300);
  const [warningPnlPct, setWarningPnlPct] = useState(currentSettings.warning_pnl_pct ?? 0.5);
  const [showStopConfirm, setShowStopConfirm] = useState(false);
  const [securityStatus, setSecurityStatus] = useState<string | null>(null);
  const [showRestartConfirm, setShowRestartConfirm] = useState(false);
  const [showRestartAllConfirm, setShowRestartAllConfirm] = useState(false);
  const toast = useToast();
  // v0.31: 24h volumes are fetched globally from this Global tab and propagated
  // to per-config Fee Management modals via prop drilling. Persists across the
  // Settings page lifetime so re-opening a config's modal still has volume data.
  // v0.31: volumes are server-cached and broadcast — `auto_disable_state.cached_volumes`
  // survives page refresh + bot restart. Local state is only used to show the
  // optimistic "fetched just now" feedback before the next broadcast tick.
  const cachedFromServer = autoDisableState?.cached_volumes ?? null;
  const [globalVolumesLocal, setGlobalVolumesLocal] = useState<Record<string, Record<string, number>> | null>(null);
  const globalVolumes = globalVolumesLocal ?? cachedFromServer;
  const [globalVolumesLoading, setGlobalVolumesLoading] = useState(false);
  const [globalVolumesError, setGlobalVolumesError] = useState<string | null>(null);

  const handleFetchGlobalVolumes = () => {
    if (!onSendWithCallback) return;
    setGlobalVolumesLoading(true);
    setGlobalVolumesError(null);
    onSendWithCallback({ type: 'fetch_volumes' }, (data: any) => {
      setGlobalVolumesLoading(false);
      if (data?.ok && data.volumes) {
        setGlobalVolumesLocal(data.volumes);
        const summary = data.auto_disable_summary;
        if (summary) {
          toast.show(
            `Volumes fetched: +${summary.total_added} disabled, -${summary.total_removed} re-enabled across ${summary.configs_updated} config(s)`,
            'success',
            4000,
          );
        } else {
          toast.show('24h volumes fetched', 'success');
        }
      } else {
        setGlobalVolumesError(data?.error || 'Unknown error');
        toast.show('Volume fetch failed', 'error');
      }
    });
  };

  const globalVolumeFetcher = (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex-1 min-w-[240px]">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-1">
            24h Volume Fetcher
          </h3>
          <p className="text-xs text-slate-500">
            Pull live 24h USD volumes from each exchange. Volumes are cached for the page lifetime
            and feed every config's <span className="text-cyan-400">Fee Management</span> tab inside
            its Edit modal — used by the per-symbol blocklist UI to bulk-disable thinly-traded pairs.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <button
            onClick={handleFetchGlobalVolumes}
            disabled={globalVolumesLoading || !onSendWithCallback}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            {globalVolumesLoading ? 'Fetching…' : globalVolumes ? 'Refresh 24h Volumes' : 'Fetch 24h Volumes'}
          </button>
          {globalVolumesError && (
            <span className="text-xs text-rose-400">{globalVolumesError}</span>
          )}
          {globalVolumes && !globalVolumesError && (
            <span className="text-xs text-emerald-400">
              {Object.keys(globalVolumes).length} exchange(s) loaded
            </span>
          )}
        </div>
      </div>
    </div>
  );
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
      setCustodyHubExchange(currentSettings.custody_hub_exchange ?? 'Bybit');
      setCustodyHubNetwork(currentSettings.custody_hub_network ?? 'Aptos');
      setTradingFloatMultiplier(currentSettings.trading_float_multiplier ?? 8.0);
      setTradingFloatReplenishTrigger(currentSettings.trading_float_replenish_trigger ?? 3.0);
      setTradingFloatOverflowMultiplier(currentSettings.trading_float_overflow_multiplier ?? 1.5);
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
      setFastTrackDiscoveryEnabled(currentSettings.fast_track_discovery_enabled ?? true);
      setFastTrackAggressiveness(currentSettings.fast_track_aggressiveness ?? 1.0);
      setAutoDisableVolumeEnabled(currentSettings.auto_disable_volume_enabled ?? true);
      setAutoDisableVolumeThreshold(currentSettings.auto_disable_volume_threshold_usd ?? 10000);
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
      setRealizedDdEmergencyPct(currentSettings.realized_drawdown_emergency_pct ?? 15.0);
      setCombinedDdEmergencyPct(currentSettings.combined_drawdown_emergency_pct ?? 25.0);
      setCombinedDdSustainedSec(currentSettings.combined_drawdown_sustained_seconds ?? 300);
      setEmergencyAutoLiquidate(currentSettings.emergency_auto_liquidate ?? false);
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
    custody_hub_exchange: custodyHubExchange,
    custody_hub_network: custodyHubNetwork,
    trading_float_multiplier: tradingFloatMultiplier,
    trading_float_replenish_trigger: tradingFloatReplenishTrigger,
    trading_float_overflow_multiplier: tradingFloatOverflowMultiplier,
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
    fast_track_discovery_enabled: fastTrackDiscoveryEnabled,
    fast_track_aggressiveness: fastTrackAggressiveness,
    auto_disable_volume_enabled: autoDisableVolumeEnabled,
    auto_disable_volume_threshold_usd: autoDisableVolumeThreshold,
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
    realized_drawdown_emergency_pct: realizedDdEmergencyPct,
    combined_drawdown_emergency_pct: combinedDdEmergencyPct,
    combined_drawdown_sustained_seconds: combinedDdSustainedSec,
    emergency_auto_liquidate: emergencyAutoLiquidate,
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


  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Sub-tab navigation */}
      <div className="flex gap-1 bg-slate-800/50 rounded-lg p-1">
        {([
          ['/settings', 'Config Groups'],
          ['/settings/general', 'Global'],
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

      {activeSubTab === 'config-groups' ? (
        <ConfigGroupsTab
          registry={registry}
          configsLite={configsLite}
          selectedConfigId={selectedConfigId}
          onSendMessage={onSendMessage}
          onSendWithCallback={onSendWithCallback}
          globalVolumes={globalVolumes}
        />
      ) : activeSubTab === 'transfers' ? (
        <TransferFeeManagementTab
          transferConfigs={transferConfigs}
          onSendMessage={onSendMessage}
        />
      ) : (
      <>
      {/* v0.31: per-config settings now live inside the per-config Edit modal.
          The Global tab keeps only shared concerns (24h volume fetcher,
          security/IP whitelist, danger zone). The per-config form sections
          below are kept hidden as `{false && ...}` so the legacy code is
          available for follow-up cleanup without losing it. */}
      <div className="bg-slate-800/40 border border-slate-700/50 rounded-lg p-4 text-sm text-slate-400">
        <div className="flex items-start gap-3">
          <span className="text-cyan-400 text-base leading-none mt-0.5">ⓘ</span>
          <div>
            <div className="text-slate-300 font-medium mb-1">Per-config settings moved</div>
            <p className="text-xs">
              Trade sizing, scoring, anomaly protection, hedging, and all other per-config
              parameters now live inside each config's <span className="text-cyan-400">Edit</span> modal
              (Settings → <NavLink to="/settings" className="text-cyan-400 hover:underline">Config Groups</NavLink>).
              This Global tab keeps only shared settings: 24h volume fetcher, IP whitelist, and the
              Danger Zone (process/all-config restarts).
            </p>
          </div>
        </div>
      </div>

      {/* Execution Mode (super-primary inheritance) */}
      {registry && (
        <ExecutionModeSection
          registry={registry}
          configsLite={configsLite}
          onSendMessage={onSendMessage}
        />
      )}

      {/* 24h Volume Fetcher (universal) */}
      {globalVolumeFetcher}


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
          {/* v0.31: Manual Trading Control moved per-config — each config in
              the Config Groups tab now has its own Stop / Resume button. */}
          {/* Hard Stop — affects ONLY the selected config. The label
              shows which config to make the scope explicit. */}
          {(() => {
            const selectedCfgName =
              configsLite?.find((l) => l.id === selectedConfigId)?.name
              ?? 'Selected Config';
            return (
              <>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-slate-300">
                      Hard Stop <span className="text-amber-400 font-medium">{selectedCfgName}</span> — Convert Crypto to USDT
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Sells all crypto in <span className="text-amber-400 font-medium">{selectedCfgName}</span>'s wallet across all exchanges. Stops trading automatically. Other configs are unaffected.
                    </p>
                  </div>
                  <button onClick={() => { setShowHardStop(true); setHardStopConfirmText(''); setHardStopResult(null); }}
                    className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors whitespace-nowrap">
                    Hard Stop {selectedCfgName}
                  </button>
                </div>
                <div className="border-t border-red-900/30" />
                {/* Distribute from custody hub — also scoped to selected config */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-slate-300">
                      Distribute USDT from {currentSettings.custody_hub_exchange ?? 'Bybit'} <span className="text-amber-400 font-medium">({selectedCfgName})</span>
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {distributeEnabled
                        ? <>Distribute {currentSettings.custody_hub_exchange ?? 'Bybit'} USDT to exchanges in <span className="text-amber-400 font-medium">{selectedCfgName}</span>'s wallet based on symbol profitability.</>
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
              </>
            );
          })()}
          <div className="border-t border-red-900/30" />
          {/* Restart All Configs (v0.31) */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <p className="text-sm text-slate-300">Restart All Configs</p>
              <p className="text-xs text-slate-500 mt-0.5">Reset every config's per-config state (trades, balance, optimizer) without restarting the bot process. Use this to start a fresh session for all variations simultaneously.</p>
            </div>
            <button
              onClick={() => setShowRestartAllConfirm(true)}
              className="px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white rounded-lg text-sm font-medium transition-colors">
              Restart All Configs
            </button>
          </div>
          <div className="border-t border-red-900/30" />
          {/* Restart Process (was Restart Bot) */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <p className="text-sm text-slate-300">Restart Process</p>
              <p className="text-xs text-slate-500 mt-0.5">Re-execute the Python process (used after deploying code changes). Discards all session data and starts fresh.</p>
            </div>
            <button onClick={() => setShowRestartConfirm(true)}
              className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors">
              Restart Process
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

      {/* Restart Process Confirmation Modal */}
      {showRestartConfirm && (
        <ConfirmModal
          title="Restart Process?"
          message={
            <>
              This re-executes the Python process and discards all current session
              data. Use this after deploying code changes. The bot will reload
              from <span className="text-white font-medium">settings.json</span>.
            </>
          }
          confirmLabel="Restart Process"
          destructive
          onConfirm={() => {
            onSendMessage({ type: 'restart' });
            setShowRestartConfirm(false);
            toast.show('Restart requested — reconnecting…', 'info', 4000);
          }}
          onCancel={() => setShowRestartConfirm(false)}
        />
      )}

      {/* Restart All Configs Confirmation Modal */}
      {showRestartAllConfirm && (
        <ConfirmModal
          title="Restart All Configs?"
          message={
            <>
              This resets per-config state (trades, balance, optimizer rankings)
              for <span className="text-white font-medium">every config</span>.
              The bot process keeps running. Use this to start a fresh session
              for all variations simultaneously.
            </>
          }
          confirmLabel="Restart All"
          destructive
          onConfirm={() => {
            onSendMessage({ type: 'config_restart_all' });
            setShowRestartAllConfirm(false);
            toast.show('All configs restarted', 'success');
          }}
          onCancel={() => setShowRestartAllConfirm(false)}
        />
      )}

      {/* Hard Stop Modal */}
      {showHardStop && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl max-w-lg w-full mx-4 border border-red-900/50 overflow-hidden">
            <div className="bg-red-900/60 px-6 py-3">
              <h3 className="text-lg font-semibold text-red-200">
                Hard Stop {configsLite?.find((l) => l.id === selectedConfigId)?.name ?? 'Selected Config'} — Convert Crypto to USDT
              </h3>
              <p className="text-xs text-red-300/70 mt-0.5">Affects only this config's wallet. Other configs continue trading.</p>
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

      {/* Distribute USDT from custody hub Modal (v0.30+: dynamic label) */}
      {showDistribute && (() => {
        const hub = currentSettings.custody_hub_exchange ?? 'Bybit';
        const network = currentSettings.custody_hub_network ?? 'Aptos';
        const hubBalance = balances?.[hub];
        return (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-xl max-w-lg w-full mx-4 border border-red-900/50 overflow-hidden">
            <div className="bg-red-900/60 px-6 py-3">
              <h3 className="text-lg font-semibold text-red-200">Distribute USDT from {hub}</h3>
            </div>
            <div className="p-6">
              {distributeResult ? (
                <div>
                  <p className="text-emerald-400 font-medium mb-3">Distribution Complete ({distributeResult.strategy})</p>
                  <div className="text-sm text-slate-300 space-y-1">
                    <div>Total distributed: <span className="text-white font-mono">${distributeResult.distributed.toFixed(2)}</span></div>
                    {distributeResult.transfers.map((t, i) => (
                      <div key={i} className="text-xs text-slate-400">{hub} → {t.exchange}: <span className="font-mono text-white">${t.amount.toFixed(2)}</span></div>
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
                  {hubBalance && (
                    <div className="bg-slate-900/50 rounded-lg p-3 mb-4 text-xs">
                      <div className="text-slate-500 font-medium mb-2">{hub} Balance</div>
                      <div className="space-y-1 text-slate-300">
                        <div>USDT: <span className="text-white font-mono">${hubBalance.usdt.toFixed(2)}</span></div>
                        <div>Distributable (95%): <span className="text-emerald-400 font-mono">${(hubBalance.usdt * 0.95).toFixed(2)}</span></div>
                      </div>
                      <div className="mt-2 text-slate-500">Distribution via {network} (score-weighted to profitable exchanges)</div>
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
                          { type: 'distribute_from_custody_hub' },
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
        );
      })()}

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
