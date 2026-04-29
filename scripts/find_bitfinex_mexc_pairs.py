"""
Find all spot symbols that trade on BOTH Bitfinex AND MEXC.

Use case: when the operator pins the bot to Bitfinex(buyer)+MEXC(seller)
only, every active symbol must exist on both. This script lists all
common symbols, sorted by combined 24h USD volume, and flags which ones
are missing from `config.py:SYMBOLS`.

Public endpoints, no auth needed:
  Bitfinex pairs:   https://api-pub.bitfinex.com/v2/conf/pub:list:pair:exchange
  Bitfinex tickers: https://api-pub.bitfinex.com/v2/tickers?symbols=ALL
  MEXC info:        https://api.mexc.com/api/v3/exchangeInfo
  MEXC tickers:     https://api.mexc.com/api/v3/ticker/24hr

Bitfinex quirks:
- USDT pairs are listed as `BASEUST` not `BASEUSDT` (e.g. BTCUST).
- Some pairs use USD instead of UST and we accept both as the USDT
  equivalent (BTCUSD == BTCUSDT for arbitrage purposes within Bitfinex).
- Tickers come back as `tBASEUST` / `tBASEUSD` with the `t` prefix.

Usage:
    python scripts/find_bitfinex_mexc_pairs.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Currently configured symbols in config.py
def _load_current_symbols() -> list[str]:
    text = (PROJECT_ROOT / "config.py").read_text()
    m = re.search(r"^SYMBOLS:.*?\n\]", text, re.S | re.M)
    if not m:
        return []
    return re.findall(r'"([A-Z0-9]+USDT)"', m.group(0))


def _fetch_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "ArbitrageBot-Pairs/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_bitfinex_pairs_with_volume() -> dict[str, float]:
    """Return {base_symbol_normalized: usd_volume_24h} for Bitfinex.

    Accepts both UST (BTCUST) and USD (BTCUSD) pairs and normalizes the
    base to look like a USDT pair (BTC → BTCUSDT). When both exist,
    keeps the larger volume.
    """
    # Tickers contain USD volume; pair list is just for sanity check
    tickers = _fetch_json("https://api-pub.bitfinex.com/v2/tickers?symbols=ALL")
    out: dict[str, float] = {}
    for row in tickers:
        if not isinstance(row, list) or not row:
            continue
        sym = row[0]
        if not isinstance(sym, str) or not sym.startswith("t"):
            continue
        # tBASEUST or tBASEUSD or tBASE:UST (some have colons for long bases)
        body = sym[1:].replace(":", "")
        base = None
        if body.endswith("UST"):
            base = body[:-3]
        elif body.endswith("USD"):
            base = body[:-3]
        if not base:
            continue
        # row layout for tickers: [SYM, BID, BID_SIZE, ASK, ASK_SIZE,
        #                          DAILY_CHANGE, DAILY_CHANGE_REL,
        #                          LAST_PRICE, VOLUME, HIGH, LOW]
        try:
            volume = float(row[8])
            last_price = float(row[7])
        except (TypeError, ValueError, IndexError):
            continue
        usd_volume = volume * last_price
        normalized = f"{base}USDT"
        # Keep the larger volume across UST/USD variants
        if usd_volume > out.get(normalized, 0.0):
            out[normalized] = usd_volume
    return out


def fetch_mexc_pairs_with_volume() -> dict[str, float]:
    """Return {symbol: usd_volume_24h} for MEXC USDT spot pairs."""
    tickers = _fetch_json("https://api.mexc.com/api/v3/ticker/24hr")
    out: dict[str, float] = {}
    for row in tickers:
        sym = row.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            quote_volume = float(row.get("quoteVolume", 0))
        except (TypeError, ValueError):
            continue
        out[sym] = quote_volume  # quoteVolume on MEXC is already in USDT
    return out


def main() -> int:
    print("Fetching Bitfinex pairs+volume...")
    bfx = fetch_bitfinex_pairs_with_volume()
    print(f"  {len(bfx)} USD/UST pairs on Bitfinex")

    print("Fetching MEXC pairs+volume...")
    mex = fetch_mexc_pairs_with_volume()
    print(f"  {len(mex)} USDT pairs on MEXC")

    common = set(bfx.keys()) & set(mex.keys())
    print(f"\nCommon symbols on BOTH exchanges: {len(common)}")

    current = set(_load_current_symbols())
    missing = sorted(common - current)
    already = sorted(common & current)
    not_on_bfx = sorted(current - set(bfx.keys()))
    not_on_mex = sorted(current - set(mex.keys()))

    # Build rows
    rows = []
    for sym in common:
        rows.append({
            "symbol": sym,
            "bfx_vol_usd": bfx.get(sym, 0),
            "mex_vol_usd": mex.get(sym, 0),
            "combined_vol_usd": bfx.get(sym, 0) + mex.get(sym, 0),
            "in_config": sym in current,
        })
    rows.sort(key=lambda r: r["combined_vol_usd"], reverse=True)

    print()
    print("=" * 100)
    print(f"{'Symbol':<14} {'In config?':<10} {'Bitfinex 24h $':>18} {'MEXC 24h $':>18} {'Combined $':>18}")
    print("-" * 100)
    for r in rows:
        flag = "✓" if r["in_config"] else "MISSING"
        print(
            f"{r['symbol']:<14} {flag:<10} "
            f"{r['bfx_vol_usd']:>18,.0f} "
            f"{r['mex_vol_usd']:>18,.0f} "
            f"{r['combined_vol_usd']:>18,.0f}"
        )
    print("=" * 100)

    print(f"\nSummary:")
    print(f"  Common symbols (both exchanges): {len(common)}")
    print(f"  Already in config.py SYMBOLS: {len(already)}")
    print(f"  MISSING from config.py (could be added): {len(missing)}")
    print(f"  In config but NOT on Bitfinex: {len(not_on_bfx)}")
    print(f"    {not_on_bfx}")
    print(f"  In config but NOT on MEXC: {len(not_on_mex)}")
    print(f"    {not_on_mex}")

    if missing:
        print(f"\n=== TOP 30 MISSING SYMBOLS BY COMBINED VOLUME ===")
        miss_rows = [r for r in rows if not r["in_config"]][:30]
        for r in miss_rows:
            print(
                f"  {r['symbol']:<14} "
                f"BFX ${r['bfx_vol_usd']:>15,.0f}  "
                f"MEX ${r['mex_vol_usd']:>15,.0f}  "
                f"Total ${r['combined_vol_usd']:>15,.0f}"
            )

    # Persist results for later analysis
    out_path = PROJECT_ROOT / "state" / "bitfinex_mexc_pairs.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "common_count": len(common),
        "in_config": already,
        "missing_from_config": missing,
        "in_config_not_on_bitfinex": not_on_bfx,
        "in_config_not_on_mexc": not_on_mex,
        "rows": rows,
    }, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
