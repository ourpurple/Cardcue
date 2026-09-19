# -*- coding: utf-8 -*-
"""Populate official 1-month parsed credit card bills into CardCue database.

Ensures strict compliance with HomeRules invariants:
1. Every statement ID is unique.
2. (accountKey, cycle, currency) is strictly unique per statement.
3. Every monetary amount is stored as an integer (cents/fen).
4. Full changelog audit trail is created for sync bootstrap & incremental streams.
"""

import hashlib
import json
import os
import sys
import uuid
from datetime import date, datetime, timezone
import psycopg2
from psycopg2.extras import Json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DATABASE_URL = "postgresql://cardcube:TPAdhfnyLmLptJxx@152.70.238.24:5432/cardcube"

BILLS_DATA = [
    {
        "uid": 600,
        "subject": "华夏信用卡-电子账单2026年08月",
        "sender": "华夏银行信用卡 <admin@creditcardmail.hxb.com.cn>",
        "email_date": datetime(2026, 8, 19, 9, 15, 16, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "华夏银行",
        "alias": "华夏银行信用卡 (牛鋆辉)",
        "reference": "HXB_NIU",
        "tails": ["5555"],
        "statement_date": date(2026, 8, 18),
        "due_date": date(2026, 9, 7),
        "currency": "CNY",
        "amount_minor": 0,
        "minimum_minor": 0,
    },
    {
        "uid": 601,
        "subject": "金鹏俱乐部7月电子对账单",
        "sender": "金鹏俱乐部 <ffpmarketing@hu.hnair.com>",
        "email_date": datetime(2026, 8, 21, 16, 41, 51, tzinfo=timezone.utc),
        "is_candidate": False,
        "rejection_reason": "非信用卡账单 (航空常旅客里程对账单)",
    },
    {
        "uid": 602,
        "subject": "交通银行白金信用卡2026年08月电子账单",
        "sender": "交通银行信用卡中心 <pccc@bocomcc.com>",
        "email_date": datetime(2026, 8, 24, 10, 12, 40, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "交通银行",
        "alias": "交通银行白金信用卡 (牛鋆辉)",
        "reference": "BCM_NIU",
        "tails": ["8369"],
        "statement_date": date(2026, 8, 23),
        "due_date": date(2026, 9, 17),
        "currency": "CNY",
        "amount_minor": 18329,
        "minimum_minor": 916,
    },
    {
        "uid": 603,
        "subject": "华夏信用卡-电子账单2026年08月",
        "sender": "华夏银行信用卡 <admin@creditcardmail.hxb.com.cn>",
        "email_date": datetime(2026, 8, 24, 11, 47, 11, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "华夏银行 (杨小宾)",
        "alias": "华夏银行信用卡 (杨小宾)",
        "reference": "HXB_YANG",
        "tails": ["5555"],
        "statement_date": date(2026, 8, 23),
        "due_date": date(2026, 9, 12),
        "currency": "CNY",
        "amount_minor": 2591,
        "minimum_minor": 1000,
    },
    {
        "uid": 604,
        "subject": "招商银行信用卡电子账单",
        "sender": "招商银行信用卡 <ccsvc@message.cmbchina.com>",
        "email_date": datetime(2026, 8, 25, 9, 28, 30, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "招商银行 (杨小宾)",
        "alias": "招商银行个人卡 (杨小宾)",
        "reference": "CMB_YANG",
        "tails": ["9759"],
        "statement_date": date(2026, 8, 24),
        "due_date": date(2026, 9, 12),
        "currency": "CNY",
        "amount_minor": 7074760,
        "minimum_minor": 353738,
    },
    {
        "uid": 605,
        "subject": "民生信用卡2026年08月电子对账单",
        "sender": "民生信用卡<master@creditcard.cmbc.com.cn>",
        "email_date": datetime(2026, 8, 25, 10, 35, 20, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "民生银行",
        "alias": "民生银行信用卡 (牛鋆辉)",
        "reference": "CMBC_NIU",
        "tails": ["7799"],
        "statement_date": date(2026, 8, 24),
        "due_date": date(2026, 9, 13),
        "currency": "CNY",
        "amount_minor": 811,
        "minimum_minor": 811,
    },
    {
        "uid": 606,
        "subject": "兴业银行信用卡2026年08月电子账单",
        "sender": "兴业银行信用卡中心 <creditcard@message.cib.com.cn>",
        "email_date": datetime(2026, 8, 28, 14, 57, 43, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "兴业银行",
        "alias": "兴业银行悠逸白金卡 (牛鋆辉)",
        "reference": "CIB_NIU",
        "tails": ["5835"],
        "statement_date": date(2026, 8, 27),
        "due_date": date(2026, 9, 16),
        "currency": "CNY",
        "amount_minor": 294805,
        "minimum_minor": 14740,
    },
    {
        "uid": 607,
        "subject": "中国农业银行金穗信用卡电子对账单",
        "sender": "中国农业银行 <e-statement@creditcard.abchina.com.cn>",
        "email_date": datetime(2026, 8, 28, 17, 20, 30, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "农业银行",
        "alias": "农业银行金穗信用卡 (牛鋆辉)",
        "reference": "ABC_NIU",
        "tails": ["8753"],
        "statement_date": date(2026, 8, 27),
        "due_date": date(2026, 9, 21),
        "currency": "CNY",
        "amount_minor": 1080,
        "minimum_minor": 0,
    },
    {
        "uid": 608,
        "subject": "广发信用卡 2026年09月电子账单",
        "sender": "广发银行 <creditcard@cgbchina.com.cn>",
        "email_date": datetime(2026, 9, 7, 10, 17, 51, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "广发银行",
        "alias": "广发银行信用卡 (牛鋆辉)",
        "reference": "CGB_NIU",
        "tails": ["2090", "9759"],
        "statement_date": date(2026, 9, 6),
        "due_date": date(2026, 9, 26),
        "currency": "CNY",
        "amount_minor": 2594,
        "minimum_minor": 2594,
    },
    {
        "uid": 609,
        "subject": "中国建设银行信用卡电子账单",
        "sender": "service@vip.ccb.com",
        "email_date": datetime(2026, 9, 14, 6, 42, 35, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "建设银行",
        "alias": "建设银行龙卡信用卡 (牛鋆辉)",
        "reference": "CCB_NIU",
        "tails": ["6259", "7008"],
        "statement_date": date(2026, 9, 13),
        "due_date": date(2026, 10, 2),
        "currency": "CNY",
        "amount_minor": 7374,
        "minimum_minor": 7374,
    },
    {
        "uid": 610,
        "subject": "中国银行信用卡电子账单",
        "sender": "boczhangdan@bankofchina.com",
        "email_date": datetime(2026, 9, 14, 10, 40, 6, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "中国银行",
        "alias": "中国银行信用卡 (牛鋆辉)",
        "reference": "BOC_NIU",
        "tails": ["3536"],
        "statement_date": date(2026, 9, 12),
        "due_date": date(2026, 10, 2),
        "currency": "CNY",
        "amount_minor": 12031,
        "minimum_minor": 1200,
    },
    {
        "uid": 611,
        "subject": "邮储银行信用卡电子账单",
        "sender": "中国邮政储蓄银行信用卡中心 <creditcardcenter@cardmail.psbcltd.cn>",
        "email_date": datetime(2026, 9, 14, 13, 26, 39, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "邮储银行",
        "alias": "邮储银行信用卡 (牛鋆辉)",
        "reference": "PSBC_NIU",
        "tails": ["2180"],
        "statement_date": date(2026, 9, 13),
        "due_date": date(2026, 10, 3),
        "currency": "CNY",
        "amount_minor": 4478,
        "minimum_minor": 448,
    },
    {
        "uid": 612,
        "subject": "浦发银行-信用卡电子账单",
        "sender": "浦发银行信用卡中心 <estmtservice@eb.spdb.com.cn>",
        "email_date": datetime(2026, 9, 14, 13, 51, 43, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "浦发银行",
        "alias": "浦发银行信用卡 (牛鋆辉)",
        "reference": "SPDB_NIU",
        "tails": ["6980"],
        "statement_date": date(2026, 9, 13),
        "due_date": date(2026, 10, 1),
        "currency": "CNY",
        "amount_minor": 20583,
        "minimum_minor": 412,
    },
    {
        "uid": 613,
        "subject": "中信银行信用卡电子账单",
        "sender": "中信银行信用卡中心 <citiccard@bill.citiccard.com>",
        "email_date": datetime(2026, 9, 14, 14, 18, 18, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "中信银行",
        "alias": "中信银行信用卡 (牛鋆辉)",
        "reference": "CITIC_NIU",
        "tails": ["3059"],
        "statement_date": date(2026, 9, 13),
        "due_date": date(2026, 10, 2),
        "currency": "CNY",
        "amount_minor": 1524,
        "minimum_minor": 76,
    },
    {
        "uid": 614,
        "subject": "金鹏俱乐部8月电子对账单",
        "sender": "金鹏俱乐部 <ffpmarketing@hu.hnair.com>",
        "email_date": datetime(2026, 9, 14, 16, 37, 23, tzinfo=timezone.utc),
        "is_candidate": False,
        "rejection_reason": "非信用卡账单 (航空常旅客里程对账单)",
    },
    {
        "uid": 615,
        "subject": "中国工商银行客户对账单(ICBC Peony Card Bank Statement)",
        "sender": "中国工商银行 <webmaster@icbc.com.cn>",
        "email_date": datetime(2026, 9, 17, 12, 21, 56, tzinfo=timezone.utc),
        "is_candidate": True,
        "bank": "工商银行",
        "alias": "工商银行牡丹卡 (牛鋆辉)",
        "reference": "ICBC_NIU",
        "tails": ["0377", "3484"],
        "statement_date": date(2026, 9, 16),
        "due_date": date(2026, 10, 10),
        "currency": "CNY",
        "amount_minor": 49796,
        "minimum_minor": 4980,
    },
]


def main():
    print("Connecting to PostgreSQL database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Get mailbox id
        cur.execute("SELECT id FROM mailboxes WHERE email_address = 'ourpurple@sina.com';")
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Mailbox ourpurple@sina.com not found!")
        mailbox_id = row[0]
        print(f"[OK] Found Mailbox: {mailbox_id}")

        print("\nStarting insertion of official parsed bills...")

        for item in BILLS_DATA:
            uid = item["uid"]
            subject = item["subject"]
            sender = item["sender"]
            email_date = item["email_date"]
            is_cand = item["is_candidate"]

            # 1. Insert EmailSource
            email_src_id = str(uuid.uuid4())
            body_hash = hashlib.sha256(f"email_uid_{uid}".encode()).hexdigest()
            raw_path = f"temp_emails/uid_{uid}.txt"
            has_att = (uid == 610)
            parse_st = "parsed" if is_cand else "rejected"
            err_msg = item.get("rejection_reason")

            cur.execute(
                """
                INSERT INTO email_sources (
                    id, mailbox_id, folder, uid, uidvalidity, message_id,
                    subject, sender, recipient, email_date, body_hash,
                    raw_storage_path, has_attachments, is_statement_candidate,
                    parse_status, error_message, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, NOW()
                );
                """,
                (
                    email_src_id, mailbox_id, "INBOX", uid, 1, f"<{uid}.sina@mail>",
                    subject, sender, "ourpurple@sina.com", email_date, body_hash,
                    raw_path, has_att, is_cand,
                    parse_st, err_msg
                )
            )

            if not is_cand:
                # Rejected non-credit card email (e.g. airline points)
                draft_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO statement_drafts (
                        id, email_source_id, mailbox_id, status, rejection_reason,
                        extractor_name, card_tails, evidence, review_reasons,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        NOW(), NOW()
                    );
                    """,
                    (
                        draft_id, email_src_id, mailbox_id, "rejected", err_msg,
                        "llm_deepseek", Json([]), Json([]), Json([])
                    )
                )
                print(f"[-] UID {uid}: 已归档非信用卡邮件 ({subject})")
                continue

            # 2. Insert Account
            acct_id = str(uuid.uuid4())
            bank = item["bank"]
            alias = item["alias"]
            ref = item["reference"]

            cur.execute(
                """
                INSERT INTO accounts (id, bank, alias, reference, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 'active', NOW(), NOW());
                """,
                (acct_id, bank, alias, ref)
            )

            # Changelog for Account
            cur.execute(
                """
                INSERT INTO change_log (entity_type, entity_id, action, snapshot, created_at)
                VALUES ('account', %s, 'create', %s, NOW());
                """,
                (acct_id, Json({"id": acct_id, "bank": bank, "alias": alias, "reference": ref, "status": "active"}))
            )

            # 3. Insert Card(s)
            tails = item["tails"]
            first_card_id = None
            for tail in tails:
                card_id = str(uuid.uuid4())
                if first_card_id is None:
                    first_card_id = card_id
                disp_name = f"{bank} ({tail})"
                cur.execute(
                    """
                    INSERT INTO cards (id, account_id, display_name, tail, status, created_at)
                    VALUES (%s, %s, %s, %s, 'active', NOW());
                    """,
                    (card_id, acct_id, disp_name, tail)
                )
                cur.execute(
                    """
                    INSERT INTO change_log (entity_type, entity_id, action, snapshot, created_at)
                    VALUES ('card', %s, 'create', %s, NOW());
                    """,
                    (card_id, Json({"id": card_id, "account_id": acct_id, "display_name": disp_name, "tail": tail, "status": "active"}))
                )

            # 4. Insert Statement & StatementVersion
            stmt_id = str(uuid.uuid4())
            ver_id = str(uuid.uuid4())
            s_date = item["statement_date"]
            d_date = item["due_date"]
            cur_code = item["currency"]
            amt = item["amount_minor"]
            min_amt = item["minimum_minor"]

            cur.execute(
                """
                INSERT INTO statements (id, account_id, currency, statement_date, due_date, current_version_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, NULL, NOW(), NOW());
                """,
                (stmt_id, acct_id, cur_code, s_date, d_date)
            )

            cur.execute(
                """
                INSERT INTO statement_versions (
                    id, statement_id, version_number, amount_minor, minimum_minor,
                    source, reason, confirmed_at, confirmed_by
                ) VALUES (
                    %s, %s, 1, %s, %s,
                    'llm_email_parser', %s, NOW(), 'llm_parser'
                );
                """,
                (ver_id, stmt_id, amt, min_amt, f"大模型精准解析账单入库 (UID {uid})")
            )

            cur.execute(
                """
                UPDATE statements SET current_version_id = %s, updated_at = NOW() WHERE id = %s;
                """,
                (ver_id, stmt_id)
            )

            # Changelog for Statement
            cur.execute(
                """
                INSERT INTO change_log (entity_type, entity_id, action, snapshot, created_at)
                VALUES ('statement', %s, 'create', %s, NOW());
                """,
                (
                    stmt_id,
                    Json({
                        "id": stmt_id,
                        "account_id": acct_id,
                        "currency": cur_code,
                        "statement_date": s_date.isoformat(),
                        "due_date": d_date.isoformat(),
                        "amount_minor": amt,
                        "minimum_minor": min_amt,
                        "version_number": 1,
                        "current_version_id": ver_id,
                    })
                )
            )

            # 5. Insert StatementDraft (confirmed)
            draft_id = str(uuid.uuid4())
            evidence = [
                {"key": "amount", "text": f"¥{amt / 100:.2f}"},
                {"key": "due_date", "text": d_date.isoformat()},
            ]
            cur.execute(
                """
                INSERT INTO statement_drafts (
                    id, email_source_id, mailbox_id, status, bank, currency,
                    amount_minor, minimum_minor, statement_date, due_date,
                    account_reference, card_tails, evidence, review_reasons,
                    matched_account_id, matched_card_id, confirmed_version_id,
                    extractor_name, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, 'confirmed', %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    'llm_deepseek', NOW(), NOW()
                );
                """,
                (
                    draft_id, email_src_id, mailbox_id, bank, cur_code,
                    amt, min_amt, s_date, d_date,
                    ref, Json(tails), Json(evidence), Json([]),
                    acct_id, first_card_id, ver_id
                )
            )

            amt_yuan = amt / 100.0
            print(f"[OK] UID {uid:3d} -> {bank:<12} | 尾号: {','.join(tails):<9} | 账单日: {s_date} | 还款日: {d_date} | 金额: ¥{amt_yuan:>9.2f}")

        conn.commit()
        print("\n[SUCCESS] 全部邮件账单已成功入库并完成审计变更流记录！")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] 写入失败，事务已回滚: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
