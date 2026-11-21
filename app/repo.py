"""Repository functions for the technical demonstration project."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import User
from app.schemas import UserRead


async def get_user_with_orders(
    session: AsyncSession, user_id: int
) -> UserRead | None:
    result = await session.execute(
        select(User).where(User.id == user_id).options(selectinload(User.orders))
    )
    user = result.scalar_one_or_none()
    if user is None:
        return None
    return UserRead.model_validate(user)
