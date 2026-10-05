from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class TradingAccount(SQLModel, table=True):
    __tablename__ = "trading_accounts"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False, description="Owner user ID")
    broker: str = Field(index=True, description="mt5 | iqoption | quotex | pocketoption")
    account_name: str = Field(description="Descriptive user-facing alias for the account")
    account_number: Optional[str] = Field(default=None, index=True, description="Account login or identifier")
    account_mode: str = Field(default="PRACTICE", description="PRACTICE / DEMO or REAL")
    
    # Encrypted credentials via Fernet (stores JSON with user/pass, ssid, or mt5 login info)
    encrypted_credentials: str = Field(description="Fernet ciphertext containing account credentials")
    
    is_active: bool = Field(default=True, index=True)
    balance: float = Field(default=0.0)
    equity: Optional[float] = Field(default=0.0)
    currency: str = Field(default="USD")
    server: Optional[str] = Field(default=None, description="Broker server for MT5")
    
    last_connected_at: Optional[datetime] = Field(default=None)
    last_error: Optional[str] = Field(default=None)
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
