"""
Balance tracker for cross-exchange arbitrage simulation.

Tracks USDT and crypto balances across exchanges, handles rebalancing
when funds are insufficient for a trade, and accounts for transfer fees.

Balance model:
    - USDT is tracked per exchange (shared across symbols, fungible)
    - Crypto is tracked per (exchange, symbol) in quantity units
    - Allocation is configurable per exchange (custom USDT + crypto amounts)

Rebalancing priority:
    1. Internal (trade on same exchange) — pays taker fee only
    2. External (transfer USDT via BEP20) — pays withdrawal fee
"""

import logging
import time
from dataclasses import dataclass

from config import (
    ACTIVE_EXCHANGES,
    ACTIVE_SYMBOLS,
    EXCHANGE_TAKER_FEES,
    INITIAL_BALANCE_PER_SYMBOL,
    REBALANCE_AMOUNT,
    REBALANCE_THRESHOLD,
    USDT_WITHDRAWAL_FEES,
)

logger = logging.getLogger(__name__)


@dataclass
class Transfer:
    """Record of a simulated balance transfer/rebalance."""

    timestamp: float
    transfer_type: str  # "internal_sell", "internal_buy", "external_usdt"
    from_exchange: str
    to_exchange: str  # Same as from_exchange for internal
    symbol: str
    amount_usd: float
    fee_usd: float


class BalanceTracker:
    """
    Tracks simulated USDT and crypto balances across exchanges.

    USDT is per exchange (shared pool). Crypto is per (exchange, symbol)
    in quantity units. Handles rebalancing with internal-first preference.

    Supports custom per-exchange allocations via the `allocations` parameter:
        {"KuCoin": {"usdt": 800, "crypto": {"SNXUSDT": 800}}, ...}
    Values in crypto dict are USD amounts (converted to qty on first price).
    """

    def __init__(
        self,
        exchanges: list[str] | None = None,
        symbols: list[str] | None = None,
        allocations: dict | None = None,
        rebalance_amount: float | None = None,
        rebalance_cooldown: float = 30.0,
        trade_amount: float = 50.0,
        adaptive_mode: bool = True,
    ) -> None:
        self._exchanges = exchanges or ACTIVE_EXCHANGES
        self._symbols = symbols or ACTIVE_SYMBOLS
        self._rebalance_amount = rebalance_amount or REBALANCE_AMOUNT
        self._rebalance_cooldown = rebalance_cooldown
        self._trade_amount = trade_amount
        self._max_rebalance = trade_amount * 4  # cap at 4× trade size
        self._adaptive_mode = adaptive_mode
        self._estimated_profit_per_trade: float = 0.02
        self._allocations = allocations

        # Initialize balances from allocations
        if allocations:
            self.usdt: dict[str, float] = {
                ex: allocations.get(ex, {}).get("usdt", 0.0) for ex in self._exchanges
            }
            # Store crypto USD targets for initialize_crypto()
            self._crypto_usd: dict[str, dict[str, float]] = {
                ex: {
                    sym: allocations.get(ex, {}).get("crypto", {}).get(sym, 0.0)
                    for sym in self._symbols
                }
                for ex in self._exchanges
            }
            self._initial_investment = sum(self.usdt.values())
            for ex in self._exchanges:
                for sym in self._symbols:
                    self._initial_investment += self._crypto_usd[ex][sym]
        else:
            # Uniform default: $80 USDT + $80 crypto per symbol per exchange
            half = INITIAL_BALANCE_PER_SYMBOL / 2.0
            self.usdt = {ex: half * len(self._symbols) for ex in self._exchanges}
            self._crypto_usd = {
                ex: {sym: half for sym in self._symbols} for ex in self._exchanges
            }
            self._initial_investment = (
                INITIAL_BALANCE_PER_SYMBOL * len(self._symbols) * len(self._exchanges)
            )

        # Crypto quantities per (exchange, symbol) — set on initialization
        self.crypto: dict[str, dict[str, float]] = {
            ex: {sym: 0.0 for sym in self._symbols} for ex in self._exchanges
        }

        # Transfer/rebalance log
        self.transfers: list[Transfer] = []
        self.total_transfer_fees: float = 0.0
        self.skipped_trades: int = 0

        # Rebalance cooldown tracking: "exchange:direction" → last rebalance timestamp
        self._last_rebalance: dict[str, float] = {}

        # Initialization state
        self._initialized: bool = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def update_symbols(self, symbols: list[str]) -> None:
        """Update active symbols list and ensure crypto dicts have entries."""
        self._symbols = list(symbols)
        for ex in self._exchanges:
            for sym in symbols:
                if sym not in self.crypto[ex]:
                    self.crypto[ex][sym] = 0.0

    def reset(self, allocations: dict | None = None) -> None:
        """Reset all balances and state. Optionally apply new allocations."""
        if allocations:
            self._allocations = allocations
        self.__init__(
            exchanges=self._exchanges,
            symbols=self._symbols,
            allocations=self._allocations,
            rebalance_amount=self._rebalance_amount,
            rebalance_cooldown=self._rebalance_cooldown,
            trade_amount=self._trade_amount,
            adaptive_mode=self._adaptive_mode,
        )
        logger.info("[Balance] Reset complete")

    def initialize_crypto(self, prices: dict[str, float]) -> None:
        """
        Set initial crypto quantities based on first available prices.

        Uses per-exchange-per-symbol USD amounts from allocations.
        """
        if self._initialized:
            return

        missing = [s for s in self._symbols if s not in prices or prices[s] <= 0]
        if missing:
            logger.warning(f"[Balance] Waiting for prices: {missing}")
            return

        for ex in self._exchanges:
            for sym in self._symbols:
                usd_amount = self._crypto_usd[ex][sym]
                if usd_amount > 0:
                    qty = usd_amount / prices[sym]
                    self.crypto[ex][sym] = qty

        self._initialized = True

        # Log allocation summary
        parts = []
        for ex in self._exchanges:
            ex_usdt = self.usdt[ex]
            ex_crypto = sum(
                self.crypto[ex][sym] * prices.get(sym, 0) for sym in self._symbols
            )
            parts.append(f"{ex}: ${ex_usdt:.0f} USDT + ${ex_crypto:.0f} crypto")
        logger.info(
            f"[Balance] Initialized (${self._initial_investment:.0f} total): "
            + " | ".join(parts)
        )

    def can_execute(
        self,
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        trade_amount: float,
        sell_price: float,
    ) -> tuple[bool, bool]:
        """
        Check if we have enough balance to execute this trade.

        Returns (has_usdt_to_buy, has_crypto_to_sell).
        """
        has_usdt = self.usdt.get(buy_exchange, 0.0) >= trade_amount
        crypto_qty = self.crypto.get(sell_exchange, {}).get(symbol, 0.0)
        crypto_value = crypto_qty * sell_price
        has_crypto = crypto_value >= trade_amount
        return has_usdt, has_crypto

    def compute_rebalance_amount(self, exchange: str, symbol: str = "") -> float:
        """Compute how much to rebalance based on position deficit and trade size."""
        target = self._trade_amount * 3
        if symbol:
            return min(target, self._max_rebalance)
        current_usdt = self.usdt.get(exchange, 0.0)
        deficit = max(0, target - current_usdt)
        return min(max(deficit, self._trade_amount), self._max_rebalance)

    def try_rebalance(
        self,
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        trade_amount: float,
        prices: dict[str, float],
    ) -> list[Transfer]:
        """
        Attempt to rebalance so the trade can execute.

        Priority: internal (trade on same exchange) > external (USDT transfer).
        Returns list of Transfer records for any rebalancing performed.
        """
        transfers: list[Transfer] = []
        now = time.time()
        sell_price = prices.get(symbol, 0.0)

        has_usdt, has_crypto = self.can_execute(
            buy_exchange, sell_exchange, symbol, trade_amount, sell_price
        )

        # --- Rebalance crypto on sell exchange FIRST ---
        # Do crypto before USDT so external crypto transfer from buyer can use
        # accumulated crypto before internal sell on buyer consumes it.
        # External crypto ($0.10) is cheaper than internal buy ($0.24).
        if not has_crypto:
            transfer = self._rebalance_crypto(
                sell_exchange, symbol, prices.get(symbol, 0.0), now
            )
            if transfer:
                transfers.append(transfer)

        # --- Rebalance USDT on buy exchange ---
        has_usdt, has_crypto = self.can_execute(
            buy_exchange, sell_exchange, symbol, trade_amount, sell_price
        )
        if not has_usdt:
            transfer = self._rebalance_usdt(buy_exchange, prices, now)
            if transfer:
                transfers.append(transfer)

        return transfers

    def _rebalance_usdt(
        self, exchange: str, prices: dict[str, float], now: float
    ) -> Transfer | None:
        """
        Get more USDT on an exchange. Always picks the cheapest option.

        Options compared by cost:
        - External: transfer USDT from another exchange (flat withdrawal fee)
        - Internal: sell crypto on this exchange for USDT (percentage taker fee)
        """
        # Cooldown check
        cooldown_key = f"{exchange}:usdt"
        if now - self._last_rebalance.get(cooldown_key, 0) < self._rebalance_cooldown:
            return None

        if self._adaptive_mode:
            rebal = self.compute_rebalance_amount(exchange)
        else:
            rebal = self._rebalance_amount

        # --- Compute cost of each option ---

        # External option: cheapest withdrawal fee among eligible sources
        external_cost = float("inf")
        external_source = None
        external_rebal = rebal
        eligible = [
            ex for ex in self._exchanges
            if ex != exchange and self.usdt[ex] >= rebal + REBALANCE_THRESHOLD
        ]
        # Fallback: if no source covers full amount, try 1× trade_amount from cheapest source
        if not eligible:
            min_rebal = self._trade_amount
            smaller_eligible = [
                ex for ex in self._exchanges
                if ex != exchange and self.usdt[ex] >= min_rebal + REBALANCE_THRESHOLD
            ]
            if smaller_eligible:
                eligible = smaller_eligible
                external_rebal = min_rebal
        if eligible:
            external_source = min(
                eligible,
                key=lambda ex: USDT_WITHDRAWAL_FEES.get(ex, 1.0),
            )
            external_cost = USDT_WITHDRAWAL_FEES.get(external_source, 1.0)

            # Transfer worthiness check (adaptive mode only)
            if self._adaptive_mode and self._estimated_profit_per_trade > 0:
                trades_to_recoup = external_cost / self._estimated_profit_per_trade
                if trades_to_recoup > 50:
                    logger.debug(
                        f"[Balance] External transfer {external_source}→{exchange} "
                        f"skipped: fee ${external_cost:.2f} needs "
                        f"{trades_to_recoup:.0f} trades to recoup"
                    )
                    external_cost = float("inf")
                    external_source = None

        # Internal option: sell crypto for USDT (percentage taker fee)
        internal_cost = float("inf")
        internal_sym = None
        internal_price = 0.0
        best_value = 0.0
        for sym in self._symbols:
            qty = self.crypto[exchange].get(sym, 0.0)
            p = prices.get(sym, 0.0)
            val = qty * p
            if val > best_value:
                best_value = val
                internal_sym = sym
                internal_price = p

        if internal_sym and internal_price > 0 and best_value >= rebal + REBALANCE_THRESHOLD:
            internal_cost = rebal * EXCHANGE_TAKER_FEES.get(exchange, 0.001)

        # --- Pick cheapest ---
        if external_source and external_cost <= internal_cost:
            amt = external_rebal
            self.usdt[external_source] -= amt + external_cost
            self.usdt[exchange] += amt
            self.total_transfer_fees += external_cost

            transfer = Transfer(
                timestamp=now,
                transfer_type="external_usdt",
                from_exchange=external_source,
                to_exchange=exchange,
                symbol="USDT",
                amount_usd=amt,
                fee_usd=external_cost,
            )
            self.transfers.append(transfer)
            self._last_rebalance[cooldown_key] = now
            logger.debug(
                f"[Balance] External USDT: ${amt:.2f} {external_source}→{exchange} "
                f"(fee: ${external_cost:.4f}, internal would be ${internal_cost:.4f})"
            )
            return transfer

        if internal_sym and internal_cost < float("inf"):
            fee_usd = internal_cost
            sell_qty = rebal / internal_price
            self.crypto[exchange][internal_sym] -= sell_qty
            self.usdt[exchange] += rebal - fee_usd
            self.total_transfer_fees += fee_usd

            transfer = Transfer(
                timestamp=now,
                transfer_type="internal_sell",
                from_exchange=exchange,
                to_exchange=exchange,
                symbol=internal_sym,
                amount_usd=rebal,
                fee_usd=fee_usd,
            )
            self.transfers.append(transfer)
            self._last_rebalance[cooldown_key] = now
            logger.debug(
                f"[Balance] Internal sell: {internal_sym} on {exchange}, "
                f"${rebal:.2f} → USDT (fee: ${fee_usd:.4f}, external would be ${external_cost:.4f})"
            )
            return transfer

        return None

    def _rebalance_crypto(
        self, exchange: str, symbol: str, price: float, now: float
    ) -> Transfer | None:
        """
        Get more crypto on an exchange.

        Priority (cheapest first):
        1. External crypto transfer — move token from another exchange (withdrawal fee only)
        2. Internal buy — buy with local USDT (taker fee on full amount)
        3. External USDT + buy — transfer USDT then buy (withdrawal fee + taker fee)

        External crypto is preferred because the buy exchange naturally accumulates
        crypto (from buying) while the sell exchange depletes it (from selling).
        Transferring the token directly avoids paying a taker fee.
        """
        # Cooldown check
        cooldown_key = f"{exchange}:crypto:{symbol}"
        if now - self._last_rebalance.get(cooldown_key, 0) < self._rebalance_cooldown:
            return None

        if self._adaptive_mode:
            rebal = self.compute_rebalance_amount(exchange, symbol)
        else:
            rebal = self._rebalance_amount

        # --- Option 1: External crypto transfer (cheapest when source has excess) ---
        # Find exchanges with enough crypto of this symbol to transfer
        crypto_rebal = rebal
        crypto_sources = []
        for ex in self._exchanges:
            if ex == exchange:
                continue
            qty = self.crypto[ex].get(symbol, 0.0)
            crypto_val = qty * price
            if crypto_val >= rebal * 1.2:
                crypto_sources.append(ex)
        # Fallback: try smaller amount from any source
        if not crypto_sources:
            min_rebal = self._trade_amount
            for ex in self._exchanges:
                if ex == exchange:
                    continue
                qty = self.crypto[ex].get(symbol, 0.0)
                crypto_val = qty * price
                if crypto_val >= min_rebal * 1.2:
                    crypto_sources.append(ex)
            if crypto_sources:
                crypto_rebal = min_rebal

        internal_buy_cost = crypto_rebal * EXCHANGE_TAKER_FEES.get(exchange, 0.001)
        transfer_qty = crypto_rebal / price

        if crypto_sources:
            # Pick source with cheapest withdrawal fee
            best_source = min(
                crypto_sources,
                key=lambda ex: USDT_WITHDRAWAL_FEES.get(ex, 1.0),
            )
            # Use USDT withdrawal fee as proxy for token withdrawal fee
            # (same networks, similar fees)
            external_crypto_cost = USDT_WITHDRAWAL_FEES.get(best_source, 1.0)

            # Transfer worthiness check
            if self._adaptive_mode and self._estimated_profit_per_trade > 0:
                trades_to_recoup = external_crypto_cost / self._estimated_profit_per_trade
                if trades_to_recoup > 50:
                    crypto_sources = []  # Skip, fall through to internal

            # Prefer external crypto if cheaper than internal buy
            if crypto_sources and external_crypto_cost < internal_buy_cost:
                self.crypto[best_source][symbol] -= transfer_qty
                self.crypto[exchange][symbol] += transfer_qty
                self.total_transfer_fees += external_crypto_cost

                transfer = Transfer(
                    timestamp=now,
                    transfer_type="external_crypto",
                    from_exchange=best_source,
                    to_exchange=exchange,
                    symbol=symbol,
                    amount_usd=crypto_rebal,
                    fee_usd=external_crypto_cost,
                )
                self.transfers.append(transfer)
                self._last_rebalance[cooldown_key] = now
                logger.debug(
                    f"[Balance] External crypto: {symbol} {best_source}→{exchange}, "
                    f"${rebal:.2f} worth (fee: ${external_crypto_cost:.4f})"
                )
                return transfer

        # --- Option 2: Internal buy with local USDT ---
        if self.usdt[exchange] >= rebal:
            fee_rate = EXCHANGE_TAKER_FEES.get(exchange, 0.001)
            fee_usd = rebal * fee_rate
            buy_qty = (rebal - fee_usd) / price
            self.usdt[exchange] -= rebal
            self.crypto[exchange][symbol] += buy_qty
            self.total_transfer_fees += fee_usd

            transfer = Transfer(
                timestamp=now,
                transfer_type="internal_buy",
                from_exchange=exchange,
                to_exchange=exchange,
                symbol=symbol,
                amount_usd=rebal,
                fee_usd=fee_usd,
            )
            self.transfers.append(transfer)
            self._last_rebalance[cooldown_key] = now
            logger.debug(
                f"[Balance] Internal buy: {symbol} on {exchange}, "
                f"${rebal:.2f} USDT → crypto (fee: ${fee_usd:.4f})"
            )
            return transfer

        # --- Option 3: External USDT transfer + buy (last resort) ---
        ext_buy_rebal = rebal
        eligible = [
            ex for ex in self._exchanges
            if ex != exchange and self.usdt[ex] >= rebal + REBALANCE_THRESHOLD
        ]
        if not eligible:
            min_rebal = self._trade_amount
            eligible = [
                ex for ex in self._exchanges
                if ex != exchange and self.usdt[ex] >= min_rebal + REBALANCE_THRESHOLD
            ]
            if eligible:
                ext_buy_rebal = min_rebal
        richest_ex = min(
            eligible,
            key=lambda ex: USDT_WITHDRAWAL_FEES.get(ex, 1.0),
            default=None,
        )
        if richest_ex:
            withdrawal_fee = USDT_WITHDRAWAL_FEES.get(richest_ex, 1.0)

            # Transfer worthiness check (adaptive mode only)
            if self._adaptive_mode and self._estimated_profit_per_trade > 0:
                trades_to_recoup = withdrawal_fee / self._estimated_profit_per_trade
                if trades_to_recoup > 50:
                    logger.debug(
                        f"[Balance] External+buy {richest_ex}→{exchange} "
                        f"skipped: fee ${withdrawal_fee:.2f} needs "
                        f"{trades_to_recoup:.0f} trades to recoup"
                    )
                    return None

            fee_rate = EXCHANGE_TAKER_FEES.get(exchange, 0.001)
            buy_fee = ext_buy_rebal * fee_rate

            # Transfer USDT
            self.usdt[richest_ex] -= ext_buy_rebal + withdrawal_fee
            # Buy crypto on destination
            buy_qty = (ext_buy_rebal - buy_fee) / price
            self.crypto[exchange][symbol] += buy_qty
            total_fee = withdrawal_fee + buy_fee
            self.total_transfer_fees += total_fee

            transfer = Transfer(
                timestamp=now,
                transfer_type="external_usdt",
                from_exchange=richest_ex,
                to_exchange=exchange,
                symbol=symbol,
                amount_usd=ext_buy_rebal,
                fee_usd=total_fee,
            )
            self.transfers.append(transfer)
            self._last_rebalance[cooldown_key] = now
            logger.debug(
                f"[Balance] External+buy: ${rebal:.2f} USDT {richest_ex}→{exchange}, "
                f"buy {symbol} (total fee: ${total_fee:.4f})"
            )
            return transfer

        return None

    def execute_trade(
        self,
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        trade_amount: float,
        buy_price: float,
        sell_price: float,
        buy_fee: float,
        sell_fee: float,
    ) -> None:
        """
        Execute a simulated trade and update balances.

        buy_fee/sell_fee are decimal rates (e.g., 0.00075 for 0.075%).
        """
        # Buy side: spend USDT, receive crypto (minus fee)
        coins_bought = trade_amount / buy_price
        coins_after_fee = coins_bought * (1.0 - buy_fee)
        self.usdt[buy_exchange] -= trade_amount
        self.crypto[buy_exchange][symbol] += coins_after_fee

        # Sell side: spend crypto, receive USDT (minus fee)
        coins_to_sell = trade_amount / sell_price
        usdt_received = trade_amount * (1.0 - sell_fee)
        self.crypto[sell_exchange][symbol] -= coins_to_sell
        self.usdt[sell_exchange] += usdt_received

    def get_portfolio_value(self, prices: dict[str, float]) -> float:
        """Calculate total portfolio value in USD."""
        total = sum(self.usdt.values())
        for ex in self._exchanges:
            for sym in self._symbols:
                qty = self.crypto[ex].get(sym, 0.0)
                p = prices.get(sym, 0.0)
                total += qty * p
        return total

    def get_balance_lines(self, prices: dict[str, float]) -> list[str]:
        """Get formatted balance summary lines for live display."""
        parts = []
        for ex in self._exchanges:
            ex_total = self.usdt[ex]
            for sym in self._symbols:
                ex_total += self.crypto[ex].get(sym, 0.0) * prices.get(sym, 0.0)
            parts.append(f"{ex} ${ex_total:.0f}")
        portfolio = self.get_portfolio_value(prices)
        transfer_count = len(self.transfers)
        return [
            f"  Balances: {' | '.join(parts)} | "
            f"Transfers: {transfer_count} (${self.total_transfer_fees:.2f} fees) | "
            f"Portfolio: ${portfolio:.0f}"
        ]
