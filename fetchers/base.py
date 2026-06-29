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
    CSV_MAX_FILE_MB,
    CSV_COLUMNS,
    CSV_SNAPSHOTS_ENABLED,
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
    book_received_at: float = 0.0  # Local time when order-book depth was received
    # Multi-level order book (up to 5 levels)
    # bids: [(price_str, qty_str), ...] descending by price
    # asks: [(price_str, qty_str), ...] ascending by price
    bids: list[tuple[str, str]] | None = None
    asks: list[tuple[str, str]] | None = None


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

    # Event-driven exchanges (e.g., Bitfinex) send updates only on price
    # changes, not at fixed intervals. Their high "freshness" values (10s+)
    # reflect market inactivity, not stale/inaccurate data.
    IS_EVENT_DRIVEN: bool = False

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
        # CSV write timing diagnostics — measured per snapshot batch.
        # Useful for detecting filesystem slowdown over long sessions.
        self._csv_write_total_ms: float = 0.0
        self._csv_write_count: int = 0
        self._csv_last_log_ts: float = 0.0
        # Latency tracking
        self._connect_time: float = 0.0  # when WS connection was established
        self._first_data_time: float = 0.0  # when first price data arrived
        self._latency_samples: list[float] = []  # recent message processing times (ms)
        self._last_latency_log: float = 0.0  # last time latency was logged
        self._latency_log_interval: float = 60.0  # log latency stats every 60s

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
        if CSV_SNAPSHOTS_ENABLED:
            self._ensure_output_dir()
        else:
            logger.info(f"[{self.exchange_name}] CSV snapshots disabled")
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
            self._connect_time = time.time()
            self._first_data_time = 0.0
            self._last_data_received = self._connect_time
            logger.info(f"[{self.exchange_name}] Connected successfully")

            await self._on_connect(ws)

            tasks = [
                asyncio.create_task(self._listen(ws)),
                asyncio.create_task(self._keep_alive(ws)),
                asyncio.create_task(self._staleness_watchdog(ws)),
                asyncio.create_task(self._latency_log_loop()),
            ]
            if CSV_SNAPSHOTS_ENABLED:
                tasks.append(asyncio.create_task(self._snapshot_loop()))

            try:
                done, pending = await asyncio.wait(
                    tasks,
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
                t0 = time.time()
                message = json.loads(raw)
                result = self._parse_message(message)
                if result is not None:
                    symbol, price_data = result
                    if symbol in self._state:
                        now = time.time()
                        existing = self._state[symbol]
                        if price_data.book_received_at < 0:
                            price_data.book_received_at = now
                        elif price_data.book_received_at <= 0:
                            price_data.book_received_at = existing.book_received_at
                        price_data.received_at = now
                        self._last_data_received = now
                        self._state[symbol] = price_data
                        self._message_count += 1
                        # Track message processing latency
                        proc_ms = (now - t0) * 1000
                        self._latency_samples.append(proc_ms)
                        # Log first data received after connect
                        if self._first_data_time == 0.0:
                            self._first_data_time = now
                            conn_to_data_ms = (now - self._connect_time) * 1000
                            logger.info(
                                f"[Latency] [{self.exchange_name}] "
                                f"First data received in {conn_to_data_ms:.0f}ms "
                                f"after connect"
                            )
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
        t_start = time.monotonic()
        for symbol in self.symbols:
            state = self._state[symbol]
            self._append_csv(symbol, ts_str, state)
        elapsed_ms = (time.monotonic() - t_start) * 1000.0
        self._csv_write_total_ms += elapsed_ms
        self._csv_write_count += 1
        # Per-minute aggregate log — confirms whether CSV writes are the
        # cause of `yield` time growth in the orchestrator's [Capacity] log.
        now = timestamp
        if now - self._csv_last_log_ts >= 60.0 and self._csv_write_count > 0:
            avg_ms = self._csv_write_total_ms / self._csv_write_count
            logger.info(
                f"[CSV] {self.exchange_name}: avg={avg_ms:.1f}ms/snapshot "
                f"({self._csv_write_count} snapshots in last min, "
                f"{len(self.symbols)} files/snapshot)"
            )
            self._csv_write_total_ms = 0.0
            self._csv_write_count = 0
            self._csv_last_log_ts = now

    def _ensure_output_dir(self) -> None:
        """Create the output directory if it does not exist."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def _append_csv(self, symbol: str, timestamp_str: str, state: PriceState) -> None:
        """Append a single row to the symbol's CSV file."""
        csv_path = self._output_dir / f"{symbol}.csv"

        if CSV_MAX_FILE_MB > 0 and csv_path.exists():
            max_bytes = int(CSV_MAX_FILE_MB * 1024 * 1024)
            if csv_path.stat().st_size >= max_bytes:
                self._csv_files_initialized.add(symbol)
                with open(csv_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(CSV_COLUMNS)

        needs_header = not csv_path.exists() or csv_path.stat().st_size == 0
        if symbol not in self._csv_files_initialized or needs_header:
            if needs_header:
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

    async def _latency_log_loop(self) -> None:
        """Periodically log latency statistics."""
        # Wait for initial data to accumulate
        await asyncio.sleep(self._latency_log_interval)

        while self._running and self._ws_connected:
            samples = self._latency_samples
            if samples:
                count = len(samples)
                avg_ms = sum(samples) / count
                min_ms = min(samples)
                max_ms = max(samples)
                # Keep only last 1000 samples
                self._latency_samples = samples[-1000:] if count > 1000 else []

                # Compute data freshness: separate active vs dormant symbols
                now = time.time()
                _MAX_FRESHNESS_AGE_MS = 120_000  # 2 minutes
                active_ages: list[float] = []
                dormant_count = 0
                for s in self._state.values():
                    if s.received_at > 0:
                        age_ms = (now - s.received_at) * 1000
                        if age_ms <= _MAX_FRESHNESS_AGE_MS:
                            active_ages.append(age_ms)
                        else:
                            dormant_count += 1

                avg_age_ms = sum(active_ages) / len(active_ages) if active_ages else 0.0
                max_age_ms = max(active_ages) if active_ages else 0.0
                dormant_str = f", {dormant_count} dormant" if dormant_count > 0 else ""

                msgs_per_sec = count / self._latency_log_interval
                if self.IS_EVENT_DRIVEN:
                    # Event-driven exchanges (e.g., Bitfinex) send updates
                    # only on price changes. High data_age is expected and
                    # reflects market inactivity, not stale data.
                    avg_age_s = avg_age_ms / 1000
                    max_age_s = max_age_ms / 1000
                    logger.info(
                        f"[Latency] [{self.exchange_name}] "
                        f"proc: avg={avg_ms:.2f}ms min={min_ms:.2f}ms max={max_ms:.2f}ms "
                        f"({count} msgs, rate={msgs_per_sec:.0f}/s) | "
                        f"data_age: avg={avg_age_s:.1f}s max={max_age_s:.1f}s "
                        f"({len(active_ages)} active{dormant_str} / {len(self.symbols)} symbols) "
                        f"(event-driven)"
                    )
                else:
                    logger.info(
                        f"[Latency] [{self.exchange_name}] "
                        f"proc: avg={avg_ms:.2f}ms min={min_ms:.2f}ms max={max_ms:.2f}ms "
                        f"({count} msgs, rate={msgs_per_sec:.0f}/s) | "
                        f"freshness: avg={avg_age_ms:.0f}ms max={max_age_ms:.0f}ms "
                        f"({len(active_ages)} active{dormant_str} / {len(self.symbols)} symbols)"
                    )
            await asyncio.sleep(self._latency_log_interval)
