"""
Multi-config orchestrator for ArbitrageBot v0.31.0-beta.

Owns the lifecycle of per-config component bundles (BalanceTracker /
ArbitrageMonitor / SymbolOptimizer / FeeManager / HedgeManager / optional
DemoExecutor) and drives the per-tick sweep across all active configs.

A single orchestrator coroutine replaces the per-component `run()` tasks
that the v0.30 single-config setup spawned. With N configs, the sweep
visits each config sequentially (in registry order), sets the
`ConfigContextVar` for log routing, and calls `optimizer.tick_once()` +
`monitor.tick_once()`. Sweep duration is recorded by `CapacityMonitor`,
which warns the operator when the budget (default 1500ms) is exceeded.

Shared resources (fetchers, FundingMonitor, ExchangeInfoManager,
TransferFeeManager, BinanceFuturesExecutor) are passed through unchanged
to every bundle. Per-config resources (Balance/Monitor/Optimizer/etc.)
are constructed by `ConfigFactory.build(config)`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from config_registry import Config, ConfigRegistry
from log_context import ConfigContextVar, set_config_context, reset_config_context

logger = logging.getLogger(__name__)


# ── Capacity monitor ────────────────────────────────────────────────────


@dataclass
class CapacitySnapshot:
    """Read-only snapshot of capacity metrics for the dashboard broadcast."""

    avg_sweep_ms: float
    p95_sweep_ms: float
    last_sweep_ms: float
    config_count: int
    over_budget: bool
    severity: str  # "ok" | "warn" | "critical"
    budget_ms: float


class CapacityMonitor:
    """Rolling window over recent sweep times. Warns when over budget."""

    def __init__(self, budget_ms: float = 1500.0, critical_ms: float = 2500.0, window: int = 60):
        self._budget_ms = budget_ms
        self._critical_ms = critical_ms
        self._samples: deque[float] = deque(maxlen=window)
        self._last_warn_ts: float = 0.0
        self._warn_interval: float = 60.0

    def record(self, sweep_ms: float, config_count: int) -> None:
        self._samples.append(sweep_ms)
        if not self._samples:
            return
        avg = sum(self._samples) / len(self._samples)
        now = time.time()
        if avg > self._budget_ms and now - self._last_warn_ts >= self._warn_interval:
            severity = "CRITICAL" if avg > self._critical_ms else "WARN"
            logger.warning(
                f"[Capacity] {severity} sweep budget exceeded: "
                f"avg={avg:.0f}ms last={sweep_ms:.0f}ms over {config_count} configs "
                f"(budget={self._budget_ms:.0f}ms)"
            )
            self._last_warn_ts = now

    def snapshot(self, config_count: int) -> CapacitySnapshot:
        if not self._samples:
            return CapacitySnapshot(0.0, 0.0, 0.0, config_count, False, "ok", self._budget_ms)
        avg = sum(self._samples) / len(self._samples)
        last = self._samples[-1]
        sorted_s = sorted(self._samples)
        p95 = sorted_s[int(len(sorted_s) * 0.95)] if len(sorted_s) >= 5 else sorted_s[-1]
        if avg > self._critical_ms:
            severity = "critical"
        elif avg > self._budget_ms:
            severity = "warn"
        else:
            severity = "ok"
        return CapacitySnapshot(
            avg_sweep_ms=avg,
            p95_sweep_ms=p95,
            last_sweep_ms=last,
            config_count=config_count,
            over_budget=(avg > self._budget_ms),
            severity=severity,
            budget_ms=self._budget_ms,
        )


# ── Component bundle ────────────────────────────────────────────────────


@dataclass
class ComponentBundle:
    """All per-config components for one Config. Built by ConfigFactory."""

    config_id: str
    group_id: str
    config_name: str
    group_name: str
    balance: Any  # BalanceTracker
    monitor: Any  # ArbitrageMonitor
    optimizer: Any  # SymbolOptimizer
    fee_manager: Any  # FeeManager
    hedge_manager: Any  # HedgeManager
    demo_executor: Any | None  # DemoExecutor or None
    execution_mode: str  # effective (sim/demo/demo_only/live)
    hedge_mode: str  # effective (sim/testnet/live)


# ── Orchestrator ───────────────────────────────────────────────────────


class Orchestrator:
    """Coordinates the per-tick sweep across all configs."""

    def __init__(
        self,
        registry: ConfigRegistry,
        factory: "ConfigFactory",
        capacity: CapacityMonitor | None = None,
        tick_interval: float = 1.0,
    ):
        self._registry = registry
        self._factory = factory
        self._capacity = capacity or CapacityMonitor()
        self._tick_interval = tick_interval
        self._bundles: dict[str, ComponentBundle] = {}
        self._running = True
        # Lock serializes structural mutations (build/teardown) against ticks
        self._swap_lock = asyncio.Lock()
        # v0.31.0-beta+: optional post-build hook so the dashboard server can
        # apply the full per-config settings dict to the freshly-built bundle.
        # The factory only sets settings it explicitly knows about — many
        # tunables (fee_threshold_multiplier, diversification_floor_*, etc.)
        # have hot-apply logic in dashboard_server but no factory wiring,
        # so without this hook a new bundle starts with constructor-default
        # values for those settings (observed: Group 2/Config 1 stuck in
        # discovery for 5+ hours because optimizer.fee_threshold_multiplier
        # was 0.5 instead of the user-saved 0.2).
        self._post_build_hook: Callable[[ComponentBundle, dict], None] | None = None

    def set_post_build_hook(
        self, hook: Callable[[ComponentBundle, dict], None] | None
    ) -> None:
        """Register a hook called after every successful bundle build.

        Hook receives (bundle, config.settings). Used by the dashboard
        server to apply the full hot-apply settings list.
        """
        self._post_build_hook = hook

    # ----- read-only accessors ----------------------------------------
    def get_bundle(self, config_id: str) -> ComponentBundle | None:
        return self._bundles.get(config_id)

    def all_bundles(self) -> list[ComponentBundle]:
        # Return in registry order
        out = []
        for cfg in self._registry.iter_configs():
            b = self._bundles.get(cfg.id)
            if b:
                out.append(b)
        return out

    def capacity_snapshot(self) -> CapacitySnapshot:
        return self._capacity.snapshot(len(self._bundles))

    def invalidate_globally_allowed_cache(self) -> None:
        """Force recomputation of the globally-allowed (symbol, exchange)
        map on the next sweep. Called by the dashboard server after
        settings save / auto-disable run / bundle add or remove."""
        self._globally_allowed = None
        self._globally_allowed_signature = None

    def _get_globally_allowed(
        self, bundles: list[ComponentBundle]
    ) -> dict[str, set[str]] | None:
        """Return the cached map of {symbol: set(exchange)} where AT LEAST
        ONE config can act as buyer or seller. Recomputed only when the
        signature (set of fee_manager identities + their version
        counters) changes.

        Returns None when no bundles exist (no filter — pre-startup).
        """
        if not bundles:
            return None
        # Build a cheap signature: each fee_manager exposes a `version`
        # counter (incremented on apply_auto_disable / save_fee_settings)
        # OR we fall back to id() which changes when a bundle rebuilds.
        sig_parts: list[tuple] = []
        for b in bundles:
            fm = getattr(b, "fee_manager", None)
            if fm is None:
                continue
            ver = getattr(fm, "_version", None)
            sig_parts.append((id(fm), ver))
        sig = tuple(sig_parts)
        if sig == self._globally_allowed_signature and self._globally_allowed is not None:
            return self._globally_allowed
        # Recompute.
        from config import SYMBOLS
        all_symbols = self._factory._all_symbols or list(SYMBOLS)
        all_exchanges = [f.exchange_name for f in self._factory._fetchers]
        allowed: dict[str, set[str]] = {sym: set() for sym in all_symbols}
        for sym in all_symbols:
            sym_set = allowed[sym]
            for ex in all_exchanges:
                # If any config can act as buyer or seller for (ex, sym),
                # keep it. We short-circuit on the first config that allows.
                for b in bundles:
                    fm = getattr(b, "fee_manager", None)
                    if fm is None:
                        continue
                    try:
                        if fm.can_buy(ex, sym) or fm.can_sell(ex, sym):
                            sym_set.add(ex)
                            break
                    except Exception:
                        # Conservative: include the exchange on error.
                        sym_set.add(ex)
                        break
        self._globally_allowed = allowed
        self._globally_allowed_signature = sig
        return allowed

    # ----- lifecycle --------------------------------------------------
    def stop(self) -> None:
        self._running = False

    async def reconcile_components(self) -> None:
        """Compare registry to live bundles; build new ones, tear down removed
        ones, rebuild any whose effective execution_mode has drifted (super-
        primary handoff or shared mode change)."""
        async with self._swap_lock:
            target_ids = {c.id for c in self._registry.iter_configs()}
            current_ids = set(self._bundles.keys())

            # Remove gone configs
            for cid in current_ids - target_ids:
                bundle = self._bundles.pop(cid)
                logger.info(
                    f"[Orchestrator] Tearing down config {cid[:8]}… ({bundle.config_name})"
                )
                await self._factory.teardown(bundle)

            # Add new configs. Wrap factory.build in try/except so a single
            # failed build doesn't roll back the WS handler — the operator
            # gets a clean error log instead of a silently-missing bundle.
            for cid in target_ids - current_ids:
                cfg = self._registry.find_config(cid)
                if cfg is None:
                    continue
                group = self._registry.find_group_for_config(cid)
                token = set_config_context(
                    cfg.group_id,
                    group.name if group else "?",
                    cfg.id,
                    cfg.name,
                )
                try:
                    logger.info(
                        f"[Orchestrator] Building config {cid[:8]}… ({cfg.name}) "
                        f"in group {group.name if group else '?'} "
                        f"capital=${group.initial_capital if group else 0:.2f}"
                    )
                    bundle = self._factory.build(cfg, self._registry)
                    self._bundles[cid] = bundle
                    logger.info(
                        f"[Orchestrator] Built {cid[:8]}…: "
                        f"exchanges={bundle.balance._exchanges} "
                        f"symbols={bundle.balance._symbols} "
                        f"_initial_investment=${bundle.balance._initial_investment:.2f}"
                    )
                    if self._post_build_hook is not None:
                        try:
                            self._post_build_hook(bundle, dict(cfg.settings))
                        except Exception as e:
                            import traceback
                            logger.error(
                                f"[Orchestrator] post_build_hook failed for "
                                f"{cid[:8]}…: {type(e).__name__}: {e}\n"
                                f"{traceback.format_exc()}"
                            )
                except Exception as e:
                    import traceback
                    logger.error(
                        f"[Orchestrator] BUILD_FAILED {cid[:8]}… ({cfg.name}): "
                        f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
                    )
                    # Don't store the bundle — operator can see this in the
                    # log + the config will be retried on next reconcile.
                finally:
                    reset_config_context(token)

            # Detect mode drift on existing bundles → rebuild affected
            for cid, bundle in list(self._bundles.items()):
                expected_exec = self._registry.effective_execution_mode(cid)
                expected_hedge = self._registry.effective_hedge_mode(cid)
                if (
                    bundle.execution_mode != expected_exec
                    or bundle.hedge_mode != expected_hedge
                ):
                    cfg = self._registry.find_config(cid)
                    logger.info(
                        f"[Orchestrator] Mode drift on {cid[:8]}… "
                        f"({bundle.execution_mode}→{expected_exec}, "
                        f"hedge {bundle.hedge_mode}→{expected_hedge}) — rebuilding"
                    )
                    await self._factory.teardown(bundle)
                    token = set_config_context(
                        cfg.group_id,
                        self._registry.find_group_for_config(cid).name,
                        cfg.id,
                        cfg.name,
                    )
                    try:
                        new_bundle = self._factory.build(cfg, self._registry)
                        self._bundles[cid] = new_bundle
                        if self._post_build_hook is not None:
                            try:
                                self._post_build_hook(new_bundle, dict(cfg.settings))
                            except Exception as e:
                                import traceback
                                logger.error(
                                    f"[Orchestrator] post_build_hook failed for "
                                    f"{cid[:8]}…: {type(e).__name__}: {e}\n"
                                    f"{traceback.format_exc()}"
                                )
                    finally:
                        reset_config_context(token)

    async def request_restart(self, config_id: str) -> bool:
        """Reset one config's state — wipe its bundle, rebuild fresh."""
        async with self._swap_lock:
            bundle = self._bundles.pop(config_id, None)
            if bundle is None:
                return False
            logger.info(
                f"[Orchestrator] Restarting config {config_id[:8]}… ({bundle.config_name})"
            )
            await self._factory.teardown(bundle)
            cfg = self._registry.find_config(config_id)
            if cfg is None:
                return False
            token = set_config_context(
                cfg.group_id,
                self._registry.find_group_for_config(config_id).name,
                cfg.id,
                cfg.name,
            )
            try:
                new_bundle = self._factory.build(
                    cfg, self._registry, fresh_state=True
                )
                self._bundles[config_id] = new_bundle
                if self._post_build_hook is not None:
                    try:
                        self._post_build_hook(new_bundle, dict(cfg.settings))
                    except Exception as e:
                        import traceback
                        logger.error(
                            f"[Orchestrator] post_build_hook failed for "
                            f"{config_id[:8]}…: {type(e).__name__}: {e}\n"
                            f"{traceback.format_exc()}"
                        )
            finally:
                reset_config_context(token)
            return True

    async def request_restart_all(self) -> int:
        """Reset all configs — preserves the registry, wipes all per-config state."""
        n = 0
        for cid in list(self._bundles.keys()):
            ok = await self.request_restart(cid)
            if ok:
                n += 1
        logger.info(f"[Orchestrator] Restarted {n} config(s)")
        return n

    # ----- main loop --------------------------------------------------
    async def run(self) -> None:
        """Single coroutine that round-robin-sweeps every config each tick."""
        await self.reconcile_components()
        logger.info(
            f"[Orchestrator] Sweep loop started: {len(self._bundles)} config(s), "
            f"interval={self._tick_interval:.1f}s, "
            f"budget={self._capacity._budget_ms:.0f}ms"
        )

        # Lazy-imports to avoid forcing the dep when orchestrator is used
        # outside the multi-config context (e.g. unit tests).
        from slippage import begin_sweep, end_sweep, cache_stats
        from tick_cache import (
            build_sweep_prices,
            set_sweep_prices,
            clear_sweep_prices,
        )
        from config import SYMBOLS

        # Pull symbols + fetchers from the factory (it's the canonical owner).
        sweep_symbols = self._factory._all_symbols or list(SYMBOLS)
        sweep_fetchers = self._factory._fetchers

        # Globally-allowed (symbol, exchange) cache. Recomputed lazily
        # when the bundle set or any fee_manager state changes — see
        # `_compute_globally_allowed`. Lets `build_sweep_prices` skip
        # entries no config can use, eliminating per-tick float/book
        # parsing work for ~10-15% of cells (auto-disabled low-volume
        # pairs across the whole registry).
        self._globally_allowed: dict[str, set[str]] | None = None
        self._globally_allowed_signature: tuple | None = None

        # Diagnostic state for the per-minute breakdown log
        last_diag_log_ts: float = 0.0
        diag_build_prices_ms: float = 0.0
        diag_per_config_ms: float = 0.0
        diag_yield_ms: float = 0.0
        diag_sweep_count: int = 0
        # Split per-config time by phase (optimizer vs monitor) — lets us
        # see whether per_cfg growth comes from scoring or trading logic
        diag_opt_ms: float = 0.0
        diag_mon_ms: float = 0.0
        # Per-config running totals for opt time. Keyed by config_id.
        # Logged in [SlowConfigs] every minute to identify outliers.
        diag_per_config_opt_ms: dict[str, float] = {}
        diag_per_config_opt_count: dict[str, int] = {}
        # GC pause timing — wrap the explicit gc.collect() calls if any,
        # but also infer gen2 pauses by measuring time delta around
        # large allocations. We sample gc.get_count() per sweep and log
        # detected gen2 firings (count drops to 0).
        diag_gen2_collections_seen: int = 0
        diag_gen2_collection_ms: float = 0.0
        prev_gen2_count: int = -1

        while self._running:
            t0 = time.monotonic()
            # Snapshot the bundle list (so concurrent reconciles don't break iteration)
            bundles = self.all_bundles()
            # v0.31.0-beta+: per-sweep optimizations stack here:
            #   1. Slippage memoization (slippage._SWEEP_CACHE) — repeated
            #      walks on the same book + size return cached results.
            #   2. Pre-built exchange_prices (tick_cache._SWEEP_PRICES) —
            #      every config reads the SAME snapshot of fetcher state
            #      instead of each config calling fetcher.get_state() N×.
            #   3. Pre-parsed order book floats — bids/asks pre-converted
            #      to list[tuple[float, float]] in build_sweep_prices, so
            #      slippage walkers skip per-call string→float parsing.
            #   4. Globally-allowed filter — drops (symbol, exchange) that
            #      no config can use. The cache invalidates only when
            #      fee_managers change (auto-disable run / manual save /
            #      bundle add or remove), so the per-tick cost is just
            #      one dict lookup per fetcher.
            begin_sweep()
            t_build_start = time.monotonic()
            globally_allowed = self._get_globally_allowed(bundles)
            sweep_prices = build_sweep_prices(
                sweep_fetchers, sweep_symbols,
                globally_allowed=globally_allowed,
            )
            set_sweep_prices(sweep_prices)
            diag_build_prices_ms += (time.monotonic() - t_build_start) * 1000.0
            t_per_config_start = time.monotonic()
            for bundle in bundles:
                # Skip torn-down bundles (race with restart)
                if bundle.config_id not in self._bundles:
                    continue
                cfg = self._registry.find_config(bundle.config_id)

                # Pre-tick markers for change detection (dirty-flag triggers
                # without touching component internals). `_trades` is a
                # bounded recent deque, so use the cumulative counter for
                # trade detection after the deque reaches maxlen.
                pre_trades = int(
                    getattr(bundle.monitor, "_cumulative_trade_count", len(bundle.monitor._trades))
                )
                pre_transfers = len(bundle.balance.transfers)
                pre_active = tuple(bundle.optimizer._active_symbols)

                token = set_config_context(
                    bundle.group_id,
                    bundle.group_name,
                    bundle.config_id,
                    bundle.config_name,
                )
                try:
                    t_opt = time.monotonic()
                    try:
                        bundle.optimizer.tick_once()
                    except Exception as e:
                        logger.exception(
                            f"[Orchestrator] optimizer.tick_once failed for "
                            f"{bundle.config_name}: {e}"
                        )
                    opt_elapsed = (time.monotonic() - t_opt) * 1000.0
                    diag_opt_ms += opt_elapsed
                    diag_per_config_opt_ms[bundle.config_id] = (
                        diag_per_config_opt_ms.get(bundle.config_id, 0.0) + opt_elapsed
                    )
                    diag_per_config_opt_count[bundle.config_id] = (
                        diag_per_config_opt_count.get(bundle.config_id, 0) + 1
                    )
                    t_mon = time.monotonic()
                    try:
                        bundle.monitor.tick_once()
                    except Exception as e:
                        logger.exception(
                            f"[Orchestrator] monitor.tick_once failed for "
                            f"{bundle.config_name}: {e}"
                        )
                    diag_mon_ms += (time.monotonic() - t_mon) * 1000.0
                finally:
                    reset_config_context(token)

                # Post-tick: mark hedge + state dirty if anything material
                # changed. The hedge wake-up is independent of the state dirty
                # flag because a config can already be dirty and still need an
                # immediate hedge resync after a later trade/transfer.
                changed_reasons: list[str] = []
                post_trades = int(
                    getattr(bundle.monitor, "_cumulative_trade_count", len(bundle.monitor._trades))
                )
                if post_trades != pre_trades:
                    changed_reasons.append("trade")
                if len(bundle.balance.transfers) != pre_transfers:
                    changed_reasons.append("transfer")
                if tuple(bundle.optimizer._active_symbols) != pre_active:
                    changed_reasons.append("active_symbols")
                if changed_reasons:
                    try:
                        if bundle.hedge_manager:
                            bundle.hedge_manager.mark_inventory_changed(
                                ",".join(changed_reasons)
                            )
                    except Exception:
                        pass
                    if cfg is not None and not cfg._dirty:
                        cfg.mark_dirty()

                # Yield between configs so a slow one doesn't starve
                # WebSocket / dashboard / state-save tasks. Time spent
                # in the yield = time taken by OTHER tasks (broadcast,
                # state save, fetcher message processing, CSV writes,
                # GC pauses) that ran during this yield. If sweep_ms
                # grows but per-config sweep time is constant, the
                # yield component is the culprit.
                t_yield_start = time.monotonic()
                await asyncio.sleep(0)
                diag_yield_ms += (time.monotonic() - t_yield_start) * 1000.0

            diag_per_config_ms += (time.monotonic() - t_per_config_start) * 1000.0
            diag_sweep_count += 1
            sweep_ms = (time.monotonic() - t0) * 1000.0
            # Detect gen2 collections: gen2 count resets to 0 right after
            # a collection. If the previous reading was non-zero and now
            # it's 0, gen2 just fired during this sweep.
            try:
                import gc as _gc
                cur_gen2_count = _gc.get_count()[2]
                if prev_gen2_count > 0 and cur_gen2_count < prev_gen2_count:
                    # gen2 collection happened — attribute the difference
                    # to "the collection just occurred". Pause time equals
                    # the portion of sweep_ms over the typical baseline,
                    # but we can't isolate it cheaply without explicit
                    # callbacks. Just count the events.
                    diag_gen2_collections_seen += 1
                prev_gen2_count = cur_gen2_count
            except Exception:
                pass
            cache_h, cache_m = cache_stats()
            end_sweep()
            clear_sweep_prices()
            self._capacity.record(sweep_ms, len(bundles))

            # Periodic cache-effectiveness log so it's visible whether the
            # cache is actually helping. Logs once per minute when running.
            if int(t0) % 60 == 0 and cache_m > 0:
                hit_pct = cache_h / (cache_h + cache_m) * 100
                logger.debug(
                    f"[Capacity] Slippage cache: {cache_h} hits, {cache_m} misses "
                    f"({hit_pct:.0f}% hit rate) over {len(bundles)} configs"
                )

            # Per-minute diagnostic breakdown — the only log designed to
            # reveal WHY sweep_ms grows over time. Compares averages
            # across the last minute's sweeps:
            #   - build_prices_avg = time building shared exchange_prices
            #   - per_config_avg   = time inside per-bundle tick_once (sum)
            #   - yield_avg        = time taken by OTHER tasks during
            #                        `await asyncio.sleep(0)` between configs
            #                        (broadcast, state save, GC, fetchers,
            #                        CSV writes — anything on the same loop)
            # Plus snapshot of long-lived collection sizes that could
            # indicate hidden growth:
            #   - heap_mb: process RSS memory
            #   - gc_counts: Python GC generation counters
            #   - n_log_entries / n_trades / n_transfers / n_dirty
            now_ts = time.monotonic()
            if now_ts - last_diag_log_ts >= 60.0 and diag_sweep_count > 0:
                last_diag_log_ts = now_ts
                build_avg = diag_build_prices_ms / diag_sweep_count
                per_cfg_avg = diag_per_config_ms / diag_sweep_count
                yield_avg = diag_yield_ms / diag_sweep_count
                opt_avg = diag_opt_ms / diag_sweep_count
                mon_avg = diag_mon_ms / diag_sweep_count
                # Reset accumulators for the next window
                diag_build_prices_ms = 0.0
                diag_per_config_ms = 0.0
                diag_yield_ms = 0.0
                diag_opt_ms = 0.0
                diag_mon_ms = 0.0
                diag_sweep_count = 0

                # Process memory + GC stats — read CURRENT RSS from
                # /proc/self/status (Linux). Not ru_maxrss because that
                # only ratchets up (peak), giving a misleading flat value
                # when memory is actually fluctuating.
                heap_mb = -1.0
                try:
                    with open("/proc/self/status") as fp:
                        for line in fp:
                            if line.startswith("VmRSS:"):
                                # Format: "VmRSS:    920372 kB"
                                heap_mb = float(line.split()[1]) / 1024.0
                                break
                except Exception:
                    pass
                try:
                    import gc
                    gc_counts = gc.get_count()
                    gc_thresh = gc.get_threshold()
                except Exception:
                    gc_counts = (-1, -1, -1)
                    gc_thresh = (-1, -1, -1)

                # Aggregate per-config totals. `_trades` is a bounded recent
                # deque, so true lifetime trade count must come from the
                # cumulative counter.
                n_trades_total = 0
                n_transfers_total = 0
                n_dirty = 0
                n_watchlist_total = 0
                n_rotations_total = 0
                n_ticks_total = 0  # SUM of optimizer._ticks deque sizes
                n_ticks_max = 0   # MAX deque size (any sym, any config)
                for b in bundles:
                    try:
                        n_trades_total += int(
                            getattr(b.monitor, "_cumulative_trade_count", len(b.monitor._trades))
                        )
                        n_transfers_total += len(b.balance.transfers)
                        n_watchlist_total += len(b.optimizer._watchlist)
                        n_rotations_total += len(b.optimizer._rotations)
                        for dq in b.optimizer._ticks.values():
                            n = len(dq)
                            n_ticks_total += n
                            if n > n_ticks_max:
                                n_ticks_max = n
                    except Exception:
                        pass
                for cfg in self._registry.iter_configs():
                    if cfg._dirty:
                        n_dirty += 1
                # Total Python objects tracked by GC — proves whether
                # heap growth is from "small leaky containers" (this
                # number climbs) or just bigger per-object payloads
                # (this stays ~flat).
                try:
                    import gc
                    n_gc_objects = len(gc.get_objects())
                except Exception:
                    n_gc_objects = -1

                cap = self._capacity.snapshot(len(bundles))
                logger.info(
                    f"[Capacity] sweep_avg={cap.avg_sweep_ms:.0f}ms "
                    f"last={cap.last_sweep_ms:.0f}ms p95={cap.p95_sweep_ms:.0f}ms "
                    f"| build_prices={build_avg:.1f}ms per_cfg={per_cfg_avg:.0f}ms "
                    f"(opt={opt_avg:.0f}ms mon={mon_avg:.0f}ms) "
                    f"yield={yield_avg:.0f}ms | configs={len(bundles)} dirty={n_dirty} "
                    f"trades={n_trades_total} transfers={n_transfers_total} "
                    f"watchlist={n_watchlist_total} rotations={n_rotations_total} "
                    f"ticks_total={n_ticks_total} ticks_max={n_ticks_max} "
                    f"gen2_collections={diag_gen2_collections_seen} "
                    f"| heap={heap_mb:.0f}MB gc_objects={n_gc_objects} "
                    f"gc={gc_counts} thresh={gc_thresh}"
                )

                # ── [SlowConfigs] Top 5 slowest configs by avg opt time
                # Identifies whether the slowdown is uniform across configs
                # or driven by a few outliers (e.g., a config with many
                # active symbols vs a barely-trading one).
                config_avgs: list[tuple[str, float, int]] = []
                for cid, total_ms in diag_per_config_opt_ms.items():
                    cnt = diag_per_config_opt_count.get(cid, 1)
                    cfg = self._registry.find_config(cid)
                    name = cfg.name if cfg else cid[:8]
                    config_avgs.append((name, total_ms / max(1, cnt), cnt))
                config_avgs.sort(key=lambda x: x[1], reverse=True)
                if config_avgs:
                    top5 = config_avgs[:5]
                    bot5 = config_avgs[-3:]
                    logger.info(
                        "[SlowConfigs] top5_opt: " +
                        ", ".join(f"{n[:24]}={ms:.1f}ms" for n, ms, _ in top5) +
                        " | bot3: " +
                        ", ".join(f"{n[:24]}={ms:.1f}ms" for n, ms, _ in bot5)
                    )
                diag_per_config_opt_ms.clear()
                diag_per_config_opt_count.clear()
                diag_gen2_collections_seen = 0

                # ── [Heap] Top 10 Python object types by count
                # Reveals what's accumulating. If SymbolTick dominates AND
                # grows over time → deque saturation. If `dict` or `list`
                # grows unbounded → hidden container leak. If a type we
                # don't expect grows → unexpected accumulation.
                try:
                    import gc
                    from collections import Counter as _Counter
                    type_counts: _Counter = _Counter()
                    for o in gc.get_objects():
                        type_counts[type(o).__name__] += 1
                    top10 = type_counts.most_common(10)
                    # Also probe for our specific dataclasses
                    sym_tick = type_counts.get("SymbolTick", 0)
                    sym_score = type_counts.get("SymbolScore", 0)
                    slip_res = type_counts.get("SlippageResult", 0)
                    sim_trade = type_counts.get("SimulatedTrade", 0)
                    transfer = type_counts.get("Transfer", 0)
                    logger.info(
                        f"[Heap] objects: total={n_gc_objects} | "
                        f"SymbolTick={sym_tick} SymbolScore={sym_score} "
                        f"SlippageResult={slip_res} SimulatedTrade={sim_trade} "
                        f"Transfer={transfer} | top10: " +
                        ", ".join(f"{t}={c}" for t, c in top10)
                    )
                except Exception as e:
                    logger.debug(f"[Heap] failed to enumerate: {e}")

                # ── [Tasks] asyncio task count + WS clients
                # If pending task count grows monotonically → task leak.
                # If WS clients climb → operator opening more dashboard
                # tabs without closing them.
                try:
                    n_tasks = len(asyncio.all_tasks())
                except Exception:
                    n_tasks = -1
                logger.info(f"[Tasks] asyncio_tasks={n_tasks}")

                # ── [Fetcher] Per-fetcher health: WS connected, state size,
                # latency samples, last-data age. If any fetcher's
                # `_latency_samples` grows unbounded → leak there.
                # If `last_data_received` lags far behind now → silent stall.
                try:
                    f_lines = []
                    now_t = time.time()
                    for f in self._factory._fetchers:
                        try:
                            ws = "✓" if f._ws_connected else "✗"
                            n_state = len(f._state) if hasattr(f, "_state") else 0
                            n_lat = (
                                len(f._latency_samples)
                                if hasattr(f, "_latency_samples") else 0
                            )
                            last_age = (
                                (now_t - f._last_data_received)
                                if getattr(f, "_last_data_received", 0) > 0
                                else -1
                            )
                            f_lines.append(
                                f"{f.exchange_name}({ws} state={n_state} "
                                f"lat_n={n_lat} age={last_age:.0f}s)"
                            )
                        except Exception:
                            pass
                    if f_lines:
                        logger.info(f"[Fetcher] " + " ".join(f_lines))
                except Exception as e:
                    logger.debug(f"[Fetcher] failed: {e}")

            # Adaptive sleep: if the sweep took a full second, just yield;
            # otherwise sleep the remainder so each config still ticks at ~1Hz.
            remaining = self._tick_interval - (sweep_ms / 1000.0)
            await asyncio.sleep(max(0.0, remaining))

        logger.info("[Orchestrator] Sweep loop stopped")

    # ----- per-config state persistence -------------------------------
    def _build_state_payload(self, bundle: ComponentBundle) -> dict:
        """Snapshot of one bundle's serializable state (mirrors the legacy
        v0.30 session.json shape but scoped to one config)."""
        return {
            "schema_version": 2,
            "saved_at": time.time(),
            "balance": bundle.balance.to_state_dict(),
            "monitor": bundle.monitor.to_state_dict(),
            "optimizer": bundle.optimizer.to_state_dict(),
            "fee_manager": bundle.fee_manager.to_state_dict()
            if bundle.fee_manager else None,
            "hedge_manager": bundle.hedge_manager.to_state_dict()
            if bundle.hedge_manager else None,
        }

    def save_dirty(self, state_mgr) -> int:
        """Save every dirty config to its own session file. Returns count saved."""
        n = 0
        for cfg in self._registry.iter_configs():
            if not cfg._dirty:
                continue
            bundle = self._bundles.get(cfg.id)
            if bundle is None:
                continue
            payload = self._build_state_payload(bundle)
            if state_mgr.save_config(cfg.id, payload):
                cfg._dirty = False
                n += 1
        return n

    def save_all(self, state_mgr) -> int:
        """Force-save every config (ignore dirty flags). Used by shutdown."""
        n = 0
        for bundle in self.all_bundles():
            payload = self._build_state_payload(bundle)
            if state_mgr.save_config(bundle.config_id, payload):
                n += 1
        return n

    async def periodic_save_loop(
        self, state_mgr, save_interval: float = 60.0
    ) -> None:
        """Background task: every `save_interval` seconds, write any dirty
        configs to disk. Spaces fsyncs across the loop with `asyncio.sleep(0)`
        so a 60-config save doesn't starve the event loop."""
        logger.info(
            f"[State] Per-config periodic save started (every {save_interval:.0f}s)"
        )
        while self._running:
            await asyncio.sleep(save_interval)
            if not self._running:
                break
            try:
                n = 0
                t_start = time.monotonic()
                build_total_ms = 0.0
                save_total_ms = 0.0
                payload_total_bytes = 0
                for cfg in self._registry.iter_configs():
                    if not cfg._dirty:
                        continue
                    bundle = self._bundles.get(cfg.id)
                    if bundle is None:
                        continue
                    t_b = time.monotonic()
                    payload = self._build_state_payload(bundle)
                    build_total_ms += (time.monotonic() - t_b) * 1000.0
                    # Estimate payload size (cheap on a small dict)
                    try:
                        import json as _json
                        payload_total_bytes += len(_json.dumps(payload, default=str))
                    except Exception:
                        pass
                    t_s = time.monotonic()
                    if state_mgr.save_config(cfg.id, payload):
                        cfg._dirty = False
                        n += 1
                    save_total_ms += (time.monotonic() - t_s) * 1000.0
                    # Yield between fsyncs
                    await asyncio.sleep(0)
                if n > 0:
                    total_ms = (time.monotonic() - t_start) * 1000.0
                    avg_kb = (payload_total_bytes / max(1, n)) / 1024.0
                    logger.info(
                        f"[State] Saved {n} dirty config(s): "
                        f"build={build_total_ms:.0f}ms save={save_total_ms:.0f}ms "
                        f"total={total_ms:.0f}ms avg_payload={avg_kb:.0f}KB"
                    )
            except Exception as e:
                logger.exception(f"[State] periodic_save_loop error: {e}")


# ── Factory ────────────────────────────────────────────────────────────


class ConfigFactory:
    """Builds a `ComponentBundle` for a single `Config`.

    The factory holds references to all SHARED resources and a callback
    used to apply per-config force-locks (super-primary execution mode,
    hedge mode). Per-config state files are loaded on `build()` if present
    and `fresh_state=False` (the default).
    """

    def __init__(
        self,
        fetchers: list,
        exchange_info,
        transfer_fee_manager,
        funding_monitor,
        futures_executor_builder: Callable[[str], Any] | None = None,
        demo_executor_builder: Callable[[str], Any] | None = None,
        active_symbols_default: list[str] | None = None,
        all_symbols: list[str] | None = None,
        log_file=None,
        state_loader: Callable[[str], dict | None] | None = None,
    ):
        self._fetchers = fetchers
        self._exchange_info = exchange_info
        self._transfer_fee_manager = transfer_fee_manager
        self._funding_monitor = funding_monitor
        self._futures_executor_builder = futures_executor_builder
        self._demo_executor_builder = demo_executor_builder
        self._active_symbols_default = list(active_symbols_default or [])
        self._all_symbols = list(all_symbols or [])
        self._log_file = log_file
        self._state_loader = state_loader
        # Cache the current super-primary's futures executor so we can
        # close + rebuild on handoff
        self._futures_executor: Any | None = None
        # Cache the current super-primary's demo executor
        self._demo_executor: Any | None = None

    def build(
        self,
        config: Config,
        registry: ConfigRegistry,
        fresh_state: bool = False,
    ) -> ComponentBundle:
        """Construct a full component bundle for this config."""
        # Lazy imports avoid circular dependencies at module load time
        from balance import BalanceTracker
        from monitor import ArbitrageMonitor
        from optimizer import SymbolOptimizer
        from fee_manager import FeeManager
        from hedge_manager import HedgeManager
        from config import MIN_WARMUP_TICKS, SYMBOLS

        s = config.settings
        group = registry.find_group_for_config(config.id)
        if group is None:
            raise RuntimeError(f"Config {config.id} has no group")

        # ── Capital from group ─────────────────────────────────────────
        total_capital = float(group.initial_capital)
        hedging_enabled = bool(s.get("hedging_enabled", True))
        futures_reserve_pct = (
            max(0.0, min(0.90, float(s.get("futures_capital_target_pct", 0.40))))
            if hedging_enabled
            else 0.0
        )
        futures_reserve_usdt = round(total_capital * futures_reserve_pct, 2)
        spot_capital = max(0.0, total_capital - futures_reserve_usdt)
        trade_amount_pct = float(s.get("trade_amount_pct", 0.0))
        if trade_amount_pct > 0:
            trade_amount = round(spot_capital * trade_amount_pct, 2)
        else:
            trade_amount = float(s.get("trade_amount_usd", 25.0))

        # ── Per-config FeeManager from this config's fee_configs ──────
        fee_manager = FeeManager.from_settings_dict(
            s.get("fee_configs", {}),
            real_mode=False,  # multi-config is simulation-only
        )

        # ── Effective execution + hedge mode (super-primary force-lock) ─
        effective_exec = registry.effective_execution_mode(config.id)
        effective_hedge = registry.effective_hedge_mode(config.id)

        # ── Active exchanges derived from this config's enabled set ────
        enabled_set = set(fee_manager.get_enabled_exchanges())
        active_exchanges = [
            f.exchange_name for f in self._fetchers
            if f.exchange_name in enabled_set
        ]
        if not active_exchanges:
            active_exchanges = [f.exchange_name for f in self._fetchers]

        # demo_only restricts active exchanges (super-primary only)
        if effective_exec == "demo_only":
            demo_exchanges = {"Binance", "OKX", "Bybit"}
            active_exchanges = [ex for ex in active_exchanges if ex in demo_exchanges]
            if not active_exchanges:
                active_exchanges = [f.exchange_name for f in self._fetchers]

        active_symbols = list(self._active_symbols_default)

        # ── Initial allocations ────────────────────────────────────────
        per_exchange = spot_capital / max(1, len(active_exchanges))
        num_positions = 1 + len(active_symbols)
        per_position = per_exchange / max(1, num_positions)
        allocations = {
            ex: {
                "usdt": per_position,
                "crypto": {sym: per_position for sym in active_symbols},
            }
            for ex in active_exchanges
        }

        # ── BalanceTracker ─────────────────────────────────────────────
        balance = BalanceTracker(
            exchanges=active_exchanges,
            symbols=active_symbols,
            allocations=allocations,
            rebalance_cooldown=float(s.get("rebalance_cooldown", 30.0)),
            trade_amount=trade_amount,
            adaptive_mode=bool(s.get("adaptive_mode", True)),
            exchange_info=self._exchange_info,
            fee_manager=fee_manager,
            transfer_fee_manager=self._transfer_fee_manager,
            hourly_external_transfer_cap=float(s.get("hourly_external_transfer_cap", 2.0)),
            bitfinex_reserve_pct=float(s.get("bitfinex_reserve_pct", 0.15)),
            bitfinex_reserve_hard_floor=float(s.get("bitfinex_reserve_hard_floor", 0.05)),
            futures_reserve_usdt=futures_reserve_usdt,
            binance_spot_bnb_reserved_usd=float(s.get("binance_spot_bnb_min_usd", 5.0)),
        )

        # ── ArbitrageMonitor ───────────────────────────────────────────
        monitor = ArbitrageMonitor(
            self._fetchers,
            balance=balance,
            symbols=active_symbols,
            exchanges=active_exchanges,
            trade_amount=trade_amount,
            min_net_profit_pct=float(s.get("min_net_profit_pct", 0.02)),
            min_misses_before_rebalance=int(s.get("min_misses_before_rebalance", 15)),
            rebalance_roi_horizon=float(s.get("rebalance_roi_horizon", 1800)),
            total_capital=total_capital,
            adaptive_mode=bool(s.get("adaptive_mode", True)),
            log_file=self._log_file,
            exchange_info=self._exchange_info,
            fee_manager=fee_manager,
            net_pct_sizing_enabled=bool(s.get("net_pct_sizing_enabled", True)),
            net_pct_multiplier_cap=float(s.get("net_pct_multiplier_cap", 2.5)),
            strict_slippage_guards_enabled=bool(s.get("strict_slippage_guards_enabled", True)),
            require_order_book_depth=bool(s.get("require_order_book_depth", True)),
            order_book_depth_buffer_multiplier=float(
                s.get("order_book_depth_buffer_multiplier", 1.25)
            ),
            missing_order_book_penalty_pct=float(
                s.get("missing_order_book_penalty_pct", 0.25)
            ),
            max_leg_slippage_pct=float(s.get("max_leg_slippage_pct", 0.05)),
            max_total_slippage_pct=float(s.get("max_total_slippage_pct", 0.08)),
            slippage_safety_multiplier=float(s.get("slippage_safety_multiplier", 1.5)),
            slippage_latency_buffer_pct=float(s.get("slippage_latency_buffer_pct", 0.01)),
            book_age_guard_enabled=bool(s.get("book_age_guard_enabled", True)),
            max_book_age_seconds=float(s.get("max_book_age_seconds", 2.0)),
            event_driven_max_book_age_seconds=float(
                s.get("event_driven_max_book_age_seconds", 15.0)
            ),
            depth_aware_trade_size_shrink_enabled=bool(
                s.get("depth_aware_trade_size_shrink_enabled", True)
            ),
            min_depth_shrink_ratio=float(s.get("min_depth_shrink_ratio", 0.5)),
        )

        # ── SymbolOptimizer ────────────────────────────────────────────
        optimizer = SymbolOptimizer(
            fetchers=self._fetchers,
            monitor=monitor,
            balance=balance,
            active_exchanges=active_exchanges,
            active_symbols=active_symbols,
            all_symbols=self._all_symbols or list(SYMBOLS),
            trade_amount=trade_amount,
            total_capital=total_capital,
            fee_manager=fee_manager,
            num_active_symbols=int(s.get("num_active_symbols", 3)),
            scoring_window=int(s.get("scoring_window", 1800)),
            evaluation_interval=int(s.get("evaluation_interval", 300)),
            safety_multiplier=float(s.get("safety_multiplier", 2.0)),
            auto_rotate=bool(s.get("auto_rotate", True)),
            discovery_duration=int(s.get("discovery_duration", 300)),
            max_active_symbols=int(s.get("max_active_symbols", 8)),
            min_rebalance_score=float(s.get("min_rebalance_score", 0.0001)),
            confirmation_period=int(s.get("confirmation_period", 300)),
            score_stability_seconds=int(s.get("score_stability_seconds", 120)),
            score_stability_factor=float(s.get("score_stability_factor", 0.5)),
            promotion_threshold=float(s.get("promotion_threshold", 0.0001)),
            demotion_threshold=float(s.get("demotion_threshold", 0.0)),
            demotion_period=int(s.get("demotion_period", 600)),
            demotion_cooldown_multiplier=float(s.get("demotion_cooldown_multiplier", 5.0)),
            reallocation_cost_horizon=float(s.get("reallocation_cost_horizon", 2.0)),
            min_warmup_ticks=MIN_WARMUP_TICKS,
            strict_slippage_guards_enabled=bool(s.get("strict_slippage_guards_enabled", True)),
            require_order_book_depth=bool(s.get("require_order_book_depth", True)),
            order_book_depth_buffer_multiplier=float(
                s.get("order_book_depth_buffer_multiplier", 1.25)
            ),
            missing_order_book_penalty_pct=float(
                s.get("missing_order_book_penalty_pct", 0.25)
            ),
            max_leg_slippage_pct=float(s.get("max_leg_slippage_pct", 0.05)),
            max_total_slippage_pct=float(s.get("max_total_slippage_pct", 0.08)),
            slippage_safety_multiplier=float(s.get("slippage_safety_multiplier", 1.5)),
            slippage_latency_buffer_pct=float(s.get("slippage_latency_buffer_pct", 0.01)),
            book_age_guard_enabled=bool(s.get("book_age_guard_enabled", True)),
            max_book_age_seconds=float(s.get("max_book_age_seconds", 2.0)),
            event_driven_max_book_age_seconds=float(
                s.get("event_driven_max_book_age_seconds", 15.0)
            ),
        )
        if "trading_score_threshold" in s:
            optimizer._trading_threshold = float(s["trading_score_threshold"])
        if "strong_score_threshold" in s:
            optimizer._strong_threshold = float(s["strong_score_threshold"])
        if "very_strong_score_threshold" in s:
            optimizer._very_strong_threshold = float(s["very_strong_score_threshold"])
        if "net_pnl_gate_warmup_trades" in s:
            monitor._net_pnl_gate_warmup_trades = int(s["net_pnl_gate_warmup_trades"])
        if "net_pnl_gate_grace_seconds" in s:
            monitor._net_pnl_gate_grace_seconds = int(s["net_pnl_gate_grace_seconds"])
        if "rebalance_roi_divisor" in s:
            monitor._rebalance_roi_divisor = int(s["rebalance_roi_divisor"])

        monitor.set_optimizer(optimizer)
        optimizer.set_funding_monitor(self._funding_monitor)

        # ── Hedge: super-primary may have a real executor; others always shadow
        futures_executor = None
        if effective_hedge in ("testnet", "live") and self._futures_executor_builder:
            try:
                futures_executor = self._futures_executor_builder(effective_hedge)
            except Exception as e:
                logger.warning(
                    f"[Orchestrator] Failed to build futures executor "
                    f"({effective_hedge}) — falling back to simulation: {e}"
                )
                effective_hedge = "simulation"
                futures_executor = None
        hedge_manager = HedgeManager(
            balance=balance,
            funding_monitor=self._funding_monitor,
            optimizer=optimizer,
            executor=futures_executor,
            enabled=bool(s.get("hedging_enabled", True)),
            execution_mode=effective_hedge,
            dust_threshold_usd=float(s.get("hedge_dust_threshold_usd", 20.0)),
            evaluation_interval_seconds=float(s.get("hedge_evaluation_interval_seconds", 60.0)),
            margin_buffer_pct=float(s.get("hedge_margin_buffer_pct", 0.20)),
            adjust_threshold_pct=float(s.get("hedge_adjust_threshold_pct", 0.01)),
            leverage=int(s.get("hedge_leverage", 2)),
            futures_taker_fee_rate=float(s.get("binance_futures_taker_fee_rate", 0.0005)),
            futures_bnb_discount_enabled=bool(s.get("binance_futures_bnb_discount_enabled", True)),
            futures_bnb_discount_pct=float(s.get("binance_futures_bnb_discount_pct", 0.10)),
            futures_referral_cashback_enabled=bool(
                s.get("binance_futures_referral_cashback_enabled", False)
            ),
            futures_referral_cashback_pct=float(
                s.get("binance_futures_referral_cashback_pct", 0.10)
            ),
            futures_bnb_auto_topup_enabled=bool(
                s.get("binance_futures_bnb_auto_topup_enabled", True)
            ),
            futures_bnb_min_usd=float(s.get("binance_futures_bnb_min_usd", 5.0)),
            futures_bnb_target_pct=float(s.get("binance_futures_bnb_target_pct", 0.05)),
            futures_bnb_transfer_min_usd=float(
                s.get("binance_futures_bnb_transfer_min_usd", 5.0)
            ),
            spot_bnb_min_usd=float(s.get("binance_spot_bnb_min_usd", 5.0)),
            spot_bnb_auto_buy_enabled=bool(
                s.get("binance_spot_bnb_auto_buy_enabled", True)
            ),
            spot_bnb_target_pct=float(s.get("binance_spot_bnb_target_pct", 0.01)),
            spot_bnb_buy_min_usd=float(s.get("binance_spot_bnb_buy_min_usd", 10.0)),
            total_capital=total_capital,
            futures_capital_target_pct=float(s.get("futures_capital_target_pct", 0.40)),
            futures_capital_topup_pct=float(s.get("futures_capital_topup_pct", 0.35)),
            futures_capital_emergency_pct=float(s.get("futures_capital_emergency_pct", 0.30)),
            futures_capital_overflow_pct=float(s.get("futures_capital_overflow_pct", 0.45)),
            futures_capital_transfer_min_usd=float(s.get("futures_capital_transfer_min_usd", 10.0)),
        )
        monitor.set_hedge_manager(hedge_manager)

        # ── Demo executor: super-primary only ──────────────────────────
        demo_executor = None
        if effective_exec in ("demo", "demo_only") and self._demo_executor_builder:
            try:
                demo_executor = self._demo_executor_builder(effective_exec)
                if demo_executor:
                    monitor.set_executor(
                        demo_executor, None, None, execution_mode=effective_exec,
                    )
                    balance._execution_mode = effective_exec
            except Exception as e:
                logger.warning(f"[Orchestrator] Demo executor build failed: {e}")

        # ── Restore per-config state if present ────────────────────────
        if not fresh_state and self._state_loader is not None:
            saved = self._state_loader(config.id)
            if saved:
                try:
                    if "balance" in saved:
                        balance.from_state_dict(saved["balance"])
                    # Capital sanity check: if the restored balance's
                    # initial investment doesn't match the configured group
                    # capital (e.g., user changed group capital between
                    # sessions, or this is a v0.30 → v0.31 migration with
                    # a different default), reset to fresh allocations so
                    # the per-config view matches the user's expectation.
                    saved_initial = float(getattr(balance, "_initial_investment", 0.0) or 0.0)
                    saved_balance_state = saved.get("balance", {}) if isinstance(saved, dict) else {}
                    needs_futures_reserve_migration = (
                        futures_reserve_usdt > 0.5
                        and isinstance(saved_balance_state, dict)
                        and "binance_futures_usdt" not in saved_balance_state
                    )
                    if abs(saved_initial - total_capital) > 0.5 or needs_futures_reserve_migration:
                        reset_reason = (
                            "futures reserve allocation missing"
                            if needs_futures_reserve_migration
                            else "capital mismatch"
                        )
                        logger.warning(
                            f"[State] Balance reset on config {config.id[:8]}…: "
                            f"saved=${saved_initial:.2f} group=${total_capital:.2f} — "
                            f"resetting balance to group capital ({reset_reason})"
                        )
                        balance = BalanceTracker(
                            exchanges=active_exchanges,
                            symbols=active_symbols,
                            allocations=allocations,
                            rebalance_cooldown=float(s.get("rebalance_cooldown", 30.0)),
                            trade_amount=trade_amount,
                            adaptive_mode=bool(s.get("adaptive_mode", True)),
                            exchange_info=self._exchange_info,
                            fee_manager=fee_manager,
                            transfer_fee_manager=self._transfer_fee_manager,
                            hourly_external_transfer_cap=float(
                                s.get("hourly_external_transfer_cap", 2.0)
                            ),
                            bitfinex_reserve_pct=float(s.get("bitfinex_reserve_pct", 0.15)),
                            bitfinex_reserve_hard_floor=float(
                                s.get("bitfinex_reserve_hard_floor", 0.05)
                            ),
                            futures_reserve_usdt=futures_reserve_usdt,
                            binance_spot_bnb_reserved_usd=float(
                                s.get("binance_spot_bnb_min_usd", 5.0)
                            ),
                        )
                        # Re-wire monitor/optimizer to the fresh balance
                        monitor._balance = balance
                        optimizer._balance = balance
                        hedge_manager._balance = balance
                        # Skip restoring monitor/optimizer state since the
                        # capital basis has changed
                        if "fee_manager" in saved:
                            fee_manager.from_state_dict(saved["fee_manager"])
                    else:
                        if "monitor" in saved:
                            monitor.from_state_dict(saved["monitor"])
                        if "optimizer" in saved:
                            optimizer.from_state_dict(saved["optimizer"])
                        if "fee_manager" in saved:
                            fee_manager.from_state_dict(saved["fee_manager"])
                        if "hedge_manager" in saved:
                            hedge_manager.from_state_dict(saved["hedge_manager"])
                        if optimizer._active_symbols:
                            monitor.update_symbols(optimizer._active_symbols)
                            balance.update_symbols(optimizer._active_symbols)
                        logger.info(
                            f"[State] Restored config {config.id[:8]}…: "
                            f"{getattr(monitor, '_cumulative_trade_count', len(monitor._trades))} trades, "
                            f"{len(balance.transfers)} transfers, "
                            f"{len(optimizer._active_symbols)} active symbols"
                        )
                except Exception as e:
                    logger.exception(
                        f"[State] Failed to restore config {config.id[:8]}…: {e}"
                    )

        return ComponentBundle(
            config_id=config.id,
            group_id=config.group_id,
            config_name=config.name,
            group_name=group.name,
            balance=balance,
            monitor=monitor,
            optimizer=optimizer,
            fee_manager=fee_manager,
            hedge_manager=hedge_manager,
            demo_executor=demo_executor,
            execution_mode=effective_exec,
            hedge_mode=effective_hedge,
        )

    async def teardown(self, bundle: ComponentBundle) -> None:
        """Clean up a bundle. Closes real Binance Futures positions if the
        bundle held any (super-primary downgrade safety)."""
        try:
            bundle.monitor.stop()
        except Exception:
            pass
        try:
            bundle.optimizer.stop()
        except Exception:
            pass
        # Close real hedge positions before tearing down the executor
        if bundle.hedge_mode in ("testnet", "live") and bundle.hedge_manager:
            try:
                await bundle.hedge_manager.close_all_real_positions(
                    reason="orchestrator_teardown"
                )
            except Exception as e:
                logger.warning(
                    f"[Orchestrator] hedge close-all on teardown failed: {e}"
                )
        if bundle.demo_executor is not None:
            try:
                await bundle.demo_executor.close()
            except Exception:
                pass
