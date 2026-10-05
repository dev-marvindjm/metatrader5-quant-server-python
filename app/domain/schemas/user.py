from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", description="User email address")
    password: str = Field(min_length=6, description="Plaintext password (min 6 characters)")
    username: Optional[str] = Field(default=None, min_length=3, max_length=50)
    full_name: Optional[str] = Field(default=None)
    role: str = Field(default="user", description="user | trader | viewer | admin")
    telegram_id: Optional[int] = Field(default=None, description="Optional Telegram User ID for automated signal attribution")


class UserUpdate(BaseModel):
    email: Optional[str] = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: Optional[str] = Field(default=None, min_length=6)
    username: Optional[str] = Field(default=None, min_length=3, max_length=50)
    full_name: Optional[str] = None
    role: Optional[str] = None
    telegram_id: Optional[int] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    email: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    telegram_id: Optional[int] = None
    api_key: Optional[str] = None
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    email_or_username: str = Field(description="Email or username")
    password: str = Field(description="Plaintext password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: UserResponse


class ApiKeyResponse(BaseModel):
    api_key: str
    created_at: datetime
    message: str = "Keep this API key secret. It grants full programmatic access to your account."
