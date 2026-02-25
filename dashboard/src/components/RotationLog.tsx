import type { RotationEvent } from '../types';

interface RotationLogProps {
  rotations: RotationEvent[];
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString();
}

export default function RotationLog({ rotations }: RotationLogProps) {
  return (
    <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5 flex flex-col h-full">
      <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
        Rotation Log
      </h2>

      {rotations.length === 0 ? (
        <p className="text-slate-500 text-sm">No rotations yet</p>
      ) : (
        <div className="space-y-2 flex-1 overflow-y-auto min-h-0">
          {rotations.map((r, i) => (
            <div key={i} className="bg-slate-700/30 rounded-lg px-3 py-2 text-sm">
              <div className="flex items-center justify-between mb-1">
                <span className="text-slate-400 text-xs">{formatTime(r.timestamp)}</span>
                <span className="text-xs text-emerald-400 font-mono">
                  +${r.est_hourly_improvement_usd.toFixed(4)}/hr
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-red-400 font-medium">{r.old_symbol.replace('USDT', '')}</span>
                <span className="text-slate-500">→</span>
                <span className="text-emerald-400 font-medium">{r.new_symbol.replace('USDT', '')}</span>
              </div>
              <div className="flex items-center justify-between mt-1 text-xs text-slate-500">
                <span>Score: {r.old_score.toFixed(4)} → {r.new_score.toFixed(4)}</span>
                <span>Fee: ${r.switching_cost_usd.toFixed(4)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
