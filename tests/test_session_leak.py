"""Caller contract for stream_pending_ids session cleanup."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import ClassVar, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import QueuePool

from app.stream_repo import stream_pending_ids
from tests.sqlite import assert_pool_idle


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _stream(
    engine: AsyncEngine, limit: int = 100
) -> AsyncGenerator[int, None]:
    return cast(
        AsyncGenerator[int, None],
        stream_pending_ids(_factory(engine), limit),
    )


async def test_early_break_with_aclosing_returns_connection(
    engine: AsyncEngine,
) -> None:
    async with aclosing(_stream(engine, limit=3)) as pending_ids:
        async for pending_id in pending_ids:
            assert pending_id == 1
            break
    assert_pool_idle(engine)


async def test_plain_break_leaves_connection_until_aclose(
    engine: AsyncEngine,
) -> None:
    pending_ids = _stream(engine, limit=3)
    async for pending_id in pending_ids:
        assert pending_id == 1
        break
    pool = engine.pool
    assert isinstance(pool, QueuePool)
    assert pool.checkedout() == 1
    await pending_ids.aclose()
    assert_pool_idle(engine)


async def test_exhaustion_returns_connection(engine: AsyncEngine) -> None:
    async with aclosing(_stream(engine, limit=3)) as pending_ids:
        assert [pending_id async for pending_id in pending_ids] == [1, 2, 3]
    assert_pool_idle(engine)


async def test_task_cancellation_returns_connection(engine: AsyncEngine) -> None:
    entered = asyncio.Event()

    async def consume() -> None:
        async with aclosing(_stream(engine, limit=3)) as pending_ids:
            async for _pending_id in pending_ids:
                entered.set()
                await asyncio.Event().wait()

    task = asyncio.create_task(consume())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert_pool_idle(engine)


class _CloseHold:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.saw_cancel = asyncio.Event()
        self.release = asyncio.Event()
        self.attempts = 0


class _HoldingSession(AsyncSession):
    """Session whose close waits, and reports cancellation, before check-in."""

    hold: ClassVar[_CloseHold]

    async def close(self) -> None:
        hold = type(self).hold
        hold.attempts += 1
        hold.started.set()
        try:
            await hold.release.wait()
        except asyncio.CancelledError:
            hold.saw_cancel.set()
            raise
        await super().close()


async def test_cancellation_during_close_checks_in_before_it_surfaces(
    engine: AsyncEngine,
) -> None:
    hold = _CloseHold()
    _HoldingSession.hold = hold
    # async_sessionmaker is invariant in its session type. The holding
    # subclass is still an AsyncSession at runtime.
    factory = cast(
        async_sessionmaker[AsyncSession],
        async_sessionmaker(
            engine,
            class_=_HoldingSession,
            expire_on_commit=False,
        ),
    )
    pending = cast(
        AsyncGenerator[int, None],
        stream_pending_ids(factory, limit=3),
    )

    async def consume() -> None:
        async with aclosing(pending) as pending_ids:
            async for _pending_id in pending_ids:
                break

    task = asyncio.create_task(consume())
    await hold.started.wait()
    pool = engine.pool
    assert isinstance(pool, QueuePool)
    assert pool.checkedout() == 1
    task.cancel()
    await asyncio.wait_for(hold.saw_cancel.wait(), timeout=2)
    # One loop turn lets a cleanup that gave up on cancellation finish the task.
    # A cleanup that still has to check the connection in stays blocked on release.
    await asyncio.sleep(0)
    assert not task.done()
    hold.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert hold.attempts >= 2
    assert_pool_idle(engine)
