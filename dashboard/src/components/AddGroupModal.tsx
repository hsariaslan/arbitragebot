import { useEffect, useState } from 'react';

interface Props {
  defaultName?: string;
  defaultCapital?: number;
  onConfirm: (name: string, initialCapital: number) => void;
  onCancel: () => void;
}

export default function AddGroupModal({
  defaultName = '',
  defaultCapital = 1000,
  onConfirm,
  onCancel,
}: Props) {
  const [name, setName] = useState(defaultName);
  const [capital, setCapital] = useState(defaultCapital);
  const valid = capital > 0;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCancel();
      } else if (e.key === 'Enter' && valid) {
        e.stopPropagation();
        onConfirm(name.trim(), capital);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [name, capital, valid, onCancel, onConfirm]);

  return (
    <div
      className="fixed inset-0 z-[80] bg-black/70 flex items-center justify-center p-4"
      onClick={onCancel}
    >
      <div
        className="bg-slate-900 border border-slate-700 rounded-lg shadow-2xl w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-slate-700 px-5 py-3">
          <h3 className="text-base font-semibold text-white">Add Config Group</h3>
        </div>
        <div className="px-5 py-4 space-y-3">
          <div>
            <label className="block text-xs text-slate-500 mb-1">
              Group Name <span className="text-slate-600">(optional, defaults to "Group N")</span>
            </label>
            <input
              type="text"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. $1k Tier"
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">
              Initial Capital ($) <span className="text-rose-400">*</span>
            </label>
            <input
              type="number"
              min={1}
              step={100}
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value))}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
            />
            <p className="text-xs text-slate-500 mt-1 italic">
              Every config in this group will start with this amount.
            </p>
          </div>
        </div>
        <div className="border-t border-slate-700 px-5 py-3 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-4 py-1.5 rounded-md bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm"
          >
            Cancel
          </button>
          <button
            onClick={() => valid && onConfirm(name.trim(), capital)}
            disabled={!valid}
            className={`px-4 py-1.5 rounded-md text-sm font-medium ${
              valid
                ? 'bg-blue-600 hover:bg-blue-500 text-white'
                : 'bg-slate-800 text-slate-600 cursor-not-allowed'
            }`}
          >
            Create Group
          </button>
        </div>
      </div>
    </div>
  );
}
