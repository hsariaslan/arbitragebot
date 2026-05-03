"""
WebSocket server for the ArbitrageBot live dashboard.

Pushes a full state snapshot (balances, trades, transfers, prices, system status)
to all connected browser clients every second via WebSocket on port 8765.

Also handles incoming messages from the dashboard for settings updates.
"""

import asyncio
import base64
import gzip
import json
import logging
import os
import re
import secrets
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime as _dt
from datetime import timezone as _tz
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
from settings import save_settings, save_registry

if TYPE_CHECKING:
    from balance import BalanceTracker
    from fee_manager import FeeManager
    from fetchers.base import BaseFetcher
    from funding_monitor import FundingMonitor
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
    """Captures recent log entries in memory for dashboard broadcast and export.

    v0.31.0-beta: also captures `config_group_id` / `config_id` from the
    LogRecord (stamped by `ConfigPrefixFilter` in `log_context.py`) so the
    frontend Bot Logs cascading dropdowns can filter by group → config.
    Records without context (shared subsystems) get `None` IDs and are
    surfaced in the "Universal" bucket.
    """

    _COMPONENT_RE = re.compile(r"^\[([\w.]+)\]\s*(.*)$", re.DOTALL)
    # Matches the multi-config prefix the filter prepends to record.msg
    _CONFIG_PREFIX_RE = re.compile(r"^\[[^\]]+\]\[[^\]]+\]\s*", re.DOTALL)

    def __init__(self, maxlen: int = 2000):
        super().__init__()
        self._entries: deque[dict] = deque(maxlen=maxlen)
        # Bounded deque(maxlen=50000) — pre-fix this was an UNBOUNDED list
        # appended on every log emit. Even though it's only READ on one
        # specific WS message (`request_all_bot_logs` for the filtered
        # log view), the unbounded list inflated Python's gen2 GC scan
        # time every collection cycle. With 30K log lines per 15 min
        # and a 30+ min session this list held 60K+ dicts that the GC
        # had to traverse. Cross-day exports go through
        # `_read_bot_logs_from_disk` so they don't depend on this. 50K
        # is plenty for the in-memory filtered view (~20-25 min at our
        # current emit rate).
        self._all_entries: deque[dict] = deque(maxlen=50000)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            # Strip the [GROUP_x][CONFIG_y] prefix added by ConfigPrefixFilter
            # so the dashboard can render component + message cleanly. The
            # filter already stashed group/config IDs as record attrs.
            group_id = getattr(record, "config_group_id", None)
            config_id = getattr(record, "config_id", None)
            group_name = getattr(record, "config_group_name", None)
            config_name = getattr(record, "config_name", None)
            if group_id and config_id:
                msg = self._CONFIG_PREFIX_RE.sub("", msg, count=1)
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
                "config_group_id": group_id,
                "config_id": config_id,
                "config_group_name": group_name,
                "config_name": config_name,
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
        funding_monitor: "FundingMonitor | None" = None,
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
        self._funding_monitor = funding_monitor
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

        # Auto trade-amount rescale (when trade_amount_pct > 0). Hourly tick
        # plus immediate trigger on discovery state transitions, so the bot
        # trades larger as capital compounds rather than staying pegged to
        # the configured `total_capital` constant. See _rescale_trade_amount().
        self._trade_amount_rescale_interval: float = 3600.0  # 1 hour
        self._last_trade_amount_rescale_ts: float = 0.0
        self._last_discovery_state: bool | None = None  # None = not yet observed

        # Daily auto-disable thinly-traded (exchange, symbol) combos. Runs once
        # per UTC day at 00:01 UTC (or on first eligible cycle after restart if
        # the scheduled time was missed during downtime). State persisted to
        # disk so multi-restart days don't double-run, and so a bot that was
        # offline at 00:01 UTC catches up on next start. See
        # `_maybe_run_auto_disable_volumes()`.
        self._auto_disable_target_hour_utc: int = 0   # 00:01 UTC
        self._auto_disable_target_minute_utc: int = 1
        self._auto_disable_state_file = Path("state/auto_disable_volumes.json")
        self._last_auto_disable_run_date_utc: str = ""  # "YYYY-MM-DD"
        self._last_auto_disable_run_ts: float = 0.0
        # Force-run flag: cleared after the first successful run on each
        # bot startup. The daily-cap check ("already ran today") is
        # bypassed on this first call so a mid-day restart immediately
        # refreshes the blocklist instead of running yesterday's lists
        # until tomorrow's 00:01 UTC trigger. Operator request: "When
        # the bot is restarted, it must run the auto fetcher&updater."
        self._auto_disable_force_run_on_start: bool = True
        # Track manual volume fetches server-side too, so the Fee Management
        # tab's "last manual fetch" indicator survives component remounts
        # (sub-tab navigation, WS reconnect, browser refresh). Stored in the
        # same state file so it survives bot restart.
        self._last_manual_volumes_fetch_ts: float = 0.0
        # Cached volumes from the last fetch — broadcast in state so the
        # Fee Management tab keeps showing them after a page refresh.
        self._cached_volumes: dict[str, dict[str, float]] = {}
        self._load_auto_disable_state()
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
        auth_log = logging.getLogger("arbitragebot.auth")
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
                # Multi-config: dump every config's full settings (each
                # tagged with [Group X][Config Y] via ConfigContextVar)
                self._log_all_configs_settings("session_start")
            asyncio.get_event_loop().call_later(10.0, _log_startup)
            # Broadcast diagnostics — accumulated then logged per minute.
            # Reveals whether the broadcast loop's `_build_state()` and
            # `json.dumps()` are growing over time (which would inflate
            # the orchestrator's measured sweep_ms because broadcast runs
            # during the sweep's `await asyncio.sleep(0)` yields).
            bcast_diag_last_ts: float = 0.0
            bcast_diag_build_ms: float = 0.0
            bcast_diag_dumps_ms: float = 0.0
            bcast_diag_payload_bytes: int = 0
            bcast_diag_count: int = 0
            while self._running:
                if self._clients:
                    t_build = time.monotonic()
                    state = self._build_state()
                    build_ms = (time.monotonic() - t_build) * 1000.0
                    t_dumps = time.monotonic()
                    payload = json.dumps(state)
                    dumps_ms = (time.monotonic() - t_dumps) * 1000.0
                    bcast_diag_build_ms += build_ms
                    bcast_diag_dumps_ms += dumps_ms
                    bcast_diag_payload_bytes += len(payload)
                    bcast_diag_count += 1
                    dead: set[Any] = set()
                    # Snapshot to a tuple — `await ws.send()` yields control,
                    # and new clients connecting during the await would mutate
                    # the underlying set, raising "Set changed size during iteration".
                    for ws in tuple(self._clients):
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
                # Auto trade-amount rescale (hourly + on discovery transitions)
                self._check_trade_amount_rescale_triggers()
                # Daily auto-disable thinly-traded (exchange, symbol) combos at 00:01 UTC
                await self._maybe_run_auto_disable_volumes()
                # Periodic auth cleanup (~every 5 min)
                now = time.time()
                if now - self._last_cleanup > 300:
                    self._cleanup_auth()
                    self._last_cleanup = now
                # Enforce IP whitelist on every broadcast cycle (~1s)
                await self._enforce_ip_whitelist()
                # Per-minute broadcast diagnostic — averages of build/dumps
                # times + payload size. Compares directly against the
                # orchestrator's sweep_ms growth to identify whether the
                # broadcast is the source of progressive slowdown.
                now_mono = time.monotonic()
                if now_mono - bcast_diag_last_ts >= 60.0 and bcast_diag_count > 0:
                    bcast_diag_last_ts = now_mono
                    build_avg = bcast_diag_build_ms / bcast_diag_count
                    dumps_avg = bcast_diag_dumps_ms / bcast_diag_count
                    payload_avg_kb = (bcast_diag_payload_bytes / bcast_diag_count) / 1024.0
                    n_clients = len(self._clients)
                    log_total = (
                        self._log_handler.total_count() if self._log_handler else 0
                    )
                    bcast_diag_build_ms = 0.0
                    bcast_diag_dumps_ms = 0.0
                    bcast_diag_payload_bytes = 0
                    bcast_diag_count = 0
                    # Per-section payload sizing — sample one build to
                    # see which sections dominate the payload. Cheap
                    # because we already build the state every second.
                    section_sizes: dict[str, int] = {}
                    try:
                        sample_state = self._build_state()
                        for k, v in sample_state.items():
                            try:
                                section_sizes[k] = len(json.dumps(v, default=str))
                            except Exception:
                                section_sizes[k] = 0
                    except Exception:
                        pass
                    top_sections = sorted(
                        section_sizes.items(), key=lambda kv: kv[1], reverse=True
                    )[:8]
                    logger.info(
                        f"[Broadcast] build_avg={build_avg:.0f}ms "
                        f"dumps_avg={dumps_avg:.0f}ms payload_avg={payload_avg_kb:.0f}KB "
                        f"clients={n_clients} log_entries={log_total}"
                    )
                    if top_sections:
                        logger.info(
                            "[Broadcast] top_sections: " +
                            ", ".join(
                                f"{k}={v // 1024}KB" if v >= 1024
                                else f"{k}={v}B"
                                for k, v in top_sections
                            )
                        )
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

    # Fields where 0 is a valid "feature off / ignore this knob" signal.
    # The validator accepts 0 even when the field's `min` is otherwise > 0,
    # so the operator can opt out of the feature while leaving normal
    # ranges enforced when the feature IS in use. Fields not in this set
    # reject 0 with a clear error pointing the operator at the matching
    # `*_enabled` toggle (or telling them no disable exists for that knob).
    _DISABLE_VIA_ZERO: set[str] = {
        "trade_amount_pct",  # 0 = use fixed trade_amount_usd
        "fee_threshold_multiplier",  # 0 = no fee-aware threshold adjustment
        "hourly_external_transfer_cap",  # 0 = unlimited
        "spread_persistence_ticks",  # 0 = instant execution
        "event_driven_seller_penalty_pct",  # 0 = no EVD penalty
        "one_leg_failure_rate",  # 0 = no one-leg simulation
        "max_position_multiplier",  # 0 = no per-position cap
        "auto_disable_volume_threshold_usd",  # 0 = never auto-disable
        "trading_float_multiplier",  # 0 = trading float disabled entirely
        "trading_float_replenish_trigger",  # 0 = never auto-replenish
        "trading_float_overflow_multiplier",  # 0 = never sweep overflow
        "min_net_profit_pct",  # 0 = trade on any positive net
    }

    # Fields where 0 would silently break the bot (timers, division, etc.)
    # The validator rejects 0 with a message pointing at the right toggle.
    _DISABLE_HINT: dict[str, str] = {
        "anomaly_protection_enabled": "anomaly_protection_enabled=false",
        "circuit_breaker_window": "anomaly_protection_enabled=false",
        "circuit_breaker_threshold": "anomaly_protection_enabled=false",
        "drawdown_threshold_pct": "anomaly_protection_enabled=false",
        "drawdown_emergency_mult": "anomaly_protection_enabled=false",
        "realized_drawdown_emergency_pct": "anomaly_protection_enabled=false",
        "combined_drawdown_emergency_pct": "anomaly_protection_enabled=false",
        "combined_drawdown_sustained_seconds": "anomaly_protection_enabled=false",
        "symbol_loss_streak_threshold": "anomaly_protection_enabled=false",
        "warning_pnl_pct": "anomaly_protection_enabled=false",
        "momentum_lookback_hours": "momentum_filter_enabled=false",
        "momentum_sample_interval_minutes": "momentum_filter_enabled=false",
        "inventory_rebalance_interval_hours": "inventory_rebalance_enabled=false",
        "inventory_drift_threshold": "inventory_rebalance_enabled=false",
        "funding_poll_interval_seconds": "funding_aware_scoring_enabled=false",
        "funding_score_min_factor": "funding_aware_scoring_enabled=false",
        "funding_score_max_factor": "funding_aware_scoring_enabled=false",
        "hedge_evaluation_interval_seconds": "hedging_enabled=false",
        "hedge_dust_threshold_usd": "hedging_enabled=false",
        "hedge_adjust_threshold_pct": "hedging_enabled=false",
        "scoring_window": "(no disable — would divide by zero)",
        "evaluation_interval": "(no disable — would tight-loop)",
        "discovery_duration": "(no disable — would skip discovery)",
        "num_active_symbols": "(no disable — would prevent any activation)",
        "max_active_symbols": "(no disable — would prevent any activation)",
        "confirmation_period": "(no disable — would activate on first sample)",
        "score_stability_seconds": "(no disable — see score_stability_factor)",
        "score_stability_factor": "(no disable — would reject every candidate)",
        "demotion_period": "(no disable — would demote instantly)",
        "rebalance_cooldown": "(no disable — would rebalance every tick)",
        "rebalance_roi_horizon": "(no disable — would divide by zero)",
        "rebalance_roi_divisor": "(no disable — would divide by zero)",
        "total_capital": "(no disable — use Stop Trading instead)",
        "trade_amount_usd": "(no disable — set trade_amount_pct > 0 to ignore)",
    }

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
        # v0.30+: capital architecture
        "custody_hub_exchange": (str, None, None),
        "custody_hub_network": (str, None, None),
        # 0 accepted as "trading float disabled" via _DISABLE_VIA_ZERO.
        "trading_float_multiplier": (float, 2.0, 50.0),
        "trading_float_replenish_trigger": (float, 0.5, 50.0),
        "trading_float_overflow_multiplier": (float, 1.1, 5.0),
        # Deprecated v0.30 (kept for backward-compat — operator can ignore)
        "bitfinex_reserve_pct": (float, 0.0, 0.5),
        "bitfinex_reserve_hard_floor": (float, 0.0, 0.20),
        "net_pct_sizing_enabled": (bool, None, None),
        "net_pct_multiplier_cap": (float, 1.0, 10.0),
        "spread_persistence_ticks": (int, 0, 5),
        "event_driven_seller_penalty_pct": (float, 0.0, 1.0),
        "one_leg_failure_rate": (float, 0.0, 0.20),
        "one_leg_unwind_slippage_mult": (float, 1.0, 5.0),
        "max_position_multiplier": (float, 0, 50),
        # Price momentum filter (Feature 3)
        "momentum_filter_enabled": (bool, None, None),
        "momentum_lookback_hours": (float, 1.0, 168.0),
        "momentum_sample_interval_minutes": (float, 1.0, 360.0),
        "momentum_min_factor": (float, 0.0, 1.0),
        "momentum_max_factor": (float, 1.0, 5.0),
        # Periodic inventory rebalance (Feature 4)
        "inventory_rebalance_enabled": (bool, None, None),
        "inventory_rebalance_interval_hours": (float, 0.5, 168.0),
        "inventory_drift_threshold": (float, 0.05, 2.0),
        # Bitfinex over-target redistribution (Feature 5)
        "bitfinex_over_target_enabled": (bool, None, None),
        "bitfinex_over_target_multiplier": (float, 1.0, 5.0),
        # Auto-expand on understaff (Feature 6)
        "auto_expand_on_understaff": (bool, None, None),
        # Time-based regime gating (per-config). UTC hours are categorized
        # into strong/neutral/weak buckets; weak hours apply tightened
        # thresholds + suppress rebalance/demote/expand to avoid fee
        # churn during thin spread windows. See SESSIONS.md analysis of
        # 9-day pattern showing 17:00-19:00 / 12:00-14:00 UTC as worst
        # hours and 07:00 / 20:00-22:00 UTC as best.
        "regime_gating_enabled": (bool, None, None),
        "regime_strong_hours": (list, None, None),     # list[int 0-23]
        "regime_neutral_hours": (list, None, None),    # list[int 0-23]
        "regime_weak_min_net_multiplier": (float, 1.0, 10.0),
        "regime_weak_disable_rebalance": (bool, None, None),
        "regime_weak_disable_demote": (bool, None, None),
        "regime_weak_disable_expand": (bool, None, None),
        # Anti-churn: demotion-frequency cooldown scaling + quiet-period
        # pause + activation-cost multiplier (3-bundle for 2026-05-03 fix).
        "demotion_freq_scaling_enabled": (bool, None, None),
        "quiet_period_pause_minutes": (float, 0.0, 240.0),
        "activation_profit_horizon_multiplier": (float, 1.0, 10.0),
        # Diversification floor (S21 follow-up)
        "diversification_floor_enabled": (bool, None, None),
        "diversification_floor_multiplier": (float, 0.1, 1.0),
        # Fast-track discovery exit (S29 follow-up)
        "fast_track_discovery_enabled": (bool, None, None),
        "fast_track_aggressiveness": (float, 0.1, 3.0),
        "auto_disable_volume_enabled": (bool, None, None),
        "auto_disable_volume_threshold_usd": (float, 0.0, 10_000_000.0),
        # Funding-aware scoring (Phase A)
        "funding_aware_scoring_enabled": (bool, None, None),
        "funding_skip_threshold_4h_pct": (float, -1.0, 1.0),
        "funding_skip_threshold_8h_pct": (float, -1.0, 1.0),
        "funding_score_min_factor": (float, 0.05, 1.0),
        "funding_score_max_factor": (float, 1.0, 5.0),
        "funding_poll_interval_seconds": (float, 30.0, 600.0),
        # Spot-futures hedging (Phase C+)
        "hedging_enabled": (bool, None, None),
        "hedge_execution_mode": (str, None, None),
        "hedge_dust_threshold_usd": (float, 1.0, 10000.0),
        "hedge_evaluation_interval_seconds": (float, 30.0, 7200.0),
        "hedge_margin_buffer_pct": (float, 0.0, 1.0),
        "hedge_adjust_threshold_pct": (float, 0.01, 1.0),
        # Anomaly protection
        "anomaly_protection_enabled": (bool, None, None),
        "circuit_breaker_window": (int, 60, 7200),
        "circuit_breaker_threshold": (float, -1000, 0),
        "circuit_breaker_resume_pct": (float, 0.1, 1.0),
        "circuit_breaker_cooldown": (int, 30, 3600),
        "drawdown_threshold_pct": (float, 0.5, 20.0),
        "drawdown_resume_pct": (float, 0.1, 10.0),
        "drawdown_emergency_mult": (float, 1.5, 5.0),
        # v0.31.0-beta+: two-layer emergency gate
        "realized_drawdown_emergency_pct": (float, 1.0, 50.0),
        "combined_drawdown_emergency_pct": (float, 1.0, 80.0),
        "combined_drawdown_sustained_seconds": (float, 30.0, 3600.0),
        "emergency_auto_liquidate": (bool, None, None),
        "symbol_loss_streak_threshold": (int, 2, 50),
        "symbol_loss_streak_cooldown": (int, 60, 7200),
        "warning_pnl_pct": (float, 0.1, 1.0),
    }

    _SETTINGS_ENUMS: dict[str, list[str]] = {
        "execution_mode": ["simulation", "demo", "demo_only"],
        "hedge_execution_mode": ["simulation", "testnet", "live"],
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
                # 0 = "feature off" for fields in the disable-via-zero set.
                # Skip the min check so the operator can opt out while still
                # enforcing the normal range when the feature IS in use.
                if value == 0 and key in cls._DISABLE_VIA_ZERO:
                    continue
                # If 0 isn't a valid disable signal for this field, reject
                # with a hint pointing at the correct toggle.
                if value == 0 and min_val is not None and min_val > 0:
                    hint = cls._DISABLE_HINT.get(key)
                    if hint:
                        return False, (
                            f"{key} cannot be 0 — to disable this feature, "
                            f"use {hint}. Otherwise must be >= {min_val}."
                        )
                    return False, f"{key} must be >= {min_val}"
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
        "as_buyer": (bool, None, None),
        "as_seller": (bool, None, None),
        "disabled_symbols": (list, None, None),
        "auto_disabled_symbols": (list, None, None),
        "buyer_boost": (float, 0.0, 100.0),
        "seller_boost": (float, 0.0, 100.0),
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
            logger.info("[Dashboard] Settings applied")

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

        elif msg_type == "fetch_volumes":
            # On-demand 24h USD volume fetch for all 9 exchanges. After the
            # fetch, applies the auto-disable threshold across EVERY config's
            # FeeManager so disabled symbols stay in sync with the latest
            # volumes (manual fetch == immediate apply, just like the daily
            # cron at 00:01 UTC).
            try:
                from volume_fetcher import fetch_all_24h_volumes
                volumes = await fetch_all_24h_volumes()
                fetched_at = time.time()
                self._last_manual_volumes_fetch_ts = fetched_at
                # Cache for broadcast — survives page refresh
                self._cached_volumes = volumes
                self._save_auto_disable_state()
                # Apply auto-disable across all configs (multi-config aware)
                apply_summary = self._apply_auto_disable_to_all_configs(volumes)
                await ws.send(json.dumps({
                    "type": "volumes_response",
                    "ok": True,
                    "volumes": volumes,
                    "fetched_at": fetched_at,
                    "auto_disable_summary": apply_summary,
                }))
                logger.info(
                    f"[VolumeFetch] Fetched 24h volumes: "
                    f"{ {ex: len(v) for ex, v in volumes.items()} } — "
                    f"applied auto-disable to {apply_summary['configs_updated']} config(s) "
                    f"(+{apply_summary['total_added']} disabled / "
                    f"-{apply_summary['total_removed']} re-enabled)"
                )
            except Exception as e:
                logger.exception("[VolumeFetch] Failed")
                await ws.send(json.dumps({
                    "type": "volumes_response",
                    "ok": False,
                    "error": str(e),
                }))

        elif msg_type == "request_all_bot_logs":
            # Return ALL in-memory session logs (for filtered views)
            entries = self._log_handler.get_all() if self._log_handler else []
            await ws.send(json.dumps({"type": "all_bot_logs_result", "logs": entries}))

        elif msg_type == "export_bot_logs":
            start_ts = msg.get("start", 0)
            end_ts = msg.get("end", time.time())
            entries = await asyncio.to_thread(self._read_bot_logs_from_disk, start_ts, end_ts)
            await self._send_chunked_export(ws, "export_bot_logs", entries)

        elif msg_type == "export_auth_logs":
            start_ts = msg.get("start", 0)
            end_ts = msg.get("end", time.time())
            entries = await asyncio.to_thread(self._read_auth_logs_from_disk, start_ts, end_ts)
            await self._send_chunked_export(ws, "export_auth_logs", entries)

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

        elif msg_type in ("distribute_from_custody_hub", "distribute_from_bitfinex"):
            # v0.30+: accepts new message type, keeps old one as alias for
            # forward compatibility with cached frontends after deploy
            if not self._distribute_enabled:
                await ws.send(json.dumps({
                    "type": "distribute_error",
                    "error": "Distribution not enabled",
                }))
                return
            result = self._distribute_from_custody_hub()
            self._distribute_enabled = False
            await ws.send(json.dumps({"type": "distribute_result", **result}))

        elif msg_type == "restart" or msg_type == "process_restart":
            logger.info("[Dashboard] Fresh restart requested from dashboard")
            # Close all real futures positions before clearing state — orphan
            # positions inherited across restarts produce phantom drawdowns
            # via futures markPrice divergence (S30: -$215 unrealized loss
            # from a -273 PENDLE short adopted at $1.3357 from prior session).
            try:
                hm = getattr(self._monitor, "_hedge_manager", None)
                if hm is not None:
                    res = await hm.close_all_real_positions(reason="restart")
                    logger.info(
                        f"[Dashboard] Restart pre-flight: "
                        f"closed {res.get('n_closed', 0)} hedge positions, "
                        f"failed {res.get('n_failed', 0)}"
                    )
            except Exception as e:
                logger.error(f"[Dashboard] Restart pre-flight hedge close failed: {e}")
            if self._state_manager:
                self._state_manager.clear()
            await ws.send(json.dumps({"type": "restart_ack"}))
            asyncio.get_event_loop().call_later(1.0, self._trigger_restart)

        # ── Multi-config CRUD (v0.31.0-beta) ─────────────────────────
        elif msg_type.startswith("config_") or msg_type == "save_shared_execution_mode" or msg_type == "select_config" or msg_type == "subscribe_logs":
            await self._handle_config_message(msg, ws, msg_type)

    async def _handle_config_message(self, msg: dict, ws: Any, msg_type: str) -> None:
        """Multi-config (v0.31.0-beta) WS handlers. All mutations save the
        registry to settings.json; structural mutations also call
        orchestrator.reconcile_components() to propagate."""
        if not getattr(self, "_registry", None) or not getattr(self, "_orchestrator", None):
            await ws.send(json.dumps({
                "type": "config_error",
                "error": "Multi-config registry not initialized",
            }))
            return

        registry = self._registry
        orch = self._orchestrator

        async def _ack(extra: dict | None = None) -> None:
            payload = {"type": "config_ack", "msg_type": msg_type, "ok": True}
            if extra:
                payload.update(extra)
            await ws.send(json.dumps(payload))

        async def _err(message: str) -> None:
            await ws.send(json.dumps({
                "type": "config_error",
                "msg_type": msg_type,
                "error": message,
            }))

        try:
            if msg_type == "config_add_group":
                name = msg.get("name") or None
                capital = float(msg.get("initial_capital", 1000.0))
                g = registry.add_group(name=name, initial_capital=capital)
                save_registry(registry)
                await orch.reconcile_components()
                await _ack({"group_id": g.id})

            elif msg_type == "config_remove_group":
                gid = msg.get("group_id")
                # Capture the cascading config list BEFORE remove so we can
                # clean up per-config state files + close real hedges.
                # Without this, group-remove orphans every config's
                # session.json on disk indefinitely (S31: 11 stale files).
                g = registry.find_group(gid)
                cascade_ids: list[str] = []
                cascade_names: list[str] = []
                if g is not None:
                    for c in list(g.configs):
                        cascade_ids.append(c.id)
                        cascade_names.append(c.name)
                        bundle = orch.get_bundle(c.id)
                        if bundle and bundle.hedge_mode in ("testnet", "live") and bundle.hedge_manager:
                            try:
                                await bundle.hedge_manager.close_all_real_positions(
                                    reason="config_remove_group"
                                )
                            except Exception as e:
                                logger.warning(
                                    f"[Config] hedge close on group remove failed for "
                                    f"{c.id[:8]}…: {e}"
                                )
                group_name = g.name if g else "(unknown)"
                registry.remove_group(gid)
                save_registry(registry)
                # Wipe per-config state files + their directories
                if self._state_manager:
                    for cid in cascade_ids:
                        self._state_manager.clear_config(cid, remove_dir=True)
                await orch.reconcile_components()
                # Re-point selected config if it was in the removed group
                if getattr(self, "_selected_config_id", None) in cascade_ids:
                    fallback_cfg = registry.default_config
                    if fallback_cfg is None:
                        # Defensive: pick any remaining config
                        for c in registry.iter_configs():
                            fallback_cfg = c
                            break
                    if fallback_cfg is not None:
                        fallback_bundle = orch.get_bundle(fallback_cfg.id)
                        if fallback_bundle is not None:
                            self._monitor = fallback_bundle.monitor
                            self._optimizer = fallback_bundle.optimizer
                            self._balance = fallback_bundle.balance
                            self._fee_manager = fallback_bundle.fee_manager
                            self._selected_config_id = fallback_cfg.id
                            logger.info(
                                f"[Config] Selected config was in removed "
                                f"group; falling back to '{fallback_cfg.name}'"
                            )
                logger.info(
                    f"[Config] Removed group '{group_name}' "
                    f"({len(cascade_ids)} config(s): "
                    f"{', '.join(cascade_names) if cascade_names else 'none'})"
                )
                await _ack()

            elif msg_type == "config_rename_group":
                gid = msg.get("group_id")
                name = msg.get("name", "")
                registry.rename_group(gid, name)
                save_registry(registry)
                await _ack()

            elif msg_type == "config_set_capital":
                gid = msg.get("group_id")
                cap = float(msg.get("initial_capital", 0))
                registry.set_group_capital(gid, cap)
                save_registry(registry)
                # Capital change resets per-config balances → restart configs
                g = registry.find_group(gid)
                if g:
                    for c in g.configs:
                        await orch.request_restart(c.id)
                await _ack()

            elif msg_type == "config_reorder_groups":
                order = msg.get("order", [])
                registry.reorder_groups(order)
                save_registry(registry)
                await _ack()

            elif msg_type == "config_add":
                gid = msg.get("group_id")
                # If no settings provided, inherit from default config (so new
                # configs start with current bot defaults, not empty)
                settings = msg.get("settings")
                if not settings and registry.default_config:
                    settings = dict(registry.default_config.settings)
                c = registry.add_config(
                    group_id=gid,
                    settings=settings,
                    name=msg.get("name"),
                    description=msg.get("description", ""),
                )
                save_registry(registry)
                await orch.reconcile_components()
                # Log full settings for the new config
                self._log_one_config_settings(c.id, "config_added")
                await _ack({"config_id": c.id})

            elif msg_type == "config_remove":
                cid = msg.get("config_id")
                # Capture name + group BEFORE registry removal so the log
                # line is human-readable.
                cfg = registry.find_config(cid)
                grp = registry.find_group_for_config(cid) if cfg else None
                cfg_name = cfg.name if cfg else "(unknown)"
                grp_name = grp.name if grp else "(unknown)"
                # Try to close any real futures positions first if super-primary
                bundle = orch.get_bundle(cid)
                if bundle and bundle.hedge_mode in ("testnet", "live") and bundle.hedge_manager:
                    try:
                        await bundle.hedge_manager.close_all_real_positions(
                            reason="config_remove"
                        )
                    except Exception as e:
                        logger.warning(f"[Config] hedge close on remove failed: {e}")
                registry.remove_config(cid)
                save_registry(registry)
                # Delete per-config state file + the now-empty directory
                if self._state_manager:
                    self._state_manager.clear_config(cid, remove_dir=True)
                await orch.reconcile_components()
                # Re-point selected config if it was the removed one. Otherwise
                # the dashboard's `self._monitor` / `self._optimizer` / etc.
                # still reference torn-down components — the next broadcast
                # would try to read state from objects no longer wired to
                # fetchers, producing stale or zero data.
                if getattr(self, "_selected_config_id", None) == cid:
                    fallback_cfg = registry.default_config or (
                        registry.iter_configs().__next__()
                        if any(True for _ in registry.iter_configs()) else None
                    )
                    if fallback_cfg is not None:
                        fallback_bundle = orch.get_bundle(fallback_cfg.id)
                        if fallback_bundle is not None:
                            self._monitor = fallback_bundle.monitor
                            self._optimizer = fallback_bundle.optimizer
                            self._balance = fallback_bundle.balance
                            self._fee_manager = fallback_bundle.fee_manager
                            self._selected_config_id = fallback_cfg.id
                            logger.info(
                                f"[Config] Selected config was removed; "
                                f"falling back to '{fallback_cfg.name}'"
                            )
                logger.info(
                    f"[Config] Removed config '{cfg_name}' from group '{grp_name}' "
                    f"(id={cid[:8]}…)"
                )
                await _ack()

            elif msg_type == "config_clone":
                cid = msg.get("config_id")
                target_gid = msg.get("target_group_id")
                new_name = msg.get("name")
                clone = registry.clone_config(cid, target_gid, new_name)
                save_registry(registry)
                await orch.reconcile_components()
                self._log_one_config_settings(clone.id, "config_cloned")
                await _ack({"config_id": clone.id})

            elif msg_type == "config_clone_group":
                gid = msg.get("group_id")
                new_name = msg.get("name")
                src_group = registry.find_group(gid)
                if src_group is None:
                    return await _err(f"Group not found: {gid}")
                # Create new group with same capital
                new_group = registry.add_group(
                    name=new_name or f"{src_group.name} (copy)",
                    initial_capital=src_group.initial_capital,
                )
                # Copy each config (without primary/default/super-primary flags)
                for src_cfg in sorted(src_group.configs, key=lambda x: x.order):
                    registry.add_config(
                        group_id=new_group.id,
                        settings=dict(src_cfg.settings),
                        name=src_cfg.name,
                        description=src_cfg.description,
                    )
                save_registry(registry)
                await orch.reconcile_components()
                # Log every newly-cloned config in the new group
                logger.info(
                    f"[Config] Cloned group '{src_group.name}' → "
                    f"'{new_group.name}' ({len(new_group.configs)} configs)"
                )
                for c in new_group.configs:
                    self._log_one_config_settings(c.id, "group_cloned")
                await _ack({"group_id": new_group.id})

            elif msg_type == "config_rename":
                cid = msg.get("config_id")
                name = msg.get("name", "")
                desc = msg.get("description")
                registry.rename_config(cid, name, desc)
                save_registry(registry)
                await _ack()

            elif msg_type == "config_reorder":
                gid = msg.get("group_id")
                order = msg.get("order", [])
                registry.reorder_configs(gid, order)
                save_registry(registry)
                await _ack()

            elif msg_type == "config_set_primary":
                cid = msg.get("config_id")
                value = bool(msg.get("value", False))
                registry.set_primary(cid, value)
                save_registry(registry)
                await _ack()

            elif msg_type == "config_set_default":
                cid = msg.get("config_id")
                registry.set_default(cid)
                save_registry(registry)
                await _ack()

            elif msg_type == "config_set_super_primary":
                cid = msg.get("config_id")
                # Close real futures positions on the outgoing super-primary
                old_sp_id = registry.super_primary_id
                if old_sp_id and old_sp_id != cid:
                    old_bundle = orch.get_bundle(old_sp_id)
                    if old_bundle and old_bundle.hedge_mode in ("testnet", "live") and old_bundle.hedge_manager:
                        try:
                            await old_bundle.hedge_manager.close_all_real_positions(
                                reason="super_primary_handoff"
                            )
                        except Exception as e:
                            logger.warning(
                                f"[Config] hedge close on super-primary handoff failed: {e}"
                            )
                registry.set_super_primary(cid)
                save_registry(registry)
                # Reconcile rebuilds both old + new super-primary with new
                # effective execution mode + hedge mode
                await orch.reconcile_components()
                await _ack()

            elif msg_type == "config_apply_settings":
                cid = msg.get("config_id")
                settings = msg.get("settings", {})
                cfg = registry.find_config(cid)
                if cfg is None:
                    return await _err(f"Config not found: {cid}")
                bundle = orch.get_bundle(cid)
                if bundle is None:
                    return await _err(f"Bundle not built: {cid}")
                # Update the registry first (persisted source of truth)
                registry.update_config_settings(cid, settings)
                save_registry(registry)
                # Hot-apply against the bundle's components, tagged in logs
                from log_context import set_config_context, reset_config_context
                group = registry.find_group_for_config(cid)
                token = (
                    set_config_context(group.id, group.name, cfg.id, cfg.name)
                    if group else None
                )
                try:
                    self._apply_settings_to_bundle(bundle, dict(cfg.settings))
                finally:
                    if token:
                        reset_config_context(token)
                # Log the new state of this specific config
                self._log_one_config_settings(cid, "settings_applied")
                await _ack()

            elif msg_type == "config_apply_settings_bulk":
                cids = msg.get("config_ids", [])
                settings = msg.get("settings", {})
                applied = 0
                for cid in cids:
                    cfg = registry.find_config(cid)
                    bundle = orch.get_bundle(cid)
                    if cfg is None or bundle is None:
                        continue
                    registry.update_config_settings(cid, settings)
                    self._apply_settings_to_bundle(bundle, dict(cfg.settings))
                    applied += 1
                save_registry(registry)
                await _ack({"applied": applied})

            elif msg_type == "config_restart":
                cid = msg.get("config_id")
                # Wipe per-config state file, then rebuild
                if self._state_manager:
                    self._state_manager.clear_config(cid)
                ok = await orch.request_restart(cid)
                if not ok:
                    return await _err(f"Config not found in orchestrator: {cid}")
                # Log the freshly-rebuilt config's full settings so the operator
                # has a clean record of what's now running after the restart.
                self._log_one_config_settings(cid, "config_restarted")
                # If this was the selected config, repoint to the new bundle —
                # the OLD bundle's components are torn down and stale.
                if getattr(self, "_selected_config_id", None) == cid:
                    new_bundle = orch.get_bundle(cid)
                    if new_bundle is not None:
                        self._monitor = new_bundle.monitor
                        self._optimizer = new_bundle.optimizer
                        self._balance = new_bundle.balance
                        self._fee_manager = new_bundle.fee_manager
                await _ack()

            elif msg_type == "config_restart_all":
                # Wipe all per-config state files, then rebuild every config
                if self._state_manager:
                    for c in registry.iter_configs():
                        self._state_manager.clear_config(c.id)
                n = await orch.request_restart_all()
                self._log_all_configs_settings("restart_all_configs")
                # All bundles were torn down + rebuilt; selected config's
                # references are stale. Repoint to the new bundle.
                cur_sel = getattr(self, "_selected_config_id", None)
                if cur_sel:
                    new_bundle = orch.get_bundle(cur_sel)
                    if new_bundle is not None:
                        self._monitor = new_bundle.monitor
                        self._optimizer = new_bundle.optimizer
                        self._balance = new_bundle.balance
                        self._fee_manager = new_bundle.fee_manager
                await _ack({"restarted": n})

            elif msg_type == "config_anomaly_resume":
                # Per-config anomaly resume — clears emergency_triggered + paused
                # for ONE config (vs the legacy `anomaly_resume` which targets
                # the dashboard-bound default config).
                cid = msg.get("config_id")
                bundle = orch.get_bundle(cid)
                if bundle is None:
                    return await _err(f"Config not found: {cid}")
                try:
                    bundle.monitor._anomaly.manual_resume()
                    bundle.monitor._anomaly_paused = False
                    cfg = registry.find_config(cid)
                    g = registry.find_group_for_config(cid)
                    label = f"{g.name}/{cfg.name}" if cfg and g else cid[:8]
                    logger.info(f"[Anomaly] Manual resume for {label} via dashboard")
                except Exception as e:
                    return await _err(f"Resume failed: {e}")
                await _ack()

            elif msg_type == "config_manual_stop":
                # Per-config manual stop — sets _manual_stopped + timestamp.
                cid = msg.get("config_id")
                bundle = orch.get_bundle(cid)
                if bundle is None:
                    return await _err(f"Config not found: {cid}")
                bundle.monitor._manual_stopped = True
                bundle.monitor._manual_stop_timestamp = time.time()
                cfg = registry.find_config(cid)
                g = registry.find_group_for_config(cid)
                label = f"{g.name}/{cfg.name}" if cfg and g else cid[:8]
                logger.info(f"[Monitor] MANUAL_STOP for {label} via dashboard")
                await _ack()

            elif msg_type == "config_manual_start":
                # Per-config manual start — clears _manual_stopped.
                cid = msg.get("config_id")
                bundle = orch.get_bundle(cid)
                if bundle is None:
                    return await _err(f"Config not found: {cid}")
                bundle.monitor._manual_stopped = False
                bundle.monitor._manual_stop_timestamp = 0.0
                cfg = registry.find_config(cid)
                g = registry.find_group_for_config(cid)
                label = f"{g.name}/{cfg.name}" if cfg and g else cid[:8]
                logger.info(f"[Monitor] MANUAL_START for {label} via dashboard")
                await _ack()

            elif msg_type == "config_export_all":
                # Returns the full registry payload as the operator would see
                # it on disk. Frontend serializes to JSON + downloads as file.
                payload = registry.to_settings_dict()
                await ws.send(json.dumps({
                    "type": "config_export_response",
                    "ok": True,
                    "payload": payload,
                    "exported_at": time.time(),
                }))

            elif msg_type == "config_import_all":
                # Replaces the entire registry with the uploaded payload.
                # The new registry is reconciled against the orchestrator —
                # configs not in the new payload are torn down (real hedges
                # closed first); new configs are built; existing configs are
                # rebuilt if their settings changed.
                payload = msg.get("payload")
                if not isinstance(payload, dict) or "groups" not in payload:
                    return await _err("Invalid import payload: missing 'groups'")
                # Validate schema_version
                if payload.get("schema_version") not in (None, 2):
                    return await _err(
                        f"Unsupported schema_version: {payload.get('schema_version')}"
                    )
                # Close real hedge positions on every existing bundle BEFORE
                # the registry swap — otherwise teardown might race against
                # the import.
                for bundle in orch.all_bundles():
                    if bundle.hedge_mode in ("testnet", "live") and bundle.hedge_manager:
                        try:
                            await bundle.hedge_manager.close_all_real_positions(
                                reason="config_import"
                            )
                        except Exception as e:
                            logger.warning(
                                f"[Config] hedge close on import failed: {e}"
                            )
                # Replace registry — delete on-disk state for configs that won't
                # exist after import (best-effort cleanup).
                old_ids = {c.id for c in registry.iter_configs()}
                from config_registry import ConfigRegistry as _CR
                new_registry = _CR.from_settings_dict(payload)
                new_ids = {c.id for c in new_registry.iter_configs()}
                for gone_id in old_ids - new_ids:
                    if self._state_manager:
                        self._state_manager.clear_config(gone_id)
                # Atomically swap the registry on the dashboard + orchestrator
                # then rebuild the orchestrator's bundles to match.
                self._registry = new_registry
                orch._registry = new_registry
                save_registry(new_registry)
                await orch.reconcile_components()
                self._log_all_configs_settings("config_import")
                logger.info(
                    f"[Config] Imported registry: "
                    f"{len(new_registry.groups)} group(s), "
                    f"{len(new_registry.all_configs())} config(s) "
                    f"(was {len(old_ids)}, removed {len(old_ids - new_ids)}, added {len(new_ids - old_ids)})"
                )
                await _ack({
                    "groups": len(new_registry.groups),
                    "configs": len(new_registry.all_configs()),
                    "added": len(new_ids - old_ids),
                    "removed": len(old_ids - new_ids),
                })

            elif msg_type == "save_shared_execution_mode":
                exec_mode = msg.get("execution_mode")
                hedge_mode = msg.get("hedge_execution_mode")
                # If multiple configs exist, force-lock to simulation
                if len(registry.all_configs()) > 1:
                    if exec_mode and exec_mode != "simulation":
                        logger.warning(
                            f"[Config] Forcing execution_mode=simulation "
                            f"({len(registry.all_configs())} configs > 1; only super-primary "
                            f"can use {exec_mode})"
                        )
                    # Allow setting it — orchestrator force-locks at component build
                if exec_mode is not None:
                    registry.update_shared("execution_mode", exec_mode)
                if hedge_mode is not None:
                    registry.update_shared("hedge_execution_mode", hedge_mode)
                save_registry(registry)
                # Reconcile — super-primary's bundle rebuilds with new mode
                await orch.reconcile_components()
                await _ack()

            elif msg_type == "config_request_settings":
                # Returns a single config's full settings blob (for copy/paste)
                cid = msg.get("config_id")
                cfg = registry.find_config(cid)
                if cfg is None:
                    return await _err(f"Config not found: {cid}")
                await ws.send(json.dumps({
                    "type": "config_settings_response",
                    "config_id": cid,
                    "name": cfg.name,
                    "description": cfg.description,
                    "settings": cfg.settings,
                }))

            elif msg_type == "select_config":
                cid = msg.get("config_id")
                bundle = orch.get_bundle(cid)
                if bundle is None:
                    return await _err(f"Config not found: {cid}")
                # Swap the dashboard's references so subsequent broadcasts
                # render the heavy slice for this bundle. Single-operator
                # model — the latest selection wins (multi-operator racing
                # is acceptable for current use case).
                self._monitor = bundle.monitor
                self._optimizer = bundle.optimizer
                self._balance = bundle.balance
                self._fee_manager = bundle.fee_manager
                self._selected_config_id = cid
                logger.info(f"[Dashboard] Selected config: {cid} ({bundle.config_name})")
                await _ack({"selected_config_id": cid})

            elif msg_type == "subscribe_logs":
                # Per-WS log filter: stash on the websocket
                ws._log_subscription = {
                    "scope": msg.get("scope", "all"),  # all|universal|group|config
                    "group_id": msg.get("group_id"),
                    "config_id": msg.get("config_id"),
                }
                await _ack({"log_subscription": ws._log_subscription})

            else:
                await _err(f"Unknown config message type: {msg_type}")

        except (KeyError, ValueError) as e:
            await _err(str(e))
        except Exception as e:
            logger.exception(f"[Config] {msg_type} failed: {e}")
            await _err(f"Internal error: {e}")

    def _apply_settings_to_bundle(self, bundle, settings: dict) -> None:
        """Hot-apply per-config settings against an arbitrary bundle by
        temporarily swapping dashboard component references and reusing
        the existing `_apply_settings` logic.

        v0.31.0-beta+: total_capital is ALWAYS sourced from the bundle's
        group, never from the passed `settings` dict. This prevents the
        Paste / Paste-All flow from corrupting capital — pasting Group 1's
        Config 1 settings onto a Group 2 config used to inject Group 1's
        $1000 (or worse, fall back to the 1800 default) into Group 2's
        bundle, even though Group 2's group capital was $2000. The capital
        mismatch then poisoned the realized peak vs current realized
        comparison and triggered phantom Layer A emergencies (observed in
        S31 with realized_drawdown=50% the moment the operator clicked a
        freshly-pasted config).
        """
        # Pull group capital from the registry — single source of truth.
        registry = getattr(self, "_registry", None)
        group_capital = None
        if registry is not None:
            group = registry.find_group_for_config(bundle.config_id)
            if group is not None:
                group_capital = float(group.initial_capital)
        # Strip total_capital from the incoming dict (paste payloads may
        # carry it from older flows / legacy frontend code) and inject the
        # authoritative group capital. Done on a copy so callers' dicts
        # aren't mutated.
        applied = dict(settings)
        applied.pop("total_capital", None)
        if group_capital is not None:
            applied["total_capital"] = group_capital

        saved = (self._monitor, self._optimizer, self._balance, self._fee_manager)
        self._monitor = bundle.monitor
        self._optimizer = bundle.optimizer
        self._balance = bundle.balance
        self._fee_manager = bundle.fee_manager
        try:
            # log_global_dump=False: the per-bundle apply path has its own
            # `_log_one_config_settings("settings_applied")` caller-side
            # dump with the correct per-config + group-capital values.
            # Letting the global dump fire here would emit a confusing
            # second log line tagged with the bundle's prefix but
            # showing the stale legacy `self._settings.total_capital`.
            self._apply_settings(applied, log_global_dump=False)
            # Realized peak invariant: after a basis change (capital was
            # configured differently than the anomaly state's prior peak),
            # reset peak to the current realized so we don't drag a stale
            # high-water mark from a different capital era.
            anomaly = getattr(bundle.monitor, "_anomaly", None)
            if anomaly is not None and group_capital is not None:
                peak_realized = float(getattr(anomaly, "_peak_realized_value", 0.0) or 0.0)
                # If the recorded peak differs meaningfully from the new
                # configured capital, the basis has shifted (paste, group
                # capital change, restart with new capital). Reset to 0 so
                # the next update_portfolio_value re-seeds peak from the
                # actual current realized — not the stale value.
                if peak_realized > 0 and abs(peak_realized - group_capital) > max(1.0, group_capital * 0.05):
                    logger.warning(
                        f"[Anomaly] Capital basis change on bundle: "
                        f"peak_realized=${peak_realized:.2f} vs "
                        f"group_capital=${group_capital:.2f} — "
                        f"resetting realized peak to avoid phantom drawdown"
                    )
                    anomaly._peak_realized_value = 0.0
                    anomaly._current_realized_drawdown_pct = 0.0
                    anomaly._peak_portfolio_value = 0.0
                    anomaly._current_drawdown_pct = 0.0
                    anomaly._combined_breach_start = None
        finally:
            self._monitor, self._optimizer, self._balance, self._fee_manager = saved

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

    def _rescale_trade_amount(self, reason: str) -> bool:
        """Recompute trade_amount from current portfolio value × trade_amount_pct.

        Auto-scaling mode: when `trade_amount_pct > 0`, the bot's per-trade size
        should grow with capital. Without this rescale, trade_amount is locked to
        `configured_capital × pct` at startup/settings-apply time and never moves
        as profits compound.

        Triggered:
        - hourly during normal operation (`hourly_tick`)
        - on discovery start/complete transitions (`discovery_started`, `discovery_completed`)
          so symbol allocations use the freshest sizing.

        No-ops when:
        - `trade_amount_pct <= 0` (fixed-size mode is in force)
        - balance is uninitialized (pre-discovery)
        - the new value would be within $0.01 of the existing one

        Returns True if a rescale actually happened.
        """
        if not self._monitor or not self._balance or not self._optimizer:
            return False
        pct = float(self._settings.get("trade_amount_pct", 0.0))
        if pct <= 0:
            return False  # fixed-size mode, nothing to do
        if not self._balance.initialized:
            return False  # pre-discovery, no portfolio value yet

        # Use the same price source the monitor uses for trade decisions, so the
        # rescale tracks the value the bot will actually trade against.
        try:
            prices = self._monitor._get_current_prices()
        except Exception:
            return False

        # Include hedge unrealized PnL — same convention as _build_state's
        # portfolio_value, so drawdown/peak/trade-size all share one definition.
        hedge_pnl_usd = 0.0
        hm = getattr(self._monitor, "_hedge_manager", None)
        if hm is not None:
            try:
                hedge_pnl_usd = float(hm.get_debug_state().get("total_unrealized_pnl_usd", 0.0))
            except Exception:
                hedge_pnl_usd = 0.0

        try:
            # v0.30.1+: per-exchange MTM (Fix A) — same convention as _build_state
            ppe = self._monitor._get_per_exchange_prices()
            portfolio_value = self._balance.get_portfolio_value(
                prices,
                hedge_pnl_usd=hedge_pnl_usd,
                prices_per_exchange=ppe,
            )
        except Exception:
            return False
        if portfolio_value <= 0:
            return False

        new_trade_amount = round(portfolio_value * pct, 2)
        old_trade_amount = float(self._monitor._trade_amount)
        old_capital = float(self._monitor._total_capital)
        if abs(new_trade_amount - old_trade_amount) < 0.01 and abs(portfolio_value - old_capital) < 0.01:
            return False  # within rounding noise

        # Apply to monitor + optimizer (both consume _trade_amount and _total_capital
        # for trade sizing, depth gates, expansion cost estimates, etc.)
        self._monitor._trade_amount = new_trade_amount
        self._monitor._total_capital = portfolio_value
        self._optimizer._trade_amount = new_trade_amount
        self._optimizer._total_capital = portfolio_value

        delta_amount = new_trade_amount - old_trade_amount
        delta_pct = (delta_amount / old_trade_amount * 100) if old_trade_amount > 0 else 0.0
        capital_delta = portfolio_value - old_capital
        capital_delta_pct = (capital_delta / old_capital * 100) if old_capital > 0 else 0.0

        logger.info(
            f"[TradeSize] Rescale ({reason}): "
            f"trade_amount ${old_trade_amount:.2f} → ${new_trade_amount:.2f} "
            f"({delta_pct:+.2f}%, Δ${delta_amount:+.2f}) | "
            f"capital ${old_capital:.2f} → ${portfolio_value:.2f} "
            f"({capital_delta_pct:+.2f}%, Δ${capital_delta:+.2f}) | "
            f"pct={pct * 100:.2f}%"
        )
        self._last_trade_amount_rescale_ts = time.time()
        return True

    def _load_auto_disable_state(self) -> None:
        """Read last-run timestamp from state/auto_disable_volumes.json.

        Survives bot restarts so that:
        - A bot restarted multiple times in the same UTC day does NOT re-fetch
          volumes on every restart (would otherwise hit each exchange's REST
          API redundantly).
        - A bot that was offline at 00:01 UTC reads the stale date on startup
          and the existing time-check logic in `_maybe_run_auto_disable_volumes`
          fires immediately on the first eligible tick.
        """
        if not self._auto_disable_state_file.exists():
            return
        try:
            data = json.loads(self._auto_disable_state_file.read_text())
            self._last_auto_disable_run_date_utc = str(data.get("last_run_date_utc", ""))
            self._last_auto_disable_run_ts = float(data.get("last_run_ts", 0.0))
            self._last_manual_volumes_fetch_ts = float(data.get("last_manual_fetch_ts", 0.0))
            cached = data.get("cached_volumes")
            if isinstance(cached, dict):
                # Validate shape: dict[str, dict[str, float]]
                self._cached_volumes = {
                    str(ex): {str(s): float(v) for s, v in (vols or {}).items() if isinstance(v, (int, float))}
                    for ex, vols in cached.items() if isinstance(vols, dict)
                }
            if self._last_auto_disable_run_date_utc:
                age_hours = (time.time() - self._last_auto_disable_run_ts) / 3600.0
                today_utc = time.strftime("%Y-%m-%d", time.gmtime(time.time()))
                stale = self._last_auto_disable_run_date_utc != today_utc
                logger.info(
                    f"[AutoDisable] Loaded last-run state: {self._last_auto_disable_run_date_utc} "
                    f"({age_hours:.1f}h ago) — {'stale, will fire on next eligible tick' if stale else 'current, will skip until next UTC day'}"
                )
        except Exception as e:
            logger.warning(f"[AutoDisable] Failed to read state file (will run fresh): {e}")
            self._last_auto_disable_run_date_utc = ""
            self._last_auto_disable_run_ts = 0.0

    def _save_auto_disable_state(
        self,
        threshold: float | None = None,
        per_exchange_disable: dict[str, list[str]] | None = None,
        diffs: dict[str, dict] | None = None,
    ) -> None:
        """Persist last-run timestamp + threshold + blocklist snapshot.

        Partial update semantics: pass `None` for fields the caller doesn't
        want to overwrite (e.g. the manual-fetch handler doesn't have new
        blocklist data). Existing values are read from disk and preserved.

        Atomic write via temp file + os.replace, same pattern as state_manager.
        """
        try:
            self._auto_disable_state_file.parent.mkdir(parents=True, exist_ok=True)
            # Preserve existing fields when caller passes None
            existing: dict = {}
            if self._auto_disable_state_file.exists():
                try:
                    existing = json.loads(self._auto_disable_state_file.read_text())
                except Exception:
                    existing = {}
            payload = {
                "last_run_date_utc": self._last_auto_disable_run_date_utc,
                "last_run_ts": self._last_auto_disable_run_ts,
                "last_manual_fetch_ts": self._last_manual_volumes_fetch_ts,
                "threshold_used_usd": (
                    threshold if threshold is not None
                    else existing.get("threshold_used_usd", 10000.0)
                ),
                "blocked_per_exchange": (
                    {ex: list(syms) for ex, syms in per_exchange_disable.items()}
                    if per_exchange_disable is not None
                    else existing.get("blocked_per_exchange", {})
                ),
                "last_diff": (
                    diffs if diffs is not None
                    else existing.get("last_diff", {})
                ),
                # Cached fetched volumes — survives bot restart so the Fee
                # Management UI keeps showing them after browser refresh.
                "cached_volumes": self._cached_volumes,
            }
            tmp = self._auto_disable_state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2))
            os.replace(tmp, self._auto_disable_state_file)
        except Exception:
            logger.exception("[AutoDisable] Failed to persist state file")

    async def _maybe_run_auto_disable_volumes(self) -> None:
        """Hourly auto-disable of thinly-traded (exchange, symbol) combos.

        v0.31 update: was once-per-UTC-day; now runs every hour because
        24h volumes shift fast (operator observed JUP volume jump 100×
        from $205 to $25.6K in minutes once the bot's own trades flowed
        through it). A daily cadence misses this kind of fast change.

        Trigger logic:
          - Forced first run after bot start (refreshes blocklist
            immediately on restart so stale data doesn't persist)
          - Otherwise fires when `last_run_ts` is older than 1 hour

        For each enabled exchange × each symbol in SYMBOLS:
          - Fetch live 24h USD volume from the exchange
          - If volume < threshold → add to auto_disabled_symbols
          - If volume >= threshold → ensure it's NOT in auto_disabled_symbols
        Manual `disabled_symbols` per exchange are never touched.
        """
        if not self._fee_manager:
            return
        if not bool(self._settings.get("auto_disable_volume_enabled", True)):
            return

        # Trigger logic: forced first run, or > 1 hour since last run.
        now = time.time()
        forced = self._auto_disable_force_run_on_start
        if not forced:
            if now - self._last_auto_disable_run_ts < 3600.0:
                return  # ran less than an hour ago
        else:
            logger.info(
                "[AutoDisable] Forced run on startup — refreshing blocklist "
                "regardless of cadence (operator: 'must run on restart')"
            )
        # Keep `_last_auto_disable_run_date_utc` updated for the state
        # file's audit history (operator inspects it via state file).
        now_utc = time.gmtime(now)
        today_utc = time.strftime("%Y-%m-%d", now_utc)

        threshold = float(self._settings.get("auto_disable_volume_threshold_usd", 10000.0))
        from config import SYMBOLS

        # Mark as run BEFORE the slow fetch — if the fetch fails we still don't
        # retry until tomorrow, and prevents the broadcast loop from firing this
        # method twice while the first call is in-flight (~5-10s for 9 exchanges).
        # We also persist immediately so a crash mid-fetch doesn't cause a re-run
        # on next start (the previous-day blocklist remains in fee_configs).
        self._last_auto_disable_run_date_utc = today_utc
        self._last_auto_disable_run_ts = time.time()
        # Clear the force-run flag now (regardless of fetch outcome) so the
        # broadcast loop doesn't reprime it next tick.
        self._auto_disable_force_run_on_start = False

        try:
            from volume_fetcher import fetch_all_24h_volumes
            volumes = await fetch_all_24h_volumes()
            # Cache for broadcast — daily run also feeds the Fee Mgmt UI
            self._cached_volumes = volumes
        except Exception as e:
            logger.exception("[AutoDisable] Volume fetch failed; skipping today's run: %s", e)
            # Persist the attempt so we don't retry today even though fetch failed.
            # Pass None for blocklist fields so the prior day's audit snapshot is
            # preserved (the live blocklist in fee_configs is also untouched).
            self._save_auto_disable_state(threshold=threshold)
            return

        # Build per-exchange lists of symbols to auto-disable. Iterates ALL
        # symbols on the exchange (not just our tracked SYMBOLS) to match
        # the manual bulk-disable button behavior.
        per_exchange_disable: dict[str, list[str]] = {}
        per_exchange_kept_count: dict[str, int] = {}
        for exchange in self._fee_manager.get_enabled_exchanges():
            ex_vols = volumes.get(exchange, {})
            disable_list: list[str] = []
            keep_count = 0
            for sym, vol in ex_vols.items():
                if vol is None:
                    continue
                if vol < threshold:
                    disable_list.append(sym)
                else:
                    keep_count += 1
            per_exchange_disable[exchange] = sorted(disable_list)
            per_exchange_kept_count[exchange] = keep_count

        # The dashboard's bound `self._fee_manager` is the super-primary /
        # default config's fee_manager (same instance). Compute its
        # blocklist from its OWN config threshold (not the global one)
        # so behavior matches every other config — and so a $10k-capital
        # super-primary correctly uses $100k threshold instead of the
        # global default $10k.
        registry = getattr(self, "_registry", None)
        default_cfg = registry.default_config if registry is not None else None
        default_threshold = float(
            default_cfg.settings.get("auto_disable_volume_threshold_usd", threshold)
            if default_cfg is not None else threshold
        )
        default_blocklist = self._build_per_exchange_disable_lists(volumes, default_threshold)
        diffs = self._fee_manager.apply_auto_disable(default_blocklist)

        # Apply per-config thresholds to every OTHER bundle.
        self._apply_auto_disable_to_other_configs(volumes, threshold)

        # Persist updated fee_configs to settings.json so the auto-block survives
        # restarts (matches manual disabled_symbols persistence behavior).
        self._settings["fee_configs"] = self._fee_manager.to_settings_dict()
        try:
            save_settings(self._settings)
        except Exception:
            logger.exception("[AutoDisable] Failed to persist fee_configs")
        # Persist registry too (per-config fee_configs were updated). The
        # default config's bundle was applied via `self._fee_manager` above
        # but `_apply_auto_disable_to_other_configs` skipped it — so its
        # registry settings were stale and `save_registry()` would write
        # an empty blocklist for the super-primary, leaving it un-blocked
        # after restart even though every other config was correctly
        # blocked. Sync it explicitly here before save.
        if registry is not None:
            try:
                if default_cfg is not None and self._fee_manager is not None:
                    default_cfg.settings["fee_configs"] = self._fee_manager.to_settings_dict()
                save_registry(registry)
            except Exception:
                logger.exception("[AutoDisable] Failed to persist registry")

        # Persist last-run timestamp + threshold + diff to state file so the
        # next bot start knows whether today's run already happened.
        self._save_auto_disable_state(threshold, per_exchange_disable, diffs)

        # Logging: one summary line, then per-exchange detail when there were changes
        total_added = sum(len(d.get("added", [])) for d in diffs.values())
        total_removed = sum(len(d.get("removed", [])) for d in diffs.values())
        total_blocked = sum(len(syms) for syms in per_exchange_disable.values())
        logger.info(
            f"[AutoDisable] Hourly run @ {time.strftime('%Y-%m-%d %H:%M:%S', now_utc)} UTC: "
            f"threshold=${threshold:,.0f}/24h, blocked={total_blocked} pairs across "
            f"{len(per_exchange_disable)} exchanges, +{total_added} added, -{total_removed} removed"
        )
        for exchange in sorted(per_exchange_disable.keys()):
            disable_list = per_exchange_disable[exchange]
            kept = per_exchange_kept_count.get(exchange, 0)
            diff = diffs.get(exchange, {})
            added = diff.get("added", [])
            removed = diff.get("removed", [])
            if added or removed:
                logger.info(
                    f"[AutoDisable]   {exchange}: blocked={len(disable_list)}/kept={kept} | "
                    f"added={added or 'none'} removed={removed or 'none'}"
                )
            else:
                # Quiet line (no change since yesterday)
                logger.info(
                    f"[AutoDisable]   {exchange}: blocked={len(disable_list)}/kept={kept} (unchanged)"
                )

    def _build_per_exchange_disable_lists(
        self, volumes: dict[str, dict[str, float]], threshold: float
    ) -> dict[str, list[str]]:
        """Compute per-exchange auto-disable lists from a volumes snapshot.

        Iterates ALL symbols on each exchange (not just our tracked SYMBOLS)
        so the auto-disable matches the manual "<$10K/24h" button behavior:
        any symbol on the exchange with vol < threshold gets blocked. This
        keeps the per-exchange `disabled_symbols` consistent with what the
        operator would produce by clicking the manual bulk-disable buttons.
        """
        out: dict[str, list[str]] = {}
        for exchange, ex_vols in volumes.items():
            disable_list: list[str] = []
            for sym, vol in ex_vols.items():
                if vol is None:
                    continue
                if vol < threshold:
                    disable_list.append(sym)
            out[exchange] = sorted(disable_list)
        return out

    def _apply_auto_disable_to_other_configs(
        self, volumes: dict[str, dict[str, float]],
        default_threshold: float,
    ) -> int:
        """Apply auto-disable to every per-config FeeManager that ISN'T
        `self._fee_manager` (already applied by caller). Each config
        computes its OWN blocklist from `volumes` using its OWN
        `auto_disable_volume_threshold_usd` — so a $10k-capital config
        can correctly use a higher threshold ($100k) than a $1k-capital
        config ($10k). Also syncs the resulting fee_manager state back
        into the registry Config.settings so `save_registry()` persists
        the per-config blocklist.

        Pre-fix #1: bundles got an in-memory blocklist update but the
        registry's stored settings kept empty `auto_disabled_symbols`,
        so a restart un-blocked everything (e.g., JUP at $205/24h on
        Bitfinex).

        Pre-fix #2: every bundle received the SAME blocklist computed
        from `self._settings`'s global threshold, ignoring per-config
        `auto_disable_volume_threshold_usd`. The high-capital configs
        (intended threshold $100k+) were getting the default $10k list,
        leaving thinly-traded pairs tradeable for them too.
        """
        orch = getattr(self, "_orchestrator", None)
        if orch is None:
            return 0
        registry = getattr(self, "_registry", None)
        n = 0
        for bundle in orch.all_bundles():
            if bundle.fee_manager is self._fee_manager:
                continue
            try:
                # Look up this config's own threshold; fall back to the
                # default if not set on the config.
                cfg = registry.find_config(bundle.config_id) if registry is not None else None
                cfg_threshold = default_threshold
                if cfg is not None:
                    cfg_threshold = float(
                        cfg.settings.get(
                            "auto_disable_volume_threshold_usd",
                            default_threshold,
                        )
                    )
                # Build this config's blocklist from the shared volumes.
                cfg_disable = self._build_per_exchange_disable_lists(volumes, cfg_threshold)
                bundle.fee_manager.apply_auto_disable(cfg_disable)
                if cfg is not None:
                    cfg.settings["fee_configs"] = bundle.fee_manager.to_settings_dict()
                n += 1
            except Exception:
                logger.exception(
                    f"[AutoDisable] apply to bundle {bundle.config_id[:8]}… failed"
                )
        return n

    def _apply_auto_disable_to_all_configs(
        self, volumes: dict[str, dict[str, float]]
    ) -> dict:
        """Apply auto-disable to every config's FeeManager based on the
        provided volumes snapshot. Returns a summary dict for the WS reply
        and logging.

        Symbols below `auto_disable_volume_threshold_usd` are added to each
        FeeManager's `auto_disabled_symbols`; symbols at/above the threshold
        are removed (re-enabled). Manual `disabled_symbols` are never touched.
        """
        # Default (dashboard's bound) FeeManager uses the global threshold
        # for backward compatibility with single-config deployments.
        default_threshold = float(self._settings.get("auto_disable_volume_threshold_usd", 10000.0))

        # Apply to default fee_manager + every per-config fee_manager.
        # Each per-config bundle uses ITS OWN
        # `auto_disable_volume_threshold_usd` so a $10k-capital config
        # with $100k threshold blocks more pairs than a $1k-capital
        # config with $10k threshold, even though both share the same
        # `volumes` snapshot.
        total_added = 0
        total_removed = 0
        configs_updated = 0
        registry = getattr(self, "_registry", None)
        orch = getattr(self, "_orchestrator", None)

        # Resolve (label, fee_manager, threshold) for each manager to apply.
        managers_with_thresholds: list[tuple[str, Any, float]] = []
        if self._fee_manager:
            managers_with_thresholds.append(("default", self._fee_manager, default_threshold))
        if orch is not None:
            for bundle in orch.all_bundles():
                if not bundle.fee_manager or bundle.fee_manager is self._fee_manager:
                    continue
                cfg_threshold = default_threshold
                if registry is not None:
                    cfg = registry.find_config(bundle.config_id)
                    if cfg is not None:
                        cfg_threshold = float(
                            cfg.settings.get(
                                "auto_disable_volume_threshold_usd",
                                default_threshold,
                            )
                        )
                managers_with_thresholds.append(
                    (bundle.config_name, bundle.fee_manager, cfg_threshold)
                )

        for label, fm, threshold in managers_with_thresholds:
            try:
                # Compute this manager's blocklist from the shared volumes
                # using its specific threshold.
                per_exchange_disable = self._build_per_exchange_disable_lists(volumes, threshold)
                diff = fm.apply_auto_disable(per_exchange_disable)
                added = sum(len(d.get("added", [])) for d in diff.values())
                removed = sum(len(d.get("removed", [])) for d in diff.values())
                total_added += added
                total_removed += removed
                if added or removed:
                    configs_updated += 1
                    logger.info(
                        f"[AutoDisable] Manual fetch → {label} "
                        f"(threshold=${threshold:,.0f}): +{added} disabled, -{removed} re-enabled"
                    )
            except Exception:
                logger.exception(f"[AutoDisable] apply to {label} failed")

        # Persist updated registry so per-config blocklists survive restart
        if getattr(self, "_registry", None):
            try:
                # Sync each bundle's fee_manager state back into its config's settings
                for bundle in orch.all_bundles() if orch else []:
                    cfg = self._registry.find_config(bundle.config_id)
                    if cfg and bundle.fee_manager:
                        cfg.settings["fee_configs"] = bundle.fee_manager.to_settings_dict()
                save_registry(self._registry)
            except Exception:
                logger.exception("[AutoDisable] Failed to persist registry")

        # Persist legacy fee_configs in settings (default config view)
        if self._fee_manager:
            self._settings["fee_configs"] = self._fee_manager.to_settings_dict()
            try:
                save_settings(self._settings)
            except Exception:
                pass

        return {
            "configs_updated": configs_updated,
            "total_added": total_added,
            "total_removed": total_removed,
            "threshold_usd": threshold,
        }

    def _check_trade_amount_rescale_triggers(self) -> None:
        """Called from the broadcast loop. Fires hourly + on discovery transitions."""
        if not self._monitor or not self._optimizer:
            return
        now = time.time()

        # Hourly tick — wait until first tick fires before starting the timer
        # (avoids firing during the 10s startup window before settings are logged).
        if self._last_trade_amount_rescale_ts == 0.0:
            self._last_trade_amount_rescale_ts = now
        elif now - self._last_trade_amount_rescale_ts >= self._trade_amount_rescale_interval:
            self._rescale_trade_amount("hourly_tick")

        # Discovery state transitions — fire once per state change
        try:
            cur_state = bool(self._optimizer._discovery_complete)
        except AttributeError:
            cur_state = None
        if cur_state is not None:
            if self._last_discovery_state is not None and cur_state != self._last_discovery_state:
                if cur_state:
                    self._rescale_trade_amount("discovery_completed")
                else:
                    self._rescale_trade_amount("discovery_started")
            self._last_discovery_state = cur_state

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

    @staticmethod
    def _filter_log_files_by_date(
        files: list[Path], pattern: re.Pattern[str], start_ts: float, end_ts: float, current_file: Path | None
    ) -> list[Path]:
        """Pre-filter rotated log files by parsing YYYY-MM-DD from filename.

        Skips files whose entire date is outside [start_ts, end_ts]. The
        currently-active log file (no date suffix) is always included.
        Reduces I/O by 80-95% for narrow ranges across 30 days of rotation.
        """
        start_day = _dt.fromtimestamp(start_ts, tz=_tz.utc).date()
        end_day = _dt.fromtimestamp(end_ts, tz=_tz.utc).date()
        kept: list[Path] = []
        for f in files:
            if current_file is not None and f == current_file:
                kept.append(f)
                continue
            m = pattern.search(f.name)
            if not m:
                # Unparseable name — keep it to be safe (better slow than wrong)
                kept.append(f)
                continue
            try:
                file_day = _dt.strptime(m.group(1), "%Y-%m-%d").date()
            except ValueError:
                kept.append(f)
                continue
            if start_day <= file_day <= end_day:
                kept.append(f)
        return kept

    _BOT_LOG_DATE_RE = re.compile(r"\.(\d{4}-\d{2}-\d{2})$")

    def _read_bot_logs_from_disk(self, start_ts: float, end_ts: float) -> list[dict]:
        """Read bot log entries from disk log files within time range.

        Pre-filters files by filename date (Fix A) so a 1-day export doesn't
        scan 30 days of rotated files.
        """
        entries: list[dict] = []
        log_dir = Path("logs")

        rotated = sorted(log_dir.glob("arbitragebot.log.*"))
        main = log_dir / "arbitragebot.log"
        all_files = rotated + ([main] if main.exists() else [])
        log_files = self._filter_log_files_by_date(
            all_files, self._BOT_LOG_DATE_RE, start_ts, end_ts, main if main.exists() else None,
        )

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

    # Chunked export: ~500 entries per chunk, gzip+base64, multi-WS-message delivery.
    # Solves three issues that broke long-session exports (S19 9-day pull):
    #   A. File pre-filter (above) — skip files outside date range
    #   B. Chunk into multiple frames so no single WS message blows the size limit
    #   C. Gzip-compress each chunk (~10× reduction on log text)
    EXPORT_CHUNK_SIZE: int = 500

    async def _send_chunked_export(self, ws: Any, kind: str, entries: list[dict]) -> None:
        """Stream large export results to a client in compressed chunks.

        Sends N messages of type `{kind}_chunk` then a final `{kind}_done`.
        Each chunk carries gzipped+base64-encoded JSON of up to EXPORT_CHUNK_SIZE entries.
        Yields control to the event loop between chunks so other clients keep getting
        broadcasts and ping-pong stays alive.
        """
        total_entries = len(entries)
        if total_entries == 0:
            try:
                await ws.send(json.dumps({
                    "type": f"{kind}_done",
                    "total_chunks": 0,
                    "total_entries": 0,
                }))
            except Exception:
                pass
            return

        chunk_size = self.EXPORT_CHUNK_SIZE
        total_chunks = (total_entries + chunk_size - 1) // chunk_size
        sent_bytes = 0
        for i in range(total_chunks):
            batch = entries[i * chunk_size : (i + 1) * chunk_size]
            raw = json.dumps(batch, separators=(",", ":")).encode("utf-8")
            compressed = gzip.compress(raw, compresslevel=6)
            payload_b64 = base64.b64encode(compressed).decode("ascii")
            sent_bytes += len(payload_b64)
            try:
                await ws.send(json.dumps({
                    "type": f"{kind}_chunk",
                    "chunk_index": i,
                    "total_chunks": total_chunks,
                    "encoding": "gzip+base64",
                    "data": payload_b64,
                }))
            except Exception as e:
                logger.warning(f"[Export] send failed at chunk {i}/{total_chunks}: {e}")
                return
            # Yield to event loop between chunks so we don't starve broadcasts/pings
            await asyncio.sleep(0)

        try:
            await ws.send(json.dumps({
                "type": f"{kind}_done",
                "total_chunks": total_chunks,
                "total_entries": total_entries,
            }))
        except Exception:
            pass
        logger.info(
            f"[Export] {kind}: sent {total_entries} entries in {total_chunks} chunks "
            f"(~{sent_bytes // 1024} KB compressed)"
        )

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

    def _apply_settings(self, settings: dict, *, log_global_dump: bool = True) -> None:
        """Apply new settings: restart discovery with updated parameters.

        `log_global_dump`: when True, ends with a `_log_all_settings(...)`
        dump using the GLOBAL `self._settings`. This makes sense for the
        legacy single-config save_settings path. When called via
        `_apply_settings_to_bundle` (per-config hot-apply), pass False —
        the per-config caller has its own `_log_one_config_settings(...)`
        dump with the correct settings, and the global dump just adds a
        misleading line tagged with the bundle's prefix that prints
        `total_capital=$1000` (the legacy global value) for every config
        regardless of the bundle's actual group capital.
        """
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

        # Update optimizer parameters — only restart discovery when scoring
        # fundamentals change (scoring_window, num_active_symbols, auto_rotate).
        # All other settings are hot-applied without wiping tick windows,
        # preserving 15+ minutes of collected scoring data.
        if self._optimizer:
            opt = self._optimizer
            opt._total_capital = total_capital
            # Hot-apply all optimizer parameters
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
            if "trade_amount_usd" in settings or "trade_amount_pct" in settings:
                opt._trade_amount = trade_amount
            if "evaluation_interval" in settings:
                opt._evaluation_interval = int(settings["evaluation_interval"])
            if "safety_multiplier" in settings:
                opt._safety_multiplier = float(settings["safety_multiplier"])
            if "auto_rotate" in settings:
                opt._auto_rotate = settings["auto_rotate"]

            # Only restart discovery if scoring fundamentals changed
            # (these affect what data the score is computed from)
            discovery_triggers = {"scoring_window", "num_active_symbols", "auto_rotate"}
            needs_discovery_restart = any(
                k in settings and settings[k] != old_settings.get(k)
                for k in discovery_triggers
            )
            if needs_discovery_restart:
                if "num_active_symbols" in settings:
                    opt._min_active_symbols = int(settings["num_active_symbols"])
                if "scoring_window" in settings:
                    opt._scoring_window = int(settings["scoring_window"])
                opt.reset(trade_amount=trade_amount)
                logger.info("[Settings] Discovery restarted (scoring fundamentals changed)")
            else:
                logger.info("[Settings] Hot-applied without discovery restart")

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
        # v0.30+: capital architecture (custody hub + trading float)
        if "custody_hub_exchange" in settings:
            self._balance._custody_hub_exchange = str(settings["custody_hub_exchange"])
        if "custody_hub_network" in settings:
            self._balance._custody_hub_network = str(settings["custody_hub_network"])
        if "trading_float_multiplier" in settings:
            self._balance._trading_float_multiplier = float(settings["trading_float_multiplier"])
            # Recompute the float target — bounded by trade size, not capital
            self._balance._bitfinex_reserve_target = (
                self._balance._trade_amount
                * self._balance._trading_float_multiplier
            )
        if "trading_float_replenish_trigger" in settings:
            self._balance._trading_float_replenish_trigger = float(
                settings["trading_float_replenish_trigger"]
            )
        if "trading_float_overflow_multiplier" in settings:
            self._balance._trading_float_overflow_multiplier = float(
                settings["trading_float_overflow_multiplier"]
            )

        # Simulation realism features
        if "spread_persistence_ticks" in settings:
            self._monitor._spread_persistence_ticks = int(settings["spread_persistence_ticks"])
        if "event_driven_seller_penalty_pct" in settings:
            self._monitor._event_driven_seller_penalty = float(settings["event_driven_seller_penalty_pct"])
            if self._optimizer:
                self._optimizer._event_driven_seller_penalty = float(settings["event_driven_seller_penalty_pct"])
        if "one_leg_failure_rate" in settings:
            self._monitor._one_leg_failure_rate = float(settings["one_leg_failure_rate"])
        if "one_leg_unwind_slippage_mult" in settings:
            self._monitor._one_leg_unwind_slippage_mult = float(settings["one_leg_unwind_slippage_mult"])
        if "max_position_multiplier" in settings:
            self._monitor._max_position_multiplier = float(settings["max_position_multiplier"])

        # Price momentum filter (Feature 3) + Periodic inventory rebalance (Feature 4)
        if self._optimizer:
            if "momentum_filter_enabled" in settings:
                self._optimizer._momentum_filter_enabled = bool(settings["momentum_filter_enabled"])
            if "momentum_lookback_hours" in settings:
                self._optimizer._momentum_lookback_seconds = float(settings["momentum_lookback_hours"]) * 3600
            if "momentum_sample_interval_minutes" in settings:
                self._optimizer._momentum_sample_interval = float(settings["momentum_sample_interval_minutes"]) * 60
            if "momentum_min_factor" in settings:
                self._optimizer._momentum_min_factor = float(settings["momentum_min_factor"])
            if "momentum_max_factor" in settings:
                self._optimizer._momentum_max_factor = float(settings["momentum_max_factor"])
            if "inventory_rebalance_enabled" in settings:
                self._optimizer._inventory_rebalance_enabled = bool(settings["inventory_rebalance_enabled"])
            if "inventory_rebalance_interval_hours" in settings:
                self._optimizer._inventory_rebalance_interval = float(settings["inventory_rebalance_interval_hours"]) * 3600
            if "inventory_drift_threshold" in settings:
                self._optimizer._inventory_drift_threshold = float(settings["inventory_drift_threshold"])
            if "bitfinex_over_target_enabled" in settings:
                self._optimizer._bitfinex_over_target_enabled = bool(settings["bitfinex_over_target_enabled"])
            if "bitfinex_over_target_multiplier" in settings:
                self._optimizer._bitfinex_over_target_multiplier = float(settings["bitfinex_over_target_multiplier"])
            if "auto_expand_on_understaff" in settings:
                self._optimizer._auto_expand_on_understaff = bool(settings["auto_expand_on_understaff"])
            if "diversification_floor_enabled" in settings:
                self._optimizer._diversification_floor_enabled = bool(settings["diversification_floor_enabled"])
            if "diversification_floor_multiplier" in settings:
                self._optimizer._diversification_floor_multiplier = float(settings["diversification_floor_multiplier"])
            if "fast_track_discovery_enabled" in settings:
                self._optimizer._fast_track_discovery_enabled = bool(settings["fast_track_discovery_enabled"])
            if "fast_track_aggressiveness" in settings:
                self._optimizer._fast_track_aggressiveness = float(settings["fast_track_aggressiveness"])
            # Time-based regime gating — mirrored to monitor + optimizer
            if "regime_gating_enabled" in settings:
                v = bool(settings["regime_gating_enabled"])
                self._optimizer._regime_gating_enabled = v
                if self._monitor:
                    self._monitor._regime_gating_enabled = v
            if "regime_strong_hours" in settings:
                hrs = {int(h) for h in settings["regime_strong_hours"] if 0 <= int(h) <= 23}
                self._optimizer._regime_strong_hours = hrs
                if self._monitor:
                    self._monitor._regime_strong_hours = hrs
            if "regime_neutral_hours" in settings:
                hrs = {int(h) for h in settings["regime_neutral_hours"] if 0 <= int(h) <= 23}
                self._optimizer._regime_neutral_hours = hrs
                if self._monitor:
                    self._monitor._regime_neutral_hours = hrs
            if "regime_weak_min_net_multiplier" in settings and self._monitor:
                self._monitor._regime_weak_min_net_multiplier = float(settings["regime_weak_min_net_multiplier"])
            if "regime_weak_disable_rebalance" in settings and self._monitor:
                self._monitor._regime_weak_disable_rebalance = bool(settings["regime_weak_disable_rebalance"])
            if "regime_weak_disable_demote" in settings:
                self._optimizer._regime_weak_disable_demote = bool(settings["regime_weak_disable_demote"])
            if "regime_weak_disable_expand" in settings:
                self._optimizer._regime_weak_disable_expand = bool(settings["regime_weak_disable_expand"])
            # Anti-churn bundle (A+B+C)
            if "demotion_freq_scaling_enabled" in settings:
                self._optimizer._demotion_freq_scaling_enabled = bool(settings["demotion_freq_scaling_enabled"])
            if "activation_profit_horizon_multiplier" in settings:
                self._optimizer._activation_profit_horizon_multiplier = float(settings["activation_profit_horizon_multiplier"])
            if "quiet_period_pause_minutes" in settings and self._monitor:
                self._monitor._quiet_period_pause_minutes = float(settings["quiet_period_pause_minutes"])

        # Funding-aware scoring (Phase A)
        if self._funding_monitor:
            fm_kwargs = {}
            if "funding_aware_scoring_enabled" in settings:
                fm_kwargs["scoring_enabled"] = bool(settings["funding_aware_scoring_enabled"])
            if "funding_skip_threshold_4h_pct" in settings:
                fm_kwargs["skip_threshold_4h_pct"] = float(settings["funding_skip_threshold_4h_pct"])
            if "funding_skip_threshold_8h_pct" in settings:
                fm_kwargs["skip_threshold_8h_pct"] = float(settings["funding_skip_threshold_8h_pct"])
            if "funding_score_min_factor" in settings:
                fm_kwargs["score_min_factor"] = float(settings["funding_score_min_factor"])
            if "funding_score_max_factor" in settings:
                fm_kwargs["score_max_factor"] = float(settings["funding_score_max_factor"])
            if fm_kwargs:
                self._funding_monitor.update_settings(**fm_kwargs)

        # Hedge manager (Phase C+)
        hm = getattr(self._monitor, "_hedge_manager", None)
        if hm is not None:
            hm_kwargs = {}
            if "hedging_enabled" in settings:
                hm_kwargs["enabled"] = bool(settings["hedging_enabled"])
            if "hedge_execution_mode" in settings:
                hm_kwargs["execution_mode"] = str(settings["hedge_execution_mode"])
            if "hedge_dust_threshold_usd" in settings:
                hm_kwargs["dust_threshold_usd"] = float(settings["hedge_dust_threshold_usd"])
            if "hedge_evaluation_interval_seconds" in settings:
                hm_kwargs["evaluation_interval_seconds"] = float(settings["hedge_evaluation_interval_seconds"])
            if "hedge_margin_buffer_pct" in settings:
                hm_kwargs["margin_buffer_pct"] = float(settings["hedge_margin_buffer_pct"])
            if "hedge_adjust_threshold_pct" in settings:
                hm_kwargs["adjust_threshold_pct"] = float(settings["hedge_adjust_threshold_pct"])
            if hm_kwargs:
                hm.update_settings(**hm_kwargs)

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
        # v0.31.0-beta+: two-layer emergency gate
        if "realized_drawdown_emergency_pct" in settings:
            anomaly._realized_dd_emergency_pct = float(settings["realized_drawdown_emergency_pct"])
        if "combined_drawdown_emergency_pct" in settings:
            anomaly._combined_dd_emergency_pct = float(settings["combined_drawdown_emergency_pct"])
        if "combined_drawdown_sustained_seconds" in settings:
            anomaly._combined_dd_sustained_s = float(settings["combined_drawdown_sustained_seconds"])
        if "emergency_auto_liquidate" in settings:
            anomaly._emergency_auto_liquidate = bool(settings["emergency_auto_liquidate"])
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

        # Log comprehensive settings snapshot with diffs.
        # Skipped in per-bundle hot-apply (multi-config) — see docstring.
        if log_global_dump:
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
        # v0.30+: capital architecture
        if "custody_hub_exchange" in settings:
            old_val = self._balance._custody_hub_exchange
            new_val = str(settings["custody_hub_exchange"])
            self._balance._custody_hub_exchange = new_val
            if old_val != new_val:
                synced.append(f"custody_hub: {old_val} -> {new_val}")
        if "custody_hub_network" in settings:
            old_val = self._balance._custody_hub_network
            new_val = str(settings["custody_hub_network"])
            self._balance._custody_hub_network = new_val
            if old_val != new_val:
                synced.append(f"custody_network: {old_val} -> {new_val}")
        if "trading_float_multiplier" in settings:
            old_val = self._balance._trading_float_multiplier
            new_val = float(settings["trading_float_multiplier"])
            self._balance._trading_float_multiplier = new_val
            self._balance._bitfinex_reserve_target = (
                self._balance._trade_amount * new_val
            )
            if old_val != new_val:
                synced.append(
                    f"trading_float_mult: {old_val:.1f}x -> {new_val:.1f}x "
                    f"(target=${self._balance._bitfinex_reserve_target:.0f})"
                )
        if "trading_float_replenish_trigger" in settings:
            old_val = self._balance._trading_float_replenish_trigger
            new_val = float(settings["trading_float_replenish_trigger"])
            self._balance._trading_float_replenish_trigger = new_val
            if old_val != new_val:
                synced.append(f"replenish_trigger: {old_val:.1f}x -> {new_val:.1f}x")
        if "trading_float_overflow_multiplier" in settings:
            old_val = self._balance._trading_float_overflow_multiplier
            new_val = float(settings["trading_float_overflow_multiplier"])
            self._balance._trading_float_overflow_multiplier = new_val
            if old_val != new_val:
                synced.append(f"overflow_mult: {old_val:.2f}x -> {new_val:.2f}x")
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
            if self._optimizer:
                self._optimizer._event_driven_seller_penalty = float(settings["event_driven_seller_penalty_pct"])
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
            # Momentum filter + inventory rebalance
            if "momentum_filter_enabled" in settings:
                self._optimizer._momentum_filter_enabled = bool(settings["momentum_filter_enabled"])
            if "momentum_lookback_hours" in settings:
                self._optimizer._momentum_lookback_seconds = float(settings["momentum_lookback_hours"]) * 3600
            if "momentum_sample_interval_minutes" in settings:
                self._optimizer._momentum_sample_interval = float(settings["momentum_sample_interval_minutes"]) * 60
            if "momentum_min_factor" in settings:
                self._optimizer._momentum_min_factor = float(settings["momentum_min_factor"])
            if "momentum_max_factor" in settings:
                self._optimizer._momentum_max_factor = float(settings["momentum_max_factor"])
            if "inventory_rebalance_enabled" in settings:
                self._optimizer._inventory_rebalance_enabled = bool(settings["inventory_rebalance_enabled"])
            if "inventory_rebalance_interval_hours" in settings:
                self._optimizer._inventory_rebalance_interval = float(settings["inventory_rebalance_interval_hours"]) * 3600
            if "inventory_drift_threshold" in settings:
                self._optimizer._inventory_drift_threshold = float(settings["inventory_drift_threshold"])
            if "bitfinex_over_target_enabled" in settings:
                self._optimizer._bitfinex_over_target_enabled = bool(settings["bitfinex_over_target_enabled"])
            if "bitfinex_over_target_multiplier" in settings:
                self._optimizer._bitfinex_over_target_multiplier = float(settings["bitfinex_over_target_multiplier"])
            if "auto_expand_on_understaff" in settings:
                self._optimizer._auto_expand_on_understaff = bool(settings["auto_expand_on_understaff"])
            if "diversification_floor_enabled" in settings:
                self._optimizer._diversification_floor_enabled = bool(settings["diversification_floor_enabled"])
            if "diversification_floor_multiplier" in settings:
                self._optimizer._diversification_floor_multiplier = float(settings["diversification_floor_multiplier"])
            if "fast_track_discovery_enabled" in settings:
                self._optimizer._fast_track_discovery_enabled = bool(settings["fast_track_discovery_enabled"])
            if "fast_track_aggressiveness" in settings:
                self._optimizer._fast_track_aggressiveness = float(settings["fast_track_aggressiveness"])
            # Time-based regime gating — mirrored to monitor + optimizer
            if "regime_gating_enabled" in settings:
                v = bool(settings["regime_gating_enabled"])
                self._optimizer._regime_gating_enabled = v
                if self._monitor:
                    self._monitor._regime_gating_enabled = v
            if "regime_strong_hours" in settings:
                hrs = {int(h) for h in settings["regime_strong_hours"] if 0 <= int(h) <= 23}
                self._optimizer._regime_strong_hours = hrs
                if self._monitor:
                    self._monitor._regime_strong_hours = hrs
            if "regime_neutral_hours" in settings:
                hrs = {int(h) for h in settings["regime_neutral_hours"] if 0 <= int(h) <= 23}
                self._optimizer._regime_neutral_hours = hrs
                if self._monitor:
                    self._monitor._regime_neutral_hours = hrs
            if "regime_weak_min_net_multiplier" in settings and self._monitor:
                self._monitor._regime_weak_min_net_multiplier = float(settings["regime_weak_min_net_multiplier"])
            if "regime_weak_disable_rebalance" in settings and self._monitor:
                self._monitor._regime_weak_disable_rebalance = bool(settings["regime_weak_disable_rebalance"])
            if "regime_weak_disable_demote" in settings:
                self._optimizer._regime_weak_disable_demote = bool(settings["regime_weak_disable_demote"])
            if "regime_weak_disable_expand" in settings:
                self._optimizer._regime_weak_disable_expand = bool(settings["regime_weak_disable_expand"])
            # Anti-churn bundle (A+B+C)
            if "demotion_freq_scaling_enabled" in settings:
                self._optimizer._demotion_freq_scaling_enabled = bool(settings["demotion_freq_scaling_enabled"])
            if "activation_profit_horizon_multiplier" in settings:
                self._optimizer._activation_profit_horizon_multiplier = float(settings["activation_profit_horizon_multiplier"])
            if "quiet_period_pause_minutes" in settings and self._monitor:
                self._monitor._quiet_period_pause_minutes = float(settings["quiet_period_pause_minutes"])

        # Funding-aware scoring (Phase A) — startup sync
        if self._funding_monitor:
            fm_kwargs = {}
            if "funding_aware_scoring_enabled" in settings:
                fm_kwargs["scoring_enabled"] = bool(settings["funding_aware_scoring_enabled"])
            if "funding_skip_threshold_4h_pct" in settings:
                fm_kwargs["skip_threshold_4h_pct"] = float(settings["funding_skip_threshold_4h_pct"])
            if "funding_skip_threshold_8h_pct" in settings:
                fm_kwargs["skip_threshold_8h_pct"] = float(settings["funding_skip_threshold_8h_pct"])
            if "funding_score_min_factor" in settings:
                fm_kwargs["score_min_factor"] = float(settings["funding_score_min_factor"])
            if "funding_score_max_factor" in settings:
                fm_kwargs["score_max_factor"] = float(settings["funding_score_max_factor"])
            if fm_kwargs:
                self._funding_monitor.update_settings(**fm_kwargs)

        # Hedge manager (Phase C+) — startup sync
        hm = getattr(self._monitor, "_hedge_manager", None)
        if hm is not None:
            hm_kwargs = {}
            if "hedging_enabled" in settings:
                hm_kwargs["enabled"] = bool(settings["hedging_enabled"])
            if "hedge_execution_mode" in settings:
                hm_kwargs["execution_mode"] = str(settings["hedge_execution_mode"])
            if "hedge_dust_threshold_usd" in settings:
                hm_kwargs["dust_threshold_usd"] = float(settings["hedge_dust_threshold_usd"])
            if "hedge_evaluation_interval_seconds" in settings:
                hm_kwargs["evaluation_interval_seconds"] = float(settings["hedge_evaluation_interval_seconds"])
            if "hedge_margin_buffer_pct" in settings:
                hm_kwargs["margin_buffer_pct"] = float(settings["hedge_margin_buffer_pct"])
            if "hedge_adjust_threshold_pct" in settings:
                hm_kwargs["adjust_threshold_pct"] = float(settings["hedge_adjust_threshold_pct"])
            if hm_kwargs:
                hm.update_settings(**hm_kwargs)

        # Anomaly protection
        anomaly = self._monitor._anomaly
        if "anomaly_protection_enabled" in settings:
            anomaly._enabled = settings["anomaly_protection_enabled"]
        if "circuit_breaker_threshold" in settings:
            anomaly._cb_threshold = float(settings["circuit_breaker_threshold"])
        if "drawdown_threshold_pct" in settings:
            anomaly._dd_threshold_pct = float(settings["drawdown_threshold_pct"])
        # v0.31.0-beta+: two-layer emergency gate
        if "realized_drawdown_emergency_pct" in settings:
            anomaly._realized_dd_emergency_pct = float(settings["realized_drawdown_emergency_pct"])
        if "combined_drawdown_emergency_pct" in settings:
            anomaly._combined_dd_emergency_pct = float(settings["combined_drawdown_emergency_pct"])
        if "combined_drawdown_sustained_seconds" in settings:
            anomaly._combined_dd_sustained_s = float(settings["combined_drawdown_sustained_seconds"])
        if "emergency_auto_liquidate" in settings:
            anomaly._emergency_auto_liquidate = bool(settings["emergency_auto_liquidate"])

        # Log sync results
        if synced:
            logger.info(f"[Settings] Startup sync: {', '.join(synced)}")
        else:
            logger.info("[Settings] Startup sync: all values match constructors")
        # Always log critical runtime values for debugging
        logger.info(
            f"[Settings] Verified: hourly_cap=${self._balance._hourly_external_transfer_cap:.2f}, "
            f"custody={self._balance._custody_hub_exchange}, "
            f"trading_float=${self._balance._bitfinex_reserve_target:.0f} "
            f"({self._balance._trading_float_multiplier:.1f}x), "
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

        # Update balance exchanges (list, preserve order). Initialize the
        # per-exchange dicts (usdt, crypto, _crypto_usd) for any newly-added
        # exchange — without this, downstream consumers like _build_state's
        # `for ex in _exchanges: self.crypto[ex]` raise KeyError the moment
        # an exchange is enabled mid-session (observed enabling Gate.io +
        # KuCoin).
        if self._balance:
            new_list = [ex for ex in fetcher_exchanges if ex in target_active]
            symbols = list(self._balance._symbols)
            for ex in new_list:
                if ex not in self._balance.usdt:
                    self._balance.usdt[ex] = 0.0
                if ex not in self._balance.crypto:
                    self._balance.crypto[ex] = {sym: 0.0 for sym in symbols}
                else:
                    # Backfill any missing symbol keys (defensive — symbols
                    # may have been added after the per-exchange dict was
                    # first created).
                    for sym in symbols:
                        self._balance.crypto[ex].setdefault(sym, 0.0)
                if hasattr(self._balance, "_crypto_usd") and ex not in self._balance._crypto_usd:
                    self._balance._crypto_usd[ex] = {sym: 0.0 for sym in symbols}
            self._balance._exchanges = new_list

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

        # Phase F: hard stop also closes all open futures hedges (fire-and-forget;
        # operator sees result via the dashboard's hedges panel within 1s).
        # Use _safe_task so any close failure is logged (Phase F follow-up to S21
        # silent-task-exception issue).
        hm = getattr(self._monitor, "_hedge_manager", None)
        hedge_close_scheduled = False
        if hm is not None:
            try:
                _safe_task(hm.close_all_for_emergency(reason="hard_stop"), "hard_stop_hedge_close")
                hedge_close_scheduled = True
            except RuntimeError:
                logger.warning("[Monitor] HARD_STOP: cannot schedule hedge close (no event loop)")

        return {
            "positions_sold": len(sells),
            "total_gross": round(total_gross, 2),
            "total_fees": round(total_fees, 4),
            "total_net": round(total_net, 2),
            "sells": sells,
            "hedge_close_scheduled": hedge_close_scheduled,
        }

    def _distribute_from_custody_hub(self) -> dict:
        """Distribute USDT from the custody hub to other active exchanges.

        v0.30+: was `_distribute_from_bitfinex`. Source is now the configured
        custody hub (default Bybit), routed via the configured custody-hub
        network (default Aptos $0). Used by the Danger Zone "Distribute USDT
        from {custody_hub}" operator button.
        """
        if not self._balance:
            return {"available": 0, "transfers": [], "strategy": "none"}
        hub = self._balance._custody_hub_exchange
        if hub not in (self._balance._exchanges or []):
            return {"available": 0, "transfers": [], "strategy": "none"}

        hub_usdt = self._balance.usdt.get(hub, 0.0)
        # Keep a small buffer on the hub (5% as a safety margin)
        reserve = hub_usdt * 0.05
        available = max(0, hub_usdt - reserve)
        if available < 10:
            return {"available": round(available, 2), "transfers": [], "strategy": "insufficient"}

        # Determine allocation strategy
        enabled_exchanges = (
            self._fee_manager.get_enabled_exchanges()
            if self._fee_manager else set(self._balance._exchanges or [])
        )
        targets = [ex for ex in enabled_exchanges if ex != hub]
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
                # Symmetric: all dominant exchanges (buyers + sellers) need USDT
                for role in ("buyers", "sellers"):
                    for ex_info in dom.get(role, []):
                        bex = ex_info[0] if isinstance(ex_info, (list, tuple)) else ex_info
                        if bex in targets:
                            w = score * (ex_info[1] if isinstance(ex_info, (list, tuple)) and len(ex_info) > 1 else 1.0)
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
            fee = self._balance._get_withdrawal_fee(hub, amount)
            self._balance.usdt[hub] -= amount
            self._balance.usdt[ex] = self._balance.usdt.get(ex, 0.0) + (amount - fee)
            if fee > 0:
                self._balance.total_transfer_fees += fee
                self._balance.total_external_transfer_fees += fee
                self._balance._record_external_fee(fee)
            transfers.append({"exchange": ex, "amount": round(amount, 2)})
            logger.info(
                f"[Capital] DISTRIBUTE {hub}→{ex}: ${amount:.2f} via "
                f"{self._balance._custody_hub_network} (fee=${fee:.4f})"
            )

        total_distributed = sum(t["amount"] for t in transfers)
        logger.info(
            f"[Capital] DISTRIBUTE_COMPLETE: ${total_distributed:.2f} from "
            f"{hub} to {len(transfers)} exchanges ({strategy})"
        )
        return {
            "available": round(available, 2),
            "distributed": round(total_distributed, 2),
            "transfers": transfers,
            "strategy": strategy,
            "source_exchange": hub,
        }

    # Backward-compat alias
    _distribute_from_bitfinex = _distribute_from_custody_hub

    def _log_all_configs_settings(self, reason: str) -> None:
        """v0.31: log every config's full settings, each wrapped in its
        own ConfigContextVar so log lines are tagged `[Group X][Config Y]`.

        Called on session start, after `config_add` / `config_clone` /
        `config_clone_group`, so the operator can grep the log file for
        a specific config's full state at any moment.
        """
        registry = getattr(self, "_registry", None)
        if registry is None:
            return
        from log_context import set_config_context, reset_config_context
        n = 0
        for cfg in registry.iter_configs():
            group = registry.find_group_for_config(cfg.id)
            if group is None:
                continue
            # Build a flat settings view: per-config settings + shared keys
            # + group capital, so the standard _log_all_settings produces
            # the same shape as the legacy single-config dump.
            flat = dict(cfg.settings)
            flat["execution_mode"] = registry.effective_execution_mode(cfg.id)
            flat["hedge_execution_mode"] = registry.effective_hedge_mode(cfg.id)
            flat["total_capital"] = group.initial_capital
            token = set_config_context(group.id, group.name, cfg.id, cfg.name)
            try:
                logger.info(
                    f"[Config] === {reason}: id={cfg.id[:8]}… "
                    f"primary={cfg.is_primary} default={cfg.is_default} "
                    f"super_primary={cfg.id == registry.super_primary_id} "
                    f"order={cfg.order} ==="
                )
                if cfg.description:
                    logger.info(f"[Config] description: {cfg.description}")
                self._log_all_settings(
                    reason=f"{reason}_per_config",
                    settings_override=flat,
                )
                n += 1
            finally:
                reset_config_context(token)
        # Summary line (untagged so it lands in Universal)
        logger.info(
            f"[Config] {reason}: dumped settings for {n} config(s) "
            f"across {len(registry.groups)} group(s)"
        )

    def _log_one_config_settings(self, config_id: str, reason: str) -> None:
        """Log a single config's full settings (tagged via ConfigContextVar)."""
        registry = getattr(self, "_registry", None)
        if registry is None:
            return
        cfg = registry.find_config(config_id)
        if cfg is None:
            return
        group = registry.find_group_for_config(config_id)
        if group is None:
            return
        from log_context import set_config_context, reset_config_context
        flat = dict(cfg.settings)
        flat["execution_mode"] = registry.effective_execution_mode(cfg.id)
        flat["hedge_execution_mode"] = registry.effective_hedge_mode(cfg.id)
        flat["total_capital"] = group.initial_capital
        token = set_config_context(group.id, group.name, cfg.id, cfg.name)
        try:
            logger.info(
                f"[Config] === {reason}: id={cfg.id[:8]}… "
                f"primary={cfg.is_primary} default={cfg.is_default} "
                f"super_primary={cfg.id == registry.super_primary_id} ==="
            )
            if cfg.description:
                logger.info(f"[Config] description: {cfg.description}")
            self._log_all_settings(
                reason=f"{reason}_per_config",
                settings_override=flat,
            )
        finally:
            reset_config_context(token)

    def _log_all_settings(
        self,
        reason: str,
        old_settings: dict | None = None,
        settings_override: dict | None = None,
    ) -> None:
        """Log comprehensive settings snapshot. Called at session start and on change.

        v0.31: when `settings_override` is supplied, logs against that dict
        instead of the dashboard-bound `self._settings`. Used by the
        multi-config logger to dump every config's full settings (each
        wrapped in its own ConfigContextVar so the logs are tagged
        `[Group X][Config Y]` automatically).
        """
        s = settings_override if settings_override is not None else self._settings
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
        boost_parts: list[str] = []
        role_parts: list[str] = []
        blocklist_parts: list[str] = []
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
            # Boost markers (only when non-default 1.0)
            buy_b = cfg.get("buyer_boost", 1.0)
            sell_b = cfg.get("seller_boost", 1.0)
            if buy_b != 1.0 or sell_b != 1.0:
                boost_parts.append(f"{short}(buy={buy_b:.1f}x,sell={sell_b:.1f}x)")
            # Role flags (only when restrictive)
            as_buy = cfg.get("as_buyer", True)
            as_sell = cfg.get("as_seller", True)
            if not as_buy or not as_sell:
                role_str = "buyer-only" if as_buy and not as_sell else "seller-only" if as_sell and not as_buy else "no-role"
                role_parts.append(f"{short}={role_str}")
            # Per-symbol blocklist
            blocked_syms = cfg.get("disabled_symbols", [])
            if blocked_syms:
                blocklist_parts.append(f"{short}=[{','.join(sorted(blocked_syms))}]")

        # Anomaly settings
        ano_enabled = s.get("anomaly_protection_enabled", True)
        cb_w = s.get("circuit_breaker_window", 900)
        cb_t = s.get("circuit_breaker_threshold", -5.0)
        cb_c = s.get("circuit_breaker_cooldown", 300)
        dd_t = s.get("drawdown_threshold_pct", 5.0)
        dd_e = s.get("drawdown_emergency_mult", 2.0)
        sls_t = s.get("symbol_loss_streak_threshold", 4)
        sls_c = s.get("symbol_loss_streak_cooldown", 300)

        # v0.30+: capital architecture
        custody_hub = s.get("custody_hub_exchange", "Bybit")
        custody_net = s.get("custody_hub_network", "Aptos")
        tf_mult = float(s.get("trading_float_multiplier", 8.0))
        tf_trigger = float(s.get("trading_float_replenish_trigger", 3.0))
        tf_overflow = float(s.get("trading_float_overflow_multiplier", 1.5))
        trade_amt_for_log = float(s.get("trade_amount_usd", 40.0))
        tf_target_dollar = trade_amt_for_log * tf_mult

        lines = [
            f"trade_amount={ta_str}",
            f"adaptive_mode={s.get('adaptive_mode', True)}, auto_rotate={s.get('auto_rotate', True)}",
            f"max_symbols={s.get('max_active_symbols', 8)}, min_symbols={s.get('num_active_symbols', 3)}, scoring_window={s.get('scoring_window', 60)}s, eval_interval={s.get('evaluation_interval', 60)}s",
            f"min_net_pct={s.get('min_net_profit_pct', 0.02):.2f}%, rebalance_cooldown={s.get('rebalance_cooldown', 30)}s, roi_horizon={s.get('rebalance_roi_horizon', 300)}s, roi_divisor={s.get('rebalance_roi_divisor', 5)}",
            f"net_pnl_gate: warmup={s.get('net_pnl_gate_warmup_trades', 10)} trades, grace={s.get('net_pnl_gate_grace_seconds', 1800)}s",
            f"net_pct_sizing={s.get('net_pct_sizing_enabled', True)}, cap={s.get('net_pct_multiplier_cap', 2.5)}",
            f"spread_persistence={s.get('spread_persistence_ticks', 1)} ticks, evd_penalty={s.get('event_driven_seller_penalty_pct', 0.05)}, one_leg_rate={s.get('one_leg_failure_rate', 0.02)}, max_pos_mult={s.get('max_position_multiplier', 5.0)}, fee_threshold_mult={s.get('fee_threshold_multiplier', 0.5)}",
            f"demotion: period={s.get('demotion_period', 900)}s, cooldown_mult={s.get('demotion_cooldown_multiplier', 5.0)}, realloc_horizon={s.get('reallocation_cost_horizon', 2)}h",
            f"thresholds: trading={s.get('trading_score_threshold', 0.01)}, strong={s.get('strong_score_threshold', 0.1)}, very_strong={s.get('very_strong_score_threshold', 0.3)}",
            f"stability: factor={s.get('score_stability_factor', 0.5)}, min_seconds={s.get('score_stability_seconds', 120)}s",
            f"anomaly: enabled={ano_enabled}, cb_window={cb_w}s, cb_threshold=${cb_t:.2f}, cb_cooldown={cb_c}s",
            f"anomaly: dd_threshold={dd_t:.1f}%, dd_emergency={dd_e:.1f}x, streak_threshold={sls_t}, streak_cooldown={sls_c}s",
            f"capital_hub: custody={custody_hub} via {custody_net}, "
            f"trading_float=Bitfinex (target=${tf_target_dollar:.0f} = trade_amount ${trade_amt_for_log:.0f} × {tf_mult:.1f}x, "
            f"replenish_trigger={tf_trigger:.1f}x, overflow={tf_overflow:.2f}x)",
            f"hourly_transfer_cap=${s.get('hourly_external_transfer_cap', 2.0):.2f}",
            f"momentum_filter: enabled={s.get('momentum_filter_enabled', True)}, lookback={s.get('momentum_lookback_hours', 24.0)}h, sample_interval={s.get('momentum_sample_interval_minutes', 60.0)}min, factor=[{s.get('momentum_min_factor', 0.3)}, {s.get('momentum_max_factor', 1.5)}]",
            f"inventory_rebalance: enabled={s.get('inventory_rebalance_enabled', True)}, interval={s.get('inventory_rebalance_interval_hours', 6.0)}h, drift_threshold={s.get('inventory_drift_threshold', 0.3)*100:.0f}%",
            f"auto_expand_on_understaff={s.get('auto_expand_on_understaff', True)}",
            f"diversification_floor: enabled={s.get('diversification_floor_enabled', True)}, "
            f"multiplier={s.get('diversification_floor_multiplier', 0.7)}x (relaxes activation threshold when understaffed)",
            f"fast_track_discovery: enabled={s.get('fast_track_discovery_enabled', True)}, "
            f"aggressiveness={s.get('fast_track_aggressiveness', 1.0)}x "
            f"(strong+rising=30s × aggr, strong+stable=60s × aggr, normal+rising=240s × aggr, normal+stable=300s × aggr)",
            f"funding_aware: enabled={s.get('funding_aware_scoring_enabled', True)}, "
            f"skip_4h={s.get('funding_skip_threshold_4h_pct', -0.05):+.4f}%, "
            f"skip_8h={s.get('funding_skip_threshold_8h_pct', -0.05):+.4f}%, "
            f"factor=[{s.get('funding_score_min_factor', 0.3):.2f}, {s.get('funding_score_max_factor', 1.5):.2f}], "
            f"poll={s.get('funding_poll_interval_seconds', 60.0):.0f}s",
            f"hedging: enabled={s.get('hedging_enabled', True)}, "
            f"mode={s.get('hedge_execution_mode', 'simulation')}, "
            f"dust=${s.get('hedge_dust_threshold_usd', 20.0):.0f}, "
            f"eval_interval={s.get('hedge_evaluation_interval_seconds', 300.0):.0f}s, "
            f"margin_buffer={s.get('hedge_margin_buffer_pct', 0.20)*100:.0f}%, "
            f"adjust_threshold={s.get('hedge_adjust_threshold_pct', 0.10)*100:.0f}%",
            f"fee_real_mode={s.get('fee_real_mode', False)}",
            f"exchanges: {' '.join(fee_parts)}",
            f"role_boosts: {' '.join(boost_parts) if boost_parts else 'all neutral (1.0x)'}",
            f"role_restrictions: {' '.join(role_parts) if role_parts else 'none (all enabled as buyer+seller)'}",
            f"symbol_blocklists: {' '.join(blocklist_parts) if blocklist_parts else 'none'}",
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
                "symbol_loss_streak_cooldown",
                "custody_hub_exchange", "custody_hub_network",
                "trading_float_multiplier", "trading_float_replenish_trigger",
                "trading_float_overflow_multiplier",
                "hourly_external_transfer_cap", "execution_mode",
                "net_pct_sizing_enabled", "net_pct_multiplier_cap",
                "fee_threshold_multiplier",
                "demotion_period", "demotion_cooldown_multiplier",
                "reallocation_cost_horizon",
                "trading_score_threshold", "strong_score_threshold",
                "very_strong_score_threshold",
                "score_stability_factor", "score_stability_seconds",
                "momentum_filter_enabled", "momentum_lookback_hours",
                "momentum_sample_interval_minutes",
                "momentum_min_factor", "momentum_max_factor",
                "inventory_rebalance_enabled",
                "inventory_rebalance_interval_hours",
                "inventory_drift_threshold",
                "bitfinex_over_target_enabled",
                "bitfinex_over_target_multiplier",
                "auto_expand_on_understaff",
                "diversification_floor_enabled",
                "diversification_floor_multiplier",
                "funding_aware_scoring_enabled",
                "funding_skip_threshold_4h_pct",
                "funding_skip_threshold_8h_pct",
                "funding_score_min_factor",
                "funding_score_max_factor",
                "funding_poll_interval_seconds",
                "hedging_enabled",
                "hedge_execution_mode",
                "hedge_dust_threshold_usd",
                "hedge_evaluation_interval_seconds",
                "hedge_margin_buffer_pct",
                "hedge_adjust_threshold_pct",
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

    def _build_hedge_state(self) -> dict[str, Any]:
        """Collect hedge state for dashboard broadcast (Phase F)."""
        hm = getattr(self._monitor, "_hedge_manager", None)
        if hm is None:
            return {}
        state = hm.get_debug_state()
        state["recent_events"] = hm.get_recent_events(limit=200)
        return state

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

    def _compute_bundle_portfolio_value(
        self,
        balance: Any,
        monitor: Any,
        hedge_manager: Any,
        prices: dict[str, float],
        fallback: float,
    ) -> tuple[float, float]:
        """Single source of truth for per-bundle portfolio value.

        Mirrors the convention used by every consumer: spot MTM via per-
        exchange prices when available, plus hedge unrealized PnL so the
        metric represents net spot+futures exposure. Returns
        (portfolio_value, hedge_pnl_usd) — both call sites need the hedge
        component for downstream display fields.
        """
        if not (balance and getattr(balance, "initialized", False)):
            return float(fallback), 0.0
        hedge_pnl_usd = 0.0
        if hedge_manager is not None:
            try:
                hedge_pnl_usd = float(
                    hedge_manager.get_debug_state().get("total_unrealized_pnl_usd", 0.0)
                )
            except Exception:
                hedge_pnl_usd = 0.0
        try:
            prices_per_exchange = monitor._get_per_exchange_prices() if monitor else None
        except Exception:
            prices_per_exchange = None
        try:
            portfolio_value = balance.get_portfolio_value(
                prices,
                hedge_pnl_usd=hedge_pnl_usd,
                prices_per_exchange=prices_per_exchange,
            )
        except Exception:
            portfolio_value = float(fallback)
        return float(portfolio_value), hedge_pnl_usd

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

        # Portfolio — single source via _compute_bundle_portfolio_value so
        # the dashboard's selected-config view and every per-config row in
        # the header stats bar resolve to the same number. Includes hedge
        # unrealized PnL (shadow preview or real testnet/live position PnL)
        # so drawdown reflects net spot+futures exposure.
        initial = self._balance._initial_investment
        portfolio_value, hedge_pnl_usd = self._compute_bundle_portfolio_value(
            self._balance,
            self._monitor,
            getattr(self._monitor, "_hedge_manager", None),
            prices,
            fallback=initial,
        )
        # Use the monitor's incremental cumulative aggregate (O(1))
        # instead of a per-tick scan over the trades deque.
        trading_pnl = self._monitor._cumulative_pnl
        transfer_fees = self._balance.total_transfer_fees

        # v0.30.1+: realized capital is what peak should ratchet against
        # (USDT + locked-in trade P&L + credited cashback - external fees).
        # This eliminates phantom drawdowns from MTM oscillation that the
        # hedge couldn't perfectly offset (S25/S26). Drawdown is still
        # measured against MTM portfolio_value — peak just doesn't include
        # MTM noise anymore.
        credited_cashback_for_peak = (
            self._fee_manager._total_credited_cashback if self._fee_manager else 0.0
        )
        realized_value = (
            self._balance.get_realized_capital(
                trading_pnl=trading_pnl,
                credited_cashback=credited_cashback_for_peak,
            )
            if self._balance.initialized else initial
        )

        # Anomaly protection: update drawdown tracking with portfolio context
        # Collect symbols with crypto exposure (for per-symbol drawdown blocking)
        crypto_symbols = set()
        if self._balance.initialized:
            for ex in self._balance._exchanges:
                for sym, qty in self._balance.crypto.get(ex, {}).items():
                    if qty > 0 and prices.get(sym, 0) > 0:
                        crypto_symbols.add(sym)
        self._monitor._anomaly.update_portfolio_value(
            portfolio_value,
            realized_value=realized_value,
            context={
                "portfolio_value": portfolio_value,
                "realized_value": realized_value,
                "mtm_offset": portfolio_value - realized_value,  # how much MTM diverges
                "active_symbols": len(active_symbols),
                "connected_exchanges": connected,
                "total_exchanges": len(active_exchanges),
                "crypto_symbols": sorted(crypto_symbols),
                "total_capital": float(getattr(self._monitor, "_total_capital", 0.0) or 0.0),
            },
        )

        # Net profit awareness: update optimizer to gate rotations when in deficit
        credited_cashback = (
            self._fee_manager._total_credited_cashback if self._fee_manager else 0.0
        )
        net_profit = trading_pnl - transfer_fees + credited_cashback
        elapsed_s = now - self._start_time if self._start_time else 0
        # Same warmup gate as monitor.get_net_profit_stats — without it, a tiny
        # setup-time fee divided by a sub-second elapsed window produces a
        # huge phantom $/hr that doesn't match the displayed Net Total.
        WARMUP_SECONDS = 300.0
        if len(self._monitor._trades) == 0 or elapsed_s < WARMUP_SECONDS:
            session_hourly_rate = 0.0
        else:
            session_hourly_rate = net_profit / (elapsed_s / 3600)
        # For optimizer gating: use external-only fees (internal rebalances are cheap)
        external_fees = self._balance.total_external_transfer_fees
        net_profit_gating = trading_pnl - external_fees + credited_cashback
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

        # Recent trades (last 100, newest first). `_trades` is a
        # bounded deque; deque doesn't support `[-100:]` slicing, so
        # convert to list once.
        recent_trades = []
        for t in reversed(list(self._monitor._trades)[-100:]):
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

        # Adaptive trade size stats — _trades is a deque, must convert
        # to list before slicing.
        recent_trades_list = list(self._monitor._trades)[-100:] if self._monitor._trades else []
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
                "trades_per_minute": round(trades_per_min, 2),
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
            "custody_hub_exchange": self._balance._custody_hub_exchange if self._balance else "Bybit",
            "custody_hub_network": self._balance._custody_hub_network if self._balance else "Aptos",
            **(self._monitor._anomaly.to_broadcast_dict()),
            "all_exchanges": ALL_EXCHANGES,
            "all_symbols": SYMBOLS,
            "optimizer": self._build_optimizer_state(),
            "hedges": self._build_hedge_state(),
            "funding_rates": (
                self._funding_monitor.get_all_rates() if self._funding_monitor else {}
            ),
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
            "auto_disable_state": {
                "last_run_date_utc": self._last_auto_disable_run_date_utc,
                "last_run_ts": self._last_auto_disable_run_ts,
                "last_manual_fetch_ts": self._last_manual_volumes_fetch_ts,
                "threshold_used_usd": float(
                    self._settings.get("auto_disable_volume_threshold_usd", 10000.0)
                ),
                "enabled": bool(self._settings.get("auto_disable_volume_enabled", True)),
                # Cached volumes from the last fetch (manual or daily cron) —
                # included so the Fee Management UI keeps the per-symbol
                # blocklist data after a page refresh.
                "cached_volumes": self._cached_volumes,
            },
            # Multi-config (v0.31.0-beta): registry tree + per-config lite
            # summaries + capacity stats. Heavy slice (rankings/trades/etc.)
            # is the rest of this dict, scoped to the currently-selected
            # config (whose components self._monitor/optimizer/etc. point to).
            **self._build_multi_config_payload(),
        }

    def _build_multi_config_payload(self) -> dict[str, Any]:
        """v0.31.0-beta: registry tree + per-config lite summaries + capacity.

        Always included in every broadcast. The frontend renders the header
        rows, ConfigSwitcher tree, and capacity banner from this data, while
        the heavy state (rankings, trades, balances, etc.) reflects the
        currently-selected config (set via `select_config` WS message).
        """
        registry = getattr(self, "_registry", None)
        orch = getattr(self, "_orchestrator", None)
        if registry is None or orch is None:
            return {}

        # Registry tree (groups + configs metadata; no settings blobs)
        groups_dict: list[dict[str, Any]] = []
        for g in sorted(registry.groups, key=lambda x: x.order):
            groups_dict.append({
                "id": g.id,
                "name": g.name,
                "initial_capital": g.initial_capital,
                "order": g.order,
                "configs": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "description": c.description,
                        "is_primary": c.is_primary,
                        "is_default": c.is_default,
                        "is_super_primary": (c.id == registry.super_primary_id),
                        "order": c.order,
                    }
                    for c in sorted(g.configs, key=lambda x: x.order)
                ],
            })

        # Build a global flat prices dict ONCE so each per-config
        # `get_portfolio_value` can MTM-mark crypto correctly. Without prices,
        # crypto held on the books is valued at $0 and configs all show the
        # same USDT-only value (looks "shared" — see v0.31 user feedback).
        global_prices: dict[str, float] = {}
        for fetcher in self._fetchers:
            try:
                state = fetcher.get_state()
            except Exception:
                continue
            for sym, ps in state.items():
                if ps and ps.bid:
                    try:
                        bid_f = float(ps.bid)
                        if bid_f > 0 and sym not in global_prices:
                            global_prices[sym] = bid_f
                    except (ValueError, TypeError):
                        continue

        # Per-config lite summaries
        configs_lite: list[dict[str, Any]] = []
        for bundle in orch.all_bundles():
            # Read names + flags LIVE from the registry — bundle.config_name
            # is captured at build time and would go stale on rename.
            cfg = registry.find_config(bundle.config_id)
            group = registry.find_group_for_config(bundle.config_id)
            if cfg is None or group is None:
                continue
            # Pre-discovery, BalanceTracker.initialize_crypto() hasn't
            # converted USD allocations into crypto quantities yet, so the
            # helper falls back to _initial_investment so the user sees the
            # group capital they configured. Same helper as _build_state to
            # guarantee the dashboard's selected-config view and this row
            # resolve to the same number (single source of truth).
            fallback = float(
                getattr(bundle.balance, "_initial_investment", 0.0)
                or group.initial_capital
            )
            portfolio_value, bundle_hedge_pnl = self._compute_bundle_portfolio_value(
                bundle.balance,
                bundle.monitor,
                bundle.hedge_manager,
                global_prices,
                fallback=fallback,
            )
            try:
                profit_stats = bundle.monitor.get_net_profit_stats()
                net_pnl = float(profit_stats.get("net_profit", 0.0))
                hourly_rate = float(profit_stats.get("hourly_rate", 0.0))
                session_hourly_rate = float(profit_stats.get("session_hourly_rate", hourly_rate))
                trading_pnl = float(profit_stats.get("trading_pnl", 0.0))
                transfer_fees = float(profit_stats.get("transfer_fees", 0.0))
                credited_cashback = float(profit_stats.get("credited_cashback", 0.0))
            except Exception:
                net_pnl = 0.0
                hourly_rate = 0.0
                session_hourly_rate = 0.0
                trading_pnl = 0.0
                transfer_fees = 0.0
                credited_cashback = 0.0
            # Per-config deficit gate: update each bundle's optimizer with
            # its OWN rotation_budget_ok state. Pre-fix this was only
            # called on the dashboard's bound config (the selected one),
            # so the 53 non-selected configs traded as if always profitable
            # — defeating the whole point of the deficit-protection logic
            # at multi-config scale. Now every config maintains its own
            # rotation budget state correctly.
            try:
                bundle_external_fees = (
                    bundle.balance.total_external_transfer_fees
                    if bundle.balance else 0.0
                )
                # Same external-only-fees gating semantics as the legacy path
                bundle_net_for_gating = trading_pnl - bundle_external_fees + credited_cashback
                bundle_start_t = float(getattr(bundle.monitor, "_start_time", 0.0) or 0.0)
                bundle_elapsed = (time.time() - bundle_start_t) if bundle_start_t > 0 else 0.0
                bundle_grace_s = float(getattr(bundle.monitor, "_net_pnl_gate_grace_seconds", 1800))
                bundle_grace_active = bundle_elapsed < bundle_grace_s
                bundle.optimizer.update_profit_state(
                    bundle_net_for_gating,
                    session_hourly_rate,
                    bundle_grace_active,
                )
            except Exception:
                pass

            # Per-config anomaly portfolio update. Pre-fix this only ran
            # for the selected config — the other 53 had no drawdown
            # peak ratcheting, no Layer A/B gate evaluation, no per-symbol
            # drawdown blocks. Effectively zero anomaly protection for
            # non-selected configs. Each bundle's anomaly now sees its
            # own portfolio_value every broadcast tick.
            try:
                # Compute realized capital for THIS bundle (not the selected one)
                bundle_credited_cb = (
                    bundle.fee_manager._total_credited_cashback if bundle.fee_manager else 0.0
                )
                bundle_realized = (
                    bundle.balance.get_realized_capital(
                        trading_pnl=trading_pnl,
                        credited_cashback=bundle_credited_cb,
                    )
                    if bundle.balance and bundle.balance.initialized
                    else float(group.initial_capital)
                )
                # Crypto-symbols set for the per-symbol drawdown block path
                bundle_crypto_syms: set[str] = set()
                if bundle.balance and bundle.balance.initialized:
                    for ex in bundle.balance._exchanges:
                        for sym, qty in bundle.balance.crypto.get(ex, {}).items():
                            if qty > 0 and global_prices.get(sym, 0) > 0:
                                bundle_crypto_syms.add(sym)
                bundle.monitor._anomaly.update_portfolio_value(
                    portfolio_value,
                    realized_value=bundle_realized,
                    context={
                        "portfolio_value": portfolio_value,
                        "realized_value": bundle_realized,
                        "mtm_offset": portfolio_value - bundle_realized,
                        "active_symbols": len(bundle.optimizer._active_symbols)
                        if bundle.optimizer else 0,
                        "crypto_symbols": sorted(bundle_crypto_syms),
                    },
                )
            except Exception:
                pass

            # Per-config trade_amount rescale. Pre-fix only the selected
            # config's trade_amount auto-scaled with capital — non-selected
            # configs stayed locked at startup-time trade_amount even when
            # their portfolio doubled. For "Maximize Profits" configs that
            # rely on trade_amount_pct, this defeated the entire feature.
            try:
                bundle_pct = float(cfg.settings.get("trade_amount_pct", 0.0))
                if bundle_pct > 0 and bundle.balance and bundle.balance.initialized:
                    new_amt = round(portfolio_value * bundle_pct, 2)
                    cur_amt = float(bundle.monitor._trade_amount)
                    if new_amt > 0 and abs(new_amt - cur_amt) > 0.01:
                        bundle.monitor._trade_amount = new_amt
                        if bundle.optimizer:
                            bundle.optimizer._trade_amount = new_amt
            except Exception:
                pass
            try:
                drawdown_pct = float(getattr(bundle.monitor._anomaly, "_current_drawdown_pct", 0.0))
            except Exception:
                drawdown_pct = 0.0
            initial_capital = float(group.initial_capital)
            # Trades-per-minute, transfers, skipped — same fields as the
            # global Stats bar (computed from per-config monitor + balance)
            try:
                total_trades = len(bundle.monitor._trades)
                start_t = float(getattr(bundle.monitor, "_start_time", 0.0) or 0.0)
                if start_t > 0:
                    elapsed_min = max(1e-6, (time.time() - start_t) / 60.0)
                    # 2-decimal precision so low-activity configs (e.g.,
                    # 1 trade per ~30 min) don't all round down to 0.0
                    trades_per_minute = round(total_trades / elapsed_min, 2)
                else:
                    trades_per_minute = 0.0
                total_transfers = len(bundle.balance.transfers)
                skipped_trades = int(getattr(bundle.balance, "skipped_trades", 0))
            except Exception:
                total_trades = len(bundle.monitor._trades)
                trades_per_minute = 0.0
                total_transfers = len(bundle.balance.transfers)
                skipped_trades = 0
            # Hedge state from the bundle's hedge manager
            try:
                hm_state = bundle.hedge_manager.get_debug_state() if bundle.hedge_manager else {}
                hedge_enabled = bool(hm_state.get("enabled", False))
                hedge_open_count = int(hm_state.get("open_count", 0))
                hedge_total_notional_usd = float(hm_state.get("total_notional_usd", 0.0))
                hedge_total_unrealized_pnl_usd = float(hm_state.get("total_unrealized_pnl_usd", 0.0))
                hedge_cumulative_funding_usd = float(hm_state.get("cumulative_funding_usd", 0.0))
                hedge_executor_errors = int(hm_state.get("total_executor_errors", 0))
                hedge_safety_paused = bool(hm_state.get("safety_paused", False))
            except Exception:
                hedge_enabled = False
                hedge_open_count = 0
                hedge_total_notional_usd = 0.0
                hedge_total_unrealized_pnl_usd = 0.0
                hedge_cumulative_funding_usd = 0.0
                hedge_executor_errors = 0
                hedge_safety_paused = False
            configs_lite.append({
                "id": bundle.config_id,
                "group_id": bundle.group_id,
                "name": cfg.name,            # live from registry
                "group_name": group.name,    # live from registry
                "is_primary": cfg.is_primary,
                "is_default": cfg.is_default,
                "is_super_primary": (bundle.config_id == registry.super_primary_id),
                "execution_mode": bundle.execution_mode,
                "hedge_mode": bundle.hedge_mode,
                "portfolio_value": float(portfolio_value),
                "initial_capital": initial_capital,
                "net_pnl": net_pnl,
                "hourly_rate": hourly_rate,
                "session_hourly_rate": session_hourly_rate,
                "drawdown_pct": drawdown_pct,
                "trades_count": total_trades,
                "trades_per_minute": trades_per_minute,
                "total_transfers": total_transfers,
                "skipped_trades": skipped_trades,
                "trading_pnl": trading_pnl,
                "transfer_fees": transfer_fees,
                "credited_cashback": credited_cashback,
                "hedge_enabled": hedge_enabled,
                "hedge_open_count": hedge_open_count,
                "hedge_total_notional_usd": hedge_total_notional_usd,
                "hedge_total_unrealized_pnl_usd": hedge_total_unrealized_pnl_usd,
                "hedge_cumulative_funding_usd": hedge_cumulative_funding_usd,
                "hedge_executor_errors": hedge_executor_errors,
                "hedge_safety_paused": hedge_safety_paused,
                "anomaly_paused": bool(getattr(bundle.monitor, "_anomaly_paused", False)),
                "manual_stopped": bool(getattr(bundle.monitor, "_manual_stopped", False)),
            })

        cap = orch.capacity_snapshot()
        capacity = {
            "avg_sweep_ms": cap.avg_sweep_ms,
            "p95_sweep_ms": cap.p95_sweep_ms,
            "last_sweep_ms": cap.last_sweep_ms,
            "config_count": cap.config_count,
            "over_budget": cap.over_budget,
            "severity": cap.severity,
            "budget_ms": cap.budget_ms,
        }

        # Per-config anomaly state — full snapshot for the AnomalyDetailsModal
        # to show severity-grouped details across every config.
        configs_anomaly: list[dict[str, Any]] = []
        for bundle in orch.all_bundles():
            cfg = registry.find_config(bundle.config_id)
            group = registry.find_group_for_config(bundle.config_id)
            if cfg is None or group is None:
                continue
            try:
                ano = bundle.monitor._anomaly
                ano_dict = ano.to_broadcast_dict().get("anomaly_protection", {})
            except Exception:
                ano_dict = {}
            configs_anomaly.append({
                "config_id": bundle.config_id,
                "group_id": bundle.group_id,
                "name": cfg.name,
                "group_name": group.name,
                "is_super_primary": (bundle.config_id == registry.super_primary_id),
                "is_primary": cfg.is_primary,
                "is_default": cfg.is_default,
                "manual_stopped": bool(getattr(bundle.monitor, "_manual_stopped", False)),
                **ano_dict,
            })

        return {
            "registry": {
                "groups": groups_dict,
                "super_primary_config_id": registry.super_primary_id,
                "default_config_id": registry.default_config.id if registry.default_config else None,
                "shared": {
                    "execution_mode": registry.shared.get("execution_mode", "simulation"),
                    "hedge_execution_mode": registry.shared.get(
                        "hedge_execution_mode", "simulation"
                    ),
                },
            },
            "configs_lite": configs_lite,
            "configs_anomaly": configs_anomaly,
            "selected_config_id": getattr(self, "_selected_config_id", None)
                or (registry.default_config.id if registry.default_config else None),
            "capacity": capacity,
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

        recent = list(monitor._trades)[-100:] if monitor._trades else []
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
