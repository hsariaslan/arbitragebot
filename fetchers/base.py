"""
Abstract base class for exchange WebSocket fetchers.

Handles all exchange-agnostic logic:
- WebSocket connection lifecycle with automatic reconnection
- In-memory price state management
- Periodic CSV snapshots
- Graceful shutdown

Subclasses implement only exchange-specific parts:
- exchange_name property
- _build_ws_url() for WebSocket URL construction
- _parse_message() for exchange-specific JSON parsing
- _on_connect() (optional) for post-connect subscription messages
"""

import abc
import asyncio
import csv
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import websockets

from config import (
    CSV_COLUMNS,
    DATA_DIR,
    RECONNECT_BACKOFF_FACTOR,
    RECONNECT_INITIAL_DELAY,
    RECONNECT_MAX_DELAY,
    SNAPSHOT_INTERVAL_SECONDS,
    SYMBOLS,
)

logger = logging.getLogger(__name__)


@dataclass
class PriceState:
    """Latest price data for a single symbol."""

    bid: str = ""
    ask: str = ""
    bid_qty: str = ""
    ask_qty: str = ""
    last_price: str = ""
    volume: str = ""
    updated_at: float = 0.0
    received_at: float = 0.0  # Local time when data was received (for staleness detection)


class BaseFetcher(abc.ABC):
    """
    Abstract base class for exchange WebSocket data fetchers.

    Manages WebSocket lifecycle, in-memory price state, CSV snapshots,
    console output, and automatic reconnection with exponential backoff.

    Subclasses must implement:
        exchange_name (property) - exchange identifier string
        _build_ws_url() - WebSocket URL with stream subscriptions
        _parse_message(raw) - parse exchange JSON into (symbol, PriceState)
    """

    # If no fresh data received for this many seconds, force reconnect
    STALENESS_RECONNECT_SECONDS: float = 30.0

    def __init__(self, symbols: list[str] | None = None) -> None:
        self.symbols: list[str] = symbols or SYMBOLS
        self._state: dict[str, PriceState] = {s: PriceState() for s in self.symbols}
        self._running: bool = False
        self._ws_connected: bool = False
        self._output_dir: Path = Path(DATA_DIR) / self.exchange_name
        self._csv_files_initialized: set[str] = set()
        self._reconnect_delay: float = RECONNECT_INITIAL_DELAY
        self._message_count: int = 0
        self._last_snapshot_time: float = 0.0
        self._last_data_received: float = 0.0  # for staleness detection

    @property
    @abc.abstractmethod
    def exchange_name(self) -> str:
        """Return the exchange name (e.g., 'Binance')."""
        ...

    @abc.abstractmethod
    def _build_ws_url(self) -> str:
        """Build the WebSocket URL including all stream subscriptions."""
        ...

    @abc.abstractmethod
    def _parse_message(self, raw_message: dict[str, Any]) -> tuple[str, PriceState] | None:
        """
        Parse a raw WebSocket message into (symbol, PriceState).

        Returns None if the message is not a price update.
        """
        ...

    async def _on_connect(self, ws: Any) -> None:
        """
        Called after WebSocket connection is established.

        Override in subclasses that need to send subscription messages
        after connecting (e.g., OKX, Bybit). Default does nothing.
        """

    async def _keep_alive(self, ws: Any) -> None:
        """
        Send periodic application-level keep-alive messages.

        Override in subclasses that require application-level pings
        (OKX, Bybit, MEXC). Default does nothing — just waits until
        the fetcher is stopped.
        """
        while self._running and self._ws_connected:
            await asyncio.sleep(1.0)

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """
        Return kwargs for websockets.connect().

        Override in subclasses that need different ping/connection settings.
        Default returns Binance-compatible settings (library-level ping).
        """
        return {
            "ping_interval": 20,
            "ping_timeout": 60,
            "close_timeout": 10,
            "max_size": 2**20,
        }

    def get_state(self) -> dict[str, PriceState]:
        """Return a reference to the current price state dictionary."""
        return self._state

    async def run(self) -> None:
        """Main entry point. Connects to WebSocket and runs until stopped."""
        self._running = True
        self._ensure_output_dir()
        logger.info(f"[{self.exchange_name}] Starting fetcher for {len(self.symbols)} symbols")

        while self._running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                if not self._running:
                    break
                logger.error(f"[{self.exchange_name}] Connection error: {e}")
                await self._handle_reconnect()

        logger.info(f"[{self.exchange_name}] Fetcher stopped")

    def stop(self) -> None:
        """Signal the fetcher to stop gracefully."""
        self._running = False
        logger.info(f"[{self.exchange_name}] Stop requested")

    async def _connect_and_listen(self) -> None:
        """Establish WebSocket connection and run listener + snapshot + keep-alive + staleness tasks."""
        url = self._build_ws_url()
        logger.info(f"[{self.exchange_name}] Connecting...")

        async with websockets.connect(url, **self._ws_connect_kwargs()) as ws:
            self._ws_connected = True
            self._reconnect_delay = RECONNECT_INITIAL_DELAY
            self._last_data_received = time.time()
            logger.info(f"[{self.exchange_name}] Connected successfully")

            await self._on_connect(ws)

            listener_task = asyncio.create_task(self._listen(ws))
            snapshot_task = asyncio.create_task(self._snapshot_loop())
            keepalive_task = asyncio.create_task(self._keep_alive(ws))
            staleness_task = asyncio.create_task(self._staleness_watchdog(ws))

            try:
                done, pending = await asyncio.wait(
                    [listener_task, snapshot_task, keepalive_task, staleness_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                for task in done:
                    task.result()
            finally:
                self._ws_connected = False

    async def _listen(self, ws: Any) -> None:
        """Listen for WebSocket messages and update in-memory state."""
        async for raw in ws:
            if not self._running:
                break

            try:
                message = json.loads(raw)
                result = self._parse_message(message)
                if result is not None:
                    symbol, price_data = result
                    if symbol in self._state:
                        now = time.time()
                        price_data.received_at = now
                        self._last_data_received = now
                        self._state[symbol] = price_data
                        self._message_count += 1
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.debug(f"[{self.exchange_name}] Parse error: {e}")

    async def _snapshot_loop(self) -> None:
        """Periodically snapshot state to CSV."""
        while self._running and self._ws_connected:
            now = time.time()
            next_snapshot = self._last_snapshot_time + SNAPSHOT_INTERVAL_SECONDS

            if now < next_snapshot:
                await asyncio.sleep(next_snapshot - now)
                continue

            self._last_snapshot_time = now
            self._take_snapshot(now)

    def _take_snapshot(self, timestamp: float) -> None:
        """Write current state to CSV files."""
        ts_str = f"{timestamp:.3f}"

        for symbol in self.symbols:
            state = self._state[symbol]
            self._append_csv(symbol, ts_str, state)

    def _ensure_output_dir(self) -> None:
        """Create the output directory if it does not exist."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def _append_csv(self, symbol: str, timestamp_str: str, state: PriceState) -> None:
        """Append a single row to the symbol's CSV file."""
        csv_path = self._output_dir / f"{symbol}.csv"

        if symbol not in self._csv_files_initialized:
            if not csv_path.exists() or csv_path.stat().st_size == 0:
                with open(csv_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(CSV_COLUMNS)
            self._csv_files_initialized.add(symbol)

        with open(csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp_str,
                state.bid,
                state.ask,
                state.bid_qty,
                state.ask_qty,
                state.last_price,
                state.volume,
            ])

    async def _handle_reconnect(self) -> None:
        """Wait with exponential backoff before reconnecting."""
        delay = self._reconnect_delay
        logger.warning(f"[{self.exchange_name}] Reconnecting in {delay:.1f}s...")
        await asyncio.sleep(delay)
        self._reconnect_delay = min(
            self._reconnect_delay * RECONNECT_BACKOFF_FACTOR,
            RECONNECT_MAX_DELAY,
        )

    async def _staleness_watchdog(self, ws: Any) -> None:
        """Force reconnect if no fresh data received for STALENESS_RECONNECT_SECONDS."""
        while self._running and self._ws_connected:
            await asyncio.sleep(5.0)
            if self._last_data_received > 0:
                stale_secs = time.time() - self._last_data_received
                if stale_secs >= self.STALENESS_RECONNECT_SECONDS:
                    logger.warning(
                        f"[{self.exchange_name}] No data for {stale_secs:.0f}s, "
                        f"forcing reconnect"
                    )
                    await ws.close()
                    return
