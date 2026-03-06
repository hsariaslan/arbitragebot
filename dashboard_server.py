"""
WebSocket server for the CoirnaBot live dashboard.

Pushes a full state snapshot (balances, trades, transfers, prices, system status)
to all connected browser clients every second via WebSocket on port 8765.

Also handles incoming messages from the dashboard for settings updates.
"""

import asyncio
import json
import logging
import re
import secrets
import time
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any

import websockets

from config import (
    ALL_EXCHANGES,
    ALLOWED_ORIGINS,
    DASHBOARD_BIND_HOST,
    DASHBOARD_USERNAME,
    DASHBOARD_WS_PORT,
    RECAPTCHA_SECRET_KEY,
    RECAPTCHA_SITE_KEY,
    SYMBOLS,
    TRUSTED_PROXIES,
    verify_dashboard_password,
)
from email_notifier import notify_blocked, notify_login
from settings import save_settings

if TYPE_CHECKING:
    from balance import BalanceTracker
    from fee_manager import FeeManager
    from fetchers.base import BaseFetcher
    from monitor import ArbitrageMonitor
    from optimizer import SymbolOptimizer
    from state_manager import StateManager
    from transfer_fee_manager import TransferFeeManager

logger = logging.getLogger(__name__)


def _safe_task(coro, name: str = "task") -> asyncio.Task:
    """Create an asyncio task that logs exceptions instead of silently swallowing them."""
    task = asyncio.create_task(coro)

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.error(f"[Dashboard] Async {name} failed: {exc!r}", exc_info=exc)

    task.add_done_callback(_on_done)
    return task


class DashboardLogHandler(logging.Handler):
    """Captures recent log entries in memory for dashboard broadcast and export."""

    _COMPONENT_RE = re.compile(r"^\[([\w.]+)\]\s*(.*)$", re.DOTALL)

    def __init__(self, maxlen: int = 2000):
        super().__init__()
        self._entries: deque[dict] = deque(maxlen=maxlen)
        self._all_entries: list[dict] = []  # full session for export

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            component = ""
            m = self._COMPONENT_RE.match(msg)
            if m:
                component = m.group(1)
                msg = m.group(2)
            entry = {
                "timestamp": record.created,
                "level": record.levelname,
                "component": component,
                "message": msg,
            }
            self._entries.append(entry)
            self._all_entries.append(entry)
        except Exception:
            pass

    def get_recent(self) -> list[dict]:
        """Return last N entries for live broadcast."""
        return list(self._entries)

    def get_all(self) -> list[dict]:
        """Return all session entries (for filtered views)."""
        return list(self._all_entries)

    def total_count(self) -> int:
        """Return total session entry count."""
        return len(self._all_entries)

    def get_entries_range(self, start: float, end: float) -> list[dict]:
        """Return all session entries within a time range (for export)."""
        return [e for e in self._all_entries if start <= e["timestamp"] <= end]


class DashboardServer:
    """WebSocket server that broadcasts live state to dashboard clients."""

    def __init__(
        self,
        monitor: "ArbitrageMonitor",
        balance: "BalanceTracker",
        fetchers: list["BaseFetcher"],
        settings: dict | None = None,
        optimizer: "SymbolOptimizer | None" = None,
        log_handler: DashboardLogHandler | None = None,
        state_manager: "StateManager | None" = None,
        fee_manager: "FeeManager | None" = None,
        transfer_fee_manager: "TransferFeeManager | None" = None,
    ) -> None:
        self._monitor = monitor
        self._balance = balance
        self._fetchers = fetchers
        self._settings = settings or {}
        self._optimizer = optimizer
        self._log_handler = log_handler
        self._state_manager = state_manager
        self._fee_manager = fee_manager
        self._transfer_fee_mgr = transfer_fee_manager
        self._demo_fetcher: "DemoPortfolioFetcher | None" = None
        if optimizer:
            optimizer.set_dashboard(self)
        self._running = False
        self._clients: set[Any] = set()
        self._client_ips: dict[Any, str] = {}  # ws → resolved IP (for whitelist enforcement)
        self._start_time = 0.0
        self._uptime_data: dict = {}
        self._uptime_file = Path("state/uptime.json")
        self._last_heartbeat_save = 0.0

        # Proxy (Zurich VPS) uptime tracking
        self._proxy_uptime_data: dict = {}
        self._proxy_uptime_file = Path("state/proxy_uptime.json")
        self._proxy_last_heartbeat_save = 0.0
        self._proxy_was_connected: bool | None = None
        self._proxy_disconnect_start: float = 0.0
        self._bitfinex_fetcher: Any = None

        # Auth state
        self._sessions: dict[str, dict] = {}  # token -> {ip, last_seen, remember}
        self._sessions_file = Path("logs/auth/sessions.json")
        self._failed_attempts: dict[str, list[float]] = {}  # IP -> failure timestamps
        self._blocked_ips: dict[str, float] = {}  # IP -> block_expires_at
        self._rate_limit_file = Path("logs/auth/rate_limits.json")
        self._max_attempts = 10
        self._block_duration = 3600.0  # 1 hour
        self._load_rate_limits()
        self._session_expiry = 86400.0  # 24h idle timeout for non-remember sessions
        self._session_absolute_max = 172800.0  # 48h absolute max for non-remember
        self._remember_expiry = 2592000.0  # 30 days absolute max for remember-me
        self._last_cleanup = 0.0
        self._captcha_threshold = 3  # require CAPTCHA after this many failures
        self._load_sessions()

        # Restart grace period — suppress login email after bot restart
        self._restart_grace = False
        self._check_restart_marker()

        # Auth events (for Auth Log page)
        self._max_auth_events = 500
        self._auth_events: list[dict] = self._load_auth_events()

        # Auth logger
        self._auth_logger = self._setup_auth_logger()

        # Startup warnings
        if not RECAPTCHA_SITE_KEY or not RECAPTCHA_SECRET_KEY:
            logger.warning(
                "[Auth] reCAPTCHA keys not configured — CAPTCHA protection DISABLED. "
                "Set RECAPTCHA_SITE_KEY and RECAPTCHA_SECRET_KEY in .env"
            )

        # Authenticated command rate limiting
        self._last_settings_save: float = 0.0
        self._settings_cooldown: float = 5.0  # 5s between settings operations

        # Distribute from Bitfinex — one-shot enabled on specific triggers
        self._distribute_enabled: bool = False

    @staticmethod
    def _setup_auth_logger() -> logging.Logger:
        """Create a dedicated logger for authentication events."""
        auth_dir = Path("logs/auth")
        auth_dir.mkdir(parents=True, exist_ok=True)
        auth_log = logging.getLogger("coirnabot.auth")
        auth_log.setLevel(logging.INFO)
        if not auth_log.handlers:
            fh = logging.FileHandler(auth_dir / "auth.log")
            fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            ))
            auth_log.addHandler(fh)
        return auth_log

    def _load_auth_events(self) -> list[dict]:
        """Load persisted auth events from JSONL file on startup."""
        path = Path("logs/auth/auth_events.jsonl")
        if not path.exists():
            return []
        events: list[dict] = []
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if line:
                    event = json.loads(line)
                    # Mask legacy plaintext passwords from old log entries
                    pw = event.get("password", "")
                    if pw and not pw.endswith("*"):
                        event["password"] = DashboardServer._mask_password(pw)
                    events.append(event)
        except Exception as e:
            logger.warning(f"[Auth] Failed to load auth events: {e}")
        # Keep only the most recent entries
        if len(events) > self._max_auth_events:
            events = events[-self._max_auth_events:]
        return events

    _AUTH_LOG_MAX_SIZE = 5 * 1024 * 1024  # 5 MB
    _AUTH_LOG_MAX_ROTATIONS = 2

    def _persist_auth_event(self, event: dict) -> None:
        """Append a single auth event to the JSONL file, rotating if too large."""
        path = Path("logs/auth/auth_events.jsonl")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size > self._AUTH_LOG_MAX_SIZE:
                self._rotate_auth_log(path)
            with open(path, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.warning(f"[Auth] Failed to persist auth event: {e}")

    @staticmethod
    def _rotate_auth_log(path: Path) -> None:
        """Rotate auth_events.jsonl -> .jsonl.1 -> .jsonl.2 (max 2 rotated)."""
        try:
            oldest = Path(f"{path}.{DashboardServer._AUTH_LOG_MAX_ROTATIONS}")
            if oldest.exists():
                oldest.unlink()
            for i in range(DashboardServer._AUTH_LOG_MAX_ROTATIONS - 1, 0, -1):
                src = Path(f"{path}.{i}")
                dst = Path(f"{path}.{i + 1}")
                if src.exists():
                    src.rename(dst)
            if path.exists():
                path.rename(Path(f"{path}.1"))
            logger.info("[Auth] Rotated auth log (exceeded 5MB)")
        except Exception as e:
            logger.warning(f"[Auth] Failed to rotate auth log: {e}")

    # --- Rate limiting ---

    def _load_rate_limits(self) -> None:
        """Load persisted rate limit state from disk on startup."""
        if not self._rate_limit_file.exists():
            return
        try:
            with open(self._rate_limit_file) as f:
                data = json.load(f)
            now = time.time()
            for ip, expires in data.get("blocked_ips", {}).items():
                if expires > now:
                    self._blocked_ips[ip] = expires
            cutoff = now - self._block_duration
            for ip, timestamps in data.get("failed_attempts", {}).items():
                valid = [t for t in timestamps if t > cutoff]
                if valid:
                    self._failed_attempts[ip] = valid
            logger.info(
                f"[Auth] Loaded rate limits: {len(self._blocked_ips)} blocked, "
                f"{len(self._failed_attempts)} tracked IPs"
            )
        except Exception as e:
            logger.warning(f"[Auth] Failed to load rate limits: {e}")

    def _persist_rate_limits(self) -> None:
        """Save rate limit state to disk."""
        try:
            self._rate_limit_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "blocked_ips": self._blocked_ips,
                "failed_attempts": self._failed_attempts,
            }
            with open(self._rate_limit_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"[Auth] Failed to persist rate limits: {e}")

    def _load_sessions(self) -> None:
        """Load persisted sessions from disk on startup."""
        if not self._sessions_file.exists():
            return
        try:
            with open(self._sessions_file) as f:
                data = json.load(f)
            now = time.time()
            loaded = 0
            for token, session in data.items():
                if not isinstance(session, dict):
                    continue
                created = session.get("created_at", 0)
                last_seen = session.get("last_seen", 0)
                remember = session.get("remember", False)
                # Prune expired sessions on load
                if remember:
                    if now - created > self._remember_expiry:
                        continue
                else:
                    if (now - last_seen > self._session_expiry
                            or now - created > self._session_absolute_max):
                        continue
                self._sessions[token] = session
                loaded += 1
            if loaded:
                logger.info(f"[Auth] Loaded {loaded} persisted session(s)")
        except Exception as e:
            logger.warning(f"[Auth] Failed to load sessions: {e}")

    def _persist_sessions(self) -> None:
        """Save sessions to disk so they survive restarts."""
        try:
            self._sessions_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._sessions_file, "w") as f:
                json.dump(self._sessions, f)
        except Exception as e:
            logger.warning(f"[Auth] Failed to persist sessions: {e}")

    def _check_rate_limit(self, ip: str) -> tuple[bool, int, int]:
        """Check if IP is rate limited. Returns (blocked, remaining, retry_after_s)."""
        now = time.time()
        if ip in self._blocked_ips:
            expires = self._blocked_ips[ip]
            if now < expires:
                return True, 0, int(expires - now)
            del self._blocked_ips[ip]
            self._failed_attempts.pop(ip, None)
            self._persist_rate_limits()

        if ip in self._failed_attempts:
            cutoff = now - self._block_duration
            self._failed_attempts[ip] = [t for t in self._failed_attempts[ip] if t > cutoff]
            count = len(self._failed_attempts[ip])
        else:
            count = 0
        return False, max(self._max_attempts - count, 0), 0

    def _record_failed_attempt(self, ip: str) -> int:
        """Record a failed login attempt. Returns attempts remaining."""
        now = time.time()
        if ip not in self._failed_attempts:
            self._failed_attempts[ip] = []
        self._failed_attempts[ip].append(now)
        cutoff = now - self._block_duration
        self._failed_attempts[ip] = [t for t in self._failed_attempts[ip] if t > cutoff]
        remaining = max(self._max_attempts - len(self._failed_attempts[ip]), 0)
        if remaining <= 0:
            self._blocked_ips[ip] = now + self._block_duration
            self._persist_rate_limits()
            self._auth_logger.warning(f"{ip} - Blocked for {int(self._block_duration)}s after {self._max_attempts} failed attempts")
        return remaining

    # --- Session management ---

    def _create_session(self, ip: str, remember: bool = False) -> str:
        """Create a new session token."""
        token = secrets.token_hex(32)
        self._sessions[token] = {
            "ip": ip,
            "created_at": time.time(),
            "last_seen": time.time(),
            "remember": remember,
        }
        self._persist_sessions()
        return token

    def _validate_session(self, token: str) -> bool:
        """Validate a session token. Returns True if valid."""
        if token not in self._sessions:
            return False
        session = self._sessions[token]
        now = time.time()
        created = session.get("created_at", session["last_seen"])

        # Check if session's IP is still whitelisted
        session_ip = session.get("ip", "")
        if not self._check_ip_whitelist(session_ip):
            del self._sessions[token]
            self._persist_sessions()
            logger.info(f"[Auth] Session rejected — IP {session_ip} no longer whitelisted")
            return False

        if session["remember"]:
            # Remember-me: 30-day absolute max from creation
            if now - created > self._remember_expiry:
                del self._sessions[token]
                return False
        else:
            # Non-remember: 24h idle timeout AND 48h absolute max
            if now - session["last_seen"] > self._session_expiry:
                del self._sessions[token]
                return False
            if now - created > self._session_absolute_max:
                del self._sessions[token]
                return False

        session["last_seen"] = now
        return True

    def _invalidate_session(self, token: str) -> None:
        """Remove a session token (logout)."""
        self._sessions.pop(token, None)
        self._persist_sessions()

    def _cleanup_auth(self) -> None:
        """Prune expired sessions and stale rate limit entries."""
        now = time.time()
        expired_blocks = [ip for ip, exp in self._blocked_ips.items() if now >= exp]
        for ip in expired_blocks:
            del self._blocked_ips[ip]
        empty = [ip for ip, a in self._failed_attempts.items() if not a]
        for ip in empty:
            del self._failed_attempts[ip]
        expired_sessions = []
        for t, s in self._sessions.items():
            created = s.get("created_at", s["last_seen"])
            if s["remember"]:
                if now - created > self._remember_expiry:
                    expired_sessions.append(t)
            else:
                if (now - s["last_seen"] > self._session_expiry
                        or now - created > self._session_absolute_max):
                    expired_sessions.append(t)
        for t in expired_sessions:
            del self._sessions[t]
        if expired_sessions:
            self._persist_sessions()

    # --- IP whitelist ---

    def _check_ip_whitelist(self, ip: str) -> bool:
        """Check if IP is allowed. Returns True if allowed."""
        if not self._settings.get("ip_whitelist_enabled", False):
            return True
        whitelist = self._settings.get("ip_whitelist", [])
        if not whitelist:
            return True  # empty whitelist = allow all
        return ip in whitelist

    async def _enforce_ip_whitelist(self) -> None:
        """Disconnect any authenticated clients whose IP is no longer whitelisted.

        Called after IP whitelist settings change and periodically in broadcast loop.
        If a phone is lost/stolen, removing its IP immediately kills the session.
        """
        if not self._client_ips:
            return
        if not self._settings.get("ip_whitelist_enabled", False):
            return
        whitelist = self._settings.get("ip_whitelist", [])
        if not whitelist:
            return  # empty whitelist = allow all (don't lock everyone out)
        to_disconnect: list[tuple[Any, str]] = []
        for ws, client_ip in list(self._client_ips.items()):
            if client_ip not in whitelist:
                to_disconnect.append((ws, client_ip))
        for ws, client_ip in to_disconnect:
            logger.warning(f"[Auth] Force disconnecting {client_ip} (IP not in whitelist: {whitelist})")
            # Invalidate any sessions from this IP
            self._invalidate_sessions_by_ip(client_ip)
            try:
                await ws.send(json.dumps({
                    "type": "auth_denied",
                    "reason": "IP removed from whitelist",
                }))
                await ws.close()
            except Exception:
                pass
            self._clients.discard(ws)
            self._client_ips.pop(ws, None)
            self._auth_logger.warning(f"{client_ip} - Force disconnected (IP removed from whitelist)")
            self._record_auth_event("ip_revoked", client_ip, details="IP removed from whitelist while connected")

    def _invalidate_sessions_by_ip(self, target_ip: str) -> None:
        """Invalidate all stored sessions created from the given IP."""
        to_remove = [
            token for token, data in self._sessions.items()
            if data.get("ip") == target_ip
        ]
        for token in to_remove:
            del self._sessions[token]
        if to_remove:
            self._persist_sessions()
            logger.info(f"[Auth] Invalidated {len(to_remove)} session(s) from IP {target_ip}")

    # --- Auth events ---

    @staticmethod
    def _mask_password(password: str) -> str:
        """Mask a password for safe logging (e.g., 'co******')."""
        if not password:
            return ""
        if len(password) <= 2:
            return password[0] + "*" * 7
        return password[:2] + "*" * min(len(password) - 2, 6)

    def _record_auth_event(
        self, event: str, ip: str, username: str = "", password: str = "",
        browser: str = "", os_info: str = "", details: str = "",
    ) -> None:
        """Record an authentication event for the Auth Log page."""
        entry = {
            "timestamp": time.time(),
            "event": event,
            "ip": ip,
            "username": username,
            "password": self._mask_password(password),
            "browser": browser,
            "os": os_info,
            "details": details,
        }
        self._auth_events.append(entry)
        if len(self._auth_events) > self._max_auth_events:
            self._auth_events = self._auth_events[-self._max_auth_events:]
        self._persist_auth_event(entry)

    # --- User-Agent parsing ---

    @staticmethod
    def _parse_user_agent(ua: str) -> tuple[str, str]:
        """Parse User-Agent string into (browser, os). Simple substring matching."""
        # Browser detection (order matters: Edge contains Chrome, etc.)
        browser = "Unknown"
        if "Edg/" in ua or "Edge/" in ua:
            m = re.search(r"Edg/(\d+)", ua)
            browser = f"Edge {m.group(1)}" if m else "Edge"
        elif "OPR/" in ua or "Opera" in ua:
            m = re.search(r"OPR/(\d+)", ua)
            browser = f"Opera {m.group(1)}" if m else "Opera"
        elif "Chrome/" in ua and "Safari/" in ua:
            m = re.search(r"Chrome/(\d+)", ua)
            browser = f"Chrome {m.group(1)}" if m else "Chrome"
        elif "Firefox/" in ua:
            m = re.search(r"Firefox/(\d+)", ua)
            browser = f"Firefox {m.group(1)}" if m else "Firefox"
        elif "Safari/" in ua:
            m = re.search(r"Version/(\d+)", ua)
            browser = f"Safari {m.group(1)}" if m else "Safari"

        # OS detection
        os_info = "Unknown"
        if "Windows NT 10" in ua:
            os_info = "Windows 10/11"
        elif "Windows NT" in ua:
            os_info = "Windows"
        elif "Macintosh" in ua or "Mac OS X" in ua:
            os_info = "macOS"
        elif "Android" in ua:
            m = re.search(r"Android (\d+)", ua)
            os_info = f"Android {m.group(1)}" if m else "Android"
        elif "iPhone" in ua or "iPad" in ua:
            os_info = "iOS"
        elif "Linux" in ua:
            os_info = "Linux"

        return browser, os_info

    # --- reCAPTCHA ---

    def _is_captcha_required(self, ip: str) -> bool:
        """Check if CAPTCHA is required for this IP (after N failures)."""
        if not RECAPTCHA_SITE_KEY or not RECAPTCHA_SECRET_KEY:
            return False
        count = len(self._failed_attempts.get(ip, []))
        return count >= self._captcha_threshold

    async def _verify_recaptcha(self, token: str, ip: str) -> bool:
        """Verify reCAPTCHA token with Google. Non-blocking."""
        if not RECAPTCHA_SECRET_KEY:
            return True
        try:
            data = urllib.parse.urlencode({
                "secret": RECAPTCHA_SECRET_KEY,
                "response": token,
                "remoteip": ip,
            }).encode()
            req = urllib.request.Request(
                "https://www.google.com/recaptcha/api/siteverify",
                data=data,
                method="POST",
            )

            def _do_verify() -> bool:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    result = json.loads(resp.read())
                    return result.get("success", False)

            return await asyncio.to_thread(_do_verify)
        except Exception as e:
            logger.warning(f"[Auth] reCAPTCHA verification failed: {e}")
            return False

    def stop(self) -> None:
        self._running = False
        self._persist_sessions()

    def set_demo_fetcher(self, demo_fetcher: "DemoPortfolioFetcher") -> None:
        """Attach the demo portfolio fetcher for comparison data."""
        self._demo_fetcher = demo_fetcher

    async def _check_origin(self, connection: Any, request: Any) -> None:
        """Validate Origin header for CSRF protection (process_request callback)."""
        origin = ""
        if hasattr(request, "headers"):
            origin = request.headers.get("Origin", "")
        if not origin:
            return None  # Allow connections without Origin (direct WS tools)

        # Always allow localhost origins for development
        for allowed_host in ("http://localhost", "https://localhost",
                             "http://127.0.0.1", "https://127.0.0.1"):
            if origin == allowed_host or origin.startswith(allowed_host + ":"):
                return None

        # Check configured allowed origins
        for allowed in ALLOWED_ORIGINS:
            if origin == allowed or origin.startswith(allowed + ":"):
                return None

        logger.warning(f"[Auth] Rejected WebSocket from origin: {origin}")
        return connection.respond(403, "Forbidden\n")

    async def run(self) -> None:
        """Start WebSocket server and broadcast state every second."""
        self._running = True
        self._start_time = time.time()
        self._load_uptime_data()

        # Proxy (Zurich VPS) tracking
        self._bitfinex_fetcher = next(
            (f for f in self._fetchers if f.exchange_name == "Bitfinex"), None
        )
        self._load_proxy_uptime_data()

        # Apply exchange enabled/disabled state from persisted settings
        fee_configs = self._settings.get("fee_configs")
        if fee_configs:
            self._apply_enabled_exchanges(fee_configs)

        # Sync persisted settings to components at startup.
        # run.py passes some settings to constructors, but may use stale defaults
        # if settings.json was updated via dashboard in a previous session.
        # This ensures values like hourly_external_transfer_cap are current.
        self._sync_settings_on_startup(self._settings)

        # Schedule restart grace period end
        if self._restart_grace:
            asyncio.get_event_loop().call_later(30.0, self._clear_restart_grace)

        serve_kwargs: dict[str, Any] = {
            "ping_interval": 20,
            "ping_timeout": 60,
        }
        if ALLOWED_ORIGINS:
            serve_kwargs["process_request"] = self._check_origin

        async with websockets.serve(
            self._handle_client,
            DASHBOARD_BIND_HOST,
            DASHBOARD_WS_PORT,
            **serve_kwargs,
        ):
            logger.info(
                f"[Dashboard] WebSocket server started on ws://{DASHBOARD_BIND_HOST}:{DASHBOARD_WS_PORT}"
            )
            # Log version and all settings 10s after server start (ensures log handler is ready for export)
            def _log_startup():
                from config import __version__
                logger.info(f"[Config] version=v{__version__}")
                self._log_all_settings("session_start")
            asyncio.get_event_loop().call_later(10.0, _log_startup)
            while self._running:
                if self._clients:
                    state = self._build_state()
                    payload = json.dumps(state)
                    dead: set[Any] = set()
                    for ws in self._clients:
                        try:
                            await ws.send(payload)
                        except Exception:
                            dead.add(ws)
                    self._clients -= dead
                    for ws in dead:
                        self._client_ips.pop(ws, None)
                # Periodic uptime heartbeat (~every 60s)
                self._save_uptime_heartbeat()
                # Track proxy (Zurich VPS) connection state
                self._track_proxy_state()
                # Periodic auth cleanup (~every 5 min)
                now = time.time()
                if now - self._last_cleanup > 300:
                    self._cleanup_auth()
                    self._last_cleanup = now
                # Enforce IP whitelist on every broadcast cycle (~1s)
                await self._enforce_ip_whitelist()
                await asyncio.sleep(1.0)

        logger.info("[Dashboard] WebSocket server stopped")

    async def _handle_client(self, ws: Any) -> None:
        """Handle a new WebSocket client connection with authentication."""
        # Extract real client IP (behind reverse proxy) and User-Agent
        raw_ip = ws.remote_address[0] if ws.remote_address else "unknown"
        if hasattr(ws, "request") and hasattr(ws.request, "headers"):
            headers = ws.request.headers
        elif hasattr(ws, "request_headers"):
            headers = ws.request_headers
        else:
            headers = {}
        # Only trust X-Forwarded-For from known reverse proxies
        forwarded = headers.get("X-Forwarded-For", "")
        if forwarded and raw_ip in TRUSTED_PROXIES:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = raw_ip
        ua = headers.get("User-Agent", "")
        browser, os_info = self._parse_user_agent(ua)

        # IP whitelist check
        if not self._check_ip_whitelist(ip):
            self._auth_logger.warning(f"{ip} - Connection denied (IP not in whitelist)")
            self._record_auth_event("ip_denied", ip, browser=browser, os_info=os_info)
            await ws.send(json.dumps({
                "type": "auth_denied",
                "reason": "IP not allowed",
            }))
            await ws.close()
            return

        # Rate limit check
        is_blocked, _, retry_after = self._check_rate_limit(ip)
        if is_blocked:
            self._auth_logger.info(f"{ip} - Connection denied (blocked, {retry_after}s remaining)")
            self._record_auth_event("blocked", ip, browser=browser, os_info=os_info, details=f"retry_after={retry_after}s")
            await ws.send(json.dumps({
                "type": "auth_blocked",
                "reason": f"Too many failed attempts. Try again in {retry_after // 60} minutes.",
                "retry_after": retry_after,
            }))
            await ws.close()
            return

        # Request authentication (include captcha info if needed)
        captcha_needed = self._is_captcha_required(ip)
        auth_msg: dict[str, Any] = {"type": "auth_required"}
        if captcha_needed:
            auth_msg["captcha_required"] = True
            auth_msg["captcha_site_key"] = RECAPTCHA_SITE_KEY
        await ws.send(json.dumps(auth_msg))

        authenticated = False
        session_token = None

        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if not authenticated:
                    if msg.get("type") != "auth":
                        continue

                    # Try token-based reconnection
                    token = msg.get("token")
                    if token and self._validate_session(token):
                        authenticated = True
                        session_token = token
                        await ws.send(json.dumps({"type": "auth_ok", "token": token}))
                        self._clients.add(ws)
                        self._client_ips[ws] = ip
                        await ws.send(json.dumps(self._build_state()))
                        self._auth_logger.info(f"{ip} - Reconnected with session token")
                        self._record_auth_event("reconnected", ip, browser=browser, os_info=os_info)
                        continue

                    # Username/password authentication
                    username = msg.get("username", "")
                    password = msg.get("password", "")
                    remember = msg.get("remember", False)

                    # Re-check rate limit
                    is_blocked, remaining, retry_after = self._check_rate_limit(ip)
                    if is_blocked:
                        self._auth_logger.info(f"{ip} - Blocked during auth")
                        self._record_auth_event("blocked", ip, username=username, browser=browser, os_info=os_info)
                        await ws.send(json.dumps({
                            "type": "auth_blocked",
                            "reason": f"Too many failed attempts. Try again in {retry_after // 60} minutes.",
                            "retry_after": retry_after,
                        }))
                        await ws.close()
                        return

                    # reCAPTCHA check (required after N failures)
                    if self._is_captcha_required(ip):
                        captcha_token = msg.get("captcha_token", "")
                        if not captcha_token:
                            remaining = self._record_failed_attempt(ip)
                            if remaining <= 0:
                                self._record_auth_event("blocked", ip, browser=browser, os_info=os_info, details="CAPTCHA not provided")
                                _safe_task(notify_blocked(ip, browser, os_info), "notify_blocked")
                                await ws.send(json.dumps({
                                    "type": "auth_blocked",
                                    "reason": "Too many failed attempts. Try again in 60 minutes.",
                                    "retry_after": int(self._block_duration),
                                }))
                                await ws.close()
                                return
                            await ws.send(json.dumps({
                                "type": "auth_failed",
                                "reason": "Please complete the CAPTCHA",
                                "captcha_required": True,
                                "captcha_site_key": RECAPTCHA_SITE_KEY,
                                "attempts_remaining": remaining,
                            }))
                            continue
                        if not await self._verify_recaptcha(captcha_token, ip):
                            remaining = self._record_failed_attempt(ip)
                            if remaining <= 0:
                                self._record_auth_event("blocked", ip, browser=browser, os_info=os_info, details="CAPTCHA verification failed")
                                _safe_task(notify_blocked(ip, browser, os_info), "notify_blocked")
                                await ws.send(json.dumps({
                                    "type": "auth_blocked",
                                    "reason": "Too many failed attempts. Try again in 60 minutes.",
                                    "retry_after": int(self._block_duration),
                                }))
                                await ws.close()
                                return
                            await ws.send(json.dumps({
                                "type": "auth_failed",
                                "reason": "CAPTCHA verification failed. Please try again.",
                                "captcha_required": True,
                                "captcha_site_key": RECAPTCHA_SITE_KEY,
                                "attempts_remaining": remaining,
                            }))
                            continue

                    if username == DASHBOARD_USERNAME and verify_dashboard_password(password):
                        authenticated = True
                        session_token = self._create_session(ip, remember)
                        self._failed_attempts.pop(ip, None)
                        await ws.send(json.dumps({"type": "auth_ok", "token": session_token}))
                        self._clients.add(ws)
                        self._client_ips[ws] = ip
                        await ws.send(json.dumps(self._build_state()))
                        self._auth_logger.info(f"{ip} - Login successful ({username}, remember={remember})")
                        self._record_auth_event(
                            "login_success", ip, username=username, password=password,
                            browser=browser, os_info=os_info, details=f"remember={remember}",
                        )
                        # Fire-and-forget email notification (skip during restart grace)
                        if not self._restart_grace:
                            _safe_task(notify_login(ip, browser, os_info), "notify_login")
                    else:
                        remaining = self._record_failed_attempt(ip)
                        self._auth_logger.warning(f"{ip} - Login failed (user={username}, {remaining} attempts remaining)")
                        self._record_auth_event(
                            "login_failed", ip, username=username, password=password,
                            browser=browser, os_info=os_info, details=f"{remaining} attempts remaining",
                        )

                        if remaining <= 0:
                            self._record_auth_event("blocked", ip, username=username, browser=browser, os_info=os_info, details="10 failed attempts")
                            # Fire-and-forget email notification
                            _safe_task(notify_blocked(ip, browser, os_info), "notify_blocked")
                            await ws.send(json.dumps({
                                "type": "auth_blocked",
                                "reason": "Too many failed attempts. Try again in 60 minutes.",
                                "retry_after": int(self._block_duration),
                            }))
                            await ws.close()
                            return

                        # Include captcha info if threshold reached
                        fail_response: dict[str, Any] = {
                            "type": "auth_failed",
                            "reason": "Invalid credentials",
                            "attempts_remaining": remaining,
                        }
                        if self._is_captcha_required(ip):
                            fail_response["captcha_required"] = True
                            fail_response["captcha_site_key"] = RECAPTCHA_SITE_KEY
                        await ws.send(json.dumps(fail_response))
                else:
                    # Authenticated — handle normal messages
                    if msg.get("type") == "logout":
                        if session_token:
                            self._invalidate_session(session_token)
                        self._auth_logger.info(f"{ip} - Logged out")
                        self._record_auth_event("logout", ip, browser=browser, os_info=os_info)
                        await ws.send(json.dumps({"type": "logged_out"}))
                        await ws.close()
                        return
                    await self._handle_message(msg, ws)
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            self._client_ips.pop(ws, None)
            if authenticated:
                logger.info(f"[Dashboard] Client {ip} disconnected ({len(self._clients)} total)")

    # --- Settings validation ---

    _SETTINGS_SCHEMA: dict[str, tuple[type, float | None, float | None]] = {
        "trade_amount_usd": (float, 1, 100000),
        "trade_amount_pct": (float, 0.0, 0.50),
        "total_capital": (float, 1, 10000000),
        "auto_rotate": (bool, None, None),
        "num_active_symbols": (int, 1, 60),
        "max_active_symbols": (int, 1, 60),
        "scoring_window": (int, 60, 86400),
        "evaluation_interval": (int, 10, 86400),
        "safety_multiplier": (float, 0.1, 100),
        "discovery_duration": (int, 30, 3600),
        "min_rebalance_score": (float, 0, 1),
        "confirmation_period": (int, 0, 86400),
        "score_stability_seconds": (int, 0, 3600),
        "score_stability_factor": (float, 0.0, 1.0),
        "promotion_threshold": (float, 0, 1),
        "demotion_threshold": (float, 0, 1),
        "demotion_period": (int, 0, 86400),
        "min_net_profit_pct": (float, 0, 10),
        "rebalance_cooldown": (float, 0, 3600),
        "min_misses_before_rebalance": (int, 1, 100),
        "rebalance_roi_horizon": (int, 0, 86400),
        "adaptive_mode": (bool, None, None),
        "execution_mode": (str, None, None),
        "trading_score_threshold": (float, 0.0001, 0.5),
        "strong_score_threshold": (float, 0.01, 1.0),
        "very_strong_score_threshold": (float, 0.05, 2.0),
        "fee_threshold_multiplier": (float, 0.0, 5.0),
        "net_pnl_gate_warmup_trades": (int, 1, 200),
        "net_pnl_gate_grace_seconds": (int, 60, 7200),
        "rebalance_roi_divisor": (int, 2, 20),
        "reallocation_cost_horizon": (float, 0.5, 24.0),
        "demotion_cooldown_multiplier": (float, 1.0, 20.0),
        "hourly_external_transfer_cap": (float, 0, 100.0),
        "bitfinex_reserve_pct": (float, 0.0, 0.5),
        "bitfinex_reserve_hard_floor": (float, 0.0, 0.20),
        "net_pct_sizing_enabled": (bool, None, None),
        "net_pct_multiplier_cap": (float, 1.0, 10.0),
        "spread_persistence_ticks": (int, 0, 5),
        "event_driven_seller_penalty_pct": (float, 0.0, 1.0),
        "one_leg_failure_rate": (float, 0.0, 0.20),
        "one_leg_unwind_slippage_mult": (float, 1.0, 5.0),
        "max_position_multiplier": (float, 0, 50),
        # Anomaly protection
        "anomaly_protection_enabled": (bool, None, None),
        "circuit_breaker_window": (int, 60, 7200),
        "circuit_breaker_threshold": (float, -1000, 0),
        "circuit_breaker_resume_pct": (float, 0.1, 1.0),
        "circuit_breaker_cooldown": (int, 30, 3600),
        "drawdown_threshold_pct": (float, 0.5, 20.0),
        "drawdown_resume_pct": (float, 0.1, 10.0),
        "drawdown_emergency_mult": (float, 1.5, 5.0),
        "symbol_loss_streak_threshold": (int, 2, 50),
        "symbol_loss_streak_cooldown": (int, 60, 7200),
        "warning_pnl_pct": (float, 0.1, 1.0),
    }

    _SETTINGS_ENUMS: dict[str, list[str]] = {
        "execution_mode": ["simulation", "demo", "demo_only"],
    }

    @classmethod
    def _validate_settings(cls, settings: dict) -> tuple[bool, str]:
        """Validate settings dict. Returns (ok, error_message)."""
        for key, value in settings.items():
            if key not in cls._SETTINGS_SCHEMA:
                return False, f"Unknown setting: {key}"
            expected_type, min_val, max_val = cls._SETTINGS_SCHEMA[key]
            if expected_type == bool:
                if not isinstance(value, bool):
                    return False, f"{key} must be boolean"
            elif expected_type == str:
                if not isinstance(value, str):
                    return False, f"{key} must be a string"
                allowed = cls._SETTINGS_ENUMS.get(key, [])
                if allowed and value not in allowed:
                    return False, f"{key} must be one of {allowed}"
            elif expected_type in (int, float):
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    return False, f"{key} must be a number"
                if min_val is not None and value < min_val:
                    return False, f"{key} must be >= {min_val}"
                if max_val is not None and value > max_val:
                    return False, f"{key} must be <= {max_val}"
        return True, ""

    _FEE_CONFIG_SCHEMA: dict[str, tuple[type, float | None, float | None]] = {
        "base_taker_rate": (float, 0.0, 0.01),
        "token_discount_enabled": (bool, None, None),
        "token_discount_pct": (float, 0.0, 1.0),
        "fee_mechanism": (str, None, None),
        "fee_model": (str, None, None),
        "referral_enabled": (bool, None, None),
        "referral_cashback_pct": (float, 0.0, 1.0),
        "referral_settlement_minutes": (float, 0, 10080),
        "referral_paid_in": (str, None, None),
        "referrer_commission_pct": (float, 0.0, 1.0),
        "zero_fee_pairs": (list, None, None),
        "enabled": (bool, None, None),
    }
    _FEE_ENUMS: dict[str, list[str]] = {
        "fee_mechanism": ["instant", "rebate", "tier"],
        "fee_model": ["received", "spent", "token"],
        "referral_paid_in": ["same_as_fee", "USDT"],
    }

    _TRANSFER_NETWORK_SCHEMA: dict[str, tuple[type, float | None, float | None]] = {
        "network": (str, None, None),
        "fee": (float, 0.0, 100.0),
        "fee_type": (str, None, None),
        "percentage_rate": (float, 0.0, 1.0),
        "percentage_min": (float, 0.0, 100.0),
        "min_withdrawal": (float, 0.0, 100000.0),
        "speed_seconds": (float, 0.0, 86400.0),
        "enabled": (bool, None, None),
        "notes": (str, None, None),
    }
    _TRANSFER_ENUMS: dict[str, list[str]] = {
        "fee_type": ["flat", "percentage", "conditional"],
    }

    @classmethod
    def _validate_transfer_settings(cls, transfer_configs: dict) -> tuple[bool, str]:
        """Validate per-exchange transfer fee config dict."""
        if not isinstance(transfer_configs, dict):
            return False, "transfer_configs must be a dict"
        for exchange, cfg in transfer_configs.items():
            if not isinstance(exchange, str):
                return False, "Exchange name must be a string"
            if not isinstance(cfg, dict):
                return False, f"{exchange}: config must be a dict"
            pref = cfg.get("preferred_network", "auto")
            if not isinstance(pref, str):
                return False, f"{exchange}.preferred_network must be a string"
            networks = cfg.get("networks", [])
            if not isinstance(networks, list):
                return False, f"{exchange}.networks must be a list"
            for i, net in enumerate(networks):
                if not isinstance(net, dict):
                    return False, f"{exchange}.networks[{i}] must be a dict"
                for key, value in net.items():
                    if key not in cls._TRANSFER_NETWORK_SCHEMA:
                        return False, f"{exchange}.networks[{i}]: unknown key '{key}'"
                    expected_type, min_val, max_val = cls._TRANSFER_NETWORK_SCHEMA[key]
                    if expected_type == bool:
                        if not isinstance(value, bool):
                            return False, f"{exchange}.networks[{i}].{key} must be boolean"
                    elif expected_type == str:
                        if not isinstance(value, str):
                            return False, f"{exchange}.networks[{i}].{key} must be a string"
                        allowed = cls._TRANSFER_ENUMS.get(key, [])
                        if allowed and value not in allowed:
                            return False, f"{exchange}.networks[{i}].{key} must be one of {allowed}"
                    elif expected_type in (int, float):
                        if not isinstance(value, (int, float)) or isinstance(value, bool):
                            return False, f"{exchange}.networks[{i}].{key} must be a number"
                        if min_val is not None and value < min_val:
                            return False, f"{exchange}.networks[{i}].{key} must be >= {min_val}"
                        if max_val is not None and value > max_val:
                            return False, f"{exchange}.networks[{i}].{key} must be <= {max_val}"
        return True, ""

    @classmethod
    def _validate_fee_settings(cls, fee_configs: dict) -> tuple[bool, str]:
        """Validate per-exchange fee config dict."""
        if not isinstance(fee_configs, dict):
            return False, "fee_configs must be a dict"
        for exchange, cfg in fee_configs.items():
            if not isinstance(exchange, str):
                return False, "Exchange name must be a string"
            if not isinstance(cfg, dict):
                return False, f"{exchange}: config must be a dict"
            for key, value in cfg.items():
                if key not in cls._FEE_CONFIG_SCHEMA:
                    return False, f"{exchange}: unknown fee setting '{key}'"
                expected_type, min_val, max_val = cls._FEE_CONFIG_SCHEMA[key]
                if expected_type == bool:
                    if not isinstance(value, bool):
                        return False, f"{exchange}.{key} must be boolean"
                elif expected_type == str:
                    if not isinstance(value, str):
                        return False, f"{exchange}.{key} must be a string"
                    allowed = cls._FEE_ENUMS.get(key, [])
                    if allowed and value not in allowed:
                        return False, f"{exchange}.{key} must be one of {allowed}"
                elif expected_type == list:
                    if not isinstance(value, list):
                        return False, f"{exchange}.{key} must be a list"
                elif expected_type in (int, float):
                    if not isinstance(value, (int, float)) or isinstance(value, bool):
                        return False, f"{exchange}.{key} must be a number"
                    if min_val is not None and value < min_val:
                        return False, f"{exchange}.{key} must be >= {min_val}"
                    if max_val is not None and value > max_val:
                        return False, f"{exchange}.{key} must be <= {max_val}"
        return True, ""

    @staticmethod
    def _validate_security_settings(settings: dict) -> tuple[bool, str]:
        """Validate security settings dict."""
        import ipaddress

        allowed_keys = {"ip_whitelist_enabled", "ip_whitelist"}
        for key in settings:
            if key not in allowed_keys:
                return False, f"Unknown security setting: {key}"
        if "ip_whitelist_enabled" in settings:
            if not isinstance(settings["ip_whitelist_enabled"], bool):
                return False, "ip_whitelist_enabled must be boolean"
        if "ip_whitelist" in settings:
            if not isinstance(settings["ip_whitelist"], list):
                return False, "ip_whitelist must be a list"
            for ip_str in settings["ip_whitelist"]:
                if not isinstance(ip_str, str):
                    return False, "ip_whitelist entries must be strings"
                try:
                    ipaddress.ip_address(ip_str.strip())
                except ValueError:
                    return False, f"Invalid IP address: {ip_str}"
        return True, ""

    async def _handle_message(self, msg: dict, ws: Any) -> None:
        """Process an incoming message from the dashboard."""
        msg_type = msg.get("type", "")

        if msg_type == "get_settings":
            await ws.send(json.dumps({"type": "settings", "settings": self._settings}))

        elif msg_type == "save_settings":
            now = time.time()
            if now - self._last_settings_save < self._settings_cooldown:
                await ws.send(json.dumps({"type": "settings_error", "error": f"Please wait {int(self._settings_cooldown)}s between saves."}))
                return
            new_settings = msg.get("settings", {})
            ok, err = self._validate_settings(new_settings)
            if not ok:
                await ws.send(json.dumps({"type": "settings_error", "error": err}))
                return
            self._last_settings_save = now
            self._settings.update(new_settings)
            save_settings(self._settings)
            await ws.send(json.dumps({"type": "settings_saved", "ok": True}))
            logger.info("[Dashboard] Settings saved to file")

        elif msg_type == "apply_settings":
            now = time.time()
            if now - self._last_settings_save < self._settings_cooldown:
                await ws.send(json.dumps({"type": "settings_error", "error": f"Please wait {int(self._settings_cooldown)}s between applies."}))
                return
            new_settings = msg.get("settings", {})
            ok, err = self._validate_settings(new_settings)
            if not ok:
                await ws.send(json.dumps({"type": "settings_error", "error": err}))
                return
            self._last_settings_save = now
            self._settings.update(new_settings)
            save_settings(self._settings)
            self._apply_settings(self._settings)
            await ws.send(json.dumps({"type": "settings_applied", "ok": True}))
            logger.info("[Dashboard] Settings applied and simulation reset")

        elif msg_type == "save_security_settings":
            now = time.time()
            if now - self._last_settings_save < self._settings_cooldown:
                await ws.send(json.dumps({"type": "settings_error", "error": f"Please wait {int(self._settings_cooldown)}s between saves."}))
                return
            security = msg.get("settings", {})
            ok, err = self._validate_security_settings(security)
            if not ok:
                await ws.send(json.dumps({"type": "settings_error", "error": err}))
                return
            self._last_settings_save = now
            if "ip_whitelist_enabled" in security:
                self._settings["ip_whitelist_enabled"] = security["ip_whitelist_enabled"]
            if "ip_whitelist" in security:
                self._settings["ip_whitelist"] = security["ip_whitelist"]
            save_settings(self._settings)
            await ws.send(json.dumps({"type": "security_settings_saved", "ok": True}))
            logger.info("[Dashboard] Security settings saved")
            # Immediately disconnect clients whose IP is no longer whitelisted
            await self._enforce_ip_whitelist()

        elif msg_type == "save_fee_settings":
            now = time.time()
            if now - self._last_settings_save < self._settings_cooldown:
                await ws.send(json.dumps({
                    "type": "fee_settings_error",
                    "error": f"Please wait {int(self._settings_cooldown)}s between saves.",
                }))
                return
            fee_data = msg.get("fee_configs", {})
            fee_real_mode = msg.get("fee_real_mode", None)
            ok, err = self._validate_fee_settings(fee_data)
            if not ok:
                await ws.send(json.dumps({"type": "fee_settings_error", "error": err}))
                return
            self._last_settings_save = now
            # Persist to settings.json
            self._settings["fee_configs"] = fee_data
            if fee_real_mode is not None:
                self._settings["fee_real_mode"] = bool(fee_real_mode)
            save_settings(self._settings)
            # Hot-apply to FeeManager
            if self._fee_manager:
                self._fee_manager.update_from_settings(fee_data)
                if fee_real_mode is not None:
                    self._fee_manager.real_mode = bool(fee_real_mode)
            # Hot-apply enabled/disabled exchanges to components
            self._apply_enabled_exchanges(fee_data)
            await ws.send(json.dumps({"type": "fee_settings_saved", "ok": True}))
            logger.info("[Fee] Fee settings saved and applied")

        elif msg_type == "save_transfer_settings":
            now = time.time()
            if now - self._last_settings_save < self._settings_cooldown:
                await ws.send(json.dumps({
                    "type": "transfer_settings_error",
                    "error": f"Please wait {int(self._settings_cooldown)}s between saves.",
                }))
                return
            transfer_data = msg.get("transfer_configs", {})
            ok, err = self._validate_transfer_settings(transfer_data)
            if not ok:
                await ws.send(json.dumps({"type": "transfer_settings_error", "error": err}))
                return
            self._last_settings_save = now
            # Persist to settings.json
            self._settings["transfer_configs"] = transfer_data
            save_settings(self._settings)
            # Hot-apply to TransferFeeManager
            if self._transfer_fee_mgr:
                self._transfer_fee_mgr.update_from_settings(transfer_data)
            await ws.send(json.dumps({"type": "transfer_settings_saved", "ok": True}))
            logger.info("[Transfer] Transfer fee settings saved and applied")

        elif msg_type == "request_all_bot_logs":
            # Return ALL in-memory session logs (for filtered views)
            entries = self._log_handler.get_all() if self._log_handler else []
            await ws.send(json.dumps({"type": "all_bot_logs_result", "logs": entries}))

        elif msg_type == "export_bot_logs":
            start_ts = msg.get("start", 0)
            end_ts = msg.get("end", time.time())
            entries = await asyncio.to_thread(self._read_bot_logs_from_disk, start_ts, end_ts)
            await ws.send(json.dumps({"type": "export_bot_logs_result", "logs": entries}))

        elif msg_type == "export_auth_logs":
            start_ts = msg.get("start", 0)
            end_ts = msg.get("end", time.time())
            entries = await asyncio.to_thread(self._read_auth_logs_from_disk, start_ts, end_ts)
            await ws.send(json.dumps({"type": "export_auth_logs_result", "logs": entries}))

        elif msg_type == "anomaly_resume":
            self._monitor._anomaly.manual_resume()
            self._monitor._anomaly_paused = False
            logger.info("[Dashboard] Anomaly protection manually resumed")

        elif msg_type == "manual_stop":
            self._monitor._manual_stopped = True
            self._monitor._manual_stop_timestamp = time.time()
            logger.info("[Monitor] MANUAL_STOP by operator")

        elif msg_type == "manual_start":
            self._monitor._manual_stopped = False
            self._monitor._manual_stop_timestamp = 0.0
            logger.info("[Monitor] MANUAL_START by operator")

        elif msg_type == "hard_stop":
            transfer_to_bitfinex = msg.get("transfer_to_bitfinex", True)
            self._monitor._manual_stopped = True
            self._monitor._manual_stop_timestamp = time.time()
            result = self._hard_stop_all(transfer_to_bitfinex)
            if transfer_to_bitfinex:
                self._distribute_enabled = True
            await ws.send(json.dumps({"type": "hard_stop_result", **result}))

        elif msg_type == "distribute_from_bitfinex":
            if not self._distribute_enabled:
                await ws.send(json.dumps({
                    "type": "distribute_error",
                    "error": "Distribution not enabled",
                }))
                return
            result = self._distribute_from_bitfinex()
            self._distribute_enabled = False
            await ws.send(json.dumps({"type": "distribute_result", **result}))

        elif msg_type == "restart":
            logger.info("[Dashboard] Fresh restart requested from dashboard")
            if self._state_manager:
                self._state_manager.clear()
            await ws.send(json.dumps({"type": "restart_ack"}))
            asyncio.get_event_loop().call_later(1.0, self._trigger_restart)

    def _trigger_restart(self) -> None:
        """Restart the bot process by replacing it with a fresh one."""
        import os as _os
        import sys as _sys

        # Write restart marker so the next startup suppresses login emails
        marker = Path("state/restart_marker")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(time.time()))

        # Clear uptime data — intentional restart starts fresh
        try:
            Path("state/uptime.json").unlink(missing_ok=True)
            Path("state/proxy_uptime.json").unlink(missing_ok=True)
        except OSError:
            pass

        logger.info("[Dashboard] Restarting process via execv...")
        _os.execv(_sys.executable, [_sys.executable] + _sys.argv)

    def _check_restart_marker(self) -> None:
        """Check if a restart marker exists from a recent restart. If so, suppress login emails for 30s."""
        marker = Path("state/restart_marker")
        if marker.exists():
            try:
                age = time.time() - float(marker.read_text().strip())
                if age < 60:
                    self._restart_grace = True
                    logger.info(f"[Dashboard] Restart marker found ({age:.0f}s old), suppressing login emails for 30s")
            except (ValueError, OSError):
                pass
            try:
                marker.unlink()
            except OSError:
                pass

    def _clear_restart_grace(self) -> None:
        """Called ~30s after startup to re-enable login email notifications."""
        self._restart_grace = False
        logger.info("[Dashboard] Restart grace period ended, login emails re-enabled")

    # --- Uptime tracking ---

    _DOWNTIME_THRESHOLD = 90.0  # seconds — gaps shorter than this are ignored

    def _load_uptime_data(self) -> None:
        """Load uptime data from state/uptime.json. Detect downtime gaps."""
        now = time.time()

        # Intentional restart → start fresh
        if self._restart_grace:
            try:
                self._uptime_file.unlink(missing_ok=True)
            except OSError:
                pass
            self._uptime_data = {
                "first_start": now,
                "last_heartbeat": now,
                "downtimes": [],
            }
            self._save_uptime_heartbeat(force=True)
            logger.info(
                f"[Uptime] Bangkok VPS fresh start (intentional restart) at "
                f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now))} UTC"
            )
            return

        # Try to load existing data
        if self._uptime_file.exists():
            try:
                with open(self._uptime_file) as f:
                    data = json.load(f)
                last_hb = data.get("last_heartbeat", now)
                gap = now - last_hb
                downtimes = data.get("downtimes", [])

                if gap > self._DOWNTIME_THRESHOLD:
                    downtimes.append({
                        "start": last_hb,
                        "end": now,
                        "duration": round(gap, 1),
                    })
                    logger.info(
                        f"[Uptime] Bangkok VPS was DOWN for {gap:.0f}s "
                        f"({time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(last_hb))} → "
                        f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now))} UTC)"
                    )

                self._uptime_data = {
                    "first_start": data.get("first_start", now),
                    "last_heartbeat": now,
                    "downtimes": downtimes[-50:],  # keep last 50
                }
                self._save_uptime_heartbeat(force=True)
                total_down = sum(d["duration"] for d in downtimes)
                first_start = data.get("first_start", now)
                logger.info(
                    f"[Uptime] Bangkok VPS UP at "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now))} UTC "
                    f"(running since {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(first_start))} UTC, "
                    f"{len(downtimes)} downtimes, {total_down:.0f}s total downtime)"
                )
                return
            except (json.JSONDecodeError, OSError, KeyError) as e:
                logger.warning(f"[Uptime] Failed to load {self._uptime_file}: {e}")

        # First ever start
        self._uptime_data = {
            "first_start": now,
            "last_heartbeat": now,
            "downtimes": [],
        }
        self._save_uptime_heartbeat(force=True)
        logger.info(
            f"[Uptime] Bangkok VPS first start at "
            f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now))} UTC"
        )

    def _save_uptime_heartbeat(self, force: bool = False) -> None:
        """Update last_heartbeat and write to disk. Called every 60s."""
        now = time.time()
        if not force and now - self._last_heartbeat_save < 60:
            return
        self._last_heartbeat_save = now
        self._uptime_data["last_heartbeat"] = now
        try:
            self._uptime_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._uptime_file, "w") as f:
                json.dump(self._uptime_data, f)
        except OSError as e:
            logger.warning(f"[Uptime] Failed to save heartbeat: {e}")

    def _get_uptime_info(self) -> dict:
        """Compute true uptime and return broadcast-ready dict."""
        now = time.time()
        if not self._uptime_data:
            return {
                "true_uptime_seconds": round(now - self._start_time, 0),
                "first_start": self._start_time,
                "total_downtime": 0,
                "restart_count": 0,
                "downtimes": [],
            }
        first = self._uptime_data.get("first_start", self._start_time)
        downtimes = self._uptime_data.get("downtimes", [])
        total_down = sum(d["duration"] for d in downtimes)
        true_uptime = (now - first) - total_down
        return {
            "true_uptime_seconds": round(max(0, true_uptime), 0),
            "first_start": first,
            "total_downtime": round(total_down, 0),
            "restart_count": len(downtimes),
            "downtimes": downtimes[-20:],
        }

    # --- Proxy (Zurich VPS) uptime tracking ---

    _PROXY_DOWNTIME_THRESHOLD = 30.0  # seconds — brief reconnections ignored

    def _load_proxy_uptime_data(self) -> None:
        """Load proxy uptime data from state/proxy_uptime.json."""
        if self._restart_grace:
            try:
                self._proxy_uptime_file.unlink(missing_ok=True)
            except OSError:
                pass
            self._proxy_uptime_data = {"first_connected": 0.0, "last_heartbeat": 0.0, "downtimes": []}
            logger.info("[Uptime] Proxy tracking reset (intentional restart)")
            return

        if self._proxy_uptime_file.exists():
            try:
                with open(self._proxy_uptime_file) as f:
                    data = json.load(f)
                self._proxy_uptime_data = {
                    "first_connected": data.get("first_connected", 0.0),
                    "last_heartbeat": data.get("last_heartbeat", 0.0),
                    "downtimes": data.get("downtimes", [])[-50:],
                }
                n = len(self._proxy_uptime_data["downtimes"])
                logger.info(f"[Uptime] Proxy tracking loaded ({n} past outages)")
                return
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[Uptime] Failed to load proxy uptime: {e}")

        self._proxy_uptime_data = {"first_connected": 0.0, "last_heartbeat": 0.0, "downtimes": []}
        logger.info("[Uptime] Proxy tracking initialized")

    def _track_proxy_state(self) -> None:
        """Track Bitfinex fetcher connection state transitions."""
        if not self._bitfinex_fetcher:
            return
        is_connected = self._bitfinex_fetcher._ws_connected
        now = time.time()

        if self._proxy_was_connected is None:
            # First check after startup
            if is_connected:
                if self._proxy_uptime_data.get("first_connected", 0.0) == 0.0:
                    self._proxy_uptime_data["first_connected"] = now
                    logger.info(
                        f"[Uptime] Zurich proxy first connected at "
                        f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now))} UTC"
                    )
                else:
                    logger.info(
                        f"[Uptime] Zurich proxy UP at "
                        f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now))} UTC"
                    )
                self._proxy_was_connected = True
            # If not connected, stay None — don't start tracking until first connection
            return

        if self._proxy_was_connected and not is_connected:
            # Connected → disconnected
            self._proxy_disconnect_start = now
            self._proxy_was_connected = False
            logger.warning(
                f"[Uptime] Zurich proxy DOWN at "
                f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now))} UTC"
            )

        elif not self._proxy_was_connected and is_connected:
            # Disconnected → connected
            duration = now - self._proxy_disconnect_start
            if duration >= self._PROXY_DOWNTIME_THRESHOLD:
                self._proxy_uptime_data.setdefault("downtimes", []).append({
                    "start": self._proxy_disconnect_start,
                    "end": now,
                    "duration": round(duration, 1),
                })
                # Keep last 50
                self._proxy_uptime_data["downtimes"] = self._proxy_uptime_data["downtimes"][-50:]
                logger.info(
                    f"[Uptime] Zurich proxy UP at "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now))} UTC "
                    f"(was down {duration:.0f}s since "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(self._proxy_disconnect_start))} UTC)"
                )
            else:
                logger.info(
                    f"[Uptime] Zurich proxy UP at "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now))} UTC "
                    f"(brief reconnection {duration:.0f}s, below threshold)"
                )
            self._proxy_was_connected = True

        # Periodic heartbeat save (~60s)
        if now - self._proxy_last_heartbeat_save >= 60:
            self._proxy_last_heartbeat_save = now
            self._proxy_uptime_data["last_heartbeat"] = now
            try:
                self._proxy_uptime_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._proxy_uptime_file, "w") as f:
                    json.dump(self._proxy_uptime_data, f)
            except OSError as e:
                logger.warning(f"[Uptime] Failed to save proxy heartbeat: {e}")

    def _get_proxy_uptime_info(self) -> dict:
        """Return proxy uptime info for dashboard broadcast."""
        is_connected = (
            self._bitfinex_fetcher._ws_connected if self._bitfinex_fetcher else False
        )
        now = time.time()
        first = self._proxy_uptime_data.get("first_connected", 0.0)
        downtimes = self._proxy_uptime_data.get("downtimes", [])
        total_down = sum(d["duration"] for d in downtimes)

        # Include ongoing downtime if currently disconnected
        if not is_connected and self._proxy_was_connected is not None and self._proxy_disconnect_start > 0:
            total_down += now - self._proxy_disconnect_start

        if first > 0:
            true_uptime = (now - first) - total_down
        else:
            true_uptime = 0

        return {
            "is_connected": is_connected,
            "first_connected": first,
            "true_uptime_seconds": round(max(0, true_uptime), 0),
            "total_downtime": round(total_down, 0),
            "outage_count": len(downtimes),
            "downtimes": downtimes[-20:],
        }

    # --- Log export from disk ---

    _LOG_LINE_RE = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] (.*)$"
    )

    def _read_bot_logs_from_disk(self, start_ts: float, end_ts: float) -> list[dict]:
        """Read bot log entries from disk log files within time range."""
        from datetime import datetime as _dt
        from datetime import timezone as _tz

        entries: list[dict] = []
        log_dir = Path("logs")

        # Collect rotated files (oldest first) + current log file
        rotated = sorted(log_dir.glob("coirnabot.log.*"))
        main = log_dir / "coirnabot.log"
        log_files = rotated + ([main] if main.exists() else [])

        for log_file in log_files:
            try:
                with open(log_file) as f:
                    for line in f:
                        m = self._LOG_LINE_RE.match(line.rstrip())
                        if not m:
                            continue
                        ts_str, level, msg = m.groups()
                        ts = _dt.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(
                            tzinfo=_tz.utc
                        ).timestamp()
                        if ts < start_ts:
                            continue
                        if ts > end_ts:
                            break  # entries are chronological within a file
                        component = ""
                        cm = DashboardLogHandler._COMPONENT_RE.match(msg)
                        if cm:
                            component = cm.group(1)
                            msg = cm.group(2)
                        entries.append({
                            "timestamp": ts,
                            "level": level,
                            "component": component,
                            "message": msg,
                        })
            except Exception:
                continue
        return entries

    def _read_auth_logs_from_disk(self, start_ts: float, end_ts: float) -> list[dict]:
        """Read auth log entries from JSONL files within time range."""
        entries: list[dict] = []
        auth_dir = Path("logs/auth")

        # Rotated files (oldest first) + main
        jsonl_files: list[Path] = []
        for i in range(self._AUTH_LOG_MAX_ROTATIONS, 0, -1):
            rotated = auth_dir / f"auth_events.jsonl.{i}"
            if rotated.exists():
                jsonl_files.append(rotated)
        main = auth_dir / "auth_events.jsonl"
        if main.exists():
            jsonl_files.append(main)

        for jf in jsonl_files:
            try:
                for line in jf.read_text().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    event = json.loads(line)
                    ts = event.get("timestamp", 0)
                    if start_ts <= ts <= end_ts:
                        pw = event.get("password", "")
                        if pw and not pw.endswith("*"):
                            event["password"] = DashboardServer._mask_password(pw)
                        entries.append(event)
            except Exception:
                continue
        return entries

    def _apply_settings(self, settings: dict) -> None:
        """Apply new settings: restart discovery with updated parameters."""
        old_settings = dict(self._settings)  # snapshot for change detection
        trade_amount_pct = float(settings.get("trade_amount_pct", 0.0))
        total_capital = settings.get("total_capital", 1800.0)
        if trade_amount_pct > 0:
            trade_amount = round(total_capital * trade_amount_pct, 2)
            logger.info(
                f"[Settings] Auto trade amount: ${trade_amount} "
                f"({trade_amount_pct * 100:.1f}% of ${total_capital})"
            )
        else:
            trade_amount = settings.get("trade_amount_usd", self._monitor._trade_amount)

        # Reset optimizer if present — triggers new discovery
        if self._optimizer:
            opt = self._optimizer
            opt._total_capital = total_capital
            # Update Phase 2-4 parameters directly (not in reset())
            if "max_active_symbols" in settings:
                opt._max_active_symbols = max(int(settings["max_active_symbols"]), int(settings.get("num_active_symbols", opt._min_active_symbols)))
            if "min_rebalance_score" in settings:
                opt._min_rebalance_score = float(settings["min_rebalance_score"])
            if "confirmation_period" in settings:
                opt._confirmation_period = int(settings["confirmation_period"])
            if "score_stability_seconds" in settings:
                opt._score_stability_seconds = int(settings["score_stability_seconds"])
            if "score_stability_factor" in settings:
                opt._score_stability_factor = float(settings["score_stability_factor"])
            if "promotion_threshold" in settings:
                opt._promotion_threshold = float(settings["promotion_threshold"])
            if "demotion_threshold" in settings:
                opt._demotion_threshold = float(settings["demotion_threshold"])
            if "demotion_period" in settings:
                opt._demotion_period = int(settings["demotion_period"])
            if "trading_score_threshold" in settings:
                opt._trading_threshold = float(settings["trading_score_threshold"])
            if "strong_score_threshold" in settings:
                opt._strong_threshold = float(settings["strong_score_threshold"])
            if "very_strong_score_threshold" in settings:
                opt._very_strong_threshold = float(settings["very_strong_score_threshold"])
            if "fee_threshold_multiplier" in settings:
                opt._fee_threshold_multiplier = float(settings["fee_threshold_multiplier"])
            if "discovery_duration" in settings:
                opt._discovery_duration = int(settings["discovery_duration"])
            opt.reset(
                trade_amount=trade_amount,
                num_active_symbols=settings.get("num_active_symbols"),
                scoring_window=settings.get("scoring_window"),
                evaluation_interval=settings.get("evaluation_interval"),
                safety_multiplier=settings.get("safety_multiplier"),
                auto_rotate=settings.get("auto_rotate"),
            )

        # Update monitor thresholds
        if "min_net_profit_pct" in settings:
            self._monitor._min_net_profit_pct = float(settings["min_net_profit_pct"])
        if "rebalance_roi_horizon" in settings:
            self._monitor._rebalance_roi_horizon = int(settings["rebalance_roi_horizon"])
        self._monitor._total_capital = total_capital

        # Net P&L gate params
        if "net_pnl_gate_warmup_trades" in settings:
            self._monitor._net_pnl_gate_warmup_trades = int(settings["net_pnl_gate_warmup_trades"])
        if "net_pnl_gate_grace_seconds" in settings:
            self._monitor._net_pnl_gate_grace_seconds = int(settings["net_pnl_gate_grace_seconds"])
        if "rebalance_roi_divisor" in settings:
            self._monitor._rebalance_roi_divisor = int(settings["rebalance_roi_divisor"])
        if "net_pct_sizing_enabled" in settings:
            self._monitor._net_pct_sizing_enabled = settings["net_pct_sizing_enabled"]
        if "net_pct_multiplier_cap" in settings:
            self._monitor._net_pct_multiplier_cap = float(settings["net_pct_multiplier_cap"])

        # Adaptive mode
        if "adaptive_mode" in settings:
            self._monitor._adaptive_mode = settings["adaptive_mode"]
            self._balance._adaptive_mode = settings["adaptive_mode"]

        # Update balance cooldown and trade amount
        if "rebalance_cooldown" in settings:
            self._balance._rebalance_cooldown = int(settings["rebalance_cooldown"])
        if "min_misses_before_rebalance" in settings:
            self._monitor._min_misses_before_rebalance = int(settings["min_misses_before_rebalance"])
        self._balance._trade_amount = trade_amount
        self._balance._max_rebalance = trade_amount * 4

        # Profitability controls
        if "reallocation_cost_horizon" in settings:
            self._optimizer._reallocation_cost_horizon = float(settings["reallocation_cost_horizon"])
        if "demotion_cooldown_multiplier" in settings:
            self._optimizer._demotion_cooldown_multiplier = float(settings["demotion_cooldown_multiplier"])
            self._optimizer._demotion_cooldown = self._optimizer._demotion_period * self._optimizer._demotion_cooldown_multiplier
        if "hourly_external_transfer_cap" in settings:
            self._balance._hourly_external_transfer_cap = float(settings["hourly_external_transfer_cap"])
        if "bitfinex_reserve_pct" in settings:
            self._balance._bitfinex_reserve_pct = float(settings["bitfinex_reserve_pct"])
            self._balance._bitfinex_reserve_target = (
                self._balance._initial_investment * self._balance._bitfinex_reserve_pct
            )
        if "bitfinex_reserve_hard_floor" in settings:
            self._balance._bitfinex_reserve_hard_floor = float(settings["bitfinex_reserve_hard_floor"])
            self._balance._bitfinex_reserve_hard_floor_amount = (
                self._balance._initial_investment * self._balance._bitfinex_reserve_hard_floor
            )

        # Simulation realism features
        if "spread_persistence_ticks" in settings:
            self._monitor._spread_persistence_ticks = int(settings["spread_persistence_ticks"])
        if "event_driven_seller_penalty_pct" in settings:
            self._monitor._event_driven_seller_penalty = float(settings["event_driven_seller_penalty_pct"])
        if "one_leg_failure_rate" in settings:
            self._monitor._one_leg_failure_rate = float(settings["one_leg_failure_rate"])
        if "one_leg_unwind_slippage_mult" in settings:
            self._monitor._one_leg_unwind_slippage_mult = float(settings["one_leg_unwind_slippage_mult"])
        if "max_position_multiplier" in settings:
            self._monitor._max_position_multiplier = float(settings["max_position_multiplier"])

        # Anomaly protection
        anomaly = self._monitor._anomaly
        if "anomaly_protection_enabled" in settings:
            anomaly._enabled = settings["anomaly_protection_enabled"]
        if "circuit_breaker_window" in settings:
            anomaly._cb_window = int(settings["circuit_breaker_window"])
        if "circuit_breaker_threshold" in settings:
            anomaly._cb_threshold = float(settings["circuit_breaker_threshold"])
        if "circuit_breaker_resume_pct" in settings:
            anomaly._cb_resume_pct = float(settings["circuit_breaker_resume_pct"])
        if "circuit_breaker_cooldown" in settings:
            anomaly._cb_cooldown = int(settings["circuit_breaker_cooldown"])
        if "drawdown_threshold_pct" in settings:
            anomaly._dd_threshold_pct = float(settings["drawdown_threshold_pct"])
        if "drawdown_resume_pct" in settings:
            anomaly._dd_resume_pct = float(settings["drawdown_resume_pct"])
        if "drawdown_emergency_mult" in settings:
            anomaly._dd_emergency_mult = float(settings["drawdown_emergency_mult"])
        if "symbol_loss_streak_threshold" in settings:
            anomaly._sls_threshold = int(settings["symbol_loss_streak_threshold"])
        if "symbol_loss_streak_cooldown" in settings:
            anomaly._sls_cooldown = int(settings["symbol_loss_streak_cooldown"])
        if "warning_pnl_pct" in settings:
            anomaly._warning_pnl_pct = float(settings["warning_pnl_pct"])

        # execution_mode: persisted to settings.json but requires restart
        # (no hot-apply — executor creation happens at startup)

        # Hot-apply fee settings if present
        if self._fee_manager:
            fee_configs = settings.get("fee_configs")
            if fee_configs:
                self._fee_manager.update_from_settings(fee_configs)
                self._apply_enabled_exchanges(fee_configs)
            fee_real_mode = settings.get("fee_real_mode")
            if fee_real_mode is not None:
                self._fee_manager.real_mode = bool(fee_real_mode)

        # Hot-apply transfer fee settings if present
        if self._transfer_fee_mgr:
            tc = settings.get("transfer_configs")
            if tc:
                self._transfer_fee_mgr.update_from_settings(tc)

        # Record config snapshot
        self._monitor.record_config_snapshot("settings_applied")

        # Enable distribute if switching to live mode
        old_mode = old_settings.get("execution_mode", "simulation")
        new_mode = settings.get("execution_mode", old_mode)
        if new_mode == "live" and old_mode != "live":
            self._distribute_enabled = True
            logger.info("[Settings] Execution mode changed to live — distribute from Bitfinex enabled")

        # Log comprehensive settings snapshot with diffs
        self._log_all_settings("settings_applied", old_settings=old_settings)

    def _sync_settings_on_startup(self, settings: dict) -> None:
        """Sync persisted settings to components at startup.

        Targeted subset of _apply_settings() — only syncs numeric/boolean
        values without triggering optimizer reset or discovery restart.
        Ensures settings.json values changed via dashboard in previous
        sessions are applied to BalanceTracker, Monitor, etc.
        """
        synced: list[str] = []
        # Balance settings
        if "hourly_external_transfer_cap" in settings:
            old_val = self._balance._hourly_external_transfer_cap
            new_val = float(settings["hourly_external_transfer_cap"])
            self._balance._hourly_external_transfer_cap = new_val
            if old_val != new_val:
                synced.append(f"hourly_cap: ${old_val:.2f} -> ${new_val:.2f}")
            # Verify the attribute was actually set
            actual = self._balance._hourly_external_transfer_cap
            if actual != new_val:
                logger.warning(
                    f"[Settings] SYNC FAILED: hourly_cap set to ${new_val:.2f} "
                    f"but reads back as ${actual:.2f}"
                )
        if "bitfinex_reserve_pct" in settings:
            old_val = self._balance._bitfinex_reserve_pct
            new_val = float(settings["bitfinex_reserve_pct"])
            self._balance._bitfinex_reserve_pct = new_val
            self._balance._bitfinex_reserve_target = (
                self._balance._initial_investment * new_val
            )
            if old_val != new_val:
                synced.append(f"bfx_reserve: {old_val*100:.1f}% -> {new_val*100:.1f}%")
        if "bitfinex_reserve_hard_floor" in settings:
            old_val = self._balance._bitfinex_reserve_hard_floor
            new_val = float(settings["bitfinex_reserve_hard_floor"])
            self._balance._bitfinex_reserve_hard_floor = new_val
            self._balance._bitfinex_reserve_hard_floor_amount = (
                self._balance._initial_investment * new_val
            )
            if old_val != new_val:
                synced.append(f"bfx_floor: {old_val*100:.1f}% -> {new_val*100:.1f}%")
        if "rebalance_cooldown" in settings:
            old_val = self._balance._rebalance_cooldown
            new_val = int(settings["rebalance_cooldown"])
            self._balance._rebalance_cooldown = new_val
            if old_val != new_val:
                synced.append(f"rebal_cooldown: {old_val}s -> {new_val}s")
        if "adaptive_mode" in settings:
            self._balance._adaptive_mode = settings["adaptive_mode"]

        # Monitor settings
        if "min_net_profit_pct" in settings:
            old_val = self._monitor._min_net_profit_pct
            new_val = float(settings["min_net_profit_pct"])
            self._monitor._min_net_profit_pct = new_val
            if old_val != new_val:
                synced.append(f"min_net_pct: {old_val:.4f} -> {new_val:.4f}")
        if "rebalance_roi_horizon" in settings:
            self._monitor._rebalance_roi_horizon = int(settings["rebalance_roi_horizon"])
        if "rebalance_roi_divisor" in settings:
            self._monitor._rebalance_roi_divisor = int(settings["rebalance_roi_divisor"])
        if "min_misses_before_rebalance" in settings:
            self._monitor._min_misses_before_rebalance = int(settings["min_misses_before_rebalance"])
        if "net_pnl_gate_warmup_trades" in settings:
            self._monitor._net_pnl_gate_warmup_trades = int(settings["net_pnl_gate_warmup_trades"])
        if "net_pnl_gate_grace_seconds" in settings:
            self._monitor._net_pnl_gate_grace_seconds = int(settings["net_pnl_gate_grace_seconds"])
        if "adaptive_mode" in settings:
            self._monitor._adaptive_mode = settings["adaptive_mode"]

        # Simulation realism
        if "spread_persistence_ticks" in settings:
            self._monitor._spread_persistence_ticks = int(settings["spread_persistence_ticks"])
        if "event_driven_seller_penalty_pct" in settings:
            self._monitor._event_driven_seller_penalty = float(settings["event_driven_seller_penalty_pct"])
        if "max_position_multiplier" in settings:
            self._monitor._max_position_multiplier = float(settings["max_position_multiplier"])

        # Optimizer settings (no reset — just sync values)
        if self._optimizer:
            if "reallocation_cost_horizon" in settings:
                self._optimizer._reallocation_cost_horizon = float(settings["reallocation_cost_horizon"])
            if "demotion_cooldown_multiplier" in settings:
                self._optimizer._demotion_cooldown_multiplier = float(settings["demotion_cooldown_multiplier"])
                self._optimizer._demotion_cooldown = self._optimizer._demotion_period * self._optimizer._demotion_cooldown_multiplier
            if "trading_score_threshold" in settings:
                self._optimizer._trading_threshold = float(settings["trading_score_threshold"])
            if "strong_score_threshold" in settings:
                self._optimizer._strong_threshold = float(settings["strong_score_threshold"])
            if "very_strong_score_threshold" in settings:
                self._optimizer._very_strong_threshold = float(settings["very_strong_score_threshold"])
            if "fee_threshold_multiplier" in settings:
                self._optimizer._fee_threshold_multiplier = float(settings["fee_threshold_multiplier"])

        # Anomaly protection
        anomaly = self._monitor._anomaly
        if "anomaly_protection_enabled" in settings:
            anomaly._enabled = settings["anomaly_protection_enabled"]
        if "circuit_breaker_threshold" in settings:
            anomaly._cb_threshold = float(settings["circuit_breaker_threshold"])
        if "drawdown_threshold_pct" in settings:
            anomaly._dd_threshold_pct = float(settings["drawdown_threshold_pct"])

        # Log sync results
        if synced:
            logger.info(f"[Settings] Startup sync: {', '.join(synced)}")
        else:
            logger.info("[Settings] Startup sync: all values match constructors")
        # Always log critical runtime values for debugging
        logger.info(
            f"[Settings] Verified: hourly_cap=${self._balance._hourly_external_transfer_cap:.2f}, "
            f"bfx_reserve={self._balance._bitfinex_reserve_pct*100:.1f}%, "
            f"rebal_cooldown={self._balance._rebalance_cooldown}s, "
            f"min_net_pct={self._monitor._min_net_profit_pct:.4f}"
        )

    def _apply_enabled_exchanges(self, fee_data: dict) -> None:
        """Hot-apply exchange enabled/disabled state to monitor/optimizer/balance.

        Handles both disabling (remove from active sets) and re-enabling
        (add back if a fetcher exists for that exchange).
        Respects demo_only mode — never re-enables exchanges outside the demo set.
        """
        enabled = {ex for ex, cfg in fee_data.items() if cfg.get("enabled", True)}
        disabled = {ex for ex in fee_data if ex not in enabled}

        # Get the set of exchanges that have fetchers (the full possible set)
        fetcher_exchanges = set()
        if self._monitor:
            fetcher_exchanges = {f.exchange_name for f in self._monitor._fetchers}

        # Only enable exchanges that actually have fetchers
        target_active = enabled & fetcher_exchanges

        # Respect demo_only mode — never expand beyond demo-capable exchanges
        execution_mode = self._settings.get("execution_mode", "simulation")
        if execution_mode == "demo_only":
            demo_set = {"Binance", "OKX", "Bybit"}
            target_active = target_active & demo_set

        # Update monitor active exchanges
        if self._monitor:
            self._monitor._active_exchanges = target_active.copy()

        # Update optimizer active exchanges
        if self._optimizer:
            self._optimizer._active_exchanges = target_active.copy()

        # Update balance exchanges (list, preserve order)
        if self._balance:
            self._balance._exchanges = [
                ex for ex in fetcher_exchanges if ex in target_active
            ]

        logger.info(
            f"[Settings] Exchange state updated — "
            f"active: {sorted(target_active)}"
            + (f", disabled: {sorted(disabled)}" if disabled else "")
        )

    def _hard_stop_all(self, transfer_to_bitfinex: bool) -> dict:
        """Convert all crypto positions to USDT. Operator action."""
        if not self._balance:
            return {"positions_sold": 0, "total_gross": 0, "total_fees": 0, "total_net": 0, "sells": []}

        prices = self._monitor._get_current_prices()
        bitfinex_available = "Bitfinex" in (self._balance._exchanges or [])
        sells: list[dict] = []
        total_gross = 0.0
        total_fees = 0.0

        for ex in list(self._balance._exchanges or []):
            for sym in list(self._balance.crypto.get(ex, {}).keys()):
                qty = self._balance.crypto[ex].get(sym, 0.0)
                if qty <= 0:
                    continue
                price = prices.get(sym, 0.0)
                if price <= 0:
                    continue

                # Determine sell path
                use_bitfinex = (
                    transfer_to_bitfinex
                    and bitfinex_available
                    and ex != "Bitfinex"
                    and prices.get(sym, 0) > 0  # symbol has price data
                )

                if use_bitfinex:
                    result = self._balance.force_sell_crypto_via_bitfinex(
                        ex, sym, qty, price,
                    )
                    gross = result["gross"]
                    fee = result["withdrawal_fee"]
                    net = result["net"]
                    sell_path = f"{ex}→Bitfinex (0% taker)"
                else:
                    # Sell locally
                    fee_rate = (
                        self._fee_manager.get_taker_fee(ex, sym)
                        if self._fee_manager else 0.001
                    )
                    gross = qty * price
                    fee = gross * fee_rate
                    net = gross - fee
                    self._balance.usdt[ex] += net
                    self._balance.crypto[ex][sym] = 0.0
                    sell_path = f"local ({ex})"

                total_gross += gross
                total_fees += fee
                sells.append({
                    "exchange": ex, "symbol": sym, "qty": round(qty, 8),
                    "price": round(price, 4), "gross": round(gross, 2),
                    "fee": round(fee, 4), "net": round(net, 2), "path": sell_path,
                })
                logger.warning(
                    f"[Monitor] HARD_STOP_SELL {sym} on {ex}: "
                    f"qty={qty:.6f} price=${price:.4f} gross=${gross:.2f} "
                    f"fee=${fee:.4f} net=${net:.2f} via {sell_path}"
                )

        total_net = total_gross - total_fees
        logger.warning(
            f"[Monitor] HARD_STOP_COMPLETE: {len(sells)} positions sold, "
            f"gross=${total_gross:.2f} fees=${total_fees:.4f} net=${total_net:.2f}"
        )
        return {
            "positions_sold": len(sells),
            "total_gross": round(total_gross, 2),
            "total_fees": round(total_fees, 4),
            "total_net": round(total_net, 2),
            "sells": sells,
        }

    def _distribute_from_bitfinex(self) -> dict:
        """Distribute USDT from Bitfinex to other exchanges. Operator action."""
        if not self._balance or "Bitfinex" not in (self._balance._exchanges or []):
            return {"available": 0, "transfers": [], "strategy": "none"}

        bitfinex_usdt = self._balance.usdt.get("Bitfinex", 0.0)
        reserve = getattr(self._balance, "_bitfinex_reserve_target", 0.0)
        available = max(0, bitfinex_usdt - reserve)
        if available < 10:
            return {"available": round(available, 2), "transfers": [], "strategy": "insufficient"}

        # Determine allocation strategy
        enabled_exchanges = (
            self._fee_manager.get_enabled_exchanges()
            if self._fee_manager else set(self._balance._exchanges or [])
        )
        targets = [ex for ex in enabled_exchanges if ex != "Bitfinex"]
        if not targets:
            return {"available": round(available, 2), "transfers": [], "strategy": "no_targets"}

        strategy = "even_split"
        allocations: dict[str, float] = {}

        # Try score-weighted allocation from optimizer
        if self._optimizer and self._optimizer._active_symbols:
            opt = self._optimizer
            total_weight = 0.0
            ex_weights: dict[str, float] = {}
            for sym in opt._active_symbols:
                score = opt._latest_scores.get(sym, 0.01)
                dom = opt._dominant_pairs.get(sym, {})
                buyers = dom.get("buyers", [])
                for buyer_info in buyers:
                    bex = buyer_info[0] if isinstance(buyer_info, (list, tuple)) else buyer_info
                    if bex in targets:
                        w = score * (buyer_info[1] if isinstance(buyer_info, (list, tuple)) and len(buyer_info) > 1 else 1.0)
                        ex_weights[bex] = ex_weights.get(bex, 0) + w
                        total_weight += w

            if total_weight > 0 and ex_weights:
                strategy = "score_weighted"
                for ex, w in ex_weights.items():
                    allocations[ex] = available * (w / total_weight)
                # Give remaining exchanges a minimum share
                remaining = [ex for ex in targets if ex not in allocations]
                if remaining and len(allocations) < len(targets):
                    min_share = available * 0.05  # 5% floor per exchange
                    total_min = min_share * len(remaining)
                    if total_min < available * 0.3:  # Don't exceed 30% for unallocated
                        scale = (available - total_min) / available
                        for ex in allocations:
                            allocations[ex] *= scale
                        for ex in remaining:
                            allocations[ex] = min_share

        # Fallback: even split
        if not allocations:
            per_exchange = available / len(targets)
            allocations = {ex: per_exchange for ex in targets}

        transfers: list[dict] = []
        for ex, amount in allocations.items():
            if amount < 1:
                continue
            self._balance.usdt["Bitfinex"] -= amount
            self._balance.usdt[ex] = self._balance.usdt.get(ex, 0.0) + amount
            transfers.append({"exchange": ex, "amount": round(amount, 2)})
            logger.info(
                f"[Monitor] DISTRIBUTE Bitfinex→{ex}: ${amount:.2f} (free)"
            )

        total_distributed = sum(t["amount"] for t in transfers)
        logger.info(
            f"[Monitor] DISTRIBUTE_COMPLETE: ${total_distributed:.2f} to "
            f"{len(transfers)} exchanges ({strategy})"
        )
        return {
            "available": round(available, 2),
            "distributed": round(total_distributed, 2),
            "transfers": transfers,
            "strategy": strategy,
        }

    def _log_all_settings(self, reason: str, old_settings: dict | None = None) -> None:
        """Log comprehensive settings snapshot. Called at session start and on change."""
        s = self._settings
        mon = self._monitor
        opt = self._optimizer
        bal = self._balance
        ano = mon._anomaly if mon else None

        # Trade amount
        trade_pct = float(s.get("trade_amount_pct", 0))
        capital = float(s.get("total_capital", 1800))
        if trade_pct > 0:
            ta_str = f"${round(capital * trade_pct, 2)} ({trade_pct * 100:.1f}% of ${capital:.0f})"
        else:
            ta_str = f"${s.get('trade_amount_usd', 10)} (fixed, capital=${capital:.0f})"

        # Exchange fees summary
        fee_parts = []
        fee_cfgs = s.get("fee_configs", {})
        disabled_exs = []
        for ex_name in sorted(fee_cfgs.keys()):
            cfg = fee_cfgs[ex_name]
            if not cfg.get("enabled", True):
                disabled_exs.append(ex_name)
                continue
            eff = cfg.get("base_taker_rate", 0.001)
            if cfg.get("token_discount_enabled"):
                eff *= (1 - cfg.get("token_discount_pct", 0))
            # Short exchange name
            short = {"Binance": "BIN", "OKX": "OKX", "Bybit": "BYB", "MEXC": "MEX",
                     "Bitget": "BGT", "KuCoin": "KUC", "Gate.io": "GAT",
                     "Pionex": "PIO", "Bitfinex": "BFX"}.get(ex_name, ex_name[:3])
            ref_comm = cfg.get("referrer_commission_pct", 0)
            ref_str = f"+ref{ref_comm * 100:.0f}%" if ref_comm > 0 else ""
            fee_parts.append(f"{short}={eff * 100:.3f}%{ref_str}")

        # Anomaly settings
        ano_enabled = s.get("anomaly_protection_enabled", True)
        cb_w = s.get("circuit_breaker_window", 900)
        cb_t = s.get("circuit_breaker_threshold", -5.0)
        cb_c = s.get("circuit_breaker_cooldown", 300)
        dd_t = s.get("drawdown_threshold_pct", 5.0)
        dd_e = s.get("drawdown_emergency_mult", 2.0)
        sls_t = s.get("symbol_loss_streak_threshold", 4)
        sls_c = s.get("symbol_loss_streak_cooldown", 300)

        # Bitfinex reserve
        bfx_pct = s.get("bitfinex_reserve_pct", 0.15)
        bfx_floor = s.get("bitfinex_reserve_hard_floor", 0.05)

        lines = [
            f"trade_amount={ta_str}",
            f"adaptive_mode={s.get('adaptive_mode', True)}, auto_rotate={s.get('auto_rotate', True)}",
            f"max_symbols={s.get('max_active_symbols', 8)}, min_symbols={s.get('num_active_symbols', 3)}, scoring_window={s.get('scoring_window', 60)}s, eval_interval={s.get('evaluation_interval', 60)}s",
            f"min_net_pct={s.get('min_net_profit_pct', 0.02):.2f}%, rebalance_cooldown={s.get('rebalance_cooldown', 30)}s, roi_horizon={s.get('rebalance_roi_horizon', 300)}s, roi_divisor={s.get('rebalance_roi_divisor', 5)}",
            f"net_pnl_gate: warmup={s.get('net_pnl_gate_warmup_trades', 10)} trades, grace={s.get('net_pnl_gate_grace_seconds', 1800)}s",
            f"net_pct_sizing={s.get('net_pct_sizing_enabled', True)}, cap={s.get('net_pct_multiplier_cap', 2.5)}",
            f"spread_persistence={s.get('spread_persistence_ticks', 1)} ticks, evd_penalty={s.get('event_driven_seller_penalty_pct', 0.05)}, one_leg_rate={s.get('one_leg_failure_rate', 0.02)}, max_pos_mult={s.get('max_position_multiplier', 5.0)}, fee_threshold_mult={s.get('fee_threshold_multiplier', 0.5)}",
            f"anomaly: enabled={ano_enabled}, cb_window={cb_w}s, cb_threshold=${cb_t:.2f}, cb_cooldown={cb_c}s",
            f"anomaly: dd_threshold={dd_t:.1f}%, dd_emergency={dd_e:.1f}x, streak_threshold={sls_t}, streak_cooldown={sls_c}s",
            f"bitfinex_reserve={bfx_pct * 100:.1f}% (${capital * bfx_pct:.0f}), hard_floor={bfx_floor * 100:.1f}% (${capital * bfx_floor:.0f})",
            f"hourly_transfer_cap=${s.get('hourly_external_transfer_cap', 2.0):.2f}",
            f"fee_real_mode={s.get('fee_real_mode', False)}",
            f"exchanges: {' '.join(fee_parts)}",
            f"disabled_exchanges: {', '.join(disabled_exs) if disabled_exs else 'none'}",
            f"execution_mode={s.get('execution_mode', 'simulation')}",
        ]

        # Change detection
        diffs: list[str] = []
        if old_settings:
            keys_to_check = [
                "trade_amount_usd", "trade_amount_pct", "total_capital",
                "adaptive_mode", "auto_rotate", "max_active_symbols",
                "num_active_symbols", "min_net_profit_pct", "rebalance_cooldown",
                "scoring_window", "evaluation_interval", "rebalance_roi_horizon",
                "rebalance_roi_divisor", "net_pnl_gate_warmup_trades",
                "net_pnl_gate_grace_seconds", "spread_persistence_ticks",
                "event_driven_seller_penalty_pct", "one_leg_failure_rate",
                "max_position_multiplier", "anomaly_protection_enabled",
                "circuit_breaker_window", "circuit_breaker_threshold",
                "circuit_breaker_cooldown", "drawdown_threshold_pct",
                "drawdown_emergency_mult", "symbol_loss_streak_threshold",
                "symbol_loss_streak_cooldown", "bitfinex_reserve_pct",
                "hourly_external_transfer_cap", "execution_mode",
                "net_pct_sizing_enabled", "net_pct_multiplier_cap",
                "fee_threshold_multiplier",
            ]
            for k in keys_to_check:
                old_v = old_settings.get(k)
                new_v = s.get(k)
                if old_v != new_v and old_v is not None:
                    diffs.append(f"{k} {old_v}→{new_v}")

        tag = reason.upper()
        logger.info(f"[Settings] {tag}")
        for line in lines:
            logger.info(f"[Settings]   | {line}")
        if diffs:
            logger.info(f"[Settings]   | CHANGES: {', '.join(diffs)}")

    def _build_optimizer_state(self) -> dict[str, Any]:
        """Collect optimizer state for dashboard broadcast."""
        if not self._optimizer:
            return {}
        opt = self._optimizer
        is_discovering = opt._discovery_mode and not opt._discovery_complete
        now = time.time()
        exchange_rankings = opt.get_exchange_rankings()
        return {
            "rankings": opt.get_rankings(),
            "exchange_rankings": exchange_rankings.get("exchanges", []),
            "pair_rankings": exchange_rankings.get("pairs", []),
            "rotations": opt.get_rotations(),
            "historical_rankings": opt.get_historical_rankings(),
            "historical_exchange_rankings": opt.get_historical_exchange_rankings(),
            "watchlist": opt.get_watchlist(),
            "auto_rotate": opt._auto_rotate,
            "active_symbols": opt.active_symbols,
            "min_active_symbols": opt._min_active_symbols,
            "max_active_symbols": opt._max_active_symbols,
            "scoring_window": opt._scoring_window,
            "evaluation_interval": opt._evaluation_interval,
            "tick_count": opt._tick_count,
            "warmup_remaining": max(
                0, opt._min_warmup_ticks - opt._tick_count
            ),
            "discovery_mode": is_discovering,
            "discovery_remaining": max(
                0,
                opt._discovery_duration - (now - opt._discovery_start),
            )
            if is_discovering
            else 0,
            "session_start": opt._session_start,
        }

    def _build_state(self) -> dict[str, Any]:
        """Collect all system state into a JSON-serializable dict."""
        now = time.time()
        active_exchanges = self._balance._exchanges
        active_symbols = self._balance._symbols
        # Also fetch prices for any residual crypto from demoted symbols
        all_held_symbols = set(active_symbols)
        for ex in active_exchanges:
            for sym, qty in self._balance.crypto[ex].items():
                if qty > 0:
                    all_held_symbols.add(sym)
        prices = self._get_prices(active_exchanges, list(all_held_symbols))

        # Connection status
        active_set = set(active_exchanges)
        connected = sum(
            1
            for f in self._fetchers
            if f._ws_connected and f.exchange_name in active_set
        )

        # Portfolio
        initial = self._balance._initial_investment
        portfolio_value = self._balance.get_portfolio_value(prices) if self._balance.initialized else initial
        trading_pnl = sum(t.profit_usd for t in self._monitor._trades)
        transfer_fees = self._balance.total_transfer_fees

        # Anomaly protection: update drawdown tracking with portfolio context
        self._monitor._anomaly.update_portfolio_value(portfolio_value, context={
            "portfolio_value": portfolio_value,
            "active_symbols": len(active_symbols),
            "connected_exchanges": connected,
            "total_exchanges": len(active_exchanges),
        })

        # Net profit awareness: update optimizer to gate rotations when in deficit
        credited_cashback = (
            self._fee_manager._total_credited_cashback if self._fee_manager else 0.0
        )
        net_profit = trading_pnl - transfer_fees + credited_cashback
        elapsed_hours = max((now - self._start_time) / 3600, 1 / 3600)
        session_hourly_rate = net_profit / elapsed_hours
        # For optimizer gating: use external-only fees (internal rebalances are cheap)
        external_fees = self._balance.total_external_transfer_fees
        net_profit_gating = trading_pnl - external_fees + credited_cashback
        elapsed_s = now - self._start_time if self._start_time else 0
        grace_seconds = getattr(self._monitor, "_net_pnl_gate_grace_seconds", 1800)
        grace_active = elapsed_s < grace_seconds
        if self._optimizer:
            self._optimizer.update_profit_state(net_profit_gating, session_hourly_rate, grace_active)

        # Balances per exchange (include ALL held crypto, not just active symbols)
        balances: dict[str, Any] = {}
        for ex in active_exchanges:
            usdt = self._balance.usdt[ex]
            crypto_data: dict[str, Any] = {}
            ex_total = usdt
            # Active symbols
            for sym in active_symbols:
                qty = self._balance.crypto[ex].get(sym, 0.0)
                p = prices.get(sym, 0.0)
                val = qty * p
                ex_total += val
                crypto_data[sym] = {"qty": round(qty, 6), "value": round(val, 2), "price": round(p, 6)}
            # Residual crypto from demoted symbols
            for sym, qty in self._balance.crypto[ex].items():
                if qty > 0 and sym not in crypto_data:
                    p = prices.get(sym, 0.0)
                    val = qty * p
                    ex_total += val
                    crypto_data[sym] = {"qty": round(qty, 6), "value": round(val, 2), "price": round(p, 6)}
            balances[ex] = {
                "usdt": round(usdt, 2),
                "crypto": crypto_data,
                "total": round(ex_total, 2),
            }

        # Prices per symbol per exchange
        price_grid: dict[str, dict[str, Any]] = {}
        for sym in active_symbols:
            price_grid[sym] = {}
            for fetcher in self._fetchers:
                if fetcher.exchange_name not in active_set:
                    continue
                state = fetcher.get_state()
                ps = state.get(sym)
                if ps and ps.bid and ps.ask:
                    try:
                        age = now - ps.received_at if ps.received_at > 0 else 999.0
                        price_grid[sym][fetcher.exchange_name] = {
                            "bid": round(float(ps.bid), 6),
                            "ask": round(float(ps.ask), 6),
                            "age": round(age, 1),
                        }
                    except (ValueError, TypeError):
                        pass

        # Simulation stats
        total_trades = len(self._monitor._trades)
        elapsed = now - self._monitor._start_time if self._monitor._start_time else 0
        trades_per_min = total_trades / (elapsed / 60) if elapsed > 60 else 0.0

        # Recent trades (last 100, newest first)
        recent_trades = []
        for t in reversed(self._monitor._trades[-100:]):
            trade_dict: dict = {
                "timestamp": t.timestamp,
                "symbol": t.symbol,
                "buy_exchange": t.buy_exchange,
                "sell_exchange": t.sell_exchange,
                "buy_price": round(t.buy_price, 6),
                "sell_price": round(t.sell_price, 6),
                "spread_pct": round(t.spread_pct, 4),
                "fee_pct": round(t.fee_pct, 4),
                "net_pct": round(t.net_pct, 4),
                "profit_usd": round(t.profit_usd, 6),
                "trade_amount": round(t.trade_amount, 2),
                "sim_slippage_pct": round(t.sim_slippage_pct, 4),
            }
            # Include demo fields when present (Phase 2)
            if t.demo_status:
                trade_dict.update({
                    "demo_buy_price": round(t.demo_buy_price, 6),
                    "demo_sell_price": round(t.demo_sell_price, 6),
                    "demo_buy_qty": round(t.demo_buy_qty, 8),
                    "demo_sell_qty": round(t.demo_sell_qty, 8),
                    "demo_profit_usd": round(t.demo_profit_usd, 6),
                    "demo_latency_ms": round(t.demo_latency_ms, 1),
                    "demo_slippage_pct": round(t.demo_slippage_pct, 4),
                    "demo_status": t.demo_status,
                })
            recent_trades.append(trade_dict)

        # Recent transfers (last 50, newest first)
        recent_transfers = []
        for tr in reversed(self._balance.transfers[-50:]):
            recent_transfers.append({
                "timestamp": tr.timestamp,
                "type": tr.transfer_type,
                "from_exchange": tr.from_exchange,
                "to_exchange": tr.to_exchange,
                "symbol": tr.symbol,
                "amount_usd": round(tr.amount_usd, 2),
                "fee_usd": round(tr.fee_usd, 4),
            })

        price_pnl = portfolio_value - initial - trading_pnl + transfer_fees if self._balance.initialized else 0.0

        # Adaptive trade size stats
        recent_trades_list = self._monitor._trades[-100:] if self._monitor._trades else []
        trade_sizes = [t.trade_amount for t in recent_trades_list if t.trade_amount > 0]
        avg_trade_size = sum(trade_sizes) / len(trade_sizes) if trade_sizes else self._monitor._trade_amount
        min_trade_size = min(trade_sizes) if trade_sizes else 0
        max_trade_size = max(trade_sizes) if trade_sizes else 0

        uptime_info = self._get_uptime_info()

        return {
            "timestamp": now,
            "uptime_seconds": uptime_info["true_uptime_seconds"],
            "uptime_info": uptime_info,
            "proxy_uptime_info": self._get_proxy_uptime_info(),
            "connected_exchanges": connected,
            "total_exchanges": len(active_exchanges),
            "portfolio": {
                "total_value": round(portfolio_value, 2),
                "initial_investment": round(initial, 2),
                "net_pnl": round(portfolio_value - initial, 2) if self._balance.initialized else 0.0,
                "trading_pnl": round(trading_pnl, 4),
                "transfer_fees": round(transfer_fees, 4),
                "price_pnl": round(price_pnl, 2) if self._balance.initialized else 0.0,
            },
            "balances": balances,
            "prices": price_grid,
            "simulation": {
                "total_trades": total_trades,
                "skipped_trades": self._balance.skipped_trades,
                "total_transfers": len(self._balance.transfers),
                "trades_per_minute": round(trades_per_min, 1),
                "low_profit_skips": self._monitor._low_profit_skips,
                "avg_trade_size": round(avg_trade_size, 2),
                "min_trade_size": round(min_trade_size, 2),
                "max_trade_size": round(max_trade_size, 2),
                "configured_trade_amount": self._monitor._trade_amount,
            },
            "recent_trades": recent_trades,
            "recent_transfers": recent_transfers,
            "all_trades": [
                {
                    "timestamp": t.timestamp,
                    "symbol": t.symbol,
                    "buy_exchange": t.buy_exchange,
                    "sell_exchange": t.sell_exchange,
                    "buy_price": round(t.buy_price, 6),
                    "sell_price": round(t.sell_price, 6),
                    "spread_pct": round(t.spread_pct, 4),
                    "fee_pct": round(t.fee_pct, 4),
                    "net_pct": round(t.net_pct, 4),
                    "profit_usd": round(t.profit_usd, 6),
                    "trade_amount": round(t.trade_amount, 2),
                    "sim_slippage_pct": round(t.sim_slippage_pct, 4),
                    **({"demo_buy_price": round(t.demo_buy_price, 6),
                        "demo_sell_price": round(t.demo_sell_price, 6),
                        "demo_profit_usd": round(t.demo_profit_usd, 6),
                        "demo_slippage_pct": round(t.demo_slippage_pct, 4),
                        "demo_latency_ms": round(t.demo_latency_ms, 1),
                        "demo_status": t.demo_status,
                    } if t.demo_status else {}),
                }
                for t in self._monitor._trades
            ],
            "all_transfers": [
                {
                    "timestamp": tr.timestamp,
                    "type": tr.transfer_type,
                    "from_exchange": tr.from_exchange,
                    "to_exchange": tr.to_exchange,
                    "symbol": tr.symbol,
                    "amount_usd": round(tr.amount_usd, 2),
                    "fee_usd": round(tr.fee_usd, 4),
                }
                for tr in self._balance.transfers
            ],
            "hourly_pnl": self._build_hourly_pnl(),
            "daily_pnl": self._build_daily_pnl(),
            "settings": self._settings,
            "execution_mode": self._monitor._execution_mode,
            "manual_stopped": self._monitor._manual_stopped,
            "manual_stop_timestamp": self._monitor._manual_stop_timestamp,
            "distribute_enabled": self._distribute_enabled,
            **(self._monitor._anomaly.to_broadcast_dict()),
            "all_exchanges": ALL_EXCHANGES,
            "all_symbols": SYMBOLS,
            "optimizer": self._build_optimizer_state(),
            "adaptive_config": self._build_adaptive_config(),
            "all_config_history": [
                {
                    "timestamp": c.timestamp,
                    "reason": c.reason,
                    "trade_amount": c.trade_amount,
                    "adaptive_mode": c.adaptive_mode,
                    "min_net_profit_pct": c.min_net_profit_pct,
                    "rebalance_cooldown": c.rebalance_cooldown,
                    "min_misses_before_rebalance": c.min_misses_before_rebalance,
                    "rebalance_roi_horizon": c.rebalance_roi_horizon,
                    "total_capital": c.total_capital,
                    "num_active_symbols": c.num_active_symbols,
                    "max_active_symbols": c.max_active_symbols,
                    "avg_trade_size": round(c.avg_trade_size, 2),
                    "estimated_profit_per_trade": round(c.estimated_profit_per_trade, 6),
                }
                for c in self._monitor._config_history
            ],
            "profit_stats": self._monitor.get_net_profit_stats(),
            "auth_logs": self._auth_events,
            "bot_logs": self._log_handler.get_recent() if self._log_handler else [],
            "bot_logs_total": self._log_handler.total_count() if self._log_handler else 0,
            "demo_comparison": self._build_demo_state() if self._demo_fetcher and self._demo_fetcher.enabled else None,
            **(self._fee_manager.to_broadcast_dict() if self._fee_manager else {}),
            **(self._transfer_fee_mgr.to_broadcast_dict() if self._transfer_fee_mgr else {}),
        }

    def _build_hourly_pnl(self) -> list[dict[str, Any]]:
        """Build hourly P&L data for dashboard charts (last 48 hours)."""
        from datetime import datetime, timedelta, timezone

        hourly = self._monitor._hourly_pnl
        # Compute transfer fees per hour from transfers
        hourly_fees: dict[str, float] = {}
        for tr in self._balance.transfers:
            if tr.fee_usd > 0:
                dt = datetime.fromtimestamp(tr.timestamp, tz=timezone.utc)
                key = dt.strftime("%Y-%m-%d_%H")
                hourly_fees[key] = hourly_fees.get(key, 0.0) + tr.fee_usd

        now = datetime.now(timezone.utc)
        result = []
        for i in range(48):
            dt = now - timedelta(hours=47 - i)
            key = dt.strftime("%Y-%m-%d_%H")
            bucket = hourly.get(key, {})
            pnl = bucket.get("pnl", 0.0)
            trades = bucket.get("trades", 0)
            fees = hourly_fees.get(key, 0.0)
            if pnl != 0 or trades > 0 or fees > 0:
                result.append({
                    "hour": key,
                    "pnl": round(pnl, 6),
                    "fees": round(fees, 6),
                    "net": round(pnl - fees, 6),
                    "trades": trades,
                })
        return result

    def _build_daily_pnl(self) -> list[dict[str, Any]]:
        """Build daily P&L data for dashboard charts (last 7 days)."""
        from datetime import datetime, timedelta, timezone

        daily = self._monitor._daily_pnl
        # Compute transfer fees per day from transfers
        daily_fees: dict[str, float] = {}
        for tr in self._balance.transfers:
            if tr.fee_usd > 0:
                dt = datetime.fromtimestamp(tr.timestamp, tz=timezone.utc)
                key = dt.strftime("%Y-%m-%d")
                daily_fees[key] = daily_fees.get(key, 0.0) + tr.fee_usd

        now = datetime.now(timezone.utc)
        result = []
        for i in range(7):
            dt = now - timedelta(days=6 - i)
            key = dt.strftime("%Y-%m-%d")
            bucket = daily.get(key, {})
            pnl = bucket.get("pnl", 0.0)
            trades = bucket.get("trades", 0)
            fees = daily_fees.get(key, 0.0)
            result.append({
                "date": key,
                "pnl": round(pnl, 6),
                "fees": round(fees, 6),
                "net": round(pnl - fees, 6),
                "trades": trades,
            })
        return result

    def _build_demo_state(self) -> dict[str, Any]:
        """Build demo comparison state for dashboard broadcast."""
        df = self._demo_fetcher
        if not df:
            return {}

        # Only include symbols the sim actually holds (qty > 0).
        # Active symbols with 0 holdings have pre-loaded testnet crypto, not ours.
        sim_held = set()
        for ex in self._balance._exchanges:
            for sym, qty in self._balance.crypto[ex].items():
                if qty > 0:
                    sim_held.add(sym)
        prices = self._get_prices(self._balance._exchanges, list(sim_held))

        comparisons: dict[str, Any] = {}
        for ex_name, demo_bal in df.latest_balances.items():
            # Simulation side
            sim_usdt = self._balance.usdt.get(ex_name, 0.0)
            sim_crypto: dict[str, Any] = {}
            sim_total = sim_usdt
            for sym, qty in self._balance.crypto.get(ex_name, {}).items():
                if qty > 0:
                    p = prices.get(sym, 0.0)
                    val = qty * p
                    sim_total += val
                    sim_crypto[sym] = {"qty": round(qty, 6), "value": round(val, 2)}

            # Demo side — use baseline-adjusted values so pre-funded
            # testnet amounts are subtracted. adjusted = sim + (demo - baseline).
            # When no trades: adjusted = sim (delta=0). Phase 2: shows real diffs.
            baseline = df.baselines.get(ex_name)
            baseline_usdt = baseline.usdt if baseline else demo_bal.usdt
            demo_usdt_delta = demo_bal.usdt - baseline_usdt
            adjusted_demo_usdt = sim_usdt + demo_usdt_delta

            demo_crypto: dict[str, Any] = {}
            demo_total = adjusted_demo_usdt
            for sym, qty in demo_bal.crypto.items():
                if qty > 0 and sym in sim_held:
                    baseline_qty = baseline.crypto.get(sym, 0.0) if baseline else 0.0
                    qty_delta = qty - baseline_qty
                    p = prices.get(sym, 0.0)
                    # Show sim_qty + delta as the adjusted demo qty
                    sim_qty = self._balance.crypto.get(ex_name, {}).get(sym, 0.0)
                    adjusted_qty = sim_qty + qty_delta
                    val = adjusted_qty * p
                    demo_total += val
                    demo_crypto[sym] = {"qty": round(adjusted_qty, 6), "value": round(val, 2)}

            diff_usdt = sim_usdt - adjusted_demo_usdt
            diff_total = sim_total - demo_total
            diff_total_pct = diff_total / max(abs(demo_total), 1) * 100

            comparisons[ex_name] = {
                "sim": {
                    "usdt": round(sim_usdt, 2),
                    "crypto": sim_crypto,
                    "total": round(sim_total, 2),
                },
                "demo": {
                    "usdt": round(adjusted_demo_usdt, 2),
                    "crypto": demo_crypto,
                    "total": round(demo_total, 2),
                    "error": demo_bal.error,
                    "fetched_at": demo_bal.fetched_at,
                },
                "diff_usdt": round(diff_usdt, 2),
                "diff_total": round(diff_total, 2),
                "diff_total_pct": round(diff_total_pct, 2),
            }

        # Demo portfolio total = sim portfolio total + sum(baseline deltas).
        # Baseline deltas measure the net USD change from actual demo trades
        # (current demo balance - first-fetch baseline, at current prices).
        # When no demo trades have executed, deltas are ~0 and demo ≈ sim.
        # When Phase 2 starts, deltas capture real P&L vs simulated P&L.
        all_prices = self._get_prices(self._balance._exchanges, list(set(self._balance._symbols) | sim_held))
        if self._balance.initialized:
            sim_total = self._balance.get_portfolio_value(all_prices)
        else:
            sim_total = self._balance._initial_investment
        total_delta = df.get_total_delta(all_prices)
        demo_portfolio_total = sim_total + total_delta

        return {
            "enabled": True,
            "exchanges": comparisons,
            "demo_portfolio_total": round(demo_portfolio_total, 2),
            "recent_discrepancies": [
                {
                    "timestamp": d.timestamp,
                    "exchange": d.exchange,
                    "type": d.discrepancy_type,
                    "symbol": d.symbol,
                    "sim_value": round(d.sim_value, 4),
                    "demo_value": round(d.demo_value, 4),
                    "diff_abs": round(d.diff_abs, 4),
                    "diff_pct": round(d.diff_pct, 2),
                    "root_cause": d.root_cause,
                }
                for d in df.recent_discrepancies[-50:]
            ],
            "total_discrepancies": df.total_discrepancy_count,
            "last_fetch_time": df.last_fetch_time,
            "configured_exchanges": [ex for ex, ok in df._configured.items() if ok],
        }

    def _build_adaptive_config(self) -> dict[str, Any]:
        """Current adaptive configuration decisions."""
        monitor = self._monitor
        balance = self._balance

        # Per-exchange transfer worthiness
        exchange_transfer_status: dict[str, Any] = {}
        for ex in balance._exchanges:
            fee = self._transfer_fee_mgr.get_withdrawal_fee(ex) if self._transfer_fee_mgr else 1.0
            est_profit = balance._estimated_profit_per_trade
            trades_to_recoup = fee / est_profit if est_profit > 0 else 999
            exchange_transfer_status[ex] = {
                "withdrawal_fee": fee,
                "trades_to_recoup": round(trades_to_recoup, 1),
                "transfer_allowed": trades_to_recoup <= 50,
            }

        recent = monitor._trades[-100:] if monitor._trades else []
        sizes = [t.trade_amount for t in recent if t.trade_amount > 0]

        return {
            "adaptive_mode": monitor._adaptive_mode,
            "configured_trade_amount": monitor._trade_amount,
            "avg_trade_size": round(sum(sizes) / len(sizes), 2) if sizes else 0,
            "min_trade_size": round(min(sizes), 2) if sizes else 0,
            "max_trade_size": round(max(sizes), 2) if sizes else 0,
            "min_net_profit_pct": monitor._min_net_profit_pct,
            "estimated_profit_per_trade": round(balance._estimated_profit_per_trade, 6),
            "total_capital": monitor._total_capital,
            "exchange_transfer_status": exchange_transfer_status,
        }

    def _get_prices(
        self, exchanges: list[str], symbols: list[str]
    ) -> dict[str, float]:
        """Get current mid prices for active symbols."""
        prices: dict[str, float] = {}
        active = set(exchanges)
        for sym in symbols:
            for fetcher in self._fetchers:
                if fetcher.exchange_name not in active:
                    continue
                state = fetcher.get_state()
                ps = state.get(sym)
                if ps and ps.bid and ps.ask:
                    try:
                        mid = (float(ps.bid) + float(ps.ask)) / 2.0
                        if mid > 0:
                            prices[sym] = mid
                            break
                    except (ValueError, TypeError):
                        continue
        return prices
