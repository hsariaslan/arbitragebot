import { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import type { ConfigSnapshot, DemoDiscrepancy, ExchangeFeeConfig, ExchangeTransferConfig, OptimizerState, ProfitStats, WatchlistEntry, Portfolio, Simulation, Trade, Transfer } from '../types';
import { exportXlsx } from '../utils/exportXlsx';
import { exportRankingsMarkdown } from '../utils/exportMarkdown';
import PerformanceCharts from './PerformanceCharts';

interface RankingPageProps {
  optimizer: OptimizerState;
  tickCount: number;
  portfolio?: Portfolio | null;
  simulation?: Simulation | null;
  allTrades?: Trade[];
  allTransfers?: Transfer[];
  allConfigHistory?: ConfigSnapshot[];
  demoDiscrepancies?: DemoDiscrepancy[];
  feeConfigs?: Record<string, ExchangeFeeConfig>;
  transferConfigs?: Record<string, ExchangeTransferConfig>;
  profitStats?: ProfitStats | null;
  defaultView?: 'rolling' | 'historical';
}

function ProfitBar({ value, maxValue }: { value: number; maxValue: number }) {
  const width = maxValue > 0 ? Math.min(100, (value / maxValue) * 100) : 0;
  const color = value > 0 ? 'bg-emerald-500/40' : 'bg-red-500/20';
  return (
    <div className="w-20 h-3 bg-slate-700 rounded-sm overflow-hidden inline-block ml-2 align-middle">
      <div className={`h-full ${color} rounded-sm`} style={{ width: `${width}%` }} />
    </div>
  );
}

function FrequencyDot({ frequency }: { frequency: number }) {
  const pct = frequency * 100;
  const color = pct >= 50 ? 'bg-emerald-400' : pct >= 20 ? 'bg-amber-400' : pct >= 5 ? 'bg-orange-400' : 'bg-red-400';
  return <div className={`w-2.5 h-2.5 rounded-full ${color} inline-block`} title={`${pct.toFixed(1)}%`} />;
}

function HBarRow({ label, value, maxValue, color, suffix = '' }: {
  label: string; value: number; maxValue: number; color: string; suffix?: string;
}) {
  const barWidth = maxValue > 0 ? Math.min(100, Math.abs(value) / maxValue * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 text-right text-xs font-mono text-slate-300 truncate">{label}</span>
      <div className="flex-1 h-4 bg-slate-700/50 rounded-sm overflow-hidden relative">
        <div className={`h-full rounded-sm ${color}`} style={{ width: `${barWidth}%` }} />
        <span className="absolute inset-0 flex items-center px-2 text-[10px] font-mono text-white/80">
          {value > 0 ? value.toFixed(4) : value === 0 ? '0' : value.toFixed(4)}{suffix}
        </span>
      </div>
    </div>
  );
}

function TrendArrow({ trend }: { trend: number }) {
  if (Math.abs(trend) < 0.000001) return <span className="text-slate-500">—</span>;
  if (trend > 0) return <span className="text-emerald-400">▲</span>;
  return <span className="text-red-400">▼</span>;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

// ── Tier helpers ──
const tier1 = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT', 'DOGEUSDT', 'ADAUSDT'];
const tier2 = ['AVAXUSDT', 'LINKUSDT', 'POLUSDT', 'DOTUSDT', 'NEARUSDT', 'SUIUSDT', 'APTUSDT', 'TRXUSDT'];
const tier3 = ['ARBUSDT', 'OPUSDT', 'FILUSDT', 'ATOMUSDT', 'INJUSDT'];
const getTier = (sym: string) => tier1.includes(sym) ? 1 : tier2.includes(sym) ? 2 : tier3.includes(sym) ? 3 : 4;
const tierColors = ['', 'text-yellow-300', 'text-blue-300', 'text-orange-300', 'text-slate-400'];

// ── WatchlistCard ──
function WatchlistCard({ watchlist }: { watchlist: WatchlistEntry[] }) {
  if (!watchlist || watchlist.length === 0) return null;
  return (
    <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
      <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
        Watchlist — Candidates Being Tracked
      </h3>
      <div className="space-y-2">
        {watchlist.map((w) => (
          <div key={w.symbol} className="flex items-center gap-3">
            <span className={`w-20 text-right text-sm font-medium ${w.confirmed ? 'text-emerald-300' : 'text-amber-300'}`}>
              {w.symbol.replace('USDT', '')}
            </span>
            <div className="flex-1 h-4 bg-slate-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${w.confirmed ? 'bg-emerald-500/60' : 'bg-amber-500/40'}`}
                style={{ width: `${w.progress}%` }}
              />
            </div>
            <span className="text-xs font-mono text-slate-400 w-12 text-right">{w.progress.toFixed(0)}%</span>
            <span className={`text-xs px-1.5 py-0.5 rounded ${w.confirmed ? 'bg-emerald-500/20 text-emerald-300' : 'bg-amber-500/10 text-amber-400'}`}>
              {w.confirmed ? 'CONFIRMED' : 'watching'}
            </span>
            <span className="text-xs font-mono text-slate-500">{formatDuration(w.elapsed)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Rolling View (existing)
// ══════════════════════════════════════════════════════════════════════════════

function RollingView({ optimizer }: { optimizer: OptimizerState }) {
  const { rankings, exchange_rankings, pair_rankings, watchlist } = optimizer;
  const windowMinutes = Math.round(optimizer.scoring_window / 60);

  const maxScore = Math.max(...rankings.map(r => r.score), 0.001);
  const maxFreq = Math.max(...rankings.map(r => r.frequency), 0.01);
  const maxExProfit = Math.max(...(exchange_rankings || []).map(e => e.profit_sum), 0.001);
  const maxAvgNet = Math.max(...rankings.map(r => Math.abs(r.avg_net_pct)), 0.0001);
  const maxEstHourly = Math.max(...rankings.map(r => r.est_hourly_profit), 0.0001);

  const profitable = rankings.filter(r => r.score > 0);
  const unprofitable = rankings.filter(r => r.score <= 0 && r.total_ticks > 0);
  const noData = rankings.filter(r => r.total_ticks === 0);

  const tierStats = [1, 2, 3, 4].map(tier => {
    const symbols = rankings.filter(r => getTier(r.symbol) === tier && r.total_ticks > 0);
    const profitableCount = symbols.filter(s => s.score > 0).length;
    const avgScore = symbols.length > 0 ? symbols.reduce((s, r) => s + r.score, 0) / symbols.length : 0;
    const avgFreq = symbols.length > 0 ? symbols.reduce((s, r) => s + r.frequency, 0) / symbols.length : 0;
    const totalEst = symbols.reduce((s, r) => s + r.est_hourly_profit, 0);
    return { tier, total: symbols.length, profitable: profitableCount, avgScore, avgFreq, totalEst };
  });

  const worstByNet = [...rankings].filter(r => r.total_ticks > 0).sort((a, b) => a.avg_net_pct - b.avg_net_pct).slice(0, 10);
  const bestByFreq = [...rankings].filter(r => r.total_ticks > 0 && r.frequency > 0).sort((a, b) => b.frequency - a.frequency).slice(0, 10);
  const bestByHourly = [...rankings].filter(r => r.est_hourly_profit > 0).sort((a, b) => b.est_hourly_profit - a.est_hourly_profit).slice(0, 10);

  return (
    <div className="space-y-5">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-emerald-400">{profitable.length}</div>
          <div className="text-xs text-slate-400 mt-1">Profitable</div>
        </div>
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-red-400">{unprofitable.length}</div>
          <div className="text-xs text-slate-400 mt-1">Unprofitable</div>
        </div>
        <div className="bg-slate-700/50 border border-slate-600/30 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-slate-400">{noData.length}</div>
          <div className="text-xs text-slate-400 mt-1">No Data</div>
        </div>
        <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-blue-400">
            {profitable.length > 0
              ? (profitable.reduce((s, r) => s + r.frequency, 0) / profitable.length * 100).toFixed(1) + '%'
              : '—'}
          </div>
          <div className="text-xs text-slate-400 mt-1">Avg Freq (profitable)</div>
        </div>
        <div className="bg-cyan-500/10 border border-cyan-500/20 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-cyan-400">
            {profitable.length > 0 ? '$' + profitable.reduce((s, r) => s + r.est_hourly_profit, 0).toFixed(4) : '—'}
          </div>
          <div className="text-xs text-slate-400 mt-1">Total Est $/hr</div>
        </div>
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-purple-400">
            {profitable.length > 0
              ? (profitable.reduce((s, r) => s + r.avg_profitable_net, 0) / profitable.length).toFixed(4) + '%'
              : '—'}
          </div>
          <div className="text-xs text-slate-400 mt-1">Avg Profitable Spread</div>
        </div>
      </div>

      {/* Watchlist */}
      <WatchlistCard watchlist={watchlist} />

      {/* Full Symbol Rankings Table */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
          All Symbols — Rolling {windowMinutes}min Window
        </h3>
        <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead className="sticky top-0 bg-slate-800 z-10">
              <tr className="text-slate-400 text-xs uppercase">
                <th className="text-left px-2 py-2 font-medium">#</th>
                <th className="text-left px-2 py-2 font-medium">Symbol</th>
                <th className="text-center px-2 py-2 font-medium">Tier</th>
                <th className="text-right px-2 py-2 font-medium">Score</th>
                <th className="text-center px-2 py-2 font-medium">Freq</th>
                <th className="text-right px-2 py-2 font-medium">Freq%</th>
                <th className="text-right px-2 py-2 font-medium">Avg Prof. Net%</th>
                <th className="text-right px-2 py-2 font-medium">Avg Net%</th>
                <th className="text-right px-2 py-2 font-medium">Best%</th>
                <th className="text-right px-2 py-2 font-medium">Prof. Ticks</th>
                <th className="text-right px-2 py-2 font-medium">Total Ticks</th>
                <th className="text-right px-2 py-2 font-medium">Est $/hr</th>
                <th className="text-right px-2 py-2 font-medium">Mult</th>
                <th className="text-right px-2 py-2 font-medium">Trade $</th>
                <th className="text-center px-2 py-2 font-medium">Status</th>
                <th className="text-left px-2 py-2 font-medium">Score Distribution</th>
              </tr>
            </thead>
            <tbody>
              {rankings.map((r, i) => {
                const isActive = r.is_active;
                const tier = getTier(r.symbol);
                const rowBg = isActive ? 'bg-emerald-500/10' : r.score > 0 ? '' : r.total_ticks > 0 ? 'bg-red-500/5' : 'bg-slate-900/30';
                return (
                  <tr key={r.symbol} className={`border-t border-slate-700/30 ${rowBg}`}>
                    <td className="px-2 py-1.5 text-slate-500 font-mono">{i + 1}</td>
                    <td className={`px-2 py-1.5 font-medium ${isActive ? 'text-emerald-300' : r.score > 0 ? 'text-white' : 'text-slate-500'}`}>
                      {r.symbol.replace('USDT', '')}
                    </td>
                    <td className={`px-2 py-1.5 text-center text-xs font-mono ${tierColors[tier]}`}>T{tier}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-300">
                      {r.score > 0 ? r.score.toFixed(4) : r.total_ticks > 0 ? '0' : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      {r.total_ticks > 0 ? <FrequencyDot frequency={r.frequency} /> : null}
                    </td>
                    <td className={`px-2 py-1.5 text-right font-mono ${r.frequency > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {r.total_ticks > 0 ? (r.frequency * 100).toFixed(1) + '%' : '—'}
                    </td>
                    <td className={`px-2 py-1.5 text-right font-mono ${r.avg_profitable_net > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {r.avg_profitable_net > 0 ? r.avg_profitable_net.toFixed(4) + '%' : '—'}
                    </td>
                    <td className={`px-2 py-1.5 text-right font-mono ${r.avg_net_pct > 0 ? 'text-emerald-400' : 'text-red-400/60'}`}>
                      {r.total_ticks > 0 ? r.avg_net_pct.toFixed(4) + '%' : '—'}
                    </td>
                    <td className={`px-2 py-1.5 text-right font-mono ${r.best_net_pct > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {r.total_ticks > 0 ? r.best_net_pct.toFixed(4) + '%' : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-400">
                      {r.profitable_ticks > 0 ? r.profitable_ticks : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-500">
                      {r.total_ticks > 0 ? r.total_ticks : '—'}
                    </td>
                    <td className={`px-2 py-1.5 text-right font-mono ${r.est_hourly_profit > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {r.est_hourly_profit > 0 ? '$' + r.est_hourly_profit.toFixed(4) : '—'}
                    </td>
                    <td className={`px-2 py-1.5 text-right font-mono ${isActive ? r.trade_multiplier >= 1 ? 'text-emerald-400' : 'text-amber-400' : 'text-slate-600'}`}>
                      {isActive ? r.trade_multiplier.toFixed(2) + '×' : '—'}
                    </td>
                    <td className={`px-2 py-1.5 text-right font-mono ${isActive ? r.trade_multiplier >= 1 ? 'text-emerald-400' : 'text-amber-400' : 'text-slate-600'}`}>
                      {isActive ? '$' + r.allocated_trade_size.toFixed(0) : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      {isActive ? (
                        <span className="text-xs bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded">ACTIVE</span>
                      ) : r.cooldown_remaining > 0 ? (
                        <span className="text-xs bg-red-500/20 text-red-300 px-1.5 py-0.5 rounded">
                          CD {Math.ceil(r.cooldown_remaining / 60)}m
                        </span>
                      ) : r.score > 0 ? (
                        <span className="text-xs bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded">candidate</span>
                      ) : r.total_ticks > 0 ? (
                        <span className="text-xs bg-red-500/10 text-red-400/60 px-1.5 py-0.5 rounded">avoid</span>
                      ) : null}
                    </td>
                    <td className="px-2 py-1.5">
                      <ProfitBar value={r.score} maxValue={maxScore} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 sm:gap-5">
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Top 10 by Score</h3>
          {profitable.length > 0 ? (
            <div className="space-y-1.5">
              {profitable.slice(0, 10).map((r) => (
                <HBarRow key={r.symbol} label={r.symbol.replace('USDT', '')} value={r.score} maxValue={maxScore}
                  color={r.is_active ? 'bg-emerald-500/50' : 'bg-blue-500/40'} />
              ))}
            </div>
          ) : <p className="text-slate-500 text-sm">No profitable symbols yet</p>}
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Top 10 by Frequency</h3>
          {bestByFreq.length > 0 ? (
            <div className="space-y-1.5">
              {bestByFreq.slice(0, 10).map((r) => (
                <HBarRow key={r.symbol} label={r.symbol.replace('USDT', '')} value={r.frequency * 100} maxValue={maxFreq * 100}
                  color={r.is_active ? 'bg-emerald-500/50' : 'bg-cyan-500/40'} suffix="%" />
              ))}
            </div>
          ) : <p className="text-slate-500 text-sm">No data yet</p>}
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Top 10 by Est $/hr</h3>
          {bestByHourly.length > 0 ? (
            <div className="space-y-1.5">
              {bestByHourly.slice(0, 10).map((r) => (
                <HBarRow key={r.symbol} label={r.symbol.replace('USDT', '')} value={r.est_hourly_profit} maxValue={maxEstHourly}
                  color={r.is_active ? 'bg-emerald-500/50' : 'bg-purple-500/40'} suffix="$/hr" />
              ))}
            </div>
          ) : <p className="text-slate-500 text-sm">No profitable symbols yet</p>}
        </div>
      </div>

      {/* Worst + Heatmap */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 sm:gap-5">
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Worst 10 by Avg Net% (Avoid)</h3>
          {worstByNet.length > 0 ? (
            <div className="space-y-1.5">
              {worstByNet.map((r) => (
                <HBarRow key={r.symbol} label={r.symbol.replace('USDT', '')} value={r.avg_net_pct} maxValue={maxAvgNet} color="bg-red-500/40" suffix="%" />
              ))}
            </div>
          ) : <p className="text-slate-500 text-sm">No data yet</p>}
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Frequency Heatmap</h3>
          <div className="flex flex-wrap gap-1">
            {rankings.filter(r => r.total_ticks > 0).map((r) => {
              const pct = r.frequency * 100;
              const bg = pct >= 50 ? 'bg-emerald-500' : pct >= 30 ? 'bg-emerald-600/80' : pct >= 15 ? 'bg-amber-500/70' : pct >= 5 ? 'bg-orange-500/60' : 'bg-red-500/40';
              return (
                <div key={r.symbol} className={`${bg} rounded px-1.5 py-0.5 text-[9px] font-mono text-white/90 cursor-default`}
                  title={`${r.symbol}: ${pct.toFixed(1)}% freq, score ${r.score.toFixed(4)}`}>
                  {r.symbol.replace('USDT', '')} {pct.toFixed(0)}%
                </div>
              );
            })}
          </div>
          <div className="flex items-center gap-3 mt-3 text-[10px] text-slate-500">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-emerald-500" /> 50%+</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-emerald-600/80" /> 30-50%</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-amber-500/70" /> 15-30%</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-orange-500/60" /> 5-15%</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-500/40" /> &lt;5%</span>
          </div>
        </div>
      </div>

      {/* Tier Analysis */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Performance by Tier</h3>
        <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[650px]">
          <thead>
            <tr className="text-slate-400 text-xs uppercase">
              <th className="text-left px-3 py-2 font-medium">Tier</th>
              <th className="text-right px-3 py-2 font-medium">Symbols</th>
              <th className="text-right px-3 py-2 font-medium">Profitable</th>
              <th className="text-right px-3 py-2 font-medium">% Profitable</th>
              <th className="text-right px-3 py-2 font-medium">Avg Score</th>
              <th className="text-right px-3 py-2 font-medium">Avg Freq%</th>
              <th className="text-right px-3 py-2 font-medium">Total Est $/hr</th>
              <th className="text-left px-3 py-2 font-medium">Distribution</th>
            </tr>
          </thead>
          <tbody>
            {tierStats.map((ts) => {
              const tierLabels = ['', 'T1 Majors', 'T2 Strong', 'T3 Volatile', 'T4 Others'];
              const pctProfitable = ts.total > 0 ? (ts.profitable / ts.total * 100) : 0;
              return (
                <tr key={ts.tier} className="border-t border-slate-700/30">
                  <td className={`px-3 py-2 font-medium ${tierColors[ts.tier]}`}>{tierLabels[ts.tier]}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-300">{ts.total}</td>
                  <td className="px-3 py-2 text-right font-mono text-emerald-400">{ts.profitable}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-300">{ts.total > 0 ? pctProfitable.toFixed(0) + '%' : '—'}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-300">{ts.avgScore > 0 ? ts.avgScore.toFixed(4) : '0'}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-300">{ts.total > 0 ? (ts.avgFreq * 100).toFixed(1) + '%' : '—'}</td>
                  <td className={`px-3 py-2 text-right font-mono ${ts.totalEst > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                    {ts.totalEst > 0 ? '$' + ts.totalEst.toFixed(4) : '—'}
                  </td>
                  <td className="px-3 py-2">
                    <div className="w-24 h-3 bg-slate-700 rounded-sm overflow-hidden flex">
                      <div className="h-full bg-emerald-500/50" style={{ width: `${pctProfitable}%` }} />
                      <div className="h-full bg-red-500/30" style={{ width: `${100 - pctProfitable}%` }} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      </div>

      {/* Exchange + Pair Rankings */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 sm:gap-5">
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Exchange Rankings</h3>
          {exchange_rankings && exchange_rankings.length > 0 ? (
            <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[500px]">
              <thead>
                <tr className="text-slate-400 text-xs uppercase">
                  <th className="text-left px-2 py-2 font-medium">Exchange</th>
                  <th className="text-right px-2 py-2 font-medium">Fee%</th>
                  <th className="text-right px-2 py-2 font-medium">Buy</th>
                  <th className="text-right px-2 py-2 font-medium">Sell</th>
                  <th className="text-right px-2 py-2 font-medium">Total</th>
                  <th className="text-right px-2 py-2 font-medium">Profit</th>
                  <th className="text-left px-2 py-2 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {exchange_rankings.map((ex) => (
                  <tr key={ex.exchange} className="border-t border-slate-700/30">
                    <td className="px-2 py-1.5 font-medium text-white">{ex.exchange}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-400">{ex.fee_pct}%</td>
                    <td className="px-2 py-1.5 text-right font-mono text-cyan-400">{ex.as_buyer}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-amber-400">{ex.as_seller}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-300">{ex.total_involvement}</td>
                    <td className={`px-2 py-1.5 text-right font-mono ${ex.profit_sum > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {ex.profit_sum > 0 ? ex.profit_sum.toFixed(2) : '0'}
                    </td>
                    <td className="px-2 py-1.5"><ProfitBar value={ex.profit_sum} maxValue={maxExProfit} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          ) : <p className="text-slate-500 text-sm">Waiting for scoring data...</p>}
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Best Exchange Pairs (Buy @ → Sell @)</h3>
          {pair_rankings && pair_rankings.length > 0 ? (
            <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[400px]">
              <thead>
                <tr className="text-slate-400 text-xs uppercase">
                  <th className="text-left px-2 py-2 font-medium">#</th>
                  <th className="text-left px-2 py-2 font-medium">Buy @</th>
                  <th className="text-left px-2 py-2 font-medium">Sell @</th>
                  <th className="text-right px-2 py-2 font-medium">Ticks</th>
                  <th className="text-right px-2 py-2 font-medium">Profit</th>
                </tr>
              </thead>
              <tbody>
                {pair_rankings.map((p, i) => (
                  <tr key={`${p.buy_exchange}-${p.sell_exchange}`} className="border-t border-slate-700/30">
                    <td className="px-2 py-1.5 text-slate-500 font-mono">{i + 1}</td>
                    <td className="px-2 py-1.5 font-medium text-cyan-300">{p.buy_exchange}</td>
                    <td className="px-2 py-1.5 font-medium text-amber-300">{p.sell_exchange}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-300">{p.trades}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-emerald-400">{p.profit_sum.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          ) : <p className="text-slate-500 text-sm">Waiting for scoring data...</p>}
        </div>
      </div>

      {/* Buy/Sell Role Distribution */}
      {exchange_rankings && exchange_rankings.length > 0 && (
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Exchange Buy/Sell Role Distribution</h3>
          <div className="space-y-2">
            {exchange_rankings.map((ex) => {
              const total = ex.as_buyer + ex.as_seller;
              const buyPct = total > 0 ? (ex.as_buyer / total * 100) : 50;
              return (
                <div key={ex.exchange} className="flex items-center gap-3">
                  <span className="w-20 text-right text-xs font-medium text-slate-300">{ex.exchange}</span>
                  <div className="flex-1 h-5 bg-slate-700/50 rounded-sm overflow-hidden flex relative">
                    <div className="h-full bg-cyan-500/50" style={{ width: `${buyPct}%` }} />
                    <div className="h-full bg-amber-500/50" style={{ width: `${100 - buyPct}%` }} />
                    <span className="absolute inset-0 flex items-center justify-center text-[10px] font-mono text-white/80">
                      {total > 0 ? `Buy ${buyPct.toFixed(0)}% | Sell ${(100 - buyPct).toFixed(0)}%` : 'No data'}
                    </span>
                  </div>
                  <span className="w-16 text-right text-xs font-mono text-slate-500">{total} ticks</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Historical View (NEW)
// ══════════════════════════════════════════════════════════════════════════════

function HistoricalView({ optimizer }: { optimizer: OptimizerState }) {
  const { historical_rankings: hist, historical_exchange_rankings: histEx } = optimizer;
  const sessionStart = optimizer.session_start || 0;
  const sessionDuration = sessionStart > 0 ? Date.now() / 1000 - sessionStart : 0;

  if (!hist || hist.length === 0) {
    return (
      <div className="bg-slate-800/50 rounded-lg p-8 text-center">
        <p className="text-slate-400 text-lg">No historical data yet</p>
        <p className="text-slate-500 text-sm mt-2">Historical stats accumulate over the entire session</p>
      </div>
    );
  }

  const totalTicks = hist.reduce((s, h) => s + h.total_ticks, 0);
  const profitable = hist.filter(h => h.all_time_score > 0);
  const bestSymbol = hist.length > 0 ? hist.reduce((a, b) => a.est_total_profit > b.est_total_profit ? a : b) : null;
  const mostConsistent = hist.length > 0 ? hist.reduce((a, b) => a.overall_frequency > b.overall_frequency ? a : b) : null;
  const mostActivated = hist.length > 0 ? hist.reduce((a, b) => a.times_activated > b.times_activated ? a : b) : null;

  const maxAllTimeScore = Math.max(...hist.map(h => h.all_time_score), 0.001);
  const maxEstProfit = Math.max(...hist.map(h => h.est_total_profit), 0.001);
  const maxFreq = Math.max(...hist.map(h => h.overall_frequency), 0.01);

  // Top/bottom lists
  const topByScore = [...hist].sort((a, b) => b.all_time_score - a.all_time_score).slice(0, 10);
  const topByProfit = [...hist].filter(h => h.est_total_profit > 0).sort((a, b) => b.est_total_profit - a.est_total_profit).slice(0, 10);
  const topByFreq = [...hist].filter(h => h.overall_frequency > 0).sort((a, b) => b.overall_frequency - a.overall_frequency).slice(0, 10);
  const bottomByNet = [...hist].filter(h => h.avg_net_pct < 0).sort((a, b) => a.avg_net_pct - b.avg_net_pct);

  // Trend analysis
  const trendingUp = [...hist].filter(h => h.trend > 0.0001).sort((a, b) => b.trend - a.trend).slice(0, 10);
  const trendingDown = [...hist].filter(h => h.trend < -0.0001).sort((a, b) => a.trend - b.trend).slice(0, 10);

  // Lifecycle funnel
  const totalSymbols = hist.length;
  const totalCandidates = hist.filter(h => h.times_became_candidate > 0).length;
  const totalWatchlisted = hist.filter(h => h.times_entered_watchlist > 0).length;
  const totalConfirmed = hist.filter(h => h.times_confirmed > 0).length;
  const totalActivated = hist.filter(h => h.times_activated > 0).length;

  // Strong/very strong stats
  const totalStrong = hist.filter(h => h.times_became_strong > 0).length;
  const totalVeryStrong = hist.filter(h => h.times_became_very_strong > 0).length;
  const totalStrongTimes = hist.reduce((s, h) => s + h.times_became_strong, 0);
  const totalVeryStrongTimes = hist.reduce((s, h) => s + h.times_became_very_strong, 0);

  return (
    <div className="space-y-5">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
        <div className="bg-slate-700/50 border border-slate-600/30 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-white">{formatDuration(sessionDuration)}</div>
          <div className="text-xs text-slate-400 mt-1">Session Duration</div>
        </div>
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-emerald-400">{profitable.length}</div>
          <div className="text-xs text-slate-400 mt-1">All-Time Profitable</div>
        </div>
        <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-blue-400">{totalTicks.toLocaleString()}</div>
          <div className="text-xs text-slate-400 mt-1">Total Ticks Scored</div>
        </div>
        <div className="bg-cyan-500/10 border border-cyan-500/20 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-cyan-400">{bestSymbol?.symbol.replace('USDT', '') ?? '—'}</div>
          <div className="text-xs text-slate-400 mt-1">Best (est profit)</div>
          {bestSymbol && <div className="text-[10px] text-cyan-400/70">${bestSymbol.est_total_profit.toFixed(4)}</div>}
        </div>
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-purple-400">{mostConsistent?.symbol.replace('USDT', '') ?? '—'}</div>
          <div className="text-xs text-slate-400 mt-1">Most Consistent</div>
          {mostConsistent && <div className="text-[10px] text-purple-400/70">{(mostConsistent.overall_frequency * 100).toFixed(1)}% freq</div>}
        </div>
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-amber-400">{mostActivated?.symbol.replace('USDT', '') ?? '—'}</div>
          <div className="text-xs text-slate-400 mt-1">Most Activated</div>
          {mostActivated && <div className="text-[10px] text-amber-400/70">{mostActivated.times_activated}x activated</div>}
        </div>
        <div className="bg-orange-500/10 border border-orange-500/20 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-orange-400">{totalStrong}</div>
          <div className="text-xs text-slate-400 mt-1">Strong Symbols</div>
          <div className="text-[10px] text-orange-400/70">{totalStrongTimes}x total</div>
        </div>
        <div className="bg-rose-500/10 border border-rose-500/20 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-rose-400">{totalVeryStrong}</div>
          <div className="text-xs text-slate-400 mt-1">Very Strong Symbols</div>
          <div className="text-[10px] text-rose-400/70">{totalVeryStrongTimes}x total</div>
        </div>
      </div>

      {/* Lifecycle Funnel */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Lifecycle Funnel</h3>
        <div className="flex items-center gap-2">
          {[
            { label: 'All Symbols', count: totalSymbols, color: 'bg-slate-500' },
            { label: 'Candidates', count: totalCandidates, color: 'bg-blue-500' },
            { label: 'Watchlisted', count: totalWatchlisted, color: 'bg-amber-500' },
            { label: 'Confirmed', count: totalConfirmed, color: 'bg-purple-500' },
            { label: 'Activated', count: totalActivated, color: 'bg-emerald-500' },
            { label: 'Strong', count: totalStrong, color: 'bg-orange-500' },
            { label: 'Very Strong', count: totalVeryStrong, color: 'bg-rose-500' },
          ].map((stage, i) => (
            <div key={stage.label} className="flex items-center gap-2 flex-1">
              <div className="flex-1">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-slate-400">{stage.label}</span>
                  <span className="text-sm font-bold text-white">{stage.count}</span>
                </div>
                <div className="h-6 bg-slate-700 rounded">
                  <div className={`h-full ${stage.color}/40 rounded`}
                    style={{ width: `${totalSymbols > 0 ? (stage.count / totalSymbols * 100) : 0}%` }} />
                </div>
              </div>
              {i < 6 && <span className="text-slate-600 text-lg">→</span>}
            </div>
          ))}
        </div>
      </div>

      {/* Full Historical Symbol Table */}
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
          All-Time Symbol Rankings ({hist.length} symbols)
        </h3>
        <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
          <table className="w-full text-sm min-w-[1100px]">
            <thead className="sticky top-0 bg-slate-800 z-10">
              <tr className="text-slate-400 text-xs uppercase">
                <th className="text-left px-2 py-2 font-medium">#</th>
                <th className="text-left px-2 py-2 font-medium">Symbol</th>
                <th className="text-center px-2 py-2 font-medium">Trend</th>
                <th className="text-right px-2 py-2 font-medium">All-Time</th>
                <th className="text-right px-2 py-2 font-medium">Rolling</th>
                <th className="text-right px-2 py-2 font-medium">Freq%</th>
                <th className="text-right px-2 py-2 font-medium">Avg Net%</th>
                <th className="text-right px-2 py-2 font-medium">Best%</th>
                <th className="text-right px-2 py-2 font-medium">Worst%</th>
                <th className="text-right px-2 py-2 font-medium">Est $</th>
                <th className="text-right px-2 py-2 font-medium">$/hr</th>
                <th className="text-right px-2 py-2 font-medium">P.Streak</th>
                <th className="text-right px-2 py-2 font-medium">U.Streak</th>
                <th className="text-right px-2 py-2 font-medium">Cand</th>
                <th className="text-right px-2 py-2 font-medium">Actv</th>
                <th className="text-right px-2 py-2 font-medium">Demot</th>
                <th className="text-right px-2 py-2 font-medium">Strong</th>
                <th className="text-right px-2 py-2 font-medium">V.Strong</th>
                <th className="text-right px-2 py-2 font-medium">Active Time</th>
              </tr>
            </thead>
            <tbody>
              {hist.map((h, i) => {
                const rowBg = h.is_active ? 'bg-emerald-500/10' : h.all_time_score > 0 ? '' : 'bg-red-500/5';
                return (
                  <tr key={h.symbol} className={`border-t border-slate-700/30 ${rowBg}`}>
                    <td className="px-2 py-1.5 text-slate-500 font-mono">{i + 1}</td>
                    <td className={`px-2 py-1.5 font-medium ${h.is_active ? 'text-emerald-300' : h.all_time_score > 0 ? 'text-white' : 'text-slate-500'}`}>
                      {h.symbol.replace('USDT', '')}
                    </td>
                    <td className="px-2 py-1.5 text-center"><TrendArrow trend={h.trend} /></td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-300">{h.all_time_score > 0 ? h.all_time_score.toFixed(4) : '0'}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-blue-400">{h.rolling_score > 0 ? h.rolling_score.toFixed(4) : '0'}</td>
                    <td className={`px-2 py-1.5 text-right font-mono ${h.overall_frequency > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {(h.overall_frequency * 100).toFixed(1)}%
                    </td>
                    <td className={`px-2 py-1.5 text-right font-mono ${h.avg_net_pct > 0 ? 'text-emerald-400' : 'text-red-400/60'}`}>
                      {h.avg_net_pct.toFixed(4)}%
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-emerald-400/70">{h.best_net_pct.toFixed(4)}%</td>
                    <td className="px-2 py-1.5 text-right font-mono text-red-400/70">{h.worst_net_pct.toFixed(4)}%</td>
                    <td className={`px-2 py-1.5 text-right font-mono ${h.est_total_profit > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {h.est_total_profit > 0 ? '$' + h.est_total_profit.toFixed(4) : '—'}
                    </td>
                    <td className={`px-2 py-1.5 text-right font-mono ${h.est_hourly_rate > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {h.est_hourly_rate > 0 ? '$' + h.est_hourly_rate.toFixed(4) : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-400">{h.longest_profitable_streak || '—'}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-red-400/60">{h.longest_unprofitable_streak || '—'}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-400">{h.times_became_candidate || '—'}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-emerald-400/70">{h.times_activated || '—'}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-red-400/60">{h.times_demoted || '—'}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-orange-400" title={h.total_strong_duration > 0 ? formatDuration(h.total_strong_duration) : ''}>
                      {h.times_became_strong > 0 ? `${h.times_became_strong}×` : '—'}
                      {h.total_strong_duration > 0 && <span className="text-orange-400/60 text-[10px] ml-0.5">({formatDuration(h.total_strong_duration)})</span>}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-rose-400" title={h.total_very_strong_duration > 0 ? formatDuration(h.total_very_strong_duration) : ''}>
                      {h.times_became_very_strong > 0 ? `${h.times_became_very_strong}×` : '—'}
                      {h.total_very_strong_duration > 0 && <span className="text-rose-400/60 text-[10px] ml-0.5">({formatDuration(h.total_very_strong_duration)})</span>}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-400">
                      {h.total_active_duration > 0 ? formatDuration(h.total_active_duration) : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Top 10 Charts - 3 column */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 sm:gap-5">
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Top 10 by All-Time Score</h3>
          <div className="space-y-1.5">
            {topByScore.filter(h => h.all_time_score > 0).map((h) => (
              <HBarRow key={h.symbol} label={h.symbol.replace('USDT', '')} value={h.all_time_score} maxValue={maxAllTimeScore}
                color={h.is_active ? 'bg-emerald-500/50' : 'bg-blue-500/40'} />
            ))}
          </div>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Top 10 by Est Total Profit</h3>
          <div className="space-y-1.5">
            {topByProfit.map((h) => (
              <HBarRow key={h.symbol} label={h.symbol.replace('USDT', '')} value={h.est_total_profit} maxValue={maxEstProfit}
                color={h.is_active ? 'bg-emerald-500/50' : 'bg-purple-500/40'} suffix="$" />
            ))}
          </div>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Top 10 by Overall Frequency</h3>
          <div className="space-y-1.5">
            {topByFreq.map((h) => (
              <HBarRow key={h.symbol} label={h.symbol.replace('USDT', '')} value={h.overall_frequency * 100} maxValue={maxFreq * 100}
                color={h.is_active ? 'bg-emerald-500/50' : 'bg-cyan-500/40'} suffix="%" />
            ))}
          </div>
        </div>
      </div>

      {/* Unprofitable Assets + Trend Analysis */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 sm:gap-5">
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
            Unprofitable Assets ({bottomByNet.length}) — Permanently Avoid
          </h3>
          <div className="space-y-1.5 max-h-[500px] overflow-y-auto">
            {bottomByNet.map((h) => (
              <HBarRow key={h.symbol} label={h.symbol.replace('USDT', '')} value={h.avg_net_pct}
                maxValue={Math.max(...bottomByNet.map(b => Math.abs(b.avg_net_pct)), 0.001)}
                color="bg-red-500/40" suffix="%" />
            ))}
          </div>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-emerald-400 uppercase tracking-wider mb-3">Trending UP (improving)</h3>
          {trendingUp.length > 0 ? (
            <div className="space-y-1.5">
              {trendingUp.map((h) => (
                <div key={h.symbol} className="flex items-center gap-2 text-xs">
                  <span className="w-16 text-right font-mono text-emerald-300">{h.symbol.replace('USDT', '')}</span>
                  <TrendArrow trend={h.trend} />
                  <span className="font-mono text-emerald-400">+{h.trend.toFixed(4)}</span>
                  <span className="text-slate-500">
                    (rolling {h.rolling_score.toFixed(4)} vs hist {h.all_time_score.toFixed(4)})
                  </span>
                </div>
              ))}
            </div>
          ) : <p className="text-slate-500 text-sm">No symbols trending up</p>}
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-red-400 uppercase tracking-wider mb-3">Trending DOWN (declining)</h3>
          {trendingDown.length > 0 ? (
            <div className="space-y-1.5">
              {trendingDown.map((h) => (
                <div key={h.symbol} className="flex items-center gap-2 text-xs">
                  <span className="w-16 text-right font-mono text-red-300">{h.symbol.replace('USDT', '')}</span>
                  <TrendArrow trend={h.trend} />
                  <span className="font-mono text-red-400">{h.trend.toFixed(4)}</span>
                  <span className="text-slate-500">
                    (rolling {h.rolling_score.toFixed(4)} vs hist {h.all_time_score.toFixed(4)})
                  </span>
                </div>
              ))}
            </div>
          ) : <p className="text-slate-500 text-sm">No symbols trending down</p>}
        </div>
      </div>

      {/* Historical Exchange Rankings */}
      {histEx && histEx.length > 0 && (
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Historical Exchange Rankings</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-xs uppercase">
                <th className="text-left px-3 py-2 font-medium">Exchange</th>
                <th className="text-right px-3 py-2 font-medium">Buy Ticks</th>
                <th className="text-right px-3 py-2 font-medium">Sell Ticks</th>
                <th className="text-right px-3 py-2 font-medium">Total</th>
                <th className="text-right px-3 py-2 font-medium">Profit Sum</th>
                <th className="text-left px-3 py-2 font-medium">Buy/Sell Ratio</th>
              </tr>
            </thead>
            <tbody>
              {histEx.map((ex) => {
                const total = ex.total_buy_ticks + ex.total_sell_ticks;
                const buyPct = total > 0 ? (ex.total_buy_ticks / total * 100) : 50;
                return (
                  <tr key={ex.exchange} className="border-t border-slate-700/30">
                    <td className="px-3 py-2 font-medium text-white">{ex.exchange}</td>
                    <td className="px-3 py-2 text-right font-mono text-cyan-400">{ex.total_buy_ticks.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right font-mono text-amber-400">{ex.total_sell_ticks.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right font-mono text-slate-300">{ex.total_involvement.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right font-mono text-emerald-400">{ex.total_profit_sum.toFixed(2)}</td>
                    <td className="px-3 py-2">
                      <div className="w-32 h-4 bg-slate-700 rounded-sm overflow-hidden flex relative">
                        <div className="h-full bg-cyan-500/50" style={{ width: `${buyPct}%` }} />
                        <div className="h-full bg-amber-500/50" style={{ width: `${100 - buyPct}%` }} />
                        <span className="absolute inset-0 flex items-center justify-center text-[10px] font-mono text-white/80">
                          {buyPct.toFixed(0)}% / {(100 - buyPct).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Main Component
// ══════════════════════════════════════════════════════════════════════════════

export default function RankingPage({ optimizer, tickCount, portfolio, simulation, allTrades, allTransfers, allConfigHistory, demoDiscrepancies, feeConfigs, transferConfigs, profitStats, defaultView }: RankingPageProps) {
  const location = useLocation();
  const view: 'rolling' | 'historical' = defaultView || (location.pathname.endsWith('/historical') ? 'historical' : 'rolling');
  const windowMinutes = Math.round(optimizer.scoring_window / 60);
  const [mdCopied, setMdCopied] = useState(false);

  const activeCount = optimizer.active_symbols?.length ?? 0;
  const minActive = optimizer.min_active_symbols ?? activeCount;
  const maxActive = optimizer.max_active_symbols ?? activeCount;

  return (
    <div className="space-y-3 sm:space-y-5">
      {/* Header with toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-white">Symbol & Exchange Rankings</h2>
          <p className="text-sm text-slate-400">
            {view === 'rolling'
              ? `Rolling ${windowMinutes}min window`
              : 'All-time session stats'
            }
            {' | '}{tickCount.toLocaleString()} ticks
            {activeCount > 0 && ` | ${activeCount} active (${minActive}-${maxActive})`}
            {optimizer.discovery_mode && <span className="text-amber-400 ml-2">(Discovery Mode)</span>}
          </p>
        </div>
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
          <button
            onClick={() => exportXlsx(optimizer, portfolio ?? null, simulation ?? null, allTrades ?? [], allTransfers ?? [], allConfigHistory ?? [], demoDiscrepancies ?? [], feeConfigs, transferConfigs, profitStats)}
            className="px-4 py-1.5 rounded-lg text-sm font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
          >
            Export XLSX
          </button>
          <button
            onClick={() => {
              const md = exportRankingsMarkdown({ optimizer, portfolio, simulation, profitStats, allTrades, allTransfers, allConfigHistory });
              navigator.clipboard.writeText(md).then(() => {
                setMdCopied(true);
                setTimeout(() => setMdCopied(false), 2000);
              });
            }}
            className="px-4 py-1.5 rounded-lg text-sm font-medium border border-slate-600 text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-colors"
          >
            {mdCopied ? 'Copied!' : 'Copy MD'}
          </button>
          <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-1">
            <NavLink to="/rankings" end
              className={({ isActive }) => `px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                isActive ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Rolling
            </NavLink>
            <NavLink to="/rankings/historical"
              className={({ isActive }) => `px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                isActive ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Historical
            </NavLink>
          </div>
        </div>
      </div>

      {/* Performance Charts */}
      {(allTrades?.length ?? 0) > 0 && (
        <PerformanceCharts trades={allTrades ?? []} transfers={allTransfers ?? []} />
      )}

      {view === 'rolling' ? (
        <RollingView optimizer={optimizer} />
      ) : (
        <HistoricalView optimizer={optimizer} />
      )}
    </div>
  );
}
