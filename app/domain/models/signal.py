from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class SignalTemplate(SQLModel, table=True):
    __tablename__ = "signal_templates"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, description="Template identifier name, e.g. 'Binarias VIP M1'")
    description: Optional[str] = Field(default=None)
    pattern: Optional[str] = Field(default=None, description="Parsing regex or grammar pattern")
    target_broker: Optional[str] = Field(default=None, description="mt5 | quotex | pocketoption | iqoption")
    market_type: str = Field(default="BINARY", description="BINARY | FOREX | CRYPTO | CFD")
    default_amount: float = Field(default=10.0)
    default_duration_seconds: Optional[int] = Field(default=60)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SenderRule(SQLModel, table=True):
    __tablename__ = "sender_rules"

    id: Optional[int] = Field(default=None, primary_key=True)
    sender_id: str = Field(unique=True, index=True, description="Telegram numeric ID, channel username, or webhook key")
    channel_name: Optional[str] = Field(default=None, description="Human friendly channel or group title")
    default_template_id: Optional[int] = Field(default=None, foreign_key="signal_templates.id", index=True)
    is_trusted: bool = Field(default=True, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TradingSignal(SQLModel, table=True):
    __tablename__ = "trading_signals"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True, description="Owner user ID if personalized")
    sender_id: Optional[str] = Field(default=None, index=True, description="Attributed sender/channel source ID")
    template_id: Optional[int] = Field(default=None, foreign_key="signal_templates.id", index=True, description="Associated parsing template")
    
    source: str = Field(default="webhook", index=True, description="telegram | tradingview | webhook | manual")
    symbol: str = Field(index=True, description="Raw symbol parsed from signal")
    action: str = Field(index=True, description="BUY | SELL")
    market_type: str = Field(default="BINARY", description="BINARY | FOREX | CRYPTO | CFD")
    timeframe: Optional[str] = Field(default=None, description="e.g. M1, M5, H1")
    duration_seconds: Optional[int] = Field(default=None, description="Expiration in seconds for binary options")
    
    entry_price: Optional[float] = Field(default=None)
    stop_loss: Optional[float] = Field(default=None)
    take_profit: Optional[float] = Field(default=None)
    target_broker: Optional[str] = Field(default=None, description="Target broker code if constrained")
    
    gale_steps: int = Field(default=0, description="Martingale steps configured")
    gale_multiplier: float = Field(default=2.0)
    
    status: str = Field(
        default="RECEIVED",
        index=True,
        description="RECEIVED | EXECUTING | EXECUTED | REJECTED | EXPIRED",
    )
    raw_data: Optional[str] = Field(default=None, description="Original signal JSON or text string")
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
