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
from collections import deque
from dataclasses import dataclass

from config import (
    ACTIVE_EXCHANGES,
    ACTIVE_SYMBOLS,
    INITIAL_BALANCE_PER_SYMBOL,
    REBALANCE_AMOUNT,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fee_manager import FeeManager
    from transfer_fee_manager import TransferFeeManager

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


@dataclass
class InTransitFund:
    """D-17: Tracks funds in transit between exchanges.

    In demo mode, external transfers are not instant. Funds are deducted
    from source immediately but credited to destination only after the
    estimated network transit time.
    """

    amount: float           # USDT or crypto quantity
    asset: str              # "USDT" or crypto symbol (e.g. "BTCUSDT")
    sent_at: float          # time.time() when transfer initiated
    eta: float              # estimated time of arrival (sent_at + network_delay)
    from_exchange: str
    to_exchange: str


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
        exchange_info: "ExchangeInfoManager | None" = None,
        fee_manager: "FeeManager | None" = None,
        transfer_fee_manager: "TransferFeeManager | None" = None,
        hourly_external_transfer_cap: float = 2.0,
        bitfinex_reserve_pct: float = 0.15,
        bitfinex_reserve_hard_floor: float = 0.05,
    ) -> None:
        self._fee_manager = fee_manager
        self._transfer_fee_mgr = transfer_fee_manager
        self._exchanges = exchanges or ACTIVE_EXCHANGES
        self._symbols = symbols or ACTIVE_SYMBOLS
        self._exchange_info = exchange_info
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
        self.total_external_transfer_fees: float = 0.0  # Only withdrawal fees (not internal taker fees)
        self.skipped_trades: int = 0

        # Rebalance cooldown tracking: "exchange:direction" → last rebalance timestamp
        self._last_rebalance: dict[str, float] = {}

        # D-18: Track last trade time per exchange (for demo sync grace period)
        self.last_trade_time: dict[str, float] = {}

        # D-17: In-transit funds (demo mode only)
        self._in_transit: list[InTransitFund] = []
        self._execution_mode: str = "simulation"

        # Hourly external transfer fee budget tracking
        self._external_fee_log: deque[tuple[float, float]] = deque()  # (timestamp, fee_amount)
        self._hourly_external_transfer_cap: float = hourly_external_transfer_cap

        # Bitfinex USDT reserve: keep a % of capital as emergency liquidity
        self._bitfinex_reserve_pct: float = bitfinex_reserve_pct
        self._bitfinex_reserve_target: float = self._initial_investment * bitfinex_reserve_pct
        self._bitfinex_reserve_hard_floor: float = bitfinex_reserve_hard_floor
        self._bitfinex_reserve_hard_floor_amount: float = self._initial_investment * bitfinex_reserve_hard_floor

        # Emergency draw log throttle (avoid 60+ identical messages)
        self._emergency_draw_log_time: float = 0.0

        # Initialization state
        self._initialized: bool = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def _rebalance_buffer(self) -> float:
        """Dynamic buffer for rebalance eligibility, scales with trade amount.

        Replaces the fixed REBALANCE_THRESHOLD ($50). With $10 trades this
        returns $20, making internal sell viable for smaller positions.
        """
        return self._trade_amount * 2

    def _check_hourly_transfer_budget(self, proposed_fee: float) -> bool:
        """Return True if external transfer is within hourly budget."""
        if self._hourly_external_transfer_cap <= 0:
            return True  # Disabled
        if proposed_fee <= 0.01:
            return True  # Zero/near-zero fee transfers always allowed
        now = time.time()
        # Evict entries older than 1 hour
        while self._external_fee_log and self._external_fee_log[0][0] < now - 3600:
            self._external_fee_log.popleft()
        current = sum(fee for _, fee in self._external_fee_log)
        if current + proposed_fee > self._hourly_external_transfer_cap:
            logger.info(
                f"[Balance] External transfer BLOCKED by hourly cap: "
                f"${current:.2f}+${proposed_fee:.2f} > "
                f"${self._hourly_external_transfer_cap:.2f}/hr"
            )
            return False
        return True

    def _record_external_fee(self, fee: float) -> None:
        """Record external transfer fee for hourly budget tracking."""
        self._external_fee_log.append((time.time(), fee))

    def _get_withdrawal_fee(self, exchange: str, amount: float = 0.0) -> float:
        """Get withdrawal fee for an exchange, using TransferFeeManager if available."""
        if self._transfer_fee_mgr:
            return self._transfer_fee_mgr.get_withdrawal_fee(exchange, amount)
        return 1.0

    def _available_usdt_for_rebalance(self, exchange: str) -> float:
        """USDT available for rebalance on an exchange, protecting Bitfinex reserve."""
        usdt = self.usdt.get(exchange, 0.0)
        if exchange == "Bitfinex" and self._bitfinex_reserve_pct > 0:
            return max(0.0, usdt - self._bitfinex_reserve_target)
        return usdt

    def available_usdt_for_trading(self, exchange: str) -> float:
        """USDT available for trading on an exchange, protecting Bitfinex reserve.

        Unlike _available_usdt_for_rebalance (used for transfer source selection),
        this protects the reserve from being spent by normal trade execution.
        """
        usdt = self.usdt.get(exchange, 0.0)
        if exchange == "Bitfinex" and self._bitfinex_reserve_pct > 0:
            return max(0.0, usdt - self._bitfinex_reserve_target)
        return usdt

    def update_symbols(self, symbols: list[str]) -> None:
        """Update active symbols list and ensure crypto dicts have entries."""
        self._symbols = list(symbols)
        for ex in self._exchanges:
            for sym in symbols:
                if sym not in self.crypto[ex]:
                    self.crypto[ex][sym] = 0.0

    def reconfigure(self, allocations: dict | None = None) -> None:
        """Reconfigure balances for new symbols/exchanges, preserving cumulative state.

        Resets USDT/crypto balances and initialization state for the new
        allocation, but keeps cumulative data (transfers, fees, trade times,
        external fee log, in-transit funds, skipped trades) intact across
        demotion→discovery→activation cycles.
        """
        if allocations:
            self._allocations = allocations

        # Reset balance allocation state
        if self._allocations:
            self.usdt = {
                ex: self._allocations.get(ex, {}).get("usdt", 0.0)
                for ex in self._exchanges
            }
            self._crypto_usd = {
                ex: {
                    sym: self._allocations.get(ex, {}).get("crypto", {}).get(sym, 0.0)
                    for sym in self._symbols
                }
                for ex in self._exchanges
            }
            self._initial_investment = sum(self.usdt.values())
            for ex in self._exchanges:
                for sym in self._symbols:
                    self._initial_investment += self._crypto_usd[ex][sym]
        else:
            half = INITIAL_BALANCE_PER_SYMBOL / 2.0
            self.usdt = {ex: half * len(self._symbols) for ex in self._exchanges}
            self._crypto_usd = {
                ex: {sym: half for sym in self._symbols} for ex in self._exchanges
            }
            self._initial_investment = (
                INITIAL_BALANCE_PER_SYMBOL * len(self._symbols) * len(self._exchanges)
            )

        # Reset crypto quantities and initialization
        self.crypto = {
            ex: {sym: 0.0 for sym in self._symbols} for ex in self._exchanges
        }
        self._initialized = False
        self._last_rebalance.clear()
        self._max_rebalance = self._trade_amount * 4

        # Update Bitfinex reserve targets
        self._bitfinex_reserve_target = self._initial_investment * self._bitfinex_reserve_pct
        self._bitfinex_reserve_hard_floor_amount = (
            self._initial_investment * self._bitfinex_reserve_hard_floor
        )

        # Preserve: transfers, total_transfer_fees, total_external_transfer_fees,
        # skipped_trades, last_trade_time, _in_transit, _external_fee_log,
        # _execution_mode, _estimated_profit_per_trade

        logger.info(
            f"[Balance] Reconfigured (cumulative: {len(self.transfers)} transfers, "
            f"${self.total_transfer_fees:.4f} total fees, "
            f"${self.total_external_transfer_fees:.4f} external fees)"
        )

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

    # ── D-17: In-transit fund tracking ──────────────────────────────────

    # Estimated network transit times in seconds per network type
    _NETWORK_DELAYS: dict[str, float] = {
        "BEP20": 30.0,       # BSC: ~3s block + confirmations
        "Arbitrum": 15.0,    # L2: fast finality
        "Polygon": 30.0,     # PoS: moderate
        "Solana": 10.0,      # Fast but occasional outages
        "TRC20": 60.0,       # TRON: slower confirmations
        "default": 60.0,     # Conservative default
    }

    def deliver_in_transit(self) -> int:
        """Credit arrived in-transit funds to destination balances.

        Called periodically (e.g., each tick). Returns number of deliveries.
        """
        now = time.time()
        delivered = 0
        still_in_transit = []

        for fund in self._in_transit:
            if now >= fund.eta:
                # Deliver to destination
                if fund.asset == "USDT":
                    self.usdt[fund.to_exchange] += fund.amount
                else:
                    self.crypto[fund.to_exchange][fund.asset] += fund.amount
                delivered += 1
                logger.debug(
                    f"[Balance] In-transit delivered: {fund.amount:.4f} {fund.asset} "
                    f"→ {fund.to_exchange} (transit {now - fund.sent_at:.0f}s)"
                )
            else:
                still_in_transit.append(fund)

        self._in_transit = still_in_transit
        return delivered

    def in_transit_total(self, exchange: str, asset: str = "USDT") -> float:
        """Get total amount in transit to an exchange for a given asset."""
        return sum(
            f.amount for f in self._in_transit
            if f.to_exchange == exchange and f.asset == asset
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
        has_usdt = self.available_usdt_for_trading(buy_exchange) >= trade_amount
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
        remaining = self._rebalance_cooldown - (now - self._last_rebalance.get(cooldown_key, 0))
        if remaining > 0:
            logger.debug(
                f"[Balance] USDT rebalance {exchange}: cooldown {remaining:.0f}s remaining"
            )
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
        buf = self._rebalance_buffer
        eligible = [
            ex for ex in self._exchanges
            if ex != exchange and self._available_usdt_for_rebalance(ex) >= rebal + buf
        ]
        # Fallback: if no source covers full amount, try 1× trade_amount from cheapest source
        if not eligible:
            min_rebal = self._trade_amount
            smaller_eligible = [
                ex for ex in self._exchanges
                if ex != exchange and self._available_usdt_for_rebalance(ex) >= min_rebal + buf
            ]
            if smaller_eligible:
                eligible = smaller_eligible
                external_rebal = min_rebal
        if eligible:
            # Prefer cheap sources (fee <= $0.10), expensive as last resort
            cheap_eligible = [ex for ex in eligible if self._get_withdrawal_fee(ex) <= 0.10]
            if cheap_eligible:
                external_source = min(cheap_eligible, key=lambda ex: self._get_withdrawal_fee(ex))
            else:
                external_source = min(eligible, key=lambda ex: self._get_withdrawal_fee(ex))
            external_cost = self._get_withdrawal_fee(external_source)

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

            # Hourly external transfer budget check
            if external_source and not self._check_hourly_transfer_budget(external_cost):
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

        if internal_sym and internal_price > 0 and best_value >= rebal + self._rebalance_buffer:
            internal_cost = rebal * (self._fee_manager.get_taker_fee(exchange) if self._fee_manager else 0.001)

        # --- Pick cheapest ---
        if external_source and external_cost <= internal_cost:
            amt = external_rebal
            self.usdt[external_source] -= amt + external_cost

            if self._execution_mode in ("demo", "demo_only"):
                # D-17: In demo mode, funds transit through network
                self._in_transit.append(InTransitFund(
                    amount=amt,
                    asset="USDT",
                    sent_at=now,
                    eta=now + self._NETWORK_DELAYS.get("BEP20", 60.0),
                    from_exchange=external_source,
                    to_exchange=exchange,
                ))
                logger.debug(
                    f"[Balance] USDT in-transit: ${amt:.2f} {external_source}→{exchange}"
                )
            else:
                # Simulation: instant credit
                self.usdt[exchange] += amt

            self.total_transfer_fees += external_cost
            self.total_external_transfer_fees += external_cost
            self._record_external_fee(external_cost)

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
            self.last_trade_time[exchange] = now
            self.last_trade_time[external_source] = now
            logger.info(
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
            self.last_trade_time[exchange] = now
            logger.info(
                f"[Balance] Internal sell: {internal_sym} on {exchange}, "
                f"${rebal:.2f} → USDT (fee: ${fee_usd:.4f}, external would be ${external_cost:.4f})"
            )
            return transfer

        # Log why USDT rebalance failed
        best_other = max(
            (self.usdt[ex] for ex in self._exchanges if ex != exchange),
            default=0.0,
        )
        logger.info(
            f"[Balance] USDT rebalance FAILED for {exchange}: "
            f"need=${rebal:.2f}+buf=${buf:.2f}, "
            f"best_other_usdt=${best_other:.2f}, "
            f"best_crypto_val=${best_value:.2f}, "
            f"ext={'blocked' if external_source is None else f'${external_cost:.2f}'}"
        )
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
        # Cooldown check — shorter for free transfers (Bitfinex, MEXC, Bybit)
        cooldown_key = f"{exchange}:crypto:{symbol}"
        effective_cooldown = self._rebalance_cooldown
        # Find cheapest crypto source to check if free transfer is possible
        cheapest_fee = float("inf")
        for ex in self._exchanges:
            if ex != exchange:
                qty = self.crypto[ex].get(symbol, 0.0)
                if qty * price >= self._trade_amount:
                    fee = self._get_withdrawal_fee(ex)
                    if fee < cheapest_fee:
                        cheapest_fee = fee
        if cheapest_fee <= 0.01:
            # Free transfer available — use shorter cooldown (10s vs 30s default)
            effective_cooldown = min(self._rebalance_cooldown, 10.0)
        remaining = effective_cooldown - (now - self._last_rebalance.get(cooldown_key, 0))
        if remaining > 0:
            logger.debug(
                f"[Balance] Crypto rebalance {exchange}/{symbol}: cooldown {remaining:.0f}s remaining"
            )
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

        internal_buy_cost = crypto_rebal * (self._fee_manager.get_taker_fee(exchange) if self._fee_manager else 0.001)
        transfer_qty = crypto_rebal / price

        if crypto_sources:
            # Pick source with cheapest withdrawal fee
            best_source = min(
                crypto_sources,
                key=lambda ex: self._get_withdrawal_fee(ex),
            )
            # Use USDT withdrawal fee as proxy for token withdrawal fee
            # (same networks, similar fees)
            external_crypto_cost = self._get_withdrawal_fee(best_source)

            # Transfer worthiness check
            if self._adaptive_mode and self._estimated_profit_per_trade > 0:
                trades_to_recoup = external_crypto_cost / self._estimated_profit_per_trade
                if trades_to_recoup > 50:
                    crypto_sources = []  # Skip, fall through to internal

            # Hourly external transfer budget check
            if crypto_sources and not self._check_hourly_transfer_budget(external_crypto_cost):
                crypto_sources = []  # Skip, fall through to internal

            # Prefer external crypto if cheaper than internal buy
            if crypto_sources and external_crypto_cost < internal_buy_cost:
                self.crypto[best_source][symbol] -= transfer_qty
                self.crypto[exchange][symbol] += transfer_qty
                self.total_transfer_fees += external_crypto_cost
                self.total_external_transfer_fees += external_crypto_cost
                self._record_external_fee(external_crypto_cost)

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
                self.last_trade_time[exchange] = now
                self.last_trade_time[best_source] = now
                logger.info(
                    f"[Balance] External crypto: {symbol} {best_source}→{exchange}, "
                    f"${rebal:.2f} worth (fee: ${external_crypto_cost:.4f})"
                )
                return transfer

        # --- Option 2: Internal buy with local USDT ---
        if self.usdt[exchange] >= rebal:
            fee_rate = self._fee_manager.get_taker_fee(exchange) if self._fee_manager else 0.001
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
            self.last_trade_time[exchange] = now
            logger.info(
                f"[Balance] Internal buy: {symbol} on {exchange}, "
                f"${rebal:.2f} USDT → crypto (fee: ${fee_usd:.4f})"
            )
            return transfer

        # --- Option 3: External USDT transfer + buy (last resort) ---
        ext_buy_rebal = rebal
        eligible = [
            ex for ex in self._exchanges
            if ex != exchange and self._available_usdt_for_rebalance(ex) >= rebal + self._rebalance_buffer
        ]
        if not eligible:
            min_rebal = self._trade_amount
            eligible = [
                ex for ex in self._exchanges
                if ex != exchange and self._available_usdt_for_rebalance(ex) >= min_rebal + self._rebalance_buffer
            ]
            if eligible:
                ext_buy_rebal = min_rebal
        richest_ex = min(
            eligible,
            key=lambda ex: self._get_withdrawal_fee(ex),
            default=None,
        )
        if richest_ex:
            withdrawal_fee = self._get_withdrawal_fee(richest_ex)

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

            # Hourly external transfer budget check
            if not self._check_hourly_transfer_budget(withdrawal_fee):
                return None

            fee_rate = self._fee_manager.get_taker_fee(exchange) if self._fee_manager else 0.001
            buy_fee = ext_buy_rebal * fee_rate

            # Transfer USDT
            self.usdt[richest_ex] -= ext_buy_rebal + withdrawal_fee
            # Buy crypto on destination
            buy_qty = (ext_buy_rebal - buy_fee) / price
            self.crypto[exchange][symbol] += buy_qty
            total_fee = withdrawal_fee + buy_fee
            self.total_transfer_fees += total_fee
            self.total_external_transfer_fees += withdrawal_fee  # Only withdrawal portion
            self._record_external_fee(withdrawal_fee)

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
            logger.info(
                f"[Balance] External+buy: ${rebal:.2f} USDT {richest_ex}→{exchange}, "
                f"buy {symbol} (total fee: ${total_fee:.4f})"
            )
            return transfer

        # Log why crypto rebalance failed
        best_crypto_source = max(
            (self.crypto[ex].get(symbol, 0.0) * price
             for ex in self._exchanges if ex != exchange),
            default=0.0,
        )
        local_usdt = self.usdt.get(exchange, 0.0)
        logger.info(
            f"[Balance] Crypto rebalance FAILED for {symbol} on {exchange}: "
            f"need=${rebal:.2f}, local_usdt=${local_usdt:.2f}, "
            f"best_other_crypto=${best_crypto_source:.2f}, "
            f"crypto_sources={len(crypto_sources)}"
        )
        return None

    # ── Bitfinex Reserve ─────────────────────────────────────────────────

    def emergency_reserve_draw(
        self, target_exchange: str, needed_amount: float
    ) -> list[Transfer]:
        """Draw USDT from Bitfinex reserve to break a capital death spiral.

        Bypasses all gates (net P&L, hourly cap, transfer worthiness).
        Only called when normal rebalancing is blocked and trading is stalled.
        """
        if self._bitfinex_reserve_pct <= 0:
            return []
        if "Bitfinex" not in self._exchanges or target_exchange == "Bitfinex":
            return []

        bitfinex_usdt = self.usdt.get("Bitfinex", 0.0)
        hard_floor = max(5.0, self._bitfinex_reserve_hard_floor_amount)
        available = bitfinex_usdt - hard_floor
        now_t = time.time()
        if available <= 0:
            if now_t - self._emergency_draw_log_time >= 30.0:
                logger.info(
                    f"[Balance] Emergency draw blocked by hard floor: "
                    f"Bitfinex=${bitfinex_usdt:.2f}, floor=${hard_floor:.2f}"
                )
                self._emergency_draw_log_time = now_t
            return []

        amount = min(needed_amount, available)
        if amount < needed_amount:
            if now_t - self._emergency_draw_log_time >= 30.0:
                logger.info(
                    f"[Balance] Emergency draw limited by hard floor: "
                    f"requested=${needed_amount:.2f}, available=${amount:.2f} "
                    f"(floor=${hard_floor:.2f})"
                )
                self._emergency_draw_log_time = now_t
        if amount < self._trade_amount:
            return []  # Not enough for even one trade

        # Withdrawal fee is $0 for Bitfinex (14/15 networks are free)
        fee = self._get_withdrawal_fee("Bitfinex", amount)

        now = time.time()
        self.usdt["Bitfinex"] -= amount
        self.usdt[target_exchange] = self.usdt.get(target_exchange, 0.0) + (amount - fee)
        if fee > 0:
            self.total_transfer_fees += fee
            self.total_external_transfer_fees += fee
            self._record_external_fee(fee)

        transfer = Transfer(
            timestamp=now,
            transfer_type="reserve_draw",
            from_exchange="Bitfinex",
            to_exchange=target_exchange,
            symbol="USDT",
            amount_usd=amount,
            fee_usd=fee,
        )
        self.transfers.append(transfer)
        logger.info(
            f"[Balance] EMERGENCY reserve draw: Bitfinex→{target_exchange} "
            f"${amount:.2f} (fee=${fee:.4f}, reserve_remaining="
            f"${self.usdt.get('Bitfinex', 0.0):.2f})"
        )
        return [transfer]

    def replenish_reserve(
        self,
        prices: dict[str, float] | None = None,
        max_fee_per_source: float | None = None,
    ) -> list[Transfer]:
        """Top up Bitfinex USDT reserve from all exchanges, sorted by withdrawal fee.

        Not gated by net profit — reserve replenishment is always beneficial.
        Respects hourly cap and per-source cooldown.

        Args:
            max_fee_per_source: If set, skip sources with fee above this amount.
                Used when net-negative to avoid expensive replenishment.
        """
        if self._bitfinex_reserve_pct <= 0:
            return []
        if "Bitfinex" not in self._exchanges:
            return []

        current = self.usdt.get("Bitfinex", 0.0)
        if current >= self._bitfinex_reserve_target:
            return []

        deficit = self._bitfinex_reserve_target - current
        min_replenish = max(20.0, self._trade_amount * 2)
        if deficit < min_replenish:
            return []  # Not worth replenishing small amounts

        # Find all senders with surplus USDT, sorted by withdrawal fee (cheapest first)
        buf = self._rebalance_buffer
        candidates = []
        for ex in self._exchanges:
            if ex == "Bitfinex":
                continue
            avail = self.usdt.get(ex, 0.0) - buf
            if avail < min_replenish:
                continue
            fee = self._get_withdrawal_fee(ex, min(deficit, avail))
            candidates.append((ex, avail, fee))

        if not candidates:
            return []

        # Sort by fee (cheapest first)
        candidates.sort(key=lambda x: x[2])

        now = time.time()
        reserve_cooldown = max(self._rebalance_cooldown, 600)
        transfers = []
        remaining_deficit = deficit

        for sender, avail, fee in candidates:
            if remaining_deficit < min_replenish:
                break

            # Skip expensive sources when net-negative
            if max_fee_per_source is not None and fee > max_fee_per_source:
                continue

            # Check cooldown (10 min per source to avoid fee churn)
            cooldown_key = f"reserve_replenish:{sender}"
            if now - self._last_rebalance.get(cooldown_key, 0) < reserve_cooldown:
                continue

            # Check hourly budget
            if not self._check_hourly_transfer_budget(fee):
                continue

            amount = min(remaining_deficit, avail)
            self.usdt[sender] -= amount
            self.usdt["Bitfinex"] += amount - fee
            if fee > 0:
                self.total_transfer_fees += fee
                self.total_external_transfer_fees += fee
                self._record_external_fee(fee)
            self._last_rebalance[cooldown_key] = now

            transfer = Transfer(
                timestamp=now,
                transfer_type="reserve_replenish",
                from_exchange=sender,
                to_exchange="Bitfinex",
                symbol="USDT",
                amount_usd=amount,
                fee_usd=fee,
            )
            self.transfers.append(transfer)
            transfers.append(transfer)
            remaining_deficit -= amount
            logger.info(
                f"[Balance] Reserve replenish: {sender}→Bitfinex "
                f"${amount:.2f} (fee=${fee:.4f}, reserve="
                f"${self.usdt.get('Bitfinex', 0.0):.2f}/"
                f"${self._bitfinex_reserve_target:.2f})"
            )

        return transfers

    def consolidate_to_bitfinex(
        self,
        active_buyer_exchanges: set[str] | None = None,
        idle_threshold: float = 600.0,
        active_seller_exchanges: set[str] | None = None,
        max_fee_per_source: float | None = None,
    ) -> list[Transfer]:
        """Consolidate USDT from non-essential exchanges to Bitfinex hub.

        Bitfinex has $0 withdrawal fees, making it the ideal capital hub.
        Capital on Bitfinex can be redistributed to any exchange for free.

        Active buyer/seller exchanges that have been idle (no trades) for longer
        than idle_threshold are treated as non-essential and consolidated too.

        When net-negative, callers pass max_fee_per_source=0.02 to limit
        consolidation to free/near-free sources and avoid deepening deficit.
        Respects hourly budget cap and per-source cooldown.

        Args:
            active_buyer_exchanges: Exchanges still needed as buyers.
                Keep trade_amount×3 buffer on recently-active ones.
                None = consolidate everything.
            idle_threshold: Seconds since last trade before an active exchange
                is considered idle and its capital consolidated. Default 600s (10 min).
            active_seller_exchanges: Exchanges still needed as sellers.
                Keep trade_amount×3 buffer on recently-active ones so USDT
                accumulated from sells isn't immediately pulled back to Bitfinex
                (which would cause expensive crypto rebalance cycles).
                None = no seller protection.
            max_fee_per_source: If set, skip sources with withdrawal fee above
                this amount. Used during discovery to avoid expensive consolidation
                when the next symbol's exchanges are unknown.
        """
        if self._bitfinex_reserve_pct <= 0:
            return []
        if "Bitfinex" not in self._exchanges:
            return []

        now = time.time()
        consolidation_cooldown = max(self._rebalance_cooldown, 600)  # 10 min
        min_transfer = max(20.0, self._trade_amount * 2)
        transfers = []

        # Sort non-Bitfinex exchanges by withdrawal fee (cheapest first)
        sources = sorted(
            (ex for ex in self._exchanges if ex != "Bitfinex"),
            key=lambda ex: self._get_withdrawal_fee(ex),
        )

        for ex in sources:
            # Compute available USDT based on exchange activity
            usdt = self.usdt.get(ex, 0.0)
            is_active_buyer = active_buyer_exchanges and ex in active_buyer_exchanges
            is_active_seller = active_seller_exchanges and ex in active_seller_exchanges
            if is_active_buyer or is_active_seller:
                # Check if this active exchange is actually idle
                last_trade = self.last_trade_time.get(ex, 0.0)
                idle_seconds = now - last_trade if last_trade > 0 else float("inf")
                if idle_seconds < idle_threshold:
                    # Recently active — keep buffer for upcoming trades
                    keep = self._trade_amount * 3
                else:
                    # Active but idle for too long — consolidate
                    keep = 0.0
            else:
                # Not an active exchange — transfer everything
                keep = 0.0
            available = usdt - keep
            if available < min_transfer:
                continue

            # Check cooldown
            cooldown_key = f"{ex}:consolidate"
            if now - self._last_rebalance.get(cooldown_key, 0) < consolidation_cooldown:
                continue

            fee = self._get_withdrawal_fee(ex, available)

            # Skip expensive sources during discovery
            if max_fee_per_source is not None and fee > max_fee_per_source:
                continue

            # Check hourly budget
            if not self._check_hourly_transfer_budget(fee):
                continue

            # Execute consolidation
            self.usdt[ex] -= available
            self.usdt["Bitfinex"] += available - fee
            if fee > 0:
                self.total_transfer_fees += fee
                self.total_external_transfer_fees += fee
                self._record_external_fee(fee)
            self._last_rebalance[cooldown_key] = now

            transfer = Transfer(
                timestamp=now,
                transfer_type="hub_consolidation",
                from_exchange=ex,
                to_exchange="Bitfinex",
                symbol="USDT",
                amount_usd=available,
                fee_usd=fee,
            )
            self.transfers.append(transfer)
            transfers.append(transfer)
            logger.info(
                f"[Balance] Hub consolidation: {ex}→Bitfinex "
                f"${available:.2f} (fee=${fee:.4f})"
            )

        return transfers

    def sell_crypto_via_bitfinex(
        self,
        source_exchange: str,
        symbol: str,
        qty: float,
        bitfinex_bid: float,
    ) -> Transfer | None:
        """Transfer crypto from source exchange to Bitfinex and sell at 0% taker.

        Used for idle seller consolidation — frees crypto capital as USDT on
        Bitfinex where it can be redistributed for free.

        Returns the transfer record, or None if blocked by budget/cooldown.
        """
        if qty <= 0 or bitfinex_bid <= 0:
            return None
        if "Bitfinex" not in self._exchanges:
            return None

        gross = qty * bitfinex_bid
        min_transfer = max(20.0, self._trade_amount * 2)
        if gross < min_transfer:
            return None

        now = time.time()
        cooldown_key = f"{source_exchange}:crypto_consolidate"
        consolidation_cooldown = max(self._rebalance_cooldown, 600)
        if now - self._last_rebalance.get(cooldown_key, 0) < consolidation_cooldown:
            return None

        withdrawal_fee = self._get_withdrawal_fee(source_exchange)
        if not self._check_hourly_transfer_budget(withdrawal_fee):
            return None

        # Execute: move crypto out, sell at 0% on Bitfinex, credit USDT
        self.crypto[source_exchange][symbol] -= qty
        self.usdt["Bitfinex"] += gross  # 0% taker on Bitfinex
        if withdrawal_fee > 0:
            self.total_transfer_fees += withdrawal_fee
            self.total_external_transfer_fees += withdrawal_fee
            self._record_external_fee(withdrawal_fee)
        self._last_rebalance[cooldown_key] = now

        transfer = Transfer(
            timestamp=now,
            transfer_type="idle_crypto_consolidation",
            from_exchange=source_exchange,
            to_exchange="Bitfinex",
            symbol=symbol,
            amount_usd=gross,
            fee_usd=withdrawal_fee,
        )
        self.transfers.append(transfer)
        logger.info(
            f"[Balance] Idle crypto consolidation: {symbol} "
            f"{source_exchange}→Bitfinex, ${gross:.2f} "
            f"(withdrawal ${withdrawal_fee:.4f})"
        )
        return transfer

    def emergency_consolidate_to_bitfinex(self) -> list[Transfer]:
        """Emergency consolidation — moves all non-Bitfinex USDT to Bitfinex.

        Walks every exchange except Bitfinex sorted by withdrawal fee
        (cheapest first), transferring the full USDT balance regardless of
        cooldowns or hourly budget caps. Used after `_emergency_sell_all`
        when anomaly protection has paused trading and operator needs the
        capital safe on the Bitfinex hub.

        Returns the list of Transfer records executed (also appended to
        self.transfers and counted in total_external_transfer_fees).
        """
        if "Bitfinex" not in self._exchanges:
            return []

        transfers: list[Transfer] = []
        now = time.time()
        # Sort non-Bitfinex exchanges by withdrawal fee (cheapest first)
        sources = sorted(
            (ex for ex in self._exchanges if ex != "Bitfinex"),
            key=lambda ex: self._get_withdrawal_fee(ex),
        )
        for ex in sources:
            usdt = self.usdt.get(ex, 0.0)
            # Skip dust (smaller than withdrawal fee or $1, whichever is larger)
            fee = self._get_withdrawal_fee(ex, usdt)
            min_amount = max(1.0, fee * 1.5)
            if usdt < min_amount:
                continue
            # Move everything (fee paid from source side — net arrives on Bitfinex)
            self.usdt[ex] -= usdt
            net = max(0.0, usdt - fee)
            self.usdt["Bitfinex"] += net
            self.total_transfer_fees += fee
            self.total_external_transfer_fees += fee
            self._record_external_fee(fee)
            transfer = Transfer(
                timestamp=now,
                transfer_type="emergency_consolidate",
                from_exchange=ex,
                to_exchange="Bitfinex",
                symbol="USDT",
                amount_usd=usdt,
                fee_usd=fee,
            )
            self.transfers.append(transfer)
            transfers.append(transfer)
            logger.warning(
                f"[Anomaly] EMERGENCY_CONSOLIDATE {ex}→Bitfinex: "
                f"${usdt:.2f} (fee=${fee:.4f}, net=${net:.2f})"
            )
        return transfers

    def force_sell_crypto_via_bitfinex(
        self,
        source_exchange: str,
        symbol: str,
        qty: float,
        bitfinex_bid: float,
    ) -> dict:
        """Force-sell crypto via Bitfinex, bypassing all cooldowns and budget checks.

        Used by Hard Stop operator action — always executes, no gatekeeping.
        Returns result dict (not Transfer) — this is an operator action.
        """
        gross = qty * bitfinex_bid
        withdrawal_fee = self._get_withdrawal_fee(source_exchange)

        # Execute: move crypto out, sell at 0% on Bitfinex, credit USDT
        self.crypto[source_exchange][symbol] -= qty
        self.usdt["Bitfinex"] += gross  # 0% taker on Bitfinex
        if withdrawal_fee > 0:
            self.total_transfer_fees += withdrawal_fee
            self.total_external_transfer_fees += withdrawal_fee
            self._record_external_fee(withdrawal_fee)

        return {
            "gross": gross,
            "withdrawal_fee": withdrawal_fee,
            "taker_fee": 0.0,  # Bitfinex 0%
            "net": gross,
        }

    def rebalance_inventory_drift(
        self,
        symbol_exchange_pairs: list[tuple[str, str]],
        prices: dict[str, float],
        drift_threshold: float = 0.3,
    ) -> list[Transfer]:
        """Periodic inventory drift correction — Feature 4.

        For each (exchange, symbol) pair:
          - target_crypto_value = original allocated crypto USD (`_crypto_usd[ex][sym]`)
          - actual_crypto_value = current `crypto[ex][sym] * price`
          - If actual > target × (1 + threshold) → sell excess to USDT (internal sell)
          - If actual < target × (1 - threshold) → buy back to target (internal buy, if USDT available)

        Each correction uses the exchange's taker fee (internal trade — no withdrawal fee).
        Returns list of Transfer records logged with type "inventory_drift_sell"/"_buy".
        """
        transfers: list[Transfer] = []
        if not symbol_exchange_pairs or drift_threshold <= 0:
            return transfers

        now = time.time()
        # Aggregate per-exchange stats for summary log
        ex_actions: dict[str, dict] = {}

        for exchange, symbol in symbol_exchange_pairs:
            if exchange not in self._exchanges or exchange not in self.crypto:
                continue
            target = self._crypto_usd.get(exchange, {}).get(symbol, 0.0)
            if target <= 0:
                continue
            price = prices.get(symbol, 0.0)
            if price <= 0:
                continue

            qty = self.crypto[exchange].get(symbol, 0.0)
            actual = qty * price
            high_band = target * (1.0 + drift_threshold)
            low_band = target * (1.0 - drift_threshold)
            taker_fee = self._fee_manager.get_taker_fee(exchange) if self._fee_manager else 0.001

            stats = ex_actions.setdefault(exchange, {"sell_count": 0, "buy_count": 0, "skip_count": 0, "fee_total": 0.0, "value_total": 0.0})

            if actual > high_band:
                # Sell excess crypto to bring inventory back to target
                excess_usd = actual - target
                sell_qty = excess_usd / price
                if sell_qty > 0 and qty >= sell_qty:
                    fee_usd = excess_usd * taker_fee
                    self.crypto[exchange][symbol] -= sell_qty
                    self.usdt[exchange] += excess_usd - fee_usd
                    self.total_transfer_fees += fee_usd
                    transfer = Transfer(
                        timestamp=now,
                        transfer_type="inventory_drift_sell",
                        from_exchange=exchange,
                        to_exchange=exchange,
                        symbol=symbol,
                        amount_usd=excess_usd,
                        fee_usd=fee_usd,
                    )
                    self.transfers.append(transfer)
                    transfers.append(transfer)
                    stats["sell_count"] += 1
                    stats["fee_total"] += fee_usd
                    stats["value_total"] += excess_usd
                    drift_pct = (actual - target) / target * 100
                    logger.info(
                        f"[Inventory] DRIFT_SELL {symbol} on {exchange}: "
                        f"actual=${actual:.2f}/target=${target:.2f} (+{drift_pct:.1f}%), "
                        f"sold ${excess_usd:.2f} (fee ${fee_usd:.4f} @ {taker_fee*100:.3f}%)"
                    )
                else:
                    stats["skip_count"] += 1
                    logger.info(
                        f"[Inventory] DRIFT_SELL SKIPPED {symbol} on {exchange}: "
                        f"sell_qty={sell_qty:.6f} > qty={qty:.6f}"
                    )
            elif actual < low_band:
                # Buy back crypto using available USDT
                shortage_usd = target - actual
                available_usdt = self.available_usdt_for_trading(exchange)
                buy_usd = min(shortage_usd, available_usdt)
                if buy_usd > 0:
                    fee_usd = buy_usd * taker_fee
                    crypto_received = (buy_usd - fee_usd) / price
                    self.usdt[exchange] -= buy_usd
                    self.crypto[exchange][symbol] += crypto_received
                    self.total_transfer_fees += fee_usd
                    transfer = Transfer(
                        timestamp=now,
                        transfer_type="inventory_drift_buy",
                        from_exchange=exchange,
                        to_exchange=exchange,
                        symbol=symbol,
                        amount_usd=buy_usd,
                        fee_usd=fee_usd,
                    )
                    self.transfers.append(transfer)
                    transfers.append(transfer)
                    stats["buy_count"] += 1
                    stats["fee_total"] += fee_usd
                    stats["value_total"] += buy_usd
                    drift_pct = (actual - target) / target * 100
                    logger.info(
                        f"[Inventory] DRIFT_BUY {symbol} on {exchange}: "
                        f"actual=${actual:.2f}/target=${target:.2f} ({drift_pct:.1f}%), "
                        f"bought ${buy_usd:.2f} (fee ${fee_usd:.4f} @ {taker_fee*100:.3f}%) "
                        f"[shortage=${shortage_usd:.2f}, usdt_avail=${available_usdt:.2f}]"
                    )
                else:
                    stats["skip_count"] += 1
                    logger.info(
                        f"[Inventory] DRIFT_BUY SKIPPED {symbol} on {exchange}: "
                        f"shortage=${shortage_usd:.2f}, usdt_avail=${available_usdt:.2f}"
                    )

        # Per-exchange summary
        for ex, stats in ex_actions.items():
            if stats["sell_count"] + stats["buy_count"] + stats["skip_count"] > 0:
                logger.info(
                    f"[Inventory] {ex} summary: sells={stats['sell_count']}, "
                    f"buys={stats['buy_count']}, skipped={stats['skip_count']}, "
                    f"value=${stats['value_total']:.2f}, fees=${stats['fee_total']:.4f}"
                )
        return transfers

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
        buy_fee_model: str = "received",
        sell_fee_model: str = "received",
    ) -> dict | None:
        """
        Execute a simulated trade and update balances.

        buy_fee/sell_fee are decimal rates (e.g., 0.00075 for 0.075%).

        fee_model controls where the fee is deducted from (D-05):
          - "received" (default): fee deducted from received asset
            Buy: receive less crypto. Sell: receive less USDT.
          - "spent": fee added to spent amount
            Buy: spend more USDT. Sell: spend more crypto.
          - "token": fee deducted from discount token (BNB/BGB/KCS)
            Full qty received; fee tracked separately.

        When exchange_info is available, quantities are rounded DOWN to
        the exchange's lot_size_step (D-01) and unspent USDT stays in
        balance. Returns a dict with rounding details, or None if no
        exchange_info.
        """
        from decimal import Decimal, ROUND_DOWN

        info = self._exchange_info
        adjustment = None

        # Buy side: spend USDT, receive crypto
        coins_bought_raw = trade_amount / buy_price

        if buy_fee_model == "received":
            # Fee deducted from received crypto (default sim behavior)
            coins_after_fee_raw = coins_bought_raw * (1.0 - buy_fee)
        elif buy_fee_model == "spent":
            # Fee added to USDT spent, full crypto received
            coins_after_fee_raw = coins_bought_raw
        else:  # "token"
            # Full qty received, fee from discount token
            coins_after_fee_raw = coins_bought_raw

        if info:
            # Round quantity to exchange lot size (D-01)
            coins_after_fee_dec = info.round_quantity(
                buy_exchange, symbol, Decimal(str(coins_after_fee_raw))
            )
            coins_after_fee = float(coins_after_fee_dec)
            if buy_fee_model == "received":
                actual_buy_spend = coins_after_fee / (1.0 - buy_fee) * buy_price if coins_after_fee > 0 else 0.0
            elif buy_fee_model == "spent":
                actual_buy_spend = coins_after_fee * buy_price * (1.0 + buy_fee)
            else:  # "token"
                actual_buy_spend = coins_after_fee * buy_price
            buy_rounding_saved = trade_amount - actual_buy_spend
        else:
            coins_after_fee = coins_after_fee_raw
            if buy_fee_model == "spent":
                actual_buy_spend = trade_amount * (1.0 + buy_fee)
            elif buy_fee_model == "token":
                actual_buy_spend = trade_amount
            else:
                actual_buy_spend = trade_amount
            buy_rounding_saved = 0.0

        self.usdt[buy_exchange] -= actual_buy_spend
        self.crypto[buy_exchange][symbol] += coins_after_fee

        # Sell side: spend crypto, receive USDT
        coins_to_sell_raw = trade_amount / sell_price

        if info:
            coins_to_sell_dec = info.round_quantity(
                sell_exchange, symbol, Decimal(str(coins_to_sell_raw))
            )
            coins_to_sell = float(coins_to_sell_dec)
            if sell_fee_model == "received":
                usdt_received = coins_to_sell * sell_price * (1.0 - sell_fee)
            elif sell_fee_model == "spent":
                # Fee in crypto: sell more crypto but receive full USDT value
                usdt_received = coins_to_sell * sell_price
            else:  # "token"
                usdt_received = coins_to_sell * sell_price
            sell_rounding_loss = (coins_to_sell_raw - coins_to_sell) * sell_price * (1.0 - sell_fee)
        else:
            coins_to_sell = coins_to_sell_raw
            if sell_fee_model == "received":
                usdt_received = trade_amount * (1.0 - sell_fee)
            elif sell_fee_model == "spent":
                # Fee in crypto: need to sell more to cover fee
                usdt_received = trade_amount
            else:  # "token"
                usdt_received = trade_amount
            sell_rounding_loss = 0.0

        if sell_fee_model == "spent":
            # Fee charged in crypto (the spent asset)
            self.crypto[sell_exchange][symbol] -= coins_to_sell * (1.0 + sell_fee)
        else:
            self.crypto[sell_exchange][symbol] -= coins_to_sell
        self.usdt[sell_exchange] += usdt_received

        # D-18: Record trade time for demo sync grace period
        now = time.time()
        self.last_trade_time[buy_exchange] = now
        self.last_trade_time[sell_exchange] = now

        if info:
            total_rounding_impact = buy_rounding_saved - sell_rounding_loss
            adjustment = {
                "buy_qty_raw": coins_after_fee_raw,
                "buy_qty_rounded": coins_after_fee,
                "sell_qty_raw": coins_to_sell_raw,
                "sell_qty_rounded": coins_to_sell,
                "buy_rounding_saved_usd": buy_rounding_saved,
                "sell_rounding_loss_usd": sell_rounding_loss,
                "rounding_impact_usd": total_rounding_impact,
            }

        return adjustment

    def get_portfolio_value(
        self,
        prices: dict[str, float],
        hedge_pnl_usd: float = 0.0,
    ) -> float:
        """Calculate total portfolio value in USD.

        Includes spot USDT + spot crypto value + optional futures hedge
        unrealized PnL. When hedging is active (testnet/live), passing the
        hedge PnL keeps the metric representing real economic exposure —
        spot price moves are offset by opposing futures PnL, so peak/drawdown
        tracking reflects net portfolio risk instead of single-side noise.

        In shadow mode, hedge_pnl_usd is the simulated unrealized PnL on
        the would-be short. Passing it makes the drawdown signal a useful
        preview of what real-mode behavior would look like.
        """
        total = sum(self.usdt.values())
        for ex in self._exchanges:
            for sym, qty in self.crypto[ex].items():
                if qty > 0:
                    p = prices.get(sym, 0.0)
                    total += qty * p
        total += hedge_pnl_usd
        return total

    def get_balance_lines(self, prices: dict[str, float]) -> list[str]:
        """Get formatted balance summary lines for live display."""
        parts = []
        for ex in self._exchanges:
            ex_total = self.usdt[ex]
            for sym, qty in self.crypto[ex].items():
                if qty > 0:
                    ex_total += qty * prices.get(sym, 0.0)
            parts.append(f"{ex} ${ex_total:.0f}")
        portfolio = self.get_portfolio_value(prices)
        transfer_count = len(self.transfers)
        return [
            f"  Balances: {' | '.join(parts)} | "
            f"Transfers: {transfer_count} (${self.total_transfer_fees:.2f} fees) | "
            f"Portfolio: ${portfolio:.0f}"
        ]

    # ── State persistence ────────────────────────────────────────────────

    def to_state_dict(self) -> dict:
        """Serialize all mutable state to a JSON-serializable dict."""
        from dataclasses import asdict

        return {
            "usdt": dict(self.usdt),
            "crypto": {ex: dict(syms) for ex, syms in self.crypto.items()},
            "_crypto_usd": {ex: dict(syms) for ex, syms in self._crypto_usd.items()},
            "_initial_investment": self._initial_investment,
            "_initialized": self._initialized,
            "transfers": [asdict(t) for t in self.transfers],
            "total_transfer_fees": self.total_transfer_fees,
            "total_external_transfer_fees": self.total_external_transfer_fees,
            "skipped_trades": self.skipped_trades,
            "_last_rebalance": dict(self._last_rebalance),
            "_estimated_profit_per_trade": self._estimated_profit_per_trade,
            "last_trade_time": dict(self.last_trade_time),
            "_in_transit": [asdict(f) for f in self._in_transit],
            "_execution_mode": self._execution_mode,
            "_external_fee_log": list(self._external_fee_log),
            "_bitfinex_reserve_hard_floor": self._bitfinex_reserve_hard_floor,
        }

    def from_state_dict(self, data: dict) -> None:
        """Restore mutable state from a previously saved dict."""
        # Merge saved state with current exchanges (handle added/removed exchanges)
        saved_usdt = data["usdt"]
        saved_crypto = data["crypto"]
        saved_crypto_usd = data["_crypto_usd"]
        for ex in self._exchanges:
            if ex in saved_usdt:
                self.usdt[ex] = saved_usdt[ex]
            if ex in saved_crypto:
                self.crypto[ex] = saved_crypto[ex]
            if ex in saved_crypto_usd:
                self._crypto_usd[ex] = saved_crypto_usd[ex]
        self._initial_investment = data["_initial_investment"]
        self._initialized = data["_initialized"]
        self.transfers = [
            Transfer(
                timestamp=t["timestamp"],
                transfer_type=t["transfer_type"],
                from_exchange=t["from_exchange"],
                to_exchange=t["to_exchange"],
                symbol=t["symbol"],
                amount_usd=t["amount_usd"],
                fee_usd=t["fee_usd"],
            )
            for t in data.get("transfers", [])
        ]
        self.total_transfer_fees = data.get("total_transfer_fees", 0.0)
        self.total_external_transfer_fees = data.get("total_external_transfer_fees", 0.0)
        self.skipped_trades = data.get("skipped_trades", 0)
        self._last_rebalance = data.get("_last_rebalance", {})
        self._estimated_profit_per_trade = data.get("_estimated_profit_per_trade", 0.02)
        self.last_trade_time = data.get("last_trade_time", {})
        self._in_transit = [
            InTransitFund(**f) for f in data.get("_in_transit", [])
        ]
        self._execution_mode = data.get("_execution_mode", "simulation")
        self._external_fee_log = deque(
            tuple(x) for x in data.get("_external_fee_log", [])
        )
        if "_bitfinex_reserve_hard_floor" in data:
            self._bitfinex_reserve_hard_floor = data["_bitfinex_reserve_hard_floor"]
            self._bitfinex_reserve_hard_floor_amount = (
                self._initial_investment * self._bitfinex_reserve_hard_floor
            )
