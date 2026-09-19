"""Integration tests for S4 statement drafts REST API and review workflow."""

import uuid
from datetime import date, datetime, timezone
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from cardcue_api.main import app
from cardcue_api.mail.storage import MailStorageManager
from cardcue_api.persistence import Account, Card, ChangeLog, EmailSource, Mailbox, StatementDraftModel
from cardcue_api.persistence.database import async_session_factory


async def test_drafts_end_to_end_flow(tmp_path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create test Account and Card
        acct_res = await client.post("/v1/accounts", json={
            "bank": "招商银行",
            "alias": f"招行信用卡_{uuid.uuid4().hex[:6]}",
            "reference": f"CMB_{uuid.uuid4().hex[:8]}",
        })
        assert acct_res.status_code == 201
        acct_data = acct_res.json()
        account_id = acct_data["id"]

        test_tail = f"{uuid.uuid4().int % 9000 + 1000}"
        card_res = await client.post("/v1/cards", json={
            "account_id": account_id,
            "tail": test_tail,
            "display_name": "主卡",
        })
        assert card_res.status_code == 201
        card_id = card_res.json()["id"]

        # 2. Setup mock raw storage and EmailSource
        storage = MailStorageManager(base_dir=tmp_path)
        raw_html = (
            "<html><body>"
            "<h1>招商银行信用卡电子账单</h1>"
            f"<p>尊敬的客户，您的信用卡账户（卡号末四位：{test_tail}）对账单如下：</p>"
            "<p>本期应还金额：￥15,820.50</p>"
            "<p>最低还款额：￥1,582.00</p>"
            "<p>账单日：2026-09-18</p>"
            "<p>到期还款日：2026-10-06</p>"
            "</body></html>"
        )
        sample_mime = (
            f"Subject: 招商银行信用卡电子账单\r\n"
            f"From: ccard@cmbchina.com\r\n"
            f"To: user@example.com\r\n"
            f"Date: Fri, 18 Sep 2026 12:00:00 +0800\r\n"
            f"Content-Type: text/html; charset=utf-8\r\n\r\n"
            f"{raw_html}"
        ).encode("utf-8")

        async with async_session_factory() as session:
            # Create dummy mailbox
            mb = Mailbox(
                email_address=f"test_{uuid.uuid4().hex[:8]}@example.com",
                imap_host="imap.example.com",
                encrypted_auth_token="fake",
            )
            session.add(mb)
            await session.flush()

            email_id = uuid.uuid4()
            stored_path = storage.save_raw_email(mb.id, email_id, sample_mime)

            source = EmailSource(
                id=email_id,
                mailbox_id=mb.id,
                folder="INBOX",
                uid=101,
                uidvalidity=1,
                message_id=f"msg_{uuid.uuid4().hex}@cmb",
                subject="招商银行信用卡电子账单",
                sender="ccard@cmbchina.com",
                recipient=mb.email_address,
                email_date=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc),
                body_hash="fakehash",
                raw_storage_path=stored_path,
                is_statement_candidate=True,
                parse_status="pending",
            )
            session.add(source)
            await session.commit()
            source_id = str(source.id)

        # 3. Parse EmailSource into Draft via API
        parse_res = await client.post(f"/v1/drafts/parse-source/{source_id}")
        assert parse_res.status_code == 200
        draft_data = parse_res.json()
        draft_id = draft_data["id"]

        assert draft_data["status"] == "pending_review"
        assert draft_data["bank"] == "招商银行"
        assert draft_data["amount_minor"] == 1582050
        assert draft_data["minimum_minor"] == 158200
        assert draft_data["statement_date"] == "2026-09-18"
        assert draft_data["due_date"] == "2026-10-06"
        assert test_tail in draft_data["card_tails"]
        # Automatic matching resolution
        assert draft_data["matched_account_id"] == account_id
        assert draft_data["matched_card_id"] == card_id
        assert len(draft_data["evidence"]) >= 2

        # 4. List Drafts
        list_res = await client.get("/v1/drafts?status=pending_review")
        assert list_res.status_code == 200
        draft_ids = [d["id"] for d in list_res.json()]
        assert draft_id in draft_ids

        # 5. Get Draft Detail
        detail_res = await client.get(f"/v1/drafts/{draft_id}")
        assert detail_res.status_code == 200
        assert detail_res.json()["id"] == draft_id

        # 6. Confirm Draft into official Statement
        confirm_res = await client.post(
            f"/v1/drafts/{draft_id}/confirm",
            json={
                "account_id": account_id,
                "card_id": card_id,
                "amount_minor": 1582050,
                "minimum_minor": 158200,
                "statement_date": "2026-09-18",
                "due_date": "2026-10-06",
            },
            headers={"X-Device-Id": "test-device-01"},
        )
        assert confirm_res.status_code == 200
        confirm_data = confirm_res.json()
        assert confirm_data["draft_id"] == draft_id
        stmt = confirm_data["statement"]
        assert stmt["account_id"] == account_id
        assert stmt["remaining_minor"] == 1582050
        ver = confirm_data["version"]
        assert ver["amount_minor"] == 1582050
        assert ver["minimum_minor"] == 158200
        assert ver["version_number"] == 1

        # 7. Check draft status updated to confirmed
        recheck_draft = await client.get(f"/v1/drafts/{draft_id}")
        assert recheck_draft.status_code == 200
        assert recheck_draft.json()["status"] == "confirmed"
        assert recheck_draft.json()["confirmed_version_id"] == ver["id"]

        # 8. Duplicate confirmation rejected (Conflict 409)
        dup_confirm = await client.post(
            f"/v1/drafts/{draft_id}/confirm",
            json={"account_id": account_id},
        )
        assert dup_confirm.status_code == 409

        # 9. Verify ChangeLog was written for sync
        async with async_session_factory() as session:
            stmt_id = uuid.UUID(stmt["id"])
            changes = await session.execute(
                select(ChangeLog).where(ChangeLog.entity_id == stmt_id)
            )
            logs = list(changes.scalars().all())
            assert len(logs) >= 1
            assert logs[0].action == "create"
            assert logs[0].entity_type == "statement"


async def test_draft_rejection_and_conflict():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a draft directly in pending_review
        async with async_session_factory() as session:
            draft = StatementDraftModel(
                status="pending_review",
                bank="测试银行",
                currency="CNY",
                amount_minor=10000,
                minimum_minor=1000,
                statement_date=date(2026, 9, 1),
                due_date=date(2026, 9, 20),
                extractor_name="test",
            )
            session.add(draft)
            await session.commit()
            draft_id = str(draft.id)

        # Reject draft
        reject_res = await client.post(
            f"/v1/drafts/{draft_id}/reject",
            json={"reason": "不是本人的信用卡账单"},
        )
        assert reject_res.status_code == 200
        assert reject_res.json()["status"] == "rejected"
        assert reject_res.json()["rejection_reason"] == "不是本人的信用卡账单"

        # Double reject should conflict (409)
        dup_reject = await client.post(
            f"/v1/drafts/{draft_id}/reject",
            json={"reason": "重复拒绝"},
        )
        assert dup_reject.status_code == 409


async def test_draft_confirm_validation_errors():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create an account
        acct_res = await client.post("/v1/accounts", json={
            "bank": "测试银行",
            "alias": f"验证账户_{uuid.uuid4().hex[:6]}",
        })
        assert acct_res.status_code == 201
        account_id = acct_res.json()["id"]

        # Draft with due_date before statement_date
        async with async_session_factory() as session:
            draft = StatementDraftModel(
                status="pending_review",
                bank="测试银行",
                currency="CNY",
                amount_minor=5000,
                minimum_minor=500,
                statement_date=date(2026, 9, 20),
                due_date=date(2026, 9, 10),  # INVALID: due_date < statement_date
                extractor_name="test",
            )
            session.add(draft)
            await session.commit()
            draft_id = str(draft.id)

        # Confirm should fail with 409 due to due_date < statement_date
        res = await client.post(
            f"/v1/drafts/{draft_id}/confirm",
            json={"account_id": account_id},
        )
        assert res.status_code == 409
        assert "due_date must be >= statement_date" in res.json()["detail"]
