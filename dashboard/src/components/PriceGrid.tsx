import type { PriceEntry } from '../types';

interface PriceGridProps {
  prices: Record<string, Record<string, PriceEntry>>;
}

export default function PriceGrid({ prices }: PriceGridProps) {
  const symbols = Object.keys(prices);
  if (symbols.length === 0) return null;

  // Collect all exchanges
  const exchangeSet = new Set<string>();
  for (const sym of symbols) {
    for (const ex of Object.keys(prices[sym])) {
      exchangeSet.add(ex);
    }
  }
  const exchanges = Array.from(exchangeSet);

  return (
    <div className="bg-slate-800/50 rounded-lg overflow-hidden">
      <div className="px-3 sm:px-4 py-3 border-b border-slate-700">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Live Prices</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 text-xs uppercase">
              <th className="text-left px-4 py-2 font-medium">Symbol</th>
              {exchanges.map(ex => (
                <th key={ex} className="text-center px-4 py-2 font-medium" colSpan={2}>{ex}</th>
              ))}
            </tr>
            <tr className="text-slate-500 text-xs">
              <th></th>
              {exchanges.map(ex => (
                <Fragment key={ex}>
                  <th className="text-right px-2 py-1 font-normal">Bid</th>
                  <th className="text-right px-2 py-1 font-normal">Ask</th>
                </Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {symbols.map(sym => {
              // Find best bid (highest) and best ask (lowest) across exchanges
              let bestBid = -Infinity;
              let bestAsk = Infinity;
              for (const ex of exchanges) {
                const p = prices[sym]?.[ex];
                if (p) {
                  if (p.bid > bestBid) bestBid = p.bid;
                  if (p.ask < bestAsk) bestAsk = p.ask;
                }
              }

              const decimals = bestBid > 100 ? 2 : bestBid > 1 ? 4 : 6;

              return (
                <tr key={sym} className="border-t border-slate-700/50 hover:bg-slate-700/30">
                  <td className="px-4 py-2 font-medium text-white">{sym.replace('USDT', '')}</td>
                  {exchanges.map(ex => {
                    const p = prices[sym]?.[ex];
                    if (!p) {
                      return (
                        <Fragment key={ex}>
                          <td className="px-2 py-2 text-right text-slate-600 font-mono">—</td>
                          <td className="px-2 py-2 text-right text-slate-600 font-mono">—</td>
                        </Fragment>
                      );
                    }
                    const isStale = p.age > 5;
                    const isBestBid = p.bid === bestBid;
                    const isBestAsk = p.ask === bestAsk;
                    return (
                      <Fragment key={ex}>
                        <td className={`px-2 py-2 text-right font-mono ${isStale ? 'text-yellow-600' : isBestBid ? 'text-emerald-400 font-semibold' : 'text-slate-300'}`}>
                          {p.bid.toFixed(decimals)}
                        </td>
                        <td className={`px-2 py-2 text-right font-mono ${isStale ? 'text-yellow-600' : isBestAsk ? 'text-emerald-400 font-semibold' : 'text-slate-300'}`}>
                          {p.ask.toFixed(decimals)}
                        </td>
                      </Fragment>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Need Fragment import
import { Fragment } from 'react';
