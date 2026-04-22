"""
Async Database Session — PostgreSQL via SQLAlchemy + asyncpg
=============================================================
Provides async engine, session factory, and a get_db() FastAPI dependency.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from cloud.shared.config import get_settings
from cloud.shared.db_models import Base

settings = get_settings()

# ─────────────────────────────────────────────
# Engine — NullPool recommended for serverless/K8s
# ─────────────────────────────────────────────
is_sqlite = "sqlite" in settings.postgres_url

engine_kwargs = {
    "echo": settings.environment == "development",
    "future": True,
}

if not is_sqlite:
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    })

engine: AsyncEngine = create_async_engine(
    settings.postgres_url,
    **engine_kwargs
)

# ─────────────────────────────────────────────
# Session factory
# ─────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ─────────────────────────────────────────────
# FastAPI dependency: yields a session per request
# ─────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Usage in FastAPI route:
        async def my_route(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─────────────────────────────────────────────
# Init DB: create all tables (used in dev / first run)
# ─────────────────────────────────────────────
async def init_db() -> None:
    """
    Creates all tables if they don't exist.
    In production, use Alembic migrations instead.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ─────────────────────────────────────────────
# Health check helper
# ─────────────────────────────────────────────
async def check_db_connection() -> bool:
    """Returns True if the database is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception:
        return False
