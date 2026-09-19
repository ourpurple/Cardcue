#!/usr/bin/env python3
"""Sync and parse bills for the last 2 months into CardCue database.

Usage:
  # 1. Real mailbox sync (e.g. QQ, 163, etc.):
  python scripts/sync-bills.py --server http://152.70.238.24:8000 --email user@qq.com --auth-code YOUR_AUTH_CODE

  # 2. Or generate realistic 2-month bill statements for testing:
  python scripts/sync-bills.py --server http://152.70.238.24:8000 --demo

  # 3. Optional --clean to truncate existing test tables before populating:
  python scripts/sync-bills.py --server http://152.70.238.24:8000 --clean --demo
"""

import argparse
import getpass
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_SERVER = "http://152.70.238.24:8000"

SAMPLE_ACCOUNTS = [
    {
        "bank": "招商银行",
        "alias": "招行个人经典信用卡",
        "reference": "CMB_001",
        "cards": [
            {"card_tail": "9759", "card_holder": "主卡", "color_hex": "#C25259", "card_type": "credit"},
            {"card_tail": "2090", "card_holder": "附属卡", "color_hex": "#C25259", "card_type": "credit"},
        ],
    },
    {
        "bank": "交通银行",
        "alias": "交行买单吧信用卡",
        "reference": "BCM_001",
        "cards": [
            {"card_tail": "8369", "card_holder": "主卡", "color_hex": "#3476C3", "card_type": "credit"},
        ],
    },
    {
        "bank": "农业银行",
        "alias": "农行金穗悠游信用卡",
        "reference": "ABC_001",
        "cards": [
            {"card_tail": "8753", "card_holder": "主卡", "color_hex": "#208979", "card_type": "credit"},
        ],
    },
]


def request(url: str, method: str = "GET", data: dict | list | None = None, timeout: int = 30) -> dict | list:
    req_body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={"Content-Type": "application/json"} if req_body else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            err_json = json.loads(body)
            detail = err_json.get("detail", body)
            raise RuntimeError(f"HTTP {e.code}: {detail}")
        except Exception:
            raise RuntimeError(f"HTTP {e.code}: {body}")
    except Exception as e:
        raise RuntimeError(f"网络请求失败 ({url}): {e}")


def clean_database_tables():
    try:
        import psycopg2
        db_url = "postgresql://cardcube:TPAdhfnyLmLptJxx@152.70.238.24:5432/cardcube"
        tables = [
            "change_log", "email_attachments", "statement_drafts",
            "statement_versions", "payments", "statements",
            "cards", "accounts", "email_sources",
            "mail_jobs", "mail_cursors", "mailboxes", "devices",
        ]
        print("正在清空测试数据表...")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        tables_joined = ", ".join(tables)
        cur.execute(f"TRUNCATE TABLE {tables_joined} CASCADE;")
        conn.commit()
        cur.close()
        conn.close()
        print("[OK] 数据库测试数据已全部清空。\n")
    except Exception as e:
        print(f"[!] 清空数据库失败 (若无直接数据库连接可忽略): {e}\n")


def ensure_starter_accounts(server: str) -> dict[str, dict]:
    """Ensure baseline accounts and cards exist, returning {bank: account_info}."""
    existing = request(f"{server}/v1/accounts")
    bank_map = {a["bank"]: a for a in existing}

    for item in SAMPLE_ACCOUNTS:
        bank = item["bank"]
        if bank not in bank_map:
            acct = request(f"{server}/v1/accounts", method="POST", data={
                "bank": bank,
                "alias": item["alias"],
                "reference": item["reference"],
            })
            bank_map[bank] = acct
            print(f"[OK] 自动补齐基础账户: {bank}")
        else:
            acct = bank_map[bank]

        # Check existing cards for this account
        existing_cards = request(f"{server}/v1/accounts/{acct['id']}/cards")
        existing_tails = {c["tail"] for c in existing_cards}

        for c in item["cards"]:
            tail = c["card_tail"]
            if tail not in existing_tails:
                card_payload = {
                    "account_id": acct["id"],
                    "tail": tail,
                    "display_name": f"{item['bank']}{c.get('card_holder', '')} ({tail})",
                }
                request(f"{server}/v1/cards", method="POST", data=card_payload)
                existing_tails.add(tail)
                print(f"  |-- 自动绑定卡片: 尾号 {tail}")
    return bank_map


def guess_imap_host(email_address: str) -> tuple[str, int, bool]:
    domain = email_address.split("@")[-1].lower()
    if domain in ("qq.com", "foxmail.com"):
        return ("imap.qq.com", 993, True)
    elif domain == "163.com":
        return ("imap.163.com", 993, True)
    elif domain == "126.com":
        return ("imap.126.com", 993, True)
    elif domain in ("sina.com", "sina.cn"):
        return ("imap.sina.com", 993, True)
    elif domain in ("gmail.com", "googlemail.com"):
        return ("imap.gmail.com", 993, True)
    elif domain in ("outlook.com", "hotmail.com", "live.com"):
        return ("outlook.office365.com", 993, True)
    return (f"imap.{domain}", 993, True)


def create_demo_statements(server: str, bank_map: dict[str, dict]):
    """Create realistic statements for the last 2 months for testing."""
    today = date.today()
    # Month 1 (Current month or late last month)
    m1_stmt_date = (today.replace(day=1) - timedelta(days=5))
    m1_due_date = m1_stmt_date + timedelta(days=20)
    # Month 2 (2 months ago)
    m2_stmt_date = (m1_stmt_date.replace(day=1) - timedelta(days=5))
    m2_due_date = m2_stmt_date + timedelta(days=20)

    bill_plans = [
        {"bank": "招商银行", "card_tail": "9759", "stmt": m1_stmt_date, "due": m1_due_date, "bal": 625000, "min": 62500},
        {"bank": "招商银行", "card_tail": "9759", "stmt": m2_stmt_date, "due": m2_due_date, "bal": 482000, "min": 48200},
        {"bank": "交通银行", "card_tail": "8369", "stmt": m1_stmt_date, "due": m1_due_date, "bal": 318050, "min": 31800},
        {"bank": "交通银行", "card_tail": "8369", "stmt": m2_stmt_date, "due": m2_due_date, "bal": 289000, "min": 28900},
        {"bank": "农业银行", "card_tail": "8753", "stmt": m1_stmt_date, "due": m1_due_date, "bal": 156000, "min": 15600},
        {"bank": "农业银行", "card_tail": "8753", "stmt": m2_stmt_date, "due": m2_due_date, "bal": 192000, "min": 19200},
    ]

    print("\n正在生成近两个月的真实账单数据入库...")
    for b in bill_plans:
        acct = bank_map.get(b["bank"])
        if not acct:
            continue
        payload = {
            "account_id": acct["id"],
            "currency": "CNY",
            "statement_date": b["stmt"].isoformat(),
            "due_date": b["due"].isoformat(),
            "amount_minor": b["bal"],
            "minimum_minor": b["min"],
            "source": "demo",
        }
        try:
            res = request(f"{server}/v1/statements", method="POST", data=payload)
            stmt_amt_yuan = b["bal"] / 100.0
            print(f"[OK] 已保存账单: {b['bank']} | 账单日: {b['stmt']} | 到期还款日: {b['due']} | 金额: ¥{stmt_amt_yuan:.2f}")
        except Exception as e:
            if "409" in str(e) or "already exists" in str(e):
                print(f"[-] 账单已存在 ({b['bank']} {b['stmt']})，跳过")
            else:
                print(f"[!] 保存账单跳过/失败 ({b['bank']} {b['stmt']}): {e}")


def main():
    parser = argparse.ArgumentParser(description="CardCue 账单拉取与解析入库工具 (支持近2个月筛选)")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="后台服务根地址 (默认: %(default)s)")
    parser.add_argument("--clean", action="store_true", help="先清空数据库测试数据表")
    parser.add_argument("--email", help="邮箱地址 (例如: user@qq.com)")
    parser.add_argument("--auth-code", help="邮箱 IMAP 授权码/密码 (留空将安全交互式输入)")
    parser.add_argument("--imap-host", help="IMAP 服务器地址 (默认自动根据邮箱后缀匹配)")
    parser.add_argument("--imap-port", type=int, default=993, help="IMAP 端口 (默认: 993)")
    parser.add_argument("--since-days", type=int, default=60, help="拉取近多少天的账单邮件 (默认: 60天，即近2个月)")
    parser.add_argument("--demo", action="store_true", help="直接生成并入库近两个月的仿真账单数据")
    parser.add_argument("--auto-confirm", action="store_true", default=True, help="解析草稿后自动确认入库")
    parser.add_argument("--reparse", action="store_true", help="重新解析所有已抓取的候选邮件（使用大模型/最新解析引擎，即使之前已解析过）")
    parser.add_argument("--skip-imap", action="store_true", help="跳过 IMAP 邮件拉取步骤，直接对已有邮件执行解析入库")
    args = parser.parse_args()

    if args.clean:
        clean_database_tables()

    server = args.server.rstrip("/")
    print(f"正在检查服务状态: {server}/health ...")
    try:
        health = request(f"{server}/health")
        print(f"[OK] 服务在线: {health}\n")
    except Exception as e:
        print(f"[FAIL] 无法连接到服务 {server}: {e}")
        sys.exit(1)

    # 1. Ensure starter accounts exist so statements can link
    bank_map = ensure_starter_accounts(server)

    if args.demo:
        create_demo_statements(server, bank_map)
        print("\n近两个月测试账单已全部入库！")
        print("现在打开手机 App 点击同步，即可看到近两个月的完整账单数据。")
        return

    if not args.skip_imap:
        email_address = args.email
        if not email_address:
            print("提示: 若要直接生成近两个月仿真账单进行手机测试，可运行: python scripts/sync-bills.py --demo")
            print("提示: 若仅需重新解析已拉取的邮件，可添加参数: --skip-imap --reparse")
            email_address = input("请输入要绑定的邮箱地址 (例如 your_name@qq.com，直接回车取消): ").strip()
            if not email_address:
                print("操作已取消。")
                return

        existing_mbs = request(f"{server}/v1/mailboxes")
        target_mb = next((m for m in existing_mbs if m.get("email_address") == email_address), None)

        auth_code = args.auth_code
        mb_id = None

        if target_mb and not auth_code:
            reuse = input(f"检测到邮箱 {email_address} 已存在于系统中，是否直接使用已有配置同步？[Y/n]: ").strip().lower()
            if reuse != "n":
                mb_id = target_mb["id"]
                print(f"[OK] 直接使用已有邮箱配置 (ID: {mb_id})")
            else:
                auth_code = getpass.getpass("请输入该邮箱的 IMAP 授权码 (输入时不显示字符): ").strip()
                if not auth_code:
                    print("未输入授权码，操作已取消。")
                    return
        elif not auth_code:
            auth_code = getpass.getpass("请输入该邮箱的 IMAP 授权码 (输入时不显示字符): ").strip()
            if not auth_code:
                print("未输入授权码，操作已取消。")
                return

        if auth_code:
            imap_host = args.imap_host
            if not imap_host:
                guessed_host, guessed_port, guessed_ssl = guess_imap_host(email_address)
                imap_host = guessed_host
                print(f"自动识别 IMAP 服务器: {imap_host}:{args.imap_port}")

            print(f"\n正在配置邮箱账户 {email_address} ...")
            mb_payload = {
                "email_address": email_address,
                "imap_host": imap_host,
                "imap_port": args.imap_port,
                "use_ssl": True,
                "auth_token": auth_code,
                "check_interval_minutes": 30,
            }
            try:
                mb = request(f"{server}/v1/mailboxes", method="POST", data=mb_payload)
                mb_id = mb["id"]
                print(f"[OK] 邮箱已成功注册入库 (ID: {mb_id})")
            except RuntimeError as e:
                if "already exists" in str(e) or "409" in str(e):
                    mbs = request(f"{server}/v1/mailboxes")
                    target = next((m for m in mbs if m["email_address"] == email_address), None)
                    if target:
                        mb_id = target["id"]
                        request(f"{server}/v1/mailboxes/{mb_id}", method="PATCH", data={"auth_token": auth_code})
                        print(f"[OK] 邮箱已存在，更新授权凭证成功 (ID: {mb_id})")
                    else:
                        print(f"[FAIL] 获取已有邮箱失败: {e}")
                        sys.exit(1)
                else:
                    print(f"[FAIL] 邮箱注册失败: {e}")
                    sys.exit(1)

        # 3. Trigger IMAP sync for the last N days
        print(f"\n正在通过 IMAP 拉取近 {args.since_days} 天 (约2个月) 的账单邮件...")
        sync_data = {
            "mailbox_id": mb_id,
            "since_days": args.since_days,
        }
        try:
            sync_resp = request(f"{server}/v1/mail/sync-now", method="POST", data=sync_data, timeout=180)
        except RuntimeError as e:
            if "extra_forbidden" in str(e) or "since_days" in str(e):
                print("[提示] 远程 VPS 后端运行的是基础镜像，尚未更新 since_days 过滤参数支持。")
                print("       正在自动降级为标准拉取（拉取所有未同步邮件）...")
                sync_resp = request(f"{server}/v1/mail/sync-now", method="POST", data={"mailbox_id": mb_id}, timeout=300)
            else:
                raise
        print(f"[OK] 邮件抓取任务已完成: {sync_resp.get('message')}")
    else:
        print("\n[提示] 已指定 --skip-imap，跳过 IMAP 邮件拉取阶段，直接解析入库现有邮件...")

    # 4. Parse pending email drafts
    parse_param = "?reparse=true" if args.reparse else ""
    engine_desc = "（使用大模型 / 最新解析引擎重新解析所有候选邮件）" if args.reparse else "（HTML/PDF）"
    print(f"\n正在启动解析引擎解析邮件草稿 {engine_desc}...")
    parse_resp = request(f"{server}/v1/drafts/parse-all-pending{parse_param}", method="POST", timeout=300)
    total_parsed = len(parse_resp) if isinstance(parse_resp, list) else parse_resp.get("total_parsed", 0)
    print(f"[OK] 解析完成，成功提取 {total_parsed} 份账单草稿")

    # 5. List drafts and confirm into statements
    drafts = request(f"{server}/v1/drafts?status=pending_review")
    print(f"\n待审核账单草稿数: {len(drafts)}")

    if not drafts:
        print("未检测到新的待确认草稿 (可能近两个月邮箱内无银行对账单邮件，或已归档)。")
        return

    print("\n" + "=" * 60)
    print(f"{'银行':<8} {'尾号':<6} {'账单日':<12} {'到期还款日':<12} {'金额(元)':<10}")
    print("-" * 60)
    for d in drafts:
        amt_yuan = (d.get("amount_minor") or 0) / 100.0
        tails = ",".join(d.get("card_tails") or [])
        print(f"{d.get('bank') or '未知':<8} {tails or '----':<6} {str(d.get('statement_date') or '----'):<12} {str(d.get('due_date') or '----'):<12} ¥{amt_yuan:<10.2f}")
    print("=" * 60)

    if args.auto_confirm:
        print("\n正在自动将已识别卡片的草稿确认归档进正式数据库...")
        for d in drafts:
            draft_id = d["id"]
            bank = d.get("bank") or "未知银行"
            if bank not in bank_map:
                try:
                    acct = request(f"{server}/v1/accounts", method="POST", data={
                        "bank": bank,
                        "alias": f"{bank}信用卡",
                        "reference": f"AUTO_{bank}",
                    })
                    bank_map[bank] = acct
                    print(f"[OK] 自动为草稿创建新银行账户: {bank}")
                except Exception as e:
                    print(f"[-] 创建账户失败 ({bank}): {e}")
                    acct = None
            else:
                acct = bank_map[bank]

            acct_id = d.get("matched_account_id") or (acct["id"] if acct else None)
            if not acct_id:
                print(f"[!] 草稿 {draft_id[:8]} 未匹配到对应账户，跳过自动确认")
                continue

            card_id = d.get("matched_card_id")
            card_tails = d.get("card_tails") or []
            if not card_id and card_tails:
                try:
                    existing_cards = request(f"{server}/v1/accounts/{acct_id}/cards")
                    tail_card_map = {c["tail"]: c["id"] for c in existing_cards}
                    target_tail = card_tails[0]
                    if target_tail in tail_card_map:
                        card_id = tail_card_map[target_tail]
                    else:
                        new_card = request(f"{server}/v1/cards", method="POST", data={
                            "account_id": acct_id,
                            "tail": target_tail,
                            "display_name": f"{bank} ({target_tail})",
                        })
                        card_id = new_card["id"]
                        print(f"  |-- 自动创建并绑定卡片: 尾号 {target_tail}")
                except Exception as e:
                    print(f"  |-- [-] 绑定卡片跳过: {e}")

            if d.get("amount_minor") is None:
                print(f"[!] 草稿 {draft_id[:8]} 未识别出有效金额，需人工核实，跳过自动确认")
                continue
            if not d.get("statement_date") or not d.get("due_date"):
                print(f"[!] 草稿 {draft_id[:8]} 缺少账单日或到期还款日，跳过自动确认")
                continue
            if str(d.get("due_date")) < str(d.get("statement_date")):
                print(f"[!] 草稿 {draft_id[:8]} 到期还款日早于账单日，存在异常，跳过自动确认")
                continue

            confirm_payload = {
                "account_id": acct_id,
                "currency": d.get("currency") or "CNY",
            }
            if card_id:
                confirm_payload["card_id"] = card_id
            if d.get("amount_minor") is not None:
                confirm_payload["amount_minor"] = d["amount_minor"]
            if d.get("minimum_minor") is not None:
                confirm_payload["minimum_minor"] = d["minimum_minor"]
            if d.get("statement_date") is not None:
                confirm_payload["statement_date"] = str(d["statement_date"])
            if d.get("due_date") is not None:
                confirm_payload["due_date"] = str(d["due_date"])

            try:
                stmt_res = request(f"{server}/v1/drafts/{draft_id}/confirm", method="POST", data=confirm_payload)
                stmt_id = stmt_res.get("statement", {}).get("id") or stmt_res.get("id") or ""
                print(f"[OK] 草稿 {draft_id[:8]} 已确认入库正式账单 (ID: {stmt_id[:8]})")
            except Exception as e:
                print(f"[!] 草稿 {draft_id[:8]} 确认失败: {e}")

    print("\n所有近两个月账单已处理完毕！")
    print("现在打开手机 CardCue App，点击右上角【同步】或下拉刷新，即可在手机上看到正式账单！")


if __name__ == "__main__":
    main()