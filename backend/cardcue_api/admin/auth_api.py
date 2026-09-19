import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from cardcue_api.admin.models import AdminUser, PairingCode, WebSession
from cardcue_api.admin.schemas import Login, Password, ChangePassword
from cardcue_api.admin.security import (COOKIE, DUMMY_PASSWORD, audit, digest, now, origin_check,
    password_hash, password_valid, recent_admin, require_admin, throttle)
from cardcue_api.config import settings
from cardcue_api.persistence.database import get_session

router = APIRouter(prefix="/v1/admin/auth", tags=["admin-auth"])

@router.post("/login")
async def login(data: Login, request: Request, response: Response, session=Depends(get_session)):
    origin_check(request)
    ip = request.client.host if request.client else "unknown"
    await throttle(session, "login-ip:" + ip, 30)
    await throttle(session, "login-user:" + data.username, 8)
    user = (await session.execute(select(AdminUser).where(AdminUser.username == data.username))).scalar_one_or_none()
    valid = password_valid(data.password, user.password_hash if user else DUMMY_PASSWORD)
    if not valid or not user or not user.active:
        raise HTTPException(401, "用户名或密码错误")
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    session.add(WebSession(token_hash=digest(token), admin_id=user.id, csrf_token=csrf,
                          expires_at=now()+timedelta(hours=settings.session_hours), verified_at=now()))
    await audit(session, str(user.id), "login")
    await session.commit()
    response.set_cookie(COOKIE, token, httponly=True, secure=settings.environment=="production", samesite="strict",
                        max_age=settings.session_hours*3600, path="/")
    return {"username": user.username, "csrf_token": csrf}

@router.get("/session")
async def current(actor=Depends(require_admin), session=Depends(get_session)):
    user = await session.get(AdminUser, actor.session.admin_id)
    return {"username": user.username, "csrf_token": actor.session.csrf_token, "expires_at": actor.session.expires_at}

@router.post("/logout")
async def logout(response: Response, actor=Depends(require_admin), session=Depends(get_session)):
    await session.delete(actor.session)
    response.delete_cookie(COOKIE, path="/", secure=settings.environment=="production", httponly=True, samesite="strict")
    return {"ok": True}

@router.post("/verify")
async def verify(data: Password, actor=Depends(require_admin), session=Depends(get_session)):
    await throttle(session, "verify:"+actor.id)
    user = await session.get(AdminUser, actor.session.admin_id)
    if not password_valid(data.password, user.password_hash):
        raise HTTPException(401, "密码不正确")
    actor.session.verified_at = now()
    return {"ok": True}

@router.post("/password")
async def change_password(data: ChangePassword, actor=Depends(require_admin), session=Depends(get_session)):
    await throttle(session, "verify:"+actor.id)
    user = await session.get(AdminUser, actor.session.admin_id)
    if not password_valid(data.password, user.password_hash):
        raise HTTPException(401, "密码不正确")
    user.password_hash = password_hash(data.new_password)
    await session.execute(delete(WebSession).where(WebSession.admin_id == user.id))
    await audit(session, actor, "password_changed")
    return {"ok": True, "message": "密码已更改，请重新登录"}

@router.post("/pairing-codes")
async def pairing_code(actor=Depends(recent_admin), session=Depends(get_session)):
    code = secrets.token_urlsafe(24)
    session.add(PairingCode(code_hash=digest(code), expires_at=now()+timedelta(minutes=10)))
    await audit(session, actor, "pairing_code_created")
    return {"code": code, "expires_in_seconds": 600}
