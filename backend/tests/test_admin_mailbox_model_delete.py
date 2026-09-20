"""Integration tests for Mailbox and ModelProfile deletion in Web Admin."""

import uuid
from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from cardcue_api.main import app
from cardcue_api.admin.security import Actor, require_admin, recent_admin
from cardcue_api.persistence.database import async_session_factory
from cardcue_api.persistence.mail import Mailbox, MailCursor, MailJob, EmailSource, EmailAttachment
from cardcue_api.persistence.drafts import StatementDraftModel
from cardcue_api.admin.models import ModelProfile, ModelRevision, RuntimeSettings, AuditEvent


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


async def test_mailbox_deletion_flow(admin_client: AsyncClient):
    suffix = uuid.uuid4().hex[:6]
    test_email = f"delete_test_{suffix}@example.com"

    # 1. Create a mailbox via admin API
    r_create = await admin_client.post("/v1/admin/mailboxes", json={
        "name": "待删除测试邮箱",
        "email_address": test_email,
        "imap_host": "imap.example.com",
        "imap_port": 993,
        "use_ssl": True,
        "auth_token": "secret_token_123",
        "folder": "INBOX",
        "check_interval_minutes": 30,
    })
    assert r_create.status_code == 201, r_create.text
    mailbox_data = r_create.json()
    mailbox_id = uuid.UUID(mailbox_data["id"])

    # 2. Add some related objects in DB (Cursor, Job, EmailSource, EmailAttachment, and Draft)
    async with async_session_factory() as session:
        cursor = MailCursor(mailbox_id=mailbox_id, folder="INBOX", uidvalidity=100, last_uid=50)
        job = MailJob(mailbox_id=mailbox_id, trigger_type="manual", status="completed")
        email_source = EmailSource(
            id=uuid.uuid4(),
            mailbox_id=mailbox_id,
            folder="INBOX",
            uid=123,
            uidvalidity=100,
            message_id=f"msg_{suffix}",
            subject="测试账单邮件",
            sender="service@bank.com",
            recipient=test_email,
            email_date=datetime.now(timezone.utc),
            body_hash=f"hash_{suffix}",
            is_statement_candidate=True,
            parse_status="parsed",
        )
        session.add_all([cursor, job, email_source])
        await session.flush()

        attachment = EmailAttachment(
            email_source_id=email_source.id,
            filename="bill.pdf",
            storage_path="/tmp/fake.pdf",
        )
        draft = StatementDraftModel(
            email_source_id=email_source.id,
            mailbox_id=mailbox_id,
            status="pending_review",
            bank="测试银行",
            currency="CNY",
            amount_minor=8800,
        )
        session.add_all([attachment, draft])
        await session.commit()
        draft_id = draft.id

    # 3. Delete the mailbox via admin DELETE endpoint
    r_del = await admin_client.delete(f"/v1/admin/mailboxes/{mailbox_id}")
    assert r_del.status_code == 200, r_del.text
    assert r_del.json()["ok"] is True
    assert r_del.json()["id"] == str(mailbox_id)

    # 4. Verify DB cleanup
    async with async_session_factory() as session:
        # Mailbox should be gone
        mb_row = await session.get(Mailbox, mailbox_id)
        assert mb_row is None

        # Related cursor, job, email_source should be gone
        cursors = (await session.execute(select(MailCursor).where(MailCursor.mailbox_id == mailbox_id))).scalars().all()
        assert len(cursors) == 0

        jobs = (await session.execute(select(MailJob).where(MailJob.mailbox_id == mailbox_id))).scalars().all()
        assert len(jobs) == 0

        sources = (await session.execute(select(EmailSource).where(EmailSource.mailbox_id == mailbox_id))).scalars().all()
        assert len(sources) == 0

        # Draft should still exist, but mailbox_id and email_source_id are unlinked (None)
        draft_row = await session.get(StatementDraftModel, draft_id)
        assert draft_row is not None
        assert draft_row.mailbox_id is None
        assert draft_row.email_source_id is None

        # Audit event recorded
        audits = (await session.execute(
            select(AuditEvent).where(AuditEvent.action == "mailbox_deleted", AuditEvent.target == str(mailbox_id))
        )).scalars().all()
        assert len(audits) >= 1

    # 5. Repeated deletion should return 404
    r_del_again = await admin_client.delete(f"/v1/admin/mailboxes/{mailbox_id}")
    assert r_del_again.status_code == 404


async def test_model_profile_deletion_flow(admin_client: AsyncClient):
    # 1. Create a model profile
    r_create = await admin_client.post("/v1/admin/models", json={
        "name": "待删除模型方案",
        "api_key": "sk-delete-test-key",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "temperature": 0.1,
    })
    assert r_create.status_code == 201, r_create.text
    model_data = r_create.json()
    profile_id = uuid.UUID(model_data["id"])
    rev_id = model_data["revisions"][0]["id"]

    # 2. If it is set as active, deletion should be rejected
    async with async_session_factory() as session:
        state = await session.get(RuntimeSettings, "model")
        if not state:
            state = RuntimeSettings(key="model", value={"revision_id": str(rev_id)})
            session.add(state)
        else:
            state.value = {"revision_id": str(rev_id)}
        await session.commit()

    r_del_active = await admin_client.delete(f"/v1/admin/models/{profile_id}")
    assert r_del_active.status_code == 400
    assert "激活状态" in r_del_active.json()["detail"]

    # 3. Clear active state or switch to dummy revision
    async with async_session_factory() as session:
        state = await session.get(RuntimeSettings, "model")
        state.value = {}
        await session.commit()

    # 4. Now delete should succeed
    r_del_ok = await admin_client.delete(f"/v1/admin/models/{profile_id}")
    assert r_del_ok.status_code == 200, r_del_ok.text
    assert r_del_ok.json()["ok"] is True

    # 5. Verify DB cleanup
    async with async_session_factory() as session:
        p_row = await session.get(ModelProfile, profile_id)
        assert p_row is None

        revs = (await session.execute(
            select(ModelRevision).where(ModelRevision.profile_id == profile_id)
        )).scalars().all()
        assert len(revs) == 0

        audits = (await session.execute(
            select(AuditEvent).where(AuditEvent.action == "model_profile_deleted", AuditEvent.target == str(profile_id))
        )).scalars().all()
        assert len(audits) >= 1

    # 6. Second deletion returns 404
    r_del_again = await admin_client.delete(f"/v1/admin/models/{profile_id}")
    assert r_del_again.status_code == 404

async def test_mailbox_update_flow(admin_client: AsyncClient):
    suffix = uuid.uuid4().hex[:6]
    test_email = f"update_test_{suffix}@sina.com"

    # 1. Create mailbox with empty username
    r_create = await admin_client.post("/v1/admin/mailboxes", json={
        "name": "未命名邮箱",
        "email_address": test_email,
        "username": "",
        "imap_host": "imap.sina.com",
        "imap_port": 993,
        "use_ssl": True,
        "auth_token": "secret_token_123",
        "folder": "INBOX",
        "check_interval_minutes": 30,
    })
    assert r_create.status_code == 201, r_create.text
    mailbox_data = r_create.json()
    mailbox_id = uuid.UUID(mailbox_data["id"])
    rev = mailbox_data["revision"]

    # 2. Update alias name to "hhh邮箱", username is blank
    r_update = await admin_client.put(f"/v1/admin/mailboxes/{mailbox_id}", json={
        "expected_revision": rev,
        "name": "hhh邮箱",
        "email_address": test_email,
        "username": "",
        "imap_host": "imap.sina.com",
        "imap_port": 993,
        "use_ssl": True,
        "folder": "INBOX",
        "check_interval_minutes": 45,
    })
    assert r_update.status_code == 200, r_update.text
    updated_data = r_update.json()
    assert updated_data["name"] == "hhh邮箱"
    rev = updated_data["revision"]

    # 3. Update alias again with username matching email address
    r_update2 = await admin_client.put(f"/v1/admin/mailboxes/{mailbox_id}", json={
        "expected_revision": rev,
        "name": "hhh新名称",
        "email_address": test_email,
        "username": test_email,
        "imap_host": "imap.sina.com",
        "imap_port": 993,
        "use_ssl": True,
        "folder": "INBOX",
        "check_interval_minutes": 45,
    })
    assert r_update2.status_code == 200, r_update2.text
    assert r_update2.json()["name"] == "hhh新名称"
    rev = r_update2.json()["revision"]

    # 4. Attempt to change email address to another account -> must raise 409
    r_update_fail = await admin_client.put(f"/v1/admin/mailboxes/{mailbox_id}", json={
        "expected_revision": rev,
        "name": "试图换邮箱",
        "email_address": "different_account@sina.com",
        "username": "",
        "imap_host": "imap.sina.com",
        "imap_port": 993,
        "use_ssl": True,
        "folder": "INBOX",
        "check_interval_minutes": 45,
    })
    assert r_update_fail.status_code == 409
    assert "邮箱身份、服务器或文件夹变化请新建配置" in r_update_fail.json()["detail"]

    # Clean up
    await admin_client.delete(f"/v1/admin/mailboxes/{mailbox_id}")

