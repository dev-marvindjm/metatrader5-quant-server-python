from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc

from app.core.dependencies import get_db
from app.core.auth import get_current_active_user
from app.domain.enums import GoalType, FundStatus, TradeOutcome
from app.domain.models.fund import Fund, FundContributionAudit
from app.domain.models.user import User
from app.domain.schemas.common import ApiResponse
from app.domain.schemas.fund_schema import (
    FundCreate,
    FundResponse,
    FundMetricsResponse,
    FundContributionAuditItem,
)
from app.services.progress_evaluator import compute_metrics

router = APIRouter(prefix="/funds", tags=["Accumulation Funds & Goals"])


def _to_fund_response(fund: Fund) -> FundResponse:
    win_rate, pf = compute_metrics(
        fund.total_trades,
        fund.winning_trades,
        fund.gross_profit,
        fund.gross_loss,
    )
    if fund.goal_target_value > 0:
        progress_pct = round(min(100.0, max(0.0, (fund.current_progress_value / fund.goal_target_value) * 100.0)), 2)
    else:
        progress_pct = 0.0

    return FundResponse(
        id=fund.id,
        user_id=fund.user_id,
        title=fund.title,
        description=fund.description,
        target_amount=fund.target_amount,
        current_amount=fund.current_amount,
        goal_type=fund.goal_type,
        goal_target_value=fund.goal_target_value,
        current_progress_value=round(fund.current_progress_value, 4),
        progress_percentage=progress_pct,
        total_trades=fund.total_trades,
        winning_trades=fund.winning_trades,
        losing_trades=fund.losing_trades,
        win_rate_percentage=round(win_rate, 2),
        profit_factor=round(pf, 2),
        current_drawdown=fund.current_drawdown,
        max_drawdown_limit=fund.max_drawdown_limit,
        allowed_brokers=fund.allowed_brokers,
        allowed_sender_ids=fund.allowed_sender_ids,
        allowed_template_ids=fund.allowed_template_ids,
        status=fund.status,
        created_at=fund.created_at,
        updated_at=fund.updated_at,
        completed_at=fund.completed_at,
    )


@router.post("", response_model=ApiResponse[FundResponse], status_code=status.HTTP_201_CREATED)
async def create_fund(
    fund_in: FundCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Creates a new operational quantitative Fund / accumulation goal.
    Supports filters by allowed_brokers, allowed_sender_ids, and allowed_template_ids.
    """
    fund = Fund(
        user_id=current_user.id,
        title=fund_in.title,
        description=fund_in.description,
        target_amount=fund_in.target_amount,
        goal_type=fund_in.goal_type,
        goal_target_value=fund_in.goal_target_value,
        max_drawdown_limit=fund_in.max_drawdown_limit,
        max_consecutive_losses=fund_in.max_consecutive_losses,
        min_sample_trades=fund_in.min_sample_trades,
        allowed_brokers=fund_in.allowed_brokers,
        allowed_sender_ids=fund_in.allowed_sender_ids,
        allowed_template_ids=fund_in.allowed_template_ids,
        status=FundStatus.ACTIVE,
    )
    db.add(fund)
    await db.commit()
    await db.refresh(fund)

    return ApiResponse(data=_to_fund_response(fund))


@router.get("", response_model=ApiResponse[List[FundResponse]])
async def list_funds(
    status_filter: Optional[FundStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lists accumulation funds for the authenticated user with computed progress percentage and metrics.
    """
    stmt = select(Fund)
    if current_user.role != "admin" and not current_user.is_superuser:
        stmt = stmt.where(Fund.user_id == current_user.id)

    if status_filter:
        stmt = stmt.where(Fund.status == status_filter)

    stmt = stmt.order_by(desc(Fund.created_at)).offset(offset).limit(limit)
    res = await db.exec(stmt)
    funds = res.all()

    return ApiResponse(data=[_to_fund_response(f) for f in funds])


@router.get("/{fund_id}", response_model=ApiResponse[FundResponse])
async def get_fund_detail(
    fund_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Retrieves full details of a specific fund.
    """
    stmt = select(Fund).where(Fund.id == fund_id)
    res = await db.exec(stmt)
    fund = res.first()
    if not fund:
        raise HTTPException(status_code=404, detail=f"Fund #{fund_id} not found.")

    if fund.user_id != current_user.id and current_user.role != "admin" and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this fund.")

    return ApiResponse(data=_to_fund_response(fund))


@router.get("/{fund_id}/metrics", response_model=ApiResponse[FundMetricsResponse])
async def get_fund_metrics(
    fund_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Provides a mathematical breakdown and complete contribution audit trail of all trades
    that contributed to the fund's capital and progress.
    """
    stmt = select(Fund).where(Fund.id == fund_id)
    res = await db.exec(stmt)
    fund = res.first()
    if not fund:
        raise HTTPException(status_code=404, detail=f"Fund #{fund_id} not found.")

    if fund.user_id != current_user.id and current_user.role != "admin" and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this fund.")

    audit_stmt = (
        select(FundContributionAudit)
        .where(FundContributionAudit.fund_id == fund_id)
        .order_by(desc(FundContributionAudit.timestamp))
        .limit(limit)
    )
    audit_res = await db.exec(audit_stmt)
    audits = audit_res.all()

    audit_items = [
        FundContributionAuditItem(
            id=a.id,
            fund_id=a.fund_id,
            challenge_participant_id=a.challenge_participant_id,
            order_execution_id=a.order_execution_id,
            broker=a.broker,
            symbol=a.symbol,
            broker_ticket=a.broker_ticket,
            sender_id=a.sender_id,
            template_id=a.template_id,
            profit_loss=a.profit_loss,
            outcome=a.outcome,
            previous_progress_value=a.previous_progress_value,
            new_progress_value=a.new_progress_value,
            drawdown_recorded=a.drawdown_recorded,
            timestamp=a.timestamp,
        )
        for a in audits
    ]

    return ApiResponse(
        data=FundMetricsResponse(
            fund=_to_fund_response(fund),
            audits=audit_items,
            total_audited_trades=len(audit_items),
        )
    )


@router.post("/{fund_id}/pause", response_model=ApiResponse[FundResponse])
async def pause_fund(
    fund_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Pauses an active fund, temporarily preventing trades from contributing to it.
    """
    stmt = select(Fund).where(Fund.id == fund_id)
    res = await db.exec(stmt)
    fund = res.first()
    if not fund:
        raise HTTPException(status_code=404, detail=f"Fund #{fund_id} not found.")

    if fund.user_id != current_user.id and current_user.role != "admin" and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Forbidden.")

    if fund.status != FundStatus.ACTIVE:
        raise HTTPException(status_code=400, detail=f"Only ACTIVE funds can be paused. Current: {fund.status}")

    fund.status = FundStatus.PAUSED
    db.add(fund)
    await db.commit()
    await db.refresh(fund)
    return ApiResponse(data=_to_fund_response(fund))


@router.post("/{fund_id}/resume", response_model=ApiResponse[FundResponse])
async def resume_fund(
    fund_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Resumes a paused fund.
    """
    stmt = select(Fund).where(Fund.id == fund_id)
    res = await db.exec(stmt)
    fund = res.first()
    if not fund:
        raise HTTPException(status_code=404, detail=f"Fund #{fund_id} not found.")

    if fund.user_id != current_user.id and current_user.role != "admin" and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Forbidden.")

    if fund.status != FundStatus.PAUSED:
        raise HTTPException(status_code=400, detail=f"Only PAUSED funds can be resumed. Current: {fund.status}")

    fund.status = FundStatus.ACTIVE
    db.add(fund)
    await db.commit()
    await db.refresh(fund)
    return ApiResponse(data=_to_fund_response(fund))
