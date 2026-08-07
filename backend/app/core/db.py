from collections.abc import AsyncIterator
from functools import lru_cache
from typing import cast

from redis.asyncio import Redis, from_url
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


async def database_is_ready() -> bool:
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


@lru_cache
def get_redis() -> Redis:
    return cast(
        Redis,
        from_url(  # type: ignore[no-untyped-call]
            get_settings().redis_url,
            encoding="utf-8",
            decode_responses=True,
        ),
    )


async def redis_is_ready() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:  # Redis client errors are intentionally not exposed to callers.
        return False


async def dispose_engine() -> None:
    await get_engine().dispose()
    await get_redis().aclose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_redis.cache_clear()
