#!/usr/bin/env python
"""
Binance Perpetual Futures Data Fetcher CLI

Downloads historical candle (kline) data from Binance Perpetual Futures API
and saves to both CSV and Parquet files.

IMPORTANT: This script ALWAYS fetches only 1m data from Binance API.
Higher timeframes (3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M) are aggregated from 1m data
to ensure accurate OHLCV values.

Parquet files are optimized for fast loading (~5-10x faster than CSV) and
contain only the essential OHLCV columns. CSV files contain full data.

Usage:
    # Fetch 1m data for ALL symbols and aggregate ALL HTF timeframes
    python fetch_binance_data.py --all --all-intervals

    # Fetch 1m data for all symbols (no HTF aggregation)
    python fetch_binance_data.py --all

    # Fetch 1m and aggregate specific HTF timeframes
    python fetch_binance_data.py --all --interval 5m,15m,1h

    # Custom end date (UTC+3 timezone)
    python fetch_binance_data.py --all --interval 5m,15m --end-date "2025-12-08 00:00"

    # List all predefined symbols
    python fetch_binance_data.py --list-symbols

Intelligent Update System:
    - For NEW symbols: Fetches ALL historical data from listing date
    - For EXISTING symbols: Only fetches new data since last update
    - Binance Futures started on 2019-09-08 (BTCUSDT was first)

HTF Aggregation (from 1m data):
    After fetching 1m data, the script aggregates specified higher timeframes.
    This ensures accurate OHLCV aggregation:
        - Open = first 1m open in window
        - High = MAX of all 1m highs
        - Low = MIN of all 1m lows
        - Close = LAST 1m close
        - Volume = SUM of all 1m volumes

    Available HTF: 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M

Output structure:
    data/
    ├── 1m/
    │   ├── BTCUSDT/
    │   │   ├── 2019_09_08-2025_12_07.csv      (full data, 10 columns)
    │   │   └── 2019_09_08-2025_12_07.parquet  (OHLCV only, 6 columns)
    │   ├── ETHUSDT/
    │   │   ├── 2019_09_08-2025_12_07.csv
    │   │   └── 2019_09_08-2025_12_07.parquet
    │   └── ...
    └── ...
"""

import argparse
from datetime import datetime, timedelta

from binance_perpetual_fetcher import BinancePerpetualDataFetcher

# Binance Perpetual Futures launched on 2019-09-08 (BTCUSDT was first)
BINANCE_FUTURES_LAUNCH_DATE = datetime(2019, 9, 8, 0, 0, 0)

# UTC+3 offset in hours
UTC_PLUS_3_OFFSET_HOURS = 3


def get_default_end_date() -> datetime:
    """
    Get the default end date (current local time).

    When no --end-date is provided, use the current local time.
    This ensures the script always fetches the latest available data.

    Returns:
        Current local time as a naive datetime
    """
    return datetime.now()


# All HTF intervals that can be aggregated from 1m data (largest to smallest)
# Note: 1m is always fetched from API, these are aggregation targets
ALL_HTF_INTERVALS = [
    "1M",  # 1 month
    "1w",  # 1 week
    "1d",  # 1 day
    "4h",  # 4 hours
    "1h",  # 1 hour
    "30m",  # 30 minutes
    "15m",  # 15 minutes
    "5m",  # 5 minutes
    "3m",  # 3 minutes
]


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Fetch historical candle data from Binance Perpetual Futures",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch 1m data for ALL symbols and aggregate ALL HTF timeframes
  python fetch_binance_data.py --all --all-intervals

  # Fetch 1m data for all symbols (no HTF aggregation)
  python fetch_binance_data.py --all

  # Fetch 1m and aggregate specific HTF timeframes
  python fetch_binance_data.py --all --interval 5m,15m,1h

  # Custom end date (UTC+3 timezone)
  python fetch_binance_data.py --all --interval 5m,15m --end-date "2025-12-08 00:00"

  # Fetch 1m data for a single symbol
  python fetch_binance_data.py --symbol SOLUSDT

  # Fetch 1m and aggregate HTFs for single symbol
  python fetch_binance_data.py --symbol SOLUSDT --interval 5m,15m,1h

  # List all predefined symbols
  python fetch_binance_data.py --list-symbols

IMPORTANT: This script ALWAYS fetches 1m data from Binance API.
Higher timeframes are aggregated from 1m data to ensure accuracy.

HTF intervals available for aggregation (--interval):
  3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M

Date/Time Format:
  --end-date uses UTC+3 timezone. Example: "2025-12-08 00:00" = midnight Turkey time

Intelligent Update System:
  - First run: Downloads ALL historical 1m data from each symbol's listing date
  - Subsequent runs: Only fetches new 1m candles since last update
  - Adding new symbols: New symbols get full history, existing ones just update

  Binance Futures started on 2019-09-08 (BTCUSDT first). Each symbol's data
  starts from when it was actually listed on Binance Futures.

Output structure:
  data/
  ├── 1m/          <- Always fetched from Binance API
  │   ├── BTCUSDT/
  │   │   ├── 2019_09_08-2025_12_07.csv
  │   │   └── 2019_09_08-2025_12_07.parquet
  │   └── ...
  ├── 5m/          <- Aggregated from 1m
  ├── 15m/         <- Aggregated from 1m
  ├── 1h/          <- Aggregated from 1m
  └── ...
        """,
    )

    # Main options
    parser.add_argument("--symbol", type=str, help="Trading pair symbol (e.g., SOLUSDT, BTCUSDT, SOL-USDT)")

    parser.add_argument(
        "--all", action="store_true", help="Fetch ALL historical data for predefined symbols (from their listing date)"
    )

    parser.add_argument(
        "--interval",
        type=str,
        default=None,
        help="HTF intervals to aggregate from 1m (comma-separated). Example: 5m,15m,1h,4h. "
             "Available: 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M",
    )

    parser.add_argument(
        "--all-intervals",
        action="store_true",
        help="Aggregate ALL HTF intervals from 1m: 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M",
    )

    # Date range options
    parser.add_argument("--days", type=int, default=None, help="Number of days to fetch (from today backwards)")

    parser.add_argument("--start-date", type=str, default=None, help="Start date (YYYY-MM-DD or 'YYYY-MM-DD HH:MM')")

    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date in UTC+3 format: 'YYYY-MM-DD HH:MM'. Example: '2025-12-08 00:00' means midnight UTC+3",
    )

    # Output options
    parser.add_argument("--output-dir", type=str, default="data", help="Output directory for CSV files (default: data)")

    # Utility options
    parser.add_argument("--list-symbols", action="store_true", help="List all predefined perpetual futures symbols")

    parser.add_argument("--list-api-symbols", action="store_true", help="List all available symbols from Binance API")

    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress all output (no prints, no progress bars)")

    parser.add_argument(
        "--regenerate-parquet",
        action="store_true",
        help="Regenerate parquet files from CSV. Can be combined with --all to run after fetch/aggregation."
    )

    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Force full HTF regeneration instead of incremental update. Use when HTF data is corrupted."
    )

    return parser.parse_args()


def parse_date(date_string: str) -> datetime:
    """
    Parse date string to datetime object.

    IMPORTANT: All times are treated as LOCAL time (UTC+3) because Python's
    datetime.timestamp() interprets naive datetimes as local time.

    Args:
        date_string: Date string in various formats:
            - YYYY-MM-DD
            - YYYY-MM-DD HH:MM

    Returns:
        datetime object in local time

    Raises:
        ValueError: If date format is invalid
    """
    # Remove "UTC+3" suffix if present (for backwards compatibility)
    clean_string = date_string.replace("UTC+3", "").replace("utc+3", "").strip()

    try:
        if " " in clean_string or "T" in clean_string:
            parsed = datetime.strptime(clean_string.replace("T", " "), "%Y-%m-%d %H:%M")
        else:
            parsed = datetime.strptime(clean_string, "%Y-%m-%d")

        # No conversion needed - user provides local time, system uses local time
        return parsed
    except ValueError as err:
        raise ValueError(
            f"Invalid date format: {date_string}. Use 'YYYY-MM-DD HH:MM' (interpreted as local time / UTC+3)"
        ) from err


def list_predefined_symbols() -> None:
    """List all predefined symbols."""
    symbols = BinancePerpetualDataFetcher.get_predefined_symbols()

    print(f"\nPredefined Perpetual Futures Symbols ({len(symbols)} total):")
    print("=" * 70)

    # Print in columns
    columns = 5
    for i in range(0, len(symbols), columns):
        row = symbols[i : i + columns]
        print("  ".join(f"{s:<14}" for s in row))

    print("=" * 70)
    print("\nUse --all to fetch ALL historical data for these symbols")
    print("Example: python fetch_binance_data.py --all --interval 1m")


def list_api_symbols(fetcher: BinancePerpetualDataFetcher) -> None:
    """List all available symbols from Binance API."""
    print("Fetching available symbols from Binance Perpetual Futures API...")
    symbols = fetcher.get_available_symbols()

    if not symbols:
        print("Failed to fetch symbols or no symbols available.")
        return

    print(f"\nAvailable Perpetual Futures Symbols ({len(symbols)} total):")
    print("=" * 70)

    # Print in columns
    columns = 5
    for i in range(0, len(symbols), columns):
        row = symbols[i : i + columns]
        print("  ".join(f"{s:<14}" for s in row))

    print("=" * 70)


def fetch_single_symbol(
    fetcher: BinancePerpetualDataFetcher, symbol: str, interval: str, start_date: datetime, end_date: datetime,
    quiet: bool = False
) -> None:
    """Fetch data for a single symbol."""
    if not quiet:
        print("=" * 70)
        print("Binance Perpetual Futures Data Fetcher")
        print("=" * 70)
        print(f"Symbol:     {symbol}")
        print(f"Interval:   {interval}")
        print(f"Start:      {start_date.strftime('%Y-%m-%d %H:%M')}")
        print(f"End:        {end_date.strftime('%Y-%m-%d %H:%M')}")
        print(f"Output dir: {fetcher.output_directory}")
        print("=" * 70)

    try:
        dataframe = fetcher.fetch_candles(
            symbol=symbol, interval=interval, start_date=start_date, end_date=end_date, save_to_csv=True
        )

        if dataframe.empty:
            if not quiet:
                print("No data fetched. Please check the symbol and date range.")
            return

        # Print summary
        if not quiet:
            print("\n" + "=" * 70)
            print("Download Summary")
            print("=" * 70)
            print(f"Total candles:  {len(dataframe):,}")
            print(
                f"Date range:     {datetime.fromtimestamp(dataframe['timestamp'].min()):%Y-%m-%d %H:%M} to "
                f"{datetime.fromtimestamp(dataframe['timestamp'].max()):%Y-%m-%d %H:%M}"
            )
            print(f"Price range:    ${dataframe['low'].min():.2f} - ${dataframe['high'].max():.2f}")
            print(f"Total volume:   {dataframe['volume'].sum():,.2f}")
            print("=" * 70)

    except Exception as error:
        if not quiet:
            print(f"\nError: {error}")
        raise


def fetch_all_symbols(
    fetcher: BinancePerpetualDataFetcher, interval: str, start_date: datetime, end_date: datetime
) -> None:
    """Fetch data for all predefined symbols."""
    fetcher.fetch_all_symbols(interval=interval, start_date=start_date, end_date=end_date)


def main():
    """Main entry point."""
    args = parse_arguments()

    # Create fetcher with quiet mode if specified
    fetcher = BinancePerpetualDataFetcher(output_directory=args.output_dir, quiet=args.quiet)

    # List predefined symbols mode
    if args.list_symbols:
        list_predefined_symbols()
        return

    # List API symbols mode
    if args.list_api_symbols:
        list_api_symbols(fetcher)
        return

    # Regenerate parquet ONLY mode (no fetch)
    if args.regenerate_parquet and not args.symbol and not args.all:
        fetcher.regenerate_all_parquet()
        return

    # Validate that either --symbol or --all is provided
    if not args.symbol and not args.all:
        print("Error: Either --symbol or --all is required")
        print("Example: python fetch_binance_data.py --symbol SOLUSDT --interval 1m")
        print("Example: python fetch_binance_data.py --all --interval 1m")
        return

    # Determine date range
    end_date = parse_date(args.end_date) if args.end_date else get_default_end_date()

    if args.start_date:
        start_date = parse_date(args.start_date)
    elif args.days:
        start_date = end_date - timedelta(days=args.days)
    else:
        # Default: fetch ALL historical data from Binance Futures launch date
        # The API will automatically return data from when each symbol was listed
        start_date = BINANCE_FUTURES_LAUNCH_DATE

    # Determine which HTF intervals to aggregate
    if args.all_intervals:
        htf_intervals_to_aggregate = ALL_HTF_INTERVALS
    elif args.interval:
        # Parse comma-separated intervals
        htf_intervals_to_aggregate = [i.strip() for i in args.interval.split(",") if i.strip()]
        # Filter out 1m since it's always fetched directly
        htf_intervals_to_aggregate = [i for i in htf_intervals_to_aggregate if i != "1m"]
    else:
        htf_intervals_to_aggregate = []

    # Determine which symbols to process
    if args.all:
        symbols = BinancePerpetualDataFetcher.get_predefined_symbols()
    else:
        symbols = [args.symbol.upper().replace("-", "")]

    # STEP 1: Always fetch 1m data first
    if not args.quiet:
        print(f"\n{'#' * 70}")
        print("# STEP 1: FETCHING 1m DATA FROM BINANCE API")
        print(f"{'#' * 70}")

    if args.all:
        fetch_all_symbols(fetcher, "1m", start_date, end_date)
    else:
        fetch_single_symbol(fetcher, args.symbol, "1m", start_date, end_date, quiet=args.quiet)

    # STEP 2: Aggregate HTF intervals from 1m data
    if htf_intervals_to_aggregate:
        if not args.quiet:
            print(f"\n{'#' * 70}")
            print(f"# STEP 2: AGGREGATING HTF DATA FROM 1m ({len(htf_intervals_to_aggregate)} timeframes)")
            print(f"# Timeframes: {', '.join(htf_intervals_to_aggregate)}")
            print(f"{'#' * 70}")

        fetcher.generate_all_timeframes_from_1m(
            symbols=symbols,
            timeframes=htf_intervals_to_aggregate,
            force_full=args.force_full
        )

        if not args.quiet:
            print(f"\n{'=' * 70}")
            print(f"COMPLETED HTF AGGREGATION FOR {len(symbols)} SYMBOLS")
            print(f"Timeframes: {', '.join(htf_intervals_to_aggregate)}")
            print(f"{'=' * 70}")
    else:
        if not args.quiet:
            print(f"\n{'=' * 70}")
            print("COMPLETED 1m DATA FETCH (no HTF aggregation requested)")
            print("Use --interval 5m,15m,1h or --all-intervals to aggregate HTF data")
            print(f"{'=' * 70}")

    # STEP 3: Regenerate parquet files (if requested)
    if args.regenerate_parquet:
        if not args.quiet:
            print(f"\n{'#' * 70}")
            print("# STEP 3: REGENERATING PARQUET FILES FROM CSV")
            print(f"{'#' * 70}")

        fetcher.regenerate_all_parquet()


if __name__ == "__main__":
    main()
