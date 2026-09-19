"""MIME email parser extracting headers, bodies, attachments, and integrity fingerprints."""

import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedAttachment:
    filename: str
    content_type: str
    size_bytes: int
    payload_bytes: bytes


@dataclass
class ParsedEmail:
    message_id: str | None
    subject: str
    sender: str
    recipient: str
    email_date: datetime
    body_text: str
    body_html: str
    body_hash: str
    attachments: list[ParsedAttachment] = field(default_factory=list)

    @property
    def body_plain(self) -> str:
        return self.body_text


def decode_mime_header(raw_header: str | None) -> str:
    """Decode a MIME encoded-word header (e.g. =?UTF-8?B?...?=) into unicode text."""
    if not raw_header:
        return ""
    try:
        parts = decode_header(raw_header)
        decoded_pieces = []
        for content, encoding in parts:
            if isinstance(content, bytes):
                enc = encoding or "utf-8"
                try:
                    decoded_pieces.append(content.decode(enc, errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    decoded_pieces.append(content.decode("gb18030", errors="replace"))
            else:
                decoded_pieces.append(str(content))
        return "".join(decoded_pieces).strip()
    except Exception:
        return str(raw_header).strip()


def sanitize_filename(raw_name: str | None, default_name: str = "attachment.bin") -> str:
    """Sanitize attachment filenames to prevent path traversal and unsafe characters."""
    if not raw_name:
        return default_name
    cleaned = decode_mime_header(raw_name)
    # Remove directory separators and dangerous characters
    cleaned = Path(cleaned).name
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', cleaned).strip()
    if not cleaned or cleaned.startswith("."):
        cleaned = default_name
    return cleaned[:250]


def parse_email_bytes(raw_bytes: bytes) -> ParsedEmail:
    """Parse raw RFC 822 email bytes into a structured ParsedEmail object."""
    msg = email.message_from_bytes(raw_bytes)

    # 1. Headers
    raw_msg_id = msg.get("Message-ID")
    message_id = None
    if raw_msg_id:
        message_id = str(raw_msg_id).strip("<> ").strip()[:255]

    subject = decode_mime_header(msg.get("Subject", ""))
    sender = decode_mime_header(msg.get("From", ""))
    recipient = decode_mime_header(msg.get("To", "") or msg.get("Cc", ""))

    # 2. Date
    raw_date = msg.get("Date")
    parsed_date = None
    if raw_date:
        try:
            parsed_date = parsedate_to_datetime(raw_date)
            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(tzinfo=timezone.utc)
        except Exception:
            parsed_date = None
    if parsed_date is None:
        parsed_date = datetime.now(timezone.utc)

    # 3. Payload walk
    body_text_parts = []
    body_html_parts = []
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")
            filename = part.get_filename()

            is_attachment = (
                "attachment" in content_disposition.lower()
                or (filename is not None and "inline" not in content_disposition.lower())
                or (content_type.startswith("application/") and filename is not None)
            )

            if is_attachment:
                payload = part.get_payload(decode=True) or b""
                safe_name = sanitize_filename(filename, default_name=f"part_{len(attachments) + 1}.bin")
                attachments.append(
                    ParsedAttachment(
                        filename=safe_name,
                        content_type=content_type[:100],
                        size_bytes=len(payload),
                        payload_bytes=payload,
                    )
                )
            else:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        text = payload.decode(charset, errors="replace")
                    except (LookupError, UnicodeDecodeError):
                        text = payload.decode("gb18030", errors="replace")

                    if content_type == "text/html":
                        body_html_parts.append(text)
                    elif content_type == "text/plain":
                        body_text_parts.append(text)
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            text = payload.decode("gb18030", errors="replace")

        if content_type == "text/html":
            body_html_parts.append(text)
        else:
            body_text_parts.append(text)

    body_text = "\n".join(body_text_parts)
    body_html = "\n".join(body_html_parts)

    # 4. Content fingerprint (SHA-256)
    content_for_hash = (body_html or body_text or raw_bytes.hex()).encode("utf-8")
    body_hash = hashlib.sha256(content_for_hash).hexdigest()

    return ParsedEmail(
        message_id=message_id,
        subject=subject,
        sender=sender,
        recipient=recipient,
        email_date=parsed_date,
        body_text=body_text,
        body_html=body_html,
        body_hash=body_hash,
        attachments=attachments,
    )


class MailMimeParser:
    """Service class for parsing MIME email bytes."""

    def parse_bytes(self, raw_bytes: bytes) -> ParsedEmail:
        return parse_email_bytes(raw_bytes)


class MailMimeParser:
    def parse_bytes(self, raw_bytes: bytes) -> ParsedEmail:
        return parse_email_bytes(raw_bytes)
