"""
MEXC Spot WebSocket fetcher.

Connects to MEXC WebSocket API and streams real-time aggregated book
ticker data for all configured symbols via Protocol Buffers.

MEXC switched to protobuf-only WebSocket in August 2025.
Proto schema: https://github.com/mexcdevelop/websocket-proto

PushDataV3ApiWrapper (outer):
    channel(1)=string, symbol(3)=string, sendTime(6)=int64
    publicAggreBookTicker(315)=PublicAggreBookTickerV3Api

PublicAggreBookTickerV3Api (inner):
    bidPrice(1)=string, bidQuantity(2)=string,
    askPrice(3)=string, askQuantity(4)=string

Connection notes:
    - Subscription is done post-connect via JSON message
    - Symbol format: BTCUSDT uppercase (matches our config)
    - Application-level ping: send {"method": "PING"}, every 10-20s
    - Max 30 subscriptions per connection
    - Data arrives as binary protobuf frames (not JSON)
"""

import asyncio
import json
import logging
import time
from typing import Any

import websockets

from config import CSV_SNAPSHOTS_ENABLED, MEXC_EXCHANGE_NAME, MEXC_WS_URL
from fetchers.base import BaseFetcher, PriceState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Minimal protobuf wire-format decoder (no external dependencies)
# ---------------------------------------------------------------------------

def _decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decode a protobuf varint, return (value, new_position)."""
    result = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        result |= (byte & 0x7F) << shift
        pos += 1
        if (byte & 0x80) == 0:
            break
        shift += 7
    return result, pos


def _decode_fields(data: bytes) -> dict[int, bytes | int]:
    """Decode a protobuf message into {field_number: value}.

    Wire types:
      0 = varint (int)
      2 = length-delimited (bytes — always raw, caller decodes strings)
      1 = 64-bit fixed, 5 = 32-bit fixed (skipped)
    """
    fields: dict[int, bytes | int] = {}
    pos = 0
    while pos < len(data):
        tag, pos = _decode_varint(data, pos)
        field_number = tag >> 3
        wire_type = tag & 0x07

        if wire_type == 0:  # varint
            value, pos = _decode_varint(data, pos)
            fields[field_number] = value
        elif wire_type == 2:  # length-delimited
            length, pos = _decode_varint(data, pos)
            if pos + length > len(data):
                break
            fields[field_number] = data[pos : pos + length]
            pos += length
        elif wire_type == 1:  # 64-bit fixed
            pos += 8
        elif wire_type == 5:  # 32-bit fixed
            pos += 4
        else:
            break  # unknown wire type
    return fields


def _get_str(fields: dict, key: int, default: str = "") -> str:
    """Extract a string field from decoded protobuf fields."""
    val = fields.get(key)
    if val is None:
        return default
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return str(val)


def _decode_repeated(data: bytes, field_number: int) -> list[bytes]:
    """Decode all occurrences of a repeated length-delimited field."""
    results: list[bytes] = []
    pos = 0
    while pos < len(data):
        tag, pos = _decode_varint(data, pos)
        fn = tag >> 3
        wt = tag & 0x07
        if wt == 0:
            _, pos = _decode_varint(data, pos)
        elif wt == 2:
            length, pos = _decode_varint(data, pos)
            if pos + length > len(data):
                break
            if fn == field_number:
                results.append(data[pos : pos + length])
            pos += length
        elif wt == 1:
            pos += 8
        elif wt == 5:
            pos += 4
        else:
            break
    return results


def _parse_depth_pb(data: bytes) -> tuple[str, list[tuple[str, str]], list[tuple[str, str]], int] | None:
    """Parse a PushDataV3ApiWrapper containing publicLimitDepths.

    MEXC depth channel: spot@public.depth.v3.api.pb@100ms@{symbol}
    Wrapper field 316 = PublicLimitDepthsV3Api (embedded message)
    PublicLimitDepthsV3Api:
        repeated PublicLimitDepthV3ApiItem asks (field 1)
        repeated PublicLimitDepthV3ApiItem bids (field 2)
    Each item: string price (field 1), string quantity (field 2)

    Returns (symbol, bids_list, asks_list, sendTime_ms) or None.
    """
    wrapper = _decode_fields(data)

    depth_raw = wrapper.get(316)
    if depth_raw is None or not isinstance(depth_raw, bytes):
        return None

    symbol = _get_str(wrapper, 3)
    send_time = wrapper.get(6, 0)
    if not isinstance(send_time, int):
        send_time = 0

    # Parse asks (field 1, repeated) and bids (field 2, repeated)
    asks_items = _decode_repeated(depth_raw, 1)
    bids_items = _decode_repeated(depth_raw, 2)

    asks: list[tuple[str, str]] = []
    for item_bytes in asks_items:
        item = _decode_fields(item_bytes)
        price = _get_str(item, 1)
        qty = _get_str(item, 2)
        if price and qty:
            asks.append((price, qty))

    bids: list[tuple[str, str]] = []
    for item_bytes in bids_items:
        item = _decode_fields(item_bytes)
        price = _get_str(item, 1)
        qty = _get_str(item, 2)
        if price and qty:
            bids.append((price, qty))

    return symbol, bids, asks, send_time


def _parse_book_ticker_pb(data: bytes) -> tuple[str, str, str, str, str, int] | None:
    """Parse a PushDataV3ApiWrapper containing a publicAggreBookTicker.

    Returns (symbol, bidPrice, bidQty, askPrice, askQty, sendTime_ms)
    or None if not a bookTicker message.
    """
    wrapper = _decode_fields(data)

    # Field 315 = publicAggreBookTicker (embedded message, bytes)
    ticker_raw = wrapper.get(315)
    if ticker_raw is None or not isinstance(ticker_raw, bytes):
        return None

    ticker = _decode_fields(ticker_raw)

    symbol = _get_str(wrapper, 3)       # field 3 = symbol
    send_time = wrapper.get(6, 0)       # field 6 = sendTime (int64 ms)
    if not isinstance(send_time, int):
        send_time = 0

    bid_price = _get_str(ticker, 1)     # field 1 = bidPrice
    bid_qty = _get_str(ticker, 2)       # field 2 = bidQuantity
    ask_price = _get_str(ticker, 3)     # field 3 = askPrice
    ask_qty = _get_str(ticker, 4)       # field 4 = askQuantity

    return symbol, bid_price, bid_qty, ask_price, ask_qty, send_time


# ---------------------------------------------------------------------------
# MEXC Fetcher
# ---------------------------------------------------------------------------

class MEXCFetcher(BaseFetcher):
    """MEXC Spot WebSocket fetcher using protobuf bookTicker channel."""

    @property
    def exchange_name(self) -> str:
        return MEXC_EXCHANGE_NAME

    def _build_ws_url(self) -> str:
        return MEXC_WS_URL

    async def _on_connect(self, ws: Any) -> None:
        """Subscribe to aggre bookTicker for all symbols (batched, max 30 per message)."""
        params = [
            f"spot@public.aggre.bookTicker.v3.api.pb@100ms@{s}"
            for s in self.symbols
        ]
        batch_size = 30
        for i in range(0, len(params), batch_size):
            batch = params[i : i + batch_size]
            await ws.send(json.dumps({"method": "SUBSCRIPTION", "params": batch}))
        logger.info(f"[{self.exchange_name}] Subscribed to {len(self.symbols)} bookTickers")

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Disable library-level ping; MEXC uses application-level JSON ping."""
        return {
            "ping_interval": None,
            "ping_timeout": None,
            "close_timeout": 10,
            "max_size": 2**20,
        }

    async def _keep_alive(self, ws: Any) -> None:
        """Send {"method": "PING"} every 15 seconds (MEXC requires 10-20s)."""
        while self._running and self._ws_connected:
            try:
                await ws.send(json.dumps({"method": "PING"}))
            except Exception:
                break
            await asyncio.sleep(15)

    async def _listen(self, ws: Any) -> None:
        """Listen for binary protobuf messages and update state."""
        async for raw in ws:
            if not self._running:
                break

            try:
                t0 = time.time()

                # Text frames are JSON control messages (subscription ack, pong)
                if isinstance(raw, str):
                    # Could be subscription confirmation or pong — skip
                    continue

                # Binary frames are protobuf
                result = _parse_book_ticker_pb(raw)
                if result is None:
                    continue

                symbol, bid, bid_qty, ask, ask_qty, send_time_ms = result
                if symbol not in self._state:
                    continue

                now = time.time()
                updated_at = send_time_ms / 1000.0 if send_time_ms else 0.0
                existing = self._state.get(symbol, PriceState())

                price_data = PriceState(
                    bid=bid,
                    ask=ask,
                    bid_qty=bid_qty,
                    ask_qty=ask_qty,
                    last_price="",
                    volume="",
                    updated_at=updated_at,
                    received_at=now,
                    book_received_at=existing.book_received_at,
                    bids=existing.bids,
                    asks=existing.asks,
                )
                self._last_data_received = now
                self._state[symbol] = price_data
                self._message_count += 1

                proc_ms = (now - t0) * 1000
                self._latency_samples.append(proc_ms)

                if self._first_data_time == 0.0:
                    self._first_data_time = now
                    conn_to_data_ms = (now - self._connect_time) * 1000
                    logger.info(
                        f"[Latency] [{self.exchange_name}] "
                        f"First data received in {conn_to_data_ms:.0f}ms "
                        f"after connect"
                    )
            except Exception as e:
                logger.debug(f"[{self.exchange_name}] Parse error: {e}")

    def _parse_message(self, raw_message: dict[str, Any]) -> tuple[str, PriceState] | None:
        """Not used — MEXC uses binary protobuf parsed in _listen()."""
        return None

    async def run(self) -> None:
        """Override run to handle multiple connections.

        Uses 2 connections for bookTicker + 2 for depth (4 total when >30 symbols).
        """
        if len(self.symbols) <= 30:
            # Single bookTicker + single depth connection
            self._running = True
            if CSV_SNAPSHOTS_ENABLED:
                self._ensure_output_dir()
            else:
                logger.info(f"[{self.exchange_name}] CSV snapshots disabled")
            self._connect_time = time.time()
            self._first_data_time = 0.0

            ticker_sub = _MEXCSubFetcher(self, self.symbols)
            depth_sub = _MEXCDepthSubFetcher(self, self.symbols)
            tasks = [
                ticker_sub.run(),
                depth_sub.run(),
                self._latency_log_loop(),
            ]
            if CSV_SNAPSHOTS_ENABLED:
                tasks.append(self._snapshot_loop())

            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                if self._running:
                    logger.error(f"[{self.exchange_name}] Multi-connection error: {e}")
            return

        mid = len(self.symbols) // 2
        batch1 = self.symbols[:mid]
        batch2 = self.symbols[mid:]

        logger.info(
            f"[{self.exchange_name}] Splitting {len(self.symbols)} symbols "
            f"across 4 connections (2 bookTicker + 2 depth)"
        )

        ticker1 = _MEXCSubFetcher(self, batch1)
        ticker2 = _MEXCSubFetcher(self, batch2)
        depth1 = _MEXCDepthSubFetcher(self, batch1)
        depth2 = _MEXCDepthSubFetcher(self, batch2)

        self._running = True
        if CSV_SNAPSHOTS_ENABLED:
            self._ensure_output_dir()
        else:
            logger.info(f"[{self.exchange_name}] CSV snapshots disabled")
        self._connect_time = time.time()
        self._first_data_time = 0.0
        tasks = [
            ticker1.run(),
            ticker2.run(),
            depth1.run(),
            depth2.run(),
            self._latency_log_loop(),
        ]
        if CSV_SNAPSHOTS_ENABLED:
            tasks.append(self._snapshot_loop())

        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            if self._running:
                logger.error(f"[{self.exchange_name}] Multi-connection error: {e}")

    def stop(self) -> None:
        """Signal stop for main fetcher and any sub-fetchers."""
        self._running = False
        logger.info(f"[{self.exchange_name}] Stop requested")


class _MEXCSubFetcher:
    """Internal helper: single MEXC WS connection for a subset of symbols (≤30)."""

    def __init__(self, parent: MEXCFetcher, symbols: list[str]) -> None:
        self._parent = parent
        self._symbols = symbols
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

            # Subscribe (single batch, all ≤30 — within MEXC limit)
            params = [
                f"spot@public.aggre.bookTicker.v3.api.pb@100ms@{s}"
                for s in self._symbols
            ]
            await ws.send(json.dumps({"method": "SUBSCRIPTION", "params": params}))
            logger.info(
                f"[{self._parent.exchange_name}] Subscribed to "
                f"{len(self._symbols)} bookTickers"
            )

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
            # Surface listener/keepalive/staleness crashes — without this the
            # exception goes silent at GC time (S21 silent-task-exception fix).
            for t in done:
                try:
                    t.result()
                except Exception as e:
                    logger.warning(f"[MEXC] task crashed: {type(e).__name__}: {e}")

    async def _listen(self, ws: Any) -> None:
        """Listen for binary protobuf messages and update parent state."""
        async for raw in ws:
            if not self._parent._running:
                break
            try:
                t0 = time.time()

                # Text frames are JSON control messages (subscription ack, pong)
                if isinstance(raw, str):
                    continue

                # Binary frames are protobuf
                result = _parse_book_ticker_pb(raw)
                if result is None:
                    continue

                symbol, bid, bid_qty, ask, ask_qty, send_time_ms = result
                if symbol not in self._parent._state:
                    continue

                now = time.time()
                updated_at = send_time_ms / 1000.0 if send_time_ms else 0.0
                existing = self._parent._state.get(symbol, PriceState())

                price_data = PriceState(
                    bid=bid,
                    ask=ask,
                    bid_qty=bid_qty,
                    ask_qty=ask_qty,
                    last_price="",
                    volume="",
                    updated_at=updated_at,
                    received_at=now,
                    book_received_at=existing.book_received_at,
                    bids=existing.bids,
                    asks=existing.asks,
                )
                self._parent._last_data_received = now
                self._last_data_time = now
                self._parent._state[symbol] = price_data
                self._parent._message_count += 1

                proc_ms = (now - t0) * 1000
                self._parent._latency_samples.append(proc_ms)

                if self._parent._first_data_time == 0.0:
                    self._parent._first_data_time = now
                    conn_to_data_ms = (now - self._parent._connect_time) * 1000
                    logger.info(
                        f"[Latency] [{self._parent.exchange_name}] "
                        f"First data received in {conn_to_data_ms:.0f}ms "
                        f"after connect"
                    )
            except Exception as e:
                logger.debug(f"[{self._parent.exchange_name}] Parse error: {e}")

    async def _keep_alive(self, ws: Any) -> None:
        """Send {"method": "PING"} every 15 seconds."""
        while self._parent._running:
            try:
                await ws.send(json.dumps({"method": "PING"}))
            except Exception:
                break
            await asyncio.sleep(15)

    async def _staleness_watchdog(self, ws: Any) -> None:
        """Force reconnect if no data received for 30 seconds."""
        while self._parent._running:
            await asyncio.sleep(5.0)
            if self._last_data_time > 0:
                stale = time.time() - self._last_data_time
                if stale >= self._parent.STALENESS_RECONNECT_SECONDS:
                    logger.warning(
                        f"[{self._parent.exchange_name}] Sub-connection stale "
                        f"({stale:.0f}s, {len(self._symbols)} symbols), "
                        f"reconnecting"
                    )
                    self._last_data_time = 0.0
                    await ws.close()
                    return


class _MEXCDepthSubFetcher:
    """Internal helper: single MEXC WS connection for depth data (≤30 symbols)."""

    def __init__(self, parent: MEXCFetcher, symbols: list[str]) -> None:
        self._parent = parent
        self._symbols = symbols
        self._last_data_time: float = 0.0
        self._connect_count: int = 0
        self._connected_at: float = 0.0

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
                    f"[{self._parent.exchange_name}] Depth sub-connection error: {e}"
                )
                await asyncio.sleep(delay)
                delay = min(delay * RECONNECT_BACKOFF_FACTOR, RECONNECT_MAX_DELAY)

    async def _connect_and_listen(self) -> None:
        url = self._parent._build_ws_url()
        kwargs = self._parent._ws_connect_kwargs()

        async with websockets.connect(url, **kwargs) as ws:
            self._connected_at = time.time()
            self._last_data_time = 0.0
            self._parent._ws_connected = True
            self._connect_count += 1
            if self._connect_count == 1:
                logger.info(
                    f"[{self._parent.exchange_name}] Depth sub-connection for "
                    f"{len(self._symbols)} symbols connected"
                )
            elif self._connect_count % 10 == 0:
                logger.info(
                    f"[{self._parent.exchange_name}] Depth sub-connection "
                    f"reconnected ({self._connect_count} times)"
                )

            # Subscribe to depth channel
            params = [
                f"spot@public.depth.v3.api.pb@100ms@{s}"
                for s in self._symbols
            ]
            await ws.send(json.dumps({"method": "SUBSCRIPTION", "params": params}))
            if self._connect_count == 1:
                logger.info(
                    f"[{self._parent.exchange_name}] Subscribed to "
                    f"{len(self._symbols)} depth channels"
                )

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
            # Surface listener/keepalive/staleness crashes — without this the
            # exception goes silent at GC time (S21 silent-task-exception fix).
            for t in done:
                try:
                    t.result()
                except Exception as e:
                    logger.warning(f"[MEXC] task crashed: {type(e).__name__}: {e}")

    async def _listen(self, ws: Any) -> None:
        async for raw in ws:
            if not self._parent._running:
                break
            try:
                if isinstance(raw, str):
                    continue

                result = _parse_depth_pb(raw)
                if result is None:
                    continue

                symbol, bids, asks, send_time_ms = result
                if symbol not in self._parent._state:
                    continue

                now = time.time()
                existing = self._parent._state[symbol]

                # Merge depth into existing state (preserve bookTicker fields)
                self._parent._state[symbol] = PriceState(
                    bid=bids[0][0] if bids else existing.bid,
                    ask=asks[0][0] if asks else existing.ask,
                    bid_qty=bids[0][1] if bids else existing.bid_qty,
                    ask_qty=asks[0][1] if asks else existing.ask_qty,
                    last_price=existing.last_price,
                    volume=existing.volume,
                    updated_at=existing.updated_at,
                    received_at=now,
                    book_received_at=now,
                    bids=bids or None,
                    asks=asks or None,
                )
                self._parent._last_data_received = now
                self._last_data_time = now
                self._parent._message_count += 1

            except Exception as e:
                logger.debug(f"[{self._parent.exchange_name}] Depth parse error: {e}")

    async def _keep_alive(self, ws: Any) -> None:
        while self._parent._running:
            try:
                await ws.send(json.dumps({"method": "PING"}))
            except Exception:
                break
            await asyncio.sleep(15)

    async def _staleness_watchdog(self, ws: Any) -> None:
        while self._parent._running:
            await asyncio.sleep(5.0)
            ref_time = self._last_data_time or self._connected_at
            if ref_time <= 0:
                continue
            stale = time.time() - ref_time
            if stale < self._parent.STALENESS_RECONNECT_SECONDS:
                continue
            if self._last_data_time <= 0:
                logger.warning(
                    f"[{self._parent.exchange_name}] Depth sub-connection received "
                    f"no initial depth data for {stale:.0f}s, reconnecting"
                )
            elif self._connect_count <= 1:
                logger.warning(
                    f"[{self._parent.exchange_name}] Depth sub-connection stale "
                    f"({stale:.0f}s), reconnecting"
                )
            self._last_data_time = 0.0
            await ws.close()
            return
