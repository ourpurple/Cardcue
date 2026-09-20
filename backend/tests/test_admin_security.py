"""Unit tests for CardCue Web Admin security, authentication helpers, and outbound protection."""

import pytest
from pydantic import ValidationError
from starlette.datastructures import Headers
from starlette.requests import Request
from fastapi import HTTPException

from cardcue_api.admin.security import (
    password_hash,
    password_valid,
    digest,
    origin_check,
    DUMMY_PASSWORD,
)
from cardcue_api.admin.outbound import validate_url, UnsafeDestination
from cardcue_api.admin.schemas import (
    Login,
    ChangePassword,
    StatementCorrection,
    MailConfig,
    ModelConfig,
)
from cardcue_api.config import settings


def test_password_hashing_and_verification():
    raw = "correct-horse-battery-staple-14"
    h1 = password_hash(raw)
    h2 = password_hash(raw)

    assert h1.startswith("scrypt$")
    # Different salts produce different hashes
    assert h1 != h2

    assert password_valid(raw, h1) is True
    assert password_valid(raw, h2) is True
    assert password_valid("wrong-password", h1) is False
    assert password_valid("", h1) is False
    assert password_valid(raw, "invalid$format") is False
    assert password_valid(raw, "md5$salt$hash") is False


def test_dummy_password_exists():
    assert isinstance(DUMMY_PASSWORD, str)
    assert DUMMY_PASSWORD.startswith("scrypt$")
    assert password_valid("any_guess", DUMMY_PASSWORD) is False


def test_digest():
    d1 = digest("hello")
    d2 = digest("hello")
    assert d1 == d2
    assert len(d1) == 64


def test_origin_check_development():
    orig_env = settings.environment
    try:
        settings.environment = "development"

        def make_request(headers_dict):
            scope = {
                "type": "http",
                "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers_dict.items()],
            }
            return Request(scope)

        # Allowed dev origins
        req1 = make_request({"origin": "http://localhost:5173"})
        origin_check(req1)  # should not raise

        req2 = make_request({"origin": "http://127.0.0.1:3000"})
        origin_check(req2)  # should not raise

        # Disallowed origin raises 403
        req_bad = make_request({"origin": "https://evil.com"})
        with pytest.raises(HTTPException) as exc:
            origin_check(req_bad)
        assert exc.value.status_code == 403
    finally:
        settings.environment = orig_env


def test_validate_outbound_url():
    # Valid https URLs
    parsed = validate_url("https://api.openai.com/v1/chat/completions")
    assert parsed.scheme == "https"
    assert parsed.hostname == "api.openai.com"

    # HTTP rejected
    with pytest.raises(UnsafeDestination):
        validate_url("http://api.openai.com/v1")

    # Userinfo rejected
    with pytest.raises(UnsafeDestination):
        validate_url("https://user:pass@api.openai.com/v1")

    # Query params rejected
    with pytest.raises(UnsafeDestination):
        validate_url("https://api.openai.com/v1?key=secret")

    # Non-allowed port rejected
    with pytest.raises(UnsafeDestination):
        validate_url("https://api.openai.com:8080/v1")


def test_schema_password_complexity():
    # Min length 14 for ChangePassword
    with pytest.raises(ValidationError):
        ChangePassword(password="current_password", new_password="short")

    valid = ChangePassword(password="current_password", new_password="a_secure_14_char_password!")
    assert valid.new_password == "a_secure_14_char_password!"


def test_schema_integer_amount_strict():
    # Float amount is rejected due to strict=True
    import uuid
    with pytest.raises(ValidationError):
        StatementCorrection(
            expected_version_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            amount_minor=123.45,  # float not allowed
            reason="Correcting bill",
        )

    valid = StatementCorrection(
        expected_version_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        amount_minor=12345,  # integer cents
        reason="Correcting bill",
    )
    assert valid.amount_minor == 12345


def test_schema_mail_config_validation():
    # Invalid email
    with pytest.raises(ValidationError):
        MailConfig(
            name="Test",
            email_address="not-an-email",
            imap_host="imap.example.com",
        )

    # Valid config
    valid = MailConfig(
        name="Test",
        email_address="test@example.com",
        imap_host="imap.example.com",
    )
    assert valid.imap_port == 993
    assert valid.use_ssl is True
