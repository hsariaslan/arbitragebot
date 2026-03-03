import { useMemo } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, Legend,
} from 'recharts';
import type { DailyPnlEntry, HourlyPnlEntry, Trade, Transfer } from '../types';

interface PerformanceChartsProps {
  trades: Trade[];
  transfers: Transfer[];
  hourlyPnl: HourlyPnlEntry[];
  dailyPnl: DailyPnlEntry[];
}

const TOOLTIP_STYLE = {
  contentStyle: { backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 8 },
  labelStyle: { color: '#94a3b8' },
  itemStyle: { color: '#e2e8f0' },
};

function formatHour(ts: number): string {
  const d = new Date(ts * 1000);
  return d.getUTCHours().toString().padStart(2, '0') + ':' + d.getUTCMinutes().toString().padStart(2, '0');
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

export default function PerformanceCharts({ trades, transfers, hourlyPnl, dailyPnl }: PerformanceChartsProps) {
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

    const points: { time: string; tradingPnl: number; fees: number; netPnl: number }[] = [];
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
        time: formatHour(bucket),
        tradingPnl: Number(cumTrading.toFixed(4)),
        fees: Number((-cumFees).toFixed(4)),
        netPnl: Number((cumTrading - cumFees).toFixed(4)),
      });
    }
    return points;
  }, [trades, transfers]);

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
              <XAxis dataKey="time" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
              <Tooltip
                {...TOOLTIP_STYLE}
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
    </div>
  );
}
