"""Evidence snippet extraction, normalization and security utilities."""

import re
from datetime import date, datetime
from typing import Literal

MAX_TEXT_LENGTH = 1_000_000  # 1 MB max text extraction to prevent ReDoS / memory exhaustion
MAX_PDF_PAGES = 10           # Max pages to process per PDF attachment


def sanitize_text(text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Trim excess whitespace and bound length."""
    if not text:
        return ""
    if len(text) > max_length:
        text = text[:max_length]
    # Replace non-printable control chars while preserving newlines and tabs
    return "".join(ch for ch in text if ch in ("\n", "\r", "\t") or ord(ch) >= 32)


def extract_excerpt(text: str, start: int, end: int, window: int = 30) -> str:
    """Extract a verbatim snippet around [start:end] with surrounding context."""
    prefix_start = max(0, start - window)
    suffix_end = min(len(text), end + window)
    
    snippet = text[prefix_start:suffix_end].replace("\r", " ").replace("\n", " ")
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet[:300]


def parse_amount_to_minor(amount_str: str) -> int | None:
    """Parse monetary string to integer minor currency units (cents / 分).
    
    Examples:
        '1,234.56' -> 123456
        '500'      -> 50000
        '0.50'     -> 50
    """
    if not amount_str:
        return None
    cleaned = amount_str.replace(",", "").replace("¥", "").replace("￥", "").replace("$", "").strip()
    try:
        parts = cleaned.split(".")
        if len(parts) == 1:
            # Whole integer
            return int(parts[0]) * 100
        elif len(parts) == 2:
            integer_part = int(parts[0]) if parts[0] else 0
            fraction_part = parts[1]
            if len(fraction_part) == 1:
                fraction_part = fraction_part + "0"
            elif len(fraction_part) > 2:
                fraction_part = fraction_part[:2]
            return integer_part * 100 + int(fraction_part)
        return None
    except Exception:
        return None


def parse_date_string(date_str: str, reference_year: int | None = None) -> date | None:
    """Parse date strings commonly found in bank statements."""
    if not date_str:
        return None
    cleaned = date_str.strip().replace("年", "-").replace("月", "-").replace("日", "").replace("号", "").replace(".", "-").replace("/", "-")
    
    # Try YYYY-MM-DD or YYYY-M-D
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", cleaned)
    if match:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return date(y, m, d)
        except ValueError:
            return None

    # Try MM-DD or M-D (relative to reference_year)
    match_short = re.match(r"^(\d{1,2})-(\d{1,2})$", cleaned)
    if match_short:
        y = reference_year or datetime.now().year
        m, d = int(match_short.group(1)), int(match_short.group(2))
        try:
            return date(y, m, d)
        except ValueError:
            return None

    return None
