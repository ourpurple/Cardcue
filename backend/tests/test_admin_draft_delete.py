"""Integration tests for Statement Draft deletion and clear endpoints in Web Admin."""

import uuid
from datetime import date, datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from cardcue_api.main import app
from cardcue_api.admin.security import Actor, require_admin
from cardcue_api.persistence.database import async_session_factory
from cardcue_api.persistence import StatementDraftModel, EmailSource, Mailbox


@pytest.fixture(scope="function")
async def admin_client():
    mock_admin = Actor(id="admin-draft-test", kind="admin")
    app.dependency_overrides[require_admin] = lambda: mock_admin
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(require_admin, None)


async def test_draft_delete_batch_delete_and_clear_flow(admin_client: AsyncClient):
    async with async_session_factory() as session:
        # Create a test mailbox
        mb = Mailbox(
            email_address=f"draft_test_{uuid.uuid4().hex[:6]}@example.com",
            imap_host="imap.example.com",
            imap_port=993,
            use_ssl=True,
            encrypted_auth_token="dummy",
            auth_type="password",
            is_active=True,
            status="active",
            check_interval_minutes=30,
            revision=1,
        )
        session.add(mb)
        await session.flush()

        # Create a test email source
        es = EmailSource(
            mailbox_id=mb.id,
            folder="INBOX",
            uid=101,
            uidvalidity=1,
            message_id=f"<draft-test-{uuid.uuid4().hex[:8]}@example.com>",
            sender="cc@testbank.com",
            subject="Test Bank Statement",
            email_date=datetime.now(timezone.utc),
            body_hash='dummyhash',
            raw_storage_path='/tmp/fake_storage.eml',
            is_statement_candidate=True,
            parse_status="parsed",
        )
        session.add(es)
        await session.flush()

        # Create 3 test drafts (2 for this email, 1 independent)
        d1 = StatementDraftModel(
            mailbox_id=mb.id,
            email_source_id=es.id,
            status="pending_review",
            bank="招商银行测试",
            currency="CNY",
            amount_minor=10000,
            statement_date=date(2026, 2, 1),
            due_date=date(2026, 2, 25),
        )
        d2 = StatementDraftModel(
            mailbox_id=mb.id,
            email_source_id=es.id,
            status="pending_review",
            bank="招商银行测试2",
            currency="CNY",
            amount_minor=20000,
            statement_date=date(2026, 3, 1),
            due_date=date(2026, 3, 25),
        )
        d3 = StatementDraftModel(
            mailbox_id=mb.id,
            status="pending_review",
            bank="测试无邮件草稿",
            currency="CNY",
            amount_minor=5000,
            statement_date=date(2026, 4, 1),
            due_date=date(2026, 4, 25),
        )
        session.add_all([d1, d2, d3])
        await session.commit()

        d1_id = str(d1.id)
        d2_id = str(d2.id)
        d3_id = str(d3.id)
        es_id = es.id

    # 1. Test single delete on d1
    r = await admin_client.delete(f"/v1/admin/drafts/{d1_id}")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    # Check d1 is gone, but es still has d2 so parse_status remains parsed
    async with async_session_factory() as session:
        check_d1 = await session.get(StatementDraftModel, uuid.UUID(d1_id))
        assert check_d1 is None
        check_es = await session.get(EmailSource, es_id)
        assert check_es.parse_status == "parsed"

    # 2. Test batch delete on d2
    r_batch = await admin_client.post("/v1/admin/drafts/batch-delete", json={"draft_ids": [d2_id]})
    assert r_batch.status_code == 200, r_batch.text
    assert r_batch.json()["deleted_count"] == 1

    # Now all drafts for es are deleted, so es.parse_status should be reset to "pending"
    async with async_session_factory() as session:
        check_d2 = await session.get(StatementDraftModel, uuid.UUID(d2_id))
        assert check_d2 is None
        check_es = await session.get(EmailSource, es_id)
        assert check_es.parse_status == "pending"

    # 3. Test clear drafts (clearing pending_review which will clear d3)
    r_clear = await admin_client.post("/v1/admin/drafts/clear", json={"status": "pending_review"})
    assert r_clear.status_code == 200, r_clear.text
    assert r_clear.json()["deleted_count"] >= 1

    async with async_session_factory() as session:
        check_d3 = await session.get(StatementDraftModel, uuid.UUID(d3_id))
        assert check_d3 is None

