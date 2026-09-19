"""R1-04 / R1-05: Backup-restore drill and backend independence tests.

R1-04: After simulating a database restore (sequence reset), clients whose cursor
exceeds the new max sequence get CURSOR_OUT_OF_RANGE and must bootstrap. A new
bootstrap after restore yields valid data and a lower cursor.

R1-05: Backend email/parsing services operate independently of app lifecycle.
The scheduler and draft endpoints don't require a paired device to function
on the server side (device token is only needed for client-facing sync endpoints).
"""

import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from cardcue_api.main import app


@pytest.fixture(scope="function")
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _pair_and_headers(client: AsyncClient, name: str = "R1测试设备") -> tuple[dict, dict]:
    res = await client.post("/v1/devices/pair", json={"name": name})
    assert res.status_code == 201
    data = res.json()
    return data, {"Authorization": f"Bearer {data['token']}"}


# ── R1-04: Backup Restore Drill ──

async def test_restore_triggers_cursor_out_of_range_and_forces_full_sync(client: AsyncClient):
    """Simulate restore: after creating data and advancing the cursor, a client
    whose cursor exceeds the restored max sequence gets CURSOR_OUT_OF_RANGE.
    A subsequent bootstrap returns valid data with a usable cursor."""
    dev, headers = await _pair_and_headers(client, "备份恢复测试设备")

    # 1. Create some data to advance the change_log sequence.
    suffix = uuid.uuid4().hex[:6]
    acct = (await client.post("/v1/accounts", json={"bank": f"恢复测试银行_{suffix}"})).json()
    stmt = (await client.post("/v1/statements", json={
        "account_id": acct["id"],
        "currency": "CNY",
        "statement_date": "2026-09-01",
        "due_date": "2026-09-25",
        "amount_minor": 100000,
        "minimum_minor": 10000,
    })).json()

    # 2. Get current cursor through bootstrap.
    boot = (await client.get("/v1/sync/bootstrap", headers=headers)).json()
    pre_restore_cursor = boot["cursor"]
    assert pre_restore_cursor > 0

    # 3. Simulate "restore": client cursor is now far ahead of what
    # the server sequence would be after a restore. We use a very
    # high cursor value to simulate this.
    future_cursor = pre_restore_cursor + 1_000_000

    res = await client.get(f"/v1/sync/changes?cursor={future_cursor}", headers=headers)
    assert res.status_code == 409, f"Expected CURSOR_OUT_OF_RANGE, got {res.status_code}"
    err = res.json()
    assert "CURSOR_OUT_OF_RANGE" in str(err)

    # 4. After receiving CURSOR_OUT_OF_RANGE, client does a full bootstrap.
    boot2 = (await client.get("/v1/sync/bootstrap", headers=headers)).json()
    assert boot2["cursor"] >= 0
    assert isinstance(boot2["accounts"], list)
    assert isinstance(boot2["statements"], list)

    # 5. Incremental sync from new cursor should work cleanly.
    changes = (await client.get(f"/v1/sync/changes?cursor={boot2['cursor']}", headers=headers)).json()
    assert changes["cursor"] == boot2["cursor"]  # no new changes
    assert len(changes["changes"]) == 0


# ── R1-05: Backend Independence ──

async def test_health_and_capabilities_independent_of_devices(client: AsyncClient):
    """Health and capabilities endpoints work without any device paired."""
    h = await client.get("/health")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"

    c = await client.get("/v1/capabilities")
    assert c.status_code == 200
    caps = c.json()
    assert caps["email_sync"] is True
    assert caps["statement_parsing"] is True


async def test_backend_data_creation_without_active_app_session(client: AsyncClient):
    """Server can create accounts, statements, and payments entirely server-side,
    independent of any app session. This simulates the backend continuing to
    process email-derived data while the app is closed."""
    suffix = uuid.uuid4().hex[:6]

    # Create account (as if discovered from email)
    acct = (await client.post("/v1/accounts", json={
        "bank": f"后台独立测试银行_{suffix}",
        "alias": "后台自动创建",
    })).json()
    assert "id" in acct

    # Create statement (as if parsed from email)
    stmt = (await client.post("/v1/statements", json={
        "account_id": acct["id"],
        "currency": "CNY",
        "statement_date": "2026-09-01",
        "due_date": "2026-09-25",
        "amount_minor": 250000,
        "minimum_minor": 25000,
    })).json()
    assert "id" in stmt

    # Now a device pairs and bootstraps — it should see the data.
    dev, headers = await _pair_and_headers(client, f"后启动设备_{suffix}")
    boot = (await client.get("/v1/sync/bootstrap", headers=headers)).json()
    acct_ids = [a["id"] for a in boot["accounts"]]
    stmt_ids = [s["id"] for s in boot["statements"]]
    assert acct["id"] in acct_ids, "Account created by backend should appear in bootstrap"
    assert stmt["id"] in stmt_ids, "Statement created by backend should appear in bootstrap"


async def test_payment_consistency_across_both_ends(client: AsyncClient):
    """Payment made via sync API and then checked via billing API yields consistent results."""
    suffix = uuid.uuid4().hex[:6]
    dev, headers = await _pair_and_headers(client, f"一致性测试_{suffix}")

    acct = (await client.post("/v1/accounts", json={"bank": f"一致性银行_{suffix}"})).json()
    stmt = (await client.post("/v1/statements", json={
        "account_id": acct["id"],
        "currency": "CNY",
        "statement_date": "2026-09-01",
        "due_date": "2026-09-25",
        "amount_minor": 80000,
        "minimum_minor": 8000,
    })).json()

    # Payment via sync endpoint (simulating app).
    pay = await client.post("/v1/sync/payments", json={
        "statement_id": stmt["id"],
        "amount_minor": 30000,
        "currency": "CNY",
        "note": "手机端还款",
    }, headers=headers)
    assert pay.status_code == 201
    pay_data = pay.json()
    assert pay_data["statement_detail"]["remaining_minor"] == 50000

    # Verify via billing API (simulating backend check).
    detail = (await client.get(f"/v1/statements/{stmt['id']}")).json()
    assert detail["remaining_minor"] == 50000
    assert detail["total_paid_minor"] == 30000

    # Revoke via sync endpoint (simulating app undo).
    rev = await client.post(
        f"/v1/sync/payments/{pay_data['payment']['id']}/revoke",
        json={"reason": "测试撤销"},
        headers=headers,
    )
    assert rev.status_code == 200
    assert rev.json()["statement_detail"]["remaining_minor"] == 80000

    # Verify billing API reflects the revocation.
    detail2 = (await client.get(f"/v1/statements/{stmt['id']}")).json()
    assert detail2["remaining_minor"] == 80000
    assert detail2["total_paid_minor"] == 0
