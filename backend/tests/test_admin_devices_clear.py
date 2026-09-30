"""Synthetic device cleanup tests: no user database or real credentials."""
import uuid
from datetime import timedelta
from types import SimpleNamespace as Row

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Delete

from cardcue_api.admin.business_api import clear_revoked_devices, router
from cardcue_api.admin.models import AdminUser, AuditEvent, WebSession
from cardcue_api.admin.security import Actor, authenticate, digest, now, COOKIE
from cardcue_api.persistence.database import get_session
from cardcue_api.persistence.device import Device


class Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class Session:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.queries = []
        self.added = []
        self.commits = 0
        self.web = Row(admin_id=uuid.uuid4(), expires_at=now() + timedelta(hours=1),
                       csrf_token="synthetic-csrf", verified_at=now())
        self.user = Row(id=self.web.admin_id, active=True)

    async def execute(self, query):
        self.queries.append(query)
        if isinstance(query, Delete):
            sql = str(query.compile(dialect=postgresql.dialect()))
            assert "DELETE FROM devices WHERE devices.status =" in sql
            assert "OR devices.revoked_at IS NOT NULL" in sql
            assert "RETURNING devices.id" in sql
            assert query.compile().params["status_1"] == "revoked"
            removed = [r for r in self.rows if r.status == "revoked" or r.revoked_at is not None]
            self.rows = [r for r in self.rows if r not in removed]
            return Result([r.id for r in removed])
        return Result(self.rows)

    async def get(self, model, identifier):
        if model is WebSession and identifier == digest("synthetic-cookie"):
            return self.web
        if model is AdminUser and identifier == self.user.id:
            return self.user
        return None

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.commits += 1


def device(status="active", revoked_at=None):
    return Device(id=uuid.uuid4(), name="Synthetic device", token_hash="synthetic-hash",
                  status=status, paired_at=now(), last_seen_at=None, revoked_at=revoked_at)


def make_app(session):
    app = FastAPI()
    app.include_router(router)

    async def fake_session():
        yield session

    app.dependency_overrides[get_session] = fake_session
    return app


@pytest.mark.asyncio
async def test_empty_cleanup_is_idempotent_and_audited():
    session = Session()
    for _ in range(2):
        assert await clear_revoked_devices(actor="synthetic-admin", session=session) == {"deleted_count": 0}
    assert len(session.added) == session.commits == 2
    assert all(event.detail == {"deleted_count": 0} for event in session.added)


@pytest.mark.asyncio
async def test_cleanup_only_revoked_rows_and_preserves_unknown_status():
    retained = [device(), device("pending"), device("disabled")]
    session = Session(retained + [device("revoked", now()), device("revoked"), device("active", now())])
    assert await clear_revoked_devices(actor=Actor("synthetic-admin", "admin"), session=session) == {"deleted_count": 3}
    assert session.rows == retained
    assert len(session.queries) == session.commits == 1
    event = session.added[0]
    assert isinstance(event, AuditEvent)
    assert event.actor == "synthetic-admin"
    assert event.action == "revoked_devices_cleared"
    assert event.detail == {"deleted_count": 3}
    assert event.target is None
    assert "synthetic-hash" not in str(event.detail)
    sql = str(session.queries[0].compile(dialect=postgresql.dialect()))
    assert not any(name in sql for name in ("statements", "payments", "audit_events", "accounts"))


@pytest.mark.asyncio
async def test_cleanup_is_not_limited_to_visible_page():
    active = device()
    session = Session([device("revoked") for _ in range(125)] + [active])
    assert await clear_revoked_devices(actor="synthetic-admin", session=session) == {"deleted_count": 125}
    assert session.rows == [active]
    sql = str(session.queries[0].compile(dialect=postgresql.dialect()))
    assert "LIMIT" not in sql and "OFFSET" not in sql


@pytest.mark.asyncio
async def test_cleanup_requires_login():
    session = Session([device("revoked")])
    async with AsyncClient(transport=ASGITransport(app=make_app(session)), base_url="http://test") as client:
        response = await client.post("/v1/admin/devices/clear-revoked")
    assert response.status_code == 401
    assert not session.queries and not session.added and not session.commits


@pytest.mark.asyncio
async def test_device_role_cannot_clear_devices():
    session = Session([device("revoked")])
    app = make_app(session)
    app.dependency_overrides[authenticate] = lambda: Actor("synthetic-device", "device")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/admin/devices/clear-revoked")
    assert response.status_code == 403
    assert not session.queries and not session.added and not session.commits


@pytest.mark.asyncio
@pytest.mark.parametrize("csrf,expected", [(None, 403), ("wrong-csrf", 403), ("synthetic-csrf", 200)])
async def test_cleanup_enforces_csrf(csrf, expected):
    active = device()
    session = Session([active, device("revoked")])
    headers = {"origin": "http://localhost:5173"}
    if csrf:
        headers["x-csrf-token"] = csrf
    async with AsyncClient(transport=ASGITransport(app=make_app(session)), base_url="http://test",
                           cookies={COOKIE: "synthetic-cookie"}) as client:
        response = await client.post("/v1/admin/devices/clear-revoked", headers=headers)
    assert response.status_code == expected, response.text
    if expected == 200:
        assert response.json() == {"deleted_count": 1}
        assert session.rows == [active]
    else:
        assert not session.queries and not session.added and not session.commits


@pytest.mark.asyncio
async def test_device_list_matches_frontend_contract_and_excludes_token_hash():
    row = device()
    session = Session([row])
    async with AsyncClient(transport=ASGITransport(app=make_app(session)), base_url="http://test",
                           cookies={COOKIE: "synthetic-cookie"}) as client:
        response = await client.get("/v1/admin/devices")
    assert response.status_code == 200, response.text
    item = response.json()[0]
    assert set(item) == {"id", "name", "status", "paired_at", "last_seen_at", "revoked_at"}
    assert item["status"] == "active"
    assert item["name"] == row.name
    assert item["paired_at"] == row.paired_at.isoformat().replace("+00:00", "Z")
    assert "token_hash" not in item
