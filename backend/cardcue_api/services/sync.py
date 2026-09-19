"""Sync service for snapshot bootstrap and incremental change stream (SYNC-01 / SYNC-02)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from cardcue_api.persistence.changelog import ChangeLog
from cardcue_api.persistence.models import (
    Account, Card, Statement, Payment,
)
from cardcue_api.domain.schemas import (
    AccountOut, CardOut, StatementDetail, StatementVersionOut, PaymentOut,
    SyncBootstrapResponse, SyncChangesResponse, SyncChangeItem,
    PaymentCreate, SyncPaymentResponse,
)
from cardcue_api.services.billing import BillingService, NotFoundError, ConflictError


class CursorOutOfRangeError(Exception):
    """Raised when client cursor is greater than server max sequence (e.g. after restore)."""
    pass


class SyncService:
    def __init__(self, billing_service: BillingService | None = None):
        self.billing_service = billing_service or BillingService()

    async def get_latest_seq(self, session: AsyncSession) -> int:
        result = await session.execute(select(func.coalesce(func.max(ChangeLog.id), 0)))
        return int(result.scalar_one())

    async def get_bootstrap(self, session: AsyncSession) -> SyncBootstrapResponse:
        current_cursor = await self.get_latest_seq(session)

        # Accounts
        acct_res = await session.execute(select(Account).order_by(Account.created_at))
        accounts = [AccountOut.model_validate(a) for a in acct_res.scalars().all()]

        # Cards
        card_res = await session.execute(select(Card).order_by(Card.created_at))
        cards = [CardOut.model_validate(c) for c in card_res.scalars().all()]

        # Statements with details
        stmt_res = await session.execute(select(Statement).order_by(Statement.due_date.desc()))
        stmts = list(stmt_res.scalars().all())

        statement_details: list[StatementDetail] = []
        for stmt in stmts:
            detail = await self.billing_service.get_statement_detail(session, stmt.id)
            ver = detail["current_version"]
            statement_details.append(
                StatementDetail(
                    id=stmt.id,
                    account_id=stmt.account_id,
                    currency=stmt.currency,
                    statement_date=stmt.statement_date,
                    due_date=stmt.due_date,
                    current_version_id=stmt.current_version_id,
                    created_at=stmt.created_at,
                    updated_at=stmt.updated_at,
                    current_version=StatementVersionOut.model_validate(ver) if ver else None,
                    total_paid_minor=detail["total_paid_minor"],
                    remaining_minor=detail["remaining_minor"],
                )
            )

        # Payments
        pay_res = await session.execute(select(Payment).order_by(Payment.recorded_at))
        payments = [PaymentOut.model_validate(p) for p in pay_res.scalars().all()]

        return SyncBootstrapResponse(
            cursor=current_cursor,
            server_time=datetime.now(timezone.utc),
            accounts=accounts,
            cards=cards,
            statements=statement_details,
            payments=payments,
        )

    async def get_changes(
        self, session: AsyncSession, cursor: int = 0, limit: int = 100,
    ) -> SyncChangesResponse:
        if cursor < 0:
            raise ValueError("Cursor must be non-negative")

        max_seq = await self.get_latest_seq(session)
        if cursor > max_seq:
            raise CursorOutOfRangeError(
                f"Cursor {cursor} exceeds server latest sequence {max_seq}. Full bootstrap required."
            )

        q = (
            select(ChangeLog)
            .where(ChangeLog.id > cursor)
            .order_by(ChangeLog.id.asc())
            .limit(limit + 1)
        )
        result = await session.execute(q)
        logs = list(result.scalars().all())

        has_more = len(logs) > limit
        items = logs[:limit]
        new_cursor = items[-1].id if items else cursor

        changes = [
            SyncChangeItem(
                seq=item.id,
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                action=item.action,
                snapshot=item.snapshot,
                created_at=item.created_at,
            )
            for item in items
        ]

        return SyncChangesResponse(
            cursor=new_cursor,
            has_more=has_more,
            changes=changes,
            server_time=datetime.now(timezone.utc),
        )

    async def record_payment(
        self, session: AsyncSession, data: PaymentCreate,
    ) -> SyncPaymentResponse:
        payment, created = await self.billing_service.record_payment(session, data, request_id=data.request_id)
        detail_data = await self.billing_service.get_statement_detail(session, payment.statement_id)
        stmt = detail_data["statement"]
        ver = detail_data["current_version"]
        detail = StatementDetail(
            id=stmt.id,
            account_id=stmt.account_id,
            currency=stmt.currency,
            statement_date=stmt.statement_date,
            due_date=stmt.due_date,
            current_version_id=stmt.current_version_id,
            created_at=stmt.created_at,
            updated_at=stmt.updated_at,
            current_version=StatementVersionOut.model_validate(ver) if ver else None,
            total_paid_minor=detail_data["total_paid_minor"],
            remaining_minor=detail_data["remaining_minor"],
        )
        return SyncPaymentResponse(
            payment=PaymentOut.model_validate(payment),
            created=created,
            statement_detail=detail,
        )

    async def revoke_payment(
        self, session: AsyncSession, payment_id: uuid.UUID, reason: str,
    ) -> SyncPaymentResponse:
        payment = await self.billing_service.revoke_payment(session, payment_id, reason)
        detail_data = await self.billing_service.get_statement_detail(session, payment.statement_id)
        stmt = detail_data["statement"]
        ver = detail_data["current_version"]
        detail = StatementDetail(
            id=stmt.id,
            account_id=stmt.account_id,
            currency=stmt.currency,
            statement_date=stmt.statement_date,
            due_date=stmt.due_date,
            current_version_id=stmt.current_version_id,
            created_at=stmt.created_at,
            updated_at=stmt.updated_at,
            current_version=StatementVersionOut.model_validate(ver) if ver else None,
            total_paid_minor=detail_data["total_paid_minor"],
            remaining_minor=detail_data["remaining_minor"],
        )
        return SyncPaymentResponse(
            payment=PaymentOut.model_validate(payment),
            created=False,
            statement_detail=detail,
        )
