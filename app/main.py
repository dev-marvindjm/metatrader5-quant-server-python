import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.middleware import CorrelationIdAndTimingMiddleware, register_exception_handlers
from app.db.session import init_db, async_engine
from app.services.brokers.factory import broker_manager
from app.api.v1.api_router import api_v1_router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("quant_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan lifecycle manager.
    Bootstraps database on startup and performs clean teardown on exit.
    """
    logger.info("Initializing Quant Trading Server...")
    # Initialize database tables and catalog
    await init_db()
    logger.info("Startup complete. Quant Server is ready to receive orders.")

    yield

    logger.info("Shutting down Quant Trading Server...")
    # Gracefully close all live broker adapter connections
    await broker_manager.close_all()
    # Close database connection pool
    await async_engine.dispose()
    logger.info("All connections closed. Shutdown complete.")


def create_app() -> FastAPI:
    """
    FastAPI Application Factory.
    """
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Modular, asynchronous, decoupled, and secure quant trading server for traditional "
            "financial markets (MetaTrader 5) and binary options (IQ Option, Quotex, Pocket Option). "
            "Features strict typing, safe Result/Either error monad, and async PostgreSQL persistence."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # 1. CORS Middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Correlation ID & Execution Timing Middleware
    application.add_middleware(CorrelationIdAndTimingMiddleware)

    # 3. Global Exception Handling Handlers
    register_exception_handlers(application)

    # 4. Include API Routers
    application.include_router(api_v1_router, prefix="/api")

    # 5. Root status endpoint
    @application.get("/", tags=["Root"])
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "operational",
            "docs": "/docs",
            "api_prefix": "/api/v1",
        }

    return application


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
