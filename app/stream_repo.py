"""Supplied async-generator session-leak exercise.

Closing the session only after the loop is the challenge reproduction.
``aclose()`` from an early exit throws ``GeneratorExit`` at the yield, so
this ``close()`` does not run and the pooled connection stays checked out.
This is a technical exercise, not a production incident.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_PENDING_IDS = text("SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3")


async def stream_pending_ids(
    session_factory: async_sessionmaker[AsyncSession],
    limit: int = 100,
) -> AsyncIterator[int]:
    session = session_factory()
    result = await session.execute(_PENDING_IDS)
    rows = result.scalars().all()
    for value in list(rows)[:limit]:
        yield int(value)
    await session.close()
