from datetime import datetime, timezone
from enum import Enum
from typing import Generic, Optional, TypeVar, Any
from pydantic import BaseModel, Field

T = TypeVar("T")


class BrokerEnum(str, Enum):
    MT5 = "mt5"
    IQOPTION = "iqoption"
    QUOTEX = "quotex"
    POCKETOPTION = "pocketoption"


class AccountModeEnum(str, Enum):
    PRACTICE = "PRACTICE"
    REAL = "REAL"


class ActionEnum(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderTypeEnum(str, Enum):
    BINARY = "BINARY"
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatusEnum(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    CLOSED = "CLOSED"
    WON = "WON"
    LOST = "LOST"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ApiResponse(BaseModel, Generic[T]):
    """Standardized response envelope for all API endpoints."""
    success: bool = Field(default=True)
    data: Optional[T] = Field(default=None)
    error: Optional[Any] = Field(default=None)
    correlation_id: Optional[str] = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
