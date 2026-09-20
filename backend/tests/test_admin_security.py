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

    # Valid http URL with custom port (e.g. self-hosted LLM gateway)
    parsed_custom = validate_url("http://23.169.184.101:8317/v1")
    assert parsed_custom.scheme == "http"
    assert parsed_custom.hostname == "23.169.184.101"
    assert parsed_custom.port == 8317

    # Disallowed scheme rejected
    with pytest.raises(UnsafeDestination):
        validate_url("ftp://api.openai.com/v1")

    with pytest.raises(UnsafeDestination):
        validate_url("file:///etc/passwd")

    # Userinfo rejected
    with pytest.raises(UnsafeDestination):
        validate_url("https://user:pass@api.openai.com/v1")

    # Query params rejected
    with pytest.raises(UnsafeDestination):
        validate_url("https://api.openai.com/v1?key=secret")

    # Invalid port rejected
    with pytest.raises(UnsafeDestination):
        validate_url("https://api.openai.com:99999/v1")


def test_validate_production_encryption_key():
    orig_env = settings.environment
    orig_origin = settings.public_origin
    orig_key = settings.mail_encryption_key
    try:
        settings.environment = "production"
        settings.public_origin = "https://cardcue.example.com"

        # 32 characters key is accepted (standard AES-256)
        settings.mail_encryption_key = "WoMCevRe4fkUW3yrrt4eCXR0cP1GOpF4"
        settings.validate_production()  # should not raise

        # Under 32 characters rejected
        settings.mail_encryption_key = "too_short_key_under_32_chars"
        with pytest.raises(ValueError, match="at least 32 characters"):
            settings.validate_production()

        # Default prefix rejected
        settings.mail_encryption_key = "cardcue-secret-key-that-is-32-chars-long"
        with pytest.raises(ValueError, match="Set a unique"):
            settings.validate_production()
    finally:
        settings.environment = orig_env
        settings.public_origin = orig_origin
        settings.mail_encryption_key = orig_key


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
