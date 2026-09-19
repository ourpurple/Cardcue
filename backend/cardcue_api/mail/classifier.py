"""Email classifier to identify credit card monthly statements and filter out marketing/reminders."""

import re

# Recognizable Chinese and international bank sender domains
KNOWN_BANK_DOMAINS = [
    "cmbchina.com",
    "cmb-creditcard.com",
    "icbc.com.cn",
    "ccb.com",
    "ccb.cn",
    "bankcomm.com",
    "boc.cn",
    "citicbank.com",
    "cebbank.com",
    "spdb.com.cn",
    "pingan.com.cn",
    "cgbchina.com.cn",
    "cmbc.com.cn",
    "hxb.com.cn",
    "cib.com.cn",
    "psbc.com",
    "bosc.cn",
    "bankofbeijing.com.cn",
    "hsbc.com.cn",
    "sc.com",
    "citibank.com",
]

# Patterns for negative matches (notifications, single transaction alerts, marketing, verification codes)
EXCLUSION_KEYWORDS = [
    "还款成功",
    "还款确认",
    "交易提醒",
    "动账提醒",
    "动账通知",
    "消费提醒",
    "消费通知",
    "取现通知",
    "转账提醒",
    "验证码",
    "动态密码",
    "密码重置",
    "理财推荐",
    "专享额度",
    "额度提升",
    "分期优惠",
    "借款推荐",
    "积分兑换",
    "优惠活动",
    "营销推广",
    "温馨提示",
]

# Patterns for positive matches indicating a periodic / monthly credit card statement
STATEMENT_KEYWORDS = [
    "信用卡电子对账单",
    "信用卡电子账单",
    "信用卡对账单",
    "信用卡账单",
    "信用卡月结单",
    "电子对账单",
    "电子账单",
    "对账单",
    "月结单",
    "e-statement",
    "credit card statement",
    "statement of account",
    "billing statement",
]


def is_from_bank_domain(sender: str) -> bool:
    """Check if the sender email address matches any known banking domain."""
    if not sender:
        return False
    sender_lower = sender.lower()
    for domain in KNOWN_BANK_DOMAINS:
        if f"@{domain}" in sender_lower or f".{domain}" in sender_lower:
            return True
    return False


def classify_email(sender: str, subject: str, body_preview: str = "") -> tuple[bool, str]:
    """Classify an email into a statement candidate or non-statement email.

    Returns:
        (is_statement_candidate, reason_code)
    """
    subject_clean = (subject or "").strip()
    subject_lower = subject_clean.lower()
    body_clean = (body_preview or "")[:2000].lower()
    sender_clean = (sender or "").strip().lower()

    # Step 1: Check for explicit exclusions in subject (notifications, alerts, promo)
    for excl in EXCLUSION_KEYWORDS:
        if excl in subject_clean:
            return False, f"excluded_by_keyword:{excl}"

    # Step 2: Check for statement keywords in subject
    has_statement_keyword = False
    matched_keyword = ""
    for kw in STATEMENT_KEYWORDS:
        if kw in subject_lower:
            has_statement_keyword = True
            matched_keyword = kw
            break

    # Step 3: Check bank domain
    is_bank = is_from_bank_domain(sender_clean)

    if has_statement_keyword:
        if is_bank:
            return True, f"bank_statement:{matched_keyword}"
        return True, f"statement_keyword:{matched_keyword}"

    # Step 4: If subject didn't match keyword, check if bank domain + body has statement signals
    if is_bank:
        for kw in STATEMENT_KEYWORDS:
            if kw in body_clean:
                return True, f"bank_body_statement:{kw}"

    return False, "non_statement"
