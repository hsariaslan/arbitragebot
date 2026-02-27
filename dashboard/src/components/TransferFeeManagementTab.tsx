import { useState, useEffect } from 'react';
import type { ExchangeTransferConfig } from '../types';

const EXCHANGE_ORDER = ['Binance', 'OKX', 'Bybit', 'MEXC', 'Bitget', 'KuCoin', 'Gate.io', 'Pionex', 'Bitfinex'];

interface TransferFeeManagementTabProps {
  transferConfigs?: Record<string, ExchangeTransferConfig>;
  onSendMessage: (msg: object) => void;
}

type EditableNetwork = {
  network: string;
  fee: number;
  fee_type: 'flat' | 'percentage' | 'conditional';
  percentage_rate: number;
  percentage_min: number;
  min_withdrawal: number;
  speed_seconds: number;
  enabled: boolean;
  notes: string;
};

type EditableExchangeConfig = {
  preferred_network: string;
  networks: EditableNetwork[];
};

function toEditable(cfg: ExchangeTransferConfig): EditableExchangeConfig {
  return {
    preferred_network: cfg.preferred_network,
    networks: cfg.networks.map(n => ({ ...n })),
  };
}

function formatFee(net: EditableNetwork, amount?: number): string {
  if (net.fee_type === 'percentage') {
    const pctStr = `${(net.percentage_rate * 100).toFixed(1)}%`;
    return `max($${net.percentage_min.toFixed(2)}, ${amount ? `$${amount}` : 'amt'} × ${pctStr})`;
  }
  if (net.fee_type === 'conditional') {
    if (amount !== undefined && amount >= net.min_withdrawal) return `$${net.fee.toFixed(2)}`;
    return `Free if ≥ $${net.min_withdrawal.toLocaleString()}`;
  }
  return `$${net.fee.toFixed(net.fee < 0.01 ? 3 : 2)}`;
}

function computeEffectiveFee(nets: EditableNetwork[], preferred: string): { fee: number; network: string } {
  const enabled = nets.filter(n => n.enabled);
  if (enabled.length === 0) return { fee: 1.0, network: 'none' };

  if (preferred !== 'auto') {
    const match = enabled.find(n => n.network === preferred);
    if (match) {
      const fee = match.fee_type === 'flat' ? match.fee
        : match.fee_type === 'percentage' ? Math.max(match.percentage_min, 0)
        : match.fee;
      return { fee, network: match.network };
    }
  }

  // Auto: find cheapest flat fee (percentage/conditional are complex, use their base fee for sorting)
  let cheapest = enabled[0];
  let cheapestFee = Infinity;
  for (const n of enabled) {
    let f: number;
    if (n.fee_type === 'flat') f = n.fee;
    else if (n.fee_type === 'percentage') f = n.percentage_min;
    else f = n.fee; // conditional: use base fee (0 for free tiers)
    if (f < cheapestFee) {
      cheapestFee = f;
      cheapest = n;
    }
  }
  return { fee: cheapestFee, network: cheapest.network };
}

function formatSpeed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

const FEE_TYPE_BADGE: Record<string, { bg: string; text: string }> = {
  flat: { bg: 'bg-slate-600', text: 'text-slate-200' },
  percentage: { bg: 'bg-purple-900/50', text: 'text-purple-300' },
  conditional: { bg: 'bg-amber-900/50', text: 'text-amber-300' },
};

export default function TransferFeeManagementTab({ transferConfigs, onSendMessage }: TransferFeeManagementTabProps) {
  const serverConfigs = transferConfigs ?? {};
  const [configs, setConfigs] = useState<Record<string, EditableExchangeConfig>>(() => {
    const initial: Record<string, EditableExchangeConfig> = {};
    for (const ex of EXCHANGE_ORDER) {
      if (serverConfigs[ex]) {
        initial[ex] = toEditable(serverConfigs[ex]);
      }
    }
    return initial;
  });
  const [dirty, setDirty] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  // Sync from server when not dirty
  const configKey = JSON.stringify(transferConfigs);
  useEffect(() => {
    if (!dirty && transferConfigs) {
      const updated: Record<string, EditableExchangeConfig> = {};
      for (const ex of EXCHANGE_ORDER) {
        if (transferConfigs[ex]) {
          updated[ex] = toEditable(transferConfigs[ex]);
        }
      }
      setConfigs(updated);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configKey]);

  const updatePreferred = (exchange: string, value: string) => {
    setDirty(true);
    setConfigs(prev => ({
      ...prev,
      [exchange]: { ...prev[exchange], preferred_network: value },
    }));
  };

  const updateNetwork = (exchange: string, idx: number, field: keyof EditableNetwork, value: unknown) => {
    setDirty(true);
    setConfigs(prev => {
      const nets = [...prev[exchange].networks];
      nets[idx] = { ...nets[idx], [field]: value };
      return { ...prev, [exchange]: { ...prev[exchange], networks: nets } };
    });
  };

  const handleSave = () => {
    const transferData: Record<string, object> = {};
    for (const [ex, cfg] of Object.entries(configs)) {
      transferData[ex] = {
        preferred_network: cfg.preferred_network,
        networks: cfg.networks.map(n => ({
          network: n.network,
          fee: n.fee,
          fee_type: n.fee_type,
          percentage_rate: n.percentage_rate,
          percentage_min: n.percentage_min,
          min_withdrawal: n.min_withdrawal,
          speed_seconds: n.speed_seconds,
          enabled: n.enabled,
          notes: n.notes,
        })),
      };
    }
    onSendMessage({ type: 'save_transfer_settings', transfer_configs: transferData });
    setDirty(false);
    setSaveStatus('Saved!');
    setTimeout(() => setSaveStatus(null), 3000);
  };

  const exchanges = EXCHANGE_ORDER.filter(ex => configs[ex]);

  return (
    <div className="space-y-4 sm:space-y-5 max-w-4xl">
      {/* Per-exchange cards */}
      {exchanges.map(exchange => {
        const cfg = configs[exchange];
        if (!cfg) return null;
        const { fee: effectiveFee, network: effectiveNetwork } = computeEffectiveFee(cfg.networks, cfg.preferred_network);
        const enabledNets = cfg.networks.filter(n => n.enabled);

        return (
          <div key={exchange} className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">{exchange}</h2>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-700 text-emerald-400">
                Effective: ${effectiveFee < 0.01 ? effectiveFee.toFixed(3) : effectiveFee.toFixed(2)} ({effectiveNetwork})
              </span>
            </div>

            {/* Preferred Network */}
            <div className="mb-3">
              <label className="block text-xs text-slate-500 mb-1">Preferred Network</label>
              <select
                value={cfg.preferred_network}
                onChange={e => updatePreferred(exchange, e.target.value)}
                className="bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500 w-full sm:w-64"
              >
                <option value="auto">Auto (cheapest)</option>
                {enabledNets.map(n => (
                  <option key={n.network} value={n.network}>
                    {n.network} — ${n.fee_type === 'flat' ? n.fee.toFixed(n.fee < 0.01 ? 3 : 2) : formatFee(n)}
                  </option>
                ))}
              </select>
            </div>

            {/* Network table */}
            <div className="overflow-x-auto -mx-3 sm:-mx-5">
              <table className="w-full text-xs min-w-[640px]">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-700/50">
                    <th className="text-left py-1.5 px-3 font-medium">Network</th>
                    <th className="text-right py-1.5 px-3 font-medium">Fee</th>
                    <th className="text-center py-1.5 px-2 font-medium">Type</th>
                    <th className="text-right py-1.5 px-3 font-medium">Min Wd</th>
                    <th className="text-right py-1.5 px-2 font-medium">Speed</th>
                    <th className="text-left py-1.5 px-2 font-medium">Notes</th>
                    <th className="text-center py-1.5 px-2 font-medium">On</th>
                  </tr>
                </thead>
                <tbody>
                  {cfg.networks.map((net, idx) => {
                    const badge = FEE_TYPE_BADGE[net.fee_type] || FEE_TYPE_BADGE.flat;
                    const isActive = cfg.preferred_network === 'auto'
                      ? net.network === effectiveNetwork && net.enabled
                      : net.network === cfg.preferred_network && net.enabled;

                    return (
                      <tr key={net.network}
                        className={`border-b border-slate-700/30 ${!net.enabled ? 'opacity-40' : ''} ${isActive ? 'bg-emerald-900/10' : ''}`}>
                        <td className="py-1.5 px-3 text-slate-200 font-medium">
                          {net.network}
                          {isActive && <span className="ml-1 text-emerald-400 text-[10px]">●</span>}
                        </td>
                        <td className="py-1.5 px-3 text-right">
                          {net.fee_type === 'flat' ? (
                            <input type="number" step="0.001" min="0" max="100"
                              value={net.fee}
                              onChange={e => updateNetwork(exchange, idx, 'fee', Number(e.target.value) || 0)}
                              className="w-20 bg-slate-700 border border-slate-600 rounded px-2 py-0.5 text-white text-xs text-right focus:outline-none focus:border-blue-500"
                            />
                          ) : net.fee_type === 'conditional' ? (
                            <input type="number" step="0.001" min="0" max="100"
                              value={net.fee}
                              onChange={e => updateNetwork(exchange, idx, 'fee', Number(e.target.value) || 0)}
                              className="w-20 bg-slate-700 border border-slate-600 rounded px-2 py-0.5 text-white text-xs text-right focus:outline-none focus:border-blue-500"
                            />
                          ) : (
                            <span className="text-purple-300" title={formatFee(net)}>
                              {formatFee(net)}
                            </span>
                          )}
                        </td>
                        <td className="py-1.5 px-2 text-center">
                          <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${badge.bg} ${badge.text}`}>
                            {net.fee_type}
                          </span>
                        </td>
                        <td className="py-1.5 px-3 text-right text-slate-400">
                          {net.min_withdrawal > 0 ? `$${net.min_withdrawal.toLocaleString()}` : '—'}
                        </td>
                        <td className="py-1.5 px-2 text-right text-slate-400">
                          {formatSpeed(net.speed_seconds)}
                        </td>
                        <td className="py-1.5 px-2 text-slate-500 max-w-[120px] truncate" title={net.notes}>
                          {net.notes || '—'}
                        </td>
                        <td className="py-1.5 px-2 text-center">
                          <input type="checkbox" checked={net.enabled}
                            onChange={e => updateNetwork(exchange, idx, 'enabled', e.target.checked)}
                            className="w-3.5 h-3.5 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500"
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Summary */}
            <div className="mt-2 pt-2 border-t border-slate-700/50 text-xs text-slate-400">
              <span>Cheapest: <span className="text-emerald-400">{effectiveNetwork}</span> at </span>
              <span className="text-emerald-400">${effectiveFee < 0.01 ? effectiveFee.toFixed(3) : effectiveFee.toFixed(2)}</span>
              <span className="ml-3 text-slate-500">{enabledNets.length}/{cfg.networks.length} networks enabled</span>
            </div>
          </div>
        );
      })}

      {/* Save Button */}
      <div className="flex items-center gap-3">
        <button onClick={handleSave}
          className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors">
          Save Transfer Settings
        </button>
        {saveStatus && (
          <span className="text-emerald-400 text-sm font-medium">{saveStatus}</span>
        )}
        {dirty && !saveStatus && (
          <span className="text-amber-400 text-xs">Unsaved changes</span>
        )}
      </div>
    </div>
  );
}
