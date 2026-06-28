# Codex Instructions

Don't commit anything without my confirmation.

When I say to commit, before committing, update necessary docs, bump version to appropriate version following semver rules, perform separate commits by scope with appropriate messages, create new tag with detailed changelog. Let me push.

When config changes are needed, update `arbitragebot-configs.json` accordingly and remind me to import the new configs to the VPS.

Do not add current-version or release-history notes to `CLAUDE.md`. Keep runtime version in the root `__version__` file and keep release history in this file.

## Version History

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
