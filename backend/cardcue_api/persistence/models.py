"""SQLAlchemy ORM models for CardCue core business entities.

All monetary amounts are stored as integers in the smallest currency unit
(e.g. cents / 分). No floating point is used anywhere for money.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Account – a billing account at a bank (not a card)
# ---------------------------------------------------------------------------

class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank: Mapped[str] = mapped_column(String(100), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="User-chosen display name")
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Account reference from bank email")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cards: Mapped[list["Card"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    statements: Mapped[list["Statement"]] = relationship(back_populates="account")


# ---------------------------------------------------------------------------
# Card – a physical/virtual card linked to an Account
# ---------------------------------------------------------------------------

class Card(Base):
    __tablename__ = "cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tail: Mapped[str] = mapped_column(String(10), nullable=False, comment="Last 4 digits shown; NOT a unique key")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["Account"] = relationship(back_populates="cards")


# ---------------------------------------------------------------------------
# Statement – one billing period for one account & currency
# ---------------------------------------------------------------------------

class Statement(Base):
    __tablename__ = "statements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, comment="ISO 4217, e.g. CNY / USD")
    statement_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statement_versions.id", use_alter=True), nullable=True,
        comment="Points to the currently effective version"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("account_id", "currency", "statement_date", name="uq_statement_account_currency_period"),
        CheckConstraint("due_date >= statement_date", name="ck_statement_due_after_start"),
    )

    account: Mapped["Account"] = relationship(back_populates="statements")
    versions: Mapped[list["StatementVersion"]] = relationship(
        back_populates="statement", foreign_keys="StatementVersion.statement_id"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="statement")


# ---------------------------------------------------------------------------
# StatementVersion – immutable snapshot of a statement's amounts
# ---------------------------------------------------------------------------

class StatementVersion(Base):
    __tablename__ = "statement_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("statements.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False, default=1)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="Total bill in minor units")
    minimum_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="Minimum payment in minor units")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual", comment="manual / email / model")
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="Why this version was created")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="device id or 'system'")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("statement_id", "version_number", name="uq_version_per_statement"),
        CheckConstraint("amount_minor >= 0", name="ck_version_amount_nonneg"),
        CheckConstraint("minimum_minor IS NULL OR minimum_minor >= 0", name="ck_version_minimum_nonneg"),
        CheckConstraint("minimum_minor IS NULL OR minimum_minor <= amount_minor", name="ck_version_minimum_le_amount"),
    )

    statement: Mapped["Statement"] = relationship(
        back_populates="versions", foreign_keys=[statement_id]
    )


# ---------------------------------------------------------------------------
# Payment – a recorded repayment against a Statement
# ---------------------------------------------------------------------------

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("statements.id"), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="Payment in minor units")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_payment_amount_positive"),
        Index("ix_payment_statement", "statement_id"),
    )

    statement: Mapped["Statement"] = relationship(back_populates="payments")
