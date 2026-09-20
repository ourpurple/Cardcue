"""Durable queue shared by manual requests and scheduler."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from cardcue_api.admin.models import AdminJob, RuntimeSettings
from cardcue_api.admin.schemas import JobCreate
from cardcue_api.admin.security import require_admin, audit, now
from cardcue_api.persistence import Mailbox, EmailSource
from cardcue_api.persistence.database import get_session

router = APIRouter(prefix="/v1/admin/jobs", dependencies=[Depends(require_admin)])

def public_job(row):
    return {k: getattr(row, k) for k in ("id", "kind", "target_id", "status", "attempts", "cancel_requested", "result", "error_code", "created_at", "started_at", "finished_at")}

async def enqueue(session, data: JobCreate, actor="scheduler"):
    cls = Mailbox if data.kind == "sync" else EmailSource
    target = (await session.execute(select(cls).where(cls.id == data.target_id).with_for_update())).scalar_one_or_none()
    if not target:
        raise HTTPException(404, "任务对象不存在")
    if data.kind == "sync" and not target.is_active:
        raise HTTPException(409, "邮箱未启用；请先测试并启用")
    if data.kind == "parse" and (not target.raw_storage_path or target.parse_status in ("ignored", "duplicate")):
        raise HTTPException(409, "邮件正文不可用或已忽略")
    current = (await session.execute(select(AdminJob).where(AdminJob.kind == data.kind,
        AdminJob.target_id == data.target_id, AdminJob.status.in_(["queued", "running"])))).scalars().first()
    if current:
        return current
    payload = data.model_dump(mode="json")
    if data.kind == "parse":
        state = await session.get(RuntimeSettings, "model")
        revision_id = (state.value if state else {}).get("revision_id")
        if revision_id and not data.allow_external:
            raise HTTPException(409, "需明确同意将邮件内容发送到配置的模型服务")
        payload["model_revision_id"] = revision_id
        if target.parse_status == "failed":
            target.parse_status = "pending"
            target.error_message = None
    job = AdminJob(kind=data.kind, target_id=data.target_id, payload=payload)
    session.add(job)
    await session.flush()
    await audit(session, actor, "job_enqueued", job.id, {"kind": data.kind})
    return job

@router.post("", status_code=202)
async def create(data: JobCreate, actor=Depends(require_admin), session=Depends(get_session)):
    return public_job(await enqueue(session, data, actor))

@router.get("")
async def jobs(page: int = Query(1, ge=1), size: int = Query(30, ge=1, le=100), session=Depends(get_session)):
    total = (await session.execute(select(func.count()).select_from(AdminJob))).scalar_one()
    rows = (await session.execute(select(AdminJob).order_by(AdminJob.created_at.desc()).offset((page-1)*size).limit(size))).scalars()
    return {"items": [public_job(r) for r in rows], "total": total}

@router.post("/{identifier}/cancel")
async def cancel(identifier: uuid.UUID, actor=Depends(require_admin), session=Depends(get_session)):
    row = (await session.execute(select(AdminJob).where(AdminJob.id == identifier).with_for_update())).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "任务不存在")
    if row.status in ("queued", "running"):
        row.cancel_requested = True
        if row.status == "queued":
            row.status, row.finished_at = "cancelled", now()
    await audit(session, actor, "job_cancel_requested", identifier)
    return public_job(row)
