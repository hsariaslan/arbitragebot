import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import type { BotLogEntry, RegistryView } from '../types';
import ExportLogsModal from './ExportLogsModal';

interface BotLogsTabProps {
  logs: BotLogEntry[];
  totalCount: number;
  sendWithCallback: (msg: object, callback: (data: any) => void) => void;
  uptimeSeconds: number;
  registry?: RegistryView;
}

type ScopeFilter = 'all' | 'universal' | 'group' | 'config';

const LEVEL_OPTIONS = [
  { value: 'all', label: 'All Levels' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
];

// Base components always shown in filter dropdown
const BASE_COMPONENTS = [
  { value: 'Monitor', label: 'Monitor' },
  { value: 'Optimizer', label: 'Optimizer' },
  { value: 'Balance', label: 'Balance' },
  { value: 'Binance', label: 'Binance' },
  { value: 'OKX', label: 'OKX' },
  { value: 'Bybit', label: 'Bybit' },
  { value: 'Bitget', label: 'Bitget' },
  { value: 'KuCoin', label: 'KuCoin' },
  { value: 'MEXC', label: 'MEXC' },
  { value: 'Gate.io', label: 'Gate.io' },
  { value: 'Pionex', label: 'Pionex' },
  { value: 'Bitfinex', label: 'Bitfinex' },
  { value: 'Latency', label: 'Latency' },
  { value: 'Dashboard', label: 'Dashboard' },
  { value: 'Auth', label: 'Auth' },
  { value: 'Email', label: 'Email' },
  { value: 'Settings', label: 'Settings' },
  { value: 'Config', label: 'Config' },
  { value: 'Fee', label: 'Fee' },
  { value: 'Transfer', label: 'Transfer' },
  { value: 'Candidate', label: 'Candidate' },
  { value: 'Trade', label: 'Trade' },
  { value: 'Rebalance', label: 'Rebalance' },
  { value: 'Anomaly', label: 'Anomaly' },
  { value: 'Session', label: 'Session' },
  { value: 'State', label: 'State' },
  { value: 'DemoCompare', label: 'DemoCompare' },
  { value: 'DemoTrade', label: 'DemoTrade' },
  { value: 'FeeValidation', label: 'FeeValidation' },
  { value: 'Uptime', label: 'Uptime' },
  { value: 'Funding', label: 'Funding' },
  { value: 'Hedge', label: 'Hedge' },
  { value: 'BinanceFutures', label: 'BinanceFutures' },
  { value: 'Inventory', label: 'Inventory' },
  { value: 'Momentum', label: 'Momentum' },
];

const LEVEL_STYLES: Record<string, { text: string }> = {
  INFO: { text: 'text-slate-300' },
  WARNING: { text: 'text-amber-300' },
  ERROR: { text: 'text-red-300' },
  DEBUG: { text: 'text-slate-500' },
};

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

function formatFullTimestamp(ts: number): string {
  const d = new Date(ts * 1000);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

function applyBotLogFilters(
  logs: BotLogEntry[],
  level: string,
  component: string,
  search: string,
  scope: ScopeFilter = 'all',
  groupId: string | null = null,
  configId: string | null = null,
): BotLogEntry[] {
  let result = logs;
  // Multi-config scope filter (v0.31.0-beta)
  if (scope === 'universal') {
    result = result.filter(l => !l.config_id);
  } else if (scope === 'group' && groupId) {
    result = result.filter(l => l.config_group_id === groupId);
  } else if (scope === 'config' && configId) {
    result = result.filter(l => l.config_id === configId);
  }
  if (level !== 'all') {
    result = result.filter(l => l.level === level);
  }
  if (component !== 'all') {
    result = result.filter(l => l.component === component);
  }
  if (search.trim()) {
    const q = search.trim().toLowerCase();
    result = result.filter(l =>
      l.message.toLowerCase().includes(q) ||
      l.component.toLowerCase().includes(q)
    );
  }
  return result;
}

function downloadFile(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function BotLogsTab({ logs, totalCount, sendWithCallback, uptimeSeconds, registry }: BotLogsTabProps) {
  const [levelFilter, setLevelFilter] = useState('all');
  const [componentFilter, setComponentFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const [showExportModal, setShowExportModal] = useState(false);
  const [allSessionLogs, setAllSessionLogs] = useState<BotLogEntry[] | null>(null);
  const [fetchingAll, setFetchingAll] = useState(false);
  // Multi-config scope cascading filter (v0.31.0-beta)
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>('all');
  const [groupFilter, setGroupFilter] = useState<string | null>(null);
  const [configFilter, setConfigFilter] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastFetchedTotal = useRef(0);

  const hasActiveFilters =
    levelFilter !== 'all' ||
    componentFilter !== 'all' ||
    search.trim() !== '' ||
    scopeFilter !== 'all';

  // Reset dependent dropdowns when scope or group changes
  useEffect(() => {
    if (scopeFilter !== 'group' && scopeFilter !== 'config') {
      setGroupFilter(null);
      setConfigFilter(null);
    } else if (scopeFilter === 'group') {
      setConfigFilter(null);
    }
  }, [scopeFilter]);

  useEffect(() => {
    setConfigFilter(null);
  }, [groupFilter]);

  // Build dynamic component options from base list + any extra components seen in logs
  const componentOptions = useMemo(() => {
    const baseValues = new Set(BASE_COMPONENTS.map(c => c.value));
    const extra: { value: string; label: string }[] = [];
    const source = allSessionLogs ?? logs;
    for (const entry of source) {
      if (entry.component && !baseValues.has(entry.component)) {
        baseValues.add(entry.component);
        extra.push({ value: entry.component, label: entry.component });
      }
    }
    extra.sort((a, b) => a.label.localeCompare(b.label));
    return [{ value: 'all', label: 'All Components' }, ...BASE_COMPONENTS, ...extra];
  }, [logs, allSessionLogs]);

  // When filter is active and we have more logs on server than in broadcast, fetch all session logs
  const fetchAllLogs = useCallback(() => {
    if (fetchingAll) return;
    setFetchingAll(true);
    sendWithCallback({ type: 'request_all_bot_logs' }, (data: any) => {
      const entries: BotLogEntry[] = data.logs || [];
      setAllSessionLogs(entries);
      lastFetchedTotal.current = entries.length;
      setFetchingAll(false);
    });
  }, [sendWithCallback, fetchingAll]);

  // Auto-fetch all logs when filter becomes active and there are more logs on server
  useEffect(() => {
    if (hasActiveFilters && totalCount > logs.length && !allSessionLogs) {
      fetchAllLogs();
    }
  }, [hasActiveFilters, totalCount, logs.length, allSessionLogs, fetchAllLogs]);

  // When filter is active, keep fetching if new logs arrived on server since last fetch
  useEffect(() => {
    if (hasActiveFilters && allSessionLogs && totalCount > lastFetchedTotal.current) {
      fetchAllLogs();
    }
  }, [hasActiveFilters, allSessionLogs, totalCount, fetchAllLogs]);

  // Clear cached all-logs when filter is removed (back to broadcast mode)
  useEffect(() => {
    if (!hasActiveFilters) {
      setAllSessionLogs(null);
      lastFetchedTotal.current = 0;
    }
  }, [hasActiveFilters]);

  // Use all session logs when filtering (if available), otherwise broadcast logs
  const sourceLogs = hasActiveFilters && allSessionLogs ? allSessionLogs : logs;

  const filtered = useMemo(
    () => applyBotLogFilters(sourceLogs, levelFilter, componentFilter, search, scopeFilter, groupFilter, configFilter),
    [sourceLogs, levelFilter, componentFilter, search, scopeFilter, groupFilter, configFilter]
  );

  // Cascading group → config dropdown options.
  //
  // Sourced from the live registry PLUS historical (group_id, config_id)
  // pairs harvested from log entries that no longer exist in the registry.
  // Without the historical pass, removing a config/group hides ALL filter
  // access to its prior log lines — the entries stay in memory + on disk
  // but the dropdown can't surface them. With it, removed groups/configs
  // appear in the dropdown tagged "(removed)" so the operator can still
  // grep the log history.
  type HistGroup = { id: string; name: string; configs: { id: string; name: string }[]; removed: boolean };
  const groupOptions = useMemo<HistGroup[]>(() => {
    const live: HistGroup[] = (registry?.groups ?? []).map((g) => ({
      id: g.id,
      name: g.name,
      configs: g.configs.map((c) => ({ id: c.id, name: c.name })),
      removed: false,
    }));
    const liveGroupIds = new Set(live.map((g) => g.id));
    const liveConfigIds = new Set(
      live.flatMap((g) => g.configs.map((c) => c.id)),
    );
    // Walk all in-memory log entries; collect any (group_id, config_id)
    // tuple whose group OR config isn't in the live registry.
    const histGroups = new Map<string, HistGroup>();
    for (const e of sourceLogs) {
      if (!e.config_group_id || !e.config_id) continue;
      const gname = e.config_group_name ?? '(unknown group)';
      const cname = e.config_name ?? '(unknown config)';
      const groupRemoved = !liveGroupIds.has(e.config_group_id);
      const configRemoved = !liveConfigIds.has(e.config_id);
      if (!groupRemoved && !configRemoved) continue;
      // Add the group entry (either historical or augmenting a live group
      // with a removed config).
      let target = histGroups.get(e.config_group_id);
      if (!target) {
        // If the group is live, copy its live configs first so the live
        // ones still appear, and we just add the missing config below.
        const liveGroup = live.find((g) => g.id === e.config_group_id);
        target = liveGroup
          ? {
              id: e.config_group_id,
              name: liveGroup.name,
              configs: [...liveGroup.configs],
              removed: false,
            }
          : { id: e.config_group_id, name: gname, configs: [], removed: true };
        histGroups.set(e.config_group_id, target);
      }
      if (configRemoved && !target.configs.find((c) => c.id === e.config_id)) {
        target.configs.push({ id: e.config_id, name: `${cname} (removed)` });
      }
    }
    // Final list: live groups (augmented if any of their configs were
    // removed) + fully-removed groups.
    const merged: HistGroup[] = live.map((g) => {
      const aug = histGroups.get(g.id);
      return aug ? { ...g, configs: aug.configs } : g;
    });
    for (const [gid, hg] of histGroups) {
      if (!liveGroupIds.has(gid)) merged.push({ ...hg, name: `${hg.name} (removed)` });
    }
    return merged;
  }, [registry, sourceLogs]);

  const configOptions = useMemo(() => {
    if (!groupFilter) return [];
    const g = groupOptions.find((g) => g.id === groupFilter);
    return g?.configs ?? [];
  }, [groupFilter, groupOptions]);

  const sessionStart = Math.floor(Date.now() / 1000) - uptimeSeconds;

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filtered, autoScroll]);

  const handleExport = (start: number, end: number, useFilters: boolean) => {
    sendWithCallback({ type: 'export_bot_logs', start, end }, (data: any) => {
      let entries: BotLogEntry[] = data.logs || [];
      if (useFilters) {
        entries = applyBotLogFilters(entries, levelFilter, componentFilter, search);
      }
      const lines = entries.map(e => {
        const comp = e.component ? `[${e.component}] ` : '';
        return `${formatFullTimestamp(e.timestamp)} [${e.level}] ${comp}${e.message}`;
      });
      const ts = new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-');
      downloadFile(`bot-logs-${ts}.log`, lines.join('\n'), 'text/plain');
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
        <h2 className="text-lg font-semibold text-white">Bot Logs</h2>
        <span className="text-xs text-slate-500">
          {hasActiveFilters && allSessionLogs
            ? `${filtered.length} matched / ${allSessionLogs.length} total session entries`
            : `${logs.length} recent / ${totalCount} total entries`}
        </span>
      </div>

      {/* Filters row */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Multi-config scope cascading filter (v0.31.0-beta).
            Shown when there's any live OR historical (removed-but-logged)
            group, so the operator can still grep removed configs' lines. */}
        {groupOptions.length > 0 && (
          <>
            <select
              value={scopeFilter}
              onChange={e => setScopeFilter(e.target.value as ScopeFilter)}
              className="bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500"
              title="Scope: All / Universal (shared subsystems) / Group / Config"
            >
              <option value="all">All Scopes</option>
              <option value="universal">Universal (shared)</option>
              <option value="group">By Group</option>
              <option value="config">By Config</option>
            </select>
            {(scopeFilter === 'group' || scopeFilter === 'config') && (
              <select
                value={groupFilter ?? ''}
                onChange={e => setGroupFilter(e.target.value || null)}
                className="bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="">— Select Group —</option>
                {groupOptions.map(g => (
                  <option key={g.id} value={g.id}>{g.name}</option>
                ))}
              </select>
            )}
            {scopeFilter === 'config' && groupFilter && (
              <select
                value={configFilter ?? ''}
                onChange={e => setConfigFilter(e.target.value || null)}
                className="bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="">— Select Config —</option>
                {configOptions.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            )}
          </>
        )}
        <select
          value={levelFilter}
          onChange={e => setLevelFilter(e.target.value)}
          className="bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500"
        >
          {LEVEL_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <select
          value={componentFilter}
          onChange={e => setComponentFilter(e.target.value)}
          className="bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500"
        >
          {componentOptions.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search log messages..."
          className="bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500 placeholder-slate-500 w-full sm:w-64"
        />
        <button
          onClick={() => setAutoScroll(!autoScroll)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            autoScroll
              ? 'bg-blue-600 text-white'
              : 'bg-slate-700 text-slate-400 hover:text-slate-200'
          }`}
          title={autoScroll ? 'Auto-scroll enabled' : 'Auto-scroll disabled'}
        >
          {autoScroll ? 'Auto-scroll ON' : 'Auto-scroll OFF'}
        </button>
        <button
          onClick={() => setShowExportModal(true)}
          className="px-3 py-1.5 rounded-lg text-sm font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
        >
          Export Logs
        </button>
        <span className="text-xs text-slate-500 sm:ml-auto">{filtered.length} shown</span>
      </div>

      {/* Log output (terminal-style) */}
      <div
        ref={scrollRef}
        className="bg-slate-900 rounded-xl border border-slate-700 overflow-auto font-mono text-xs"
        style={{ maxHeight: '70vh' }}
      >
        {filtered.length === 0 ? (
          <div className="text-center text-slate-500 py-8">
            {fetchingAll ? 'Loading full session logs...' :
             sourceLogs.length === 0 ? 'No bot logs yet' : 'No matching log entries'}
          </div>
        ) : (
          <div className="p-3 space-y-0.5">
            {filtered.map((log, i) => {
              const style = LEVEL_STYLES[log.level] || LEVEL_STYLES.INFO;
              return (
                <div
                  key={i}
                  className={`flex gap-2 px-2 py-0.5 rounded ${
                    log.level === 'ERROR' ? 'bg-red-500/10' : log.level === 'WARNING' ? 'bg-amber-500/5' : ''
                  }`}
                >
                  <span className="text-slate-500 whitespace-nowrap shrink-0">
                    {formatTime(log.timestamp)}
                  </span>
                  <span className={`whitespace-nowrap shrink-0 w-16 ${style.text}`}>
                    [{log.level}]
                  </span>
                  {log.config_group_name && log.config_name && (
                    <span
                      className="text-cyan-400 whitespace-nowrap shrink-0 text-[10px]"
                      title="Config that emitted this log"
                    >
                      [{log.config_group_name}/{log.config_name}]
                    </span>
                  )}
                  {log.component && (
                    <span className="text-blue-400 whitespace-nowrap shrink-0">
                      [{log.component}]
                    </span>
                  )}
                  <span className={style.text}>
                    {log.message}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <ExportLogsModal
        open={showExportModal}
        onClose={() => setShowExportModal(false)}
        onExport={handleExport}
        sessionStart={sessionStart}
        hasActiveFilters={hasActiveFilters}
      />
    </div>
  );
}
