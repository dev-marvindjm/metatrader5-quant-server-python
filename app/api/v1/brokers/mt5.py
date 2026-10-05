from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.core.dependencies import get_db, get_broker_service
from app.core.exceptions import AccountNotFoundError
from app.domain.models.account import TradingAccount
from app.domain.schemas.common import ApiResponse
from app.services.brokers.factory import BrokerManager
from app.services.brokers.base import IMarketBrokerAdapter

router = APIRouter(prefix="/brokers/mt5", tags=["MetaTrader 5 Special"])


@router.get("/terminal-info/{account_id}", response_model=ApiResponse[dict])
async def get_mt5_terminal_info(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    """
    Returns connection health and terminal info for MT5 instance.
    """
    stmt = select(TradingAccount).where(TradingAccount.id == account_id)
    result = await db.exec(stmt)
    account = result.first()
    if not account:
        raise AccountNotFoundError(account_id)

    adapter_res = await broker_srv.get_or_create_adapter(account)
    if adapter_res.is_err():
        raise HTTPException(status_code=400, detail=adapter_res.unwrap_err())

    adapter = adapter_res.unwrap()
    connected = await adapter.is_connected()
    balance = (await adapter.get_balance()).unwrap_or(0.0)

    return ApiResponse(
        data={
            "account_id": account.id,
            "broker": account.broker,
            "connected": connected,
            "server": account.server,
            "balance": balance,
            "account_mode": account.account_mode,
        }
    )


@router.get("/history-deals/{account_id}", response_model=ApiResponse[List[dict]])
async def get_mt5_deals_history(
    account_id: int,
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    """
    Fetches raw MT5 history deals for the past N days directly from the terminal.
    """
    stmt = select(TradingAccount).where(TradingAccount.id == account_id)
    result = await db.exec(stmt)
    account = result.first()
    if not account:
        raise AccountNotFoundError(account_id)

    adapter_res = await broker_srv.get_or_create_adapter(account)
    if adapter_res.is_err():
        raise HTTPException(status_code=400, detail=adapter_res.unwrap_err())

    adapter = adapter_res.unwrap()
    if not isinstance(adapter, IMarketBrokerAdapter):
        raise HTTPException(status_code=400, detail="Not an MT5 / market account.")

    date_to = datetime.now(timezone.utc)
    date_from = date_to - timedelta(days=days)

    deals_res = await adapter.get_history_deals(date_from=date_from, date_to=date_to)
    if deals_res.is_err():
        raise HTTPException(status_code=502, detail=deals_res.unwrap_err())

    return ApiResponse(data=deals_res.unwrap())
