"""Comprehensive USDT withdrawal/transfer fee management for all exchanges.

Replaces the flat USDT_WITHDRAWAL_FEES dict with a system that models:
- Per-exchange, per-network fee matrix (8-17 networks per exchange)
- Flat fees (most networks), percentage-based (KuCoin ERC20), and
  conditional fees (Gate.io TRC20 free above 2,020 USDT minimum)
- Preferred network selection (auto=cheapest or user-specified)
- Hot-apply from dashboard without restart
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class NetworkFeeConfig:
    """Fee configuration for a single network on a single exchange."""

    network: str  # "BEP20", "Plasma", "Arbitrum", etc.
    fee: float  # Flat withdrawal fee in USD (e.g., 0.01)
    fee_type: str  # "flat" | "percentage" | "conditional"
    percentage_rate: float  # For "percentage" type (e.g., 0.002 = 0.2%)
    percentage_min: float  # Minimum fee for percentage type (e.g., 5.50)
    min_withdrawal: float  # Minimum withdrawal amount in USDT
    speed_seconds: float  # Estimated transit time in seconds
    enabled: bool  # Whether this network is available/selectable
    notes: str  # Human-readable notes ("promo", "dynamic", etc.)

    def compute_fee(self, amount: float = 0.0) -> float:
        """Compute actual withdrawal fee for a given amount.

        - "flat": returns self.fee regardless of amount
        - "percentage": returns max(percentage_min, amount * percentage_rate)
        - "conditional": returns self.fee if amount >= min_withdrawal, else inf
        """
        if self.fee_type == "percentage":
            return max(self.percentage_min, amount * self.percentage_rate)
        elif self.fee_type == "conditional":
            if amount >= self.min_withdrawal:
                return self.fee
            return float("inf")  # Not eligible at this amount
        # "flat" (default)
        return self.fee

    def to_dict(self) -> dict:
        return {
            "network": self.network,
            "fee": self.fee,
            "fee_type": self.fee_type,
            "percentage_rate": self.percentage_rate,
            "percentage_min": self.percentage_min,
            "min_withdrawal": self.min_withdrawal,
            "speed_seconds": self.speed_seconds,
            "enabled": self.enabled,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> NetworkFeeConfig:
        return cls(
            network=str(data.get("network", "unknown")),
            fee=float(data.get("fee", 1.0)),
            fee_type=str(data.get("fee_type", "flat")),
            percentage_rate=float(data.get("percentage_rate", 0.0)),
            percentage_min=float(data.get("percentage_min", 0.0)),
            min_withdrawal=float(data.get("min_withdrawal", 10.0)),
            speed_seconds=float(data.get("speed_seconds", 60.0)),
            enabled=bool(data.get("enabled", True)),
            notes=str(data.get("notes", "")),
        )


@dataclass
class ExchangeTransferConfig:
    """Complete transfer fee configuration for a single exchange."""

    exchange: str
    networks: list[NetworkFeeConfig] = field(default_factory=list)
    preferred_network: str = "auto"  # "auto" (cheapest) or network name

    def get_effective_fee(self, amount: float = 0.0) -> float:
        """Get withdrawal fee based on preferred network or cheapest.

        If preferred_network is set to a specific network, uses that.
        If "auto", returns the cheapest eligible network fee.
        """
        if self.preferred_network != "auto":
            for net in self.networks:
                if net.network == self.preferred_network and net.enabled:
                    return net.compute_fee(amount)
        # Auto: cheapest eligible
        _, fee = self.get_cheapest_network(amount)
        return fee

    def get_cheapest_network(
        self, amount: float = 0.0
    ) -> tuple[str, float]:
        """Return (network_name, fee) of cheapest eligible network."""
        best_name = "unknown"
        best_fee = float("inf")
        for net in self.networks:
            if not net.enabled:
                continue
            f = net.compute_fee(amount)
            if f < best_fee:
                best_fee = f
                best_name = net.network
        return (best_name, best_fee if best_fee < float("inf") else 1.0)

    def to_dict(self) -> dict:
        return {
            "preferred_network": self.preferred_network,
            "networks": [n.to_dict() for n in self.networks],
        }

    @classmethod
    def from_dict(cls, exchange: str, data: dict) -> ExchangeTransferConfig:
        networks = [
            NetworkFeeConfig.from_dict(n)
            for n in data.get("networks", [])
        ]
        return cls(
            exchange=exchange,
            networks=networks,
            preferred_network=str(data.get("preferred_network", "auto")),
        )


class TransferFeeManager:
    """Centralized USDT withdrawal fee computation for all exchanges.

    Replaces direct USDT_WITHDRAWAL_FEES.get() calls throughout the codebase.
    """

    def __init__(
        self,
        configs: dict[str, ExchangeTransferConfig] | None = None,
    ):
        self._configs: dict[str, ExchangeTransferConfig] = configs or {}
        if not self._configs:
            self._configs = self._build_defaults()

    # ── Public API ────────────────────────────────────────────────────

    def get_withdrawal_fee(
        self, exchange: str, amount: float = 0.0
    ) -> float:
        """Get effective withdrawal fee for an exchange.

        This is THE replacement for USDT_WITHDRAWAL_FEES.get(ex, 1.0).
        Respects preferred_network setting per exchange.
        """
        cfg = self._configs.get(exchange)
        if cfg is None:
            return 1.0  # safe fallback
        return cfg.get_effective_fee(amount)

    def get_cheapest_network(
        self, exchange: str, amount: float = 0.0
    ) -> tuple[str, float]:
        """Return (network_name, fee) for cheapest eligible network."""
        cfg = self._configs.get(exchange)
        if cfg is None:
            return ("unknown", 1.0)
        return cfg.get_cheapest_network(amount)

    # ── Config Access ─────────────────────────────────────────────────

    def get_config(self, exchange: str) -> ExchangeTransferConfig | None:
        return self._configs.get(exchange)

    def get_all_configs(self) -> dict[str, ExchangeTransferConfig]:
        return dict(self._configs)

    # ── Settings Integration ──────────────────────────────────────────

    def update_from_settings(self, transfer_configs: dict) -> None:
        """Hot-apply transfer config changes from dashboard settings."""
        for exchange, data in transfer_configs.items():
            self._configs[exchange] = ExchangeTransferConfig.from_dict(
                exchange, data
            )
        logger.info("[Transfer] Transfer fee configs updated from settings")

    def to_settings_dict(self) -> dict:
        """Serialize all transfer configs for settings.json."""
        return {
            ex: cfg.to_dict() for ex, cfg in self._configs.items()
        }

    @classmethod
    def from_settings_dict(cls, data: dict) -> TransferFeeManager:
        """Reconstruct from settings.json data.

        Backward compatible: empty dict → defaults.
        """
        configs: dict[str, ExchangeTransferConfig] = {}
        if data:
            for exchange, cfg_data in data.items():
                configs[exchange] = ExchangeTransferConfig.from_dict(
                    exchange, cfg_data
                )
        return cls(configs=configs if configs else None)

    # ── Dashboard Broadcast ───────────────────────────────────────────

    def to_broadcast_dict(self) -> dict:
        """Build transfer fee state for dashboard WebSocket broadcast."""
        configs_out = {}
        for ex, cfg in self._configs.items():
            d = cfg.to_dict()
            d["effective_fee"] = round(cfg.get_effective_fee(), 6)
            name, fee = cfg.get_cheapest_network()
            d["cheapest_network"] = name
            d["cheapest_fee"] = round(fee, 6)
            configs_out[ex] = d

        return {
            "transfer_configs": configs_out,
        }

    # ── Defaults ──────────────────────────────────────────────────────

    @staticmethod
    def _build_defaults() -> dict[str, ExchangeTransferConfig]:
        """Build default configs from DEFAULT_TRANSFER_CONFIGS in config.py."""
        try:
            from config import DEFAULT_TRANSFER_CONFIGS

            return {
                ex: ExchangeTransferConfig.from_dict(ex, data)
                for ex, data in DEFAULT_TRANSFER_CONFIGS.items()
            }
        except ImportError:
            return TransferFeeManager._hardcoded_defaults()

    @staticmethod
    def _hardcoded_defaults() -> dict[str, ExchangeTransferConfig]:
        """Hardcoded fallback matching current USDT_WITHDRAWAL_FEES behavior."""

        def _flat(
            network: str,
            fee: float,
            speed: float = 3.0,
            min_w: float = 10.0,
            notes: str = "",
        ) -> NetworkFeeConfig:
            return NetworkFeeConfig(
                network=network,
                fee=fee,
                fee_type="flat",
                percentage_rate=0.0,
                percentage_min=0.0,
                min_withdrawal=min_w,
                speed_seconds=speed,
                enabled=True,
                notes=notes,
            )

        return {
            "Binance": ExchangeTransferConfig(
                exchange="Binance",
                preferred_network="auto",
                networks=[
                    _flat("BEP20", 0.01, 3),
                    _flat("Plasma", 0.012, 1),
                    _flat("Arbitrum", 0.10, 1),
                    _flat("TRC20", 1.00, 5),
                ],
            ),
            "OKX": ExchangeTransferConfig(
                exchange="OKX",
                preferred_network="auto",
                networks=[
                    _flat("Polygon", 0.10, 3, notes="dynamic"),
                    _flat("BEP20", 0.30, 3, notes="dynamic"),
                    _flat("Arbitrum", 0.50, 1, notes="dynamic"),
                    _flat("ERC20", 3.00, 12, notes="dynamic"),
                ],
            ),
            "Bybit": ExchangeTransferConfig(
                exchange="Bybit",
                preferred_network="auto",
                networks=[
                    _flat("Aptos", 0.00, 1, notes="promo"),
                    _flat("BEP20", 0.20, 3, notes="dynamic"),
                    _flat("Arbitrum", 0.50, 1, notes="dynamic"),
                    _flat("TRC20", 1.60, 5),
                ],
            ),
            "Bitget": ExchangeTransferConfig(
                exchange="Bitget",
                preferred_network="auto",
                networks=[
                    _flat("Plasma", 0.001, 1, notes="verified"),
                    _flat("Aptos", 0.03, 1, notes="verified"),
                    _flat("BEP20", 0.15, 3, notes="verified"),
                    _flat("TRC20", 1.50, 5, notes="verified"),
                ],
            ),
            "KuCoin": ExchangeTransferConfig(
                exchange="KuCoin",
                preferred_network="auto",
                networks=[
                    _flat("Plasma", 0.40, 1, 5),
                    _flat("KCC", 0.50, 3, 1),
                    _flat("BEP20", 1.00, 3),
                    _flat("TRC20", 1.50, 5, 3),
                ],
            ),
            "Gate.io": ExchangeTransferConfig(
                exchange="Gate.io",
                preferred_network="auto",
                networks=[
                    _flat("BEP20", 0.50, 3),
                    _flat("Arbitrum", 0.50, 1),
                    _flat("ERC20", 4.00, 12),
                ],
            ),
        }
