"""On-demand 24h USD volume fetcher for all 9 exchanges.

Used by the Fee Management tab in the dashboard: operator clicks "Fetch 24h
Volumes" → backend calls `fetch_all_24h_volumes()` → returns one dict per
exchange so the operator can decide which (exchange, symbol) combos to
disable via the per-symbol blocklist.

All endpoints are public, no auth needed. Runs concurrently in a thread
pool to keep the WebSocket loop responsive.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

UA = {"User-Agent": "ArbitrageBot-VolFetch/1.0"}


def _fetch(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── Per-exchange fetchers ─────────────────────────────────────────────
# Each returns {symbol_normalized_to_BASEUSDT: usd_volume_24h}.

def _binance() -> dict[str, float]:
    rows = _fetch("https://api.binance.com/api/v3/ticker/24hr")
    out: dict[str, float] = {}
    for r in rows:
        sym = r.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            out[sym] = float(r.get("quoteVolume", 0))
        except (TypeError, ValueError):
            pass
    return out


def _okx() -> dict[str, float]:
    data = _fetch("https://www.okx.com/api/v5/market/tickers?instType=SPOT")
    out: dict[str, float] = {}
    for r in data.get("data", []):
        inst = r.get("instId", "")  # "BTC-USDT"
        if not inst.endswith("-USDT"):
            continue
        sym = inst.replace("-", "")
        try:
            # volCcy24h is in quote currency (USDT). Some endpoints use volCcyQuote.
            out[sym] = float(r.get("volCcy24h", 0))
        except (TypeError, ValueError):
            pass
    return out


def _bybit() -> dict[str, float]:
    data = _fetch("https://api.bybit.com/v5/market/tickers?category=spot")
    out: dict[str, float] = {}
    for r in data.get("result", {}).get("list", []):
        sym = r.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            # turnover24h is in quote currency
            out[sym] = float(r.get("turnover24h", 0))
        except (TypeError, ValueError):
            pass
    return out


def _mexc() -> dict[str, float]:
    rows = _fetch("https://api.mexc.com/api/v3/ticker/24hr")
    out: dict[str, float] = {}
    for r in rows:
        sym = r.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            out[sym] = float(r.get("quoteVolume", 0))
        except (TypeError, ValueError):
            pass
    return out


def _bitget() -> dict[str, float]:
    data = _fetch("https://api.bitget.com/api/v2/spot/market/tickers")
    out: dict[str, float] = {}
    for r in data.get("data", []):
        sym = r.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            # usdtVolume = base*price ≈ USDT turnover
            out[sym] = float(r.get("usdtVolume", 0) or r.get("quoteVolume", 0))
        except (TypeError, ValueError):
            pass
    return out


def _kucoin() -> dict[str, float]:
    data = _fetch("https://api.kucoin.com/api/v1/market/allTickers")
    out: dict[str, float] = {}
    for r in data.get("data", {}).get("ticker", []):
        sym = r.get("symbol", "")  # "BTC-USDT"
        if not sym.endswith("-USDT"):
            continue
        normalized = sym.replace("-", "")
        try:
            # volValue = quote currency (USDT) volume
            out[normalized] = float(r.get("volValue", 0))
        except (TypeError, ValueError):
            pass
    return out


def _gateio() -> dict[str, float]:
    rows = _fetch("https://api.gateio.ws/api/v4/spot/tickers")
    out: dict[str, float] = {}
    for r in rows:
        sym = r.get("currency_pair", "")  # "BTC_USDT"
        if not sym.endswith("_USDT"):
            continue
        normalized = sym.replace("_", "")
        try:
            out[normalized] = float(r.get("quote_volume", 0))
        except (TypeError, ValueError):
            pass
    return out


def _pionex() -> dict[str, float]:
    """Pionex doesn't expose 24h ticker volume on a stable public endpoint
    we trust here. Return empty dict so the UI shows N/A — operator can
    skip Pionex for the volume-based blocklist or fall back to manual data.
    """
    try:
        data = _fetch("https://api.pionex.com/api/v1/market/tickers")
    except Exception:
        return {}
    out: dict[str, float] = {}
    # Try a generic shape: {data: {tickers: [{symbol: "BTC_USDT", amount: "..."}]}}
    tickers = data.get("data", {}).get("tickers", [])
    for r in tickers:
        sym = r.get("symbol", "")
        if not sym.endswith("_USDT"):
            continue
        normalized = sym.replace("_", "")
        # `amount` is quote volume on Pionex
        try:
            out[normalized] = float(r.get("amount", 0))
        except (TypeError, ValueError):
            pass
    return out


def _bitfinex() -> dict[str, float]:
    """Bitfinex uses tBASEUST or tBASEUSD; normalize to BASEUSDT keeping
    larger-volume variant."""
    rows = _fetch("https://api-pub.bitfinex.com/v2/tickers?symbols=ALL")
    out: dict[str, float] = {}
    for row in rows:
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
        if usd_volume > out.get(normalized, 0.0):
            out[normalized] = usd_volume
    return out


_FETCHERS = {
    "Binance": _binance,
    "OKX": _okx,
    "Bybit": _bybit,
    "MEXC": _mexc,
    "Bitget": _bitget,
    "KuCoin": _kucoin,
    "Gate.io": _gateio,
    "Pionex": _pionex,
    "Bitfinex": _bitfinex,
}


# ── Public API ────────────────────────────────────────────────────────

async def fetch_all_24h_volumes(
    exchanges: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    """Fetch 24h USD volumes for all (or specified) exchanges in parallel.

    Returns: {exchange: {symbol: usd_volume_24h}}.
    Failed exchanges return empty dict and are logged.
    """
    targets = exchanges or list(_FETCHERS.keys())
    loop = asyncio.get_running_loop()

    def run_one(ex: str) -> tuple[str, dict[str, float]]:
        try:
            return ex, _FETCHERS[ex]()
        except Exception as e:
            logger.warning(f"[VolumeFetch] {ex} failed: {e}")
            return ex, {}

    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        tasks = [
            loop.run_in_executor(pool, run_one, ex)
            for ex in targets
            if ex in _FETCHERS
        ]
        results = await asyncio.gather(*tasks)

    return {ex: vols for ex, vols in results}
