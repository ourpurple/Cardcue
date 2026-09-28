"""Explicit, read-only preflight for historical statement ownership decisions.

This cannot authorize execution: the eventual writer must re-check all invariants
under locks after an independently verified backup. Never derive an account or
card identity from a holder name or tail number.
"""

from collections import Counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cardcue_api.domain.bank_rules import normalise_bank_name
from cardcue_api.persistence import Account, Card, Statement
from cardcue_api.services.ownership_preview import preview_account_history


def validate_mapping(preview, decisions, targets, target_cards, existing_statements):
    """Return reasons rather than a token that could be mistaken for approval."""
    issues = []
    source = preview['account']
    source_statements = {s['id']: s for s in preview['statements']}
    ids = [str(d.statement_id) for d in decisions]
    duplicate_ids = sorted(k for k, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        issues.append('重复提交账单 ID：' + '、'.join(duplicate_ids))
    missing = sorted(set(source_statements) - set(ids))
    unexpected = sorted(set(ids) - set(source_statements))
    if missing:
        issues.append('未明确处理的账单：' + '、'.join(missing))
    if unexpected:
        issues.append('不属于原账户的账单：' + '、'.join(unexpected))

    # The original row remains in the target account until a real writer moves it.
    occupied = {(str(s.account_id), s.currency, s.statement_date.isoformat()): str(s.id)
                for s in existing_statements}
    proposed = set()
    reviewed = []
    for decision in decisions:
        stmt_id = str(decision.statement_id)
        stmt = source_statements.get(stmt_id)
        target_id = str(decision.target_account_id)
        account = targets.get(target_id)
        card_id = str(decision.target_card_id) if decision.target_card_id else None
        errors = []
        if stmt is None:
            continue
        if stmt['current_version_id'] != (str(decision.expected_current_version_id) if decision.expected_current_version_id else None):
            errors.append('当前账单版本已变化')
        # The expected version does not repair a broken historical version chain.
        if stmt['current_version_id'] and stmt['current_version_id'] not in stmt['version_ids']:
            errors.append('当前版本不属于该账单，需先核查数据完整性')
        if stmt['account_id'] != source['id']:
            errors.append('账单原归属与预览账户不一致')
        if account is None:
            errors.append('目标账户不存在')
        else:
            if account.status != 'active':
                errors.append('目标账户不是有效状态，不能接收历史账单')
            if account.revision != decision.target_account_revision:
                errors.append('目标账户修订号已变化')
            if normalise_bank_name(account.bank) != normalise_bank_name(source['bank']):
                errors.append('目标账户银行与原账户不一致')
            if target_id != source['id'] and (not source['holder'] or not account.holder or source['holder'] != account.holder):
                errors.append('跨账户持卡人身份缺失或不一致')
            if account.billing_mode == 'per_card':
                cards = target_cards.get(target_id, [])
                active_cards = [card for card in cards if card.status == 'active']
                if len(active_cards) != 1 or card_id != str(active_cards[0].id):
                    errors.append('独立还款目标必须明确指定该账户唯一的有效卡片 ID')
                if len(stmt['observed_card_tails']) > 1:
                    errors.append('账单明细含多个卡尾号，不可整体映射至独立还款单卡；须人工核对，不能按尾号自动拆分')
            elif account.billing_mode == 'consolidated':
                if card_id is not None:
                    errors.append('合并还款目标只能映射到账户，不指定单卡')
            else:
                errors.append('目标账户还款模式未确认')
            key = (target_id, stmt['currency'], stmt['statement_date'])
            existing_id = occupied.get(key)
            if existing_id and existing_id != stmt_id:
                errors.append('目标账户已有相同币种和账期的账单，不可覆盖或合并')
            if key in proposed:
                errors.append('多个原账单指向同一目标账期，不可合并金额')
            proposed.add(key)
        reviewed.append({
            'statement_id': stmt_id,
            'original_account_id': stmt['account_id'],
            'target_account_id': target_id,
            'target_card_id': card_id,
            'version_count': stmt['version_count'],
            'payment_count': stmt['payment_count'],
            'issues': errors,
        })
        issues.extend(f'{stmt_id}：{error}' for error in errors)
    if not decisions and not source_statements:
        issues.append('该账户没有待整理账单')
    return {
        'read_only': True, 'can_execute': False,
        'valid_mapping': not issues,
        'issues': issues, 'decisions': reviewed,
        'notice': '仅校验明确映射；未执行迁移，未验证备份，也未锁定数据。执行前必须重新核验。',
    }


async def preflight_mapping(session: AsyncSession, account_id: UUID, request):
    preview = await preview_account_history(session, account_id)
    if preview is None:
        return None
    if request.expected_account_revision != preview['account']['revision']:
        from fastapi import HTTPException
        raise HTTPException(409, '原账户已被其他操作修改，请重新预览')
    target_ids = {d.target_account_id for d in request.decisions}
    targets = list((await session.execute(select(Account).where(Account.id.in_(target_ids)))).scalars()) if target_ids else []
    cards = list((await session.execute(select(Card).where(Card.account_id.in_(target_ids)))).scalars()) if target_ids else []
    statements = list((await session.execute(select(Statement).where(Statement.account_id.in_(target_ids)))).scalars()) if target_ids else []
    by_account = {str(a.id): a for a in targets}
    grouped_cards = {str(a.id): [c for c in cards if c.account_id == a.id] for a in targets}
    return validate_mapping(preview, request.decisions, by_account, grouped_cards, statements)
