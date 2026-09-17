"""Device authentication service.

Token flow:
1. Client calls POST /v1/devices/pair with a device name.
2. Server generates a random token, stores its SHA-256 hash, returns the
   raw token once. The client must store it securely (Android Keystore).
3. Subsequent requests include `Authorization: Bearer <token>`.
4. Server hashes the presented token and looks up the device.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cardcue_api.persistence.device import Device


class AuthError(Exception):
    pass


class DeviceService:

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def pair_device(self, session: AsyncSession, name: str) -> tuple[Device, str]:
        """Create a new device and return (device, raw_token).

        The raw token is returned exactly once; only its hash is stored.
        """
        raw_token = secrets.token_urlsafe(48)
        device = Device(
            name=name,
            token_hash=self._hash_token(raw_token),
        )
        session.add(device)
        await session.flush()
        await session.refresh(device)
        return device, raw_token

    async def authenticate(self, session: AsyncSession, token: str) -> Device:
        """Look up device by token hash. Raises AuthError if invalid/revoked."""
        token_hash = self._hash_token(token)
        result = await session.execute(
            select(Device).where(Device.token_hash == token_hash)
        )
        device = result.scalar_one_or_none()
        if not device:
            raise AuthError("Invalid token")
        if device.status != "active" or device.revoked_at is not None:
            raise AuthError("Device revoked")
        device.last_seen_at = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(device)
        return device

    async def revoke_device(self, session: AsyncSession, device_id: uuid.UUID) -> Device:
        device = await session.get(Device, device_id)
        if not device:
            raise AuthError("Device not found")
        device.status = "revoked"
        device.revoked_at = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(device)
        return device

    async def list_devices(self, session: AsyncSession) -> list[Device]:
        result = await session.execute(select(Device).order_by(Device.paired_at))
        return list(result.scalars().all())
