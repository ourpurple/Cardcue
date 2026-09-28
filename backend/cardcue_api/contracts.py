"""Parsing contract models for CardCue V2.

Null means missing evidence, never zero. Validation is required before a parsed draft
can become a confirmed local bill. CNY/USD are the first supported currencies.

V2 additions:
- TransactionItem: per-transaction detail from model extraction
- SourceManifest / SourceEntry: tracks what content was submitted to the model
- StatementDraft extended with transactions and source_manifest
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    field: Literal[
        "bank", "account_reference", "card_tails", "currency",
        "amount_minor", "minimum_minor", "statement_date", "due_date",
        "transaction",  # V2: evidence for a transaction row
    ]
    excerpt: str = Field(min_length=1, max_length=1000)


# ---------------------------------------------------------------------------
# Transaction item (V2)
# ---------------------------------------------------------------------------

class TransactionItem(BaseModel):
    """A single transaction extracted by the model."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sequence: int = Field(ge=1, description="1-based order within the statement")
    transaction_date: date | None = None
    posting_date: date | None = None
    description: str | None = Field(default=None, max_length=500)
    amount_minor: int | None = Field(default=None, description="Positive=debit, negative=credit/refund; integer minor units")
    currency: Literal["CNY", "USD"] | None = None
    card_tail: str | None = Field(default=None, min_length=4, max_length=4)
    transaction_type: str | None = Field(default=None, max_length=20,
        description="消费/退款/利息/费用/取现/还款 etc.")
    evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    review_flags: list[str] = Field(default_factory=list, max_length=10)


# ---------------------------------------------------------------------------
# Source manifest (V2): what was submitted to the model
# ---------------------------------------------------------------------------

class SourceEntry(BaseModel):
    """One piece of content submitted to the model."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["html_body", "text_body", "pdf_file", "image_file", "other_file"]
    filename: str | None = None
    char_count: int = Field(ge=0)
    truncated: bool = False
    content_hash: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=200)


class SourceManifest(BaseModel):
    """Tracks all content pieces assembled for a single model invocation."""
    model_config = ConfigDict(extra="forbid")

    entries: list[SourceEntry] = Field(default_factory=list, max_length=20)
    total_chars: int = Field(ge=0, default=0)
    has_unsupported: bool = False
    unsupported_files: list[str] = Field(default_factory=list, max_length=10)


# ---------------------------------------------------------------------------
# Statement draft
# ---------------------------------------------------------------------------

class StatementDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    bank: str | None = Field(default=None, min_length=1, max_length=100)
    account_reference: str | None = Field(default=None, max_length=100)
    card_tails: list[str] = Field(default_factory=list, max_length=30)
    currency: Literal["CNY", "USD"] | None = None
    amount_minor: int | None = Field(default=None, ge=0, le=999999999999)
    minimum_minor: int | None = Field(default=None, ge=0, le=999999999999)
    statement_date: date | None = None
    due_date: date | None = None
    evidence: list[Evidence] = Field(default_factory=list, max_length=100)
    review_reasons: list[str] = Field(default_factory=list, max_length=30)

    # V2 additions
    transactions: list[TransactionItem] = Field(default_factory=list, max_length=10000)
    source_manifest: SourceManifest | None = None

    @model_validator(mode="after")
    def review(self) -> "StatementDraft":
        reasons = list(self.review_reasons)
        evidence_fields = {item.field for item in self.evidence}
        for field in ("bank", "currency", "amount_minor", "statement_date", "due_date"):
            if getattr(self, field) is None:
                reasons.append(f"missing:{field}")
            elif field not in evidence_fields:
                reasons.append(f"no_evidence:{field}")
        if not self.account_reference and not self.card_tails:
            reasons.append("unresolved:account")
        if self.account_reference and "account_reference" not in evidence_fields:
            reasons.append("no_evidence:account_reference")
        if self.card_tails and "card_tails" not in evidence_fields:
            reasons.append("no_evidence:card_tails")
        if any(len(tail) != 4 or not tail.isascii() or not tail.isdigit() for tail in self.card_tails):
            reasons.append("invalid:card_tails")
        if self.minimum_minor is not None and self.amount_minor is not None and self.minimum_minor > self.amount_minor:
            reasons.append("conflict:minimum_exceeds_total")
        if self.statement_date and self.due_date and self.due_date < self.statement_date:
            reasons.append("conflict:due_before_statement")
        # Statement balance includes previous balances, fees and repayments;
        # it is not necessarily equal to the sum of this period's transactions.
        if any(t.amount_minor is None for t in self.transactions):
            reasons.append("partial:transaction_amounts")
        self.review_reasons = list(dict.fromkeys(reasons))
        return self

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)
