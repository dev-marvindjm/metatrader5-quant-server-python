from enum import Enum


class GoalType(str, Enum):
    """
    Types of quantitative targets for Funds and Challenges.
    """
    TARGET_CAPITAL = "TARGET_CAPITAL"          # Accumulate monetary P&L / balance (e.g. $1,000 USD)
    TRADE_COUNT = "TRADE_COUNT"                # Complete N audited trades
    WIN_RATE_PERCENTAGE = "WIN_RATE_PERCENTAGE"# Achieve >= X% win rate over min sample
    PROFIT_FACTOR_RATIO = "PROFIT_FACTOR_RATIO"# Achieve Gross Profit / Gross Loss >= Y


class FundStatus(str, Enum):
    """
    Operational lifecycle state of an accumulation Fund.
    """
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"


class ChallengeStatus(str, Enum):
    """
    Lifecycle state of a competitive Challenge.
    """
    REGISTRATION = "REGISTRATION"
    RUNNING = "RUNNING"
    CONCLUDED = "CONCLUDED"
    CANCELLED = "CANCELLED"


class TradeOutcome(str, Enum):
    """
    Evaluation outcome of a closed trade/order.
    """
    WIN = "WIN"
    LOSS = "LOSS"
    DRAW = "DRAW"


class RankingMetric(str, Enum):
    """
    Primary metric used to sort participants on the Leaderboard.
    """
    PROGRESS = "PROGRESS"
    WIN_RATE = "WIN_RATE"
    PROFIT_FACTOR = "PROFIT_FACTOR"
    SPEED = "SPEED"
