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
    zero_fee_pairs: list[str] = field(default_factory=list)

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
            "zero_fee_pairs": list(self.zero_fee_pairs),
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
            zero_fee_pairs=list(data.get("zero_fee_pairs", [])),
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
        }

    def from_state_dict(self, data: dict) -> None:
        """Restore pending cashbacks from saved state."""
        if not data:
            return
        self._total_credited_cashback = float(
            data.get("total_credited_cashback", 0.0)
        )
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
        """Hardcoded fallback matching current EXCHANGE_TAKER_FEES behavior."""
        defaults = {
            "Binance": ExchangeFeeConfig(
                exchange="Binance",
                base_taker_rate=0.001,
                token_discount_enabled=True,
                token_discount_pct=0.25,
                fee_mechanism="instant",
                fee_model="token",
                referral_enabled=False,
                referral_cashback_pct=0.0,
                referral_settlement_minutes=30,
                referral_paid_in="same_as_fee",
                zero_fee_pairs=[],
            ),
            "OKX": ExchangeFeeConfig(
                exchange="OKX",
                base_taker_rate=0.001,
                token_discount_enabled=False,
                token_discount_pct=0.0,
                fee_mechanism="tier",
                fee_model="received",
                referral_enabled=False,
                referral_cashback_pct=0.0,
                referral_settlement_minutes=90,
                referral_paid_in="same_as_fee",
                zero_fee_pairs=[],
            ),
            "Bybit": ExchangeFeeConfig(
                exchange="Bybit",
                base_taker_rate=0.001,
                token_discount_enabled=False,
                token_discount_pct=0.0,
                fee_mechanism="tier",
                fee_model="received",
                referral_enabled=False,
                referral_cashback_pct=0.0,
                referral_settlement_minutes=720,
                referral_paid_in="USDT",
                zero_fee_pairs=[],
            ),
            "MEXC": ExchangeFeeConfig(
                exchange="MEXC",
                base_taker_rate=0.0005,
                token_discount_enabled=False,
                token_discount_pct=0.20,
                fee_mechanism="instant",
                fee_model="received",
                referral_enabled=False,
                referral_cashback_pct=0.0,
                referral_settlement_minutes=720,
                referral_paid_in="same_as_fee",
                zero_fee_pairs=[],
            ),
            "Bitget": ExchangeFeeConfig(
                exchange="Bitget",
                base_taker_rate=0.001,
                token_discount_enabled=True,
                token_discount_pct=0.20,
                fee_mechanism="instant",
                fee_model="token",
                referral_enabled=False,
                referral_cashback_pct=0.0,
                referral_settlement_minutes=1080,
                referral_paid_in="USDT",
                zero_fee_pairs=[],
            ),
            "KuCoin": ExchangeFeeConfig(
                exchange="KuCoin",
                base_taker_rate=0.001,
                token_discount_enabled=True,
                token_discount_pct=0.20,
                fee_mechanism="rebate",
                fee_model="token",
                referral_enabled=False,
                referral_cashback_pct=0.0,
                referral_settlement_minutes=1080,
                referral_paid_in="same_as_fee",
                zero_fee_pairs=[],
            ),
            "Gate.io": ExchangeFeeConfig(
                exchange="Gate.io",
                base_taker_rate=0.001,
                token_discount_enabled=False,
                token_discount_pct=0.10,
                fee_mechanism="instant",
                fee_model="received",
                referral_enabled=False,
                referral_cashback_pct=0.0,
                referral_settlement_minutes=0,
                referral_paid_in="same_as_fee",
                zero_fee_pairs=["BTCUSDT"],
            ),
        }
        return defaults
