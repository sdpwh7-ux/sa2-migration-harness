"""ORM models for the technical demonstration project."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    orders: Mapped[list[Order]] = relationship(
        back_populates="user",
        lazy="raise",
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sku: Mapped[str] = mapped_column(String(64))
    amount_cents: Mapped[int] = mapped_column()
    user: Mapped[User] = relationship(
        back_populates="orders",
        lazy="raise",
    )
