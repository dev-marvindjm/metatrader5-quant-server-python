import sqlalchemy as sa
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, nullable=False, description="Primary email address")
    username: Optional[str] = Field(default=None, unique=True, index=True, description="Optional unique username")
    hashed_password: str = Field(nullable=False, description="PBKDF2-HMAC-SHA256 hashed password")
    full_name: Optional[str] = Field(default=None, description="Full display name")
    
    role: str = Field(
        default="user",
        index=True,
        description="Role: admin | trader | user | viewer",
    )
    
    # Telegram ID mapping for multi-tenant signal ingestion via msg-incoming
    telegram_id: Optional[int] = Field(
        default=None,
        sa_type=sa.BigInteger,
        unique=True,
        index=True,
        description="Telegram numeric User ID for signal attribution",
    )
    
    # Dedicated API key for headless bots, webhooks, or TradingView alerts
    api_key: Optional[str] = Field(
        default=None,
        unique=True,
        index=True,
        description="Personal API key for programmatic trading",
    )
    
    is_active: bool = Field(default=True, index=True)
    is_superuser: bool = Field(default=False)
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
