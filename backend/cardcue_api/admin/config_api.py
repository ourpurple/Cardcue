import asyncio
import uuid
from fastapi import APIRouter, Depends, HTTPException
import shutil
from sqlalchemy import delete, select, update
from cardcue_api.config import settings
from cardcue_api.admin.models import AdminJob, ModelCall, ModelProfile, ModelRevision, RuntimeSettings
from cardcue_api.admin.schemas import MailConfig, ModelConfig, ModelTest, RevisionRequest
from cardcue_api.admin.security import audit, now, recent_admin, require_admin
from cardcue_api.mail.client import ReadOnlyImapClient
from cardcue_api.mail.crypto import decrypt_token, encrypt_token
from cardcue_api.persistence.database import get_session
from cardcue_api.persistence.drafts import StatementDraftModel
from cardcue_api.persistence.mail import EmailAttachment, EmailSource, MailCursor, MailJob, Mailbox

router = APIRouter(prefix="/v1/admin", tags=["configuration"], dependencies=[Depends(require_admin)])

async def get_locked(session, cls, identifier):
    value = (await session.execute(select(cls).where(cls.id == identifier).with_for_update())).scalar_one_or_none()
    if not value:
        raise HTTPException(404, "记录不存在")
    return value

def revision_check(row, expected):
    if row.revision != expected:
        raise HTTPException(409, "内容已被其他操作更新，请刷新后重试")

def mailbox_public(row):
    config = dict(row.settings_json or {})
    config.setdefault("auto_parse", True)
    config.update(email_address=row.email_address, imap_host=row.imap_host, imap_port=row.imap_port,
                  use_ssl=row.use_ssl, check_interval_minutes=row.check_interval_minutes)
    if row.pending_config:
        config.update(row.pending_config)
    config.update(id=str(row.id), revision=row.revision, tested_revision=row.tested_revision,
                  is_active=row.is_active, status=row.status, last_checked_at=row.last_checked_at,
                  last_attempt_at=row.last_attempt_at, error_message=row.error_message,
                  has_secret=bool(row.pending_token or row.encrypted_auth_token), has_pending=bool(row.pending_config))
    return config

@router.get("/mailboxes")
async def list_mailboxes(session=Depends(get_session)):
    rows = (await session.execute(select(Mailbox).order_by(Mailbox.created_at.desc()))).scalars()
    return [mailbox_public(row) for row in rows]

@router.post("/mailboxes", status_code=201)
async def create_mailbox(data: MailConfig, actor=Depends(recent_admin), session=Depends(get_session)):
    if not data.auth_token:
        raise HTTPException(422, "首次配置必须填写授权码")
    if (await session.execute(select(Mailbox.id).where(Mailbox.email_address == data.email_address))).first():
        raise HTTPException(409, "邮箱已存在；请编辑或恢复原配置")
    config = data.model_dump(exclude={"auth_token", "expected_revision"})
    row = Mailbox(email_address=data.email_address, imap_host=data.imap_host, imap_port=data.imap_port,
                  use_ssl=data.use_ssl, encrypted_auth_token=encrypt_token(data.auth_token), auth_type="password",
                  is_active=False, status="disabled", check_interval_minutes=data.check_interval_minutes,
                  settings_json=config, revision=1)
    session.add(row)
    await session.flush()
    await audit(session, actor, "mailbox_created_disabled", row.id)
    return mailbox_public(row)

@router.put("/mailboxes/{identifier}")
async def update_mailbox(identifier: uuid.UUID, data: MailConfig, actor=Depends(recent_admin), session=Depends(get_session)):
    row = await get_locked(session, Mailbox, identifier)
    revision_check(row, data.expected_revision)
    # Changing mailbox identity must be a separate mailbox, never silently reuse old UID cursors.
    old = row.settings_json or {}
    old_user = (old.get("username") or row.email_address or "").strip()
    new_user = (data.username or data.email_address or "").strip()
    old_folder = (old.get("folder") or "INBOX").strip()
    new_folder = (data.folder or "INBOX").strip()
    old_host = (row.imap_host or "").strip()
    new_host = (data.imap_host or "").strip()
    old_email = (row.email_address or "").strip()
    new_email = (data.email_address or "").strip()

    if new_email != old_email or new_host != old_host or new_folder != old_folder or new_user != old_user:
        raise HTTPException(409, "邮箱身份、服务器或文件夹变化请新建配置；旧邮箱可停用，历史保留")

    row.pending_config = data.model_dump(exclude={"auth_token", "expected_revision"})
    if data.auth_token:
        row.pending_token = encrypt_token(data.auth_token)
        row.tested_revision = None
    else:
        # Secret didn't change: if the previous revision was tested, keep it tested
        if row.tested_revision is not None:
            row.tested_revision = row.revision + 1
        # If already active and only metadata (e.g. name, check interval) changed:
        if row.is_active:
            row.settings_json = {**(row.settings_json or {}), **row.pending_config, "active_revision": row.revision + 1}
            row.check_interval_minutes = data.check_interval_minutes
            row.pending_config = None
            row.pending_token = None

    row.revision += 1
    await audit(session, actor, "mailbox_configuration_staged", row.id, {"revision": row.revision, "secret_changed": bool(data.auth_token)})
    return mailbox_public(row)

@router.post("/mailboxes/{identifier}/test")
async def test_mailbox(identifier: uuid.UUID, data: RevisionRequest, actor=Depends(recent_admin), session=Depends(get_session)):
    row = await get_locked(session, Mailbox, identifier)
    revision_check(row, data.expected_revision)
    conf = mailbox_public(row)
    token = decrypt_token(row.pending_token or row.encrypted_auth_token)
    def test():
        with ReadOnlyImapClient(host=conf["imap_host"], port=conf["imap_port"],
                               username=conf.get("username") or conf["email_address"], password=token,
                               use_ssl=conf["use_ssl"], timeout=20) as client:
            client.select_folder(conf.get("folder", "INBOX"))
    try:
        await asyncio.to_thread(test)
    except Exception:
        row.tested_revision = None
        await audit(session, actor, "mailbox_test_failed", row.id)
        await session.commit()
        raise HTTPException(400, "连接测试失败，请检查地址、TLS 和授权码；未修改原生效配置")
    row.tested_revision = row.revision
    await audit(session, actor, "mailbox_test_succeeded", row.id)
    return {"ok": True, "revision": row.revision}

@router.post("/mailboxes/{identifier}/enable")
async def enable_mailbox(identifier: uuid.UUID, data: RevisionRequest, actor=Depends(recent_admin), session=Depends(get_session)):
    row = await get_locked(session, Mailbox, identifier)
    revision_check(row, data.expected_revision)
    if row.tested_revision != row.revision:
        raise HTTPException(409, "请先测试当前版本的连接")
    conf = row.pending_config or row.settings_json
    for field in ("imap_host", "imap_port", "use_ssl", "check_interval_minutes"):
        if field in conf:
            setattr(row, field, conf[field])
    if row.pending_token:
        row.encrypted_auth_token = row.pending_token
    row.settings_json = {**conf, "active_revision": row.revision}
    row.pending_config, row.pending_token = None, None
    row.is_active, row.status, row.error_message = True, "active", None
    await audit(session, actor, "mailbox_enabled", row.id, {"revision": row.revision})
    return mailbox_public(row)

@router.post("/mailboxes/{identifier}/disable")
async def disable_mailbox(identifier: uuid.UUID, data: RevisionRequest, actor=Depends(recent_admin), session=Depends(get_session)):
    row = await get_locked(session, Mailbox, identifier)
    revision_check(row, data.expected_revision)
    row.is_active, row.status = False, "disabled"
    await audit(session, actor, "mailbox_disabled", row.id)
    return mailbox_public(row)

@router.delete("/mailboxes/{identifier}")
async def delete_mailbox(identifier: uuid.UUID, actor=Depends(require_admin), session=Depends(get_session)):
    row = await get_locked(session, Mailbox, identifier)
    email_addr = row.email_address

    # 1. Gather all email source IDs under this mailbox
    source_ids = (await session.execute(
        select(EmailSource.id).where(EmailSource.mailbox_id == identifier)
    )).scalars().all()

    if source_ids:
        # Unlink drafts associated with these email sources
        await session.execute(
            update(StatementDraftModel)
            .where(StatementDraftModel.email_source_id.in_(source_ids))
            .values(email_source_id=None)
        )
        # Delete admin background jobs for these email sources
        await session.execute(
            delete(AdminJob).where(AdminJob.target_id.in_(source_ids))
        )
        # Delete attachments
        await session.execute(
            delete(EmailAttachment).where(EmailAttachment.email_source_id.in_(source_ids))
        )
        # Delete email sources
        await session.execute(
            delete(EmailSource).where(EmailSource.mailbox_id == identifier)
        )

    # 2. Unlink drafts directly referencing this mailbox
    await session.execute(
        update(StatementDraftModel)
        .where(StatementDraftModel.mailbox_id == identifier)
        .values(mailbox_id=None)
    )

    # 3. Clean up mail cursors, mail jobs, and admin jobs for this mailbox
    await session.execute(
        delete(MailCursor).where(MailCursor.mailbox_id == identifier)
    )
    await session.execute(
        delete(MailJob).where(MailJob.mailbox_id == identifier)
    )
    await session.execute(
        delete(AdminJob).where(AdminJob.target_id == identifier)
    )

    # 4. Clean up disk files under storage directory
    try:
        from cardcue_api.mail.storage import MailStorageManager
        storage = MailStorageManager()
        mb_dir = storage.base_dir / str(identifier)
        if mb_dir.exists() and mb_dir.is_dir():
            shutil.rmtree(mb_dir, ignore_errors=True)
    except Exception:
        pass

    # 5. Delete the mailbox record
    await session.delete(row)
    await audit(session, actor, "mailbox_deleted", str(identifier), {"email_address": email_addr})
    return {"ok": True, "id": str(identifier)}

async def ensure_default_model_from_env(session) -> ModelProfile | None:
    """Ensure that if LLM credentials exist in .env and no model profile exists,
    a default profile is automatically seeded and activated.
    Also ensures an active revision is set in RuntimeSettings if missing."""
    if not settings.llm_api_key or not settings.llm_base_url or not settings.llm_model:
        return None

    existing = (await session.execute(select(ModelProfile.id).limit(1))).first()
    if not existing:
        profile = ModelProfile(name="默认模型 (.env)")
        session.add(profile)
        await session.flush()

        params = {
            "base_url": settings.llm_base_url,
            "model": settings.llm_model,
            "temperature": 0.0,
            "max_tokens": 4096,
            "timeout_seconds": 45,
            "max_retries": 1,
            "input_limit": 24000,
            "json_mode": True,
            "daily_limit": 500,
        }
        rev = ModelRevision(
            profile_id=profile.id,
            number=1,
            parameters=params,
            encrypted_key=encrypt_token(settings.llm_api_key),
            tested_at=now(),
            test_error=None,
            revoked=False,
        )
        session.add(rev)
        await session.flush()

        state = await session.get(RuntimeSettings, "model")
        if not state:
            session.add(RuntimeSettings(key="model", value={"revision_id": str(rev.id)}))
        else:
            state.value = {"revision_id": str(rev.id)}

        await session.commit()
        return profile
    else:
        state = await session.get(RuntimeSettings, "model")
        if not state or not state.value or not state.value.get("revision_id"):
            latest_rev = (await session.execute(
                select(ModelRevision)
                .where(ModelRevision.revoked == False)
                .order_by(ModelRevision.created_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            if latest_rev:
                if not state:
                    session.add(RuntimeSettings(key="model", value={"revision_id": str(latest_rev.id)}))
                else:
                    state.value = {"revision_id": str(latest_rev.id)}
                await session.commit()
        return None

async def model_public(session, profile):
    revisions = list((await session.execute(select(ModelRevision).where(ModelRevision.profile_id == profile.id).order_by(ModelRevision.number.desc()))).scalars())
    state = await session.get(RuntimeSettings, "model")
    active = (state.value or {}).get("revision_id") if state else None
    return {"id": profile.id, "name": profile.name, "revisions": [
        {"id": row.id, "number": row.number, "parameters": row.parameters, "has_secret": bool(row.encrypted_key),
         "tested_at": row.tested_at, "test_error": row.test_error, "revoked": row.revoked,
         "active": str(row.id) == active, "created_at": row.created_at} for row in revisions]}

@router.get("/models")
async def models(session=Depends(get_session)):
    await ensure_default_model_from_env(session)
    rows = (await session.execute(select(ModelProfile).order_by(ModelProfile.created_at.desc()))).scalars()
    return [await model_public(session, row) for row in rows]

async def save_model(session, data, actor, identifier=None):
    if identifier:
        profile = await get_locked(session, ModelProfile, identifier)
        latest = (await session.execute(select(ModelRevision).where(ModelRevision.profile_id == identifier).order_by(ModelRevision.number.desc()).limit(1))).scalar_one()
        if data.expected_revision != latest.number:
            raise HTTPException(409, "配置已更新，请刷新")
        key, number = latest.encrypted_key, latest.number + 1
        profile.name = data.name
    else:
        profile = ModelProfile(name=data.name)
        session.add(profile)
        await session.flush()
        key, number = "", 1
    if data.api_key:
        key = encrypt_token(data.api_key)
    if not key:
        raise HTTPException(422, "请填写模型 API Key")
    revision = ModelRevision(profile_id=profile.id, number=number,
        parameters=data.model_dump(exclude={"name", "api_key", "expected_revision"}), encrypted_key=key)
    session.add(revision)
    await session.flush()
    await audit(session, actor, "model_revision_saved", profile.id, {"revision": number})
    return await model_public(session, profile)

@router.post("/models", status_code=201)
async def create_model(data: ModelConfig, actor=Depends(recent_admin), session=Depends(get_session)):
    return await save_model(session, data, actor)

@router.put("/models/{identifier}")
async def update_model(identifier: uuid.UUID, data: ModelConfig, actor=Depends(recent_admin), session=Depends(get_session)):
    return await save_model(session, data, actor, identifier)

@router.delete("/models/{identifier}")
async def delete_model(identifier: uuid.UUID, actor=Depends(require_admin), session=Depends(get_session)):
    profile = await get_locked(session, ModelProfile, identifier)
    rev_ids = (await session.execute(
        select(ModelRevision.id).where(ModelRevision.profile_id == identifier)
    )).scalars().all()

    # Check if any revision is globally active
    state = await session.get(RuntimeSettings, "model")
    active_id = (state.value or {}).get("revision_id") if state else None
    if active_id and any(str(r) == str(active_id) for r in rev_ids):
        raise HTTPException(400, "该方案包含当前处于全局激活状态的模型版本，无法直接删除。请先激活其他模型方案。")

    if rev_ids:
        await session.execute(
            delete(ModelCall).where(ModelCall.revision_id.in_(rev_ids))
        )
        await session.execute(
            delete(ModelRevision).where(ModelRevision.profile_id == identifier)
        )

    await session.delete(profile)
    await audit(session, actor, "model_profile_deleted", str(identifier), {"name": profile.name})
    return {"ok": True, "id": str(identifier)}

@router.post("/model-revisions/{identifier}/test")
async def test_model(identifier: uuid.UUID, data: ModelTest, actor=Depends(recent_admin), session=Depends(get_session)):
    from cardcue_api.admin.model_runtime import ManagedExtractor
    row = await get_locked(session, ModelRevision, identifier)
    if row.revoked:
        raise HTTPException(409, "配置已撤销")
    await session.commit()
    extractor = ManagedExtractor(row, force=True)
    try:
        result, _ = await extractor.extract("测试银行信用卡账单：币种人民币 CNY，账单金额 100.00 元，最低还款 10.00 元，账单日 2026-01-01，到期日 2026-01-20。" if data.sample else "This is a connection test, not a bill. Return all financial fields as null.")
    except Exception:
        row.test_error = "connection_or_schema_failed"
        row.tested_at = None
        await session.commit()
        raise HTTPException(400, "模型测试失败：检查地址、密钥、模型名称及 JSON 支持情况")
    row.tested_at, row.test_error = now(), None
    await audit(session, actor, "model_test_succeeded", row.id)
    return {"ok": True, "sample": result.model_dump(mode="json"), "usage": extractor.usage}

@router.post("/model-revisions/{identifier}/activate")
async def activate_model(identifier: uuid.UUID, actor=Depends(recent_admin), session=Depends(get_session)):
    state = (await session.execute(select(RuntimeSettings).where(RuntimeSettings.key == "model").with_for_update())).scalar_one()
    row = await get_locked(session, ModelRevision, identifier)
    if row.revoked or not row.tested_at:
        raise HTTPException(409, "请先成功测试未撤销的配置版本")
    state.value = {"revision_id": str(identifier)}
    await audit(session, actor, "model_activated", identifier)
    return {"ok": True}

@router.post("/model-revisions/{identifier}/revoke")
async def revoke_model(identifier: uuid.UUID, actor=Depends(recent_admin), session=Depends(get_session)):
    state = (await session.execute(select(RuntimeSettings).where(RuntimeSettings.key == "model").with_for_update())).scalar_one()
    row = await get_locked(session, ModelRevision, identifier)
    row.revoked = True
    if state.value.get("revision_id") == str(identifier):
        state.value = {}
    await audit(session, actor, "model_revoked", identifier)
    return {"ok": True}
