# Session #35 - Log Audit for 2026-07-04/2026-07-05 Run

## Scope

- Original source log: `logs/bot-logs-2026-07-04-16-34-41.log`
- Continuation source log: `logs/bot-logs-2026-07-05-02-31-17.log`
- This file is updated from the continuation log because it contains the same run plus additional runtime.
- Bot version in continuation log: `v0.35.2-beta`
- Log window: `2026-07-03 08:10:01` to `2026-07-05 02:30:21`
- Longest latest config session runtime: `42h20m`
- Continuation log size: `122M`
- `wc -l`: `470,423`
- Parsed log records: `470,424`
- Severity counts:
  - `INFO`: `443,845`
  - `WARNING`: `24,964`
  - `ERROR`: `1,615`
- Config count: `30`
- Execution mode: forced to simulation twice because 30 configs were active:
  - `[Config] Forcing execution_mode=simulation (30 configs > 1; demo/live spot execution requires single-config mode)`

No `Errno 28`, `No space left on device`, or `ENOSPC` entries were found in this continuation log. The file is still very large, mostly due to repeated diagnostics and reconnect/top-up warnings, so log rotation remains important.

## Continuation Delta

Compared with the previous Session #35 report endpoint (`2026-07-04 16:33:53`), the continuation ran roughly 10 more hours and got worse after hedge costs:

| Metric | Previous report | Continuation endpoint | Delta |
|---|---:|---:|---:|
| Raw executed trade lines | `1,606` | `2,103` | `+497` |
| Latest session trades | `1,571` | `2,103` | `+532` |
| Gross spot PnL | `$293.12` | `$346.98` | `+$53.86` |
| Transfer fees | `$61.16` | `$72.83` | `+$11.67` |
| Cashback | `$6.12` | `$8.38` | `+$2.26` |
| Spot net | `$236.00` | `$280.54` | `+$44.54` |
| Hedge net | `$-334.80` | `$-411.89` | `$-77.09` |
| Total reported net | `$-98.80` | `$-131.36` | `$-32.56` |
| Positive configs | `6/30` | `6/30` | no change |
| Positive net total | `$53.40` | `$47.40` | `$-6.00` |
| Negative net total | `$-152.20` | `$-178.76` | `$-26.56` |
| Warnings | `20,990` | `24,964` | `+3,974` |
| Errors | `1,072` | `1,615` | `+543` |

## Executive Summary

The bot is still finding gross spot arbitrage, but it is not profitable after hedge and transfer costs.

Latest session totals across all 30 configs:

- Gross spot PnL: `+$346.98`
- Transfer fees: `$72.83`
- Cashback: `$8.38`
- Spot net: `+$280.54`
- Hedge funding: `+$6.13`
- Futures fees: `$417.97`
- Hedge net: `-$411.89`
- Total reported net: `-$131.36`
- Positive configs: `6/30`, total `+$47.40`
- Negative configs: `24/30`, total `-$178.76`

The important fact did not change from the previous report: hedge fees are larger than the realized spot edge. The extra 10 hours added `+$44.54` spot net but `-$77.09` additional hedge net, so the combined result became `-$32.56` worse.

There is also a serious anomaly event near the end of the continuation:

- `2026-07-05 02:27:41`: `[Anomaly] EMERGENCY: EMERGENCY (layer_a_realized): drawdown 27.77% >= threshold 15.0% — realized capital drop — actual locked-in loss`
- `2026-07-05 02:27:42`: `Group 1 / Neutral (Baseline)` logged anomaly protection and paused trading.

That config is also the only config using `hedge_mode=testnet`, and it produced all config-level errors.

## Main Findings

1. Hedge fees still dominate the strategy.
   The run made `+$280.54` spot net but lost `-$411.89` hedge net. This is not a display issue; it is session accounting showing hedge fee drag.

2. `Group 1 / Neutral (Baseline)` is unhealthy because of Binance futures testnet.
   It has `1,551` errors: `1,400` hedge open timeouts, `150` bad gateway failures, and `1` tiny quantity adjust failure. Its balance snapshot also lacks `accounting` and `drift`, unlike the other configs.

3. MEXC depth streaming remains noisy.
   There are `9,682` MEXC depth "no initial data" warnings, plus MEXC handshake errors. This contributes to log growth and may worsen book-age/depth reliability.

4. BNB futures top-up simulation is still noisy.
   There are `12,981` `FUTURES_BNB_TOPUP_SKIPPED` warnings and many futures BNB discount skipped warnings. The strategy often pays futures fees without the intended discount state.

5. End-of-run monitors show no config had an executable trade at the latest status.
   Latest monitor statuses for all 30 configs show `profitable=0 executed=0`. Most candidates were weak/low-profit and then blocked by book age, visible depth, or slippage.

6. Portfolio totals are still not realized PnL.
   Aggregate latest balance snapshots show `total=$93,334`, `accounting=$88,868`, and `drift=+$2,732.10`. This favorable drift can reverse. Use session net/accounting as the strategy truth.

7. Capacity is usable but tight for a 1 vCPU VPS.
   Average sweep is about `902ms`, latest sweep is `861ms`, and worst p95 hit `3,537ms`. Heap reached `1,388MB` and ended at `1,383MB`, which is high on a 2GB VPS.

## Capacity And Sweep

| Metric | Value |
|---|---:|
| Capacity samples | `2,519` |
| Average `sweep_avg` | `902.4ms` |
| Median `sweep_avg` | `862ms` |
| Average p95 | `1,108.4ms` |
| Worst `sweep_avg` | `1,775ms` at `2026-07-04 15:11:09` |
| Worst p95 | `3,537ms` at `2026-07-04 15:11:09` |
| Latest capacity line | `2026-07-05 02:30:20` |
| Latest `sweep_avg` | `861ms` |
| Latest `last` | `774ms` |
| Latest p95 | `1,246ms` |
| Latest `build_prices` | `20.0ms` |
| Latest `per_cfg` | `846ms` |
| Latest optimizer/monitor split | `opt=604ms`, `mon=42ms` |
| Latest configs | `30` |
| Latest dirty configs | `0` |
| Latest capacity trades | `2,103` |
| Latest transfers | `9,993` |
| Latest watchlist | `43` |
| Latest rotations | `343` |
| Latest ticks total/max | `972,085` / `570` |
| Max heap | `1,388MB` |
| Latest heap | `1,383MB` |
| Max GC objects | `1,074,517` |
| Latest GC objects | `1,055,160` |

The continuation log does not include separate `SlowConfigs`, `Fetcher`, `Heap`, or `Broadcast` sub-lines. It only includes the main `[Capacity]` line with heap and GC object counts.

## Errors And Warnings

Top global warnings:

| Warning class | Count | Notes |
|---|---:|---|
| MEXC depth no initial data | `9,682` | Depth sub-connections repeatedly reconnect after no initial data. |
| WS task crashed | `25` | Mostly exchange websocket task churn. |
| Rejected dashboard WS origin | `10` | Auth/origin noise from `https://38.60.156.236`; not trading logic. |
| Bitfinex subscribe failed | `6` | Bitfinex subscription failures. |
| Capacity sweep budget exceeded | `3` | Sweep overran configured budget. |
| Forced simulation warning | `2` | Multi-config mode forced spot execution to simulation. |

Top global errors:

| Error class | Count |
|---|---:|
| MEXC depth handshake timeout | `16` |
| MEXC ticker/sub-connection handshake timeout | `12` |
| Generic opening handshake failed | `10` |
| KuCoin connection error | `8` |
| Bybit connection error | `7` |
| Bitget connection error | `7` |
| OKX connection error | `3` |
| Pionex sub-connection reset | `1` |

Top config warnings:

| Count | Config | Warning |
|---:|---|---|
| `2,072` | G2 / Large ($120, 6%) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `1,822` | G4 / Concentrated (2 active) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `1,800` | G3 / Neutral (Baseline) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `1,247` | G4 / Conservative (3 active) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `837` | G5 / Loose Inventory Drift | `FUTURES_BNB_TOPUP_SKIPPED` |
| `803` | G1 / Conservative | `FUTURES_BNB_TOPUP_SKIPPED` |
| `731` | G5 / Conservative (Sticky) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `712` | G3 / Conservative (Strict Scoring) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `385` | G1 / + Gate.io | `FUTURES_BNB_TOPUP_SKIPPED` |
| `379` | G1 / Neutral (Baseline) | Binance futures `set_margin_type` 408 |
| `378` | G1 / Aggressive | `FUTURES_BNB_TOPUP_SKIPPED` |
| `295` | G3 / Tight Stability Gates | `FUTURES_BNB_TOPUP_SKIPPED` |
| `186` | G5 / Neutral (Baseline) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `184` | G4 / Neutral (4 active) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `161` | G3 / Aggressive (Permissive Scoring) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `160` | G4 / No Auto-Expand | `FUTURES_BNB_TOPUP_SKIPPED` |
| `157` | G1 / Neutral (Baseline) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `152` | G2 / Medium-Conservative ($80, 4%) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `150` | G2 / Medium-Aggressive ($80, 4%) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `149` | G2 / Medium-Neutral ($80, 4%) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `146` | G3 / Loose Stability Gates | `FUTURES_BNB_TOPUP_SKIPPED` |
| `139` | G5 / No Boosts (Pure Score) | `FUTURES_BNB_TOPUP_SKIPPED` |
| `137` | G3 / Neutral (Baseline) | Futures BNB discount skipped |

Config errors:

| Count | Config | Error |
|---:|---|---|
| `1,400` | G1 / Neutral (Baseline) | Hedge `OPEN_FAILED` timeout `-1007` |
| `150` | G1 / Neutral (Baseline) | Hedge `OPEN_FAILED` bad gateway |
| `1` | G1 / Neutral (Baseline) | Hedge `ADJUST_FAILED` tiny HYPEUSDT quantity |

## Aggregate Trading Results

| Metric | Value |
|---|---:|
| Session trades | `2,103` |
| Raw executed trade lines | `2,103` |
| Raw trade size | `$115,828.20` |
| Raw/gross spot PnL | `$346.98` |
| Transfer fees | `$72.83` |
| Cashback | `$8.38` |
| Spot net | `$280.54` |
| Hedge funding | `$6.13` |
| Futures fees | `$417.97` |
| Hedge net | `$-411.89` |
| Total reported net | `$-131.36` |
| Raw trade net avg / median | `0.3743%` / `0.1485%` |
| Raw trade net min / max | `0.0666%` / `6.1011%` |
| Positive configs | `6`, total `+$47.40` |
| Negative configs | `24`, total `-$178.76` |

Top traded symbols:

| Symbol | Trades |
|---|---:|
| ADAUSDT | `1,081` |
| ALGOUSDT | `149` |
| NEOUSDT | `136` |
| HYPEUSDT | `104` |
| XLMUSDT | `92` |
| ZROUSDT | `85` |
| GRTUSDT | `78` |
| ZECUSDT | `65` |
| XRPUSDT | `56` |
| ETHUSDT | `48` |

Top routes:

| Route | Trades |
|---|---:|
| MEXC -> Bitfinex | `819` |
| Bitfinex -> MEXC | `717` |
| Bitget -> Bitfinex | `278` |
| OKX -> Bitfinex | `63` |
| MEXC -> Bitget | `44` |
| Binance -> Bitget | `30` |
| MEXC -> KuCoin | `24` |
| Binance -> Bitfinex | `22` |
| Bitfinex -> Binance | `17` |
| Binance -> KuCoin | `12` |
| KuCoin -> Bitfinex | `12` |

## Config Details

Common settings logged across configs:

- `adaptive_mode=True`, `auto_rotate=True`
- `net_pnl_gate`: warmup `3` trades, grace `600s`
- `spot_execution_order`: `marketable_limit_fok`, limit buffer `0.0200%`, one-leg drill off
- Hedging enabled for all configs; only G1 / Neutral uses `mode=testnet`, all others use `mode=simulation`
- Futures leverage: `2x`
- Futures taker fee in settings: `0.0500%`
- Futures BNB top-up enabled; futures BNB min `$5`, target `5%`
- Spot BNB floor `$5`, spot BNB auto-buy enabled, spot BNB target `1%`, order type `market`
- Futures reserve target `40%`, top-up `35%`, emergency `30%`, overflow `45%`, transfer minimum `$10`
- Inventory rebalance enabled, interval `12h`, drift threshold `35%`
- Regime weak rebalance policy: `refill_only`
- Funding aware enabled, skip threshold `-0.0500%`

| # | Config | Capital | Trade | Symbols | Min net | Slip leg/total | Depth | Book age | Hedge | Reserve | Disabled |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| 1 | G1 / + KuCoin | `$1,000` | `$24` (`4.0%`) | `4-6` | `0.09%` | `0.045/0.08%` | `1.3x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, Pionex |
| 2 | G1 / All 8 Exchanges | `$1,000` | `$24` (`4.0%`) | `4-6` | `0.10%` | `0.04/0.075%` | `1.4x` | `2.5/18.0s` | simulation, `2x` | `40%/35%` | Pionex |
| 3 | G1 / Neutral (Baseline) | `$1,000` | `$24` (`4.0%`) | `4-6` | `0.08%` | `0.05/0.085%` | `1.25x` | `3.0/20.0s` | testnet, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 4 | G1 / Conservative | `$1,000` | `$12` (`2.0%`) | `4-6` | `0.10%` | `0.04/0.07%` | `1.35x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 5 | G1 / Aggressive | `$1,000` | `$48` (`8.0%`) | `4-6` | `0.07%` | `0.06/0.10%` | `1.15x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 6 | G1 / + Gate.io | `$1,000` | `$24` (`4.0%`) | `4-6` | `0.09%` | `0.045/0.08%` | `1.3x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | KuCoin, Pionex |
| 7 | G2 / Tiny ($20, 1%) | `$2,000` | `$12` (`1.0%`) | `4-6` | `0.12%` | `0.06/0.10%` | `1.15x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 8 | G2 / Small ($40, 2%) | `$2,000` | `$24` (`2.0%`) | `4-6` | `0.09%` | `0.055/0.095%` | `1.2x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 9 | G2 / Medium-Conservative ($80, 4%) | `$2,000` | `$48` (`4.0%`) | `4-6` | `0.09%` | `0.04/0.07%` | `1.35x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 10 | G2 / Medium-Neutral ($80, 4%) | `$2,000` | `$48` (`4.0%`) | `4-6` | `0.07%` | `0.05/0.085%` | `1.25x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 11 | G2 / Medium-Aggressive ($80, 4%) | `$2,000` | `$48` (`4.0%`) | `4-6` | `0.07%` | `0.06/0.10%` | `1.15x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 12 | G2 / Large ($120, 6%) | `$2,000` | `$72` (`6.0%`) | `4-6` | `0.08%` | `0.035/0.065%` | `1.5x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 13 | G3 / Conservative (Strict Scoring) | `$3,000` | `$54` (`3.0%`) | `4-6` | `0.09%` | `0.04/0.07%` | `1.35x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 14 | G3 / Neutral (Baseline) | `$3,000` | `$72` (`4.0%`) | `4-6` | `0.07%` | `0.05/0.085%` | `1.25x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 15 | G3 / Aggressive (Permissive Scoring) | `$3,000` | `$90` (`5.0%`) | `4-6` | `0.07%` | `0.06/0.10%` | `1.15x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 16 | G3 / Short Scoring Window (10min) | `$3,000` | `$72` (`4.0%`) | `4-6` | `0.07%` | `0.05/0.085%` | `1.25x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 17 | G3 / Tight Stability Gates | `$3,000` | `$72` (`4.0%`) | `4-6` | `0.09%` | `0.04/0.07%` | `1.35x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 18 | G3 / Loose Stability Gates | `$3,000` | `$72` (`4.0%`) | `4-6` | `0.07%` | `0.055/0.095%` | `1.2x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 19 | G4 / Concentrated (2 active) | `$4,000` | `$96` (`4.0%`) | `2-3` | `0.07%` | `0.045/0.08%` | `1.3x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 20 | G4 / Conservative (3 active) | `$4,000` | `$96` (`4.0%`) | `3-5` | `0.09%` | `0.04/0.07%` | `1.35x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 21 | G4 / Neutral (4 active) | `$4,000` | `$96` (`4.0%`) | `4-6` | `0.07%` | `0.05/0.085%` | `1.25x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 22 | G4 / Diverse (6 active) | `$4,000` | `$96` (`4.0%`) | `6-8` | `0.07%` | `0.05/0.085%` | `1.25x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 23 | G4 / Wide (8 active) | `$4,000` | `$96` (`4.0%`) | `8-10` | `0.08%` | `0.045/0.08%` | `1.35x` | `2.5/18.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 24 | G4 / No Auto-Expand | `$4,000` | `$96` (`4.0%`) | `4-6` | `0.07%` | `0.045/0.08%` | `1.3x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 25 | G5 / Conservative (Sticky) | `$5,000` | `$90` (`3.0%`) | `4-6` | `0.08%` | `0.04/0.07%` | `1.35x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 26 | G5 / Neutral (Baseline) | `$5,000` | `$120` (`4.0%`) | `4-6` | `0.07%` | `0.05/0.085%` | `1.25x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 27 | G5 / Aggressive (Rapid Shifts) | `$5,000` | `$150` (`5.0%`) | `4-6` | `0.07%` | `0.055/0.095%` | `1.2x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 28 | G5 / No Boosts (Pure Score) | `$5,000` | `$120` (`4.0%`) | `4-6` | `0.07%` | `0.045/0.08%` | `1.3x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 29 | G5 / Tight Inventory Drift | `$5,000` | `$120` (`4.0%`) | `4-6` | `0.08%` | `0.04/0.07%` | `1.35x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |
| 30 | G5 / Loose Inventory Drift | `$5,000` | `$120` (`4.0%`) | `4-6` | `0.07%` | `0.05/0.085%` | `1.25x` | `3.0/20.0s` | simulation, `2x` | `40%/35%` | Gate.io, KuCoin, Pionex |

## All Config Results

| # | Config | Runtime | Trades | PnL | Spot net | Hedge net | Net | $/hr | Total | Accounting | Drift | Futures fees | W/E |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | G1 / + KuCoin | `42h17m` | `44` | `$1.78` | `$-2.03` | `$-3.15` | `$-5.18` | `$-0.12` | `$1,015.00` | `$995.00` | `$21.48` | `$3.22` | `16/0` |
| 2 | G1 / All 8 Exchanges | `42h16m` | `70` | `$2.62` | `$-1.24` | `$-3.86` | `$-5.10` | `$-0.12` | `$1,021.00` | `$995.00` | `$21.99` | `$3.92` | `14/0` |
| 3 | G1 / Neutral (Baseline) | `42h16m` | `101` | `$2.64` | `$1.45` | `$-1.93` | `$-0.47` | `$-0.01` | `$1,452.00` | `n/a` | `n/a` | `$1.97` | `586/1551` |
| 4 | G1 / Conservative | `42h17m` | `19` | `$0.42` | `$-0.20` | `$-2.65` | `$-2.85` | `$-0.07` | `$1,038.00` | `$997.00` | `$42.91` | `$2.74` | `849/0` |
| 5 | G1 / Aggressive | `42h15m` | `66` | `$2.28` | `$0.73` | `$-6.81` | `$-6.08` | `$-0.14` | `$1,058.00` | `$994.00` | `$59.65` | `$6.90` | `443/0` |
| 6 | G1 / + Gate.io | `42h15m` | `64` | `$11.90` | `$9.75` | `$-5.38` | `$4.37` | `$0.10` | `$1,047.00` | `$1,004.00` | `$41.39` | `$5.46` | `455/0` |
| 7 | G2 / Tiny ($20, 1%) | `42h16m` | `14` | `$0.37` | `$-1.60` | `$-7.45` | `$-9.04` | `$-0.21` | `$2,035.00` | `$1,991.00` | `$38.63` | `$7.58` | `31/0` |
| 8 | G2 / Small ($40, 2%) | `42h18m` | `104` | `$10.00` | `$7.13` | `$-8.88` | `$-1.75` | `$-0.04` | `$2,071.00` | `$1,998.00` | `$66.02` | `$9.01` | `114/0` |
| 9 | G2 / Medium-Conservative ($80, 4%) | `42h18m` | `15` | `$1.11` | `$-0.15` | `$-6.54` | `$-6.69` | `$-0.16` | `$2,113.00` | `$1,993.00` | `$116.16` | `$6.71` | `195/0` |
| 10 | G2 / Medium-Neutral ($80, 4%) | `42h18m` | `70` | `$8.84` | `$7.24` | `$-8.40` | `$-1.17` | `$-0.03` | `$2,105.00` | `$1,999.00` | `$101.77` | `$8.56` | `205/0` |
| 11 | G2 / Medium-Aggressive ($80, 4%) | `42h14m` | `158` | `$8.26` | `$5.86` | `$-10.43` | `$-4.57` | `$-0.11` | `$2,100.00` | `$1,995.00` | `$98.99` | `$10.58` | `208/0` |
| 12 | G2 / Large ($120, 6%) | `42h17m` | `18` | `$1.14` | `$0.50` | `$-7.07` | `$-6.58` | `$-0.16` | `$1,987.00` | `$1,993.00` | `$-0.03` | `$7.28` | `2169/0` |
| 13 | G3 / Conservative (Strict Scoring) | `42h18m` | `34` | `$22.28` | `$21.38` | `$-9.15` | `$12.23` | `$0.29` | `$3,031.00` | `$3,012.00` | `$12.93` | `$9.40` | `777/0` |
| 14 | G3 / Neutral (Baseline) | `42h15m` | `85` | `$23.84` | `$21.46` | `$-16.93` | `$4.53` | `$0.11` | `$3,006.00` | `$3,005.00` | `$-13.92` | `$17.13` | `1972/0` |
| 15 | G3 / Aggressive (Permissive Scoring) | `42h15m` | `135` | `$14.17` | `$10.97` | `$-18.59` | `$-7.62` | `$-0.18` | `$3,164.00` | `$2,992.00` | `$152.96` | `$18.79` | `222/0` |
| 16 | G3 / Short Scoring Window (10min) | `42h19m` | `88` | `$18.57` | `$13.16` | `$-28.22` | `$-15.06` | `$-0.36` | `$3,138.00` | `$2,985.00` | `$127.14` | `$28.37` | `168/0` |
| 17 | G3 / Tight Stability Gates | `42h20m` | `30` | `$4.18` | `$2.44` | `$-12.83` | `$-10.40` | `$-0.25` | `$3,069.00` | `$2,990.00` | `$68.71` | `$13.06` | `348/0` |
| 18 | G3 / Loose Stability Gates | `42h16m` | `107` | `$12.95` | `$9.19` | `$-15.55` | `$-6.37` | `$-0.15` | `$3,178.00` | `$2,994.00` | `$170.69` | `$15.77` | `211/0` |
| 19 | G4 / Concentrated (2 active) | `42h18m` | `9` | `$2.08` | `$1.69` | `$-7.50` | `$-5.80` | `$-0.14` | `$4,080.00` | `$3,994.00` | `$94.03` | `$7.82` | `1875/0` |
| 20 | G4 / Conservative (3 active) | `42h16m` | `35` | `$28.93` | `$27.40` | `$-14.10` | `$13.30` | `$0.31` | `$4,013.00` | `$4,013.00` | `$-10.01` | `$14.43` | `1334/0` |
| 21 | G4 / Neutral (4 active) | `42h19m` | `110` | `$22.63` | `$19.02` | `$-21.71` | `$-2.69` | `$-0.06` | `$4,104.00` | `$3,997.00` | `$87.88` | `$21.94` | `254/0` |
| 22 | G4 / Diverse (6 active) | `42h15m` | `126` | `$26.88` | `$24.61` | `$-19.36` | `$5.24` | `$0.12` | `$4,233.00` | `$4,005.00` | `$210.74` | `$19.60` | `98/0` |
| 23 | G4 / Wide (8 active) | `42h17m` | `86` | `$19.70` | `$17.57` | `$-20.59` | `$-3.02` | `$-0.07` | `$4,196.00` | `$3,997.00` | `$181.96` | `$20.81` | `105/0` |
| 24 | G4 / No Auto-Expand | `42h16m` | `82` | `$31.86` | `$28.37` | `$-20.64` | `$7.73` | `$0.18` | `$4,058.00` | `$4,008.00` | `$33.64` | `$20.88` | `228/0` |
| 25 | G5 / Conservative (Sticky) | `42h16m` | `17` | `$2.87` | `$1.96` | `$-12.13` | `$-10.17` | `$-0.24` | `$5,096.00` | `$4,990.00` | `$98.66` | `$12.61` | `766/0` |
| 26 | G5 / Neutral (Baseline) | `42h15m` | `97` | `$13.53` | `$11.30` | `$-23.69` | `$-12.38` | `$-0.29` | `$5,108.00` | `$4,988.00` | `$103.59` | `$23.96` | `248/0` |
| 27 | G5 / Aggressive (Rapid Shifts) | `42h19m` | `149` | `$20.81` | `$18.20` | `$-34.25` | `$-16.05` | `$-0.38` | `$5,252.00` | `$4,984.00` | `$248.09` | `$34.50` | `105/0` |
| 28 | G5 / No Boosts (Pure Score) | `42h17m` | `22` | `$5.44` | `$4.03` | `$-17.55` | `$-13.52` | `$-0.32` | `$5,252.00` | `$4,986.00` | `$253.66` | `$17.86` | `175/0` |
| 29 | G5 / Tight Inventory Drift | `42h18m` | `101` | `$16.22` | `$14.53` | `$-24.02` | `$-9.49` | `$-0.22` | `$5,260.00` | `$4,991.00` | `$249.62` | `$24.27` | `96/0` |
| 30 | G5 / Loose Inventory Drift | `42h19m` | `47` | `$8.68` | `$5.82` | `$-22.53` | `$-16.71` | `$-0.39` | `$5,054.00` | `$4,983.00` | `$52.77` | `$22.84` | `933/0` |

Best latest session nets:

| Config | Net |
|---|---:|
| G4 / Conservative (3 active) | `$13.30` |
| G3 / Conservative (Strict Scoring) | `$12.23` |
| G4 / No Auto-Expand | `$7.73` |
| G4 / Diverse (6 active) | `$5.24` |
| G3 / Neutral (Baseline) | `$4.53` |
| G1 / + Gate.io | `$4.37` |

Worst latest session nets:

| Config | Net |
|---|---:|
| G5 / Loose Inventory Drift | `$-16.71` |
| G5 / Aggressive (Rapid Shifts) | `$-16.05` |
| G3 / Short Scoring Window (10min) | `$-15.06` |
| G5 / No Boosts (Pure Score) | `$-13.52` |
| G5 / Neutral (Baseline) | `$-12.38` |
| G3 / Tight Stability Gates | `$-10.40` |
| G5 / Conservative (Sticky) | `$-10.17` |
| G5 / Tight Inventory Drift | `$-9.49` |
| G2 / Tiny ($20, 1%) | `$-9.04` |
| G3 / Aggressive (Permissive Scoring) | `$-7.62` |

## Guard And Realism Counters

Aggregate guard totals:

| Counter | Count |
|---|---:|
| `sz0` | `19,033,087` |
| `rebal_blocked` | `16,374` |
| `phantom` | `17,580` |
| `slip_guard` | `1,530,236` |
| `missing_book` | `0` |
| `visible_depth` | `4,164,592` |
| `book_age` | `13,211,764` |
| `depth_shrink` | `263` / `$6,500.71` |
| `evd_sell` | `18,412,708` |
| `demoted` | `104` |
| `one_leg` | `0` / `$0.00` |
| `pos_cap` | `12,279,249` |

Per-config guard counters:

| # | Config | sz0 | rebal | phantom | slip | missing | visible | book | depth shrink | evd/demoted | one-leg | pos cap |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | G1 / + KuCoin | `1,269,585` | `3,168` | `1,515` | `82,410` | `0` | `88,327` | `1,091,027` | `2 / $7.08` | `521,259 / 0` | `0 / $0.00` | `294,290` |
| 2 | G1 / All 8 Exchanges | `1,608,946` | `6,208` | `2,585` | `174,374` | `0` | `73,960` | `1,349,810` | `0 / $0.00` | `585,504 / 2` | `0 / $0.00` | `348,620` |
| 3 | G1 / Neutral (Baseline) | `558,711` | `592` | `804` | `47,032` | `0` | `52,121` | `455,675` | `4 / $39.59` | `530,072 / 0` | `0 / $0.00` | `523,140` |
| 4 | G1 / Conservative | `663,632` | `14` | `149` | `5,278` | `0` | `36,806` | `617,215` | `0 / $0.00` | `779,832 / 52` | `0 / $0.00` | `1,175,532` |
| 5 | G1 / Aggressive | `590,510` | `1,869` | `1,095` | `79,021` | `0` | `131,500` | `373,526` | `4 / $54.55` | `522,767 / 6` | `0 / $0.00` | `0` |
| 6 | G1 / + Gate.io | `892,114` | `646` | `859` | `78,457` | `0` | `87,833` | `720,898` | `3 / $17.18` | `756,438 / 1` | `0 / $0.00` | `601,234` |
| 7 | G2 / Tiny ($20, 1%) | `215,645` | `8` | `62` | `106` | `0` | `7,205` | `206,217` | `0 / $0.00` | `274,590 / 0` | `0 / $0.00` | `1,019,888` |
| 8 | G2 / Small ($40, 2%) | `373,516` | `56` | `450` | `3,860` | `0` | `37,037` | `329,023` | `2 / $15.04` | `514,454 / 0` | `0 / $0.00` | `779,899` |
| 9 | G2 / Medium-Conservative ($80, 4%) | `695,638` | `143` | `178` | `80,212` | `0` | `164,418` | `447,334` | `3 / $10.64` | `723,283 / 33` | `0 / $0.00` | `875,084` |
| 10 | G2 / Medium-Neutral ($80, 4%) | `587,343` | `420` | `558` | `32,999` | `0` | `102,529` | `447,887` | `2 / $16.00` | `583,210 / 0` | `0 / $0.00` | `509,691` |
| 11 | G2 / Medium-Aggressive ($80, 4%) | `459,809` | `368` | `592` | `9,880` | `0` | `102,233` | `343,715` | `7 / $144.83` | `494,271 / 0` | `0 / $0.00` | `318,133` |
| 12 | G2 / Large ($120, 6%) | `672,020` | `525` | `513` | `114,651` | `0` | `191,211` | `361,014` | `2 / $15.63` | `934,375 / 8` | `0 / $0.00` | `99,686` |
| 13 | G3 / Conservative (Strict Scoring) | `862,640` | `60` | `478` | `55,572` | `0` | `268,085` | `534,126` | `16 / $247.55` | `1,051,411 / 0` | `0 / $0.00` | `405,633` |
| 14 | G3 / Neutral (Baseline) | `557,886` | `195` | `547` | `38,715` | `0` | `134,257` | `381,099` | `6 / $103.76` | `623,133 / 0` | `0 / $0.00` | `283,818` |
| 15 | G3 / Aggressive (Permissive Scoring) | `410,299` | `289` | `591` | `13,508` | `0` | `127,721` | `265,455` | `12 / $306.00` | `479,717 / 0` | `0 / $0.00` | `341,685` |
| 16 | G3 / Short Scoring Window (10min) | `384,188` | `314` | `501` | `25,772` | `0` | `113,019` | `242,731` | `1 / $51.59` | `423,570 / 0` | `0 / $0.00` | `345,082` |
| 17 | G3 / Tight Stability Gates | `865,207` | `240` | `465` | `76,440` | `0` | `265,788` | `518,776` | `5 / $171.21` | `861,145 / 0` | `0 / $0.00` | `242,871` |
| 18 | G3 / Loose Stability Gates | `524,269` | `254` | `555` | `18,374` | `0` | `158,248` | `344,404` | `5 / $135.31` | `435,247 / 0` | `0 / $0.00` | `493,568` |
| 19 | G4 / Concentrated (2 active) | `521,397` | `17` | `223` | `62,102` | `0` | `131,402` | `324,094` | `23 / $238.81` | `634,419 / 2` | `0 / $0.00` | `335,528` |
| 20 | G4 / Conservative (3 active) | `781,154` | `115` | `454` | `83,403` | `0` | `255,414` | `437,499` | `20 / $517.28` | `867,105 / 0` | `0 / $0.00` | `258,918` |
| 21 | G4 / Neutral (4 active) | `591,701` | `79` | `579` | `36,373` | `0` | `166,652` | `384,996` | `20 / $415.42` | `609,466 / 0` | `0 / $0.00` | `327,402` |
| 22 | G4 / Diverse (6 active) | `503,942` | `160` | `572` | `32,924` | `0` | `159,355` | `308,217` | `16 / $492.04` | `475,806 / 0` | `0 / $0.00` | `355,535` |
| 23 | G4 / Wide (8 active) | `459,307` | `54` | `492` | `43,271` | `0` | `125,755` | `287,060` | `14 / $166.90` | `436,207 / 0` | `0 / $0.00` | `294,662` |
| 24 | G4 / No Auto-Expand | `619,896` | `74` | `464` | `54,280` | `0` | `156,614` | `405,800` | `16 / $234.93` | `554,397 / 0` | `0 / $0.00` | `261,843` |
| 25 | G5 / Conservative (Sticky) | `530,596` | `33` | `137` | `62,051` | `0` | `163,783` | `300,123` | `2 / $42.50` | `999,992 / 0` | `0 / $0.00` | `896,949` |
| 26 | G5 / Neutral (Baseline) | `591,250` | `73` | `524` | `39,954` | `0` | `161,677` | `386,185` | `22 / $885.38` | `543,584 / 0` | `0 / $0.00` | `225,656` |
| 27 | G5 / Aggressive (Rapid Shifts) | `289,673` | `129` | `570` | `20,875` | `0` | `104,614` | `160,553` | `22 / $1,103.05` | `356,545 / 0` | `0 / $0.00` | `0` |
| 28 | G5 / No Boosts (Pure Score) | `808,547` | `9` | `115` | `61,646` | `0` | `266,422` | `477,180` | `1 / $66.46` | `717,538 / 0` | `0 / $0.00` | `179,429` |
| 29 | G5 / Tight Inventory Drift | `472,481` | `61` | `391` | `60,423` | `0` | `138,099` | `271,349` | `17 / $448.89` | `398,757 / 0` | `0 / $0.00` | `309,051` |
| 30 | G5 / Loose Inventory Drift | `671,185` | `201` | `562` | `36,273` | `0` | `192,507` | `438,776` | `16 / $553.09` | `724,614 / 0` | `0 / $0.00` | `176,422` |

## Raw Executed Trades By Config

| # | Config | Raw trades | Raw profit | Raw size | Avg net | Median net | Avg slip | Top symbols | Top routes |
|---:|---|---:|---:|---:|---:|---:|---:|---|---|
| 1 | G1 / + KuCoin | `44` | `$1.78` | `$947.92` | `0.1854%` | `0.1505%` | `0.0070%` | SNX 18, AR 7, ALGO 6, ADA 5 | MEXC->KuCoin 15, KuCoin->Bitfinex 7, Binance->KuCoin 6 |
| 2 | G1 / All 8 Exchanges | `70` | `$2.62` | `$1,416.92` | `0.1722%` | `0.1417%` | `0.0058%` | ADA 26, SNX 25, XMR 14, AR 2 | MEXC->Bitfinex 18, Bitfinex->KuCoin 9, Bitget->KuCoin 9 |
| 3 | G1 / Neutral (Baseline) | `101` | `$2.64` | `$1,659.38` | `0.1563%` | `0.1401%` | `0.0143%` | GRT 61, ADA 27, HYPE 8, XRP 2 | MEXC->Bitget 36, Binance->Bitget 24, Bitfinex->MEXC 17 |
| 4 | G1 / Conservative | `19` | `$0.42` | `$257.01` | `0.1709%` | `0.1351%` | `0.0095%` | GRT 15, ADA 2, BCH 2 | MEXC->Bitget 7, MEXC->Bitfinex 4, Bybit->Bitget 4 |
| 5 | G1 / Aggressive | `66` | `$2.28` | `$1,690.95` | `0.1346%` | `0.1092%` | `0.0057%` | ADA 22, XLM 12, WIF 11, ALGO 8 | MEXC->Bitfinex 25, Bitfinex->MEXC 17, Bitget->Bitfinex 7 |
| 6 | G1 / + Gate.io | `64` | `$11.90` | `$1,261.03` | `1.0092%` | `0.2038%` | `0.0051%` | ADA 28, NEO 13, ZRO 6, ALGO 6 | Bitfinex->MEXC 30, MEXC->Bitfinex 24, Bitget->Bitfinex 7 |
| 7 | G2 / Tiny ($20, 1%) | `14` | `$0.37` | `$179.60` | `0.1796%` | `0.1608%` | `0.0050%` | ADA 7, HYPE 7 | MEXC->Bitfinex 8, Bitget->Bitfinex 6 |
| 8 | G2 / Small ($40, 2%) | `104` | `$10.00` | `$2,041.91` | `0.5186%` | `0.1626%` | `0.0051%` | ADA 57, HYPE 15, ALGO 10, NEO 9 | Bitfinex->MEXC 41, MEXC->Bitfinex 40, Bitget->Bitfinex 20 |
| 9 | G2 / Medium-Conservative ($80, 4%) | `15` | `$1.11` | `$517.50` | `0.2369%` | `0.2144%` | `0.0056%` | ADA 4, ZRO 3, ALGO 3, XLM 2 | MEXC->Bitfinex 7, Bitget->Bitfinex 4, OKX->Bitfinex 3 |
| 10 | G2 / Medium-Neutral ($80, 4%) | `70` | `$8.84` | `$2,423.05` | `0.4554%` | `0.1626%` | `0.0053%` | ADA 39, NEO 8, XLM 7, HYPE 7 | Bitfinex->MEXC 29, MEXC->Bitfinex 27, Bitget->Bitfinex 12 |
| 11 | G2 / Medium-Aggressive ($80, 4%) | `158` | `$8.26` | `$4,960.10` | `0.1626%` | `0.1297%` | `0.0051%` | ADA 102, ZRO 12, ALGO 11, XLM 7 | MEXC->Bitfinex 68, Bitfinex->MEXC 67, Bitget->Bitfinex 8 |
| 12 | G2 / Large ($120, 6%) | `18` | `$1.14` | `$731.17` | `0.1521%` | `0.1271%` | `0.0050%` | ADA 8, XLM 8, ZEC 1, ZRO 1 | MEXC->Bitfinex 12, Bitfinex->MEXC 4, Bitfinex->OKX 1 |
| 13 | G3 / Conservative (Strict Scoring) | `34` | `$22.28` | `$1,412.35` | `1.9903%` | `0.3103%` | `0.0050%` | NEO 15, ADA 12, ALGO 3, ETH 2 | Bitfinex->MEXC 20, MEXC->Bitfinex 10, Bitget->Bitfinex 3 |
| 14 | G3 / Neutral (Baseline) | `85` | `$23.84` | `$4,313.87` | `0.6719%` | `0.1846%` | `0.0056%` | ADA 39, NEO 13, ZEC 7, ALGO 7 | Bitfinex->MEXC 39, MEXC->Bitfinex 32, Bitget->Bitfinex 10 |
| 15 | G3 / Aggressive (Permissive Scoring) | `135` | `$14.17` | `$7,126.43` | `0.2000%` | `0.1339%` | `0.0057%` | ADA 81, ZRO 11, ALGO 9, XRP 9 | Bitfinex->MEXC 50, MEXC->Bitfinex 49, Bitget->Bitfinex 18 |
| 16 | G3 / Short Scoring Window (10min) | `88` | `$18.57` | `$4,889.30` | `0.5064%` | `0.1376%` | `0.0052%` | ADA 44, NEO 11, ALGO 7, HYPE 5 | Bitfinex->MEXC 46, MEXC->Bitfinex 28, Bitget->Bitfinex 10 |
| 17 | G3 / Tight Stability Gates | `30` | `$4.18` | `$1,662.00` | `0.2613%` | `0.2542%` | `0.0062%` | ADA 17, ALGO 7, NEO 2, ETH 2 | MEXC->Bitfinex 14, Bitfinex->MEXC 10, OKX->Bitfinex 3 |
| 18 | G3 / Loose Stability Gates | `107` | `$12.95` | `$5,087.48` | `0.3054%` | `0.1249%` | `0.0052%` | ADA 54, HYPE 11, NEO 7, ETH 6 | Bitfinex->MEXC 40, MEXC->Bitfinex 40, Bitget->Bitfinex 17 |
| 19 | G4 / Concentrated (2 active) | `9` | `$2.08` | `$1,049.27` | `0.2013%` | `0.1249%` | `0.0050%` | ADA 5, ETH 3, ZEC 1 | MEXC->Bitfinex 6, Bitfinex->MEXC 3 |
| 20 | G4 / Conservative (3 active) | `35` | `$28.93` | `$2,291.84` | `1.6472%` | `0.3023%` | `0.0050%` | NEO 13, ADA 13, ALGO 4, XLM 2 | Bitfinex->MEXC 18, MEXC->Bitfinex 10, Bitget->Bitfinex 7 |
| 21 | G4 / Neutral (4 active) | `110` | `$22.63` | `$7,582.35` | `0.3856%` | `0.1616%` | `0.0054%` | ADA 53, HYPE 9, NEO 8, ZEC 8 | MEXC->Bitfinex 48, Bitfinex->MEXC 35, Bitget->Bitfinex 21 |
| 22 | G4 / Diverse (6 active) | `126` | `$26.88` | `$9,060.61` | `0.3942%` | `0.1448%` | `0.0054%` | ADA 78, ZEC 9, NEO 8, ALGO 8 | MEXC->Bitfinex 49, Bitfinex->MEXC 41, Bitget->Bitfinex 25 |
| 23 | G4 / Wide (8 active) | `86` | `$19.70` | `$5,967.55` | `0.3559%` | `0.1485%` | `0.0050%` | ADA 52, ALGO 8, NEO 7, HYPE 6 | Bitfinex->MEXC 39, MEXC->Bitfinex 37, Bitget->Bitfinex 7 |
| 24 | G4 / No Auto-Expand | `82` | `$31.86` | `$6,201.85` | `0.7809%` | `0.1696%` | `0.0055%` | ADA 48, NEO 14, XLM 5, AAVE 3 | MEXC->Bitfinex 34, Bitfinex->MEXC 34, Bitget->Bitfinex 11 |
| 25 | G5 / Conservative (Sticky) | `17` | `$2.87` | `$1,484.79` | `0.1809%` | `0.1249%` | `0.0050%` | ADA 9, ALGO 5, ZEC 2, ETH 1 | MEXC->Bitfinex 10, Bitget->Bitfinex 5, Bitfinex->MEXC 1 |
| 26 | G5 / Neutral (Baseline) | `97` | `$13.53` | `$8,602.49` | `0.1617%` | `0.1560%` | `0.0052%` | ADA 49, ALGO 9, ZEC 8, ZRO 7 | MEXC->Bitfinex 43, Bitfinex->MEXC 24, Bitget->Bitfinex 21 |
| 27 | G5 / Aggressive (Rapid Shifts) | `149` | `$20.81` | `$15,080.90` | `0.1395%` | `0.1206%` | `0.0053%` | ADA 97, XLM 10, SOL 8, XRP 8 | MEXC->Bitfinex 84, Bitfinex->MEXC 49, Bitget->Bitfinex 8 |
| 28 | G5 / No Boosts (Pure Score) | `22` | `$5.44` | `$2,578.98` | `0.2054%` | `0.2185%` | `0.0067%` | ADA 11, ZEC 3, ZRO 3, ALGO 3 | MEXC->Bitfinex 10, Bitget->Bitfinex 8, OKX->Bitfinex 4 |
| 29 | G5 / Tight Inventory Drift | `101` | `$16.22` | `$9,109.75` | `0.1677%` | `0.1485%` | `0.0050%` | ADA 69, ALGO 9, HYPE 6, XLM 5 | MEXC->Bitfinex 47, Bitfinex->MEXC 38, Bitget->Bitfinex 13 |
| 30 | G5 / Loose Inventory Drift | `47` | `$8.68` | `$4,239.85` | `0.2130%` | `0.1947%` | `0.0063%` | ADA 23, ALGO 8, ZEC 7, AAVE 3 | MEXC->Bitfinex 17, Bitfinex->MEXC 15, Bitget->Bitfinex 14 |

## Latest Monitor Status

At the latest status tick, every config had `profitable=0` and `executed=0`.

| # | Config | Latest monitor status |
|---:|---|---|
| 1 | G1 / + KuCoin | `2026-07-05 02:30:19`, `low_profit=244`, `slippage_guard=5`, `visible_depth=30`, `book_age_skip=228`; ALGO weak, BCH normal |
| 2 | G1 / All 8 Exchanges | `2026-07-05 02:30:13`, `low_profit=0`, `book_age_skip=12`; LTC weak |
| 3 | G1 / Neutral (Baseline) | `2026-07-05 02:27:17`, `low_profit=0`, `book_age_skip=116`; ALGO weak |
| 4 | G1 / Conservative | `2026-07-05 02:29:58`, `low_profit=223`, `visible_depth=19`, `book_age_skip=138`; ALGO weak, ADA weak, BCH normal |
| 5 | G1 / Aggressive | `2026-07-05 02:30:15`, `low_profit=72`, `book_age_skip=166`; ALGO weak |
| 6 | G1 / + Gate.io | `2026-07-05 02:29:54`, `low_profit=69`, `slippage_guard=10`, `book_age_skip=114`; ALGO weak |
| 7 | G2 / Tiny ($20, 1%) | `2026-07-05 02:29:50`, `low_profit=0`, `book_age_skip=126`; ALGO weak |
| 8 | G2 / Small ($40, 2%) | `2026-07-05 02:29:57`, `low_profit=90`, `book_age_skip=102`; ALGO weak |
| 9 | G2 / Medium-Conservative ($80, 4%) | `2026-07-05 02:29:51`, `low_profit=0`, `book_age_skip=128`; ALGO weak |
| 10 | G2 / Medium-Neutral ($80, 4%) | `2026-07-05 02:30:19`, `low_profit=83`, `slippage_guard=3`, `book_age_skip=194`; ALGO weak |
| 11 | G2 / Medium-Aggressive ($80, 4%) | `2026-07-05 02:29:59`, `low_profit=88`, `book_age_skip=130`; ALGO weak |
| 12 | G2 / Large ($120, 6%) | `2026-07-05 02:30:04`, `low_profit=84`, `slippage_guard=31`, `visible_depth=99`, `book_age_skip=140`; ADA weak, ALGO weak |
| 13 | G3 / Conservative (Strict Scoring) | `2026-07-05 02:30:16`, `low_profit=87`, `slippage_guard=13`, `book_age_skip=174`; ADA weak, ALGO weak, LTC weak |
| 14 | G3 / Neutral (Baseline) | `2026-07-05 02:30:17`, `low_profit=64`, `slippage_guard=13`, `visible_depth=107`, `book_age_skip=183`; ADA weak, ALGO weak, LTC weak |
| 15 | G3 / Aggressive (Permissive Scoring) | `2026-07-05 02:30:12`, `low_profit=55`, `book_age_skip=10`; ADA weak, LTC weak |
| 16 | G3 / Short Scoring Window (10min) | `2026-07-05 02:30:06`, `low_profit=50`, `visible_depth=103`, `book_age_skip=146`; ALGO weak |
| 17 | G3 / Tight Stability Gates | `2026-07-05 02:30:09`, `low_profit=65`, `slippage_guard=4`, `visible_depth=166`, `book_age_skip=161`; ALGO weak, LTC weak |
| 18 | G3 / Loose Stability Gates | `2026-07-05 02:30:05`, `low_profit=67`, `book_age_skip=159`; ALGO weak, LTC weak |
| 19 | G4 / Concentrated (2 active) | `2026-07-05 02:30:12`, `low_profit=140`, `slippage_guard=25`, `visible_depth=147`, `book_age_skip=164`; ADA weak, ALGO weak |
| 20 | G4 / Conservative (3 active) | `2026-07-05 02:30:19`, `low_profit=70`, `slippage_guard=34`, `visible_depth=129`, `book_age_skip=209`; ADA weak, ALGO weak, LTC weak |
| 21 | G4 / Neutral (4 active) | `2026-07-05 02:30:05`, `low_profit=56`, `slippage_guard=21`, `visible_depth=151`, `book_age_skip=177`; ADA weak, ALGO weak, LTC weak |
| 22 | G4 / Diverse (6 active) | `2026-07-05 02:30:15`, `low_profit=55`, `slippage_guard=29`, `visible_depth=146`, `book_age_skip=174`; ADA weak, ALGO weak, LTC weak |
| 23 | G4 / Wide (8 active) | `2026-07-05 02:30:14`, `low_profit=69`, `slippage_guard=29`, `visible_depth=146`, `book_age_skip=235`; ADA weak, ALGO weak |
| 24 | G4 / No Auto-Expand | `2026-07-05 02:30:14`, `low_profit=52`, `slippage_guard=22`, `visible_depth=144`, `book_age_skip=171`; ADA weak, ALGO weak |
| 25 | G5 / Conservative (Sticky) | `2026-07-05 02:30:06`, `low_profit=71`, `slippage_guard=16`, `visible_depth=147`, `book_age_skip=184`; ADA weak, ALGO weak, LTC weak |
| 26 | G5 / Neutral (Baseline) | `2026-07-05 02:29:50`, `low_profit=63`, `visible_depth=77`, `book_age_skip=160`; ADA weak, ALGO weak |
| 27 | G5 / Aggressive (Rapid Shifts) | `2026-07-05 02:29:56`, `low_profit=71`, `visible_depth=35`, `book_age_skip=137`; ALGO weak |
| 28 | G5 / No Boosts (Pure Score) | `2026-07-05 02:30:09`, `low_profit=93`, `slippage_guard=24`, `visible_depth=183`, `book_age_skip=171`; ADA weak, ALGO weak |
| 29 | G5 / Tight Inventory Drift | `2026-07-05 02:29:53`, `low_profit=66`, `slippage_guard=4`, `visible_depth=122`, `book_age_skip=164`; ADA weak, ALGO weak |
| 30 | G5 / Loose Inventory Drift | `2026-07-05 02:29:55`, `low_profit=39`, `visible_depth=120`, `book_age_skip=130`; ALGO weak |

## Portfolio And Wallet Display Notes

Aggregate latest balance snapshots:

| Metric | Value |
|---|---:|
| Sum `total` | `$93,334.00` |
| Sum `hedged` | `$93,049.00` |
| Sum `accounting` | `$88,868.00` |
| Sum `drift` | `$2,732.10` |
| Sum hedge PnL | `$-283.27` |
| Sum futures fees | `$417.97` |

`Group 1 / Neutral (Baseline)` reports `total=$1,452` on `$1,000` capital, but its balance snapshot has no `accounting` or `drift` fields. Given its `1,551` hedge errors and testnet mode, this config's wallet total should not be trusted as realized performance.

For all configs, `total` and `hedged` remain mark-to-market wallet values. `accounting`, `spot_net`, `hedge_net`, and `net` are the useful strategy-performance fields.

## Anomaly Events

Important anomaly entries near the end:

```text
2026-07-05 02:27:41 [WARNING] [Anomaly] EMERGENCY: EMERGENCY (layer_a_realized): drawdown 27.77% >= threshold 15.0% — realized capital drop — actual locked-in loss
2026-07-05 02:27:42 [WARNING] [Group 1: $1k — Architecture & Exchange Ablations][Neutral (Baseline)] [Monitor] Anomaly protection activated, trading paused
```

The emergency claims a realized capital drawdown, not just mark-to-market drift. It occurs at the same time as the noisy Binance futures testnet hedge config, so the first investigation target is G1 / Neutral testnet accounting and hedge state.

## Group Observations

### Group 1 - Architecture & Exchange Ablations

- Only `+ Gate.io` is positive: `+$4.37`.
- `Neutral (Baseline)` is not reliable because it uses Binance futures testnet and produced all `1,551` config errors.
- `+ KuCoin` and `All 8 Exchanges` have very large `sz0`, `book_age`, and rebalance blockers.
- `Conservative` has the largest `pos_cap` count in the group: `1,175,532`.

### Group 2 - Trade Size & Threshold Sweep

- All six `$2k` configs are negative.
- `Small ($40, 2%)` and `Medium-Neutral ($80, 4%)` are closest to break-even, but still lose after hedge fees.
- `Tiny ($20, 1%)` is too small after hedging: gross PnL `$0.37`, hedge net `-$7.45`.
- `Large ($120, 6%)` has the highest warning count in the whole run: `2,169`, mostly BNB top-up failures.

### Group 3 - Discovery & Scoring Tuning

- `Conservative (Strict Scoring)` is the best Group 3 result: `+$12.23`.
- `Neutral (Baseline)` is also positive: `+$4.53`.
- `Short Scoring Window`, `Tight Stability`, `Loose Stability`, and `Aggressive` are all negative after hedge fees.
- `Short Scoring Window` has the worst Group 3 net: `-$15.06`, driven by `-$28.22` hedge net.

### Group 4 - Symbol Count & Diversification

- Group 4 remains the best group.
- Positive configs: `Conservative (3 active)`, `No Auto-Expand`, and `Diverse (6 active)`.
- `Conservative (3 active)` is the best overall result: `+$13.30`.
- `Diverse` and `Wide` still have large positive drift (`+$210.74`, `+$181.96`), so wallet total can look better than realized net.

### Group 5 - Capital Allocation & Routing

- All six `$5k` configs are negative.
- Larger notional amplifies hedge fee drag.
- Worst config overall is `Loose Inventory Drift`: `-$16.71`.
- `Aggressive (Rapid Shifts)` made `+$18.20` spot net but paid `-$34.25` hedge net.
- `$5k` configs are not ready to scale.

## Likely Root Causes

1. Hedge fee drag is structurally too high for the current realized spot edge.
   Futures fees are `$417.97`; hedge funding is only `+$6.13`.

2. Hedge churn is still too high.
   The strategy is paying more to maintain neutrality than it earns from most spot opportunities.

3. BNB reserve/top-up simulation is not stable.
   `FUTURES_BNB_TOPUP_SKIPPED` dominates warnings. Many hedge fees likely miss the intended BNB discount.

4. MEXC depth websocket behavior is unhealthy.
   The repeated no-initial-depth reconnects are a major source of warning volume and likely contribute to book/depth skips.

5. Book age is a dominant blocker.
   Aggregate `book_age` is `13,211,764`. End-of-run monitors also show `book_age_skip` in every config.

6. Inventory and position constraints are still fighting the opportunity stream.
   Aggregate `sz0` is `19,033,087` and `pos_cap` is `12,279,249`.

7. The testnet hedge config should not be used to judge live readiness.
   G1 / Neutral has testnet-specific Binance futures errors, missing accounting fields in balance output, and triggered anomaly protection.

## Recommendations

1. Do not scale capital based on these results.
   The strategy is still negative after realistic hedge fees.

2. Treat G4 / Conservative and G3 / Conservative as the current best candidates.
   They are the only strong positive results and have better realized/accounting behavior than most configs.

3. Disable or isolate the G1 / Neutral testnet hedge config for normal batch tests.
   It is useful for futures integration diagnostics, but it pollutes error totals and anomaly state.

4. Reduce hedge churn before tuning more spot scoring.
   The spot side already finds gross edges; the hedge side is where the loss is coming from.

5. Fix BNB reserve/top-up behavior or reduce its warning spam.
   The warning count is too high, and the fee discount path may not be operating as intended.

6. Investigate MEXC depth reconnect behavior separately.
   If MEXC cannot provide stable initial depth, it should be rate-limited, partially disabled, or handled with less noisy reconnect logging.

7. Keep using `accounting`/session net as the performance source of truth.
   Do not trust `total`/wallet portfolio as realized PnL while drift is this large.

8. Consider fewer configs or a larger VPS for latency-sensitive tests.
   The current 1 vCPU/2GB box can run the batch, but heap near `1.38GB` and p95 sweep spikes above `3s` are not comfortable.

## Session Work Notes

- Parsed the continuation log deeply.
- Updated this Session #35 file with cumulative details through `2026-07-05 02:30:21`.
- No code or config changes were made.
- No tests were run because this was a documentation/log-audit task.
- No commit was made.
