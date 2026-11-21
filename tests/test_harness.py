"""Eager-load, lazy='raise', and outer-rollback checks."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import Order, User
from app.repo import get_user_with_orders
from app.schemas import OrderRead, UserRead
from tests.sqlite import assert_pool_idle, open_savepoint_session


async def _add_user(session: AsyncSession, email: str) -> User:
    user = User()
    user.email = email
    session.add(user)
    await session.flush()
    return user


async def _add_order(
    session: AsyncSession, user_id: int, sku: str, amount_cents: int
) -> Order:
    order = Order()
    order.user_id = user_id
    order.sku = sku
    order.amount_cents = amount_cents
    session.add(order)
    await session.flush()
    return order


async def test_get_user_with_orders_returns_eager_loaded_dto(
    session: AsyncSession,
) -> None:
    user = await _add_user(session, "reader@example.com")
    await _add_order(session, user.id, "SKU-1", 1200)
    await _add_order(session, user.id, "SKU-2", 500)
    await session.commit()

    dto = await get_user_with_orders(session, user.id)

    assert isinstance(dto, UserRead)
    assert dto.id == user.id
    assert dto.email == "reader@example.com"
    assert [order.sku for order in dto.orders] == ["SKU-1", "SKU-2"]
    assert [order.amount_cents for order in dto.orders] == [1200, 500]
    assert all(order.user_id == user.id for order in dto.orders)
    assert all(isinstance(order, OrderRead) for order in dto.orders)


async def test_get_user_with_orders_empty_collection(session: AsyncSession) -> None:
    user = await _add_user(session, "empty@example.com")
    await session.commit()

    dto = await get_user_with_orders(session, user.id)

    assert dto is not None
    assert dto.orders == []


async def test_get_user_with_orders_missing_returns_none(
    session: AsyncSession,
) -> None:
    assert await get_user_with_orders(session, 999_999) is None


async def test_user_orders_lazy_raise(session: AsyncSession) -> None:
    user = await _add_user(session, "lazy-user@example.com")
    await _add_order(session, user.id, "SKU-L", 100)
    await session.commit()

    loaded = await session.scalar(select(User).where(User.id == user.id))
    assert loaded is not None
    with pytest.raises(InvalidRequestError):
        _ = loaded.orders


async def test_order_user_lazy_raise(session: AsyncSession) -> None:
    user = await _add_user(session, "lazy-order@example.com")
    order = await _add_order(session, user.id, "SKU-U", 250)
    await session.commit()

    loaded = await session.scalar(select(Order).where(Order.id == order.id))
    assert loaded is not None
    with pytest.raises(InvalidRequestError):
        _ = loaded.user


async def test_inner_commit_does_not_persist_after_outer_rollback(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        outer = await connection.begin()
        inner = open_savepoint_session(connection)
        user = User()
        user.email = "rollback@example.com"
        inner.add(user)
        await inner.commit()
        visible = await inner.scalar(
            select(User.id).where(User.email == "rollback@example.com")
        )
        assert visible is not None
        await inner.close()
        await outer.rollback()

    assert_pool_idle(engine)

    async with engine.connect() as connection:
        remaining = await connection.scalar(
            select(User.id).where(User.email == "rollback@example.com")
        )
        assert remaining is None
