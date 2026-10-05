import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db
from app.domain.models.user import User

# Bearer Token & API Key schemes (auto_error=False to allow fallback between Bearer and API Key)
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ============================================================================
# Password Hashing (PBKDF2-HMAC-SHA256, 100,000 iterations + 128-bit salt)
# ============================================================================
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    iterations = 100000
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${derived}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_hash = parts[3]
        calc_hash = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return secrets.compare_digest(calc_hash, expected_hash)
    except Exception:
        return False


# ============================================================================
# API Key Generator
# ============================================================================
def generate_api_key(prefix: str = "quant") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


# ============================================================================
# JWT Tokens (HMAC-SHA256, Zero-dependency RFC 7519 Compliant)
# ============================================================================
def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def create_access_token(
    user_id: int,
    email: str,
    role: str = "user",
    expires_delta: Optional[timedelta] = None,
) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=7))
    
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    
    h_b64 = _b64_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    message = f"{h_b64}.{p_b64}"
    
    sig = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    sig_b64 = _b64_encode(sig)
    
    return f"{message}.{sig_b64}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h_b64, p_b64, sig_b64 = parts
        message = f"{h_b64}.{p_b64}"
        
        expected_sig = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        
        actual_sig = _b64_decode(sig_b64)
        if not secrets.compare_digest(expected_sig, actual_sig):
            return None
        
        payload_bytes = _b64_decode(p_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        
        # Verify expiration
        exp = payload.get("exp")
        if not exp or datetime.now(timezone.utc).timestamp() > exp:
            return None
            
        return payload
    except Exception:
        return None


# ============================================================================
# FastAPI Authentication Dependencies
# ============================================================================
async def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Authenticates requests using either:
    1. HTTP Bearer JWT token in Authorization header
    2. Personal X-API-Key in header
    """
    user: Optional[User] = None

    # 1. Try JWT Bearer authentication
    if auth_header and auth_header.credentials:
        payload = decode_access_token(auth_header.credentials)
        if payload and "sub" in payload:
            try:
                user_id = int(payload["sub"])
                stmt = select(User).where(User.id == user_id)
                res = await db.exec(stmt)
                user = res.first()
            except (ValueError, TypeError):
                pass

    # 2. Try API Key authentication if no valid Bearer token
    if not user and api_key:
        stmt = select(User).where(User.api_key == api_key)
        res = await db.exec(stmt)
        user = res.first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials. Please provide a valid Bearer token or X-API-Key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account.",
        )
    return current_user


async def get_current_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    if current_user.role != "admin" and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Administrator privileges required.",
        )
    return current_user
