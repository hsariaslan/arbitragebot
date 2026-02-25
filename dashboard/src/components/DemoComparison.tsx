import { useState } from 'react';
import type { DemoComparisonState, DemoExchangeComparison, DemoDiscrepancy } from '../types';

interface DemoComparisonProps {
  data: DemoComparisonState;
}

function formatAge(timestamp: number): string {
  const age = Math.floor((Date.now() / 1000) - timestamp);
  if (age < 5) return 'just now';
  if (age < 60) return `${age}s ago`;
  if (age < 3600) return `${Math.floor(age / 60)}m ago`;
  return `${Math.floor(age / 3600)}h ago`;
}

function formatTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleTimeString();
}

function diffColor(pct: number): string {
  const abs = Math.abs(pct);
  if (abs < 1) return 'text-emerald-400';
  if (abs < 5) return 'text-yellow-400';
  return 'text-red-400';
}

function diffBg(pct: number): string {
  const abs = Math.abs(pct);
  if (abs < 1) return 'bg-emerald-500/10';
  if (abs < 5) return 'bg-yellow-500/10';
  return 'bg-red-500/10';
}

function ExchangeCard({ exchange, comparison }: { exchange: string; comparison: DemoExchangeComparison }) {
  const hasError = !!comparison.demo.error;
  const allSymbols = new Set([
    ...Object.keys(comparison.sim.crypto),
    ...Object.keys(comparison.demo.crypto),
  ]);

  return (
    <div className="bg-slate-800/70 rounded-lg border border-slate-700 overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-slate-700 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${hasError ? 'bg-yellow-400' : 'bg-emerald-400'}`} />
          <span className="text-sm font-semibold text-slate-200">{exchange}</span>
        </div>
        {comparison.demo.fetched_at && (
          <span className="text-xs text-slate-500">{formatAge(comparison.demo.fetched_at)}</span>
        )}
      </div>

      {/* Error banner */}
      {hasError && (
        <div className="px-3 py-1.5 bg-yellow-900/20 border-b border-yellow-800/30 text-xs text-yellow-400">
          API Error: {comparison.demo.error}
        </div>
      )}

      {/* Comparison table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-500 uppercase">
              <th className="text-left px-3 py-1.5 font-medium">Asset</th>
              <th className="text-right px-3 py-1.5 font-medium">Sim</th>
              <th className="text-right px-3 py-1.5 font-medium">Demo</th>
              <th className="text-right px-3 py-1.5 font-medium">Diff</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {/* USDT row */}
            <tr className="text-slate-300">
              <td className="px-3 py-1">USDT</td>
              <td className="text-right px-3 py-1">${comparison.sim.usdt.toFixed(2)}</td>
              <td className="text-right px-3 py-1">${comparison.demo.usdt.toFixed(2)}</td>
              <td className={`text-right px-3 py-1 ${diffColor(comparison.diff_usdt / Math.max(comparison.demo.usdt, 1) * 100)}`}>
                {comparison.diff_usdt >= 0 ? '+' : ''}{comparison.diff_usdt.toFixed(2)}
              </td>
            </tr>

            {/* Crypto rows */}
            {[...allSymbols].sort().map(sym => {
              const simVal = comparison.sim.crypto[sym]?.value ?? 0;
              const demoVal = comparison.demo.crypto[sym]?.value ?? 0;
              const diff = simVal - demoVal;
              const pct = demoVal > 0 ? diff / demoVal * 100 : (simVal > 0 ? 100 : 0);
              if (simVal < 0.01 && demoVal < 0.01) return null;
              return (
                <tr key={sym} className="text-slate-300">
                  <td className="px-3 py-1">{sym.replace('USDT', '')}</td>
                  <td className="text-right px-3 py-1">${simVal.toFixed(2)}</td>
                  <td className="text-right px-3 py-1">${demoVal.toFixed(2)}</td>
                  <td className={`text-right px-3 py-1 ${diffColor(pct)}`}>
                    {diff >= 0 ? '+' : ''}{diff.toFixed(2)}
                  </td>
                </tr>
              );
            })}

            {/* Total row */}
            <tr className={`font-semibold ${diffBg(comparison.diff_total_pct)}`}>
              <td className="px-3 py-1.5 text-slate-200">Total</td>
              <td className="text-right px-3 py-1.5 text-slate-200">${comparison.sim.total.toFixed(2)}</td>
              <td className="text-right px-3 py-1.5 text-slate-200">${comparison.demo.total.toFixed(2)}</td>
              <td className={`text-right px-3 py-1.5 ${diffColor(comparison.diff_total_pct)}`}>
                {comparison.diff_total >= 0 ? '+' : ''}{comparison.diff_total.toFixed(2)}
                <span className="text-[10px] ml-1">({comparison.diff_total_pct >= 0 ? '+' : ''}{comparison.diff_total_pct.toFixed(1)}%)</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DiscrepancyLog({ discrepancies, total }: { discrepancies: DemoDiscrepancy[]; total: number }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? discrepancies : discrepancies.slice(-10);

  return (
    <div className="bg-slate-800/50 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-700 flex items-center justify-between">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          Discrepancy Log ({total} total)
        </h3>
        {discrepancies.length > 10 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-blue-400 hover:text-blue-300"
          >
            {expanded ? 'Show less' : `Show all ${discrepancies.length}`}
          </button>
        )}
      </div>
      <div className="overflow-x-auto max-h-64 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-800">
            <tr className="text-slate-500 uppercase">
              <th className="text-left px-3 py-1.5 font-medium">Time</th>
              <th className="text-left px-3 py-1.5 font-medium">Exchange</th>
              <th className="text-left px-3 py-1.5 font-medium">Type</th>
              <th className="text-left px-3 py-1.5 font-medium">Symbol</th>
              <th className="text-right px-3 py-1.5 font-medium">Sim</th>
              <th className="text-right px-3 py-1.5 font-medium">Demo</th>
              <th className="text-right px-3 py-1.5 font-medium">Diff%</th>
              <th className="text-left px-3 py-1.5 font-medium">Root Cause</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/30">
            {[...shown].reverse().map((d, i) => (
              <tr key={i} className="text-slate-300 hover:bg-slate-700/30">
                <td className="px-3 py-1 text-slate-500 whitespace-nowrap">{formatTime(d.timestamp)}</td>
                <td className="px-3 py-1">{d.exchange}</td>
                <td className="px-3 py-1">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                    d.type === 'balance_mismatch' ? 'bg-yellow-900/40 text-yellow-400' :
                    d.type === 'missing_position' ? 'bg-red-900/40 text-red-400' :
                    d.type === 'extra_position' ? 'bg-blue-900/40 text-blue-400' :
                    'bg-slate-700 text-slate-400'
                  }`}>
                    {d.type.replace('_', ' ')}
                  </span>
                </td>
                <td className="px-3 py-1">{d.symbol.replace('USDT', '') || 'USDT'}</td>
                <td className="text-right px-3 py-1">${d.sim_value.toFixed(2)}</td>
                <td className="text-right px-3 py-1">${d.demo_value.toFixed(2)}</td>
                <td className={`text-right px-3 py-1 ${diffColor(d.diff_pct)}`}>
                  {d.diff_pct >= 0 ? '+' : ''}{d.diff_pct.toFixed(1)}%
                </td>
                <td className="px-3 py-1 text-slate-400 max-w-xs truncate" title={d.root_cause}>
                  {d.root_cause}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && (
          <div className="text-center text-slate-500 py-4 text-xs">No discrepancies detected yet</div>
        )}
      </div>
    </div>
  );
}

export default function DemoComparison({ data }: DemoComparisonProps) {
  const exchanges = Object.entries(data.exchanges);
  if (exchanges.length === 0) return null;

  return (
    <div className="space-y-4">
      <div className="bg-slate-800/50 rounded-lg overflow-hidden">
        <div className="px-3 sm:px-4 py-3 border-b border-slate-700 flex flex-col sm:flex-row sm:items-center justify-between gap-1">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
            Demo Portfolio Comparison
          </h2>
          <span className="text-xs text-slate-500">
            {data.configured_exchanges.join(', ')} | Last fetch: {data.last_fetch_time ? formatAge(data.last_fetch_time) : 'never'}
          </span>
        </div>
        <div className={`grid gap-4 p-4 ${
          exchanges.length === 1 ? 'grid-cols-1 max-w-lg' :
          exchanges.length === 2 ? 'grid-cols-1 lg:grid-cols-2' :
          'grid-cols-1 lg:grid-cols-3'
        }`}>
          {exchanges.map(([exchange, comp]) => (
            <ExchangeCard key={exchange} exchange={exchange} comparison={comp} />
          ))}
        </div>
      </div>

      <DiscrepancyLog
        discrepancies={data.recent_discrepancies}
        total={data.total_discrepancies}
      />
    </div>
  );
}
