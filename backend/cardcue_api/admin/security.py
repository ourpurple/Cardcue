"""Single-owner authentication, DB-backed throttling and CSRF protection."""
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from cardcue_api.admin.models import AdminUser, AuditEvent, LoginGuard, WebSession
from cardcue_api.config import settings
from cardcue_api.persistence.database import get_session
from cardcue_api.services.auth import AuthError, DeviceService

COOKIE = "cardcue_session"
def now():
    return datetime.now(timezone.utc)
def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return "scrypt$" + salt.hex() + "$" + key.hex()
def password_valid(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, key = encoded.split("$")
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(derived, bytes.fromhex(key))
    except (ValueError, TypeError):
        return False

DUMMY_PASSWORD = password_hash(secrets.token_urlsafe(32))

@dataclass
class Actor:
    id: str
    kind: str
    session: WebSession | None = None

def origin_check(request: Request):
    origin = request.headers.get("origin")
    if not origin:
        referer = request.headers.get("referer")
        if referer:
            from urllib.parse import urlsplit
            r_parts = urlsplit(referer)
            origin = f"{r_parts.scheme}://{r_parts.netloc}"
    if not origin:
        if settings.environment == "production":
            raise HTTPException(403, "缺少请求来源标头，请从正式管理页面操作")
        return

    allowed = {settings.public_origin.rstrip("/")}
    if settings.environment != "production":
        allowed.update([
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ])
    if origin.rstrip("/") not in allowed:
        raise HTTPException(403, "请求来源不受信任，请从正式管理页面操作")

async def authenticate(request: Request, session=Depends(get_session)) -> Actor:
    existing = getattr(request.state, "actor", None)
    if existing:
        return existing
    token = request.cookies.get(COOKIE)
    if token:
        web = await session.get(WebSession, digest(token))
        if web and web.expires_at > now():
            user = await session.get(AdminUser, web.admin_id)
            if user and user.active:
                if request.method not in ("GET", "HEAD", "OPTIONS"):
                    origin_check(request)
                    if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), web.csrf_token):
                        raise HTTPException(403, "安全校验失败，请刷新页面重试")
                actor = Actor(str(user.id), "admin", web)
                request.state.actor = actor
                return actor
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            device = await DeviceService().authenticate(session, auth[7:])
            actor = Actor(str(device.id), "device")
            request.state.actor = actor
            return actor
        except AuthError:
            pass
    raise HTTPException(401, "请登录或重新配对设备")

async def require_admin(actor=Depends(authenticate)):
    if actor.kind != "admin":
        raise HTTPException(403, "仅管理员可执行此操作")
    return actor

async def recent_admin(actor=Depends(require_admin)):
    if actor.session.verified_at < now() - timedelta(minutes=10):
        raise HTTPException(403, "请先在设备与安全页面重新验证密码")
    return actor

async def protect_api(request: Request, actor=Depends(authenticate)):
    path = request.url.path
    if actor.kind == "device":
        allowed = (path.startswith("/v1/sync/") or path.startswith("/v1/drafts")
                   or path == "/v1/mail/sync-now" or path.startswith("/v1/mail/jobs")
                   or path == "/v1/mail/sources")
        if not allowed:
            raise HTTPException(403, "设备没有管理配置的权限")
    return actor

async def throttle(session, key: str, limit: int = 8):
    key = digest(key)
    await session.execute(insert(LoginGuard).values(key=key, attempts=0, reset_at=now()+timedelta(minutes=15)).on_conflict_do_nothing())
    row = (await session.execute(select(LoginGuard).where(LoginGuard.key == key).with_for_update())).scalar_one()
    if row.reset_at <= now():
        row.attempts = 0
        row.reset_at = now() + timedelta(minutes=15)
    row.attempts += 1
    denied = row.attempts > limit
    await session.commit()
    if denied:
        raise HTTPException(429, "尝试过于频繁，请 15 分钟后再试", headers={"Retry-After": "900"})

async def audit(session, actor: Actor | str, action: str, target=None, detail=None):
    session.add(AuditEvent(actor=actor.id if isinstance(actor, Actor) else actor,
                          action=action, target=str(target) if target else None, detail=detail or {}))
