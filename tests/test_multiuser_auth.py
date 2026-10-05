import unittest
import time
from datetime import timedelta
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    generate_api_key,
)
from app.domain.schemas.user import UserCreate, LoginRequest


class TestMultiuserAuth(unittest.TestCase):
    def test_password_hashing_and_verification(self):
        password = "SuperSecretTraderPass2026!"
        hashed = hash_password(password)
        self.assertTrue(hashed.startswith("pbkdf2_sha256$100000$"))
        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("WrongPassword!", hashed))
        self.assertFalse(verify_password("", hashed))

    def test_jwt_token_flow(self):
        token = create_access_token(user_id=42, email="test@quant.com", role="trader", expires_delta=timedelta(hours=1))
        self.assertIsInstance(token, str)

        decoded = decode_access_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["sub"], "42")
        self.assertEqual(decoded["email"], "test@quant.com")
        self.assertEqual(decoded["role"], "trader")
        self.assertIn("exp", decoded)

    def test_jwt_expired_token(self):
        # Create expired token (-10 seconds)
        expired_token = create_access_token(user_id=1, email="admin@quant.com", role="admin", expires_delta=timedelta(seconds=-10))
        decoded = decode_access_token(expired_token)
        self.assertIsNone(decoded, "Expired token should return None")

    def test_jwt_tampered_token(self):
        token = create_access_token(user_id=1, email="admin@quant.com", role="admin")
        parts = token.split(".")
        # Tamper signature
        tampered_token = f"{parts[0]}.{parts[1]}.tampered_signature"
        decoded = decode_access_token(tampered_token)
        self.assertIsNone(decoded, "Tampered token should return None")

    def test_api_key_generation(self):
        key1 = generate_api_key("quant_user")
        key2 = generate_api_key("quant_user")
        self.assertTrue(key1.startswith("quant_user_"))
        self.assertTrue(key2.startswith("quant_user_"))
        self.assertNotEqual(key1, key2)
        self.assertGreater(len(key1), 30)

    def test_user_create_schema_validation(self):
        # Valid user
        user = UserCreate(
            email="trader@quant.com",
            password="securePassword123!",
            username="trader1",
            role="trader",
            telegram_id=123456789,
        )
        self.assertEqual(user.email, "trader@quant.com")
        self.assertEqual(user.telegram_id, 123456789)

        # Invalid email format should fail
        with self.assertRaises(Exception):
            UserCreate(
                email="not-an-email",
                password="securePassword123!",
            )

        # Short password (< 6 chars) should fail
        with self.assertRaises(Exception):
            UserCreate(
                email="valid@quant.com",
                password="123",
            )


if __name__ == "__main__":
    unittest.main()
