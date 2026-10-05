from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.core.dependencies import get_db, get_broker_service
from app.core.exceptions import AccountNotFoundError
from app.domain.models.account import TradingAccount
from app.domain.schemas.common import ApiResponse
from app.services.brokers.factory import BrokerManager
from app.services.brokers.base import IBinaryBrokerAdapter

router = APIRouter(prefix="/brokers/binary", tags=["Binary Options Special"])


@router.get("/resolve-symbol/{account_id}/{symbol}", response_model=ApiResponse[dict])
async def resolve_binary_symbol(
    account_id: int,
    symbol: str,
    db: AsyncSession = Depends(get_db),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    """
    Checks if a symbol is open and resolves provider-specific formatting
    (e.g., standard vs OTC suffix like -OTC or _otc) for IQ Option, Quotex, or Pocket Option.
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
    clean_base, is_otc, is_perp = adapter.parse_asset_info(symbol)
    target = adapter.format_broker_asset(symbol, account.broker)

    price_res = await adapter.get_current_price(target)

    return ApiResponse(
        data={
            "raw_symbol": symbol,
            "broker": account.broker,
            "resolved_symbol": target,
            "is_otc": is_otc,
            "current_price": price_res.unwrap_or(None),
            "is_tradeable": price_res.is_ok(),
        }
    )


@router.get("/martingale-calculator", response_model=ApiResponse[dict])
async def simulate_martingale_steps(
    initial_amount: float = Query(1.0, gt=0),
    steps: int = Query(2, ge=0, le=6),
    multiplier: float = Query(2.0, ge=1.0, le=5.0),
    payout_percent: float = Query(85.0, ge=50.0, le=100.0),
):
    """
    Calculates required capital, risk, and expected net profit across Martingale step levels.
    """
    schedule = []
    total_invested = 0.0
    current_amount = initial_amount

    for s in range(steps + 1):
        total_invested += current_amount
        win_payout = current_amount * (1.0 + (payout_percent / 100.0))
        net_profit_if_won = win_payout - total_invested

        schedule.append({
            "step": s,
            "trade_amount": round(current_amount, 2),
            "cumulative_invested": round(total_invested, 2),
            "net_profit_if_win": round(net_profit_if_won, 2),
        })
        current_amount = round(current_amount * multiplier, 2)

    return ApiResponse(
        data={
            "initial_amount": initial_amount,
            "steps": steps,
            "multiplier": multiplier,
            "payout_percent": payout_percent,
            "max_risk": round(total_invested, 2),
            "schedule": schedule,
        }
    )
