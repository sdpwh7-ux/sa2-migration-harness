"""Read models for the technical demonstration project."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    sku: str
    amount_cents: int


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    orders: list[OrderRead]
