from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class OrderExecution(SQLModel, table=True):
    __tablename__ = "order_executions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True, description="Owner user ID")
    account_id: int = Field(foreign_key="trading_accounts.id", index=True)
    signal_id: Optional[int] = Field(default=None, foreign_key="trading_signals.id", index=True)
    sender_id: Optional[str] = Field(default=None, index=True, description="Attributed sender/channel source ID")
    template_id: Optional[int] = Field(default=None, index=True, description="Associated parsing template ID")
    
    broker: str = Field(index=True, description="mt5 | iqoption | quotex | pocketoption")
    broker_order_id: Optional[str] = Field(default=None, index=True, description="Deal or ticket identifier from broker")
    
    symbol: str = Field(index=True, description="Resolved execution symbol")
    raw_symbol: Optional[str] = Field(default=None, description="Original requested asset")
    action: str = Field(description="BUY | SELL")
    order_type: str = Field(default="BINARY", description="BINARY | MARKET | LIMIT | STOP")
    
    amount: float = Field(description="Requested lot volume or monetary amount")
    executed_amount: Optional[float] = Field(default=None)
    
    entry_price: Optional[float] = Field(default=None)
    close_price: Optional[float] = Field(default=None)
    stop_loss: Optional[float] = Field(default=None)
    take_profit: Optional[float] = Field(default=None)
    duration_seconds: Optional[int] = Field(default=None, description="Duration in seconds if binary option")
    
    profit_loss: Optional[float] = Field(default=None, description="Realized PnL")
    drawdown: Optional[float] = Field(default=None, description="Maximum adverse excursion if tracked")
    spread: Optional[float] = Field(default=None)
    slippage: Optional[float] = Field(default=None)
    latency_ms: Optional[int] = Field(default=None, description="Round-trip execution latency in ms")
    
    gale_step: int = Field(default=0, description="0 = initial trade, 1+ = martingale steps")
    status: str = Field(
        default="PENDING",
        index=True,
        description="PENDING | SUBMITTED | FILLED | CLOSED | WON | LOST | REJECTED | FAILED",
    )
    error_log: Optional[str] = Field(default=None, description="Detailed error traceback or rejection reason")
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    closed_at: Optional[datetime] = Field(default=None)
