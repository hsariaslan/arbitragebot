"""Comprehensive fee management for all exchanges.

Replaces the flat EXCHANGE_TAKER_FEES dict with a system that models:
- Token discounts (BNB, BGB, KCS, GT, MX) with instant/rebate/tier mechanisms
- Referral cashbacks with delayed settlement (0 min to 18 hours)
- Zero-fee pair overrides (e.g., Gate.io BTC/USDT)
- Real mode: API-queried rates override config values
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExchangeFeeConfig:
    """Complete fee configuration for a single exchange."""

    exchange: str
    base_taker_rate: float  # e.g., 0.001 = 0.10%
    token_discount_enabled: bool  # Whether BNB/BGB/KCS/GT/MX discount is active
    token_discount_pct: float  # e.g., 0.25 = 25% off
    fee_mechanism: str  # "instant" | "rebate" | "tier"
    fee_model: str  # "received" | "spent" | "token"
    referral_enabled: bool
    referral_cashback_pct: float  # 0.0 = disabled/ignored
    referral_settlement_minutes: float  # avg delay until cashback credited
    referral_paid_in: str  # "same_as_fee" | "USDT"
    referrer_commission_pct: float = 0.0  # % of fee earned by referrer (user's account)
    zero_fee_pairs: list[str] = field(default_factory=list)
    enabled: bool = True  # Whether this exchange is active for trading
    # Per-role enable flags (within an enabled exchange). Operator can pin
    # the bot to specific routes — e.g. Bitfinex(buyer)+MEXC(seller) only.
    # Both default to True (full participation when enabled).
    as_buyer: bool = True
    as_seller: bool = True
    # Per-symbol blocklist — symbols listed here are excluded from this
    # exchange's pair selection (both buyer and seller side). Used to
    # disable thinly-traded symbols on illiquid exchanges (e.g. LDO/HYPE
    # on Bitfinex have ~$2/day volume — useless to trade).
    disabled_symbols: list[str] = field(default_factory=list)
    # Auto-managed blocklist — refreshed daily at 00:01 UTC by the
    # volume-based auto-disable task. Operator-set `disabled_symbols`
    # are never touched by automation, and vice-versa: a manual block
    # survives auto-rescue, an auto-block can be manually cleared
    # (until the next daily refresh re-adds it if volume is still low).
    # `is_symbol_enabled()` checks BOTH lists.
    auto_disabled_symbols: list[str] = field(default_factory=list)
    # Soft preference multipliers for pair selection. 1.0 = neutral, >1.0
    # makes the exchange a more-attractive buyer/seller, <1.0 makes it less.
    # Default Bitfinex.buyer_boost=5.0 + MEXC.seller_boost=5.0 enforces a
    # strong "Bitfinex(buy)+MEXC(sell)" route preference, while still letting
    # other pairs win if their net% beats the preferred pair's by more than
    # the boost factor (e.g. AR's 12% spike on OKX→MEXC trivially overrides).
    buyer_boost: float = 1.0
    seller_boost: float = 1.0

    @property
    def effective_taker_rate(self) -> float:
        """Compute rate after token discount (before referral)."""
        if self.token_discount_enabled and self.token_discount_pct > 0:
            return self.base_taker_rate * (1.0 - self.token_discount_pct)
        return self.base_taker_rate

    @property
    def effective_rate_after_referral(self) -> float:
        """Compute rate after both token discount AND referral cashback.

        For display purposes only — referral is actually delayed cashback,
        not an instant reduction.
        """
        rate = self.effective_taker_rate
        if self.referral_enabled and self.referral_cashback_pct > 0:
            rate *= 1.0 - self.referral_cashback_pct
        return rate

    def to_dict(self) -> dict:
        return {
            "base_taker_rate": self.base_taker_rate,
            "token_discount_enabled": self.token_discount_enabled,
            "token_discount_pct": self.token_discount_pct,
            "fee_mechanism": self.fee_mechanism,
            "fee_model": self.fee_model,
            "referral_enabled": self.referral_enabled,
            "referral_cashback_pct": self.referral_cashback_pct,
            "referral_settlement_minutes": self.referral_settlement_minutes,
            "referral_paid_in": self.referral_paid_in,
            "referrer_commission_pct": self.referrer_commission_pct,
            "zero_fee_pairs": list(self.zero_fee_pairs),
            "enabled": self.enabled,
            "as_buyer": self.as_buyer,
            "as_seller": self.as_seller,
            "disabled_symbols": list(self.disabled_symbols),
            "auto_disabled_symbols": list(self.auto_disabled_symbols),
            "buyer_boost": self.buyer_boost,
            "seller_boost": self.seller_boost,
        }

    @classmethod
    def from_dict(cls, exchange: str, data: dict) -> ExchangeFeeConfig:
        return cls(
            exchange=exchange,
            base_taker_rate=float(data.get("base_taker_rate", 0.001)),
            token_discount_enabled=bool(data.get("token_discount_enabled", False)),
            token_discount_pct=float(data.get("token_discount_pct", 0.0)),
            fee_mechanism=str(data.get("fee_mechanism", "instant")),
            fee_model=str(data.get("fee_model", "received")),
            referral_enabled=bool(data.get("referral_enabled", False)),
            referral_cashback_pct=float(data.get("referral_cashback_pct", 0.0)),
            referral_settlement_minutes=float(
                data.get("referral_settlement_minutes", 0)
            ),
            referral_paid_in=str(data.get("referral_paid_in", "same_as_fee")),
            referrer_commission_pct=float(data.get("referrer_commission_pct", 0.0)),
            zero_fee_pairs=list(data.get("zero_fee_pairs", [])),
            enabled=bool(data.get("enabled", True)),
            as_buyer=bool(data.get("as_buyer", True)),
            as_seller=bool(data.get("as_seller", True)),
            disabled_symbols=list(data.get("disabled_symbols", [])),
            auto_disabled_symbols=list(data.get("auto_disabled_symbols", [])),
            buyer_boost=float(data.get("buyer_boost", 1.0)),
            seller_boost=float(data.get("seller_boost", 1.0)),
        )


@dataclass
class PendingCashback:
    """A referral cashback earned but not yet credited."""

    timestamp: float  # when the trade occurred
    exchange: str
    symbol: str
    cashback_usd: float
    expected_credit_at: float  # timestamp + settlement delay in seconds
    credited: bool = False


class FeeManager:
    """Centralized fee computation for all exchanges.

    Replaces direct EXCHANGE_TAKER_FEES.get() calls throughout the codebase.
    """

    def __init__(
        self,
        configs: dict[str, ExchangeFeeConfig] | None = None,
        real_mode: bool = False,
    ):
        self._configs: dict[str, ExchangeFeeConfig] = configs or {}
        self._real_mode = real_mode
        self._real_rates: dict[str, float] = {}  # from exchange APIs
        self._pending_cashbacks: list[PendingCashback] = []
        self._total_pending_cashback: float = 0.0
        self._total_credited_cashback: float = 0.0
        # Referrer commission tracking (display-only, user's personal account)
        self._total_referrer_earnings: float = 0.0
        self._referrer_earnings_per_exchange: dict[str, float] = {}
        # Version counter — bumped whenever the routing-relevant config
        # state changes (apply_auto_disable, save_fee_settings, etc.).
        # Read by the orchestrator's globally-allowed cache to detect
        # when its (symbol, exchange) filter needs rebuilding.
        self._version: int = 0

        if not self._configs:
            self._configs = self._build_defaults()

    # ── Public API ────────────────────────────────────────────────────

    def get_taker_fee(self, exchange: str, symbol: str = "") -> float:
        """Get effective taker fee for an exchange+symbol pair.

        This is THE replacement for EXCHANGE_TAKER_FEES.get(ex, 0.001).
        - Zero-fee pairs → 0.0
        - Real mode → API rate if available, else config
        - Otherwise → effective_taker_rate (base × (1 - discount))
        - Referral NOT subtracted here (it's delayed, tracked separately)
        """
        cfg = self._configs.get(exchange)
        if cfg is None:
            return 0.001  # safe fallback

        # Zero-fee pair override
        if symbol and symbol in cfg.zero_fee_pairs:
            return 0.0

        # Real mode: prefer API-queried rate
        if self._real_mode and exchange in self._real_rates:
            return self._real_rates[exchange]

        return cfg.effective_taker_rate

    def get_scoring_fee(self, exchange: str, symbol: str = "") -> float:
        """Get fee rate for scoring and exchange ranking decisions.

        Unlike get_taker_fee() which returns the actual fee per trade,
        this returns a time-weighted rate that factors in referral cashback:
        - Instant (0 min): 100% cashback applied — effectively a fee reduction
        - Hourly (≤120 min): 75% applied — fast capital return
        - Daily (>120 min): 50% applied — eventual income

        Used in: scoring, threshold checks, pair selection, trade sizing.
        NOT used in: trade execution, rebalance cost, cashback recording.
        """
        cfg = self._configs.get(exchange)
        if cfg is None:
            return 0.001

        if symbol and symbol in cfg.zero_fee_pairs:
            return 0.0

        if self._real_mode and exchange in self._real_rates:
            rate = self._real_rates[exchange]
        else:
            rate = cfg.effective_taker_rate

        if cfg.referral_enabled and cfg.referral_cashback_pct > 0:
            settlement = cfg.referral_settlement_minutes
            if settlement <= 0:
                weight = 1.0
            elif settlement <= 120:
                weight = 0.75
            else:
                weight = 0.50
            rate *= 1.0 - cfg.referral_cashback_pct * weight

        return rate

    def is_exchange_enabled(self, exchange: str) -> bool:
        """Check if an exchange is enabled for trading."""
        cfg = self._configs.get(exchange)
        if cfg is None:
            return True  # unknown exchange = allow by default
        return cfg.enabled

    def get_enabled_exchanges(self) -> list[str]:
        """Return list of all enabled exchange names."""
        return [ex for ex, cfg in self._configs.items() if cfg.enabled]

    def can_buy(self, exchange: str, symbol: str = "") -> bool:
        """Check if an enabled exchange is allowed to act as a BUYER for a symbol.

        Operator-set per-role flags constrain pair selection — e.g. setting
        only Bitfinex.as_buyer=True and MEXC.as_seller=True restricts trades
        to the cheapest possible pair. Disabled exchanges always return False.
        Symbols in either the manual `disabled_symbols` blocklist or the
        daily-refreshed `auto_disabled_symbols` blocklist also return False.
        """
        cfg = self._configs.get(exchange)
        if cfg is None:
            return True  # unknown = allow
        if symbol and (symbol in cfg.disabled_symbols or symbol in cfg.auto_disabled_symbols):
            return False
        return cfg.enabled and cfg.as_buyer

    def can_sell(self, exchange: str, symbol: str = "") -> bool:
        """Check if an enabled exchange is allowed to act as a SELLER for a symbol."""
        cfg = self._configs.get(exchange)
        if cfg is None:
            return True
        if symbol and (symbol in cfg.disabled_symbols or symbol in cfg.auto_disabled_symbols):
            return False
        return cfg.enabled and cfg.as_seller

    def is_symbol_enabled(self, exchange: str, symbol: str) -> bool:
        """Check if a (exchange, symbol) combination is allowed (either role).

        Blocked if symbol is in either the manual blocklist (`disabled_symbols`)
        or the auto-managed daily blocklist (`auto_disabled_symbols`).
        """
        cfg = self._configs.get(exchange)
        if cfg is None:
            return True
        return symbol not in cfg.disabled_symbols and symbol not in cfg.auto_disabled_symbols

    def get_buyer_boost(self, exchange: str) -> float:
        """Soft preference multiplier when this exchange is selected as buyer.

        Stacks on top of fee weighting in pair scoring. Default 1.0 (neutral).
        Bitfinex defaults to 5.0 to bias the bot toward the cheapest sustainable
        route, while still letting strong opportunities on other pairs win.
        """
        cfg = self._configs.get(exchange)
        if cfg is None:
            return 1.0
        return max(0.0, cfg.buyer_boost)

    def get_seller_boost(self, exchange: str) -> float:
        """Soft preference multiplier when this exchange is selected as seller.

        MEXC defaults to 5.0 — pairs with Bitfinex(buyer) for the cheapest
        possible round-trip on USDT pairs the bot supports.
        """
        cfg = self._configs.get(exchange)
        if cfg is None:
            return 1.0
        return max(0.0, cfg.seller_boost)

    def apply_auto_disable(
        self, per_exchange: dict[str, list[str]]
    ) -> dict[str, dict]:
        """Replace the auto-managed blocklist for each exchange.

        `per_exchange`: {exchange: [symbols_to_auto_disable]}. Each exchange's
        existing `auto_disabled_symbols` is fully replaced (so symbols whose
        volume rose back above threshold are automatically un-blocked).
        Manual `disabled_symbols` is never touched here.

        Returns a per-exchange diff: {exchange: {"added": [...], "removed": [...], "kept": [...]}}.
        Caller should persist via to_settings_dict + save_settings.
        """
        diffs: dict[str, dict] = {}
        any_change = False
        for exchange, new_list in per_exchange.items():
            cfg = self._configs.get(exchange)
            if cfg is None:
                continue
            new_set = set(new_list)
            old_set = set(cfg.auto_disabled_symbols)
            added = sorted(new_set - old_set)
            removed = sorted(old_set - new_set)
            kept = sorted(new_set & old_set)
            cfg.auto_disabled_symbols = sorted(new_set)
            if added or removed:
                diffs[exchange] = {"added": added, "removed": removed, "kept": kept}
                any_change = True
        if any_change:
            self._version += 1
        return diffs

    def get_fee_model(self, exchange: str) -> str:
        """Get fee deduction model for an exchange.

        Replacement for EXCHANGE_FEE_MODELS.get(ex, "received").
        """
        cfg = self._configs.get(exchange)
        if cfg is None:
            return "received"
        return cfg.fee_model

    def record_referral_cashback(
        self,
        exchange: str,
        symbol: str,
        trade_amount: float,
        fee_rate: float,
    ) -> float:
        """After a trade, compute and record pending referral cashback.

        Returns the cashback amount in USD (0 if referral disabled).
        """
        cfg = self._configs.get(exchange)
        if cfg is None or not cfg.referral_enabled or cfg.referral_cashback_pct <= 0:
            return 0.0

        fee_usd = trade_amount * fee_rate
        cashback_usd = fee_usd * cfg.referral_cashback_pct
        if cashback_usd <= 0:
            return 0.0

        now = time.time()
        settlement_seconds = cfg.referral_settlement_minutes * 60.0
        cb = PendingCashback(
            timestamp=now,
            exchange=exchange,
            symbol=symbol,
            cashback_usd=cashback_usd,
            expected_credit_at=now + settlement_seconds,
        )
        self._pending_cashbacks.append(cb)
        self._total_pending_cashback += cashback_usd
        return cashback_usd

    def record_referrer_commission(
        self,
        exchange: str,
        symbol: str,
        trade_amount: float,
        fee_rate: float,
    ) -> float:
        """Track referrer commission earned on the user's personal account.

        Display-only — never touches balance, P&L, scoring, or gating.
        Returns the commission amount in USD (0 if referral disabled or rate is 0).
        """
        cfg = self._configs.get(exchange)
        if cfg is None or not cfg.referral_enabled or cfg.referrer_commission_pct <= 0:
            return 0.0

        fee_usd = trade_amount * fee_rate
        commission_usd = fee_usd * cfg.referrer_commission_pct
        if commission_usd <= 0:
            return 0.0

        self._total_referrer_earnings += commission_usd
        self._referrer_earnings_per_exchange[exchange] = (
            self._referrer_earnings_per_exchange.get(exchange, 0.0) + commission_usd
        )
        return commission_usd

    def credit_due_cashbacks(self) -> list[PendingCashback]:
        """Credit any pending cashbacks whose settlement time has passed.

        Called periodically (e.g., each tick). Returns list of newly credited.
        """
        now = time.time()
        credited: list[PendingCashback] = []

        for cb in self._pending_cashbacks:
            if not cb.credited and now >= cb.expected_credit_at:
                cb.credited = True
                self._total_credited_cashback += cb.cashback_usd
                self._total_pending_cashback -= cb.cashback_usd
                credited.append(cb)

        # Prune old credited entries (keep last 1000)
        if len(self._pending_cashbacks) > 2000:
            self._pending_cashbacks = [
                cb
                for cb in self._pending_cashbacks
                if not cb.credited
            ] + [
                cb
                for cb in self._pending_cashbacks
                if cb.credited
            ][-1000:]

        return credited

    def set_real_rate(self, exchange: str, rate: float) -> None:
        """Set an API-queried real fee rate (used in real_mode)."""
        self._real_rates[exchange] = rate
        logger.info(
            f"[Fee] Real rate set for {exchange}: {rate*100:.4f}%"
        )

    # ── Config Access ─────────────────────────────────────────────────

    def get_config(self, exchange: str) -> ExchangeFeeConfig | None:
        return self._configs.get(exchange)

    def get_all_configs(self) -> dict[str, ExchangeFeeConfig]:
        return dict(self._configs)

    @property
    def real_mode(self) -> bool:
        return self._real_mode

    @real_mode.setter
    def real_mode(self, value: bool) -> None:
        self._real_mode = value

    # ── Settings Integration ──────────────────────────────────────────

    def update_from_settings(self, fee_configs: dict) -> None:
        """Hot-apply fee config changes from dashboard settings."""
        for exchange, data in fee_configs.items():
            self._configs[exchange] = ExchangeFeeConfig.from_dict(exchange, data)
        self._version += 1
        logger.info("[Fee] Fee configs updated from settings")

    def to_settings_dict(self) -> dict:
        """Serialize all fee configs for settings.json."""
        return {
            ex: cfg.to_dict() for ex, cfg in self._configs.items()
        }

    @classmethod
    def from_settings_dict(
        cls, data: dict, real_mode: bool = False
    ) -> FeeManager:
        """Reconstruct from settings.json data.

        Backward compatible: empty dict → defaults.
        """
        configs: dict[str, ExchangeFeeConfig] = {}
        if data:
            for exchange, cfg_data in data.items():
                configs[exchange] = ExchangeFeeConfig.from_dict(exchange, cfg_data)

        fm = cls(configs=configs if configs else None, real_mode=real_mode)
        return fm

    # ── State Persistence (pending cashbacks) ─────────────────────────

    def to_state_dict(self) -> dict:
        """Serialize mutable state (pending cashbacks) for session state."""
        pending = [
            {
                "timestamp": cb.timestamp,
                "exchange": cb.exchange,
                "symbol": cb.symbol,
                "cashback_usd": cb.cashback_usd,
                "expected_credit_at": cb.expected_credit_at,
                "credited": cb.credited,
            }
            for cb in self._pending_cashbacks
            if not cb.credited  # only save uncredited
        ]
        return {
            "pending_cashbacks": pending,
            "total_credited_cashback": self._total_credited_cashback,
            "total_referrer_earnings": self._total_referrer_earnings,
            "referrer_earnings_per_exchange": dict(
                self._referrer_earnings_per_exchange
            ),
        }

    def from_state_dict(self, data: dict) -> None:
        """Restore pending cashbacks from saved state."""
        if not data:
            return
        self._total_credited_cashback = float(
            data.get("total_credited_cashback", 0.0)
        )
        self._total_referrer_earnings = float(
            data.get("total_referrer_earnings", 0.0)
        )
        self._referrer_earnings_per_exchange = {
            k: float(v)
            for k, v in data.get("referrer_earnings_per_exchange", {}).items()
        }
        for cb_data in data.get("pending_cashbacks", []):
            cb = PendingCashback(
                timestamp=float(cb_data["timestamp"]),
                exchange=str(cb_data["exchange"]),
                symbol=str(cb_data["symbol"]),
                cashback_usd=float(cb_data["cashback_usd"]),
                expected_credit_at=float(cb_data["expected_credit_at"]),
                credited=False,
            )
            self._pending_cashbacks.append(cb)
            self._total_pending_cashback += cb.cashback_usd

    # ── Dashboard Broadcast ───────────────────────────────────────────

    def to_broadcast_dict(self) -> dict:
        """Build fee state for dashboard WebSocket broadcast."""
        configs_out = {}
        for ex, cfg in self._configs.items():
            d = cfg.to_dict()
            d["effective_taker_rate"] = round(cfg.effective_taker_rate, 8)
            d["effective_rate_after_referral"] = round(
                cfg.effective_rate_after_referral, 8
            )
            d["scoring_fee"] = round(self.get_scoring_fee(ex), 8)
            d["enabled"] = cfg.enabled
            configs_out[ex] = d

        return {
            "fee_configs": configs_out,
            "fee_real_mode": self._real_mode,
            "fee_stats": {
                "pending_cashback_total": round(self._total_pending_cashback, 4),
                "credited_cashback_total": round(self._total_credited_cashback, 4),
                "pending_count": sum(
                    1 for cb in self._pending_cashbacks if not cb.credited
                ),
                "referrer_earnings_total": round(
                    self._total_referrer_earnings, 4
                ),
                "referrer_earnings_per_exchange": {
                    ex: round(val, 4)
                    for ex, val in self._referrer_earnings_per_exchange.items()
                    if val > 0
                },
            },
        }

    # ── Defaults ──────────────────────────────────────────────────────

    @staticmethod
    def _build_defaults() -> dict[str, ExchangeFeeConfig]:
        """Build default configs from DEFAULT_FEE_CONFIGS in config.py."""
        try:
            from config import DEFAULT_FEE_CONFIGS

            return {
                ex: ExchangeFeeConfig.from_dict(ex, data)
                for ex, data in DEFAULT_FEE_CONFIGS.items()
            }
        except ImportError:
            # Fallback if config.py doesn't have the new constant yet
            return FeeManager._hardcoded_defaults()

    @staticmethod
    def _hardcoded_defaults() -> dict[str, ExchangeFeeConfig]:
        """Hardcoded fallback matching current DEFAULT_FEE_CONFIGS."""
        defaults = {
            "Binance": ExchangeFeeConfig(
                exchange="Binance",
                base_taker_rate=0.001,
                token_discount_enabled=True,
                token_discount_pct=0.25,
                fee_mechanism="instant",
                fee_model="token",
                referral_enabled=True,
                referral_cashback_pct=0.10,
                referral_settlement_minutes=60,
                referral_paid_in="same_as_fee",
                referrer_commission_pct=0.10,
                zero_fee_pairs=[],
            ),
            "OKX": ExchangeFeeConfig(
                exchange="OKX",
                base_taker_rate=0.001,
                token_discount_enabled=False,
                token_discount_pct=0.0,
                fee_mechanism="tier",
                fee_model="received",
                referral_enabled=True,
                referral_cashback_pct=0.20,
                referral_settlement_minutes=90,
                referral_paid_in="same_as_fee",
                referrer_commission_pct=0.10,
                zero_fee_pairs=[],
            ),
            "Bybit": ExchangeFeeConfig(
                exchange="Bybit",
                base_taker_rate=0.001,
                token_discount_enabled=False,
                token_discount_pct=0.0,
                fee_mechanism="tier",
                fee_model="received",
                referral_enabled=True,
                referral_cashback_pct=0.20,
                referral_settlement_minutes=1440,
                referral_paid_in="USDT",
                referrer_commission_pct=0.20,
                zero_fee_pairs=[],
            ),
            "MEXC": ExchangeFeeConfig(
                exchange="MEXC",
                base_taker_rate=0.0005,
                token_discount_enabled=False,
                token_discount_pct=0.20,
                fee_mechanism="instant",
                fee_model="received",
                referral_enabled=True,
                referral_cashback_pct=0.10,
                referral_settlement_minutes=1440,
                referral_paid_in="same_as_fee",
                referrer_commission_pct=0.40,
                zero_fee_pairs=[],
            ),
            "Bitget": ExchangeFeeConfig(
                exchange="Bitget",
                base_taker_rate=0.001,
                token_discount_enabled=True,
                token_discount_pct=0.20,
                fee_mechanism="instant",
                fee_model="token",
                referral_enabled=True,
                referral_cashback_pct=0.20,
                referral_settlement_minutes=0,
                referral_paid_in="same_as_fee",
                referrer_commission_pct=0.20,
                zero_fee_pairs=[],
            ),
            "KuCoin": ExchangeFeeConfig(
                exchange="KuCoin",
                base_taker_rate=0.001,
                token_discount_enabled=True,
                token_discount_pct=0.20,
                fee_mechanism="rebate",
                fee_model="token",
                referral_enabled=True,
                referral_cashback_pct=0.20,
                referral_settlement_minutes=1440,
                referral_paid_in="same_as_fee",
                zero_fee_pairs=[],
            ),
            "Gate.io": ExchangeFeeConfig(
                exchange="Gate.io",
                base_taker_rate=0.001,
                token_discount_enabled=True,
                token_discount_pct=0.10,
                fee_mechanism="instant",
                fee_model="token",
                referral_enabled=True,
                referral_cashback_pct=0.30,
                referral_settlement_minutes=1440,
                referral_paid_in="same_as_fee",
                referrer_commission_pct=0.10,
                zero_fee_pairs=["BTCUSDT"],
            ),
            "Pionex": ExchangeFeeConfig(
                exchange="Pionex",
                base_taker_rate=0.0005,
                token_discount_enabled=False,
                token_discount_pct=0.0,
                fee_mechanism="instant",
                fee_model="received",
                referral_enabled=True,
                referral_cashback_pct=0.20,
                referral_settlement_minutes=60,
                referral_paid_in="same_as_fee",
                referrer_commission_pct=0.0,
                zero_fee_pairs=[],
            ),
            "Bitfinex": ExchangeFeeConfig(
                exchange="Bitfinex",
                base_taker_rate=0.0,
                token_discount_enabled=False,
                token_discount_pct=0.0,
                fee_mechanism="instant",
                fee_model="received",
                referral_enabled=False,
                referral_cashback_pct=0.0,
                referral_settlement_minutes=0,
                referral_paid_in="same_as_fee",
                zero_fee_pairs=[],
            ),
        }
        return defaults
