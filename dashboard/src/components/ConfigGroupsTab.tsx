import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
  rectSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { ConfigLite, GroupMeta, ConfigMeta, RegistryView } from '../types';
import ConfigEditModal from './ConfigEditModal';
import ConfirmModal from './ConfirmModal';
import AddGroupModal from './AddGroupModal';
import { useToast } from './ToastContext';

interface ConfirmAction {
  title: string;
  message: string | React.ReactNode;
  destructive?: boolean;
  confirmLabel?: string;
  onConfirm: () => void;
}

interface Props {
  registry?: RegistryView;
  configsLite?: ConfigLite[];
  selectedConfigId?: string | null;
  onSendMessage: (msg: object) => void;
  onSendWithCallback: (msg: object, callback: (data: any) => void) => void;
  /** 24h USD volumes fetched globally from the Settings page Global tab. */
  globalVolumes?: Record<string, Record<string, number>> | null;
}

// ── Utilities ──────────────────────────────────────────────────────────

const formatUsd = (v: number, fixed = 2) =>
  v.toLocaleString('en-US', { minimumFractionDigits: fixed, maximumFractionDigits: fixed });

const useLocalStorageBool = (key: string, defaultValue: boolean) => {
  const [val, setVal] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem(key);
      return stored === null ? defaultValue : stored === '1';
    } catch {
      return defaultValue;
    }
  });
  const update = (v: boolean) => {
    setVal(v);
    try {
      localStorage.setItem(key, v ? '1' : '0');
    } catch {
      /* noop */
    }
  };
  return [val, update] as const;
};

// ── Sortable wrappers ─────────────────────────────────────────────────

function SortableGroupCard(props: GroupCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: props.group.id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  return (
    <div ref={setNodeRef} style={style} className="touch-none">
      <ConfigGroupCard {...props} dragHandle={{ ...attributes, ...listeners }} />
    </div>
  );
}

function SortableConfigCard(props: ConfigCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: props.config.id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  return (
    <div ref={setNodeRef} style={style} className="touch-none">
      <ConfigCard {...props} dragHandle={{ ...attributes, ...listeners }} />
    </div>
  );
}

// ── ConfigCard (one strategy variation) ───────────────────────────────

interface ConfigCardProps {
  config: ConfigMeta;
  group: GroupMeta;
  lite?: ConfigLite;
  isSelected: boolean;
  hasCopyAvailable: boolean;
  hasOtherConfigs: boolean;
  primaryCount: number;
  onSelect: () => void;
  onSetPrimary: (value: boolean) => void;
  onSetSuperPrimary: () => void;
  onSetDefault: () => void;
  onRename: (name: string, description?: string) => void;
  onClone: () => void;
  onCopy: () => void;
  onPaste: () => void;
  onRestart: () => void;
  onRemove: () => void;
  onEdit: () => void;
  onToggleStop: () => void;
  requestConfirm: (action: ConfirmAction) => void;
  dragHandle?: any;
}

function ConfigCard({
  config,
  lite,
  isSelected,
  hasCopyAvailable,
  hasOtherConfigs,
  primaryCount,
  onSelect,
  onSetPrimary,
  onSetSuperPrimary,
  onSetDefault,
  onRename,
  onClone,
  onCopy,
  onPaste,
  onRestart,
  onRemove,
  onEdit,
  onToggleStop,
  requestConfirm,
  dragHandle,
}: ConfigCardProps) {
  const [expanded, setExpanded] = useLocalStorageBool(`config_${config.id}_expanded`, false);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState(config.name);
  const [descDraft, setDescDraft] = useState(config.description);

  useEffect(() => {
    if (!editingName) {
      setNameDraft(config.name);
      setDescDraft(config.description);
    }
  }, [config.name, config.description, editingName]);

  const handleRestart = () => {
    requestConfirm({
      title: `Restart ${config.name}?`,
      message: `This wipes the per-config session state (trades, balance, optimizer rankings) for "${config.name}" — but does NOT restart the bot process. Other configs are unaffected.`,
      confirmLabel: 'Restart Config',
      destructive: true,
      onConfirm: onRestart,
    });
  };

  const isStopped = !!lite?.manual_stopped;
  const handleToggleStop = () => {
    if (isStopped) {
      requestConfirm({
        title: `Resume trading for ${config.name}?`,
        message: `Trading will resume on the next sweep tick. Pre-stop state (trade history, balances, optimizer scores) is preserved.`,
        confirmLabel: 'Resume Trading',
        destructive: false,
        onConfirm: onToggleStop,
      });
    } else {
      requestConfirm({
        title: `Stop trading for ${config.name}?`,
        message: `Trading will pause for this config. Other configs are unaffected. Existing trades, balances, and optimizer state are preserved — click Resume to continue. Use the per-config Restart button if you want to wipe state instead.`,
        confirmLabel: 'Stop Trading',
        destructive: true,
        onConfirm: onToggleStop,
      });
    }
  };

  const handleRemove = () => {
    const isLastPrimary = config.is_primary && primaryCount <= 1;
    const warnings: React.ReactNode[] = [];
    if (config.is_super_primary) {
      warnings.push(
        <div key="sp" className="mt-2 px-3 py-2 bg-amber-950/40 border border-amber-700/40 rounded text-amber-200 text-xs">
          <span className="font-bold">⚠ Super-Primary</span> — this is the only config allowed to use
          non-simulation execution / real Binance Futures positions. Removing it will auto-reassign
          super-primary to the <span className="font-medium">first config of the first group</span>.
        </div>
      );
    }
    if (isLastPrimary) {
      warnings.push(
        <div key="p" className="mt-2 px-3 py-2 bg-purple-950/40 border border-purple-700/40 rounded text-purple-200 text-xs">
          <span className="font-bold">⚠ Last Primary</span> — this is the only config marked as primary
          (shown in the header). Removing it will auto-mark the{' '}
          <span className="font-medium">first config of the first group</span> as primary.
        </div>
      );
    }
    if (config.is_default) {
      warnings.push(
        <div key="d" className="mt-2 px-3 py-2 bg-blue-950/40 border border-blue-700/40 rounded text-blue-200 text-xs">
          <span className="font-bold">⚠ Default</span> — this is the default dashboard view. Removing
          it will auto-assign default to the <span className="font-medium">first config of the first group</span>.
        </div>
      );
    }
    requestConfirm({
      title: `Remove ${config.name}?`,
      message: (
        <>
          <span>Per-config state will be deleted from disk. This cannot be undone.</span>
          {warnings}
        </>
      ),
      confirmLabel: 'Delete Config',
      destructive: true,
      onConfirm: onRemove,
    });
  };

  const accent = config.is_super_primary
    ? 'border-amber-500/60 bg-amber-950/10'
    : config.is_default
    ? 'border-blue-500/40 bg-blue-950/10'
    : 'border-slate-700 bg-slate-800/40';

  const pnlColor = (lite?.net_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400';

  return (
    <div
      className={`border rounded-md overflow-hidden transition-all ${accent} ${
        isSelected ? 'ring-2 ring-cyan-500' : ''
      }`}
    >
      {/* Header row */}
      <div className="flex items-center gap-2 px-2 py-2">
        <button
          {...dragHandle}
          className="text-slate-500 hover:text-slate-300 cursor-grab active:cursor-grabbing"
          title="Drag to reorder"
        >
          ⋮⋮
        </button>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-slate-400 hover:text-white"
          title={expanded ? 'Collapse' : 'Expand'}
        >
          {expanded ? '▼' : '▶'}
        </button>
        <div className="flex-1 min-w-0 flex items-center gap-2">
          {editingName ? (
            <input
              autoFocus
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              onBlur={() => {
                onRename(nameDraft.trim() || config.name, descDraft);
                setEditingName(false);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  onRename(nameDraft.trim() || config.name, descDraft);
                  setEditingName(false);
                }
                if (e.key === 'Escape') {
                  setNameDraft(config.name);
                  setDescDraft(config.description);
                  setEditingName(false);
                }
              }}
              className="bg-slate-700 border border-slate-600 rounded px-2 py-0.5 text-sm text-white flex-1 min-w-0"
            />
          ) : (
            <button
              onClick={() => setEditingName(true)}
              className="text-sm font-medium text-white hover:text-cyan-300 truncate"
              title="Click to edit"
            >
              {config.name}
            </button>
          )}
          {config.is_super_primary && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
              ★★ SUPER
            </span>
          )}
          {config.is_primary && !config.is_super_primary && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40">
              ★ PRIMARY
            </span>
          )}
          {config.is_default && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/40">
              DEFAULT
            </span>
          )}
        </div>
        {/* Quick metrics */}
        {lite ? (
          <div className="hidden md:flex items-center gap-3 text-xs text-slate-400 mr-2">
            <span title="Portfolio value">${formatUsd(lite.portfolio_value, 0)}</span>
            <span className={pnlColor} title="Net P&L">
              {lite.net_pnl >= 0 ? '+' : ''}${formatUsd(lite.net_pnl, 2)}
            </span>
            <span title="Trades">{lite.trades_count}t</span>
          </div>
        ) : (
          <span
            className="hidden md:inline text-xs text-amber-400 mr-2"
            title="Bundle not yet built. If this persists past a few seconds, check the bot log for [Orchestrator] BUILD_FAILED entries."
          >
            building…
          </span>
        )}
        {/* Action buttons */}
        <div className="flex items-center gap-1">
          <button
            onClick={onEdit}
            className="px-2 py-1 rounded text-xs bg-blue-700 hover:bg-blue-600 text-white inline-flex items-center gap-1"
            title="Edit this config's settings in a modal"
          >
            <span className="text-sm leading-none">✎</span>
            <span>Edit</span>
          </button>
          <button
            onClick={onSelect}
            disabled={isSelected}
            className={`px-2 py-1 rounded text-xs ${
              isSelected
                ? 'bg-cyan-600 text-white cursor-default'
                : 'bg-slate-700 hover:bg-cyan-700 text-slate-200'
            }`}
            title="Make this config the active dashboard view"
          >
            {isSelected ? '✓ Selected' : 'Select'}
          </button>
          <button
            onClick={onCopy}
            className="px-2 py-1 rounded text-xs bg-slate-700 hover:bg-slate-600 text-slate-200"
            title="Copy this config's settings to clipboard buffer"
          >
            Copy
          </button>
          <button
            onClick={onPaste}
            disabled={!hasCopyAvailable}
            className={`px-2 py-1 rounded text-xs ${
              hasCopyAvailable
                ? 'bg-emerald-700 hover:bg-emerald-600 text-white'
                : 'bg-slate-800 text-slate-600 cursor-not-allowed'
            }`}
            title={
              hasCopyAvailable
                ? 'Apply the copied settings to this config'
                : 'Copy a config first'
            }
          >
            Paste
          </button>
          <button
            onClick={onClone}
            className="px-2 py-1 rounded text-xs bg-slate-700 hover:bg-slate-600 text-slate-200"
            title="Clone this config (creates a new one with same settings)"
          >
            Clone
          </button>
          <button
            onClick={handleToggleStop}
            className={`px-2 py-1 rounded text-xs inline-flex items-center gap-1 ${
              isStopped
                ? 'bg-emerald-700 hover:bg-emerald-600 text-white'
                : 'bg-amber-700 hover:bg-amber-600 text-white'
            }`}
            title={
              isStopped
                ? 'Resume trading for this config (state preserved)'
                : 'Stop trading for this config (state preserved)'
            }
          >
            {isStopped ? (
              <>
                <span>▶</span>
                <span>Resume</span>
              </>
            ) : (
              <>
                <span>■</span>
                <span>Stop</span>
              </>
            )}
          </button>
          <button
            onClick={handleRestart}
            className="px-2 py-1 rounded text-xs bg-orange-700 hover:bg-orange-600 text-white"
            title="Reset this config's state (trades, balance, optimizer) — does not restart the bot process"
          >
            Restart
          </button>
          <button
            onClick={handleRemove}
            disabled={config.is_default || (config.is_super_primary && hasOtherConfigs)}
            className={`px-2 py-1 rounded text-xs ${
              config.is_default || (config.is_super_primary && hasOtherConfigs)
                ? 'bg-slate-800 text-slate-600 cursor-not-allowed'
                : 'bg-rose-700 hover:bg-rose-600 text-white'
            }`}
            title={
              config.is_default
                ? 'Reassign default first'
                : config.is_super_primary && hasOtherConfigs
                ? 'Reassign super-primary first'
                : 'Remove this config (state file is wiped)'
            }
          >
            ✕
          </button>
        </div>
      </div>
      {/* Expanded body */}
      {expanded && (
        <div className="border-t border-slate-700 px-3 py-3 bg-slate-900/40 space-y-3 text-sm">
          {/* Description */}
          <div>
            <label className="block text-xs text-slate-500 mb-1">Description</label>
            <textarea
              value={descDraft}
              onChange={(e) => {
                setDescDraft(e.target.value);
              }}
              onBlur={() => {
                if (descDraft !== config.description) {
                  onRename(config.name, descDraft);
                }
              }}
              rows={2}
              placeholder="Why did you create this config? What's the hypothesis?"
              className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 focus:border-blue-500 focus:outline-none resize-none"
            />
          </div>
          {/* Flags */}
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={config.is_primary}
                onChange={(e) => onSetPrimary(e.target.checked)}
                className="accent-purple-500"
              />
              <span className="text-xs text-slate-300">Primary (header row)</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                name="super_primary"
                checked={config.is_super_primary}
                onChange={onSetSuperPrimary}
                className="accent-amber-500"
              />
              <span className="text-xs text-slate-300">★★ Super-Primary (real exec)</span>
            </label>
            <button
              onClick={onSetDefault}
              disabled={config.is_default}
              className={`text-xs px-2 py-0.5 rounded ${
                config.is_default
                  ? 'bg-blue-700 text-white cursor-default'
                  : 'bg-slate-700 hover:bg-blue-700 text-slate-300'
              }`}
            >
              {config.is_default ? '✓ Default' : 'Make Default'}
            </button>
          </div>
          {/* Lite metrics */}
          {lite && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div className="bg-slate-800 rounded p-2">
                <div className="text-slate-500">Portfolio</div>
                <div className="text-white font-semibold">
                  ${formatUsd(lite.portfolio_value, 2)}
                </div>
              </div>
              <div className="bg-slate-800 rounded p-2">
                <div className="text-slate-500">Net P&L</div>
                <div className={`font-semibold ${pnlColor}`}>
                  {lite.net_pnl >= 0 ? '+' : ''}${formatUsd(lite.net_pnl, 2)}
                </div>
              </div>
              <div className="bg-slate-800 rounded p-2">
                <div className="text-slate-500">$/hr</div>
                <div className={`font-semibold ${lite.hourly_rate >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {lite.hourly_rate >= 0 ? '+' : ''}${formatUsd(lite.hourly_rate, 2)}
                </div>
              </div>
              <div className="bg-slate-800 rounded p-2">
                <div className="text-slate-500">Drawdown</div>
                <div className="text-white font-semibold">
                  {(lite.drawdown_pct * 100).toFixed(2)}%
                </div>
              </div>
            </div>
          )}
          <div className="text-xs text-slate-500">
            Effective execution: <span className="text-slate-300">{lite?.execution_mode ?? 'simulation'}</span>{' '}
            • hedge: <span className="text-slate-300">{lite?.hedge_mode ?? 'simulation'}</span>
            {!config.is_super_primary && (
              <span className="ml-2 text-amber-400">(force-locked to simulation; super-primary inherits shared mode)</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── ConfigGroupCard (one capital tier) ─────────────────────────────────

interface GroupCardProps {
  group: GroupMeta;
  configsLite: ConfigLite[];
  selectedConfigId: string | null;
  copiedConfig: { settings: any; name: string } | null;
  copiedGroup: { configs: any[] } | null;
  onSendMessage: (msg: object) => void;
  onSendWithCallback: (msg: object, callback: (data: any) => void) => void;
  onCopyConfig: (id: string) => void;
  onCopyGroup: (id: string) => void;
  onEditConfig: (cfg: ConfigMeta, group: GroupMeta) => void;
  requestConfirm: (action: ConfirmAction) => void;
  hasOtherGroups: boolean;
  totalConfigCount: number;
  primaryCount: number;
  superPrimaryConfigId: string | null;
  dragHandle?: any;
}

function ConfigGroupCard(props: GroupCardProps) {
  const {
    group,
    configsLite,
    selectedConfigId,
    copiedConfig,
    copiedGroup,
    onSendMessage,
    onCopyConfig,
    onCopyGroup,
    onEditConfig,
    requestConfirm,
    hasOtherGroups,
    totalConfigCount,
    primaryCount,
    superPrimaryConfigId,
    dragHandle,
  } = props;
  const toast = useToast();
  const [expanded, setExpanded] = useLocalStorageBool(`group_${group.id}_expanded`, false);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState(group.name);
  const [capitalDraft, setCapitalDraft] = useState(group.initial_capital);
  // Capital is locked by default — Edit toggles it editable; Save submits.
  const [capitalEditing, setCapitalEditing] = useState(false);

  useEffect(() => {
    if (!editingName) setNameDraft(group.name);
    if (!capitalEditing) setCapitalDraft(group.initial_capital);
  }, [group.name, group.initial_capital, editingName, capitalEditing]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleConfigDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const ids = group.configs.map((c) => c.id);
    const oldIndex = ids.indexOf(String(active.id));
    const newIndex = ids.indexOf(String(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    const reordered = arrayMove(ids, oldIndex, newIndex);
    onSendMessage({ type: 'config_reorder', group_id: group.id, order: reordered });
  };

  const aggregateValue = configsLite
    .filter((l) => l.group_id === group.id)
    .reduce((sum, l) => sum + l.portfolio_value, 0);
  const aggregatePnl = configsLite
    .filter((l) => l.group_id === group.id)
    .reduce((sum, l) => sum + l.net_pnl, 0);

  const onSetPrimary = (cid: string, value: boolean) =>
    onSendMessage({ type: 'config_set_primary', config_id: cid, value });
  const onSetSuperPrimary = (cid: string) => {
    // Find the outgoing super-primary's lite to warn about active state.
    const currentSP = configsLite.find((l) => l.is_super_primary);
    const incoming = configsLite.find((l) => l.id === cid);
    if (!currentSP || currentSP.id === cid) {
      // No-op or no current super-primary — fire directly
      onSendMessage({ type: 'config_set_super_primary', config_id: cid });
      toast.show('Super-primary updated', 'success');
      return;
    }
    // Identify what will be torn down on the outgoing super-primary
    const hasOpenHedges = currentSP.hedge_mode !== 'simulation' && currentSP.hedge_open_count > 0;
    const hasNonSimExec = currentSP.execution_mode !== 'simulation';
    const hasActiveTrades = currentSP.trades_count > 0;
    const warnings: React.ReactNode[] = [];
    if (hasOpenHedges) {
      warnings.push(
        <div key="h" className="mt-2 px-3 py-2 bg-rose-950/40 border border-rose-700/40 rounded text-rose-200 text-xs">
          <span className="font-bold">⚠ Active Real Hedge Positions</span> — the outgoing super-primary
          ({currentSP.group_name}/{currentSP.name}) has{' '}
          <span className="font-medium">{currentSP.hedge_open_count} open Binance Futures position(s)</span> on{' '}
          <span className="font-mono">{currentSP.hedge_mode}</span>. They will be{' '}
          <span className="font-medium">closed automatically</span> at market price before the handoff
          (cumulative funding: {currentSP.hedge_cumulative_funding_usd >= 0 ? '+' : ''}$
          {currentSP.hedge_cumulative_funding_usd.toFixed(2)}).
        </div>
      );
    }
    if (hasNonSimExec) {
      warnings.push(
        <div key="e" className="mt-2 px-3 py-2 bg-amber-950/40 border border-amber-700/40 rounded text-amber-200 text-xs">
          <span className="font-bold">⚠ Non-Simulation Execution</span> — the outgoing super-primary is
          running <span className="font-mono">{currentSP.execution_mode}</span>. Demo/testnet balances on
          the exchange account persist (they're not "owned" by a config), but the new super-primary will
          inherit them via the shared demo fetcher. Active spot positions will keep marking-to-market
          until liquidated through normal trading.
        </div>
      );
    }
    if (hasActiveTrades && !hasOpenHedges && !hasNonSimExec) {
      warnings.push(
        <div key="t" className="mt-2 px-3 py-2 bg-blue-950/40 border border-blue-700/40 rounded text-blue-200 text-xs">
          <span className="font-bold">ℹ Active Trade History</span> — the outgoing super-primary has{' '}
          <span className="font-medium">{currentSP.trades_count} trade(s)</span> recorded. Trade history
          is preserved on its config; only the super-primary flag transfers.
        </div>
      );
    }
    requestConfirm({
      title: `Make ${incoming?.name ?? 'this'} the super-primary?`,
      message: (
        <>
          <span>
            Super-primary will move from{' '}
            <span className="text-amber-300 font-medium">{currentSP.group_name}/{currentSP.name}</span> to{' '}
            <span className="text-amber-300 font-medium">{incoming?.group_name}/{incoming?.name}</span>.
            The new super-primary will inherit shared <span className="font-mono">execution_mode</span> and{' '}
            <span className="font-mono">hedge_execution_mode</span> from the Global tab.
          </span>
          {warnings}
        </>
      ),
      confirmLabel: 'Make Super-Primary',
      destructive: hasOpenHedges,
      onConfirm: () => {
        onSendMessage({ type: 'config_set_super_primary', config_id: cid });
        toast.show('Super-primary updated', 'success');
      },
    });
  };
  const onSetDefault = (cid: string) =>
    onSendMessage({ type: 'config_set_default', config_id: cid });
  const onRename = (cid: string, name: string, description?: string) =>
    onSendMessage({ type: 'config_rename', config_id: cid, name, description });
  const onClone = (cid: string) =>
    onSendMessage({ type: 'config_clone', config_id: cid });
  const onPaste = (cid: string) => {
    if (!copiedConfig) return;
    onSendMessage({
      type: 'config_apply_settings',
      config_id: cid,
      settings: copiedConfig.settings,
    });
    toast.show(`Pasted "${copiedConfig.name}" settings`, 'success');
  };
  const onRestartConfig = (cid: string) => {
    onSendMessage({ type: 'config_restart', config_id: cid });
    toast.show('Config restarted', 'success');
  };
  const onRemoveConfig = (cid: string) => {
    onSendMessage({ type: 'config_remove', config_id: cid });
    toast.show('Config deleted', 'success');
  };
  const onToggleStopConfig = (cid: string) => {
    const lite = configsLite.find((l) => l.id === cid);
    const isStopped = !!lite?.manual_stopped;
    if (isStopped) {
      onSendMessage({ type: 'config_manual_start', config_id: cid });
      toast.show('Trading resumed', 'success');
    } else {
      onSendMessage({ type: 'config_manual_stop', config_id: cid });
      toast.show('Trading stopped', 'info');
    }
  };
  const onSelect = (cid: string) =>
    onSendMessage({ type: 'select_config', config_id: cid });

  const handleAddConfig = () => {
    onSendMessage({ type: 'config_add', group_id: group.id });
    toast.show(`Added new config to ${group.name}`, 'success');
  };

  const handlePasteAll = () => {
    if (!copiedGroup) return;
    // For each config in this group, fan out the corresponding source settings
    // by index. Excess source configs are added as new configs; excess target
    // configs are skipped.
    const targetCount = group.configs.length;
    copiedGroup.configs.forEach((srcCfg, idx) => {
      if (idx < targetCount) {
        onSendMessage({
          type: 'config_apply_settings',
          config_id: group.configs[idx].id,
          settings: srcCfg.settings,
        });
      } else {
        onSendMessage({
          type: 'config_add',
          group_id: group.id,
          settings: srcCfg.settings,
          name: srcCfg.name,
          description: srcCfg.description,
        });
      }
    });
    toast.show(`Pasted ${copiedGroup.configs.length} config(s) to ${group.name}`, 'success');
  };

  const handleSaveCapital = () => {
    if (capitalDraft <= 0) return;
    if (capitalDraft === group.initial_capital) {
      setCapitalEditing(false);
      return;
    }
    requestConfirm({
      title: `Change capital from $${group.initial_capital} to $${capitalDraft}?`,
      message: (
        <>
          This resets balances for <span className="text-white font-medium">all {group.configs.length} config(s)</span>{' '}
          in <span className="text-white font-medium">{group.name}</span>. Trade history is preserved per config but per-config balances restart at $
          {capitalDraft.toFixed(2)}.
        </>
      ),
      confirmLabel: 'Apply New Capital',
      destructive: true,
      onConfirm: () => {
        onSendMessage({
          type: 'config_set_capital',
          group_id: group.id,
          initial_capital: capitalDraft,
        });
        setCapitalEditing(false);
        toast.show(`Capital updated to $${capitalDraft.toFixed(2)}`, 'success');
      },
    });
  };

  return (
    <div className="border border-slate-700 rounded-lg bg-slate-900/40 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 bg-slate-800/60">
        <button
          {...dragHandle}
          className="text-slate-500 hover:text-slate-300 cursor-grab active:cursor-grabbing"
          title="Drag to reorder"
        >
          ⋮⋮
        </button>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-slate-400 hover:text-white"
        >
          {expanded ? '▼' : '▶'}
        </button>
        <div className="flex-1 flex items-center gap-2 min-w-0">
          {editingName ? (
            <input
              autoFocus
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              onBlur={() => {
                if (nameDraft.trim() && nameDraft !== group.name) {
                  onSendMessage({
                    type: 'config_rename_group',
                    group_id: group.id,
                    name: nameDraft.trim(),
                  });
                }
                setEditingName(false);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  if (nameDraft.trim() && nameDraft !== group.name) {
                    onSendMessage({
                      type: 'config_rename_group',
                      group_id: group.id,
                      name: nameDraft.trim(),
                    });
                  }
                  setEditingName(false);
                }
                if (e.key === 'Escape') {
                  setNameDraft(group.name);
                  setEditingName(false);
                }
              }}
              className="bg-slate-700 border border-slate-600 rounded px-2 py-0.5 text-base font-semibold text-white"
            />
          ) : (
            <button
              onClick={() => setEditingName(true)}
              className="text-base font-semibold text-white hover:text-cyan-300"
            >
              {group.name}
            </button>
          )}
          <span className="text-xs text-slate-500">
            ({group.configs.length} config{group.configs.length === 1 ? '' : 's'})
          </span>
        </div>
        {/* Aggregate metrics */}
        <div className="hidden md:flex items-center gap-3 text-xs text-slate-400 mr-2">
          <span title="Aggregate portfolio">${formatUsd(aggregateValue, 0)}</span>
          <span
            className={aggregatePnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}
            title="Aggregate P&L"
          >
            {aggregatePnl >= 0 ? '+' : ''}${formatUsd(aggregatePnl, 2)}
          </span>
        </div>
        {/* Capital input — locked by default; Edit toggles editable, Save submits */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-slate-500">$</span>
          <input
            type="number"
            value={capitalDraft}
            min={1}
            disabled={!capitalEditing}
            onChange={(e) => setCapitalDraft(Number(e.target.value))}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSaveCapital();
              if (e.key === 'Escape') {
                setCapitalDraft(group.initial_capital);
                setCapitalEditing(false);
              }
            }}
            className={`w-24 rounded px-2 py-0.5 text-sm transition-colors ${
              capitalEditing
                ? 'bg-slate-700 border border-blue-500 text-white'
                : 'bg-slate-800 border border-slate-700 text-slate-400 cursor-not-allowed'
            }`}
            title={capitalEditing ? 'Editing capital' : 'Click Edit to change capital'}
          />
          {!capitalEditing ? (
            <button
              onClick={() => setCapitalEditing(true)}
              className="px-1.5 py-0.5 rounded text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 inline-flex items-center gap-1"
              title="Edit initial capital"
            >
              <span>✎</span>
              <span>Edit</span>
            </button>
          ) : (
            <>
              <button
                onClick={handleSaveCapital}
                className="px-1.5 py-0.5 rounded text-xs bg-emerald-700 hover:bg-emerald-600 text-white inline-flex items-center gap-1"
                title="Save (resets balances of all configs in this group)"
              >
                <span>✓</span>
                <span>Save</span>
              </button>
              <button
                onClick={() => {
                  setCapitalDraft(group.initial_capital);
                  setCapitalEditing(false);
                }}
                className="px-1.5 py-0.5 rounded text-xs bg-slate-700 hover:bg-slate-600 text-slate-200"
                title="Cancel"
              >
                ✕
              </button>
            </>
          )}
        </div>
        <button
          onClick={() => onCopyGroup(group.id)}
          className="px-2 py-0.5 rounded text-xs bg-slate-700 hover:bg-slate-600 text-slate-200"
          title="Copy all configs in this group"
        >
          Copy All
        </button>
        <button
          onClick={handlePasteAll}
          disabled={!copiedGroup}
          className={`px-2 py-0.5 rounded text-xs ${
            copiedGroup
              ? 'bg-emerald-700 hover:bg-emerald-600 text-white'
              : 'bg-slate-800 text-slate-600 cursor-not-allowed'
          }`}
          title={copiedGroup ? 'Apply copied group to this group' : 'Copy a group first'}
        >
          Paste All
        </button>
        <button
          onClick={() => onSendMessage({ type: 'config_clone_group', group_id: group.id })}
          className="px-2 py-0.5 rounded text-xs bg-slate-700 hover:bg-slate-600 text-slate-200"
          title="Clone this group (creates a new group with all configs)"
        >
          Clone Group
        </button>
        <button
          onClick={() => {
            const containsSuper = group.configs.some((c) => c.id === superPrimaryConfigId);
            const containsDefault = group.configs.some((c) => c.is_default);
            const groupPrimaryCount = group.configs.filter((c) => c.is_primary).length;
            const willEliminatePrimaries = groupPrimaryCount > 0 && primaryCount === groupPrimaryCount;
            const warnings: React.ReactNode[] = [];
            if (containsSuper) {
              warnings.push(
                <div key="sp" className="mt-2 px-3 py-2 bg-amber-950/40 border border-amber-700/40 rounded text-amber-200 text-xs">
                  <span className="font-bold">⚠ Contains Super-Primary</span> — super-primary will be reassigned to the
                  <span className="font-medium"> first config of the first remaining group</span>.
                </div>
              );
            }
            if (willEliminatePrimaries) {
              warnings.push(
                <div key="p" className="mt-2 px-3 py-2 bg-purple-950/40 border border-purple-700/40 rounded text-purple-200 text-xs">
                  <span className="font-bold">⚠ Removes All Primaries</span> — this group has the only primary config(s).
                  After removal, the <span className="font-medium">first config of the first remaining group</span> will
                  be auto-marked primary.
                </div>
              );
            }
            if (containsDefault) {
              warnings.push(
                <div key="d" className="mt-2 px-3 py-2 bg-blue-950/40 border border-blue-700/40 rounded text-blue-200 text-xs">
                  <span className="font-bold">⚠ Contains Default</span> — default will be reassigned to the
                  <span className="font-medium"> first config of the first remaining group</span>.
                </div>
              );
            }
            requestConfirm({
              title: `Remove group "${group.name}"?`,
              message: (
                <>
                  <span>
                    This deletes the group and <span className="text-white font-medium">all {group.configs.length} config(s)</span>{' '}
                    inside it. Per-config state files are wiped. This cannot be undone.
                  </span>
                  {warnings}
                </>
              ),
              confirmLabel: 'Delete Group',
              destructive: true,
              onConfirm: () => {
                onSendMessage({ type: 'config_remove_group', group_id: group.id });
                toast.show(`Group "${group.name}" deleted`, 'success');
              },
            });
          }}
          disabled={!hasOtherGroups}
          className={`px-2 py-0.5 rounded text-xs ${
            !hasOtherGroups
              ? 'bg-slate-800 text-slate-600 cursor-not-allowed'
              : 'bg-rose-700 hover:bg-rose-600 text-white'
          }`}
          title={!hasOtherGroups ? 'Cannot remove the last group' : 'Remove group + all its configs'}
        >
          ✕
        </button>
      </div>
      {expanded && (
        <div className="p-2 space-y-2">
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleConfigDragEnd}
          >
            <SortableContext
              items={group.configs.map((c) => c.id)}
              strategy={verticalListSortingStrategy}
            >
              {group.configs.map((cfg) => {
                const lite = configsLite.find((l) => l.id === cfg.id);
                return (
                  <SortableConfigCard
                    key={cfg.id}
                    config={cfg}
                    group={group}
                    lite={lite}
                    isSelected={selectedConfigId === cfg.id}
                    hasCopyAvailable={!!copiedConfig}
                    hasOtherConfigs={totalConfigCount > 1}
                    primaryCount={primaryCount}
                    onSelect={() => onSelect(cfg.id)}
                    onSetPrimary={(v) => onSetPrimary(cfg.id, v)}
                    onSetSuperPrimary={() => onSetSuperPrimary(cfg.id)}
                    onSetDefault={() => onSetDefault(cfg.id)}
                    onRename={(name, desc) => onRename(cfg.id, name, desc)}
                    onClone={() => onClone(cfg.id)}
                    onCopy={() => onCopyConfig(cfg.id)}
                    onPaste={() => onPaste(cfg.id)}
                    onRestart={() => onRestartConfig(cfg.id)}
                    onRemove={() => onRemoveConfig(cfg.id)}
                    onToggleStop={() => onToggleStopConfig(cfg.id)}
                    onEdit={() => onEditConfig(cfg, group)}
                    requestConfirm={requestConfirm}
                  />
                );
              })}
            </SortableContext>
          </DndContext>
          <button
            onClick={handleAddConfig}
            className="w-full border border-dashed border-slate-600 rounded-md py-2 text-sm text-slate-400 hover:border-cyan-500 hover:text-cyan-400 transition-colors"
            title="Add a new config to this group (inherits the default config's settings)"
          >
            + Add Config
          </button>
        </div>
      )}
    </div>
  );
}

// ── Main ConfigGroupsTab ───────────────────────────────────────────────

export default function ConfigGroupsTab({
  registry,
  configsLite,
  selectedConfigId,
  onSendMessage,
  onSendWithCallback,
  globalVolumes,
}: Props) {
  const toast = useToast();
  const [copiedConfig, setCopiedConfig] = useState<{ settings: any; name: string } | null>(null);
  const [copiedGroup, setCopiedGroup] = useState<{ configs: any[] } | null>(null);
  const [editingConfig, setEditingConfig] = useState<{ cfg: ConfigMeta; group: GroupMeta } | null>(null);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const [showAddGroup, setShowAddGroup] = useState(false);

  // Clear copy buffers when user navigates away (per the plan)
  useEffect(() => {
    return () => {
      setCopiedConfig(null);
      setCopiedGroup(null);
    };
  }, []);

  const onEditConfig = useCallback((cfg: ConfigMeta, group: GroupMeta) => {
    setEditingConfig({ cfg, group });
  }, []);

  const requestConfirm = useCallback((action: ConfirmAction) => {
    setConfirmAction(action);
  }, []);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleGroupDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id || !registry) return;
    const ids = registry.groups.map((g) => g.id);
    const oldIndex = ids.indexOf(String(active.id));
    const newIndex = ids.indexOf(String(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    const reordered = arrayMove(ids, oldIndex, newIndex);
    onSendMessage({ type: 'config_reorder_groups', order: reordered });
  };

  const handleAddGroup = () => {
    setShowAddGroup(true);
  };

  // ── Export / Import ────────────────────────────────────────────────
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleExportAll = () => {
    onSendWithCallback({ type: 'config_export_all' }, (data: any) => {
      if (!data?.ok || !data.payload) {
        toast.show('Export failed', 'error');
        return;
      }
      const json = JSON.stringify(data.payload, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const ts = new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-');
      a.href = url;
      a.download = `coirnabot-configs-${ts}.json`;
      a.click();
      URL.revokeObjectURL(url);
      const total = data.payload.groups?.reduce(
        (s: number, g: any) => s + (g.configs?.length ?? 0), 0,
      ) ?? 0;
      toast.show(`Exported ${data.payload.groups?.length ?? 0} group(s) / ${total} config(s)`, 'success');
    });
  };

  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    file.text().then((text) => {
      let payload: any;
      try {
        payload = JSON.parse(text);
      } catch (err) {
        toast.show(`Invalid JSON: ${err}`, 'error', 4000);
        return;
      }
      if (payload && typeof payload === 'object' && payload.payload && typeof payload.payload === 'object') {
        payload = payload.payload;
      }
      if (!payload || typeof payload !== 'object' || !Array.isArray(payload.groups)) {
        toast.show('Invalid file: missing "groups" array', 'error', 4000);
        return;
      }
      const incomingGroups = payload.groups.length;
      const incomingConfigs = payload.groups.reduce(
        (s: number, g: any) => s + (g.configs?.length ?? 0), 0,
      );
      const incomingSP = payload.shared?.super_primary_config_id;
      requestConfirm({
        title: `Import ${incomingGroups} group(s) / ${incomingConfigs} config(s)?`,
        message: (
          <>
            <span>
              This <span className="text-rose-300 font-medium">replaces</span> every group and
              config currently in the registry. Configs not in the imported file are
              <span className="font-medium"> deleted</span> (their per-config state files are
              wiped). Real Binance Futures positions on the current super-primary are closed at
              market price <span className="font-medium">before</span> the swap.
            </span>
            <div className="mt-3 px-3 py-2 bg-amber-950/40 border border-amber-700/40 rounded text-amber-200 text-xs">
              <div><span className="font-bold">⚠ Irreversible.</span> Export the current registry first if you want a backup.</div>
              <div className="mt-1 text-slate-300">
                Schema v{payload.schema_version ?? '?'}, super-primary id={incomingSP?.slice(0, 8) ?? '(none)'}
              </div>
            </div>
          </>
        ),
        confirmLabel: 'Import (Overwrite)',
        destructive: true,
        onConfirm: () => {
          onSendWithCallback({ type: 'config_import_all', payload }, (data: any) => {
            if (data?.ok) {
              toast.show(
                `Imported ${data.groups ?? incomingGroups} group(s) / ${data.configs ?? incomingConfigs} config(s)`,
                'success',
                4000,
              );
            } else {
              toast.show(`Import failed: ${data?.error ?? 'unknown error'}`, 'error', 6000);
            }
          });
          toast.show('Importing — registry will reload momentarily', 'info', 3000);
        },
      });
    });
  };

  const handleAddGroupConfirm = (name: string, cap: number) => {
    onSendMessage({ type: 'config_add_group', name: name || undefined, initial_capital: cap });
    toast.show(`Group "${name || 'Group N'}" created with $${cap.toFixed(0)} capital`, 'success');
    setShowAddGroup(false);
  };

  const onCopyConfig = useCallback(
    (cid: string) => {
      onSendWithCallback({ type: 'config_request_settings', config_id: cid }, (data) => {
        if (data && data.settings) {
          setCopiedConfig({ settings: data.settings, name: data.name });
        }
      });
    },
    [onSendWithCallback],
  );

  const onCopyGroup = useCallback(
    (gid: string) => {
      const group = registry?.groups.find((g) => g.id === gid);
      if (!group || group.configs.length === 0) return;
      // sendWithCallback is single-shot, so chain requests sequentially.
      // For typical group sizes (10 configs), this completes in <100ms.
      const collected: any[] = [];
      const queue = [...group.configs];
      const next = () => {
        const c = queue.shift();
        if (!c) {
          setCopiedGroup({ configs: collected });
          return;
        }
        onSendWithCallback({ type: 'config_request_settings', config_id: c.id }, (data) => {
          if (data && data.settings) {
            collected.push({
              settings: data.settings,
              name: data.name,
              description: data.description,
            });
          }
          next();
        });
      };
      next();
    },
    [registry, onSendWithCallback],
  );

  const totalConfigCount = useMemo(
    () => registry?.groups.reduce((sum, g) => sum + g.configs.length, 0) ?? 0,
    [registry],
  );
  const primaryCount = useMemo(
    () => registry?.groups.reduce(
      (sum, g) => sum + g.configs.filter((c) => c.is_primary).length,
      0,
    ) ?? 0,
    [registry],
  );

  if (!registry) {
    return (
      <div className="p-6 text-center text-slate-400">
        Loading multi-config registry…
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header banner */}
      <div className="flex items-center justify-between bg-slate-800/40 border border-slate-700 rounded-md px-4 py-2 gap-3 flex-wrap">
        <div className="text-xs text-slate-400">
          <span className="text-slate-300 font-medium">
            {registry.groups.length} group(s) / {totalConfigCount} config(s)
          </span>
          {' • Super-primary: '}
          <span className="text-amber-400">
            {configsLite?.find((l) => l.is_super_primary)?.name ?? '(none)'}
          </span>
          {' • Default: '}
          <span className="text-blue-400">
            {configsLite?.find((l) => l.is_default)?.name ?? '(none)'}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {copiedConfig && (
            <span className="text-xs text-emerald-400">
              📋 Copied config: <span className="text-emerald-300 font-semibold">{copiedConfig.name}</span>
            </span>
          )}
          {copiedGroup && (
            <span className="text-xs text-emerald-400">
              📋 Copied group: <span className="text-emerald-300 font-semibold">{copiedGroup.configs.length} configs</span>
            </span>
          )}
          <button
            onClick={handleExportAll}
            className="px-3 py-1 rounded text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 inline-flex items-center gap-1.5"
            title="Download all groups + configs as a JSON file"
          >
            <span>↓</span>
            <span>Export All Configs</span>
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="px-3 py-1 rounded text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 inline-flex items-center gap-1.5"
            title="Upload a JSON file — overwrites every group + config currently in the registry"
          >
            <span>↑</span>
            <span>Import Configs</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={handleImportFile}
          />
        </div>
      </div>

      {/* Groups grid */}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleGroupDragEnd}
      >
        <SortableContext items={registry.groups.map((g) => g.id)} strategy={rectSortingStrategy}>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {registry.groups.map((g) => (
              <SortableGroupCard
                key={g.id}
                group={g}
                configsLite={configsLite ?? []}
                selectedConfigId={selectedConfigId ?? null}
                copiedConfig={copiedConfig}
                copiedGroup={copiedGroup}
                onSendMessage={onSendMessage}
                onSendWithCallback={onSendWithCallback}
                onCopyConfig={onCopyConfig}
                onCopyGroup={onCopyGroup}
                onEditConfig={onEditConfig}
                requestConfirm={requestConfirm}
                hasOtherGroups={registry.groups.length > 1}
                totalConfigCount={totalConfigCount}
                primaryCount={primaryCount}
                superPrimaryConfigId={registry.super_primary_config_id}
              />
            ))}
            {/* Add Group tile (occupies next slot in the grid flow) */}
            <button
              onClick={handleAddGroup}
              className="border border-dashed border-slate-600 rounded-lg bg-slate-900/30 hover:border-cyan-500 hover:bg-cyan-950/20 transition-colors min-h-[80px] flex items-center justify-center text-slate-400 hover:text-cyan-400"
              title="Add a new config group"
            >
              <span className="text-base">+ Add Group</span>
            </button>
          </div>
        </SortableContext>
      </DndContext>

      {/* Help footer */}
      <div className="text-xs text-slate-500 italic px-2">
        Drag <span className="text-slate-300">⋮⋮</span> to reorder. Reordering is hot-applied; the
        Header, Dashboard, and Rankings reflect the new order automatically. Click{' '}
        <span className="text-blue-300">✎ Edit</span> on a config to open its settings in a modal.
      </div>

      {/* Per-config Edit modal */}
      {editingConfig && (
        <ConfigEditModal
          configId={editingConfig.cfg.id}
          configName={editingConfig.cfg.name}
          groupName={editingConfig.group.name}
          isSuperPrimary={editingConfig.cfg.is_super_primary}
          onClose={() => setEditingConfig(null)}
          onSendMessage={onSendMessage}
          onSendWithCallback={onSendWithCallback}
          globalVolumes={globalVolumes}
        />
      )}

      {/* Confirm dialog (single instance, switched per action) */}
      {confirmAction && (
        <ConfirmModal
          title={confirmAction.title}
          message={confirmAction.message}
          confirmLabel={confirmAction.confirmLabel}
          destructive={confirmAction.destructive}
          onConfirm={() => {
            confirmAction.onConfirm();
            setConfirmAction(null);
          }}
          onCancel={() => setConfirmAction(null)}
        />
      )}

      {/* Add Group modal (replaces prompt) */}
      {showAddGroup && (
        <AddGroupModal
          defaultName={`Group ${(registry?.groups.length ?? 0) + 1}`}
          onConfirm={handleAddGroupConfirm}
          onCancel={() => setShowAddGroup(false)}
        />
      )}
    </div>
  );
}
