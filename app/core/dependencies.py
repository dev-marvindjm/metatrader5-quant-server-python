from typing import AsyncGenerator, Optional
from fastapi import Header, HTTPException, status, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.config import Settings, settings
from app.db.session import get_db
from app.services.brokers.factory import BrokerManager, broker_manager
from app.services.execution_engine import ExecutionEngine, execution_engine


def get_current_settings() -> Settings:
    return settings


def get_broker_service() -> BrokerManager:
    return broker_manager


def get_engine() -> ExecutionEngine:
    return execution_engine


async def verify_api_key_auth(
    x_api_key: Optional[str] = Header(None),
    curr_settings: Settings = Depends(get_current_settings),
) -> None:
    """
    Optional API Key verification. If API_KEY is set in settings,
    incoming requests must match the X-API-Key header.
    """
    if curr_settings.API_KEY:
        if not x_api_key or x_api_key != curr_settings.API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-API-Key header.",
            )
