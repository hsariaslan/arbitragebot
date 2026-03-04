import { useEffect, useRef, useState, useCallback } from 'react';
import type { DashboardState } from '../types';

const WS_URL =
  window.location.hostname === 'localhost'
    ? 'ws://localhost:8765'
    : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;
const RECONNECT_DELAY = 2000;
const TOKEN_KEY = 'coirnabot_token';

function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY);
}

function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
}

export function useWebSocket() {
  const [state, setState] = useState<DashboardState | null>(null);
  const [connected, setConnected] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [attemptsRemaining, setAttemptsRemaining] = useState<number | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [retryAfter, setRetryAfter] = useState(0);
  const [authLoading, setAuthLoading] = useState(false);
  const [captchaRequired, setCaptchaRequired] = useState(false);
  const [captchaSiteKey, setCaptchaSiteKey] = useState<string | null>(null);
  const [ipDenied, setIpDenied] = useState(false);
  const [wsInitialized, setWsInitialized] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>();
  const blockedRef = useRef(false);
  const restartingRef = useRef(false);
  const pendingCredentials = useRef<{ username: string; password: string; remember: boolean; captchaToken?: string } | null>(null);
  const exportCallbackRef = useRef<((data: any) => void) | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Mark initialized on first auth-related message (before any UI renders)
        if (data.type === 'auth_required' || data.type === 'auth_denied' || data.type === 'auth_blocked') {
          setWsInitialized(true);
        }

        if (data.type === 'auth_required') {
          if (data.captcha_required) {
            setCaptchaRequired(true);
            if (data.captcha_site_key) setCaptchaSiteKey(data.captcha_site_key);
          }
          const savedToken = getStoredToken();
          if (savedToken) {
            setAuthLoading(true);
            ws.send(JSON.stringify({ type: 'auth', token: savedToken }));
          } else if (pendingCredentials.current) {
            const { username, password, remember, captchaToken } = pendingCredentials.current;
            pendingCredentials.current = null;
            setAuthLoading(true);
            ws.send(JSON.stringify({ type: 'auth', username, password, remember, captcha_token: captchaToken }));
          }
          return;
        }

        if (data.type === 'auth_ok') {
          setAuthenticated(true);
          setAuthError(null);
          setAttemptsRemaining(null);
          setAuthLoading(false);
          setBlocked(false);
          blockedRef.current = false;
          setRetryAfter(0);
          setCaptchaRequired(false);
          restartingRef.current = false;
          // Store token: respect remember-me preference
          if (data.token) {
            const wasInLocal = localStorage.getItem(TOKEN_KEY);
            const wasInSession = sessionStorage.getItem(TOKEN_KEY);
            const rememberPref = localStorage.getItem(TOKEN_KEY + '_remember');

            if (wasInLocal || wasInSession) {
              // Reconnecting: keep in same storage type
              if (wasInLocal) {
                localStorage.setItem(TOKEN_KEY, data.token);
              } else {
                sessionStorage.setItem(TOKEN_KEY, data.token);
              }
            } else {
              // Fresh login: use remember preference
              if (rememberPref === '1') {
                localStorage.setItem(TOKEN_KEY, data.token);
              } else {
                sessionStorage.setItem(TOKEN_KEY, data.token);
              }
            }
          }
          return;
        }

        if (data.type === 'auth_failed') {
          setAuthenticated(false);
          setAuthError(data.reason);
          setAttemptsRemaining(data.attempts_remaining ?? null);
          setAuthLoading(false);
          clearStoredToken();
          if (data.captcha_required) {
            setCaptchaRequired(true);
            if (data.captcha_site_key) setCaptchaSiteKey(data.captcha_site_key);
          }
          return;
        }

        if (data.type === 'auth_blocked') {
          setAuthenticated(false);
          setBlocked(true);
          blockedRef.current = true;
          setRetryAfter(data.retry_after ?? 3600);
          setAuthError(data.reason);
          setAuthLoading(false);
          clearStoredToken();
          return;
        }

        if (data.type === 'auth_denied') {
          setAuthenticated(false);
          setBlocked(true);
          blockedRef.current = true;
          setAuthError(data.reason || 'IP not allowed');
          setAuthLoading(false);
          setIpDenied(true);
          clearStoredToken();
          return;
        }

        if (data.type === 'logged_out') {
          setAuthenticated(false);
          setState(null);
          clearStoredToken();
          return;
        }

        // Restart acknowledgment: preserve auth state during reconnect
        if (data.type === 'restart_ack') {
          restartingRef.current = true;
          return;
        }

        // Result callbacks (export, hard stop, distribute)
        if (data.type === 'export_bot_logs_result' || data.type === 'export_auth_logs_result'
            || data.type === 'all_bot_logs_result'
            || data.type === 'hard_stop_result' || data.type === 'distribute_result' || data.type === 'distribute_error') {
          exportCallbackRef.current?.(data);
          exportCallbackRef.current = null;
          return;
        }

        // Normal state broadcast
        if (data.timestamp && data.portfolio) {
          setState(data as DashboardState);
        }
      } catch {
        // ignore parse errors
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;

      // During restart or if we have a token: keep authenticated and state (show stale data)
      if (restartingRef.current || getStoredToken()) {
        // Keep authenticated=true and state intact for yellow "Reconnecting..." indicator
      } else {
        setAuthenticated(false);
      }

      setAuthLoading(false);
      if (!blockedRef.current) {
        reconnectRef.current = setTimeout(connect, RECONNECT_DELAY);
      }
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  const login = useCallback((username: string, password: string, remember: boolean, captchaToken?: string) => {
    // Store remember preference for token storage on auth_ok
    if (remember) {
      localStorage.setItem(TOKEN_KEY + '_remember', '1');
    } else {
      localStorage.removeItem(TOKEN_KEY + '_remember');
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      setAuthLoading(true);
      setAuthError(null);
      wsRef.current.send(JSON.stringify({ type: 'auth', username, password, remember, captcha_token: captchaToken }));
    } else {
      pendingCredentials.current = { username, password, remember, captchaToken };
      connect();
    }
  }, [connect]);

  const logout = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'logout' }));
    }
    clearStoredToken();
    localStorage.removeItem(TOKEN_KEY + '_remember');
    setAuthenticated(false);
    setState(null);
  }, []);

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const sendWithCallback = useCallback((msg: object, callback: (data: any) => void) => {
    exportCallbackRef.current = callback;
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return {
    state, connected, authenticated, authError,
    attemptsRemaining, blocked, retryAfter, authLoading,
    captchaRequired, captchaSiteKey, ipDenied, wsInitialized,
    login, logout, send, sendWithCallback,
  };
}
