import unittest
from app.services.brokers.base import IBrokerAdapter


class DummyBrokerAdapter(IBrokerAdapter):
    async def connect(self):
        pass
    async def is_connected(self):
        return True
    async def get_balance(self):
        pass
    async def get_current_price(self, symbol: str):
        pass
    async def close(self):
        pass


class TestBrokerBaseUtilities(unittest.TestCase):
    def setUp(self):
        self.adapter = DummyBrokerAdapter()

    def test_parse_asset_info_standard(self):
        base, is_otc, is_perp = self.adapter.parse_asset_info("EURUSD")
        self.assertEqual(base, "EURUSD")
        self.assertFalse(is_otc)
        self.assertFalse(is_perp)

    def test_parse_asset_info_with_slash(self):
        base, is_otc, is_perp = self.adapter.parse_asset_info("EUR/USD")
        self.assertEqual(base, "EURUSD")
        self.assertFalse(is_otc)
        self.assertFalse(is_perp)

    def test_parse_asset_info_otc_variants(self):
        cases = [
            ("EURUSD-OTC", "EURUSD", True),
            ("EURUSD_otc", "EURUSD", True),
            ("EURUSD (OTC)", "EURUSD", True),
            ("GBPUSD [OTC]", "GBPUSD", True),
        ]
        for raw, expected_base, expected_otc in cases:
            b, otc, perp = self.adapter.parse_asset_info(raw)
            self.assertEqual(b, expected_base, f"Failed for {raw}")
            self.assertEqual(otc, expected_otc, f"Failed for {raw}")
            self.assertFalse(perp)

    def test_parse_asset_info_perp(self):
        b, otc, perp = self.adapter.parse_asset_info("BTCUSDT.P")
        self.assertEqual(b, "BTCUSDT")
        self.assertTrue(perp)
        self.assertFalse(otc)

    def test_format_broker_asset(self):
        # IQ Option format: BASE-OTC
        self.assertEqual(self.adapter.format_broker_asset("EURUSD (OTC)", "iqoption"), "EURUSD-OTC")
        self.assertEqual(self.adapter.format_broker_asset("EURUSD", "iqoption"), "EURUSD")

        # Quotex format: BASE_otc
        self.assertEqual(self.adapter.format_broker_asset("EURUSD-OTC", "quotex"), "EURUSD_otc")
        self.assertEqual(self.adapter.format_broker_asset("EURUSD", "quotex"), "EURUSD")

        # MT5 format: standard clean base
        self.assertEqual(self.adapter.format_broker_asset("EURUSD_otc", "mt5"), "EURUSD")


if __name__ == "__main__":
    unittest.main()
