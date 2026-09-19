"""API routes for mobile client sync and online write commands (SYNC-01 / SYNC-02)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from cardcue_api.persistence.database import get_session
from cardcue_api.persistence.device import Device
from cardcue_api.services.auth import DeviceService, AuthError
from cardcue_api.services.billing import NotFoundError, ConflictError
from cardcue_api.services.sync import SyncService, CursorOutOfRangeError
from cardcue_api.domain.schemas import (
    SyncBootstrapResponse,
    SyncChangesResponse,
    SyncPaymentResponse,
    PaymentCreate,
    RevokeRequest,
)

router = APIRouter(prefix="/v1/sync", tags=["sync"])
device_svc = DeviceService()
sync_svc = SyncService()
security = HTTPBearer(auto_error=False)


async def get_current_device(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    session: AsyncSession = Depends(get_session),
) -> Device:
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Authentication required: missing bearer token")
    try:
        return await device_svc.authenticate(session, credentials.credentials)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/bootstrap", response_model=SyncBootstrapResponse)
async def sync_bootstrap(
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
):
    """Full snapshot bootstrap for client initialization or recovery."""
    return await sync_svc.get_bootstrap(session)


@router.get("/changes", response_model=SyncChangesResponse)
async def sync_changes(
    cursor: int = Query(default=0, ge=0, description="Last processed change sequence"),
    limit: int = Query(default=100, ge=1, le=500, description="Max changes per page"),
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
):
    """Incremental change log polling using commit sequence cursor."""
    try:
        return await sync_svc.get_changes(session, cursor=cursor, limit=limit)
    except CursorOutOfRangeError as e:
        raise HTTPException(status_code=409, detail={"code": "CURSOR_OUT_OF_RANGE", "message": str(e)})


@router.post("/payments", response_model=SyncPaymentResponse, status_code=201)
async def sync_record_payment(
    data: PaymentCreate,
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
):
    """Online payment write command with client-generated request_id idempotency."""
    try:
        return await sync_svc.record_payment(session, data)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/payments/{payment_id}/revoke", response_model=SyncPaymentResponse)
async def sync_revoke_payment(
    payment_id: uuid.UUID,
    data: RevokeRequest,
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
):
    """Online revoke payment command."""
    try:
        return await sync_svc.revoke_payment(session, payment_id, data.reason)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
