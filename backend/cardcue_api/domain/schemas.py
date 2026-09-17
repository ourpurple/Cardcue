"""Pydantic schemas for API input/output. Separate from SQLAlchemy models."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------- Account ----------

class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bank: str = Field(min_length=1, max_length=100)
    alias: str | None = Field(default=None, max_length=100)
    reference: str | None = Field(default=None, max_length=100)


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str | None = Field(default=None, max_length=100)
    status: Literal["active", "archived"] | None = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    bank: str
    alias: str | None
    reference: str | None
    status: str
    created_at: datetime
    updated_at: datetime


# ---------- Card ----------

class CardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: uuid.UUID
    display_name: str | None = Field(default=None, max_length=100)
    tail: str = Field(min_length=1, max_length=10)


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    account_id: uuid.UUID
    display_name: str | None
    tail: str
    status: str
    created_at: datetime


# ---------- Statement ----------

class StatementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: uuid.UUID
    currency: Literal["CNY", "USD"]
    statement_date: date
    due_date: date
    amount_minor: int = Field(ge=0, le=999_999_999_999)
    minimum_minor: int | None = Field(default=None, ge=0, le=999_999_999_999)
    source: str = Field(default="manual", max_length=50)


class StatementVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    statement_id: uuid.UUID
    version_number: int
    amount_minor: int
    minimum_minor: int | None
    source: str
    reason: str | None
    confirmed_at: datetime | None
    confirmed_by: str | None
    created_at: datetime


class StatementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    account_id: uuid.UUID
    currency: str
    statement_date: date
    due_date: date
    current_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class StatementDetail(StatementOut):
    current_version: StatementVersionOut | None = None
    total_paid_minor: int = 0
    remaining_minor: int = 0


# ---------- Payment ----------

class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement_id: uuid.UUID
    amount_minor: int = Field(gt=0, le=999_999_999_999)
    currency: Literal["CNY", "USD"]
    note: str | None = Field(default=None, max_length=200)
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Client-generated idempotency key")


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    statement_id: uuid.UUID
    amount_minor: int
    currency: str
    note: str | None
    recorded_at: datetime
    revoked_at: datetime | None
    revoke_reason: str | None


class RevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=200)
