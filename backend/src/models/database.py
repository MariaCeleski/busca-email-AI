"""SQLAlchemy async engine, session factory, and declarative Base.

Provides the core database infrastructure for the application:
- Async engine configured for asyncpg
- Async session factory for dependency injection
- Declarative Base class for ORM models
"""

from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config import get_settings


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""

    pass


def create_engine(database_url: Optional[str] = None):
    """Create an async SQLAlchemy engine.

    Args:
        database_url: Optional override for database URL. Uses settings if not provided.

    Returns:
        AsyncEngine instance configured for asyncpg.
    """
    url = database_url or get_settings().database_url
    return create_async_engine(
        url,
        echo=False,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
    )


def create_session_factory(engine=None) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine.

    Args:
        engine: Optional engine instance. Creates one from settings if not provided.

    Returns:
        async_sessionmaker configured for the engine.
    """
    if engine is None:
        engine = create_engine()
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# Default engine and session factory (lazy, created on first import if needed)
_engine = None
_session_factory = None


def get_engine():
    """Get or create the default async engine."""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the default async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = create_session_factory(get_engine())
    return _session_factory


async def get_session() -> AsyncSession:
    """Dependency that yields an async database session.

    Usage in FastAPI:
        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session
