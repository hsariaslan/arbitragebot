#!/usr/bin/env python3
"""
CoirnaBot Real-Time Price Fetcher

Connects to exchange WebSocket feeds, stores price snapshots to CSV
every second, and prints cross-exchange arbitrage comparison to console.

Usage:
    python run.py

Press Ctrl+C to stop gracefully.
"""

import asyncio
import logging
import signal
from datetime import datetime
from pathlib import Path

from balance import BalanceTracker
from config import ACTIVE_SYMBOLS, MIN_WARMUP_TICKS, SYMBOLS
from dashboard_server import DashboardServer
from fetchers.binance import BinanceFetcher
from fetchers.bitget import BitgetFetcher
from fetchers.bybit import BybitFetcher
from fetchers.kucoin import KuCoinFetcher
from fetchers.okx import OKXFetcher
from monitor import ArbitrageMonitor
from optimizer import SymbolOptimizer
from settings import load_settings


def setup_logging() -> Path:
    """Configure logging to console and timestamped log file under logs/."""
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = logs_dir / f"coirnabot_{ts}.log"

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    file_h = logging.FileHandler(log_file)
    file_h.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(file_h)
    return log_file


async def main() -> None:
    """Run all exchange fetchers and arbitrage monitor concurrently."""
    log_file = setup_logging()
    logger = logging.getLogger(__name__)

    # Load settings from settings.json (or create defaults)
    settings = load_settings()
    trade_amount = settings["trade_amount_usd"]
    total_capital = settings.get("total_capital", 1800.0)
    adaptive_mode = settings.get("adaptive_mode", True)

    fetchers = [
        BinanceFetcher(),
        OKXFetcher(),
        BybitFetcher(),
        BitgetFetcher(),
        KuCoinFetcher(),
    ]

    # Derive active exchanges from fetchers, use configured default symbols
    active_exchanges = [f.exchange_name for f in fetchers]
    active_symbols = list(ACTIVE_SYMBOLS)  # from config.py, discovery may override

    # Compute uniform initial allocations from total_capital
    per_exchange = total_capital / len(active_exchanges)
    num_positions = 1 + len(active_symbols)  # USDT + each symbol
    per_position = per_exchange / num_positions
    allocations = {
        ex: {"usdt": per_position, "crypto": {sym: per_position for sym in active_symbols}}
        for ex in active_exchanges
    }

    logger.info(f"CoirnaBot starting — log: {log_file}")
    logger.info(
        f"{len(active_exchanges)} exchanges, ${total_capital:.0f} capital, "
        f"${trade_amount}/trade"
    )

    balance = BalanceTracker(
        exchanges=active_exchanges,
        symbols=active_symbols,
        allocations=allocations,
        rebalance_cooldown=settings.get("rebalance_cooldown", 30.0),
        trade_amount=trade_amount,
        adaptive_mode=adaptive_mode,
    )
    monitor = ArbitrageMonitor(
        fetchers,
        balance=balance,
        symbols=active_symbols,
        exchanges=active_exchanges,
        trade_amount=trade_amount,
        min_net_profit_pct=settings.get("min_net_profit_pct", 0.02),
        rebalance_roi_horizon=settings.get("rebalance_roi_horizon", 1800),
        total_capital=total_capital,
        adaptive_mode=adaptive_mode,
        log_file=log_file,
    )
    optimizer = SymbolOptimizer(
        fetchers=fetchers,
        monitor=monitor,
        balance=balance,
        active_exchanges=active_exchanges,
        active_symbols=active_symbols,
        all_symbols=SYMBOLS,
        trade_amount=trade_amount,
        total_capital=total_capital,
        num_active_symbols=settings.get("num_active_symbols", 3),
        scoring_window=settings.get("scoring_window", 1800),
        evaluation_interval=settings.get("evaluation_interval", 300),
        safety_multiplier=settings.get("safety_multiplier", 2.0),
        auto_rotate=settings.get("auto_rotate", True),
        discovery_duration=settings.get("discovery_duration", 300),
        max_active_symbols=settings.get("max_active_symbols", 8),
        min_rebalance_score=settings.get("min_rebalance_score", 0.0001),
        confirmation_period=settings.get("confirmation_period", 300),
        promotion_threshold=settings.get("promotion_threshold", 0.0001),
        demotion_threshold=settings.get("demotion_threshold", 0.0),
        demotion_period=settings.get("demotion_period", 600),
        min_warmup_ticks=MIN_WARMUP_TICKS,
    )
    monitor.set_optimizer(optimizer)
    monitor.record_config_snapshot("initial")
    dashboard = DashboardServer(monitor, balance, fetchers, settings, optimizer=optimizer)

    loop = asyncio.get_running_loop()

    def shutdown_handler():
        logger.info("Shutdown signal received, stopping all fetchers...")
        for fetcher in fetchers:
            fetcher.stop()
        monitor.stop()
        optimizer.stop()
        dashboard.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)

    tasks = [asyncio.create_task(f.run()) for f in fetchers]
    tasks.append(asyncio.create_task(monitor.run()))
    tasks.append(asyncio.create_task(optimizer.run()))
    tasks.append(asyncio.create_task(dashboard.run()))

    try:
        await asyncio.gather(*tasks)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        for fetcher in fetchers:
            fetcher.stop()
        monitor.stop()
        optimizer.stop()
        dashboard.stop()
        raise
    finally:
        monitor.print_summary()
        logger.info("CoirnaBot Price Fetcher stopped")


if __name__ == "__main__":
    asyncio.run(main())
