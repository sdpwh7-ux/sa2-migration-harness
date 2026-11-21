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

`stream_pending_ids` is a supplied technical exercise reproduction, not a production incident. The session is closed only after the `for` loop. Early `aclose()` throws `GeneratorExit` at the `yield`, skips that `close()`, and leaves the pooled connection checked out.
