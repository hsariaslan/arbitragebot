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
from collections import defaultdict, deque
from dataclasses import dataclass

from config import (
    ACTIVE_EXCHANGES,
    ACTIVE_SYMBOLS,
    EXCHANGE_TAKER_FEES,
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
        bitfinex_reserve_pct: float = 0.15,           # DEPRECATED — used only for migration of old state files
        bitfinex_reserve_hard_floor: float = 0.05,    # DEPRECATED
        custody_hub_exchange: str = "Bybit",
        custody_hub_network: str = "Aptos",
        trading_float_multiplier: float = 8.0,
        trading_float_replenish_trigger: float = 3.0,
        trading_float_overflow_multiplier: float = 1.5,
        futures_reserve_usdt: float = 0.0,
        binance_spot_bnb_reserved_usd: float = 0.0,
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
        self._estimated_profit_per_trade: float = 0.0
        self._allocations = allocations
        self.binance_futures_usdt: float = max(0.0, float(futures_reserve_usdt))
        self.binance_spot_bnb: float = 0.0
        self.binance_futures_bnb: float = 0.0
        self._binance_spot_bnb_reserved_usd: float = max(
            0.0, float(binance_spot_bnb_reserved_usd)
        )
        self._bnb_reserve_block_log_count: dict[str, int] = defaultdict(int)

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
            self._initial_investment += self.binance_futures_usdt
        else:
            # Uniform default: $80 USDT + $80 crypto per symbol per exchange
            half = INITIAL_BALANCE_PER_SYMBOL / 2.0
            self.usdt = {ex: half * len(self._symbols) for ex in self._exchanges}
            self._crypto_usd = {
                ex: {sym: half for sym in self._symbols} for ex in self._exchanges
            }
            self._initial_investment = (
                INITIAL_BALANCE_PER_SYMBOL * len(self._symbols) * len(self._exchanges)
                + self.binance_futures_usdt
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

        # Capital architecture (v0.30+):
        #   - Custody hub (default Bybit): bulk USDT lives here. Third-party PoR
        #     audited, stress-tested. Replaces Bitfinex as parking location.
        #   - Trading float (Bitfinex): small working balance for the 0%-taker
        #     buy leg of the preferred Bitfinex+MEXC route. Sized by
        #     trade_amount × multiplier — bounded in dollars regardless of
        #     capital growth.
        #   - Replenish: custody → Bitfinex via Aptos $0 when float < trigger.
        #   - Overflow: Bitfinex → custody via Aptos $0 when float > target × overflow.
        self._custody_hub_exchange: str = custody_hub_exchange
        self._custody_hub_network: str = custody_hub_network
        self._trading_float_multiplier: float = trading_float_multiplier
        self._trading_float_replenish_trigger: float = trading_float_replenish_trigger
        self._trading_float_overflow_multiplier: float = trading_float_overflow_multiplier
        # `_bitfinex_reserve_target` field name kept for backward state-dict
        # compatibility, but its semantics are now: dollar amount of USDT to
        # keep on Bitfinex as a working trading float (= trade_amount × multiplier).
        self._bitfinex_reserve_target: float = trade_amount * trading_float_multiplier
        # Legacy fields kept only for state-dict round-trip compatibility
        self._bitfinex_reserve_pct: float = bitfinex_reserve_pct
        self._bitfinex_reserve_hard_floor: float = bitfinex_reserve_hard_floor
        self._bitfinex_reserve_hard_floor_amount: float = 0.0  # No longer used; replaced by replenish trigger

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

    def _paid_transfer_worthwhile(
        self,
        fee_usd: float,
        context: str,
        *,
        max_trades_to_recoup: float = 50.0,
    ) -> bool:
        """Gate paid rebalance-class moves until realized edge can repay them."""
        fee = max(0.0, float(fee_usd))
        if fee <= 0.02:
            return True
        if not self._adaptive_mode:
            return True

        est = max(0.0, float(self._estimated_profit_per_trade or 0.0))
        if est <= 0:
            logger.debug(
                f"[Balance] {context} skipped: fee ${fee:.4f} with no positive "
                "realized profit estimate"
            )
            return False

        trades_to_recoup = fee / est
        if trades_to_recoup > max_trades_to_recoup:
            logger.debug(
                f"[Balance] {context} skipped: fee ${fee:.4f} needs "
                f"{trades_to_recoup:.0f} trades to recoup"
            )
            return False
        return True

    def _get_withdrawal_fee(self, exchange: str, amount: float = 0.0) -> float:
        """Get withdrawal fee for an exchange, using TransferFeeManager if available."""
        if self._transfer_fee_mgr:
            return self._transfer_fee_mgr.get_withdrawal_fee(exchange, amount)
        return 1.0

    def _available_usdt_for_rebalance(self, exchange: str) -> float:
        """USDT available for rebalance on an exchange, protecting Bitfinex reserve."""
        usdt = self.usdt.get(exchange, 0.0)
        if exchange == "Bitfinex" and self._bitfinex_reserve_target > 0:
            return max(0.0, usdt - self._bitfinex_reserve_target)
        return usdt

    def available_usdt_for_trading(self, exchange: str) -> float:
        """USDT available for trading on an exchange, protecting Bitfinex reserve.

        Unlike _available_usdt_for_rebalance (used for transfer source selection),
        this protects the reserve from being spent by normal trade execution.
        """
        usdt = self.usdt.get(exchange, 0.0)
        if exchange == "Bitfinex" and self._bitfinex_reserve_target > 0:
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
            self._initial_investment += self.binance_futures_usdt
        else:
            half = INITIAL_BALANCE_PER_SYMBOL / 2.0
            self.usdt = {ex: half * len(self._symbols) for ex in self._exchanges}
            self._crypto_usd = {
                ex: {sym: half for sym in self._symbols} for ex in self._exchanges
            }
            self._initial_investment = (
                INITIAL_BALANCE_PER_SYMBOL * len(self._symbols) * len(self._exchanges)
                + self.binance_futures_usdt
            )

        # Reset crypto quantities and initialization
        self.crypto = {
            ex: {sym: 0.0 for sym in self._symbols} for ex in self._exchanges
        }
        self._initialized = False
        self._last_rebalance.clear()
        self._max_rebalance = self._trade_amount * 4

        # Recompute trading float target from the new trade_amount (v0.30+).
        # Float = trade_amount × multiplier — bounded in dollars, not capital%.
        self._bitfinex_reserve_target = (
            self._trade_amount * self._trading_float_multiplier
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
            + (
                f" | Binance Futures reserve: ${self.binance_futures_usdt:.0f}"
                if self.binance_futures_usdt > 0
                else ""
            )
        )

    def set_futures_reserve_usdt(self, amount: float) -> None:
        """Set the simulated/accounting Binance USD-M Futures reserve balance."""
        self.binance_futures_usdt = max(0.0, float(amount))

    def set_binance_spot_bnb_reserved_usd(self, amount: float) -> None:
        """Protect this much Binance Spot BNB value from normal BNBUSDT sells."""
        self._binance_spot_bnb_reserved_usd = max(0.0, float(amount))

    @property
    def binance_spot_bnb_reserved_usd(self) -> float:
        return max(0.0, float(getattr(self, "_binance_spot_bnb_reserved_usd", 0.0)))

    @staticmethod
    def _is_binance_bnbusdt(exchange: str, symbol: str) -> bool:
        return exchange == "Binance" and symbol == "BNBUSDT"

    def crypto_trade_availability(
        self,
        exchange: str,
        symbol: str,
        price: float,
    ) -> dict[str, float]:
        """Return crypto quantity/value available to normal trading.

        Binance Spot BNB is also the fee-discount/top-up asset. When the bot
        trades BNBUSDT on Binance, keep the configured BNB floor unavailable
        to sell legs so an arbitrage fill cannot drain the fee reserve.
        """
        held_qty = max(0.0, float(self.crypto.get(exchange, {}).get(symbol, 0.0) or 0.0))
        px = max(0.0, float(price or 0.0))
        reserve_usd = 0.0
        reserve_qty = 0.0
        if self._is_binance_bnbusdt(exchange, symbol):
            reserve_usd = self.binance_spot_bnb_reserved_usd
            if px > 0 and reserve_usd > 0:
                reserve_qty = reserve_usd / px
        available_qty = max(0.0, held_qty - reserve_qty)
        return {
            "held_qty": held_qty,
            "held_usd": held_qty * px,
            "reserve_qty": reserve_qty,
            "reserve_usd": reserve_qty * px,
            "available_qty": available_qty,
            "available_usd": available_qty * px,
        }

    def _log_bnb_reserve_sell_block(
        self,
        exchange: str,
        symbol: str,
        trade_amount: float,
        availability: dict[str, float],
    ) -> None:
        key = f"{exchange}:{symbol}"
        self._bnb_reserve_block_log_count[key] += 1
        count = self._bnb_reserve_block_log_count[key]
        if count == 1 or count % 100 == 0:
            logger.info(
                f"[Balance] BNB_RESERVE_SELL_BLOCK {exchange} {symbol}: "
                f"held=${availability.get('held_usd', 0.0):.2f} "
                f"reserve_floor=${availability.get('reserve_usd', 0.0):.2f} "
                f"available=${availability.get('available_usd', 0.0):.2f} "
                f"need=${trade_amount:.2f} count={count}"
            )

    def buy_spot_bnb_with_usdt(
        self,
        amount_usd: float,
        price_usd: float,
        fee_rate: float | None = None,
    ) -> dict:
        """Simulate buying BNB in the Binance Spot wallet with Binance USDT."""
        price = float(price_usd)
        requested = max(0.0, float(amount_usd))
        available = max(0.0, float(self.usdt.get("Binance", 0.0)))
        if requested <= 0:
            return {"success": False, "error": "amount_must_be_positive"}
        if price <= 0:
            return {"success": False, "error": "price_unavailable"}
        if available <= 0:
            return {"success": False, "error": "binance_usdt_unavailable"}

        spent = min(requested, available)
        gross_qty = spent / price
        rate = (
            max(0.0, float(fee_rate))
            if fee_rate is not None
            else max(0.0, float(EXCHANGE_TAKER_FEES.get("Binance", 0.00075)))
        )
        fee_bnb = gross_qty * rate
        net_qty = max(0.0, gross_qty - fee_bnb)
        if net_qty <= 0:
            return {"success": False, "error": "net_bnb_zero_after_fee"}

        self.usdt["Binance"] = available - spent
        self.binance_spot_bnb += net_qty
        return {
            "success": True,
            "requested_usd": requested,
            "spent_usd": spent,
            "price_usd": price,
            "gross_qty": gross_qty,
            "fee_bnb": fee_bnb,
            "net_qty": net_qty,
            "fee_rate": rate,
            "spot_qty": self.binance_spot_bnb,
        }

    def transfer_spot_bnb_to_futures(self, qty: float) -> dict:
        """Simulate moving BNB from Binance Spot to USD-M Futures."""
        requested = max(0.0, float(qty))
        available = max(0.0, float(getattr(self, "binance_spot_bnb", 0.0) or 0.0))
        if requested <= 0:
            return {"success": False, "error": "amount_must_be_positive"}
        if available <= 0:
            return {"success": False, "error": "spot_bnb_unavailable"}

        moved = min(requested, available)
        self.binance_spot_bnb = available - moved
        self.binance_futures_bnb += moved
        return {
            "success": True,
            "direction": "spot_to_futures",
            "asset": "BNB",
            "amount": moved,
            "spot_qty": self.binance_spot_bnb,
            "futures_qty": self.binance_futures_bnb,
        }

    def deduct_spot_bnb_fee(
        self,
        exchange: str,
        fee_usd: float,
        bnb_price_usd: float,
        context: str = "",
    ) -> float:
        """Deduct simulated BNB for token-paid Binance Spot trading fees."""
        if exchange != "Binance":
            return 0.0
        fee_value = max(0.0, float(fee_usd))
        price = max(0.0, float(bnb_price_usd))
        if fee_value <= 0 or price <= 0:
            return 0.0
        qty = fee_value / price
        available = max(0.0, float(getattr(self, "binance_spot_bnb", 0.0) or 0.0))
        deducted = min(qty, available)
        self.binance_spot_bnb = max(0.0, available - deducted)
        if deducted < qty:
            logger.warning(
                f"[Balance] Binance Spot BNB fee reserve exhausted "
                f"({context}): needed={qty:.8f} BNB, deducted={deducted:.8f} BNB"
            )
        return deducted

    def deduct_futures_bnb_fee(
        self,
        fee_usd: float,
        bnb_price_usd: float,
        context: str = "",
    ) -> float:
        """Deduct simulated BNB for Binance USD-M Futures fee payments."""
        fee_value = max(0.0, float(fee_usd))
        price = max(0.0, float(bnb_price_usd))
        if fee_value <= 0 or price <= 0:
            return 0.0
        qty = fee_value / price
        available = max(0.0, float(getattr(self, "binance_futures_bnb", 0.0) or 0.0))
        deducted = min(qty, available)
        self.binance_futures_bnb = max(0.0, available - deducted)
        if deducted < qty:
            logger.warning(
                f"[Balance] Binance Futures BNB fee reserve exhausted "
                f"({context}): needed={qty:.8f} BNB, deducted={deducted:.8f} BNB"
            )
        return deducted

    def _can_pay_spot_bnb_fee(
        self,
        exchange: str,
        fee_usd: float,
        bnb_price_usd: float,
    ) -> bool:
        if exchange != "Binance":
            return True
        fee_value = max(0.0, float(fee_usd))
        price = max(0.0, float(bnb_price_usd))
        if fee_value <= 0:
            return True
        if price <= 0:
            return False
        available_value = (
            max(0.0, float(getattr(self, "binance_spot_bnb", 0.0) or 0.0))
            * price
        )
        return available_value >= fee_value

    def _non_token_fee_rate(self, exchange: str, current_rate: float) -> float:
        configs = getattr(self._fee_manager, "_configs", {}) if self._fee_manager else {}
        cfg = configs.get(exchange) if isinstance(configs, dict) else None
        base_rate = getattr(cfg, "base_taker_rate", None)
        try:
            return max(float(current_rate), float(base_rate))
        except (TypeError, ValueError):
            return float(current_rate)

    def resolve_fee_model_for_trade(
        self,
        exchange: str,
        symbol: str,
        trade_amount: float,
        fee_rate: float,
        fee_model: str,
        bnb_price: float,
        *,
        side: str = "",
        log_fallback: bool = False,
    ) -> dict:
        """Return the effective fee model/rate before a simulated mutation.

        Binance token-paid fees depend on the BNB reserve actually being able
        to fund the fee. If it cannot, the trade should be scored/executed with
        the non-discounted received-asset fee model.
        """
        rate = max(0.0, float(fee_rate))
        model = str(fee_model or "received")
        fee_usd = max(0.0, float(trade_amount)) * rate
        fallback = False
        if model == "token" and not self._can_pay_spot_bnb_fee(exchange, fee_usd, bnb_price):
            fallback = True
            model = "received"
            rate = self._non_token_fee_rate(exchange, rate)
            fee_usd = max(0.0, float(trade_amount)) * rate
            if log_fallback:
                label = f" on {side}" if side else ""
                logger.warning(
                    f"[Balance] {exchange} token-fee fallback{label} {symbol}: "
                    f"bnb_price=${bnb_price:.4f}, fee=${fee_usd:.4f}"
                )
        return {
            "fee_rate": rate,
            "fee_model": model,
            "fee_usd": fee_usd,
            "fallback": fallback,
        }

    def _round_trade_qty(self, exchange: str, symbol: str, qty: float) -> float:
        if qty <= 0:
            return 0.0
        if not self._exchange_info:
            return float(qty)
        from decimal import Decimal

        rounded = self._exchange_info.round_quantity(
            exchange, symbol, Decimal(str(qty))
        )
        return max(0.0, float(rounded))

    def _order_meets_exchange_minimums(
        self,
        exchange: str,
        symbol: str,
        qty: float,
        price: float,
        side: str,
    ) -> tuple[bool, str]:
        if qty <= 0 or price <= 0:
            return False, f"{side}_qty_zero"
        if not self._exchange_info:
            return True, ""
        from decimal import Decimal

        rules = self._exchange_info.get_rules(exchange, symbol)
        if not rules:
            return True, ""
        qty_d = Decimal(str(qty))
        price_d = Decimal(str(price))
        if not self._exchange_info.check_min_qty(exchange, symbol, qty_d):
            return False, f"{side}_min_qty {float(rules.min_qty)}"
        if not self._exchange_info.check_min_notional(exchange, symbol, qty_d, price_d):
            return False, f"{side}_min_notional ${float(rules.min_notional):.2f}"
        return True, ""

    def _build_trade_adjustment(
        self,
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        trade_amount: float,
        buy_price: float,
        sell_price: float,
        buy_fee: float,
        sell_fee: float,
        buy_fee_model: str,
        sell_fee_model: str,
        bnb_price: float,
        *,
        mutate: bool,
    ) -> dict:
        """Build or apply a same-base-quantity trade mutation.

        The requested trade_amount is a buy-side quote budget. The executable
        order quantity is rounded down on both exchanges and capped by the
        sell-side inventory and buy-side USDT actually available. P&L is then
        computed from the same base quantity on both legs, with all fee models
        converted to USD cost.
        """
        requested = max(0.0, float(trade_amount))
        buy_px = max(0.0, float(buy_price))
        sell_px = max(0.0, float(sell_price))
        if requested <= 0 or buy_px <= 0 or sell_px <= 0:
            return {"aborted": True, "reason": "invalid_trade_inputs"}

        buy_fee_info = self.resolve_fee_model_for_trade(
            buy_exchange,
            symbol,
            requested,
            buy_fee,
            buy_fee_model,
            bnb_price,
            side="buy",
            log_fallback=mutate,
        )
        sell_fee_info = self.resolve_fee_model_for_trade(
            sell_exchange,
            symbol,
            requested,
            sell_fee,
            sell_fee_model,
            bnb_price,
            side="sell",
            log_fallback=mutate,
        )
        buy_fee = float(buy_fee_info["fee_rate"])
        buy_fee_model = str(buy_fee_info["fee_model"])
        sell_fee = float(sell_fee_info["fee_rate"])
        sell_fee_model = str(sell_fee_info["fee_model"])

        raw_qty = requested / buy_px
        buy_qty_limit = self._round_trade_qty(buy_exchange, symbol, raw_qty)
        sell_qty_limit = self._round_trade_qty(sell_exchange, symbol, raw_qty)

        buy_spend_multiplier = 1.0 + buy_fee if buy_fee_model == "spent" else 1.0
        buy_usdt_available = self.available_usdt_for_trading(buy_exchange)
        max_buy_qty_by_usdt = (
            buy_usdt_available / (buy_px * buy_spend_multiplier)
            if buy_px > 0 and buy_spend_multiplier > 0
            else 0.0
        )
        buy_balance_qty_limit = self._round_trade_qty(
            buy_exchange, symbol, max_buy_qty_by_usdt
        )

        availability = self.crypto_trade_availability(sell_exchange, symbol, sell_px)
        sell_spend_multiplier = 1.0 + sell_fee if sell_fee_model == "spent" else 1.0
        max_sell_qty_by_inventory = (
            availability["available_qty"] / sell_spend_multiplier
            if sell_spend_multiplier > 0
            else 0.0
        )
        sell_inventory_qty_limit = self._round_trade_qty(
            sell_exchange, symbol, max_sell_qty_by_inventory
        )

        order_qty = min(
            buy_qty_limit,
            sell_qty_limit,
            buy_balance_qty_limit,
            sell_inventory_qty_limit,
        )
        order_qty = self._round_trade_qty(buy_exchange, symbol, order_qty)
        order_qty = self._round_trade_qty(sell_exchange, symbol, order_qty)

        if (
            self._is_binance_bnbusdt(sell_exchange, symbol)
            and order_qty < min(buy_qty_limit, sell_qty_limit)
        ):
            self._log_bnb_reserve_sell_block(
                sell_exchange, symbol, requested, availability
            )

        if order_qty <= 0:
            return {
                "aborted": True,
                "reason": "rounded_or_available_qty_zero",
                "buy_qty_limit": buy_qty_limit,
                "sell_qty_limit": sell_qty_limit,
                "buy_qty_available": buy_balance_qty_limit,
                "sell_qty_available": sell_inventory_qty_limit,
            }

        buy_ok, buy_reason = self._order_meets_exchange_minimums(
            buy_exchange, symbol, order_qty, buy_px, "buy"
        )
        if not buy_ok:
            return {"aborted": True, "reason": buy_reason, "order_qty": order_qty}
        sell_ok, sell_reason = self._order_meets_exchange_minimums(
            sell_exchange, symbol, order_qty, sell_px, "sell"
        )
        if not sell_ok:
            return {"aborted": True, "reason": sell_reason, "order_qty": order_qty}

        buy_notional = order_qty * buy_px
        sell_notional = order_qty * sell_px
        buy_fee_usd = buy_notional * buy_fee
        sell_fee_usd = sell_notional * sell_fee

        actual_buy_spend = buy_notional + (
            buy_fee_usd if buy_fee_model == "spent" else 0.0
        )
        buy_qty_received = order_qty
        if buy_fee_model == "received":
            buy_qty_received = max(0.0, order_qty * (1.0 - buy_fee))

        sell_qty_spent = order_qty
        if sell_fee_model == "spent":
            sell_qty_spent = order_qty * (1.0 + sell_fee)
        actual_sell_received = sell_notional - (
            sell_fee_usd if sell_fee_model == "received" else 0.0
        )

        if actual_buy_spend > buy_usdt_available + 1e-12:
            return {
                "aborted": True,
                "reason": "buy_usdt_insufficient_after_fees",
                "required_usdt": actual_buy_spend,
                "available_usdt": buy_usdt_available,
            }
        if sell_qty_spent > availability["available_qty"] + 1e-12:
            return {
                "aborted": True,
                "reason": "sell_inventory_insufficient_after_fees",
                "sell_qty_required": sell_qty_spent,
                "sell_qty_available": availability["available_qty"],
                "reserve_qty": availability["reserve_qty"],
                "reserve_usd": availability["reserve_usd"],
            }

        buy_token_fee_usd = buy_fee_usd if buy_fee_model == "token" else 0.0
        sell_token_fee_usd = sell_fee_usd if sell_fee_model == "token" else 0.0
        actual_profit_usd = sell_notional - buy_notional - buy_fee_usd - sell_fee_usd

        if mutate:
            self.usdt[buy_exchange] -= actual_buy_spend
            self.crypto[buy_exchange][symbol] += buy_qty_received
            self.crypto[sell_exchange][symbol] -= sell_qty_spent
            self.usdt[sell_exchange] += actual_sell_received
            if buy_fee_model == "token":
                self.deduct_spot_bnb_fee(
                    buy_exchange,
                    buy_token_fee_usd,
                    bnb_price,
                    context=f"buy {symbol}",
                )
            if sell_fee_model == "token":
                self.deduct_spot_bnb_fee(
                    sell_exchange,
                    sell_token_fee_usd,
                    bnb_price,
                    context=f"sell {symbol}",
                )
            now = time.time()
            self.last_trade_time[buy_exchange] = now
            self.last_trade_time[sell_exchange] = now

        buy_rounding_saved = requested - buy_notional
        sell_rounding_loss = max(0.0, (raw_qty - order_qty) * sell_px)
        total_rounding_impact = buy_rounding_saved - sell_rounding_loss
        return {
            "buy_qty_raw": raw_qty,
            "buy_qty_rounded": order_qty,
            "buy_qty_received": buy_qty_received,
            "sell_qty_raw": raw_qty,
            "sell_qty_rounded": order_qty,
            "sell_qty_spent": sell_qty_spent,
            "order_qty": order_qty,
            "actual_buy_notional_usd": buy_notional,
            "actual_sell_notional_usd": sell_notional,
            "actual_buy_spend_usd": actual_buy_spend,
            "actual_sell_received_usd": actual_sell_received,
            "buy_fee_rate": buy_fee,
            "sell_fee_rate": sell_fee,
            "buy_fee_model": buy_fee_model,
            "sell_fee_model": sell_fee_model,
            "buy_fee_fallback": bool(buy_fee_info.get("fallback")),
            "sell_fee_fallback": bool(sell_fee_info.get("fallback")),
            "buy_fee_usd": buy_fee_usd,
            "sell_fee_usd": sell_fee_usd,
            "buy_token_fee_usd": buy_token_fee_usd,
            "sell_token_fee_usd": sell_token_fee_usd,
            "token_fee_usd": buy_token_fee_usd + sell_token_fee_usd,
            "actual_profit_usd": actual_profit_usd,
            "buy_rounding_saved_usd": buy_rounding_saved,
            "sell_rounding_loss_usd": sell_rounding_loss,
            "rounding_impact_usd": total_rounding_impact,
        }

    def preview_trade(
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
        bnb_price: float = 0.0,
    ) -> dict:
        return self._build_trade_adjustment(
            buy_exchange,
            sell_exchange,
            symbol,
            trade_amount,
            buy_price,
            sell_price,
            buy_fee,
            sell_fee,
            buy_fee_model,
            sell_fee_model,
            bnb_price,
            mutate=False,
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
        availability = self.crypto_trade_availability(sell_exchange, symbol, sell_price)
        crypto_value = availability["available_usd"]
        has_crypto = crypto_value >= trade_amount
        if (
            not has_crypto
            and self._is_binance_bnbusdt(sell_exchange, symbol)
            and availability["reserve_qty"] > 0
            and availability["held_usd"] >= trade_amount
        ):
            self._log_bnb_reserve_sell_block(
                sell_exchange, symbol, trade_amount, availability
            )
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
        max_external_fee_usd: float | None = None,
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
                sell_exchange,
                symbol,
                prices.get(symbol, 0.0),
                now,
                max_external_fee_usd=max_external_fee_usd,
            )
            if transfer:
                transfers.append(transfer)

        # --- Rebalance USDT on buy exchange ---
        has_usdt, has_crypto = self.can_execute(
            buy_exchange, sell_exchange, symbol, trade_amount, sell_price
        )
        if not has_usdt:
            transfer = self._rebalance_usdt(
                buy_exchange,
                prices,
                now,
                max_external_fee_usd=max_external_fee_usd,
            )
            if transfer:
                transfers.append(transfer)

        return transfers

    def preview_refill_rebalance(
        self,
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        trade_amount: float,
        prices: dict[str, float],
        max_external_fee_usd: float = 0.10,
    ) -> dict:
        """Dry-run whether a missed trade can be fixed as a cheap refill.

        Used by weak-regime gating: allow balance refills that are local or
        near-free, but keep expensive cross-exchange rotation suppressed.
        The actual rebalance still runs normal cooldown/ROI/hourly-cap checks.
        """
        sell_price = prices.get(symbol, 0.0)
        if sell_price <= 0:
            return {"allowed": False, "reason": "missing_price", "plan": []}

        has_usdt, has_crypto = self.can_execute(
            buy_exchange, sell_exchange, symbol, trade_amount, sell_price
        )
        plan: list[dict] = []
        if not has_crypto:
            plan.append(self._preview_crypto_refill(
                sell_exchange, symbol, sell_price, max_external_fee_usd
            ))
        if not has_usdt:
            plan.append(self._preview_usdt_refill(
                buy_exchange, prices, max_external_fee_usd
            ))
        if not plan:
            return {"allowed": True, "reason": "no_refill_needed", "plan": []}

        blocked = [p for p in plan if not p.get("allowed")]
        if blocked:
            return {
                "allowed": False,
                "reason": ";".join(str(p.get("reason", "blocked")) for p in blocked),
                "plan": plan,
            }
        types = ",".join(str(p.get("type", "unknown")) for p in plan)
        return {"allowed": True, "reason": f"cheap_refill:{types}", "plan": plan}

    def _preview_usdt_refill(
        self,
        exchange: str,
        prices: dict[str, float],
        max_external_fee_usd: float,
    ) -> dict:
        rebal = self.compute_rebalance_amount(exchange) if self._adaptive_mode else self._rebalance_amount
        buf = self._rebalance_buffer

        internal_cost = float("inf")
        internal_sym = None
        best_value = 0.0
        for sym in self._symbols:
            p = prices.get(sym, 0.0)
            val = self.crypto_trade_availability(exchange, sym, p)["available_usd"]
            if val > best_value:
                best_value = val
                internal_sym = sym
        if internal_sym and best_value >= rebal + buf:
            fee_rate = self._fee_manager.get_taker_fee(exchange) if self._fee_manager else 0.001
            internal_cost = rebal * fee_rate

        external_cost = float("inf")
        external_source = None
        eligible = [
            ex for ex in self._exchanges
            if ex != exchange and self._available_usdt_for_rebalance(ex) >= rebal + buf
        ]
        if not eligible:
            min_rebal = self._trade_amount
            eligible = [
                ex for ex in self._exchanges
                if ex != exchange and self._available_usdt_for_rebalance(ex) >= min_rebal + buf
            ]
        if eligible:
            external_source = min(eligible, key=lambda ex: self._get_withdrawal_fee(ex))
            external_cost = self._get_withdrawal_fee(external_source)

        if external_source and external_cost <= internal_cost:
            if external_cost <= max_external_fee_usd:
                return {
                    "allowed": True,
                    "type": "external_usdt",
                    "fee_usd": external_cost,
                    "from_exchange": external_source,
                    "to_exchange": exchange,
                }
            return {
                "allowed": False,
                "reason": f"external_usdt_fee>${max_external_fee_usd:.2f}",
                "type": "external_usdt",
                "fee_usd": external_cost,
            }

        if internal_cost < float("inf"):
            return {
                "allowed": True,
                "type": "internal_sell",
                "fee_usd": internal_cost,
                "to_exchange": exchange,
            }

        return {
            "allowed": False,
            "reason": "no_usdt_refill_source",
            "best_other_usdt": max(
                (self._available_usdt_for_rebalance(ex) for ex in self._exchanges if ex != exchange),
                default=0.0,
            ),
            "best_crypto_value": best_value,
        }

    def _preview_crypto_refill(
        self,
        exchange: str,
        symbol: str,
        price: float,
        max_external_fee_usd: float,
    ) -> dict:
        rebal = self.compute_rebalance_amount(exchange, symbol) if self._adaptive_mode else self._rebalance_amount
        crypto_sources = []
        for ex in self._exchanges:
            if ex == exchange:
                continue
            crypto_val = self.crypto_trade_availability(ex, symbol, price)["available_usd"]
            if crypto_val >= rebal * 1.2:
                crypto_sources.append(ex)
        if not crypto_sources:
            min_rebal = self._trade_amount
            for ex in self._exchanges:
                if ex == exchange:
                    continue
                crypto_val = self.crypto_trade_availability(ex, symbol, price)["available_usd"]
                if crypto_val >= min_rebal * 1.2:
                    crypto_sources.append(ex)
                    rebal = min_rebal

        internal_buy_cost = rebal * (self._fee_manager.get_taker_fee(exchange) if self._fee_manager else 0.001)
        if crypto_sources:
            best_source = min(crypto_sources, key=lambda ex: self._get_withdrawal_fee(ex))
            external_cost = self._get_withdrawal_fee(best_source)
            if external_cost < internal_buy_cost:
                if external_cost <= max_external_fee_usd:
                    return {
                        "allowed": True,
                        "type": "external_crypto",
                        "fee_usd": external_cost,
                        "from_exchange": best_source,
                        "to_exchange": exchange,
                    }
                return {
                    "allowed": False,
                    "reason": f"external_crypto_fee>${max_external_fee_usd:.2f}",
                    "type": "external_crypto",
                    "fee_usd": external_cost,
                }

        if self.usdt.get(exchange, 0.0) >= rebal:
            return {
                "allowed": True,
                "type": "internal_buy",
                "fee_usd": internal_buy_cost,
                "to_exchange": exchange,
            }

        eligible = [
            ex for ex in self._exchanges
            if ex != exchange and self._available_usdt_for_rebalance(ex) >= rebal + self._rebalance_buffer
        ]
        if eligible:
            best_source = min(eligible, key=lambda ex: self._get_withdrawal_fee(ex))
            external_cost = self._get_withdrawal_fee(best_source)
            if external_cost <= max_external_fee_usd:
                return {
                    "allowed": True,
                    "type": "external_usdt_buy",
                    "fee_usd": external_cost,
                    "from_exchange": best_source,
                    "to_exchange": exchange,
                }
            return {
                "allowed": False,
                "reason": f"external_usdt_buy_fee>${max_external_fee_usd:.2f}",
                "type": "external_usdt_buy",
                "fee_usd": external_cost,
            }

        return {"allowed": False, "reason": "no_crypto_refill_source"}

    def _rebalance_usdt(
        self,
        exchange: str,
        prices: dict[str, float],
        now: float,
        max_external_fee_usd: float | None = None,
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

            if not self._paid_transfer_worthwhile(
                external_cost,
                f"External transfer {external_source}→{exchange}",
            ):
                external_cost = float("inf")
                external_source = None

            # Hourly external transfer budget check
            if external_source and not self._check_hourly_transfer_budget(external_cost):
                external_cost = float("inf")
                external_source = None
            if (
                external_source
                and max_external_fee_usd is not None
                and external_cost > max_external_fee_usd
            ):
                logger.debug(
                    f"[Balance] External transfer {external_source}→{exchange} "
                    f"blocked by weak-regime refill cap: "
                    f"${external_cost:.2f} > ${max_external_fee_usd:.2f}"
                )
                external_cost = float("inf")
                external_source = None

        # Internal option: sell crypto for USDT (percentage taker fee)
        internal_cost = float("inf")
        internal_sym = None
        internal_price = 0.0
        best_value = 0.0
        for sym in self._symbols:
            p = prices.get(sym, 0.0)
            val = self.crypto_trade_availability(exchange, sym, p)["available_usd"]
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

        if internal_sym and internal_cost < float("inf") and not self._paid_transfer_worthwhile(
            internal_cost,
            f"Internal sell {internal_sym} on {exchange}",
        ):
            internal_cost = float("inf")
            internal_sym = None

        if internal_sym and internal_cost < float("inf"):
            fee_usd = internal_cost
            sell_qty = rebal / internal_price
            available_qty = self.crypto_trade_availability(
                exchange, internal_sym, internal_price
            )["available_qty"]
            if sell_qty > available_qty + 1e-12:
                logger.info(
                    f"[Balance] Internal sell blocked by reserve: "
                    f"{internal_sym} on {exchange}, need={sell_qty:.8f} "
                    f"available={available_qty:.8f}"
                )
                return None
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
        self,
        exchange: str,
        symbol: str,
        price: float,
        now: float,
        max_external_fee_usd: float | None = None,
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
                crypto_val = self.crypto_trade_availability(ex, symbol, price)["available_usd"]
                if crypto_val >= self._trade_amount:
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
            crypto_val = self.crypto_trade_availability(ex, symbol, price)["available_usd"]
            if crypto_val >= rebal * 1.2:
                crypto_sources.append(ex)
        # Fallback: try smaller amount from any source
        if not crypto_sources:
            min_rebal = self._trade_amount
            for ex in self._exchanges:
                if ex == exchange:
                    continue
                crypto_val = self.crypto_trade_availability(ex, symbol, price)["available_usd"]
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

            if not self._paid_transfer_worthwhile(
                external_crypto_cost,
                f"External crypto {best_source}→{exchange}",
            ):
                crypto_sources = []  # Skip, fall through to internal

            # Hourly external transfer budget check
            if crypto_sources and not self._check_hourly_transfer_budget(external_crypto_cost):
                crypto_sources = []  # Skip, fall through to internal
            if (
                crypto_sources
                and max_external_fee_usd is not None
                and external_crypto_cost > max_external_fee_usd
            ):
                logger.debug(
                    f"[Balance] External crypto {best_source}→{exchange} "
                    f"blocked by weak-regime refill cap: "
                    f"${external_crypto_cost:.2f} > ${max_external_fee_usd:.2f}"
                )
                crypto_sources = []

            # Prefer external crypto if cheaper than internal buy
            if crypto_sources and external_crypto_cost < internal_buy_cost:
                available_qty = self.crypto_trade_availability(
                    best_source, symbol, price
                )["available_qty"]
                if transfer_qty > available_qty + 1e-12:
                    logger.info(
                        f"[Balance] External crypto blocked by reserve: "
                        f"{symbol} {best_source}→{exchange}, need={transfer_qty:.8f} "
                        f"available={available_qty:.8f}"
                    )
                    return None
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
            if not self._paid_transfer_worthwhile(
                fee_usd,
                f"Internal buy {symbol} on {exchange}",
            ):
                logger.info(
                    f"[Balance] Internal buy blocked by profit gate: "
                    f"{symbol} on {exchange}, fee=${fee_usd:.4f}"
                )
                return None
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

            # Hourly external transfer budget check
            if not self._check_hourly_transfer_budget(withdrawal_fee):
                return None
            if max_external_fee_usd is not None and withdrawal_fee > max_external_fee_usd:
                logger.debug(
                    f"[Balance] External+buy {richest_ex}→{exchange} "
                    f"blocked by weak-regime refill cap: "
                    f"${withdrawal_fee:.2f} > ${max_external_fee_usd:.2f}"
                )
                return None

            fee_rate = self._fee_manager.get_taker_fee(exchange) if self._fee_manager else 0.001
            buy_fee = ext_buy_rebal * fee_rate
            if not self._paid_transfer_worthwhile(
                withdrawal_fee + buy_fee,
                f"External+buy {richest_ex}→{exchange}",
            ):
                return None

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

    # ── Capital Architecture (custody hub + trading float) ──────────────

    def is_custody_hub(self, exchange: str) -> bool:
        """Whether this exchange is the configured bulk-USDT custody hub."""
        return exchange == self._custody_hub_exchange

    def is_trading_float(self, exchange: str) -> bool:
        """Whether this exchange is the trading float (Bitfinex for the 0% leg)."""
        return exchange == "Bitfinex"

    def emergency_draw_from_custody(
        self, target_exchange: str, needed_amount: float
    ) -> list[Transfer]:
        """Pull USDT from the custody hub to break a capital death spiral.

        v0.30+: this used to draw from Bitfinex's reserve. Now it draws from
        the custody hub (default Bybit) — Bitfinex is the trading float and
        shouldn't be tapped for emergencies. Bypasses gates (net P&L, hourly
        cap, transfer worthiness). Routes via the configured custody-hub
        network (default Aptos $0).
        """
        hub = self._custody_hub_exchange
        if hub not in self._exchanges or target_exchange == hub:
            return []

        hub_usdt = self.usdt.get(hub, 0.0)
        if hub_usdt <= 0:
            now_t = time.time()
            if now_t - self._emergency_draw_log_time >= 30.0:
                logger.info(
                    f"[Capital] Emergency draw blocked: {hub}=${hub_usdt:.2f} (empty)"
                )
                self._emergency_draw_log_time = now_t
            return []

        amount = min(needed_amount, hub_usdt)
        if amount < self._trade_amount:
            return []  # Not enough for even one trade

        # Withdrawal fee on the configured custody-hub network (Bybit→Aptos = $0)
        fee = self._get_withdrawal_fee(hub, amount)

        now = time.time()
        self.usdt[hub] -= amount
        self.usdt[target_exchange] = self.usdt.get(target_exchange, 0.0) + (amount - fee)
        if fee > 0:
            self.total_transfer_fees += fee
            self.total_external_transfer_fees += fee
            self._record_external_fee(fee)

        transfer = Transfer(
            timestamp=now,
            transfer_type="custody_emergency_draw",
            from_exchange=hub,
            to_exchange=target_exchange,
            symbol="USDT",
            amount_usd=amount,
            fee_usd=fee,
        )
        self.transfers.append(transfer)
        logger.info(
            f"[Capital] EMERGENCY draw from custody: {hub}→{target_exchange} "
            f"${amount:.2f} via {self._custody_hub_network} (fee=${fee:.4f}, "
            f"custody now ${self.usdt.get(hub, 0.0):.2f})"
        )
        return [transfer]

    # Backward-compat alias — old callers still use this name
    emergency_reserve_draw = emergency_draw_from_custody

    def replenish_trading_float(
        self,
        prices: dict[str, float] | None = None,
        max_fee_per_source: float | None = None,
    ) -> list[Transfer]:
        """Top up Bitfinex trading float from the custody hub via Aptos $0.

        v0.30+: replaces the old multi-source replenish logic. Single source
        (custody hub), single network (default Aptos), single trigger
        (`bitfinex_usdt < trade_amount × replenish_trigger`). Float target
        is `trade_amount × trading_float_multiplier` — bounded by trade size,
        not capital.

        v0.31+: `trading_float_multiplier == 0` is the explicit "disabled"
        signal. When disabled, no float is maintained, no replenishment
        ever fires, and overflow sweeping is also skipped. The other paths
        (demotion via Bitfinex 0%, distribute, etc.) continue working.

        max_fee_per_source is accepted for backward compat but largely
        irrelevant when routing via Aptos $0.
        """
        if "Bitfinex" not in self._exchanges:
            return []
        # 0 = disabled. Explicit early return so the semantic is unmissable.
        if self._trading_float_multiplier <= 0:
            return []
        hub = self._custody_hub_exchange
        if hub == "Bitfinex" or hub not in self._exchanges:
            return []

        current = self.usdt.get("Bitfinex", 0.0)
        target = self._bitfinex_reserve_target  # = trade_amount × multiplier
        trigger = self._trade_amount * self._trading_float_replenish_trigger
        if current >= trigger:
            return []  # Float still healthy

        deficit = target - current
        min_replenish = max(10.0, self._trade_amount)
        if deficit < min_replenish:
            return []

        hub_avail = self.usdt.get(hub, 0.0) - self._rebalance_buffer
        if hub_avail < min_replenish:
            return []

        amount = min(deficit, hub_avail)
        fee = self._get_withdrawal_fee(hub, amount)

        if max_fee_per_source is not None and fee > max_fee_per_source:
            return []
        if not self._paid_transfer_worthwhile(
            fee,
            f"Trading float replenish {hub}→Bitfinex",
        ):
            return []
        if not self._check_hourly_transfer_budget(fee):
            return []

        # Cooldown to avoid micro-replenishes
        now = time.time()
        cooldown_key = f"trading_float_replenish:{hub}"
        if now - self._last_rebalance.get(cooldown_key, 0) < max(self._rebalance_cooldown, 60):
            return []

        self.usdt[hub] -= amount
        self.usdt["Bitfinex"] += amount - fee
        if fee > 0:
            self.total_transfer_fees += fee
            self.total_external_transfer_fees += fee
            self._record_external_fee(fee)
        self._last_rebalance[cooldown_key] = now

        transfer = Transfer(
            timestamp=now,
            transfer_type="trading_float_replenish",
            from_exchange=hub,
            to_exchange="Bitfinex",
            symbol="USDT",
            amount_usd=amount,
            fee_usd=fee,
        )
        self.transfers.append(transfer)
        logger.info(
            f"[Capital] Replenished trading float: {hub}→Bitfinex "
            f"${amount:.2f} via {self._custody_hub_network} (fee=${fee:.4f}, "
            f"float now ${self.usdt.get('Bitfinex', 0.0):.2f}/${target:.2f}, "
            f"trigger=${trigger:.2f})"
        )
        return [transfer]

    # Backward-compat alias
    replenish_reserve = replenish_trading_float

    def consolidate_to_custody_hub(
        self,
        active_buyer_exchanges: set[str] | None = None,
        idle_threshold: float = 600.0,
        active_seller_exchanges: set[str] | None = None,
        max_fee_per_source: float | None = None,
    ) -> list[Transfer]:
        """Consolidate USDT from non-essential exchanges to the custody hub.

        v0.30+: previously consolidated to Bitfinex (the trading float).
        Now flows to the configured custody hub (default Bybit) which has
        third-party PoR audit and is the bulk-USDT parking layer.

        The trading float on Bitfinex itself is excluded as a source —
        excess Bitfinex USDT flows back to custody via the separate
        overflow path in optimizer (`_consolidate_trading_float_overflow`).

        Active buyer/seller exchanges idle for longer than idle_threshold
        are treated as non-essential and consolidated too. When net-negative,
        callers pass max_fee_per_source=0.02 to limit consolidation to
        free/near-free sources.

        Args:
            active_buyer_exchanges: Exchanges still needed as buyers.
                Keep trade_amount×3 buffer on recently-active ones.
                None = consolidate everything.
            idle_threshold: Seconds since last trade before an active exchange
                is considered idle. Default 600s (10 min).
            active_seller_exchanges: Exchanges still needed as sellers.
                Keep trade_amount×3 buffer on recently-active ones.
                None = no seller protection.
            max_fee_per_source: Skip sources with withdrawal fee above this
                amount.
        """
        hub = self._custody_hub_exchange
        if hub not in self._exchanges:
            return []

        now = time.time()
        consolidation_cooldown = max(self._rebalance_cooldown, 600)  # 10 min
        min_transfer = max(20.0, self._trade_amount * 2)
        transfers = []

        # Sort non-hub, non-trading-float exchanges by withdrawal fee
        # (Bitfinex excluded — its overflow has a separate dedicated path)
        sources = sorted(
            (ex for ex in self._exchanges if ex != hub and ex != "Bitfinex"),
            key=lambda ex: self._get_withdrawal_fee(ex),
        )

        for ex in sources:
            # Compute available USDT based on exchange activity
            usdt = self.usdt.get(ex, 0.0)
            is_active_buyer = active_buyer_exchanges and ex in active_buyer_exchanges
            is_active_seller = active_seller_exchanges and ex in active_seller_exchanges
            if is_active_buyer or is_active_seller:
                last_trade = self.last_trade_time.get(ex, 0.0)
                idle_seconds = now - last_trade if last_trade > 0 else float("inf")
                if idle_seconds < idle_threshold:
                    keep = self._trade_amount * 3
                else:
                    keep = 0.0
            else:
                keep = 0.0
            available = usdt - keep
            if available < min_transfer:
                continue

            cooldown_key = f"{ex}:custody_consolidate"
            if now - self._last_rebalance.get(cooldown_key, 0) < consolidation_cooldown:
                continue

            fee = self._get_withdrawal_fee(ex, available)

            if max_fee_per_source is not None and fee > max_fee_per_source:
                continue
            if not self._paid_transfer_worthwhile(
                fee,
                f"Custody consolidation {ex}→{hub}",
            ):
                continue
            if not self._check_hourly_transfer_budget(fee):
                continue

            self.usdt[ex] -= available
            self.usdt[hub] += available - fee
            if fee > 0:
                self.total_transfer_fees += fee
                self.total_external_transfer_fees += fee
                self._record_external_fee(fee)
            self._last_rebalance[cooldown_key] = now

            transfer = Transfer(
                timestamp=now,
                transfer_type="custody_consolidation",
                from_exchange=ex,
                to_exchange=hub,
                symbol="USDT",
                amount_usd=available,
                fee_usd=fee,
            )
            self.transfers.append(transfer)
            transfers.append(transfer)
            logger.info(
                f"[Capital] Custody consolidation: {ex}→{hub} "
                f"${available:.2f} via {self._custody_hub_network} (fee=${fee:.4f})"
            )

        return transfers

    # Backward-compat alias
    consolidate_to_bitfinex = consolidate_to_custody_hub

    def transfer_excess_to_custody(self, amount: float) -> Transfer | None:
        """Move excess Bitfinex trading-float USDT back to the custody hub.

        Called by optimizer's `_consolidate_trading_float_overflow` when
        Bitfinex USDT > target × overflow_multiplier. Routes via configured
        custody-hub network ($0 on Aptos for Bybit).
        """
        hub = self._custody_hub_exchange
        if hub == "Bitfinex" or hub not in self._exchanges:
            return None
        if amount < max(10.0, self._trade_amount):
            return None

        bitfinex_usdt = self.usdt.get("Bitfinex", 0.0)
        if amount > bitfinex_usdt:
            amount = bitfinex_usdt
        if amount <= 0:
            return None

        fee = self._get_withdrawal_fee("Bitfinex", amount)
        if not self._paid_transfer_worthwhile(
            fee,
            f"Trading float overflow Bitfinex→{hub}",
        ):
            return None
        if not self._check_hourly_transfer_budget(fee):
            return None

        now = time.time()
        self.usdt["Bitfinex"] -= amount
        self.usdt[hub] = self.usdt.get(hub, 0.0) + (amount - fee)
        if fee > 0:
            self.total_transfer_fees += fee
            self.total_external_transfer_fees += fee
            self._record_external_fee(fee)

        transfer = Transfer(
            timestamp=now,
            transfer_type="trading_float_overflow",
            from_exchange="Bitfinex",
            to_exchange=hub,
            symbol="USDT",
            amount_usd=amount,
            fee_usd=fee,
        )
        self.transfers.append(transfer)
        logger.info(
            f"[Capital] Trading float overflow: Bitfinex→{hub} "
            f"${amount:.2f} via {self._custody_hub_network} (fee=${fee:.4f})"
        )
        return transfer

    def transfer_to_custody_hub(self, source_exchange: str, amount: float) -> Transfer | None:
        """Sweep USDT from any source exchange to the custody hub.

        Used by demotion/idle-consolidation flows: after crypto sells via
        Bitfinex at 0% taker, the resulting USDT is swept to the custody hub
        via the configured network ($0 on Aptos).
        """
        hub = self._custody_hub_exchange
        if source_exchange == hub or hub not in self._exchanges:
            return None
        if amount < max(10.0, self._trade_amount):
            return None

        avail = self.usdt.get(source_exchange, 0.0)
        if amount > avail:
            amount = avail
        if amount <= 0:
            return None

        fee = self._get_withdrawal_fee(source_exchange, amount)
        if not self._paid_transfer_worthwhile(
            fee,
            f"Custody sweep {source_exchange}→{hub}",
        ):
            return None
        if not self._check_hourly_transfer_budget(fee):
            return None

        now = time.time()
        self.usdt[source_exchange] -= amount
        self.usdt[hub] = self.usdt.get(hub, 0.0) + (amount - fee)
        if fee > 0:
            self.total_transfer_fees += fee
            self.total_external_transfer_fees += fee
            self._record_external_fee(fee)

        transfer = Transfer(
            timestamp=now,
            transfer_type="custody_sweep",
            from_exchange=source_exchange,
            to_exchange=hub,
            symbol="USDT",
            amount_usd=amount,
            fee_usd=fee,
        )
        self.transfers.append(transfer)
        logger.info(
            f"[Capital] Custody sweep: {source_exchange}→{hub} "
            f"${amount:.2f} via {self._custody_hub_network} (fee=${fee:.4f})"
        )
        return transfer

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

        available_qty = self.crypto_trade_availability(
            source_exchange, symbol, bitfinex_bid
        )["available_qty"]
        if qty > available_qty:
            qty = available_qty
        if qty <= 0:
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
        if not self._paid_transfer_worthwhile(
            withdrawal_fee,
            f"Idle crypto consolidation {source_exchange}→Bitfinex",
        ):
            return None
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

    def emergency_consolidate_to_custody_hub(self) -> list[Transfer]:
        """Emergency consolidation — moves all USDT to the custody hub.

        v0.30+: previously sent to Bitfinex. Now sends to the configured
        custody hub (default Bybit) which has third-party PoR audit and is
        the safer parking destination after an anomaly emergency. Walks
        every other exchange (including Bitfinex's trading float) sorted
        by withdrawal fee (cheapest first), transferring full USDT balances
        regardless of cooldowns or hourly budget caps. Used after
        `_emergency_sell_all` when anomaly protection has paused trading.

        Returns the list of Transfer records executed.
        """
        hub = self._custody_hub_exchange
        if hub not in self._exchanges:
            return []

        transfers: list[Transfer] = []
        now = time.time()
        sources = sorted(
            (ex for ex in self._exchanges if ex != hub),
            key=lambda ex: self._get_withdrawal_fee(ex),
        )
        for ex in sources:
            usdt = self.usdt.get(ex, 0.0)
            fee = self._get_withdrawal_fee(ex, usdt)
            min_amount = max(1.0, fee * 1.5)
            if usdt < min_amount:
                continue
            self.usdt[ex] -= usdt
            net = max(0.0, usdt - fee)
            self.usdt[hub] += net
            self.total_transfer_fees += fee
            self.total_external_transfer_fees += fee
            self._record_external_fee(fee)
            transfer = Transfer(
                timestamp=now,
                transfer_type="emergency_consolidate",
                from_exchange=ex,
                to_exchange=hub,
                symbol="USDT",
                amount_usd=usdt,
                fee_usd=fee,
            )
            self.transfers.append(transfer)
            transfers.append(transfer)
            logger.warning(
                f"[Anomaly] EMERGENCY_CONSOLIDATE {ex}→{hub}: "
                f"${usdt:.2f} (fee=${fee:.4f}, net=${net:.2f})"
            )
        return transfers

    # Backward-compat alias
    emergency_consolidate_to_bitfinex = emergency_consolidate_to_custody_hub

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

            availability = self.crypto_trade_availability(exchange, symbol, price)
            qty = availability["held_qty"]
            actual = availability["available_usd"]
            high_band = target * (1.0 + drift_threshold)
            low_band = target * (1.0 - drift_threshold)
            taker_fee = self._fee_manager.get_taker_fee(exchange) if self._fee_manager else 0.001

            stats = ex_actions.setdefault(exchange, {"sell_count": 0, "buy_count": 0, "skip_count": 0, "fee_total": 0.0, "value_total": 0.0})

            if actual > high_band:
                # Sell excess crypto to bring inventory back to target
                excess_usd = actual - target
                sell_qty = excess_usd / price
                if sell_qty > 0 and availability["available_qty"] >= sell_qty:
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
        bnb_price: float = 0.0,
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
        balance. Returns a dict with rounding, fee, and realized P&L details.
        """
        return self._build_trade_adjustment(
            buy_exchange,
            sell_exchange,
            symbol,
            trade_amount,
            buy_price,
            sell_price,
            buy_fee,
            sell_fee,
            buy_fee_model,
            sell_fee_model,
            bnb_price,
            mutate=True,
        )

    def get_portfolio_value(
        self,
        prices: dict[str, float],
        hedge_pnl_usd: float = 0.0,
        prices_per_exchange: dict[str, dict[str, float]] | None = None,
    ) -> float:
        """Calculate total portfolio value in USD.

        v0.30.1+: when `prices_per_exchange` is provided, crypto held on
        each exchange is MTM-marked against THAT exchange's actual price
        (Fix A — per-exchange spot pricing). Eliminates the dispersion error
        where, e.g., SNX held on Bitget was being marked at Binance's price.

        Falls back to flat `prices` dict for any (exchange, symbol) missing
        from `prices_per_exchange`.

        Includes spot USDT + spot crypto value + Binance Futures reserve +
        in-transit USDT/crypto (debited from source, not yet credited to
        destination — D-17 demo mode network delay) + optional futures hedge
        unrealized PnL.

        v0.31.0-beta+: in-transit funds MUST be counted. Without them,
        a burst of USDT rebalances in demo mode reads as a phantom
        portfolio drop equal to the in-flight total during the network-
        delay window — observed in S31 with three back-to-back transfers
        ($88+$114+$120) producing a momentary $321 phantom drop on a
        $1000 portfolio (32%) that crossed the emergency drawdown
        threshold and triggered a false sell-all.
        """
        total = sum(self.usdt.values()) + float(getattr(self, "binance_futures_usdt", 0.0) or 0.0)
        bnb_price = float(prices.get("BNBUSDT", 0.0) or 0.0)
        if bnb_price > 0:
            total += (
                float(getattr(self, "binance_spot_bnb", 0.0) or 0.0)
                + float(getattr(self, "binance_futures_bnb", 0.0) or 0.0)
            ) * bnb_price
        for ex in self._exchanges:
            ex_prices = (prices_per_exchange or {}).get(ex, {})
            for sym, qty in self.crypto[ex].items():
                if qty > 0:
                    # Prefer per-exchange price; fall back to flat dict
                    p = ex_prices.get(sym) or prices.get(sym, 0.0)
                    total += qty * p
        # In-transit funds: real money that's been debited from source
        # but not yet credited to dest. USDT counts at face value; in-
        # transit crypto is MTM-marked against the destination exchange's
        # price (closest proxy, since that's where it's about to land).
        for fund in self._in_transit:
            if fund.asset == "USDT":
                total += fund.amount
            else:
                ex_prices = (prices_per_exchange or {}).get(fund.to_exchange, {})
                p = ex_prices.get(fund.asset) or prices.get(fund.asset, 0.0)
                total += fund.amount * p
        total += hedge_pnl_usd
        return total

    def get_realized_capital(
        self,
        trading_pnl: float = 0.0,
        credited_cashback: float = 0.0,
    ) -> float:
        """Capital that's actually locked in (no MTM dependency).

        Used for peak-tracking in anomaly protection: peak should ratchet
        up only when capital is *realized* (sold to USDT, cashback credited),
        not when crypto inventory transiently MTMs higher and then reverts.

        formula:
            realized = initial_investment
                     + cumulative_trading_pnl     (locked-in trade profits/losses)
                     - total_external_fees        (spent on withdrawals)
                     + credited_cashback          (credited to USDT, not pending)

        This deliberately EXCLUDES:
          - Spot crypto MTM (qty × current_price) — that's the volatility we
            want to measure drawdown AGAINST, not pollute peak with
          - Hedge unrealized PnL — same reason, it's MTM noise on either side
          - Pending cashback — not yet credited

        The caller passes trading_pnl and credited_cashback because those
        live in monitor + fee_manager respectively; balance only knows
        about transfers.
        """
        return (
            self._initial_investment
            + trading_pnl
            - self.total_external_transfer_fees
            + credited_cashback
        )

    def get_balance_lines(self, prices: dict[str, float]) -> list[str]:
        """Get formatted balance summary lines for live display."""
        parts = []
        for ex in self._exchanges:
            ex_total = self.usdt[ex]
            for sym, qty in self.crypto[ex].items():
                if qty > 0:
                    ex_total += qty * prices.get(sym, 0.0)
            if ex == "Binance":
                ex_total += (
                    float(getattr(self, "binance_spot_bnb", 0.0) or 0.0)
                    * prices.get("BNBUSDT", 0.0)
                )
            parts.append(f"{ex} ${ex_total:.0f}")
        futures_reserve = float(getattr(self, "binance_futures_usdt", 0.0) or 0.0)
        futures_bnb_value = (
            float(getattr(self, "binance_futures_bnb", 0.0) or 0.0)
            * prices.get("BNBUSDT", 0.0)
        )
        if futures_reserve > 0 or futures_bnb_value > 0:
            parts.append(f"BinanceFutures ${futures_reserve + futures_bnb_value:.0f}")
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
            "binance_futures_usdt": float(getattr(self, "binance_futures_usdt", 0.0) or 0.0),
            "binance_spot_bnb": float(getattr(self, "binance_spot_bnb", 0.0) or 0.0),
            "binance_futures_bnb": float(getattr(self, "binance_futures_bnb", 0.0) or 0.0),
            "binance_spot_bnb_reserved_usd": self.binance_spot_bnb_reserved_usd,
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
            "_bitfinex_reserve_hard_floor": self._bitfinex_reserve_hard_floor,  # legacy
            "_custody_hub_exchange": self._custody_hub_exchange,
            "_custody_hub_network": self._custody_hub_network,
            "_trading_float_multiplier": self._trading_float_multiplier,
            "_trading_float_replenish_trigger": self._trading_float_replenish_trigger,
            "_trading_float_overflow_multiplier": self._trading_float_overflow_multiplier,
            "_bnb_reserve_block_log_count": dict(self._bnb_reserve_block_log_count),
        }

    def from_state_dict(self, data: dict) -> None:
        """Restore mutable state from a previously saved dict."""
        # Merge saved state with current exchanges (handle added/removed exchanges)
        saved_usdt = data["usdt"]
        saved_crypto = data["crypto"]
        saved_crypto_usd = data["_crypto_usd"]
        self.binance_futures_usdt = float(data.get("binance_futures_usdt", 0.0) or 0.0)
        self.binance_spot_bnb = float(data.get("binance_spot_bnb", 0.0) or 0.0)
        self.binance_futures_bnb = float(data.get("binance_futures_bnb", 0.0) or 0.0)
        self._binance_spot_bnb_reserved_usd = max(
            0.0, float(data.get("binance_spot_bnb_reserved_usd", self.binance_spot_bnb_reserved_usd) or 0.0)
        )
        self._bnb_reserve_block_log_count = defaultdict(
            int,
            data.get("_bnb_reserve_block_log_count", {}),
        )
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
        self._estimated_profit_per_trade = data.get("_estimated_profit_per_trade", 0.0)
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
            self._bitfinex_reserve_hard_floor_amount = 0.0  # No longer used in v0.30
        # v0.30 capital architecture state
        if "_custody_hub_exchange" in data:
            self._custody_hub_exchange = data["_custody_hub_exchange"]
        if "_custody_hub_network" in data:
            self._custody_hub_network = data["_custody_hub_network"]
        if "_trading_float_multiplier" in data:
            self._trading_float_multiplier = float(data["_trading_float_multiplier"])
            self._bitfinex_reserve_target = (
                self._trade_amount * self._trading_float_multiplier
            )
        if "_trading_float_replenish_trigger" in data:
            self._trading_float_replenish_trigger = float(
                data["_trading_float_replenish_trigger"]
            )
        if "_trading_float_overflow_multiplier" in data:
            self._trading_float_overflow_multiplier = float(
                data["_trading_float_overflow_multiplier"]
            )
