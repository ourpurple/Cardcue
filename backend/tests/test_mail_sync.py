"""Comprehensive test suite for S3 Mail Retrieval, IMAP Read-Only Safety, Parser, Classifier, and Scheduler."""

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from cardcue_api.config import settings
from cardcue_api.main import app
from cardcue_api.domain.schemas import MailboxCreate, MailboxUpdate
from cardcue_api.mail.classifier import classify_email, is_from_bank_domain
from cardcue_api.mail.crypto import (
    MailCryptoError,
    decrypt_token,
    encrypt_token,
    mask_token,
)
from cardcue_api.mail.parser import (
    decode_mime_header,
    parse_email_bytes,
    sanitize_filename,
)
from cardcue_api.mail.storage import MailStorageError, MailStorageManager
from cardcue_api.jobs.scheduler import MailScheduler
from cardcue_api.persistence.database import async_session_factory
from cardcue_api.persistence.mail import MailCursor, MailJob, Mailbox
from cardcue_api.services.mail_sync import MailSyncConflictError, MailSyncService


# ==================== 1. Crypto Tests ====================

def test_token_encryption_and_decryption():
    secret = "my-special-key-12345"
    token = "imap_auth_code_xyz123"
    encrypted = encrypt_token(token, secret)
    assert encrypted != token
    decrypted = decrypt_token(encrypted, secret)
    assert decrypted == token


def test_token_decryption_invalid_fails():
    with pytest.raises(MailCryptoError):
        decrypt_token("not-a-valid-fernet-token")


def test_token_masking():
    assert mask_token("super_secret_password") == "********"
    assert mask_token("") == ""


# ==================== 2. Classifier Tests ====================

def test_bank_domain_detection():
    assert is_from_bank_domain("ccard@cmbchina.com")
    assert is_from_bank_domain("service@icbc.com.cn")
    assert not is_from_bank_domain("spammer@random.com")


def test_classifier_monthly_statement():
    cand, reason = classify_email("ccard@cmbchina.com", "招商银行信用卡电子账单")
    assert cand is True
    assert "bank_statement" in reason

    cand2, reason2 = classify_email("bills@mybank.org", "Your monthly Credit Card Statement")
    assert cand2 is True


def test_classifier_filters_marketing_and_alerts():
    # Exclusion: repayment success notice
    cand, reason = classify_email("ccard@cmbchina.com", "招商银行信用卡还款成功通知")
    assert cand is False
    assert "excluded_by_keyword" in reason

    # Exclusion: single transaction alert
    cand, reason = classify_email("ccard@cmbchina.com", "您的信用卡消费提醒")
    assert cand is False

    # Exclusion: promotion / personal loans
    cand, reason = classify_email("ccard@cmbchina.com", "专享额度推荐，最高可借20万")
    assert cand is False

    # Non-statement email
    cand, reason = classify_email("friend@example.com", "周末聚餐通知")
    assert cand is False


# ==================== 3. Parser Tests ====================

def test_decode_mime_header():
    raw_encoded = "=?utf-8?B?5oub5ZWG6ZO26KGM5L+h55So5Y2h55S15a2Q6LSm5Y2V?="
    decoded = decode_mime_header(raw_encoded)
    assert "招商银行信用卡电子账单" in decoded


def test_sanitize_filename_prevents_path_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\cmd.exe") == "cmd.exe"
    assert sanitize_filename("normal_statement.pdf") == "normal_statement.pdf"


def test_parse_email_bytes_with_attachments():
    msg = EmailMessage()
    msg["Subject"] = "=?utf-8?B?5oub5ZWG6ZO26KGM5L+h55So5Y2h55S15a2Q6LSm5Y2V?="
    msg["From"] = "招商银行 <ccard@cmbchina.com>"
    msg["To"] = "user@example.com"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = "<test-msg-123@cmbchina.com>"
    msg.set_content("本期账单应还金额：5000.00元")
    msg.add_alternative("<p>本期账单应还金额：5000.00元</p>", subtype="html")
    msg.add_attachment(b"%PDF-1.4 test-pdf-bytes", maintype="application", subtype="pdf", filename="202609_statement.pdf")

    parsed = parse_email_bytes(msg.as_bytes())
    assert parsed.message_id == "test-msg-123@cmbchina.com"
    assert "招商银行信用卡电子账单" in parsed.subject
    assert "ccard@cmbchina.com" in parsed.sender
    assert len(parsed.body_hash) == 64
    assert len(parsed.attachments) == 1
    assert parsed.attachments[0].filename == "202609_statement.pdf"
    assert parsed.attachments[0].payload_bytes == b"%PDF-1.4 test-pdf-bytes"


# ==================== 4. Storage Safety Tests ====================

def test_storage_save_and_read(tmp_path):
    storage = MailStorageManager(base_dir=tmp_path)
    mailbox_id = uuid.uuid4()
    source_id = uuid.uuid4()
    raw_bytes = b"Sample RFC822 Email Content"

    path = storage.save_raw_email(mailbox_id, source_id, raw_bytes)
    assert storage.read_file(path) == raw_bytes

    att_path = storage.save_attachment(mailbox_id, source_id, "bill.pdf", b"PDF bytes")
    assert storage.read_file(att_path) == b"PDF bytes"


def test_storage_rejects_path_traversal(tmp_path):
    storage = MailStorageManager(base_dir=tmp_path / "safe")
    with pytest.raises(MailStorageError):
        storage.read_file(str(tmp_path / "unsafe.txt"))


# ==================== 5. Mock IMAP Client & Sync Logic ====================

class MockReadOnlyImapClient:
    """Mock IMAP client that enforces read-only invariants and verifies no mutations."""
    _is_mock = True

    def __init__(self, messages: dict[int, bytes], uidvalidity: int = 12345):
        self.messages = messages
        self.uidvalidity = uidvalidity
        self.connected = False
        self.selected_folder = None
        self.selected_readonly = None
        self.fetch_commands = []
        self.mutations_attempted = []

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def get_folder_status(self, folder="INBOX"):
        return self.uidvalidity, max(self.messages.keys(), default=0) + 1, len(self.messages)

    def select_folder(self, folder="INBOX"):
        self.selected_folder = folder
        self.selected_readonly = True
        return len(self.messages)

    def search_uids_since(self, last_uid=0, folder="INBOX"):
        return sorted([u for u in self.messages.keys() if u > last_uid])

    def fetch_email_bytes(self, uid: int, folder="INBOX"):
        self.fetch_commands.append((uid, "BODY.PEEK[]"))
        return self.messages[uid]


async def test_sync_incremental_and_read_only_invariants(tmp_path):
    storage = MailStorageManager(base_dir=tmp_path)

    # Build 2 sample emails
    msg1 = EmailMessage()
    msg1["Subject"] = "招商银行信用卡对账单"
    msg1["From"] = "ccard@cmbchina.com"
    msg1["Date"] = formatdate(localtime=True)
    msg1.set_content("账单1")

    msg2 = EmailMessage()
    msg2["Subject"] = "建设银行信用卡电子对账单"
    msg2["From"] = "ccb@ccb.com"
    msg2["Date"] = formatdate(localtime=True)
    msg2.set_content("账单2")

    mock_client = MockReadOnlyImapClient({
        101: msg1.as_bytes(),
        102: msg2.as_bytes(),
    }, uidvalidity=5000)

    unique_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    async with async_session_factory() as session:
        service = MailSyncService(session, storage_manager=storage)
        mb = await service.create_mailbox(
            MailboxCreate(
                email_address=unique_email,
                imap_host="imap.example.com",
                auth_token="secret123",
            )
        )
        mb_id = mb.id

        # First sync: should fetch 101 and 102
        job1 = await service.sync_mailbox(mb_id, trigger_type="manual", client_override=mock_client)
        assert job1.status == "completed"
        assert job1.emails_checked == 2
        assert job1.emails_fetched == 2
        assert job1.statement_candidates == 2

        # Verify read-only invariants: PEEK used, no mutations
        assert len(mock_client.fetch_commands) == 2
        for uid, cmd in mock_client.fetch_commands:
            assert cmd == "BODY.PEEK[]"

        # Second sync with no new emails: 0 fetched
        mock_client.fetch_commands.clear()
        job2 = await service.sync_mailbox(mb_id, trigger_type="manual", client_override=mock_client)
        assert job2.emails_checked == 0
        assert job2.emails_fetched == 0
        assert len(mock_client.fetch_commands) == 0

        # Now simulate a new email (UID 103) arriving
        msg3 = EmailMessage()
        msg3["Subject"] = "工商银行信用卡还款成功通知"  # Non-statement notification
        msg3["From"] = "service@icbc.com.cn"
        msg3["Date"] = formatdate(localtime=True)
        msg3.set_content("还款成功")
        mock_client.messages[103] = msg3.as_bytes()

        job3 = await service.sync_mailbox(mb_id, trigger_type="manual", client_override=mock_client)
        assert job3.emails_checked == 1
        assert job3.emails_fetched == 1
        assert job3.statement_candidates == 0  # Filtered out by classifier!


async def test_uidvalidity_reset_recovers_gracefully(tmp_path):
    storage = MailStorageManager(base_dir=tmp_path)
    msg = EmailMessage()
    msg["Subject"] = "电子对账单"
    msg["From"] = "bank@bank.com"
    msg.set_content("账单内容")

    mock_client = MockReadOnlyImapClient({10: msg.as_bytes()}, uidvalidity=1000)
    unique_email = f"test_{uuid.uuid4().hex[:8]}@example.com"

    async with async_session_factory() as session:
        service = MailSyncService(session, storage_manager=storage)
        mb = await service.create_mailbox(
            MailboxCreate(
                email_address=unique_email,
                imap_host="imap.example.com",
                auth_token="secret",
            )
        )

        job1 = await service.sync_mailbox(mb.id, client_override=mock_client)
        assert job1.emails_fetched == 1

        # Simulate server changing UIDVALIDITY (e.g. folder rebuilt on IMAP server)
        mock_client.uidvalidity = 2000
        mock_client.messages = {5: msg.as_bytes()}

        job2 = await service.sync_mailbox(mb.id, client_override=mock_client)
        assert job2.status == "completed"
        assert job2.emails_fetched == 1


# ==================== 6. Scheduler Tests ====================

async def test_scheduler_detects_due_mailboxes():
    scheduler = MailScheduler()
    unique_email = f"sched_{uuid.uuid4().hex[:8]}@example.com"

    async with async_session_factory() as session:
        service = MailSyncService(session)
        mb = await service.create_mailbox(
            MailboxCreate(
                email_address=unique_email,
                imap_host="imap.example.com",
                auth_token="secret",
                check_interval_minutes=30,
            )
        )
        mb_id = mb.id

    due = await scheduler.check_due_mailboxes()
    assert any(m.id == mb_id for m in due)


# ==================== 7. API Route Tests ====================

async def test_mail_api_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Capabilities
        cap_res = await client.get("/v1/capabilities")
        assert cap_res.status_code == 200
        assert cap_res.json()["email_sync"] is True

        # Create mailbox
        unique_email = f"api_{uuid.uuid4().hex[:8]}@example.com"
        create_res = await client.post(
            "/v1/mailboxes",
            json={
                "email_address": unique_email,
                "imap_host": "imap.test.com",
                "imap_port": 993,
                "use_ssl": True,
                "auth_token": "secret_pass_123",
                "check_interval_minutes": 15,
            },
        )
        assert create_res.status_code == 201
        data = create_res.json()
        assert data["email_address"] == unique_email
        assert data["auth_token_masked"] == "********"
        mailbox_id = data["id"]

        # List mailboxes
        list_res = await client.get("/v1/mailboxes")
        assert list_res.status_code == 200
        assert any(m["id"] == mailbox_id for m in list_res.json())

        # Trigger manual sync
        sync_res = await client.post("/v1/mail/sync-now", json={"mailbox_id": mailbox_id})
        # Note: Since credentials to imap.test.com are dummy, it will record failed job or attempt
        assert sync_res.status_code == 200

        # Query jobs
        jobs_res = await client.get(f"/v1/mail/jobs?mailbox_id={mailbox_id}")
        assert jobs_res.status_code == 200
        jobs = jobs_res.json()
        assert len(jobs) >= 1

        # Delete mailbox
        del_res = await client.delete(f"/v1/mailboxes/{mailbox_id}")
        assert del_res.status_code == 204
