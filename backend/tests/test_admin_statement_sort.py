"""Integration tests for Statement sorting endpoints in Web Admin."""

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


async def test_list_statements_sorting_by_due_date(admin_client: AsyncClient):
    # 1. Create account
    r = await admin_client.post("/v1/admin/accounts", json={"bank": "排序测试银行", "alias": "排序测试账户"})
    assert r.status_code == 201, r.text
    acct_id = r.json()["id"]

    billing_svc = BillingService()
    stmt_ids = []

    try:
        # 2. Create statements with varying due dates and statement dates
        # Stmt A: statement 2026-09-16, due 2026-10-10
        # Stmt B: statement 2026-09-06, due 2026-09-26
        # Stmt C: statement 2026-09-13, due 2026-10-01
        async with async_session_factory() as session:
            stmt_a = await billing_svc.create_statement(
                session,
                StatementCreate(
                    account_id=uuid.UUID(acct_id),
                    currency="CNY",
                    statement_date=date(2026, 9, 16),
                    due_date=date(2026, 10, 10),
                    amount_minor=49796,
                    minimum_minor=4980,
                    source="manual",
                ),
            )
            stmt_ids.append(str(stmt_a.id))

            stmt_b = await billing_svc.create_statement(
                session,
                StatementCreate(
                    account_id=uuid.UUID(acct_id),
                    currency="CNY",
                    statement_date=date(2026, 9, 6),
                    due_date=date(2026, 9, 26),
                    amount_minor=2594,
                    minimum_minor=2594,
                    source="manual",
                ),
            )
            stmt_ids.append(str(stmt_b.id))

            stmt_c = await billing_svc.create_statement(
                session,
                StatementCreate(
                    account_id=uuid.UUID(acct_id),
                    currency="CNY",
                    statement_date=date(2026, 9, 13),
                    due_date=date(2026, 10, 1),
                    amount_minor=20583,
                    minimum_minor=412,
                    source="manual",
                ),
            )
            stmt_ids.append(str(stmt_c.id))
            await session.commit()

        # 3. Default sort: should be due_date ASC
        r_default = await admin_client.get(f"/v1/admin/statements?account_id={acct_id}")
        assert r_default.status_code == 200
        items_default = r_default.json()["items"]
        assert len(items_default) == 3
        due_dates_default = [item["due_date"] for item in items_default]
        assert due_dates_default == ["2026-09-26", "2026-10-01", "2026-10-10"]

        # 4. Explicit sort: due_date DESC
        r_desc = await admin_client.get(f"/v1/admin/statements?account_id={acct_id}&sort_by=due_date&sort_order=desc")
        assert r_desc.status_code == 200
        items_desc = r_desc.json()["items"]
        assert len(items_desc) == 3
        due_dates_desc = [item["due_date"] for item in items_desc]
        assert due_dates_desc == ["2026-10-10", "2026-10-01", "2026-09-26"]

        # 5. Sort by statement_date ASC
        r_stmt_asc = await admin_client.get(f"/v1/admin/statements?account_id={acct_id}&sort_by=statement_date&sort_order=asc")
        assert r_stmt_asc.status_code == 200
        items_stmt_asc = r_stmt_asc.json()["items"]
        assert len(items_stmt_asc) == 3
        stmt_dates_asc = [item["statement_date"] for item in items_stmt_asc]
        assert stmt_dates_asc == ["2026-09-06", "2026-09-13", "2026-09-16"]

        # 6. Sort by statement_date DESC
        r_stmt_desc = await admin_client.get(f"/v1/admin/statements?account_id={acct_id}&sort_by=statement_date&sort_order=desc")
        assert r_stmt_desc.status_code == 200
        items_stmt_desc = r_stmt_desc.json()["items"]
        assert len(items_stmt_desc) == 3
        stmt_dates_desc = [item["statement_date"] for item in items_stmt_desc]
        assert stmt_dates_desc == ["2026-09-16", "2026-09-13", "2026-09-06"]

    finally:
        # Cleanup
        for sid in stmt_ids:
            await admin_client.delete(f"/v1/admin/statements/{sid}")
        await admin_client.delete(f"/v1/admin/accounts/{acct_id}")
