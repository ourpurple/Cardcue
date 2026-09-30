"""Guard legacy card operations from silently discarding ownership evidence."""
import uuid
from types import SimpleNamespace as R

import pytest
from fastapi import HTTPException

from cardcue_api.admin.business_api import (
    delete_account, delete_card, split_card_to_new_account, update_account, update_card,
)
from cardcue_api.admin.schemas import AccountEdit, CardEdit


class Result:
    def __init__(self, value):
        self.value = value
    def scalar_one_or_none(self):
        return self.value
    def scalar_one(self):
        return self.value
    def first(self):
        return self.value


class GuardSession:
    def __init__(self, results):
        self.results = iter(results)
        self.queries = []
    async def execute(self, query):
        self.queries.append(str(query))
        return Result(next(self.results))
    def add(self, value):
        raise AssertionError('guard should not create or modify rows')
    async def commit(self):
        raise AssertionError('guard should not commit')
    async def delete(self, value):
        raise AssertionError('guard should not delete')


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize('history,draft', [(True, False), (False, True)])
async def test_delete_card_with_evidence_requires_archive(history, draft):
    card = R(id=uuid.uuid4(), account_id=uuid.uuid4())
    session = GuardSession([card, (1,) if history else None, (1,) if draft else None])
    with pytest.raises(HTTPException) as exc:
        await delete_card(card.id, session=session)
    assert exc.value.status_code == 409


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize('history,draft', [(True, False), (False, True)])
async def test_split_card_with_history_or_draft_requires_review(history, draft):
    card = R(id=uuid.uuid4(), account_id=uuid.uuid4(), status='active')
    account = R(id=card.account_id, status='active', billing_mode='per_card', cards=[card, R(status='active')])
    session = GuardSession([card, account, (1,) if history else None, (1,) if draft else None])
    with pytest.raises(HTTPException) as exc:
        await split_card_to_new_account(card.id, session=session)
    assert exc.value.status_code == 409


@pytest.mark.asyncio(loop_scope="function")
async def test_unknown_mode_cannot_use_legacy_split():
    card = R(id=uuid.uuid4(), account_id=uuid.uuid4(), status='active')
    account = R(id=card.account_id, status='active', billing_mode=None, cards=[card, R(status='active')])
    with pytest.raises(HTTPException) as exc:
        await split_card_to_new_account(card.id, session=GuardSession([card, account]))
    assert exc.value.status_code == 409


@pytest.mark.asyncio(loop_scope="function")
async def test_delete_account_with_matched_draft_preserves_evidence():
    account = R(id=uuid.uuid4())
    session = GuardSession([account, 0, (uuid.uuid4(),)])
    with pytest.raises(HTTPException) as exc:
        await delete_account(account.id, session=session)
    assert exc.value.status_code == 409
    assert '草稿' in exc.value.detail
    assert 'matched_account_id' in session.queries[-1]
    assert 'matched_card_id' in session.queries[-1]


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize('change', [
    {'bank': '另一个银行'}, {'holder': '另一持卡人'}, {'reference': '另一个账号'},
    {'billing_mode': 'consolidated'},
])
@pytest.mark.parametrize('evidence', ['statement', 'draft'])
async def test_account_identity_and_mode_change_require_ownership_review(change, evidence):
    acct = R(id=uuid.uuid4(), revision=1, bank='建行', holder='合成用户',
             reference='合成引用', billing_mode='per_card')
    session = GuardSession([acct, (1,) if evidence == 'statement' else None,
                            (1,) if evidence == 'draft' else None])
    with pytest.raises(HTTPException) as exc:
        await update_account(acct.id, AccountEdit(expected_revision=1, **change), session=session)
    assert exc.value.status_code == 409
    assert acct.revision == 1
    assert acct.bank == '建行'


@pytest.mark.asyncio(loop_scope="function")
async def test_reactivating_second_per_card_card_rejected():
    card = R(id=uuid.uuid4(), account_id=uuid.uuid4(), revision=2,
             tail='1234', status='archived', display_name='合成卡')
    account = R(id=card.account_id, billing_mode='per_card')
    session = GuardSession([card, account, (uuid.uuid4(),)])
    with pytest.raises(HTTPException) as exc:
        await update_card(card.id, CardEdit(expected_revision=2, status='active'), session=session)
    assert exc.value.status_code == 409
    assert card.status == 'archived'
    assert card.revision == 2


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize('evidence', ['statement', 'draft'])
async def test_tail_change_with_evidence_rejected(evidence):
    card = R(id=uuid.uuid4(), account_id=uuid.uuid4(), revision=1,
             tail='1234', status='active', display_name='合成卡')
    session = GuardSession([card, (1,) if evidence == 'statement' else None,
                            (1,) if evidence == 'draft' else None])
    with pytest.raises(HTTPException) as exc:
        await update_card(card.id, CardEdit(expected_revision=1, tail='5678'), session=session)
    assert exc.value.status_code == 409
    assert card.tail == '1234'


@pytest.mark.asyncio(loop_scope="function")
async def test_split_archived_card_does_not_create_active_account():
    card = R(id=uuid.uuid4(), account_id=uuid.uuid4(), status='archived')
    account = R(id=card.account_id, status='active', billing_mode='per_card',
                cards=[card, R(status='active'), R(status='active')])
    with pytest.raises(HTTPException) as exc:
        await split_card_to_new_account(card.id, session=GuardSession([card, account]))
    assert exc.value.status_code == 409


@pytest.mark.asyncio(loop_scope="function")
async def test_delete_card_with_account_matched_draft_rejected():
    card = R(id=uuid.uuid4(), account_id=uuid.uuid4())
    with pytest.raises(HTTPException) as exc:
        await delete_card(card.id, session=GuardSession([card, None, (uuid.uuid4(),)]))
    assert exc.value.status_code == 409


@pytest.mark.asyncio(loop_scope="function")
async def test_single_card_reactivation_still_allowed(monkeypatch):
    card = R(id=uuid.uuid4(), account_id=uuid.uuid4(), revision=1,
             tail='1234', status='archived', display_name='old')
    account = R(id=card.account_id, billing_mode='per_card')
    session = GuardSession([card, account, None])
    async def no_op(*args, **kwargs):
        return None
    monkeypatch.setattr('cardcue_api.admin.business_api.billing_svc._log_change', no_op)
    monkeypatch.setattr('cardcue_api.admin.business_api.audit', no_op)
    session.commit = no_op
    response = await update_card(card.id, CardEdit(expected_revision=1,
                                  display_name='new', status='active'),
                                 actor='synthetic-admin', session=session)
    assert response['status'] == 'active'
    assert response['revision'] == 2
    assert card.display_name == 'new'


@pytest.mark.asyncio(loop_scope="function")
async def test_noop_tail_edit_does_not_require_history_review(monkeypatch):
    card = R(id=uuid.uuid4(), account_id=uuid.uuid4(), revision=1,
             tail='1234', status='active', display_name='old')
    session = GuardSession([card])
    async def no_op(*args, **kwargs):
        return None
    monkeypatch.setattr('cardcue_api.admin.business_api.billing_svc._log_change', no_op)
    monkeypatch.setattr('cardcue_api.admin.business_api.audit', no_op)
    session.commit = no_op
    response = await update_card(card.id, CardEdit(expected_revision=1, tail='1234',
                                 display_name='new'), actor='synthetic-admin', session=session)
    assert response['tail'] == '1234'
    assert len(session.queries) == 1


@pytest.mark.asyncio(loop_scope="function")
async def test_safe_legacy_split_advances_membership_revisions(monkeypatch):
    card = R(id=uuid.uuid4(), account_id=uuid.uuid4(), revision=3,
             status='active', tail='1234')
    account = R(id=card.account_id, bank='CCB', holder='synthetic',
                billing_mode='per_card', billing_mode_source='bank_default',
                status='active', cards=[card, R(status='active')], revision=2)
    session = GuardSession([card, account, None, None])
    created = []
    async def no_op(*args, **kwargs):
        return None
    def add(obj):
        obj.id = uuid.uuid4()
        created.append(obj)
    session.add = add
    session.flush = no_op
    session.commit = no_op
    monkeypatch.setattr('cardcue_api.admin.business_api.billing_svc._log_change', no_op)
    monkeypatch.setattr('cardcue_api.admin.business_api.audit', no_op)
    result = await split_card_to_new_account(card.id, actor='synthetic-admin', session=session)
    assert result['success'] is True
    assert card.account_id == created[0].id
    assert card.revision == 4
    assert account.revision == 3


@pytest.mark.asyncio(loop_scope="function")
async def test_create_card_checks_account_under_lock_before_active_count():
    from cardcue_api.services.billing import BillingService, ConflictError
    from cardcue_api.domain.schemas import CardCreate
    account = R(id=uuid.uuid4(), billing_mode='per_card')
    session = GuardSession([account, (uuid.uuid4(),)])
    with pytest.raises(ConflictError):
        await BillingService().create_card(session, CardCreate(account_id=account.id, tail='1234'))
    assert 'FOR UPDATE' in session.queries[0]
    assert 'cards.status' in session.queries[1]
