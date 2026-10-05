from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.accounts import router as accounts_router
from app.api.v1.orders import router as orders_router
from app.api.v1.positions import router as positions_router
from app.api.v1.signals import router as signals_router
from app.api.v1.market_data import router as data_router
from app.api.v1.brokers.mt5 import router as mt5_router
from app.api.v1.brokers.binary import router as binary_router
from app.api.v1.endpoints.funds import router as funds_router
from app.api.v1.endpoints.challenges import router as challenges_router

api_v1_router = APIRouter(prefix="/v1")

api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(accounts_router)
api_v1_router.include_router(orders_router)
api_v1_router.include_router(positions_router)
api_v1_router.include_router(signals_router)
api_v1_router.include_router(data_router)
api_v1_router.include_router(mt5_router)
api_v1_router.include_router(binary_router)
api_v1_router.include_router(funds_router)
api_v1_router.include_router(challenges_router)

