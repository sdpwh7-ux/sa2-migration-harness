# sa2-migration-harness

Technical demonstration project (技术演示项目) for async SQLAlchemy 2 and Pydantic 2.

`get_user_with_orders` loads a `User` with `selectinload(User.orders)` and validates a `UserRead`. `User.orders` and `Order.user` both use `lazy="raise"`. The repository holds that model, schema, repository function, and tests.

## Setup

Python 3.11.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Checks

```bash
mypy app tests
pytest -v
```

`pyproject.toml` sets mypy strict mode and the Pydantic mypy plugin. GitHub Actions runs `mypy app tests` and `pytest -v` on push and pull_request with Python 3.11.

## Guardrails

- Reading `User.orders` or `Order.user` without an eager option raises `InvalidRequestError`.
- `get_user_with_orders` returns `UserRead | None`. The query uses `selectinload(User.orders)` before `UserRead.model_validate`.
- Tests open a file-backed `sqlite+aiosqlite` engine with `AsyncAdaptedQueuePool`. Each session test joins an outer connection transaction, uses `AsyncSession(..., join_transaction_mode="create_savepoint", expire_on_commit=False)`, closes the session, and rolls back the outer transaction. After that connection closes, the pool is a `QueuePool` and `checkedout()` is `0`.
- Python 3.11 `sqlite3` still uses legacy transaction control: `SAVEPOINT` does not imply `BEGIN`, so a released savepoint can remain after `ROLLBACK`. The test engine disables the driver's `BEGIN` and emits `BEGIN` from SQLAlchemy. An inner `session.commit()` is therefore undone by the outer rollback.

## Supplied async-generator exercise

`stream_pending_ids` is a supplied technical exercise. The first form, kept in the reproduction commit, closed the `AsyncSession` only after a normal loop. That was not a production incident. `aclose()` throws `GeneratorExit` at `yield` and skipped `close()`, so the pooled connection stayed checked out (`checkedout() == 1` after `aclosing` and `break`).

Cleanup now runs in `finally`. If cancellation hits `session.close()`, that cancellation is cleared only long enough to run `close()` again. `CancelledError` is raised after a `close()` attempt finishes. `await asyncio.shield(session.close())` alone does not give that order: a cancel during the shield raises `CancelledError` in the caller while the shielded close is still running.

On Python 3.11 a bare `async for` / `break` does not close the generator, so it does not run that `finally`. Callers use `contextlib.aclosing` unless they take ownership another way that calls `aclose()`:

```python
from contextlib import aclosing

async with aclosing(stream_pending_ids(session_factory)) as pending_ids:
    async for pending_id in pending_ids:
        ...
```

The leak tests check `pool.checkedout() == 0` after `aclosing` plus `break`, after task cancellation, and after cancellation delivered during `close()`, before engine disposal. They do not wait on the garbage collector. They do not show that a bare `async for` / `break` returns the connection.
