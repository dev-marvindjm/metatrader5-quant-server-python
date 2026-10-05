from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field

from app.domain.enums import GoalType, ChallengeStatus, RankingMetric


class ChallengeCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120, description="Title of the competition")
    description: Optional[str] = Field(default=None, max_length=500)
    goal_type: GoalType = Field(description="TARGET_CAPITAL | TRADE_COUNT | WIN_RATE_PERCENTAGE | PROFIT_FACTOR_RATIO")
    goal_target_value: float = Field(gt=0, description="Target value required to complete the challenge")
    min_sample_trades: int = Field(default=5, ge=1, description="Minimum trades for win rate / profit factor")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    entry_fee: Decimal = Field(default=Decimal("0.0"), ge=0)
    max_drawdown_limit: Optional[Decimal] = Field(default=None, gt=0, description="Risk brake before disqualification")
    allowed_brokers: Optional[List[str]] = None
    allowed_sender_ids: Optional[List[str]] = None
    allowed_template_ids: Optional[List[int]] = None
    is_public: bool = True
    ranking_metric: RankingMetric = RankingMetric.PROGRESS


class ChallengeResponse(BaseModel):
    id: int
    creator_user_id: int
    title: str
    description: Optional[str] = None
    goal_type: GoalType
    goal_target_value: float
    min_sample_trades: int
    start_time: datetime
    end_time: Optional[datetime] = None
    entry_fee: Decimal
    max_drawdown_limit: Optional[Decimal] = None
    allowed_brokers: Optional[List[str]] = None
    allowed_sender_ids: Optional[List[str]] = None
    allowed_template_ids: Optional[List[int]] = None
    is_public: bool
    ranking_metric: RankingMetric
    status: ChallengeStatus
    created_at: datetime
    concluded_at: Optional[datetime] = None
    participants_count: int = 0


class LeaderboardParticipantItem(BaseModel):
    rank_position: Optional[int] = None
    user_id: int
    username: Optional[str] = None
    current_progress_value: float
    progress_percentage: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_percentage: float
    profit_factor: float
    gross_profit: Decimal
    gross_loss: Decimal
    current_drawdown: Decimal
    is_disqualified: bool
    disqualification_reason: Optional[str] = None
    completed_at: Optional[datetime] = None
    joined_at: datetime


class ChallengeLeaderboardResponse(BaseModel):
    challenge_id: int
    challenge_title: str
    status: ChallengeStatus
    goal_type: GoalType
    goal_target_value: float
    total_participants: int
    active_participants: int
    disqualified_participants: int
    completed_participants: int
    leaderboard: List[LeaderboardParticipantItem]


class WinnerHistoryItem(BaseModel):
    challenge_id: int
    title: str
    goal_type: GoalType
    concluded_at: Optional[datetime] = None
    winner_user_id: Optional[int] = None
    winner_username: Optional[str] = None
    winning_progress_value: Optional[float] = None
    total_participants: int
