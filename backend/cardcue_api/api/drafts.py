"""API routes for statement drafts, parsing, and manual review confirmation."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cardcue_api.domain.schemas import (
    StatementDetail,
    StatementDraftConfirmRequest,
    StatementDraftConfirmResponse,
    StatementDraftOut,
    StatementDraftRejectRequest,
    StatementVersionOut,
)
from cardcue_api.persistence.database import get_session
from cardcue_api.services.billing import BillingService, ConflictError, NotFoundError
from cardcue_api.services.drafts import DraftService

router = APIRouter(prefix="/v1/drafts", tags=["drafts"])
svc = DraftService()
billing_svc = BillingService()


def _not_found(e: NotFoundError):
    raise HTTPException(status_code=404, detail=str(e))


def _conflict(e: ConflictError):
    raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=list[StatementDraftOut])
async def list_drafts(
    status: str | None = Query(default="pending_review", description="Filter by status: pending_review, confirmed, rejected, all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """List drafts with optional status filtering and pagination."""
    return await svc.list_drafts(session, status=status, limit=limit, offset=offset)


@router.get("/{draft_id}", response_model=StatementDraftOut)
async def get_draft(
    draft_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Get draft detail by ID."""
    try:
        return await svc.get_draft(session, draft_id)
    except NotFoundError as e:
        _not_found(e)


@router.post("/{draft_id}/confirm", response_model=StatementDraftConfirmResponse)
async def confirm_draft(
    draft_id: uuid.UUID,
    data: StatementDraftConfirmRequest,
    x_device_id: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
):
    """Confirm a statement draft into an official Statement and StatementVersion."""
    try:
        stmt, ver, draft = await svc.confirm_draft(
            session=session,
            draft_id=draft_id,
            req=data,
            confirmed_by=x_device_id or "device",
        )
        total_paid = await billing_svc._active_paid(session, stmt.id)
        stmt_detail = StatementDetail(
            id=stmt.id,
            account_id=stmt.account_id,
            currency=stmt.currency,
            statement_date=stmt.statement_date,
            due_date=stmt.due_date,
            current_version_id=stmt.current_version_id,
            created_at=stmt.created_at,
            updated_at=stmt.updated_at,
            current_version=StatementVersionOut.model_validate(ver),
            total_paid_minor=total_paid,
            remaining_minor=max(0, ver.amount_minor - total_paid),
        )
        return StatementDraftConfirmResponse(
            draft_id=draft.id,
            statement=stmt_detail,
            version=StatementVersionOut.model_validate(ver),
        )
    except NotFoundError as e:
        _not_found(e)
    except ConflictError as e:
        _conflict(e)


@router.post("/{draft_id}/reject", response_model=StatementDraftOut)
async def reject_draft(
    draft_id: uuid.UUID,
    data: StatementDraftRejectRequest,
    session: AsyncSession = Depends(get_session),
):
    """Reject a statement draft with reason."""
    try:
        return await svc.reject_draft(session, draft_id, reason=data.reason)
    except NotFoundError as e:
        _not_found(e)
    except ConflictError as e:
        _conflict(e)


@router.post("/parse-source/{source_id}", response_model=StatementDraftOut)
async def parse_email_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Parse an email source into a draft."""
    try:
        return await svc.parse_email_source(session, source_id)
    except NotFoundError as e:
        _not_found(e)
    except ConflictError as e:
        _conflict(e)


@router.post("/parse-all-pending", response_model=list[StatementDraftOut])
async def parse_all_pending(
    limit: int = Query(default=50, ge=1, le=100),
    reparse: bool = Query(default=False, description="Whether to reparse already processed email candidates"),
    session: AsyncSession = Depends(get_session),
):
    """Trigger parsing of all pending statement candidate email sources."""
    return await svc.parse_all_pending(session, limit=limit, reparse=reparse)
