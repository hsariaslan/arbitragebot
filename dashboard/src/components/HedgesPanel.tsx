// Phase F — futures hedge state panel.
// Shows open hedge positions with live mark price, unrealized P&L, and
// cumulative funding P&L per symbol. Visible on the main Dashboard page.

import type { HedgeState } from '../types';

interface HedgesPanelProps {
  hedges?: HedgeState;
}

function fmtDuration(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}

function fmtUsd(n: number, decimals = 2): string {
  const sign = n >= 0 ? '+' : '−';
  return `${sign}$${Math.abs(n).toFixed(decimals)}`;
}

function modeBadge(mode: string): { label: string; cls: string } {
  switch (mode) {
    case 'live':    return { label: 'LIVE',    cls: 'bg-red-700/40 text-red-300 border-red-600' };
    case 'testnet': return { label: 'TESTNET', cls: 'bg-amber-700/40 text-amber-300 border-amber-600' };
    default:        return { label: 'SHADOW',  cls: 'bg-slate-700/40 text-slate-400 border-slate-600' };
  }
}

function reserveBadge(status: string): { label: string; cls: string } {
  switch (status) {
    case 'healthy': return { label: 'RESERVE OK', cls: 'bg-emerald-700/30 text-emerald-300 border-emerald-600' };
    case 'topup_needed': return { label: 'TOP-UP NEEDED', cls: 'bg-amber-700/40 text-amber-300 border-amber-600' };
    case 'emergency': return { label: 'RESERVE LOW', cls: 'bg-red-700/40 text-red-300 border-red-600' };
    case 'unavailable': return { label: 'RESERVE UNKNOWN', cls: 'bg-red-700/40 text-red-300 border-red-600' };
    case 'disabled': return { label: 'RESERVE OFF', cls: 'bg-slate-700/40 text-slate-400 border-slate-600' };
    default: return { label: 'RESERVE PENDING', cls: 'bg-blue-700/40 text-blue-300 border-blue-600' };
  }
}

export default function HedgesPanel({ hedges }: HedgesPanelProps) {
  if (!hedges || !hedges.enabled) {
    return null;
  }
  const badge = modeBadge(hedges.execution_mode);
  const totalCum = hedges.cumulative_funding_usd;
  const totalUnreal = hedges.total_unrealized_pnl_usd;
  const totalGap = hedges.total_hedge_gap_usd ?? 0;
  const gapClass = Math.abs(totalGap) <= 5 ? 'text-slate-200' : 'text-amber-400';
  const unhedgedTargets = hedges.unhedged_targets ?? [];
  const materialUnhedged = unhedgedTargets.filter(t => t.reason !== 'dust');
  const reserve = hedges.futures_reserve;
  const reserveUi = reserveBadge(reserve?.status ?? 'unknown');

  return (
    <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
          Futures Hedges
        </h3>
        <span className={`px-2 py-0.5 text-[10px] font-semibold rounded border ${badge.cls}`}>
          {badge.label}
        </span>
        {reserve && (
          <span className={`px-2 py-0.5 text-[10px] font-semibold rounded border ${reserveUi.cls}`}>
            {reserveUi.label}
          </span>
        )}
        {hedges.safety_paused && (
          <span className="px-2 py-0.5 text-[10px] font-semibold rounded border bg-amber-700/40 text-amber-300 border-amber-600">
            OPENS PAUSED
          </span>
        )}
        {materialUnhedged.length > 0 && (
          <span className="px-2 py-0.5 text-[10px] font-semibold rounded border bg-amber-700/40 text-amber-300 border-amber-600">
            UNHEDGED {materialUnhedged.length}
          </span>
        )}
        {!hedges.reconciled && hedges.execution_mode !== 'simulation' && (
          <span className="px-2 py-0.5 text-[10px] font-semibold rounded border bg-blue-700/40 text-blue-300 border-blue-600">
            RECONCILE PENDING
          </span>
        )}
        <div className="flex-1" />
        <div className="text-xs text-slate-500">
          opens={hedges.total_opens} adjusts={hedges.total_adjusts} closes={hedges.total_closes}
          {hedges.total_executor_errors > 0 && (
            <span className="text-red-400 ml-2">errors={hedges.total_executor_errors}</span>
          )}
        </div>
      </div>

      {reserve && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
          <div className="bg-slate-900/40 rounded p-2">
            <div className="text-[10px] text-slate-500 uppercase">Futures reserve</div>
            <div className="text-lg font-mono text-slate-200">
              ${reserve.margin_balance_usd.toFixed(0)}
              <span className="text-xs text-slate-500"> / ${reserve.target_usd.toFixed(0)}</span>
            </div>
          </div>
          <div className="bg-slate-900/40 rounded p-2">
            <div className="text-[10px] text-slate-500 uppercase">Available margin</div>
            <div className="text-lg font-mono text-slate-200">${reserve.available_usd.toFixed(0)}</div>
          </div>
          <div className="bg-slate-900/40 rounded p-2">
            <div className="text-[10px] text-slate-500 uppercase">Needed buffered</div>
            <div className="text-lg font-mono text-slate-200">
              ${reserve.required_buffered_margin_usd.toFixed(0)}
            </div>
          </div>
          <div className="bg-slate-900/40 rounded p-2">
            <div className="text-[10px] text-slate-500 uppercase">Policy</div>
            <div className="text-lg font-mono text-slate-200">
              {reserve.leverage}x
              <span className="text-xs text-slate-500">
                {' '}T{(reserve.target_pct * 100).toFixed(0)} E{(reserve.emergency_pct * 100).toFixed(0)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Aggregate totals */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-3">
        <div className="bg-slate-900/40 rounded p-2">
          <div className="text-[10px] text-slate-500 uppercase">Open hedges</div>
          <div className="text-lg font-mono text-slate-200">{hedges.open_count}</div>
        </div>
        <div className="bg-slate-900/40 rounded p-2">
          <div className="text-[10px] text-slate-500 uppercase">Total notional</div>
          <div className="text-lg font-mono text-slate-200">${hedges.total_notional_usd.toFixed(0)}</div>
        </div>
        <div className="bg-slate-900/40 rounded p-2">
          <div className="text-[10px] text-slate-500 uppercase">Hedge gap</div>
          <div className={`text-lg font-mono ${gapClass}`}>{fmtUsd(totalGap, 2)}</div>
        </div>
        <div className="bg-slate-900/40 rounded p-2">
          <div className="text-[10px] text-slate-500 uppercase">Unrealized P&L</div>
          <div className={`text-lg font-mono ${totalUnreal >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {fmtUsd(totalUnreal, 2)}
          </div>
        </div>
        <div className="bg-slate-900/40 rounded p-2">
          <div className="text-[10px] text-slate-500 uppercase">Cumulative funding</div>
          <div className={`text-lg font-mono ${totalCum >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {fmtUsd(totalCum, 2)}
          </div>
        </div>
      </div>

      {/* Open hedges table */}
      {hedges.open_hedges.length === 0 ? (
        <p className="text-slate-500 text-xs">
          No open hedges. {materialUnhedged.length > 0
            ? `${materialUnhedged.length} held target(s) are waiting for a hedge decision.`
            : hedges.execution_mode === 'simulation'
              ? 'Shadow-only mode — see [Hedge] WOULD_OPEN logs in Bot Logs for decisions.'
              : 'Bot will hedge when active symbols accumulate above the dust threshold ($' + hedges.dust_threshold_usd.toFixed(0) + ').'}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-700">
                <th className="text-left py-1.5 px-2">Symbol</th>
                <th className="text-right py-1.5 px-2">Side</th>
                <th className="text-right py-1.5 px-2">Qty</th>
                <th className="text-right py-1.5 px-2">Entry</th>
                <th className="text-right py-1.5 px-2">Mark</th>
                <th className="text-right py-1.5 px-2">Notional</th>
                <th className="text-right py-1.5 px-2">Target</th>
                <th className="text-right py-1.5 px-2">Gap</th>
                <th className="text-right py-1.5 px-2">Unrealized</th>
                <th className="text-right py-1.5 px-2">Funding</th>
                <th className="text-right py-1.5 px-2">Rate (ann)</th>
                <th className="text-right py-1.5 px-2">Held</th>
              </tr>
            </thead>
            <tbody>
              {hedges.open_hedges.map(h => {
                const pnlClass = h.unrealized_pnl_usd >= 0 ? 'text-emerald-400' : 'text-red-400';
                const fundingClass = h.accumulated_funding_usd >= 0 ? 'text-emerald-400' : 'text-red-400';
                const ann = h.annualized_short_pct ?? 0;
                const annClass = ann >= 0 ? 'text-emerald-400' : ann < -10 ? 'text-red-400' : 'text-amber-400';
                const gap = h.notional_gap_usd ?? 0;
                const rowGapClass = Math.abs(gap) <= 5 ? 'text-slate-500' : 'text-amber-400';
                return (
                  <tr key={h.symbol} className="border-b border-slate-800/50 hover:bg-slate-700/30">
                    <td className="py-1.5 px-2 font-mono text-slate-200">{h.symbol.replace(/USDT$/, '')}</td>
                    <td className="text-right py-1.5 px-2 text-rose-400">{h.side}</td>
                    <td className="text-right py-1.5 px-2 font-mono text-slate-300">{h.qty.toFixed(6)}</td>
                    <td className="text-right py-1.5 px-2 font-mono text-slate-400">${h.entry_price.toFixed(4)}</td>
                    <td className="text-right py-1.5 px-2 font-mono text-slate-300">${h.mark_price.toFixed(4)}</td>
                    <td className="text-right py-1.5 px-2 font-mono text-slate-300">${h.notional_usd.toFixed(2)}</td>
                    <td className="text-right py-1.5 px-2 font-mono text-slate-400">${(h.target_notional_usd ?? h.notional_usd).toFixed(2)}</td>
                    <td className={`text-right py-1.5 px-2 font-mono ${rowGapClass}`}>{fmtUsd(gap, 2)}</td>
                    <td className={`text-right py-1.5 px-2 font-mono ${pnlClass}`}>{fmtUsd(h.unrealized_pnl_usd, 4)}</td>
                    <td className={`text-right py-1.5 px-2 font-mono ${fundingClass}`}>{fmtUsd(h.accumulated_funding_usd, 4)}</td>
                    <td className={`text-right py-1.5 px-2 font-mono ${annClass}`}>
                      {ann >= 0 ? '+' : ''}{ann.toFixed(2)}%
                    </td>
                    <td className="text-right py-1.5 px-2 font-mono text-slate-400">{fmtDuration(h.held_seconds)}</td>
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
