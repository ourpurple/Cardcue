from datetime import date
import pytest
from pydantic import ValidationError
from cardcue_api.contracts import Evidence, StatementDraft


def confirmed_payload():
    data = dict(bank="示例银行", card_tails=["1234"], currency="CNY", amount_minor=18329,
                minimum_minor=1800, statement_date=date(2026, 8, 28), due_date=date(2026, 9, 17))
    data["evidence"] = [Evidence(field=key, excerpt=str(value)) for key, value in data.items()]
    return data


def test_valid_draft_with_evidence():
    assert StatementDraft(**confirmed_payload()).needs_review is False


def test_missing_fields_are_not_guessed():
    draft = StatementDraft()
    assert draft.amount_minor is None
    assert "missing:due_date" in draft.review_reasons
    assert "unresolved:account" in draft.review_reasons


def test_zero_is_not_missing():
    data = confirmed_payload()
    data.update(amount_minor=0, minimum_minor=0)
    assert StatementDraft(**data).needs_review is False


@pytest.mark.parametrize("value", [183.29, "18329", True, -1, 10**20])
def test_amounts_require_bounded_integer_minor_units(value):
    with pytest.raises(ValidationError):
        StatementDraft(amount_minor=value)


def test_conflicting_dates_and_minimum_are_reviewed():
    data = confirmed_payload()
    data.update(due_date=date(2026, 8, 1), minimum_minor=20000)
    draft = StatementDraft(**data)
    assert "conflict:due_before_statement" in draft.review_reasons
    assert "conflict:minimum_exceeds_total" in draft.review_reasons


def test_missing_evidence_requires_review():
    data = confirmed_payload()
    data["evidence"] = []
    assert "no_evidence:amount_minor" in StatementDraft(**data).review_reasons


def test_full_card_number_not_accepted_as_tail():
    data = confirmed_payload()
    data["card_tails"] = ["1234567890123456"]
    assert "invalid:card_tails" in StatementDraft(**data).review_reasons
