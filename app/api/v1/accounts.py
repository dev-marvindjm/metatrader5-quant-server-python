from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.core.dependencies import get_db, get_broker_service
from app.core.security import cipher
from app.core.auth import get_current_active_user
from app.core.exceptions import AccountNotFoundError
from app.domain.models.account import TradingAccount
from app.domain.models.broker import BrokerCatalog
from app.domain.models.user import User
from app.domain.schemas.common import ApiResponse
from app.domain.schemas.account import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountConnectResponse,
    AccountBalanceResponse,
)
from app.services.brokers.factory import BrokerManager

router = APIRouter(prefix="/accounts", tags=["Trading Accounts"])


def _check_account_owner(account: TradingAccount, user: User) -> None:
    """Enforces multi-tenant data isolation per user unless administrator."""
    if account.user_id != user.id and user.role != "admin" and not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this trading account.",
        )


def _to_account_response(account: TradingAccount) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        user_id=account.user_id,
        broker=account.broker,
        account_name=account.account_name,
        account_number=account.account_number,
        account_mode=account.account_mode,
        is_active=account.is_active,
        balance=account.balance,
        equity=account.equity,
        currency=account.currency,
        server=account.server,
        last_connected_at=account.last_connected_at,
        last_error=account.last_error,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.get("/catalog", response_model=ApiResponse[List[BrokerCatalog]])
async def get_broker_catalog(
    db: AsyncSession = Depends(get_db),
):
    """
    Lists all supported brokers in the system with their capabilities and market types.
    Publicly available to all authenticated and potential clients.
    """
    stmt = select(BrokerCatalog).where(BrokerCatalog.is_active == True)
    result = await db.exec(stmt)
    return ApiResponse(data=result.all())


@router.post("", response_model=ApiResponse[AccountResponse], status_code=status.HTTP_201_CREATED)
async def create_account(
    account_in: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Registers a new trading broker account for the currently authenticated user.
    Credentials are encrypted at rest using AES-Fernet cryptography.
    """
    encrypted_creds = cipher.encrypt(account_in.credentials)

    acc_num = str(
        account_in.credentials.get("login")
        or account_in.credentials.get("email")
        or account_in.credentials.get("account_id")
        or ""
    )

    account = TradingAccount(
        user_id=current_user.id,
        broker=account_in.broker.value,
        account_name=account_in.account_name,
        account_number=acc_num or None,
        account_mode=account_in.account_mode.value,
        encrypted_credentials=encrypted_creds,
        server=account_in.server or account_in.credentials.get("server"),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    return ApiResponse(data=_to_account_response(account))


@router.get("", response_model=ApiResponse[List[AccountResponse]])
async def list_accounts(
    is_active: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lists registered trading accounts owned by the authenticated user (or all if admin).
    """
    stmt = select(TradingAccount).where(TradingAccount.is_active == is_active)
    if current_user.role != "admin" and not current_user.is_superuser:
        stmt = stmt.where(TradingAccount.user_id == current_user.id)

    result = await db.exec(stmt)
    accounts = result.all()

    return ApiResponse(data=[_to_account_response(a) for a in accounts])


@router.get("/{account_id}", response_model=ApiResponse[AccountResponse])
async def get_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(TradingAccount).where(TradingAccount.id == account_id)
    result = await db.exec(stmt)
    account = result.first()
    if not account:
        raise AccountNotFoundError(account_id)

    _check_account_owner(account, current_user)
    return ApiResponse(data=_to_account_response(account))


@router.put("/{account_id}", response_model=ApiResponse[AccountResponse])
async def update_account(
    account_id: int,
    account_update: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(TradingAccount).where(TradingAccount.id == account_id)
    result = await db.exec(stmt)
    account = result.first()
    if not account:
        raise AccountNotFoundError(account_id)

    _check_account_owner(account, current_user)

    if account_update.account_name is not None:
        account.account_name = account_update.account_name
    if account_update.account_mode is not None:
        account.account_mode = account_update.account_mode.value
    if account_update.is_active is not None:
        account.is_active = account_update.is_active
    if account_update.server is not None:
        account.server = account_update.server
    if account_update.credentials is not None:
        account.encrypted_credentials = cipher.encrypt(account_update.credentials)

    account.updated_at = datetime.now(timezone.utc)
    db.add(account)
    await db.commit()
    await db.refresh(account)

    return ApiResponse(data=_to_account_response(account))


@router.delete("/{account_id}", response_model=ApiResponse[dict])
async def delete_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    stmt = select(TradingAccount).where(TradingAccount.id == account_id)
    result = await db.exec(stmt)
    account = result.first()
    if not account:
        raise AccountNotFoundError(account_id)

    _check_account_owner(account, current_user)

    await broker_srv.disconnect_account(account_id)
    await db.delete(account)
    await db.commit()
    return ApiResponse(data={"message": f"Account {account_id} deleted successfully."})


@router.post("/{account_id}/toggle", response_model=ApiResponse[AccountResponse])
async def toggle_account_endpoint(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Toggles the is_active state of a trading account.
    """
    stmt = select(TradingAccount).where(TradingAccount.id == account_id)
    result = await db.exec(stmt)
    account = result.first()
    if not account:
        raise AccountNotFoundError(account_id)

    _check_account_owner(account, current_user)

    account.is_active = not account.is_active
    account.updated_at = datetime.now(timezone.utc)
    db.add(account)
    await db.commit()
    await db.refresh(account)

    return ApiResponse(data=_to_account_response(account))


@router.post("/{account_id}/connect", response_model=ApiResponse[AccountConnectResponse])
async def connect_account_endpoint(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    """
    Initiates live connection to the broker for this account and verifies credentials.
    """
    stmt = select(TradingAccount).where(TradingAccount.id == account_id)
    result = await db.exec(stmt)
    account = result.first()
    if not account:
        raise AccountNotFoundError(account_id)

    _check_account_owner(account, current_user)

    conn_res = await broker_srv.connect_account(account)
    if conn_res.is_err():
        account.last_error = conn_res.unwrap_err()
        db.add(account)
        await db.commit()
        return ApiResponse(
            success=False,
            error=conn_res.unwrap_err(),
            data=AccountConnectResponse(
                account_id=account.id,
                broker=account.broker,
                connected=False,
                balance=account.balance,
                account_mode=account.account_mode,
                message=conn_res.unwrap_err(),
            ),
        )

    data = conn_res.unwrap()
    account.balance = data["balance"]
    account.last_connected_at = datetime.now(timezone.utc)
    account.last_error = None
    db.add(account)
    await db.commit()

    return ApiResponse(
        data=AccountConnectResponse(
            account_id=account.id,
            broker=account.broker,
            connected=True,
            balance=data["balance"],
            account_mode=account.account_mode,
            message="Broker connection established successfully.",
        )
    )


@router.post("/{account_id}/disconnect", response_model=ApiResponse[dict])
async def disconnect_account_endpoint(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    stmt = select(TradingAccount).where(TradingAccount.id == account_id)
    result = await db.exec(stmt)
    account = result.first()
    if not account:
        raise AccountNotFoundError(account_id)

    _check_account_owner(account, current_user)

    disc_res = await broker_srv.disconnect_account(account_id)
    return ApiResponse(data={"disconnected": disc_res.unwrap_or(True)})


@router.get("/{account_id}/balance", response_model=ApiResponse[AccountBalanceResponse])
async def get_account_balance(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    stmt = select(TradingAccount).where(TradingAccount.id == account_id)
    result = await db.exec(stmt)
    account = result.first()
    if not account:
        raise AccountNotFoundError(account_id)

    _check_account_owner(account, current_user)

    bal_res = await broker_srv.get_balance(account)
    balance = bal_res.unwrap_or(account.balance)

    account.balance = balance
    account.last_connected_at = datetime.now(timezone.utc)
    db.add(account)
    await db.commit()

    return ApiResponse(
        data=AccountBalanceResponse(
            account_id=account.id,
            broker=account.broker,
            account_name=account.account_name,
            balance=balance,
            equity=account.equity,
            currency=account.currency,
            account_mode=account.account_mode,
            last_updated=account.last_connected_at,
        )
    )
