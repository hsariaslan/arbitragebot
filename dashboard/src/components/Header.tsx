import type { Portfolio, Simulation, ProfitStats } from '../types';

interface HeaderProps {
  connected: boolean;
  uptimeSeconds: number;
  connectedExchanges: number;
  totalExchanges: number;
  activeTab: 'dashboard' | 'ranking' | 'settings' | 'logs';
  onTabChange: (tab: 'dashboard' | 'ranking' | 'settings' | 'logs') => void;
  portfolio: Portfolio | null;
  simulation: Simulation | null;
  profitStats: ProfitStats | null;
  onLogout: () => void;
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function PnlText({ value, prefix = '$' }: { value: number; prefix?: string }) {
  const color = value >= 0 ? 'text-emerald-400' : 'text-red-400';
  const sign = value >= 0 ? '+' : '';
  return <span className={`font-mono font-medium ${color}`}>{sign}{prefix}{value.toFixed(2)}</span>;
}

export default function Header({ connected, uptimeSeconds, connectedExchanges, totalExchanges, activeTab, onTabChange, portfolio, simulation, profitStats, onLogout }: HeaderProps) {
  return (
    <>
    <header className="bg-slate-900 border-b border-slate-700">
      {/* Top row: title, tabs, connection */}
      <div className="flex items-center justify-between px-3 sm:px-6 py-2">
        <div className="flex items-center gap-3 sm:gap-6">
          <h1 className="text-lg sm:text-xl font-bold text-white tracking-tight">CoirnaBot</h1>
          <nav className="hidden md:flex gap-1">
            <button
              onClick={() => onTabChange('dashboard')}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'dashboard'
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              Dashboard
            </button>
            <button
              onClick={() => onTabChange('ranking')}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'ranking'
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              Rankings
            </button>
            <button
              onClick={() => onTabChange('settings')}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'settings'
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              Settings
            </button>
            <button
              onClick={() => onTabChange('logs')}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'logs'
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              Logs
            </button>
          </nav>
        </div>
        <div className="flex items-center gap-3 sm:gap-6 text-sm">
          <span className="text-slate-400 hidden sm:inline">
            Exchanges: <span className="text-white font-medium">{connectedExchanges}/{totalExchanges}</span>
          </span>
          <span className="text-slate-400 hidden sm:inline">
            Uptime: <span className="text-white font-medium">{formatUptime(uptimeSeconds)}</span>
          </span>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]' : 'bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.5)]'}`} />
            <span className={connected ? 'text-emerald-400' : 'text-red-400'}>
              {connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          <button
            onClick={onLogout}
            className="text-slate-500 hover:text-slate-300 text-sm transition-colors"
            title="Logout"
          >
            Logout
          </button>
        </div>
      </div>

      {/* Stats bar */}
      {portfolio && simulation && profitStats && (
        <div className="hidden md:flex items-center gap-6 px-6 py-1.5 bg-slate-800/50 border-t border-slate-700/50 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500">Portfolio:</span>
            <span className="text-white font-mono font-medium">
              ${portfolio.total_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-500">P&L:</span>
            <PnlText value={portfolio.net_pnl} />
          </div>
          <div className="h-3 w-px bg-slate-700" />
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500">Trades:</span>
            <span className="text-white font-mono font-medium">{simulation.total_trades.toLocaleString()}</span>
            <span className="text-slate-400 font-mono">({simulation.trades_per_minute}/min)</span>
          </div>
          <div className="h-3 w-px bg-slate-700" />
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500">Trade Profit:</span>
            <PnlText value={portfolio.trading_pnl} />
          </div>
          <div className="h-3 w-px bg-slate-700" />
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500">Net Profit:</span>
            <PnlText value={portfolio.trading_pnl - Math.abs(portfolio.transfer_fees)} />
          </div>
          <div className="h-3 w-px bg-slate-700" />
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500">$/hr:</span>
            <PnlText value={profitStats.session_hourly_rate} />
          </div>
          <div className="h-3 w-px bg-slate-700" />
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500">Fees:</span>
            <span className="text-amber-400 font-mono font-medium">-${Math.abs(portfolio.transfer_fees).toFixed(2)}</span>
          </div>
          <div className="h-3 w-px bg-slate-700" />
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500">Transfers:</span>
            <span className={`font-mono font-medium ${simulation.total_transfers > 0 ? 'text-amber-400' : 'text-slate-400'}`}>
              {simulation.total_transfers}
            </span>
          </div>
          <div className="h-3 w-px bg-slate-700" />
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500">Skipped:</span>
            <span className={`font-mono font-medium ${simulation.skipped_trades > 0 ? 'text-red-400' : 'text-slate-400'}`}>
              {simulation.skipped_trades}
            </span>
          </div>
        </div>
      )}
    </header>

    {/* Mobile bottom tab bar */}
    <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-slate-900 border-t border-slate-700 z-50 flex justify-around px-2 py-2">
      {(['dashboard', 'ranking', 'settings', 'logs'] as const).map(tab => (
        <button
          key={tab}
          onClick={() => onTabChange(tab)}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === tab
              ? 'bg-slate-700 text-white'
              : 'text-slate-500'
          }`}
        >
          {tab === 'dashboard' ? 'Home' : tab === 'ranking' ? 'Ranks' : tab.charAt(0).toUpperCase() + tab.slice(1)}
        </button>
      ))}
    </nav>
    </>
  );
}
