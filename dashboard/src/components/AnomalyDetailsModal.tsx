import { useEffect, useState } from 'react';
import type { ConfigAnomaly } from '../types';

interface Props {
  configsAnomaly: ConfigAnomaly[];
  onClose: () => void;
  onSendMessage: (msg: object) => void;
}

export type AnomalySeverity = 'high' | 'medium' | 'low' | 'ok' | 'off' | 'stopped';

/**
 * Classify a single config's anomaly severity using the natural escalation
 * ladder of the 3-layer protection system in `anomaly_protection.py`:
 *
 *   - HIGH   (red)    = emergency_triggered. Drawdown crossed
 *                       threshold_pct × emergency_mult (default 2.0× = 30%).
 *                       Bot ran emergency sell-all; auto-resume disabled;
 *                       requires the operator to click "Resume Trading".
 *
 *   - MEDIUM (yellow) = paused (and not emergency). Either:
 *                         · Layer 1 circuit breaker tripped (rolling P&L
 *                           below threshold for the configured window), OR
 *                         · Layer 2 drawdown ≥ threshold but < emergency.
 *                       Trading is fully suspended but auto-resumes when
 *                       the metric recovers past resume_pct.
 *
 *   - LOW    (green)  = warning_active OR symbol_blocks present, but no
 *                       global pause. Preventive: trade size halved on
 *                       warning, individual symbols sidelined on Layer 3
 *                       loss-streak. Bot keeps trading other symbols.
 *
 *   - OK              = anomaly_protection enabled and no triggers.
 *   - OFF             = anomaly_protection disabled.
 *   - STOPPED         = manual_stopped (independent of anomaly system).
 */
export function classifyConfigSeverity(c: ConfigAnomaly): AnomalySeverity {
  if (c.manual_stopped) return 'stopped';
  if (c.emergency_triggered) return 'high';
  if (c.paused) return 'medium';
  if (c.warning_active || (c.symbol_blocks && Object.keys(c.symbol_blocks).length > 0)) {
    return 'low';
  }
  if (c.enabled) return 'ok';
  return 'off';
}

const formatRelative = (ts: number): string => {
  if (!ts) return '—';
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
};

const SEVERITY_META: Record<AnomalySeverity, { label: string; bg: string; border: string; text: string; icon: string }> = {
  high: { label: 'EMERGENCY', bg: 'bg-rose-950/40', border: 'border-rose-700/40', text: 'text-rose-300', icon: '⚠' },
  medium: { label: 'PAUSED', bg: 'bg-amber-950/40', border: 'border-amber-700/40', text: 'text-amber-300', icon: '⚠' },
  low: { label: 'WARNING / SYMBOL BLOCK', bg: 'bg-emerald-950/30', border: 'border-emerald-700/40', text: 'text-emerald-300', icon: '⚠' },
  stopped: { label: 'MANUAL STOP', bg: 'bg-slate-800/60', border: 'border-slate-700', text: 'text-rose-300', icon: '■' },
  ok: { label: 'PROTECTED', bg: 'bg-slate-800/40', border: 'border-slate-700', text: 'text-emerald-400', icon: '✓' },
  off: { label: 'OFF', bg: 'bg-slate-800/30', border: 'border-slate-700', text: 'text-slate-500', icon: '·' },
};

function ConfigAnomalyCard({
  c,
  onResume,
}: {
  c: ConfigAnomaly;
  onResume?: (configId: string) => void;
}) {
  const sev = classifyConfigSeverity(c);
  const meta = SEVERITY_META[sev];
  const blockedSymbolEntries = Object.entries(c.symbol_blocks ?? {});
  // Cursor-anchored tooltip (escape modal overflow + named-group flake-out)
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);

  return (
    <>
    <div
      className={`relative border rounded-lg ${meta.bg} ${meta.border} p-3 cursor-default`}
      onMouseEnter={(e) => setHoverPos({ x: e.clientX, y: e.clientY })}
      onMouseMove={(e) => setHoverPos({ x: e.clientX, y: e.clientY })}
      onMouseLeave={() => setHoverPos(null)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`font-semibold text-sm ${meta.text}`}>
              {meta.icon} {meta.label}
            </span>
            <span className="text-white font-medium text-sm">
              {c.group_name} / {c.name}
            </span>
            {c.is_super_primary && <span className="text-amber-400 text-xs font-bold">★★ SUPER</span>}
            {c.is_primary && !c.is_super_primary && <span className="text-purple-400 text-xs">★</span>}
            {c.is_default && (
              <span className="text-blue-300 text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10">DEFAULT</span>
            )}
            {blockedSymbolEntries.length > 0 && (
              <span className="text-emerald-400 text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10">
                {blockedSymbolEntries.length} symbol(s) blocked
              </span>
            )}
          </div>
          {(c.paused || c.warning_active) && (
            <div className="mt-1 text-xs text-slate-300">
              <span className="text-slate-500">Reason:</span>{' '}
              {c.pause_reason || c.warning_reason || '—'}
              {c.pause_layer && (
                <span className="text-slate-500 ml-2">layer={c.pause_layer}</span>
              )}
              {c.pause_timestamp > 0 && (
                <span className="text-slate-500 ml-2">since {formatRelative(c.pause_timestamp)}</span>
              )}
            </div>
          )}
        </div>
        {sev === 'high' && onResume && (
          <button
            onClick={() => onResume(c.config_id)}
            className="shrink-0 px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium"
            title={`Resume trading for ${c.group_name} / ${c.name}. Clears emergency_triggered + paused flags. Re-runs the next sweep tick.`}
          >
            Resume This Config
          </button>
        )}
      </div>

      {/* Per-symbol blocks (kept inline — useful at-a-glance, hover would
          obscure long lists) */}
      {blockedSymbolEntries.length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-700/40">
          <div className="text-xs text-slate-500 mb-1.5">
            Blocked symbols ({blockedSymbolEntries.length}):
          </div>
          <div className="flex flex-wrap gap-1.5">
            {blockedSymbolEntries.map(([sym, secsLeft]) => (
              <span
                key={sym}
                className="text-xs px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 font-mono"
                title={`${sym} — unblocks in ${Math.ceil(secsLeft)}s`}
              >
                {sym} <span className="text-slate-500">{Math.ceil(secsLeft)}s</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
    {/* Cursor-anchored tooltip — fixed-positioned outside the card so the
        modal's overflow-y-auto doesn't clip it. */}
    {hoverPos && (
      <div
        className="fixed z-[100] pointer-events-none"
        style={{
          left: `${Math.min(hoverPos.x + 16, window.innerWidth - 340)}px`,
          top: `${Math.min(hoverPos.y + 16, window.innerHeight - 180)}px`,
        }}
      >
        <div className="bg-slate-900 border border-slate-600 rounded-lg shadow-2xl p-3 text-xs space-y-1 font-mono w-80">
          <div>
            <span className="text-slate-500">Rolling P&L:</span>{' '}
            <span className={c.rolling_pnl >= 0 ? 'text-emerald-300' : 'text-rose-300'}>
              ${c.rolling_pnl.toFixed(2)}
            </span>
            <span className="text-slate-500"> / threshold </span>
            <span className="text-slate-300">${c.circuit_breaker_threshold.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-slate-500">Peak portfolio:</span>{' '}
            <span className="text-slate-200">${c.peak_portfolio.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-slate-500">Drawdown:</span>{' '}
            <span className={
              c.current_drawdown_pct >= c.drawdown_threshold_pct ? 'text-rose-300'
              : c.current_drawdown_pct >= c.drawdown_threshold_pct * 0.5 ? 'text-amber-300'
              : 'text-slate-200'
            }>
              {c.current_drawdown_pct.toFixed(2)}%
            </span>
            <span className="text-slate-500"> / threshold </span>
            <span className="text-slate-300">{c.drawdown_threshold_pct.toFixed(1)}%</span>
          </div>
          <div>
            <span className="text-slate-500">Session:</span>{' '}
            <span className="text-slate-200">
              {c.total_pauses}p / {c.total_warnings}w / {c.total_symbol_blocks}sb
            </span>
            {c.total_emergency_sells > 0 && (
              <>
                <span className="text-slate-500"> / </span>
                <span className="text-rose-300">{c.total_emergency_sells} emergency</span>
              </>
            )}
          </div>
          <div className="pt-1 mt-1 border-t border-slate-700/40 text-[10px] text-slate-600">
            Loss rate {c.loss_rate.toFixed(1)}% • Trade size mult {c.trade_size_multiplier.toFixed(2)}× •
            {c.trades_in_window} trades / {c.rolling_pnl_window}s window
          </div>
        </div>
      </div>
    )}
    </>
  );
}

export default function AnomalyDetailsModal({ configsAnomaly, onClose, onSendMessage }: Props) {
  // Esc closes
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Group by severity
  const groups: Record<AnomalySeverity, ConfigAnomaly[]> = {
    high: [], medium: [], low: [], stopped: [], ok: [], off: [],
  };
  for (const c of configsAnomaly) {
    groups[classifyConfigSeverity(c)].push(c);
  }

  const counts = {
    high: groups.high.length,
    medium: groups.medium.length,
    low: groups.low.length,
    stopped: groups.stopped.length,
    ok: groups.ok.length,
    off: groups.off.length,
  };

  const handleResumeOne = (configId: string) => {
    onSendMessage({ type: 'config_anomaly_resume', config_id: configId });
  };

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/70 flex items-start sm:items-center justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-slate-900 border border-slate-700 rounded-lg shadow-2xl w-full max-w-5xl my-4 max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700 px-5 py-3 shrink-0">
          <div>
            <h3 className="text-base font-semibold text-white">Anomaly Protection — All Configs</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Aggregated 3-layer protection state across {configsAnomaly.length} config(s).
              Click <span className="text-slate-300">Esc</span> or the backdrop to close.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-xl leading-none w-8 h-8 flex items-center justify-center rounded hover:bg-slate-800"
          >
            ×
          </button>
        </div>

        {/* Severity summary chips */}
        <div className="flex items-center gap-2 flex-wrap px-5 py-3 border-b border-slate-700/50 text-xs shrink-0">
          {counts.high > 0 && (
            <SeverityChip severity="high" count={counts.high} />
          )}
          {counts.medium > 0 && (
            <SeverityChip severity="medium" count={counts.medium} />
          )}
          {counts.low > 0 && (
            <SeverityChip severity="low" count={counts.low} />
          )}
          {counts.stopped > 0 && (
            <SeverityChip severity="stopped" count={counts.stopped} />
          )}
          {counts.ok > 0 && (
            <SeverityChip severity="ok" count={counts.ok} />
          )}
          {counts.off > 0 && (
            <SeverityChip severity="off" count={counts.off} />
          )}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* HIGH severity */}
          {groups.high.length > 0 && (
            <SeveritySection severity="high" configs={groups.high} onResume={handleResumeOne} />
          )}

          {/* MEDIUM severity */}
          {groups.medium.length > 0 && (
            <SeveritySection severity="medium" configs={groups.medium} />
          )}

          {/* LOW severity */}
          {groups.low.length > 0 && (
            <SeveritySection severity="low" configs={groups.low} />
          )}

          {/* MANUAL STOP */}
          {groups.stopped.length > 0 && (
            <SeveritySection severity="stopped" configs={groups.stopped} />
          )}

          {/* OK / OFF — uses the same ConfigAnomalyCard so the cursor-anchored
              hover tooltip works for healthy configs too (most operators
              spend most of their time looking at this section). */}
          {groups.ok.length > 0 && (
            <SeveritySection severity="ok" configs={groups.ok} />
          )}
          {groups.off.length > 0 && (
            <SeveritySection severity="off" configs={groups.off} />
          )}

          {configsAnomaly.length === 0 && (
            <div className="text-center text-slate-500 py-8">
              No configs loaded.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SeveritySection({
  severity,
  configs,
  onResume,
}: {
  severity: AnomalySeverity;
  configs: ConfigAnomaly[];
  onResume?: (configId: string) => void;
}) {
  const meta = SEVERITY_META[severity];
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h4 className={`text-xs font-semibold uppercase tracking-wider ${meta.text}`}>
          {meta.icon} {meta.label} ({configs.length})
        </h4>
      </div>
      <div className="space-y-2">
        {configs.map((c) => (
          <ConfigAnomalyCard key={c.config_id} c={c} onResume={onResume} />
        ))}
      </div>
    </div>
  );
}

function SeverityChip({ severity, count }: { severity: AnomalySeverity; count: number }) {
  const meta = SEVERITY_META[severity];
  return (
    <div
      className={`flex items-center gap-1.5 px-2 py-1 rounded border ${meta.bg} ${meta.border}`}
    >
      <span className={meta.text}>{meta.icon}</span>
      <span className={`font-medium ${meta.text}`}>{meta.label}</span>
      <span className="text-white font-mono">{count}</span>
    </div>
  );
}
