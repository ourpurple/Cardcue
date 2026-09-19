"""Independent background scheduler for recurring IMAP synchronization jobs."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import signal
import sys
from typing import Any

from sqlalchemy import select

from cardcue_api.persistence.database import async_session_factory
from cardcue_api.persistence.mail import Mailbox
from cardcue_api.services.mail_sync import MailSyncConflictError, MailSyncService

logger = logging.getLogger(__name__)


class MailScheduler:
    """Recurring scheduler that checks due mailboxes and triggers IMAP synchronization."""

    def __init__(self, session_factory=None):
        self.session_factory = session_factory or async_session_factory
        self._stop_event = asyncio.Event()

    async def check_due_mailboxes(self) -> list[Mailbox]:
        """Find mailboxes that are active and due for checking."""
        async with self.session_factory() as session:
            now = datetime.now(timezone.utc)
            stmt = select(Mailbox).where(
                Mailbox.is_active.is_(True),
                Mailbox.status != "disabled",
            )
            result = await session.execute(stmt)
            mailboxes = list(result.scalars().all())

            due = []
            for mb in mailboxes:
                if mb.last_checked_at is None:
                    due.append(mb)
                else:
                    elapsed = now - mb.last_checked_at
                    if elapsed >= timedelta(minutes=mb.check_interval_minutes):
                        due.append(mb)
            return due

    async def run_once(self, imap_client_override: Any = None) -> int:
        """Run a single check cycle over all due mailboxes. Returns count of synced mailboxes."""
        due_mailboxes = await self.check_due_mailboxes()
        synced_count = 0
        for mb in due_mailboxes:
            async with self.session_factory() as session:
                service = MailSyncService(session)
                try:
                    logger.info("Scheduler triggering sync for mailbox %s", mb.email_address)
                    await service.sync_mailbox(
                        mailbox_id=mb.id,
                        trigger_type="scheduled",
                        client_override=imap_client_override,
                    )
                    synced_count += 1
                except MailSyncConflictError:
                    logger.warning("Mailbox %s already has a running job, skipping cycle", mb.email_address)
                except Exception as e:
                    logger.error("Failed to sync mailbox %s in scheduler: %s", mb.email_address, e)
        return synced_count

    async def start(self, poll_interval_seconds: int = 60) -> None:
        """Run scheduler loop until stop() is called."""
        logger.info("Starting MailScheduler loop (poll interval: %ds)", poll_interval_seconds)
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except Exception as e:
                logger.error("Unhandled error in MailScheduler loop: %s", e)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=poll_interval_seconds)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        """Signal the scheduler to stop."""
        self._stop_event.set()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    scheduler = MailScheduler()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, scheduler.stop)
        except NotImplementedError:
            # Signal handling on Windows
            pass

    try:
        await scheduler.start(poll_interval_seconds=30)
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
