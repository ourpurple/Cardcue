"""Synthetic queue-clear tests; never connect to or clear a user database."""
import uuid
from datetime import timedelta
from types import SimpleNamespace as Row

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Delete

from cardcue_api.admin.jobs import clear_jobs, router
from cardcue_api.admin.models import AdminUser, AuditEvent, WebSession
from cardcue_api.admin.security import Actor, authenticate, digest, now, COOKIE
from cardcue_api.persistence.database import get_session


class Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class Session:
    def __init__(self, statuses=()):
        self.rows = [Row(id=uuid.uuid4(), status=status) for status in statuses]
        self.queries = []
        self.added = []
        self.after_snapshot = None
        self.web = Row(admin_id=uuid.uuid4(), expires_at=now() + timedelta(hours=1),
                       csrf_token="synthetic-csrf")
        self.user = Row(id=self.web.admin_id, active=True)

    async def execute(self, query):
        self.queries.append(query)
        if isinstance(query, Delete):
            identifiers = query.compile().params["id_1"]
            self.rows = [row for row in self.rows if row.id not in identifiers]
            return Result([])
        snapshot = list(self.rows)
        if self.after_snapshot:
            self.after_snapshot(self)
        return Result(snapshot)

    async def get(self, model, identifier):
        if model is WebSession and identifier == digest("synthetic-cookie"):
            return self.web
        if model is AdminUser and identifier == self.user.id:
            return self.user
        return None

    def add(self, row):
        self.added.append(row)


@pytest.mark.asyncio
async def test_clear_empty_queue_is_idempotent_and_audited():
    session = Session()
    for _ in range(2):
        assert await clear_jobs(actor="synthetic-admin", session=session) == {"deleted_count": 0}
    assert not any(isinstance(q, Delete) for q in session.queries)
    assert len(session.added) == 2
    assert all(event.action == "jobs_cleared" for event in session.added)


@pytest.mark.asyncio
async def test_clear_all_statuses_and_audit_without_business_data_changes():
    session = Session(["queued", "succeeded", "failed", "cancelled", "completed"])
    result = await clear_jobs(actor=Actor("synthetic-admin", "admin"), session=session)
    assert result == {"deleted_count": 5}
    assert session.rows == []
    assert len(session.added) == 1
    event = session.added[0]
    assert isinstance(event, AuditEvent)
    assert event.actor == "synthetic-admin"
    assert event.action == "jobs_cleared"
    assert event.detail == {"deleted_count": 5}
    for query in session.queries:
        sql = str(query.compile(dialect=postgresql.dialect()))
        assert "admin_jobs" in sql
        assert not any(table in sql for table in (
            "email_sources", "statement_drafts", "statements", "payments", "mailboxes", "mail_jobs"
        ))


@pytest.mark.asyncio
async def test_clear_covers_all_pages_with_bounded_delete_parameters():
    session = Session(["queued"] * 1001)
    assert await clear_jobs(actor="synthetic-admin", session=session) == {"deleted_count": 1001}
    deletes = [q for q in session.queries if isinstance(q, Delete)]
    assert [len(q.compile().params["id_1"]) for q in deletes] == [1000, 1]
    assert not session.rows


@pytest.mark.asyncio
@pytest.mark.parametrize("statuses", [
    ["running"], ["queued", "running", "failed"], ["queued"] * 21 + ["running"],
])
async def test_running_task_blocks_entire_clear_without_partial_deletion(statuses):
    session = Session(statuses)
    original = list(session.rows)
    with pytest.raises(HTTPException) as exc:
        await clear_jobs(actor="synthetic-admin", session=session)
    assert exc.value.status_code == 409
    assert "等待执行结束" in exc.value.detail
    assert session.rows == original
    assert len(session.queries) == 1
    assert not session.added


@pytest.mark.asyncio
async def test_clear_locks_unpaginated_snapshot_before_deleting():
    session = Session(["queued"])
    await clear_jobs(actor="synthetic-admin", session=session)
    query = session.queries[0]
    sql = str(query.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql
    assert "ORDER BY admin_jobs.id" in sql
    assert "SKIP LOCKED" not in sql
    assert "LIMIT" not in sql and "OFFSET" not in sql


@pytest.mark.asyncio
async def test_newly_scheduled_task_outside_snapshot_is_not_deleted():
    session = Session(["queued", "failed"])
    new_job = Row(id=uuid.uuid4(), status="queued")
    session.after_snapshot = lambda s: s.rows.append(new_job)
    assert await clear_jobs(actor="synthetic-admin", session=session) == {"deleted_count": 2}
    assert session.rows == [new_job]


def make_app(session):
    app = FastAPI()
    app.include_router(router)

    async def fake_session():
        yield session

    app.dependency_overrides[get_session] = fake_session
    return app


@pytest.mark.asyncio
async def test_clear_route_requires_login():
    session = Session(["queued"])
    async with AsyncClient(transport=ASGITransport(app=make_app(session)), base_url="http://test") as client:
        response = await client.post("/v1/admin/jobs/clear")
    assert response.status_code == 401
    assert not session.queries and not session.added


@pytest.mark.asyncio
async def test_clear_route_rejects_device_role():
    session = Session(["queued"])
    app = make_app(session)
    app.dependency_overrides[authenticate] = lambda: Actor("synthetic-device", "device")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/admin/jobs/clear")
    assert response.status_code == 403
    assert not session.queries and not session.added


@pytest.mark.asyncio
@pytest.mark.parametrize("csrf,expected_status", [(None, 403), ("wrong-csrf", 403), ("synthetic-csrf", 200)])
async def test_clear_route_enforces_admin_csrf(csrf, expected_status):
    session = Session(["queued", "failed"])
    headers = {"origin": "http://localhost:5173"}
    if csrf:
        headers["x-csrf-token"] = csrf
    async with AsyncClient(transport=ASGITransport(app=make_app(session)), base_url="http://test",
                           cookies={COOKIE: "synthetic-cookie"}) as client:
        response = await client.post("/v1/admin/jobs/clear", headers=headers)
    assert response.status_code == expected_status, response.text
    if expected_status == 200:
        assert response.json() == {"deleted_count": 2}
        assert not session.rows
    else:
        assert not session.queries and not session.added


@pytest.mark.asyncio
async def test_clear_route_returns_running_conflict():
    session = Session(["queued", "running"])
    app = make_app(session)
    app.dependency_overrides[authenticate] = lambda: Actor("synthetic-admin", "admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/admin/jobs/clear")
    assert response.status_code == 409
    assert len(session.rows) == 2
    assert not session.added
