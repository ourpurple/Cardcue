"""One worker owns a PostgreSQL session advisory lock; no overlapping consumers."""
import asyncio
import uuid
from datetime import timedelta
from sqlalchemy import select, text, update
from cardcue_api.config import settings
from cardcue_api.admin.models import AdminJob, RuntimeSettings, ModelRevision
from cardcue_api.admin.jobs import enqueue
from cardcue_api.admin.schemas import JobCreate
from cardcue_api.admin.security import now
from cardcue_api.persistence import Mailbox, MailJob, EmailSource
from cardcue_api.persistence.database import engine, async_session_factory
from cardcue_api.services.mail_sync import MailSyncService
from cardcue_api.services.drafts import DraftService
from cardcue_api.admin.model_runtime import ManagedExtractor

async def heartbeat(key):
    from sqlalchemy.dialects.postgresql import insert
    async with async_session_factory() as s:
        await s.execute(insert(RuntimeSettings).values(key=key, value={"at": now().isoformat()}).on_conflict_do_update(index_elements=[RuntimeSettings.key], set_={"value": {"at": now().isoformat()}}))
        await s.commit()

async def run_job(identifier):
    async with async_session_factory() as s:
        job = await s.get(AdminJob, identifier)
        kind, target_id, payload = job.kind, job.target_id, job.payload
        async def progress(result):
            async with async_session_factory() as check:
                current = await check.get(AdminJob, identifier)
                current.lease_until = now() + timedelta(minutes=5)
                current.result = result
                await check.commit()
                return not current.cancel_requested
        try:
            if not await progress({}):
                status, result = "cancelled", {}
            elif kind == "sync":
                since = (now()-timedelta(days=payload["since_days"])).date() if payload.get("since_days") else None
                mail_job = await MailSyncService(s).sync_mailbox(target_id, since_date=since, progress=progress)
                status = "succeeded" if mail_job.status == "completed" else mail_job.status
                result = {"mail_job_id": str(mail_job.id), "fetched": mail_job.emails_fetched}
                mailbox = await s.get(Mailbox, target_id)
                if mailbox.is_active and (mailbox.settings_json or {}).get("auto_parse"):
                    sources = list((await s.execute(select(EmailSource).where(EmailSource.mailbox_id == target_id, EmailSource.parse_status == "pending", EmailSource.is_statement_candidate.is_(True)).limit(100))).scalars())
                    for source in sources:
                        await enqueue(s, JobCreate(kind="parse", target_id=source.id, allow_external=True), "worker")
                    await s.commit()
            else:
                revision = await s.get(ModelRevision, uuid.UUID(payload["model_revision_id"])) if payload.get("model_revision_id") else None
                service = DraftService()
                service.model_extractor = ManagedExtractor(revision, force=payload.get("force", False))
                draft = await service.parse_email_source(s, target_id)
                status, result = "succeeded", {"draft_id": str(draft.id)}
            job = await s.get(AdminJob, identifier, populate_existing=True)
            job.status, job.result, job.finished_at = status, result, now()
            job.lease_until = None
            await s.commit()
        except Exception as exc:
            await s.rollback()
            job = await s.get(AdminJob, identifier, populate_existing=True)
            job.status, job.error_code, job.finished_at = "failed", "processing_failed_or_outcome_unknown", now()
            job.lease_until = None
            if kind == "parse":
                source = await s.get(EmailSource, target_id)
                if source:
                    source.parse_status = "failed"
                    source.error_message = str(exc)[:500]
            await s.commit()

async def main():
    settings.validate_production()
    # Dedicated connection retains lock for lifetime of worker; never return it to pool while locked.
    async with engine.connect() as lock:
        if not (await lock.execute(text("SELECT pg_try_advisory_lock(72643001)"))).scalar():
            raise RuntimeError("worker_already_running")
        try:
            async with async_session_factory() as s:
                # Previous owner is gone. Never silently repeat a potentially billed model call.
                await s.execute(update(AdminJob).where(AdminJob.status == "running").values(status="failed", error_code="worker_interrupted_outcome_unknown", finished_at=now()))
                await s.execute(update(MailJob).where(MailJob.status == "running").values(status="failed", error_message="worker_interrupted", finished_at=now()))
                await s.commit()
            while True:
                await lock.execute(text("SELECT 1"))
                await heartbeat("worker")
                async with async_session_factory() as s:
                    job = (await s.execute(select(AdminJob).where(AdminJob.status == "queued", AdminJob.available_at <= now()).order_by(AdminJob.created_at).with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
                    identifier = None
                    if job:
                        identifier = job.id
                        job.status, job.started_at = "running", now()
                        job.attempts += 1
                        job.lease_until, job.lease_owner = now()+timedelta(minutes=5), "single-worker"
                    await s.commit()
                if identifier:
                    await run_job(identifier)
                else:
                    await asyncio.sleep(3)
        finally:
            await lock.execute(text("SELECT pg_advisory_unlock(72643001)"))

if __name__ == "__main__":
    asyncio.run(main())
