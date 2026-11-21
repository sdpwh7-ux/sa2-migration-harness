"""Pending-id stream for the supplied async-generator session exercise.

The first revision closed the session only after a normal loop. That was a
supplied challenge reproduction, not a production incident: ``aclose()``
throws ``GeneratorExit`` at ``yield`` and skipped ``close()``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_PENDING_IDS = text("SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3")


async def _close_session(session: AsyncSession) -> None:
    """Check the session's connection in, then propagate cancellation.

    A lone ``await asyncio.shield(session.close())`` does not do this on
    Python 3.11. Cancellation that arrives during the shielded await is
    raised in this task immediately, while the shielded ``close()`` keeps
    running. Callers can then observe ``CancelledError`` with the
    connection still checked out.

    ``close()`` is awaited in this task. If that await is cancelled, the
    pending cancellation is cleared only so ``close()`` can run again.
    ``CancelledError`` is raised after a ``close()`` attempt finishes.
    """
    task = asyncio.current_task()
    cancelled = False
    try:
        while True:
            if task is not None and task.cancelling():
                cancelled = True
                while task.uncancel():
                    pass
            try:
                await session.close()
            except asyncio.CancelledError:
                cancelled = True
                continue
            else:
                break
    finally:
        if cancelled and task is not None and task.cancelling() == 0:
            task.cancel()
    if cancelled:
        raise asyncio.CancelledError


async def stream_pending_ids(
    session_factory: async_sessionmaker[AsyncSession],
    limit: int = 100,
) -> AsyncIterator[int]:
    session = session_factory()
    try:
        result = await session.execute(_PENDING_IDS)
        rows = result.scalars().all()
        for value in list(rows)[:limit]:
            yield int(value)
    finally:
        await _close_session(session)
