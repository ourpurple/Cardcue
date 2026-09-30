"""Migration smoke test in a dedicated PostgreSQL database.

Set CARDCUE_ISOLATED_TEST_DB_URL to cardcue_v2_test. For a remote host,
set CARDCUE_REMOTE_TEST_DB=cardcue_v2_test as a second explicit opt-in.
Never migrate the configured business database; only per-run schemas are dropped.
"""
import os
import uuid
from pathlib import Path

import pytest
from dotenv import dotenv_values
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def _test_setting(name):
    # The ignored backend/.env supports local setup without copying passwords into chat.
    # Process environment takes precedence, including an explicitly empty value.
    if name in os.environ:
        return os.environ[name]
    return dotenv_values(Path(__file__).resolve().parents[1] / ".env").get(name)


def _isolated_url():
    raw = _test_setting("CARDCUE_ISOLATED_TEST_DB_URL")
    if not raw:
        pytest.skip("Set CARDCUE_ISOLATED_TEST_DB_URL to the dedicated cardcue_v2_test database")
    url = make_url(raw)
    if url.drivername != "postgresql+psycopg2" or url.database != "cardcue_v2_test" or not url.host:
        pytest.fail("Refusing migration test: expected psycopg2 and database cardcue_v2_test")
    if url.host not in ("localhost", "127.0.0.1", "::1"):
        if _test_setting("CARDCUE_REMOTE_TEST_DB") != "cardcue_v2_test":
            pytest.fail("Refusing remote migration test without explicit test-database opt-in")
    from cardcue_api.config import settings
    business = make_url(settings.database_sync_url)
    if (url.host, url.port, url.database) == (business.host, business.port, business.database):
        pytest.fail("Refusing migration test against configured business database")
    return url


def _alembic(connection):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.mark.parametrize("start", ["base", "0007"])
def test_empty_and_legacy_upgrade_preserve_data(start):
    engine = create_engine(_isolated_url(), isolation_level="AUTOCOMMIT")
    schema = "v2_migration_" + uuid.uuid4().hex
    created = False
    try:
        with engine.connect() as conn:
            if conn.scalar(text("SELECT current_database()")) != "cardcue_v2_test":
                pytest.fail("Refusing migration test: connected database is not cardcue_v2_test")
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            conn.execute(text(f'SET search_path TO "{schema}"'))
            config = _alembic(conn)
            if start == "0007":
                command.upgrade(config, "0007")
                account_id = uuid.uuid4()
                conn.execute(text("INSERT INTO accounts (id, bank, alias) VALUES (:id, :bank, :alias)"),
                             {"id": account_id, "bank": "合成银行", "alias": "历史演示账户"})
                card_id = uuid.uuid4()
                conn.execute(text("INSERT INTO cards (id, account_id, tail) VALUES (:id, :account_id, :tail)"),
                             {"id": card_id, "account_id": account_id, "tail": "1234"})
                statement_id, version_id, payment_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
                conn.execute(text("""INSERT INTO statements (id, account_id, currency, statement_date, due_date)
                                    VALUES (:id, :account_id, 'CNY', '2026-09-01', '2026-09-25')"""),
                             {"id": statement_id, "account_id": account_id})
                conn.execute(text("""INSERT INTO statement_versions
                                    (id, statement_id, version_number, amount_minor, minimum_minor, source)
                                    VALUES (:id, :statement_id, 1, 2300, 200, 'manual')"""),
                             {"id": version_id, "statement_id": statement_id})
                conn.execute(text("UPDATE statements SET current_version_id=:version WHERE id=:id"),
                             {"version": version_id, "id": statement_id})
                conn.execute(text("""INSERT INTO payments (id, statement_id, amount_minor, currency)
                                    VALUES (:id, :statement_id, 500, 'CNY')"""),
                             {"id": payment_id, "statement_id": statement_id})
            command.upgrade(config, "head")
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0012"
            if start == "0007":
                row = conn.execute(text("SELECT alias, billing_mode, holder FROM accounts WHERE id=:id"), {"id": account_id}).one()
                assert row.alias == "历史演示账户"
                assert conn.scalar(text("SELECT account_id FROM cards WHERE id=:id"), {"id": card_id}) == account_id
                assert conn.scalar(text("SELECT current_version_id FROM statements WHERE id=:id"),
                                   {"id": statement_id}) == version_id
                assert conn.scalar(text("SELECT amount_minor FROM statement_versions WHERE id=:id"),
                                   {"id": version_id}) == 2300
                assert conn.scalar(text("SELECT amount_minor FROM payments WHERE id=:id"),
                                   {"id": payment_id}) == 500
                # Backfills must not turn ambiguous history into a confirmed identity.
                assert row.holder is None
    finally:
        if created:
            with engine.connect() as conn:
                if conn.scalar(text("SELECT current_database()")) != "cardcue_v2_test":
                    pytest.fail("Refusing to clean up on an unexpected database")
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
