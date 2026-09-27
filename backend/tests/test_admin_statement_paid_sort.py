"""Test that settled (paid) statements appear after unpaid ones."""

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


async def test_settled_statements_after_unpaid(admin_client: AsyncClient):
    """Settled bills should always appear after unpaid ones regardless of due date order."""
    # 1. Create account
    r = await admin_client.post(
        "/v1/admin/accounts",
        json={"bank": "sort-group-bank", "alias": "sort-group-acct"},
    )
    assert r.status_code == 201, r.text
    acct_id = r.json()["id"]

    billing_svc = BillingService()
    stmt_ids: list[str] = []

    try:
        async with async_session_factory() as session:
            # Stmt A: due 2026-09-20, will be fully paid (settled)
            stmt_a = await billing_svc.create_statement(
                session,
                StatementCreate(
                    account_id=uuid.UUID(acct_id),
                    currency="CNY",
                    statement_date=date(2026, 9, 1),
                    due_date=date(2026, 9, 20),
                    amount_minor=10000,
                    source="manual",
                ),
            )
            stmt_ids.append(str(stmt_a.id))

            # Stmt B: due 2026-10-05, unpaid
            stmt_b = await billing_svc.create_statement(
                session,
                StatementCreate(
                    account_id=uuid.UUID(acct_id),
                    currency="CNY",
                    statement_date=date(2026, 9, 10),
                    due_date=date(2026, 10, 5),
                    amount_minor=50000,
                    source="manual",
                ),
            )
            stmt_ids.append(str(stmt_b.id))

            # Stmt C: due 2026-09-25, will be fully paid (settled)
            stmt_c = await billing_svc.create_statement(
                session,
                StatementCreate(
                    account_id=uuid.UUID(acct_id),
                    currency="CNY",
                    statement_date=date(2026, 9, 5),
                    due_date=date(2026, 9, 25),
                    amount_minor=20000,
                    source="manual",
                ),
            )
            stmt_ids.append(str(stmt_c.id))

            # Stmt D: due 2026-09-18, unpaid
            stmt_d = await billing_svc.create_statement(
                session,
                StatementCreate(
                    account_id=uuid.UUID(acct_id),
                    currency="CNY",
                    statement_date=date(2026, 9, 3),
                    due_date=date(2026, 9, 18),
                    amount_minor=30000,
                    source="manual",
                ),
            )
            stmt_ids.append(str(stmt_d.id))
            await session.commit()

        # Pay stmt A and stmt C fully
        for sid in [stmt_ids[0], stmt_ids[2]]:
            r_detail = await admin_client.get(f"/v1/admin/statements/{sid}")
            assert r_detail.status_code == 200
            amount = r_detail.json()["amount_minor"]
            r_pay = await admin_client.post(
                f"/v1/admin/statements/{sid}/payments",
                json={
                    "request_id": str(uuid.uuid4()),
                    "statement_id": sid,
                    "amount_minor": amount,
                    "currency": "CNY",
                },
            )
            assert r_pay.status_code == 201, r_pay.text

        # Fetch all statements for this account, default sort (due_date ASC)
        r_list = await admin_client.get(f"/v1/admin/statements?account_id={acct_id}")
        assert r_list.status_code == 200
        items = r_list.json()["items"]
        assert len(items) == 4

        # First two should be unpaid (D due 09-18, B due 10-05)
        # Last two should be settled (A due 09-20, C due 09-25)
        unpaid_ids = {items[0]["id"], items[1]["id"]}
        paid_ids = {items[2]["id"], items[3]["id"]}
        assert unpaid_ids == {stmt_ids[3], stmt_ids[1]}, (
            f"Unpaid bills should come first; got {[it['id'] for it in items]}"
        )
        assert paid_ids == {stmt_ids[0], stmt_ids[2]}, (
            f"Settled bills should come last; got {[it['id'] for it in items]}"
        )

        # Within unpaid group: D (due 09-18) before B (due 10-05) -- due_date ASC
        assert items[0]["id"] == stmt_ids[3]
        assert items[1]["id"] == stmt_ids[1]

        # Within settled group: A (due 09-20) before C (due 09-25) -- due_date ASC
        assert items[2]["id"] == stmt_ids[0]
        assert items[3]["id"] == stmt_ids[2]

        # Verify is_paid flags
        assert items[0]["is_paid"] is False
        assert items[1]["is_paid"] is False
        assert items[2]["is_paid"] is True
        assert items[3]["is_paid"] is True

    finally:
        for sid in stmt_ids:
            await admin_client.delete(f"/v1/admin/statements/{sid}")
        await admin_client.delete(f"/v1/admin/accounts/{acct_id}")
