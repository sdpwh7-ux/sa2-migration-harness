"""Regression for the supplied async-generator AsyncSession leak."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import cast

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.stream_repo import stream_pending_ids
from tests.sqlite import assert_pool_idle


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_early_break_with_aclosing_returns_connection(
    engine: AsyncEngine,
) -> None:
    factory = _factory(engine)
    pending = cast(
        AsyncGenerator[int, None],
        stream_pending_ids(factory, limit=3),
    )
    async with aclosing(pending) as pending_ids:
        async for pending_id in pending_ids:
            assert pending_id == 1
            break
    assert_pool_idle(engine)
