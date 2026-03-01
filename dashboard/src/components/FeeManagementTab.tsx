import { useState, useEffect } from 'react';
import type { ExchangeFeeConfig, FeeStats } from '../types';

// Default configs matching config.py DEFAULT_FEE_CONFIGS
const DEFAULT_CONFIGS: Record<string, ExchangeFeeConfig> = {
  Binance: {
    base_taker_rate: 0.001, token_discount_enabled: true, token_discount_pct: 0.25,
    effective_taker_rate: 0.00075, effective_rate_after_referral: 0.00075,
    fee_mechanism: 'instant', fee_model: 'token',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 30,
    referral_paid_in: 'same_as_fee', zero_fee_pairs: [], enabled: true,
  },
  OKX: {
    base_taker_rate: 0.001, token_discount_enabled: false, token_discount_pct: 0,
    effective_taker_rate: 0.001, effective_rate_after_referral: 0.001,
    fee_mechanism: 'tier', fee_model: 'received',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 90,
    referral_paid_in: 'same_as_fee', zero_fee_pairs: [], enabled: true,
  },
  Bybit: {
    base_taker_rate: 0.001, token_discount_enabled: false, token_discount_pct: 0,
    effective_taker_rate: 0.001, effective_rate_after_referral: 0.001,
    fee_mechanism: 'tier', fee_model: 'received',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 720,
    referral_paid_in: 'USDT', zero_fee_pairs: [], enabled: true,
  },
  MEXC: {
    base_taker_rate: 0.0005, token_discount_enabled: false, token_discount_pct: 0.20,
    effective_taker_rate: 0.0005, effective_rate_after_referral: 0.0005,
    fee_mechanism: 'instant', fee_model: 'received',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 720,
    referral_paid_in: 'same_as_fee', zero_fee_pairs: [], enabled: true,
  },
  Bitget: {
    base_taker_rate: 0.001, token_discount_enabled: true, token_discount_pct: 0.20,
    effective_taker_rate: 0.0008, effective_rate_after_referral: 0.0008,
    fee_mechanism: 'instant', fee_model: 'token',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 1080,
    referral_paid_in: 'USDT', zero_fee_pairs: [], enabled: true,
  },
  KuCoin: {
    base_taker_rate: 0.001, token_discount_enabled: true, token_discount_pct: 0.20,
    effective_taker_rate: 0.0008, effective_rate_after_referral: 0.0008,
    fee_mechanism: 'rebate', fee_model: 'token',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 1080,
    referral_paid_in: 'same_as_fee', zero_fee_pairs: [], enabled: true,
  },
  'Gate.io': {
    base_taker_rate: 0.001, token_discount_enabled: false, token_discount_pct: 0.10,
    effective_taker_rate: 0.001, effective_rate_after_referral: 0.001,
    fee_mechanism: 'instant', fee_model: 'received',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 0,
    referral_paid_in: 'same_as_fee', zero_fee_pairs: ['BTCUSDT'], enabled: true,
  },
  Pionex: {
    base_taker_rate: 0.0005, token_discount_enabled: false, token_discount_pct: 0,
    effective_taker_rate: 0.0005, effective_rate_after_referral: 0.0005,
    fee_mechanism: 'instant', fee_model: 'received',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 0,
    referral_paid_in: 'same_as_fee', zero_fee_pairs: [], enabled: true,
  },
  Bitfinex: {
    base_taker_rate: 0, token_discount_enabled: false, token_discount_pct: 0,
    effective_taker_rate: 0, effective_rate_after_referral: 0,
    fee_mechanism: 'instant', fee_model: 'received',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 0,
    referral_paid_in: 'same_as_fee', zero_fee_pairs: [], enabled: true,
  },
};

const EXCHANGE_ORDER = ['Binance', 'OKX', 'Bybit', 'MEXC', 'Bitget', 'KuCoin', 'Gate.io', 'Pionex', 'Bitfinex'];

const TOKEN_NAMES: Record<string, string> = {
  Binance: 'BNB', Bitget: 'BGB', KuCoin: 'KCS', 'Gate.io': 'GT', MEXC: 'MX',
};

interface FeeManagementTabProps {
  feeConfigs?: Record<string, ExchangeFeeConfig>;
  feeRealMode?: boolean;
  feeStats?: FeeStats;
  onSendMessage: (msg: object) => void;
}

type EditableConfig = {
  base_taker_rate: number;
  token_discount_enabled: boolean;
  token_discount_pct: number;
  fee_mechanism: 'instant' | 'rebate' | 'tier';
  fee_model: 'received' | 'spent' | 'token';
  referral_enabled: boolean;
  referral_cashback_pct: number;
  referral_settlement_minutes: number;
  referral_paid_in: 'same_as_fee' | 'USDT';
  zero_fee_pairs: string;
  enabled: boolean;
};

function toEditable(cfg: ExchangeFeeConfig): EditableConfig {
  return {
    base_taker_rate: cfg.base_taker_rate,
    token_discount_enabled: cfg.token_discount_enabled,
    token_discount_pct: cfg.token_discount_pct,
    fee_mechanism: cfg.fee_mechanism,
    fee_model: cfg.fee_model,
    referral_enabled: cfg.referral_enabled,
    referral_cashback_pct: cfg.referral_cashback_pct,
    referral_settlement_minutes: cfg.referral_settlement_minutes,
    referral_paid_in: cfg.referral_paid_in,
    zero_fee_pairs: cfg.zero_fee_pairs.join(', '),
    enabled: cfg.enabled ?? true,
  };
}

function computeEffective(cfg: EditableConfig): { effective: number; afterReferral: number } {
  let rate = cfg.base_taker_rate;
  if (cfg.token_discount_enabled && cfg.token_discount_pct > 0) {
    rate *= (1.0 - cfg.token_discount_pct);
  }
  const effective = rate;
  let afterRef = rate;
  if (cfg.referral_enabled && cfg.referral_cashback_pct > 0) {
    afterRef *= (1.0 - cfg.referral_cashback_pct);
  }
  return { effective, afterReferral: afterRef };
}

export default function FeeManagementTab({ feeConfigs, feeRealMode, feeStats, onSendMessage }: FeeManagementTabProps) {
  const serverConfigs = feeConfigs ?? {};
  const [configs, setConfigs] = useState<Record<string, EditableConfig>>(() => {
    const initial: Record<string, EditableConfig> = {};
    for (const ex of EXCHANGE_ORDER) {
      initial[ex] = toEditable(serverConfigs[ex] ?? DEFAULT_CONFIGS[ex]);
    }
    return initial;
  });
  const [dirty, setDirty] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  // Sync from server when not dirty
  const configKey = JSON.stringify(feeConfigs);
  useEffect(() => {
    if (!dirty && feeConfigs) {
      const updated: Record<string, EditableConfig> = {};
      for (const ex of EXCHANGE_ORDER) {
        updated[ex] = toEditable(feeConfigs[ex] ?? DEFAULT_CONFIGS[ex]);
      }
      setConfigs(updated);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configKey]);

  const updateField = (exchange: string, field: keyof EditableConfig, value: unknown) => {
    setDirty(true);
    setConfigs(prev => ({
      ...prev,
      [exchange]: { ...prev[exchange], [field]: value },
    }));
  };

  const handleSave = () => {
    // Build the wire format
    const feeData: Record<string, object> = {};
    for (const [ex, cfg] of Object.entries(configs)) {
      feeData[ex] = {
        base_taker_rate: cfg.base_taker_rate,
        token_discount_enabled: cfg.token_discount_enabled,
        token_discount_pct: cfg.token_discount_pct,
        fee_mechanism: cfg.fee_mechanism,
        fee_model: cfg.fee_model,
        referral_enabled: cfg.referral_enabled,
        referral_cashback_pct: cfg.referral_cashback_pct,
        referral_settlement_minutes: cfg.referral_settlement_minutes,
        referral_paid_in: cfg.referral_paid_in,
        zero_fee_pairs: cfg.zero_fee_pairs.split(',').map(s => s.trim()).filter(Boolean),
        enabled: cfg.enabled,
      };
    }
    onSendMessage({ type: 'save_fee_settings', fee_configs: feeData });
    setDirty(false);
    setSaveStatus('Saved!');
    setTimeout(() => setSaveStatus(null), 3000);
  };

  const inputCls = 'w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500';
  const selectCls = 'bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500';

  return (
    <div className="space-y-4 sm:space-y-5 max-w-3xl">
      {/* Real mode banner */}
      {feeRealMode && (
        <div className="bg-blue-900/30 border border-blue-700/50 rounded-lg px-4 py-3">
          <p className="text-sm text-blue-300">
            Real Mode active — fees from exchange APIs override these config values.
          </p>
        </div>
      )}

      {/* Cashback stats */}
      {feeStats && (feeStats.pending_count > 0 || feeStats.credited_cashback_total > 0) && (
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-4">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Referral Cashback</h3>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-slate-500">Pending</span>
              <p className="text-amber-400 font-medium">${feeStats.pending_cashback_total.toFixed(4)}</p>
              <span className="text-xs text-slate-500">{feeStats.pending_count} entries</span>
            </div>
            <div>
              <span className="text-slate-500">Credited</span>
              <p className="text-emerald-400 font-medium">${feeStats.credited_cashback_total.toFixed(4)}</p>
            </div>
            <div>
              <span className="text-slate-500">Total</span>
              <p className="text-white font-medium">
                ${(feeStats.pending_cashback_total + feeStats.credited_cashback_total).toFixed(4)}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Per-exchange cards */}
      {EXCHANGE_ORDER.map(exchange => {
        const cfg = configs[exchange];
        if (!cfg) return null;
        const { effective, afterReferral } = computeEffective(cfg);
        const tokenName = TOKEN_NAMES[exchange];

        return (
          <div key={exchange} className={`rounded-lg p-3 sm:p-5 ${cfg.enabled ? 'bg-slate-800/50' : 'bg-slate-800/20 opacity-60'}`}>
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={cfg.enabled}
                    onChange={e => updateField(exchange, 'enabled', e.target.checked)}
                    className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500" />
                </label>
                <h2 className={`text-sm font-semibold uppercase tracking-wider ${cfg.enabled ? 'text-slate-200' : 'text-slate-500 line-through'}`}>{exchange}</h2>
                {!cfg.enabled && (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-red-900/40 text-red-400">Disabled</span>
                )}
              </div>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-700 text-emerald-400">
                Effective: {(effective * 100).toFixed(4)}%
              </span>
            </div>

            {/* Base rate + fee model */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">Base Taker Rate (%)</label>
                <input type="number" step="0.001" min="0" max="1"
                  value={(cfg.base_taker_rate * 100).toFixed(3)}
                  onChange={e => updateField(exchange, 'base_taker_rate', (Number(e.target.value) || 0) / 100)}
                  className={inputCls} />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Fee Model</label>
                <select value={cfg.fee_model}
                  onChange={e => updateField(exchange, 'fee_model', e.target.value)}
                  className={selectCls + ' w-full'}>
                  <option value="received">Received</option>
                  <option value="spent">Spent</option>
                  <option value="token">Token</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Mechanism</label>
                <span className="inline-block mt-1 px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-300">
                  {cfg.fee_mechanism}
                </span>
              </div>
            </div>

            {/* Token Discount */}
            <div className="border-t border-slate-700/50 pt-3 mb-3">
              <div className="flex items-center gap-3 mb-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={cfg.token_discount_enabled}
                    onChange={e => updateField(exchange, 'token_discount_enabled', e.target.checked)}
                    className="w-3.5 h-3.5 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500" />
                  <span className="text-xs text-slate-300">
                    Token Discount{tokenName ? ` (${tokenName})` : ''}
                  </span>
                </label>
              </div>
              {cfg.token_discount_enabled && (
                <div className="ml-5">
                  <label className="block text-xs text-slate-500 mb-1">Discount (%)</label>
                  <input type="number" step="1" min="0" max="100"
                    value={(cfg.token_discount_pct * 100).toFixed(0)}
                    onChange={e => updateField(exchange, 'token_discount_pct', (Number(e.target.value) || 0) / 100)}
                    className={inputCls + ' w-32'} />
                </div>
              )}
            </div>

            {/* Referral Cashback */}
            <div className="border-t border-slate-700/50 pt-3 mb-3">
              <div className="flex items-center gap-3 mb-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={cfg.referral_enabled}
                    onChange={e => updateField(exchange, 'referral_enabled', e.target.checked)}
                    className="w-3.5 h-3.5 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500" />
                  <span className="text-xs text-slate-300">Referral Cashback</span>
                </label>
              </div>
              {cfg.referral_enabled && (
                <div className="ml-5 grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Cashback (%)</label>
                    <input type="number" step="1" min="0" max="100"
                      value={(cfg.referral_cashback_pct * 100).toFixed(0)}
                      onChange={e => updateField(exchange, 'referral_cashback_pct', (Number(e.target.value) || 0) / 100)}
                      className={inputCls} />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Settlement (min)</label>
                    <input type="number" step="1" min="0"
                      value={cfg.referral_settlement_minutes}
                      onChange={e => updateField(exchange, 'referral_settlement_minutes', Number(e.target.value) || 0)}
                      className={inputCls} />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Paid In</label>
                    <select value={cfg.referral_paid_in}
                      onChange={e => updateField(exchange, 'referral_paid_in', e.target.value)}
                      className={selectCls + ' w-full'}>
                      <option value="same_as_fee">Same as Fee</option>
                      <option value="USDT">USDT</option>
                    </select>
                  </div>
                </div>
              )}
            </div>

            {/* Zero-Fee Pairs */}
            <div className="border-t border-slate-700/50 pt-3">
              <label className="block text-xs text-slate-500 mb-1">Zero-Fee Pairs (comma-separated)</label>
              <input type="text" value={cfg.zero_fee_pairs}
                onChange={e => updateField(exchange, 'zero_fee_pairs', e.target.value)}
                placeholder="e.g. BTCUSDT, ETHUSDT"
                className={inputCls + ' placeholder-slate-500'} />
            </div>

            {/* Effective rate summary */}
            <div className="mt-3 pt-2 border-t border-slate-700/50 text-xs text-slate-400">
              <span>Effective: <span className="text-emerald-400">{(effective * 100).toFixed(4)}%</span></span>
              {cfg.token_discount_enabled && cfg.token_discount_pct > 0 && (
                <span className="ml-1">
                  (base {(cfg.base_taker_rate * 100).toFixed(2)}% - {(cfg.token_discount_pct * 100).toFixed(0)}%
                  {tokenName ? ` ${tokenName}` : ''})
                </span>
              )}
              {cfg.referral_enabled && cfg.referral_cashback_pct > 0 && (
                <span className="ml-3">
                  After referral: <span className="text-blue-400">{(afterReferral * 100).toFixed(4)}%</span>
                  <span className="ml-1">(delayed ~{cfg.referral_settlement_minutes}min)</span>
                </span>
              )}
            </div>
          </div>
        );
      })}

      {/* Save Button */}
      <div className="flex items-center gap-3">
        <button onClick={handleSave}
          className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors">
          Save Fee Settings
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
