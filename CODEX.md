# Codex Instructions

Don't commit anything without my confirmation.

When I say to commit, before committing, update necessary docs, bump version to appropriate version following semver rules, perform separate commits by scope with appropriate messages, create new tag with detailed changelog. Let me push.

When config changes are needed, update `arbitragebot-configs.json` accordingly and remind me to import the new configs to the VPS.

Do not add current-version or release-history notes to `CLAUDE.md`. Keep runtime version in the root `__version__` file and keep release history in this file.

## Version History

### v0.33.1-beta — Reserve-Aware Portfolio Accounting

- Fixed post-discovery optimizer allocation so Binance Futures reserve is not double-counted as spot capital.
- Percentage trade sizing now uses spot-usable capital after subtracting the futures reserve.
- Dashboard portfolio accounting clamps stale over-inflated initial balance state created by the v0.33.0 reserve migration.
- Settings and trade-size logs now report spot capital, futures reserve, and total capital explicitly.

### v0.33.0-beta — Hedge Capital Allocation & Weak-Regime Refills

- Added Binance USD-M Futures capital allocation with 2x isolated leverage, 40% futures reserve target, 35% top-up threshold, 30% emergency threshold, and 45% overflow threshold.
- Spot allocations now reserve futures collateral first, so hedged simulations no longer double-count capital across spot wallets and futures margin.
- Added live Binance Spot ↔ USD-M Futures universal-transfer support for futures reserve top-ups and overflow sweeps.
- Hedge margin checks now use leveraged initial margin plus buffer, and new spot exposure is blocked when futures reserve health is unsafe.
- Dashboard and config editing now expose futures reserve status, reserve policy, leverage, and transfer settings.
- Added weak-regime rebalance policy modes: `strict`, `refill_only`, and `off`; default `refill_only` allows internal/cheap inventory refills while keeping expensive weak-hour rebalances blocked.
- Updated `settings.json` and `arbitragebot-configs.json` with the v0.33.0-beta reserve and weak-regime refill settings for all 46 configs.

### v0.32.3-beta — Hedge Inventory Coverage

- Hedge targets now include active symbols plus any positive held spot inventory, including residual inventory from demoted symbols.
- Hedges stay open for demoted symbols until the spot inventory is actually gone.
- Hedge evaluation wakes immediately after trades, transfers, or active-symbol changes instead of waiting for the periodic interval.
- Default hedge reconciliation tightened to 60 seconds and 1% quantity drift.
- Dashboard hedge diagnostics now show target notional, hedge gap, and unhedged inventory warnings.
- `arbitragebot-configs.json` was regenerated from the VPS export with the updated hedge settings for all 46 configs.

### v0.32.2-beta — Deficit Recovery Expansion

- Net-negative configs still block normal rotations and unrestricted expansion.
- Under-filled configs can perform one bounded, low-cost recovery expansion toward `num_active_symbols`.
- Recovery expansion uses the normal activation, stability, setup-profit, and pair-fee viability gates.
- Recovery setup fees are capped by deficit-recovery cost limits.

### v0.32.1-beta — Dashboard Config Import Reliability

- Raised dashboard WebSocket import capacity through `DASHBOARD_WS_MAX_SIZE_MB`.
- Config import accepts raw registry JSON and wrapped export payloads.
- Import flow now waits for backend success/failure instead of only showing an optimistic toast.

### v0.32.0-beta — VPS Storage Hardening

- Added runtime controls for CSV snapshot generation, snapshot cadence, CSV file size, and bot log retention.
- Added `scripts/cleanup_storage.sh` for dry-run-first VPS disk cleanup.

### v0.31.0-beta — Multi-Config Architecture

- Introduced the schema v2 config registry with groups, per-config settings, and one super-primary config.
- Added the orchestrator sweep model where each config owns its BalanceTracker, ArbitrageMonitor, SymbolOptimizer, FeeManager, HedgeManager, and anomaly state.
- Added per-config dashboard summaries, state persistence, logging context, capacity diagnostics, and multi-config bug fixes.
