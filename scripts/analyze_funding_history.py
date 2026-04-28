"""
Funding rate history analyzer for Binance USDⓈ-M perpetual futures.

Pulls ~90 days of funding history per symbol, computes statistics
(avg, median, p5/p95, worst spike, period interval), and persists
results to state/funding_history.json for the bot's funding-aware
scoring layer.

Designed to be runnable standalone (no bot dependencies) and also
schedulable as a weekly cron once the hedging engine is live.

Usage:
    python scripts/analyze_funding_history.py [--days 90] [--out state/funding_history.json]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# 60 spot symbols the bot trades. PEPE/SHIB/FLOKI use the 1000X prefix
# on Binance Futures because the unit price is too small.
SPOT_SYMBOLS: list[str] = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT",
    "AVAXUSDT", "LINKUSDT", "POLUSDT", "DOTUSDT", "NEARUSDT", "SUIUSDT", "APTUSDT", "TRXUSDT",
    "ARBUSDT", "OPUSDT", "FILUSDT", "ATOMUSDT", "INJUSDT",
    "AAVEUSDT", "BCHUSDT", "PEPEUSDT", "ZECUSDT", "LTCUSDT", "HYPEUSDT", "XLMUSDT",
    "UNIUSDT", "ENAUSDT", "SNXUSDT", "TONUSDT", "SHIBUSDT", "ICPUSDT", "ETCUSDT",
    "TRUMPUSDT", "HBARUSDT", "CHZUSDT", "AXSUSDT", "PENGUUSDT", "WLDUSDT", "WIFUSDT",
    "RENDERUSDT", "ONDOUSDT", "STRKUSDT", "CRVUSDT", "ARUSDT", "FETUSDT", "LDOUSDT",
    "ALGOUSDT", "EIGENUSDT", "PENDLEUSDT", "APEUSDT", "TIAUSDT", "FLOKIUSDT", "WUSDT",
    "GRTUSDT", "ORDIUSDT", "JUPUSDT", "COMPUSDT", "DYDXUSDT",
]

# Spot symbol → (futures symbol, contract multiplier).
# For 1000X contracts: spot price × multiplier = futures quoted price.
# Quantity: spot_qty / multiplier = futures contracts.
FUTURES_SYMBOL_OVERRIDE: dict[str, tuple[str, int]] = {
    "PEPEUSDT":  ("1000PEPEUSDT",  1000),
    "SHIBUSDT":  ("1000SHIBUSDT",  1000),
    "FLOKIUSDT": ("1000FLOKIUSDT", 1000),
}

BINANCE_FUNDING_RATE_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


def get_futures_symbol(spot_symbol: str) -> tuple[str, int]:
    """Return (futures_symbol, contract_multiplier) for a spot symbol."""
    return FUTURES_SYMBOL_OVERRIDE.get(spot_symbol, (spot_symbol, 1))


def fetch_funding_history(futures_symbol: str, limit: int = 1000) -> list[dict]:
    """Fetch up to `limit` historical funding records for a symbol.

    Binance returns the most recent N records. limit max=1000 per call.
    No API key required.
    """
    url = f"{BINANCE_FUNDING_RATE_URL}?symbol={futures_symbol}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "ArbitrageBot-Analyzer/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def compute_stats(records: list[dict], days_filter: int | None = None) -> dict:
    """Compute funding rate statistics from raw records.

    If days_filter is given, only consider records from the last N days.
    """
    if not records:
        return {"error": "no records"}

    now_ms = time.time() * 1000
    cutoff_ms = now_ms - (days_filter * 24 * 3600 * 1000) if days_filter else 0

    rates = []
    for r in records:
        if r["fundingTime"] < cutoff_ms:
            continue
        rates.append(float(r["fundingRate"]))

    if len(rates) < 2:
        return {"error": f"insufficient data ({len(rates)} records after filter)"}

    # Detect funding interval from timestamps
    times = sorted([r["fundingTime"] for r in records])
    if len(times) >= 2:
        intervals_ms = [times[i+1] - times[i] for i in range(len(times)-1)]
        # Mode of intervals (in hours, rounded)
        interval_hours = round(statistics.median(intervals_ms) / 3600 / 1000)
    else:
        interval_hours = 8  # default

    rates_sorted = sorted(rates)
    n = len(rates_sorted)
    p5 = rates_sorted[max(0, int(n * 0.05))]
    p95 = rates_sorted[min(n - 1, int(n * 0.95))]

    avg = statistics.mean(rates)
    median = statistics.median(rates)
    worst = min(rates)  # most negative = worst for shorts
    best = max(rates)   # most positive = best for shorts

    # Annualized cost/income for a SHORT position
    # short receives funding when positive, pays when negative
    # so annualized_for_short = avg_rate * periods_per_year
    periods_per_day = 24 / interval_hours
    periods_per_year = periods_per_day * 365
    annualized_short_pct = avg * periods_per_year * 100

    # Daily cost/income for short on $1000 notional
    daily_per_1000_short = avg * periods_per_day * 1000

    return {
        "samples": n,
        "interval_hours": interval_hours,
        "avg_pct_per_period": avg * 100,
        "median_pct_per_period": median * 100,
        "p5_pct_per_period": p5 * 100,
        "p95_pct_per_period": p95 * 100,
        "worst_pct_per_period": worst * 100,
        "best_pct_per_period": best * 100,
        "annualized_short_pct": annualized_short_pct,
        "daily_per_1000_short_usd": daily_per_1000_short,
    }


def classify(stats: dict) -> str:
    """Hedge-friendliness classification.

    Based on average funding rate from the short's perspective:
      - Very Good: avg > +0.01%/period (short earns >10%/yr)
      - Good: avg > 0
      - Neutral: avg in [-0.005%, 0]
      - Caution: avg in [-0.01%, -0.005%]
      - Bad: avg in [-0.05%, -0.01%]
      - Toxic: avg < -0.05%
    """
    if "error" in stats:
        return "?"
    avg = stats["avg_pct_per_period"]
    if avg > 0.01:
        return "VeryGood"
    if avg > 0:
        return "Good"
    if avg >= -0.005:
        return "Neutral"
    if avg >= -0.01:
        return "Caution"
    if avg >= -0.05:
        return "Bad"
    return "Toxic"


def main() -> int:
    ap = argparse.ArgumentParser(description="Binance Futures funding rate history analyzer")
    ap.add_argument("--days", type=int, default=90, help="Days of history to analyze (default 90)")
    ap.add_argument("--out", type=str, default="state/funding_history.json", help="Output JSON path")
    ap.add_argument("--limit", type=int, default=1000, help="Max records per fetch (Binance max 1000)")
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Analyzing {len(SPOT_SYMBOLS)} symbols, {args.days}-day window...\n")
    results: dict[str, dict] = {}
    failed: list[str] = []

    for i, spot in enumerate(SPOT_SYMBOLS, 1):
        futures, mult = get_futures_symbol(spot)
        try:
            records = fetch_funding_history(futures, limit=args.limit)
        except urllib.error.HTTPError as e:
            print(f"  [{i:2d}/{len(SPOT_SYMBOLS)}] {spot:>14s} → {futures:>18s}  HTTP {e.code} ({e.reason})")
            failed.append(spot)
            results[spot] = {"futures_symbol": futures, "contract_multiplier": mult, "error": f"HTTP {e.code}"}
            continue
        except Exception as e:
            print(f"  [{i:2d}/{len(SPOT_SYMBOLS)}] {spot:>14s} → {futures:>18s}  ERROR: {e}")
            failed.append(spot)
            results[spot] = {"futures_symbol": futures, "contract_multiplier": mult, "error": str(e)}
            continue

        stats = compute_stats(records, days_filter=args.days)
        results[spot] = {
            "futures_symbol": futures,
            "contract_multiplier": mult,
            **stats,
            "classification": classify(stats),
        }
        if "error" in stats:
            print(f"  [{i:2d}/{len(SPOT_SYMBOLS)}] {spot:>14s} → {futures:>18s}  {stats['error']}")
        else:
            print(
                f"  [{i:2d}/{len(SPOT_SYMBOLS)}] {spot:>14s} → {futures:>18s}  "
                f"n={stats['samples']:>4d} interval={stats['interval_hours']}h "
                f"avg={stats['avg_pct_per_period']:+.4f}% "
                f"ann_short={stats['annualized_short_pct']:+7.2f}%/yr "
                f"[{classify(stats)}]"
            )

        # Be polite — Binance allows 2400 weight/min, fundingRate is weight 1.
        # 60 calls in ~6 seconds is fine but space them slightly.
        time.sleep(0.1)

    # Persist
    output = {
        "generated_at": int(time.time()),
        "days_window": args.days,
        "symbols": results,
    }
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {out_path}")

    if failed:
        print(f"\n{len(failed)} symbol(s) failed: {', '.join(failed)}")

    # Print summary table sorted by avg (best for shorts first)
    print_summary_table(results)
    return 0


def print_summary_table(results: dict[str, dict]) -> None:
    rows = []
    for spot, r in results.items():
        if "error" in r:
            continue
        rows.append((spot, r))
    rows.sort(key=lambda x: x[1]["avg_pct_per_period"], reverse=True)

    print()
    print("=" * 122)
    print(
        f"{'Symbol':<14} {'Futures':<18} {'Mult':>5} {'Int':>4} {'Samples':>8} "
        f"{'Avg%/per':>10} {'Med%/per':>10} {'P5%':>10} {'P95%':>10} {'Worst%':>10} "
        f"{'Ann.%/yr':>10} {'Class':>10}"
    )
    print("-" * 122)
    for spot, r in rows:
        print(
            f"{spot:<14} {r['futures_symbol']:<18} {r['contract_multiplier']:>5} "
            f"{r['interval_hours']:>3}h {r['samples']:>8d} "
            f"{r['avg_pct_per_period']:>+10.4f} "
            f"{r['median_pct_per_period']:>+10.4f} "
            f"{r['p5_pct_per_period']:>+10.4f} "
            f"{r['p95_pct_per_period']:>+10.4f} "
            f"{r['worst_pct_per_period']:>+10.4f} "
            f"{r['annualized_short_pct']:>+10.2f} "
            f"{r['classification']:>10}"
        )
    print("=" * 122)
    print()
    print(f"Total: {len(rows)} symbols analyzed.")
    by_class: dict[str, int] = {}
    for _, r in rows:
        c = r["classification"]
        by_class[c] = by_class.get(c, 0) + 1
    print(f"Classification: " + ", ".join(f"{k}={v}" for k, v in sorted(by_class.items())))


if __name__ == "__main__":
    sys.exit(main())
