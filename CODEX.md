# Codex Instructions

Don't commit anything without my confirmation.

When I say to commit, before committing, update necessary docs, bump version to appropriate version following semver rules, perform separate commits by scope with appropriate messages, create new tag with detailed changelog. Let me push.

When config changes are needed, update `arbitragebot-configs.json` accordingly and remind me to import the new configs to the VPS.

Do not add current-version or release-history notes to `CLAUDE.md`. Keep runtime version in the root `__version__` file and keep release history in this file.

## Version History

### v0.35.3-beta — Demo Mode, Session Docs & Session 35 Noise Fixes

- Fixed the multi-config dashboard/runtime path that prevented the super-primary spot execution mode from switching to demo/demo-only execution.
- Rebound demo comparison state to the current super-primary bundle so dashboard controls, demo fetcher wiring, restored balance state, and config acknowledgements stay synchronized.
- Updated dashboard/header/wallet portfolio fields to use consistent backend payload data for multi-config portfolio display.
- Preserved one super-primary execution target while allowing non-primary configs to remain safely simulated.
- Added config-registry and dashboard demo-state regression tests for the super-primary execution-mode flow.
- Bounded optimizer score retention and sampling behavior to reduce long-run memory/sweep pressure on the 30-config batch.
- Throttled repeated Binance futures BNB top-up and fee-discount skip diagnostics while keeping reserve-health status logs visible.
- Reduced the default/configured Binance futures BNB fee-reserve target from `5%` to `1%` to avoid unnecessary reserve churn.
- Slowed and throttled MEXC no-initial-depth reconnect diagnostics so unstable depth streams do not flood bot logs.
- Tuned all 30 local configs with higher hedge dust floors, `5%` hedge-adjust drift, and `180s` periodic hedge checks to reduce futures-fee churn.
- Moved session documentation into `documentations/sessions/` and added the detailed Session #35 continuation report.

### v0.35.2-beta — Low-Edge Rebalance, Hedge Churn & MEXC Depth Fixes

- Fixed MEXC spot depth subscriptions to use the official partial-depth protobuf channel format: `spot@public.limit.depth.v3.api.pb@{symbol}@20`.
- Bounded optimizer score sample retention to reduce long-run heap growth and sweep latency while preserving the scoring time horizon.
- Made optimizer discovery, expansion, recent-frequency checks, and estimated hourly profit sample-cadence aware.
- Fixed rolling aggregate eviction so zero-size score samples no longer subtract the default trade amount from expected profit.
- Stopped positive-but-below-threshold routes and realized-net skips from building stale rebalance pressure.
- Prevented position-cap and depth-size-zero skips from triggering inventory rebalances.
- Fixed balance snapshot totals to include Binance Futures reserve, Binance spot/futures BNB reserves, in-transit funds, and hedge P&L through `BalanceTracker.get_portfolio_value()`.
- Added a hedge adjustment notional floor so tiny hedge drift does not repeatedly pay simulated or live futures taker fees.
- Documented Session #34 with the July 3 poor-performance audit, root causes, implemented fixes, and verification results.
- Added regression tests for optimizer sampling, rebalance-streak cleanup, hedge dust-delta suppression, and MEXC depth channel formatting.

### v0.35.1-beta — Bitfinex Market-Price Realism Fix

- Fixed Bitfinex pair-info precision parsing so margin/risk fields like `0.5/0.25` no longer become `tick_size=0.1`.
- Stopped rounding live market quotes in monitor spread and execution paths; static tick rounding is reserved for explicit limit-order placement.
- Added quote/book mismatch guards before scoring and execution to reject incoherent snapshots such as a rounded Bitfinex ticker quote far away from the executable book.
- Changed simulated market fills to use order-book VWAP plus the configured safety buffer, instead of applying slippage to a potentially bad ticker top.
- Updated optimizer scoring to skip quote/book mismatches so bad market-data snapshots cannot promote or activate symbols.
- Updated D-03 discrepancy documentation and added regression tests for Bitfinex precision parsing and quote/book consistency.

### v0.35.0-beta — Profitability Gating & Market-Data Reliability

- Fixed Bitfinex exchange-info parsing for the real row-array API response and added normal user-agent headers, so supported-symbol filtering now loads the actual Bitfinex symbol set instead of leaving all configured symbols subscribed.
- Added Bitfinex historical pair overrides for `ALGOUSDT`, `ATOMUSDT`, and `BCHUSDT`, while filtering unsupported Bitfinex pairs such as `GRTUSDT` and `BNBUSDT` before websocket subscription.
- Hardened MEXC depth liveness so depth sub-connections reconnect when no initial depth arrives, and depth updates now count toward fetcher liveness.
- Added conservative top-of-book fallback from fresh best bid/ask quantities when full multi-level depth is absent, without inventing hidden liquidity.
- Changed quiet-period rebalance behavior to allow bounded refill-only recovery while still blocking expensive rotation during dead windows.
- Capped total refill-preview cost, including internal taker fees, before allowing refill-only rebalances.
- Disabled one-leg failure drills by default and made one-leg unwind costs debit simulated wallets when drills are enabled.
- Added all-in hedge accounting to net-profit/session reporting by including hedge funding minus futures execution fees.
- Prevented position-capped or immediate-net-negative routes from winning symbol selection and blocking better executable routes.
- Raised realistic per-config minimum immediate net thresholds in `settings.json` and `arbitragebot-configs.json` to avoid trades that cannot amortize maintenance/rebalance costs.
- Throttled repeated Binance spot BNB buy-skip logs while preserving state-change diagnostics.

### v0.34.2-beta — Realism Guard & Simulation Noise Fixes

- Fixed Bybit order-book depth handling to merge v5 snapshots and deltas instead of treating deltas as full books.
- Increased Binance visible depth to 20 levels and fixed MEXC depth-state propagation for more realistic slippage/depth checks.
- Split slippage diagnostics into true slippage, missing-book, visible-depth, and book-age guard counters across backend state, dashboard payloads, and XLSX export.
- Added depth-aware size shrinking before rejecting opportunities for insufficient visible book depth.
- Added a short Binance Futures account-info cache to reduce reserve polling rate-limit risk while still invalidating after capital transfers.
- Forced multi-config spot execution to simulation, disabled demo comparison polling in forced simulation, and kept hedge testnet/live mode separate.
- Filtered Bitfinex subscriptions to supported symbols and fixed two-character Bitfinex pair formatting such as `ARUSDT` and `OPUSDT`.
- Aligned rotation gating with displayed net P&L by using all transfer fees, not external-only fees.
- Made simulated BNB reserve auto-buy wallet-aware and throttled noisy unstable-candidate rejection logs.

### v0.34.1-beta — Realized P&L & Rebalance Cost Fixes

- Fixed simulated trade accounting so both arbitrage legs use the same executable base quantity, exchange minimums, available balances, and fee models before wallet mutation.
- Applied order-book slippage to simulated execution prices, so balances, trade P&L, and later portfolio/inventory state use the same realized economics.
- Added preflight realized-net skips for opportunities that become negative or below the configured minimum after fees, rounding, inventory limits, and slippage-adjusted prices.
- Tightened rebalance admission so paid internal/external rebalances need a positive realized profit estimate, and net-P&L gates account for all rebalance fees, not only withdrawal fees.
- Added per-symbol Binance Futures close backoff for transient testnet/live close failures and suppressed demo comparison output for simulation-only configs.
- Regenerated local `settings.json` and `arbitragebot-configs.json` with 30 configs total: six carefully tuned configs in each of the five config groups.

### v0.34.0-beta — Live-Realism Execution & Fee Hardening

- Added strict order-book slippage/depth gates so scoring and execution reject missing, stale, thin, or overly expensive books before routes can trade.
- Added book-age tracking from depth updates and depth-aware trade-size shrinking for opportunities that are still viable at a smaller executable size.
- Switched demo/testnet spot execution defaults to capped marketable-limit FOK orders for Binance, OKX, and Bybit, while keeping emergency one-leg recovery on market orders.
- Added controlled one-leg drill support for demo/testnet recovery testing and improved post-fill reconciliation for partial fills, quantity mismatches, fees, and recovery P&L.
- Added Binance BNB fee-reserve automation/protection, including spot reserve floors, futures fee reserve diagnostics, token-fee fallback to normal taker fees, and reserve-aware rebalance paths.
- Hardened hedge reserve gating so real/testnet spot trades block on stale, unavailable, emergency, or top-up-needed futures reserve status.
- Exposed new realism, execution, reserve, and diagnostics settings through the dashboard, backend settings schema, XLSX export, and regenerated `settings.json` / `arbitragebot-configs.json` for all 46 configs.
- Documented Session #31 with the live-slippage risk analysis, implementation details, follow-up robustness fixes, validation, and remaining live-trading caveats.

### v0.33.2-beta — Binance Futures Testnet Parser Hardening

- Hardened Binance USD-M Futures testnet account, balance, position, exchange-filter, and order parsing against blank numeric fields returned by the API.
- Futures account info now falls back to the USDT asset row when top-level futures account balance fields are blank.
- Hedge reserve status parsing now tolerates string/blank numeric values so async reserve refresh and hedge evaluation tasks do not crash.
- Real-position cleanup now reads executor `size` as well as legacy `positionAmt`, preventing missed orphan futures positions during close-all cleanup.
- Documented Session #30 with the testnet hedge failure, root cause, validation, and Binance Futures testnet credential requirements.

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
