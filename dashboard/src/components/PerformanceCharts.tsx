import { useMemo } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, Legend,
} from 'recharts';
import type { DailyPnlEntry, HistoricalSymbolStats, HourlyPnlEntry, SymbolRanking, Trade, Transfer } from '../types';

interface PerformanceChartsProps {
  trades: Trade[];
  transfers: Transfer[];
  hourlyPnl: HourlyPnlEntry[];
  dailyPnl: DailyPnlEntry[];
  rankings?: SymbolRanking[];
  historicalRankings?: HistoricalSymbolStats[];
}

const TOOLTIP_STYLE = {
  contentStyle: { backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 8 },
  labelStyle: { color: '#94a3b8' },
  itemStyle: { color: '#e2e8f0' },
};

function formatBucketTick(ts: number, spanSeconds: number): string {
  const d = new Date(ts * 1000);
  const HH = d.getUTCHours().toString().padStart(2, '0');
  // Multi-day sessions: include MM-DD so duplicate hour-of-day labels are distinguishable.
  if (spanSeconds > 36 * 3600) {
    const mo = (d.getUTCMonth() + 1).toString().padStart(2, '0');
    const dd = d.getUTCDate().toString().padStart(2, '0');
    return `${mo}-${dd} ${HH}:00`;
  }
  return `${HH}:00`;
}

function formatBucketTooltip(ts: number): string {
  const d = new Date(ts * 1000);
  const mo = (d.getUTCMonth() + 1).toString().padStart(2, '0');
  const dd = d.getUTCDate().toString().padStart(2, '0');
  const HH = d.getUTCHours().toString().padStart(2, '0');
  const MM = d.getUTCMinutes().toString().padStart(2, '0');
  return `${d.getUTCFullYear()}-${mo}-${dd} ${HH}:${MM} UTC`;
}

const EXCHANGE_COLORS: Record<string, string> = {
  Binance: '#F0B90B',
  OKX: '#fff',
  Bybit: '#F7A600',
  MEXC: '#00B897',
  Bitget: '#00D4AA',
  KuCoin: '#24AE8F',
  'Gate.io': '#2354E6',
  Pionex: '#E95E30',
  Bitfinex: '#16B157',
};

export default function PerformanceCharts({
  trades,
  transfers,
  hourlyPnl,
  dailyPnl,
  rankings = [],
  historicalRankings = [],
}: PerformanceChartsProps) {
  // --- Cumulative P&L data ---
  const cumulativeData = useMemo(() => {
    if (trades.length === 0) return [];
    const bucketSize = 3600; // 1 hour
    const sortedTrades = [...trades].sort((a, b) => a.timestamp - b.timestamp);
    const sortedTransfers = [...transfers].sort((a, b) => a.timestamp - b.timestamp);

    const firstTs = Math.min(
      sortedTrades[0]?.timestamp ?? Infinity,
      sortedTransfers[0]?.timestamp ?? Infinity,
    );
    if (!isFinite(firstTs)) return [];

    const startBucket = Math.floor(firstTs / bucketSize) * bucketSize;
    const endBucket = Math.floor(Date.now() / 1000 / bucketSize) * bucketSize;

    const points: { bucket: number; tradingPnl: number; fees: number; netPnl: number }[] = [];
    let cumTrading = 0;
    let cumFees = 0;
    let tIdx = 0;
    let fIdx = 0;

    for (let bucket = startBucket; bucket <= endBucket; bucket += bucketSize) {
      const bucketEnd = bucket + bucketSize;
      while (tIdx < sortedTrades.length && sortedTrades[tIdx].timestamp < bucketEnd) {
        cumTrading += sortedTrades[tIdx].profit_usd;
        tIdx++;
      }
      while (fIdx < sortedTransfers.length && sortedTransfers[fIdx].timestamp < bucketEnd) {
        cumFees += sortedTransfers[fIdx].fee_usd;
        fIdx++;
      }
      points.push({
        bucket,
        tradingPnl: Number(cumTrading.toFixed(4)),
        fees: Number((-cumFees).toFixed(4)),
        netPnl: Number((cumTrading - cumFees).toFixed(4)),
      });
    }
    return points;
  }, [trades, transfers]);

  // Span used by the X-axis tick formatter to decide whether to include date.
  const cumulativeSpanSeconds = useMemo(() => {
    if (cumulativeData.length < 2) return 0;
    return cumulativeData[cumulativeData.length - 1].bucket - cumulativeData[0].bucket;
  }, [cumulativeData]);

  // --- Hourly P&L data (from backend, persisted) ---
  const hourlyData = useMemo(() => {
    if (hourlyPnl.length === 0) return [];
    return hourlyPnl.map(h => ({
      time: h.hour.slice(-2) + ':00',  // "YYYY-MM-DD_HH" -> "HH:00"
      pnl: h.pnl,
      fees: -h.fees,
      net: h.net,
      trades: h.trades,
    }));
  }, [hourlyPnl]);

  // --- Daily P&L data (from backend, persisted) ---
  const dailyData = useMemo(() => {
    if (dailyPnl.length === 0) return [];
    return dailyPnl.map(d => ({
      date: d.date.slice(5),  // "YYYY-MM-DD" -> "MM-DD"
      fullDate: d.date,
      pnl: d.pnl,
      fees: -d.fees,
      net: d.net,
      trades: d.trades,
    }));
  }, [dailyPnl]);

  // --- Exchange profit data ---
  const exchangeData = useMemo(() => {
    if (trades.length === 0) return [];
    const profits = new Map<string, number>();
    for (const t of trades) {
      profits.set(t.buy_exchange, (profits.get(t.buy_exchange) ?? 0) + t.profit_usd / 2);
      profits.set(t.sell_exchange, (profits.get(t.sell_exchange) ?? 0) + t.profit_usd / 2);
    }
    return [...profits.entries()]
      .map(([exchange, profit]) => ({ exchange, profit: Number(profit.toFixed(4)) }))
      .sort((a, b) => b.profit - a.profit);
  }, [trades]);

  // --- Top Symbols (Rolling, $/hr from current scoring window) ---
  const topRollingSymbols = useMemo(() => {
    if (!rankings.length) return [];
    return rankings
      .filter(r => r.est_hourly_profit > 0)
      .sort((a, b) => b.est_hourly_profit - a.est_hourly_profit)
      .slice(0, 10)
      .map(r => ({
        symbol: r.symbol.replace(/USDT$/, ''),
        profit: Number(r.est_hourly_profit.toFixed(4)),
        active: r.is_active,
        avgNetPct: Number(r.avg_profitable_net.toFixed(4)),
        frequency: Number((r.frequency * 100).toFixed(1)),
      }));
  }, [rankings]);

  // --- Top Symbols (Historical, cumulative session $) ---
  const topHistoricalSymbols = useMemo(() => {
    if (!historicalRankings.length) return [];
    return historicalRankings
      .filter(s => s.est_total_profit > 0)
      .sort((a, b) => b.est_total_profit - a.est_total_profit)
      .slice(0, 10)
      .map(s => ({
        symbol: s.symbol.replace(/USDT$/, ''),
        profit: Number(s.est_total_profit.toFixed(2)),
        hourlyRate: Number(s.est_hourly_rate.toFixed(4)),
        ticks: s.total_ticks,
        active: s.is_active,
      }));
  }, [historicalRankings]);

  // --- Top Symbol × Exchange-Pair combos (from executed trades) ---
  // Aggregates every executed trade by (symbol, buy_exchange, sell_exchange).
  // Answers: "which specific symbol+route makes the most money?"
  const topSymbolPairs = useMemo(() => {
    if (trades.length === 0) return [];
    const buckets = new Map<string, { symbol: string; buyExchange: string; sellExchange: string; trades: number; profit: number }>();
    for (const t of trades) {
      const key = `${t.symbol}|${t.buy_exchange}|${t.sell_exchange}`;
      const cur = buckets.get(key);
      if (cur) {
        cur.trades += 1;
        cur.profit += t.profit_usd;
      } else {
        buckets.set(key, {
          symbol: t.symbol,
          buyExchange: t.buy_exchange,
          sellExchange: t.sell_exchange,
          trades: 1,
          profit: t.profit_usd,
        });
      }
    }
    const EX_SHORT: Record<string, string> = {
      Binance: 'BIN', OKX: 'OKX', Bybit: 'BYB', MEXC: 'MEX',
      Bitget: 'BGT', KuCoin: 'KUC', 'Gate.io': 'GAT',
      Pionex: 'PIO', Bitfinex: 'BFX',
    };
    return [...buckets.values()]
      .sort((a, b) => b.profit - a.profit)
      .slice(0, 10)
      .map(b => ({
        label: `${b.symbol.replace(/USDT$/, '')}: ${EX_SHORT[b.buyExchange] ?? b.buyExchange}→${EX_SHORT[b.sellExchange] ?? b.sellExchange}`,
        symbol: b.symbol,
        buyExchange: b.buyExchange,
        sellExchange: b.sellExchange,
        trades: b.trades,
        profit: Number(b.profit.toFixed(4)),
        avgPerTrade: Number((b.profit / b.trades).toFixed(4)),
      }));
  }, [trades]);

  if (trades.length === 0 && hourlyPnl.length === 0) {
    return (
      <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Performance Charts</h3>
        <p className="text-slate-500 text-sm">No trades yet — charts will appear after the first trade.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3 sm:space-y-5">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 sm:gap-5">
        {/* Cumulative P&L */}
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Cumulative P&L</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={cumulativeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="bucket"
                type="number"
                domain={['dataMin', 'dataMax']}
                scale="time"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                tickFormatter={v => formatBucketTick(v, cumulativeSpanSeconds)}
                minTickGap={40}
              />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
              <Tooltip
                {...TOOLTIP_STYLE}
                labelFormatter={(label: number) => formatBucketTooltip(label)}
                formatter={(value: number | undefined, name: string | undefined) => [`$${(value ?? 0).toFixed(4)}`, name ?? '']}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
              <Line type="monotone" dataKey="tradingPnl" name="Trading P&L" stroke="#34d399" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="fees" name="Fees" stroke="#f87171" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
              <Line type="monotone" dataKey="netPnl" name="Net P&L" stroke="#60a5fa" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Hourly P&L (from persisted backend data) */}
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Hourly P&L (last 48h)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={hourlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="time" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
              <Tooltip
                {...TOOLTIP_STYLE}
                formatter={(value: number | undefined, name: string | undefined) => [`$${(value ?? 0).toFixed(4)}`, name ?? '']}
              />
              <Bar dataKey="pnl" name="Trading P&L">
                {hourlyData.map((entry, i) => (
                  <Cell key={i} fill={entry.pnl >= 0 ? '#34d399' : '#f87171'} fillOpacity={0.7} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Daily P&L (last 7 days) */}
      {dailyData.length > 0 && (
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Daily P&L (last 7 days)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={dailyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
              <Tooltip
                {...TOOLTIP_STYLE}
                labelFormatter={(label) => {
                  const entry = dailyData.find(d => d.date === String(label));
                  return entry ? `${entry.fullDate} (${entry.trades} trades)` : String(label);
                }}
                formatter={(value: number | undefined, name: string | undefined) => [`$${(value ?? 0).toFixed(4)}`, name ?? '']}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
              <Bar dataKey="pnl" name="Trading P&L">
                {dailyData.map((entry, i) => (
                  <Cell key={i} fill={entry.pnl >= 0 ? '#34d399' : '#f87171'} fillOpacity={0.7} />
                ))}
              </Bar>
              <Bar dataKey="fees" name="Fees">
                {dailyData.map((_entry, i) => (
                  <Cell key={i} fill="#f87171" fillOpacity={0.4} />
                ))}
              </Bar>
              <Bar dataKey="net" name="Net P&L">
                {dailyData.map((entry, i) => (
                  <Cell key={i} fill={entry.net >= 0 ? '#60a5fa' : '#fb923c'} fillOpacity={0.7} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Exchange Profit */}
      {exchangeData.length > 0 && (
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Exchange Profit Contribution</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={exchangeData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
              <YAxis type="category" dataKey="exchange" tick={{ fill: '#94a3b8', fontSize: 11 }} width={70} />
              <Tooltip
                {...TOOLTIP_STYLE}
                formatter={(value: number | undefined) => [`$${(value ?? 0).toFixed(4)}`, 'Profit']}
              />
              <Bar dataKey="profit" name="Profit">
                {exchangeData.map((entry, i) => (
                  <Cell key={i} fill={EXCHANGE_COLORS[entry.exchange] ?? '#8b5cf6'} fillOpacity={0.7} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Top Symbols by profit — Rolling vs Historical, side by side */}
      {(topRollingSymbols.length > 0 || topHistoricalSymbols.length > 0) && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 sm:gap-5">
          {/* Top Symbols — Rolling */}
          {topRollingSymbols.length > 0 && (
            <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
              <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
                Top Symbols (Rolling $/hr)
              </h3>
              <ResponsiveContainer width="100%" height={Math.max(220, topRollingSymbols.length * 28)}>
                <BarChart data={topRollingSymbols} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
                  <YAxis type="category" dataKey="symbol" tick={{ fill: '#94a3b8', fontSize: 11 }} width={68} />
                  <Tooltip
                    {...TOOLTIP_STYLE}
                    formatter={(_v: number | undefined, _n: string | undefined, ctx: { payload?: typeof topRollingSymbols[number] }) => {
                      const p = ctx?.payload;
                      if (!p) return ['', ''];
                      return [
                        `$${p.profit.toFixed(4)}/hr · avg ${p.avgNetPct.toFixed(3)}% · freq ${p.frequency}%`,
                        p.active ? 'Active' : 'Watching',
                      ];
                    }}
                  />
                  <Bar dataKey="profit" name="$/hr">
                    {topRollingSymbols.map((entry, i) => (
                      <Cell key={i} fill={entry.active ? '#34d399' : '#94a3b8'} fillOpacity={0.7} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Top Symbols — Historical */}
          {topHistoricalSymbols.length > 0 && (
            <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
              <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
                Top Symbols (Historical Cumulative $)
              </h3>
              <ResponsiveContainer width="100%" height={Math.max(220, topHistoricalSymbols.length * 28)}>
                <BarChart data={topHistoricalSymbols} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
                  <YAxis type="category" dataKey="symbol" tick={{ fill: '#94a3b8', fontSize: 11 }} width={68} />
                  <Tooltip
                    {...TOOLTIP_STYLE}
                    formatter={(_v: number | undefined, _n: string | undefined, ctx: { payload?: typeof topHistoricalSymbols[number] }) => {
                      const p = ctx?.payload;
                      if (!p) return ['', ''];
                      return [
                        `$${p.profit.toFixed(2)} cum · ${p.hourlyRate.toFixed(4)}/hr · ${p.ticks} ticks`,
                        p.active ? 'Active' : 'Inactive',
                      ];
                    }}
                  />
                  <Bar dataKey="profit" name="Total $">
                    {topHistoricalSymbols.map((entry, i) => (
                      <Cell key={i} fill={entry.active ? '#60a5fa' : '#a78bfa'} fillOpacity={0.7} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* Top Symbol × Exchange-Pair (from executed trades) */}
      {topSymbolPairs.length > 0 && (
        <div className="bg-slate-800/50 rounded-lg p-3 sm:p-5">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
            Top Symbol × Exchange-Pair Combos by Profit
          </h3>
          <p className="text-xs text-slate-500 mb-3">
            Aggregated from executed trades. Answers: which specific symbol+route generated the most profit?
          </p>
          <ResponsiveContainer width="100%" height={Math.max(240, topSymbolPairs.length * 30)}>
            <BarChart data={topSymbolPairs} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
              <YAxis type="category" dataKey="label" tick={{ fill: '#94a3b8', fontSize: 11 }} width={140} />
              <Tooltip
                {...TOOLTIP_STYLE}
                formatter={(_v: number | undefined, _n: string | undefined, ctx: { payload?: typeof topSymbolPairs[number] }) => {
                  const p = ctx?.payload;
                  if (!p) return ['', ''];
                  return [
                    `$${p.profit.toFixed(4)} total · ${p.trades} trades · $${p.avgPerTrade.toFixed(4)}/trade`,
                    `${p.symbol} ${p.buyExchange}→${p.sellExchange}`,
                  ];
                }}
              />
              <Bar dataKey="profit" name="Profit">
                {topSymbolPairs.map((entry, i) => (
                  <Cell key={i} fill={EXCHANGE_COLORS[entry.sellExchange] ?? '#8b5cf6'} fillOpacity={0.7} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
