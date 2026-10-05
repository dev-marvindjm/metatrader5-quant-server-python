import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import SQLModel, select
from app.core.config import settings

logger = logging.getLogger("quant_server.db")

async_engine = create_async_engine(
    settings.async_database_url,
    echo=settings.DEBUG,
    future=True,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an async database session with automatic commit / rollback.
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Creates tables if they don't exist and seeds initial broker catalog.
    Used for local testing or initial dev bootstrapping before running alembic migrations.
    """
    from app.domain.models import BrokerCatalog

    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("Database tables verified/created successfully.")

        # Seed broker catalog if empty
        async with async_session_maker() as session:
            result = await session.exec(select(BrokerCatalog))
            existing = result.first()
            if not existing:
                brokers = [
                    BrokerCatalog(
                        code="mt5",
                        name="MetaTrader 5",
                        market_types="FOREX,CFD,CRYPTO,STOCKS",
                        supports_demo=True,
                        supports_real=True,
                        notes="Traditional market broker via MT5 Terminal or bridge",
                    ),
                    BrokerCatalog(
                        code="iqoption",
                        name="IQ Option",
                        market_types="BINARY_OPTIONS,DIGITAL_OPTIONS",
                        supports_demo=True,
                        supports_real=True,
                        notes="Binary options broker with OTC weekend coverage",
                    ),
                    BrokerCatalog(
                        code="quotex",
                        name="Quotex",
                        market_types="BINARY_OPTIONS",
                        supports_demo=True,
                        supports_real=True,
                        notes="Fast binary options broker with WebSocket & REST API",
                    ),
                    BrokerCatalog(
                        code="pocketoption",
                        name="Pocket Option",
                        market_types="BINARY_OPTIONS",
                        supports_demo=True,
                        supports_real=True,
                        notes="Binary options broker using SSID session tokens",
                    ),
                ]
                session.add_all(brokers)
                await session.commit()
                logger.info("Seeded initial BrokerCatalog entries.")
    except Exception as e:
        logger.warning(f"Database initialization notice: {e}")
