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
from cardcue_api.parsing.model_adapter import SYSTEM_PROMPT_V2, parse_model_response_multi
from cardcue_api.persistence.database import async_session_factory

PROMPT_VERSION = "v2-direct-transactions-2"

class ManagedExtractor:
    def __init__(self, revision: ModelRevision | None):
        self.revision = revision
        self.usage = None
        self.fingerprint = None

    async def extract(self, text: str, subject="", sender="", email_date=None):
        """Extract a single draft (backwards compatible). Returns (StatementDraft, extractor_name)."""
        drafts, extractor_name = await self.extract_multi(text, subject=subject, sender=sender, email_date=email_date)
        return drafts[0], extractor_name

    async def extract_multi(self, text: str, subject="", sender="", email_date=None, source_manifest=None):
        """Extract one or more drafts. Returns (list[StatementDraft], extractor_name)."""
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
            raise ValueError("model_not_configured")
        if source_manifest is not None and source_manifest.has_unsupported:
            raise ValueError("attachment_capability_unavailable")
        params = self.revision.parameters
        if len(text) > params["input_limit"]:
            raise ValueError("input_exceeds_limit_manual_review_required")
        fingerprint = hashlib.sha256(json.dumps([str(self.revision.id), PROMPT_VERSION, text, subject, sender,
            str(email_date), source_manifest.model_dump() if source_manifest else None],
            ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.fingerprint = fingerprint
        url = params["base_url"].rstrip("/")
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"
        prompt = SYSTEM_PROMPT_V2
        payload = {"model": params["model"], "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps({"untrusted_email": {"subject": subject, "sender": sender, "body": text, "email_date": str(email_date) if email_date else None,
                "source_manifest": source_manifest.model_dump() if source_manifest else None}}, ensure_ascii=False)}],
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
                results = parse_model_response_multi(raw, email_date=None)
                # Preserve invalid evidence as a review reason, never certify it as verified.
                corpus = text + "\n" + subject + "\n" + sender
                for result in results:
                    bad_fields = {e.field for e in result.evidence if e.excerpt not in corpus}
                    result.evidence = [e for e in result.evidence if e.excerpt in corpus]
                    if bad_fields:
                        result.review_reasons = list(dict.fromkeys([
                            *result.review_reasons, *[f"unverified_evidence:{field}" for field in sorted(bad_fields)]]))
                    for tx in result.transactions:
                        if not tx.evidence or any(e.excerpt not in corpus for e in tx.evidence):
                            tx.review_flags = list(dict.fromkeys([*tx.review_flags, "unverified_evidence"]))
                        tx.evidence = [e for e in tx.evidence if e.excerpt in corpus]
                    result.source_manifest = source_manifest
                results = [StatementDraft.model_validate_json(r.model_dump_json()) for r in results]
                usage = data.get("usage") or {}
                self.usage = {k: v for k, v in usage.items() if k in ("prompt_tokens", "completion_tokens", "total_tokens") and type(v) is int and v >= 0}
                async with async_session_factory() as session:
                    call = await session.get(ModelCall, call_id)
                    call.status, call.usage = "succeeded", self.usage
                    await session.commit()
                return results, "model"
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