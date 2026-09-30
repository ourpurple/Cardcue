"""Synthetic checks for immutable detail carry-forward on manual corrections."""
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace as Row

import pytest
from fastapi import HTTPException

from cardcue_api.admin.business_api import correct_statement
from cardcue_api.admin.schemas import StatementCorrection
from cardcue_api.persistence import ConfirmedTransaction, StatementVersion


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value


class Session:
    def __init__(self, stmt, version, transactions):
        self.stmt = stmt
        self.version = version
        self.transactions = transactions
        self.added = []
        self.queries = []
        self.committed = False

    async def get(self, model, identity):
        if model is StatementVersion:
            return self.version
        return None  # no existing idempotency receipt

    async def execute(self, query):
        self.queries.append(str(query))
        if len(self.queries) == 1:
            return Result(self.stmt)
        if "FROM detail_sets" in str(query):
            return Result(None)
        return Result(self.transactions)

    def add(self, value):
        self.added.append(value)
        if isinstance(value, StatementVersion):
            value.id = uuid.uuid4()

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True


def make_case(status='complete', transaction_count=1):
    version_id = uuid.uuid4()
    stmt = Row(id=uuid.uuid4(), account_id=uuid.uuid4(), currency='CNY',
               statement_date=date(2026, 1, 1), due_date=date(2026, 2, 1),
               current_version_id=version_id, updated_at=None)
    version = Row(id=version_id, version_number=2, amount_minor=1000,
                  detail_status=status, expected_transaction_count=transaction_count or None,
                  recognized_transaction_count=transaction_count or None,
                  confirmed_transaction_count=transaction_count or None,
                  flagged_transaction_count=0)
    original = [Row(id=uuid.uuid4(), sequence=index + 1,
                    transaction_date=date(2026, 1, 1), posting_date=None,
                    description='synthetic', amount_minor=1000, currency='CNY',
                    card_tail='1234', transaction_type='purchase',
                    source_draft_tx_id=uuid.uuid4(),
                    confirmed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                    confirmed_by='synthetic-reviewer') for index in range(transaction_count)]
    return Session(stmt, version, original)


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize('new_amount,expected_status', [(1000, 'complete'), (1100, 'partial')])
async def test_correction_preserves_rows_without_claiming_changed_total_complete(
    monkeypatch, new_amount, expected_status,
):
    session = make_case()
    changes = []
    async def paid(*args):
        return 200
    async def log(*args):
        changes.append(args[1:4])
    async def audit(*args):
        pass
    monkeypatch.setattr('cardcue_api.admin.business_api.billing_svc._active_paid', paid)
    monkeypatch.setattr('cardcue_api.admin.business_api.billing_svc._log_change', log)
    monkeypatch.setattr('cardcue_api.admin.business_api.audit', audit)
    response = await correct_statement(session.stmt.id,
        StatementCorrection(expected_version_id=session.version.id, request_id=uuid.uuid4(),
                            amount_minor=new_amount, minimum_minor=100, reason='synthetic correction'),
        actor=Row(id='synthetic-admin'), session=session)
    new_ver = next(value for value in session.added if isinstance(value, StatementVersion))
    new_tx = next(value for value in session.added if isinstance(value, ConfirmedTransaction))
    old_tx = session.transactions[0]
    assert new_ver.detail_status == response['detail_status'] == expected_status
    assert new_ver.confirmed_transaction_count == 1
    assert new_ver.expected_transaction_count == 1
    assert new_tx.statement_version_id == new_ver.id
    assert new_tx.statement_id == session.stmt.id
    assert new_tx.source_draft_tx_id == old_tx.source_draft_tx_id
    assert new_tx.amount_minor == old_tx.amount_minor
    assert new_tx.confirmed_at == old_tx.confirmed_at
    assert new_tx.confirmed_by == old_tx.confirmed_by
    assert new_tx is not old_tx
    assert session.stmt.current_version_id == new_ver.id
    assert [entry[0:2] for entry in changes] == [
        ('statement_version', new_ver.id), ('statement', session.stmt.id),
    ]
    assert 'FOR UPDATE' in session.queries[0]
    assert session.committed


@pytest.mark.asyncio(loop_scope="function")
async def test_legacy_version_without_rows_never_becomes_complete(monkeypatch):
    session = make_case(transaction_count=0)
    async def paid(*args):
        return 0
    async def no_op(*args, **kwargs):
        pass
    monkeypatch.setattr('cardcue_api.admin.business_api.billing_svc._active_paid', paid)
    monkeypatch.setattr('cardcue_api.admin.business_api.billing_svc._log_change', no_op)
    monkeypatch.setattr('cardcue_api.admin.business_api.audit', no_op)
    result = await correct_statement(session.stmt.id,
        StatementCorrection(expected_version_id=session.version.id, request_id=uuid.uuid4(),
                            amount_minor=1000, reason='synthetic correction'),
        actor=Row(id='synthetic-admin'), session=session)
    assert result['detail_status'] == 'none'
    assert result['confirmed_transaction_count'] == 0
    assert not any(isinstance(value, ConfirmedTransaction) for value in session.added)


@pytest.mark.asyncio(loop_scope="function")
async def test_stale_correction_cannot_copy_details_or_write():
    session = make_case()
    with pytest.raises(HTTPException) as exc:
        await correct_statement(session.stmt.id,
            StatementCorrection(expected_version_id=uuid.uuid4(), request_id=uuid.uuid4(),
                                amount_minor=1200, reason='synthetic correction'),
            actor=Row(id='synthetic-admin'), session=session)
    assert exc.value.status_code == 409
    assert len(session.queries) == 1
    assert session.added == []
    assert not session.committed


@pytest.mark.asyncio(loop_scope="function")
async def test_legacy_rows_without_coverage_are_not_labeled_none(monkeypatch):
    session = make_case(status='none')
    async def no_op(*args, **kwargs):
        return None
    monkeypatch.setattr('cardcue_api.admin.business_api.billing_svc._log_change', no_op)
    monkeypatch.setattr('cardcue_api.admin.business_api.audit', no_op)
    # An old version might have detail rows but no trustworthy coverage metadata.
    session.version.confirmed_transaction_count = None
    async def zero_paid(*args):
        return 0
    monkeypatch.setattr('cardcue_api.admin.business_api.billing_svc._active_paid', zero_paid)
    result = await correct_statement(session.stmt.id,
        StatementCorrection(expected_version_id=session.version.id, request_id=uuid.uuid4(),
                            amount_minor=1000, reason='synthetic correction'),
        actor=Row(id='synthetic-admin'), session=session)
    assert result['detail_status'] == 'partial'


@pytest.mark.asyncio(loop_scope="function")
async def test_correction_carries_latest_detail_snapshot_not_stale_legacy_rows(monkeypatch):
    session = make_case(status='none')
    session.detail_set = Row(id=uuid.uuid4(), revision=2, detail_status='complete',
                             expected_transaction_count=1, recognized_transaction_count=1,
                             confirmed_transaction_count=1, flagged_transaction_count=0)
    session.transactions[0].description = 'latest reviewed detail'
    async def paid(*args):
        return 0
    async def noop(*args, **kwargs):
        pass
    monkeypatch.setattr('cardcue_api.admin.business_api.billing_svc._active_paid', paid)
    monkeypatch.setattr('cardcue_api.admin.business_api.billing_svc._log_change', noop)
    monkeypatch.setattr('cardcue_api.admin.business_api.audit', noop)
    result = await correct_statement(session.stmt.id,
        StatementCorrection(expected_version_id=session.version.id, request_id=uuid.uuid4(),
                            amount_minor=1200, reason='synthetic correction'),
        actor=Row(id='synthetic-admin'), session=session)
    new_ver = next(value for value in session.added if isinstance(value, StatementVersion))
    new_tx = next(value for value in session.added if isinstance(value, ConfirmedTransaction))
    assert result['detail_status'] == new_ver.detail_status == 'partial'
    assert new_tx.description == 'latest reviewed detail'
    assert new_tx.source_draft_tx_id == session.transactions[0].source_draft_tx_id
    assert session.detail_set.detail_status == 'complete'
