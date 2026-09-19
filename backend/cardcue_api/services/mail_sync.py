"""Service layer for mailbox management, IMAP synchronization, deduplication, and email storage."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cardcue_api.domain.schemas import MailboxCreate, MailboxUpdate
from cardcue_api.mail.classifier import classify_email
from cardcue_api.mail.client import (
    ImapAuthenticationError,
    ImapClientError,
    ReadOnlyImapClient,
)
from cardcue_api.mail.crypto import decrypt_token, encrypt_token
from cardcue_api.mail.parser import parse_email_bytes
from cardcue_api.mail.storage import MailStorageManager
from cardcue_api.persistence.mail import (
    EmailAttachment,
    EmailSource,
    MailCursor,
    MailJob,
    Mailbox,
)

logger = logging.getLogger(__name__)


class MailboxNotFoundError(Exception):
    pass


class MailSyncConflictError(Exception):
    pass


class MailSyncService:
    def __init__(self, session: AsyncSession, storage_manager: MailStorageManager | None = None):
        self.session = session
        self.storage = storage_manager or MailStorageManager()

    async def create_mailbox(self, data: MailboxCreate) -> Mailbox:
        """Create a new mailbox with encrypted credentials."""
        existing = await self.session.execute(
            select(Mailbox).where(Mailbox.email_address == data.email_address)
        )
        if existing.scalar_one_or_none():
            raise MailSyncConflictError(f"Mailbox with email {data.email_address} already exists")

        encrypted_token = encrypt_token(data.auth_token)
        mailbox = Mailbox(
            email_address=data.email_address,
            imap_host=data.imap_host,
            imap_port=data.imap_port,
            use_ssl=data.use_ssl,
            encrypted_auth_token=encrypted_token,
            auth_type=data.auth_type,
            is_active=data.is_active,
            check_interval_minutes=data.check_interval_minutes,
            status="active",
        )
        self.session.add(mailbox)
        await self.session.commit()
        await self.session.refresh(mailbox)
        return mailbox

    async def get_mailbox(self, mailbox_id: uuid.UUID) -> Mailbox:
        mailbox = await self.session.get(Mailbox, mailbox_id)
        if not mailbox:
            raise MailboxNotFoundError(f"Mailbox {mailbox_id} not found")
        return mailbox

    async def list_mailboxes(self) -> list[Mailbox]:
        result = await self.session.execute(select(Mailbox).order_by(Mailbox.created_at.desc()))
        return list(result.scalars().all())

    async def update_mailbox(self, mailbox_id: uuid.UUID, data: MailboxUpdate) -> Mailbox:
        mailbox = await self.get_mailbox(mailbox_id)
        if data.imap_host is not None:
            mailbox.imap_host = data.imap_host
        if data.imap_port is not None:
            mailbox.imap_port = data.imap_port
        if data.use_ssl is not None:
            mailbox.use_ssl = data.use_ssl
        if data.auth_token is not None:
            mailbox.encrypted_auth_token = encrypt_token(data.auth_token)
        if data.is_active is not None:
            mailbox.is_active = data.is_active
        if data.check_interval_minutes is not None:
            mailbox.check_interval_minutes = data.check_interval_minutes
        if data.status is not None:
            mailbox.status = data.status

        await self.session.commit()
        await self.session.refresh(mailbox)
        return mailbox

    async def delete_mailbox(self, mailbox_id: uuid.UUID) -> None:
        mailbox = await self.get_mailbox(mailbox_id)
        await self.session.delete(mailbox)
        await self.session.commit()

    async def test_connection(self, mailbox_id: uuid.UUID, client_override: Any = None) -> bool:
        """Test IMAP connection and login for a configured mailbox."""
        mailbox = await self.get_mailbox(mailbox_id)
        if client_override:
            client_override.connect()
            client_override.disconnect()
            return True

        plain_token = decrypt_token(mailbox.encrypted_auth_token)
        client = ReadOnlyImapClient(
            host=mailbox.imap_host,
            port=mailbox.imap_port,
            username=mailbox.email_address,
            password=plain_token,
            use_ssl=mailbox.use_ssl,
        )
        try:
            with client:
                client.select_folder("INBOX")
            mailbox.status = "active"
            mailbox.error_message = None
            await self.session.commit()
            return True
        except Exception as e:
            mailbox.status = "error"
            mailbox.error_message = "connection_failed"
            await self.session.commit()
            raise

    async def sync_mailbox(self, mailbox_id, trigger_type="manual", client_override=None,
                           folder="INBOX", since_date=None, progress=None):
        import asyncio
        import inspect
        from datetime import timedelta
        mailbox = await self.get_mailbox(mailbox_id)
        config = mailbox.settings_json or {}
        folder = config.get("folder", folder)
        running = (await self.session.execute(select(MailJob).where(MailJob.mailbox_id == mailbox_id, MailJob.status == "running"))).scalars().first()
        if running:
            raise MailSyncConflictError("Mailbox already has a running job")
        job = MailJob(mailbox_id=mailbox_id, trigger_type=trigger_type, status="running", started_at=datetime.now(timezone.utc))
        self.session.add(job)
        mailbox.last_attempt_at = datetime.now(timezone.utc)
        await self.session.commit()
        job_id = job.id
        client = client_override or ReadOnlyImapClient(host=mailbox.imap_host, port=mailbox.imap_port,
            username=config.get("username") or mailbox.email_address,
            password=decrypt_token(mailbox.encrypted_auth_token), use_ssl=mailbox.use_ssl)
        async def call(method, *args, **kwargs):
            return await asyncio.to_thread(method, *args, **kwargs)
        try:
            if not hasattr(client, "_is_mock"):
                await call(client.connect)
            validity, _, _ = await call(client.get_folder_status, folder)
            cursor = (await self.session.execute(select(MailCursor).where(MailCursor.mailbox_id == mailbox_id, MailCursor.folder == folder))).scalar_one_or_none()
            if not cursor:
                cursor = MailCursor(mailbox_id=mailbox_id, folder=folder, uidvalidity=validity, last_uid=0)
                self.session.add(cursor)
            elif cursor.uidvalidity != validity:
                cursor.last_uid, cursor.uidvalidity = 0, validity
            # An explicit backfill does not change the incremental cursor backwards.
            start_uid = 0 if since_date is not None else cursor.last_uid
            cutoff = since_date
            if cutoff is None and cursor.last_uid == 0:
                cutoff = (datetime.now(timezone.utc) - timedelta(days=config.get("since_days", 90))).date()
            kwargs = {"folder": folder}
            if "since_date" in inspect.signature(client.search_uids_since).parameters:
                kwargs["since_date"] = cutoff
            uids = await call(client.search_uids_since, start_uid, **kwargs)
            known = set((await self.session.execute(select(EmailSource.uid).where(EmailSource.mailbox_id == mailbox_id,
                EmailSource.folder == folder, EmailSource.uidvalidity == validity))).scalars())
            uids = [uid for uid in sorted(set(uids)) if uid not in known][:config.get("max_messages", 100)]
            for uid in uids:
                if progress and not await progress({"checked": job.emails_checked, "fetched": job.emails_fetched}):
                    job.status = "cancelled"
                    break
                job.emails_checked += 1
                try:
                    raw = await call(client.fetch_email_bytes, uid, folder=folder)
                    parsed = parse_email_bytes(raw)
                    candidate, _ = classify_email(parsed.sender, parsed.subject, parsed.body_text)
                    sender_filter, subject_filter = config.get("sender_filter", ""), config.get("subject_filter", "")
                    if sender_filter and not any(term.strip().lower() in parsed.sender.lower() for term in sender_filter.split(",") if term.strip()):
                        candidate = False
                    if subject_filter and not any(term.strip().lower() in parsed.subject.lower() for term in subject_filter.split(",") if term.strip()):
                        candidate = False
                    existing_hash = (await self.session.execute(select(EmailSource.id).where(EmailSource.mailbox_id == mailbox_id,
                        EmailSource.body_hash == parsed.body_hash, EmailSource.subject == parsed.subject,
                        EmailSource.sender == parsed.sender, EmailSource.email_date == parsed.email_date).limit(1))).first()
                    source_id = uuid.uuid4()
                    keep = candidate or config.get("keep_non_candidates", False)
                    source = EmailSource(id=source_id, mailbox_id=mailbox_id, folder=folder, uid=uid, uidvalidity=validity,
                        message_id=parsed.message_id, subject=parsed.subject[:500], sender=parsed.sender[:255], recipient=parsed.recipient[:255],
                        email_date=parsed.email_date, body_hash=parsed.body_hash, has_attachments=bool(parsed.attachments),
                        is_statement_candidate=candidate, parse_status="duplicate" if existing_hash else ("pending" if candidate else "ignored"))
                    self.session.add(source)
                    if keep and not existing_hash:
                        source.raw_storage_path = self.storage.save_raw_email(mailbox_id, source_id, raw, parsed.email_date)
                        for att in parsed.attachments:
                            if att.size_bytes > config.get("max_attachment_mb", 10) * 1024 * 1024:
                                source.error_message = "attachment_exceeds_limit"
                                continue
                            path = self.storage.save_attachment(mailbox_id, source_id, att.filename, att.payload_bytes, parsed.email_date)
                            self.session.add(EmailAttachment(email_source_id=source_id, filename=att.filename,
                                content_type=att.content_type, size_bytes=att.size_bytes, storage_path=path))
                        job.emails_fetched += 1
                    if candidate and not existing_hash:
                        job.statement_candidates += 1
                    cursor.last_uid = max(cursor.last_uid, uid)
                    await self.session.commit()
                except Exception:
                    # Preserve the checkpoint but do not advance past an unread message. Manual retry can recover it.
                    await self.session.rollback()
                    job = await self.session.get(MailJob, job_id)
                    job.status, job.error_message = "failed", "message_processing_failed"
                    break
            if job.status == "running":
                job.status = "completed"
            job.finished_at = datetime.now(timezone.utc)
            mailbox = await self.session.get(Mailbox, mailbox_id, populate_existing=True)
            if job.status == "completed":
                mailbox.last_checked_at = datetime.now(timezone.utc)
                mailbox.error_message = None
                if mailbox.is_active:
                    mailbox.status = "active"
            await self.session.commit()
            return job
        except Exception as exc:
            await self.session.rollback()
            job = await self.session.get(MailJob, job_id)
            mailbox = await self.session.get(Mailbox, mailbox_id)
            job.status, job.finished_at = "failed", datetime.now(timezone.utc)
            job.error_message = "imap_authentication_failed" if isinstance(exc, ImapAuthenticationError) else "imap_sync_failed"
            mailbox.error_message = job.error_message
            if mailbox.is_active:
                mailbox.status = "auth_error" if isinstance(exc, ImapAuthenticationError) else "sync_error"
            await self.session.commit()
            raise RuntimeError(job.error_message) from None
        finally:
            if not hasattr(client, "_is_mock"):
                await call(client.disconnect)

    async def list_jobs(self, mailbox_id: uuid.UUID | None = None, limit: int = 50) -> list[MailJob]:
        stmt = select(MailJob).order_by(desc(MailJob.created_at)).limit(limit)
        if mailbox_id:
            stmt = stmt.where(MailJob.mailbox_id == mailbox_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_job(self, job_id: uuid.UUID) -> MailJob | None:
        return await self.session.get(MailJob, job_id)

    async def list_email_sources(
        self,
        mailbox_id: uuid.UUID | None = None,
        is_statement_candidate: bool | None = None,
        limit: int = 50,
    ) -> list[EmailSource]:
        stmt = (
            select(EmailSource)
            .options(selectinload(EmailSource.attachments))
            .order_by(desc(EmailSource.email_date))
            .limit(limit)
        )
        if mailbox_id:
            stmt = stmt.where(EmailSource.mailbox_id == mailbox_id)
        if is_statement_candidate is not None:
            stmt = stmt.where(EmailSource.is_statement_candidate == is_statement_candidate)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
