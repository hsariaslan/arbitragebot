"""
Pionex Spot WebSocket fetcher.

Connects to Pionex WebSocket API and streams real-time order book data
for all configured symbols using the DEPTH topic for bid/ask prices
and the TRADE topic for last traded price.

Pionex DEPTH fields:
    bids = [[price, size], ...] sorted by price descending
    asks = [[price, size], ...] sorted by price ascending
    We use bids[0] / asks[0] for best bid/ask.

Pionex TRADE fields:
    price = last trade price
    size  = trade size
    side  = BUY or SELL

Connection notes:
    - Subscription is done post-connect via JSON messages
    - Symbol format: BTC_USDT (underscore-separated, uppercase)
    - Server sends {"op": "PING"} every 15s, client must reply {"op": "PONG"}
    - Max 10 WebSocket connections per IP
    - Undocumented topic limit per connection — use multiple connections
    - Public endpoint: wss://ws.pionex.com/wsPub
"""

import asyncio
import json
import logging
import time
from typing import Any

import websockets

from config import (
    PIONEX_EXCHANGE_NAME,
    PIONEX_WS_URL,
    RECONNECT_BACKOFF_FACTOR,
    RECONNECT_INITIAL_DELAY,
    RECONNECT_MAX_DELAY,
)
from fetchers.base import BaseFetcher, PriceState

logger = logging.getLogger(__name__)

# Max subscriptions per connection (DEPTH + TRADE = 2 topics per symbol)
# Pionex has an undocumented limit; 20 symbols × 2 topics = 40 is safe
_MAX_SYMBOLS_PER_CONN = 20


class PionexFetcher(BaseFetcher):
    """Pionex Spot WebSocket fetcher using DEPTH + TRADE topics.

    Splits symbols across multiple connections to stay within
    Pionex's undocumented per-connection topic limit.
    """

    def __init__(self, symbols: list[str] | None = None) -> None:
        super().__init__(symbols)
        # Track last trade prices per symbol (TRADE topic updates these)
        self._last_prices: dict[str, str] = {}
        # Symbols confirmed unavailable on Pionex (skip on reconnect)
        self._invalid_symbols: set[str] = set()

    @property
    def exchange_name(self) -> str:
        return PIONEX_EXCHANGE_NAME

    def _build_ws_url(self) -> str:
        return PIONEX_WS_URL

    @staticmethod
    def _to_pionex_symbol(symbol: str) -> str:
        """Convert BTCUSDT -> BTC_USDT."""
        if symbol.endswith("USDT"):
            return f"{symbol[:-4]}_USDT"
        return symbol

    @staticmethod
    def _from_pionex_symbol(pionex_symbol: str) -> str:
        """Convert BTC_USDT -> BTCUSDT."""
        return pionex_symbol.replace("_", "")

    async def _on_connect(self, ws: Any) -> None:
        """Not used — multi-connection run() handles subscription."""

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Disable library-level ping; Pionex uses application-level JSON ping."""
        return {
            "ping_interval": None,
            "ping_timeout": None,
            "close_timeout": 10,
            "max_size": 2**20,
        }

    def _parse_message(self, raw_message: dict[str, Any]) -> tuple[str, PriceState] | None:
        """
        Parse Pionex DEPTH or TRADE push messages.

        DEPTH format:
            {"topic": "DEPTH", "symbol": "BTC_USDT", "timestamp": ...,
             "data": {"bids": [["price", "size"], ...],
                      "asks": [["price", "size"], ...]}}

        TRADE format:
            {"topic": "TRADE", "symbol": "BTC_USDT", "timestamp": ...,
             "data": [{"price": "...", "size": "...", "side": "BUY", "timestamp": ...}]}
        """
        # Handle server PING
        op = raw_message.get("op", "")
        if op == "PING":
            return None

        # Ignore subscription confirmations and errors (handled in sub-connection _listen)
        msg_type = raw_message.get("type", "")
        if msg_type in ("SUBSCRIBED", "UNSUBSCRIBED", "ERROR"):
            return None

        topic = raw_message.get("topic", "")
        pionex_symbol = raw_message.get("symbol", "")
        if not pionex_symbol:
            return None

        symbol = self._from_pionex_symbol(pionex_symbol)

        ts_raw = raw_message.get("timestamp", 0)
        try:
            updated_at = int(ts_raw) / 1000.0
        except (ValueError, TypeError):
            updated_at = 0.0

        if topic == "TRADE":
            data_list = raw_message.get("data")
            if data_list and isinstance(data_list, list) and len(data_list) > 0:
                self._last_prices[symbol] = str(data_list[0].get("price", ""))
            return None

        if topic == "DEPTH":
            data = raw_message.get("data")
            if data is None:
                return None

            bids_raw = data.get("bids", [])
            asks_raw = data.get("asks", [])

            bid = ""
            bid_qty = ""
            ask = ""
            ask_qty = ""

            if bids_raw and len(bids_raw) > 0:
                bid = str(bids_raw[0][0]) if len(bids_raw[0]) > 0 else ""
                bid_qty = str(bids_raw[0][1]) if len(bids_raw[0]) > 1 else ""
            if asks_raw and len(asks_raw) > 0:
                ask = str(asks_raw[0][0]) if len(asks_raw[0]) > 0 else ""
                ask_qty = str(asks_raw[0][1]) if len(asks_raw[0]) > 1 else ""

            # Parse multi-level depth
            depth_bids = [
                (str(b[0]), str(b[1])) for b in bids_raw if len(b) >= 2
            ] or None
            depth_asks = [
                (str(a[0]), str(a[1])) for a in asks_raw if len(a) >= 2
            ] or None

            price_state = PriceState(
                bid=bid,
                ask=ask,
                bid_qty=bid_qty,
                ask_qty=ask_qty,
                last_price=self._last_prices.get(symbol, ""),
                volume="",
                updated_at=updated_at,
                bids=depth_bids,
                asks=depth_asks,
            )
            return symbol, price_state

        return None

    async def run(self) -> None:
        """Split symbols across multiple connections to avoid topic limit."""
        self._running = True
        self._ensure_output_dir()
        self._connect_time = time.time()
        self._first_data_time = 0.0
        logger.info(
            f"[{self.exchange_name}] Starting fetcher for {len(self.symbols)} symbols"
        )

        # Split symbols into batches
        batches: list[list[str]] = []
        for i in range(0, len(self.symbols), _MAX_SYMBOLS_PER_CONN):
            batches.append(self.symbols[i : i + _MAX_SYMBOLS_PER_CONN])

        num_conns = len(batches)
        if num_conns > 1:
            logger.info(
                f"[{self.exchange_name}] Splitting {len(self.symbols)} symbols "
                f"across {num_conns} connections "
                f"({', '.join(str(len(b)) for b in batches)})"
            )

        subs = [
            _PionexSubConnection(self, batch, index=i)
            for i, batch in enumerate(batches)
        ]

        try:
            await asyncio.gather(
                *(sub.run() for sub in subs),
                self._snapshot_loop(),
                self._latency_log_loop(),
            )
        except Exception as e:
            if self._running:
                logger.error(f"[{self.exchange_name}] Error in multi-connection run: {e}")

    def stop(self) -> None:
        self._running = False
        logger.info(f"[{self.exchange_name}] Stop requested")


class _PionexSubConnection:
    """Manages a single Pionex WS connection for a subset of symbols."""

    def __init__(self, parent: PionexFetcher, symbols: list[str], index: int = 0) -> None:
        self._parent = parent
        self._symbols = symbols
        self._index = index
        # Track subscription state per connection attempt
        self._confirmed_symbols: set[str] = set()
        self._subscription_order: list[str] = []
        self._got_invalid_error: bool = False

    async def run(self) -> None:
        # Stagger connections: 5s delay per connection to avoid IP rate limit
        if self._index > 0:
            await asyncio.sleep(self._index * 5.0)

        delay = RECONNECT_INITIAL_DELAY
        while self._parent._running:
            # Filter out known invalid symbols
            valid = [s for s in self._symbols if s not in self._parent._invalid_symbols]
            if not valid:
                logger.info(
                    f"[{self._parent.exchange_name}] Sub-connection {self._index}: "
                    f"no valid symbols remaining, stopping"
                )
                return

            try:
                await self._connect_and_listen(valid)
                delay = RECONNECT_INITIAL_DELAY
            except Exception as e:
                if not self._parent._running:
                    break
                # After disconnect, identify invalid symbols from unconfirmed subscriptions
                if self._got_invalid_error:
                    self._identify_invalid_symbols()
                    delay = RECONNECT_INITIAL_DELAY  # retry quickly with fixed symbol list
                else:
                    logger.error(f"[{self._parent.exchange_name}] Sub-connection error: {e}")
                    await asyncio.sleep(delay)
                    delay = min(delay * RECONNECT_BACKOFF_FACTOR, RECONNECT_MAX_DELAY)

    def _identify_invalid_symbols(self) -> None:
        """After a disconnect with INVALID_SYMBOL, find the first unconfirmed symbol."""
        for s in self._subscription_order:
            if s not in self._confirmed_symbols and s not in self._parent._invalid_symbols:
                self._parent._invalid_symbols.add(s)
                logger.warning(
                    f"[{self._parent.exchange_name}] {s} not available on Pionex, "
                    f"will skip on reconnect"
                )
                break  # only mark the first unconfirmed (server disconnects at first error)

    async def _connect_and_listen(self, symbols: list[str]) -> None:
        url = self._parent._build_ws_url()
        kwargs = self._parent._ws_connect_kwargs()

        # Reset subscription tracking
        self._confirmed_symbols = set()
        self._subscription_order = list(symbols)
        self._got_invalid_error = False

        async with websockets.connect(url, **kwargs) as ws:
            self._parent._ws_connected = True
            logger.info(
                f"[{self._parent.exchange_name}] Sub-connection {self._index} for "
                f"{len(symbols)} symbols connected"
            )

            # Subscribe with throttling to avoid rate limiting
            for s in symbols:
                pionex_sym = PionexFetcher._to_pionex_symbol(s)
                await ws.send(json.dumps({
                    "op": "SUBSCRIBE",
                    "topic": "DEPTH",
                    "symbol": pionex_sym,
                    "limit": 5,
                }))
                await ws.send(json.dumps({
                    "op": "SUBSCRIBE",
                    "topic": "TRADE",
                    "symbol": pionex_sym,
                }))
                await asyncio.sleep(0.25)  # Throttle: 250ms between symbols (safe for 10 req/s)

            skipped = len(self._symbols) - len(symbols)
            skip_msg = f" ({skipped} skipped)" if skipped else ""
            logger.info(
                f"[{self._parent.exchange_name}] Subscribed to "
                f"{len(symbols)} symbols (DEPTH+TRADE){skip_msg}"
            )

            listener = asyncio.create_task(self._listen(ws))
            keepalive = asyncio.create_task(self._keep_alive(ws))

            done, pending = await asyncio.wait(
                [listener, keepalive],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
            # Surface listener/keepalive crashes — without this the exception
            # goes silent as "Task exception was never retrieved" at GC time
            # (S21 produced 6 such warnings during OKX reconnect / Pionex cycling).
            for t in done:
                try:
                    t.result()
                except Exception as e:
                    logger.warning(f"[Pionex] task crashed: {type(e).__name__}: {e}")

    async def _listen(self, ws: Any) -> None:
        async for raw in ws:
            if not self._parent._running:
                break
            try:
                message = json.loads(raw)

                # Handle server PING inline — must respond immediately
                op = message.get("op", "")
                if op == "PING":
                    await ws.send(json.dumps({
                        "op": "PONG",
                        "timestamp": int(time.time() * 1000),
                    }))
                    continue

                # Handle subscription confirmations and errors
                msg_type = message.get("type", "")
                if msg_type == "SUBSCRIBED":
                    sym = message.get("symbol", "")
                    if sym:
                        self._confirmed_symbols.add(
                            PionexFetcher._from_pionex_symbol(sym)
                        )
                    continue
                if msg_type == "ERROR":
                    code = message.get("code", "")
                    if code == "INVALID_SYMBOL":
                        self._got_invalid_error = True
                    else:
                        logger.warning(
                            f"[{self._parent.exchange_name}] Server error: {message}"
                        )
                    continue
                if msg_type == "UNSUBSCRIBED":
                    continue

                t0 = time.time()
                result = self._parent._parse_message(message)
                if result is not None:
                    symbol, price_data = result
                    if symbol in self._parent._state:
                        now = time.time()
                        price_data.received_at = now
                        self._parent._state[symbol] = price_data
                        self._parent._last_data_received = now
                        self._parent._message_count += 1
                        proc_ms = (now - t0) * 1000
                        self._parent._latency_samples.append(proc_ms)
                        if self._parent._first_data_time == 0.0:
                            self._parent._first_data_time = now
                            conn_ms = (now - self._parent._connect_time) * 1000
                            logger.info(
                                f"[Latency] [{self._parent.exchange_name}] "
                                f"First data received in {conn_ms:.0f}ms "
                                f"after connect"
                            )

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.debug(f"[{self._parent.exchange_name}] Parse error: {e}")

    async def _keep_alive(self, ws: Any) -> None:
        """Send periodic PONG as fallback (server PING handled in _listen)."""
        while self._parent._running:
            try:
                await ws.send(json.dumps({
                    "op": "PONG",
                    "timestamp": int(time.time() * 1000),
                }))
            except Exception:
                break
            await asyncio.sleep(14)
