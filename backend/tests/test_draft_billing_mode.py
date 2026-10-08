"""Synthetic mode-confirmation regression tests: no user database or mail."""
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace as Row

import pytest
from pydantic import ValidationError

from cardcue_api.domain.schemas import StatementDraftConfirmRequest as Request
from cardcue_api.persistence import Statement, StatementVersion, ChangeLog
from cardcue_api.services.billing import ConflictError
from cardcue_api.services.drafts import DraftService
from cardcue_api.admin.business_api import get_draft_detail


class Result:
    def __init__(self, value):
        self.value = value
    def scalar_one_or_none(self):
        return self.value
    def scalars(self):
        return self
    def all(self):
        return self.value
    def first(self):
        return self.value


class Session:
    def __init__(self, mode=None, card_count=1, history=False):
        self.account = Row(id=uuid.uuid4(), bank="广发银行", holder="合成用户",
                           alias=None, reference=None, status="active", billing_mode=mode,
                           billing_mode_source=None, revision=3, updated_at=None)
        self.cards = [Row(id=uuid.uuid4(), account_id=self.account.id, tail=f"{i+1000}",
                          display_name=None, status="active") for i in range(card_count)]
        self.account.cards = self.cards
        self.draft = Row(id=uuid.uuid4(), status="pending_review", revision=2,
                         bank="广发银行", currency="CNY", amount_minor=2317, minimum_minor=2317,
                         statement_date=date(2026, 10, 6), due_date=date(2026, 10, 26),
                         card_tails=["1000"], source_manifest=None, matched_account_id=None,
                         matched_card_id=None, email_source_id=None, account_reference=None,
                         evidence=[], detail_status="none", review_reasons=[],
                         confirmed_version_id=None, rejection_reason=None, extractor_name="model",
                         created_at=datetime.now(timezone.utc), updated_at=None)
        self.history = history
        self.added = []
        self.queries = []
        self.receipt = None
    async def execute(self, query):
        sql = str(query)
        self.queries.append(sql)
        if "FROM statement_drafts" in sql:
            return Result(self.draft)
        if "FROM accounts" in sql:
            return Result(self.account if "FOR UPDATE" in sql else [self.account])
        if "FROM cards" in sql:
            return Result(self.cards)
        if "FROM draft_transactions" in sql:
            return Result([])
        if "FROM statements" in sql:
            return Result((uuid.uuid4(),) if self.history else None)
        raise AssertionError(sql)
    async def get(self, model, key):
        if model.__name__ == "CommandReceipt":
            return self.receipt
        if model.__name__ == "StatementDraftModel":
            return self.draft
        raise AssertionError(model)
    def add(self, row):
        self.added.append(row)
    async def flush(self):
        for row in self.added:
            if getattr(row, "id", None) is None:
                row.id = uuid.uuid4()
    async def refresh(self, row):
        pass
    async def commit(self):
        raise AssertionError("Service must leave the mode and statement in the caller's transaction")


def request(session, **overrides):
    values = dict(account_id=session.account.id, request_id=uuid.uuid4(), expected_revision=2,
                  confirmed_billing_mode="per_card", expected_account_revision=3)
    values.update(overrides)
    return Request(**values)


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize("mode,card_count", [("per_card", 1), ("consolidated", 2)])
async def test_manual_mode_and_statement_are_written_together(mode, card_count):
    session = Session(card_count=card_count)
    stmt, ver, draft = await DraftService().confirm_draft(
        session, session.draft.id, request(session, confirmed_billing_mode=mode), "synthetic-admin")
    assert session.account.billing_mode == mode
    assert session.account.billing_mode_source == "manual_override"
    assert session.account.revision == 4
    assert draft.status == "confirmed" and draft.revision == 3
    assert draft.matched_account_id == session.account.id
    if mode == "per_card":
        assert draft.matched_card_id == session.cards[0].id
    assert stmt.account_id == session.account.id and ver.amount_minor == 2317
    assert len([r for r in session.added if isinstance(r, Statement)]) == 1
    assert len([r for r in session.added if isinstance(r, StatementVersion)]) == 1
    account_logs = [r for r in session.added if isinstance(r, ChangeLog) and r.entity_type == "account"]
    assert len(account_logs) == 1
    assert account_logs[0].snapshot["billing_mode"] == mode
    assert account_logs[0].snapshot["billing_mode_source"] == "manual_override"
    assert "FOR UPDATE" in session.queries[1]
    with pytest.raises(ConflictError, match="already confirmed"):
        await DraftService().confirm_draft(session, draft.id, request(session))
    assert len([r for r in session.added if isinstance(r, Statement)]) == 1


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize("overrides,message", [
    ({"confirmed_billing_mode": None}, "人工确认"),
    ({"expected_account_revision": None}, "人工确认"),
    ({"expected_account_revision": 2}, "其他操作"),
    ({"expected_revision": 1}, "Draft changed"),
])
async def test_unknown_mode_missing_confirmation_or_stale_revision_preserves_data(overrides, message):
    session = Session()
    with pytest.raises(ConflictError, match=message):
        await DraftService().confirm_draft(session, session.draft.id, request(session, **overrides))
    assert session.account.billing_mode is None and session.account.revision == 3
    assert session.draft.status == "pending_review"
    assert not session.added


@pytest.mark.asyncio(loop_scope="function")
async def test_unknown_mode_with_existing_history_must_not_be_reinterpreted():
    session = Session(history=True)
    with pytest.raises(ConflictError, match="历史归属"):
        await DraftService().confirm_draft(session, session.draft.id, request(session))
    assert session.account.billing_mode is None and not session.added


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize("mode", ["per_card", "consolidated"])
async def test_existing_mode_stays_unchanged_and_legacy_request_remains_supported(mode):
    session = Session(mode=mode)
    await DraftService().confirm_draft(session, session.draft.id,
                                     request(session, confirmed_billing_mode=None, expected_account_revision=None))
    assert session.account.billing_mode == mode and session.account.revision == 3
    assert not [r for r in session.added if isinstance(r, ChangeLog) and r.entity_type == "account"]


@pytest.mark.asyncio(loop_scope="function")
async def test_confirmed_mode_cannot_be_changed_through_draft():
    session = Session(mode="consolidated")
    with pytest.raises(ConflictError, match="更改已确认模式"):
        await DraftService().confirm_draft(session, session.draft.id, request(session))
    assert session.account.billing_mode == "consolidated" and not session.added


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize("card_count", [0, 2])
async def test_per_card_mode_requires_exactly_one_active_card(card_count):
    session = Session(card_count=card_count)
    with pytest.raises(ConflictError, match="exactly one active card"):
        await DraftService().confirm_draft(session, session.draft.id, request(session))
    assert session.account.billing_mode is None and not session.added


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize("case,message", [
    ("bank", "bank conflicts"), ("tail", "tail conflicts"),
    ("multi_tail", "Multi-card"), ("foreign_card", "does not belong"),
    ("transactions", "does not belong"), ("complete", "remain unconfirmed"),
    ("archived", "Active repayment"),
])
async def test_failed_bill_validation_does_not_persist_reviewed_mode(case, message):
    session = Session()
    overrides = {}
    if case == "bank": session.draft.bank = "建设银行"
    if case == "tail": session.draft.card_tails = ["9999"]
    if case == "multi_tail": session.draft.card_tails = ["1000", "9999"]
    if case == "foreign_card": overrides["card_id"] = uuid.uuid4()
    if case == "transactions": overrides["confirm_transaction_ids"] = [uuid.uuid4()]
    if case == "complete": overrides["details_complete"] = True
    if case == "archived": session.account.status = "archived"
    with pytest.raises(ConflictError, match=message):
        await DraftService().confirm_draft(session, session.draft.id, request(session, **overrides))
    assert session.account.billing_mode is None and session.account.revision == 3
    assert session.draft.status == "pending_review" and not session.added


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize("mode", [None, "per_card", "consolidated"])
async def test_candidate_contract_exposes_mode_and_revision_for_manual_review(mode):
    session = Session(mode=mode)
    detail = await get_draft_detail(session.draft.id, session=session)
    candidate = detail["candidate_accounts"][0]
    assert candidate["billing_mode"] == mode
    assert candidate["billing_mode_source"] is None
    assert candidate["revision"] == 3


@pytest.mark.parametrize("overrides", [
    {"confirmed_billing_mode": "auto"}, {"expected_account_revision": 0},
    {"expected_account_revision": 3.0}, {"expected_account_revision": True},
])
def test_untrusted_confirmation_fields_are_rejected(overrides):
    with pytest.raises(ValidationError):
        request(Session(), **overrides)


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize("mode", ["per_card", "consolidated"])
async def test_known_mode_stale_account_revision_blocks_confirmation(mode):
    session = Session(mode=mode)
    with pytest.raises(ConflictError, match="其他操作"):
        await DraftService().confirm_draft(session, session.draft.id,
            request(session, confirmed_billing_mode=None, expected_account_revision=2))
    assert session.account.billing_mode == mode and session.account.revision == 3
    assert session.draft.status == "pending_review" and not session.added
