import { useState, useRef, useEffect } from 'react';

interface TooltipProps {
  text: string;
}

export default function Tooltip({ text }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [above, setAbove] = useState(true);
  const iconRef = useRef<HTMLSpanElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (visible && iconRef.current) {
      const rect = iconRef.current.getBoundingClientRect();
      setAbove(rect.top > 120);
    }
  }, [visible]);

  // Dismiss on outside tap (mobile)
  useEffect(() => {
    if (!visible) return;
    const handler = (e: MouseEvent | TouchEvent) => {
      if (
        iconRef.current && !iconRef.current.contains(e.target as Node) &&
        tipRef.current && !tipRef.current.contains(e.target as Node)
      ) {
        setVisible(false);
      }
    };
    document.addEventListener('mousedown', handler);
    document.addEventListener('touchstart', handler);
    return () => {
      document.removeEventListener('mousedown', handler);
      document.removeEventListener('touchstart', handler);
    };
  }, [visible]);

  return (
    <span className="relative inline-flex items-center ml-1.5">
      <span
        ref={iconRef}
        className="w-4 h-4 rounded-full bg-slate-600 text-slate-300 text-[10px] font-bold flex items-center justify-center cursor-help select-none hover:bg-slate-500 transition-colors"
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onClick={() => setVisible(v => !v)}
      >
        ?
      </span>
      {visible && (
        <div
          ref={tipRef}
          className={`absolute z-50 left-1/2 -translate-x-1/2 max-w-[280px] w-max bg-slate-700 text-slate-200 text-xs rounded-lg p-2.5 shadow-lg leading-relaxed ${
            above ? 'bottom-full mb-2' : 'top-full mt-2'
          }`}
        >
          {text}
          <div
            className={`absolute left-1/2 -translate-x-1/2 w-0 h-0 border-x-[5px] border-x-transparent ${
              above
                ? 'top-full border-t-[5px] border-t-slate-700'
                : 'bottom-full border-b-[5px] border-b-slate-700'
            }`}
          />
        </div>
      )}
    </span>
  );
}
