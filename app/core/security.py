import json
import logging
from typing import Any, Dict, Union
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings

logger = logging.getLogger(__name__)


class CredentialCipher:
    """
    Symmetric encryption service for broker credentials and sensitive access tokens.
    Uses Fernet (AES-128 in CBC mode with HMAC authentication) with keys loaded via settings.
    """

    def __init__(self, key: Union[str, bytes] = settings.FERNET_KEY):
        if isinstance(key, str):
            key = key.encode()
        try:
            self.cipher = Fernet(key)
        except Exception as e:
            logger.warning(f"Invalid FERNET_KEY provided ({e}), generating ephemeral key for safety.")
            self.cipher = Fernet(Fernet.generate_key())

    def encrypt(self, data: Union[str, Dict[str, Any]]) -> str:
        """
        Encrypts a string or dictionary into a secure URL-safe base64 string.
        """
        if isinstance(data, dict):
            raw_text = json.dumps(data)
        else:
            raw_text = str(data)

        encrypted_bytes = self.cipher.encrypt(raw_text.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, encrypted_text: str) -> Dict[str, Any]:
        """
        Decrypts an encrypted string and parses it back into a dictionary.
        If it's plain text, wraps it in {'raw': text}.
        """
        if not encrypted_text:
            return {}

        try:
            decrypted_bytes = self.cipher.decrypt(encrypted_text.encode("utf-8"))
            decrypted_str = decrypted_bytes.decode("utf-8")
            try:
                return json.loads(decrypted_str)
            except json.JSONDecodeError:
                return {"raw": decrypted_str}
        except InvalidToken:
            logger.error("Failed to decrypt credentials: Invalid Token or altered ciphertext.")
            raise ValueError("Invalid or corrupted credential token.")
        except Exception as exc:
            logger.error(f"Unexpected error decrypting credentials: {exc}")
            raise ValueError(f"Credential decryption error: {str(exc)}")


cipher = CredentialCipher()
