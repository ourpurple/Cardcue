"""Synthetic tests: no real mail, database, payments or model calls."""
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace as Row

import pytest
from fastapi import HTTPException

from cardcue_api.admin.business_api import complete_statement_details, _detail_request_fingerprint
from cardcue_api.admin.models import CommandReceipt
from cardcue_api.admin.schemas import DetailCompletion, StatementCorrection
from cardcue_api.persistence import (
    Account, StatementVersion, DetailSet, DetailSetTransaction,
)


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
        return self.value[0] if self.value else None


class Session:
    def __init__(self, *, old_set=None, old_rows=()):
        self.statement = Row(
            id=uuid.uuid4(), account_id=uuid.uuid4(), currency="CNY",
            statement_date=date(2026, 1, 1), due_date=date(2026, 2, 1),
            current_version_id=uuid.uuid4(), updated_at=None,
        )
        self.version = Row(
            id=self.statement.current_version_id, version_number=1,
            amount_minor=5000, minimum_minor=1000, detail_status="none",
            expected_transaction_count=None, recognized_transaction_count=0,
            confirmed_transaction_count=0, flagged_transaction_count=0,
        )
        self.account = Row(id=self.statement.account_id, status="active", billing_mode="per_card", bank="建行")
        self.card = Row(id=uuid.uuid4(), account_id=self.account.id, tail="1234", status="active")
        self.source_id = uuid.uuid4()
        self.draft = Row(
            id=uuid.uuid4(), status="pending_review", revision=2, matched_account_id=None,
            matched_card_id=None, bank="建行", currency="CNY", statement_date=self.statement.statement_date,
            due_date=self.statement.due_date, amount_minor=5000, card_tails=["1234"],
            email_source_id=self.source_id, source_manifest={"entries": [{"filename": "body"}]},
        )
        self.transaction = Row(
            id=uuid.uuid4(), sequence=1, transaction_date=date(2026, 1, 2), posting_date=None,
            description="synthetic", amount_minor=5000, currency="CNY", card_tail="1234",
            transaction_type="purchase", review_flags=[],
        )
        self.old_set, self.old_rows = old_set, list(old_rows)
        self.existing_sources = [uuid.uuid4()]
        self.added = []
        self.commits = 0
        self.queries = []
        self.receipt = None

    async def get(self, model, key):
        if model is CommandReceipt:
            return self.receipt
        if model is StatementVersion:
            return self.version
        if model is Account:
            return self.account
        raise AssertionError(model)

    async def execute(self, query):
        sql = str(query)
        self.queries.append(sql)
        if "FROM statements" in sql:
            return Result(self.statement)
        if "FROM detail_sets" in sql:
            return Result(self.old_set)
        if "FROM detail_set_transactions" in sql or "FROM confirmed_transactions" in sql:
            return Result(self.old_rows)
        if "FROM statement_drafts" in sql and "JOIN draft_transactions" in sql:
            return Result(self.existing_sources)
        if "FROM statement_drafts" in sql:
            return Result(self.draft)
        if "FROM draft_transactions" in sql:
            return Result([self.transaction])
        if "FROM cards" in sql:
            return Result([self.card])
        raise AssertionError(sql)

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, DetailSet):
            obj.id = uuid.uuid4()

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


def request(session, **overrides):
    params = dict(request_id=uuid.uuid4(), expected_version_id=session.version.id,
                  expected_detail_revision=session.old_set.revision if session.old_set else 0,
                  draft_id=session.draft.id, expected_draft_revision=2,
                  confirm_transaction_ids=[session.transaction.id])
    params.update(overrides)
    return DetailCompletion(**params)


@pytest.mark.asyncio(loop_scope="function")
async def test_complete_details_creates_snapshot_without_new_debt(monkeypatch):
    session = Session()
    async def audit(*args):
        pass
    monkeypatch.setattr("cardcue_api.admin.business_api.audit", audit)
    result = await complete_statement_details(
        session.statement.id, request(session, replace_existing=True, details_complete=True,
                                      expected_transaction_count=1),
        actor=Row(id="test"), session=session,
    )
    detail_set = next(obj for obj in session.added if isinstance(obj, DetailSet))
    line = next(obj for obj in session.added if isinstance(obj, DetailSetTransaction))
    assert detail_set.statement_version_id == session.version.id
    assert detail_set.detail_status == "complete"
    assert line.source_draft_tx_id == session.transaction.id
    assert line.amount_minor == 5000
    assert session.statement.current_version_id == session.version.id
    assert session.version.amount_minor == 5000
    assert result["detail_revision"] == 1
    # The normal confirmation flow locks draft before statement too.
    assert "FROM statement_drafts" in session.queries[0]
    assert "FROM statements" in session.queries[1]
    assert session.draft.status == "confirmed"
    assert session.commits == 1


@pytest.mark.asyncio(loop_scope="function")
async def test_append_copies_previous_snapshot_and_keeps_partial(monkeypatch):
    old = Row(id=uuid.uuid4(), revision=1, detail_status="partial",
              recognized_transaction_count=1, confirmed_transaction_count=1, flagged_transaction_count=0)
    old_row = Row(id=uuid.uuid4(), sequence=1, transaction_date=None, posting_date=None,
                  description="old", amount_minor=2000, currency="CNY", card_tail="1234",
                  transaction_type="purchase", source_draft_tx_id=uuid.uuid4(),
                  confirmed_at=datetime.now(timezone.utc), confirmed_by="test")
    session = Session(old_set=old, old_rows=[old_row])
    async def audit(*args):
        pass
    monkeypatch.setattr("cardcue_api.admin.business_api.audit", audit)
    result = await complete_statement_details(
        session.statement.id, request(session), actor=Row(id="test"), session=session,
    )
    lines = [obj for obj in session.added if isinstance(obj, DetailSetTransaction)]
    assert len(lines) == 2
    assert [line.sequence for line in lines] == [1, 2]
    assert lines[0].source_draft_tx_id == old_row.source_draft_tx_id
    assert lines[1].source_draft_tx_id == session.transaction.id
    assert result["detail_status"] == "partial"
    assert result["detail_revision"] == 2
    assert old.revision == 1  # old metadata and rows are never modified


@pytest.mark.asyncio(loop_scope="function")
async def test_stale_detail_revision_does_not_write():
    session = Session()
    with pytest.raises(HTTPException) as exc:
        await complete_statement_details(
            session.statement.id, request(session, expected_detail_revision=3),
            actor=Row(id="test"), session=session,
        )
    assert exc.value.status_code == 409
    assert not session.added and not session.commits


@pytest.mark.asyncio(loop_scope="function")
async def test_duplicate_selection_does_not_write():
    session = Session()
    with pytest.raises(HTTPException) as exc:
        await complete_statement_details(
            session.statement.id,
            request(session, confirm_transaction_ids=[session.transaction.id] * 2),
            actor=Row(id="test"), session=session,
        )
    assert exc.value.status_code == 409
    assert not session.added


@pytest.mark.asyncio(loop_scope="function")
async def test_idempotent_replay_does_not_lock_or_write():
    session = Session()
    data = request(session)
    session.receipt = Row(fingerprint=_detail_request_fingerprint(session.statement.id, data), result={"ok": True})
    result = await complete_statement_details(
        session.statement.id, data, actor=Row(id="test"), session=session,
    )
    assert result == {"ok": True}
    assert not session.queries and not session.added


@pytest.mark.asyncio(loop_scope="function")
async def test_complete_requires_full_source_proof():
    session = Session()
    session.draft.source_manifest = {"entries": [{"truncated": True}]}
    with pytest.raises(HTTPException) as exc:
        await complete_statement_details(
            session.statement.id,
            request(session, replace_existing=True, details_complete=True,
                    expected_transaction_count=1),
            actor=Row(id="test"), session=session,
        )
    assert exc.value.status_code == 409
    assert not session.added and not session.commits


@pytest.mark.asyncio(loop_scope="function")
async def test_same_email_source_cannot_be_appended_as_duplicate():
    old_row = Row(id=uuid.uuid4(), sequence=1, transaction_date=None, posting_date=None,
                  description="old", amount_minor=2000, currency="CNY", card_tail="1234",
                  transaction_type="purchase", source_draft_tx_id=uuid.uuid4(),
                  confirmed_at=datetime.now(timezone.utc), confirmed_by="test")
    session = Session(old_rows=[old_row])
    session.existing_sources = [session.source_id]
    with pytest.raises(HTTPException) as exc:
        await complete_statement_details(
            session.statement.id, request(session), actor=Row(id="test"), session=session,
        )
    assert exc.value.status_code == 409
    assert not session.added and not session.commits


@pytest.mark.asyncio(loop_scope="function")
async def test_reused_id_with_changed_payload_is_conflict():
    session = Session()
    first = request(session)
    session.receipt = Row(fingerprint=_detail_request_fingerprint(session.statement.id, first), result={"ok": True})
    with pytest.raises(HTTPException) as exc:
        await complete_statement_details(
            session.statement.id, first.model_copy(update={"replace_existing": True}),
            actor=Row(id="test"), session=session,
        )
    assert exc.value.status_code == 409
    assert not session.queries and not session.added


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize("missing_side", ["existing_line", "new_draft", "old_email_lookup", "missing_old_email"])
async def test_append_without_verifiable_provenance_requires_explicit_replace(missing_side):
    old_row = Row(id=uuid.uuid4(), sequence=1, transaction_date=None, posting_date=None,
                  description="old", amount_minor=2000, currency="CNY", card_tail="1234",
                  transaction_type="purchase", source_draft_tx_id=uuid.uuid4(),
                  confirmed_at=datetime.now(timezone.utc), confirmed_by="test")
    session = Session(old_rows=[old_row])
    if missing_side == "existing_line":
        old_row.source_draft_tx_id = None
    elif missing_side == "new_draft":
        session.draft.email_source_id = None
    elif missing_side == "old_email_lookup":
        session.existing_sources = [None]
    else:
        session.existing_sources = []
    with pytest.raises(HTTPException) as exc:
        await complete_statement_details(
            session.statement.id, request(session), actor=Row(id="test"), session=session,
        )
    assert exc.value.status_code == 409
    assert "替换快照" in str(exc.value.detail)
    assert not session.added and not session.commits


@pytest.mark.asyncio(loop_scope="function")
async def test_explicit_replacement_of_untraceable_legacy_rows_retains_old_rows(monkeypatch):
    old_row = Row(id=uuid.uuid4(), sequence=1, transaction_date=None, posting_date=None,
                  description="old", amount_minor=2000, currency="CNY", card_tail="1234",
                  transaction_type="purchase", source_draft_tx_id=None,
                  confirmed_at=datetime.now(timezone.utc), confirmed_by="test")
    session = Session(old_rows=[old_row])
    async def audit(*args):
        pass
    monkeypatch.setattr("cardcue_api.admin.business_api.audit", audit)
    result = await complete_statement_details(
        session.statement.id, request(session, replace_existing=True),
        actor=Row(id="test"), session=session,
    )
    lines = [obj for obj in session.added if isinstance(obj, DetailSetTransaction)]
    assert len(lines) == 1 and lines[0].source_draft_tx_id == session.transaction.id
    assert old_row.source_draft_tx_id is None and old_row.description == "old"
    assert result["detail_status"] == "partial"
    assert session.commits == 1
