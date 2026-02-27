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

        # Ignore subscription confirmations and errors
        msg_type = raw_message.get("type", "")
        if msg_type in ("SUBSCRIBED", "UNSUBSCRIBED", "ERROR"):
            if msg_type == "ERROR":
                logger.warning(
                    f"[{self.exchange_name}] Server error: {raw_message}"
                )
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

            bids = data.get("bids", [])
            asks = data.get("asks", [])

            bid = ""
            bid_qty = ""
            ask = ""
            ask_qty = ""

            if bids and len(bids) > 0:
                bid = str(bids[0][0]) if len(bids[0]) > 0 else ""
                bid_qty = str(bids[0][1]) if len(bids[0]) > 1 else ""
            if asks and len(asks) > 0:
                ask = str(asks[0][0]) if len(asks[0]) > 0 else ""
                ask_qty = str(asks[0][1]) if len(asks[0]) > 1 else ""

            price_state = PriceState(
                bid=bid,
                ask=ask,
                bid_qty=bid_qty,
                ask_qty=ask_qty,
                last_price=self._last_prices.get(symbol, ""),
                volume="",
                updated_at=updated_at,
            )
            return symbol, price_state

        return None

    async def run(self) -> None:
        """Split symbols across multiple connections to avoid topic limit."""
        self._running = True
        self._ensure_output_dir()
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

        subs = [_PionexSubConnection(self, batch) for batch in batches]

        try:
            await asyncio.gather(
                *(sub.run() for sub in subs),
                self._snapshot_loop(),
            )
        except Exception as e:
            if self._running:
                logger.error(f"[{self.exchange_name}] Error in multi-connection run: {e}")

    def stop(self) -> None:
        self._running = False
        logger.info(f"[{self.exchange_name}] Stop requested")


class _PionexSubConnection:
    """Manages a single Pionex WS connection for a subset of symbols."""

    def __init__(self, parent: PionexFetcher, symbols: list[str]) -> None:
        self._parent = parent
        self._symbols = symbols

    async def run(self) -> None:
        delay = RECONNECT_INITIAL_DELAY
        while self._parent._running:
            try:
                await self._connect_and_listen()
                delay = RECONNECT_INITIAL_DELAY
            except Exception as e:
                if not self._parent._running:
                    break
                logger.error(f"[{self._parent.exchange_name}] Sub-connection error: {e}")
                await asyncio.sleep(delay)
                delay = min(delay * RECONNECT_BACKOFF_FACTOR, RECONNECT_MAX_DELAY)

    async def _connect_and_listen(self) -> None:
        url = self._parent._build_ws_url()
        kwargs = self._parent._ws_connect_kwargs()

        async with websockets.connect(url, **kwargs) as ws:
            self._parent._ws_connected = True
            logger.info(
                f"[{self._parent.exchange_name}] Sub-connection for "
                f"{len(self._symbols)} symbols connected"
            )

            # Subscribe with throttling to avoid rate limiting
            for s in self._symbols:
                pionex_sym = PionexFetcher._to_pionex_symbol(s)
                await ws.send(json.dumps({
                    "op": "SUBSCRIBE",
                    "topic": "DEPTH",
                    "symbol": pionex_sym,
                    "limit": 1,
                }))
                await ws.send(json.dumps({
                    "op": "SUBSCRIBE",
                    "topic": "TRADE",
                    "symbol": pionex_sym,
                }))
                await asyncio.sleep(0.05)  # Throttle: 50ms between symbols

            logger.info(
                f"[{self._parent.exchange_name}] Subscribed to "
                f"{len(self._symbols)} symbols (DEPTH+TRADE)"
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

                result = self._parent._parse_message(message)
                if result is not None:
                    symbol, price_data = result
                    if symbol in self._parent._state:
                        now = time.time()
                        price_data.received_at = now
                        self._parent._state[symbol] = price_data
                        self._parent._last_data_received = now
                        self._parent._message_count += 1

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
