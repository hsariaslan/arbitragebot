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

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>();
  const blockedRef = useRef(false);
  const pendingCredentials = useRef<{ username: string; password: string; remember: boolean; captchaToken?: string } | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

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
          return;
        }

        if (data.type === 'logged_out') {
          setAuthenticated(false);
          setState(null);
          clearStoredToken();
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
      // Keep authenticated if we have a token (avoid login flash on reconnect)
      if (!getStoredToken()) {
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
    captchaRequired, captchaSiteKey, ipDenied,
    login, logout, send,
  };
}
