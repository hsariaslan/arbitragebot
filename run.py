#!/usr/bin/env python3
"""
ArbitrageBot v0.31.0-beta — multi-config orchestrator entrypoint.

Boots SHARED resources once (fetchers, ExchangeInfoManager,
TransferFeeManager, FundingMonitor, futures executor, demo fetcher,
DashboardServer) and constructs PER-CONFIG bundles (BalanceTracker,
ArbitrageMonitor, SymbolOptimizer, FeeManager, HedgeManager, optional
DemoExecutor) via the Orchestrator.

The Orchestrator's `run()` coroutine round-robin sweeps every config each
tick (~1Hz) instead of spawning a per-component task graph. Single-config
operation is the same code path as multi-config — the registry just has
one entry.

Press Ctrl+C to stop gracefully (saves state per config).
"""

import asyncio
import logging
import logging.handlers
import os
import signal
import sys
import time
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

from config import ACTIVE_SYMBOLS, SYMBOLS, __version__
from dashboard_server import DashboardLogHandler, DashboardServer
from exchange_info import ExchangeInfoManager
from fetchers.binance import BinanceFetcher
from fetchers.bitget import BitgetFetcher
from fetchers.bybit import BybitFetcher
from fetchers.gateio import GateIOFetcher
from fetchers.kucoin import KuCoinFetcher
from fetchers.mexc import MEXCFetcher
from fetchers.okx import OKXFetcher
from fetchers.pionex import PionexFetcher
from fetchers.bitfinex import BitfinexFetcher
from log_context import ConfigPrefixFilter
from orchestrator import CapacityMonitor, ConfigFactory, Orchestrator
from settings import load_registry
from state_manager import StateManager


def setup_logging() -> tuple[Path, DashboardLogHandler, "logging.handlers.QueueListener"]:
    """Configure async logging via QueueHandler + QueueListener.

    v0.31.0-beta+: every `logger.info(...)` call from the orchestrator's
    per-config tick used to do synchronous I/O — format the record, run
    filters, write to the rotating file, append to the dashboard buffer,
    extract component via regex. At 48+ configs, that's measurable
    contribution to sweep time.

    New pipeline:
      - The HOT PATH (logger.info from any thread/task) only does:
          1. Run ConfigPrefixFilter (stamps prefix from ConfigContextVar
             — MUST run synchronously to capture per-task context)
          2. Enqueue the LogRecord onto an unbounded Queue (microseconds)
      - A daemon thread (QueueListener) drains the queue and dispatches
        to the real handlers (file, console, dashboard buffer). All
        blocking I/O happens off the orchestrator tick path.

    The unbounded queue is intentional. Logging back-pressure on the
    orchestrator would be far worse than memory growth: a normal session
    produces ~10 records/sec and the listener drains as fast as I/O
    allows. If the disk catastrophically backs up, the queue grows but
    the bot keeps trading; we'd notice via Bot Logs / file truncation
    long before memory becomes a real concern.

    Returns the listener so the caller can `listener.stop()` on shutdown
    to flush any queued records before exit.
    """
    import queue
    import logging.handlers

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / "arbitragebot.log"

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fmt.converter = time.gmtime  # UTC timestamps

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    # Console only surfaces WARNING+ERROR. The file + dashboard buffer
    # still capture every INFO/DEBUG record. Without this cap, every
    # per-tick log line would print to stderr — noisy when running under
    # tmux/SSH and slow when the terminal is hooked into a logger
    # daemon. WARNING+ERROR are the things you actually want to see live
    # without grep'ing the file (anomaly triggers, capacity warnings,
    # fatal startup errors).
    console.setLevel(logging.WARNING)

    file_h = logging.handlers.TimedRotatingFileHandler(
        log_file, when="midnight", utc=True, backupCount=30,
    )
    file_h.suffix = "%Y-%m-%d"
    file_h.setFormatter(fmt)

    dashboard_h = DashboardLogHandler(maxlen=2000)

    # Build the async pipeline.
    #
    # ConfigPrefixFilter MUST run synchronously on the calling thread so
    # it can read ConfigContextVar (set by the orchestrator's per-config
    # sweep). The listener thread doesn't share contextvars, so a filter
    # there would always see ctx=None and fail to prefix records. Install
    # the filter on the QueueHandler — it fires once on enqueue, the
    # prefix is baked into record.msg, and the listener's handlers see
    # the already-prefixed record.
    log_queue: queue.Queue = queue.Queue(-1)  # unbounded
    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_handler.addFilter(ConfigPrefixFilter())

    listener = logging.handlers.QueueListener(
        log_queue,
        console,
        file_h,
        dashboard_h,
        respect_handler_level=True,
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Idempotent: strip any handlers a previous setup_logging() left on
    # the root logger (test re-runs, hot reloads).
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(queue_handler)

    # Start the listener thread. Daemon=True so it exits with the process
    # if shutdown is missed; cooperative .stop() is preferred and flushes
    # remaining records.
    listener.start()
    return log_file, dashboard_h, listener


async def main() -> None:
    log_file, log_handler, log_listener = setup_logging()
    logger = logging.getLogger(__name__)
    logger.info(f"ArbitrageBot v{__version__} starting — log: {log_file}")

    # GC tuning — at 48 configs the bot accumulates millions of long-lived
    # SymbolTick / aggregate / state objects in optimizer/monitor/balance.
    # Default thresholds (700, 10, 10) cause gen2 GC to fire every ~70K
    # allocations — at our allocation rate that's roughly 3-4 times per
    # minute. Each gen2 scan walks ALL tracked containers in the heap,
    # taking 100ms+ once 2M+ objects accumulate. Those pauses happen
    # synchronously inside `optimizer.tick_once`, inflating sweep time.
    # Raising gen2 to 100 means it fires ~10× less often, cutting total
    # GC pause time per minute by ~10× without changing correctness
    # (gen0/gen1 still collect normally so short-lived objects are
    # reclaimed promptly).
    import gc
    gc.set_threshold(700, 100, 100)
    logger.info(
        f"[Config] GC thresholds: {gc.get_threshold()} "
        f"(raised gen1+gen2 from default 10 to reduce stop-the-world pauses)"
    )

    # ── Load multi-config registry (auto-migrates v1 → v2) ────────────
    registry = load_registry()
    n_configs = len(registry.all_configs())
    n_groups = len(registry.groups)
    sp = registry.super_primary_config
    sp_label = f"{sp.name} (in {registry.find_group_for_config(sp.id).name})" if sp else "(none)"
    logger.info(
        f"[Config] Loaded {n_groups} group(s) / {n_configs} config(s); "
        f"super-primary: {sp_label}"
    )

    # ── SHARED: TransferFeeManager (lives in registry.shared) ─────────
    from transfer_fee_manager import TransferFeeManager
    transfer_fee_manager = TransferFeeManager.from_settings_dict(
        registry.shared.get("transfer_configs", {}),
    )

    # ── SHARED: Fetchers ──────────────────────────────────────────────
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

    # ── SHARED: ExchangeInfoManager ───────────────────────────────────
    # Always fetch info for all 9 exchanges (configs may enable any subset)
    all_exchanges = [f.exchange_name for f in fetchers]
    exchange_info = ExchangeInfoManager(exchanges=all_exchanges)
    await exchange_info.fetch_all()
    await exchange_info.validate_withdrawal_fees(transfer_fee_manager)

    # ── SHARED: FundingMonitor (used for scoring + super-primary hedge) ─
    from funding_monitor import FundingMonitor
    # Funding settings come from the default config (any config could change
    # them, but they're a global subscription — 1 poll covers all configs)
    default_cfg = registry.default_config
    s = default_cfg.settings if default_cfg else {}
    funding_monitor = FundingMonitor(
        symbols=SYMBOLS,
        history_path="state/funding_history.json",
        poll_interval_seconds=float(s.get("funding_poll_interval_seconds", 60.0)),
        scoring_enabled=bool(s.get("funding_aware_scoring_enabled", True)),
        skip_threshold_4h_pct=float(s.get("funding_skip_threshold_4h_pct", -0.05)),
        skip_threshold_8h_pct=float(s.get("funding_skip_threshold_8h_pct", -0.05)),
        score_min_factor=float(s.get("funding_score_min_factor", 0.3)),
        score_max_factor=float(s.get("funding_score_max_factor", 1.5)),
    )

    # ── SHARED: per-process state manager (Phase 3 will partition) ────
    state_mgr = StateManager()

    # State loader bridge: for the migrated default config, return the
    # legacy state/session.json contents. Phase 3 replaces this with
    # per-config session files.
    legacy_state = state_mgr.load()

    def state_loader(config_id: str) -> dict | None:
        # Per-config state files (Phase 3)
        per_cfg = state_mgr.load_config(config_id) if hasattr(state_mgr, "load_config") else None
        if per_cfg is not None:
            return per_cfg
        # Legacy bridge: only feed the v0.30 state to the migrated default config
        if legacy_state and registry.default_config and registry.default_config.id == config_id:
            return legacy_state
        return None

    # ── SHARED: futures executor builder (super-primary only) ─────────
    futures_executor_holder: dict = {"current": None}

    def build_futures_executor(mode: str):
        """Lazy-build a single Binance Futures executor (mode = testnet|live).
        Returns the cached one if mode hasn't changed."""
        cur = futures_executor_holder["current"]
        if cur is not None:
            try:
                # If mode matches, reuse
                if getattr(cur, "_mode", None) == mode:
                    return cur
                # Mode changed — close and rebuild
                asyncio.ensure_future(cur.close())
                futures_executor_holder["current"] = None
            except Exception:
                pass
        from executors.binance_futures_exec import BinanceFuturesExecutor
        ex = BinanceFuturesExecutor(exchange_info=exchange_info, mode=mode)
        if not ex._credentials_ok():
            logger.warning(
                f"[Hedge] futures mode={mode} but credentials not set — "
                f"falling back to simulation."
            )
            return None
        futures_executor_holder["current"] = ex
        return ex

    # ── SHARED: demo executor builder (super-primary only) ────────────
    demo_executor_holder: dict = {"current": None}

    def build_demo_executor(mode: str):
        cur = demo_executor_holder["current"]
        if cur is not None:
            return cur
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

        if not exchange_executors:
            logger.warning(f"[Executor] mode={mode} but no API keys configured")
            return None
        ex = DemoExecutor(exchange_info, exchange_executors)
        demo_executor_holder["current"] = ex
        logger.info(
            f"[Executor] {mode} mode enabled for: {list(exchange_executors.keys())}"
        )
        return ex

    # ── PER-CONFIG factory ────────────────────────────────────────────
    factory = ConfigFactory(
        fetchers=fetchers,
        exchange_info=exchange_info,
        transfer_fee_manager=transfer_fee_manager,
        funding_monitor=funding_monitor,
        futures_executor_builder=build_futures_executor,
        demo_executor_builder=build_demo_executor,
        active_symbols_default=list(ACTIVE_SYMBOLS),
        all_symbols=list(SYMBOLS),
        # log_file=None: in multi-config mode the legacy per-tick
        # _print_table / _output (stdout print + file write) would fire
        # for every config every tick — flooding stdout AND adding 48
        # synchronous file opens/writes per second. The dashboard +
        # standard logger already capture everything; the legacy table
        # is dead in this mode.
        log_file=None,
        state_loader=state_loader,
    )

    # ── Orchestrator: builds bundles, runs the per-tick sweep ─────────
    capacity = CapacityMonitor(budget_ms=1500.0, critical_ms=2500.0)
    orchestrator = Orchestrator(
        registry=registry,
        factory=factory,
        capacity=capacity,
        tick_interval=1.0,
    )
    await orchestrator.reconcile_components()

    # ── Default-config bundle for legacy DashboardServer wiring ───────
    # (Phase 6 reshapes the dashboard to be config-aware; for now it points
    # at the default config so single-config UI keeps working.)
    default_bundle = orchestrator.get_bundle(registry.default_config.id) if registry.default_config else None
    if default_bundle is None:
        raise RuntimeError("No default config — cannot start dashboard")

    # Build a flat settings dict for legacy callers
    from settings import load_settings
    flat_settings = load_settings()

    dashboard = DashboardServer(
        default_bundle.monitor,
        default_bundle.balance,
        fetchers,
        flat_settings,
        optimizer=default_bundle.optimizer,
        log_handler=log_handler,
        state_manager=state_mgr,
        fee_manager=default_bundle.fee_manager,
        transfer_fee_manager=transfer_fee_manager,
        funding_monitor=funding_monitor,
    )
    # Wire the orchestrator + registry so the dashboard can reach every
    # bundle for the multi-config UI in Phase 6.
    dashboard._orchestrator = orchestrator
    dashboard._registry = registry

    # v0.31.0-beta+: register a post-build hook so every freshly-built
    # bundle (initial start, config_add, config_clone, mode-drift rebuild,
    # request_restart) gets the FULL hot-apply settings list. The
    # ConfigFactory only sets a handful of settings explicitly; tunables
    # like fee_threshold_multiplier and the diversification floor are only
    # applied via dashboard_server._apply_settings, so without this hook
    # new bundles run with constructor defaults instead of the user-saved
    # values (observed: Group 2/Config 1 stuck in 5h discovery because
    # optimizer.fee_threshold_multiplier was 0.5 not 0.2).
    def _post_build_apply_settings(bundle, settings: dict) -> None:
        try:
            dashboard._apply_settings_to_bundle(bundle, settings)
        except Exception as e:
            logger.error(f"[Orchestrator] post_build_hook apply failed: {e}")
    orchestrator.set_post_build_hook(_post_build_apply_settings)
    # Apply now to any bundles that were already built before the hook
    # was registered (initial reconcile_components ran before this point).
    for cfg in registry.iter_configs():
        b = orchestrator.get_bundle(cfg.id)
        if b is not None:
            _post_build_apply_settings(b, dict(cfg.settings))

    # ── Demo portfolio fetcher (compares super-primary balance vs demo accounts) ─
    from demo_fetcher import DemoPortfolioFetcher
    demo_fetcher = DemoPortfolioFetcher(
        balance_tracker=default_bundle.balance,
        fetchers=fetchers,
        poll_interval=15.0,
        fee_manager=default_bundle.fee_manager,
    )
    if legacy_state and "demo_fetcher" in legacy_state:
        demo_fetcher.from_state_dict(legacy_state["demo_fetcher"])
    if demo_fetcher.enabled:
        dashboard.set_demo_fetcher(demo_fetcher)
    else:
        logger.info("[DemoCompare] Disabled (no API keys configured in .env)")

    # ── Demo executor reconciliation (super-primary only) ─────────────
    if default_bundle.demo_executor:
        try:
            await default_bundle.demo_executor.recover_pending_orders()
            await default_bundle.demo_executor.reconcile_balances(default_bundle.balance)
        except Exception as e:
            logger.error(f"[Reconcile] Startup reconciliation failed: {e}")

    loop = asyncio.get_running_loop()

    def shutdown_handler():
        logger.info("Shutdown signal received, saving state...")
        # Per-config: save every bundle (force, ignore dirty flag)
        try:
            n = orchestrator.save_all(state_mgr)
            logger.info(f"[State] Shutdown save: {n} config(s) flushed")
        except Exception as e:
            logger.warning(f"[State] per-config save during shutdown failed: {e}")
        # Legacy state (demo_fetcher baselines + sometimes fee_manager state) —
        # keep saving until we wire those into the per-config or shared paths
        try:
            state_mgr.save(
                default_bundle.balance,
                default_bundle.monitor,
                default_bundle.optimizer,
                demo_fetcher if demo_fetcher.enabled else None,
                fee_manager=default_bundle.fee_manager,
                hedge_manager=default_bundle.hedge_manager,
            )
        except Exception as e:
            logger.warning(f"[State] legacy save during shutdown failed: {e}")
        state_mgr.stop()
        if demo_fetcher.enabled:
            demo_fetcher.stop()
        for fetcher in fetchers:
            fetcher.stop()
        for bundle in orchestrator.all_bundles():
            try:
                bundle.monitor.stop()
                bundle.optimizer.stop()
            except Exception:
                pass
        orchestrator.stop()
        dashboard.stop()
        funding_monitor.stop()
        if futures_executor_holder["current"]:
            asyncio.ensure_future(futures_executor_holder["current"].close())
        if demo_executor_holder["current"]:
            asyncio.ensure_future(demo_executor_holder["current"].close())

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_handler)

    # ── Launch all tasks ──────────────────────────────────────────────
    tasks = [asyncio.create_task(f.run()) for f in fetchers]
    tasks.append(asyncio.create_task(orchestrator.run()))
    tasks.append(asyncio.create_task(dashboard.run()))
    tasks.append(asyncio.create_task(funding_monitor.run()))
    # Per-config periodic save: only writes dirty configs, spaces fsyncs
    tasks.append(asyncio.create_task(orchestrator.periodic_save_loop(state_mgr)))
    # Legacy save (kept until demo_fetcher/uptime/etc. are migrated to
    # the new shared-state flow). Saves the default config's view to
    # state/session.json so an emergency v0.31 → v0.30 rollback still has
    # a readable state file.
    tasks.append(asyncio.create_task(state_mgr.periodic_save(
        default_bundle.balance,
        default_bundle.monitor,
        default_bundle.optimizer,
        demo_fetcher if demo_fetcher.enabled else None,
        fee_manager=default_bundle.fee_manager,
        hedge_manager=default_bundle.hedge_manager,
    )))
    if demo_fetcher.enabled:
        tasks.append(asyncio.create_task(demo_fetcher.run()))

    try:
        await asyncio.gather(*tasks)
    except Exception as e:
        import traceback
        logger.error(f"Fatal error: {e}\n{traceback.format_exc()}")
        try:
            state_mgr.save(
                default_bundle.balance,
                default_bundle.monitor,
                default_bundle.optimizer,
                demo_fetcher if demo_fetcher.enabled else None,
                fee_manager=default_bundle.fee_manager,
                hedge_manager=default_bundle.hedge_manager,
            )
        except Exception:
            pass
        for fetcher in fetchers:
            fetcher.stop()
        orchestrator.stop()
        dashboard.stop()
        funding_monitor.stop()
        if futures_executor_holder["current"]:
            await futures_executor_holder["current"].close()
        if demo_executor_holder["current"]:
            await demo_executor_holder["current"].close()
        raise
    finally:
        try:
            default_bundle.monitor.print_summary()
        except Exception:
            pass
        logger.info("ArbitrageBot stopped")
        # Drain the async log queue + flush pending records to file before
        # the process exits. Without this, records still in the queue
        # when shutdown begins would be lost (the daemon listener thread
        # is killed when the main thread returns).
        try:
            log_listener.stop()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
