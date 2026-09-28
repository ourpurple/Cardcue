"""Read-only historical ownership inventory. No bank/holder/tail matching is authoritative."""

from collections import Counter, defaultdict
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cardcue_api.domain.bank_rules import get_default_billing_mode
from cardcue_api.persistence import (
    Account, Card, Statement, StatementVersion, Payment,
    StatementDraftModel, ConfirmedTransaction,
)


def build_preview(account, cards, statements, versions, payments, transactions, drafts, peers):
    """Describe current links and risks; never propose a destination from weak evidence."""
    cards = sorted(cards, key=lambda c: str(c.id))
    statements = sorted(statements, key=lambda s: (s.statement_date, s.currency, str(s.id)))
    versions_by_stmt = defaultdict(list)
    for version in versions:
        versions_by_stmt[version.statement_id].append(version)
    payments_by_stmt = defaultdict(list)
    for payment in payments:
        payments_by_stmt[payment.statement_id].append(payment)
    tx_by_stmt = defaultdict(list)
    for tx in transactions:
        tx_by_stmt[tx.statement_id].append(tx)
    tails = Counter(card.tail for card in cards if card.tail)
    risks = []
    if account.billing_mode is None:
        risks.append('账户还款模式未确认；银行默认模式仅供参考')
    if account.billing_mode == 'per_card' and len(cards) > 1:
        risks.append('独立还款账户含多张卡；现有账单不能按尾号自动拆分')
    if not cards:
        risks.append('账户没有卡片，无法确认卡片归属')
    if any(n > 1 for n in tails.values()):
        risks.append('账户内有重复卡尾号；尾号不能作为卡片身份')
    if peers:
        risks.append('存在同银行同持卡人的其他账户；不自动合并')
    if statements and account.billing_mode == 'per_card':
        risks.append('历史账单只有账户外键，没有可靠的卡片外键；须逐笔人工核对')
    if any(d.matched_card_id and d.matched_card_id not in {c.id for c in cards} for d in drafts):
        risks.append('有草稿所选卡片不属于当前账户，需先核对')

    details = []
    for stmt in statements:
        stmt_versions = versions_by_stmt[stmt.id]
        stmt_payments = payments_by_stmt[stmt.id]
        stmt_tx = tx_by_stmt[stmt.id]
        observed_tails = sorted({tx.card_tail for tx in stmt_tx if tx.card_tail})
        flags = ['账单无可靠卡片外键；明细尾号只是线索，不是归属证明'] if account.billing_mode == 'per_card' else []
        if len(observed_tails) > 1 and account.billing_mode == 'per_card':
            flags.append('明细含多个卡尾号，不可整体自动分配给单卡')
        if stmt.current_version_id and stmt.current_version_id not in {v.id for v in stmt_versions}:
            flags.append('当前版本不属于该账单，需核查数据完整性')
        details.append({
            'id': str(stmt.id), 'account_id': str(stmt.account_id),
            'currency': stmt.currency, 'statement_date': stmt.statement_date.isoformat(),
            'current_version_id': str(stmt.current_version_id) if stmt.current_version_id else None,
            'version_count': len(stmt_versions), 'version_ids': [str(v.id) for v in sorted(stmt_versions, key=lambda v: (v.version_number, str(v.id)))],
            'payment_count': len(stmt_payments),
            'active_payment_count': sum(p.revoked_at is None for p in stmt_payments),
            'confirmed_transaction_count': len(stmt_tx),
            'observed_card_tails': observed_tails,
            'proposed_account_id': None, 'risks': flags,
        })
    return {
        'read_only': True,
        'account': {
            'id': str(account.id), 'bank': account.bank, 'alias': account.alias,
            'holder': account.holder, 'reference': account.reference,
            'billing_mode': account.billing_mode, 'billing_mode_source': account.billing_mode_source,
            'bank_default_mode_hint': get_default_billing_mode(account.bank),
            'revision': account.revision,
        },
        'cards': [{'id': str(c.id), 'account_id': str(c.account_id), 'tail': c.tail,
                   'display_name': c.display_name, 'status': c.status, 'revision': c.revision}
                  for c in cards],
        'peer_account_ids': sorted(str(p.id) for p in peers),
        'statements': details,
        'counts': {'cards': len(cards), 'statements': len(statements),
                   'versions': len(versions), 'payments': len(payments),
                   'confirmed_transactions': len(transactions), 'linked_drafts': len(drafts)},
        'linked_drafts': [{'id': str(d.id), 'status': d.status, 'revision': d.revision,
                           'matched_account_id': str(d.matched_account_id) if d.matched_account_id else None,
                           'matched_card_id': str(d.matched_card_id) if d.matched_card_id else None}
                          for d in sorted(drafts, key=lambda d: str(d.id))],
        'risks': risks,
        'next_step': '逐项核对身份、明确映射并验证备份恢复；当前没有确认或迁移入口',
    }


async def preview_account_history(session: AsyncSession, account_id: UUID):
    account = await session.get(Account, account_id)
    if account is None:
        return None
    cards = list((await session.execute(select(Card).where(Card.account_id == account_id))).scalars())
    statements = list((await session.execute(select(Statement).where(Statement.account_id == account_id))).scalars())
    statement_ids = [s.id for s in statements]
    versions = list((await session.execute(select(StatementVersion).where(StatementVersion.statement_id.in_(statement_ids)))).scalars()) if statement_ids else []
    payments = list((await session.execute(select(Payment).where(Payment.statement_id.in_(statement_ids)))).scalars()) if statement_ids else []
    transactions = list((await session.execute(select(ConfirmedTransaction).where(ConfirmedTransaction.statement_id.in_(statement_ids)))).scalars()) if statement_ids else []
    card_ids = [c.id for c in cards]
    draft_filter = or_(StatementDraftModel.matched_account_id == account_id,
                       StatementDraftModel.matched_card_id.in_(card_ids)) if card_ids else StatementDraftModel.matched_account_id == account_id
    drafts = list((await session.execute(select(StatementDraftModel).where(draft_filter))).scalars())
    peers = list((await session.execute(select(Account).where(
        Account.id != account_id, Account.bank == account.bank, Account.holder == account.holder,
    ))).scalars()) if account.holder and account.holder.strip() else []
    return build_preview(account, cards, statements, versions, payments, transactions, drafts, peers)
