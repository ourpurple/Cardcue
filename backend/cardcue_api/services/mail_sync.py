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
            mailbox.error_message = str(e)
            await self.session.commit()
            raise

    async def sync_mailbox(
        self,
        mailbox_id: uuid.UUID,
        trigger_type: str = "manual",
        client_override: Any = None,
        folder: str = "INBOX",
    ) -> MailJob:
        """Perform synchronization for a mailbox with read-only safety, incremental cursor, and deduplication."""
        mailbox = await self.get_mailbox(mailbox_id)

        # Check concurrency guard: cannot run two jobs simultaneously for the same mailbox
        running_job_stmt = select(MailJob).where(
            MailJob.mailbox_id == mailbox_id,
            MailJob.status == "running",
        )
        running_job = (await self.session.execute(running_job_stmt)).scalar_one_or_none()
        if running_job:
            raise MailSyncConflictError(f"A sync job {running_job.id} is already running for mailbox {mailbox_id}")

        # Create running MailJob
        job = MailJob(
            mailbox_id=mailbox_id,
            trigger_type=trigger_type,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)

        plain_token = decrypt_token(mailbox.encrypted_auth_token)
        imap_client = client_override or ReadOnlyImapClient(
            host=mailbox.imap_host,
            port=mailbox.imap_port,
            username=mailbox.email_address,
            password=plain_token,
            use_ssl=mailbox.use_ssl,
        )

        try:
            # If not an injected mock context, connect
            if not hasattr(imap_client, "_is_mock"):
                imap_client.connect()

            # 1. Fetch folder status and check UIDVALIDITY
            uidvalidity, uidnext, total_messages = imap_client.get_folder_status(folder)

            cursor_stmt = select(MailCursor).where(
                MailCursor.mailbox_id == mailbox_id,
                MailCursor.folder == folder,
            )
            cursor = (await self.session.execute(cursor_stmt)).scalar_one_or_none()
            if not cursor:
                cursor = MailCursor(
                    mailbox_id=mailbox_id,
                    folder=folder,
                    uidvalidity=uidvalidity,
                    last_uid=0,
                )
                self.session.add(cursor)
                await self.session.flush()
            else:
                # UIDVALIDITY change indicates mailbox re-indexing or reset on server
                if cursor.uidvalidity > 0 and cursor.uidvalidity != uidvalidity:
                    logger.warning(
                        "UIDVALIDITY mismatch for mailbox %s folder %s (%d != %d). Resetting last_uid.",
                        mailbox_id,
                        folder,
                        cursor.uidvalidity,
                        uidvalidity,
                    )
                    cursor.last_uid = 0
                cursor.uidvalidity = uidvalidity

            # 2. Search new UIDs strictly > cursor.last_uid
            uids_to_fetch = imap_client.search_uids_since(cursor.last_uid, folder=folder)

            # 3. Fetch and process each email
            for uid in uids_to_fetch:
                job.emails_checked += 1

                # Check if this exact UID was already recorded
                existing_source = (
                    await self.session.execute(
                        select(EmailSource).where(
                            EmailSource.mailbox_id == mailbox_id,
                            EmailSource.folder == folder,
                            EmailSource.uidvalidity == uidvalidity,
                            EmailSource.uid == uid,
                        )
                    )
                ).scalar_one_or_none()

                if existing_source:
                    cursor.last_uid = max(cursor.last_uid, uid)
                    continue

                # Fetch bytes with read-only guarantee (BODY.PEEK)
                raw_bytes = imap_client.fetch_email_bytes(uid, folder=folder)
                job.emails_fetched += 1

                parsed = parse_email_bytes(raw_bytes)
                is_candidate, reason = classify_email(parsed.sender, parsed.subject, parsed.body_text)

                source_id = uuid.uuid4()
                # Persist raw email to disk
                raw_path = self.storage.save_raw_email(
                    mailbox_id=mailbox_id,
                    email_source_id=source_id,
                    raw_bytes=raw_bytes,
                    email_date=parsed.email_date,
                )

                email_source = EmailSource(
                    id=source_id,
                    mailbox_id=mailbox_id,
                    folder=folder,
                    uid=uid,
                    uidvalidity=uidvalidity,
                    message_id=parsed.message_id,
                    subject=parsed.subject,
                    sender=parsed.sender,
                    recipient=parsed.recipient,
                    email_date=parsed.email_date,
                    body_hash=parsed.body_hash,
                    raw_storage_path=raw_path,
                    has_attachments=len(parsed.attachments) > 0,
                    is_statement_candidate=is_candidate,
                    parse_status="pending",
                )
                self.session.add(email_source)

                # Persist attachments
                for att in parsed.attachments:
                    att_path = self.storage.save_attachment(
                        mailbox_id=mailbox_id,
                        email_source_id=source_id,
                        filename=att.filename,
                        payload_bytes=att.payload_bytes,
                        email_date=parsed.email_date,
                    )
                    email_att = EmailAttachment(
                        email_source_id=source_id,
                        filename=att.filename,
                        content_type=att.content_type,
                        size_bytes=att.size_bytes,
                        storage_path=att_path,
                    )
                    self.session.add(email_att)

                if is_candidate:
                    job.statement_candidates += 1

                cursor.last_uid = max(cursor.last_uid, uid)
                await self.session.flush()

            # Finish job successfully
            job.status = "completed"
            job.finished_at = datetime.now(timezone.utc)
            mailbox.last_checked_at = datetime.now(timezone.utc)
            mailbox.status = "active"
            mailbox.error_message = None
            await self.session.commit()
            await self.session.refresh(job)

        except Exception as e:
            logger.exception("Error syncing mailbox %s: %s", mailbox_id, e)
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.error_message = str(e)
            mailbox.error_message = str(e)
            if isinstance(e, (ImapAuthenticationError,)):
                mailbox.status = "auth_error"
            else:
                mailbox.status = "sync_error"
            await self.session.commit()
            await self.session.refresh(job)
            raise
        finally:
            if not hasattr(imap_client, "_is_mock"):
                try:
                    imap_client.disconnect()
                except Exception:
                    pass

        return job

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
