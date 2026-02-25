"""
Binance testnet executor.

Places spot market orders on https://testnet.binance.vision using the same
HMAC-SHA256 auth pattern as demo_fetcher._fetch_binance().

Endpoints:
  POST /api/v3/order — place market order
  GET  /api/v3/order — query order status
  GET  /api/v3/account — query balances
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import aiohttp

from config import BINANCE_TESTNET_API_KEY, BINANCE_TESTNET_API_SECRET
from executor import ExecutionEngine, RateLimiter, TradeResult

if TYPE_CHECKING:
    from exchange_info import ExchangeInfoManager

logger = logging.getLogger(__name__)

_BASE_URL = "https://testnet.binance.vision"

# Coin symbol → our USDT pair mapping (for balance queries)
_COIN_TO_SYMBOL: dict[str, str] = {}  # populated from SYMBOLS if needed


class BinanceExecutor(ExecutionEngine):
    """Binance testnet spot market order executor."""

    def __init__(self, exchange_info: ExchangeInfoManager | None = None) -> None:
        super().__init__("Binance", exchange_info)
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter = RateLimiter(max_requests=100, window_seconds=60)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    def _sign(self, params: dict) -> str:
        """Create HMAC-SHA256 signature for query string."""
        query = urlencode(params)
        sig = hmac.new(
            BINANCE_TESTNET_API_SECRET.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{query}&signature={sig}"

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": BINANCE_TESTNET_API_KEY}

    def format_symbol(self, symbol: str) -> str:
        """Binance uses BTCUSDT format (same as ours)."""
        return symbol

    async def place_market_order(
        self, symbol: str, side: str, qty: float, client_order_id: str,
        expected_price: float = 0.0,
    ) -> TradeResult:
        """Place a spot market order on Binance testnet."""
        if not await self._rate_limiter.acquire():
            return self._failed_result(
                symbol, side, qty, expected_price,
                "rate_limited", client_order_id,
            )

        session = await self._ensure_session()
        t0 = time.time()

        params = {
            "symbol": self.format_symbol(symbol),
            "side": side.upper(),
            "type": "MARKET",
            "quantity": f"{qty:.8f}".rstrip("0").rstrip("."),
            "newClientOrderId": client_order_id,
            "timestamp": str(int(time.time() * 1000)),
        }

        signed_query = self._sign(params)
        url = f"{_BASE_URL}/api/v3/order?{signed_query}"

        try:
            async with session.post(url, headers=self._headers()) as resp:
                data = await resp.json()

            latency = (time.time() - t0) * 1000.0

            if resp.status != 200 or "orderId" not in data:
                error = data.get("msg", str(data))
                code = data.get("code", resp.status)
                logger.warning(
                    f"[BinanceExec] Order rejected: {symbol} {side} "
                    f"qty={qty} — {code}: {error}"
                )
                return self._failed_result(
                    symbol, side, qty, expected_price,
                    f"{code}: {error}", client_order_id,
                )

            # Parse fill details from response
            return self._parse_order_response(
                data, symbol, side, qty, expected_price,
                client_order_id, latency,
            )

        except Exception as e:
            latency = (time.time() - t0) * 1000.0
            logger.error(f"[BinanceExec] Order exception: {symbol} {side} — {e}")
            return self._failed_result(
                symbol, side, qty, expected_price,
                f"exception: {e}", client_order_id,
            )

    def _parse_order_response(
        self, data: dict, symbol: str, side: str, qty: float,
        expected_price: float, client_order_id: str, latency: float,
    ) -> TradeResult:
        """Parse Binance order response into TradeResult."""
        order_id = str(data.get("orderId", ""))
        status = data.get("status", "")
        executed_qty = float(data.get("executedQty", "0"))
        cum_quote_qty = float(data.get("cummulativeQuoteQty", "0"))

        # Calculate weighted average price from fills
        fills = data.get("fills", [])
        total_qty = 0.0
        total_cost = 0.0
        total_commission = 0.0
        commission_asset = ""
        is_maker = False

        for fill in fills:
            fill_price = float(fill.get("price", "0"))
            fill_qty = float(fill.get("qty", "0"))
            commission = float(fill.get("commission", "0"))
            comm_asset = fill.get("commissionAsset", "")

            total_qty += fill_qty
            total_cost += fill_price * fill_qty
            total_commission += commission
            if not commission_asset:
                commission_asset = comm_asset

        avg_price = total_cost / total_qty if total_qty > 0 else 0.0

        # Fallback: if no fills array, use cummulativeQuoteQty / executedQty
        if avg_price == 0 and executed_qty > 0 and cum_quote_qty > 0:
            avg_price = cum_quote_qty / executed_qty

        # Determine fee rate
        fee_rate = 0.0
        if total_commission > 0 and total_cost > 0:
            fee_rate = total_commission / total_cost if commission_asset == "USDT" else 0.0

        success = status == "FILLED" or executed_qty > 0

        return TradeResult(
            success=success,
            order_id=order_id,
            client_order_id=client_order_id,
            exchange=self.exchange_name,
            symbol=symbol,
            side=side,
            requested_qty=qty,
            filled_qty=executed_qty,
            requested_price=expected_price,
            actual_avg_price=avg_price,
            actual_fee=total_commission,
            fee_rate=fee_rate,
            fee_currency=commission_asset,
            is_maker=is_maker,
            latency_ms=latency,
            raw_response=data,
            timestamp=time.time(),
        )

    async def get_order_status(self, symbol: str, order_id: str) -> TradeResult:
        """Query order status by orderId or origClientOrderId."""
        session = await self._ensure_session()

        params = {
            "symbol": self.format_symbol(symbol),
            "timestamp": str(int(time.time() * 1000)),
        }

        # Determine if order_id is our client ID or exchange order ID
        if order_id.startswith("coirna-"):
            params["origClientOrderId"] = order_id
        else:
            params["orderId"] = order_id

        signed_query = self._sign(params)
        url = f"{_BASE_URL}/api/v3/order?{signed_query}"

        try:
            async with session.get(url, headers=self._headers()) as resp:
                data = await resp.json()

            if resp.status != 200:
                return self._failed_result(
                    symbol, "", 0, 0,
                    data.get("msg", str(data)), order_id,
                )

            side = data.get("side", "").lower()
            return self._parse_order_response(
                data, symbol, side, float(data.get("origQty", "0")),
                0.0, data.get("clientOrderId", order_id), 0.0,
            )

        except Exception as e:
            return self._failed_result(symbol, "", 0, 0, str(e), order_id)

    async def get_balance(self, asset: str) -> float:
        """Get available balance for an asset."""
        session = await self._ensure_session()

        params = {"timestamp": str(int(time.time() * 1000))}
        signed_query = self._sign(params)
        url = f"{_BASE_URL}/api/v3/account?{signed_query}"

        async with session.get(url, headers=self._headers()) as resp:
            data = await resp.json()

        for bal in data.get("balances", []):
            if bal["asset"] == asset:
                return float(bal["free"]) + float(bal["locked"])

        return 0.0

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
