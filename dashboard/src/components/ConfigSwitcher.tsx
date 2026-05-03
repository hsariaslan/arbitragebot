import { useState, useEffect } from 'react';
import type { RegistryView, ConfigLite } from '../types';

interface Props {
  registry?: RegistryView;
  configsLite?: ConfigLite[];
  selectedConfigId?: string | null;
  onSendMessage: (msg: object) => void;
  /** Page tag for localStorage scoping (dashboard/rankings) */
  scope?: string;
}

const STORAGE_KEY = 'arbitragebot_selected_config_id';

const formatUsd = (v: number, fixed = 2) =>
  v.toLocaleString('en-US', { minimumFractionDigits: fixed, maximumFractionDigits: fixed });

/**
 * Compact horizontal switcher shown at the top of Dashboard / Rankings pages.
 * Shows the currently-selected config + a dropdown of every config grouped
 * by their group, with "Make Default" affordance and per-config status dots.
 *
 * Selection is server-driven (via `select_config` WS message) so the heavy
 * state slice in the broadcast updates accordingly. The selected ID is
 * also mirrored to localStorage so a page refresh restores the same view.
 */
export default function ConfigSwitcher({
  registry,
  configsLite,
  selectedConfigId,
  onSendMessage,
  scope = 'dashboard',
}: Props) {
  const [open, setOpen] = useState(false);
  const lite = configsLite ?? [];
  const groups = registry?.groups ?? [];
  const selected = lite.find((l) => l.id === selectedConfigId);

  // On first load, restore selection from localStorage if it differs from
  // server-side current selection (e.g., user just opened a fresh tab).
  useEffect(() => {
    try {
      const stored = localStorage.getItem(`${STORAGE_KEY}_${scope}`);
      if (stored && registry && stored !== selectedConfigId) {
        const exists = registry.groups.some((g) =>
          g.configs.some((c) => c.id === stored),
        );
        if (exists) {
          onSendMessage({ type: 'select_config', config_id: stored });
        }
      }
    } catch {
      /* noop */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [registry?.groups.length]);

  // Mirror server-side selection to localStorage
  useEffect(() => {
    if (selectedConfigId) {
      try {
        localStorage.setItem(`${STORAGE_KEY}_${scope}`, selectedConfigId);
      } catch {
        /* noop */
      }
    }
  }, [selectedConfigId, scope]);

  if (!registry || groups.length === 0) return null;

  const handleSelect = (cid: string) => {
    onSendMessage({ type: 'select_config', config_id: cid });
    setOpen(false);
  };

  const handleMakeDefault = (cid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onSendMessage({ type: 'config_set_default', config_id: cid });
  };

  const totalConfigs = lite.length;
  if (totalConfigs <= 1) {
    // Single-config mode — no need to show a switcher
    return null;
  }

  return (
    <div className="relative mb-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-2 bg-slate-800/60 hover:bg-slate-700/60 border border-slate-700 rounded-md text-sm text-slate-200 transition-colors"
      >
        <span className="text-slate-500 text-xs">VIEWING</span>
        <span className="font-medium text-white">
          {selected?.group_name ?? '?'} → {selected?.name ?? 'Select…'}
        </span>
        {selected?.is_super_primary && (
          <span className="text-amber-400 text-xs">★★</span>
        )}
        {selected?.is_default && (
          <span className="text-blue-400 text-xs">DEFAULT</span>
        )}
        <span className="text-slate-500 text-xs">({totalConfigs} configs)</span>
        <span className={`transition-transform ${open ? 'rotate-180' : ''}`}>▾</span>
      </button>

      {open && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
          />
          {/* Dropdown panel */}
          <div className="absolute top-full left-0 mt-1 z-50 min-w-[420px] max-w-[600px] max-h-[70vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-lg shadow-2xl">
            {groups.map((g) => (
              <div key={g.id} className="border-b border-slate-800 last:border-b-0">
                <div className="px-3 py-1.5 bg-slate-800/60 text-xs text-slate-400 font-semibold uppercase tracking-wider flex items-center justify-between">
                  <span>{g.name}</span>
                  <span className="text-slate-500">${formatUsd(g.initial_capital, 0)}</span>
                </div>
                {g.configs.map((cfg) => {
                  const cl = lite.find((l) => l.id === cfg.id);
                  const isSelected = cfg.id === selectedConfigId;
                  const pnl = cl?.net_pnl ?? 0;
                  const status = cl?.anomaly_paused
                    ? 'paused'
                    : cl?.manual_stopped
                    ? 'stopped'
                    : 'running';
                  const dot =
                    status === 'paused'
                      ? 'bg-rose-500'
                      : status === 'stopped'
                      ? 'bg-amber-500'
                      : 'bg-emerald-500';
                  return (
                    <button
                      key={cfg.id}
                      onClick={() => handleSelect(cfg.id)}
                      className={`w-full flex items-center gap-2 px-3 py-2 text-left text-sm hover:bg-slate-800/80 transition-colors ${
                        isSelected ? 'bg-cyan-950/40 border-l-2 border-cyan-500' : ''
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full ${dot}`} />
                      <span className="flex-1 min-w-0 truncate">
                        <span className={isSelected ? 'text-cyan-300 font-medium' : 'text-slate-200'}>
                          {cfg.name}
                        </span>
                        {cfg.is_super_primary && (
                          <span className="ml-1.5 text-amber-400 text-[10px]">★★</span>
                        )}
                        {cfg.is_primary && !cfg.is_super_primary && (
                          <span className="ml-1.5 text-purple-400 text-[10px]">★</span>
                        )}
                        {cfg.is_default && (
                          <span className="ml-1.5 px-1 rounded text-[9px] bg-blue-500/20 text-blue-300">
                            DEFAULT
                          </span>
                        )}
                      </span>
                      {cl ? (
                        <span
                          className={`text-xs ${pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}
                        >
                          {pnl >= 0 ? '+' : ''}${formatUsd(pnl, 2)}
                        </span>
                      ) : (
                        <span
                          className="text-xs text-amber-400"
                          title="Bundle not yet built — check logs for [Orchestrator] BUILD_FAILED"
                        >
                          building…
                        </span>
                      )}
                      {cl && (
                        <span className="text-xs text-slate-500" title="Trades">
                          {cl.trades_count}t
                        </span>
                      )}
                      {!cfg.is_default && (
                        <span
                          onClick={(e) => handleMakeDefault(cfg.id, e)}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 hover:bg-blue-700 text-slate-300 cursor-pointer"
                          title="Make this the default config (loads on dashboard open)"
                        >
                          Make Default
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
