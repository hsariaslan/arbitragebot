"""
Standalone test for BinanceFuturesExecutor (Phase B).

Verifies the executor against Binance Futures testnet without involving
the rest of the bot. Test flow:

  1. Connect, log account balance + check credentials
  2. Set isolated margin + 1× leverage on BTCUSDT
  3. Open a small short hedge (~$15 notional, well above $5 min)
  4. Verify position appears in get_position
  5. Verify position appears in get_all_positions
  6. Close the position via close_position (reduceOnly)
  7. Verify position is now flat

Usage:
    BINANCE_FUTURES_TESTNET_API_KEY=... \
    BINANCE_FUTURES_TESTNET_API_SECRET=... \
    python scripts/test_futures_executor.py [--symbol BTCUSDT] [--notional 15]

Sign up for testnet credentials at https://testnet.binancefuture.com.
The testnet provides 100,000 USDT free starting balance.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Make the project root importable when run from anywhere
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_env() -> None:
    """Load .env from project root BEFORE importing config (which validates at import).

    Mirrors run.py's load_env(). Skips lines that are blank, comments, or
    malformed. Uses setdefault so real env vars take priority.
    """
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_env()

from executors.binance_futures_exec import BinanceFuturesExecutor  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
log = logging.getLogger("test_futures")


async def run(symbol: str, notional_usd: float) -> int:
    exe = BinanceFuturesExecutor(mode="testnet")

    if not exe._credentials_ok():
        log.error(
            "Credentials not configured. Set "
            "BINANCE_FUTURES_TESTNET_API_KEY and "
            "BINANCE_FUTURES_TESTNET_API_SECRET in your environment.\n"
            "Sign up at https://testnet.binancefuture.com."
        )
        await exe.close()
        return 1

    try:
        # 1. Account balance
        log.info("─── Step 1: account info ───────────────────────────")
        info = await exe.get_account_info()
        if not info:
            log.error("get_account_info failed — auth may be wrong")
            return 2
        log.info(
            f"Wallet: ${info['total_wallet_balance']:.2f} | "
            f"Margin: ${info['total_margin_balance']:.2f} | "
            f"Available: ${info['available_balance']:.2f} | "
            f"Unrealized: ${info['total_unrealized_pnl']:+.2f}"
        )
        usdt = await exe.get_balance("USDT")
        log.info(f"USDT available: ${usdt:.2f}")
        if usdt < notional_usd * 1.5:
            log.error(f"Insufficient testnet balance ({usdt:.2f} USDT). Need >= {notional_usd * 1.5:.2f}")
            return 3

        # 2. Configure leverage + margin type
        log.info("─── Step 2: 1x leverage + isolated margin ─────────")
        ok = await exe.set_leverage(symbol, 1)
        if not ok:
            log.error("set_leverage failed")
            return 4
        ok = await exe.set_margin_type(symbol, isolated=True)
        if not ok:
            log.error("set_margin_type failed")
            return 5

        # 3. Determine quantity from notional + current mark price
        log.info("─── Step 3: open short hedge ──────────────────────")
        cur_pos = await exe.get_position(symbol)
        if cur_pos is None:
            log.error("get_position returned None — symbol may not exist")
            return 6
        mark = cur_pos["mark_price"]
        if mark <= 0:
            log.error(f"Mark price unavailable for {symbol}")
            return 7
        qty = round(notional_usd / mark, 6)
        log.info(f"{symbol} mark=${mark:.4f} → qty={qty} (~${qty * mark:.2f} notional)")

        client_id = f"phaseb{int(time.time() * 1000) % 1_000_000_000}"
        result = await exe.place_market_order(
            symbol, side="SELL", qty=qty, client_order_id=client_id, reduce_only=False,
        )
        if not result.success:
            log.error(f"place_market_order failed: {result.error}")
            return 8
        log.info(
            f"OPENED short: order_id={result.order_id} filled={result.filled_qty} "
            f"avg_price=${result.actual_avg_price:.4f} latency={result.latency_ms:.1f}ms"
        )

        # 4. Verify with get_position
        log.info("─── Step 4: verify position ───────────────────────")
        await asyncio.sleep(0.5)  # let it settle
        pos = await exe.get_position(symbol)
        if pos is None or pos["size"] >= 0:
            log.error(f"Position not visible or wrong sign: {pos}")
            return 9
        log.info(
            f"Position: size={pos['size']:+.6f} entry=${pos['entry_price']:.4f} "
            f"mark=${pos['mark_price']:.4f} pnl=${pos['unrealized_pnl']:+.4f} "
            f"leverage={pos['leverage']}x margin={pos['margin_type']}"
        )

        # 5. Verify with get_all_positions
        log.info("─── Step 5: verify in get_all_positions ──────────")
        all_pos = await exe.get_all_positions()
        match = [p for p in all_pos if p["symbol"] == symbol]
        if not match:
            log.error("Position not in get_all_positions — bug")
            return 10
        log.info(f"get_all_positions returned {len(all_pos)} non-zero positions; ours visible.")

        # 6. Close
        log.info("─── Step 6: close position ────────────────────────")
        close_result = await exe.close_position(symbol)
        if close_result is None or not close_result.success:
            log.error(f"close_position failed: {close_result}")
            return 11
        log.info(
            f"CLOSED: order_id={close_result.order_id} filled={close_result.filled_qty} "
            f"avg_price=${close_result.actual_avg_price:.4f} latency={close_result.latency_ms:.1f}ms"
        )

        # 7. Verify flat
        log.info("─── Step 7: verify flat ──────────────────────────")
        await asyncio.sleep(0.5)
        final = await exe.get_position(symbol)
        if final and abs(final["size"]) > 1e-9:
            log.error(f"Position not flat after close: size={final['size']}")
            return 12
        log.info(f"Position flat. {symbol} fully closed.")

        # Summary
        log.info("─── ALL TESTS PASSED ─────────────────────────────")
        info = await exe.get_account_info()
        log.info(
            f"Final balance: ${info['total_wallet_balance']:.2f} "
            f"(realized P&L from this test in funding fees / taker)"
        )
        return 0

    finally:
        await exe.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Standalone test for BinanceFuturesExecutor")
    ap.add_argument("--symbol", default="BTCUSDT", help="Symbol to test (default BTCUSDT)")
    ap.add_argument("--notional", type=float, default=15.0, help="Notional USD per test trade (default $15, min ~$5)")
    args = ap.parse_args()
    return asyncio.run(run(args.symbol, args.notional))


if __name__ == "__main__":
    sys.exit(main())
