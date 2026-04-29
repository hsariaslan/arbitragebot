import { useState, useEffect } from 'react';
import type { ExchangeFeeConfig, FeeStats } from '../types';

// Default configs matching config.py DEFAULT_FEE_CONFIGS
const DEFAULT_CONFIGS: Record<string, ExchangeFeeConfig> = {
  Binance: {
    base_taker_rate: 0.001, token_discount_enabled: true, token_discount_pct: 0.25,
    effective_taker_rate: 0.00075, effective_rate_after_referral: 0.00075,
    fee_mechanism: 'instant', fee_model: 'token',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 30,
    referral_paid_in: 'same_as_fee', referrer_commission_pct: 0, zero_fee_pairs: [], enabled: true,
  },
  OKX: {
    base_taker_rate: 0.001, token_discount_enabled: false, token_discount_pct: 0,
    effective_taker_rate: 0.001, effective_rate_after_referral: 0.001,
    fee_mechanism: 'tier', fee_model: 'received',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 90,
    referral_paid_in: 'same_as_fee', referrer_commission_pct: 0, zero_fee_pairs: [], enabled: true,
  },
  Bybit: {
    base_taker_rate: 0.001, token_discount_enabled: false, token_discount_pct: 0,
    effective_taker_rate: 0.001, effective_rate_after_referral: 0.001,
    fee_mechanism: 'tier', fee_model: 'received',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 720,
    referral_paid_in: 'USDT', referrer_commission_pct: 0, zero_fee_pairs: [], enabled: true,
  },
  MEXC: {
    base_taker_rate: 0.0005, token_discount_enabled: false, token_discount_pct: 0.20,
    effective_taker_rate: 0.0005, effective_rate_after_referral: 0.0005,
    fee_mechanism: 'instant', fee_model: 'received',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 720,
    referral_paid_in: 'same_as_fee', referrer_commission_pct: 0, zero_fee_pairs: [], enabled: true,
  },
  Bitget: {
    base_taker_rate: 0.001, token_discount_enabled: true, token_discount_pct: 0.20,
    effective_taker_rate: 0.0008, effective_rate_after_referral: 0.0008,
    fee_mechanism: 'instant', fee_model: 'token',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 1080,
    referral_paid_in: 'USDT', referrer_commission_pct: 0, zero_fee_pairs: [], enabled: true,
  },
  KuCoin: {
    base_taker_rate: 0.001, token_discount_enabled: true, token_discount_pct: 0.20,
    effective_taker_rate: 0.0008, effective_rate_after_referral: 0.0008,
    fee_mechanism: 'rebate', fee_model: 'token',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 1080,
    referral_paid_in: 'same_as_fee', referrer_commission_pct: 0, zero_fee_pairs: [], enabled: true,
  },
  'Gate.io': {
    base_taker_rate: 0.001, token_discount_enabled: false, token_discount_pct: 0.10,
    effective_taker_rate: 0.001, effective_rate_after_referral: 0.001,
    fee_mechanism: 'instant', fee_model: 'received',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 0,
    referral_paid_in: 'same_as_fee', referrer_commission_pct: 0, zero_fee_pairs: ['BTCUSDT'], enabled: true,
  },
  Pionex: {
    base_taker_rate: 0.0005, token_discount_enabled: false, token_discount_pct: 0,
    effective_taker_rate: 0.0005, effective_rate_after_referral: 0.0005,
    fee_mechanism: 'instant', fee_model: 'received',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 0,
    referral_paid_in: 'same_as_fee', referrer_commission_pct: 0, zero_fee_pairs: [], enabled: true,
  },
  Bitfinex: {
    base_taker_rate: 0, token_discount_enabled: false, token_discount_pct: 0,
    effective_taker_rate: 0, effective_rate_after_referral: 0,
    fee_mechanism: 'instant', fee_model: 'received',
    referral_enabled: false, referral_cashback_pct: 0, referral_settlement_minutes: 0,
    referral_paid_in: 'same_as_fee', referrer_commission_pct: 0, zero_fee_pairs: [], enabled: true,
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
  onSendWithCallback?: (msg: object, callback: (data: unknown) => void) => void;
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
  referrer_commission_pct: number;
  zero_fee_pairs: string;
  enabled: boolean;
  as_buyer: boolean;
  as_seller: boolean;
  disabled_symbols: Set<string>;
  buyer_boost: number;
  seller_boost: number;
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
    referrer_commission_pct: cfg.referrer_commission_pct ?? 0,
    zero_fee_pairs: cfg.zero_fee_pairs.join(', '),
    enabled: cfg.enabled ?? true,
    as_buyer: cfg.as_buyer ?? true,
    as_seller: cfg.as_seller ?? true,
    disabled_symbols: new Set(cfg.disabled_symbols ?? []),
    buyer_boost: cfg.buyer_boost ?? 1.0,
    seller_boost: cfg.seller_boost ?? 1.0,
  };
}

function formatVolume(usd: number): string {
  if (usd <= 0) return '—';
  if (usd >= 1e9) return '$' + (usd / 1e9).toFixed(2) + 'B';
  if (usd >= 1e6) return '$' + (usd / 1e6).toFixed(2) + 'M';
  if (usd >= 1e3) return '$' + (usd / 1e3).toFixed(1) + 'K';
  return '$' + usd.toFixed(0);
}

function volumeColor(usd: number): string {
  if (usd <= 0) return 'text-slate-600';
  if (usd < 1_000) return 'text-red-400';        // dead
  if (usd < 10_000) return 'text-amber-400';     // very low
  if (usd < 100_000) return 'text-yellow-300';   // low
  if (usd < 1_000_000) return 'text-emerald-400'; // healthy
  return 'text-emerald-300';                     // strong
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

export default function FeeManagementTab({ feeConfigs, feeRealMode, feeStats, onSendMessage, onSendWithCallback }: FeeManagementTabProps) {
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

  // Volume-fetch state
  const [volumes, setVolumes] = useState<Record<string, Record<string, number>> | null>(null);
  const [volumesFetchedAt, setVolumesFetchedAt] = useState<number | null>(null);
  const [volumesLoading, setVolumesLoading] = useState(false);
  const [volumesError, setVolumesError] = useState<string | null>(null);
  const [expandedBlocklist, setExpandedBlocklist] = useState<Record<string, boolean>>({});

  const handleFetchVolumes = () => {
    if (!onSendWithCallback) {
      setVolumesError('Volume fetch not available — websocket callback missing.');
      return;
    }
    setVolumesLoading(true);
    setVolumesError(null);
    onSendWithCallback({ type: 'fetch_volumes' }, (data: unknown) => {
      setVolumesLoading(false);
      const d = data as { ok?: boolean; volumes?: Record<string, Record<string, number>>; error?: string; fetched_at?: number };
      if (d.ok && d.volumes) {
        setVolumes(d.volumes);
        setVolumesFetchedAt(d.fetched_at ?? Date.now() / 1000);
      } else {
        setVolumesError(d.error || 'Unknown error');
      }
    });
  };

  const toggleBlocklist = (exchange: string) => {
    setExpandedBlocklist(prev => ({ ...prev, [exchange]: !prev[exchange] }));
  };

  const toggleSymbolDisabled = (exchange: string, symbol: string) => {
    setDirty(true);
    setConfigs(prev => {
      const cur = prev[exchange];
      const next = new Set(cur.disabled_symbols);
      if (next.has(symbol)) next.delete(symbol); else next.add(symbol);
      return { ...prev, [exchange]: { ...cur, disabled_symbols: next } };
    });
  };

  const bulkDisableBelow = (exchange: string, threshold: number) => {
    const exVols = volumes?.[exchange] ?? {};
    setDirty(true);
    setConfigs(prev => {
      const cur = prev[exchange];
      const next = new Set(cur.disabled_symbols);
      for (const [sym, vol] of Object.entries(exVols)) {
        if (vol < threshold) next.add(sym);
      }
      return { ...prev, [exchange]: { ...cur, disabled_symbols: next } };
    });
  };

  const clearBlocklist = (exchange: string) => {
    setDirty(true);
    setConfigs(prev => ({
      ...prev,
      [exchange]: { ...prev[exchange], disabled_symbols: new Set() },
    }));
  };

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
        referrer_commission_pct: cfg.referrer_commission_pct,
        zero_fee_pairs: cfg.zero_fee_pairs.split(',').map(s => s.trim()).filter(Boolean),
        enabled: cfg.enabled,
        as_buyer: cfg.as_buyer,
        as_seller: cfg.as_seller,
        disabled_symbols: Array.from(cfg.disabled_symbols).sort(),
        buyer_boost: cfg.buyer_boost,
        seller_boost: cfg.seller_boost,
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

      {/* 24h Volume fetch banner — feeds the per-exchange symbol blocklist UI */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg px-4 py-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex-1 min-w-[200px]">
            <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">
              Per-Symbol Blocklist
            </h3>
            <p className="text-xs text-slate-500">
              Fetch live 24h USD volumes from each exchange, then disable individual symbols where the
              exchange has insufficient liquidity (e.g. LDO/HYPE on Bitfinex). Disabled symbols are
              skipped in pair selection but still trade on other enabled exchanges.
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <button
              onClick={handleFetchVolumes}
              disabled={volumesLoading || !onSendWithCallback}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-500 text-white rounded-lg text-xs font-medium transition-colors"
            >
              {volumesLoading ? 'Fetching…' : volumes ? 'Refresh 24h Volumes' : 'Fetch 24h Volumes'}
            </button>
            {volumesFetchedAt && (
              <span className="text-[10px] text-slate-500">
                Fetched {new Date(volumesFetchedAt * 1000).toLocaleTimeString()}
              </span>
            )}
            {volumesError && (
              <span className="text-[11px] text-red-400">{volumesError}</span>
            )}
          </div>
        </div>
      </div>

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

      {/* Referrer earnings stats */}
      {feeStats && feeStats.referrer_earnings_total > 0 && (
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-4">
          <h3 className="text-xs font-semibold text-purple-400 uppercase tracking-wider mb-1">
            Your Referrer Earnings
          </h3>
          <p className="text-xs text-slate-500 mb-2">Earned on your personal account (not included in bot P&L)</p>
          <div className="text-lg font-semibold text-purple-300 mb-2">
            ${feeStats.referrer_earnings_total.toFixed(2)}
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-5 gap-2 text-xs">
            {Object.entries(feeStats.referrer_earnings_per_exchange)
              .sort(([, a], [, b]) => b - a)
              .map(([ex, amount]) => (
                <div key={ex} className="bg-slate-700/50 rounded p-2">
                  <span className="text-slate-400">{ex}</span>
                  <p className="text-purple-300 font-mono">${amount.toFixed(4)}</p>
                  {amount >= 10 && (
                    <span className="text-amber-400 text-[10px]">Transfer to Bitfinex</span>
                  )}
                </div>
              ))}
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
                {cfg.enabled && !cfg.as_buyer && !cfg.as_seller && (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-400" title="No roles enabled — exchange present but unused">No roles</span>
                )}
                {cfg.enabled && cfg.as_buyer && !cfg.as_seller && (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-cyan-900/40 text-cyan-400">Buyer only</span>
                )}
                {cfg.enabled && !cfg.as_buyer && cfg.as_seller && (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-rose-900/40 text-rose-400">Seller only</span>
                )}
              </div>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-700 text-emerald-400">
                Effective: {(effective * 100).toFixed(4)}%
              </span>
            </div>

            {/* Per-role checkboxes — operator can pin a route by enabling
                only specific buyers/sellers. E.g. Bitfinex(buyer)+MEXC(seller)
                forces all trades through the cheapest pair. */}
            <div className="flex flex-wrap items-end gap-x-4 gap-y-2 mb-3">
              <div className="flex items-center gap-1.5">
                <label className={`flex items-center gap-1.5 text-xs cursor-pointer ${cfg.enabled ? 'text-slate-300' : 'text-slate-600'}`}>
                  <input type="checkbox" checked={cfg.as_buyer} disabled={!cfg.enabled}
                    onChange={e => updateField(exchange, 'as_buyer', e.target.checked)}
                    className="w-3.5 h-3.5 rounded border-slate-600 bg-slate-700 text-cyan-500 focus:ring-cyan-500" />
                  <span>Allow as Buyer</span>
                </label>
                <span className="text-[10px] text-slate-500">×</span>
                <input type="number" step="0.5" min="0" max="100"
                  value={cfg.buyer_boost} disabled={!cfg.enabled || !cfg.as_buyer}
                  onChange={e => updateField(exchange, 'buyer_boost', Number(e.target.value) || 1.0)}
                  title="Buyer boost multiplier (1.0 = neutral, 5.0 = strong preference)"
                  className={`w-16 text-xs text-right rounded px-1.5 py-0.5 ${cfg.buyer_boost !== 1.0 ? 'bg-cyan-900/40 border border-cyan-700 text-cyan-200' : 'bg-slate-700 border border-slate-600 text-slate-300'} disabled:opacity-50`} />
              </div>
              <div className="flex items-center gap-1.5">
                <label className={`flex items-center gap-1.5 text-xs cursor-pointer ${cfg.enabled ? 'text-slate-300' : 'text-slate-600'}`}>
                  <input type="checkbox" checked={cfg.as_seller} disabled={!cfg.enabled}
                    onChange={e => updateField(exchange, 'as_seller', e.target.checked)}
                    className="w-3.5 h-3.5 rounded border-slate-600 bg-slate-700 text-rose-500 focus:ring-rose-500" />
                  <span>Allow as Seller</span>
                </label>
                <span className="text-[10px] text-slate-500">×</span>
                <input type="number" step="0.5" min="0" max="100"
                  value={cfg.seller_boost} disabled={!cfg.enabled || !cfg.as_seller}
                  onChange={e => updateField(exchange, 'seller_boost', Number(e.target.value) || 1.0)}
                  title="Seller boost multiplier (1.0 = neutral, 5.0 = strong preference)"
                  className={`w-16 text-xs text-right rounded px-1.5 py-0.5 ${cfg.seller_boost !== 1.0 ? 'bg-rose-900/40 border border-rose-700 text-rose-200' : 'bg-slate-700 border border-slate-600 text-slate-300'} disabled:opacity-50`} />
              </div>
              <span className="text-[11px] text-slate-500 italic flex-1 min-w-[200px]">
                Boost ≥1× biases pair selection toward this role; non-preferred pairs need to beat preferred by ~boost× to win
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
                <div className="ml-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
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
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Your Commission (%)</label>
                    <input type="number" step="1" min="0" max="100"
                      value={(cfg.referrer_commission_pct * 100).toFixed(0)}
                      onChange={e => updateField(exchange, 'referrer_commission_pct', (Number(e.target.value) || 0) / 100)}
                      className={inputCls} />
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

            {/* Per-Symbol Blocklist */}
            <div className="border-t border-slate-700/50 pt-3 mt-3">
              <button
                onClick={() => toggleBlocklist(exchange)}
                className="w-full flex items-center justify-between text-xs text-slate-300 hover:text-white"
              >
                <span className="font-medium">
                  Symbol Blocklist
                  {cfg.disabled_symbols.size > 0 && (
                    <span className="ml-2 text-amber-400">
                      ({cfg.disabled_symbols.size} disabled)
                    </span>
                  )}
                </span>
                <span className="text-slate-500">{expandedBlocklist[exchange] ? '▾' : '▸'}</span>
              </button>

              {expandedBlocklist[exchange] && (() => {
                const exVols = volumes?.[exchange] ?? null;
                // Build sorted symbol list — union of (a) bot-tracked symbols
                // appearing in volumes, (b) currently-disabled symbols (in case
                // the exchange dropped them from its ticker), (c) zero-fee pairs.
                const symbolSet = new Set<string>();
                if (exVols) {
                  // Only include symbols that are also configured for the bot.
                  // (We use zero-fee pair list + volumes intersection as a heuristic.)
                  // Easier: include ALL symbols the exchange returns that end with USDT.
                  // For UX, sort by volume desc.
                  Object.keys(exVols).forEach(s => symbolSet.add(s));
                }
                cfg.disabled_symbols.forEach(s => symbolSet.add(s));
                const symbolList = Array.from(symbolSet);
                if (exVols) {
                  symbolList.sort((a, b) => (exVols[b] ?? 0) - (exVols[a] ?? 0));
                } else {
                  symbolList.sort();
                }

                return (
                  <div className="mt-3">
                    {!exVols && (
                      <p className="text-xs text-slate-500 italic mb-2">
                        Click "Fetch 24h Volumes" above to populate volume data.
                        {cfg.disabled_symbols.size > 0 && (
                          <span className="ml-1 text-amber-500">
                            Currently disabled: {Array.from(cfg.disabled_symbols).sort().join(', ')}
                          </span>
                        )}
                      </p>
                    )}
                    {exVols && (
                      <>
                        <div className="flex items-center gap-2 mb-2 text-[11px] flex-wrap">
                          <span className="text-slate-500">Quick disable below:</span>
                          <button onClick={() => bulkDisableBelow(exchange, 1_000)}
                            className="px-2 py-0.5 rounded bg-red-900/40 hover:bg-red-900/60 text-red-300">
                            &lt; $1K/24h
                          </button>
                          <button onClick={() => bulkDisableBelow(exchange, 10_000)}
                            className="px-2 py-0.5 rounded bg-amber-900/40 hover:bg-amber-900/60 text-amber-300">
                            &lt; $10K/24h
                          </button>
                          <button onClick={() => bulkDisableBelow(exchange, 100_000)}
                            className="px-2 py-0.5 rounded bg-yellow-900/40 hover:bg-yellow-900/60 text-yellow-300">
                            &lt; $100K/24h
                          </button>
                          <button onClick={() => clearBlocklist(exchange)}
                            className="px-2 py-0.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-300 ml-auto">
                            Clear all
                          </button>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-1 max-h-80 overflow-y-auto bg-slate-900/40 rounded p-2">
                          {symbolList.map(sym => {
                            const vol = exVols[sym] ?? 0;
                            const isDisabled = cfg.disabled_symbols.has(sym);
                            return (
                              <label key={sym}
                                className={`flex items-center gap-1.5 text-[11px] px-1.5 py-1 rounded cursor-pointer ${
                                  isDisabled ? 'bg-red-900/30 hover:bg-red-900/50' : 'hover:bg-slate-800'
                                }`}
                              >
                                <input type="checkbox" checked={!isDisabled}
                                  onChange={() => toggleSymbolDisabled(exchange, sym)}
                                  className="w-3 h-3 rounded border-slate-600 bg-slate-700 text-emerald-500 focus:ring-emerald-500" />
                                <span className={`font-mono ${isDisabled ? 'text-slate-500 line-through' : 'text-slate-200'}`}>
                                  {sym.replace('USDT', '')}
                                </span>
                                <span className={`ml-auto font-mono ${volumeColor(vol)}`}>
                                  {formatVolume(vol)}
                                </span>
                              </label>
                            );
                          })}
                          {symbolList.length === 0 && (
                            <span className="text-xs text-slate-500 col-span-full italic p-2">
                              No symbols returned for this exchange.
                            </span>
                          )}
                        </div>
                        <p className="text-[10px] text-slate-500 mt-1.5">
                          Checked = enabled · unchecked = blocked from this exchange · volumes are 24h USD turnover
                        </p>
                      </>
                    )}
                  </div>
                );
              })()}
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
