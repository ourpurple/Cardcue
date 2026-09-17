"""API routes for accounts, cards, statements, and payments."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from cardcue_api.persistence.database import get_session
from cardcue_api.services.billing import BillingService, NotFoundError, ConflictError
from cardcue_api.domain.schemas import (
    AccountCreate, AccountUpdate, AccountOut,
    CardCreate, CardOut,
    StatementCreate, StatementOut, StatementDetail, StatementVersionOut,
    PaymentCreate, PaymentOut, RevokeRequest,
)

router = APIRouter(prefix="/v1", tags=["billing"])
svc = BillingService()


def _not_found(e: NotFoundError):
    raise HTTPException(status_code=404, detail=str(e))


def _conflict(e: ConflictError):
    raise HTTPException(status_code=409, detail=str(e))


# ---- Accounts ----

@router.post("/accounts", response_model=AccountOut, status_code=201)
async def create_account(data: AccountCreate, session: AsyncSession = Depends(get_session)):
    acct = await svc.create_account(session, data)
    return acct


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(session: AsyncSession = Depends(get_session)):
    return await svc.list_accounts(session)


@router.get("/accounts/{account_id}", response_model=AccountOut)
async def get_account(account_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    try:
        return await svc.get_account(session, account_id)
    except NotFoundError as e:
        _not_found(e)


@router.patch("/accounts/{account_id}", response_model=AccountOut)
async def update_account(account_id: uuid.UUID, data: AccountUpdate, session: AsyncSession = Depends(get_session)):
    try:
        return await svc.update_account(session, account_id, data)
    except NotFoundError as e:
        _not_found(e)


# ---- Cards ----

@router.post("/cards", response_model=CardOut, status_code=201)
async def create_card(data: CardCreate, session: AsyncSession = Depends(get_session)):
    try:
        return await svc.create_card(session, data)
    except NotFoundError as e:
        _not_found(e)


@router.get("/accounts/{account_id}/cards", response_model=list[CardOut])
async def list_cards(account_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await svc.list_cards(session, account_id)


# ---- Statements ----

@router.post("/statements", response_model=StatementOut, status_code=201)
async def create_statement(data: StatementCreate, session: AsyncSession = Depends(get_session)):
    try:
        stmt = await svc.create_statement(session, data)
        return stmt
    except (NotFoundError, ConflictError) as e:
        if isinstance(e, NotFoundError):
            _not_found(e)
        _conflict(e)


@router.get("/statements", response_model=list[StatementOut])
async def list_statements(account_id: uuid.UUID | None = None, session: AsyncSession = Depends(get_session)):
    return await svc.list_statements(session, account_id)


@router.get("/statements/{statement_id}", response_model=StatementDetail)
async def get_statement(statement_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    try:
        detail = await svc.get_statement_detail(session, statement_id)
        stmt = detail["statement"]
        return StatementDetail(
            id=stmt.id, account_id=stmt.account_id, currency=stmt.currency,
            statement_date=stmt.statement_date, due_date=stmt.due_date,
            current_version_id=stmt.current_version_id,
            created_at=stmt.created_at, updated_at=stmt.updated_at,
            current_version=StatementVersionOut.model_validate(detail["current_version"]) if detail["current_version"] else None,
            total_paid_minor=detail["total_paid_minor"],
            remaining_minor=detail["remaining_minor"],
        )
    except NotFoundError as e:
        _not_found(e)


# ---- Payments ----

@router.post("/payments", response_model=PaymentOut, status_code=201)
async def create_payment(data: PaymentCreate, session: AsyncSession = Depends(get_session)):
    try:
        payment, created = await svc.record_payment(session, data, request_id=data.request_id)
        return payment
    except NotFoundError as e:
        _not_found(e)
    except ConflictError as e:
        _conflict(e)


@router.get("/statements/{statement_id}/payments", response_model=list[PaymentOut])
async def list_payments(statement_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await svc.list_payments(session, statement_id)


@router.post("/payments/{payment_id}/revoke", response_model=PaymentOut)
async def revoke_payment(payment_id: uuid.UUID, data: RevokeRequest, session: AsyncSession = Depends(get_session)):
    try:
        return await svc.revoke_payment(session, payment_id, data.reason)
    except NotFoundError as e:
        _not_found(e)
    except ConflictError as e:
        _conflict(e)
