from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class PositionCloseRequest(BaseModel):
    account_id: int = Field(description="Trading account ID")
    ticket: int = Field(description="Ticket ID of the position to close")
    symbol: str = Field(description="Symbol of the position")
    volume: float = Field(gt=0, description="Volume to close")
    deviation: int = Field(default=20, ge=0)
    magic: int = Field(default=0)
    comment: str = Field(default="Close via API")


class PositionsCloseAllRequest(BaseModel):
    account_id: int = Field(description="Trading account ID")
    order_type: str = Field(default="all", description="'BUY', 'SELL', or 'all'")
    magic: Optional[int] = Field(default=None, description="Optional magic filter")


class PositionInfo(BaseModel):
    ticket: int
    symbol: str
    type: int
    type_str: str = Field(description="'BUY' or 'SELL'")
    volume: float
    price_open: float
    price_current: float
    sl: float = 0.0
    tp: float = 0.0
    profit: float
    swap: float = 0.0
    magic: int = 0
    comment: str = ""
    time: Optional[datetime] = None


class PositionCloseResponse(BaseModel):
    ticket: int
    symbol: str
    closed: bool
    retcode: Optional[int] = None
    order: Optional[int] = None
    price: Optional[float] = None
    message: str
