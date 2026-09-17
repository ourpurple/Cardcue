"""Async engine and session factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import create_engine

from cardcue_api.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_size=5, max_overflow=5)
sync_engine = create_engine(settings.database_sync_url, echo=False, pool_size=3, max_overflow=3)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    """FastAPI dependency – yields an async session and commits on success."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
