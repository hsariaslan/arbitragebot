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
        """Send subscription for all symbol tickers after connecting."""
        args = [
            {"channel": "tickers", "instId": self._to_okx_symbol(s)}
            for s in self.symbols
        ]
        await ws.send(json.dumps({"op": "subscribe", "args": args}))
        logger.info(f"[{self.exchange_name}] Subscribed to {len(self.symbols)} tickers")

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
        Parse an OKX tickers channel push message.

        Format: {"arg": {"channel": "tickers", "instId": "BTC-USDT"},
                 "data": [{"bidPx": ..., "askPx": ..., ...}]}
        Returns None for subscription confirmations or other non-data messages.
        """
        data_list = raw_message.get("data")
        if not data_list:
            return None

        arg = raw_message.get("arg", {})
        if arg.get("channel") != "tickers":
            return None

        data = data_list[0]
        inst_id = arg.get("instId", "")
        symbol = self._from_okx_symbol(inst_id)

        ts_raw = data.get("ts", "0")
        try:
            updated_at = int(ts_raw) / 1000.0
        except (ValueError, TypeError):
            updated_at = 0.0

        price_state = PriceState(
            bid=data.get("bidPx", ""),
            ask=data.get("askPx", ""),
            bid_qty=data.get("bidSz", ""),
            ask_qty=data.get("askSz", ""),
            last_price=data.get("last", ""),
            volume=data.get("vol24h", ""),
            updated_at=updated_at,
        )

        return symbol, price_state
