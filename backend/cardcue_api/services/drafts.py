"""Draft service: parsing email sources into drafts, manual review, and atomic confirmation."""

import hashlib
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
from cardcue_api.parsing.model_input import assemble_model_input
from cardcue_api.persistence import (
    Account,
    Card,
    ChangeLog,
    EmailAttachment,
    EmailSource,
    Statement,
    StatementDraftModel,
    DraftTransaction,
    ConfirmedTransaction,
    StatementVersion,
)
from cardcue_api.services.billing import ConflictError, NotFoundError


def detail_coverage_status(*, recognized: int, confirmed: int, flagged: int,
                           expected: int | None, complete: bool,
                           manifest: dict | None) -> str:
    """Do not equate selected model rows with completeness of the original source."""
    if confirmed > recognized or flagged > recognized:
        raise ConflictError("Invalid detail coverage counts")
    if complete:
        if not recognized or confirmed != recognized:
            raise ConflictError("Cannot mark details complete while transactions remain unconfirmed")
        if expected is None or expected != recognized:
            raise ConflictError("Full-source expected transaction count must match recognized rows")
        sources = (manifest or {}).get("entries") or []
        if flagged or not sources or (manifest or {}).get("has_unsupported") or any(
            entry.get("truncated") or entry.get("notes") in ("unsupported_type", "file_adapter_required")
            for entry in sources
        ):
            raise ConflictError("Unresolved rows or source coverage prevent complete details")
        return "complete"
    return "partial" if recognized or expected else "none"


class DraftService:
    """Service for handling statement draft extraction, review, and confirmation."""

    def __init__(self, storage_manager: MailStorageManager | None = None) -> None:
        self.storage_manager = storage_manager or MailStorageManager()
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
            source_manifest=draft_data.source_manifest.model_dump() if draft_data.source_manifest else None,
            detail_status="partial" if draft_data.transactions else "none",
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

        # Never create duplicate drafts for one source on retry/reparse. A
        # confirmed source requires an explicit reviewed correction workflow.
        existing_drafts = list((await session.execute(
            select(StatementDraftModel).where(StatementDraftModel.email_source_id == source_id)
            .order_by(StatementDraftModel.created_at)
        )).scalars().all())
        if existing_drafts:
            if any(d.status == "confirmed" for d in existing_drafts):
                raise ConflictError("Source already confirmed; review the existing statement")
            return existing_drafts

        # V2: preserve body structure and inventory every attachment. No local
        # business-field extraction, PDF text extraction or regular-expression fallback.
        model_input = assemble_model_input(source, self.storage_manager, self.mime_parser)
        if model_input.manifest.has_unsupported:
            raise ValueError("attachment_capability_unavailable")
        email_date_value = source.email_date.date() if hasattr(source.email_date, "date") else source.email_date
        draft_data_list, extractor_name = await self.model_extractor.extract_multi(
            text=model_input.body,
            subject=source.subject,
            sender=source.sender,
            email_date=email_date_value,
            source_manifest=model_input.manifest,
        )
        if not draft_data_list:
            raise ValueError("no_statement_detected")
        fingerprint = getattr(self.model_extractor, "fingerprint", None)
        result_drafts: list[StatementDraftModel] = []
        for draft_data in draft_data_list:
            draft_data.source_manifest = model_input.manifest
            draft_model = self._create_draft_model(
                draft_data=draft_data, source=source, extractor_name=extractor_name,
                fingerprint=fingerprint,
            )
            # A four-digit tail is not an identity. Matching is a manual review
            # decision until account, bank, holder and billing mode are validated.
            session.add(draft_model)
            await session.flush()
            for tx in draft_data.transactions:
                session.add(DraftTransaction(
                    draft_id=draft_model.id, sequence=tx.sequence,
                    transaction_date=tx.transaction_date, posting_date=tx.posting_date,
                    description=tx.description, amount_minor=tx.amount_minor,
                    currency=tx.currency, card_tail=tx.card_tail,
                    transaction_type=tx.transaction_type,
                    evidence=[e.model_dump() for e in tx.evidence],
                    review_flags=tx.review_flags,
                ))
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

        if req.request_id:
            receipt = await session.get(CommandReceipt, req.request_id)
            if receipt:
                # Callers receive a conflict rather than a different return shape.
                raise ConflictError("Request already processed; reload the draft")
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

        if due_date < statement_date:
            raise ConflictError("Due date must not precede statement date")
        account = (await session.execute(select(Account).where(Account.id == account_id).with_for_update())).scalar_one_or_none()
        if not account or account.status != "active":
            raise ConflictError("Active repayment account required")
        if req.expected_account_revision is not None and account.revision != req.expected_account_revision:
            raise ConflictError("账户已被其他操作修改，请重新打开草稿核对还款模式")
        billing_mode = account.billing_mode
        confirm_account_mode = billing_mode is None
        if confirm_account_mode:
            if req.confirmed_billing_mode is None or req.expected_account_revision is None:
                raise ConflictError("请先人工确认账户还款模式：独立还款或合并还款")
            # Confirming an unknown mode must not reinterpret any existing debt.
            history = (await session.execute(select(Statement.id).where(
                Statement.account_id == account_id
            ).limit(1))).first()
            if history:
                raise ConflictError("账户已有正式账单，请先预览并人工核对历史归属，不能在入账时确认还款模式")
            billing_mode = req.confirmed_billing_mode
        elif req.confirmed_billing_mode is not None and req.confirmed_billing_mode != billing_mode:
            raise ConflictError("账户还款模式与本次选择不一致，请重新打开草稿核对；不能在入账时更改已确认模式")
        from cardcue_api.domain.bank_rules import normalise_bank_name
        if draft.bank and normalise_bank_name(draft.bank) != normalise_bank_name(account.bank):
            raise ConflictError("Draft bank conflicts with repayment account")
        active_cards = list((await session.execute(select(Card).where(
            Card.account_id == account_id, Card.status == "active"
        ))).scalars().all())
        if billing_mode == "per_card" and len(active_cards) != 1:
            raise ConflictError("Per-card account must have exactly one active card")
        if card_id is not None and card_id not in {card.id for card in active_cards}:
            raise ConflictError("Selected card does not belong to active account")
        if billing_mode == "per_card":
            if len(set(draft.card_tails or [])) > 1:
                raise ConflictError("Multi-card draft has no separate per-card total; review manually")
            if card_id is not None and card_id != active_cards[0].id:
                raise ConflictError("Per-card account and card do not match")
            card_id = active_cards[0].id
            if draft.card_tails and active_cards[0].tail not in draft.card_tails:
                raise ConflictError("Draft card tail conflicts with selected account")
        if len(set(req.confirm_transaction_ids)) != len(req.confirm_transaction_ids):
            raise ConflictError("Duplicate transaction selection")
        draft_tx = list((await session.execute(select(DraftTransaction).where(
            DraftTransaction.draft_id == draft.id).order_by(DraftTransaction.sequence)
        )).scalars().all())
        selected_ids = set(req.confirm_transaction_ids)
        if not selected_ids.issubset({tx.id for tx in draft_tx}):
            raise ConflictError("Transaction does not belong to this draft")
        selected_tx = [tx for tx in draft_tx if tx.id in selected_ids]
        for tx in selected_tx:
            if tx.amount_minor is None or tx.amount_minor == 0 or tx.currency != currency:
                raise ConflictError("Selected transaction has invalid amount or currency")
            if tx.review_flags:
                raise ConflictError("Selected transaction has unresolved review flags")
            if tx.card_tail and tx.card_tail not in {card.tail for card in active_cards}:
                raise ConflictError("Transaction card tail is not part of selected account")
        flagged_count = sum(bool(tx.review_flags) for tx in draft_tx)
        manifest = draft.source_manifest or {}
        detail_status = detail_coverage_status(
            recognized=len(draft_tx), confirmed=len(selected_tx), flagged=flagged_count,
            expected=req.expected_transaction_count, complete=req.details_complete,
            manifest=draft.source_manifest,
        )
        coverage = dict(expected_transaction_count=req.expected_transaction_count,
                        recognized_transaction_count=len(draft_tx),
                        confirmed_transaction_count=len(selected_tx),
                        flagged_transaction_count=flagged_count)

        receipt_id = req.request_id or uuid.uuid4()
        fingerprint = hashlib.sha256(f"confirm:{draft_id}:{receipt_id}".encode()).hexdigest()

        # Existing statement?
        existing_stmt = (await session.execute(
            select(Statement).where(
                Statement.account_id == account_id,
                Statement.currency == currency,
                Statement.statement_date == statement_date,
            ).with_for_update()
        )).scalar_one_or_none()

        if existing_stmt:
            if not req.expected_statement_version_id:
                raise ConflictError("An existing statement requires explicit version review")
            if existing_stmt.current_version_id != req.expected_statement_version_id:
                raise ConflictError("Statement version changed; reload")
            from cardcue_api.services.billing import BillingService
            paid = await BillingService()._active_paid(session, existing_stmt.id)
            if amount_minor < paid:
                raise ConflictError("Corrected amount is less than recorded repayments")

            stmt = existing_stmt
            max_ver = (await session.execute(
                select(func.max(StatementVersion.version_number)).where(StatementVersion.statement_id == stmt.id)
            )).scalar_one() or 0

            ver = StatementVersion(
                statement_id=stmt.id,
                version_number=max_ver + 1,
                amount_minor=amount_minor,
                minimum_minor=minimum_minor,
                detail_status=detail_status,
                **coverage,
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
                detail_status=detail_status,
                **coverage,
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

        for tx in selected_tx:
            session.add(ConfirmedTransaction(
                statement_version_id=ver.id, statement_id=stmt.id, sequence=tx.sequence,
                transaction_date=tx.transaction_date, posting_date=tx.posting_date,
                description=tx.description, amount_minor=tx.amount_minor,
                currency=tx.currency, card_tail=tx.card_tail,
                transaction_type=tx.transaction_type, source_draft_tx_id=tx.id,
                confirmed_at=datetime.now(timezone.utc), confirmed_by=confirmed_by,
            ))

        if confirm_account_mode:
            account.billing_mode = billing_mode
            account.billing_mode_source = "manual_override"
            account.revision += 1
            account.updated_at = datetime.now(timezone.utc)
            await self._log_change(session, "account", account.id, "update", {
                "id": str(account.id), "bank": account.bank, "alias": account.alias,
                "holder": account.holder, "reference": account.reference,
                "status": account.status, "billing_mode": account.billing_mode,
                "billing_mode_source": account.billing_mode_source,
                "revision": account.revision,
            })

        # Update draft
        draft.detail_status = detail_status
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
            except Exception as exc:
                # A failed batch may have flushed partial drafts/transactions.
                # Roll back before recording the source failure separately.
                await session.rollback()
                source = await session.get(EmailSource, source.id)
                if source is None:
                    continue
                if source.parse_status == "parsed":
                    # Reparse must not damage an already confirmed source.
                    continue
                source.parse_status = "failed"
                known_codes = {"model_not_configured", "attachment_capability_unavailable",
                               "email_source_unavailable", "attachment_unavailable",
                               "input_exceeds_limit_manual_review_required", "no_statement_detected"}
                source.error_message = str(exc) if str(exc) in known_codes else "parse_failed"
                await session.flush()
                await session.commit()
        return results
