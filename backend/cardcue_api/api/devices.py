"""API routes for device pairing and auth."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cardcue_api.persistence.database import get_session
from cardcue_api.services.auth import DeviceService, AuthError

from cardcue_api.admin.security import require_admin, recent_admin

router = APIRouter(prefix="/v1/devices", tags=["devices"])
svc = DeviceService()


class PairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    pairing_code: str = Field(min_length=20, max_length=100)


class PairResponse(BaseModel):
    device_id: uuid.UUID
    name: str
    token: str = Field(description="One-time bearer token. Store securely.")


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    status: str
    paired_at: object
    last_seen_at: object | None
    revoked_at: object | None


@router.post("/pair", response_model=PairResponse, status_code=201)
async def pair_device(data: PairRequest, request: Request, session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    from cardcue_api.admin.models import PairingCode
    from cardcue_api.admin.security import throttle, digest, now
    await throttle(session, "pair:" + (request.client.host if request.client else "unknown"), 8)
    code = (await session.execute(select(PairingCode).where(PairingCode.code_hash == digest(data.pairing_code)).with_for_update())).scalar_one_or_none()
    if not code or code.used_at or code.expires_at <= now():
        raise HTTPException(401, "配对码无效或已过期")
    code.used_at = now()
    device, raw_token = await svc.pair_device(session, data.name)
    return PairResponse(device_id=device.id, name=device.name, token=raw_token)


@router.get("", response_model=list[DeviceOut], dependencies=[Depends(require_admin)])
async def list_devices(session: AsyncSession = Depends(get_session)):
    return await svc.list_devices(session)


@router.post("/{device_id}/revoke", response_model=DeviceOut, dependencies=[Depends(recent_admin)])
async def revoke_device(device_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    try:
        return await svc.revoke_device(session, device_id)
    except AuthError as e:
        raise HTTPException(status_code=404, detail=str(e))
