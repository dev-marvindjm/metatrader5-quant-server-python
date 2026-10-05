from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.core.dependencies import get_db, get_broker_service
from app.core.exceptions import AccountNotFoundError
from app.domain.models.account import TradingAccount
from app.domain.schemas.common import ApiResponse
from app.domain.schemas.market_data import (
    TickResponse,
    CandleData,
    HistoryRatesResponse,
)
from app.services.brokers.factory import BrokerManager
from app.services.brokers.base import IMarketBrokerAdapter

router = APIRouter(prefix="/data", tags=["Market Data & Rates"])


@router.get("/tick/{account_id}/{symbol}", response_model=ApiResponse[TickResponse])
async def get_symbol_tick(
    account_id: int,
    symbol: str,
    db: AsyncSession = Depends(get_db),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    """
    Fetches real-time price tick (bid, ask, spread) for a symbol through the connected broker.
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
    price_res = await adapter.get_current_price(symbol)
    if price_res.is_err():
        raise HTTPException(status_code=404, detail=price_res.unwrap_err())

    price = price_res.unwrap()
    return ApiResponse(
        data=TickResponse(
            symbol=symbol,
            bid=price,
            ask=price,
            last=price,
            spread=0.0,
            time=datetime.now(timezone.utc),
        )
    )


@router.get("/candles/{account_id}/{symbol}", response_model=ApiResponse[HistoryRatesResponse])
async def get_historical_candles(
    account_id: int,
    symbol: str,
    timeframe: str = Query("M1", description="M1, M5, M15, M30, H1, H4, D1"),
    count: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    """
    Retrieves historical OHLCV candlestick rates for technical analysis or backtesting.
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
        raise HTTPException(status_code=400, detail="Historical rates supported on market brokers.")

    rates_res = await adapter.get_rates(symbol, timeframe, count)
    if rates_res.is_err():
        raise HTTPException(status_code=502, detail=rates_res.unwrap_err())

    raw_rates = rates_res.unwrap()
    candles = [
        CandleData(
            time=r.get("time", datetime.now(timezone.utc)),
            open=r.get("open", 0.0),
            high=r.get("high", 0.0),
            low=r.get("low", 0.0),
            close=r.get("close", 0.0),
            volume=r.get("tick_volume", 0.0),
        )
        for r in raw_rates
    ]

    return ApiResponse(
        data=HistoryRatesResponse(
            symbol=symbol,
            timeframe=timeframe,
            count=len(candles),
            rates=candles,
        )
    )
