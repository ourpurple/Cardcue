"""HTML and plain text statement extractor with verbatim evidence tracking."""

import re
from datetime import date
from typing import Any
import lxml.html

from cardcue_api.contracts import Evidence, StatementDraft
from cardcue_api.parsing.evidence import (
    extract_excerpt,
    parse_amount_to_minor,
    parse_date_string,
    sanitize_text,
)

# Known banks mapping
KNOWN_BANKS = [
    ("招商银行", r"(招商银行|招行|China Merchants Bank|CMB)"),
    ("中国建设银行", r"(建设银行|建行|China Construction Bank|CCB)"),
    ("中国工商银行", r"(工商银行|工行|Industrial and Commercial Bank of China|ICBC)"),
    ("中国农业银行", r"(农业银行|农行|Agricultural Bank of China|ABC)"),
    ("中国银行", r"(中国银行|中行|Bank of China|BOC)"),
    ("交通银行", r"(交通银行|交行|Bank of Communications|BCOM|BOCOM)"),
    ("中信银行", r"(中信银行|CITIC)"),
    ("浦发银行", r"(浦发银行|浦东发展银行|SPDB)"),
    ("中国光大银行", r"(光大银行|CEB)"),
    ("平安银行", r"(平安银行|PAB)"),
    ("中国民生银行", r"(民生银行|CMBC)"),
    ("兴业银行", r"(兴业银行|CIB)"),
    ("广发银行", r"(广发银行|GDB)"),
    ("华夏银行", r"(华夏银行|HXB)"),
    ("北京银行", r"(北京银行|BOB)"),
    ("上海银行", r"(上海银行|BOS)"),
    ("江苏银行", r"(江苏银行)"),
    ("宁波银行", r"(宁波银行)"),
    ("汇丰银行", r"(汇丰银行|HSBC)"),
    ("渣打银行", r"(渣打银行|Standard Chartered)"),
    ("花旗银行", r"(花旗银行|Citibank)"),
]

# Amount patterns
AMOUNT_PATTERNS = [
    r"(?:本期)?(?:应还款额|应还金额|应还款|应还总额|本期欠款|New Balance|Total Amount Due|Amount Due)[:：\s]*[¥￥$]?\s*([0-9,]+(?:\.[0-9]{1,2})?)",
    r"(?:本期账单应还款额|本期应还本金及费用)[:：\s]*[¥￥$]?\s*([0-9,]+(?:\.[0-9]{1,2})?)",
]

# Minimum payment patterns
MINIMUM_PATTERNS = [
    r"(?:本期)?(?:最低还款额|最低应还|最低还款|Minimum Payment Due|Minimum Due)[:：\s]*[¥￥$]?\s*([0-9,]+(?:\.[0-9]{1,2})?)",
]

# Due date patterns
DUE_DATE_PATTERNS = [
    r"(?:到期还款日|还款截止日|还款日|Payment Due Date|Due Date)[:：\s]*([0-9]{4}[-/年.][0-9]{1,2}[-/月.][0-9]{1,2}[日号]?)",
]

# Statement date patterns
STATEMENT_DATE_PATTERNS = [
    r"(?:账单日|账单周期|对账单日|Statement Date)[:：\s]*([0-9]{4}[-/年.][0-9]{1,2}[-/月.][0-9]{1,2}[日号]?)",
]

# Card tails patterns
CARD_TAIL_PATTERNS = [
    r"(?:卡号末[四4]位|卡号末位|尾号|末[四4]位|尾号为|Card Number)[:：\s*]*(?:\*+)?([0-9]{4})",
    r"(?:\*{4}\s*){3}([0-9]{4})",
    r"(?:卡号|账号)[^\n0-9]*\*+([0-9]{4})",
]

# Account reference patterns
ACCOUNT_REF_PATTERNS = [
    r"(?:账号|账户号|客户号|Account No)[:：\s]*([A-Za-z0-9\-_*]{6,25})",
]


class HtmlStatementExtractor:
    """Safe rule-based extractor for HTML or plain text emails."""

    def __init__(self) -> None:
        pass

    def html_to_text(self, html_content: str) -> str:
        """Convert HTML to clean plain text without network access or script execution."""
        if not html_content or not html_content.strip():
            return ""
        try:
            doc = lxml.html.fromstring(html_content)
            # Safely drop executable, styling and hidden tags
            for el in doc.xpath("//script|//style|//meta|//noscript|//iframe|//frame|//object|//embed"):
                el.drop_tree()
            text = doc.text_content()
            return sanitize_text(text)
        except Exception:
            # Fallback regex strip if malformed HTML fragments
            text = re.sub(r"<[^>]+>", " ", html_content)
            return sanitize_text(text)

    def extract(
        self,
        content: str,
        is_html: bool = True,
        subject: str = "",
        sender: str = "",
        email_date: date | None = None,
    ) -> StatementDraft:
        """Extract statement draft fields and verbatim evidence."""
        text = self.html_to_text(content) if is_html else sanitize_text(content)
        evidence_list: list[Evidence] = []
        review_reasons: list[str] = []

        # Full searchable corpus includes subject + sender + body text
        header_text = f"Subject: {subject}\nSender: {sender}\n"
        full_text = header_text + text

        # 1. Bank
        bank_val = None
        for b_name, b_pat in KNOWN_BANKS:
            m = re.search(b_pat, full_text, re.IGNORECASE)
            if m:
                bank_val = b_name
                excerpt = extract_excerpt(full_text, m.start(), m.end())
                evidence_list.append(Evidence(field="bank", excerpt=excerpt))
                break

        # 2. Currency
        currency_val = None
        if re.search(r"(美元|USD|\$)", full_text, re.IGNORECASE):
            m_curr = re.search(r"(美元|USD|\$)", full_text, re.IGNORECASE)
            currency_val = "USD"
            evidence_list.append(Evidence(field="currency", excerpt=extract_excerpt(full_text, m_curr.start(), m_curr.end())))
        elif re.search(r"(人民币|CNY|RMB|￥|¥)", full_text, re.IGNORECASE):
            m_curr = re.search(r"(人民币|CNY|RMB|￥|¥)", full_text, re.IGNORECASE)
            currency_val = "CNY"
            evidence_list.append(Evidence(field="currency", excerpt=extract_excerpt(full_text, m_curr.start(), m_curr.end())))

        # 3. Amount Due (amount_minor)
        amount_minor = None
        for pat in AMOUNT_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = parse_amount_to_minor(m.group(1))
                if val is not None:
                    amount_minor = val
                    excerpt = extract_excerpt(text, m.start(), m.end())
                    evidence_list.append(Evidence(field="amount_minor", excerpt=excerpt))
                    break

        # 4. Minimum Payment (minimum_minor)
        minimum_minor = None
        for pat in MINIMUM_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = parse_amount_to_minor(m.group(1))
                if val is not None:
                    minimum_minor = val
                    excerpt = extract_excerpt(text, m.start(), m.end())
                    evidence_list.append(Evidence(field="minimum_minor", excerpt=excerpt))
                    break

        # 5. Due Date
        due_date = None
        for pat in DUE_DATE_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                dt = parse_date_string(m.group(1), reference_year=email_date.year if email_date else None)
                if dt:
                    due_date = dt
                    excerpt = extract_excerpt(text, m.start(), m.end())
                    evidence_list.append(Evidence(field="due_date", excerpt=excerpt))
                    break

        # 6. Statement Date
        statement_date = None
        for pat in STATEMENT_DATE_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                dt = parse_date_string(m.group(1), reference_year=email_date.year if email_date else None)
                if dt:
                    statement_date = dt
                    excerpt = extract_excerpt(text, m.start(), m.end())
                    evidence_list.append(Evidence(field="statement_date", excerpt=excerpt))
                    break

        # 7. Card Tails
        card_tails: list[str] = []
        for pat in CARD_TAIL_PATTERNS:
            for m in re.finditer(pat, text, re.IGNORECASE):
                tail = m.group(1)
                if len(tail) == 4 and tail.isdigit() and tail not in card_tails:
                    card_tails.append(tail)
                    excerpt = extract_excerpt(text, m.start(), m.end())
                    evidence_list.append(Evidence(field="card_tails", excerpt=excerpt))

        # 8. Account Reference
        account_ref = None
        for pat in ACCOUNT_REF_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                account_ref = m.group(1).strip()
                excerpt = extract_excerpt(text, m.start(), m.end())
                evidence_list.append(Evidence(field="account_reference", excerpt=excerpt))
                break

        # Build draft with automatic validation
        draft = StatementDraft(
            bank=bank_val,
            account_reference=account_ref,
            card_tails=card_tails,
            currency=currency_val,
            amount_minor=amount_minor,
            minimum_minor=minimum_minor,
            statement_date=statement_date,
            due_date=due_date,
            evidence=evidence_list,
            review_reasons=review_reasons,
        )
        return draft
