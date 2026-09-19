"""S4 draft tables: statement_drafts

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "statement_drafts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email_source_id", UUID(as_uuid=True), sa.ForeignKey("email_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_review"),
        sa.Column("bank", sa.String(100), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=True),
        sa.Column("minimum_minor", sa.BigInteger(), nullable=True),
        sa.Column("statement_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("account_reference", sa.String(100), nullable=True),
        sa.Column("card_tails", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("review_reasons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("matched_account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("matched_card_id", UUID(as_uuid=True), sa.ForeignKey("cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmed_version_id", UUID(as_uuid=True), sa.ForeignKey("statement_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rejection_reason", sa.String(255), nullable=True),
        sa.Column("extractor_name", sa.String(50), nullable=False, server_default="rule"),
        sa.Column("model_fingerprint", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_statement_drafts_status", "statement_drafts", ["status"])
    op.create_index("ix_statement_drafts_email_source_id", "statement_drafts", ["email_source_id"])
    op.create_index("ix_statement_drafts_matched_account_id", "statement_drafts", ["matched_account_id"])


def downgrade() -> None:
    op.drop_index("ix_statement_drafts_matched_account_id", table_name="statement_drafts")
    op.drop_index("ix_statement_drafts_email_source_id", table_name="statement_drafts")
    op.drop_index("ix_statement_drafts_status", table_name="statement_drafts")
    op.drop_table("statement_drafts")
