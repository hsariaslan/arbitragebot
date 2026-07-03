from decimal import Decimal
import os
import unittest

os.environ.setdefault("DASHBOARD_PASSWORD", "test")

from config import BITFINEX_EXCHANGE_NAME
from exchange_info import ExchangeInfoManager
from fetchers.mexc import _depth_channel
from slippage import quote_book_mismatch_reason


class MarketPricingGuardTests(unittest.TestCase):
    def test_bitfinex_pair_info_does_not_parse_margin_fields_as_precision(self) -> None:
        manager = ExchangeInfoManager([BITFINEX_EXCHANGE_NAME])
        manager._load_bitfinex_rules_from_pairs({
            "XLMUST": [
                None, None, None, "14.0", "1000000.0",
                None, None, None, 0.5, 0.25, None, None,
            ],
            "ADAUST": [
                None, None, None, "4.0", "250000.0",
                None, None, None, 0.3, 0.15, None, None,
            ],
        })

        xlm = manager.get_rules(BITFINEX_EXCHANGE_NAME, "XLMUSDT")
        ada = manager.get_rules(BITFINEX_EXCHANGE_NAME, "ADAUSDT")

        self.assertIsNotNone(xlm)
        self.assertIsNotNone(ada)
        self.assertEqual(xlm.tick_size, Decimal("0.00001"))
        self.assertEqual(ada.tick_size, Decimal("0.00001"))

    def test_quote_book_mismatch_catches_fake_rounded_bitfinex_quote(self) -> None:
        reason = quote_book_mismatch_reason(
            "XLMUSDT",
            "Bitfinex",
            "MEXC",
            0.1000,
            0.1992,
            [(0.19933, 948772.0)],
            [(0.1992, 100000.0)],
        )

        self.assertIn("quote_book_mismatch", reason)
        self.assertIn("buy=Bitfinex", reason)

    def test_quote_book_mismatch_allows_coherent_quote_and_book(self) -> None:
        reason = quote_book_mismatch_reason(
            "XLMUSDT",
            "Bitfinex",
            "MEXC",
            0.19933,
            0.19920,
            [(0.19933, 948772.0)],
            [(0.19920, 100000.0)],
        )

        self.assertEqual(reason, "")

    def test_mexc_depth_channel_uses_official_partial_depth_format(self) -> None:
        self.assertEqual(
            _depth_channel("BTCUSDT"),
            "spot@public.limit.depth.v3.api.pb@BTCUSDT@20",
        )


if __name__ == "__main__":
    unittest.main()
