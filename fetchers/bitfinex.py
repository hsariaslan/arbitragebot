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
    """

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
        """Convert BTCUSDT -> tBTCUST (Bitfinex uses UST for USDT)."""
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            return f"t{base}UST"
        return f"t{symbol}"

    @staticmethod
    def _from_bitfinex_symbol(bfx_symbol: str) -> str:
        """Convert tBTCUST -> BTCUSDT."""
        if bfx_symbol.startswith("t") and bfx_symbol.endswith("UST"):
            base = bfx_symbol[1:-3]
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
        """Override run to handle 2 connections when symbols > 30."""
        if len(self.symbols) <= 30:
            # Single connection is enough
            await super().run()
            return

        # Split symbols into two batches
        mid = len(self.symbols) // 2
        batch1 = self.symbols[:mid]
        batch2 = self.symbols[mid:]

        logger.info(
            f"[{self.exchange_name}] Splitting {len(self.symbols)} symbols "
            f"across 2 connections ({len(batch1)} + {len(batch2)})"
        )

        # Create two sub-fetchers that share state with this parent
        fetcher1 = _BitfinexSubFetcher(self, batch1)
        fetcher2 = _BitfinexSubFetcher(self, batch2)

        self._running = True
        self._ensure_output_dir()

        try:
            await asyncio.gather(
                fetcher1.run(),
                fetcher2.run(),
                self._snapshot_loop(),
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

            # Listen + keepalive
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
                # Handle event messages (subscribed, info, pong)
                if isinstance(message, dict):
                    event = message.get("event", "")
                    if event == "subscribed":
                        chan_id = message.get("chanId")
                        bfx_symbol = message.get("symbol", "")
                        if chan_id is not None and bfx_symbol:
                            symbol = BitfinexFetcher._from_bitfinex_symbol(bfx_symbol)
                            self._channel_map[chan_id] = symbol
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
                self._parent._message_count += 1

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
