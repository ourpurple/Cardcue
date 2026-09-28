"""SQLAlchemy ORM models for transaction details.

DraftTransaction   – parsed-but-unconfirmed line items from a statement draft.
ConfirmedTransaction – reviewed and accepted line items tied to a
                       StatementVersion.

All monetary amounts are stored as integers in the smallest currency unit
(e.g. cents / 分).  No floating point is used anywhere for money.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cardcue_api.persistence.models import Base


# ---------------------------------------------------------------------------
# DraftTransaction – a single line item extracted from a statement draft
# ---------------------------------------------------------------------------

class DraftTransaction(Base):
    __tablename__ = "draft_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statement_drafts.id"), nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    posting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount_minor: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="Transaction amount in minor units",
    )
    currency: Mapped[str | None] = mapped_column(
        String(3), nullable=True, comment="ISO 4217",
    )
    card_tail: Mapped[str | None] = mapped_column(
        String(4), nullable=True, comment="Card last-4 used for this transaction",
    )
    transaction_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="purchase/refund/interest/fee/…",
    )
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list, comment="[{field, excerpt}]",
    )
    review_flags: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("draft_id", "sequence", name="uq_draft_tx_sequence"),
        CheckConstraint(
            "amount_minor IS NULL OR amount_minor != 0",
            name="ck_draft_tx_amount_nonzero",
        ),
        Index("ix_draft_tx_draft", "draft_id"),
    )

    # Relationships
    draft = relationship("StatementDraftModel", foreign_keys=[draft_id])


# ---------------------------------------------------------------------------
# ConfirmedTransaction – a reviewed, accepted transaction line item
# ---------------------------------------------------------------------------

class ConfirmedTransaction(Base):
    __tablename__ = "confirmed_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    statement_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statement_versions.id"), nullable=False,
    )
    statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statements.id"), nullable=False,
        comment="Denormalised for fast queries",
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    posting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="Transaction amount in minor units",
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, comment="ISO 4217",
    )
    card_tail: Mapped[str | None] = mapped_column(
        String(4), nullable=True,
    )
    transaction_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
    )
    source_draft_tx_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("draft_transactions.id"), nullable=True,
        comment="Traceability back to draft",
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    confirmed_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "statement_version_id", "sequence", name="uq_confirmed_tx_sequence",
        ),
        CheckConstraint("amount_minor != 0", name="ck_confirmed_tx_amount_nonzero"),
        Index("ix_confirmed_tx_stmt", "statement_id"),
        Index("ix_confirmed_tx_ver", "statement_version_id"),
    )

    # Relationships
    statement_version = relationship(
        "StatementVersion", foreign_keys=[statement_version_id],
    )
    statement = relationship("Statement", foreign_keys=[statement_id])
    source_draft_tx = relationship(
        "DraftTransaction", foreign_keys=[source_draft_tx_id],
    )


class DetailSet(Base):
    """Immutable reviewed-detail snapshot associated with a bill version, not a new debt."""

    __tablename__ = "detail_sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("statement_versions.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_draft_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("statement_drafts.id"), nullable=True)
    detail_status: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_transaction_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recognized_transaction_count: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_transaction_count: Mapped[int] = mapped_column(Integer, nullable=False)
    flagged_transaction_count: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_by: Mapped[str] = mapped_column(String(100), nullable=False)

    __table_args__ = (
        UniqueConstraint("statement_version_id", "revision", name="uq_detail_set_revision"),
        CheckConstraint("revision > 0", name="ck_detail_set_revision_positive"),
        CheckConstraint("recognized_transaction_count >= 0 AND confirmed_transaction_count >= 0 AND flagged_transaction_count >= 0", name="ck_detail_set_counts_nonnegative"),
        CheckConstraint("expected_transaction_count IS NULL OR expected_transaction_count > 0", name="ck_detail_set_expected_positive"),
        CheckConstraint("confirmed_transaction_count <= recognized_transaction_count AND flagged_transaction_count <= recognized_transaction_count", name="ck_detail_set_counts_bounded"),
    )


class DetailSetTransaction(Base):
    """Copied and new line items forming a complete immutable snapshot."""

    __tablename__ = "detail_set_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    detail_set_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("detail_sets.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    posting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    card_tail: Mapped[str | None] = mapped_column(String(4), nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_draft_tx_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("draft_transactions.id"), nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        UniqueConstraint("detail_set_id", "sequence", name="uq_detail_set_tx_sequence"),
        CheckConstraint("amount_minor != 0", name="ck_detail_set_tx_amount_nonzero"),
        Index("ix_detail_set_tx_set", "detail_set_id"),
    )

