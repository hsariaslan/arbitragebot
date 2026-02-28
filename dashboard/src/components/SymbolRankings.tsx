import type { SymbolRanking } from '../types';

const EX_SHORT: Record<string, string> = {
  Binance: 'BIN', OKX: 'OKX', Bybit: 'BYB', Bitget: 'BGT', KuCoin: 'KUC', MEXC: 'MEX', 'Gate.io': 'GAT',
};
function shortEx(name: string) { return EX_SHORT[name] ?? name.slice(0, 3).toUpperCase(); }

interface SymbolRankingsProps {
  rankings: SymbolRanking[];
  warmupRemaining: number;
  autoRotate: boolean;
  discoveryMode?: boolean;
}

export default function SymbolRankings({ rankings, warmupRemaining, autoRotate, discoveryMode }: SymbolRankingsProps) {
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
                <tr key={r.symbol} className={`border-t border-slate-700/30 ${rowClass}`}>
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
                  <td className="px-2 py-1.5 text-center font-mono text-xs">
                    {r.dominant_buyers?.length > 0 ? (
                      <span className="text-cyan-400">
                        {r.dominant_buyers.map(shortEx).join(',')}
                        <span className="text-slate-500">→</span>
                        {r.dominant_sellers.map(shortEx).join(',')}
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
    </div>
  );
}
