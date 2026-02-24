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
from pathlib import Path
from typing import TYPE_CHECKING, Any

import websockets

from config import (
    ALL_EXCHANGES,
    DASHBOARD_PASSWORD,
    DASHBOARD_USERNAME,
    DASHBOARD_WS_PORT,
    RECAPTCHA_SECRET_KEY,
    RECAPTCHA_SITE_KEY,
    SYMBOLS,
    USDT_WITHDRAWAL_FEES,
)
from email_notifier import notify_blocked, notify_login
from settings import save_settings

if TYPE_CHECKING:
    from balance import BalanceTracker
    from fetchers.base import BaseFetcher
    from monitor import ArbitrageMonitor
    from optimizer import SymbolOptimizer

logger = logging.getLogger(__name__)


class DashboardServer:
    """WebSocket server that broadcasts live state to dashboard clients."""

    def __init__(
        self,
        monitor: "ArbitrageMonitor",
        balance: "BalanceTracker",
        fetchers: list["BaseFetcher"],
        settings: dict | None = None,
        optimizer: "SymbolOptimizer | None" = None,
    ) -> None:
        self._monitor = monitor
        self._balance = balance
        self._fetchers = fetchers
        self._settings = settings or {}
        self._optimizer = optimizer
        if optimizer:
            optimizer.set_dashboard(self)
        self._running = False
        self._clients: set[Any] = set()
        self._start_time = 0.0

        # Auth state
        self._sessions: dict[str, dict] = {}  # token -> {ip, last_seen, remember}
        self._failed_attempts: dict[str, list[float]] = {}  # IP -> failure timestamps
        self._blocked_ips: dict[str, float] = {}  # IP -> block_expires_at
        self._max_attempts = 10
        self._block_duration = 3600.0  # 1 hour
        self._session_expiry = 86400.0  # 24h for non-remember sessions
        self._last_cleanup = 0.0
        self._captcha_threshold = 3  # require CAPTCHA after this many failures

        # Auth events (for Auth Log page)
        self._auth_events: list[dict] = []
        self._max_auth_events = 500

        # Auth logger
        self._auth_logger = self._setup_auth_logger()

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

    # --- Rate limiting ---

    def _check_rate_limit(self, ip: str) -> tuple[bool, int, int]:
        """Check if IP is rate limited. Returns (blocked, remaining, retry_after_s)."""
        now = time.time()
        if ip in self._blocked_ips:
            expires = self._blocked_ips[ip]
            if now < expires:
                return True, 0, int(expires - now)
            del self._blocked_ips[ip]
            self._failed_attempts.pop(ip, None)

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
            self._auth_logger.warning(f"{ip} - Blocked for {int(self._block_duration)}s after {self._max_attempts} failed attempts")
        return remaining

    # --- Session management ---

    def _create_session(self, ip: str, remember: bool = False) -> str:
        """Create a new session token."""
        token = secrets.token_hex(32)
        self._sessions[token] = {
            "ip": ip,
            "last_seen": time.time(),
            "remember": remember,
        }
        return token

    def _validate_session(self, token: str) -> bool:
        """Validate a session token. Returns True if valid."""
        if token not in self._sessions:
            return False
        session = self._sessions[token]
        now = time.time()
        if not session["remember"] and now - session["last_seen"] > self._session_expiry:
            del self._sessions[token]
            return False
        session["last_seen"] = now
        return True

    def _invalidate_session(self, token: str) -> None:
        """Remove a session token (logout)."""
        self._sessions.pop(token, None)

    def _cleanup_auth(self) -> None:
        """Prune expired sessions and stale rate limit entries."""
        now = time.time()
        expired_blocks = [ip for ip, exp in self._blocked_ips.items() if now >= exp]
        for ip in expired_blocks:
            del self._blocked_ips[ip]
        empty = [ip for ip, a in self._failed_attempts.items() if not a]
        for ip in empty:
            del self._failed_attempts[ip]
        expired_sessions = [
            t for t, s in self._sessions.items()
            if not s["remember"] and now - s["last_seen"] > self._session_expiry
        ]
        for t in expired_sessions:
            del self._sessions[t]

    # --- IP whitelist ---

    def _check_ip_whitelist(self, ip: str) -> bool:
        """Check if IP is allowed. Returns True if allowed."""
        if not self._settings.get("ip_whitelist_enabled", False):
            return True
        whitelist = self._settings.get("ip_whitelist", [])
        if not whitelist:
            return True  # empty whitelist = allow all
        return ip in whitelist

    # --- Auth events ---

    def _record_auth_event(
        self, event: str, ip: str, username: str = "",
        browser: str = "", os_info: str = "", details: str = "",
    ) -> None:
        """Record an authentication event for the Auth Log page."""
        self._auth_events.append({
            "timestamp": time.time(),
            "event": event,
            "ip": ip,
            "username": username,
            "browser": browser,
            "os": os_info,
            "details": details,
        })
        if len(self._auth_events) > self._max_auth_events:
            self._auth_events = self._auth_events[-self._max_auth_events:]

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

    async def run(self) -> None:
        """Start WebSocket server and broadcast state every second."""
        self._running = True
        self._start_time = time.time()

        async with websockets.serve(
            self._handle_client,
            "0.0.0.0",
            DASHBOARD_WS_PORT,
            ping_interval=20,
            ping_timeout=60,
        ):
            logger.info(
                f"[Dashboard] WebSocket server started on ws://localhost:{DASHBOARD_WS_PORT}"
            )
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
                # Periodic auth cleanup (~every 5 min)
                now = time.time()
                if now - self._last_cleanup > 300:
                    self._cleanup_auth()
                    self._last_cleanup = now
                await asyncio.sleep(1.0)

        logger.info("[Dashboard] WebSocket server stopped")

    async def _handle_client(self, ws: Any) -> None:
        """Handle a new WebSocket client connection with authentication."""
        ip = ws.remote_address[0] if ws.remote_address else "unknown"
        # websockets 13+: ws.request.headers; older: ws.request_headers
        if hasattr(ws, "request") and hasattr(ws.request, "headers"):
            ua = ws.request.headers.get("User-Agent", "")
        elif hasattr(ws, "request_headers"):
            ua = ws.request_headers.get("User-Agent", "")
        else:
            ua = ""
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
                            await ws.send(json.dumps({
                                "type": "auth_failed",
                                "reason": "Please complete the CAPTCHA",
                                "captcha_required": True,
                                "captcha_site_key": RECAPTCHA_SITE_KEY,
                            }))
                            continue
                        if not await self._verify_recaptcha(captcha_token, ip):
                            await ws.send(json.dumps({
                                "type": "auth_failed",
                                "reason": "CAPTCHA verification failed. Please try again.",
                                "captcha_required": True,
                                "captcha_site_key": RECAPTCHA_SITE_KEY,
                            }))
                            continue

                    if username == DASHBOARD_USERNAME and password == DASHBOARD_PASSWORD:
                        authenticated = True
                        session_token = self._create_session(ip, remember)
                        self._failed_attempts.pop(ip, None)
                        await ws.send(json.dumps({"type": "auth_ok", "token": session_token}))
                        self._clients.add(ws)
                        await ws.send(json.dumps(self._build_state()))
                        self._auth_logger.info(f"{ip} - Login successful ({username}, remember={remember})")
                        self._record_auth_event(
                            "login_success", ip, username=username,
                            browser=browser, os_info=os_info, details=f"remember={remember}",
                        )
                        # Fire-and-forget email notification
                        asyncio.create_task(notify_login(ip, browser, os_info))
                    else:
                        remaining = self._record_failed_attempt(ip)
                        self._auth_logger.warning(f"{ip} - Login failed (user={username}, {remaining} attempts remaining)")
                        self._record_auth_event(
                            "login_failed", ip, username=username,
                            browser=browser, os_info=os_info, details=f"{remaining} attempts remaining",
                        )

                        if remaining <= 0:
                            self._record_auth_event("blocked", ip, username=username, browser=browser, os_info=os_info, details="10 failed attempts")
                            # Fire-and-forget email notification
                            asyncio.create_task(notify_blocked(ip, browser, os_info))
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
            if authenticated:
                logger.info(f"[Dashboard] Client {ip} disconnected ({len(self._clients)} total)")

    async def _handle_message(self, msg: dict, ws: Any) -> None:
        """Process an incoming message from the dashboard."""
        msg_type = msg.get("type", "")

        if msg_type == "get_settings":
            await ws.send(json.dumps({"type": "settings", "settings": self._settings}))

        elif msg_type == "save_settings":
            new_settings = msg.get("settings", {})
            self._settings = new_settings
            save_settings(new_settings)
            await ws.send(json.dumps({"type": "settings_saved", "ok": True}))
            logger.info("[Dashboard] Settings saved to file")

        elif msg_type == "apply_settings":
            new_settings = msg.get("settings", {})
            self._settings = new_settings
            save_settings(new_settings)
            self._apply_settings(new_settings)
            await ws.send(json.dumps({"type": "settings_applied", "ok": True}))
            logger.info("[Dashboard] Settings applied and simulation reset")

        elif msg_type == "save_security_settings":
            security = msg.get("settings", {})
            if "ip_whitelist_enabled" in security:
                self._settings["ip_whitelist_enabled"] = security["ip_whitelist_enabled"]
            if "ip_whitelist" in security:
                self._settings["ip_whitelist"] = security["ip_whitelist"]
            save_settings(self._settings)
            await ws.send(json.dumps({"type": "security_settings_saved", "ok": True}))
            logger.info("[Dashboard] Security settings saved")

    def _apply_settings(self, settings: dict) -> None:
        """Apply new settings: restart discovery with updated parameters."""
        trade_amount = settings.get("trade_amount_usd", self._monitor._trade_amount)
        total_capital = settings.get("total_capital", 1800.0)

        # Reset optimizer if present — triggers new discovery
        if self._optimizer:
            opt = self._optimizer
            opt._total_capital = total_capital
            # Update Phase 2-4 parameters directly (not in reset())
            if "max_active_symbols" in settings:
                opt._max_active_symbols = max(settings["max_active_symbols"], settings.get("num_active_symbols", opt._min_active_symbols))
            if "min_rebalance_score" in settings:
                opt._min_rebalance_score = settings["min_rebalance_score"]
            if "confirmation_period" in settings:
                opt._confirmation_period = settings["confirmation_period"]
            if "promotion_threshold" in settings:
                opt._promotion_threshold = settings["promotion_threshold"]
            if "demotion_threshold" in settings:
                opt._demotion_threshold = settings["demotion_threshold"]
            if "demotion_period" in settings:
                opt._demotion_period = settings["demotion_period"]
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
            self._monitor._min_net_profit_pct = settings["min_net_profit_pct"]
        if "rebalance_roi_horizon" in settings:
            self._monitor._rebalance_roi_horizon = settings["rebalance_roi_horizon"]
        self._monitor._total_capital = total_capital

        # Adaptive mode
        if "adaptive_mode" in settings:
            self._monitor._adaptive_mode = settings["adaptive_mode"]
            self._balance._adaptive_mode = settings["adaptive_mode"]

        # Update balance cooldown and trade amount
        if "rebalance_cooldown" in settings:
            self._balance._rebalance_cooldown = settings["rebalance_cooldown"]
        self._balance._trade_amount = trade_amount
        self._balance._max_rebalance = trade_amount * 4

        # Record config snapshot
        self._monitor.record_config_snapshot("settings_applied")

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
        prices = self._get_prices(active_exchanges, active_symbols)

        # Connection status
        active_set = set(active_exchanges)
        connected = sum(
            1
            for f in self._fetchers
            if f._ws_connected and f.exchange_name in active_set
        )

        # Portfolio
        portfolio_value = self._balance.get_portfolio_value(prices) if self._balance.initialized else 0.0
        initial = self._balance._initial_investment
        trading_pnl = sum(t.profit_usd for t in self._monitor._trades)
        transfer_fees = self._balance.total_transfer_fees

        # Net profit awareness: update optimizer to gate rotations when in deficit
        net_profit = trading_pnl - transfer_fees
        elapsed_hours = max((now - self._start_time) / 3600, 1 / 3600)
        session_hourly_rate = net_profit / elapsed_hours
        if self._optimizer:
            self._optimizer.update_profit_state(net_profit, session_hourly_rate)

        # Balances per exchange
        balances: dict[str, Any] = {}
        for ex in active_exchanges:
            usdt = self._balance.usdt[ex]
            crypto_data: dict[str, Any] = {}
            ex_total = usdt
            for sym in active_symbols:
                qty = self._balance.crypto[ex].get(sym, 0.0)
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
            recent_trades.append({
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
            })

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

        return {
            "timestamp": now,
            "uptime_seconds": round(now - self._start_time, 0),
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
            "settings": self._settings,
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
        }

    def _build_adaptive_config(self) -> dict[str, Any]:
        """Current adaptive configuration decisions."""
        monitor = self._monitor
        balance = self._balance

        # Per-exchange transfer worthiness
        exchange_transfer_status: dict[str, Any] = {}
        for ex in balance._exchanges:
            fee = USDT_WITHDRAWAL_FEES.get(ex, 1.0)
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
