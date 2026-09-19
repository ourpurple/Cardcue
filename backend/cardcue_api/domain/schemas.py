"""Pydantic schemas for API input/output. Separate from SQLAlchemy models."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

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
    revision: int = 1
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
    tail: str = Field(pattern=r"^[0-9]{4}$")


class CardOut(BaseModel):
    revision: int = 1
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
    amount_minor: int = Field(ge=0, le=999_999_999_999, strict=True)
    minimum_minor: int | None = Field(default=None, ge=0, le=999_999_999_999, strict=True)
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
    amount_minor: int = Field(gt=0, le=999_999_999_999, strict=True)
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


# ---------- Sync (S2: SYNC-01 / SYNC-02) ----------

class SyncChangeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    seq: int
    entity_type: str = Field(description="account / card / statement / payment")
    entity_id: uuid.UUID
    action: str = Field(description="create / update / delete / revoke")
    snapshot: dict | None = None
    created_at: datetime


class SyncBootstrapResponse(BaseModel):
    cursor: int = Field(description="Baseline sequence number for incremental sync")
    server_time: datetime
    accounts: list[AccountOut]
    cards: list[CardOut]
    statements: list[StatementDetail]
    payments: list[PaymentOut]


class SyncChangesResponse(BaseModel):
    cursor: int = Field(description="Max sequence number included in this batch")
    has_more: bool
    changes: list[SyncChangeItem]
    server_time: datetime


class SyncPaymentResponse(BaseModel):
    payment: PaymentOut
    created: bool
    statement_detail: StatementDetail


# ---------- Mail (S3: Mailbox, MailJob, EmailSource, EmailAttachment) ----------

class MailboxCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_address: str = Field(min_length=3, max_length=255)
    imap_host: str = Field(min_length=1, max_length=255)
    imap_port: int = Field(default=993, ge=1, le=65535)
    use_ssl: bool = True
    auth_token: str = Field(min_length=1, description="Plaintext password or IMAP auth code")
    auth_type: str = Field(default="password", max_length=20)
    is_active: bool = True
    check_interval_minutes: int = Field(default=30, ge=5, le=1440)


class MailboxUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    imap_host: str | None = Field(default=None, max_length=255)
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    use_ssl: bool | None = None
    auth_token: str | None = Field(default=None, min_length=1)
    is_active: bool | None = None
    check_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    status: str | None = Field(default=None, max_length=30)


class MailboxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email_address: str
    imap_host: str
    imap_port: int
    use_ssl: bool
    auth_token_masked: str = "********"
    auth_type: str
    is_active: bool
    check_interval_minutes: int
    last_checked_at: datetime | None
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class MailJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    mailbox_id: uuid.UUID
    trigger_type: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    emails_checked: int
    emails_fetched: int
    statement_candidates: int
    created_at: datetime


class EmailAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email_source_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class EmailSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    mailbox_id: uuid.UUID
    folder: str
    uid: int
    uidvalidity: int
    message_id: str | None
    subject: str
    sender: str
    recipient: str
    email_date: datetime
    body_hash: str
    has_attachments: bool
    is_statement_candidate: bool
    parse_status: str
    error_message: str | None
    created_at: datetime
    attachments: list[EmailAttachmentOut] = []


class MailSyncTriggerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mailbox_id: uuid.UUID | None = None
    since_days: int | None = Field(default=None, ge=1, le=365)


class MailSyncTriggerResponse(BaseModel):
    job_ids: list[uuid.UUID]
    message: str


# ---------------------------------------------------------------------------
# S4 Statement Drafts & Review
# ---------------------------------------------------------------------------

class StatementDraftOut(BaseModel):
    revision: int = 1
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email_source_id: uuid.UUID | None
    mailbox_id: uuid.UUID | None
    status: str
    bank: str | None
    currency: str | None
    amount_minor: int | None
    minimum_minor: int | None
    statement_date: date | None
    due_date: date | None
    account_reference: str | None
    card_tails: list[str] = []
    evidence: list[dict[str, Any]] = []
    review_reasons: list[str] = []
    matched_account_id: uuid.UUID | None
    matched_card_id: uuid.UUID | None
    confirmed_version_id: uuid.UUID | None
    rejection_reason: str | None
    extractor_name: str
    created_at: datetime
    updated_at: datetime


class StatementDraftConfirmRequest(BaseModel):
    request_id: uuid.UUID | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    expected_statement_version_id: uuid.UUID | None = None
    model_config = ConfigDict(extra="forbid")
    account_id: uuid.UUID
    card_id: uuid.UUID | None = None
    currency: str | None = None
    amount_minor: int | None = Field(default=None, ge=0, le=999_999_999_999, strict=True)
    minimum_minor: int | None = Field(default=None, ge=0, le=999_999_999_999, strict=True)
    statement_date: date | None = None
    due_date: date | None = None


class StatementDraftRejectRequest(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1)
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=255)


class StatementDraftConfirmResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    draft_id: uuid.UUID
    statement: StatementDetail
    version: StatementVersionOut
