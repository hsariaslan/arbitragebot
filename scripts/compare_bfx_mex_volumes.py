"""
For the 35 hedgeable Bitfinex+MEXC symbols, fetch 24h and 30d USD volumes
on both exchanges side-by-side.

24h volume: Bitfinex /v2/tickers, MEXC /api/v3/ticker/24hr
30d volume: aggregated from daily candles
  - Bitfinex /v2/candles/trade:1D:t<SYM>/hist?limit=30
  - MEXC /api/v3/klines?symbol=<SYM>&interval=1d&limit=30

Bitfinex symbol form: tBASEUST or tBASEUSD (some bases use colon, e.g. t1INCH:UST).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# 35 hedgeable Bitfinex+MEXC symbols (32 already in config + 3 new)
SYMBOLS = [
    "AAVEUSDT", "ADAUSDT", "APTUSDT", "ARBUSDT", "AVAXUSDT", "BTCUSDT",
    "CHZUSDT", "CRVUSDT", "DOGEUSDT", "DOTUSDT", "EIGENUSDT", "ENAUSDT",
    "ETCUSDT", "ETHUSDT", "FILUSDT", "HYPEUSDT", "JUPUSDT", "LDOUSDT",
    "LINKUSDT", "LTCUSDT", "NEARUSDT", "PEPEUSDT", "POLUSDT", "SHIBUSDT",
    "SOLUSDT", "SUIUSDT", "TONUSDT", "TRXUSDT", "UNIUSDT", "XLMUSDT",
    "XRPUSDT", "ZECUSDT", "XMRUSDT", "ZROUSDT", "NEOUSDT",
]

UA = {"User-Agent": "ArbitrageBot-VolCompare/1.0"}


def _fetch_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _bfx_symbol_for(base: str) -> list[str]:
    """Return candidate Bitfinex tickers for a given base. Tries UST then USD,
    plus colon-form for long bases."""
    candidates = []
    if len(base) > 3:
        candidates.extend([f"t{base}:UST", f"t{base}:USD"])
    candidates.extend([f"t{base}UST", f"t{base}USD"])
    return candidates


def fetch_bitfinex_24h() -> dict[str, tuple[float, str]]:
    """Return {pair_USDT: (usd_vol_24h, bfx_ticker)}.

    Uses the bulk tickers endpoint. We map any tBASEUST/tBASEUSD → BASEUSDT,
    keeping the larger-volume variant.
    """
    tickers = _fetch_json("https://api-pub.bitfinex.com/v2/tickers?symbols=ALL")
    out: dict[str, tuple[float, str]] = {}
    for row in tickers:
        if not isinstance(row, list) or not row:
            continue
        sym = row[0]
        if not isinstance(sym, str) or not sym.startswith("t"):
            continue
        body = sym[1:].replace(":", "")
        if body.endswith("UST"):
            base = body[:-3]
        elif body.endswith("USD"):
            base = body[:-3]
        else:
            continue
        try:
            volume = float(row[8])
            last_price = float(row[7])
        except (TypeError, ValueError, IndexError):
            continue
        usd_volume = volume * last_price
        normalized = f"{base}USDT"
        prev = out.get(normalized)
        if prev is None or usd_volume > prev[0]:
            out[normalized] = (usd_volume, sym)
    return out


def fetch_mexc_24h() -> dict[str, float]:
    tickers = _fetch_json("https://api.mexc.com/api/v3/ticker/24hr")
    out: dict[str, float] = {}
    for row in tickers:
        sym = row.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            out[sym] = float(row.get("quoteVolume", 0))
        except (TypeError, ValueError):
            pass
    return out


def fetch_bfx_30d(bfx_ticker: str) -> float:
    """Sum 30d USD volume from daily candles. Candle layout:
    [MTS, OPEN, CLOSE, HIGH, LOW, VOLUME]   (volume in base units)"""
    url = f"https://api-pub.bitfinex.com/v2/candles/trade:1D:{bfx_ticker}/hist?limit=30"
    try:
        candles = _fetch_json(url)
    except Exception:
        return 0.0
    if not isinstance(candles, list):
        return 0.0
    total = 0.0
    for c in candles:
        try:
            close = float(c[2])
            vol = float(c[5])
        except (TypeError, ValueError, IndexError):
            continue
        total += close * vol
    return total


def fetch_mexc_30d(symbol: str) -> float:
    """Sum quote volume across last 30 daily candles."""
    url = f"https://api.mexc.com/api/v3/klines?symbol={symbol}&interval=1d&limit=30"
    try:
        candles = _fetch_json(url)
    except Exception:
        return 0.0
    if not isinstance(candles, list):
        return 0.0
    total = 0.0
    for c in candles:
        try:
            # [openTime, open, high, low, close, volume, closeTime, quoteVolume, ...]
            total += float(c[7])
        except (TypeError, ValueError, IndexError):
            continue
    return total


def main() -> int:
    print(f"Fetching 24h volumes for {len(SYMBOLS)} symbols...")
    bfx_24h = fetch_bitfinex_24h()
    mex_24h = fetch_mexc_24h()
    print(f"  Bitfinex: {len(bfx_24h)} pairs, MEXC: {len(mex_24h)} pairs")

    print(f"Fetching 30d candles in parallel...")
    bfx_30d: dict[str, float] = {}
    mex_30d: dict[str, float] = {}

    # Resolve Bitfinex tickers from the 24h map
    bfx_ticker_for: dict[str, str] = {s: bfx_24h[s][1] for s in SYMBOLS if s in bfx_24h}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {}
        for s in SYMBOLS:
            if s in bfx_ticker_for:
                futs[pool.submit(fetch_bfx_30d, bfx_ticker_for[s])] = ("bfx", s)
            if s in mex_24h:
                futs[pool.submit(fetch_mexc_30d, s)] = ("mex", s)
        for fut in as_completed(futs):
            kind, s = futs[fut]
            try:
                v = fut.result()
            except Exception:
                v = 0.0
            (bfx_30d if kind == "bfx" else mex_30d)[s] = v

    # Build rows
    rows = []
    for s in SYMBOLS:
        b24 = bfx_24h.get(s, (0.0, ""))[0]
        m24 = mex_24h.get(s, 0.0)
        b30 = bfx_30d.get(s, 0.0)
        m30 = mex_30d.get(s, 0.0)
        rows.append({
            "symbol": s,
            "bfx_24h": b24, "mex_24h": m24, "comb_24h": b24 + m24,
            "bfx_30d": b30, "mex_30d": m30, "comb_30d": b30 + m30,
        })
    rows.sort(key=lambda r: r["comb_30d"], reverse=True)

    print()
    print("=" * 132)
    print(f"{'Symbol':<10} {'BFX 24h $':>16} {'MEX 24h $':>16} {'Comb 24h $':>16}    "
          f"{'BFX 30d $':>18} {'MEX 30d $':>18} {'Comb 30d $':>18}")
    print("-" * 132)
    for r in rows:
        print(
            f"{r['symbol']:<10} "
            f"{r['bfx_24h']:>16,.0f} {r['mex_24h']:>16,.0f} {r['comb_24h']:>16,.0f}    "
            f"{r['bfx_30d']:>18,.0f} {r['mex_30d']:>18,.0f} {r['comb_30d']:>18,.0f}"
        )
    print("=" * 132)

    out_path = PROJECT_ROOT / "state" / "bfx_mex_volumes.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
