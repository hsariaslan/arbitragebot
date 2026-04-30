import { useState } from 'react';
import type { FundingRateInfo, SymbolRanking } from '../types';

const EX_SHORT: Record<string, string> = {
  Binance: 'BIN', OKX: 'OKX', Bybit: 'BYB', Bitget: 'BGT', KuCoin: 'KUC', MEXC: 'MEX', 'Gate.io': 'GAT',
};
function shortEx(name: string) { return EX_SHORT[name] ?? name.slice(0, 3).toUpperCase(); }

// Funding rate cell color: green = positive (short earns); amber = mild
// negative; red = severe negative (skip-hedge territory).
function fundingColor(annualizedShortPct: number, skip: boolean): string {
  if (skip) return 'text-red-400';
  if (annualizedShortPct >= 0) return 'text-emerald-400';
  if (annualizedShortPct >= -10) return 'text-slate-400';
  return 'text-amber-400';
}

interface SymbolRankingsProps {
  rankings: SymbolRanking[];
  warmupRemaining: number;
  autoRotate: boolean;
  discoveryMode?: boolean;
  fundingRates?: Record<string, FundingRateInfo>;
}

// Status pill colour classes by diagnostic.status
const statusPill: Record<string, string> = {
  active: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  candidate: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
  candidate_declining: 'bg-rose-500/20 text-rose-300 border-rose-500/30',
  candidate_warming_up: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  below_threshold: 'bg-slate-600/30 text-slate-400 border-slate-500/30',
  cooldown: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
};

const tierColor: Record<string, string> = {
  very_strong: 'text-emerald-400',
  strong: 'text-cyan-400',
  normal: 'text-slate-300',
  weak: 'text-slate-500',
};

const trajectoryIcon: Record<string, string> = {
  rising: '↗',
  stable: '→',
  declining: '↘',
  insufficient_data: '◌',
};

const trajectoryColor: Record<string, string> = {
  rising: 'text-emerald-400',
  stable: 'text-slate-300',
  declining: 'text-rose-400',
  insufficient_data: 'text-slate-500',
};

function SymbolDetailPopover({ r }: { r: SymbolRanking }) {
  const d = r.diagnostic;
  if (!d) return null;
  return (
    <div
      className="fixed bottom-4 right-4 z-50 w-80 max-w-[90vw] bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-xl shadow-2xl overflow-hidden pointer-events-none"
      style={{ animation: 'fadeIn 120ms ease-out' }}
    >
      {/* Header */}
      <div className="px-4 py-3 bg-gradient-to-r from-slate-800 to-slate-900 border-b border-slate-700/60">
        <div className="flex items-center justify-between">
          <div className="text-base font-semibold text-white">
            {r.symbol.replace('USDT', '')}
            <span className="text-slate-500 text-xs font-normal ml-1.5">USDT</span>
          </div>
          <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border ${statusPill[d.status] ?? statusPill.below_threshold}`}>
            {d.status.replace(/_/g, ' ')}
          </span>
        </div>
        <div className="flex items-center gap-3 mt-1.5 text-xs">
          <span className={`font-medium ${tierColor[d.tier] ?? 'text-slate-400'}`}>
            {d.tier.replace('_', ' ')}
          </span>
          <span className={`flex items-center gap-1 ${trajectoryColor[d.trajectory] ?? 'text-slate-400'}`}>
            <span className="text-base leading-none">{trajectoryIcon[d.trajectory] ?? '?'}</span>
            {d.trajectory.replace(/_/g, ' ')}
          </span>
          <span className="text-slate-500 ml-auto">
            rank #{r.rank}
          </span>
        </div>
      </div>

      {/* Reasons */}
      <div className="px-4 py-3 space-y-1.5">
        {d.reasons.map((reason, i) => (
          <div key={i} className="text-xs text-slate-300 flex items-start gap-2">
            <span className="text-slate-500 mt-0.5">•</span>
            <span className="flex-1 leading-relaxed">{reason}</span>
          </div>
        ))}
      </div>

      {/* Score breakdown */}
      <div className="px-4 py-2.5 bg-slate-800/50 border-t border-slate-700/60 space-y-1">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-slate-500 uppercase tracking-wider">Score</span>
          <span className="font-mono text-cyan-400 font-semibold">{r.score.toFixed(4)}</span>
        </div>
        <div className="text-[10px] text-slate-400 font-mono leading-relaxed">{d.score_formula}</div>
      </div>

      {/* Threshold breakdown */}
      <div className="px-4 py-2.5 bg-slate-800/30 border-t border-slate-700/60 space-y-1">
        <div className="text-[11px] text-slate-500 uppercase tracking-wider">Activation Threshold</div>
        <div className="text-[10px] text-slate-400 font-mono leading-relaxed">{d.threshold_breakdown}</div>
      </div>

      {/* Watchlist info */}
      {d.watchlist && d.watchlist.entered_seconds_ago != null && (
        <div className="px-4 py-2.5 bg-slate-800/30 border-t border-slate-700/60">
          <div className="text-[11px] text-slate-500 uppercase tracking-wider mb-1">Watchlist</div>
          <div className="grid grid-cols-2 gap-1 text-[11px]">
            <div className="text-slate-400">Watched: <span className="text-slate-200 font-mono">{d.watchlist.entered_seconds_ago}s</span></div>
            <div className="text-slate-400">Samples: <span className="text-slate-200 font-mono">{d.watchlist.samples ?? 0}</span></div>
            <div className="text-slate-400">Peak: <span className="text-slate-200 font-mono">{(d.watchlist.peak_score ?? 0).toFixed(4)}</span></div>
            <div className="text-slate-400">Confirmed: <span className={d.watchlist.confirmed ? 'text-emerald-400' : 'text-slate-500'}>{d.watchlist.confirmed ? 'yes' : 'no'}</span></div>
          </div>
        </div>
      )}

      {/* Exchange view (compact) */}
      {r.exchange_view && (r.exchange_view.buyers.length > 0 || r.exchange_view.sellers.length > 0) && (
        <div className="px-4 py-2.5 bg-slate-800/30 border-t border-slate-700/60 space-y-1.5">
          <div className="text-[11px] text-slate-500 uppercase tracking-wider">Exchange Order</div>
          <div className="text-[11px] font-mono">
            <span className="text-slate-500">Buyers: </span>
            {r.exchange_view.buyers.length === 0 ? <span className="text-slate-600">—</span> : r.exchange_view.buyers.map((b, i) => (
              <span key={`pb-${b.exchange}`} className={b.blocked ? 'text-rose-500/80 line-through' : i === 0 ? 'text-cyan-300 font-semibold' : 'text-cyan-500/80'}>
                {i > 0 && <span className="text-slate-600">,</span>}{b.exchange.slice(0, 3).toUpperCase()}
              </span>
            ))}
          </div>
          <div className="text-[11px] font-mono">
            <span className="text-slate-500">Sellers: </span>
            {r.exchange_view.sellers.length === 0 ? <span className="text-slate-600">—</span> : r.exchange_view.sellers.map((s, i) => (
              <span key={`ps-${s.exchange}`} className={s.blocked ? 'text-rose-500/80 line-through' : i === 0 ? 'text-fuchsia-300 font-semibold' : 'text-fuchsia-500/80'}>
                {i > 0 && <span className="text-slate-600">,</span>}{s.exchange.slice(0, 3).toUpperCase()}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function SymbolRankings({ rankings, warmupRemaining, autoRotate, discoveryMode, fundingRates }: SymbolRankingsProps) {
  const [hoveredSymbol, setHoveredSymbol] = useState<string | null>(null);
  const hoveredRanking = hoveredSymbol ? rankings.find(r => r.symbol === hoveredSymbol) : null;

  if (rankings.length === 0) {
    return (
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Symbol Rankings</h2>
        <p className="text-slate-500 text-sm">Waiting for scoring data...</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
          Symbol Rankings
          {discoveryMode && <span className="text-amber-400 font-normal ml-2">(Discovery)</span>}
          {!discoveryMode && !autoRotate && <span className="text-slate-500 font-normal ml-2">(auto-rotate off)</span>}
        </h2>
        {!discoveryMode && warmupRemaining > 0 && (
          <span className="text-xs text-amber-400 bg-amber-400/10 px-2 py-1 rounded">
            Warmup: {warmupRemaining}s remaining
          </span>
        )}
      </div>

      <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-800">
            <tr className="text-slate-400 text-xs uppercase">
              <th className="text-left px-2 py-1.5 font-medium">#</th>
              <th className="text-left px-2 py-1.5 font-medium">Symbol</th>
              <th className="text-right px-2 py-1.5 font-medium">Score</th>
              <th className="text-right px-2 py-1.5 font-medium">Freq%</th>
              <th className="text-right px-2 py-1.5 font-medium">Avg Net%</th>
              <th className="text-right px-2 py-1.5 font-medium">Cur Net%</th>
              <th className="text-right px-2 py-1.5 font-medium">Best%</th>
              <th className="text-right px-2 py-1.5 font-medium">Est $/hr</th>
              <th className="text-right px-2 py-1.5 font-medium">Trade $</th>
              <th className="text-right px-2 py-1.5 font-medium" title="Funding rate annualized for SHORT position. Positive = short receives; negative = short pays.">Fund%/yr</th>
              <th className="text-center px-2 py-1.5 font-medium">Exchanges</th>
              <th className="text-center px-2 py-1.5 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {rankings.map((r) => {
              const isActive = r.is_active;
              const isCandidate = !isActive && r.score > 0 && r.rank <= 5;
              const rowClass = isActive
                ? 'bg-emerald-500/10'
                : isCandidate
                  ? 'bg-amber-500/5'
                  : '';

              return (
                <tr
                  key={r.symbol}
                  className={`border-t border-slate-700/30 cursor-help transition-colors hover:bg-slate-700/30 ${rowClass}`}
                  onMouseEnter={() => setHoveredSymbol(r.symbol)}
                  onMouseLeave={() => setHoveredSymbol(prev => prev === r.symbol ? null : prev)}
                >
                  <td className="px-2 py-1.5 text-slate-500 font-mono">{r.rank}</td>
                  <td className={`px-2 py-1.5 font-medium ${isActive ? 'text-emerald-300' : 'text-white'}`}>
                    {r.symbol.replace('USDT', '')}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-300">
                    {r.score > 0 ? r.score.toFixed(4) : '—'}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-300">
                    {r.total_ticks > 0 ? (r.frequency * 100).toFixed(1) + '%' : '—'}
                  </td>
                  <td className={`px-2 py-1.5 text-right font-mono ${r.avg_net_pct > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                    {r.total_ticks > 0 ? r.avg_net_pct.toFixed(4) + '%' : '—'}
                  </td>
                  <td className={`px-2 py-1.5 text-right font-mono ${r.current_net_pct > 0 ? 'text-emerald-400' : r.current_net_pct < 0 ? 'text-red-400' : 'text-slate-500'}`}>
                    {r.total_ticks > 0 ? r.current_net_pct.toFixed(4) + '%' : '—'}
                  </td>
                  <td className={`px-2 py-1.5 text-right font-mono ${r.best_net_pct > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                    {r.total_ticks > 0 ? r.best_net_pct.toFixed(4) + '%' : '—'}
                  </td>
                  <td className={`px-2 py-1.5 text-right font-mono ${r.est_hourly_profit > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                    {r.est_hourly_profit > 0 ? '$' + r.est_hourly_profit.toFixed(4) : '—'}
                  </td>
                  <td className={`px-2 py-1.5 text-right font-mono ${isActive ? r.trade_multiplier >= 1 ? 'text-emerald-400' : 'text-amber-400' : 'text-slate-600'}`}>
                    {isActive ? '$' + r.allocated_trade_size.toFixed(0) : '—'}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono">
                    {(() => {
                      const fr = fundingRates?.[r.symbol];
                      if (!fr) return <span className="text-slate-600">—</span>;
                      const ann = fr.annualized_short_pct;
                      const cls = fundingColor(ann, fr.skip);
                      const label = `${ann >= 0 ? '+' : ''}${ann.toFixed(1)}%`;
                      const tooltip = `${fr.rate_pct >= 0 ? '+' : ''}${fr.rate_pct.toFixed(4)}% per ${fr.interval_hours}h${fr.skip ? ' (SKIP threshold)' : ''}`;
                      return <span className={cls} title={tooltip}>{label}{fr.skip && ' ⚠'}</span>;
                    })()}
                  </td>
                  <td className="px-2 py-1.5 text-center font-mono text-xs whitespace-nowrap">
                    {r.exchange_view && (r.exchange_view.buyers.length > 0 || r.exchange_view.sellers.length > 0) ? (
                      <span>
                        {r.exchange_view.buyers.length === 0 ? <span className="text-slate-600">—</span> : r.exchange_view.buyers.map((b, idx) => (
                          <span
                            key={`b-${b.exchange}`}
                            className={
                              b.blocked
                                ? 'text-rose-500/70 line-through'
                                : idx === 0
                                  ? 'text-cyan-300 font-semibold'
                                  : 'text-cyan-500/70'
                            }
                            title={`${b.exchange} weight=${b.weight.toFixed(3)}${b.blocked ? ' (BLOCKED)' : ''}`}
                          >
                            {idx > 0 && <span className="text-slate-600">,</span>}
                            {shortEx(b.exchange)}
                          </span>
                        ))}
                        <span className="text-slate-500 mx-1">→</span>
                        {r.exchange_view.sellers.length === 0 ? <span className="text-slate-600">—</span> : r.exchange_view.sellers.map((s, idx) => (
                          <span
                            key={`s-${s.exchange}`}
                            className={
                              s.blocked
                                ? 'text-rose-500/70 line-through'
                                : idx === 0
                                  ? 'text-fuchsia-300 font-semibold'
                                  : 'text-fuchsia-500/70'
                            }
                            title={`${s.exchange} weight=${s.weight.toFixed(3)}${s.blocked ? ' (BLOCKED)' : ''}`}
                          >
                            {idx > 0 && <span className="text-slate-600">,</span>}
                            {shortEx(s.exchange)}
                          </span>
                        ))}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-2 py-1.5 text-center">
                    {isActive ? (
                      <span className="text-xs bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded">ACTIVE</span>
                    ) : r.cooldown_remaining > 0 ? (
                      <span className="text-xs bg-red-500/20 text-red-300 px-1.5 py-0.5 rounded">
                        CD {Math.ceil(r.cooldown_remaining / 60)}m
                      </span>
                    ) : isCandidate ? (
                      <span className="text-xs bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded">candidate</span>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {hoveredRanking && <SymbolDetailPopover r={hoveredRanking} />}
    </div>
  );
}
