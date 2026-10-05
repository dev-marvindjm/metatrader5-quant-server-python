from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import text
from app.core.config import settings
from app.core.dependencies import get_db, get_broker_service
from app.domain.schemas.common import ApiResponse
from app.services.brokers.factory import BrokerManager

router = APIRouter(prefix="/health", tags=["System Health"])


@router.get("", response_model=ApiResponse[dict])
async def health_check(
    db: AsyncSession = Depends(get_db),
    broker_srv: BrokerManager = Depends(get_broker_service),
):
    """
    Health check probe verifying DB connection and active broker pool status.
    """
    db_status = "ok"
    try:
        await db.exec(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return ApiResponse(
        success=db_status == "ok",
        data={
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "database": db_status,
            "active_broker_sessions": len(broker_srv._adapters),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
