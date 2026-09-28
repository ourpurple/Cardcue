"""V2 parsing boundaries, using synthetic examples only (no real statements)."""
import json
from datetime import date

import pytest

from cardcue_api.parsing.model_adapter import parse_model_response_multi


def response_with_transactions(transactions):
    return json.dumps({
        "bank": "建设银行", "card_tails": ["1234"], "currency": "CNY",
        "amount_minor": 10000, "statement_date": "2026-09-01",
        "due_date": "2026-09-20", "transactions": transactions,
    }, ensure_ascii=False)


def test_v2_preserves_explicit_transaction_fields():
    draft, = parse_model_response_multi(response_with_transactions([{
        "sequence": 1, "transaction_date": "2026-08-18",
        "description": "示例交易", "amount_minor": -200,
        "currency": "CNY", "card_tail": "1234",
        "evidence": [{"field": "transaction", "excerpt": "示例交易"}],
    }]))
    assert draft.transactions[0].amount_minor == -200
    assert draft.transactions[0].transaction_date == date(2026, 8, 18)
    assert draft.transactions[0].review_flags == []


@pytest.mark.parametrize("rows", [
    "not a list", [None], [{}], [{"sequence": True}],
    [{"sequence": 1, "amount_minor": 1.25}],
    [{"sequence": 1, "amount_minor": 0}],
    [{"sequence": 1, "transaction_date": "08-18"}],
    [{"sequence": 1, "card_tail": "12"}],
    [{"sequence": 1}, {"sequence": 1}],
])
def test_v2_invalid_transactions_never_silently_drop_or_guess(rows):
    with pytest.raises(ValueError):
        parse_model_response_multi(response_with_transactions(rows))


def test_v2_missing_fields_remain_review_flags():
    draft, = parse_model_response_multi(response_with_transactions([{"sequence": 1}]))
    assert "missing:amount" in draft.transactions[0].review_flags
    assert "missing:evidence" in draft.transactions[0].review_flags


def test_v2_consolidated_bank_cannot_create_per_card_totals():
    with pytest.raises(ValueError, match="consolidated_bank_per_card_response"):
        parse_model_response_multi(json.dumps({
            "bank": "招商银行", "cards": [{"card_tails": ["1234"], "amount_minor": 100}]
        }, ensure_ascii=False))


from cardcue_api.services.billing import ConflictError
from cardcue_api.services.drafts import detail_coverage_status
from cardcue_api.domain.schemas import StatementDraftConfirmRequest
from pydantic import ValidationError
import uuid


def test_complete_requires_independently_verified_full_source_count():
    base = dict(recognized=2, confirmed=2, flagged=0, complete=True,
                manifest={"entries": [{"kind": "html_body"}], "has_unsupported": False})
    assert detail_coverage_status(**base, expected=2) == "complete"
    for count in (None, 1, 3):
        with pytest.raises(ConflictError, match="expected transaction count"):
            detail_coverage_status(**base, expected=count)
    assert detail_coverage_status(**{**base, "complete": False}, expected=None) == "partial"
    assert detail_coverage_status(**{**base, "complete": False, "recognized": 0, "confirmed": 0}, expected=2) == "partial"


@pytest.mark.parametrize("changes", [
    {"confirmed": 1}, {"flagged": 1}, {"manifest": None},
    {"manifest": {"entries": [{"kind": "html_body", "truncated": True}]}},
    {"manifest": {"entries": [{"kind": "html_body"}], "has_unsupported": True}},
    {"manifest": {"entries": [{"kind": "pdf_file", "notes": "file_adapter_required"}]}},
])
def test_complete_rejects_incomplete_coverage(changes):
    base = dict(recognized=2, confirmed=2, flagged=0, expected=2, complete=True,
                manifest={"entries": [{"kind": "text_body"}]})
    with pytest.raises(ConflictError):
        detail_coverage_status(**{**base, **changes})


def test_expected_count_must_be_positive_integer_not_boolean_or_float():
    for invalid in (True, 1.5, 0, -1):
        with pytest.raises(ValidationError):
            StatementDraftConfirmRequest(account_id=uuid.uuid4(), expected_transaction_count=invalid)


from email.message import EmailMessage
from types import SimpleNamespace
from cardcue_api.mail.parser import MailMimeParser
from cardcue_api.parsing.model_input import assemble_model_input


class _MemoryStorage:
    def __init__(self, files):
        self.files = files

    def is_file_available(self, path):
        return path in self.files

    def read_file(self, path):
        return self.files[path]


def test_input_retains_html_table_and_all_text_without_extracting_business_fields():
    email = EmailMessage()
    email["Subject"] = "示例账单"
    email.set_content("普通正文示例")
    email.add_alternative('<table><tr><th>卡片</th><th>金额</th></tr>'
                          '<tr><td>1234</td><td>9.01</td></tr></table>'
                          '<script>bad()</script><a href="https://example.invalid">文字</a>',
                          subtype="html")
    source = SimpleNamespace(raw_storage_path="mail", attachments=[])
    result = assemble_model_input(source, _MemoryStorage({"mail": email.as_bytes()}), MailMimeParser())
    content = json.loads(result.body)
    assert [part["kind"] for part in content] == ["html_body", "text_body"]
    assert "<table>" in content[0]["content"] and "<th>" in content[0]["content"]
    assert "<script>" not in content[0]["content"] and "href=" not in content[0]["content"]
    assert "普通正文示例" in content[1]["content"]
    assert result.manifest.has_unsupported is False


def test_input_inventories_every_attachment_but_never_submits_file_as_text():
    email = EmailMessage()
    email.set_content("示例正文")
    files = {"mail": email.as_bytes(), "a": b"%PDF-synthetic", "b": b"image-synthetic"}
    source = SimpleNamespace(raw_storage_path="mail", attachments=[
        SimpleNamespace(id=uuid.UUID(int=1), storage_path="a", filename="bill.pdf", content_type="application/pdf"),
        SimpleNamespace(id=uuid.UUID(int=2), storage_path="b", filename="scan.png", content_type="image/png"),
    ])
    result = assemble_model_input(source, _MemoryStorage(files), MailMimeParser())
    assert [part.kind for part in result.manifest.entries] == ["text_body", "pdf_file", "image_file"]
    assert result.manifest.has_unsupported is True
    assert result.manifest.unsupported_files == ["bill.pdf", "scan.png"]
    assert all(file_bytes.decode(errors="replace") not in result.body for file_bytes in (files["a"], files["b"]))
    assert all(entry.content_hash for entry in result.manifest.entries)
