import type { Portfolio, Simulation, ProfitStats } from '../types';

interface StatsCardsProps {
  portfolio: Portfolio;
  simulation: Simulation;
  profitStats: ProfitStats;
}

function PnlValue({ value, prefix = '$' }: { value: number; prefix?: string }) {
  const color = value >= 0 ? 'text-emerald-400' : 'text-red-400';
  const sign = value >= 0 ? '+' : '';
  return <span className={color}>{sign}{prefix}{value.toFixed(2)}</span>;
}

export default function StatsCards({ portfolio, simulation, profitStats }: StatsCardsProps) {
  const cards = [
    {
      title: 'Portfolio',
      main: `$${portfolio.total_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
      sub: <PnlValue value={portfolio.net_pnl} />,
      subLabel: 'P&L',
      accent: 'border-blue-500',
    },
    {
      title: 'Trades',
      main: simulation.total_trades.toLocaleString(),
      sub: <span className="text-slate-300">{simulation.trades_per_minute}/min</span>,
      subLabel: 'Rate',
      accent: 'border-emerald-500',
    },
    {
      title: 'Trade Profit',
      main: <PnlValue value={portfolio.trading_pnl} />,
      sub: <span className="text-amber-400">-${portfolio.transfer_fees.toFixed(2)} fees</span>,
      subLabel: 'Net',
      accent: 'border-cyan-500',
    },
    {
      title: 'Net $/hr',
      main: <PnlValue value={profitStats.session_hourly_rate} />,
      sub: <PnlValue value={profitStats.net_profit} />,
      subLabel: 'Net Total',
      accent: profitStats.is_profitable ? 'border-emerald-500' : 'border-red-500',
    },
  ];

  return (
    <div className="grid grid-cols-4 gap-4">
      {cards.map((card) => (
        <div key={card.title} className={`bg-slate-800/50 rounded-lg p-4 border-l-2 ${card.accent}`}>
          <div className="text-xs text-slate-400 uppercase tracking-wider mb-1">{card.title}</div>
          <div className="text-2xl font-bold text-white mb-1">{card.main}</div>
          <div className="text-sm">
            <span className="text-slate-500 mr-1">{card.subLabel}:</span>
            {card.sub}
          </div>
        </div>
      ))}
    </div>
  );
}
