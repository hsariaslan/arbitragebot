import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import type { Portfolio, Simulation, ProfitStats, UptimeInfo, ProxyUptimeInfo, AnomalyProtectionState, HedgeState, ConfigLite, RegistryView, CapacitySnapshot, ConfigAnomaly } from '../types';
import AnomalyDetailsModal, { classifyConfigSeverity } from './AnomalyDetailsModal';

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
  anomalyProtection?: AnomalyProtectionState;
  manualStopped?: boolean;
  manualStopTimestamp?: number;
  hedges?: HedgeState;
  onLogout: () => void;
  configsLite?: ConfigLite[];
  configsAnomaly?: ConfigAnomaly[];
  registry?: RegistryView;
  capacity?: CapacitySnapshot;
  onSendMessage?: (msg: object) => void;
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

const mobileBadge = "flex items-center gap-1 px-2 py-1 rounded-full bg-slate-800 border border-slate-700 active:bg-slate-700 transition-colors";

// Shared tooltip content components (reused by desktop hover and mobile popup)
function ProxyTooltipContent({ proxyUptimeInfo }: { proxyUptimeInfo: ProxyUptimeInfo }) {
  return (
    <>
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
    </>
  );
}

function UptimeTooltipContent({ uptimeInfo }: { uptimeInfo: UptimeInfo }) {
  return (
    <>
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
    </>
  );
}

function AnomalyTooltipContent({ anomalyProtection, manualStopped, manualStopTimestamp, portfolio }: {
  anomalyProtection?: AnomalyProtectionState;
  manualStopped?: boolean;
  manualStopTimestamp?: number;
  portfolio: Portfolio | null;
}) {
  if (manualStopped) {
    return (
      <>
        <div className="text-red-400 font-medium mb-2">Trading Manually Stopped</div>
        {manualStopTimestamp != null && manualStopTimestamp > 0 && (
          <div className="mb-1"><span className="text-slate-500">Stopped for:</span> <span className="text-white font-mono">{formatDuration(Date.now() / 1000 - manualStopTimestamp)}</span></div>
        )}
        {portfolio && (
          <>
            <div className="mb-1"><span className="text-slate-500">Portfolio:</span> <span className="text-white font-mono">${portfolio.total_value.toFixed(2)}</span></div>
            <div><span className="text-slate-500">Session P&L:</span> <PnlText value={portfolio.net_pnl} /></div>
          </>
        )}
      </>
    );
  }
  if (anomalyProtection?.emergency_triggered) {
    return (
      <>
        <div className="text-red-400 font-medium mb-2">Emergency Sell-All Triggered</div>
        <div className="text-slate-400 mb-2">{anomalyProtection.pause_reason}</div>
        {anomalyProtection.pause_timestamp > 0 && (
          <div className="mb-1"><span className="text-slate-500">Duration:</span> <span className="text-white font-mono">{formatDuration(Date.now() / 1000 - anomalyProtection.pause_timestamp)}</span></div>
        )}
        <div className="mb-1"><span className="text-slate-500">Drawdown:</span> <span className="text-red-400 font-mono">{anomalyProtection.current_drawdown_pct.toFixed(2)}%</span></div>
        <div className="text-amber-400 mt-2 font-medium">Requires manual resume</div>
      </>
    );
  }
  if (anomalyProtection?.paused) {
    return (
      <>
        <div className="text-red-400 font-medium mb-1">Trading Paused ({anomalyProtection.pause_layer})</div>
        <div className="text-slate-400 mb-2">{anomalyProtection.pause_reason}</div>
        {anomalyProtection.pause_timestamp > 0 && (
          <div className="mb-1"><span className="text-slate-500">Paused for:</span> <span className="text-white font-mono">{formatDuration(Date.now() / 1000 - anomalyProtection.pause_timestamp)}</span></div>
        )}
        <div className="mb-1"><span className="text-slate-500">Rolling P&L:</span> <span className="font-mono text-red-400">${anomalyProtection.rolling_pnl.toFixed(2)}</span> <span className="text-slate-600">/ threshold ${anomalyProtection.circuit_breaker_threshold.toFixed(2)}</span></div>
        <div className="mb-1"><span className="text-slate-500">Drawdown:</span> <span className="font-mono">{anomalyProtection.current_drawdown_pct.toFixed(2)}%</span> <span className="text-slate-600">/ threshold {anomalyProtection.drawdown_threshold_pct.toFixed(1)}%</span></div>
        <div className="mb-1"><span className="text-slate-500">Trades in window:</span> <span className="font-mono">{anomalyProtection.trades_in_window}</span> <span className="text-slate-600">({anomalyProtection.loss_rate.toFixed(1)}% loss rate)</span></div>
        {Object.keys(anomalyProtection.symbol_blocks).length > 0 && (
          <div className="mb-1"><span className="text-slate-500">Blocked symbols:</span> <span className="text-amber-400">{Object.keys(anomalyProtection.symbol_blocks).join(', ')}</span></div>
        )}
        {anomalyProtection.events.length > 0 && (
          <div className="border-t border-slate-700 pt-2 mt-2 space-y-1">
            <div className="text-slate-500 font-medium">Recent events:</div>
            {anomalyProtection.events.slice(-3).reverse().map((e, i) => (
              <div key={i} className="text-slate-400 truncate">{e.level}: {e.reason}</div>
            ))}
          </div>
        )}
      </>
    );
  }
  if (anomalyProtection?.warning_active) {
    return (
      <>
        <div className="text-amber-400 font-medium mb-1">Trade Size Reduced (x{anomalyProtection.trade_size_multiplier})</div>
        <div className="text-slate-400 mb-2">{anomalyProtection.warning_reason}</div>
        <div className="mb-1"><span className="text-slate-500">Rolling P&L:</span> <span className="font-mono text-amber-400">${anomalyProtection.rolling_pnl.toFixed(2)}</span> <span className="text-slate-600">/ threshold ${anomalyProtection.circuit_breaker_threshold.toFixed(2)}</span></div>
        <div className="mb-1"><span className="text-slate-500">Trades in window:</span> <span className="font-mono">{anomalyProtection.trades_in_window}</span> <span className="text-slate-600">({anomalyProtection.loss_rate.toFixed(1)}% loss rate)</span></div>
        <div><span className="text-slate-500">Drawdown:</span> <span className="font-mono">{anomalyProtection.current_drawdown_pct.toFixed(2)}%</span></div>
      </>
    );
  }
  if (anomalyProtection?.enabled) {
    return (
      <>
        <div className="text-emerald-400 font-medium mb-2">Anomaly Protection Active</div>
        <div className="mb-1"><span className="text-slate-500">Rolling P&L:</span> <span className="font-mono">${anomalyProtection.rolling_pnl.toFixed(2)}</span> <span className="text-slate-600">/ threshold ${anomalyProtection.circuit_breaker_threshold.toFixed(2)}</span></div>
        <div className="mb-1"><span className="text-slate-500">Peak portfolio:</span> <span className="font-mono">${anomalyProtection.peak_portfolio.toFixed(2)}</span></div>
        <div className="mb-1"><span className="text-slate-500">Drawdown:</span> <span className="font-mono">{anomalyProtection.current_drawdown_pct.toFixed(2)}%</span> <span className="text-slate-600">/ threshold {anomalyProtection.drawdown_threshold_pct.toFixed(1)}%</span></div>
        {Object.keys(anomalyProtection.symbol_blocks).length > 0 && (
          <div className="mb-1"><span className="text-slate-500">Blocked symbols:</span> <span className="text-amber-400">{Object.keys(anomalyProtection.symbol_blocks).join(', ')}</span></div>
        )}
        <div className="border-t border-slate-700 pt-2 mt-2">
          <span className="text-slate-500">Session:</span>{' '}
          <span className="text-slate-400">{anomalyProtection.total_pauses}p / {anomalyProtection.total_warnings}w / {anomalyProtection.total_symbol_blocks}sb</span>
        </div>
      </>
    );
  }
  return <div className="text-slate-500">Anomaly protection disabled</div>;
}

// Get anomaly status label and colors
function getAnomalyStatus(anomalyProtection?: AnomalyProtectionState, manualStopped?: boolean): { label: string; dotClass: string; textClass: string } {
  if (manualStopped) return { label: 'STOPPED', dotClass: 'bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.5)]', textClass: 'text-red-400' };
  if (anomalyProtection?.emergency_triggered) return { label: 'EMERGENCY', dotClass: 'bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.5)]', textClass: 'text-red-400' };
  if (anomalyProtection?.paused) return { label: 'PAUSED', dotClass: 'bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.5)] animate-pulse', textClass: 'text-red-400' };
  if (anomalyProtection?.warning_active) return { label: 'WARNING', dotClass: 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.5)] animate-pulse', textClass: 'text-amber-400' };
  if (anomalyProtection?.enabled) return { label: 'Protected', dotClass: 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.3)]', textClass: 'text-emerald-400' };
  return { label: 'Off', dotClass: 'bg-slate-500', textClass: 'text-slate-500' };
}

interface SeverityCounts {
  high: number; medium: number; low: number;
  stopped: number; ok: number; off: number;
  total: number;
}

function AnomalyHeaderBadge({
  severityCounts,
  singleAnomaly,
  manualStopped,
  onClick,
}: {
  severityCounts: SeverityCounts | null;
  singleAnomaly?: AnomalyProtectionState;
  manualStopped?: boolean;
  onClick: () => void;
}) {
  // Decide what to show in the badge. Priority: stopped → high → medium → low → ok → off.
  // Single-config fallback uses the legacy `singleAnomaly` prop when no
  // multi-config data is available.
  let labelParts: { color: string; dotClass: string; text: string; count?: number }[] = [];

  if (severityCounts && severityCounts.total > 0) {
    if (severityCounts.high > 0) {
      labelParts.push({
        color: 'text-rose-400',
        dotClass: 'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.6)]',
        text: 'EMERGENCY',
        count: severityCounts.high,
      });
    }
    if (severityCounts.medium > 0) {
      labelParts.push({
        color: 'text-amber-400',
        dotClass: 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.5)] animate-pulse',
        text: 'PAUSED',
        count: severityCounts.medium,
      });
    }
    if (severityCounts.low > 0) {
      labelParts.push({
        color: 'text-emerald-400',
        dotClass: 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]',
        text: 'WARN',
        count: severityCounts.low,
      });
    }
    if (severityCounts.stopped > 0) {
      labelParts.push({
        color: 'text-rose-400',
        dotClass: 'bg-rose-500',
        text: 'STOPPED',
        count: severityCounts.stopped,
      });
    }
    if (labelParts.length === 0) {
      // All healthy
      labelParts.push({
        color: 'text-emerald-400',
        dotClass: 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.3)]',
        text: severityCounts.off > 0 && severityCounts.ok === 0 ? 'AP Off' : 'AP Active',
      });
    }
  } else {
    // Single-config fallback (no configs_anomaly broadcast yet)
    if (manualStopped) {
      labelParts.push({ color: 'text-rose-400', dotClass: 'bg-rose-500', text: 'STOPPED' });
    } else if (singleAnomaly?.emergency_triggered) {
      labelParts.push({ color: 'text-rose-400', dotClass: 'bg-rose-500', text: 'EMERGENCY' });
    } else if (singleAnomaly?.paused) {
      labelParts.push({
        color: 'text-amber-400',
        dotClass: 'bg-amber-400 animate-pulse',
        text: 'PAUSED',
      });
    } else if (singleAnomaly?.warning_active) {
      labelParts.push({ color: 'text-emerald-400', dotClass: 'bg-emerald-400', text: 'WARN' });
    } else if (singleAnomaly?.enabled) {
      labelParts.push({ color: 'text-emerald-400', dotClass: 'bg-emerald-400', text: 'Protected' });
    } else {
      labelParts.push({ color: 'text-slate-500', dotClass: 'bg-slate-500', text: 'AP Off' });
    }
  }

  return (
    <button
      onClick={onClick}
      className="hidden sm:flex items-center gap-2 px-2 py-1 rounded hover:bg-slate-800/50 transition-colors cursor-pointer"
      title="Click for full anomaly protection details across all configs"
    >
      {labelParts.map((p, i) => (
        <span key={i} className="flex items-center gap-1">
          <span className={`w-2 h-2 rounded-full ${p.dotClass}`} />
          <span className={`text-xs font-medium ${p.color}`}>
            {p.text}{p.count !== undefined && ` (${p.count})`}
          </span>
        </span>
      ))}
    </button>
  );
}

function PrimaryConfigRows({ configsLite, registry, onSendMessage, capacity }: { configsLite?: ConfigLite[]; registry?: RegistryView; onSendMessage?: (msg: object) => void; capacity?: CapacitySnapshot }) {
  // Persisted collapse/expand state. Default: collapsed → only the default
  // (or first primary) row shows. Expanded: every primary config gets a row.
  const [expanded, setExpanded] = useState<boolean>(() => {
    try {
      return localStorage.getItem('arbitragebot_primary_rows_expanded') === '1';
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(
        'arbitragebot_primary_rows_expanded',
        expanded ? '1' : '0',
      );
    } catch {
      /* noop */
    }
  }, [expanded]);

  if (!configsLite || !registry || configsLite.length <= 1) return null;
  const primaries = configsLite.filter((l) => l.is_primary);
  const sweepWarn = capacity && capacity.severity !== 'ok';

  // Collapsed: show only the default config (fallback to first primary if
  // the default isn't primary). Expanded: show every primary in registry order.
  const visible = expanded
    ? primaries
    : primaries.length > 0
      ? [primaries.find((p) => p.is_default) ?? primaries[0]]
      : [];
  const hidden = primaries.length - visible.length;

  return (
    <>
      {sweepWarn && (
        <div className={`bg-slate-900 border-t border-slate-800 px-3 sm:px-6 py-1 text-xs flex items-center gap-2 ${capacity?.severity === 'critical' ? 'text-rose-400' : 'text-amber-400'}`}>
          <span className="font-bold">⚠ Capacity:</span>
          <span>
            {capacity?.severity === 'critical' ? 'CRITICAL' : 'WARN'} — sweep avg {capacity?.avg_sweep_ms.toFixed(0)}ms over {capacity?.config_count} configs (budget {capacity?.budget_ms.toFixed(0)}ms). Consider removing configs or upgrading the VPS.
          </span>
        </div>
      )}
      {primaries.length === 0 ? (
        <div className="hidden md:block bg-slate-900 border-t border-slate-800 px-6 py-1 text-xs text-slate-500">
          No primary config selected — pick one in <NavLink to="/settings" className="text-cyan-400 hover:underline">Settings → Config Groups</NavLink> to surface it here.
        </div>
      ) : (
        <>
          {visible.map((p) => (
            <PrimaryStatsBar key={p.id} lite={p} onSelect={() => onSendMessage?.({ type: 'select_config', config_id: p.id })} />
          ))}
          {primaries.length > 1 && (
            <button
              onClick={() => setExpanded((e) => !e)}
              className="hidden md:flex w-full items-center justify-center gap-2 px-6 py-1 bg-slate-900/80 border-t border-slate-800 text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 transition-colors"
              title={expanded ? 'Collapse — show only the default config' : `Expand — show all ${primaries.length} primary configs`}
            >
              <span className={`transition-transform ${expanded ? 'rotate-180' : ''}`}>▾</span>
              <span>
                {expanded
                  ? `Collapse primary rows (${primaries.length} shown)`
                  : `Show ${hidden} more primary config${hidden === 1 ? '' : 's'}`}
              </span>
            </button>
          )}
        </>
      )}
    </>
  );
}

function PrimaryStatsBar({ lite, onSelect }: { lite: ConfigLite; onSelect: () => void }) {
  const pnlColor = (v: number) => (v >= 0 ? 'text-emerald-400' : 'text-rose-400');
  const sign = (v: number) => (v >= 0 ? '+' : '');
  return (
    <button
      onClick={onSelect}
      className="hidden md:flex w-full items-center gap-6 px-6 py-1.5 bg-slate-800/50 border-t border-slate-700/50 text-xs hover:bg-slate-800 transition-colors text-left"
      title="Click to make this the active dashboard view"
    >
      {/* Star + config name (replaces the "Portfolio:" leading label, then we still show Portfolio) */}
      <div className="flex items-center gap-1.5 min-w-0">
        {lite.is_super_primary ? (
          <span className="text-amber-400 font-bold shrink-0" title="Super-Primary (real execution)">★★</span>
        ) : (
          <span className="text-purple-400 shrink-0" title="Primary">★</span>
        )}
        <span className="text-slate-500">Config:</span>
        <span className="text-white font-medium font-mono truncate">{lite.group_name}/{lite.name}</span>
      </div>
      <div className="h-3 w-px bg-slate-700 shrink-0" />
      {/* Portfolio | P&L */}
      <div className="flex items-center gap-1.5">
        <span className="text-slate-500">Portfolio:</span>
        <span className="text-white font-mono font-medium">
          ${lite.portfolio_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <span className="text-slate-600">|</span>
        <span className="text-slate-500">P&L:</span>
        <span className={`font-mono font-medium ${pnlColor(lite.net_pnl)}`}>
          {sign(lite.net_pnl)}${lite.net_pnl.toFixed(2)}
        </span>
      </div>
      <div className="h-3 w-px bg-slate-700 shrink-0" />
      {/* Trades */}
      <div className="flex items-center gap-1.5">
        <span className="text-slate-500">Trades:</span>
        <span className="text-white font-mono font-medium">{lite.trades_count.toLocaleString()}</span>
        <span className="text-slate-400 font-mono">({lite.trades_per_minute}/min)</span>
      </div>
      <div className="h-3 w-px bg-slate-700 shrink-0" />
      {/* Trade Profit */}
      <div className="flex items-center gap-1.5">
        <span className="text-slate-500">Trade Profit:</span>
        <span className={`font-mono font-medium ${pnlColor(lite.trading_pnl)}`}>
          {sign(lite.trading_pnl)}${lite.trading_pnl.toFixed(2)}
        </span>
      </div>
      <div className="h-3 w-px bg-slate-700 shrink-0" />
      {/* Net Profit */}
      <div className="flex items-center gap-1.5">
        <span className="text-slate-500">Net Profit:</span>
        <span className={`font-mono font-medium ${pnlColor(lite.net_pnl)}`}>
          {sign(lite.net_pnl)}${lite.net_pnl.toFixed(2)}
        </span>
      </div>
      <div className="h-3 w-px bg-slate-700 shrink-0" />
      {/* $/hr */}
      <div className="flex items-center gap-1.5">
        <span className="text-slate-500">$/hr:</span>
        <span className={`font-mono font-medium ${pnlColor(lite.session_hourly_rate)}`}>
          {sign(lite.session_hourly_rate)}${lite.session_hourly_rate.toFixed(2)}
        </span>
      </div>
      <div className="h-3 w-px bg-slate-700 shrink-0" />
      {/* Fees */}
      <div className="flex items-center gap-1.5">
        <span className="text-slate-500">Fees:</span>
        <span className="text-amber-400 font-mono font-medium">-${Math.abs(lite.transfer_fees).toFixed(2)}</span>
      </div>
      <div className="h-3 w-px bg-slate-700 shrink-0" />
      {/* Transfers */}
      <div className="flex items-center gap-1.5">
        <span className="text-slate-500">Transfers:</span>
        <span className={`font-mono font-medium ${lite.total_transfers > 0 ? 'text-amber-400' : 'text-slate-400'}`}>
          {lite.total_transfers}
        </span>
      </div>
      <div className="h-3 w-px bg-slate-700 shrink-0" />
      {/* Skipped */}
      <div className="flex items-center gap-1.5">
        <span className="text-slate-500">Skipped:</span>
        <span className={`font-mono font-medium ${lite.skipped_trades > 0 ? 'text-red-400' : 'text-slate-400'}`}>
          {lite.skipped_trades}
        </span>
      </div>
      {/* Hedge — only when enabled (mirrors Stats bar) */}
      {lite.hedge_enabled && (
        <>
          <div className="h-3 w-px bg-slate-700 shrink-0" />
          <div
            className="flex items-center gap-1.5"
            title={
              `Hedge mode: ${lite.hedge_mode} | Open: ${lite.hedge_open_count} | ` +
              `Notional: $${lite.hedge_total_notional_usd.toFixed(0)} | ` +
              `Unrealized: ${sign(lite.hedge_total_unrealized_pnl_usd)}$${lite.hedge_total_unrealized_pnl_usd.toFixed(2)} | ` +
              `Cum funding: ${sign(lite.hedge_cumulative_funding_usd)}$${lite.hedge_cumulative_funding_usd.toFixed(2)}` +
              (lite.hedge_safety_paused ? ' | OPENS PAUSED' : '')
            }
          >
            <span className="text-slate-500">Hedge:</span>
            <span className={`font-mono font-medium ${
              lite.hedge_mode === 'live' ? 'text-red-300'
              : lite.hedge_mode === 'testnet' ? 'text-amber-300'
              : 'text-slate-400'
            }`}>
              {lite.hedge_open_count}
            </span>
            <span className="text-slate-600">|</span>
            <span className={`font-mono font-medium ${pnlColor(lite.hedge_cumulative_funding_usd)}`}>
              {sign(lite.hedge_cumulative_funding_usd)}${lite.hedge_cumulative_funding_usd.toFixed(2)}
            </span>
            {lite.hedge_executor_errors > 0 && (
              <span className="text-red-400 font-mono ml-1">⚠{lite.hedge_executor_errors}</span>
            )}
          </div>
        </>
      )}
    </button>
  );
}

export default function Header({ connected, uptimeSeconds, uptimeInfo, connectedExchanges, totalExchanges, proxyUptimeInfo, portfolio, simulation, profitStats, anomalyProtection, manualStopped, manualStopTimestamp, hedges, onLogout, configsLite, configsAnomaly, registry, capacity, onSendMessage }: HeaderProps) {
  const [mobilePopup, setMobilePopup] = useState<string | null>(null);
  const [showAnomalyModal, setShowAnomalyModal] = useState(false);

  // Aggregate severity counts across all configs (multi-config). For
  // single-config, falls back to the legacy single state via configsAnomaly
  // synthesized by the dashboard.
  const severityCounts = (() => {
    if (!configsAnomaly || configsAnomaly.length === 0) return null;
    let high = 0, medium = 0, low = 0, stopped = 0, ok = 0, off = 0;
    for (const c of configsAnomaly) {
      const sev = classifyConfigSeverity(c);
      if (sev === 'high') high++;
      else if (sev === 'medium') medium++;
      else if (sev === 'low') low++;
      else if (sev === 'stopped') stopped++;
      else if (sev === 'ok') ok++;
      else off++;
    }
    return { high, medium, low, stopped, ok, off, total: configsAnomaly.length };
  })();

  // Connection state
  const proxyDown = connected && proxyUptimeInfo && !proxyUptimeInfo.is_connected;
  const connectionDot = !connected
    ? 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.5)] animate-pulse'
    : proxyDown
      ? 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.5)] animate-pulse'
      : 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]';
  const connectionText = !connected ? 'Reconnecting...' : proxyDown ? 'Disconnected (Zurich)' : 'Connected';
  const connectionColor = !connected ? 'text-amber-400' : proxyDown ? 'text-amber-400' : 'text-emerald-400';
  const anomalyStatus = getAnomalyStatus(anomalyProtection, manualStopped);

  return (
    <>
    <header className="bg-slate-900 border-b border-slate-700">
      {/* Top row: title, tabs, connection */}
      <div className="flex items-center justify-between px-3 sm:px-6 py-2">
        <div className="flex items-center gap-3 sm:gap-6">
          <h1 className="text-lg sm:text-xl font-bold text-white tracking-tight">ArbitrageBot</h1>
          <nav className="hidden md:flex gap-1">
            <NavLink to="/" end className={navLinkClass}>Dashboard</NavLink>
            <NavLink to="/wallets" className={navLinkClass}>Wallets</NavLink>
            <NavLink to="/rankings" className={({ isActive }) => navLinkClass({ isActive: isActive || window.location.hash.startsWith('#/rankings') })}>Rankings</NavLink>
            <NavLink to="/settings" className={({ isActive }) => navLinkClass({ isActive: isActive || window.location.hash.startsWith('#/settings') })}>Settings</NavLink>
            <NavLink to="/logs" className={({ isActive }) => navLinkClass({ isActive: isActive || window.location.hash.startsWith('#/logs') })}>Logs</NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-3 sm:gap-6 text-sm">
          {/* Desktop: Exchanges with hover tooltip */}
          <span className="text-slate-400 hidden sm:inline relative group/ex cursor-default">
            Exchanges: <span className="text-white font-medium">{connectedExchanges}/{totalExchanges}</span>
            {proxyUptimeInfo && (
              <div className="absolute left-0 top-full mt-2 w-72 bg-slate-800 border border-slate-600 rounded-lg shadow-xl p-3 text-xs text-slate-300 opacity-0 invisible group-hover/ex:opacity-100 group-hover/ex:visible transition-all duration-150 z-50">
                <ProxyTooltipContent proxyUptimeInfo={proxyUptimeInfo} />
              </div>
            )}
          </span>
          {/* Desktop: Sweep — orchestrator capacity (avg/last sweep ms,
              budget, config count). Color reflects severity: green ok,
              amber warn, rose critical. Hover shows full breakdown. */}
          {capacity && (
            <span className="text-slate-400 hidden sm:inline relative group/cap cursor-default">
              Sweep: <span className={`font-medium font-mono ${
                capacity.severity === 'critical' ? 'text-rose-400' :
                capacity.severity === 'warn' ? 'text-amber-400' :
                'text-emerald-400'
              }`}>{capacity.avg_sweep_ms.toFixed(0)}ms</span>
              <div className="absolute left-0 top-full mt-2 w-64 bg-slate-800 border border-slate-600 rounded-lg shadow-xl p-3 text-xs text-slate-300 opacity-0 invisible group-hover/cap:opacity-100 group-hover/cap:visible transition-all duration-150 z-50">
                <div className="font-medium text-white mb-2">Orchestrator capacity</div>
                <div className="space-y-1">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Avg sweep:</span>
                    <span className="font-mono">{capacity.avg_sweep_ms.toFixed(0)}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Last sweep:</span>
                    <span className="font-mono">{capacity.last_sweep_ms.toFixed(0)}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">p95 sweep:</span>
                    <span className="font-mono">{capacity.p95_sweep_ms.toFixed(0)}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Budget:</span>
                    <span className="font-mono">{capacity.budget_ms.toFixed(0)}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Configs:</span>
                    <span className="font-mono">{capacity.config_count}</span>
                  </div>
                  <div className="flex justify-between border-t border-slate-700 pt-1 mt-1">
                    <span className="text-slate-400">Status:</span>
                    <span className={`font-medium ${
                      capacity.severity === 'critical' ? 'text-rose-400' :
                      capacity.severity === 'warn' ? 'text-amber-400' :
                      'text-emerald-400'
                    }`}>{capacity.severity.toUpperCase()}</span>
                  </div>
                </div>
              </div>
            </span>
          )}
          {/* Desktop: Uptime with hover tooltip */}
          <span className="text-slate-400 hidden sm:inline relative group cursor-default">
            Uptime: <span className="text-white font-medium">{formatUptime(uptimeSeconds)}</span>
            {uptimeInfo && (
              <div className="absolute right-0 top-full mt-2 w-72 bg-slate-800 border border-slate-600 rounded-lg shadow-xl p-3 text-xs text-slate-300 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-150 z-50">
                <UptimeTooltipContent uptimeInfo={uptimeInfo} />
              </div>
            )}
          </span>
          {/* Connection status (visible on all sizes) */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${connectionDot}`} />
            <span className={`hidden sm:inline ${connectionColor}`}>
              {connectionText}
            </span>
          </div>
          {/* Desktop: Anomaly protection — multi-config aggregate severity badge.
              Click opens AnomalyDetailsModal with full per-config details. */}
          <AnomalyHeaderBadge
            severityCounts={severityCounts}
            singleAnomaly={anomalyProtection}
            manualStopped={manualStopped}
            onClick={() => setShowAnomalyModal(true)}
          />
          {/* placeholder for legacy block — replaced by AnomalyHeaderBadge */}
          {false && (
            <div className="hidden">{/* legacy single-config tooltip removed in v0.31 */}</div>
          )}
          <button
            onClick={onLogout}
            className="text-slate-500 hover:text-slate-300 text-sm transition-colors"
            title="Logout"
          >
            {/* Icon on mobile, text on desktop */}
            <svg className="sm:hidden w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            <span className="hidden sm:inline">Logout</span>
          </button>
        </div>
      </div>

      {/* Mobile info badges (visible only on small screens) */}
      <div className="sm:hidden flex items-center gap-2 px-3 py-1.5 border-t border-slate-700/50 overflow-x-auto">
        {/* Connection badge */}
        <button
          onClick={() => setMobilePopup(p => p === 'connection' ? null : 'connection')}
          className={mobileBadge}
        >
          <div className={`w-1.5 h-1.5 rounded-full ${connectionDot}`} />
          <span className={`text-[10px] font-medium ${connectionColor}`}>
            {!connected ? 'Reconnecting' : proxyDown ? 'Zurich' : 'Connected'}
          </span>
        </button>
        {/* Exchanges badge */}
        <button
          onClick={() => setMobilePopup(p => p === 'exchanges' ? null : 'exchanges')}
          className={mobileBadge}
        >
          <span className="text-[10px] text-slate-400">Ex</span>
          <span className="text-[10px] text-white font-mono font-medium">{connectedExchanges}/{totalExchanges}</span>
        </button>
        {/* Anomaly badge */}
        <button
          onClick={() => setMobilePopup(p => p === 'anomaly' ? null : 'anomaly')}
          className={mobileBadge}
        >
          <div className={`w-1.5 h-1.5 rounded-full ${anomalyStatus.dotClass}`} />
          <span className={`text-[10px] font-medium ${anomalyStatus.textClass}`}>{anomalyStatus.label}</span>
        </button>
        {/* Uptime badge */}
        <button
          onClick={() => setMobilePopup(p => p === 'uptime' ? null : 'uptime')}
          className={mobileBadge}
        >
          <svg className="w-2.5 h-2.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2" />
            <circle cx="12" cy="12" r="9" />
          </svg>
          <span className="text-[10px] text-white font-mono font-medium">{formatUptime(uptimeSeconds)}</span>
        </button>
      </div>

      {/* Mobile popup overlay */}
      {mobilePopup && (
        <div className="sm:hidden fixed inset-0 bg-black/50 z-50" onClick={() => setMobilePopup(null)}>
          <div
            className="absolute top-14 left-3 right-3 bg-slate-800 border border-slate-600 rounded-lg shadow-xl p-4 text-xs text-slate-300"
            onClick={e => e.stopPropagation()}
          >
            {mobilePopup === 'connection' && (
              <>
                <div className="font-medium text-white mb-2 flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${connectionDot}`} />
                  {connectionText}
                </div>
                {proxyUptimeInfo && <ProxyTooltipContent proxyUptimeInfo={proxyUptimeInfo} />}
                {!proxyUptimeInfo && <div className="text-slate-500">No proxy data available</div>}
              </>
            )}
            {mobilePopup === 'exchanges' && (
              <>
                <div className="font-medium text-white mb-2">Exchanges: {connectedExchanges}/{totalExchanges}</div>
                {proxyUptimeInfo && <ProxyTooltipContent proxyUptimeInfo={proxyUptimeInfo} />}
              </>
            )}
            {mobilePopup === 'anomaly' && (
              <AnomalyTooltipContent anomalyProtection={anomalyProtection} manualStopped={manualStopped} manualStopTimestamp={manualStopTimestamp} portfolio={portfolio} />
            )}
            {mobilePopup === 'uptime' && (
              <>
                <div className="font-medium text-white mb-2">Uptime: {formatUptime(uptimeSeconds)}</div>
                {uptimeInfo && <UptimeTooltipContent uptimeInfo={uptimeInfo} />}
              </>
            )}
          </div>
        </div>
      )}

      {/* Stats bar (desktop only) — hidden when multi-config is active because
          each primary config renders its own equivalent row below (the default
          row would duplicate one of them). */}
      {portfolio && simulation && profitStats && (configsLite?.length ?? 0) <= 1 && (
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
          {hedges && hedges.enabled && (
            <>
              <div className="h-3 w-px bg-slate-700" />
              <div
                className="flex items-center gap-1.5"
                title={
                  `Hedge mode: ${hedges.execution_mode} | Open: ${hedges.open_count} | ` +
                  `Notional: $${hedges.total_notional_usd.toFixed(0)} | ` +
                  `Unrealized: ${hedges.total_unrealized_pnl_usd >= 0 ? '+' : ''}$${hedges.total_unrealized_pnl_usd.toFixed(2)} | ` +
                  `Cum funding: ${hedges.cumulative_funding_usd >= 0 ? '+' : ''}$${hedges.cumulative_funding_usd.toFixed(2)}` +
                  (hedges.safety_paused ? ' | OPENS PAUSED' : '')
                }
              >
                <span className="text-slate-500">Hedge:</span>
                <span className={`font-mono font-medium ${
                  hedges.execution_mode === 'live' ? 'text-red-300'
                  : hedges.execution_mode === 'testnet' ? 'text-amber-300'
                  : 'text-slate-400'
                }`}>
                  {hedges.open_count}
                </span>
                <span className="text-slate-600">|</span>
                <PnlText value={hedges.cumulative_funding_usd} />
                {hedges.total_executor_errors > 0 && (
                  <span className="text-red-400 font-mono ml-1">⚠{hedges.total_executor_errors}</span>
                )}
              </div>
            </>
          )}
        </div>
      )}
      <PrimaryConfigRows
        configsLite={configsLite}
        registry={registry}
        onSendMessage={onSendMessage}
        capacity={capacity}
      />
    </header>

    {/* Mobile bottom tab bar */}
    <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-slate-900 border-t border-slate-700 z-50 flex justify-around px-2 py-2">
      <NavLink to="/" end className={mobileNavClass}>Home</NavLink>
      <NavLink to="/wallets" className={mobileNavClass}>Wallets</NavLink>
      <NavLink to="/rankings" className={({ isActive }) => mobileNavClass({ isActive: isActive || window.location.hash.startsWith('#/rankings') })}>Ranks</NavLink>
      <NavLink to="/settings" className={({ isActive }) => mobileNavClass({ isActive: isActive || window.location.hash.startsWith('#/settings') })}>Settings</NavLink>
      <NavLink to="/logs" className={({ isActive }) => mobileNavClass({ isActive: isActive || window.location.hash.startsWith('#/logs') })}>Logs</NavLink>
    </nav>

    {/* Anomaly details modal */}
    {showAnomalyModal && (
      <AnomalyDetailsModal
        configsAnomaly={configsAnomaly ?? []}
        onClose={() => setShowAnomalyModal(false)}
        onSendMessage={onSendMessage ?? (() => undefined)}
      />
    )}
    </>
  );
}
