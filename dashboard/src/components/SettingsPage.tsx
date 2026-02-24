import { useState, useEffect } from 'react';
import type { Settings } from '../types';

interface SettingsPageProps {
  currentSettings: Settings;
  onSave: (settings: Settings) => void;
  onApply: (settings: Settings) => void;
  onSendMessage: (msg: object) => void;
}

export default function SettingsPage({ currentSettings, onSave, onApply, onSendMessage }: SettingsPageProps) {
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
  const [rebalanceRoiHorizon, setRebalanceRoiHorizon] = useState(currentSettings.rebalance_roi_horizon ?? 1800);
  const [adaptiveMode, setAdaptiveMode] = useState(currentSettings.adaptive_mode ?? true);
  const [ipWhitelistEnabled, setIpWhitelistEnabled] = useState(currentSettings.ip_whitelist_enabled ?? false);
  const [ipWhitelist, setIpWhitelist] = useState((currentSettings.ip_whitelist ?? []).join(', '));
  const [securityStatus, setSecurityStatus] = useState<string | null>(null);

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
      setRebalanceRoiHorizon(currentSettings.rebalance_roi_horizon ?? 1800);
      setAdaptiveMode(currentSettings.adaptive_mode ?? true);
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
    rebalance_roi_horizon: rebalanceRoiHorizon,
    adaptive_mode: adaptiveMode,
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
    <div className="space-y-6 max-w-3xl">
      {/* Capital */}
      <div className="bg-slate-800/50 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Capital</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-slate-500 mb-1">Total Capital ($)</label>
            <input type="number" value={totalCapital} min={100} onChange={d(setTotalCapital, 1800)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            <p className="text-xs text-slate-500 mt-1">Distributed evenly across all connected exchanges</p>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Trade Amount ($)</label>
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
          </label>
          <p className="text-xs text-slate-500 ml-7 mt-1">
            Dynamically adjusts trade sizes, rebalance amounts, and thresholds based on real-time market conditions and available capital.
          </p>
        </div>
      </div>

      {/* Auto-Rotation */}
      <div className="bg-slate-800/50 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Auto-Rotation</h2>
        <div className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={autoRotate}
              onChange={e => { setDirty(true); setAutoRotate(e.target.checked); }}
              className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500" />
            <span className="text-sm text-slate-300">Enable automatic symbol rotation</span>
          </label>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label className="block text-xs text-slate-500 mb-1">Min Active Symbols</label>
              <input type="number" value={numActiveSymbols} min={1} max={20} onChange={d(setNumActiveSymbols, 3)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Max Active Symbols</label>
              <input type="number" value={maxActiveSymbols} min={1} max={30} onChange={d(setMaxActiveSymbols, 8)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Scoring Window (s)</label>
              <input type="number" value={scoringWindow} min={60} onChange={d(setScoringWindow, 1800)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Eval Interval (s)</label>
              <input type="number" value={evaluationInterval} min={30} onChange={d(setEvaluationInterval, 300)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            </div>
          </div>
          <p className="text-xs text-slate-500">
            Discovery scores all 60 symbols. Active set starts at min and can expand to max when confirmed candidates appear.
          </p>
        </div>
      </div>

      {/* Advanced Optimizer */}
      <div className="bg-slate-800/50 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Advanced Optimizer</h2>
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs text-slate-500 mb-1">Safety Multiplier</label>
            <input type="number" value={safetyMultiplier} min={1} step={0.5} onChange={d(setSafetyMultiplier, 2.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            <p className="text-xs text-slate-500 mt-1">Hourly gain must exceed N x switching cost</p>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Min Rebalance Score</label>
            <input type="number" value={minRebalanceScore} min={0} step={0.0001}
              onChange={d(setMinRebalanceScore, 0.0001)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            <p className="text-xs text-slate-500 mt-1">Skip transfers for symbols below this score</p>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Confirmation Period (s)</label>
            <input type="number" value={confirmationPeriod} min={0} onChange={d(setConfirmationPeriod, 300)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            <p className="text-xs text-slate-500 mt-1">How long a candidate must sustain high score</p>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Promotion Threshold</label>
            <input type="number" value={promotionThreshold} min={0} step={0.0001}
              onChange={d(setPromotionThreshold, 0.0001)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            <p className="text-xs text-slate-500 mt-1">Min score to enter watchlist</p>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Demotion Threshold</label>
            <input type="number" value={demotionThreshold} min={0} step={0.0001}
              onChange={d(setDemotionThreshold, 0.0)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            <p className="text-xs text-slate-500 mt-1">Score below which demotion timer starts</p>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Demotion Period (s)</label>
            <input type="number" value={demotionPeriod} min={0} onChange={d(setDemotionPeriod, 600)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            <p className="text-xs text-slate-500 mt-1">How long below threshold before removal</p>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Min Net Profit %</label>
            <input type="number" value={minNetProfitPct} min={0} step={0.01}
              onChange={d(setMinNetProfitPct, 0.02)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            <p className="text-xs text-slate-500 mt-1">Don't trade unless net spread exceeds this %</p>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Rebalance Cooldown (s)</label>
            <input type="number" value={rebalanceCooldown} min={0} onChange={d(setRebalanceCooldown, 30)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            <p className="text-xs text-slate-500 mt-1">Min seconds between rebalances per exchange</p>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Rebalance ROI Horizon (s)</label>
            <input type="number" value={rebalanceRoiHorizon} min={0} onChange={d(setRebalanceRoiHorizon, 1800)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            <p className="text-xs text-slate-500 mt-1">Max seconds to recoup rebalance cost</p>
          </div>
        </div>
      </div>

      {/* Security */}
      <div className="bg-slate-800/50 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Security</h2>
        <div className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={ipWhitelistEnabled}
              onChange={e => setIpWhitelistEnabled(e.target.checked)}
              className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500" />
            <span className="text-sm text-slate-300">Enable IP Whitelist</span>
          </label>
          <p className="text-xs text-slate-500 ml-7 -mt-2">
            Only allow connections from specific IP addresses. Leave empty to allow all.
          </p>
          {ipWhitelistEnabled && (
            <div>
              <label className="block text-xs text-slate-500 mb-1">Allowed IPs (comma-separated)</label>
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

      {/* Action Buttons */}
      <div className="flex items-center gap-4">
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
    </div>
  );
}
