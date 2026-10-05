from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
import sqlalchemy as sa
from sqlmodel import SQLModel, Field

from app.domain.enums import GoalType, FundStatus, TradeOutcome


class Fund(SQLModel, table=True):
    __tablename__ = "funds"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, description="Owner user ID")
    title: str = Field(index=True, description="Human friendly title for the accumulation goal")
    description: Optional[str] = Field(default=None)

    target_amount: Optional[Decimal] = Field(
        default=None,
        sa_column=sa.Column(sa.Numeric(14, 4), nullable=True),
        description="Optional currency target (USD/EUR) to reach",
    )
    current_amount: Decimal = Field(
        default=Decimal("0.0"),
        sa_column=sa.Column(sa.Numeric(14, 4), nullable=False, server_default="0.0"),
        description="Accumulated net profit/loss amount",
    )
    goal_type: GoalType = Field(
        sa_column=sa.Column(sa.Enum(GoalType), nullable=False, index=True),
        description="Type of quantitative milestone",
    )
    goal_target_value: float = Field(
        description="Milestone target value (e.g., 1000.0 for $1000, 50.0 trades, 75.0 for 75% win rate, 2.0 profit factor)",
    )
    current_progress_value: float = Field(
        default=0.0,
        description="Current evaluated progress matching goal_type metric",
    )
    peak_progress_value: float = Field(
        default=0.0,
        description="Highest watermark achieved for drawdown calculation",
    )

    # Trade statistics
    total_trades: int = Field(default=0)
    winning_trades: int = Field(default=0)
    losing_trades: int = Field(default=0)
    gross_profit: Decimal = Field(
        default=Decimal("0.0"),
        sa_column=sa.Column(sa.Numeric(14, 4), nullable=False, server_default="0.0"),
    )
    gross_loss: Decimal = Field(
        default=Decimal("0.0"),
        sa_column=sa.Column(sa.Numeric(14, 4), nullable=False, server_default="0.0"),
    )

    # Risk parameters
    current_drawdown: Decimal = Field(
        default=Decimal("0.0"),
        sa_column=sa.Column(sa.Numeric(14, 4), nullable=False, server_default="0.0"),
        description="Peak-to-trough drop recorded",
    )
    max_drawdown_limit: Optional[Decimal] = Field(
        default=None,
        sa_column=sa.Column(sa.Numeric(14, 4), nullable=True),
        description="Maximum permissible drawdown before failing",
    )
    max_consecutive_losses: Optional[int] = Field(default=None)
    current_consecutive_losses: int = Field(default=0)
    min_sample_trades: int = Field(
        default=5,
        description="Minimum trades needed before win-rate or profit-factor can trigger completion",
    )

    # Ingestion & exclusion filters
    allowed_brokers: Optional[List[str]] = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
        description="List of brokers allowed to contribute (e.g. ['mt5', 'quotex'])",
    )
    allowed_sender_ids: Optional[List[str]] = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
        description="List of Telegram/webhook sender IDs allowed",
    )
    allowed_template_ids: Optional[List[int]] = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
        description="List of SignalTemplate IDs allowed",
    )

    status: FundStatus = Field(
        default=FundStatus.ACTIVE,
        sa_column=sa.Column(sa.Enum(FundStatus), nullable=False, index=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Optional[datetime] = Field(default=None)


class FundContributionAudit(SQLModel, table=True):
    __tablename__ = "fund_contribution_audits"

    id: Optional[int] = Field(default=None, primary_key=True)
    fund_id: Optional[int] = Field(
        default=None,
        foreign_key="funds.id",
        index=True,
        ondelete="CASCADE",
        nullable=True,
    )
    challenge_participant_id: Optional[int] = Field(
        default=None,
        foreign_key="challenge_participants.id",
        index=True,
        ondelete="CASCADE",
        nullable=True,
    )
    order_execution_id: Optional[int] = Field(
        default=None,
        foreign_key="order_executions.id",
        index=True,
        nullable=True,
    )

    broker: str = Field(index=True)
    symbol: str
    broker_ticket: Optional[str] = Field(default=None)
    sender_id: Optional[str] = Field(default=None, index=True)
    template_id: Optional[int] = Field(default=None, index=True)
    trade_action: str = Field(default="BUY")

    profit_loss: Decimal = Field(
        default=Decimal("0.0"),
        sa_column=sa.Column(sa.Numeric(14, 4), nullable=False),
    )
    outcome: TradeOutcome = Field(
        sa_column=sa.Column(sa.Enum(TradeOutcome), nullable=False),
    )
    previous_progress_value: float = Field(default=0.0)
    new_progress_value: float = Field(default=0.0)
    drawdown_recorded: Decimal = Field(
        default=Decimal("0.0"),
        sa_column=sa.Column(sa.Numeric(14, 4), nullable=False),
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
