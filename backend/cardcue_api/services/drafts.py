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
        self.model_extractor = ModelStatementExtractor()
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
        draft = await session.get(StatementDraftModel, draft_id)
        if not draft:
            raise NotFoundError(f"Statement draft {draft_id} not found")
        return draft

    async def parse_email_source(
        self,
        session: AsyncSession,
        source_id: uuid.UUID,
    ) -> StatementDraftModel:
        """Parse an EmailSource into a StatementDraftModel."""
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
                with open(source.raw_storage_path, "rb") as f:
                    raw_bytes = f.read()
                parsed_email = self.mime_parser.parse_bytes(raw_bytes)
                if parsed_email.body_html:
                    email_body_text = self.html_extractor.html_to_text(parsed_email.body_html)
                elif parsed_email.body_plain:
                    email_body_text = parsed_email.body_plain
            except Exception:
                pass

        # 3. Choose primary text for extraction: prefer PDF text if non-empty, else email body
        text_to_extract = pdf_text.strip() if pdf_text.strip() else email_body_text.strip()

        # 4. Extract statement using model extractor (LLM if configured, rule fallback otherwise)
        if text_to_extract:
            extracted_draft, extractor_name = await self.model_extractor.extract(
                text=text_to_extract,
                subject=source.subject or "",
                sender=source.sender or "",
                email_date=source.email_date.date() if source.email_date else None,
            )
        else:
            extracted_draft = self.html_extractor.extract(
                content="",
                is_html=False,
                subject=source.subject or "",
                sender=source.sender or "",
                email_date=source.email_date.date() if source.email_date else None,
            )
            extractor_name = "rule:empty"

        if has_encrypted_pdf and "attachment_password_required" not in extracted_draft.review_reasons:
            reasons = list(extracted_draft.review_reasons)
            reasons.append("attachment_password_required")
            extracted_draft.review_reasons = list(dict.fromkeys(reasons))

        # 3. Account and Card matching in database
        matched_account_id = None
        matched_card_id = None

        # Check card tails
        if extracted_draft.card_tails:
            card_res = await session.execute(
                select(Card).where(Card.tail.in_(extracted_draft.card_tails))
            )
            found_card = card_res.scalars().first()
            if found_card:
                matched_card_id = found_card.id
                matched_account_id = found_card.account_id

        # Check account reference or bank
        if not matched_account_id and extracted_draft.account_reference:
            acct_res = await session.execute(
                select(Account).where(Account.reference == extracted_draft.account_reference)
            )
            found_acct = acct_res.scalars().first()
            if found_acct:
                matched_account_id = found_acct.id

        if not matched_account_id and extracted_draft.bank:
            acct_bank_res = await session.execute(
                select(Account).where(Account.bank == extracted_draft.bank)
            )
            accts_with_bank = list(acct_bank_res.scalars().all())
            if len(accts_with_bank) == 1:
                # Unambiguous single account for this bank
                matched_account_id = accts_with_bank[0].id

        # Update review reasons
        review_reasons = list(extracted_draft.review_reasons)
        if matched_account_id:
            # Resolved account
            review_reasons = [r for r in review_reasons if r != "unresolved:account"]
        else:
            if "unresolved:account" not in review_reasons:
                review_reasons.append("unresolved:account")

        # 4. Upsert StatementDraftModel
        existing_draft_res = await session.execute(
            select(StatementDraftModel).where(StatementDraftModel.email_source_id == source_id)
        )
        draft_model = existing_draft_res.scalar_one_or_none()

        if draft_model:
            if draft_model.status == "confirmed":
                # Already confirmed, do not overwrite
                return draft_model
            # Update existing draft
            draft_model.bank = extracted_draft.bank
            draft_model.currency = extracted_draft.currency
            draft_model.amount_minor = extracted_draft.amount_minor
            draft_model.minimum_minor = extracted_draft.minimum_minor
            draft_model.statement_date = extracted_draft.statement_date
            draft_model.due_date = extracted_draft.due_date
            draft_model.account_reference = extracted_draft.account_reference
            draft_model.card_tails = extracted_draft.card_tails
            draft_model.evidence = [e.model_dump() for e in extracted_draft.evidence]
            draft_model.review_reasons = review_reasons
            draft_model.matched_account_id = matched_account_id
            draft_model.matched_card_id = matched_card_id
            draft_model.extractor_name = extractor_name
        else:
            draft_model = StatementDraftModel(
                email_source_id=source.id,
                mailbox_id=source.mailbox_id,
                status="pending_review",
                bank=extracted_draft.bank,
                currency=extracted_draft.currency,
                amount_minor=extracted_draft.amount_minor,
                minimum_minor=extracted_draft.minimum_minor,
                statement_date=extracted_draft.statement_date,
                due_date=extracted_draft.due_date,
                account_reference=extracted_draft.account_reference,
                card_tails=extracted_draft.card_tails,
                evidence=[e.model_dump() for e in extracted_draft.evidence],
                review_reasons=review_reasons,
                matched_account_id=matched_account_id,
                matched_card_id=matched_card_id,
                extractor_name=extractor_name,
            )
            session.add(draft_model)

        source.parse_status = "parsed"
        await session.flush()
        await session.commit()
        await session.refresh(draft_model)
        return draft_model

    async def confirm_draft(
        self,
        session: AsyncSession,
        draft_id: uuid.UUID,
        req: StatementDraftConfirmRequest,
        confirmed_by: str = "device",
    ) -> tuple[Statement, StatementVersion, StatementDraftModel]:
        """Confirm a draft into an official Statement and StatementVersion in an atomic transaction."""
        draft = await session.get(StatementDraftModel, draft_id)
        if not draft:
            raise NotFoundError(f"Statement draft {draft_id} not found")

        if draft.status != "pending_review":
            raise ConflictError(f"Draft is already {draft.status}; cannot confirm")

        # Resolve values: explicit request override takes precedence
        account_id = req.account_id
        currency = req.currency or draft.currency or "CNY"
        amount_minor = req.amount_minor if req.amount_minor is not None else draft.amount_minor
        minimum_minor = req.minimum_minor if req.minimum_minor is not None else draft.minimum_minor
        statement_date = req.statement_date or draft.statement_date
        due_date = req.due_date or draft.due_date
        card_id = req.card_id or draft.matched_card_id

        # Invariant checks
        if amount_minor is None:
            raise ConflictError("amount_minor cannot be null for confirmed statement")
        if statement_date is None or due_date is None:
            raise ConflictError("statement_date and due_date are required")
        if due_date < statement_date:
            raise ConflictError("due_date must be >= statement_date")
        if minimum_minor is not None:
            if minimum_minor < 0:
                raise ConflictError("minimum_minor must be >= 0")
            if minimum_minor > amount_minor:
                raise ConflictError("minimum_minor cannot exceed amount_minor")

        # Check Account exists
        acct = await session.get(Account, account_id)
        if not acct:
            raise NotFoundError(f"Account {account_id} not found")

        # Check Card belongs to account if provided
        if card_id:
            card = await session.get(Card, card_id)
            if not card or card.account_id != account_id:
                raise ConflictError(f"Card {card_id} does not belong to Account {account_id}")

        # Check if Statement exists for (account_id, currency, statement_date)
        stmt_res = await session.execute(
            select(Statement)
            .where(
                and_(
                    Statement.account_id == account_id,
                    Statement.currency == currency,
                    Statement.statement_date == statement_date,
                )
            )
            .options(selectinload(Statement.versions))
        )
        existing_stmt = stmt_res.scalar_one_or_none()

        if existing_stmt:
            stmt = existing_stmt
            max_v = max((v.version_number for v in stmt.versions), default=0)
            ver = StatementVersion(
                statement_id=stmt.id,
                version_number=max_v + 1,
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
            stmt.due_date = due_date
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
        draft.status = "confirmed"
        draft.confirmed_version_id = ver.id
        draft.matched_account_id = account_id
        draft.matched_card_id = card_id

        await session.flush()
        await session.commit()
        await session.refresh(draft)
        await session.refresh(stmt)
        await session.refresh(ver)
        return stmt, ver, draft

    async def reject_draft(
        self,
        session: AsyncSession,
        draft_id: uuid.UUID,
        reason: str,
    ) -> StatementDraftModel:
        """Reject an unneeded draft."""
        draft = await session.get(StatementDraftModel, draft_id)
        if not draft:
            raise NotFoundError(f"Statement draft {draft_id} not found")

        if draft.status != "pending_review":
            raise ConflictError(f"Draft is already {draft.status}; cannot reject")

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
                draft = await self.parse_email_source(session, source.id)
                results.append(draft)
            except Exception as e:
                source.parse_status = "failed"
                source.error_message = str(e)
                await session.flush()
                await session.commit()
        return results

