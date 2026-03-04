"""
Bitfinex Spot WebSocket fetcher (v2 API).

Connects to Bitfinex public WebSocket and streams real-time ticker data
for all configured symbols using the ticker channel.

Bitfinex ticker fields (array-based, positional):
    [CHANNEL_ID, [BID, BID_SIZE, ASK, ASK_SIZE, DAILY_CHANGE,
                  DAILY_CHANGE_RELATIVE, LAST_PRICE, VOLUME, HIGH, LOW]]

Connection notes:
    - Subscribe post-connect: {"event":"subscribe","channel":"ticker","symbol":"tBTCUST"}
    - Symbol format: tBTCUST (t prefix + base + UST for USDT pairs)
    - Heartbeat: server sends [CHANNEL_ID, "hb"] periodically
    - Ping/pong: {"event":"ping","cid":N} -> {"event":"pong","cid":N}
    - Max 30 subscriptions per connection — need 2 connections for 60 symbols
    - Data arrives as arrays (not objects) for efficiency
    - Server info codes: 20051 (restart), 20060 (maintenance), 20061 (maintenance end)
"""

import asyncio
import json
import logging
import time
from typing import Any

import websockets

from config import BITFINEX_EXCHANGE_NAME, BITFINEX_WS_URL
from fetchers.base import BaseFetcher, PriceState

logger = logging.getLogger(__name__)

# Bitfinex ticker array field indices
_BID = 0
_BID_SIZE = 1
_ASK = 2
_ASK_SIZE = 3
_LAST_PRICE = 6
_VOLUME = 7


class BitfinexFetcher(BaseFetcher):
    """Bitfinex Spot WebSocket fetcher using the ticker channel.

    Uses two WebSocket connections to handle the 30-subscription limit
    (splits 60 symbols into two batches of 30).

    Bitfinex is event-driven: updates are sent only when the price changes,
    not at fixed intervals. High "data age" values (10-20s avg) reflect
    market inactivity on low-volume alts, not stale/inaccurate data.
    """

    IS_EVENT_DRIVEN: bool = True

    def __init__(self, symbols: list[str] | None = None) -> None:
        super().__init__(symbols)
        # Map channel_id -> symbol for each connection
        self._channel_map: dict[int, str] = {}

    @property
    def exchange_name(self) -> str:
        return BITFINEX_EXCHANGE_NAME

    def _build_ws_url(self) -> str:
        return BITFINEX_WS_URL

    @staticmethod
    def _to_bitfinex_symbol(symbol: str) -> str:
        """Convert BTCUSDT -> tBTCUST or tLINK:UST.

        Bitfinex uses UST for USDT. Legacy pairs with 3-char base use
        concatenated format (tBTCUST, 6 chars). Longer bases require
        a colon separator (tLINK:UST, tDOGE:UST).
        """
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            if len(base) <= 3:
                return f"t{base}UST"
            return f"t{base}:UST"
        return f"t{symbol}"

    @staticmethod
    def _from_bitfinex_symbol(bfx_symbol: str) -> str:
        """Convert tBTCUST or tLINK:UST -> BTCUSDT."""
        if not bfx_symbol.startswith("t"):
            return bfx_symbol
        inner = bfx_symbol[1:]
        # Colon-separated: tLINK:UST -> LINKUSDT
        if ":" in inner:
            base, quote = inner.split(":", 1)
            if quote == "UST":
                return f"{base}USDT"
            return f"{base}{quote}"
        # Legacy: tBTCUST -> BTCUSDT (last 3 chars = UST)
        if inner.endswith("UST") and len(inner) >= 6:
            base = inner[:-3]
            return f"{base}USDT"
        return bfx_symbol

    async def _on_connect(self, ws: Any) -> None:
        """Subscribe to ticker channel for all symbols (up to 30 per connection)."""
        for s in self.symbols:
            bfx_sym = self._to_bitfinex_symbol(s)
            msg = {
                "event": "subscribe",
                "channel": "ticker",
                "symbol": bfx_sym,
            }
            await ws.send(json.dumps(msg))
        logger.info(f"[{self.exchange_name}] Subscribing to {len(self.symbols)} tickers")

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Disable library-level ping; Bitfinex uses application-level ping."""
        return {
            "ping_interval": None,
            "ping_timeout": None,
            "close_timeout": 10,
            "max_size": 2**20,
        }

    async def _keep_alive(self, ws: Any) -> None:
        """Send application-level ping every 15 seconds."""
        cid = 0
        while self._running and self._ws_connected:
            try:
                cid += 1
                await ws.send(json.dumps({
                    "event": "ping",
                    "cid": cid,
                }))
            except Exception:
                break
            await asyncio.sleep(15)

    def _parse_message(self, raw_message: dict[str, Any] | list) -> tuple[str, PriceState] | None:
        """
        Parse Bitfinex WebSocket messages.

        Event messages (dicts):
            {"event":"subscribed","channel":"ticker","chanId":123,"symbol":"tBTCUST"}
            {"event":"info","version":2}
            {"event":"pong","cid":1}

        Data messages (arrays):
            [CHANNEL_ID, [BID, BID_SIZE, ASK, ASK_SIZE, DAILY_CHANGE,
                          DAILY_CHANGE_PERC, LAST_PRICE, VOLUME, HIGH, LOW]]
            [CHANNEL_ID, "hb"]  (heartbeat)
        """
        # Event messages are dicts
        if isinstance(raw_message, dict):
            event = raw_message.get("event", "")
            if event == "subscribed":
                chan_id = raw_message.get("chanId")
                bfx_symbol = raw_message.get("symbol", "")
                if chan_id is not None and bfx_symbol:
                    symbol = self._from_bitfinex_symbol(bfx_symbol)
                    self._channel_map[chan_id] = symbol
                    logger.debug(
                        f"[{self.exchange_name}] Channel {chan_id} -> {symbol}"
                    )
            elif event == "info":
                code = raw_message.get("code")
                if code == 20051:
                    logger.warning(f"[{self.exchange_name}] Server restart requested")
                elif code == 20060:
                    logger.warning(f"[{self.exchange_name}] Maintenance mode entered")
                elif code == 20061:
                    logger.info(f"[{self.exchange_name}] Maintenance mode ended")
            return None

        # Data messages are arrays
        if not isinstance(raw_message, list) or len(raw_message) < 2:
            return None

        chan_id = raw_message[0]
        payload = raw_message[1]

        # Heartbeat
        if payload == "hb":
            return None

        # Ticker snapshot/update: payload is a list of 10 floats
        if not isinstance(payload, list) or len(payload) < 10:
            return None

        symbol = self._channel_map.get(chan_id)
        if not symbol:
            return None

        price_state = PriceState(
            bid=str(payload[_BID]),
            ask=str(payload[_ASK]),
            bid_qty=str(abs(payload[_BID_SIZE])),
            ask_qty=str(abs(payload[_ASK_SIZE])),
            last_price=str(payload[_LAST_PRICE]),
            volume=str(payload[_VOLUME]),
            updated_at=time.time(),
        )

        return symbol, price_state

    async def run(self) -> None:
        """Override run to handle multiple connections.

        Uses 2 connections for ticker + 2 for book depth (4 total when >30 symbols).
        """
        if len(self.symbols) <= 30:
            # Single ticker + single book connection
            self._running = True
            self._ensure_output_dir()
            self._connect_time = time.time()
            self._first_data_time = 0.0

            ticker_sub = _BitfinexSubFetcher(self, self.symbols)
            book_sub = _BitfinexBookSubFetcher(self, self.symbols)

            try:
                await asyncio.gather(
                    ticker_sub.run(),
                    book_sub.run(),
                    self._snapshot_loop(),
                    self._latency_log_loop(),
                )
            except Exception as e:
                if self._running:
                    logger.error(f"[{self.exchange_name}] Error in multi-connection run: {e}")
            return

        # Split symbols into two batches
        mid = len(self.symbols) // 2
        batch1 = self.symbols[:mid]
        batch2 = self.symbols[mid:]

        logger.info(
            f"[{self.exchange_name}] Splitting {len(self.symbols)} symbols "
            f"across 4 connections (2 ticker + 2 book)"
        )

        ticker1 = _BitfinexSubFetcher(self, batch1)
        ticker2 = _BitfinexSubFetcher(self, batch2)
        book1 = _BitfinexBookSubFetcher(self, batch1)
        book2 = _BitfinexBookSubFetcher(self, batch2)

        self._running = True
        self._ensure_output_dir()
        self._connect_time = time.time()
        self._first_data_time = 0.0

        try:
            await asyncio.gather(
                ticker1.run(),
                ticker2.run(),
                book1.run(),
                book2.run(),
                self._snapshot_loop(),
                self._latency_log_loop(),
            )
        except Exception as e:
            if self._running:
                logger.error(f"[{self.exchange_name}] Error in multi-connection run: {e}")

    def stop(self) -> None:
        """Signal stop for main fetcher and any sub-fetchers."""
        self._running = False
        logger.info(f"[{self.exchange_name}] Stop requested")


class _BitfinexSubFetcher:
    """Internal helper that manages a single Bitfinex WS connection for a subset of symbols."""

    def __init__(self, parent: BitfinexFetcher, symbols: list[str]) -> None:
        self._parent = parent
        self._symbols = symbols
        self._channel_map: dict[int, str] = {}
        self._confirmed: set[str] = set()
        self._last_data_time: float = 0.0

    async def run(self) -> None:
        """Connect and listen loop with reconnection."""
        from config import RECONNECT_INITIAL_DELAY, RECONNECT_BACKOFF_FACTOR, RECONNECT_MAX_DELAY

        delay = RECONNECT_INITIAL_DELAY
        while self._parent._running:
            try:
                await self._connect_and_listen()
                delay = RECONNECT_INITIAL_DELAY
            except Exception as e:
                if not self._parent._running:
                    break
                logger.error(
                    f"[{self._parent.exchange_name}] Sub-connection error: {e}"
                )
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

            # Subscribe
            for s in self._symbols:
                bfx_sym = BitfinexFetcher._to_bitfinex_symbol(s)
                await ws.send(json.dumps({
                    "event": "subscribe",
                    "channel": "ticker",
                    "symbol": bfx_sym,
                }))

            # Listen + keepalive + staleness watchdog
            listener = asyncio.create_task(self._listen(ws))
            keepalive = asyncio.create_task(self._keep_alive(ws))
            staleness = asyncio.create_task(self._staleness_watchdog(ws))

            done, pending = await asyncio.wait(
                [listener, keepalive, staleness],
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
                t0 = time.time()
                message = json.loads(raw)
                # Handle event messages (subscribed, info, pong)
                if isinstance(message, dict):
                    event = message.get("event", "")
                    if event == "subscribed":
                        chan_id = message.get("chanId")
                        bfx_symbol = message.get("symbol", "")
                        if chan_id is not None and bfx_symbol:
                            symbol = BitfinexFetcher._from_bitfinex_symbol(bfx_symbol)
                            self._channel_map[chan_id] = symbol
                            self._confirmed.add(symbol)
                            logger.debug(
                                f"[{self._parent.exchange_name}] "
                                f"Subscribed: {symbol} (chan={chan_id})"
                            )
                            if len(self._confirmed) == len(self._symbols):
                                logger.info(
                                    f"[{self._parent.exchange_name}] "
                                    f"Subscribed to {len(self._confirmed)} tickers"
                                )
                    elif event == "error":
                        err_sym = message.get("symbol", "?")
                        err_msg = message.get("msg", "unknown")
                        symbol = BitfinexFetcher._from_bitfinex_symbol(err_sym) if err_sym != "?" else "?"
                        logger.warning(
                            f"[{self._parent.exchange_name}] "
                            f"Subscribe failed: {symbol} — {err_msg}"
                        )
                    continue

                # Data messages (arrays)
                if not isinstance(message, list) or len(message) < 2:
                    continue

                chan_id = message[0]
                payload = message[1]

                if payload == "hb":
                    continue

                if not isinstance(payload, list) or len(payload) < 10:
                    continue

                symbol = self._channel_map.get(chan_id)
                if not symbol or symbol not in self._parent._state:
                    continue

                now = time.time()
                price_state = PriceState(
                    bid=str(payload[_BID]),
                    ask=str(payload[_ASK]),
                    bid_qty=str(abs(payload[_BID_SIZE])),
                    ask_qty=str(abs(payload[_ASK_SIZE])),
                    last_price=str(payload[_LAST_PRICE]),
                    volume=str(payload[_VOLUME]),
                    updated_at=now,
                    received_at=now,
                )
                self._parent._state[symbol] = price_state
                self._parent._last_data_received = now
                self._last_data_time = now
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
        cid = 0
        while self._parent._running:
            try:
                cid += 1
                await ws.send(json.dumps({"event": "ping", "cid": cid}))
            except Exception:
                break
            await asyncio.sleep(15)

    async def _staleness_watchdog(self, ws: Any) -> None:
        """Force reconnect if no data received for 30 seconds on this sub-connection."""
        while self._parent._running:
            await asyncio.sleep(5.0)
            if self._last_data_time > 0:
                stale = time.time() - self._last_data_time
                if stale >= self._parent.STALENESS_RECONNECT_SECONDS:
                    logger.warning(
                        f"[{self._parent.exchange_name}] Sub-connection stale "
                        f"({stale:.0f}s, {len(self._confirmed)} symbols), "
                        f"reconnecting"
                    )
                    self._channel_map.clear()
                    self._confirmed.clear()
                    self._last_data_time = 0.0
                    await ws.close()
                    return


class _BitfinexBookSubFetcher:
    """Internal helper: single Bitfinex WS connection for book depth data (≤30 symbols).

    Subscribes to the 'book' channel with P0 precision and 5 levels.
    Data format:
        Snapshot: [CHAN_ID, [[PRICE, COUNT, AMOUNT], ...]]
        Update:   [CHAN_ID, [PRICE, COUNT, AMOUNT]]
    AMOUNT > 0 = bid, AMOUNT < 0 = ask (absolute value = qty).
    """

    def __init__(self, parent: BitfinexFetcher, symbols: list[str]) -> None:
        self._parent = parent
        self._symbols = symbols
        self._channel_map: dict[int, str] = {}
        self._confirmed: set[str] = set()
        self._last_data_time: float = 0.0
        # Maintain full book state per symbol for snapshot+update merging
        self._book_bids: dict[str, dict[float, float]] = {}  # symbol -> {price: qty}
        self._book_asks: dict[str, dict[float, float]] = {}  # symbol -> {price: qty}

    async def run(self) -> None:
        from config import RECONNECT_INITIAL_DELAY, RECONNECT_BACKOFF_FACTOR, RECONNECT_MAX_DELAY

        delay = RECONNECT_INITIAL_DELAY
        while self._parent._running:
            try:
                await self._connect_and_listen()
                delay = RECONNECT_INITIAL_DELAY
            except Exception as e:
                if not self._parent._running:
                    break
                logger.error(
                    f"[{self._parent.exchange_name}] Book sub-connection error: {e}"
                )
                await asyncio.sleep(delay)
                delay = min(delay * RECONNECT_BACKOFF_FACTOR, RECONNECT_MAX_DELAY)

    async def _connect_and_listen(self) -> None:
        url = self._parent._build_ws_url()
        kwargs = self._parent._ws_connect_kwargs()

        # Clear book state on reconnect
        self._channel_map.clear()
        self._confirmed.clear()
        self._book_bids.clear()
        self._book_asks.clear()

        async with websockets.connect(url, **kwargs) as ws:
            logger.info(
                f"[{self._parent.exchange_name}] Book sub-connection for "
                f"{len(self._symbols)} symbols connected"
            )

            for s in self._symbols:
                bfx_sym = BitfinexFetcher._to_bitfinex_symbol(s)
                await ws.send(json.dumps({
                    "event": "subscribe",
                    "channel": "book",
                    "symbol": bfx_sym,
                    "prec": "P0",
                    "freq": "F0",
                    "len": "5",
                }))

            listener = asyncio.create_task(self._listen(ws))
            keepalive = asyncio.create_task(self._keep_alive(ws))
            staleness = asyncio.create_task(self._staleness_watchdog(ws))

            done, pending = await asyncio.wait(
                [listener, keepalive, staleness],
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

                # Event messages (subscribed, error, info, pong)
                if isinstance(message, dict):
                    event = message.get("event", "")
                    if event == "subscribed" and message.get("channel") == "book":
                        chan_id = message.get("chanId")
                        bfx_symbol = message.get("symbol", "")
                        if chan_id is not None and bfx_symbol:
                            symbol = BitfinexFetcher._from_bitfinex_symbol(bfx_symbol)
                            self._channel_map[chan_id] = symbol
                            self._confirmed.add(symbol)
                            self._book_bids[symbol] = {}
                            self._book_asks[symbol] = {}
                            if len(self._confirmed) == len(self._symbols):
                                logger.info(
                                    f"[{self._parent.exchange_name}] "
                                    f"Subscribed to {len(self._confirmed)} book channels"
                                )
                    continue

                # Data messages (arrays)
                if not isinstance(message, list) or len(message) < 2:
                    continue

                chan_id = message[0]
                payload = message[1]

                if payload == "hb":
                    continue

                symbol = self._channel_map.get(chan_id)
                if not symbol or symbol not in self._parent._state:
                    continue

                # Snapshot: [[PRICE, COUNT, AMOUNT], ...]
                # Update: [PRICE, COUNT, AMOUNT]
                if isinstance(payload, list) and len(payload) > 0:
                    if isinstance(payload[0], list):
                        # Snapshot — reset book
                        self._book_bids[symbol] = {}
                        self._book_asks[symbol] = {}
                        for entry in payload:
                            if len(entry) >= 3:
                                self._process_book_entry(symbol, entry)
                    elif len(payload) >= 3:
                        # Single update
                        self._process_book_entry(symbol, payload)

                    self._update_price_state_depth(symbol)
                    self._last_data_time = time.time()

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.debug(f"[{self._parent.exchange_name}] Book parse error: {e}")

    def _process_book_entry(self, symbol: str, entry: list) -> None:
        """Process a single book entry [PRICE, COUNT, AMOUNT].

        COUNT > 0: add/update level. COUNT = 0: remove level.
        AMOUNT > 0: bid. AMOUNT < 0: ask.
        """
        price = float(entry[0])
        count = int(entry[1])
        amount = float(entry[2])

        if count == 0:
            # Remove price level
            self._book_bids.get(symbol, {}).pop(price, None)
            self._book_asks.get(symbol, {}).pop(price, None)
        elif amount > 0:
            # Bid
            self._book_bids.setdefault(symbol, {})[price] = abs(amount)
            self._book_asks.get(symbol, {}).pop(price, None)
        elif amount < 0:
            # Ask
            self._book_asks.setdefault(symbol, {})[price] = abs(amount)
            self._book_bids.get(symbol, {}).pop(price, None)

    def _update_price_state_depth(self, symbol: str) -> None:
        """Convert internal book state to sorted bids/asks lists on PriceState."""
        existing = self._parent._state.get(symbol, PriceState())

        bids_dict = self._book_bids.get(symbol, {})
        asks_dict = self._book_asks.get(symbol, {})

        # Sort bids descending, asks ascending; take top 5
        sorted_bids = sorted(bids_dict.items(), key=lambda x: -x[0])[:5]
        sorted_asks = sorted(asks_dict.items(), key=lambda x: x[0])[:5]

        depth_bids = [(str(p), str(q)) for p, q in sorted_bids] or None
        depth_asks = [(str(p), str(q)) for p, q in sorted_asks] or None

        now = time.time()
        self._parent._state[symbol] = PriceState(
            bid=existing.bid,
            ask=existing.ask,
            bid_qty=existing.bid_qty,
            ask_qty=existing.ask_qty,
            last_price=existing.last_price,
            volume=existing.volume,
            updated_at=existing.updated_at,
            received_at=now,
            bids=depth_bids,
            asks=depth_asks,
        )

    async def _keep_alive(self, ws: Any) -> None:
        cid = 0
        while self._parent._running:
            try:
                cid += 1
                await ws.send(json.dumps({"event": "ping", "cid": cid}))
            except Exception:
                break
            await asyncio.sleep(15)

    async def _staleness_watchdog(self, ws: Any) -> None:
        while self._parent._running:
            await asyncio.sleep(5.0)
            if self._last_data_time > 0:
                stale = time.time() - self._last_data_time
                if stale >= self._parent.STALENESS_RECONNECT_SECONDS:
                    logger.warning(
                        f"[{self._parent.exchange_name}] Book sub-connection stale "
                        f"({stale:.0f}s), reconnecting"
                    )
                    self._channel_map.clear()
                    self._confirmed.clear()
                    self._book_bids.clear()
                    self._book_asks.clear()
                    self._last_data_time = 0.0
                    await ws.close()
                    return
