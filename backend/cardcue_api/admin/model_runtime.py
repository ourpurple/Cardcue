"""Version-pinned model calls with durable limits and an explicit untrusted-data boundary."""
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import func, select
from cardcue_api.admin.models import ModelCall, ModelRevision, RuntimeSettings
from cardcue_api.admin.outbound import post_json
from cardcue_api.admin.security import now
from cardcue_api.contracts import StatementDraft
from cardcue_api.mail.crypto import decrypt_token
from cardcue_api.parsing.model_adapter import SYSTEM_PROMPT, parse_model_response
from cardcue_api.parsing.html_extractor import HtmlStatementExtractor
from cardcue_api.persistence.database import async_session_factory

PROMPT_VERSION = "web-1-no-date-guess"

class ManagedExtractor:
    def __init__(self, revision: ModelRevision | None, force=False):
        self.revision = revision
        self.force = force
        self.usage = None
        self.fingerprint = None
    async def extract(self, text: str, subject="", sender="", email_date=None):
        if self.revision is None:
            try:
                import uuid
                from cardcue_api.admin.config_api import ensure_default_model_from_env
                async with async_session_factory() as session:
                    state = await session.get(RuntimeSettings, "model")
                    if not (state and state.value and state.value.get("revision_id")):
                        await ensure_default_model_from_env(session)
                        state = await session.get(RuntimeSettings, "model")
                    if state and state.value and state.value.get("revision_id"):
                        rev = await session.get(ModelRevision, uuid.UUID(state.value["revision_id"]))
                        if rev and not rev.revoked:
                            self.revision = rev
            except Exception:
                pass
        if self.revision is None:
            draft = HtmlStatementExtractor().extract(text, is_html=False, subject=subject, sender=sender, email_date=email_date)
            draft.review_reasons = list(dict.fromkeys([*draft.review_reasons, "rule_only:no_active_model"]))
            return draft, "rule"
        params = self.revision.parameters
        if len(text) > params["input_limit"]:
            raise ValueError("input_exceeds_limit_manual_review_required")
        fingerprint = hashlib.sha256(json.dumps([str(self.revision.id), PROMPT_VERSION, text, subject, sender, str(email_date)], ensure_ascii=False).encode()).hexdigest()
        self.fingerprint = fingerprint
        cache_key = "cache:" + fingerprint[:40]
        async with async_session_factory() as session:
            cached = await session.get(RuntimeSettings, cache_key)
            if cached and not self.force:
                # strict JSON validation parses ISO dates without coercing money from floats.
                return StatementDraft.model_validate_json(json.dumps(cached.value)), "model:cached"
        url = params["base_url"].rstrip("/")
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"
        prompt = SYSTEM_PROMPT.replace('infer the year from Email Date.', 'leave the date null; never infer a missing year.')
        payload = {"model": params["model"], "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps({"untrusted_email": {"subject": subject, "sender": sender, "body": text}}, ensure_ascii=False)}],
            "temperature": params["temperature"], "max_tokens": params["max_tokens"]}
        if params["json_mode"]:
            payload["response_format"] = {"type": "json_object"}
        for attempt in range(params["max_retries"] + 1):
            async with async_session_factory() as session:
                revision = (await session.execute(select(ModelRevision).where(ModelRevision.id == self.revision.id).with_for_update())).scalar_one()
                if revision.revoked:
                    raise ValueError("model_revision_revoked")
                midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                count = (await session.execute(select(func.count()).select_from(ModelCall).where(ModelCall.revision_id == revision.id, ModelCall.created_at >= midnight))).scalar_one()
                if count >= params["daily_limit"]:
                    raise ValueError("model_daily_limit_reached")
                call = ModelCall(revision_id=revision.id, status="started")
                session.add(call)
                await session.commit()
                call_id = call.id
            try:
                data = await post_json(url, decrypt_token(self.revision.encrypted_key), payload, params["timeout_seconds"])
                choice = data["choices"][0]
                if choice.get("finish_reason") not in (None, "stop"):
                    raise ValueError("incomplete_model_response")
                raw = choice["message"]["content"]
                result = parse_model_response(raw, email_date=None)
                # Evidence must be an actual excerpt of the submitted data, not invented prose.
                corpus = text + "\n" + subject + "\n" + sender
                result.evidence = [e for e in result.evidence if e.excerpt in corpus]
                result = StatementDraft.model_validate_json(result.model_dump_json())
                usage = data.get("usage") or {}
                self.usage = {k: v for k, v in usage.items() if k in ("prompt_tokens", "completion_tokens", "total_tokens") and type(v) is int and v >= 0}
                async with async_session_factory() as session:
                    call = await session.get(ModelCall, call_id)
                    call.status, call.usage = "succeeded", self.usage
                    cached = await session.get(RuntimeSettings, cache_key)
                    if cached:
                        cached.value = result.model_dump(mode="json")
                    else:
                        session.add(RuntimeSettings(key=cache_key, value=result.model_dump(mode="json")))
                    await session.commit()
                return result, "model"
            except Exception as exc:
                code = str(exc) if str(exc) in ("provider_http_429", "provider_http_503") else "model_failed_or_outcome_unknown"
                async with async_session_factory() as session:
                    call = await session.get(ModelCall, call_id)
                    call.status = "rate_limited" if code == "provider_http_429" else "failed_or_unknown"
                    await session.commit()
                if code in ("provider_http_429", "provider_http_503") and attempt < params["max_retries"]:
                    import asyncio
                    await asyncio.sleep(min(2 ** attempt, 8))
                    continue
                raise ValueError(code) from None
