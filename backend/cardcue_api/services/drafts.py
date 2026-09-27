"""Draft service: parsing email sources into drafts, manual review, and atomic confirmation."""

import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cardcue_api.domain.schemas import (
    StatementDetail,
    StatementDraftConfirmRequest,
    StatementDraftOut,
    StatementVersionOut,
)
from cardcue_api.mail.parser import MailMimeParser
from cardcue_api.mail.storage import MailStorageManager
from cardcue_api.parsing.html_extractor import HtmlStatementExtractor
from cardcue_api.parsing.model_adapter import ModelStatementExtractor
from cardcue_api.parsing.pdf_extractor import PdfStatementExtractor
from cardcue_api.persistence import (
    Account,
    Card,
    ChangeLog,
    EmailAttachment,
    EmailSource,
    Statement,
    StatementDraftModel,
    StatementVersion,
)
from cardcue_api.services.billing import ConflictError, NotFoundError


class DraftService:
    """Service for handling statement draft extraction, review, and confirmation."""

    def __init__(self, storage_manager: MailStorageManager | None = None) -> None:
        self.storage_manager = storage_manager or MailStorageManager()
        self.html_extractor = HtmlStatementExtractor()
        self.pdf_extractor = PdfStatementExtractor()
        from cardcue_api.admin.model_runtime import ManagedExtractor
        self.model_extractor = ManagedExtractor(None)
        self.mime_parser = MailMimeParser()

    async def _log_change(
        self,
        session: AsyncSession,
        entity_type: str,
        entity_id: uuid.UUID,
        action: str,
        snapshot: dict[str, Any] | None = None,
    ) -> ChangeLog:
        entry = ChangeLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            snapshot=snapshot,
        )
        session.add(entry)
        await session.flush()
        return entry

    async def list_drafts(
        self,
        session: AsyncSession,
        status: str | None = "pending_review",
        limit: int = 50,
        offset: int = 0,
    ) -> list[StatementDraftModel]:
        """List drafts with optional status filtering and pagination."""
        query = select(StatementDraftModel)
        if status and status.lower() != "all":
            query = query.where(StatementDraftModel.status == status)
        query = query.order_by(desc(StatementDraftModel.created_at)).offset(offset).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_draft(self, session: AsyncSession, draft_id: uuid.UUID) -> StatementDraftModel:
        """Get draft by ID."""
        draft = (await session.execute(select(StatementDraftModel).where(StatementDraftModel.id == draft_id).with_for_update())).scalar_one_or_none()
        if not draft:
            raise NotFoundError(f"Statement draft {draft_id} not found")
        return draft

    def _create_draft_model(
        self,
        draft_data: Any,
        source: EmailSource,
        extractor_name: str,
        fingerprint: str | None = None,
    ) -> StatementDraftModel:
        """Create a StatementDraftModel from a StatementDraft contract object."""
        return StatementDraftModel(
            email_source_id=source.id,
            mailbox_id=source.mailbox_id,
            status="pending_review",
            bank=draft_data.bank,
            currency=draft_data.currency,
            amount_minor=draft_data.amount_minor,
            minimum_minor=draft_data.minimum_minor,
            statement_date=draft_data.statement_date,
            due_date=draft_data.due_date,
            account_reference=draft_data.account_reference,
            card_tails=draft_data.card_tails,
            evidence=[{"field": e.field, "excerpt": e.excerpt} for e in draft_data.evidence],
            review_reasons=draft_data.review_reasons,
            extractor_name=extractor_name,
            model_fingerprint=fingerprint,
        )

    async def parse_email_source(
        self,
        session: AsyncSession,
        source_id: uuid.UUID,
    ) -> StatementDraftModel:
        """Parse an EmailSource into StatementDraftModel(s).

        Returns the first draft. For emails with multiple cards (e.g. CCB),
        creates multiple draft records in the database.

        Use parse_email_source_multi() to get all created drafts.
        """
        drafts = await self.parse_email_source_multi(session, source_id)
        return drafts[0]

    async def parse_email_source_multi(
        self,
        session: AsyncSession,
        source_id: uuid.UUID,
    ) -> list[StatementDraftModel]:
        """Parse an EmailSource into one or more StatementDraftModel records.

        For emails containing bills for multiple cards (e.g. CCB emails listing
        each card's balance separately), creates one draft per card.
        """
        source_stmt = (
            select(EmailSource)
            .where(EmailSource.id == source_id)
            .options(selectinload(EmailSource.attachments))
        )
        res = await session.execute(source_stmt)
        source = res.scalar_one_or_none()
        if not source:
            raise NotFoundError(f"EmailSource {source_id} not found")

        # 1. Check for PDF attachments first
        pdf_text = ""
        has_encrypted_pdf = False
        pdf_attachments = [att for att in source.attachments if att.filename.lower().endswith(".pdf")]
        if pdf_attachments:
            for att in pdf_attachments:
                if os.path.exists(att.storage_path):
                    txt = self.pdf_extractor.get_text_from_path(att.storage_path)
                    if txt and txt.strip():
                        pdf_text = txt
                        break
                    else:
                        check_draft = self.pdf_extractor.extract_from_path(att.storage_path)
                        if "attachment_password_required" in check_draft.review_reasons:
                            has_encrypted_pdf = True

        # 2. Extract HTML or plain text from email body
        email_body_text = ""
        if source.raw_storage_path and os.path.exists(source.raw_storage_path):
            try:
                raw_bytes = self.storage_manager.read_file(source.raw_storage_path)
                parsed_email = self.mime_parser.parse_bytes(raw_bytes)
                if parsed_email.body_html:
                    email_body_text = self.html_extractor.html_to_text(parsed_email.body_html)
                elif parsed_email.body_text:
                    email_body_text = parsed_email.body_text
            except Exception:
                pass

        # 3. Determine the best text to parse
        parse_text = pdf_text or email_body_text
        email_date_value = source.email_date.date() if hasattr(source.email_date, "date") else source.email_date

        if not parse_text:
            # No text to parse
            draft_data_list = [self.html_extractor.extract(
                content="",
                is_html=False,
                subject=source.subject,
                sender=source.sender,
                email_date=email_date_value,
            )]
            extractor_name = "rule"
            for d in draft_data_list:
                reasons = list(d.review_reasons)
                reasons.append("no_content_extracted")
                if has_encrypted_pdf:
                    reasons.append("attachment_password_required")
                d.review_reasons = list(dict.fromkeys(reasons))
        else:
            # 4. Try model extraction first, then rule-based
            try:
                draft_data_list, extractor_name = await self.model_extractor.extract_multi(
                    text=parse_text,
                    subject=source.subject,
                    sender=source.sender,
                    email_date=email_date_value,
                )
            except Exception:
                # Fallback: rule-based multi-card extraction
                draft_data_list = self.html_extractor.extract_multi(
                    content=parse_text,
                    is_html=False,
                    subject=source.subject,
                    sender=source.sender,
                    email_date=email_date_value,
                )
                extractor_name = "rule:fallback"

        # 5. Create draft model(s) and attempt auto-matching
        fingerprint = getattr(self.model_extractor, "fingerprint", None)
        result_drafts: list[StatementDraftModel] = []

        for draft_data in draft_data_list:
            draft_model = self._create_draft_model(
                draft_data=draft_data,
                source=source,
                extractor_name=extractor_name,
                fingerprint=fingerprint,
            )

            # Auto-match account/card if possible
            if draft_data.bank and draft_data.card_tails:
                for tail in draft_data.card_tails:
                    card_match = (await session.execute(
                        select(Card).join(Account).where(
                            Account.bank == draft_data.bank,
                            Card.tail == tail,
                            Account.status == "active",
                            Card.status == "active",
                        )
                    )).scalar_one_or_none()
                    if card_match:
                        draft_model.matched_account_id = card_match.account_id
                        draft_model.matched_card_id = card_match.id
                        break

            session.add(draft_model)
            result_drafts.append(draft_model)

        # Update source status
        source.parse_status = "parsed"
        source.error_message = None
        await session.flush()
        await session.commit()

        for dm in result_drafts:
            await session.refresh(dm)

        return result_drafts

    async def confirm_draft(
        self,
        session: AsyncSession,
        draft_id: uuid.UUID,
        req: StatementDraftConfirmRequest,
        confirmed_by: str = "system",
    ) -> tuple:
        """Confirm a draft and create/update Statement + Version atomically."""
        from cardcue_api.admin.models import CommandReceipt

        draft = (await session.execute(select(StatementDraftModel).where(StatementDraftModel.id == draft_id).with_for_update())).scalar_one_or_none()
        if not draft:
            raise NotFoundError(f"Statement draft {draft_id} not found")

        if draft.status != "pending_review":
            raise ConflictError(f"Draft is already {draft.status}; cannot confirm")

        if req.expected_revision is not None and draft.revision != req.expected_revision:
            raise ConflictError("Draft changed; reload before confirming")

        account_id = req.account_id
        card_id = req.card_id
        currency = req.currency or draft.currency
        amount_minor = req.amount_minor if req.amount_minor is not None else draft.amount_minor
        minimum_minor = req.minimum_minor if req.minimum_minor is not None else draft.minimum_minor
        statement_date = req.statement_date or draft.statement_date
        due_date = req.due_date or draft.due_date

        if not currency or amount_minor is None or not statement_date or not due_date:
            raise ConflictError("Cannot confirm: required fields missing")

        receipt_id = req.request_id or uuid.uuid4()
        fingerprint = f"confirm:{draft_id}:{receipt_id}"
        existing = await session.get(CommandReceipt, receipt_id)
        if existing:
            return existing.result

        # Existing statement?
        existing_stmt = (await session.execute(
            select(Statement).where(
                Statement.account_id == account_id,
                Statement.currency == currency,
                Statement.statement_date == statement_date,
            )
        )).scalar_one_or_none()

        if existing_stmt:
            if req.expected_statement_version_id and existing_stmt.current_version_id != req.expected_statement_version_id:
                raise ConflictError("Statement version changed; reload")

            stmt = existing_stmt
            max_ver = (await session.execute(
                select(func.max(StatementVersion.version_number)).where(StatementVersion.statement_id == stmt.id)
            )).scalar_one() or 0

            ver = StatementVersion(
                statement_id=stmt.id,
                version_number=max_ver + 1,
                amount_minor=amount_minor,
                minimum_minor=minimum_minor,
                source="email",
                reason=f"Confirmed from draft {draft.id}",
                confirmed_at=datetime.now(timezone.utc),
                confirmed_by=confirmed_by,
            )
            session.add(ver)
            await session.flush()

            stmt.current_version_id = ver.id
            await session.flush()

            await self._log_change(session, "statement", stmt.id, "update", {
                "id": str(stmt.id),
                "account_id": str(stmt.account_id),
                "currency": stmt.currency,
                "statement_date": str(stmt.statement_date),
                "due_date": str(stmt.due_date),
                "current_version_id": str(ver.id),
            })
            await self._log_change(session, "statement_version", ver.id, "create", {
                "id": str(ver.id),
                "statement_id": str(stmt.id),
                "version_number": ver.version_number,
                "amount_minor": ver.amount_minor,
                "minimum_minor": ver.minimum_minor,
                "source": ver.source,
                "reason": ver.reason,
            })
        else:
            stmt = Statement(
                account_id=account_id,
                currency=currency,
                statement_date=statement_date,
                due_date=due_date,
            )
            session.add(stmt)
            await session.flush()

            ver = StatementVersion(
                statement_id=stmt.id,
                version_number=1,
                amount_minor=amount_minor,
                minimum_minor=minimum_minor,
                source="email",
                reason=f"Confirmed from draft {draft.id}",
                confirmed_at=datetime.now(timezone.utc),
                confirmed_by=confirmed_by,
            )
            session.add(ver)
            await session.flush()

            stmt.current_version_id = ver.id
            await session.flush()

            await self._log_change(session, "statement", stmt.id, "create", {
                "id": str(stmt.id),
                "account_id": str(stmt.account_id),
                "currency": stmt.currency,
                "statement_date": str(stmt.statement_date),
                "due_date": str(stmt.due_date),
                "current_version_id": str(ver.id),
            })
            await self._log_change(session, "statement_version", ver.id, "create", {
                "id": str(ver.id),
                "statement_id": str(stmt.id),
                "version_number": ver.version_number,
                "amount_minor": ver.amount_minor,
                "minimum_minor": ver.minimum_minor,
                "source": ver.source,
                "reason": ver.reason,
            })

        # Update draft
        draft.revision += 1
        session.add(CommandReceipt(id=receipt_id, fingerprint=fingerprint, result={"version_id": str(ver.id)}))
        draft.status = "confirmed"
        draft.confirmed_version_id = ver.id
        draft.matched_account_id = account_id
        draft.matched_card_id = card_id

        await session.flush()
        await session.refresh(draft)
        await session.refresh(stmt)
        await session.refresh(ver)
        return stmt, ver, draft

    async def reject_draft(
        self,
        session: AsyncSession,
        draft_id: uuid.UUID,
        reason: str,
        expected_revision: int | None = None,
    ) -> StatementDraftModel:
        """Reject an unneeded draft."""
        draft = (await session.execute(select(StatementDraftModel).where(StatementDraftModel.id == draft_id).with_for_update())).scalar_one_or_none()
        if not draft:
            raise NotFoundError(f"Statement draft {draft_id} not found")

        if draft.status != "pending_review":
            raise ConflictError(f"Draft is already {draft.status}; cannot reject")

        if expected_revision is not None and draft.revision != expected_revision:
            raise ConflictError("Draft changed; reload before rejecting")
        draft.revision += 1
        draft.status = "rejected"
        draft.rejection_reason = reason
        await session.flush()
        await session.commit()
        await session.refresh(draft)
        return draft

    async def parse_all_pending(
        self,
        session: AsyncSession,
        limit: int = 50,
        reparse: bool = False,
    ) -> list[StatementDraftModel]:
        """Parse all pending statement candidate EmailSources.

        If reparse=True, re-evaluates all statement candidates regardless of parse_status.
        """
        conditions = [EmailSource.is_statement_candidate.is_(True)]
        if not reparse:
            conditions.append(EmailSource.parse_status == "pending")

        stmt = (
            select(EmailSource)
            .where(and_(*conditions))
            .limit(limit)
        )
        sources = list((await session.execute(stmt)).scalars().all())
        results = []
        for source in sources:
            try:
                drafts = await self.parse_email_source_multi(session, source.id)
                results.extend(drafts)
            except Exception as e:
                source.parse_status = "failed"
                source.error_message = "parse_failed"
                await session.flush()
                await session.commit()
        return results
