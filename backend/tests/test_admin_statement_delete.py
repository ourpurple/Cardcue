"""Integration tests for Statement and Payment deletion endpoints in Web Admin."""

import uuid
from datetime import date
import pytest
from httpx import ASGITransport, AsyncClient

from cardcue_api.main import app
from cardcue_api.admin.security import Actor, require_admin
from cardcue_api.persistence.database import async_session_factory
from cardcue_api.domain.schemas import StatementCreate, PaymentCreate
from cardcue_api.services.billing import BillingService


@pytest.fixture(scope="function")
async def admin_client():
    mock_admin = Actor(id="admin-test", kind="admin")
    app.dependency_overrides[require_admin] = lambda: mock_admin
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(require_admin, None)


async def test_statement_and_payment_deletion_flow(admin_client: AsyncClient):
    # 1. Create account
    r = await admin_client.post("/v1/admin/accounts", json={"bank": "测试账单删除银行", "alias": "账单删除测试账户"})
    assert r.status_code == 201, r.text
    acct_id = r.json()["id"]

    # 2. Create statement via billing service
    billing_svc = BillingService()
    async with async_session_factory() as session:
        stmt = await billing_svc.create_statement(
            session,
            StatementCreate(
                account_id=uuid.UUID(acct_id),
                currency="CNY",
                statement_date=date(2026, 2, 1),
                due_date=date(2026, 2, 25),
                amount_minor=50000,
                minimum_minor=5000,
                source="manual",
            ),
        )
        stmt_id = str(stmt.id)

        # Record payment 1 (20000 cents)
        p1, _ = await billing_svc.record_payment(
            session,
            PaymentCreate(
                statement_id=stmt.id,
                amount_minor=20000,
                currency="CNY",
                note="测试还款1",
            ),
        )
        p1_id = str(p1.id)

        # Record payment 2 (10000 cents)
        p2, _ = await billing_svc.record_payment(
            session,
            PaymentCreate(
                statement_id=stmt.id,
                amount_minor=10000,
                currency="CNY",
                note="测试还款2",
            ),
        )
        p2_id = str(p2.id)
        await session.commit()

    # 3. Test deleting single payment (p2)
    r_del_p2 = await admin_client.delete(f"/v1/admin/payments/{p2_id}")
    assert r_del_p2.status_code == 200, r_del_p2.text
    assert r_del_p2.json()["success"] is True

    # Check statement detail: should only have p1 now
    r_detail = await admin_client.get(f"/v1/admin/statements/{stmt_id}")
    assert r_detail.status_code == 200
    detail_data = r_detail.json()
    assert len(detail_data["payments"]) == 1
    assert detail_data["payments"][0]["id"] == p1_id
    assert detail_data["total_paid_minor"] == 20000
    assert detail_data["remaining_minor"] == 30000

    # 4. Try deleting account -> should be blocked by existing statement
    r_del_acct_blocked = await admin_client.delete(f"/v1/admin/accounts/{acct_id}")
    assert r_del_acct_blocked.status_code == 400
    assert "无法直接删除" in r_del_acct_blocked.json()["detail"]

    # 5. Delete statement
    r_del_stmt = await admin_client.delete(f"/v1/admin/statements/{stmt_id}")
    assert r_del_stmt.status_code == 200, r_del_stmt.text
    assert r_del_stmt.json()["success"] is True

    # Verify statement is gone
    r_stmt_check = await admin_client.get(f"/v1/admin/statements/{stmt_id}")
    assert r_stmt_check.status_code == 404

    # Verify deleting again returns 404
    r_stmt_retry = await admin_client.delete(f"/v1/admin/statements/{stmt_id}")
    assert r_stmt_retry.status_code == 404

    # 6. Now that statement is deleted, account can be deleted successfully
    r_del_acct = await admin_client.delete(f"/v1/admin/accounts/{acct_id}")
    assert r_del_acct.status_code == 200, r_del_acct.text
    assert r_del_acct.json()["success"] is True
