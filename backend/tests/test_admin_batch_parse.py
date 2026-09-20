"""Integration tests for Email Batch Parsing and Auto Parsing trigger."""

import uuid
from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from cardcue_api.main import app
from cardcue_api.admin.security import Actor, require_admin, recent_admin
from cardcue_api.persistence.database import async_session_factory
from cardcue_api.persistence.mail import Mailbox, EmailSource
from cardcue_api.admin.models import AdminJob


@pytest.fixture(scope="function")
async def admin_client():
    mock_admin = Actor(id="admin-test", kind="admin")
    app.dependency_overrides[require_admin] = lambda: mock_admin
    app.dependency_overrides[recent_admin] = lambda: mock_admin
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(recent_admin, None)


async def test_email_batch_parse_endpoints(admin_client: AsyncClient):
    suffix = uuid.uuid4().hex[:6]
    test_email = f"batch_parse_{suffix}@example.com"

    async with async_session_factory() as s:
        # Create a test mailbox
        mb = Mailbox(
            email_address=test_email,
            imap_host="imap.example.com",
            imap_port=993,
            use_ssl=True,
            encrypted_auth_token="dummy",
            auth_type="password",
            is_active=True,
            status="active",
            check_interval_minutes=30,
            settings_json={"auto_parse": True},
            revision=1,
        )
        s.add(mb)
        await s.flush()

        # Create two candidate emails with raw_storage_path
        es1 = EmailSource(
            mailbox_id=mb.id,
            folder="INBOX",
            uid=101,
            uidvalidity=1,
            subject="招商银行信用卡电子账单",
            sender="ccservice@cmbchina.com",
            recipient=test_email,
            email_date=datetime.now(timezone.utc),
            body_hash="hash1",
            raw_storage_path="/tmp/fake_raw_1.eml",
            is_statement_candidate=True,
            parse_status="pending",
        )
        es2 = EmailSource(
            mailbox_id=mb.id,
            folder="INBOX",
            uid=102,
            uidvalidity=1,
            subject="广发卡电子账单",
            sender="bill@cgbchina.com.cn",
            recipient=test_email,
            email_date=datetime.now(timezone.utc),
            body_hash="hash2",
            raw_storage_path="/tmp/fake_raw_2.eml",
            is_statement_candidate=True,
            parse_status="failed",
            error_message="Previous error",
        )
        s.add_all([es1, es2])
        await s.commit()
        es1_id, es2_id, mb_id = es1.id, es2.id, mb.id

    # 1. Batch parse specific email id (es2, which was failed)
    r = await admin_client.post("/v1/admin/emails/batch-parse", json={
        "email_ids": [str(es2_id)]
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enqueued"] == 1

    # Check that es2 parse_status was reset to pending (or already parsed by active worker)
    async with async_session_factory() as s:
        refreshed_es2 = await s.get(EmailSource, es2_id)
        assert refreshed_es2.parse_status in ("pending", "parsed")

    # 2. Batch parse all pending emails for this mailbox
    r2 = await admin_client.post("/v1/admin/emails/batch-parse", json={
        "mailbox_id": str(mb_id),
        "include_failed": True
    })
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert data2["total_found"] >= 1
