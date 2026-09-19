#!/usr/bin/env python3
"""Helper script to verify backend connectivity and initialize starter accounts/cards for testing."""

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_SERVER = "http://127.0.0.1:8000"

SAMPLE_ACCOUNTS = [
    {
        "bank": "招商银行",
        "alias": "招行个人经典信用卡",
        "reference": "CMB_001",
        "cards": [
            {"card_tail": "9759", "card_holder": "持卡人", "color_hex": "#C25259", "card_type": "credit"},
            {"card_tail": "2090", "card_holder": "持卡人", "color_hex": "#C25259", "card_type": "credit"},
        ],
    },
    {
        "bank": "交通银行",
        "alias": "交行买单吧信用卡",
        "reference": "BCM_001",
        "cards": [
            {"card_tail": "8369", "card_holder": "持卡人", "color_hex": "#3476C3", "card_type": "credit"},
        ],
    },
    {
        "bank": "农业银行",
        "alias": "农行金穗悠游信用卡",
        "reference": "ABC_001",
        "cards": [
            {"card_tail": "8753", "card_holder": "持卡人", "color_hex": "#208979", "card_type": "credit"},
        ],
    },
]


def request(url: str, method: str = "GET", data: dict | None = None) -> dict:
    req_body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={"Content-Type": "application/json"} if req_body else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            err_json = json.loads(body)
            raise RuntimeError(f"HTTP {e.code}: {err_json.get('detail', body)}")
        except Exception:
            raise RuntimeError(f"HTTP {e.code}: {body}")
    except Exception as e:
        raise RuntimeError(f"网络请求失败 ({url}): {e}")


def main():
    parser = argparse.ArgumentParser(description="CardCue 测试数据初始化工具")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="后台服务根地址 (默认: %(default)s)")
    parser.add_argument("--force", action="store_true", help="强制重复创建已有账户")
    args = parser.parse_args()

    server = args.server.rstrip("/")
    print(f"正在检查服务状态: {server}/health ...")
    try:
        health = request(f"{server}/health")
        print(f"✓ 服务健康: {health}")
    except Exception as e:
        print(f"✗ 无法连接到服务: {e}")
        sys.exit(1)

    print("\n正在获取当前账户列表...")
    existing = request(f"{server}/v1/accounts")
    existing_banks = {a["bank"] for a in existing}
    print(f"当前已有账户数: {len(existing)} (包含银行: {list(existing_banks) or '无'})")

    if existing and not args.force:
        print("已有账户存在，跳过初始化。若要继续添加，请使用 --force 参数。")
        return

    print("\n正在初始化测试银行账户与卡片...")
    for item in SAMPLE_ACCOUNTS:
        if item["bank"] in existing_banks and not args.force:
            print(f"- 跳过已有银行: {item['bank']}")
            continue

        acct_payload = {
            "bank": item["bank"],
            "alias": item["alias"],
            "reference": item["reference"],
        }
        try:
            created_acct = request(f"{server}/v1/accounts", method="POST", data=acct_payload)
            acct_id = created_acct["id"]
            print(f"✓ 创建账户成功: {item['bank']} (ID: {acct_id})")

            for card in item["cards"]:
                created_card = request(f"{server}/v1/accounts/{acct_id}/cards", method="POST", data=card)
                print(f"  └─ 绑定卡片: 尾号 {card['card_tail']} (ID: {created_card['id']})")
        except Exception as e:
            print(f"✗ 创建账户/卡片失败 ({item['bank']}): {e}")

    print("\n初始化完成！App 启动或点击同步时将自动下载以上账户与卡片。")


if __name__ == "__main__":
    main()
