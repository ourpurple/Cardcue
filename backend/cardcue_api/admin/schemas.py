import uuid
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from cardcue_api.admin.outbound import validate_url

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Login(Strict):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)

class Password(Strict):
    password: str = Field(min_length=1, max_length=256)

class ChangePassword(Password):
    new_password: str = Field(min_length=14, max_length=256)

class AccountEdit(Strict):
    expected_revision: int = Field(ge=1)
    bank: str | None = Field(None, min_length=1, max_length=100)
    alias: str | None = Field(None, max_length=100)
    reference: str | None = Field(None, max_length=100)
    status: Literal["active", "archived"] = "active"

class CardEdit(Strict):
    expected_revision: int = Field(ge=1)
    display_name: str | None = Field(None, max_length=100)
    tail: str | None = Field(None, pattern=r"^[0-9]{4}$")
    status: Literal["active", "archived"] = "active"

class MailConfig(Strict):
    expected_revision: int | None = None
    name: str = Field(min_length=1, max_length=100)
    email_address: str = Field(min_length=3, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    username: str = Field(default="", max_length=255)
    imap_host: str = Field(min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9.-]+$")
    imap_port: Literal[993, 143] = 993
    use_ssl: bool = True
    auth_token: str | None = Field(None, min_length=1, max_length=1000)
    folder: str = Field(default="INBOX", min_length=1, max_length=100, pattern=r'^[^\r\n\x00]+$')
    check_interval_minutes: int = Field(default=30, ge=5, le=1440)
    since_days: int = Field(default=90, ge=1, le=3650)
    max_messages: int = Field(default=100, ge=1, le=500)
    max_attachment_mb: int = Field(default=10, ge=1, le=20)
    sender_filter: str = Field(default="", max_length=500)
    subject_filter: str = Field(default="", max_length=500)
    keep_non_candidates: bool = False
    auto_parse: bool = True

class RevisionRequest(Strict):
    expected_revision: int = Field(ge=1)

class ModelConfig(Strict):
    name: str = Field(min_length=1, max_length=100)
    expected_revision: int | None = None
    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=100)
    api_key: str | None = Field(None, min_length=1, max_length=1000)
    temperature: float = Field(default=0, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=256, le=16384)
    timeout_seconds: int = Field(default=45, ge=5, le=120)
    max_retries: int = Field(default=1, ge=0, le=3)
    input_limit: int = Field(default=24000, ge=1000, le=100000)
    json_mode: bool = True
    daily_limit: int = Field(default=100, ge=1, le=5000)
    @field_validator("base_url")
    @classmethod
    def check_url(cls, value):
        validate_url(value)
        return value.rstrip("/")

class ModelTest(Strict):
    sample: bool = False

class JobCreate(Strict):
    kind: Literal["sync", "parse"]
    target_id: uuid.UUID
    since_days: int | None = Field(None, ge=1, le=3650)
    allow_external: bool = True
    force: bool = False

class DraftEdit(Strict):
    expected_revision: int = Field(ge=1)
    bank: str | None = Field(None, max_length=100)
    currency: Literal["CNY", "USD"] | None = None
    amount_minor: int | None = Field(None, ge=0, le=999999999999, strict=True)
    minimum_minor: int | None = Field(None, ge=0, le=999999999999, strict=True)
    statement_date: date | None = None
    due_date: date | None = None
    matched_account_id: uuid.UUID | None = None
    matched_card_id: uuid.UUID | None = None

class StatementCorrection(Strict):
    expected_version_id: uuid.UUID
    request_id: uuid.UUID
    amount_minor: int = Field(ge=0, le=999999999999, strict=True)
    minimum_minor: int | None = Field(None, ge=0, le=999999999999, strict=True)
    reason: str = Field(min_length=3, max_length=200)

class SourceAction(Strict):
    action: Literal["ignore", "restore"]

class BatchParseRequest(Strict):
    mailbox_id: uuid.UUID | None = None
    email_ids: list[uuid.UUID] | None = None
    include_failed: bool = False
class BatchDeleteDraftsRequest(Strict):
    draft_ids: list[uuid.UUID]

class ClearDraftsRequest(Strict):
    status: str | None = None
