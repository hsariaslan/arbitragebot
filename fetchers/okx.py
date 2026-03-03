"""
OKX Spot WebSocket fetcher.

Connects to OKX public WebSocket API v5 and streams real-time ticker data
for all configured symbols using the tickers channel.

OKX tickers channel fields:
    bidPx = best bid price,     bidSz = best bid size
    askPx = best ask price,     askSz = best ask size
    last  = last traded price
    vol24h = 24h volume (base currency)
    ts    = timestamp (ms since epoch)

Connection notes:
    - Subscription is done post-connect via JSON message
    - Symbols use hyphen format: BTC-USDT (converted from BTCUSDT)
    - Application-level ping: send "ping" string, receive "pong" string
    - Must ping within 30s of last received message
"""

import asyncio
import json
import logging
from typing import Any

from config import OKX_EXCHANGE_NAME, OKX_WS_URL
from fetchers.base import BaseFetcher, PriceState

logger = logging.getLogger(__name__)


class OKXFetcher(BaseFetcher):
    """OKX Spot WebSocket fetcher using the tickers channel."""

    @property
    def exchange_name(self) -> str:
        return OKX_EXCHANGE_NAME

    def _build_ws_url(self) -> str:
        return OKX_WS_URL

    @staticmethod
    def _to_okx_symbol(symbol: str) -> str:
        """Convert 'BTCUSDT' to 'BTC-USDT' for OKX instId format."""
        if symbol.endswith("USDT"):
            return f"{symbol[:-4]}-USDT"
        return symbol

    @staticmethod
    def _from_okx_symbol(inst_id: str) -> str:
        """Convert 'BTC-USDT' back to 'BTCUSDT' for internal state keys."""
        return inst_id.replace("-", "")

    async def _on_connect(self, ws: Any) -> None:
        """Send subscription for tickers + books5 after connecting."""
        args = []
        for s in self.symbols:
            inst = self._to_okx_symbol(s)
            args.append({"channel": "tickers", "instId": inst})
            args.append({"channel": "books5", "instId": inst})
        await ws.send(json.dumps({"op": "subscribe", "args": args}))
        logger.info(f"[{self.exchange_name}] Subscribed to {len(self.symbols)} tickers + books5")

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Disable library-level ping; OKX uses application-level 'ping' string."""
        return {
            "ping_interval": None,
            "ping_timeout": None,
            "close_timeout": 10,
            "max_size": 2**20,
        }

    async def _keep_alive(self, ws: Any) -> None:
        """Send 'ping' string every 15 seconds (OKX requires within 30s)."""
        while self._running and self._ws_connected:
            try:
                await ws.send("ping")
            except Exception:
                break
            await asyncio.sleep(15)

    def _parse_message(self, raw_message: dict[str, Any]) -> tuple[str, PriceState] | None:
        """
        Parse an OKX tickers or books5 channel push message.

        Tickers: {"arg": {"channel": "tickers", "instId": "BTC-USDT"},
                  "data": [{"bidPx": ..., "askPx": ..., ...}]}
        Books5:  {"arg": {"channel": "books5", "instId": "BTC-USDT"},
                  "data": [{"bids": [["price","qty","0","N"], ...],
                            "asks": [["price","qty","0","N"], ...], "ts": "..."}]}
        """
        data_list = raw_message.get("data")
        if not data_list:
            return None

        arg = raw_message.get("arg", {})
        channel = arg.get("channel", "")
        inst_id = arg.get("instId", "")
        symbol = self._from_okx_symbol(inst_id)

        if channel == "books5":
            data = data_list[0]
            existing = self._state.get(symbol, PriceState())

            bids_raw = data.get("bids", [])
            asks_raw = data.get("asks", [])

            # OKX books5 format: [price, qty, deprecated, numOrders]
            depth_bids = [(b[0], b[1]) for b in bids_raw if len(b) >= 2] or None
            depth_asks = [(a[0], a[1]) for a in asks_raw if len(a) >= 2] or None

            ts_raw = data.get("ts", "0")
            try:
                updated_at = int(ts_raw) / 1000.0
            except (ValueError, TypeError):
                updated_at = existing.updated_at

            price_state = PriceState(
                bid=bids_raw[0][0] if bids_raw else existing.bid,
                ask=asks_raw[0][0] if asks_raw else existing.ask,
                bid_qty=bids_raw[0][1] if bids_raw else existing.bid_qty,
                ask_qty=asks_raw[0][1] if asks_raw else existing.ask_qty,
                last_price=existing.last_price,
                volume=existing.volume,
                updated_at=updated_at,
                bids=depth_bids,
                asks=depth_asks,
            )
            return symbol, price_state

        if channel != "tickers":
            return None

        data = data_list[0]

        ts_raw = data.get("ts", "0")
        try:
            updated_at = int(ts_raw) / 1000.0
        except (ValueError, TypeError):
            updated_at = 0.0

        existing = self._state.get(symbol, PriceState())

        price_state = PriceState(
            bid=data.get("bidPx", ""),
            ask=data.get("askPx", ""),
            bid_qty=data.get("bidSz", ""),
            ask_qty=data.get("askSz", ""),
            last_price=data.get("last", ""),
            volume=data.get("vol24h", ""),
            updated_at=updated_at,
            bids=existing.bids,
            asks=existing.asks,
        )

        return symbol, price_state
