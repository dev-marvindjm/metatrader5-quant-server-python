from app.api.v1.api_router import api_v1_router as router
from app.api.v1.endpoints.funds import router as funds_router
from app.api.v1.endpoints.challenges import router as challenges_router

__all__ = ["router", "funds_router", "challenges_router"]
