"""Integration tests for Account and Card deletion endpoints in Web Admin."""

import uuid
from datetime import date
import pytest
from httpx import ASGITransport, AsyncClient

from cardcue_api.main import app
from cardcue_api.admin.security import Actor, require_admin
from cardcue_api.persistence.database import async_session_factory
from cardcue_api.domain.schemas import StatementCreate
from cardcue_api.services.billing import BillingService


@pytest.fixture(scope="function")
async def admin_client():
    mock_admin = Actor(id="admin-test", kind="admin")
    app.dependency_overrides[require_admin] = lambda: mock_admin
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(require_admin, None)


async def test_account_and_card_deletion_flow(admin_client: AsyncClient):
    # 1. Create account
    r = await admin_client.post("/v1/admin/accounts", json={"bank": "测试删除银行", "alias": "待删账户"})
    assert r.status_code == 201, r.text
    acct = r.json()
    acct_id = acct["id"]

    # 2. Add card to account
    r_card = await admin_client.post("/v1/admin/cards", json={
        "account_id": acct_id,
        "tail": "9999",
        "display_name": "临时测试卡",
    })
    assert r_card.status_code == 201, r_card.text
    card_id = r_card.json()["id"]

    # 3. Delete single card
    r_del_card = await admin_client.delete(f"/v1/admin/cards/{card_id}")
    assert r_del_card.status_code == 200, r_del_card.text
    assert r_del_card.json()["success"] is True

    # 4. Verify card is gone
    r_card_retry = await admin_client.delete(f"/v1/admin/cards/{card_id}")
    assert r_card_retry.status_code == 404

    # 5. Add another card to account
    r_card2 = await admin_client.post("/v1/admin/cards", json={
        "account_id": acct_id,
        "tail": "8888",
        "display_name": "联带删除测试卡",
    })
    assert r_card2.status_code == 201
    card2_id = r_card2.json()["id"]

    # 6. Delete account (should cascade-delete card2 and succeed)
    r_del_acct = await admin_client.delete(f"/v1/admin/accounts/{acct_id}")
    assert r_del_acct.status_code == 200, r_del_acct.text
    assert r_del_acct.json()["success"] is True

    # 7. Verify account is gone
    r_acct_retry = await admin_client.delete(f"/v1/admin/accounts/{acct_id}")
    assert r_acct_retry.status_code == 404

    # 8. Verify card2 is also deleted
    r_card2_check = await admin_client.delete(f"/v1/admin/cards/{card2_id}")
    assert r_card2_check.status_code == 404


async def test_account_deletion_blocked_by_statements(admin_client: AsyncClient):
    # 1. Create account
    r = await admin_client.post("/v1/admin/accounts", json={"bank": "有账单银行", "alias": "不可硬删账户"})
    assert r.status_code == 201
    acct_id = r.json()["id"]

    # 2. Create statement directly via billing service
    billing_svc = BillingService()
    async with async_session_factory() as session:
        await billing_svc.create_statement(
            session,
            StatementCreate(
                account_id=uuid.UUID(acct_id),
                currency="CNY",
                statement_date=date(2026, 1, 1),
                due_date=date(2026, 1, 20),
                amount_minor=100000,
                minimum_minor=10000,
                source="manual",
            ),
        )
        await session.commit()

    # 3. Try to delete account with statements -> should be rejected with 400
    r_del = await admin_client.delete(f"/v1/admin/accounts/{acct_id}")
    assert r_del.status_code == 400
    assert "无法直接删除" in r_del.json()["detail"]
    assert "归档" in r_del.json()["detail"]
