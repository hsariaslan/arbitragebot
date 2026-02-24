import { useState, useEffect, useRef, useCallback } from 'react';

declare global {
  interface Window {
    grecaptcha?: {
      render: (container: HTMLElement, params: {
        sitekey: string;
        theme?: string;
        callback?: (token: string) => void;
        'expired-callback'?: () => void;
      }) => number;
      reset: (widgetId: number) => void;
      ready: (callback: () => void) => void;
    };
  }
}

interface LoginPageProps {
  onLogin: (username: string, password: string, remember: boolean, captchaToken?: string) => void;
  error: string | null;
  attemptsRemaining: number | null;
  blocked: boolean;
  retryAfter: number;
  loading: boolean;
  captchaRequired: boolean;
  captchaSiteKey: string | null;
}

export default function LoginPage({
  onLogin, error, attemptsRemaining, blocked, retryAfter, loading,
  captchaRequired, captchaSiteKey,
}: LoginPageProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [countdown, setCountdown] = useState(retryAfter);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);

  const captchaContainerRef = useRef<HTMLDivElement>(null);
  const captchaWidgetId = useRef<number | null>(null);
  const captchaRendered = useRef(false);

  useEffect(() => {
    setCountdown(retryAfter);
    if (retryAfter <= 0) return;
    const interval = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [retryAfter]);

  // Render reCAPTCHA widget when required
  const renderCaptcha = useCallback(() => {
    if (!captchaRequired || !captchaSiteKey || !captchaContainerRef.current) return;
    if (captchaRendered.current) return;
    if (!window.grecaptcha) return;

    try {
      captchaWidgetId.current = window.grecaptcha.render(captchaContainerRef.current, {
        sitekey: captchaSiteKey,
        theme: 'dark',
        callback: (token: string) => setCaptchaToken(token),
        'expired-callback': () => setCaptchaToken(null),
      });
      captchaRendered.current = true;
    } catch {
      // Widget may already be rendered
    }
  }, [captchaRequired, captchaSiteKey]);

  useEffect(() => {
    if (!captchaRequired || !captchaSiteKey) {
      captchaRendered.current = false;
      return;
    }

    // Try to render immediately if grecaptcha is already loaded
    if (window.grecaptcha) {
      window.grecaptcha.ready(renderCaptcha);
    } else {
      // Wait for script to load
      const interval = setInterval(() => {
        if (window.grecaptcha) {
          clearInterval(interval);
          window.grecaptcha.ready(renderCaptcha);
        }
      }, 200);
      return () => clearInterval(interval);
    }
  }, [captchaRequired, captchaSiteKey, renderCaptcha]);

  // Reset captcha after failed attempt
  useEffect(() => {
    if (error && captchaRendered.current && captchaWidgetId.current !== null && window.grecaptcha) {
      try {
        window.grecaptcha.reset(captchaWidgetId.current);
        setCaptchaToken(null);
      } catch {
        // ignore
      }
    }
  }, [error]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim() || loading || blocked) return;
    if (captchaRequired && !captchaToken) return;
    onLogin(username.trim(), password.trim(), remember, captchaToken ?? undefined);
  };

  const formatTime = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m ${s}s`;
  };

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-white tracking-tight">CoirnaBot</h1>
          <p className="text-slate-500 text-sm mt-1">Dashboard Login</p>
        </div>

        <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700">
          {blocked ? (
            <div className="text-center py-4">
              <div className="w-12 h-12 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center mx-auto mb-3">
                <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                </svg>
              </div>
              <p className="text-red-400 font-medium">Access Blocked</p>
              <p className="text-slate-500 text-sm mt-2">Too many failed attempts.</p>
              {countdown > 0 ? (
                <p className="text-slate-400 text-sm mt-1">
                  Try again in <span className="text-white font-mono">{formatTime(countdown)}</span>
                </p>
              ) : (
                <button
                  onClick={() => window.location.reload()}
                  className="mt-3 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  Try Again
                </button>
              )}
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs text-slate-500 mb-1">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  autoComplete="username"
                  autoFocus
                  disabled={loading}
                  className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500 disabled:opacity-50 placeholder-slate-500"
                  placeholder="Enter username"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  autoComplete="current-password"
                  disabled={loading}
                  className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500 disabled:opacity-50 placeholder-slate-500"
                  placeholder="Enter password"
                />
              </div>

              {captchaRequired && captchaSiteKey && (
                <div className="flex justify-center">
                  <div ref={captchaContainerRef} />
                </div>
              )}

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={e => setRemember(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-slate-400">Remember me</span>
              </label>

              {error && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
                  <p className="text-red-400 text-sm">{error}</p>
                  {attemptsRemaining !== null && (
                    <p className="text-red-400/70 text-xs mt-1">
                      {attemptsRemaining} attempt{attemptsRemaining !== 1 ? 's' : ''} remaining
                    </p>
                  )}
                </div>
              )}

              <button
                type="submit"
                disabled={loading || !username.trim() || !password.trim() || (captchaRequired && !captchaToken)}
                className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 disabled:cursor-not-allowed text-white rounded-lg py-2.5 text-sm font-medium transition-colors"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Connecting...
                  </span>
                ) : (
                  'Sign In'
                )}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
