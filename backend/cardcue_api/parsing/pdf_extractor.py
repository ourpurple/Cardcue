"""PDF attachment statement extractor using PyMuPDF (fitz) with safe bounds and encryption handling."""

import os
from datetime import date
from typing import BinaryIO
import fitz

from cardcue_api.contracts import Evidence, StatementDraft
from cardcue_api.parsing.evidence import MAX_PDF_PAGES, sanitize_text
from cardcue_api.parsing.html_extractor import HtmlStatementExtractor

MAX_PDF_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB limit


class PdfStatementExtractor:
    """Safely extracts text and statement metadata from PDF files."""

    def __init__(self, max_pages: int = MAX_PDF_PAGES) -> None:
        self.max_pages = max_pages
        self.text_extractor = HtmlStatementExtractor()

    def extract_from_bytes(
        self,
        pdf_bytes: bytes,
        filename: str = "",
        subject: str = "",
        sender: str = "",
        email_date: date | None = None,
    ) -> StatementDraft:
        """Extract statement draft from raw PDF bytes."""
        if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
            return StatementDraft(
                review_reasons=["attachment_size_exceeded", "unresolved:account"],
            )

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            return StatementDraft(
                review_reasons=["corrupt_attachment", "unresolved:account"],
            )

        return self._process_doc(doc, filename=filename, subject=subject, sender=sender, email_date=email_date)

    def extract_from_path(
        self,
        file_path: str,
        filename: str = "",
        subject: str = "",
        sender: str = "",
        email_date: date | None = None,
    ) -> StatementDraft:
        """Extract statement draft from local file path."""
        if not os.path.exists(file_path):
            return StatementDraft(
                review_reasons=["file_not_found", "unresolved:account"],
            )

        if os.path.getsize(file_path) > MAX_PDF_SIZE_BYTES:
            return StatementDraft(
                review_reasons=["attachment_size_exceeded", "unresolved:account"],
            )

        try:
            doc = fitz.open(file_path)
        except Exception:
            return StatementDraft(
                review_reasons=["corrupt_attachment", "unresolved:account"],
            )

        return self._process_doc(doc, filename=filename or os.path.basename(file_path), subject=subject, sender=sender, email_date=email_date)

    def _process_doc(
        self,
        doc: fitz.Document,
        filename: str = "",
        subject: str = "",
        sender: str = "",
        email_date: date | None = None,
    ) -> StatementDraft:
        """Process an opened fitz Document safely."""
        try:
            # Check encryption
            if doc.is_encrypted:
                return StatementDraft(
                    review_reasons=["attachment_password_required", "unresolved:account"],
                )

            page_count = doc.page_count
            pages_to_read = min(page_count, self.max_pages)
            extracted_pages_text: list[str] = []

            for i in range(pages_to_read):
                page = doc.load_page(i)
                text = page.get_text("text")
                if text:
                    extracted_pages_text.append(f"--- Page {i+1} ---\n" + text)

            full_pdf_text = "\n\n".join(extracted_pages_text)
            if not full_pdf_text.strip():
                # No selectable text found in PDF (e.g. scanned image PDF requiring OCR)
                return StatementDraft(
                    review_reasons=["ocr_required_scanned_pdf", "unresolved:account"],
                )

            draft = self.text_extractor.extract(
                content=full_pdf_text,
                is_html=False,
                subject=f"{subject} {filename}",
                sender=sender,
                email_date=email_date,
            )

            if page_count > self.max_pages:
                reasons = list(draft.review_reasons)
                reasons.append("warning:pdf_page_limit_exceeded")
                draft.review_reasons = list(dict.fromkeys(reasons))

            return draft
        finally:
            doc.close()
