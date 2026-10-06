from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.domain.schemas.common import ActionEnum, BrokerEnum


class SignalCreate(BaseModel):
    source: str = Field(default="webhook", description="telegram | tradingview | webhook | manual")
    telegram_id: Optional[int] = Field(default=None, description="Telegram user/chat ID for tenant attribution")
    symbol: str = Field(description="Trading symbol (e.g. EURUSD, BTCUSDT, EURUSD-OTC)")
    action: ActionEnum = Field(description="BUY or SELL")
    market_type: str = Field(default="BINARY", description="BINARY | FOREX | CRYPTO")
    timeframe: Optional[str] = Field(default=None, description="e.g. M1, M5, H1")
    duration_seconds: Optional[int] = Field(default=None, description="Expiration seconds for binary options")
    entry_price: Optional[float] = Field(default=None)
    stop_loss: Optional[float] = Field(default=None)
    take_profit: Optional[float] = Field(default=None)
    target_broker: Optional[str] = Field(default=None)
    gale_steps: int = Field(default=0, ge=0, le=5)
    gale_multiplier: float = Field(default=2.0, ge=1.0, le=5.0)
    raw_data: Optional[Dict[str, Any]] = Field(default=None)


class SignalExecuteRequest(BaseModel):
    signal_id: Optional[int] = Field(default=None, description="Existing signal ID from DB to execute")
    signal_data: Optional[SignalCreate] = Field(default=None, description="Inline signal payload to ingest and execute immediately")
    target_account_ids: List[int] = Field(min_length=1, description="List of trading account IDs to execute against")
    amount: float = Field(gt=0, description="Amount/volume to execute per account")
    gale_steps: Optional[int] = Field(default=None)
    gale_multiplier: Optional[float] = Field(default=None)


class SignalResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    source: str
    symbol: str
    action: str
    market_type: str
    timeframe: Optional[str] = None
    duration_seconds: Optional[int] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    target_broker: Optional[str] = None
    template_id: Optional[int] = None
    sender_id: Optional[str] = None
    raw_data: Optional[str] = None
    gale_steps: int
    gale_multiplier: float
    status: str
    created_at: datetime


class SignalExecutionSummary(BaseModel):
    signal_id: int
    total_accounts: int
    successful_executions: int
    failed_executions: int
    execution_order_ids: List[int]
