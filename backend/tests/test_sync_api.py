"""S2 (SYNC-01 / SYNC-02) integration tests:
- Sync Bootstrap (full snapshot + baseline cursor)
- Sync Changes (commit_seq ordered incremental stream, cursor advancement)
- Cursor out-of-range detection (forcing full bootstrap)
- Online payment write command with client request_id idempotency
- Online payment revoke command
- Device bearer authentication and token revocation enforcement
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


async def _pair_device_and_get_headers(client: AsyncClient, name: str = "测试同步手机") -> tuple[dict, dict]:
    pair_res = await client.post("/v1/devices/pair", json={"name": name})
    assert pair_res.status_code == 201
    device_data = pair_res.json()
    headers = {"Authorization": f"Bearer {device_data['token']}"}
    return device_data, headers


# ---- Authentication Protection ----

async def test_sync_endpoints_require_auth(client: AsyncClient):
    r1 = await client.get("/v1/sync/bootstrap")
    assert r1.status_code == 401

    r2 = await client.get("/v1/sync/changes?cursor=0")
    assert r2.status_code == 401

    r3 = await client.post("/v1/sync/payments", json={
        "statement_id": str(uuid.uuid4()),
        "amount_minor": 1000,
        "currency": "CNY",
    })
    assert r3.status_code == 401

    r4 = await client.post(f"/v1/sync/payments/{uuid.uuid4()}/revoke", json={"reason": "test"})
    assert r4.status_code == 401


async def test_sync_revoked_device_rejected(client: AsyncClient):
    dev, headers = await _pair_device_and_get_headers(client, "将要注销的手机")
    # Verify works before revoke
    r = await client.get("/v1/sync/bootstrap", headers=headers)
    assert r.status_code == 200

    # Revoke device
    revoke_res = await client.post(f"/v1/devices/{dev['device_id']}/revoke")
    assert revoke_res.status_code == 200

    # Now sync calls must fail with 401
    r_after = await client.get("/v1/sync/bootstrap", headers=headers)
    assert r_after.status_code == 401


# ---- Bootstrap Snapshot ----

async def test_sync_bootstrap_returns_valid_snapshot(client: AsyncClient):
    dev, headers = await _pair_device_and_get_headers(client, "快照测试设备")
    r = await client.get("/v1/sync/bootstrap", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "cursor" in data
    assert data["cursor"] >= 0
    assert "server_time" in data
    assert isinstance(data["accounts"], list)
    assert isinstance(data["cards"], list)
    assert isinstance(data["statements"], list)
    assert isinstance(data["payments"], list)


# ---- Incremental Changes Stream ----

async def test_sync_changes_captures_new_entities_and_advances_cursor(client: AsyncClient):
    dev, headers = await _pair_device_and_get_headers(client, "增量测试设备")

    # 1. Get baseline cursor
    boot = (await client.get("/v1/sync/bootstrap", headers=headers)).json()
    baseline = boot["cursor"]

    # 2. Create an account and card
    unique_suffix = uuid.uuid4().hex[:6]
    acct = (await client.post("/v1/accounts", json={"bank": f"招商银行_{unique_suffix}", "alias": "工资卡"})).json()
    card = (await client.post("/v1/cards", json={
        "account_id": acct["id"],
        "display_name": "经典白金卡",
        "tail": "8888",
    })).json()

    # 3. Pull changes since baseline
    res = await client.get(f"/v1/sync/changes?cursor={baseline}", headers=headers)
    assert res.status_code == 200
    changes_data = res.json()
    assert changes_data["cursor"] > baseline
    changes = changes_data["changes"]
    assert len(changes) >= 2

    # Verify entities captured in changes stream
    acct_changes = [c for c in changes if c["entity_type"] == "account" and c["entity_id"] == acct["id"]]
    card_changes = [c for c in changes if c["entity_type"] == "card" and c["entity_id"] == card["id"]]
    assert len(acct_changes) == 1
    assert acct_changes[0]["action"] == "create"
    assert acct_changes[0]["snapshot"]["bank"] == f"招商银行_{unique_suffix}"

    assert len(card_changes) == 1
    assert card_changes[0]["action"] == "create"
    assert card_changes[0]["snapshot"]["tail"] == "8888"

    # 4. Pulling with new cursor yields empty
    latest_cursor = changes_data["cursor"]
    res_empty = await client.get(f"/v1/sync/changes?cursor={latest_cursor}", headers=headers)
    assert res_empty.status_code == 200
    assert len(res_empty.json()["changes"]) == 0
    assert res_empty.json()["cursor"] == latest_cursor


async def test_sync_changes_cursor_out_of_range_forces_bootstrap(client: AsyncClient):
    dev, headers = await _pair_device_and_get_headers(client, "越界测试设备")
    r = await client.get("/v1/sync/changes?cursor=999999999", headers=headers)
    assert r.status_code == 409
    err = r.json()
    assert "CURSOR_OUT_OF_RANGE" in str(err)


# ---- Online Payment Write Command & Idempotency ----

async def test_sync_online_payment_write_and_revoke(client: AsyncClient):
    dev, headers = await _pair_device_and_get_headers(client, "还款测试设备")

    # Setup account and statement: 20000 minor units CNY
    unique_suffix = uuid.uuid4().hex[:6]
    acct = (await client.post("/v1/accounts", json={"bank": f"建设银行_{unique_suffix}"})).json()
    stmt = (await client.post("/v1/statements", json={
        "account_id": acct["id"],
        "currency": "CNY",
        "statement_date": "2026-09-01",
        "due_date": "2026-09-25",
        "amount_minor": 20000,
        "minimum_minor": 2000,
    })).json()

    # 1. First payment: 6000
    req_id = str(uuid.uuid4())
    p1 = await client.post("/v1/sync/payments", json={
        "statement_id": stmt["id"],
        "amount_minor": 6000,
        "currency": "CNY",
        "note": "手机在线还款",
        "request_id": req_id,
    }, headers=headers)
    assert p1.status_code == 201
    d1 = p1.json()
    assert d1["created"] is True
    assert d1["payment"]["amount_minor"] == 6000
    assert d1["statement_detail"]["total_paid_minor"] == 6000
    assert d1["statement_detail"]["remaining_minor"] == 14000

    # 2. Idempotent retry with exact same request_id
    p1_retry = await client.post("/v1/sync/payments", json={
        "statement_id": stmt["id"],
        "amount_minor": 6000,
        "currency": "CNY",
        "note": "重复提交",
        "request_id": req_id,
    }, headers=headers)
    assert p1_retry.status_code == 201
    d1_retry = p1_retry.json()
    assert d1_retry["created"] is False  # Idempotent response
    assert d1_retry["payment"]["id"] == d1["payment"]["id"]
    assert d1_retry["statement_detail"]["remaining_minor"] == 14000

    # 3. Overpayment rejected
    p_over = await client.post("/v1/sync/payments", json={
        "statement_id": stmt["id"],
        "amount_minor": 15000,  # exceeds 14000
        "currency": "CNY",
    }, headers=headers)
    assert p_over.status_code == 409

    # 4. Revoke payment
    rev_res = await client.post(
        f"/v1/sync/payments/{d1['payment']['id']}/revoke",
        json={"reason": "点错了"},
        headers=headers,
    )
    assert rev_res.status_code == 200
    rev_data = rev_res.json()
    assert rev_data["payment"]["revoked_at"] is not None
    assert rev_data["payment"]["revoke_reason"] == "点错了"
    assert rev_data["statement_detail"]["remaining_minor"] == 20000
    assert rev_data["statement_detail"]["total_paid_minor"] == 0
