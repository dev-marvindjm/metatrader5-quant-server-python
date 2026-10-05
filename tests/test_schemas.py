import unittest
from app.domain.schemas.common import ActionEnum, BrokerEnum, AccountModeEnum
from app.domain.schemas.order import BinaryOrderCreate, MarketOrderCreate
from app.domain.schemas.account import AccountCreate


class TestSchemasValidation(unittest.TestCase):
    def test_binary_order_validation(self):
        order = BinaryOrderCreate(
            account_id=1,
            symbol="EURUSD",
            action=ActionEnum.BUY,
            amount=25.0,
            duration_seconds=60,
            gale_steps=2,
            gale_multiplier=2.2,
        )
        self.assertEqual(order.account_id, 1)
        self.assertEqual(order.amount, 25.0)
        self.assertEqual(order.gale_steps, 2)

    def test_market_order_validation(self):
        order = MarketOrderCreate(
            account_id=2,
            symbol="GBPUSD",
            action=ActionEnum.SELL,
            volume=0.5,
            sl=1.2500,
            tp=1.2300,
            deviation=15,
        )
        self.assertEqual(order.volume, 0.5)
        self.assertEqual(order.action, ActionEnum.SELL)
        self.assertEqual(order.sl, 1.2500)

    def test_account_create_validation(self):
        acc = AccountCreate(
            broker=BrokerEnum.MT5,
            account_name="Main MT5 Account",
            account_mode=AccountModeEnum.REAL,
            credentials={"login": 12345, "password": "abc", "server": "Broker-Live"},
        )
        self.assertEqual(acc.broker, BrokerEnum.MT5)
        self.assertEqual(acc.account_mode, AccountModeEnum.REAL)


if __name__ == "__main__":
    unittest.main()
