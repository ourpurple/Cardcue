"""Business service for accounts, statements, and payments.

Payments use SELECT ... FOR UPDATE to prevent concurrent overpayment.
Request UUID provides idempotency – a duplicate request_id returns the
existing payment instead of creating a second one.

Write operations record immutable audit entries in ChangeLog in the same transaction.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from cardcue_api.persistence.models import (
    Account, Card, Statement, StatementVersion, Payment,
)
from cardcue_api.persistence.changelog import ChangeLog
from cardcue_api.domain.schemas import (
    AccountCreate, AccountUpdate, CardCreate,
    StatementCreate, PaymentCreate,
)


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class BillingService:
    """Stateless service – receives a session per call."""

    async def _log_change(
        self,
        session: AsyncSession,
        entity_type: str,
        entity_id: uuid.UUID,
        action: str,
        snapshot: dict | None = None,
    ) -> ChangeLog:
        entry = ChangeLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            snapshot=snapshot,
        )
        session.add(entry)
        await session.flush()
        return entry

    # ---- Account ----

    async def create_account(self, session: AsyncSession, data: AccountCreate) -> Account:
        acct = Account(bank=data.bank, alias=data.alias, reference=data.reference)
        session.add(acct)
        await session.flush()
        await session.refresh(acct)
        await self._log_change(session, "account", acct.id, "create", {
            "id": str(acct.id),
            "bank": acct.bank,
            "alias": acct.alias,
            "reference": acct.reference,
            "status": acct.status,
        })
        return acct

    async def get_account(self, session: AsyncSession, account_id: uuid.UUID) -> Account:
        acct = await session.get(Account, account_id)
        if not acct:
            raise NotFoundError(f"Account {account_id} not found")
        return acct

    async def list_accounts(self, session: AsyncSession) -> list[Account]:
        result = await session.execute(select(Account).order_by(Account.created_at))
        return list(result.scalars().all())

    async def update_account(self, session: AsyncSession, account_id: uuid.UUID, data: AccountUpdate) -> Account:
        acct = await self.get_account(session, account_id)
        if data.alias is not None:
            acct.alias = data.alias
        if data.status is not None:
            acct.status = data.status
        await session.flush()
        await session.refresh(acct)
        await self._log_change(session, "account", acct.id, "update", {
            "id": str(acct.id),
            "bank": acct.bank,
            "alias": acct.alias,
            "reference": acct.reference,
            "status": acct.status,
        })
        return acct

    # ---- Card ----

    async def create_card(self, session: AsyncSession, data: CardCreate) -> Card:
        await self.get_account(session, data.account_id)  # verify FK
        card = Card(account_id=data.account_id, display_name=data.display_name, tail=data.tail)
        session.add(card)
        await session.flush()
        await session.refresh(card)
        await self._log_change(session, "card", card.id, "create", {
            "id": str(card.id),
            "account_id": str(card.account_id),
            "display_name": card.display_name,
            "tail": card.tail,
            "status": card.status,
        })
        return card

    async def list_cards(self, session: AsyncSession, account_id: uuid.UUID) -> list[Card]:
        result = await session.execute(select(Card).where(Card.account_id == account_id).order_by(Card.created_at))
        return list(result.scalars().all())

    # ---- Statement ----

    async def create_statement(self, session: AsyncSession, data: StatementCreate) -> Statement:
        await self.get_account(session, data.account_id)
        if data.due_date < data.statement_date:
            raise ConflictError("due_date must be >= statement_date")
        stmt = Statement(
            account_id=data.account_id,
            currency=data.currency,
            statement_date=data.statement_date,
            due_date=data.due_date,
        )
        session.add(stmt)
        await session.flush()

        ver = StatementVersion(
            statement_id=stmt.id,
            version_number=1,
            amount_minor=data.amount_minor,
            minimum_minor=data.minimum_minor,
            source=data.source,
            confirmed_at=datetime.now(timezone.utc),
            confirmed_by="system",
        )
        session.add(ver)
        await session.flush()

        stmt.current_version_id = ver.id
        await session.flush()
        await session.refresh(stmt)
        await session.refresh(ver)
        await self._log_change(session, "statement", stmt.id, "create", {
            "id": str(stmt.id),
            "account_id": str(stmt.account_id),
            "currency": stmt.currency,
            "statement_date": stmt.statement_date.isoformat(),
            "due_date": stmt.due_date.isoformat(),
            "amount_minor": ver.amount_minor,
            "minimum_minor": ver.minimum_minor,
            "version_number": ver.version_number,
            "current_version_id": str(ver.id),
        })
        return stmt

    async def get_statement(self, session: AsyncSession, statement_id: uuid.UUID) -> Statement:
        stmt = await session.get(Statement, statement_id)
        if not stmt:
            raise NotFoundError(f"Statement {statement_id} not found")
        return stmt

    async def list_statements(self, session: AsyncSession, account_id: uuid.UUID | None = None) -> list[Statement]:
        q = select(Statement).order_by(Statement.due_date.desc())
        if account_id:
            q = q.where(Statement.account_id == account_id)
        result = await session.execute(q)
        return list(result.scalars().all())

    async def get_statement_detail(self, session: AsyncSession, statement_id: uuid.UUID) -> dict:
        stmt = await self.get_statement(session, statement_id)
        ver = None
        if stmt.current_version_id:
            ver = await session.get(StatementVersion, stmt.current_version_id)
        total_paid = await self._active_paid(session, statement_id)
        amount = ver.amount_minor if ver else 0
        return {
            "statement": stmt,
            "current_version": ver,
            "total_paid_minor": total_paid,
            "remaining_minor": max(0, amount - total_paid),
        }

    # ---- Payment (S1-05: transactional safety) ----

    async def record_payment(
        self, session: AsyncSession, data: PaymentCreate, request_id: uuid.UUID | None = None,
    ) -> tuple[Payment, bool]:
        """Record a payment. Returns (payment, created).

        Uses SELECT FOR UPDATE on the statement row to serialize concurrent
        payments. If request_id matches an existing payment, returns it without
        creating a duplicate (idempotency).
        """
        rid = request_id or data.request_id

        # Idempotency check
        existing = await session.execute(
            select(Payment).where(Payment.id == rid)
        )
        found = existing.scalar_one_or_none()
        if found:
            return found, False

        # Lock statement row to serialize concurrent payments
        result = await session.execute(
            select(Statement).where(Statement.id == data.statement_id).with_for_update()
        )
        stmt = result.scalar_one_or_none()
        if not stmt:
            raise NotFoundError(f"Statement {data.statement_id} not found")

        if data.currency != stmt.currency:
            raise ConflictError(f"Payment currency {data.currency} does not match statement currency {stmt.currency}")

        # Get current amount from version
        ver = await session.get(StatementVersion, stmt.current_version_id) if stmt.current_version_id else None
        if not ver:
            raise ConflictError("Statement has no confirmed version")

        # Calculate actual remaining
        total_paid = await self._active_paid(session, stmt.id)
        remaining = ver.amount_minor - total_paid

        if data.amount_minor > remaining:
            raise ConflictError(
                f"Payment {data.amount_minor} exceeds remaining {remaining} "
                f"(total {ver.amount_minor}, already paid {total_paid})"
            )

        payment = Payment(
            id=rid,
            statement_id=stmt.id,
            amount_minor=data.amount_minor,
            currency=data.currency,
            note=data.note,
        )
        session.add(payment)
        await session.flush()
        await session.refresh(payment)
        await self._log_change(session, "payment", payment.id, "create", {
            "id": str(payment.id),
            "statement_id": str(payment.statement_id),
            "amount_minor": payment.amount_minor,
            "currency": payment.currency,
            "note": payment.note,
            "recorded_at": payment.recorded_at.isoformat() if payment.recorded_at else None,
        })
        return payment, True

    async def revoke_payment(
        self, session: AsyncSession, payment_id: uuid.UUID, reason: str,
    ) -> Payment:
        """Revoke a payment. The record is preserved with revoked_at timestamp."""
        payment = await session.get(Payment, payment_id)
        if not payment:
            raise NotFoundError(f"Payment {payment_id} not found")
        if payment.revoked_at is not None:
            raise ConflictError("Payment already revoked")

        payment.revoked_at = datetime.now(timezone.utc)
        payment.revoke_reason = reason
        await session.flush()
        await session.refresh(payment)
        await self._log_change(session, "payment", payment.id, "revoke", {
            "id": str(payment.id),
            "statement_id": str(payment.statement_id),
            "amount_minor": payment.amount_minor,
            "currency": payment.currency,
            "note": payment.note,
            "recorded_at": payment.recorded_at.isoformat() if payment.recorded_at else None,
            "revoked_at": payment.revoked_at.isoformat() if payment.revoked_at else None,
            "revoke_reason": payment.revoke_reason,
        })
        return payment

    async def list_payments(self, session: AsyncSession, statement_id: uuid.UUID) -> list[Payment]:
        result = await session.execute(
            select(Payment).where(Payment.statement_id == statement_id).order_by(Payment.recorded_at)
        )
        return list(result.scalars().all())

    # ---- internal ----

    async def _active_paid(self, session: AsyncSession, statement_id: uuid.UUID) -> int:
        """Sum of non-revoked payments for a statement."""
        result = await session.execute(
            select(func.coalesce(func.sum(Payment.amount_minor), 0)).where(
                and_(Payment.statement_id == statement_id, Payment.revoked_at.is_(None))
            )
        )
        return result.scalar_one()
