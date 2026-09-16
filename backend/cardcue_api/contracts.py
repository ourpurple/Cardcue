"""Proposed boundary for phase-two parsing; these models are not an active parse API.

Null means missing evidence, never zero. Validation is required before a parsed draft
can become a confirmed local bill. CNY/USD are the first supported currencies.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    field: Literal["bank", "account_reference", "card_tails", "currency", "amount_minor", "minimum_minor", "statement_date", "due_date"]
    excerpt: str = Field(min_length=1, max_length=1000)


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
        self.review_reasons = list(dict.fromkeys(reasons))
        return self

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)
