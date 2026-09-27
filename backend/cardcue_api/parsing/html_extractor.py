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
    r"(?:本期)?(?:最低还款额|最低应还|最低还款|Minimum Payment Due|Minimum Due|Min\.?Payment)[:：\s]*[¥￥$]?\s*([0-9,]+(?:\.[0-9]{1,2})?)",
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

# ---------------------------------------------------------------------------
# Multi-card table patterns for CCB-style emails
# ---------------------------------------------------------------------------

# CCB per-card table row: card_number  currency  new_balance  min_payment  ...
# e.g. "53169300****7008	人民币(CNY)	27.10	27.10	..."
# Each row may have: full_card_number  currency  new_balance  min_payment  [currency2  new_balance2  min_payment2]
_CCB_TABLE_ROW = re.compile(
    r"(\d{8,}\*{3,4}\d{4})"        # full card number with mask
    r"\s+"
    r"([^\t\n]+?)"                   # currency text (e.g. 人民币(CNY))
    r"\s+"
    r"(-?[0-9,]+(?:\.[0-9]{1,2})?)" # new balance / 应还金额
    r"\s+"
    r"(-?[0-9,]+(?:\.[0-9]{1,2})?)" # min payment / 最低还款额
)

def _extract_tail_from_masked(card_number: str) -> str | None:
    """Extract last 4 digits from a masked card number like 53169300****7008."""
    m = re.search(r"(\d{4})\s*$", card_number)
    return m.group(1) if m else None


def _parse_ccb_currency(text: str) -> str | None:
    """Parse currency from CCB table cell like '人民币(CNY)' or 'USD'."""
    text = text.strip()
    if re.search(r"(人民币|CNY|RMB)", text, re.IGNORECASE):
        return "CNY"
    if re.search(r"(美元|USD)", text, re.IGNORECASE):
        return "USD"
    return None


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
            for br in doc.xpath("//br"):
                br.tail = "\n" + (br.tail or "")
            for p in doc.xpath("//p|//div|//tr|//li|//h1|//h2|//h3|//h4|//h5|//h6"):
                p.tail = "\n" + (p.tail or "")
            for td in doc.xpath("//td|//th"):
                td.tail = "\t" + (td.tail or "")
            text = doc.text_content()
            return sanitize_text(text)
        except Exception:
            # Fallback regex strip if malformed HTML fragments
            text = re.sub(r"<[^>]+>", " ", html_content)
            return sanitize_text(text)

    def _extract_shared_fields(
        self,
        text: str,
        full_text: str,
        email_date: date | None = None,
    ) -> dict:
        """Extract bank, currency, dates, card tails, account ref from text.

        Returns a dict of the extracted values and evidence list.
        """
        evidence_list: list[Evidence] = []

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
        card_tails_evidence: list[Evidence] = []
        for pat in CARD_TAIL_PATTERNS:
            for m in re.finditer(pat, text, re.IGNORECASE):
                tail = m.group(1)
                if len(tail) == 4 and tail.isdigit() and tail not in card_tails:
                    card_tails.append(tail)
                    excerpt = extract_excerpt(text, m.start(), m.end())
                    card_tails_evidence.append(Evidence(field="card_tails", excerpt=excerpt))
        evidence_list.extend(card_tails_evidence)

        # 8. Account Reference
        account_ref = None
        for pat in ACCOUNT_REF_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                account_ref = m.group(1).strip()
                excerpt = extract_excerpt(text, m.start(), m.end())
                evidence_list.append(Evidence(field="account_reference", excerpt=excerpt))
                break

        return {
            "bank": bank_val,
            "currency": currency_val,
            "amount_minor": amount_minor,
            "minimum_minor": minimum_minor,
            "due_date": due_date,
            "statement_date": statement_date,
            "card_tails": card_tails,
            "account_ref": account_ref,
            "evidence": evidence_list,
        }

    def _try_extract_multi_card_table(
        self,
        text: str,
        email_date: date | None = None,
    ) -> list[dict] | None:
        """Try to extract a per-card breakdown table (e.g. CCB format).

        Returns a list of per-card dicts with keys:
            card_tail, currency, amount_minor, minimum_minor, evidence
        or None if no multi-card table is found.
        """
        rows = _CCB_TABLE_ROW.findall(text)
        if len(rows) < 2:
            return None

        cards: list[dict] = []
        seen_tails: set[str] = set()
        for full_card, currency_text, amount_text, min_text in rows:
            tail = _extract_tail_from_masked(full_card)
            if not tail or tail in seen_tails:
                continue
            seen_tails.add(tail)
            currency = _parse_ccb_currency(currency_text)
            amount_minor = parse_amount_to_minor(amount_text)
            minimum_minor = parse_amount_to_minor(min_text)

            # Build per-card evidence
            card_evidence: list[Evidence] = []
            # Find the row in the original text for evidence excerpt
            row_match = re.search(re.escape(full_card) + r".*?" + re.escape(amount_text), text, re.DOTALL)
            if row_match:
                excerpt = extract_excerpt(text, row_match.start(), row_match.end())
                card_evidence.append(Evidence(field="card_tails", excerpt=excerpt))
                card_evidence.append(Evidence(field="amount_minor", excerpt=excerpt))
                if currency:
                    card_evidence.append(Evidence(field="currency", excerpt=excerpt))
                if minimum_minor is not None:
                    card_evidence.append(Evidence(field="minimum_minor", excerpt=excerpt))

            cards.append({
                "card_tail": tail,
                "currency": currency,
                "amount_minor": amount_minor,
                "minimum_minor": minimum_minor,
                "evidence": card_evidence,
            })

        return cards if len(cards) >= 2 else None

    def extract(
        self,
        content: str,
        is_html: bool = True,
        subject: str = "",
        sender: str = "",
        email_date: date | None = None,
    ) -> StatementDraft:
        """Extract statement draft fields and verbatim evidence.

        Returns a single StatementDraft. For multi-card emails, use extract_multi().
        """
        drafts = self.extract_multi(content, is_html=is_html, subject=subject, sender=sender, email_date=email_date)
        return drafts[0]

    def extract_multi(
        self,
        content: str,
        is_html: bool = True,
        subject: str = "",
        sender: str = "",
        email_date: date | None = None,
    ) -> list[StatementDraft]:
        """Extract one or more statement drafts from an email.

        Returns multiple StatementDraft instances when the email contains a
        per-card breakdown table (e.g. CCB emails listing each card's balance).
        """
        text = self.html_to_text(content) if is_html else sanitize_text(content)

        # Full searchable corpus includes subject + sender + body text
        header_text = f"Subject: {subject}\nSender: {sender}\n"
        full_text = header_text + text

        shared = self._extract_shared_fields(text, full_text, email_date)

        # Try multi-card table extraction
        multi_cards = self._try_extract_multi_card_table(text, email_date)
        if multi_cards:
            # Build separate drafts for each card, inheriting shared fields
            drafts: list[StatementDraft] = []
            # Shared evidence: bank, statement_date, due_date only
            shared_evidence = [e for e in shared["evidence"] if e.field in ("bank", "statement_date", "due_date")]
            for card_info in multi_cards:
                card_evidence = list(shared_evidence) + card_info["evidence"]
                draft = StatementDraft(
                    bank=shared["bank"],
                    account_reference=shared["account_ref"],
                    card_tails=[card_info["card_tail"]],
                    currency=card_info["currency"] or shared["currency"],
                    amount_minor=card_info["amount_minor"],
                    minimum_minor=card_info["minimum_minor"],
                    statement_date=shared["statement_date"],
                    due_date=shared["due_date"],
                    evidence=card_evidence,
                )
                drafts.append(draft)
            return drafts

        # Single-card path
        draft = StatementDraft(
            bank=shared["bank"],
            account_reference=shared["account_ref"],
            card_tails=shared["card_tails"],
            currency=shared["currency"],
            amount_minor=shared["amount_minor"],
            minimum_minor=shared["minimum_minor"],
            statement_date=shared["statement_date"],
            due_date=shared["due_date"],
            evidence=shared["evidence"],
        )
        return [draft]
