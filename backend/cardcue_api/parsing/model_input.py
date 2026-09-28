"""Build a traceable V2 email input without extracting business fields locally."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from cardcue_api.contracts import SourceEntry, SourceManifest
from cardcue_api.mail.storage import MailStorageManager
from cardcue_api.parsing.model_adapter import sanitize_html_for_model
from cardcue_api.persistence.mail import EmailSource
from cardcue_api.mail.parser import MailMimeParser


@dataclass(frozen=True)
class ModelEmailInput:
    body: str
    manifest: SourceManifest
    fingerprint: str


def assemble_model_input(source: EmailSource, storage: MailStorageManager,
                         parser: MailMimeParser) -> ModelEmailInput:
    """Preserve HTML table structure; inventory every attachment, never OCR/text-extract files.

    The current generic chat adapter accepts text only. All attachments are marked
    unsupported until a provider-specific, tested file adapter is configured.
    """
    if not source.raw_storage_path or not storage.is_file_available(source.raw_storage_path):
        raise ValueError("email_source_unavailable")
    parsed = parser.parse_bytes(storage.read_file(source.raw_storage_path))
    parts: list[dict[str, str]] = []
    entries: list[SourceEntry] = []
    if parsed.body_html:
        html = sanitize_html_for_model(parsed.body_html)
        parts.append({"kind": "html_body", "content": html})
        entries.append(SourceEntry(kind="html_body", char_count=len(html),
            content_hash=hashlib.sha256(html.encode()).hexdigest()))
    if parsed.body_text:
        parts.append({"kind": "text_body", "content": parsed.body_text})
        entries.append(SourceEntry(kind="text_body", char_count=len(parsed.body_text),
            content_hash=hashlib.sha256(parsed.body_text.encode()).hexdigest()))
    unsupported: list[str] = []
    for attachment in sorted(source.attachments, key=lambda item: str(item.id)):
        if not storage.is_file_available(attachment.storage_path):
            raise ValueError("attachment_unavailable")
        content = storage.read_file(attachment.storage_path)
        filename = attachment.filename or "attachment"
        content_type = attachment.content_type.lower().split(";", 1)[0]
        kind = "pdf_file" if content_type == "application/pdf" else "image_file" if content_type.startswith("image/") else None
        entries.append(SourceEntry(kind=kind or "other_file", filename=filename,
            char_count=0, content_hash=hashlib.sha256(content).hexdigest(),
            notes="unsupported_type" if kind is None else "file_adapter_required"))
        unsupported.append(filename)
    if not parts and not entries:
        raise ValueError("email_content_missing")
    manifest = SourceManifest(entries=entries, total_chars=sum(len(p["content"]) for p in parts),
        has_unsupported=bool(unsupported), unsupported_files=unsupported)
    body = json.dumps(parts, ensure_ascii=False)
    fingerprint = hashlib.sha256(json.dumps({"body": body, "manifest": manifest.model_dump()},
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return ModelEmailInput(body, manifest, fingerprint)
