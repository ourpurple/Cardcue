"""SQLAlchemy ORM model for StatementDraft."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cardcue_api.persistence.models import Base


class StatementDraftModel(Base):
    __tablename__ = "statement_drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_sources.id", ondelete="SET NULL"), nullable=True
    )
    mailbox_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_review", index=True)
    bank: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    minimum_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    statement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    account_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    card_tails: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    review_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    matched_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    matched_card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cards.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statement_versions.id", ondelete="SET NULL"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extractor_name: Mapped[str] = mapped_column(String(50), nullable=False, default="rule")
    model_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    email_source = relationship("EmailSource", foreign_keys=[email_source_id])
    mailbox = relationship("Mailbox", foreign_keys=[mailbox_id])
    matched_account = relationship("Account", foreign_keys=[matched_account_id])
    matched_card = relationship("Card", foreign_keys=[matched_card_id])
    confirmed_version = relationship("StatementVersion", foreign_keys=[confirmed_version_id])
