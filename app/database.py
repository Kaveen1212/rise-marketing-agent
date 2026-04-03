"""
app/database.py
─────────────────────────────────────────────────────────────────────────────
Async SQLAlchemy engine, session factory, and base model class.

Security measures implemented here:
  ① SSL required      — all connections encrypted in transit (TLS 1.2+)
  ② Connection pool   — limits concurrent connections; prevents DB exhaustion
  ③ Pool pre-ping     — drops stale connections before reuse (no silent failures)
  ④ Pool recycle      — rotates connections to avoid server-side timeout drops
  ⑤ No raw strings    — SQLAlchemy ORM always uses parameterised queries;
                         SQL injection is architecturally impossible via ORM
  ⑥ Scoped sessions   — each request gets its own session, closed on exit;
                         no session sharing between requests

Usage:
    from app.database import get_session, Base

    # In FastAPI route / dependency:
    async def my_route(db: AsyncSession = Depends(get_session)):
        result = await db.execute(select(PosterBrief))
─────────────────────────────────────────────────────────────────────────────
"""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, MappedColumn
from sqlalchemy.pool import NullPool

from app.config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────

def _build_engine() -> AsyncEngine:
    """
    Create the async SQLAlchemy engine with security-first configuration.

    NullPool is used in test environments (prevents connection leaks between
    tests).  Production uses QueuePool (default) with size limits.
    """
    pool_class_kwargs: dict[str, Any] = {}

    if settings.APP_ENV == "testing":
        # Each test starts with a clean slate — no pooled connections
        pool_class_kwargs["poolclass"] = NullPool
    else:
        pool_class_kwargs.update(
            {
                "pool_size": settings.DB_POOL_SIZE,
                "max_overflow": settings.DB_MAX_OVERFLOW,
                "pool_timeout": settings.DB_POOL_TIMEOUT,
                "pool_recycle": settings.DB_POOL_RECYCLE,
                # ② Pool pre-ping: test connection health before reuse
                # Costs one cheap SELECT 1 per checkout but prevents
                # "connection already closed" errors after DB restarts
                "pool_pre_ping": True,
            }
        )

    return create_async_engine(
        # ① SSL: settings.async_database_url always appends ssl=require
        settings.async_database_url,
        # Log SQL in dev/staging only — never in production
        echo=settings.DB_ECHO_SQL,
        # Future mode: enables the 2.0 style throughout
        future=True,
        **pool_class_kwargs,
    )


engine: AsyncEngine = _build_engine()


# ─────────────────────────────────────────────────────────────────────────────
# Session factory
# ─────────────────────────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    # expire_on_commit=False: after commit, ORM objects stay usable in the
    # same request without triggering extra SELECT queries
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ─────────────────────────────────────────────────────────────────────────────
# Base model
# ─────────────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """
    Shared declarative base for all ORM models.

    All models inheriting from Base are automatically discovered by Alembic
    via the metadata object.  Do NOT use multiple Base classes.
    """
    pass


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI dependency — request-scoped sessions
# ─────────────────────────────────────────────────────────────────────────────

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a request-scoped async database session.

    ⑥ Session is always closed in the finally block — even if the route
       raises an exception.  This prevents connection leaks.

    Example:
        @router.get("/briefs")
        async def list_briefs(db: AsyncSession = Depends(get_session)):
            ...
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


# ─────────────────────────────────────────────────────────────────────────────
# Database health check
# ─────────────────────────────────────────────────────────────────────────────

async def check_database_connection() -> bool:
    """
    Verify the database is reachable.
    Called at application startup — app refuses to start if DB is unreachable.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        # Log the error but don't expose connection details
        import structlog
        log = structlog.get_logger()
        log.error("database_connection_failed", error=str(exc))
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Schema initialisation (used in tests only)
# ─────────────────────────────────────────────────────────────────────────────

async def create_all_tables(connection: AsyncConnection) -> None:
    """
    Create all tables from ORM metadata.
    Use only in tests — production uses Alembic migrations.
    """
    await connection.run_sync(Base.metadata.create_all)


async def drop_all_tables(connection: AsyncConnection) -> None:
    """Drop all tables. Use only in tests."""
    await connection.run_sync(Base.metadata.drop_all)
