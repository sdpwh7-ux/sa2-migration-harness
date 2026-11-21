"""SQLite test helpers for the technical demonstration project."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
from sqlalchemy.pool import ConnectionPoolEntry, QueuePool


def install_sqlite_legacy_begin_control(async_engine: AsyncEngine) -> None:
    """Hand BEGIN to SQLAlchemy on Python 3.11's legacy sqlite3 driver.

    That driver does not start a transaction for SAVEPOINT. A released
    savepoint would then survive ROLLBACK of the outer transaction.
    """

    @event.listens_for(async_engine.sync_engine, "connect")
    def _disable_driver_begin(
        dbapi_connection: DBAPIConnection,
        _connection_record: ConnectionPoolEntry,
    ) -> None:
        dbapi_connection.isolation_level = None

    @event.listens_for(async_engine.sync_engine, "begin")
    def _emit_begin(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN")


def open_savepoint_session(connection: AsyncConnection) -> AsyncSession:
    return AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


def assert_pool_idle(async_engine: AsyncEngine) -> None:
    pool = async_engine.pool
    assert isinstance(pool, QueuePool)
    assert pool.checkedout() == 0
