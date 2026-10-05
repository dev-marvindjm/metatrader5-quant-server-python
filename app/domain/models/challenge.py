from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
import sqlalchemy as sa
from sqlmodel import SQLModel, Field

from app.domain.enums import GoalType, ChallengeStatus, RankingMetric


class Challenge(SQLModel, table=True):
    __tablename__ = "challenges"

    id: Optional[int] = Field(default=None, primary_key=True)
    creator_user_id: int = Field(foreign_key="users.id", index=True, description="Creator user ID")
    title: str = Field(index=True, description="Title of the challenge / tournament")
    description: Optional[str] = Field(default=None)

    goal_type: GoalType = Field(
        sa_column=sa.Column(sa.Enum(GoalType), nullable=False, index=True),
        description="Target milestone metric",
    )
    goal_target_value: float = Field(
        description="Milestone target value (e.g. 1000.0 profit, 50 trades, 80% win rate, 2.5 PF)",
    )
    min_sample_trades: int = Field(
        default=5,
        description="Minimum trades before win rate / profit factor can complete",
    )

    start_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    end_time: Optional[datetime] = Field(default=None, description="Optional time cutoff")
    entry_fee: Decimal = Field(
        default=Decimal("0.0"),
        sa_column=sa.Column(sa.Numeric(14, 4), nullable=False, server_default="0.0"),
    )
    max_drawdown_limit: Optional[Decimal] = Field(
        default=None,
        sa_column=sa.Column(sa.Numeric(14, 4), nullable=True),
        description="Maximum drawdown limit allowed before participant is disqualified",
    )

    # Ingestion & exclusion filters
    allowed_brokers: Optional[List[str]] = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
        description="Allowed brokers for challenge operations",
    )
    allowed_sender_ids: Optional[List[str]] = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
        description="Allowed sender IDs for challenge operations",
    )
    allowed_template_ids: Optional[List[int]] = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
        description="Allowed template IDs for challenge operations",
    )

    is_public: bool = Field(default=True, index=True)
    ranking_metric: RankingMetric = Field(
        default=RankingMetric.PROGRESS,
        sa_column=sa.Column(sa.Enum(RankingMetric), nullable=False, server_default="'PROGRESS'"),
    )
    status: ChallengeStatus = Field(
        default=ChallengeStatus.RUNNING,
        sa_column=sa.Column(sa.Enum(ChallengeStatus), nullable=False, index=True),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    concluded_at: Optional[datetime] = Field(default=None)


class ChallengeParticipant(SQLModel, table=True):
    __tablename__ = "challenge_participants"
    __table_args__ = (
        sa.UniqueConstraint("challenge_id", "user_id", name="uq_challenge_participant"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    challenge_id: int = Field(
        foreign_key="challenges.id",
        index=True,
        ondelete="CASCADE",
        nullable=False,
    )
    user_id: int = Field(
        foreign_key="users.id",
        index=True,
        ondelete="CASCADE",
        nullable=False,
    )

    current_progress_value: float = Field(
        default=0.0,
        description="Current evaluated progress score",
    )
    peak_progress_value: float = Field(
        default=0.0,
        description="Highest watermark achieved for drawdown calculation",
    )

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

    current_drawdown: Decimal = Field(
        default=Decimal("0.0"),
        sa_column=sa.Column(sa.Numeric(14, 4), nullable=False, server_default="0.0"),
        description="Peak-to-trough drop recorded",
    )
    rank_position: Optional[int] = Field(default=None, index=True)

    is_disqualified: bool = Field(default=False, index=True)
    disqualification_reason: Optional[str] = Field(default=None)

    joined_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when participant achieved target goal",
    )
