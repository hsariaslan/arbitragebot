import { NavLink } from 'react-router-dom';
import type { Portfolio, Simulation, ProfitStats, UptimeInfo, ProxyUptimeInfo } from '../types';

interface HeaderProps {
  connected: boolean;
  uptimeSeconds: number;
  uptimeInfo?: UptimeInfo;
  connectedExchanges: number;
  totalExchanges: number;
  proxyUptimeInfo?: ProxyUptimeInfo;
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

function formatDateUTC(ts: number): string {
  const d = new Date(ts * 1000);
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${months[d.getUTCMonth()]} ${d.getUTCDate()}, ${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')} UTC`;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function PnlText({ value, prefix = '$' }: { value: number; prefix?: string }) {
  const color = value >= 0 ? 'text-emerald-400' : 'text-red-400';
  const sign = value >= 0 ? '+' : '';
  return <span className={`font-mono font-medium ${color}`}>{sign}{prefix}{value.toFixed(2)}</span>;
}

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
    isActive
      ? 'bg-slate-700 text-white'
      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
  }`;

const mobileNavClass = ({ isActive }: { isActive: boolean }) =>
  `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
    isActive ? 'bg-slate-700 text-white' : 'text-slate-500'
  }`;

export default function Header({ connected, uptimeSeconds, uptimeInfo, connectedExchanges, totalExchanges, proxyUptimeInfo, portfolio, simulation, profitStats, onLogout }: HeaderProps) {
  // Connection state: connected, reconnecting (disconnected but was authed), or disconnected
  const proxyDown = connected && proxyUptimeInfo && !proxyUptimeInfo.is_connected;
  const connectionDot = !connected
    ? 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.5)] animate-pulse'
    : proxyDown
      ? 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.5)] animate-pulse'
      : 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]';
  const connectionText = !connected ? 'Reconnecting...' : proxyDown ? 'Disconnected (Zurich)' : 'Connected';
  const connectionColor = !connected ? 'text-amber-400' : proxyDown ? 'text-amber-400' : 'text-emerald-400';

  return (
    <>
    <header className="bg-slate-900 border-b border-slate-700">
      {/* Top row: title, tabs, connection */}
      <div className="flex items-center justify-between px-3 sm:px-6 py-2">
        <div className="flex items-center gap-3 sm:gap-6">
          <h1 className="text-lg sm:text-xl font-bold text-white tracking-tight">CoirnaBot</h1>
          <nav className="hidden md:flex gap-1">
            <NavLink to="/" end className={navLinkClass}>Dashboard</NavLink>
            <NavLink to="/rankings" className={({ isActive }) => navLinkClass({ isActive: isActive || window.location.hash.startsWith('#/rankings') })}>Rankings</NavLink>
            <NavLink to="/settings" className={({ isActive }) => navLinkClass({ isActive: isActive || window.location.hash.startsWith('#/settings') })}>Settings</NavLink>
            <NavLink to="/logs" className={({ isActive }) => navLinkClass({ isActive: isActive || window.location.hash.startsWith('#/logs') })}>Logs</NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-3 sm:gap-6 text-sm">
          <span className="text-slate-400 hidden sm:inline relative group/ex cursor-default">
            Exchanges: <span className="text-white font-medium">{connectedExchanges}/{totalExchanges}</span>
            {proxyUptimeInfo && (
              <div className="absolute left-0 top-full mt-2 w-72 bg-slate-800 border border-slate-600 rounded-lg shadow-xl p-3 text-xs text-slate-300 opacity-0 invisible group-hover/ex:opacity-100 group-hover/ex:visible transition-all duration-150 z-50">
                <div className="mb-2 flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${proxyUptimeInfo.is_connected ? 'bg-emerald-400' : 'bg-amber-400 animate-pulse'}`} />
                  <span className="text-slate-500">Zurich Proxy:</span>{' '}
                  <span className={proxyUptimeInfo.is_connected ? 'text-emerald-400' : 'text-amber-400'}>
                    {proxyUptimeInfo.is_connected ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
                {proxyUptimeInfo.first_connected > 0 && (
                  <div className="mb-2">
                    <span className="text-slate-500">Running since:</span>{' '}
                    <span className="text-white">{formatDateUTC(proxyUptimeInfo.first_connected)}</span>
                  </div>
                )}
                <div className="mb-2">
                  <span className="text-slate-500">Total downtime:</span>{' '}
                  {proxyUptimeInfo.total_downtime > 0 ? (
                    <span className="text-amber-400">{formatDuration(proxyUptimeInfo.total_downtime)} ({proxyUptimeInfo.outage_count} outage{proxyUptimeInfo.outage_count !== 1 ? 's' : ''})</span>
                  ) : (
                    <span className="text-emerald-400">None</span>
                  )}
                </div>
                {proxyUptimeInfo.downtimes.length > 0 && (
                  <div className="border-t border-slate-700 pt-2 mt-2 space-y-1 max-h-40 overflow-y-auto">
                    <div className="text-slate-500 font-medium mb-1">Outage log:</div>
                    {[...proxyUptimeInfo.downtimes].reverse().map((d, i) => (
                      <div key={i} className="flex justify-between">
                        <span className="text-slate-400">{formatDateUTC(d.start)}</span>
                        <span className="text-amber-400">{formatDuration(d.duration)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </span>
          <span className="text-slate-400 hidden sm:inline relative group cursor-default">
            Uptime: <span className="text-white font-medium">{formatUptime(uptimeSeconds)}</span>
            {uptimeInfo && (
              <div className="absolute right-0 top-full mt-2 w-72 bg-slate-800 border border-slate-600 rounded-lg shadow-xl p-3 text-xs text-slate-300 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-150 z-50">
                <div className="mb-2">
                  <span className="text-slate-500">Running since:</span>{' '}
                  <span className="text-white">{formatDateUTC(uptimeInfo.first_start)}</span>
                </div>
                <div className="mb-2">
                  <span className="text-slate-500">Total downtime:</span>{' '}
                  {uptimeInfo.total_downtime > 0 ? (
                    <span className="text-amber-400">{formatDuration(uptimeInfo.total_downtime)} ({uptimeInfo.restart_count} restart{uptimeInfo.restart_count !== 1 ? 's' : ''})</span>
                  ) : (
                    <span className="text-emerald-400">None</span>
                  )}
                </div>
                {uptimeInfo.downtimes.length > 0 && (
                  <div className="border-t border-slate-700 pt-2 mt-2 space-y-1 max-h-40 overflow-y-auto">
                    <div className="text-slate-500 font-medium mb-1">Downtime log:</div>
                    {[...uptimeInfo.downtimes].reverse().map((d, i) => (
                      <div key={i} className="flex justify-between">
                        <span className="text-slate-400">{formatDateUTC(d.start)}</span>
                        <span className="text-amber-400">{formatDuration(d.duration)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </span>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${connectionDot}`} />
            <span className={connectionColor}>
              {connectionText}
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
            <PnlText value={profitStats.net_profit} />
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
      <NavLink to="/" end className={mobileNavClass}>Home</NavLink>
      <NavLink to="/rankings" className={({ isActive }) => mobileNavClass({ isActive: isActive || window.location.hash.startsWith('#/rankings') })}>Ranks</NavLink>
      <NavLink to="/settings" className={({ isActive }) => mobileNavClass({ isActive: isActive || window.location.hash.startsWith('#/settings') })}>Settings</NavLink>
      <NavLink to="/logs" className={({ isActive }) => mobileNavClass({ isActive: isActive || window.location.hash.startsWith('#/logs') })}>Logs</NavLink>
    </nav>
    </>
  );
}
