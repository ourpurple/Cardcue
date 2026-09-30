"""Synthetic historical ownership inventory tests: no database or user data."""
import uuid
from datetime import date
from types import SimpleNamespace as Row

import pytest

from cardcue_api.services.ownership_preview import build_preview, preview_account_history


def row(**kwargs):
    return Row(**kwargs)


def sample():
    account_id = uuid.uuid4()
    account = row(id=account_id, bank='建行', alias=None, holder='测试人',
                  reference=None, billing_mode='per_card', billing_mode_source='manual_override', revision=4)
    cards = [row(id=uuid.uuid4(), account_id=account_id, tail=tail,
                 display_name=None, status='active', revision=1) for tail in ('1234', '5678')]
    statement = row(id=uuid.uuid4(), account_id=account_id, currency='CNY',
                    statement_date=date(2026, 1, 1), current_version_id=uuid.uuid4())
    version = row(id=statement.current_version_id, statement_id=statement.id, version_number=1)
    payment = row(id=uuid.uuid4(), statement_id=statement.id, revoked_at=None)
    tx = row(id=uuid.uuid4(), statement_id=statement.id, card_tail='1234')
    draft = row(id=uuid.uuid4(), status='pending_review', revision=2,
                matched_account_id=account_id, matched_card_id=cards[0].id)
    return account, cards, statement, version, payment, tx, draft


def test_independent_multicard_never_infers_bill_ownership():
    account, cards, stmt, version, payment, tx, draft = sample()
    result = build_preview(account, cards, [stmt], [version], [payment], [tx], [draft], [])
    assert result['read_only'] is True
    assert result['account']['bank_default_mode_hint'] == 'per_card'
    assert result['statements'][0]['proposed_account_id'] is None
    assert result['statements'][0]['version_ids'] == [str(version.id)]
    assert result['statements'][0]['payment_count'] == 1
    assert result['statements'][0]['confirmed_transaction_count'] == 1
    assert result['counts']['linked_drafts'] == 1
    assert any('不能按尾号自动拆分' in risk for risk in result['risks'])
    assert any('没有可靠的卡片外键' in risk for risk in result['risks'])


def test_duplicate_tail_and_peer_are_not_identity_proof():
    account, cards, stmt, version, payment, tx, draft = sample()
    account.billing_mode = None
    cards[1].tail = cards[0].tail
    peer = row(id=uuid.uuid4())
    result = build_preview(account, cards, [stmt], [version], [payment], [tx], [], [peer])
    assert result['peer_account_ids'] == [str(peer.id)]
    assert any('重复卡尾号' in risk for risk in result['risks'])
    assert any('不自动合并' in risk for risk in result['risks'])
    assert result['statements'][0]['proposed_account_id'] is None


def test_consolidated_bill_preserves_single_account_and_revoked_payment_count():
    account, cards, stmt, version, payment, tx, draft = sample()
    account.billing_mode = 'consolidated'
    payment.revoked_at = 'revoked'
    result = build_preview(account, cards, [stmt], [version], [payment], [tx], [], [])
    assert result['counts']['statements'] == 1
    assert result['statements'][0]['account_id'] == str(account.id)
    assert result['statements'][0]['active_payment_count'] == 0
    assert result['statements'][0]['proposed_account_id'] is None


@pytest.mark.asyncio(loop_scope="function")
async def test_reader_does_not_write_or_commit():
    account, cards, stmt, version, payment, tx, draft = sample()

    class Results:
        def __init__(self, items):
            self.items = items
        def scalars(self):
            return iter(self.items)

    class ReadOnlySession:
        def __init__(self):
            self.results = iter([cards, [stmt], [version], [payment], [tx], [draft], []])
        async def get(self, model, identifier):
            assert identifier == account.id
            return account
        async def execute(self, query):
            return Results(next(self.results))

    result = await preview_account_history(ReadOnlySession(), account.id)
    assert result['counts']['versions'] == 1
    assert result['counts']['payments'] == 1
    assert result['counts']['confirmed_transactions'] == 1
