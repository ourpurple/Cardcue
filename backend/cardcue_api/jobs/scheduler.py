"""Scheduler only enqueues work; it never makes IMAP/model requests."""
import asyncio
from datetime import timedelta
from sqlalchemy import select
from cardcue_api.admin.jobs import enqueue
from cardcue_api.admin.schemas import JobCreate
from cardcue_api.admin.security import now
from cardcue_api.config import settings
from cardcue_api.jobs.worker import heartbeat
from cardcue_api.persistence import Mailbox
from cardcue_api.persistence.database import async_session_factory

class MailScheduler:
    def __init__(self, session_factory=None):
        self.session_factory = session_factory or async_session_factory

    async def run_once(self):
        count = 0
        async with self.session_factory() as s:
            rows = list((await s.execute(select(Mailbox).where(Mailbox.is_active.is_(True)))).scalars())
            for row in rows:
                last = row.last_attempt_at or row.last_checked_at
                if last is None or now()-last >= timedelta(minutes=row.check_interval_minutes):
                    await enqueue(s, JobCreate(kind="sync", target_id=row.id))
                    count += 1
            await s.commit()
        return count

async def main():
    settings.validate_production()
    scheduler = MailScheduler()
    while True:
        await scheduler.run_once()
        await heartbeat("scheduler")
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
