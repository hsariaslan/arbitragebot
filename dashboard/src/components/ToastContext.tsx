import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

export type ToastKind = 'success' | 'error' | 'info';

interface Toast {
  id: number;
  message: string;
  kind: ToastKind;
}

interface ToastContextValue {
  show: (message: string, kind?: ToastKind, durationMs?: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Render-tree fallback so a component used outside a provider still works
    return { show: () => undefined };
  }
  return ctx;
}

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const show = useCallback((message: string, kind: ToastKind = 'success', durationMs = 2500) => {
    const id = nextId++;
    setToasts((t) => [...t, { id, message, kind }]);
    window.setTimeout(() => {
      setToasts((t) => t.filter((x) => x.id !== id));
    }, durationMs);
  }, []);

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      {/* Stack of toasts (top-right) */}
      <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => {
          const cls =
            t.kind === 'success'
              ? 'bg-emerald-600 text-white'
              : t.kind === 'error'
              ? 'bg-rose-600 text-white'
              : 'bg-slate-700 text-white';
          const icon = t.kind === 'success' ? '✓' : t.kind === 'error' ? '✕' : 'ℹ';
          return (
            <div
              key={t.id}
              className={`${cls} px-4 py-2 rounded-md shadow-lg flex items-center gap-2 text-sm font-medium pointer-events-auto animate-slide-in`}
              style={{
                animation: 'slideIn 200ms ease-out',
              }}
            >
              <span className="text-base leading-none">{icon}</span>
              <span>{t.message}</span>
            </div>
          );
        })}
      </div>
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(20px); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </ToastContext.Provider>
  );
}
