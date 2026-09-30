"""Guardrails for the migration test target; these tests never connect to a database."""

import pytest

from test_v2_migrations import _isolated_url


def test_migration_target_rejects_business_database(monkeypatch):
    monkeypatch.setenv("CARDCUE_ISOLATED_TEST_DB_URL", "postgresql+psycopg2://demo:demo@remote.example/cardcube")
    monkeypatch.setenv("CARDCUE_REMOTE_TEST_DB", "cardcue_v2_test")
    with pytest.raises(pytest.fail.Exception, match="expected psycopg2 and database cardcue_v2_test"):
        _isolated_url()


def test_remote_migration_target_requires_separate_opt_in(monkeypatch):
    monkeypatch.setenv("CARDCUE_ISOLATED_TEST_DB_URL", "postgresql+psycopg2://demo:demo@remote.example/cardcue_v2_test")
    monkeypatch.setenv("CARDCUE_REMOTE_TEST_DB", "")
    with pytest.raises(pytest.fail.Exception, match="explicit test-database opt-in"):
        _isolated_url()


def test_explicit_remote_test_target_allowed_without_connection(monkeypatch):
    from cardcue_api.config import settings

    monkeypatch.setattr(settings, "database_sync_url", "postgresql+psycopg2://demo:demo@remote.example/cardcube")
    monkeypatch.setenv("CARDCUE_ISOLATED_TEST_DB_URL", "postgresql+psycopg2://demo:demo@remote.example/cardcue_v2_test")
    monkeypatch.setenv("CARDCUE_REMOTE_TEST_DB", "cardcue_v2_test")
    assert _isolated_url().database == "cardcue_v2_test"


def test_ignored_env_file_can_supply_test_target(monkeypatch):
    import test_v2_migrations as migration_tests

    monkeypatch.delenv("CARDCUE_ISOLATED_TEST_DB_URL", raising=False)
    monkeypatch.delenv("CARDCUE_REMOTE_TEST_DB", raising=False)
    monkeypatch.setattr(migration_tests, "dotenv_values", lambda _: {
        "CARDCUE_ISOLATED_TEST_DB_URL": "postgresql+psycopg2://demo:demo@remote.example/cardcue_v2_test",
        "CARDCUE_REMOTE_TEST_DB": "cardcue_v2_test",
    })
    assert _isolated_url().database == "cardcue_v2_test"
