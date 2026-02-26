import type { Portfolio, Simulation, ProfitStats, DemoComparisonState } from '../types';

interface StatsCardsProps {
  portfolio: Portfolio;
  simulation: Simulation;
  profitStats: ProfitStats;
  demoComparison?: DemoComparisonState | null;
  uptimeSeconds: number;
}

function PnlValue({ value, prefix = '$' }: { value: number; prefix?: string }) {
  const color = value >= 0 ? 'text-emerald-400' : 'text-red-400';
  const sign = value >= 0 ? '+' : '';
  return <span className={color}>{sign}{prefix}{value.toFixed(2)}</span>;
}

function diffColor(pct: number): string {
  const abs = Math.abs(pct);
  if (abs < 1) return 'text-emerald-400';
  if (abs < 5) return 'text-yellow-400';
  return 'text-red-400';
}

function formatAge(timestamp: number): string {
  const age = Math.floor((Date.now() / 1000) - timestamp);
  if (age < 5) return 'just now';
  if (age < 60) return `${age}s ago`;
  if (age < 3600) return `${Math.floor(age / 60)}m ago`;
  return `${Math.floor(age / 3600)}h ago`;
}

export default function StatsCards({ portfolio, simulation, profitStats, demoComparison, uptimeSeconds }: StatsCardsProps) {
  const hasDemo = demoComparison?.enabled && Object.keys(demoComparison.exchanges).length > 0;
  const demoTotal = hasDemo ? demoComparison!.demo_portfolio_total : 0;
  const demoPnl = hasDemo ? demoTotal - portfolio.initial_investment : 0;
  const diff = hasDemo ? portfolio.total_value - demoTotal : 0;
  const diffPct = hasDemo && demoTotal > 0 ? (diff / demoTotal) * 100 : 0;

  const demoOnline = hasDemo
    ? Object.values(demoComparison!.exchanges).filter(e => !e.demo.error).length
    : 0;
  const demoConfigured = hasDemo ? demoComparison!.configured_exchanges.length : 0;
  const demoHourlyRate = hasDemo && uptimeSeconds > 60
    ? demoPnl / (uptimeSeconds / 3600)
    : 0;
  const simAccuracy = hasDemo ? Math.max(0, 100 - Math.abs(diffPct)) : 100;

  const cards = [
    {
      title: 'Portfolio (Sim)',
      main: `$${portfolio.total_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
      sub: <PnlValue value={portfolio.net_pnl} />,
      subLabel: 'P&L',
      accent: 'border-blue-500',
      extra: hasDemo ? (
        <div className="mt-2 pt-2 border-t border-slate-700/50">
          <div className="text-xs text-slate-400 uppercase tracking-wider mb-0.5">Demo</div>
          <div className="text-lg font-semibold text-white">${demoTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
          <div className="text-xs">
            <span className="text-slate-500 mr-1">P&L:</span>
            <PnlValue value={demoPnl} />
          </div>
          <div className={`text-xs mt-0.5 ${diffColor(diffPct)}`}>
            {'\u0394'} {diff >= 0 ? '+' : ''}{diff.toFixed(2)} ({diffPct >= 0 ? '+' : ''}{diffPct.toFixed(1)}%)
          </div>
        </div>
      ) : null,
    },
    {
      title: 'Trades',
      main: simulation.total_trades.toLocaleString(),
      sub: <span className="text-slate-300">{simulation.trades_per_minute}/min</span>,
      subLabel: 'Rate',
      accent: 'border-emerald-500',
      extra: hasDemo ? (
        <div className="mt-2 pt-2 border-t border-slate-700/50">
          <div className="text-xs">
            <span className="text-slate-500 mr-1">Demo:</span>
            <span className={demoOnline === demoConfigured ? 'text-emerald-400' : 'text-yellow-400'}>
              {demoOnline}/{demoConfigured} online
            </span>
          </div>
          <div className="text-xs mt-0.5">
            <span className="text-slate-500 mr-1">Fetched:</span>
            <span className="text-slate-300">
              {demoComparison!.last_fetch_time ? formatAge(demoComparison!.last_fetch_time) : 'never'}
            </span>
          </div>
        </div>
      ) : null,
    },
    {
      title: 'Trade Profit',
      main: <PnlValue value={portfolio.trading_pnl} />,
      sub: <span className="text-amber-400">-${Math.abs(portfolio.transfer_fees).toFixed(2)} fees</span>,
      subLabel: 'Net',
      accent: 'border-cyan-500',
      extra: hasDemo ? (
        <div className="mt-2 pt-2 border-t border-slate-700/50">
          <div className="text-xs">
            <span className="text-slate-500 mr-1">Demo P&L:</span>
            <PnlValue value={demoPnl} />
          </div>
          <div className="text-xs mt-0.5">
            <span className="text-slate-500 mr-1">Discrepancies:</span>
            <span className={demoComparison!.total_discrepancies > 0 ? 'text-yellow-400' : 'text-slate-300'}>
              {demoComparison!.total_discrepancies}
            </span>
          </div>
        </div>
      ) : null,
    },
    {
      title: 'Net $/hr',
      main: <PnlValue value={profitStats.session_hourly_rate} />,
      sub: <PnlValue value={profitStats.net_profit} />,
      subLabel: 'Net Total',
      accent: profitStats.is_profitable ? 'border-emerald-500' : 'border-red-500',
      extra: hasDemo ? (
        <div className="mt-2 pt-2 border-t border-slate-700/50">
          <div className="text-xs">
            <span className="text-slate-500 mr-1">Demo $/hr:</span>
            <PnlValue value={demoHourlyRate} />
          </div>
          <div className="text-xs mt-0.5">
            <span className="text-slate-500 mr-1">Accuracy:</span>
            <span className={simAccuracy >= 99 ? 'text-emerald-400' : simAccuracy >= 95 ? 'text-yellow-400' : 'text-red-400'}>
              {simAccuracy.toFixed(1)}%
            </span>
          </div>
        </div>
      ) : null,
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      {cards.map((card) => (
        <div key={card.title} className={`bg-slate-800/50 rounded-lg p-3 sm:p-4 border-l-2 ${card.accent}`}>
          <div className="text-xs text-slate-400 uppercase tracking-wider mb-1">{card.title}</div>
          <div className="text-xl sm:text-2xl font-bold text-white mb-1">{card.main}</div>
          <div className="text-sm">
            <span className="text-slate-500 mr-1">{card.subLabel}:</span>
            {card.sub}
          </div>
          {card.extra}
        </div>
      ))}
    </div>
  );
}
