from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc

from app.core.dependencies import get_db
from app.core.auth import get_current_active_user
from app.domain.enums import GoalType, ChallengeStatus, RankingMetric, TradeOutcome
from app.domain.models.challenge import Challenge, ChallengeParticipant
from app.domain.models.user import User
from app.domain.schemas.common import ApiResponse
from app.domain.schemas.challenge_schema import (
    ChallengeCreate,
    ChallengeResponse,
    LeaderboardParticipantItem,
    ChallengeLeaderboardResponse,
    WinnerHistoryItem,
)
from app.services.progress_evaluator import (
    evaluate_trade_progress,
    TradeSettledPayload,
    ProgressEvaluationResult,
    compute_metrics,
    recalculate_challenge_leaderboard,
)

router = APIRouter(prefix="/challenges", tags=["Challenges & Leaderboards"])


async def _to_challenge_response(challenge: Challenge, db: AsyncSession) -> ChallengeResponse:
    # Count participants
    count_stmt = select(ChallengeParticipant).where(ChallengeParticipant.challenge_id == challenge.id)
    c_res = await db.exec(count_stmt)
    parts = c_res.all()

    return ChallengeResponse(
        id=challenge.id,
        creator_user_id=challenge.creator_user_id,
        title=challenge.title,
        description=challenge.description,
        goal_type=challenge.goal_type,
        goal_target_value=challenge.goal_target_value,
        min_sample_trades=challenge.min_sample_trades,
        start_time=challenge.start_time,
        end_time=challenge.end_time,
        entry_fee=challenge.entry_fee,
        max_drawdown_limit=challenge.max_drawdown_limit,
        allowed_brokers=challenge.allowed_brokers,
        allowed_sender_ids=challenge.allowed_sender_ids,
        allowed_template_ids=challenge.allowed_template_ids,
        is_public=challenge.is_public,
        ranking_metric=challenge.ranking_metric,
        status=challenge.status,
        created_at=challenge.created_at,
        concluded_at=challenge.concluded_at,
        participants_count=len(parts),
    )


@router.post("", response_model=ApiResponse[ChallengeResponse], status_code=status.HTTP_201_CREATED)
async def create_challenge(
    ch_in: ChallengeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Creates a new competitive Challenge.
    Can be run as a single-player time trial or multi-player tournament.
    """
    now = datetime.now(timezone.utc)
    challenge = Challenge(
        creator_user_id=current_user.id,
        title=ch_in.title,
        description=ch_in.description,
        goal_type=ch_in.goal_type,
        goal_target_value=ch_in.goal_target_value,
        min_sample_trades=ch_in.min_sample_trades,
        start_time=ch_in.start_time or now,
        end_time=ch_in.end_time,
        entry_fee=ch_in.entry_fee,
        max_drawdown_limit=ch_in.max_drawdown_limit,
        allowed_brokers=ch_in.allowed_brokers,
        allowed_sender_ids=ch_in.allowed_sender_ids,
        allowed_template_ids=ch_in.allowed_template_ids,
        is_public=ch_in.is_public,
        ranking_metric=ch_in.ranking_metric,
        status=ChallengeStatus.RUNNING,
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)

    resp = await _to_challenge_response(challenge, db)
    return ApiResponse(data=resp)


@router.get("", response_model=ApiResponse[List[ChallengeResponse]])
async def list_challenges(
    status_filter: Optional[ChallengeStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lists available challenges (public challenges or created by the current user).
    """
    stmt = select(Challenge)
    if current_user.role != "admin" and not current_user.is_superuser:
        stmt = stmt.where((Challenge.is_public == True) | (Challenge.creator_user_id == current_user.id))

    if status_filter:
        stmt = stmt.where(Challenge.status == status_filter)

    stmt = stmt.order_by(desc(Challenge.created_at)).offset(offset).limit(limit)
    res = await db.exec(stmt)
    challenges = res.all()

    items = []
    for c in challenges:
        items.append(await _to_challenge_response(c, db))

    return ApiResponse(data=items)


@router.get("/{challenge_id}", response_model=ApiResponse[ChallengeResponse])
async def get_challenge_detail(
    challenge_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Retrieves details for a specific challenge.
    """
    stmt = select(Challenge).where(Challenge.id == challenge_id)
    res = await db.exec(stmt)
    challenge = res.first()
    if not challenge:
        raise HTTPException(status_code=404, detail=f"Challenge #{challenge_id} not found.")

    resp = await _to_challenge_response(challenge, db)
    return ApiResponse(data=resp)


@router.post("/{challenge_id}/join", response_model=ApiResponse[LeaderboardParticipantItem])
async def join_challenge(
    challenge_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Enrolls the authenticated user into the Challenge.
    Supports single-player (personal time-trial) or multi-player tournament competition.
    """
    stmt = select(Challenge).where(Challenge.id == challenge_id)
    res = await db.exec(stmt)
    challenge = res.first()
    if not challenge:
        raise HTTPException(status_code=404, detail=f"Challenge #{challenge_id} not found.")

    if challenge.status not in (ChallengeStatus.RUNNING, ChallengeStatus.REGISTRATION):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot join challenge in status '{challenge.status}'.",
        )

    # Check if already joined
    p_stmt = select(ChallengeParticipant).where(
        ChallengeParticipant.challenge_id == challenge_id,
        ChallengeParticipant.user_id == current_user.id,
    )
    p_res = await db.exec(p_stmt)
    existing = p_res.first()
    if existing:
        # Already enrolled, return current state
        win_rate, pf = compute_metrics(
            existing.total_trades, existing.winning_trades, existing.gross_profit, existing.gross_loss
        )
        pct = round(min(100.0, max(0.0, (existing.current_progress_value / challenge.goal_target_value) * 100.0)), 2) if challenge.goal_target_value > 0 else 0.0
        return ApiResponse(
            data=LeaderboardParticipantItem(
                rank_position=existing.rank_position,
                user_id=existing.user_id,
                username=current_user.username or current_user.email,
                current_progress_value=round(existing.current_progress_value, 4),
                progress_percentage=pct,
                total_trades=existing.total_trades,
                winning_trades=existing.winning_trades,
                losing_trades=existing.losing_trades,
                win_rate_percentage=round(win_rate, 2),
                profit_factor=round(pf, 2),
                gross_profit=existing.gross_profit,
                gross_loss=existing.gross_loss,
                current_drawdown=existing.current_drawdown,
                is_disqualified=existing.is_disqualified,
                disqualification_reason=existing.disqualification_reason,
                completed_at=existing.completed_at,
                joined_at=existing.joined_at,
            )
        )

    # Create participant
    participant = ChallengeParticipant(
        challenge_id=challenge_id,
        user_id=current_user.id,
        current_progress_value=0.0,
        peak_progress_value=0.0,
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
    )
    db.add(participant)
    await db.commit()
    await db.refresh(participant)

    # Recalculate ranks
    await recalculate_challenge_leaderboard(challenge_id, db)
    await db.commit()
    await db.refresh(participant)

    return ApiResponse(
        data=LeaderboardParticipantItem(
            rank_position=participant.rank_position,
            user_id=participant.user_id,
            username=current_user.username or current_user.email,
            current_progress_value=0.0,
            progress_percentage=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate_percentage=0.0,
            profit_factor=0.0,
            gross_profit=participant.gross_profit,
            gross_loss=participant.gross_loss,
            current_drawdown=participant.current_drawdown,
            is_disqualified=False,
            disqualification_reason=None,
            completed_at=None,
            joined_at=participant.joined_at,
        )
    )


@router.get("/{challenge_id}/leaderboard", response_model=ApiResponse[ChallengeLeaderboardResponse])
async def get_challenge_leaderboard(
    challenge_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Returns real-time dynamic leaderboard for a challenge, ordered by official rank position.
    Shows confirmed winners (podium) and active contenders.
    """
    stmt = select(Challenge).where(Challenge.id == challenge_id)
    res = await db.exec(stmt)
    challenge = res.first()
    if not challenge:
        raise HTTPException(status_code=404, detail=f"Challenge #{challenge_id} not found.")

    # Always ensure leaderboard ranks are up-to-date
    participants = await recalculate_challenge_leaderboard(challenge_id, db)
    await db.commit()

    # Load usernames
    user_ids = [p.user_id for p in participants]
    users_stmt = select(User).where(User.id.in_(user_ids)) if user_ids else None
    user_map = {}
    if users_stmt is not None:
        u_res = await db.exec(users_stmt)
        for u in u_res.all():
            user_map[u.id] = u.username or u.email

    leaderboard_items = []
    active_count = 0
    disqualified_count = 0
    completed_count = 0

    for p in participants:
        if p.is_disqualified:
            disqualified_count += 1
        elif p.completed_at is not None:
            completed_count += 1
        else:
            active_count += 1

        win_rate, pf = compute_metrics(p.total_trades, p.winning_trades, p.gross_profit, p.gross_loss)
        pct = round(min(100.0, max(0.0, (p.current_progress_value / challenge.goal_target_value) * 100.0)), 2) if challenge.goal_target_value > 0 else 0.0

        leaderboard_items.append(
            LeaderboardParticipantItem(
                rank_position=p.rank_position,
                user_id=p.user_id,
                username=user_map.get(p.user_id, f"Trader #{p.user_id}"),
                current_progress_value=round(p.current_progress_value, 4),
                progress_percentage=pct,
                total_trades=p.total_trades,
                winning_trades=p.winning_trades,
                losing_trades=p.losing_trades,
                win_rate_percentage=round(win_rate, 2),
                profit_factor=round(pf, 2),
                gross_profit=p.gross_profit,
                gross_loss=p.gross_loss,
                current_drawdown=p.current_drawdown,
                is_disqualified=p.is_disqualified,
                disqualification_reason=p.disqualification_reason,
                completed_at=p.completed_at,
                joined_at=p.joined_at,
            )
        )

    return ApiResponse(
        data=ChallengeLeaderboardResponse(
            challenge_id=challenge.id,
            challenge_title=challenge.title,
            status=challenge.status,
            goal_type=challenge.goal_type,
            goal_target_value=challenge.goal_target_value,
            total_participants=len(participants),
            active_participants=active_count,
            disqualified_participants=disqualified_count,
            completed_participants=completed_count,
            leaderboard=leaderboard_items,
        )
    )


@router.get("/history/winners", response_model=ApiResponse[List[WinnerHistoryItem]])
async def get_winners_history(
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Wall of Fame / History of concluded challenges and their champions.
    """
    stmt = (
        select(Challenge)
        .where(Challenge.status == ChallengeStatus.CONCLUDED)
        .order_by(desc(Challenge.concluded_at))
        .limit(limit)
    )
    res = await db.exec(stmt)
    concluded_challenges = res.all()

    winners = []
    for c in concluded_challenges:
        # Find winner (rank 1)
        p_stmt = (
            select(ChallengeParticipant)
            .where(
                ChallengeParticipant.challenge_id == c.id,
                ChallengeParticipant.rank_position == 1,
            )
        )
        p_res = await db.exec(p_stmt)
        champion = p_res.first()

        # Count total
        count_stmt = select(ChallengeParticipant).where(ChallengeParticipant.challenge_id == c.id)
        all_p = (await db.exec(count_stmt)).all()

        winner_name = None
        if champion:
            u_stmt = select(User).where(User.id == champion.user_id)
            u_obj = (await db.exec(u_stmt)).first()
            if u_obj:
                winner_name = u_obj.username or u_obj.email

        winners.append(
            WinnerHistoryItem(
                challenge_id=c.id,
                title=c.title,
                goal_type=c.goal_type,
                concluded_at=c.concluded_at,
                winner_user_id=champion.user_id if champion else None,
                winner_username=winner_name,
                winning_progress_value=champion.current_progress_value if champion else None,
                total_participants=len(all_p),
            )
        )

    return ApiResponse(data=winners)


@router.post("/evaluate-trade", response_model=ApiResponse[ProgressEvaluationResult])
async def evaluate_trade_endpoint(
    trade_in: TradeSettledPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Webhook or tester endpoint to manually or externally report a trade settlement
    and evaluate all active Funds and Challenges in real time.
    """
    if current_user.role != "admin" and not current_user.is_superuser:
        if trade_in.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Forbidden: Cannot report trades for other users.")

    res = await evaluate_trade_progress(trade_in, db)
    return ApiResponse(data=res)
