from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class TickResponse(BaseModel):
    symbol: str
    bid: float
    ask: float
    last: Optional[float] = None
    spread: Optional[float] = None
    time: datetime


class CandleData(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = 0.0


class HistoryRatesRequest(BaseModel):
    symbol: str = Field(description="Symbol name")
    timeframe: str = Field(default="M1", description="M1, M5, M15, M30, H1, H4, D1")
    count: int = Field(default=100, ge=1, le=5000)


class HistoryRatesResponse(BaseModel):
    symbol: str
    timeframe: str
    count: int
    rates: List[CandleData]


class SymbolInfoResponse(BaseModel):
    symbol: str
    description: Optional[str] = None
    point: Optional[float] = None
    digits: Optional[int] = None
    spread: Optional[int] = None
    trade_mode: Optional[int] = None
    currency_base: Optional[str] = None
    currency_profit: Optional[str] = None
