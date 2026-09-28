"""Add transaction detail tables: draft_transactions, confirmed_transactions.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-28

P2: Transaction-level line items for both draft and confirmed statements.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("statement_drafts", sa.Column("source_manifest", sa.JSON(), nullable=True))
    op.add_column("statement_drafts", sa.Column("detail_status", sa.String(20), nullable=False, server_default="none"))
    op.add_column("statement_versions", sa.Column("detail_status", sa.String(20), nullable=False, server_default="none"))
    # -- draft_transactions ---------------------------------------------------
    op.create_table(
        "draft_transactions",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "draft_id", UUID(as_uuid=True),
            sa.ForeignKey("statement_drafts.id"), nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("posting_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("card_tail", sa.String(4), nullable=True),
        sa.Column("transaction_type", sa.String(20), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("review_flags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_unique_constraint(
        "uq_draft_tx_sequence", "draft_transactions", ["draft_id", "sequence"],
    )
    op.create_check_constraint(
        "ck_draft_tx_amount_nonzero", "draft_transactions",
        "amount_minor IS NULL OR amount_minor != 0",
    )
    op.create_index("ix_draft_tx_draft", "draft_transactions", ["draft_id"])

    # -- confirmed_transactions -----------------------------------------------
    op.create_table(
        "confirmed_transactions",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "statement_version_id", UUID(as_uuid=True),
            sa.ForeignKey("statement_versions.id"), nullable=False,
        ),
        sa.Column(
            "statement_id", UUID(as_uuid=True),
            sa.ForeignKey("statements.id"), nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("posting_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("card_tail", sa.String(4), nullable=True),
        sa.Column("transaction_type", sa.String(20), nullable=True),
        sa.Column(
            "source_draft_tx_id", UUID(as_uuid=True),
            sa.ForeignKey("draft_transactions.id"), nullable=True,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_by", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_unique_constraint(
        "uq_confirmed_tx_sequence", "confirmed_transactions",
        ["statement_version_id", "sequence"],
    )
    op.create_check_constraint(
        "ck_confirmed_tx_amount_nonzero", "confirmed_transactions",
        "amount_minor != 0",
    )
    op.create_index(
        "ix_confirmed_tx_stmt", "confirmed_transactions", ["statement_id"],
    )
    op.create_index(
        "ix_confirmed_tx_ver", "confirmed_transactions", ["statement_version_id"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrade refused: transaction history must be retained. "
        "Restore a verified backup using the documented recovery procedure."
    )
