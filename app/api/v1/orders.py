from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc

from app.core.dependencies import get_db, get_engine
from app.core.auth import get_current_active_user
from app.domain.models.order import OrderExecution
from app.domain.models.account import TradingAccount
from app.domain.models.user import User
from app.domain.schemas.common import ApiResponse
from app.domain.schemas.order import (
    BinaryOrderCreate,
    MarketOrderCreate,
    PendingOrderCreate,
    OrderExecutionResponse,
    OrderHistoryFilter,
)
from app.services.execution_engine import ExecutionEngine

router = APIRouter(prefix="/orders", tags=["Order Execution"])


async def _verify_account_ownership(account_id: int, user: User, db: AsyncSession) -> TradingAccount:
    stmt = select(TradingAccount).where(TradingAccount.id == account_id)
    res = await db.exec(stmt)
    account = res.first()
    if not account:
        raise HTTPException(status_code=404, detail=f"Trading account {account_id} not found.")
    
    if account.user_id != user.id and user.role != "admin" and not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not own trading account {account_id}.",
        )
    return account


def _to_order_response(order: OrderExecution) -> OrderExecutionResponse:
    return OrderExecutionResponse(
        id=order.id,
        user_id=order.user_id,
        account_id=order.account_id,
        signal_id=order.signal_id,
        broker=order.broker,
        broker_order_id=order.broker_order_id,
        symbol=order.symbol,
        raw_symbol=order.raw_symbol,
        action=order.action,
        order_type=order.order_type,
        amount=order.amount,
        executed_amount=order.executed_amount,
        entry_price=order.entry_price,
        close_price=order.close_price,
        stop_loss=order.stop_loss,
        take_profit=order.take_profit,
        duration_seconds=order.duration_seconds,
        profit_loss=order.profit_loss,
        drawdown=order.drawdown,
        spread=order.spread,
        slippage=order.slippage,
        latency_ms=order.latency_ms,
        gale_step=order.gale_step,
        status=order.status,
        error_log=order.error_log,
        created_at=order.created_at,
        closed_at=order.closed_at,
    )


@router.post("/binary", response_model=ApiResponse[OrderExecutionResponse], status_code=status.HTTP_201_CREATED)
async def execute_binary_order(
    order_in: BinaryOrderCreate,
    db: AsyncSession = Depends(get_db),
    engine: ExecutionEngine = Depends(get_engine),
    current_user: User = Depends(get_current_active_user),
):
    """
    Executes a Binary Options order (IQ Option, Quotex, Pocket Option) with optional Martingale.
    Verifies that the target trading account belongs to the authenticated user.
    """
    await _verify_account_ownership(order_in.account_id, current_user, db)

    exec_res = await engine.execute_binary_order(order_in, db)
    if exec_res.is_err():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exec_res.unwrap_err(),
        )

    order = exec_res.unwrap()
    return ApiResponse(data=_to_order_response(order))


@router.post("/market", response_model=ApiResponse[OrderExecutionResponse], status_code=status.HTTP_201_CREATED)
async def execute_market_order(
    order_in: MarketOrderCreate,
    db: AsyncSession = Depends(get_db),
    engine: ExecutionEngine = Depends(get_engine),
    current_user: User = Depends(get_current_active_user),
):
    """
    Executes a Market Order in MetaTrader 5 (BUY/SELL) with SL/TP, deviation, and magic number.
    Verifies that the target trading account belongs to the authenticated user.
    """
    await _verify_account_ownership(order_in.account_id, current_user, db)

    exec_res = await engine.execute_market_order(order_in, db)
    if exec_res.is_err():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exec_res.unwrap_err(),
        )

    order = exec_res.unwrap()
    return ApiResponse(data=_to_order_response(order))


@router.get("/history", response_model=ApiResponse[List[OrderExecutionResponse]])
async def get_order_history(
    account_id: Optional[int] = Query(None),
    broker: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    order_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Retrieves full audit log of order executions with multi-parameter filtering and tenant isolation.
    """
    stmt = select(OrderExecution)

    # Multi-tenant isolation: regular users only see their own orders
    if current_user.role != "admin" and not current_user.is_superuser:
        stmt = stmt.where(OrderExecution.user_id == current_user.id)

    if account_id:
        # If user filters by account_id, ensure they own it
        if current_user.role != "admin" and not current_user.is_superuser:
            await _verify_account_ownership(account_id, current_user, db)
        stmt = stmt.where(OrderExecution.account_id == account_id)

    if broker:
        stmt = stmt.where(OrderExecution.broker == broker.lower())
    if symbol:
        stmt = stmt.where(OrderExecution.symbol.ilike(f"%{symbol}%"))
    if order_status:
        stmt = stmt.where(OrderExecution.status == order_status.upper())

    stmt = stmt.order_by(desc(OrderExecution.created_at)).offset(offset).limit(limit)
    result = await db.exec(stmt)
    orders = result.all()

    return ApiResponse(data=[_to_order_response(o) for o in orders])


@router.get("/{order_id}", response_model=ApiResponse[OrderExecutionResponse])
async def get_order_by_id(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(OrderExecution).where(OrderExecution.id == order_id)
    result = await db.exec(stmt)
    order = result.first()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found.")

    if order.user_id != current_user.id and current_user.role != "admin" and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this order.",
        )

    return ApiResponse(data=_to_order_response(order))
