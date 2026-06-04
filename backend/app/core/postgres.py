from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings


@lru_cache
def get_postgres_engine() -> AsyncEngine:
    return create_async_engine(get_settings().postgres_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_postgres_engine(), expire_on_commit=False)


async def postgres_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


async def close_postgres_engine() -> None:
    if get_postgres_engine.cache_info().currsize:
        await get_postgres_engine().dispose()
        get_postgres_engine.cache_clear()
        get_session_factory.cache_clear()
