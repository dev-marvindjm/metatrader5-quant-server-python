import unittest
from starlette.testclient import TestClient
from app.main import create_app
from app.domain.models import TradingAccount, BrokerCatalog
from sqlmodel import SQLModel, create_engine
from sqlmodel.pool import StaticPool


class TestApiEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = TestClient(cls.app)

    def test_root_endpoint(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "operational")
        self.assertIn("docs", data)

    def test_martingale_calculator(self):
        resp = self.client.get("/api/v1/brokers/binary/martingale-calculator?initial_amount=10&steps=3&multiplier=2.0&payout_percent=85")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        calc_data = data["data"]
        self.assertEqual(calc_data["initial_amount"], 10.0)
        self.assertEqual(calc_data["steps"], 3)
        self.assertEqual(len(calc_data["schedule"]), 4)  # Step 0, 1, 2, 3

    def test_unauthenticated_order_rejection(self):
        resp = self.client.post("/api/v1/orders/binary", json={})
        self.assertEqual(resp.status_code, 401)

    def test_validation_error_response_format(self):
        from app.core.auth import get_current_user, get_current_active_user
        from app.domain.models.user import User

        mock_user = User(
            id=1,
            email="test@quant.com",
            hashed_password="hash",
            role="trader",
            is_active=True,
        )
        self.app.dependency_overrides[get_current_user] = lambda: mock_user
        self.app.dependency_overrides[get_current_active_user] = lambda: mock_user
        try:
            # Missing required fields
            resp = self.client.post("/api/v1/orders/binary", json={})
            self.assertEqual(resp.status_code, 422)
            data = resp.json()
            self.assertFalse(data["success"])
            self.assertIn("error", data)
            self.assertEqual(data["error"]["code"], "VALIDATION_ERROR")
            self.assertIn("correlation_id", data)
        finally:
            self.app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
