"""S1-04/05/06/07 integration tests: API, transactional payments, device auth.

Uses httpx.AsyncClient with ASGITransport against the real PostgreSQL.
Each test gets a fresh async client with proper event loop handling.
"""

import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from cardcue_api.main import app


@pytest.fixture(scope="function")
async def client():
    """Fresh async client per test to avoid event loop conflicts."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---- Health & Capabilities ----

async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["version"] == "0.5.0"


async def test_capabilities_s1(client: AsyncClient):
    r = await client.get("/v1/capabilities")
    d = r.json()
    assert d["stage"] in ("s3-email-sync", "s4-parsing-drafts", "r1-delivery")
    assert d["accounts"] is True
    assert d["email_sync"] is True


# ---- Account CRUD ----

async def test_account_create_and_list(client: AsyncClient):
    r = await client.post("/v1/accounts", json={"bank": "测试银行"})
    assert r.status_code == 201
    acct = r.json()
    assert acct["bank"] == "测试银行"
    assert acct["status"] == "active"

    r2 = await client.get("/v1/accounts")
    assert r2.status_code == 200
    assert any(a["id"] == acct["id"] for a in r2.json())


async def test_account_get_and_update(client: AsyncClient):
    r = await client.post("/v1/accounts", json={"bank": "招商银行", "alias": "我的招行"})
    acct_id = r.json()["id"]

    r2 = await client.get(f"/v1/accounts/{acct_id}")
    assert r2.status_code == 200
    assert r2.json()["alias"] == "我的招行"

    r3 = await client.patch(f"/v1/accounts/{acct_id}", json={"alias": "改名了", "status": "archived"})
    assert r3.status_code == 200
    assert r3.json()["alias"] == "改名了"
    assert r3.json()["status"] == "archived"


async def test_account_not_found(client: AsyncClient):
    fake = str(uuid.uuid4())
    r = await client.get(f"/v1/accounts/{fake}")
    assert r.status_code == 404


# ---- Card CRUD ----

async def test_card_create_and_list(client: AsyncClient):
    acct = (await client.post("/v1/accounts", json={"bank": "交通银行"})).json()
    r = await client.post("/v1/cards", json={"account_id": acct["id"], "tail": "8369"})
    assert r.status_code == 201
    assert r.json()["tail"] == "8369"

    await client.post("/v1/cards", json={"account_id": acct["id"], "tail": "5678"})
    r2 = await client.get(f"/v1/accounts/{acct['id']}/cards")
    assert r2.status_code == 200
    assert len(r2.json()) >= 2


# ---- Statement & Version ----

async def test_statement_create_and_detail(client: AsyncClient):
    acct_id = (await client.post("/v1/accounts", json={"bank": "中信银行"})).json()["id"]
    r = await client.post("/v1/statements", json={
        "account_id": acct_id, "currency": "CNY",
        "statement_date": "2026-08-01", "due_date": "2026-08-25",
        "amount_minor": 683051,
    })
    assert r.status_code == 201
    stmt = r.json()
    assert stmt["currency"] == "CNY"
    assert stmt["current_version_id"] is not None

    r2 = await client.get(f"/v1/statements/{stmt['id']}")
    assert r2.status_code == 200
    detail = r2.json()
    assert detail["current_version"]["amount_minor"] == 683051
    assert detail["remaining_minor"] == 683051
    assert detail["total_paid_minor"] == 0


async def test_statement_due_before_start_rejected(client: AsyncClient):
    acct_id = (await client.post("/v1/accounts", json={"bank": "工商银行"})).json()["id"]
    r = await client.post("/v1/statements", json={
        "account_id": acct_id, "currency": "CNY",
        "statement_date": "2026-09-15", "due_date": "2026-09-01",
        "amount_minor": 10000,
    })
    assert r.status_code == 409


# ---- Payment with transactional safety (S1-05) ----

async def _make_statement(client: AsyncClient, amount: int = 100000) -> dict:
    acct_id = (await client.post("/v1/accounts", json={"bank": "浦发银行"})).json()["id"]
    return (await client.post("/v1/statements", json={
        "account_id": acct_id, "currency": "CNY",
        "statement_date": "2026-08-01", "due_date": "2026-08-25",
        "amount_minor": amount,
    })).json()


async def test_payment_record_and_remaining(client: AsyncClient):
    stmt = await _make_statement(client, 100000)
    r = await client.post("/v1/payments", json={
        "statement_id": stmt["id"], "amount_minor": 30000,
        "currency": "CNY", "note": "支付宝还款",
    })
    assert r.status_code == 201
    assert r.json()["amount_minor"] == 30000

    detail = (await client.get(f"/v1/statements/{stmt['id']}")).json()
    assert detail["total_paid_minor"] == 30000
    assert detail["remaining_minor"] == 70000


async def test_overpayment_rejected(client: AsyncClient):
    stmt = await _make_statement(client, 50000)
    r = await client.post("/v1/payments", json={
        "statement_id": stmt["id"], "amount_minor": 60000, "currency": "CNY",
    })
    assert r.status_code == 409


async def test_currency_mismatch_rejected(client: AsyncClient):
    stmt = await _make_statement(client, 100000)
    r = await client.post("/v1/payments", json={
        "statement_id": stmt["id"], "amount_minor": 10000, "currency": "USD",
    })
    assert r.status_code == 409


async def test_idempotent_payment(client: AsyncClient):
    stmt = await _make_statement(client)
    rid = str(uuid.uuid4())
    r1 = await client.post("/v1/payments", json={
        "statement_id": stmt["id"], "amount_minor": 20000,
        "currency": "CNY", "request_id": rid,
    })
    assert r1.status_code == 201
    r2 = await client.post("/v1/payments", json={
        "statement_id": stmt["id"], "amount_minor": 20000,
        "currency": "CNY", "request_id": rid,
    })
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


async def test_revoke_and_repay(client: AsyncClient):
    stmt = await _make_statement(client, 100000)
    pay = (await client.post("/v1/payments", json={
        "statement_id": stmt["id"], "amount_minor": 100000, "currency": "CNY",
    })).json()

    # Fully paid – can't pay more
    r_over = await client.post("/v1/payments", json={
        "statement_id": stmt["id"], "amount_minor": 1, "currency": "CNY",
    })
    assert r_over.status_code == 409

    # Revoke
    r_rev = await client.post(f"/v1/payments/{pay['id']}/revoke", json={"reason": "误操作"})
    assert r_rev.status_code == 200
    assert r_rev.json()["revoked_at"] is not None

    # Remaining is restored
    detail = (await client.get(f"/v1/statements/{stmt['id']}")).json()
    assert detail["remaining_minor"] == 100000

    # Can pay again
    r_repay = await client.post("/v1/payments", json={
        "statement_id": stmt["id"], "amount_minor": 100000, "currency": "CNY",
    })
    assert r_repay.status_code == 201


async def test_double_revoke_rejected(client: AsyncClient):
    stmt = await _make_statement(client)
    pay = (await client.post("/v1/payments", json={
        "statement_id": stmt["id"], "amount_minor": 10000, "currency": "CNY",
    })).json()
    await client.post(f"/v1/payments/{pay['id']}/revoke", json={"reason": "第一次撤销"})
    r = await client.post(f"/v1/payments/{pay['id']}/revoke", json={"reason": "再次撤销"})
    assert r.status_code == 409


async def test_list_payments(client: AsyncClient):
    stmt = await _make_statement(client)
    await client.post("/v1/payments", json={
        "statement_id": stmt["id"], "amount_minor": 10000, "currency": "CNY",
    })
    await client.post("/v1/payments", json={
        "statement_id": stmt["id"], "amount_minor": 20000, "currency": "CNY",
    })
    r = await client.get(f"/v1/statements/{stmt['id']}/payments")
    assert r.status_code == 200
    assert len(r.json()) >= 2


# ---- Device Auth (S1-06) ----

async def test_device_pair_and_list(client: AsyncClient):
    r = await client.post("/v1/devices/pair", json={"name": "我的手机"})
    assert r.status_code == 201
    d = r.json()
    assert "token" in d
    assert len(d["token"]) > 20

    r2 = await client.get("/v1/devices")
    assert r2.status_code == 200
    assert any(dev["id"] == d["device_id"] for dev in r2.json())


async def test_device_revoke(client: AsyncClient):
    d = (await client.post("/v1/devices/pair", json={"name": "旧手机"})).json()
    r = await client.post(f"/v1/devices/{d['device_id']}/revoke")
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"
    assert r.json()["revoked_at"] is not None

