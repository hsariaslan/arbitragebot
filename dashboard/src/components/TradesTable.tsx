import type { Trade } from '../types';

interface TradesTableProps {
  trades: Trade[];
  totalPnl: number;
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('en-GB', { hour12: false });
}

export default function TradesTable({ trades, totalPnl }: TradesTableProps) {
  return (
    <div className="bg-slate-800/50 rounded-lg overflow-hidden flex flex-col" style={{ maxHeight: '400px' }}>
      <div className="px-3 sm:px-4 py-3 border-b border-slate-700 flex items-center justify-between shrink-0">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Recent Trades</h2>
        <span className="text-xs">
          Total P&L:{' '}
          <span className={totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>
            ${totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(4)}
          </span>
        </span>
      </div>
      <div className="overflow-y-auto overflow-x-auto flex-1">
        <table className="w-full text-xs min-w-[600px]">
          <thead className="sticky top-0 bg-slate-800">
            <tr className="text-slate-400 uppercase">
              <th className="text-left px-3 py-2 font-medium">Time</th>
              <th className="text-left px-3 py-2 font-medium">Symbol</th>
              <th className="text-left px-3 py-2 font-medium">Buy @</th>
              <th className="text-left px-3 py-2 font-medium">Sell @</th>
              <th className="text-right px-3 py-2 font-medium">Spread</th>
              <th className="text-right px-3 py-2 font-medium">Net</th>
              <th className="text-right px-3 py-2 font-medium">Profit</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-slate-500">
                  Waiting for trades...
                </td>
              </tr>
            ) : (
              trades.map((t, i) => (
                <tr key={i} className="border-t border-slate-700/30 hover:bg-slate-700/30">
                  <td className="px-3 py-1.5 text-slate-400 font-mono">{formatTime(t.timestamp)}</td>
                  <td className="px-3 py-1.5 text-white font-medium">{t.symbol.replace('USDT', '')}</td>
                  <td className="px-3 py-1.5 text-blue-300">{t.buy_exchange}</td>
                  <td className="px-3 py-1.5 text-orange-300">{t.sell_exchange}</td>
                  <td className="px-3 py-1.5 text-right text-slate-300 font-mono">
                    {t.spread_pct >= 0 ? '+' : ''}{t.spread_pct.toFixed(4)}%
                  </td>
                  <td className={`px-3 py-1.5 text-right font-mono ${t.net_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {t.net_pct >= 0 ? '+' : ''}{t.net_pct.toFixed(4)}%
                  </td>
                  <td className={`px-3 py-1.5 text-right font-mono ${t.profit_usd >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    ${t.profit_usd >= 0 ? '+' : ''}{t.profit_usd.toFixed(4)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
