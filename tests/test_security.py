import unittest
from app.core.security import CredentialCipher


class TestSecurityCipher(unittest.TestCase):
    def setUp(self):
        self.cipher = CredentialCipher()

    def test_encrypt_decrypt_dict(self):
        original = {
            "login": 12345678,
            "password": "super-secret-password-123!",
            "server": "Demo-Server",
        }
        encrypted = self.cipher.encrypt(original)
        self.assertIsInstance(encrypted, str)
        self.assertNotEqual(encrypted, str(original))

        decrypted = self.cipher.decrypt(encrypted)
        self.assertEqual(decrypted, original)

    def test_encrypt_decrypt_ssid(self):
        original = {"ssid": "42[\"auth\",{\"session\":\"xyz_pocket_option_token_999\"}]"}
        encrypted = self.cipher.encrypt(original)
        decrypted = self.cipher.decrypt(encrypted)
        self.assertEqual(decrypted["ssid"], original["ssid"])

    def test_invalid_token_handling(self):
        with self.assertRaises(ValueError):
            self.cipher.decrypt("not-a-valid-fernet-token-at-all")


if __name__ == "__main__":
    unittest.main()
