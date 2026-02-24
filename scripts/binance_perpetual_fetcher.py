"""
Binance Perpetual Futures data fetcher.

This module provides functionality to download historical candle (kline) data
from Binance Perpetual Futures API without requiring authentication.

The data is fetched using the public API endpoint and saved to CSV and Parquet files.
Parquet files are optimized for fast loading (~5-10x faster than CSV).
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pandas as pd
import requests
from tqdm import tqdm

# Try to import pyarrow for Parquet support
try:
    import pyarrow  # noqa: F401
    PARQUET_AVAILABLE = True
except ImportError:
    PARQUET_AVAILABLE = False


class BinancePerpetualDataFetcher:
    """
    Fetches historical candle data from Binance Perpetual Futures.

    Uses the public Binance Futures API (no authentication required).
    Handles rate limiting and pagination for large date ranges.

    Supported intervals:
        1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M
    """

    BASE_URL = "https://fapi.binance.com"
    KLINES_ENDPOINT = "/fapi/v1/klines"

    # Maximum candles per request (Binance limit)
    MAX_CANDLES_PER_REQUEST = 1500

    # Rate limiting: Binance Futures API allows 2400 weight/min
    # Klines endpoint with limit=1500 has weight ~10, allowing ~240 req/min = 4 req/s
    # In practice, Binance is more lenient. Using 20ms delay (~50 req/s theoretical)
    # with robust retry logic (exponential backoff) for any 418/429 errors
    REQUESTS_PER_MINUTE = 2400
    REQUEST_DELAY_SECONDS = 0.020  # 20ms between requests (fast, retry handles limits)

    # Retry settings for rate limiting (418/429 errors)
    MAX_RETRIES = 5
    INITIAL_RETRY_DELAY = 2.0  # Start with 2 second delay
    MAX_RETRY_DELAY = 60.0  # Max 60 second delay

    # Interval to milliseconds mapping
    INTERVAL_TO_MILLISECONDS = {
        "1m": 60 * 1000,
        "3m": 3 * 60 * 1000,
        "5m": 5 * 60 * 1000,
        "15m": 15 * 60 * 1000,
        "30m": 30 * 60 * 1000,
        "1h": 60 * 60 * 1000,
        "2h": 2 * 60 * 60 * 1000,
        "4h": 4 * 60 * 60 * 1000,
        "6h": 6 * 60 * 60 * 1000,
        "8h": 8 * 60 * 60 * 1000,
        "12h": 12 * 60 * 60 * 1000,
        "1d": 24 * 60 * 60 * 1000,
        "3d": 3 * 24 * 60 * 60 * 1000,
        "1w": 7 * 24 * 60 * 60 * 1000,
        "1M": 30 * 24 * 60 * 60 * 1000,
    }

    # Predefined list of perpetual futures symbols (from your screenshots)
    PREDEFINED_SYMBOLS = [
        "BTCUSDT",
        "ETHUSDT",
        "XRPUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "DOGEUSDT",
        "TRXUSDT",
        "XLMUSDT",
        "SUIUSDT",
        "LINKUSDT",
        "1000PEPEUSDT",
        "ADAUSDT",
        "AVAXUSDT",
        "HBARUSDT",
        "1000SHIBUSDT",
        "TONUSDT",
        "BCHUSDT",
        "DOTUSDT",
        "LTCUSDT",
        "ONDOUSDT",
        "TAOUSDT",
        "UNIUSDT",
        "WLDUSDT",
        "NEARUSDT",
        "APTUSDT",
        "AAVEUSDT",
        "ICPUSDT",
        "FILUSDT",
        "ARBUSDT",
        "ETCUSDT",
        "OPUSDT",
        "POLUSDT",
        "TRUMPUSDT",
        "FETUSDT",
        "VETUSDT",
        "ENSUSDT",
        "RENDERUSDT",
        "ENAUSDT",
        "VIRTUALUSDT",
        "TIAUSDT",
        "ATOMUSDT",
        "ALGOUSDT",
        "JUPUSDT",
        "QNTUSDT",
        "JTOUSDT",
        "1000BONKUSDT",
        "INJUSDT",
        "RAYSOLUSDT",
        "STXUSDT",
        "PENDLEUSDT",
        "SUSDT",
        "FORMUSDT",
        "SEIUSDT",
    ]

    # Column names matching your format
    COLUMN_NAMES = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "n_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "ignore",
    ]

    # Columns to keep in CSV output (full data)
    OUTPUT_COLUMNS = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "n_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]

    # Columns for Parquet output (only essential OHLCV data for fast loading)
    PARQUET_COLUMNS = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    def __init__(self, output_directory: str = "data", quiet: bool = False):
        """
        Initialize the data fetcher.

        Args:
            output_directory: Directory to save downloaded CSV files
            quiet: If True, suppress all output (no prints, no progress bars)
        """
        self.output_directory = Path(output_directory)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.quiet = quiet

    def fetch_all_symbols(
        self, interval: str, start_date: datetime, end_date: datetime, symbols: list[str] | None = None
    ) -> None:
        """
        Fetch historical data for all predefined symbols.

        Args:
            interval: Candle interval (e.g., "1m", "1h")
            start_date: Start date for data fetch
            end_date: End date for data fetch
            symbols: Optional list of symbols to fetch (uses PREDEFINED_SYMBOLS if None)
        """
        if symbols is None:
            symbols = self.PREDEFINED_SYMBOLS

        # Create interval-specific directory
        interval_directory = self.output_directory / interval
        interval_directory.mkdir(parents=True, exist_ok=True)

        if not self.quiet:
            print(f"\n{'=' * 70}")
            print(f"Fetching {len(symbols)} symbols with {interval} interval")
            print(f"Date range: {start_date.strftime('%Y-%m-%d %H:%M')} to {end_date.strftime('%Y-%m-%d %H:%M')}")
            print(f"Output directory: {interval_directory}")
            print(f"{'=' * 70}\n")

        # Overall progress bar (only if not quiet)
        overall_progress_bar = None
        if not self.quiet:
            overall_progress_bar = tqdm(
                total=len(symbols),
                desc="Overall Progress",
                position=0,
                leave=True,
                colour="green",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} symbols [{elapsed}<{remaining}]",
            )

        successful_count = 0
        failed_symbols = []

        for symbol in symbols:
            try:
                self._fetch_single_symbol_with_update(
                    symbol=symbol,
                    interval=interval,
                    start_date=start_date,
                    end_date=end_date,
                    interval_directory=interval_directory,
                    position=1,
                )
                successful_count += 1
            except Exception as error:
                failed_symbols.append((symbol, str(error)))
                if not self.quiet:
                    tqdm.write(f"  ✗ {symbol}: {error}")

            if overall_progress_bar:
                overall_progress_bar.update(1)

        if overall_progress_bar:
            overall_progress_bar.close()

        # Print summary
        if not self.quiet:
            print(f"\n{'=' * 70}")
            print("FETCH SUMMARY")
            print(f"{'=' * 70}")
            print(f"Successful: {successful_count}/{len(symbols)} symbols")

            if failed_symbols:
                print(f"\nFailed symbols ({len(failed_symbols)}):")
                for symbol, err_msg in failed_symbols:
                    print(f"  - {symbol}: {err_msg}")

            print(f"{'=' * 70}\n")

    def _is_candle_in_progress(self, candle_timestamp: datetime, interval: str, current_time: datetime) -> bool:
        """
        Check if a candle is still in-progress (not yet closed).

        Args:
            candle_timestamp: The opening timestamp of the candle
            interval: Candle interval (e.g., "1m", "1w", "1M")
            current_time: The current time to compare against

        Returns:
            True if the candle is still in-progress, False if complete
        """
        interval_ms = self.INTERVAL_TO_MILLISECONDS[interval]
        candle_close_time = candle_timestamp + timedelta(milliseconds=interval_ms)
        return current_time < candle_close_time

    def _fetch_single_symbol_with_update(
        self,
        symbol: str,
        interval: str,
        start_date: datetime,
        end_date: datetime,
        interval_directory: Path,
        position: int = 1,
    ) -> pd.DataFrame:
        """
        Fetch data for a single symbol with incremental update support.

        For completed candles: only fetches new candles after the last one.
        For in-progress candles (current week/month): re-fetches to update OHLCV values.

        Output structure:
            interval_directory/SYMBOL/YYYY_MM_DD-YYYY_MM_DD.csv

        Args:
            symbol: Trading pair symbol
            interval: Candle interval
            start_date: Start date for data fetch
            end_date: End date for data fetch
            interval_directory: Directory to save the file
            position: Position for progress bar

        Returns:
            DataFrame with candle data
        """
        # Create symbol directory
        symbol_directory = interval_directory / symbol
        symbol_directory.mkdir(parents=True, exist_ok=True)

        # Find existing data files in symbol directory
        actual_start_date = start_date
        is_updating_in_progress = False

        # Check for existing data files
        parquet_files = list(symbol_directory.glob("*.parquet"))
        csv_files = list(symbol_directory.glob("*.csv"))
        metadata_path = symbol_directory / ".metadata.json"

        # For incremental updates, we only need to read the last timestamp initially
        # Full file loading is deferred until we actually need to merge
        latest_timestamp = None
        existing_parquet_path = parquet_files[0] if parquet_files else None
        existing_csv_path = csv_files[0] if csv_files else None

        if parquet_files or csv_files:
            # FAST PATH: Try to read from metadata cache first (instant)
            if metadata_path.exists():
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                        latest_timestamp = metadata.get("last_timestamp")
                except Exception:
                    pass

            # SLOW PATH: Fall back to reading parquet timestamp column
            if latest_timestamp is None and existing_parquet_path and PARQUET_AVAILABLE:
                try:
                    ts_df = pd.read_parquet(existing_parquet_path, columns=["timestamp"])
                    if len(ts_df) > 0:
                        latest_timestamp = ts_df["timestamp"].max()
                except Exception:
                    pass

            # SLOWEST PATH: Fall back to CSV
            if latest_timestamp is None and existing_csv_path:
                try:
                    ts_df = pd.read_csv(existing_csv_path, usecols=["timestamp"])
                    if len(ts_df) > 0:
                        latest_timestamp = ts_df["timestamp"].max()
                except Exception:
                    pass

            if latest_timestamp is not None:
                # We have the latest timestamp - check if update needed
                latest_datetime = datetime.fromtimestamp(latest_timestamp)
                interval_ms = self.INTERVAL_TO_MILLISECONDS[interval]

                # Check if the last candle is still in-progress
                if self._is_candle_in_progress(latest_datetime, interval, end_date):
                    # Re-fetch the in-progress candle to get updated OHLCV values
                    actual_start_date = latest_datetime
                    is_updating_in_progress = True
                    if not self.quiet:
                        tqdm.write(
                            f"  ↻ {symbol}: Updating in-progress candle from {latest_datetime.strftime('%Y-%m-%d %H:%M')}"
                        )
                else:
                    # Last candle is complete, start from the next candle
                    actual_start_date = latest_datetime + timedelta(milliseconds=interval_ms)

                    if actual_start_date >= end_date:
                        if not self.quiet:
                            tqdm.write(f"  ✓ {symbol}: Already up to date")
                        # Return None to indicate no changes needed (avoid loading full file)
                        return None

                    if not self.quiet:
                        tqdm.write(
                            f"  ↻ {symbol}: Fetching new candles from {actual_start_date.strftime('%Y-%m-%d %H:%M')}"
                        )

        # Fetch new data
        new_dataframe = self._fetch_candles_with_progress(
            symbol=symbol, interval=interval, start_date=actual_start_date, end_date=end_date, position=position
        )

        if new_dataframe.empty and latest_timestamp is None:
            if not self.quiet:
                tqdm.write(f"  ✗ {symbol}: No data fetched")
            return pd.DataFrame()

        # If we have existing data and new data, we need to merge or append
        if latest_timestamp is not None and not new_dataframe.empty:
            added_count = len(new_dataframe)

            # FAST PATH: Append-only mode (no overlap with existing data)
            # This is the common case for daily updates - skip loading full files!
            if not is_updating_in_progress and existing_csv_path:
                # Just append new data to CSV (instant - no need to load full file!)
                new_dataframe.to_csv(existing_csv_path, mode='a', header=False, index=False)

                # Update last timestamp from new data
                new_last_timestamp = new_dataframe["timestamp"].max()

                # Rename file to reflect new end date
                # Filename format: YYYY_MM_DD-YYYY_MM_DD.csv (start_date-end_date)
                old_filename = existing_csv_path.stem  # e.g., "2019_09_08-2025_12_07"
                start_date_str = old_filename.split("-")[0]  # Keep original start date
                new_end_date_str = datetime.fromtimestamp(new_last_timestamp).strftime("%Y_%m_%d")
                new_filename = f"{start_date_str}-{new_end_date_str}"

                if old_filename != new_filename:
                    new_csv_path = existing_csv_path.parent / f"{new_filename}.csv"
                    existing_csv_path.rename(new_csv_path)

                    # Also rename parquet if exists (will be regenerated later anyway)
                    if existing_parquet_path and existing_parquet_path.exists():
                        new_parquet_path = existing_parquet_path.parent / f"{new_filename}.parquet"
                        existing_parquet_path.rename(new_parquet_path)

                # NOTE: Parquet doesn't support true append - would need to read entire file
                # Skip parquet update in fast path. Run --regenerate-parquet before optimization
                # to rebuild parquet files from updated CSVs.

                # Update metadata with new last timestamp
                with open(metadata_path, 'w') as f:
                    json.dump({"last_timestamp": float(new_last_timestamp)}, f)

                if not self.quiet:
                    tqdm.write(f"  ✓ {symbol}: Appended {added_count:,} candles (fast mode)")

                return new_dataframe

            # SLOW PATH: Need full merge (updating in-progress candle or edge cases)
            if existing_parquet_path and PARQUET_AVAILABLE:
                try:
                    existing_dataframe = pd.read_parquet(existing_parquet_path)
                except Exception:
                    existing_dataframe = pd.read_csv(existing_csv_path) if existing_csv_path else None
            elif existing_csv_path:
                existing_dataframe = pd.read_csv(existing_csv_path)
            else:
                existing_dataframe = None

            if existing_dataframe is not None:
                original_count = len(existing_dataframe)
                combined_dataframe = pd.concat([existing_dataframe, new_dataframe], ignore_index=True)
                combined_dataframe = combined_dataframe.drop_duplicates(subset=["timestamp"], keep="last")
                combined_dataframe = combined_dataframe.sort_values("timestamp").reset_index(drop=True)
                final_dataframe = combined_dataframe
                new_count = len(final_dataframe)
                added_count = new_count - original_count

                if not self.quiet:
                    if is_updating_in_progress and added_count == 0:
                        tqdm.write(f"  ✓ {symbol}: Updated in-progress candle (total: {new_count:,})")
                    elif is_updating_in_progress and added_count > 0:
                        tqdm.write(f"  ✓ {symbol}: Updated + added {added_count:,} candles (total: {new_count:,})")
                    else:
                        tqdm.write(f"  ✓ {symbol}: Added {added_count:,} candles (total: {new_count:,})")
            else:
                final_dataframe = new_dataframe
        elif latest_timestamp is not None:
            # No new data fetched but we have existing - shouldn't happen normally
            return None
        else:
            final_dataframe = new_dataframe
            if not self.quiet:
                tqdm.write(f"  ✓ {symbol}: Downloaded {len(final_dataframe):,} candles")

        # Generate filename based on actual data date range
        first_timestamp = final_dataframe["timestamp"].min()
        last_timestamp = final_dataframe["timestamp"].max()
        first_date = datetime.fromtimestamp(first_timestamp)
        last_date = datetime.fromtimestamp(last_timestamp)
        base_filename = f"{first_date.strftime('%Y_%m_%d')}-{last_date.strftime('%Y_%m_%d')}"
        new_csv_path = symbol_directory / f"{base_filename}.csv"
        new_parquet_path = symbol_directory / f"{base_filename}.parquet"

        # Delete old files if they exist and have different names
        old_csv_files = [f for f in symbol_directory.glob("*.csv") if f != new_csv_path]
        for old_csv in old_csv_files:
            old_csv.unlink()
        old_parquet_files = [f for f in symbol_directory.glob("*.parquet") if f != new_parquet_path]
        for old_parquet in old_parquet_files:
            old_parquet.unlink()

        # Save to CSV (full data)
        final_dataframe.to_csv(new_csv_path, index=False)

        # Save to Parquet (essential columns only, for fast loading)
        if PARQUET_AVAILABLE:
            parquet_df = final_dataframe[self.PARQUET_COLUMNS].copy()
            parquet_df.to_parquet(new_parquet_path, engine='pyarrow', compression='snappy', index=False)

        # Update metadata cache for instant timestamp lookups next time
        with open(metadata_path, 'w') as f:
            json.dump({"last_timestamp": float(last_timestamp)}, f)

        return final_dataframe

    def _fetch_candles_with_progress(
        self, symbol: str, interval: str, start_date: datetime, end_date: datetime, position: int = 1
    ) -> pd.DataFrame:
        """
        Fetch candles with progress bar.

        Args:
            symbol: Trading pair symbol
            interval: Candle interval
            start_date: Start date
            end_date: End date
            position: Progress bar position

        Returns:
            DataFrame with candle data
        """
        # Validate interval
        if interval not in self.INTERVAL_TO_MILLISECONDS:
            raise ValueError(f"Unsupported interval: {interval}")

        # Convert symbol format (SOL-USDT -> SOLUSDT)
        symbol_formatted = symbol.replace("-", "").upper()

        # Convert dates to milliseconds
        start_timestamp_ms = int(start_date.timestamp() * 1000)
        end_timestamp_ms = int(end_date.timestamp() * 1000)

        # Estimate total candles for progress bar
        interval_ms = self.INTERVAL_TO_MILLISECONDS[interval]
        estimated_candles = (end_timestamp_ms - start_timestamp_ms) // interval_ms

        # Fetch data in chunks with progress bar
        all_candles = []
        current_start = start_timestamp_ms

        # Create progress bar for this symbol (only if not quiet)
        symbol_progress_bar = None
        if not self.quiet:
            symbol_progress_bar = tqdm(
                total=estimated_candles,
                desc=f"  {symbol_formatted:<12}",
                position=position,
                leave=False,
                colour="cyan",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            )

        while current_start < end_timestamp_ms:
            try:
                candles = self._fetch_candles_chunk(
                    symbol=symbol_formatted,
                    interval=interval,
                    start_timestamp_ms=current_start,
                    end_timestamp_ms=end_timestamp_ms,
                    limit=self.MAX_CANDLES_PER_REQUEST,
                )

                if not candles:
                    break

                all_candles.extend(candles)
                if symbol_progress_bar:
                    symbol_progress_bar.update(len(candles))

                # Move start to after last candle
                last_timestamp = candles[-1][0]
                current_start = last_timestamp + interval_ms

                # Rate limiting
                time.sleep(self.REQUEST_DELAY_SECONDS)

            except requests.exceptions.RequestException as error:
                if symbol_progress_bar:
                    symbol_progress_bar.close()
                raise error

        if symbol_progress_bar:
            symbol_progress_bar.close()

        if not all_candles:
            return pd.DataFrame()

        # Convert to DataFrame
        dataframe = pd.DataFrame(all_candles, columns=self.COLUMN_NAMES)

        # Convert timestamp from milliseconds to seconds
        dataframe["timestamp"] = dataframe["timestamp"] / 1000.0

        # Convert numeric columns
        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_asset_volume",
            "n_trades",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
        ]
        for column in numeric_columns:
            dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

        # Select output columns
        dataframe = dataframe[self.OUTPUT_COLUMNS]

        # Remove duplicates and sort
        dataframe = dataframe.drop_duplicates(subset=["timestamp"], keep="first")
        dataframe = dataframe.sort_values("timestamp").reset_index(drop=True)

        return dataframe

    def fetch_candles(
        self, symbol: str, interval: str, start_date: datetime, end_date: datetime, save_to_csv: bool = True
    ) -> pd.DataFrame:
        """
        Fetch historical candle data from Binance Perpetual Futures.

        Args:
            symbol: Trading pair symbol (e.g., "SOLUSDT", "BTCUSDT")
            interval: Candle interval (e.g., "1m", "5m", "1h", "1d")
            start_date: Start date for data fetch
            end_date: End date for data fetch
            save_to_csv: Whether to save the data to CSV file

        Returns:
            DataFrame with candle data

        Raises:
            ValueError: If interval is not supported
            requests.RequestException: If API request fails
        """
        # Validate interval
        if interval not in self.INTERVAL_TO_MILLISECONDS:
            raise ValueError(
                f"Unsupported interval: {interval}. Supported intervals: {list(self.INTERVAL_TO_MILLISECONDS.keys())}"
            )

        # Convert symbol format (SOL-USDT -> SOLUSDT)
        symbol_formatted = symbol.replace("-", "").upper()

        # Convert dates to milliseconds
        start_timestamp_ms = int(start_date.timestamp() * 1000)
        end_timestamp_ms = int(end_date.timestamp() * 1000)

        if not self.quiet:
            print(f"Fetching {symbol_formatted} {interval} candles from Binance Perpetual Futures...")
            print(f"Date range: {start_date.strftime('%Y-%m-%d %H:%M')} to {end_date.strftime('%Y-%m-%d %H:%M')}")

        # Fetch data in chunks
        all_candles = self._fetch_all_candles(
            symbol=symbol_formatted,
            interval=interval,
            start_timestamp_ms=start_timestamp_ms,
            end_timestamp_ms=end_timestamp_ms,
        )

        if not all_candles:
            if not self.quiet:
                print("No candles fetched!")
            return pd.DataFrame()

        # Convert to DataFrame
        dataframe = pd.DataFrame(all_candles, columns=self.COLUMN_NAMES)

        # Convert timestamp from milliseconds to seconds (matching your format)
        dataframe["timestamp"] = dataframe["timestamp"] / 1000.0

        # Convert numeric columns
        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_asset_volume",
            "n_trades",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
        ]
        for column in numeric_columns:
            dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

        # Select output columns
        dataframe = dataframe[self.OUTPUT_COLUMNS]

        # Remove duplicates and sort
        dataframe = dataframe.drop_duplicates(subset=["timestamp"], keep="first")
        dataframe = dataframe.sort_values("timestamp").reset_index(drop=True)

        if not self.quiet:
            print(f"Fetched {len(dataframe)} candles")

        # Save to CSV if requested
        if save_to_csv:
            output_path = self._save_to_csv(dataframe, symbol_formatted, interval)
            if not self.quiet:
                print(f"Saved to: {output_path}")

        return dataframe

    def _fetch_all_candles(
        self, symbol: str, interval: str, start_timestamp_ms: int, end_timestamp_ms: int
    ) -> list[list]:
        """
        Fetch all candles by paginating through the API.

        Args:
            symbol: Trading pair symbol
            interval: Candle interval
            start_timestamp_ms: Start timestamp in milliseconds
            end_timestamp_ms: End timestamp in milliseconds

        Returns:
            List of candle data lists
        """
        all_candles = []
        current_start = start_timestamp_ms
        interval_ms = self.INTERVAL_TO_MILLISECONDS[interval]

        total_expected = (end_timestamp_ms - start_timestamp_ms) // interval_ms
        fetched_count = 0

        while current_start < end_timestamp_ms:
            # Fetch chunk
            candles = self._fetch_candles_chunk(
                symbol=symbol,
                interval=interval,
                start_timestamp_ms=current_start,
                end_timestamp_ms=end_timestamp_ms,
                limit=self.MAX_CANDLES_PER_REQUEST,
            )

            if not candles:
                break

            all_candles.extend(candles)
            fetched_count += len(candles)

            # Progress update
            if not self.quiet:
                progress = min(100, (fetched_count / max(1, total_expected)) * 100)
                print(f"  Progress: {fetched_count:,} candles fetched ({progress:.1f}%)", end="\r")

            # Move start to after last candle
            last_timestamp = candles[-1][0]
            current_start = last_timestamp + interval_ms

            # Rate limiting
            time.sleep(self.REQUEST_DELAY_SECONDS)

        if not self.quiet:
            print()  # New line after progress
        return all_candles

    def _fetch_candles_chunk(
        self, symbol: str, interval: str, start_timestamp_ms: int, end_timestamp_ms: int, limit: int
    ) -> list[list]:
        """
        Fetch a single chunk of candles from the API with retry logic for rate limiting.

        Args:
            symbol: Trading pair symbol
            interval: Candle interval
            start_timestamp_ms: Start timestamp in milliseconds
            end_timestamp_ms: End timestamp in milliseconds
            limit: Maximum number of candles to fetch

        Returns:
            List of candle data lists

        Raises:
            requests.exceptions.RequestException: If all retries exhausted
        """
        url = f"{self.BASE_URL}{self.KLINES_ENDPOINT}"

        params: dict[str, str | int] = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_timestamp_ms,
            "endTime": end_timestamp_ms,
            "limit": limit,
        }

        retry_delay = self.INITIAL_RETRY_DELAY
        last_error: requests.exceptions.RequestException | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                return cast(list[list[Any]], response.json())
            except requests.exceptions.HTTPError as error:
                last_error = error
                # Check for rate limiting errors (418 "I'm a teapot" or 429 "Too Many Requests")
                if error.response is not None and error.response.status_code in (418, 429):
                    if attempt < self.MAX_RETRIES:
                        if not self.quiet:
                            tqdm.write(f"  ⚠ Rate limited ({error.response.status_code}), waiting {retry_delay:.1f}s...")
                        time.sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, self.MAX_RETRY_DELAY)
                        continue
                raise error
            except requests.exceptions.RequestException as error:
                raise error

        if last_error:
            raise last_error
        raise requests.exceptions.RequestException("Max retries exhausted")

    def _save_to_csv(self, dataframe: pd.DataFrame, symbol: str, interval: str) -> Path:
        """
        Save DataFrame to CSV and Parquet with folder structure and date-range filename.

        Output structure:
            output_directory/interval/SYMBOL/YYYY_MM_DD-YYYY_MM_DD.csv
            output_directory/interval/SYMBOL/YYYY_MM_DD-YYYY_MM_DD.parquet

        The filename is based on the actual data date range in the DataFrame.
        Parquet files contain only essential OHLCV columns for fast loading.

        Args:
            dataframe: DataFrame to save
            symbol: Trading pair symbol
            interval: Candle interval (e.g., "1m", "1h", "1d")

        Returns:
            Path to saved CSV file
        """
        # Format symbol (remove hyphens: SOL-USDT -> SOLUSDT)
        symbol_formatted = symbol.replace("-", "").upper()

        # Create directory structure: output_dir/interval/symbol/
        symbol_directory = self.output_directory / interval / symbol_formatted
        symbol_directory.mkdir(parents=True, exist_ok=True)

        # Generate filename based on actual data date range
        first_timestamp = dataframe["timestamp"].min()
        last_timestamp = dataframe["timestamp"].max()
        first_date = datetime.fromtimestamp(first_timestamp)
        last_date = datetime.fromtimestamp(last_timestamp)
        base_filename = f"{first_date.strftime('%Y_%m_%d')}-{last_date.strftime('%Y_%m_%d')}"

        # Check for existing files and remove them (to handle date range changes)
        for existing_file in list(symbol_directory.glob("*.csv")):
            existing_file.unlink()
        for existing_file in list(symbol_directory.glob("*.parquet")):
            existing_file.unlink()

        # Build output paths
        csv_path = symbol_directory / f"{base_filename}.csv"
        parquet_path = symbol_directory / f"{base_filename}.parquet"
        metadata_path = symbol_directory / ".metadata.json"

        # Save to CSV (full data)
        dataframe.to_csv(csv_path, index=False)

        # Save to Parquet (essential columns only, for fast loading)
        if PARQUET_AVAILABLE:
            parquet_df = dataframe[self.PARQUET_COLUMNS].copy()
            parquet_df.to_parquet(parquet_path, engine='pyarrow', compression='snappy', index=False)

        # Update metadata cache for instant timestamp lookups next time
        with open(metadata_path, 'w') as f:
            json.dump({"last_timestamp": float(last_timestamp)}, f)

        return csv_path

    def get_available_symbols(self) -> list[str]:
        """
        Get list of available perpetual futures symbols from Binance.

        Returns:
            List of available trading symbols
        """
        url = f"{self.BASE_URL}/fapi/v1/exchangeInfo"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            symbols = [
                symbol_info["symbol"]
                for symbol_info in data.get("symbols", [])
                if symbol_info.get("contractType") == "PERPETUAL"
            ]

            return sorted(symbols)
        except requests.exceptions.RequestException as error:
            if not self.quiet:
                print(f"Failed to fetch symbols: {error}")
            return []

    def get_server_time(self) -> datetime:
        """
        Get current Binance server time.

        Returns:
            Server time as datetime object
        """
        url = f"{self.BASE_URL}/fapi/v1/time"

        response = self.session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        return datetime.fromtimestamp(data["serverTime"] / 1000)

    @classmethod
    def get_predefined_symbols(cls) -> list[str]:
        """Get the predefined list of symbols."""
        return cls.PREDEFINED_SYMBOLS.copy()

    def regenerate_all_parquet(self) -> None:
        """
        Regenerate all parquet files from CSV files.

        This should be run before optimization to ensure parquet files
        are up-to-date after fast CSV-only appends from daily cron.

        Scans all timeframe directories and regenerates parquet from CSV.
        """
        if not PARQUET_AVAILABLE:
            print("ERROR: pyarrow not available. Cannot regenerate parquet files.")
            return

        # Find all timeframe directories
        timeframe_dirs = [d for d in self.output_directory.iterdir() if d.is_dir()]

        # Count total CSV files for progress bar
        all_csv_files = []
        for tf_dir in sorted(timeframe_dirs):
            symbol_dirs = [d for d in tf_dir.iterdir() if d.is_dir()]
            for symbol_dir in symbol_dirs:
                csv_files = list(symbol_dir.glob("*.csv"))
                if csv_files:
                    all_csv_files.append((tf_dir.name, symbol_dir.name, csv_files[0]))

        if not all_csv_files:
            if not self.quiet:
                print("No CSV files found to regenerate.")
            return

        total_regenerated = 0
        total_skipped = 0

        # Use tqdm progress bar
        pbar = tqdm(
            all_csv_files,
            desc="Regenerating parquet",
            unit="file",
            disable=self.quiet,
            ncols=100
        )

        for timeframe, symbol, csv_path in pbar:
            parquet_path = csv_path.with_suffix(".parquet")
            pbar.set_postfix_str(f"{timeframe}/{symbol}")

            try:
                # Read CSV and write parquet (OHLCV columns only)
                df = pd.read_csv(csv_path)
                parquet_df = df[self.PARQUET_COLUMNS].copy()
                parquet_df.to_parquet(parquet_path, engine='pyarrow', compression='snappy', index=False)
                total_regenerated += 1
            except Exception as e:
                if not self.quiet:
                    tqdm.write(f"  ERROR {timeframe}/{symbol}: {e}")
                total_skipped += 1

        if not self.quiet:
            print(f"\n{'=' * 70}")
            print(f"COMPLETED: Regenerated {total_regenerated} parquet files")
            if total_skipped > 0:
                print(f"Skipped {total_skipped} files due to errors")
            print(f"{'=' * 70}")

    def generate_timeframe_from_1m(
        self,
        symbol: str,
        target_interval: str,
    ) -> pd.DataFrame | None:
        """
        Generate higher timeframe data by aggregating from 1m data.

        This method creates accurate higher timeframe OHLCV data by properly
        aggregating 1m bars, avoiding issues with pre-aggregated data from
        external sources.

        Args:
            symbol: Trading pair symbol (e.g., "ETHUSDT")
            target_interval: Target interval to generate (e.g., "5m", "15m", "1h")

        Returns:
            DataFrame with aggregated OHLCV data, or None if 1m data not found
        """
        if target_interval not in self.INTERVAL_TO_MILLISECONDS:
            raise ValueError(f"Unsupported interval: {target_interval}")

        if target_interval == "1m":
            raise ValueError("Cannot generate 1m from 1m - use fetch directly")

        # Load 1m data
        symbol_dir_1m = self.output_directory / "1m" / symbol
        if not symbol_dir_1m.exists():
            if not self.quiet:
                print(f"  ERROR: No 1m data for {symbol}")
            return None

        csv_files = list(symbol_dir_1m.glob("*.csv"))
        if not csv_files:
            if not self.quiet:
                print(f"  ERROR: No 1m CSV files for {symbol}")
            return None

        df_1m = pd.read_csv(csv_files[0])
        if not self.quiet:
            print(f"  Loaded {len(df_1m):,} 1m bars for {symbol}")

        # Calculate target interval in minutes
        target_minutes = self.INTERVAL_TO_MILLISECONDS[target_interval] // (60 * 1000)
        target_seconds = target_minutes * 60

        # Ensure timestamp is numeric
        df_1m["timestamp"] = df_1m["timestamp"].astype(float)

        # Calculate bar group based on timestamp
        df_1m["bar_group"] = (df_1m["timestamp"] // target_seconds).astype(int)

        # Aggregate by bar group using proper OHLCV rules
        aggregated = df_1m.groupby("bar_group").agg({
            "open": "first",       # First open in window
            "high": "max",         # Max high in window
            "low": "min",          # Min low in window
            "close": "last",       # Last close in window
            "volume": "sum",       # Sum of volumes
        }).reset_index()  # Keep bar_group for timestamp calculation

        # Calculate canonical timestamp from bar_group (ensures proper boundary alignment)
        # This fixes misalignment issues when first 1m bar in group is missing
        aggregated["timestamp"] = (aggregated["bar_group"] * target_seconds).astype(float)

        # Preserve additional columns if present
        extra_cols = ["quote_asset_volume", "n_trades", "taker_buy_base_volume", "taker_buy_quote_volume"]
        for col in extra_cols:
            if col in df_1m.columns:
                agg_extra = df_1m.groupby("bar_group")[col].sum().reset_index(drop=True)
                aggregated[col] = agg_extra.values

        # Reorder columns with timestamp first, drop bar_group
        cols = ["timestamp", "open", "high", "low", "close", "volume"]
        cols += [c for c in extra_cols if c in aggregated.columns]
        aggregated = aggregated[cols]

        if not self.quiet:
            print(f"  Aggregated to {len(aggregated):,} {target_interval} bars")

        return aggregated

    def generate_all_timeframes_from_1m(
        self,
        symbols: list[str] | None = None,
        timeframes: list[str] | None = None,
        force_full: bool = False,
    ) -> None:
        """
        Generate multiple higher timeframe data files from 1m data for all symbols.

        INCREMENTAL MODE (default): Only aggregates NEW 1m data since last HTF update.
        - Reads HTF metadata to get last_timestamp
        - Filters 1m data to only new bars
        - Appends aggregated data to existing HTF CSV
        - ~100x faster for daily updates (processes ~1440 bars instead of millions)

        FULL MODE (--force-full): Regenerates entire HTF files from scratch.

        Args:
            symbols: List of symbols to process (uses PREDEFINED_SYMBOLS if None)
            timeframes: List of timeframes to generate (defaults to ["5m", "15m"])
            force_full: Force full regeneration instead of incremental update
        """
        if symbols is None:
            symbols = self.PREDEFINED_SYMBOLS

        if timeframes is None:
            timeframes = ["5m", "15m"]

        mode_str = "FULL REGENERATION" if force_full else "INCREMENTAL UPDATE"
        if not self.quiet:
            print(f"\n{'=' * 70}")
            print(f"HTF Aggregation - {mode_str}")
            print(f"Timeframes: {', '.join(timeframes)}")
            print(f"Symbols: {len(symbols)}")
            print(f"{'=' * 70}\n")

        # Create all target directories upfront
        for tf in timeframes:
            tf_dir = self.output_directory / tf
            tf_dir.mkdir(parents=True, exist_ok=True)

        # Overall progress bar for all symbols
        symbol_progress_bar = None
        if not self.quiet:
            symbol_progress_bar = tqdm(
                total=len(symbols),
                desc="Symbols",
                position=0,
                leave=True,
                colour="green",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            )

        total_success = 0
        total_incremental = 0
        total_full = 0
        failed_symbols = []

        for symbol in symbols:
            # Load 1m data ONCE per symbol
            symbol_dir_1m = self.output_directory / "1m" / symbol
            if not symbol_dir_1m.exists():
                failed_symbols.append((symbol, "No 1m directory"))
                if symbol_progress_bar:
                    symbol_progress_bar.update(1)
                continue

            csv_files_1m = list(symbol_dir_1m.glob("*.csv"))
            if not csv_files_1m:
                failed_symbols.append((symbol, "No 1m CSV"))
                if symbol_progress_bar:
                    symbol_progress_bar.update(1)
                continue

            try:
                df_1m_full = pd.read_csv(csv_files_1m[0])
                df_1m_full["timestamp"] = df_1m_full["timestamp"].astype(float)
            except Exception as e:
                failed_symbols.append((symbol, f"Error reading 1m: {e}"))
                if symbol_progress_bar:
                    symbol_progress_bar.update(1)
                continue

            # Get full date range from 1m data
            first_ts_1m = df_1m_full["timestamp"].min()
            last_ts_1m = df_1m_full["timestamp"].max()

            # Generate all timeframes for this symbol
            tf_results = []

            # Inner progress bar for timeframes
            tf_progress_bar = None
            if not self.quiet:
                tf_progress_bar = tqdm(
                    total=len(timeframes),
                    desc=f"  {symbol}",
                    position=1,
                    leave=False,
                    colour="cyan",
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}",
                )

            for tf in timeframes:
                if tf_progress_bar:
                    tf_progress_bar.set_postfix_str(tf)
                try:
                    # Check if HTF file exists and has metadata
                    tf_dir = self.output_directory / tf
                    symbol_dir = tf_dir / symbol
                    symbol_dir.mkdir(parents=True, exist_ok=True)
                    metadata_path = symbol_dir / ".metadata.json"
                    existing_csv_files = list(symbol_dir.glob("*.csv"))

                    htf_last_ts = None
                    existing_csv_path = None

                    # Try to read existing HTF metadata for incremental update
                    if not force_full and existing_csv_files and metadata_path.exists():
                        try:
                            with open(metadata_path, 'r') as f:
                                metadata = json.load(f)
                                htf_last_ts = metadata.get("last_timestamp")
                                existing_csv_path = existing_csv_files[0]
                        except Exception:
                            pass

                    # Determine if we can do incremental update
                    if htf_last_ts is not None and htf_last_ts >= first_ts_1m:
                        # INCREMENTAL MODE: Only aggregate new 1m data
                        # IMPORTANT: Filter 1m bars that start AFTER the last HTF bar CLOSES
                        # htf_last_ts is the OPEN timestamp, so we need to add the HTF duration
                        # to avoid creating duplicate bars for the same period
                        target_minutes = self.INTERVAL_TO_MILLISECONDS[tf] // (60 * 1000)
                        htf_duration = target_minutes * 60  # in seconds
                        htf_close_ts = htf_last_ts + htf_duration
                        df_1m_new = df_1m_full[df_1m_full["timestamp"] >= htf_close_ts].copy()

                        if df_1m_new.empty:
                            # No new data to aggregate
                            tf_results.append((tf, True, "up-to-date"))
                            if tf_progress_bar:
                                tf_progress_bar.update(1)
                            continue

                        # Aggregate only new data
                        df_new = self._aggregate_from_1m_data(df_1m_new, tf)
                        if df_new is None or df_new.empty:
                            tf_results.append((tf, True, "no-new-bars"))
                            if tf_progress_bar:
                                tf_progress_bar.update(1)
                            continue

                        # Append to existing CSV
                        df_new.to_csv(existing_csv_path, mode='a', header=False, index=False)

                        # Rename file to reflect new date range
                        old_filename = existing_csv_path.stem
                        start_date_str = old_filename.split("-")[0]
                        new_end_date_str = datetime.fromtimestamp(last_ts_1m).strftime("%Y_%m_%d")
                        new_filename = f"{start_date_str}-{new_end_date_str}"

                        if old_filename != new_filename:
                            new_csv_path = existing_csv_path.parent / f"{new_filename}.csv"
                            existing_csv_path.rename(new_csv_path)

                            # Also rename parquet if exists
                            old_parquet = existing_csv_path.with_suffix(".parquet")
                            if old_parquet.exists():
                                new_parquet_path = old_parquet.parent / f"{new_filename}.parquet"
                                old_parquet.rename(new_parquet_path)

                        # Update metadata
                        with open(metadata_path, 'w') as f:
                            json.dump({"last_timestamp": float(last_ts_1m)}, f)

                        tf_results.append((tf, True, f"+{len(df_new)}"))
                        total_incremental += 1

                    else:
                        # FULL MODE: Aggregate entire 1m dataset
                        df = self._aggregate_from_1m_data(df_1m_full, tf)
                        if df is None:
                            tf_results.append((tf, False, "Invalid timeframe"))
                            if tf_progress_bar:
                                tf_progress_bar.update(1)
                            continue

                        # Remove old files
                        for old_file in symbol_dir.glob("*.csv"):
                            old_file.unlink()
                        for old_file in symbol_dir.glob("*.parquet"):
                            old_file.unlink()

                        # Build filename from full date range
                        first_date = datetime.fromtimestamp(first_ts_1m)
                        last_date = datetime.fromtimestamp(last_ts_1m)
                        base_filename = f"{first_date.strftime('%Y_%m_%d')}-{last_date.strftime('%Y_%m_%d')}"

                        # Save CSV
                        csv_path = symbol_dir / f"{base_filename}.csv"
                        df.to_csv(csv_path, index=False)

                        # Save Parquet if available
                        if PARQUET_AVAILABLE:
                            parquet_path = symbol_dir / f"{base_filename}.parquet"
                            parquet_df = df[self.PARQUET_COLUMNS].copy()
                            parquet_df.to_parquet(parquet_path, engine='pyarrow', compression='snappy', index=False)

                        # Update metadata
                        with open(metadata_path, 'w') as f:
                            json.dump({"last_timestamp": float(last_ts_1m)}, f)

                        tf_results.append((tf, True, f"full:{len(df)}"))
                        total_full += 1

                except Exception as e:
                    tf_results.append((tf, False, str(e)))

                if tf_progress_bar:
                    tf_progress_bar.update(1)

            # Close timeframe progress bar
            if tf_progress_bar:
                tf_progress_bar.close()

            # Count successes for this symbol
            successes = sum(1 for _, ok, _ in tf_results if ok)
            if successes == len(timeframes):
                total_success += 1
                # Build result summary
                result_parts = []
                for tf, ok, info in tf_results:
                    if info and info.startswith("+"):
                        result_parts.append(f"{tf}{info}")
                    elif info == "up-to-date":
                        result_parts.append(f"{tf}=")
                    elif info and info.startswith("full:"):
                        result_parts.append(f"{tf}*")
                    else:
                        result_parts.append(tf)
                if not self.quiet:
                    tqdm.write(f"  ✓ {symbol}: {', '.join(result_parts)}")
            else:
                failures = [(tf, err) for tf, ok, err in tf_results if not ok]
                if not self.quiet:
                    tqdm.write(f"  ⚠ {symbol}: {successes}/{len(timeframes)} ({[f[0] for f in failures]})")

            if symbol_progress_bar:
                symbol_progress_bar.update(1)

        if symbol_progress_bar:
            symbol_progress_bar.close()

        if not self.quiet:
            print(f"\n{'=' * 70}")
            print(f"HTF aggregation complete!")
            print(f"  Symbols: {total_success}/{len(symbols)} fully processed")
            print(f"  Timeframes: {', '.join(timeframes)}")
            print(f"  Incremental updates: {total_incremental}, Full rebuilds: {total_full}")
            print(f"  Legend: tf+N=appended N bars, tf==up-to-date, tf*=full rebuild")
            if failed_symbols:
                print(f"  Failed: {[s[0] for s in failed_symbols[:5]]}" +
                      (f" (+{len(failed_symbols)-5} more)" if len(failed_symbols) > 5 else ""))
            print(f"{'=' * 70}\n")

    def _aggregate_from_1m_data(
        self,
        df_1m: pd.DataFrame,
        target_interval: str,
    ) -> pd.DataFrame | None:
        """
        Aggregate already-loaded 1m data to a higher timeframe.

        Args:
            df_1m: DataFrame with 1m OHLCV data (must have timestamp as float)
            target_interval: Target interval to generate (e.g., "5m", "15m", "1h")

        Returns:
            DataFrame with aggregated OHLCV data, or None if invalid interval
        """
        if target_interval not in self.INTERVAL_TO_MILLISECONDS:
            return None

        if target_interval == "1m":
            return None

        # Calculate target interval in seconds
        target_minutes = self.INTERVAL_TO_MILLISECONDS[target_interval] // (60 * 1000)
        target_seconds = target_minutes * 60

        # Calculate bar group based on timestamp
        df_1m = df_1m.copy()  # Avoid modifying original
        df_1m["bar_group"] = (df_1m["timestamp"] // target_seconds).astype(int)

        # Aggregate by bar group using proper OHLCV rules
        aggregated = df_1m.groupby("bar_group").agg({
            "open": "first",       # First open in window
            "high": "max",         # Max high in window
            "low": "min",          # Min low in window
            "close": "last",       # Last close in window
            "volume": "sum",       # Sum of volumes
        }).reset_index()  # Keep bar_group for timestamp calculation

        # Calculate canonical timestamp from bar_group (ensures proper boundary alignment)
        # This fixes misalignment issues when first 1m bar in group is missing
        aggregated["timestamp"] = (aggregated["bar_group"] * target_seconds).astype(float)

        # Preserve additional columns if present
        extra_cols = ["quote_asset_volume", "n_trades", "taker_buy_base_volume", "taker_buy_quote_volume"]
        for col in extra_cols:
            if col in df_1m.columns:
                agg_extra = df_1m.groupby("bar_group")[col].sum().reset_index(drop=True)
                aggregated[col] = agg_extra.values

        # Reorder columns with timestamp first, drop bar_group
        cols = ["timestamp", "open", "high", "low", "close", "volume"]
        cols += [c for c in extra_cols if c in aggregated.columns]
        aggregated = aggregated[cols]

        return aggregated

    def _generate_timeframe_from_1m_silent(
        self,
        symbol: str,
        target_interval: str,
    ) -> pd.DataFrame | None:
        """
        Generate higher timeframe data by aggregating from 1m data (silent version).

        Same as generate_timeframe_from_1m but without any print output.
        Used internally by generate_all_timeframes_from_1m for cleaner progress bars.

        Args:
            symbol: Trading pair symbol (e.g., "ETHUSDT")
            target_interval: Target interval to generate (e.g., "5m", "15m", "1h")

        Returns:
            DataFrame with aggregated OHLCV data, or None if 1m data not found
        """
        if target_interval not in self.INTERVAL_TO_MILLISECONDS:
            return None

        if target_interval == "1m":
            return None

        # Load 1m data
        symbol_dir_1m = self.output_directory / "1m" / symbol
        if not symbol_dir_1m.exists():
            return None

        csv_files = list(symbol_dir_1m.glob("*.csv"))
        if not csv_files:
            return None

        df_1m = pd.read_csv(csv_files[0])

        # Calculate target interval in minutes
        target_minutes = self.INTERVAL_TO_MILLISECONDS[target_interval] // (60 * 1000)
        target_seconds = target_minutes * 60

        # Ensure timestamp is numeric
        df_1m["timestamp"] = df_1m["timestamp"].astype(float)

        # Calculate bar group based on timestamp
        df_1m["bar_group"] = (df_1m["timestamp"] // target_seconds).astype(int)

        # Aggregate by bar group using proper OHLCV rules
        aggregated = df_1m.groupby("bar_group").agg({
            "open": "first",       # First open in window
            "high": "max",         # Max high in window
            "low": "min",          # Min low in window
            "close": "last",       # Last close in window
            "volume": "sum",       # Sum of volumes
        }).reset_index()  # Keep bar_group for timestamp calculation

        # Calculate canonical timestamp from bar_group (ensures proper boundary alignment)
        # This fixes misalignment issues when first 1m bar in group is missing
        aggregated["timestamp"] = (aggregated["bar_group"] * target_seconds).astype(float)

        # Preserve additional columns if present
        extra_cols = ["quote_asset_volume", "n_trades", "taker_buy_base_volume", "taker_buy_quote_volume"]
        for col in extra_cols:
            if col in df_1m.columns:
                agg_extra = df_1m.groupby("bar_group")[col].sum().reset_index(drop=True)
                aggregated[col] = agg_extra.values

        # Reorder columns with timestamp first, drop bar_group
        cols = ["timestamp", "open", "high", "low", "close", "volume"]
        cols += [c for c in extra_cols if c in aggregated.columns]
        aggregated = aggregated[cols]

        return aggregated
