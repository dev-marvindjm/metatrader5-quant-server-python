import json
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc

from app.core.dependencies import get_db, get_engine
from app.core.auth import (
    bearer_scheme,
    api_key_header,
    decode_access_token,
    get_current_active_user,
)
from app.domain.models.signal import TradingSignal
from app.domain.models.account import TradingAccount
from app.domain.models.user import User
from app.domain.schemas.common import ApiResponse
from app.domain.schemas.signal import (
    SignalCreate,
    SignalExecuteRequest,
    SignalResponse,
    SignalExecutionSummary,
)
from app.services.execution_engine import ExecutionEngine

router = APIRouter(prefix="/signals", tags=["Quantitative Signals"])


async def _resolve_optional_user(
    auth_header: Optional[HTTPAuthorizationCredentials],
    api_key: Optional[str],
    telegram_id: Optional[int],
    raw_data: Optional[dict],
    db: AsyncSession,
) -> Optional[int]:
    """
    Attempts to attribute an incoming signal to a user via:
    1. Bearer JWT
    2. X-API-Key
    3. Direct telegram_id
    4. Payload telegram_id inside raw_data (for Telegram bot & msg-incoming integration)
    """
    if auth_header and auth_header.credentials:
        payload = decode_access_token(auth_header.credentials)
        if payload and "sub" in payload:
            try:
                return int(payload["sub"])
            except ValueError:
                pass

    if api_key:
        stmt = select(User).where(User.api_key == api_key)
        res = await db.exec(stmt)
        u = res.first()
        if u:
            return u.id

    if telegram_id is not None:
        try:
            stmt = select(User).where(User.telegram_id == int(telegram_id))
            res = await db.exec(stmt)
            u = res.first()
            if u:
                return u.id
        except (ValueError, TypeError):
            pass

    if raw_data and isinstance(raw_data, dict):
        tg_id = raw_data.get("telegram_id") or raw_data.get("sender_id") or raw_data.get("user_id")
        if tg_id:
            try:
                stmt = select(User).where(User.telegram_id == int(tg_id))
                res = await db.exec(stmt)
                u = res.first()
                if u:
                    return u.id
            except (ValueError, TypeError):
                pass

    return None


def _to_signal_response(signal: TradingSignal) -> SignalResponse:
    return SignalResponse(
        id=signal.id,
        user_id=signal.user_id,
        source=signal.source,
        symbol=signal.symbol,
        action=signal.action,
        market_type=signal.market_type,
        timeframe=signal.timeframe,
        duration_seconds=signal.duration_seconds,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        target_broker=signal.target_broker,
        template_id=signal.template_id,
        sender_id=signal.sender_id,
        raw_data=signal.raw_data,
        gale_steps=signal.gale_steps,
        gale_multiplier=signal.gale_multiplier,
        status=signal.status,
        created_at=signal.created_at,
    )


@router.post("", response_model=ApiResponse[SignalResponse], status_code=status.HTTP_201_CREATED)
@router.post("/receive", response_model=ApiResponse[SignalResponse], status_code=status.HTTP_201_CREATED)
async def receive_signal(
    signal_in: SignalCreate,
    auth_header: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingests an incoming quantitative or algorithmic trading signal
    (from webhooks, TradingView alerts, Telegram channels, msg-incoming microservice, etc.).
    Automatically attributes signal ownership if credentials or telegram_id are provided.
    """
    user_id = await _resolve_optional_user(
        auth_header=auth_header,
        api_key=api_key,
        telegram_id=signal_in.telegram_id,
        raw_data=signal_in.raw_data,
        db=db,
    )

    signal = TradingSignal(
        user_id=user_id,
        source=signal_in.source,
        symbol=signal_in.symbol,
        action=signal_in.action.value,
        market_type=signal_in.market_type,
        timeframe=signal_in.timeframe,
        duration_seconds=signal_in.duration_seconds,
        entry_price=signal_in.entry_price,
        stop_loss=signal_in.stop_loss,
        take_profit=signal_in.take_profit,
        target_broker=signal_in.target_broker,
        gale_steps=signal_in.gale_steps,
        gale_multiplier=signal_in.gale_multiplier,
        raw_data=json.dumps(signal_in.raw_data) if signal_in.raw_data else None,
        status="RECEIVED",
    )
    db.add(signal)
    await db.commit()
    await db.refresh(signal)

    return ApiResponse(data=_to_signal_response(signal))


@router.post("/execute", response_model=ApiResponse[SignalExecutionSummary])
async def execute_signal_endpoint(
    req: SignalExecuteRequest,
    db: AsyncSession = Depends(get_db),
    engine: ExecutionEngine = Depends(get_engine),
    current_user: User = Depends(get_current_active_user),
):
    """
    Dispatches and executes a trading signal across multiple registered broker accounts simultaneously.
    Verifies that all target accounts belong to the authenticated user.
    """
    # Verify account ownership for all accounts
    if current_user.role != "admin" and not current_user.is_superuser:
        stmt = select(TradingAccount.id).where(
            TradingAccount.id.in_(req.target_account_ids),
            TradingAccount.user_id == current_user.id,
        )
        res = await db.exec(stmt)
        owned_account_ids = set(res.all())
        unauthorized = set(req.target_account_ids) - owned_account_ids
        if unauthorized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have permission to execute against account IDs: {list(unauthorized)}",
            )

    exec_res = await engine.execute_signal(req, db, user_id=current_user.id)
    if exec_res.is_err():
        raise HTTPException(status_code=400, detail=exec_res.unwrap_err())

    return ApiResponse(data=exec_res.unwrap())


@router.get("", response_model=ApiResponse[List[SignalResponse]])
@router.get("/history", response_model=ApiResponse[List[SignalResponse]])
async def get_signals_history(
    source: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Audits received signals, their parsing parameters and execution states.
    Regular users only see signals attributed to their account or broadcast signals.
    """
    stmt = select(TradingSignal)

    # Multi-tenant isolation: user sees their signals or public broadcast signals (user_id IS NULL)
    if current_user.role != "admin" and not current_user.is_superuser:
        stmt = stmt.where((TradingSignal.user_id == current_user.id) | (TradingSignal.user_id == None))

    if source:
        stmt = stmt.where(TradingSignal.source == source)
    if symbol:
        stmt = stmt.where(TradingSignal.symbol.ilike(f"%{symbol}%"))
    if status_filter:
        stmt = stmt.where(TradingSignal.status == status_filter.upper())

    stmt = stmt.order_by(desc(TradingSignal.created_at)).offset(offset).limit(limit)
    result = await db.exec(stmt)
    signals = result.all()

    return ApiResponse(data=[_to_signal_response(s) for s in signals])
