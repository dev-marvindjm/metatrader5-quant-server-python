from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field

from app.domain.enums import GoalType, FundStatus, TradeOutcome


class FundCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120, description="Title of the accumulation goal / fund")
    description: Optional[str] = Field(default=None, max_length=500)
    target_amount: Optional[Decimal] = Field(default=None, description="Monetary target if applicable")
    goal_type: GoalType = Field(description="TARGET_CAPITAL | TRADE_COUNT | WIN_RATE_PERCENTAGE | PROFIT_FACTOR_RATIO")
    goal_target_value: float = Field(gt=0, description="Numeric milestone goal (dollars, trade count, win rate %, profit factor)")
    max_drawdown_limit: Optional[Decimal] = Field(default=None, gt=0, description="Max allowed drawdown before failure")
    max_consecutive_losses: Optional[int] = Field(default=None, ge=1)
    min_sample_trades: int = Field(default=5, ge=1, description="Minimum trades for win rate/profit factor")
    
    # Ingestion filters
    allowed_brokers: Optional[List[str]] = Field(default=None, description="e.g. ['mt5', 'quotex', 'pocketoption']")
    allowed_sender_ids: Optional[List[str]] = Field(default=None, description="e.g. ['vip_channel', '-100123456789']")
    allowed_template_ids: Optional[List[int]] = Field(default=None, description="e.g. [1, 2]")


class FundContributionAuditItem(BaseModel):
    id: int
    fund_id: Optional[int] = None
    challenge_participant_id: Optional[int] = None
    order_execution_id: Optional[int] = None
    broker: str
    symbol: str
    broker_ticket: Optional[str] = None
    sender_id: Optional[str] = None
    template_id: Optional[int] = None
    profit_loss: Decimal
    outcome: TradeOutcome
    previous_progress_value: float
    new_progress_value: float
    drawdown_recorded: Decimal
    timestamp: datetime


class FundResponse(BaseModel):
    id: int
    user_id: int
    title: str
    description: Optional[str] = None
    target_amount: Optional[Decimal] = None
    current_amount: Decimal
    goal_type: GoalType
    goal_target_value: float
    current_progress_value: float
    progress_percentage: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_percentage: float
    profit_factor: float
    current_drawdown: Decimal
    max_drawdown_limit: Optional[Decimal] = None
    allowed_brokers: Optional[List[str]] = None
    allowed_sender_ids: Optional[List[str]] = None
    allowed_template_ids: Optional[List[int]] = None
    status: FundStatus
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class FundMetricsResponse(BaseModel):
    fund: FundResponse
    audits: List[FundContributionAuditItem]
    total_audited_trades: int
