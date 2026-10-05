from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.domain.schemas.common import ActionEnum, OrderTypeEnum, OrderStatusEnum


class BinaryOrderCreate(BaseModel):
    account_id: int = Field(description="Database ID of the trading account")
    symbol: str = Field(description="Asset to trade (e.g. EURUSD, EURUSD-OTC)")
    action: ActionEnum = Field(description="BUY (CALL) or SELL (PUT)")
    amount: float = Field(gt=0, description="Monetary amount to invest in this trade")
    duration_seconds: int = Field(default=60, ge=5, description="Expiration time in seconds")
    gale_steps: int = Field(default=0, ge=0, le=5, description="Martingale recovery steps")
    gale_multiplier: float = Field(default=2.0, ge=1.0, le=5.0, description="Martingale multiplier on loss")


class MarketOrderCreate(BaseModel):
    account_id: int = Field(description="Database ID of the MT5 trading account")
    symbol: str = Field(description="Trading instrument symbol (e.g. EURUSD, GBPUSD)")
    action: ActionEnum = Field(description="BUY or SELL")
    volume: float = Field(gt=0, description="Trading lot volume (e.g. 0.01, 0.1, 1.0)")
    sl: Optional[float] = Field(default=None, description="Stop Loss absolute price")
    tp: Optional[float] = Field(default=None, description="Take Profit absolute price")
    deviation: int = Field(default=20, ge=0, description="Max price deviation in points")
    comment: str = Field(default="", max_length=100)
    magic: int = Field(default=0, description="EA / Strategy Magic number identifier")
    type_filling: str = Field(default="ORDER_FILLING_IOC", description="ORDER_FILLING_IOC | ORDER_FILLING_FOK | ORDER_FILLING_RETURN")


class PendingOrderCreate(BaseModel):
    account_id: int = Field(description="Database ID of the MT5 trading account")
    symbol: str = Field(description="Trading instrument symbol")
    order_type: str = Field(description="BUY_LIMIT | SELL_LIMIT | BUY_STOP | SELL_STOP")
    volume: float = Field(gt=0)
    price: float = Field(gt=0, description="Target execution price")
    sl: Optional[float] = Field(default=None)
    tp: Optional[float] = Field(default=None)
    comment: str = Field(default="")
    magic: int = Field(default=0)


class OrderExecutionResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    account_id: int
    signal_id: Optional[int] = None
    broker: str
    broker_order_id: Optional[str] = None
    symbol: str
    raw_symbol: Optional[str] = None
    action: str
    order_type: str
    amount: float
    executed_amount: Optional[float] = None
    entry_price: Optional[float] = None
    close_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    duration_seconds: Optional[int] = None
    profit_loss: Optional[float] = None
    drawdown: Optional[float] = None
    spread: Optional[float] = None
    slippage: Optional[float] = None
    latency_ms: Optional[int] = None
    gale_step: int = 0
    status: str
    error_log: Optional[str] = None
    created_at: datetime
    closed_at: Optional[datetime] = None


class OrderHistoryFilter(BaseModel):
    account_id: Optional[int] = None
    broker: Optional[str] = None
    symbol: Optional[str] = None
    status: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
