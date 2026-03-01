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
import logging.handlers
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path


def load_env() -> None:
    """Load environment variables from .env file if it exists."""
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


# Load .env BEFORE importing config (which reads os.environ at module level)
load_env()

from balance import BalanceTracker
from config import ACTIVE_SYMBOLS, MIN_WARMUP_TICKS, SYMBOLS
from exchange_info import ExchangeInfoManager
from fee_manager import FeeManager
from dashboard_server import DashboardLogHandler, DashboardServer
from fetchers.binance import BinanceFetcher
from fetchers.bitget import BitgetFetcher
from fetchers.bybit import BybitFetcher
from fetchers.gateio import GateIOFetcher
from fetchers.kucoin import KuCoinFetcher
from fetchers.mexc import MEXCFetcher
from fetchers.okx import OKXFetcher
from fetchers.pionex import PionexFetcher
from fetchers.bitfinex import BitfinexFetcher
from monitor import ArbitrageMonitor
from optimizer import SymbolOptimizer
from settings import load_settings
from state_manager import StateManager


def setup_logging() -> tuple[Path, DashboardLogHandler]:
    """Configure logging to console, daily-rotating file (UTC), and dashboard handler."""
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / "coirnabot.log"

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fmt.converter = time.gmtime  # UTC timestamps

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    # Daily rotation at 00:00 UTC, keep 30 days
    file_h = logging.handlers.TimedRotatingFileHandler(
        log_file, when="midnight", utc=True, backupCount=30,
    )
    file_h.suffix = "%Y-%m-%d"
    file_h.setFormatter(fmt)

    dashboard_h = DashboardLogHandler(maxlen=500)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(file_h)
    root.addHandler(dashboard_h)
    return log_file, dashboard_h


async def main() -> None:
    """Run all exchange fetchers and arbitrage monitor concurrently."""
    log_file, log_handler = setup_logging()
    logger = logging.getLogger(__name__)

    # Load settings from settings.json (or create defaults)
    settings = load_settings()
    trade_amount = settings["trade_amount_usd"]
    total_capital = settings.get("total_capital", 1800.0)
    adaptive_mode = settings.get("adaptive_mode", True)

    # Initialize FeeManager from settings (backward compatible — empty → defaults)
    fee_manager = FeeManager.from_settings_dict(
        settings.get("fee_configs", {}),
        real_mode=settings.get("fee_real_mode", False),
    )

    # Initialize TransferFeeManager from settings (backward compatible — empty → defaults)
    from transfer_fee_manager import TransferFeeManager
    transfer_fee_manager = TransferFeeManager.from_settings_dict(
        settings.get("transfer_configs", {}),
    )

    fetchers = [
        BinanceFetcher(),
        OKXFetcher(),
        BybitFetcher(),
        BitgetFetcher(),
        MEXCFetcher(),
        KuCoinFetcher(),
        GateIOFetcher(),
        PionexFetcher(),
        BitfinexFetcher(),
    ]

    # Derive active exchanges from fetchers, filtering out disabled ones
    enabled_set = set(fee_manager.get_enabled_exchanges())
    active_exchanges = [
        f.exchange_name for f in fetchers
        if f.exchange_name in enabled_set
    ]
    if not active_exchanges:
        # Safety: if all are disabled, fall back to all
        active_exchanges = [f.exchange_name for f in fetchers]
        logger.warning("[Config] All exchanges disabled — falling back to all 9")
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

    # Fetch exchange trading rules (lot sizes, tick sizes, min notionals)
    # before any trading starts. Addresses D-01, D-02, D-03.
    exchange_info = ExchangeInfoManager(exchanges=active_exchanges)
    await exchange_info.fetch_all()

    # D-16: Validate USDT withdrawal fees against live exchange data
    await exchange_info.validate_withdrawal_fees(transfer_fee_manager)

    balance = BalanceTracker(
        exchanges=active_exchanges,
        symbols=active_symbols,
        allocations=allocations,
        rebalance_cooldown=settings.get("rebalance_cooldown", 30.0),
        trade_amount=trade_amount,
        adaptive_mode=adaptive_mode,
        exchange_info=exchange_info,
        fee_manager=fee_manager,
        transfer_fee_manager=transfer_fee_manager,
        hourly_external_transfer_cap=settings.get("hourly_external_transfer_cap", 2.0),
        bitfinex_reserve_pct=settings.get("bitfinex_reserve_pct", 0.15),
    )
    monitor = ArbitrageMonitor(
        fetchers,
        balance=balance,
        symbols=active_symbols,
        exchanges=active_exchanges,
        trade_amount=trade_amount,
        min_net_profit_pct=settings.get("min_net_profit_pct", 0.02),
        min_misses_before_rebalance=int(settings.get("min_misses_before_rebalance", 15)),
        rebalance_roi_horizon=settings.get("rebalance_roi_horizon", 1800),
        total_capital=total_capital,
        adaptive_mode=adaptive_mode,
        log_file=log_file,
        exchange_info=exchange_info,
        fee_manager=fee_manager,
        net_pct_sizing_enabled=settings.get("net_pct_sizing_enabled", True),
        net_pct_multiplier_cap=settings.get("net_pct_multiplier_cap", 2.5),
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
        fee_manager=fee_manager,
        num_active_symbols=settings.get("num_active_symbols", 3),
        scoring_window=settings.get("scoring_window", 1800),
        evaluation_interval=settings.get("evaluation_interval", 300),
        safety_multiplier=settings.get("safety_multiplier", 2.0),
        auto_rotate=settings.get("auto_rotate", True),
        discovery_duration=settings.get("discovery_duration", 300),
        max_active_symbols=settings.get("max_active_symbols", 8),
        min_rebalance_score=settings.get("min_rebalance_score", 0.0001),
        confirmation_period=settings.get("confirmation_period", 300),
        score_stability_seconds=settings.get("score_stability_seconds", 120),
        score_stability_factor=settings.get("score_stability_factor", 0.5),
        promotion_threshold=settings.get("promotion_threshold", 0.0001),
        demotion_threshold=settings.get("demotion_threshold", 0.0),
        demotion_period=settings.get("demotion_period", 600),
        demotion_cooldown_multiplier=settings.get("demotion_cooldown_multiplier", 5.0),
        reallocation_cost_horizon=settings.get("reallocation_cost_horizon", 2.0),
        min_warmup_ticks=MIN_WARMUP_TICKS,
    )
    # Apply configurable score thresholds and gate params from settings
    if "trading_score_threshold" in settings:
        optimizer._trading_threshold = settings["trading_score_threshold"]
    if "strong_score_threshold" in settings:
        optimizer._strong_threshold = settings["strong_score_threshold"]
    if "very_strong_score_threshold" in settings:
        optimizer._very_strong_threshold = settings["very_strong_score_threshold"]
    if "net_pnl_gate_warmup_trades" in settings:
        monitor._net_pnl_gate_warmup_trades = int(settings["net_pnl_gate_warmup_trades"])
    if "net_pnl_gate_grace_seconds" in settings:
        monitor._net_pnl_gate_grace_seconds = int(settings["net_pnl_gate_grace_seconds"])
    if "rebalance_roi_divisor" in settings:
        monitor._rebalance_roi_divisor = int(settings["rebalance_roi_divisor"])

    monitor.set_optimizer(optimizer)
    monitor.record_config_snapshot("initial")
    logger.info(
        f"[Config] trade_amount=${trade_amount} capital=${total_capital:.0f} "
        f"adaptive={adaptive_mode} min_net={settings.get('min_net_profit_pct', 0.02):.2f}% "
        f"rebalance_cooldown={settings.get('rebalance_cooldown', 30.0):.0f}s "
        f"max_symbols={settings.get('max_active_symbols', 8)} "
        f"execution_mode={settings.get('execution_mode', 'simulation')}"
    )

    state_mgr = StateManager()
    saved = state_mgr.load()
    if saved:
        balance.from_state_dict(saved["balance"])
        monitor.from_state_dict(saved["monitor"])
        optimizer.from_state_dict(saved["optimizer"])
        if "fee_manager" in saved:
            fee_manager.from_state_dict(saved["fee_manager"])
        # Sync symbols across components to match restored optimizer state
        if optimizer._active_symbols:
            monitor.update_symbols(optimizer._active_symbols)
            balance.update_symbols(optimizer._active_symbols)
        logger.info(
            f"[State] Restored: {len(monitor._trades)} trades, "
            f"{len(balance.transfers)} transfers, "
            f"{len(optimizer._active_symbols)} active symbols"
        )
    else:
        logger.info("[State] Starting fresh session")

    dashboard = DashboardServer(
        monitor, balance, fetchers, settings,
        optimizer=optimizer, log_handler=log_handler, state_manager=state_mgr,
        fee_manager=fee_manager,
        transfer_fee_manager=transfer_fee_manager,
    )

    # Demo/testnet portfolio comparison (optional — needs API keys in .env)
    from demo_fetcher import DemoPortfolioFetcher
    demo_fetcher = DemoPortfolioFetcher(
        balance_tracker=balance, fetchers=fetchers, poll_interval=15.0,
        fee_manager=fee_manager,
    )
    if saved and "demo_fetcher" in saved:
        demo_fetcher.from_state_dict(saved["demo_fetcher"])
    if demo_fetcher.enabled:
        dashboard.set_demo_fetcher(demo_fetcher)
    else:
        logger.info("[DemoCompare] Disabled (no API keys configured in .env)")

    # Phase 2: Demo order execution (optional — needs execution_mode=demo)
    execution_mode = settings.get("execution_mode", "simulation")
    demo_executor = None

    if execution_mode == "demo":
        from config import (
            BINANCE_TESTNET_API_KEY, OKX_DEMO_API_KEY, BYBIT_DEMO_API_KEY,
        )
        from executor import DemoExecutor
        from executors.binance_exec import BinanceExecutor
        from executors.okx_exec import OKXExecutor
        from executors.bybit_exec import BybitExecutor

        exchange_executors: dict = {}
        if BINANCE_TESTNET_API_KEY:
            exchange_executors["Binance"] = BinanceExecutor(exchange_info)
        if OKX_DEMO_API_KEY:
            exchange_executors["OKX"] = OKXExecutor(exchange_info)
        if BYBIT_DEMO_API_KEY:
            exchange_executors["Bybit"] = BybitExecutor(exchange_info)

        if exchange_executors:
            demo_executor = DemoExecutor(exchange_info, exchange_executors)

            # Restore pending orders from saved state (nested in monitor state)
            if saved:
                monitor_state = saved.get("monitor", {})
                executor_state = monitor_state.get("demo_executor")
                if executor_state:
                    demo_executor.from_state_dict(executor_state)

            # Startup reconciliation: check pending orders + compare balances
            try:
                await demo_executor.recover_pending_orders()
                await demo_executor.reconcile_balances(balance)
            except Exception as e:
                logger.error(f"[Reconcile] Startup reconciliation failed: {e}")

            monitor.set_executor(
                demo_executor, state_mgr,
                demo_fetcher if demo_fetcher.enabled else None,
            )
            balance._execution_mode = "demo"
            logger.info(
                f"Demo execution enabled for: {list(exchange_executors.keys())}"
            )
        else:
            logger.warning(
                "[Executor] execution_mode=demo but no API keys configured"
            )
    else:
        logger.info("[Executor] Simulation mode (no real orders)")

    loop = asyncio.get_running_loop()

    def shutdown_handler():
        logger.info("Shutdown signal received, saving state...")
        state_mgr.save(balance, monitor, optimizer, demo_fetcher if demo_fetcher.enabled else None, fee_manager=fee_manager)
        state_mgr.stop()
        if demo_fetcher.enabled:
            demo_fetcher.stop()
        for fetcher in fetchers:
            fetcher.stop()
        monitor.stop()
        optimizer.stop()
        dashboard.stop()
        if demo_executor:
            asyncio.ensure_future(demo_executor.close())

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_handler)

    tasks = [asyncio.create_task(f.run()) for f in fetchers]
    tasks.append(asyncio.create_task(monitor.run()))
    tasks.append(asyncio.create_task(optimizer.run()))
    tasks.append(asyncio.create_task(dashboard.run()))
    tasks.append(asyncio.create_task(state_mgr.periodic_save(
        balance, monitor, optimizer, demo_fetcher if demo_fetcher.enabled else None,
        fee_manager=fee_manager,
    )))
    if demo_fetcher.enabled:
        tasks.append(asyncio.create_task(demo_fetcher.run()))

    try:
        await asyncio.gather(*tasks)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        state_mgr.save(balance, monitor, optimizer, demo_fetcher if demo_fetcher.enabled else None, fee_manager=fee_manager)
        for fetcher in fetchers:
            fetcher.stop()
        monitor.stop()
        optimizer.stop()
        dashboard.stop()
        if demo_executor:
            await demo_executor.close()
        raise
    finally:
        monitor.print_summary()
        logger.info("CoirnaBot Price Fetcher stopped")


if __name__ == "__main__":
    asyncio.run(main())
