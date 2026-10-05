from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.core.dependencies import get_db, get_broker_service
from app.core.exceptions import AccountNotFoundError
from app.domain.models.account import TradingAccount
from app.domain.schemas.common import ApiResponse
from app.domain.schemas.position import (
    PositionCloseRequest,
    PositionsCloseAllRequest,
    PositionInfo,
    PositionCloseResponse,
)
from app.services.brokers.factory import BrokerManager
from app.services.brokers.base import IMarketBrokerAdapter

router = APIRouter(prefix="/positions", tags=["Position Management"])


@router.get("", response_model=ApiResponse[List[dict]])
async def get_open_positions(
    account_id: int = Query(..., description="MT5 Account ID"),
    db: AsyncSession = Depends(get_db),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    """
    Retrieves all open trading positions currently held in MetaTrader 5.
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
        raise HTTPException(
            status_code=400,
            detail=f"Broker {account.broker} does not support open market positions.",
        )

    pos_res = await adapter.get_positions()
    if pos_res.is_err():
        raise HTTPException(status_code=502, detail=pos_res.unwrap_err())

    return ApiResponse(data=pos_res.unwrap())


@router.post("/close", response_model=ApiResponse[PositionCloseResponse])
async def close_position_endpoint(
    req: PositionCloseRequest,
    db: AsyncSession = Depends(get_db),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    """
    Closes a specific MT5 position by ticket number.
    """
    stmt = select(TradingAccount).where(TradingAccount.id == req.account_id)
    result = await db.exec(stmt)
    account = result.first()
    if not account:
        raise AccountNotFoundError(req.account_id)

    adapter_res = await broker_srv.get_or_create_adapter(account)
    if adapter_res.is_err():
        raise HTTPException(status_code=400, detail=adapter_res.unwrap_err())

    adapter = adapter_res.unwrap()
    if not isinstance(adapter, IMarketBrokerAdapter):
        raise HTTPException(status_code=400, detail="Broker does not support market positions.")

    close_res = await adapter.close_position(
        ticket=req.ticket,
        symbol=req.symbol,
        volume=req.volume,
        deviation=req.deviation,
        magic=req.magic,
        comment=req.comment,
    )

    if close_res.is_err():
        return ApiResponse(
            success=False,
            error=close_res.unwrap_err(),
            data=PositionCloseResponse(
                ticket=req.ticket,
                symbol=req.symbol,
                closed=False,
                message=close_res.unwrap_err(),
            ),
        )

    res_data = close_res.unwrap()
    return ApiResponse(
        data=PositionCloseResponse(
            ticket=req.ticket,
            symbol=req.symbol,
            closed=True,
            retcode=res_data.get("retcode"),
            order=res_data.get("order"),
            price=res_data.get("price"),
            message="Position closed successfully.",
        )
    )


@router.post("/close-all", response_model=ApiResponse[dict])
async def close_all_positions_endpoint(
    req: PositionsCloseAllRequest,
    db: AsyncSession = Depends(get_db),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    """
    Emergency closure of all open positions in an MT5 account.
    Supports filtering by BUY/SELL or specific magic number.
    """
    stmt = select(TradingAccount).where(TradingAccount.id == req.account_id)
    result = await db.exec(stmt)
    account = result.first()
    if not account:
        raise AccountNotFoundError(req.account_id)

    adapter_res = await broker_srv.get_or_create_adapter(account)
    if adapter_res.is_err():
        raise HTTPException(status_code=400, detail=adapter_res.unwrap_err())

    adapter = adapter_res.unwrap()
    if not isinstance(adapter, IMarketBrokerAdapter):
        raise HTTPException(status_code=400, detail="Broker does not support market positions.")

    close_res = await adapter.close_all_positions(
        order_type=req.order_type,
        magic=req.magic,
    )

    if close_res.is_err():
        raise HTTPException(status_code=500, detail=close_res.unwrap_err())

    results = close_res.unwrap()
    return ApiResponse(data={"closed_count": len(results), "details": results})
