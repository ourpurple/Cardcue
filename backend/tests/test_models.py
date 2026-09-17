"""S1 integration tests for core models against PostgreSQL.

These tests require a live database connection (DATABASE_SYNC_URL in .env).
They create and roll back within transactions to avoid polluting the database.
"""

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from cardcue_api.config import settings
from cardcue_api.persistence.models import (
    Account, Card, Statement, StatementVersion, Payment, Base,
)


@pytest.fixture(scope="module")
def engine():
    """Create a sync engine for tests; skip if DB is unreachable."""
    eng = create_engine(settings.database_sync_url, echo=False)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL not reachable – skipping DB tests")
    return eng


@pytest.fixture(scope="module")
def tables(engine):
    """Ensure tables exist (via metadata create_all) for test module."""
    Base.metadata.create_all(engine)
    yield
    # Do NOT drop tables – migration owns schema lifecycle


@pytest.fixture
def session(engine, tables):
    """Yields a session that rolls back after each test."""
    with engine.connect() as conn:
        trans = conn.begin()
        sess = Session(bind=conn)
        yield sess
        sess.close()
        if trans.is_active:
            trans.rollback()


# ---------- Account & Card ----------

class TestAccountCard:
    def test_create_account(self, session: Session):
        acct = Account(bank="招商银行", alias="我的招行")
        session.add(acct)
        session.flush()
        assert acct.id is not None
        assert acct.status == "active"

    def test_create_card_linked_to_account(self, session: Session):
        acct = Account(bank="交通银行")
        session.add(acct)
        session.flush()
        card = Card(account_id=acct.id, tail="8369")
        session.add(card)
        session.flush()
        assert card.account_id == acct.id

    def test_card_without_account_fails(self, session: Session):
        card = Card(account_id=uuid.uuid4(), tail="0000")
        session.add(card)
        with pytest.raises(IntegrityError):
            session.flush()


# ---------- Statement & Version ----------

class TestStatementVersion:
    def _make_account(self, session: Session) -> Account:
        acct = Account(bank="工商银行")
        session.add(acct)
        session.flush()
        return acct

    def test_create_statement_and_version(self, session: Session):
        acct = self._make_account(session)
        stmt = Statement(
            account_id=acct.id,
            currency="CNY",
            statement_date=date(2026, 8, 1),
            due_date=date(2026, 8, 25),
        )
        session.add(stmt)
        session.flush()

        ver = StatementVersion(
            statement_id=stmt.id,
            version_number=1,
            amount_minor=683051,  # ¥6,830.51
            source="manual",
        )
        session.add(ver)
        session.flush()
        stmt.current_version_id = ver.id
        session.flush()

        assert ver.amount_minor == 683051
        assert stmt.current_version_id == ver.id

    def test_integer_money_no_float(self, session: Session):
        """Verify money is stored as integer, not float."""
        acct = self._make_account(session)
        stmt = Statement(
            account_id=acct.id, currency="CNY",
            statement_date=date(2026, 9, 1), due_date=date(2026, 9, 25),
        )
        session.add(stmt)
        session.flush()
        ver = StatementVersion(
            statement_id=stmt.id, version_number=1,
            amount_minor=218329, source="manual",
        )
        session.add(ver)
        session.flush()
        # Read back raw value
        row = session.execute(
            text("SELECT amount_minor FROM statement_versions WHERE id = :id"),
            {"id": ver.id},
        ).fetchone()
        assert isinstance(row[0], int)
        assert row[0] == 218329

    def test_duplicate_period_rejected(self, session: Session):
        """Same account + currency + statement_date must be unique."""
        acct = self._make_account(session)
        for i in range(2):
            stmt = Statement(
                account_id=acct.id, currency="CNY",
                statement_date=date(2026, 7, 1), due_date=date(2026, 7, 25),
            )
            session.add(stmt)
            if i == 1:
                with pytest.raises(IntegrityError):
                    session.flush()

    def test_due_before_statement_rejected(self, session: Session):
        """due_date < statement_date should violate check constraint."""
        acct = self._make_account(session)
        stmt = Statement(
            account_id=acct.id, currency="CNY",
            statement_date=date(2026, 9, 15),
            due_date=date(2026, 9, 1),  # before statement_date
        )
        session.add(stmt)
        with pytest.raises(IntegrityError):
            session.flush()

    def test_negative_amount_rejected(self, session: Session):
        """amount_minor < 0 should violate check constraint."""
        acct = self._make_account(session)
        stmt = Statement(
            account_id=acct.id, currency="CNY",
            statement_date=date(2026, 6, 1), due_date=date(2026, 6, 25),
        )
        session.add(stmt)
        session.flush()
        ver = StatementVersion(
            statement_id=stmt.id, version_number=1,
            amount_minor=-100, source="manual",
        )
        session.add(ver)
        with pytest.raises(IntegrityError):
            session.flush()

    def test_minimum_exceeds_total_rejected(self, session: Session):
        """minimum_minor > amount_minor should violate check constraint."""
        acct = self._make_account(session)
        stmt = Statement(
            account_id=acct.id, currency="USD",
            statement_date=date(2026, 8, 1), due_date=date(2026, 8, 25),
        )
        session.add(stmt)
        session.flush()
        ver = StatementVersion(
            statement_id=stmt.id, version_number=1,
            amount_minor=10000, minimum_minor=20000, source="manual",
        )
        session.add(ver)
        with pytest.raises(IntegrityError):
            session.flush()

    def test_version_uniqueness(self, session: Session):
        """Same statement + version_number must be unique."""
        acct = self._make_account(session)
        stmt = Statement(
            account_id=acct.id, currency="CNY",
            statement_date=date(2026, 5, 1), due_date=date(2026, 5, 25),
        )
        session.add(stmt)
        session.flush()
        v1 = StatementVersion(statement_id=stmt.id, version_number=1, amount_minor=5000, source="manual")
        session.add(v1)
        session.flush()
        v1_dup = StatementVersion(statement_id=stmt.id, version_number=1, amount_minor=6000, source="email")
        session.add(v1_dup)
        with pytest.raises(IntegrityError):
            session.flush()


# ---------- Payment ----------

class TestPayment:
    def _make_statement(self, session: Session) -> Statement:
        acct = Account(bank="建设银行")
        session.add(acct)
        session.flush()
        stmt = Statement(
            account_id=acct.id, currency="CNY",
            statement_date=date(2026, 8, 1), due_date=date(2026, 8, 25),
        )
        session.add(stmt)
        session.flush()
        ver = StatementVersion(
            statement_id=stmt.id, version_number=1,
            amount_minor=100000, source="manual",
        )
        session.add(ver)
        session.flush()
        stmt.current_version_id = ver.id
        session.flush()
        return stmt

    def test_record_payment(self, session: Session):
        stmt = self._make_statement(session)
        pay = Payment(
            statement_id=stmt.id, amount_minor=50000, currency="CNY",
            note="支付宝还款",
        )
        session.add(pay)
        session.flush()
        assert pay.id is not None
        assert pay.revoked_at is None

    def test_revoke_payment(self, session: Session):
        stmt = self._make_statement(session)
        pay = Payment(statement_id=stmt.id, amount_minor=30000, currency="CNY")
        session.add(pay)
        session.flush()
        pay.revoked_at = datetime.now(timezone.utc)
        pay.revoke_reason = "金额录入错误"
        session.flush()
        assert pay.revoked_at is not None

    def test_zero_payment_rejected(self, session: Session):
        """amount_minor must be > 0."""
        stmt = self._make_statement(session)
        pay = Payment(statement_id=stmt.id, amount_minor=0, currency="CNY")
        session.add(pay)
        with pytest.raises(IntegrityError):
            session.flush()

    def test_multi_currency(self, session: Session):
        """Payments in different currencies are allowed on different statements."""
        acct = Account(bank="中信银行")
        session.add(acct)
        session.flush()
        for cur, d, amt in [("CNY", date(2026, 8, 1), 100000), ("USD", date(2026, 8, 2), 12650)]:
            stmt = Statement(
                account_id=acct.id, currency=cur,
                statement_date=d, due_date=date(2026, 8, 25),
            )
            session.add(stmt)
            session.flush()
            ver = StatementVersion(statement_id=stmt.id, version_number=1, amount_minor=amt, source="manual")
            session.add(ver)
            session.flush()
            pay = Payment(statement_id=stmt.id, amount_minor=amt, currency=cur)
            session.add(pay)
            session.flush()
            assert pay.currency == cur

