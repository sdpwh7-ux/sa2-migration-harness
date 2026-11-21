"""File SQLite fixtures for the technical demonstration harness."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.models import Base
from tests.sqlite import (
    assert_pool_idle,
    install_sqlite_legacy_begin_control,
    open_savepoint_session,
)


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    database_path = tmp_path / "harness.sqlite3"
    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        poolclass=AsyncAdaptedQueuePool,
    )
    install_sqlite_legacy_begin_control(test_engine)
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield test_engine
    finally:
        await test_engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as connection:
        outer = await connection.begin()
        test_session = open_savepoint_session(connection)
        try:
            yield test_session
        finally:
            await test_session.close()
            await outer.rollback()
    assert_pool_idle(engine)
