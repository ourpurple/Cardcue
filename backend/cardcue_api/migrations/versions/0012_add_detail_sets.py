"""Independent, immutable detail snapshots for later completion (0012)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "detail_sets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("statement_version_id", UUID(as_uuid=True), sa.ForeignKey("statement_versions.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source_draft_id", UUID(as_uuid=True), sa.ForeignKey("statement_drafts.id"), nullable=True),
        sa.Column("detail_status", sa.String(20), nullable=False),
        sa.Column("expected_transaction_count", sa.Integer(), nullable=True),
        sa.Column("recognized_transaction_count", sa.Integer(), nullable=False),
        sa.Column("confirmed_transaction_count", sa.Integer(), nullable=False),
        sa.Column("flagged_transaction_count", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_by", sa.String(100), nullable=False),
        sa.UniqueConstraint("statement_version_id", "revision", name="uq_detail_set_revision"),
        sa.CheckConstraint("revision > 0", name="ck_detail_set_revision_positive"),
        sa.CheckConstraint("recognized_transaction_count >= 0 AND confirmed_transaction_count >= 0 AND flagged_transaction_count >= 0", name="ck_detail_set_counts_nonnegative"),
        sa.CheckConstraint("expected_transaction_count IS NULL OR expected_transaction_count > 0", name="ck_detail_set_expected_positive"),
        sa.CheckConstraint("confirmed_transaction_count <= recognized_transaction_count AND flagged_transaction_count <= recognized_transaction_count", name="ck_detail_set_counts_bounded"),
    )
    op.create_table(
        "detail_set_transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("detail_set_id", UUID(as_uuid=True), sa.ForeignKey("detail_sets.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("posting_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("card_tail", sa.String(4), nullable=True),
        sa.Column("transaction_type", sa.String(20), nullable=True),
        sa.Column("source_draft_tx_id", UUID(as_uuid=True), sa.ForeignKey("draft_transactions.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_by", sa.String(100), nullable=True),
        sa.UniqueConstraint("detail_set_id", "sequence", name="uq_detail_set_tx_sequence"),
        sa.CheckConstraint("amount_minor != 0", name="ck_detail_set_tx_amount_nonzero"),
    )
    op.create_index("ix_detail_set_tx_set", "detail_set_transactions", ["detail_set_id"])


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade refused: reviewed detail history must be retained")

