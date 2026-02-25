import type { ExchangeBalance } from '../types';

interface BalanceTableProps {
  balances: Record<string, ExchangeBalance>;
  symbols: string[];
}

export default function BalanceTable({ balances, symbols }: BalanceTableProps) {
  const exchanges = Object.keys(balances);
  const totals = {
    usdt: 0,
    crypto: {} as Record<string, { qty: number; value: number }>,
    total: 0,
  };

  for (const sym of symbols) {
    totals.crypto[sym] = { qty: 0, value: 0 };
  }

  for (const ex of exchanges) {
    const b = balances[ex];
    totals.usdt += b.usdt;
    totals.total += b.total;
    for (const sym of symbols) {
      const c = b.crypto[sym];
      if (c) {
        totals.crypto[sym].qty += c.qty;
        totals.crypto[sym].value += c.value;
      }
    }
  }

  return (
    <div className="bg-slate-800/50 rounded-lg overflow-hidden">
      <div className="px-3 sm:px-4 py-3 border-b border-slate-700">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Exchange Balances</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 text-xs uppercase">
              <th className="text-left px-4 py-2 font-medium">Exchange</th>
              <th className="text-right px-4 py-2 font-medium">USDT</th>
              {symbols.map(sym => {
                const short = sym.replace('USDT', '');
                return [
                  <th key={`${sym}-qty`} className="text-right px-4 py-2 font-medium">{short} Qty</th>,
                  <th key={`${sym}-val`} className="text-right px-4 py-2 font-medium">{short} Val</th>,
                ];
              })}
              <th className="text-right px-4 py-2 font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {exchanges.map(ex => {
              const b = balances[ex];
              return (
                <tr key={ex} className="border-t border-slate-700/50 hover:bg-slate-700/30">
                  <td className="px-4 py-2 font-medium text-white">{ex}</td>
                  <td className="px-4 py-2 text-right text-emerald-300 font-mono">${b.usdt.toFixed(2)}</td>
                  {symbols.map(sym => {
                    const c = b.crypto[sym];
                    return [
                      <td key={`${sym}-qty`} className="px-4 py-2 text-right text-slate-300 font-mono">
                        {c ? c.qty.toFixed(4) : '—'}
                      </td>,
                      <td key={`${sym}-val`} className="px-4 py-2 text-right text-slate-300 font-mono">
                        ${c ? c.value.toFixed(2) : '0.00'}
                      </td>,
                    ];
                  })}
                  <td className="px-4 py-2 text-right text-white font-mono font-medium">${b.total.toFixed(2)}</td>
                </tr>
              );
            })}
            <tr className="border-t-2 border-slate-600 bg-slate-800/80 font-semibold">
              <td className="px-4 py-2 text-white">TOTAL</td>
              <td className="px-4 py-2 text-right text-emerald-300 font-mono">${totals.usdt.toFixed(2)}</td>
              {symbols.map(sym => {
                const c = totals.crypto[sym];
                return [
                  <td key={`${sym}-qty`} className="px-4 py-2 text-right text-slate-300 font-mono">
                    {c.qty.toFixed(4)}
                  </td>,
                  <td key={`${sym}-val`} className="px-4 py-2 text-right text-slate-300 font-mono">
                    ${c.value.toFixed(2)}
                  </td>,
                ];
              })}
              <td className="px-4 py-2 text-right text-white font-mono">${totals.total.toFixed(2)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
