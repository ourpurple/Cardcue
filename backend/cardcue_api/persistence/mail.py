"""SQLAlchemy ORM models for Mailbox, MailCursor, MailJob, EmailSource, and EmailAttachment."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cardcue_api.persistence.models import Base


class Mailbox(Base):
    __tablename__ = "mailboxes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_address: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    imap_host: Mapped[str] = mapped_column(String(255), nullable=False)
    imap_port: Mapped[int] = mapped_column(Integer, nullable=False, default=993)
    use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    encrypted_auth_token: Mapped[str] = mapped_column(Text, nullable=False)
    auth_type: Mapped[str] = mapped_column(String(20), nullable=False, default="password")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    settings_json: Mapped[dict] = mapped_column(__import__("sqlalchemy").JSON, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tested_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_config: Mapped[dict | None] = mapped_column(__import__("sqlalchemy").JSON, nullable=True)
    pending_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cursors: Mapped[list["MailCursor"]] = relationship(back_populates="mailbox", cascade="all, delete-orphan")
    jobs: Mapped[list["MailJob"]] = relationship(back_populates="mailbox", cascade="all, delete-orphan")
    email_sources: Mapped[list["EmailSource"]] = relationship(back_populates="mailbox", cascade="all, delete-orphan")


class MailCursor(Base):
    __tablename__ = "mail_cursors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False)
    folder: Mapped[str] = mapped_column(String(100), nullable=False, default="INBOX")
    uidvalidity: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_uid: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    mailbox: Mapped["Mailbox"] = relationship(back_populates="cursors")

    __table_args__ = (
        UniqueConstraint("mailbox_id", "folder", name="uq_mail_cursor_mailbox_folder"),
    )


class MailJob(Base):
    __tablename__ = "mail_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    emails_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    emails_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    statement_candidates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    mailbox: Mapped["Mailbox"] = relationship(back_populates="jobs")


class EmailSource(Base):
    __tablename__ = "email_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False)
    folder: Mapped[str] = mapped_column(String(100), nullable=False, default="INBOX")
    uid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uidvalidity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sender: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    recipient: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    email_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_statement_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parse_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    mailbox: Mapped["Mailbox"] = relationship(back_populates="email_sources")
    attachments: Mapped[list["EmailAttachment"]] = relationship(back_populates="email_source", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("mailbox_id", "folder", "uidvalidity", "uid", name="uq_email_source_uid"),
        Index("ix_email_sources_message_id", "message_id"),
        Index("ix_email_sources_body_hash", "body_hash"),
        Index("ix_email_sources_candidate", "is_statement_candidate", "parse_status"),
    )


class EmailAttachment(Base):
    __tablename__ = "email_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("email_sources.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    email_source: Mapped["EmailSource"] = relationship(back_populates="attachments")
