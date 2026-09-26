"""Web Administration Business API.

Covers:
- Overview dashboard (/v1/admin/overview)
- Accounts & Cards management (/v1/admin/accounts, /v1/admin/cards)
- Statements & Payments (/v1/admin/statements, /v1/admin/payments)
- Email Center (/v1/admin/emails, /v1/admin/attachments)
- Draft Review (/v1/admin/drafts)
- Devices (/v1/admin/devices)
- Audit logs (/v1/admin/audit)
- System Status (/v1/admin/status)
"""

import os
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cardcue_api.admin.models import (
    AdminJob,
    AuditEvent,
    CommandReceipt,
    ModelProfile,
    ModelRevision,
    RuntimeSettings,
)
from cardcue_api.admin.jobs import enqueue
from cardcue_api.admin.schemas import (
    AccountEdit,
    BatchDeleteDraftsRequest,
    BatchParseRequest,
    CardEdit,
    ClearDraftsRequest,
    DraftEdit,
    JobCreate,
    SourceAction,
    StatementCorrection,
)
from cardcue_api.admin.security import audit, now, recent_admin, require_admin
from cardcue_api.config import settings
from cardcue_api.domain.schemas import (
    AccountCreate,
    CardCreate,
    PaymentCreate,
    RevokeRequest,
    StatementDraftConfirmRequest,
    StatementDraftRejectRequest,
)
from cardcue_api.mail.parser import MailMimeParser
from cardcue_api.mail.storage import MailStorageManager
from cardcue_api.persistence import (
    Account,
    Card,
    ChangeLog,
    EmailAttachment,
    EmailSource,
    Mailbox,
    Payment,
    Statement,
    StatementDraftModel,
    StatementVersion,
)
from cardcue_api.persistence.database import get_session
from cardcue_api.services.auth import DeviceService
from cardcue_api.services.billing import BillingService, ConflictError, NotFoundError
from cardcue_api.services.drafts import DraftService

router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])
billing_svc = BillingService()
draft_svc = DraftService()
device_svc = DeviceService()
storage_mgr = MailStorageManager()
mime_parser = MailMimeParser()

# ---------------------------------------------------------------------------
# 1. Overview Dashboard
# ---------------------------------------------------------------------------

@router.get("/overview")
async def get_overview(session: AsyncSession = Depends(get_session)):
    today = date.today()

    # Statements & Currencies summary
    stmt_rows = list((await session.execute(
        select(Statement).options(
            selectinload(Statement.versions),
            selectinload(Statement.payments),
        )
    )).scalars().all())

    curr_stats = {}
    upcoming_7d = 0

    for s in stmt_rows:
        cur_ver = None
        for v in s.versions:
            if v.id == s.current_version_id:
                cur_ver = v
                break
        total_amount = cur_ver.amount_minor if cur_ver else 0
        total_paid = sum(p.amount_minor for p in s.payments if p.revoked_at is None)
        remaining = max(0, total_amount - total_paid)

        if s.currency not in curr_stats:
            curr_stats[s.currency] = {
                "currency": s.currency,
                "unpaid_minor": 0,
                "statement_count": 0,
            }
        curr_stats[s.currency]["statement_count"] += 1
        curr_stats[s.currency]["unpaid_minor"] += remaining

        if remaining > 0 and today <= s.due_date <= today + timedelta(days=7):
            upcoming_7d += 1

    # Pending drafts
    pending_drafts = (await session.execute(
        select(func.count()).select_from(StatementDraftModel).where(StatementDraftModel.status == "pending_review")
    )).scalar_one()

    # Job stats
    failed_jobs_24h = (await session.execute(
        select(func.count()).select_from(AdminJob).where(
            AdminJob.status == "failed",
            AdminJob.finished_at >= now() - timedelta(hours=24),
        )
    )).scalar_one()

    active_jobs = (await session.execute(
        select(func.count()).select_from(AdminJob).where(
            AdminJob.status.in_(["queued", "running"])
        )
    )).scalar_one()

    # Last sync time
    last_checked = (await session.execute(
        select(func.max(Mailbox.last_checked_at))
    )).scalar_one_or_none()
    last_email = (await session.execute(
        select(func.max(EmailSource.created_at))
    )).scalar_one_or_none()
    candidates = [t for t in (last_checked, last_email) if t is not None]
    last_sync_time = max(candidates) if candidates else None

    # Total accounts & cards
    total_accounts = (await session.execute(
        select(func.count()).select_from(Account).where(Account.status == "active")
    )).scalar_one()
    total_cards = (await session.execute(
        select(func.count()).select_from(Card).where(Card.status == "active")
    )).scalar_one()

    # Active model
    runtime_model = await session.get(RuntimeSettings, "model")
    active_model_info = None
    if runtime_model and runtime_model.value.get("revision_id"):
        rev_id = uuid.UUID(str(runtime_model.value["revision_id"]))
        rev_row = (await session.execute(
            select(ModelRevision, ModelProfile.name)
            .join(ModelProfile, ModelRevision.profile_id == ModelProfile.id)
            .where(ModelRevision.id == rev_id)
        )).first()
        if rev_row:
            rev_obj, prof_name = rev_row
            params = rev_obj.parameters or {}
            active_model_info = {
                "profile_name": prof_name,
                "model": params.get("model", ""),
                "revision": rev_obj.number,
                "base_url": params.get("base_url", ""),
            }

    return {
        "currencies_summary": list(curr_stats.values()),
        "upcoming_7d_count": upcoming_7d,
        "pending_drafts_count": pending_drafts,
        "failed_jobs_24h_count": failed_jobs_24h,
        "active_jobs_count": active_jobs,
        "last_sync_time": last_sync_time,
        "total_accounts": total_accounts,
        "total_cards": total_cards,
        "active_model": active_model_info,
    }


# ---------------------------------------------------------------------------
# 2. Accounts & Cards
# ---------------------------------------------------------------------------

@router.get("/accounts")
async def list_accounts(session: AsyncSession = Depends(get_session)):
    accounts = list((await session.execute(
        select(Account).options(selectinload(Account.cards)).order_by(Account.created_at.desc())
    )).scalars().all())

    return [{
        "id": str(a.id),
        "bank": a.bank,
        "alias": a.alias,
        "holder": a.holder,
        "reference": a.reference,
        "status": a.status,
        "revision": a.revision,
        "cards_count": len(a.cards),
        "cards": [{
            "id": str(c.id),
            "account_id": str(c.account_id),
            "tail": c.tail,
            "display_name": c.display_name,
            "status": c.status,
            "revision": c.revision,
            "created_at": c.created_at,
        } for c in a.cards],
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    } for a in accounts]


@router.post("/accounts", status_code=201)
async def create_account(
    data: AccountCreate,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    acct = await billing_svc.create_account(session, data)
    await audit(session, actor, "account_created", str(acct.id), {"bank": acct.bank, "alias": acct.alias})
    await session.commit()
    return {
        "id": str(acct.id),
        "bank": acct.bank,
        "alias": acct.alias,
        "holder": acct.holder,
        "reference": acct.reference,
        "status": acct.status,
        "revision": acct.revision,
        "cards_count": 0,
        "created_at": acct.created_at,
        "updated_at": acct.updated_at,
    }


@router.put("/accounts/{account_id}")
async def update_account(
    account_id: uuid.UUID,
    data: AccountEdit,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    acct = (await session.execute(
        select(Account).where(Account.id == account_id).with_for_update()
    )).scalar_one_or_none()
    if not acct:
        raise HTTPException(404, "账户不存在")
    if acct.revision != data.expected_revision:
        raise HTTPException(409, "账户已被其他操作修改，请刷新重试")

    if data.bank is not None:
        acct.bank = data.bank
    if data.reference is not None:
        acct.reference = data.reference
    if data.holder is not None:
        acct.holder = data.holder
    acct.alias = data.alias
    acct.status = data.status
    acct.revision += 1
    acct.updated_at = now()

    await billing_svc._log_change(session, "account", acct.id, "update", {
        "id": str(acct.id),
        "bank": acct.bank,
        "alias": acct.alias,
        "reference": acct.reference,
        "status": acct.status,
        "revision": acct.revision,
    })
    await audit(session, actor, "account_updated", str(acct.id), {"revision": acct.revision, "status": acct.status})
    await session.commit()
    return {
        "id": str(acct.id),
        "bank": acct.bank,
        "alias": acct.alias,
        "holder": acct.holder,
        "reference": acct.reference,
        "status": acct.status,
        "revision": acct.revision,
        "updated_at": acct.updated_at,
    }

@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: uuid.UUID,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    acct = (await session.execute(
        select(Account).where(Account.id == account_id).with_for_update()
    )).scalar_one_or_none()
    if not acct:
        raise HTTPException(404, "账户不存在")

    stmt_count = (await session.execute(
        select(func.count()).select_from(Statement).where(Statement.account_id == account_id)
    )).scalar_one()
    if stmt_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该账户下已存在 {stmt_count} 笔正式账单或还款流水。为保障财务数据完整性，无法直接删除。如不再使用请使用【归档】功能隐藏该账户；若确需彻底删除，请先在账单管理中清理名下账单。"
        )

    await session.execute(
        update(StatementDraftModel)
        .where(StatementDraftModel.matched_account_id == account_id)
        .values(matched_account_id=None, matched_card_id=None)
    )

    cards = list((await session.execute(
        select(Card).where(Card.account_id == account_id)
    )).scalars().all())
    for card in cards:
        await session.execute(
            update(StatementDraftModel)
            .where(StatementDraftModel.matched_card_id == card.id)
            .values(matched_card_id=None)
        )
        await billing_svc._log_change(session, "card", card.id, "delete", {
            "id": str(card.id),
            "account_id": str(card.account_id),
            "tail": card.tail,
            "display_name": card.display_name,
        })
        await session.delete(card)

    await billing_svc._log_change(session, "account", acct.id, "delete", {
        "id": str(acct.id),
        "bank": acct.bank,
        "alias": acct.alias,
        "reference": acct.reference,
    })
    await audit(session, actor, "account_deleted", str(acct.id), {
        "bank": acct.bank,
        "alias": acct.alias,
        "deleted_cards_count": len(cards),
    })

    await session.delete(acct)
    await session.commit()
    return {"success": True, "message": "账户及其名下卡片已成功删除"}



@router.get("/accounts/{account_id}/cards")
async def list_account_cards(account_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    cards = list((await session.execute(
        select(Card).where(Card.account_id == account_id).order_by(Card.created_at.desc())
    )).scalars().all())
    return [{
        "id": str(c.id),
        "account_id": str(c.account_id),
        "tail": c.tail,
        "display_name": c.display_name,
        "status": c.status,
        "revision": c.revision,
        "created_at": c.created_at,
    } for c in cards]


@router.get("/cards")
async def list_all_cards(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(Card, Account.bank, Account.alias)
        .join(Account, Card.account_id == Account.id)
        .order_by(Card.created_at.desc())
    )).all()

    return [{
        "id": str(c.id),
        "account_id": str(c.account_id),
        "bank": bank,
        "account_alias": alias,
        "tail": c.tail,
        "display_name": c.display_name,
        "status": c.status,
        "revision": c.revision,
        "created_at": c.created_at,
    } for c, bank, alias in rows]


@router.post("/cards", status_code=201)
async def create_card(
    data: CardCreate,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if not re.match(r"^[0-9]{4}$", data.tail):
        raise HTTPException(422, "卡片尾号必须为4位数字")
    try:
        card = await billing_svc.create_card(session, data)
    except NotFoundError:
        raise HTTPException(404, "所属账户不存在")

    await audit(session, actor, "card_created", str(card.id), {"tail": card.tail, "account_id": str(card.account_id)})
    await session.commit()
    return {
        "id": str(card.id),
        "account_id": str(card.account_id),
        "tail": card.tail,
        "display_name": card.display_name,
        "status": card.status,
        "revision": card.revision,
        "created_at": card.created_at,
    }


@router.put("/cards/{card_id}")
async def update_card(
    card_id: uuid.UUID,
    data: CardEdit,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    card = (await session.execute(
        select(Card).where(Card.id == card_id).with_for_update()
    )).scalar_one_or_none()
    if not card:
        raise HTTPException(404, "卡片不存在")
    if card.revision != data.expected_revision:
        raise HTTPException(409, "卡片已被其他操作修改，请刷新重试")

    if data.tail is not None:
        card.tail = data.tail
    card.display_name = data.display_name
    card.status = data.status
    card.revision += 1

    await billing_svc._log_change(session, "card", card.id, "update", {
        "id": str(card.id),
        "account_id": str(card.account_id),
        "display_name": card.display_name,
        "tail": card.tail,
        "status": card.status,
        "revision": card.revision,
    })
    await audit(session, actor, "card_updated", str(card.id), {"revision": card.revision, "status": card.status})
    await session.commit()
    return {
        "id": str(card.id),
        "account_id": str(card.account_id),
        "tail": card.tail,
        "display_name": card.display_name,
        "status": card.status,
        "revision": card.revision,
    }

@router.delete("/cards/{card_id}")
async def delete_card(
    card_id: uuid.UUID,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    card = (await session.execute(
        select(Card).where(Card.id == card_id).with_for_update()
    )).scalar_one_or_none()
    if not card:
        raise HTTPException(404, "卡片不存在")

    await session.execute(
        update(StatementDraftModel)
        .where(StatementDraftModel.matched_card_id == card_id)
        .values(matched_card_id=None)
    )

    await billing_svc._log_change(session, "card", card.id, "delete", {
        "id": str(card.id),
        "account_id": str(card.account_id),
        "tail": card.tail,
        "display_name": card.display_name,
    })
    await audit(session, actor, "card_deleted", str(card.id), {
        "account_id": str(card.account_id),
        "tail": card.tail,
    })

    await session.delete(card)
    await session.commit()
    return {"success": True, "message": "信用卡已成功删除"}



# ---------------------------------------------------------------------------
# 2b. Card Split — move a card into its own new account
# ---------------------------------------------------------------------------

@router.post("/cards/{card_id}/split")
async def split_card_to_new_account(
    card_id: uuid.UUID,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Move a card from a multi-card account into a brand-new sibling account.

    The new account inherits bank, holder, and currency from the original.
    If the original account only has one card, the operation is rejected.
    """
    card = (await session.execute(
        select(Card).where(Card.id == card_id).with_for_update()
    )).scalar_one_or_none()
    if not card:
        raise HTTPException(404, "卡片不存在")

    old_acct = (await session.execute(
        select(Account).where(Account.id == card.account_id)
        .options(selectinload(Account.cards))
    )).scalar_one_or_none()
    if not old_acct:
        raise HTTPException(404, "所属账户不存在")

    active_cards = [c for c in old_acct.cards if c.status == "active"]
    if len(active_cards) <= 1:
        raise HTTPException(400, "该账户仅有一张有效卡片，无需拆分")

    # Create a new sibling account
    tail = card.tail or ""
    new_alias = f"{old_acct.bank}信用卡 ({old_acct.holder or tail})"
    new_acct = Account(
        bank=old_acct.bank,
        alias=new_alias,
        holder=old_acct.holder,
        reference=None,
        status="active",
    )
    session.add(new_acct)
    await session.flush()  # get new_acct.id

    # Move the card
    card.account_id = new_acct.id

    await billing_svc._log_change(session, "card", card.id, "split", {
        "old_account_id": str(old_acct.id),
        "new_account_id": str(new_acct.id),
        "tail": card.tail,
    })
    await audit(session, actor, "card_split", str(card.id), {
        "old_account_id": str(old_acct.id),
        "new_account_id": str(new_acct.id),
        "new_alias": new_alias,
        "tail": card.tail,
    })

    await session.commit()
    return {
        "success": True,
        "message": f"卡片尾号 {tail} 已拆分到新账户",
        "new_account_id": str(new_acct.id),
        "new_alias": new_alias,
    }


# ---------------------------------------------------------------------------
# 3. Statements & Payments
# ---------------------------------------------------------------------------

@router.get("/statements")
async def list_statements(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    account_id: uuid.UUID | None = None,
    currency: str | None = None,
    status: Literal["all", "unpaid", "paid"] = "all",
    sort_by: Literal["due_date", "statement_date", "created_at"] = "due_date",
    sort_order: Literal["asc", "desc"] = "asc",
    session: AsyncSession = Depends(get_session),
):
    query = (
        select(Statement, Account.bank, Account.alias, Account.holder)
        .join(Account, Statement.account_id == Account.id)
        .options(
            selectinload(Statement.versions),
            selectinload(Statement.payments),
        )
    )
    if account_id:
        query = query.where(Statement.account_id == account_id)
    if currency:
        query = query.where(Statement.currency == currency)

    if sort_by == "due_date":
        col_order = Statement.due_date.asc() if sort_order == "asc" else Statement.due_date.desc()
        sec_order = Statement.statement_date.asc() if sort_order == "asc" else Statement.statement_date.desc()
        third_order = Statement.created_at.asc() if sort_order == "asc" else Statement.created_at.desc()
        query = query.order_by(col_order, sec_order, third_order)
    elif sort_by == "statement_date":
        col_order = Statement.statement_date.asc() if sort_order == "asc" else Statement.statement_date.desc()
        sec_order = Statement.created_at.asc() if sort_order == "asc" else Statement.created_at.desc()
        query = query.order_by(col_order, sec_order)
    elif sort_by == "created_at":
        col_order = Statement.created_at.asc() if sort_order == "asc" else Statement.created_at.desc()
        query = query.order_by(col_order)
    else:
        query = query.order_by(Statement.due_date.asc(), Statement.statement_date.asc(), Statement.created_at.asc())
    results = list((await session.execute(query)).all())

    items = []
    for stmt, bank, alias, holder in results:
        cur_ver = None
        for v in stmt.versions:
            if v.id == stmt.current_version_id:
                cur_ver = v
                break
        total_amount = cur_ver.amount_minor if cur_ver else 0
        min_amount = cur_ver.minimum_minor if cur_ver else None
        total_paid = sum(p.amount_minor for p in stmt.payments if p.revoked_at is None)
        remaining = max(0, total_amount - total_paid)

        is_paid = (remaining == 0 and total_amount > 0) or (total_amount == 0)
        if status == "unpaid" and remaining == 0:
            continue
        if status == "paid" and remaining > 0:
            continue

        # Fetch card tails for this account
        acct_cards = (await session.execute(
            select(Card.tail).where(Card.account_id == stmt.account_id, Card.status == "active")
        )).scalars().all()

        items.append({
            "id": str(stmt.id),
            "account_id": str(stmt.account_id),
            "bank": bank,
            "account_alias": alias,
            "holder": holder,
            "card_tails": list(acct_cards),
            "currency": stmt.currency,
            "statement_date": stmt.statement_date,
            "due_date": stmt.due_date,
            "current_version_id": str(stmt.current_version_id) if stmt.current_version_id else None,
            "amount_minor": total_amount,
            "minimum_minor": min_amount,
            "total_paid_minor": total_paid,
            "remaining_minor": remaining,
            "is_paid": is_paid,
            "created_at": stmt.created_at,
        })

    total = len(items)
    paginated = items[(page - 1) * size : page * size]
    return {"items": paginated, "total": total, "page": page, "size": size}


@router.get("/statements/{statement_id}")
async def get_statement_detail(
    statement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    stmt_row = (await session.execute(
        select(Statement, Account.bank, Account.alias, Account.holder)
        .join(Account, Statement.account_id == Account.id)
        .options(
            selectinload(Statement.versions),
            selectinload(Statement.payments),
        )
        .where(Statement.id == statement_id)
    )).first()
    if not stmt_row:
        raise HTTPException(404, "账单不存在")

    stmt, bank, alias, holder = stmt_row
    cur_ver = None
    for v in stmt.versions:
        if v.id == stmt.current_version_id:
            cur_ver = v
            break

    total_amount = cur_ver.amount_minor if cur_ver else 0
    total_paid = sum(p.amount_minor for p in stmt.payments if p.revoked_at is None)
    remaining = max(0, total_amount - total_paid)

    sorted_versions = sorted(stmt.versions, key=lambda v: v.version_number, reverse=True)
    sorted_payments = sorted(stmt.payments, key=lambda p: p.recorded_at, reverse=True)

    version_ids = [v.id for v in stmt.versions]
    draft_row = (await session.execute(
        select(StatementDraftModel)
        .where(StatementDraftModel.confirmed_version_id.in_(version_ids))
    )).scalars().first()

    draft_info = None
    if draft_row:
        draft_info = {
            "draft_id": str(draft_row.id),
            "source_id": str(draft_row.email_source_id) if draft_row.email_source_id else None,
            "extractor_name": draft_row.extractor_name,
            "evidence": draft_row.evidence,
        }

    detail_cards = (await session.execute(
        select(Card.tail).where(Card.account_id == stmt.account_id, Card.status == "active")
    )).scalars().all()

    return {
        "id": str(stmt.id),
        "account_id": str(stmt.account_id),
        "bank": bank,
        "account_alias": alias,
        "holder": holder,
        "card_tails": list(detail_cards),
        "currency": stmt.currency,
        "statement_date": stmt.statement_date,
        "due_date": stmt.due_date,
        "current_version_id": str(stmt.current_version_id) if stmt.current_version_id else None,
        "amount_minor": total_amount,
        "minimum_minor": cur_ver.minimum_minor if cur_ver else None,
        "total_paid_minor": total_paid,
        "remaining_minor": remaining,
        "versions": [{
            "id": str(v.id),
            "version_number": v.version_number,
            "amount_minor": v.amount_minor,
            "minimum_minor": v.minimum_minor,
            "source": v.source,
            "reason": v.reason,
            "confirmed_at": v.confirmed_at,
            "confirmed_by": v.confirmed_by,
            "created_at": v.created_at,
        } for v in sorted_versions],
        "payments": [{
            "id": str(p.id),
            "amount_minor": p.amount_minor,
            "currency": p.currency,
            "note": p.note,
            "recorded_at": p.recorded_at,
            "revoked_at": p.revoked_at,
            "revoke_reason": p.revoke_reason,
        } for p in sorted_payments],
        "associated_draft": draft_info,
        "created_at": stmt.created_at,
        "updated_at": stmt.updated_at,
    }


@router.post("/statements/{statement_id}/correct")
async def correct_statement(
    statement_id: uuid.UUID,
    data: StatementCorrection,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    receipt = await session.get(CommandReceipt, data.request_id)
    if receipt:
        return receipt.result

    stmt = (await session.execute(
        select(Statement).where(Statement.id == statement_id).with_for_update()
    )).scalar_one_or_none()
    if not stmt:
        raise HTTPException(404, "账单不存在")

    if stmt.current_version_id != data.expected_version_id:
        raise HTTPException(409, "账单已被其他人或版本更新，请刷新重试")

    cur_ver = await session.get(StatementVersion, stmt.current_version_id)
    if not cur_ver:
        raise HTTPException(409, "账单当前生效版本缺失")

    active_paid = await billing_svc._active_paid(session, stmt.id)
    if data.amount_minor < active_paid:
        raise HTTPException(
            400,
            f"更正金额({data.amount_minor}分)不得低于已有效还款总额({active_paid}分)",
        )

    new_ver = StatementVersion(
        statement_id=stmt.id,
        version_number=cur_ver.version_number + 1,
        amount_minor=data.amount_minor,
        minimum_minor=data.minimum_minor,
        source="manual_correction",
        reason=data.reason,
        confirmed_at=now(),
        confirmed_by="admin:" + actor.id,
    )
    session.add(new_ver)
    await session.flush()

    stmt.current_version_id = new_ver.id
    stmt.updated_at = now()

    await billing_svc._log_change(session, "statement", stmt.id, "update", {
        "id": str(stmt.id),
        "account_id": str(stmt.account_id),
        "currency": stmt.currency,
        "statement_date": stmt.statement_date.isoformat(),
        "due_date": stmt.due_date.isoformat(),
        "amount_minor": new_ver.amount_minor,
        "minimum_minor": new_ver.minimum_minor,
        "version_number": new_ver.version_number,
        "current_version_id": str(new_ver.id),
    })

    result_payload = {
        "statement_id": str(stmt.id),
        "version_id": str(new_ver.id),
        "version_number": new_ver.version_number,
        "amount_minor": new_ver.amount_minor,
        "minimum_minor": new_ver.minimum_minor,
        "remaining_minor": new_ver.amount_minor - active_paid,
        "reason": new_ver.reason,
    }

    session.add(CommandReceipt(
        id=data.request_id,
        fingerprint="correct:" + str(stmt.id),
        result=result_payload,
    ))
    await audit(session, actor, "statement_corrected", str(stmt.id), {
        "version_number": new_ver.version_number,
        "amount_minor": new_ver.amount_minor,
        "reason": data.reason,
    })
    await session.commit()
    return result_payload


@router.post("/statements/{statement_id}/payments", status_code=201)
async def record_payment(
    statement_id: uuid.UUID,
    data: PaymentCreate,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if data.statement_id != statement_id:
        raise HTTPException(400, "URL账单ID与请求体不一致")

    try:
        payment, created = await billing_svc.record_payment(
            session, data, request_id=data.request_id
        )
    except ConflictError as e:
        raise HTTPException(409, str(e))
    except NotFoundError as e:
        raise HTTPException(404, str(e))

    await audit(session, actor, "payment_recorded", str(payment.id), {
        "statement_id": str(statement_id),
        "amount_minor": payment.amount_minor,
        "currency": payment.currency,
        "created": created,
    })
    await session.commit()

    active_paid = await billing_svc._active_paid(session, statement_id)
    stmt = await session.get(Statement, statement_id)
    cur_ver = await session.get(StatementVersion, stmt.current_version_id)
    total_amt = cur_ver.amount_minor if cur_ver else 0

    return {
        "id": str(payment.id),
        "statement_id": str(payment.statement_id),
        "amount_minor": payment.amount_minor,
        "currency": payment.currency,
        "note": payment.note,
        "recorded_at": payment.recorded_at,
        "remaining_minor": max(0, total_amt - active_paid),
        "created": created,
    }


@router.post("/payments/{payment_id}/revoke")
async def revoke_payment(
    payment_id: uuid.UUID,
    data: RevokeRequest,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        payment = await billing_svc.revoke_payment(session, payment_id, reason=data.reason)
    except NotFoundError:
        raise HTTPException(404, "还款记录不存在")

    await audit(session, actor, "payment_revoked", str(payment.id), {
        "statement_id": str(payment.statement_id),
        "amount_minor": payment.amount_minor,
        "reason": data.reason,
    })
    await session.commit()

    active_paid = await billing_svc._active_paid(session, payment.statement_id)
    stmt = await session.get(Statement, payment.statement_id)
    cur_ver = await session.get(StatementVersion, stmt.current_version_id)
    total_amt = cur_ver.amount_minor if cur_ver else 0

    return {
        "id": str(payment.id),
        "statement_id": str(payment.statement_id),
        "revoked_at": payment.revoked_at,
        "revoke_reason": payment.revoke_reason,
        "remaining_minor": max(0, total_amt - active_paid),
    }


@router.delete("/statements/{statement_id}")
async def delete_statement(
    statement_id: uuid.UUID,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    stmt = (await session.execute(
        select(Statement)
        .where(Statement.id == statement_id)
        .options(
            selectinload(Statement.versions),
            selectinload(Statement.payments),
        )
        .with_for_update()
    )).scalar_one_or_none()
    if not stmt:
        raise HTTPException(404, "账单不存在")

    # 1. 解开 Statement.current_version_id 与 StatementVersion 间的循环外键约束
    stmt.current_version_id = None
    await session.flush()

    # 2. 解除草稿关联引用（将关联到该账单版本的草稿重置为待审核，清空 confirmed_version_id）
    version_ids = [v.id for v in stmt.versions]
    if version_ids:
        await session.execute(
            update(StatementDraftModel)
            .where(StatementDraftModel.confirmed_version_id.in_(version_ids))
            .values(confirmed_version_id=None, status="pending_review")
        )

    # 3. 级联清理名下还款流水记录，记录移动端同步 change_log
    for p in stmt.payments:
        await billing_svc._log_change(session, "payment", p.id, "delete", {
            "id": str(p.id),
            "statement_id": str(p.statement_id),
            "amount_minor": p.amount_minor,
            "currency": p.currency,
        })
        await session.delete(p)

    # 4. 级联清理名下的不可变版本记录，记录移动端同步 change_log
    for v in stmt.versions:
        await billing_svc._log_change(session, "statement_version", v.id, "delete", {
            "id": str(v.id),
            "statement_id": str(v.statement_id),
            "version_number": v.version_number,
            "amount_minor": v.amount_minor,
        })
        await session.delete(v)

    # 5. 记录账单删除同步日志与管理员安全审计事件
    await billing_svc._log_change(session, "statement", stmt.id, "delete", {
        "id": str(stmt.id),
        "account_id": str(stmt.account_id),
        "currency": stmt.currency,
        "statement_date": str(stmt.statement_date),
        "due_date": str(stmt.due_date),
    })
    await audit(session, actor, "statement_deleted", str(stmt.id), {
        "account_id": str(stmt.account_id),
        "currency": stmt.currency,
        "statement_date": str(stmt.statement_date),
        "versions_count": len(stmt.versions),
        "payments_count": len(stmt.payments),
    })

    # 6. 删除账单实体并提交事务
    await session.delete(stmt)
    await session.commit()
    return {"success": True, "message": "账单及其关联版本与还款记录已成功删除"}


@router.delete("/payments/{payment_id}")
async def delete_payment(
    payment_id: uuid.UUID,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    payment = (await session.execute(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )).scalar_one_or_none()
    if not payment:
        raise HTTPException(404, "还款记录不存在")

    stmt_id = payment.statement_id
    await billing_svc._log_change(session, "payment", payment.id, "delete", {
        "id": str(payment.id),
        "statement_id": str(stmt_id),
        "amount_minor": payment.amount_minor,
        "currency": payment.currency,
    })
    await audit(session, actor, "payment_deleted", str(payment.id), {
        "statement_id": str(stmt_id),
        "amount_minor": payment.amount_minor,
        "currency": payment.currency,
    })
    await session.delete(payment)
    await session.commit()
    return {"success": True, "message": "还款记录已成功删除"}


# ---------------------------------------------------------------------------
# 4. Email Center
# ---------------------------------------------------------------------------

def _sanitize_preview(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<(script|style|iframe|object|embed)[^>]*>.*?</(script|style|iframe|object|embed)>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'on[a-z]+\s*=\s*["\'][^"\']*["\']', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<img[^>]*>", "[图片已阻止]", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


@router.get("/emails")
async def list_emails(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    mailbox_id: uuid.UUID | None = None,
    candidate_only: bool = False,
    parse_status: str | None = None,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(EmailSource, Mailbox.email_address).join(Mailbox, EmailSource.mailbox_id == Mailbox.id)
    if mailbox_id:
        query = query.where(EmailSource.mailbox_id == mailbox_id)
    if candidate_only:
        query = query.where(EmailSource.is_statement_candidate.is_(True))
    if parse_status and parse_status != "all":
        query = query.where(EmailSource.parse_status == parse_status)
    if search:
        s = f"%{search}%"
        query = query.where(EmailSource.subject.ilike(s) | EmailSource.sender.ilike(s))

    total_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(total_query)).scalar_one()

    query = query.order_by(EmailSource.email_date.desc()).offset((page - 1) * size).limit(size)
    rows = (await session.execute(query)).all()

    items = [{
        "id": str(es.id),
        "mailbox_id": str(es.mailbox_id),
        "mailbox_address": email_address,
        "subject": es.subject,
        "sender": es.sender,
        "recipient": es.recipient,
        "email_date": es.email_date,
        "has_attachments": es.has_attachments,
        "is_statement_candidate": es.is_statement_candidate,
        "parse_status": es.parse_status,
        "error_message": es.error_message,
        "created_at": es.created_at,
    } for es, email_address in rows]

    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/emails/{email_id}")
async def get_email_detail(
    email_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    row = (await session.execute(
        select(EmailSource, Mailbox.email_address)
        .join(Mailbox, EmailSource.mailbox_id == Mailbox.id)
        .options(selectinload(EmailSource.attachments))
        .where(EmailSource.id == email_id)
    )).first()
    if not row:
        raise HTTPException(404, "邮件不存在")

    es, mailbox_address = row

    plain_text = ""
    if es.raw_storage_path and os.path.exists(es.raw_storage_path):
        try:
            raw_bytes = storage_mgr.read_file(es.raw_storage_path)
            parsed = mime_parser.parse_bytes(raw_bytes)
            if parsed.body_plain:
                plain_text = parsed.body_plain
            elif parsed.body_html:
                from cardcue_api.parsing.html_extractor import HtmlStatementExtractor
                plain_text = HtmlStatementExtractor().html_to_text(parsed.body_html)
        except Exception as e:
            plain_text = f"[正文读取错误: {e}]"

    safe_preview = _sanitize_preview(plain_text)
    if len(safe_preview) > 30000:
        safe_preview = safe_preview[:30000] + "\n\n...[正文超出长度，已截断展示]"

    drafts = list((await session.execute(
        select(StatementDraftModel).where(StatementDraftModel.email_source_id == es.id)
    )).scalars().all())

    jobs = list((await session.execute(
        select(AdminJob).where(AdminJob.target_id == es.id).order_by(AdminJob.created_at.desc())
    )).scalars().all())

    return {
        "id": str(es.id),
        "mailbox_id": str(es.mailbox_id),
        "mailbox_address": mailbox_address,
        "folder": es.folder,
        "uid": es.uid,
        "message_id": es.message_id,
        "subject": es.subject,
        "sender": es.sender,
        "recipient": es.recipient,
        "email_date": es.email_date,
        "has_attachments": es.has_attachments,
        "is_statement_candidate": es.is_statement_candidate,
        "parse_status": es.parse_status,
        "error_message": es.error_message,
        "body_preview": safe_preview,
        "attachments": [{
            "id": str(att.id),
            "filename": att.filename,
            "content_type": att.content_type,
            "size_bytes": att.size_bytes,
            "created_at": att.created_at,
        } for att in es.attachments],
        "drafts": [{
            "id": str(d.id),
            "status": d.status,
            "bank": d.bank,
            "amount_minor": d.amount_minor,
            "currency": d.currency,
            "extractor_name": d.extractor_name,
            "created_at": d.created_at,
        } for d in drafts],
        "jobs": [{
            "id": str(j.id),
            "status": j.status,
            "kind": j.kind,
            "error_code": j.error_code,
            "created_at": j.created_at,
        } for j in jobs],
    }


@router.post("/emails/{email_id}/action")
async def action_email(
    email_id: uuid.UUID,
    data: SourceAction,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    es = (await session.execute(
        select(EmailSource).where(EmailSource.id == email_id).with_for_update()
    )).scalar_one_or_none()
    if not es:
        raise HTTPException(404, "邮件不存在")

    if data.action == "ignore":
        es.parse_status = "ignored"
    elif data.action == "restore":
        es.parse_status = "pending"

    await audit(session, actor, f"email_{data.action}", str(es.id))
    await session.commit()
    return {"id": str(es.id), "parse_status": es.parse_status}


@router.post("/emails/batch-parse")
async def batch_parse_emails(
    data: BatchParseRequest,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    query = select(EmailSource).where(
        EmailSource.raw_storage_path.isnot(None),
        EmailSource.parse_status.notin_(["ignored", "duplicate"]),
    )
    if data.email_ids:
        query = query.where(EmailSource.id.in_(data.email_ids))
    else:
        statuses = ["pending", "failed"] if data.include_failed else ["pending"]
        query = query.where(EmailSource.parse_status.in_(statuses))
        if data.mailbox_id:
            query = query.where(EmailSource.mailbox_id == data.mailbox_id)
        query = query.where(EmailSource.is_statement_candidate.is_(True))

    sources = list((await session.execute(query)).scalars().all())
    enqueued_count = 0
    for s in sources:
        try:
            await enqueue(session, JobCreate(kind="parse", target_id=s.id, allow_external=True), actor=actor)
            enqueued_count += 1
        except Exception:
            pass

    await session.commit()
    await audit(session, actor, "email_batch_parse_enqueued", None, {"count": enqueued_count})
    return {"enqueued": enqueued_count, "total_found": len(sources)}


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    att = await session.get(EmailAttachment, attachment_id)
    if not att:
        raise HTTPException(404, "附件记录不存在")

    storage_root = Path(settings.mail_storage_dir).resolve()
    target_path = Path(att.storage_path).resolve()
    if not target_path.is_relative_to(storage_root) or not target_path.exists():
        raise HTTPException(404, "附件文件不存在或已被清除")

    clean_filename = re.sub(r"[^\w\.\-]", "_", att.filename)
    return FileResponse(
        path=str(target_path),
        media_type="application/octet-stream",
        filename=clean_filename,
    )


# ---------------------------------------------------------------------------
# 5. Draft Review
# ---------------------------------------------------------------------------

@router.get("/drafts")
async def list_drafts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str = "pending_review",
    session: AsyncSession = Depends(get_session),
):
    query = (
        select(
            StatementDraftModel,
            Account.bank.label("account_bank"),
            Account.alias.label("account_alias"),
            Account.holder.label("account_holder"),
            Card.tail.label("card_tail"),
        )
        .outerjoin(Account, StatementDraftModel.matched_account_id == Account.id)
        .outerjoin(Card, StatementDraftModel.matched_card_id == Card.id)
    )
    if status and status != "all":
        query = query.where(StatementDraftModel.status == status)

    total = (await session.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar_one()

    query = query.order_by(StatementDraftModel.created_at.desc()).offset((page - 1) * size).limit(size)
    rows = (await session.execute(query)).all()

    items = []
    for d, acct_bank, acct_alias, acct_holder, card_tail in rows:
        items.append({
            "id": str(d.id),
            "email_source_id": str(d.email_source_id) if d.email_source_id else None,
            "status": d.status,
            "bank": d.bank,
            "currency": d.currency,
            "amount_minor": d.amount_minor,
            "minimum_minor": d.minimum_minor,
            "statement_date": d.statement_date,
            "due_date": d.due_date,
            "account_reference": d.account_reference,
            "card_tails": d.card_tails or [],
            "review_reasons": d.review_reasons or [],
            "matched_account_id": str(d.matched_account_id) if d.matched_account_id else None,
            "matched_account_name": (acct_alias or acct_bank) if acct_bank else None,
            "matched_account_bank": acct_bank,
            "matched_account_holder": acct_holder,
            "matched_card_id": str(d.matched_card_id) if d.matched_card_id else None,
            "matched_card_tail": card_tail,
            "extractor_name": d.extractor_name,
            "revision": d.revision,
            "created_at": d.created_at,
        })

    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/drafts/{draft_id}")
async def get_draft_detail(
    draft_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    draft = await session.get(StatementDraftModel, draft_id)
    if not draft:
        raise HTTPException(404, "草稿不存在")

    matched_account = await session.get(Account, draft.matched_account_id) if draft.matched_account_id else None
    matched_card = await session.get(Card, draft.matched_card_id) if draft.matched_card_id else None

    all_accounts = list((await session.execute(
        select(Account)
        .options(selectinload(Account.cards))
        .where(Account.status == "active")
        .order_by(Account.bank)
    )).scalars().all())

    candidate_cards = []
    if draft.matched_account_id:
        candidate_cards = list((await session.execute(
            select(Card).where(Card.account_id == draft.matched_account_id, Card.status == "active")
        )).scalars().all())

    source_info = None
    if draft.email_source_id:
        source = await session.get(EmailSource, draft.email_source_id)
        if source:
            source_info = {
                "id": str(source.id),
                "subject": source.subject,
                "sender": source.sender,
                "email_date": source.email_date,
            }

    return {
        "id": str(draft.id),
        "email_source_id": str(draft.email_source_id) if draft.email_source_id else None,
        "status": draft.status,
        "bank": draft.bank,
        "currency": draft.currency,
        "amount_minor": draft.amount_minor,
        "minimum_minor": draft.minimum_minor,
        "statement_date": draft.statement_date,
        "due_date": draft.due_date,
        "account_reference": draft.account_reference,
        "card_tails": draft.card_tails or [],
        "evidence": draft.evidence or [],
        "review_reasons": draft.review_reasons or [],
        "matched_account_id": str(draft.matched_account_id) if draft.matched_account_id else None,
        "matched_card_id": str(draft.matched_card_id) if draft.matched_card_id else None,
        "confirmed_version_id": str(draft.confirmed_version_id) if draft.confirmed_version_id else None,
        "rejection_reason": draft.rejection_reason,
        "extractor_name": draft.extractor_name,
        "revision": draft.revision,
        "matched_account": {
            "id": str(matched_account.id),
            "bank": matched_account.bank,
            "alias": matched_account.alias,
            "holder": matched_account.holder,
        } if matched_account else None,
        "matched_card": {
            "id": str(matched_card.id),
            "tail": matched_card.tail,
            "display_name": matched_card.display_name,
        } if matched_card else None,
        "candidate_accounts": [{
            "id": str(a.id),
            "bank": a.bank,
            "alias": a.alias,
            "holder": a.holder,
            "reference": a.reference,
            "cards": [{
                "id": str(c.id),
                "tail": c.tail,
                "display_name": c.display_name,
                "status": c.status,
            } for c in a.cards if c.status == "active"],
        } for a in all_accounts],
        "candidate_cards": [{
            "id": str(c.id),
            "tail": c.tail,
            "display_name": c.display_name,
        } for c in candidate_cards],
        "source_email": source_info,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
    }


@router.put("/drafts/{draft_id}")
async def update_draft(
    draft_id: uuid.UUID,
    data: DraftEdit,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    draft = (await session.execute(
        select(StatementDraftModel).where(StatementDraftModel.id == draft_id).with_for_update()
    )).scalar_one_or_none()
    if not draft:
        raise HTTPException(404, "草稿不存在")
    if draft.revision != data.expected_revision:
        raise HTTPException(409, "草稿已被其他操作更新，请刷新重试")

    if data.bank is not None:
        draft.bank = data.bank
    if data.currency is not None:
        draft.currency = data.currency
    if data.amount_minor is not None:
        draft.amount_minor = data.amount_minor
    if data.minimum_minor is not None:
        draft.minimum_minor = data.minimum_minor
    if data.statement_date is not None:
        draft.statement_date = data.statement_date
    if data.due_date is not None:
        draft.due_date = data.due_date
    if data.matched_account_id is not None:
        draft.matched_account_id = data.matched_account_id
    if data.matched_card_id is not None:
        draft.matched_card_id = data.matched_card_id

    draft.revision += 1
    draft.updated_at = now()

    await audit(session, actor, "draft_updated", str(draft.id), {"revision": draft.revision})
    await session.commit()
    return {"ok": True, "revision": draft.revision}


@router.post("/drafts/{draft_id}/confirm")
async def confirm_draft(
    draft_id: uuid.UUID,
    req: StatementDraftConfirmRequest,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        stmt, ver, draft = await draft_svc.confirm_draft(
            session=session,
            draft_id=draft_id,
            req=req,
            confirmed_by="admin:" + actor.id,
        )
    except ConflictError as e:
        raise HTTPException(409, str(e))
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))

    await audit(session, actor, "draft_confirmed", str(draft_id), {
        "statement_id": str(stmt.id),
        "version_id": str(ver.id),
        "amount_minor": ver.amount_minor,
    })
    await session.commit()
    return {
        "draft_id": str(draft.id),
        "statement_id": str(stmt.id),
        "version_id": str(ver.id),
        "amount_minor": ver.amount_minor,
        "status": draft.status,
    }


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(
    draft_id: uuid.UUID,
    req: StatementDraftRejectRequest,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        draft = await draft_svc.reject_draft(
            session=session,
            draft_id=draft_id,
            reason=req.reason,
            rejected_by="admin:" + actor.id,
        )
    except ConflictError as e:
        raise HTTPException(409, str(e))
    except NotFoundError as e:
        raise HTTPException(404, str(e))

    await audit(session, actor, "draft_rejected", str(draft_id), {"reason": req.reason})
    await session.commit()
    return {"draft_id": str(draft.id), "status": draft.status}


@router.delete("/drafts/{draft_id}")
async def delete_draft(
    draft_id: uuid.UUID,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    draft = await session.get(StatementDraftModel, draft_id)
    if not draft:
        raise HTTPException(404, "草稿不存在")

    email_source_id = draft.email_source_id
    bank = draft.bank
    status = draft.status

    await session.delete(draft)
    await session.flush()

    if email_source_id:
        remaining = (await session.execute(
            select(func.count()).select_from(StatementDraftModel).where(
                StatementDraftModel.email_source_id == email_source_id
            )
        )).scalar_one()
        if remaining == 0:
            source = await session.get(EmailSource, email_source_id)
            if source and source.parse_status == "parsed":
                source.parse_status = "pending"

    await audit(session, actor, "draft_deleted", str(draft_id), {"bank": bank, "status": status})
    await session.commit()
    return {"ok": True, "deleted_id": str(draft_id)}


@router.post("/drafts/batch-delete")
async def batch_delete_drafts(
    data: BatchDeleteDraftsRequest,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if not data.draft_ids:
        return {"deleted_count": 0}

    drafts = list((await session.execute(
        select(StatementDraftModel).where(StatementDraftModel.id.in_(data.draft_ids))
    )).scalars().all())

    email_source_ids = {d.email_source_id for d in drafts if d.email_source_id}
    for d in drafts:
        await session.delete(d)

    await session.flush()

    for es_id in email_source_ids:
        remaining = (await session.execute(
            select(func.count()).select_from(StatementDraftModel).where(
                StatementDraftModel.email_source_id == es_id
            )
        )).scalar_one()
        if remaining == 0:
            source = await session.get(EmailSource, es_id)
            if source and source.parse_status == "parsed":
                source.parse_status = "pending"

    await audit(session, actor, "draft_batch_deleted", None, {"count": len(drafts)})
    await session.commit()
    return {"deleted_count": len(drafts)}


@router.post("/drafts/clear")
async def clear_drafts(
    data: ClearDraftsRequest,
    actor=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    query = select(StatementDraftModel)
    if data.status and data.status != "all":
        query = query.where(StatementDraftModel.status == data.status)

    drafts = list((await session.execute(query)).scalars().all())
    email_source_ids = {d.email_source_id for d in drafts if d.email_source_id}
    for d in drafts:
        await session.delete(d)

    await session.flush()

    for es_id in email_source_ids:
        remaining = (await session.execute(
            select(func.count()).select_from(StatementDraftModel).where(
                StatementDraftModel.email_source_id == es_id
            )
        )).scalar_one()
        if remaining == 0:
            source = await session.get(EmailSource, es_id)
            if source and source.parse_status == "parsed":
                source.parse_status = "pending"

    await audit(session, actor, "drafts_cleared", None, {"count": len(drafts), "status": data.status})
    await session.commit()
    return {"deleted_count": len(drafts)}


# ---------------------------------------------------------------------------
# 6. Devices Management
# ---------------------------------------------------------------------------

@router.get("/devices")
async def list_admin_devices(session: AsyncSession = Depends(get_session)):
    return await device_svc.list_devices(session)


@router.post("/devices/{device_id}/revoke")
async def revoke_admin_device(
    device_id: uuid.UUID,
    actor=Depends(recent_admin),
    session: AsyncSession = Depends(get_session),
):
    from cardcue_api.services.auth import AuthError
    try:
        dev = await device_svc.revoke_device(session, device_id)
        await audit(session, actor, "device_revoked", str(device_id))
        await session.commit()
        return dev
    except AuthError as e:
        raise HTTPException(404, str(e))


# ---------------------------------------------------------------------------
# 7. Audit Events
# ---------------------------------------------------------------------------

@router.get("/audit")
async def list_audit_events(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    action: str | None = None,
    actor: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(AuditEvent)
    if action:
        query = query.where(AuditEvent.action == action)
    if actor:
        query = query.where(AuditEvent.actor == actor)

    total = (await session.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar_one()

    query = query.order_by(AuditEvent.created_at.desc()).offset((page - 1) * size).limit(size)
    events = list((await session.execute(query)).scalars().all())

    return {
        "items": [{
            "id": str(ev.id),
            "actor": ev.actor,
            "action": ev.action,
            "target": ev.target,
            "detail": ev.detail,
            "created_at": ev.created_at,
        } for ev in events],
        "total": total,
        "page": page,
        "size": size,
    }


# ---------------------------------------------------------------------------
# 8. System Status
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_system_status(session: AsyncSession = Depends(get_session)):
    t0 = time.perf_counter()
    await session.execute(select(func.now()))
    db_latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    storage_dir = Path(settings.mail_storage_dir)
    storage_exists = storage_dir.exists()
    total_files = 0
    total_bytes = 0
    if storage_exists:
        for f in storage_dir.glob("**/*"):
            if f.is_file():
                total_files += 1
                total_bytes += f.stat().st_size

    mailboxes = list((await session.execute(select(Mailbox))).scalars().all())
    active_mb = sum(1 for m in mailboxes if m.is_active)

    active_jobs = (await session.execute(
        select(func.count()).select_from(AdminJob).where(AdminJob.status.in_(["queued", "running"]))
    )).scalar_one()
    failed_jobs = (await session.execute(
        select(func.count()).select_from(AdminJob).where(AdminJob.status == "failed")
    )).scalar_one()

    return {
        "api": {
            "status": "healthy",
            "version": "0.5.0",
            "environment": settings.environment,
            "server_time": now(),
        },
        "database": {
            "connected": True,
            "latency_ms": db_latency_ms,
        },
        "storage": {
            "storage_dir": str(storage_dir),
            "exists": storage_exists,
            "file_count": total_files,
            "size_bytes": total_bytes,
        },
        "mailboxes": {
            "total": len(mailboxes),
            "active": active_mb,
        },
        "jobs": {
            "active": active_jobs,
            "failed": failed_jobs,
        },
    }
