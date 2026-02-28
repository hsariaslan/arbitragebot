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

from config import MEXC_EXCHANGE_NAME, MEXC_WS_URL
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

                price_data = PriceState(
                    bid=bid,
                    ask=ask,
                    bid_qty=bid_qty,
                    ask_qty=ask_qty,
                    last_price="",
                    volume="",
                    updated_at=updated_at,
                    received_at=now,
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
