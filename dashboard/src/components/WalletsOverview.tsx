import { useMemo, useState } from 'react';
import type { ConfigLite, RegistryView } from '../types';

interface Props {
  configsLite?: ConfigLite[];
  registry?: RegistryView;
  selectedConfigId?: string | null;
  onSendMessage: (msg: object) => void;
}

type SortKey = 'net_pnl' | 'session_hourly' | 'portfolio' | 'trades' | 'group' | 'name';

/**
 * Wallets Overview — single table of every config across every group,
 * live-updated from the broadcast (configsLite refreshes every tick).
 *
 * Sortable by any column; defaults to net P&L descending so the operator
 * sees winners first. Each row has a Primary checkbox that hot-applies via
 * `config_set_primary` — the bot picks up the change on the next sweep.
 */
export default function WalletsOverview({
  configsLite,
  registry,
  selectedConfigId,
  onSendMessage,
}: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('net_pnl');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const lite = configsLite ?? [];

  const rows = useMemo(() => {
    const sorted = [...lite].sort((a, b) => {
      let av: number | string = 0;
      let bv: number | string = 0;
      switch (sortKey) {
        case 'net_pnl':
          av = a.net_pnl;
          bv = b.net_pnl;
          break;
        case 'session_hourly':
          av = a.session_hourly_rate ?? a.hourly_rate;
          bv = b.session_hourly_rate ?? b.hourly_rate;
          break;
        case 'portfolio':
          av = a.portfolio_value;
          bv = b.portfolio_value;
          break;
        case 'trades':
          av = a.trades_count;
          bv = b.trades_count;
          break;
        case 'group':
          av = `${a.group_name}|${a.name}`;
          bv = `${b.group_name}|${b.name}`;
          break;
        case 'name':
          av = a.name;
          bv = b.name;
          break;
      }
      if (typeof av === 'string' && typeof bv === 'string') {
        const cmp = av.localeCompare(bv);
        return sortDir === 'asc' ? cmp : -cmp;
      }
      const cmp = (av as number) - (bv as number);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return sorted;
  }, [lite, sortKey, sortDir]);

  const onSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      // Numeric columns default to descending (highest first), text to ascending
      setSortDir(key === 'group' || key === 'name' ? 'asc' : 'desc');
    }
  };

  const togglePrimary = (cid: string, currently: boolean) => {
    onSendMessage({ type: 'config_set_primary', config_id: cid, value: !currently });
  };

  const onSelect = (cid: string) => {
    onSendMessage({ type: 'select_config', config_id: cid });
  };

  // Aggregate metrics for the header strip
  const totals = useMemo(() => {
    const t = lite.reduce(
      (acc, l) => {
        acc.portfolio += l.portfolio_value;
        acc.initial += l.initial_capital;
        acc.net_pnl += l.net_pnl;
        acc.trades += l.trades_count;
        return acc;
      },
      { portfolio: 0, initial: 0, net_pnl: 0, trades: 0 },
    );
    return t;
  }, [lite]);

  const fmt = (v: number, fixed = 2) =>
    v.toLocaleString('en-US', { minimumFractionDigits: fixed, maximumFractionDigits: fixed });
  const sign = (v: number) => (v >= 0 ? '+' : '');
  const pnlColor = (v: number) => (v > 0 ? 'text-emerald-400' : v < 0 ? 'text-rose-400' : 'text-slate-400');

  if (lite.length === 0) {
    return (
      <div className="text-slate-400 text-sm">
        No configs available — building bundles. Refresh in a few seconds.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Wallets Overview</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Every config across every group. Live-updated each broadcast tick.
            Toggle Primary to surface a config in the header rows. Click any row to
            switch the dashboard view.
          </p>
        </div>
        <div className="flex gap-4 text-xs">
          <Stat label="Configs" value={String(lite.length)} />
          <Stat label="Total Portfolio" value={`$${fmt(totals.portfolio)}`} />
          <Stat
            label="Total Net P&L"
            value={`${sign(totals.net_pnl)}$${fmt(totals.net_pnl)}`}
            color={pnlColor(totals.net_pnl)}
          />
          <Stat label="Total Trades" value={totals.trades.toLocaleString('en-US')} />
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-700 bg-slate-800/40">
        <table className="w-full text-sm">
          <thead className="bg-slate-800 text-xs uppercase tracking-wider text-slate-400">
            <tr>
              <th className="px-3 py-2 text-center w-16" title="Toggle Primary — primary configs surface in the header rows">
                Primary
              </th>
              <SortHeader label="Group / Config" sortKey="group" current={sortKey} dir={sortDir} onSort={onSort} align="left" />
              <SortHeader label="Portfolio" sortKey="portfolio" current={sortKey} dir={sortDir} onSort={onSort} align="right" />
              <SortHeader label="Net P&L" sortKey="net_pnl" current={sortKey} dir={sortDir} onSort={onSort} align="right" />
              <SortHeader label="$/hr" sortKey="session_hourly" current={sortKey} dir={sortDir} onSort={onSort} align="right" />
              <SortHeader label="Trades" sortKey="trades" current={sortKey} dir={sortDir} onSort={onSort} align="right" />
              <th className="px-3 py-2 text-right" title="Drawdown from session peak">
                DD%
              </th>
              <th className="px-3 py-2 text-center" title="Status flags">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((l) => {
              const isSelected = l.id === selectedConfigId;
              const hourly = l.session_hourly_rate ?? l.hourly_rate;
              return (
                <tr
                  key={l.id}
                  onClick={() => onSelect(l.id)}
                  className={`border-t border-slate-700/50 hover:bg-slate-700/30 cursor-pointer transition-colors ${
                    isSelected ? 'bg-cyan-950/30 border-l-2 border-l-cyan-500' : ''
                  }`}
                >
                  <td className="px-3 py-2 text-center" onClick={(e) => e.stopPropagation()}>
                    <label className="inline-flex items-center cursor-pointer" title={l.is_primary ? 'Primary — shown in header rows. Click to remove.' : 'Click to make this a primary config.'}>
                      <input
                        type="checkbox"
                        checked={!!l.is_primary}
                        onChange={() => togglePrimary(l.id, !!l.is_primary)}
                        className="w-4 h-4 accent-cyan-500 cursor-pointer"
                      />
                    </label>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1.5">
                      <span className="text-slate-500 text-xs">{l.group_name}</span>
                      <span className="text-slate-600">/</span>
                      <span className={isSelected ? 'text-cyan-300 font-medium' : 'text-slate-200'}>
                        {l.name}
                      </span>
                      {l.is_super_primary && (
                        <span className="ml-1 text-amber-400 text-xs" title="Super-primary — only this config can use non-simulation execution mode">
                          ★★
                        </span>
                      )}
                      {l.is_default && (
                        <span className="ml-1 px-1 rounded text-[9px] bg-blue-500/20 text-blue-300" title="Default config — loaded by the dashboard on first connection">
                          DEFAULT
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    <div>${fmt(l.portfolio_value)}</div>
                    <div className="text-[10px] text-slate-500">
                      spot ${fmt(l.spot_value ?? 0, 0)} · fut ${fmt(l.futures_reserve_value ?? 0, 0)}
                      <span className="text-slate-600 ml-1">/ ${fmt(l.initial_capital, 0)}</span>
                    </div>
                  </td>
                  <td className={`px-3 py-2 text-right font-mono ${pnlColor(l.net_pnl)}`}>
                    {sign(l.net_pnl)}${fmt(l.net_pnl)}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono ${pnlColor(hourly)}`}>
                    {sign(hourly)}${fmt(hourly)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-slate-300">
                    {l.trades_count.toLocaleString('en-US')}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono ${l.drawdown_pct > 5 ? 'text-amber-400' : 'text-slate-400'}`}>
                    {l.drawdown_pct.toFixed(1)}%
                  </td>
                  <td className="px-3 py-2 text-center text-xs">
                    <StatusFlags lite={l} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer hint about Primary semantics */}
      <p className="text-xs text-slate-500 italic">
        Primary configs appear as live rows in the header stats bar. The Default
        / Super-primary config has stricter rules (one across the registry,
        affects execution-mode inheritance) — manage those in{' '}
        <a href="#/settings" className="text-cyan-400 hover:underline">Settings → Config Groups</a>.
        {registry && (
          <span className="ml-2">
            Currently {rows.filter((r) => r.is_primary).length} primary across{' '}
            {registry.groups.length} group{registry.groups.length === 1 ? '' : 's'}.
          </span>
        )}
      </p>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="text-right">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`font-mono font-medium ${color ?? 'text-white'}`}>{value}</div>
    </div>
  );
}

function SortHeader({
  label,
  sortKey,
  current,
  dir,
  onSort,
  align = 'right',
}: {
  label: string;
  sortKey: SortKey;
  current: SortKey;
  dir: 'asc' | 'desc';
  onSort: (k: SortKey) => void;
  align?: 'left' | 'right';
}) {
  const active = current === sortKey;
  return (
    <th
      onClick={() => onSort(sortKey)}
      className={`px-3 py-2 cursor-pointer select-none hover:text-white transition-colors text-${align}`}
    >
      <span className={active ? 'text-white' : ''}>{label}</span>
      {active && <span className="ml-1 text-cyan-400">{dir === 'asc' ? '▲' : '▼'}</span>}
    </th>
  );
}

function StatusFlags({ lite }: { lite: ConfigLite }) {
  const flags: { label: string; color: string; title: string }[] = [];
  if (lite.anomaly_paused) flags.push({ label: 'PAUSED', color: 'bg-rose-500/20 text-rose-300', title: 'Anomaly protection paused this config' });
  if (lite.manual_stopped) flags.push({ label: 'STOPPED', color: 'bg-amber-500/20 text-amber-300', title: 'Operator manually stopped this config' });
  if (lite.hedge_reserve_status === 'emergency') flags.push({ label: 'FUT LOW', color: 'bg-red-500/20 text-red-300', title: `Binance Futures reserve below emergency: $${lite.futures_margin_balance_usd.toFixed(0)} / $${lite.futures_target_usd.toFixed(0)}` });
  if (lite.hedge_reserve_status === 'topup_needed') flags.push({ label: 'FUT TOP', color: 'bg-amber-500/20 text-amber-300', title: `Binance Futures reserve needs top-up: $${lite.futures_margin_balance_usd.toFixed(0)} / $${lite.futures_target_usd.toFixed(0)}` });
  if (lite.hedge_open_count > 0) flags.push({ label: `H${lite.hedge_open_count}`, color: 'bg-purple-500/20 text-purple-300', title: `${lite.hedge_open_count} hedge(s) open, notional $${lite.hedge_total_notional_usd.toFixed(0)}` });
  if (lite.execution_mode !== 'simulation') flags.push({ label: lite.execution_mode.toUpperCase(), color: 'bg-emerald-500/20 text-emerald-300', title: `Execution mode: ${lite.execution_mode}` });
  if (flags.length === 0) {
    return <span className="text-slate-600">·</span>;
  }
  return (
    <div className="flex gap-1 justify-center flex-wrap">
      {flags.map((f, i) => (
        <span key={i} title={f.title} className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${f.color}`}>
          {f.label}
        </span>
      ))}
    </div>
  );
}
