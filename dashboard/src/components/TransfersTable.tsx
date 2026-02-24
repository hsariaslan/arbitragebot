import type { Transfer } from '../types';

interface TransfersTableProps {
  transfers: Transfer[];
  totalFees: number;
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('en-GB', { hour12: false });
}

const TYPE_LABELS: Record<string, { label: string; color: string }> = {
  internal_sell: { label: 'Sell→USDT', color: 'text-amber-300' },
  internal_buy: { label: 'USDT→Buy', color: 'text-blue-300' },
  external_usdt: { label: 'Ext USDT', color: 'text-purple-300' },
  external_crypto: { label: 'Ext Crypto', color: 'text-green-300' },
};

export default function TransfersTable({ transfers, totalFees }: TransfersTableProps) {
  return (
    <div className="bg-slate-800/50 rounded-lg overflow-hidden flex flex-col" style={{ maxHeight: '400px' }}>
      <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between shrink-0">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Transfers</h2>
        <span className="text-xs">
          Total fees: <span className="text-amber-400">${totalFees.toFixed(4)}</span>
        </span>
      </div>
      <div className="overflow-y-auto flex-1">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-800">
            <tr className="text-slate-400 uppercase">
              <th className="text-left px-3 py-2 font-medium">Time</th>
              <th className="text-left px-3 py-2 font-medium">Type</th>
              <th className="text-left px-3 py-2 font-medium">From</th>
              <th className="text-left px-3 py-2 font-medium">To</th>
              <th className="text-left px-3 py-2 font-medium">Symbol</th>
              <th className="text-right px-3 py-2 font-medium">Amount</th>
              <th className="text-right px-3 py-2 font-medium">Fee</th>
            </tr>
          </thead>
          <tbody>
            {transfers.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-slate-500">
                  No transfers yet
                </td>
              </tr>
            ) : (
              transfers.map((t, i) => {
                const typeInfo = TYPE_LABELS[t.type] || { label: t.type, color: 'text-slate-300' };
                return (
                  <tr key={i} className="border-t border-slate-700/30 hover:bg-slate-700/30">
                    <td className="px-3 py-1.5 text-slate-400 font-mono">{formatTime(t.timestamp)}</td>
                    <td className={`px-3 py-1.5 font-medium ${typeInfo.color}`}>{typeInfo.label}</td>
                    <td className="px-3 py-1.5 text-slate-300">{t.from_exchange}</td>
                    <td className="px-3 py-1.5 text-slate-300">{t.to_exchange}</td>
                    <td className="px-3 py-1.5 text-white">{t.symbol.replace('USDT', '')}</td>
                    <td className="px-3 py-1.5 text-right text-slate-300 font-mono">${t.amount_usd.toFixed(2)}</td>
                    <td className="px-3 py-1.5 text-right text-amber-400 font-mono">${t.fee_usd.toFixed(4)}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
