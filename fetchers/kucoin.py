"""
KuCoin Spot WebSocket fetcher.

Connects to KuCoin WebSocket API for spot market data. KuCoin requires a
two-step connection: first a REST call to obtain a temporary token, then
a WebSocket connection using that token.

KuCoin ticker fields (Classic API):
    bestBid     = best bid price
    bestBidSize = best bid quantity
    bestAsk     = best ask price
    bestAskSize = best ask quantity
    price       = last traded price
    size        = last trade size (no 24h volume in ticker)

Connection notes:
    - Must POST to /api/v1/bullet-public to get token + endpoint
    - Token valid for 24 hours
    - Symbol format: BTC-USDT (hyphenated)
    - Application-level ping: send {"type": "ping"}, receive {"type": "pong"}
    - Must ping every 18s (timeout after 10s without pong)
    - Can subscribe to multiple symbols in one topic with comma separation
"""

import asyncio
import json
import logging
import time
import urllib.request
from typing import Any

from config import KUCOIN_EXCHANGE_NAME, KUCOIN_TOKEN_URL
from fetchers.base import BaseFetcher, PriceState

logger = logging.getLogger(__name__)


class KuCoinFetcher(BaseFetcher):
    """KuCoin Spot WebSocket fetcher using the Classic ticker channel."""

    def __init__(self, symbols: list[str] | None = None) -> None:
        self._ws_url: str = ""
        super().__init__(symbols)

    @property
    def exchange_name(self) -> str:
        return KUCOIN_EXCHANGE_NAME

    def _build_ws_url(self) -> str:
        return self._ws_url

    @staticmethod
    def _to_kucoin_symbol(symbol: str) -> str:
        """Convert BTCUSDT -> BTC-USDT."""
        if symbol.endswith("USDT"):
            return f"{symbol[:-4]}-USDT"
        return symbol

    @staticmethod
    def _from_kucoin_symbol(kc_symbol: str) -> str:
        """Convert BTC-USDT -> BTCUSDT."""
        return kc_symbol.replace("-", "")

    def _fetch_token(self) -> None:
        """Fetch a public WebSocket token from KuCoin REST API."""
        req = urllib.request.Request(
            KUCOIN_TOKEN_URL,
            method="POST",
            data=b"",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        token = data["data"]["token"]
        endpoint = data["data"]["instanceServers"][0]["endpoint"]
        self._ws_url = f"{endpoint}?token={token}"
        logger.info(f"[{self.exchange_name}] Obtained WebSocket token")

    async def _connect_and_listen(self) -> None:
        """Fetch token before connecting (overrides base to add token step)."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._fetch_token)
        await super()._connect_and_listen()

    async def _on_connect(self, ws: Any) -> None:
        """Subscribe to all tickers (avoids topic length limits with 60+ symbols)."""
        msg = {
            "id": str(int(time.time() * 1000)),
            "type": "subscribe",
            "topic": "/market/ticker:all",
            "privateChannel": False,
            "response": True,
        }
        await ws.send(json.dumps(msg))
        logger.info(f"[{self.exchange_name}] Subscribed to all tickers (filtering {len(self.symbols)} symbols)")

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Disable library-level ping; KuCoin uses application-level JSON ping."""
        return {
            "ping_interval": None,
            "ping_timeout": None,
            "close_timeout": 10,
            "max_size": 2**20,
        }

    async def _keep_alive(self, ws: Any) -> None:
        """Send {"type": "ping"} every 18 seconds."""
        while self._running and self._ws_connected:
            try:
                msg = {"id": str(int(time.time() * 1000)), "type": "ping"}
                await ws.send(json.dumps(msg))
            except Exception:
                break
            await asyncio.sleep(18)

    def _parse_message(self, raw_message: dict[str, Any]) -> tuple[str, PriceState] | None:
        """
        Parse a KuCoin ticker push message.

        Single symbol: {"type": "message", "topic": "/market/ticker:BTC-USDT",
                        "subject": "trade.ticker", "data": {...}}
        All tickers:   {"type": "message", "topic": "/market/ticker:all",
                        "subject": "BTC-USDT", "data": {...}}
        """
        msg_type = raw_message.get("type", "")
        if msg_type != "message":
            return None

        topic = raw_message.get("topic", "")
        if "/market/ticker" not in topic:
            return None

        data = raw_message.get("data")
        if data is None:
            return None

        subject = raw_message.get("subject", "")

        # Determine symbol: from topic for single-symbol, from subject for :all
        if topic == "/market/ticker:all":
            kc_symbol = subject
        else:
            # subject is "trade.ticker", symbol is in topic after ":"
            parts = topic.split(":")
            kc_symbol = parts[1] if len(parts) > 1 else ""

        symbol = self._from_kucoin_symbol(kc_symbol)

        ts_raw = data.get("time", 0)
        try:
            updated_at = int(ts_raw) / 1000.0
        except (ValueError, TypeError):
            updated_at = 0.0

        price_state = PriceState(
            bid=str(data.get("bestBid", "")),
            ask=str(data.get("bestAsk", "")),
            bid_qty=str(data.get("bestBidSize", "")),
            ask_qty=str(data.get("bestAskSize", "")),
            last_price=str(data.get("price", "")),
            volume="",  # Ticker channel does not include 24h volume
            updated_at=updated_at,
        )

        return symbol, price_state
