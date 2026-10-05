import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc

from app.domain.enums import (
    GoalType,
    FundStatus,
    ChallengeStatus,
    TradeOutcome,
    RankingMetric,
)
from app.domain.models.fund import Fund, FundContributionAudit
from app.domain.models.challenge import Challenge, ChallengeParticipant
from app.domain.models.signal import TradingSignal, SignalTemplate, SenderRule
from app.domain.models.order import OrderExecution

logger = logging.getLogger("quant_server.progress_evaluator")


class TradeSettledPayload(BaseModel):
    """
    Standard event payload dispatched when a trade closes.
    """
    order_id: Optional[int] = None
    user_id: int
    broker: str
    symbol: str
    broker_ticket: Optional[str] = None
    sender_id: Optional[str] = None
    template_id: Optional[int] = None
    profit_loss: float
    action: str = "BUY"
    outcome: TradeOutcome


class ProgressEvaluationResult(BaseModel):
    """
    Audit and status summary after processing a settled trade.
    """
    funds_updated: List[int] = Field(default_factory=list)
    funds_completed: List[int] = Field(default_factory=list)
    funds_failed: List[int] = Field(default_factory=list)
    challenges_updated: List[int] = Field(default_factory=list)
    participants_completed: List[int] = Field(default_factory=list)
    participants_disqualified: List[int] = Field(default_factory=list)
    audits_created: int = 0


def matches_filters(
    broker: str,
    sender_id: Optional[str],
    template_id: Optional[int],
    allowed_brokers: Optional[List[str]],
    allowed_sender_ids: Optional[List[str]],
    allowed_template_ids: Optional[List[int]],
) -> bool:
    """
    Verifies if a trade satisfies the inclusion/exclusion filters of a Fund or Challenge.
    """
    # 1. Broker Filter
    if allowed_brokers:
        normalized_allowed = [b.lower().strip() for b in allowed_brokers]
        if broker.lower().strip() not in normalized_allowed:
            return False

    # 2. Sender ID Filter
    if allowed_sender_ids:
        if not sender_id or sender_id not in allowed_sender_ids:
            return False

    # 3. Template ID Filter
    if allowed_template_ids:
        if template_id is None or template_id not in allowed_template_ids:
            return False

    return True


def compute_metrics(
    total_trades: int,
    winning_trades: int,
    gross_profit: Decimal,
    gross_loss: Decimal,
) -> Tuple[float, float]:
    """
    Computes (win_rate_percentage, profit_factor).
    """
    win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
    if gross_loss > 0:
        profit_factor = float(gross_profit / gross_loss)
    else:
        profit_factor = float(gross_profit) if gross_profit > 0 else 0.0
    return win_rate, profit_factor


async def recalculate_challenge_leaderboard(
    challenge_id: int,
    db: AsyncSession,
) -> List[ChallengeParticipant]:
    """
    Recalculates dynamic real-time ranking for all participants of a challenge.
    Rules:
    1. Completed participants rank highest, ordered by completed_at ASC (first to complete).
    2. Active participants follow, ordered by ranking_metric / progress DESC.
    3. Disqualified participants rank last, ordered by progress DESC.
    """
    stmt = (
        select(ChallengeParticipant)
        .where(ChallengeParticipant.challenge_id == challenge_id)
    )
    res = await db.exec(stmt)
    participants = list(res.all())
    if not participants:
        return []

    # Get challenge ranking metric
    challenge_stmt = select(Challenge).where(Challenge.id == challenge_id)
    c_res = await db.exec(challenge_stmt)
    challenge = c_res.first()
    ranking_metric = challenge.ranking_metric if challenge else RankingMetric.PROGRESS

    def sort_key(p: ChallengeParticipant):
        # Tuple ordering:
        # group 0: completed, group 1: active, group 2: disqualified
        if p.is_disqualified:
            group = 2
        elif p.completed_at is not None:
            group = 0
        else:
            group = 1

        completed_timestamp = p.completed_at.timestamp() if p.completed_at else float("inf")

        win_rate, pf = compute_metrics(p.total_trades, p.winning_trades, p.gross_profit, p.gross_loss)

        if ranking_metric == RankingMetric.WIN_RATE:
            score = win_rate
        elif ranking_metric == RankingMetric.PROFIT_FACTOR:
            score = pf
        else:
            score = p.current_progress_value

        # For group 0 (completed), lowest timestamp first, then highest score
        # For group 1 & 2, highest score first (-score), then -total_trades
        return (group, completed_timestamp, -score, -p.total_trades)

    participants.sort(key=sort_key)

    for idx, p in enumerate(participants, start=1):
        p.rank_position = idx
        db.add(p)

    return participants


async def evaluate_trade_progress(
    trade: TradeSettledPayload,
    db: AsyncSession,
) -> ProgressEvaluationResult:
    """
    Pure and asynchronous real-time evaluation engine.
    Audits settled trade, updates matching Funds and Challenges, checks
    drawdown limits, verifies victory conditions, and updates leaderboards.
    """
    now = datetime.now(timezone.utc)
    result = ProgressEvaluationResult()
    pnl_dec = Decimal(str(trade.profit_loss))

    # =========================================================================
    # 1. EVALUATE USER'S ACTIVE FUNDS
    # =========================================================================
    funds_stmt = (
        select(Fund)
        .where(
            Fund.user_id == trade.user_id,
            Fund.status == FundStatus.ACTIVE,
        )
    )
    funds_res = await db.exec(funds_stmt)
    active_funds = funds_res.all()

    for fund in active_funds:
        if not matches_filters(
            broker=trade.broker,
            sender_id=trade.sender_id,
            template_id=trade.template_id,
            allowed_brokers=fund.allowed_brokers,
            allowed_sender_ids=fund.allowed_sender_ids,
            allowed_template_ids=fund.allowed_template_ids,
        ):
            continue

        prev_progress = fund.current_progress_value

        # Update trades & financial counters
        fund.total_trades += 1
        if trade.outcome == TradeOutcome.WIN or trade.profit_loss > 0:
            fund.winning_trades += 1
            fund.gross_profit += pnl_dec
            fund.current_consecutive_losses = 0
        elif trade.outcome == TradeOutcome.LOSS or trade.profit_loss < 0:
            fund.losing_trades += 1
            fund.gross_loss += abs(pnl_dec)
            fund.current_consecutive_losses += 1
        else:
            fund.current_consecutive_losses = 0

        # Update net capital
        fund.current_amount += pnl_dec

        # High watermark & drawdown calculation
        # Capital based drawdown from peak
        current_amount_float = float(fund.current_amount)
        if current_amount_float > fund.peak_progress_value:
            fund.peak_progress_value = current_amount_float

        drawdown_val = max(0.0, fund.peak_progress_value - current_amount_float)
        fund.current_drawdown = Decimal(str(round(drawdown_val, 4)))

        # Evaluate progress based on GoalType
        win_rate, profit_factor = compute_metrics(
            fund.total_trades, fund.winning_trades, fund.gross_profit, fund.gross_loss
        )

        if fund.goal_type == GoalType.TARGET_CAPITAL:
            fund.current_progress_value = float(fund.current_amount)
            goal_reached = fund.current_progress_value >= fund.goal_target_value
        elif fund.goal_type == GoalType.TRADE_COUNT:
            fund.current_progress_value = float(fund.total_trades)
            goal_reached = fund.total_trades >= fund.goal_target_value
        elif fund.goal_type == GoalType.WIN_RATE_PERCENTAGE:
            fund.current_progress_value = win_rate
            goal_reached = (
                fund.total_trades >= fund.min_sample_trades
                and fund.current_progress_value >= fund.goal_target_value
            )
        elif fund.goal_type == GoalType.PROFIT_FACTOR_RATIO:
            fund.current_progress_value = profit_factor
            goal_reached = (
                fund.total_trades >= fund.min_sample_trades
                and fund.current_progress_value >= fund.goal_target_value
            )
        else:
            goal_reached = False

        # Risk breach checks
        failed = False
        if fund.max_drawdown_limit and fund.current_drawdown > fund.max_drawdown_limit:
            fund.status = FundStatus.FAILED
            result.funds_failed.append(fund.id)
            failed = True
        elif fund.max_consecutive_losses and fund.current_consecutive_losses > fund.max_consecutive_losses:
            fund.status = FundStatus.FAILED
            result.funds_failed.append(fund.id)
            failed = True

        # Victory check
        if not failed and goal_reached:
            fund.status = FundStatus.COMPLETED
            fund.completed_at = now
            result.funds_completed.append(fund.id)

        fund.updated_at = now
        db.add(fund)
        result.funds_updated.append(fund.id)

        # Audit trail
        audit = FundContributionAudit(
            fund_id=fund.id,
            challenge_participant_id=None,
            order_execution_id=trade.order_id,
            broker=trade.broker,
            symbol=trade.symbol,
            broker_ticket=trade.broker_ticket,
            sender_id=trade.sender_id,
            template_id=trade.template_id,
            trade_action=trade.action,
            profit_loss=pnl_dec,
            outcome=trade.outcome,
            previous_progress_value=prev_progress,
            new_progress_value=fund.current_progress_value,
            drawdown_recorded=fund.current_drawdown,
            timestamp=now,
        )
        db.add(audit)
        result.audits_created += 1

    # =========================================================================
    # 2. EVALUATE USER'S ACTIVE CHALLENGE PARTICIPATIONS
    # =========================================================================
    participants_stmt = (
        select(ChallengeParticipant, Challenge)
        .join(Challenge, Challenge.id == ChallengeParticipant.challenge_id)
        .where(
            ChallengeParticipant.user_id == trade.user_id,
            ChallengeParticipant.is_disqualified == False,
            ChallengeParticipant.completed_at == None,
            Challenge.status == ChallengeStatus.RUNNING,
        )
    )
    part_res = await db.exec(participants_stmt)
    records = part_res.all()

    challenges_to_recalculate = set()

    for participant, challenge in records:
        if not matches_filters(
            broker=trade.broker,
            sender_id=trade.sender_id,
            template_id=trade.template_id,
            allowed_brokers=challenge.allowed_brokers,
            allowed_sender_ids=challenge.allowed_sender_ids,
            allowed_template_ids=challenge.allowed_template_ids,
        ):
            continue

        prev_progress = participant.current_progress_value

        # Update stats
        participant.total_trades += 1
        if trade.outcome == TradeOutcome.WIN or trade.profit_loss > 0:
            participant.winning_trades += 1
            participant.gross_profit += pnl_dec
        elif trade.outcome == TradeOutcome.LOSS or trade.profit_loss < 0:
            participant.losing_trades += 1
            participant.gross_loss += abs(pnl_dec)

        # Drawdown calculation
        net_pnl = float(participant.gross_profit - participant.gross_loss)
        if net_pnl > participant.peak_progress_value:
            participant.peak_progress_value = net_pnl

        drawdown_val = max(0.0, participant.peak_progress_value - net_pnl)
        participant.current_drawdown = Decimal(str(round(drawdown_val, 4)))

        # Metric evaluation
        win_rate, profit_factor = compute_metrics(
            participant.total_trades,
            participant.winning_trades,
            participant.gross_profit,
            participant.gross_loss,
        )

        if challenge.goal_type == GoalType.TARGET_CAPITAL:
            participant.current_progress_value = net_pnl
            goal_reached = participant.current_progress_value >= challenge.goal_target_value
        elif challenge.goal_type == GoalType.TRADE_COUNT:
            participant.current_progress_value = float(participant.total_trades)
            goal_reached = participant.total_trades >= challenge.goal_target_value
        elif challenge.goal_type == GoalType.WIN_RATE_PERCENTAGE:
            participant.current_progress_value = win_rate
            goal_reached = (
                participant.total_trades >= challenge.min_sample_trades
                and participant.current_progress_value >= challenge.goal_target_value
            )
        elif challenge.goal_type == GoalType.PROFIT_FACTOR_RATIO:
            participant.current_progress_value = profit_factor
            goal_reached = (
                participant.total_trades >= challenge.min_sample_trades
                and participant.current_progress_value >= challenge.goal_target_value
            )
        else:
            goal_reached = False

        # Risk breach check (Drawdown limit disqualification)
        if challenge.max_drawdown_limit and participant.current_drawdown > challenge.max_drawdown_limit:
            participant.is_disqualified = True
            participant.disqualification_reason = (
                f"Drawdown breach: {participant.current_drawdown} exceeded limit of {challenge.max_drawdown_limit}"
            )
            result.participants_disqualified.append(participant.user_id)
        elif goal_reached:
            participant.completed_at = now
            result.participants_completed.append(participant.user_id)

        db.add(participant)
        challenges_to_recalculate.add(challenge.id)

        # Audit trail
        audit = FundContributionAudit(
            fund_id=None,
            challenge_participant_id=participant.id,
            order_execution_id=trade.order_id,
            broker=trade.broker,
            symbol=trade.symbol,
            broker_ticket=trade.broker_ticket,
            sender_id=trade.sender_id,
            template_id=trade.template_id,
            trade_action=trade.action,
            profit_loss=pnl_dec,
            outcome=trade.outcome,
            previous_progress_value=prev_progress,
            new_progress_value=participant.current_progress_value,
            drawdown_recorded=participant.current_drawdown,
            timestamp=now,
        )
        db.add(audit)
        result.audits_created += 1

    # Recalculate leaderboards and check elastic tournament status
    for c_id in challenges_to_recalculate:
        participants = await recalculate_challenge_leaderboard(c_id, db)
        result.challenges_updated.append(c_id)

        # Check Challenge lifecycle conclusion
        # If all participants are finished (either completed or disqualified)
        c_stmt = select(Challenge).where(Challenge.id == c_id)
        c_res = await db.exec(c_stmt)
        chal = c_res.first()
        if chal and chal.status == ChallengeStatus.RUNNING and participants:
            all_done = all(p.is_disqualified or (p.completed_at is not None) for p in participants)
            # If 1-person challenge, finishes immediately upon completion or disqualification
            if len(participants) == 1:
                single = participants[0]
                if single.completed_at or single.is_disqualified:
                    chal.status = ChallengeStatus.CONCLUDED
                    chal.concluded_at = now
                    db.add(chal)
            elif all_done:
                chal.status = ChallengeStatus.CONCLUDED
                chal.concluded_at = now
                db.add(chal)

    await db.commit()
    return result
