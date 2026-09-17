"""API routes for device pairing and auth."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cardcue_api.persistence.database import get_session
from cardcue_api.services.auth import DeviceService, AuthError

router = APIRouter(prefix="/v1/devices", tags=["devices"])
svc = DeviceService()


class PairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)


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
async def pair_device(data: PairRequest, session: AsyncSession = Depends(get_session)):
    device, raw_token = await svc.pair_device(session, data.name)
    return PairResponse(device_id=device.id, name=device.name, token=raw_token)


@router.get("", response_model=list[DeviceOut])
async def list_devices(session: AsyncSession = Depends(get_session)):
    return await svc.list_devices(session)


@router.post("/{device_id}/revoke", response_model=DeviceOut)
async def revoke_device(device_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    try:
        return await svc.revoke_device(session, device_id)
    except AuthError as e:
        raise HTTPException(status_code=404, detail=str(e))
