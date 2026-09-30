"""Synthetic preflight tests; no account, statement or payment is changed."""
import uuid
from datetime import date
from types import SimpleNamespace as R

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from cardcue_api.admin.schemas import HistoricalOwnershipDecision as Decision
from cardcue_api.admin.schemas import HistoricalOwnershipPreflight as Request
from cardcue_api.services.ownership_mapping import validate_mapping, preflight_mapping


def fixtures():
    source, target, card, stmt, version = [uuid.uuid4() for _ in range(5)]
    preview = {
        'account': {'id': str(source), 'bank': '建行', 'holder': '合成用户', 'revision': 2},
        'statements': [{'id': str(stmt), 'account_id': str(source), 'currency': 'CNY',
                        'statement_date': '2026-01-01', 'current_version_id': str(version),
                        'version_count': 2, 'version_ids': [str(version)], 'payment_count': 1,
                        'observed_card_tails': [], 'risks': []}],
    }
    account = R(id=target, bank='中国建设银行', holder='合成用户', revision=3, status='active', billing_mode='per_card')
    destination_card = R(id=card, account_id=target, status='active')
    decision = Decision(statement_id=stmt, expected_current_version_id=version,
                        target_account_id=target, target_account_revision=3, target_card_id=card)
    return preview, account, destination_card, decision


def test_explicit_one_card_mapping_preflight_is_still_not_executable():
    preview, account, card, decision = fixtures()
    result = validate_mapping(preview, [decision], {str(account.id): account}, {str(account.id): [card]}, [])
    assert result['valid_mapping'] is True
    assert result['can_execute'] is False
    assert result['decisions'][0]['version_count'] == 2
    assert result['decisions'][0]['payment_count'] == 1
    assert result['decisions'][0]['target_card_id'] == str(card.id)


def test_missing_duplicate_and_foreign_statement_are_not_silently_accepted():
    preview, account, card, decision = fixtures()
    other = decision.model_copy(update={'statement_id': uuid.uuid4()})
    target = {str(account.id): account}
    cards = {str(account.id): [card]}
    assert '未明确处理的账单' in ''.join(validate_mapping(preview, [], target, cards, [])['issues'])
    assert '重复提交账单' in ''.join(validate_mapping(preview, [decision, decision], target, cards, [])['issues'])
    assert '不属于原账户的账单' in ''.join(validate_mapping(preview, [other], target, cards, [])['issues'])


def test_stale_version_revision_or_bank_holder_mismatch_fail():
    preview, account, card, decision = fixtures()
    target = {str(account.id): account}
    cards = {str(account.id): [card]}
    stale = decision.model_copy(update={'expected_current_version_id': uuid.uuid4(), 'target_account_revision': 1})
    issues = validate_mapping(preview, [stale], target, cards, [])['issues']
    assert any('版本已变化' in x for x in issues)
    assert any('修订号已变化' in x for x in issues)
    account.bank = '招行'
    account.holder = '另一用户'
    issues = validate_mapping(preview, [decision], target, cards, [])['issues']
    assert any('银行与原账户不一致' in x for x in issues)
    assert any('身份缺失或不一致' in x for x in issues)


def test_card_identity_mode_and_existing_period_collision():
    preview, account, card, decision = fixtures()
    key = str(account.id)
    another_card = R(id=uuid.uuid4(), account_id=account.id, status='active')
    occupied = R(id=uuid.uuid4(), account_id=account.id, currency='CNY', statement_date=date(2026, 1, 1))
    issues = validate_mapping(preview, [decision], {key: account}, {key: [card, another_card]}, [occupied])['issues']
    assert any('唯一的有效卡片 ID' in x for x in issues)
    assert any('已有相同币种和账期' in x for x in issues)
    account.billing_mode = 'consolidated'
    issues = validate_mapping(preview, [decision], {key: account}, {key: [card]}, [])['issues']
    assert any('只能映射到账户' in x for x in issues)
    assert validate_mapping(preview, [decision.model_copy(update={'target_card_id': None})], {key: account}, {key: [card]}, [])['valid_mapping']


def test_invalid_input_is_rejected_before_preflight():
    preview, account, card, decision = fixtures()
    with pytest.raises(ValidationError):
        Request(expected_account_revision=0, decisions=[decision])
    with pytest.raises(ValidationError):
        Decision(statement_id=decision.statement_id, expected_current_version_id=decision.expected_current_version_id,
                 target_account_id=account.id, target_account_revision=3, extra='untrusted')


@pytest.mark.asyncio(loop_scope="function")
async def test_stale_source_revision_rejected_without_issuing_mapping_queries(monkeypatch):
    preview, account, card, decision = fixtures()
    async def mock_preview(session, account_id):
        return preview
    monkeypatch.setattr('cardcue_api.services.ownership_mapping.preview_account_history', mock_preview)
    class NoQueries:
        async def execute(self, query):
            raise AssertionError('stale input should not run target queries')
    with pytest.raises(HTTPException) as exc:
        await preflight_mapping(NoQueries(), uuid.UUID(preview['account']['id']),
                                Request(expected_account_revision=1, decisions=[decision]))
    assert exc.value.status_code == 409


def test_archived_destination_account_and_card_are_rejected():
    preview, account, card, decision = fixtures()
    targets = {str(account.id): account}
    cards = {str(account.id): [card]}
    account.status = 'archived'
    result = validate_mapping(preview, [decision], targets, cards, [])
    assert not result['valid_mapping'] and not result['can_execute']
    assert any('目标账户不是有效状态' in issue for issue in result['issues'])
    account.status = 'active'
    card.status = 'archived'
    result = validate_mapping(preview, [decision], targets, cards, [])
    assert not result['valid_mapping']
    assert any('唯一的有效卡片 ID' in issue for issue in result['issues'])


def test_archived_sibling_does_not_disqualify_single_active_card():
    preview, account, card, decision = fixtures()
    archived = R(id=uuid.uuid4(), account_id=account.id, status='archived')
    result = validate_mapping(preview, [decision], {str(account.id): account},
                              {str(account.id): [card, archived]}, [])
    assert result['valid_mapping'] and not result['can_execute']
    stale_card = decision.model_copy(update={'target_card_id': archived.id})
    result = validate_mapping(preview, [stale_card], {str(account.id): account},
                              {str(account.id): [card, archived]}, [])
    assert not result['valid_mapping']


def test_multiple_observed_tails_block_whole_bill_to_one_card_not_to_consolidated_account():
    preview, account, card, decision = fixtures()
    preview['statements'][0]['observed_card_tails'] = ['1234', '5678']
    result = validate_mapping(preview, [decision], {str(account.id): account},
                              {str(account.id): [card]}, [])
    assert not result['valid_mapping'] and not result['can_execute']
    assert any('不可整体映射至独立还款单卡' in issue for issue in result['issues'])
    account.billing_mode = 'consolidated'
    account_result = validate_mapping(preview, [decision.model_copy(update={'target_card_id': None})],
                                      {str(account.id): account}, {str(account.id): [card]}, [])
    assert account_result['valid_mapping'] and not account_result['can_execute']


def test_broken_version_chain_blocks_but_ordinary_preview_warning_is_advisory():
    preview, account, card, decision = fixtures()
    preview['statements'][0]['risks'] = ['账单无可靠卡片外键；须人工核对']
    targets = {str(account.id): account}
    cards = {str(account.id): [card]}
    assert validate_mapping(preview, [decision], targets, cards, [])['valid_mapping']
    preview['statements'][0]['version_ids'] = [str(uuid.uuid4())]
    result = validate_mapping(preview, [decision], targets, cards, [])
    assert not result['valid_mapping']
    assert any('当前版本不属于该账单' in issue for issue in result['issues'])
    preview['statements'][0]['account_id'] = str(uuid.uuid4())
    result = validate_mapping(preview, [decision], targets, cards, [])
    assert any('账单原归属与预览账户不一致' in issue for issue in result['issues'])