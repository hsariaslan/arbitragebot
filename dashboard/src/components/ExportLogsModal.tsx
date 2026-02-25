import { useState, useEffect } from 'react';

interface ExportLogsModalProps {
  open: boolean;
  onClose: () => void;
  onExport: (start: number, end: number, applyFilters: boolean) => void;
  sessionStart: number;
  hasActiveFilters: boolean;
}

function toUTCDatetimeLocal(ts: number): string {
  const d = new Date(ts * 1000);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

function fromUTCDatetimeLocal(value: string): number {
  // Parse as UTC (append Z to treat as UTC)
  return new Date(value + ':00Z').getTime() / 1000;
}

type Preset = '1h' | '6h' | 'today' | '1d' | 'session' | 'all' | 'custom';

const PRESETS: { value: Preset; label: string }[] = [
  { value: '1h', label: '1 Hour' },
  { value: '6h', label: '6 Hours' },
  { value: 'today', label: 'Today' },
  { value: '1d', label: '1 Day' },
  { value: 'session', label: 'Current Session' },
  { value: 'all', label: 'All' },
  { value: 'custom', label: 'Custom' },
];

export default function ExportLogsModal({ open, onClose, onExport, sessionStart, hasActiveFilters }: ExportLogsModalProps) {
  const [selectedPreset, setSelectedPreset] = useState<Preset | null>(null);
  const [applyFilters, setApplyFilters] = useState(false);
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');

  // Auto-check "Apply Filters" when user has active filters
  useEffect(() => {
    if (open) {
      setApplyFilters(hasActiveFilters);
      setSelectedPreset(null);
      const now = Math.floor(Date.now() / 1000);
      setCustomStart(toUTCDatetimeLocal(now - 3600));
      setCustomEnd(toUTCDatetimeLocal(now));
    }
  }, [open, hasActiveFilters]);

  if (!open) return null;

  const handleExport = () => {
    if (!selectedPreset) return;
    const now = Math.floor(Date.now() / 1000);
    let start = 0;
    let end = now;

    switch (selectedPreset) {
      case '1h': start = now - 3600; break;
      case '6h': start = now - 21600; break;
      case 'today': {
        const d = new Date();
        start = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) / 1000;
        break;
      }
      case '1d': start = now - 86400; break;
      case 'session': start = sessionStart; break;
      case 'all': start = 0; break;
      case 'custom':
        start = fromUTCDatetimeLocal(customStart);
        end = fromUTCDatetimeLocal(customEnd);
        break;
    }
    onExport(start, end, applyFilters);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 w-[420px] max-w-[90vw]" onClick={e => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-white mb-4">Export Logs</h3>

        {/* Preset buttons */}
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 mb-4">
          {PRESETS.map(p => (
            <button
              key={p.value}
              onClick={() => setSelectedPreset(p.value)}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                selectedPreset === p.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Custom date range */}
        {selectedPreset === 'custom' && (
          <div className="space-y-3 mb-4 p-3 bg-slate-900 rounded-lg border border-slate-700">
            <p className="text-xs text-amber-400 font-medium">Times are in UTC</p>
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400 w-12">Start:</label>
              <input
                type="datetime-local"
                value={customStart}
                onChange={e => setCustomStart(e.target.value)}
                className="flex-1 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400 w-12">End:</label>
              <input
                type="datetime-local"
                value={customEnd}
                onChange={e => setCustomEnd(e.target.value)}
                className="flex-1 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>
        )}

        {/* Apply Filters checkbox */}
        <label className="flex items-center gap-2 mb-4 cursor-pointer">
          <input
            type="checkbox"
            checked={applyFilters}
            onChange={e => setApplyFilters(e.target.checked)}
            className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500"
          />
          <span className="text-sm text-slate-300">Apply current filters</span>
          {hasActiveFilters && (
            <span className="text-xs text-blue-400">(filters active)</span>
          )}
        </label>

        {/* Actions */}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-700 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleExport}
            disabled={!selectedPreset}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              selectedPreset
                ? 'bg-blue-600 text-white hover:bg-blue-500'
                : 'bg-slate-700 text-slate-500 cursor-not-allowed'
            }`}
          >
            Export
          </button>
        </div>
      </div>
    </div>
  );
}
