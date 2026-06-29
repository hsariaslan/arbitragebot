"""
Bybit demo executor.

Places spot market orders on https://api-demo.bybit.com using the same
HMAC-SHA256 auth pattern as demo_fetcher._fetch_bybit().

Endpoints:
  POST /v5/order/create — place market order
  GET  /v5/order/realtime — query order details
  GET  /v5/account/wallet-balance — query balances
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import TYPE_CHECKING

import aiohttp

from config import BYBIT_DEMO_API_KEY, BYBIT_DEMO_API_SECRET
from executor import ExecutionEngine, RateLimiter, TradeResult

if TYPE_CHECKING:
    from exchange_info import ExchangeInfoManager

logger = logging.getLogger(__name__)

_BASE_URL = "https://api-demo.bybit.com"


class BybitExecutor(ExecutionEngine):
    """Bybit demo spot market order executor."""

    def __init__(self, exchange_info: ExchangeInfoManager | None = None) -> None:
        super().__init__("Bybit", exchange_info)
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter = RateLimiter(max_requests=15, window_seconds=1)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    def _sign_headers(self, method: str, params_or_body: str) -> dict:
        """Create Bybit auth headers with HMAC-SHA256 signature."""
        ts = str(int(time.time() * 1000))
        recv_window = "5000"
        sign_str = f"{ts}{BYBIT_DEMO_API_KEY}{recv_window}{params_or_body}"
        signature = hmac.new(
            BYBIT_DEMO_API_SECRET.encode(),
            sign_str.encode(),
            hashlib.sha256,
        ).hexdigest()

        return {
            "X-BAPI-API-KEY": BYBIT_DEMO_API_KEY,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json",
        }

    def format_symbol(self, symbol: str) -> str:
        """Bybit uses BTCUSDT format (same as ours)."""
        return symbol

    async def place_market_order(
        self, symbol: str, side: str, qty: float, client_order_id: str,
        expected_price: float = 0.0,
    ) -> TradeResult:
        """Place a spot market order on Bybit demo."""
        if not await self._rate_limiter.acquire():
            return self._failed_result(
                symbol, side, qty, expected_price,
                "rate_limited", client_order_id,
            )

        session = await self._ensure_session()
        t0 = time.time()

        body_dict = {
            "category": "spot",
            "symbol": self.format_symbol(symbol),
            "side": side.capitalize(),  # "Buy" or "Sell"
            "orderType": "Market",
            "qty": f"{qty:.8f}".rstrip("0").rstrip("."),
            "orderLinkId": client_order_id[:36],  # Bybit max 36 chars
        }
        body = json.dumps(body_dict)

        headers = self._sign_headers("POST", body)
        url = f"{_BASE_URL}/v5/order/create"

        try:
            async with session.post(url, headers=headers, data=body) as resp:
                data = await resp.json()

            latency_submit = (time.time() - t0) * 1000.0

            ret_code = data.get("retCode", -1)
            if ret_code != 0:
                error = data.get("retMsg", str(data))
                count = self._rejected_symbols.get(symbol, 0) + 1
                self._rejected_symbols[symbol] = count
                if count == 1:
                    logger.warning(
                        f"[BybitExec] Order rejected: {symbol} {side} "
                        f"qty={qty} — {ret_code}: {error}"
                    )
                elif count == 2:
                    logger.info(
                        f"[BybitExec] {symbol} rejection repeated — "
                        f"suppressing further logs"
                    )
                return self._failed_result(
                    symbol, side, qty, expected_price,
                    f"{ret_code}: {error}", client_order_id,
                )

            result_data = data.get("result", {})
            order_id = result_data.get("orderId", "")

            if not order_id:
                return self._failed_result(
                    symbol, side, qty, expected_price,
                    "no orderId in response", client_order_id,
                )

            # Query fill details
            await asyncio.sleep(0.2)
            fill_result = await self._query_order(symbol, order_id, side,
                                                   qty, expected_price, client_order_id)
            fill_result.latency_ms = (time.time() - t0) * 1000.0
            return fill_result

        except Exception as e:
            logger.error(f"[BybitExec] Order exception: {symbol} {side} — {e}")
            return self._failed_result(
                symbol, side, qty, expected_price,
                f"exception: {e}", client_order_id,
            )

    async def place_marketable_limit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        client_order_id: str,
        limit_price: float,
        time_in_force: str = "IOC",
        expected_price: float = 0.0,
    ) -> TradeResult:
        """Place a limit IOC/FOK order that crosses the book with a price cap."""
        if not await self._rate_limiter.acquire():
            return self._failed_result(
                symbol,
                side,
                qty,
                expected_price,
                "rate_limited",
                client_order_id,
            )

        session = await self._ensure_session()
        t0 = time.time()
        price_dec = self.round_limit_price(symbol, side, limit_price)
        tif = "FOK" if time_in_force.upper() == "FOK" else "IOC"
        body_dict = {
            "category": "spot",
            "symbol": self.format_symbol(symbol),
            "side": side.capitalize(),
            "orderType": "Limit",
            "qty": f"{qty:.8f}".rstrip("0").rstrip("."),
            "price": format(price_dec, "f").rstrip("0").rstrip("."),
            "timeInForce": tif,
            "orderLinkId": client_order_id[:36],
        }
        body = json.dumps(body_dict)

        headers = self._sign_headers("POST", body)
        url = f"{_BASE_URL}/v5/order/create"

        try:
            async with session.post(url, headers=headers, data=body) as resp:
                data = await resp.json()

            ret_code = data.get("retCode", -1)
            if ret_code != 0:
                error = data.get("retMsg", str(data))
                count = self._rejected_symbols.get(symbol, 0) + 1
                self._rejected_symbols[symbol] = count
                if count == 1:
                    logger.warning(
                        f"[BybitExec] Limit {tif} rejected: "
                        f"{symbol} {side} qty={qty} price={body_dict['price']} — "
                        f"{ret_code}: {error}"
                    )
                elif count == 2:
                    logger.info(
                        f"[BybitExec] {symbol} limit rejection repeated — "
                        f"suppressing further logs"
                    )
                return self._failed_result(
                    symbol,
                    side,
                    qty,
                    expected_price,
                    f"{ret_code}: {error}",
                    client_order_id,
                )

            result_data = data.get("result", {})
            order_id = result_data.get("orderId", "")
            if not order_id:
                return self._failed_result(
                    symbol,
                    side,
                    qty,
                    expected_price,
                    "no orderId in response",
                    client_order_id,
                )

            await asyncio.sleep(0.2)
            fill_result = await self._query_order(
                symbol,
                order_id,
                side,
                qty,
                expected_price,
                client_order_id,
            )
            fill_result.latency_ms = (time.time() - t0) * 1000.0
            if fill_result.success and fill_result.fill_ratio < 0.999:
                fill_result.error = f"partial_fill:{fill_result.fill_ratio:.4f}"
            return fill_result

        except Exception as e:
            logger.error(f"[BybitExec] Limit order exception: {symbol} {side} — {e}")
            return self._failed_result(
                symbol,
                side,
                qty,
                expected_price,
                f"exception: {e}",
                client_order_id,
            )

    async def _query_order(
        self, symbol: str, order_id: str, side: str,
        qty: float, expected_price: float, client_order_id: str,
    ) -> TradeResult:
        """Query Bybit order details for fill information."""
        session = await self._ensure_session()

        params = f"category=spot&symbol={self.format_symbol(symbol)}&orderId={order_id}"
        headers = self._sign_headers("GET", params)
        url = f"{_BASE_URL}/v5/order/realtime?{params}"

        for attempt in range(3):
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()

            if data.get("retCode") != 0:
                if attempt < 2:
                    await asyncio.sleep(0.5)
                    continue
                return self._failed_result(
                    symbol, side, qty, expected_price,
                    f"order query failed: {data.get('retMsg', data)}",
                    client_order_id,
                )

            orders = data.get("result", {}).get("list", [])
            if not orders:
                if attempt < 2:
                    await asyncio.sleep(0.5)
                    continue
                return self._failed_result(
                    symbol, side, qty, expected_price,
                    "order not found in query",
                    client_order_id,
                )

            order = orders[0]
            status = order.get("orderStatus", "")

            if status in ("Filled", "PartiallyFilled"):
                avg_price = float(order.get("avgPrice", "0") or "0")
                cum_exec_qty = float(order.get("cumExecQty", "0") or "0")
                cum_exec_value = float(order.get("cumExecValue", "0") or "0")
                cum_exec_fee = float(order.get("cumExecFee", "0") or "0")

                # Bybit fee is typically in quote currency for spot
                fee = abs(cum_exec_fee)
                fee_rate = fee / cum_exec_value if cum_exec_value > 0 else 0
                actual_fee_usd = fee

                return TradeResult(
                    success=True,
                    order_id=order_id,
                    client_order_id=client_order_id,
                    exchange=self.exchange_name,
                    symbol=symbol,
                    side=side,
                    requested_qty=qty,
                    filled_qty=cum_exec_qty,
                    requested_price=expected_price,
                    actual_avg_price=avg_price,
                    actual_fee=fee,
                    actual_fee_usd=actual_fee_usd,
                    fee_rate=fee_rate,
                    fee_currency="USDT",  # Bybit spot typically charges in quote
                    is_maker=False,
                    raw_response=order,
                    timestamp=time.time(),
                )

            if status in ("Cancelled", "Rejected"):
                return self._failed_result(
                    symbol, side, qty, expected_price,
                    f"order {status.lower()}: {order.get('rejectReason', '')}",
                    client_order_id,
                )

            if attempt < 2:
                await asyncio.sleep(0.5)

        return self._failed_result(
            symbol, side, qty, expected_price,
            f"order not filled after retries (status={status})",
            client_order_id,
        )

    async def get_order_status(self, symbol: str, order_id: str) -> TradeResult:
        """Query order by orderId or orderLinkId."""
        if order_id.startswith("coirna-"):
            params = f"category=spot&symbol={self.format_symbol(symbol)}&orderLinkId={order_id[:36]}"
        else:
            params = f"category=spot&symbol={self.format_symbol(symbol)}&orderId={order_id}"

        session = await self._ensure_session()
        headers = self._sign_headers("GET", params)
        url = f"{_BASE_URL}/v5/order/realtime?{params}"

        async with session.get(url, headers=headers) as resp:
            data = await resp.json()

        if data.get("retCode") != 0:
            return self._failed_result(
                symbol, "", 0, 0,
                data.get("retMsg", str(data)), order_id,
            )

        orders = data.get("result", {}).get("list", [])
        if not orders:
            return self._failed_result(symbol, "", 0, 0, "order not found", order_id)

        order = orders[0]
        side = order.get("side", "").lower()
        return await self._query_order(
            symbol, order.get("orderId", order_id), side,
            float(order.get("qty", "0")), 0, order_id,
        )

    async def get_balance(self, asset: str) -> float:
        """Get available balance for an asset."""
        session = await self._ensure_session()

        params = "accountType=UNIFIED"
        headers = self._sign_headers("GET", params)
        url = f"{_BASE_URL}/v5/account/wallet-balance?{params}"

        async with session.get(url, headers=headers) as resp:
            data = await resp.json()

        if data.get("retCode") != 0:
            return 0.0

        for account in data.get("result", {}).get("list", []):
            for coin in account.get("coin", []):
                if coin.get("coin") == asset:
                    return float(coin.get("walletBalance", "0") or "0")

        return 0.0

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
