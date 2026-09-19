"""API routes for mailboxes, manual IMAP sync triggering, mail jobs, and email sources (S3)."""

import asyncio
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cardcue_api.domain.schemas import (
    EmailSourceOut,
    MailJobOut,
    MailSyncTriggerRequest,
    MailSyncTriggerResponse,
    MailboxCreate,
    MailboxOut,
    MailboxUpdate,
)
from cardcue_api.persistence.database import async_session_factory, get_session
from cardcue_api.persistence.mail import Mailbox
from cardcue_api.services.mail_sync import (
    MailSyncConflictError,
    MailSyncService,
    MailboxNotFoundError,
)

router = APIRouter(prefix="/v1", tags=["mail"])


def _to_mailbox_out(mb: Mailbox) -> MailboxOut:
    return MailboxOut(
        id=mb.id,
        email_address=mb.email_address,
        imap_host=mb.imap_host,
        imap_port=mb.imap_port,
        use_ssl=mb.use_ssl,
        auth_token_masked="********",
        auth_type=mb.auth_type,
        is_active=mb.is_active,
        check_interval_minutes=mb.check_interval_minutes,
        last_checked_at=mb.last_checked_at,
        status=mb.status,
        error_message=mb.error_message,
        created_at=mb.created_at,
        updated_at=mb.updated_at,
    )


# ---------- Mailbox CRUD ----------

@router.post("/mailboxes", response_model=MailboxOut, status_code=201)
async def create_mailbox(
    data: MailboxCreate,
    session: AsyncSession = Depends(get_session),
):
    service = MailSyncService(session)
    try:
        mb = await service.create_mailbox(data)
        return _to_mailbox_out(mb)
    except MailSyncConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/mailboxes", response_model=list[MailboxOut])
async def list_mailboxes(session: AsyncSession = Depends(get_session)):
    service = MailSyncService(session)
    mailboxes = await service.list_mailboxes()
    return [_to_mailbox_out(mb) for mb in mailboxes]


@router.get("/mailboxes/{mailbox_id}", response_model=MailboxOut)
async def get_mailbox(mailbox_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    service = MailSyncService(session)
    try:
        mb = await service.get_mailbox(mailbox_id)
        return _to_mailbox_out(mb)
    except MailboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/mailboxes/{mailbox_id}", response_model=MailboxOut)
async def update_mailbox(
    mailbox_id: uuid.UUID,
    data: MailboxUpdate,
    session: AsyncSession = Depends(get_session),
):
    service = MailSyncService(session)
    try:
        mb = await service.update_mailbox(mailbox_id, data)
        return _to_mailbox_out(mb)
    except MailboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/mailboxes/{mailbox_id}", status_code=204)
async def delete_mailbox(mailbox_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    service = MailSyncService(session)
    try:
        await service.delete_mailbox(mailbox_id)
    except MailboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/mailboxes/{mailbox_id}/test-connection")
async def test_mailbox_connection(mailbox_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    service = MailSyncService(session)
    try:
        await service.test_connection(mailbox_id)
        return {"success": True, "message": "Connection and credentials verified"}
    except MailboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection test failed: {e}")


# ---------- Sync Trigger & Job Endpoints (S3-07) ----------

async def _run_sync_task(mailbox_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        service = MailSyncService(session)
        try:
            await service.sync_mailbox(mailbox_id=mailbox_id, trigger_type="manual")
        except Exception:
            pass


@router.post("/mail/sync-now", response_model=MailSyncTriggerResponse)
async def trigger_mail_sync(
    body: MailSyncTriggerRequest | None = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    session: AsyncSession = Depends(get_session),
):
    service = MailSyncService(session)
    targets = []
    if body and body.mailbox_id:
        try:
            mb = await service.get_mailbox(body.mailbox_id)
            targets.append(mb)
        except MailboxNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
    else:
        mailboxes = await service.list_mailboxes()
        targets = [mb for mb in mailboxes if mb.is_active and mb.status != "disabled"]

    if not targets:
        return MailSyncTriggerResponse(job_ids=[], message="No active mailboxes to sync")

    job_ids = []
    for mb in targets:
        # Pre-create running job or dispatch background task
        try:
            job = await service.sync_mailbox(mailbox_id=mb.id, trigger_type="manual")
            job_ids.append(job.id)
        except MailSyncConflictError:
            # Already running, fetch existing running job ID
            jobs = await service.list_jobs(mailbox_id=mb.id, limit=1)
            if jobs:
                job_ids.append(jobs[0].id)
        except Exception as e:
            # Let other mailboxes continue, record the error in job
            jobs = await service.list_jobs(mailbox_id=mb.id, limit=1)
            if jobs:
                job_ids.append(jobs[0].id)

    return MailSyncTriggerResponse(
        job_ids=job_ids,
        message=f"Sync executed for {len(job_ids)} mailbox(es)",
    )


@router.get("/mail/jobs", response_model=list[MailJobOut])
async def list_mail_jobs(
    mailbox_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    service = MailSyncService(session)
    jobs = await service.list_jobs(mailbox_id=mailbox_id, limit=limit)
    return [MailJobOut.model_validate(j) for j in jobs]


@router.get("/mail/jobs/{job_id}", response_model=MailJobOut)
async def get_mail_job(job_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    service = MailSyncService(session)
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return MailJobOut.model_validate(job)


# ---------- Email Sources & Protected Storage (S3-05) ----------

@router.get("/mail/sources", response_model=list[EmailSourceOut])
async def list_email_sources(
    mailbox_id: uuid.UUID | None = None,
    is_statement_candidate: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    service = MailSyncService(session)
    sources = await service.list_email_sources(
        mailbox_id=mailbox_id,
        is_statement_candidate=is_statement_candidate,
        limit=limit,
    )
    return [EmailSourceOut.model_validate(s) for s in sources]
