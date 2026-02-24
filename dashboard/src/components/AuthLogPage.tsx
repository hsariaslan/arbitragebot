import { useState, useMemo } from 'react';
import type { AuthLogEntry } from '../types';
import ExportLogsModal from './ExportLogsModal';

interface AuthLogPageProps {
  authLogs: AuthLogEntry[];
  sendWithCallback: (msg: object, callback: (data: any) => void) => void;
  uptimeSeconds: number;
}

const EVENT_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  login_success: { bg: 'bg-emerald-500/20', text: 'text-emerald-400', label: 'Login Success' },
  login_failed: { bg: 'bg-red-500/20', text: 'text-red-400', label: 'Login Failed' },
  blocked: { bg: 'bg-red-600/20', text: 'text-red-300', label: 'Blocked' },
  logout: { bg: 'bg-amber-500/20', text: 'text-amber-400', label: 'Logout' },
  ip_denied: { bg: 'bg-orange-500/20', text: 'text-orange-400', label: 'IP Denied' },
  reconnected: { bg: 'bg-blue-500/20', text: 'text-blue-400', label: 'Reconnected' },
};

const FILTER_OPTIONS = [
  { value: 'all', label: 'All Events' },
  { value: 'login_success', label: 'Login Success' },
  { value: 'login_failed', label: 'Login Failed' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'logout', label: 'Logout' },
  { value: 'ip_denied', label: 'IP Denied' },
  { value: 'reconnected', label: 'Reconnected' },
];

function formatTimestamp(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

function formatFullTimestampUTC(ts: number): string {
  const d = new Date(ts * 1000);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

function applyAuthFilters(logs: AuthLogEntry[], filter: string, search: string): AuthLogEntry[] {
  let result = logs;
  if (filter !== 'all') {
    result = result.filter(l => l.event === filter);
  }
  if (search.trim()) {
    const q = search.trim().toLowerCase();
    result = result.filter(l =>
      l.ip.toLowerCase().includes(q) ||
      l.username.toLowerCase().includes(q) ||
      l.browser.toLowerCase().includes(q) ||
      l.os.toLowerCase().includes(q)
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

function escapeCSV(value: string): string {
  if (value.includes(',') || value.includes('"') || value.includes('\n')) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

export default function AuthLogPage({ authLogs, sendWithCallback, uptimeSeconds }: AuthLogPageProps) {
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [showExportModal, setShowExportModal] = useState(false);

  const filtered = useMemo(() => {
    const reversed = [...authLogs].reverse(); // newest first
    return applyAuthFilters(reversed, filter, search);
  }, [authLogs, filter, search]);

  const hasActiveFilters = filter !== 'all' || search.trim() !== '';
  const sessionStart = Math.floor(Date.now() / 1000) - uptimeSeconds;

  const handleExport = (start: number, end: number, useFilters: boolean) => {
    sendWithCallback({ type: 'export_auth_logs', start, end }, (data: any) => {
      let entries: AuthLogEntry[] = data.logs || [];
      if (useFilters) {
        entries = applyAuthFilters(entries, filter, search);
      }
      const header = 'Time (UTC),Event,IP,Username,Browser,OS,Details';
      const rows = entries.map(e =>
        [
          formatFullTimestampUTC(e.timestamp),
          e.event,
          e.ip,
          escapeCSV(e.username || ''),
          escapeCSV(e.browser || ''),
          escapeCSV(e.os || ''),
          escapeCSV(e.details || ''),
        ].join(',')
      );
      const ts = new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-');
      downloadFile(`auth-logs-${ts}.csv`, [header, ...rows].join('\n'), 'text/csv');
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Auth Log</h2>
        <span className="text-xs text-slate-500">{authLogs.length} total events</span>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <select
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500"
        >
          {FILTER_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by IP, username, browser..."
          className="bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500 placeholder-slate-500 w-64"
        />
        <button
          onClick={() => setShowExportModal(true)}
          className="px-3 py-1.5 rounded-lg text-sm font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
        >
          Export Logs
        </button>
        <span className="text-xs text-slate-500 ml-auto">{filtered.length} shown</span>
      </div>

      {/* Table */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400 text-xs">
                <th className="text-left px-4 py-2.5 font-medium">Time</th>
                <th className="text-left px-4 py-2.5 font-medium">Event</th>
                <th className="text-left px-4 py-2.5 font-medium">IP</th>
                <th className="text-left px-4 py-2.5 font-medium">Username</th>
                <th className="text-left px-4 py-2.5 font-medium">Password</th>
                <th className="text-left px-4 py-2.5 font-medium">Browser</th>
                <th className="text-left px-4 py-2.5 font-medium">OS</th>
                <th className="text-left px-4 py-2.5 font-medium">Details</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center text-slate-500 py-8">
                    {authLogs.length === 0 ? 'No auth events yet' : 'No matching events'}
                  </td>
                </tr>
              ) : (
                filtered.map((log, i) => {
                  const style = EVENT_STYLES[log.event] || { bg: 'bg-slate-500/20', text: 'text-slate-400', label: log.event };
                  return (
                    <tr key={i} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="px-4 py-2 text-slate-300 font-mono text-xs whitespace-nowrap">
                        {formatTimestamp(log.timestamp)}
                      </td>
                      <td className="px-4 py-2">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${style.bg} ${style.text}`}>
                          {style.label}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-slate-300 font-mono text-xs">{log.ip}</td>
                      <td className="px-4 py-2 text-slate-300 text-xs">{log.username || '—'}</td>
                      <td className="px-4 py-2 text-slate-300 font-mono text-xs">{log.password || '—'}</td>
                      <td className="px-4 py-2 text-slate-400 text-xs">{log.browser || '—'}</td>
                      <td className="px-4 py-2 text-slate-400 text-xs">{log.os || '—'}</td>
                      <td className="px-4 py-2 text-slate-500 text-xs">{log.details || '—'}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
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
