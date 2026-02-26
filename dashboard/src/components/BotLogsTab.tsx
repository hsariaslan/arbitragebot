import { useState, useMemo, useRef, useEffect } from 'react';
import type { BotLogEntry } from '../types';
import ExportLogsModal from './ExportLogsModal';

interface BotLogsTabProps {
  logs: BotLogEntry[];
  sendWithCallback: (msg: object, callback: (data: any) => void) => void;
  uptimeSeconds: number;
}

const LEVEL_OPTIONS = [
  { value: 'all', label: 'All Levels' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
];

const COMPONENT_OPTIONS = [
  { value: 'all', label: 'All Components' },
  { value: 'Monitor', label: 'Monitor' },
  { value: 'Optimizer', label: 'Optimizer' },
  { value: 'Balance', label: 'Balance' },
  { value: 'Binance', label: 'Binance' },
  { value: 'OKX', label: 'OKX' },
  { value: 'Bybit', label: 'Bybit' },
  { value: 'Bitget', label: 'Bitget' },
  { value: 'KuCoin', label: 'KuCoin' },
  { value: 'MEXC', label: 'MEXC' },
  { value: 'Gate', label: 'Gate.io' },
  { value: 'Dashboard', label: 'Dashboard' },
  { value: 'Auth', label: 'Auth' },
  { value: 'Email', label: 'Email' },
  { value: 'Settings', label: 'Settings' },
  { value: 'Fee', label: 'Fee' },
  { value: 'Transfer', label: 'Transfer' },
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

function applyBotLogFilters(logs: BotLogEntry[], level: string, component: string, search: string): BotLogEntry[] {
  let result = logs;
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

export default function BotLogsTab({ logs, sendWithCallback, uptimeSeconds }: BotLogsTabProps) {
  const [levelFilter, setLevelFilter] = useState('all');
  const [componentFilter, setComponentFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const [showExportModal, setShowExportModal] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(
    () => applyBotLogFilters(logs, levelFilter, componentFilter, search),
    [logs, levelFilter, componentFilter, search]
  );

  const hasActiveFilters = levelFilter !== 'all' || componentFilter !== 'all' || search.trim() !== '';
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
        <span className="text-xs text-slate-500">{logs.length} total entries</span>
      </div>

      {/* Filters row */}
      <div className="flex items-center gap-3 flex-wrap">
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
          {COMPONENT_OPTIONS.map(opt => (
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
            {logs.length === 0 ? 'No bot logs yet' : 'No matching log entries'}
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
