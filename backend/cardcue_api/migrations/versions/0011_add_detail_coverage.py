"""Track audited transaction coverage on immutable statement versions.

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("statement_versions", sa.Column("expected_transaction_count", sa.Integer(), nullable=True))
    op.add_column("statement_versions", sa.Column("recognized_transaction_count", sa.Integer(), nullable=True))
    op.add_column("statement_versions", sa.Column("confirmed_transaction_count", sa.Integer(), nullable=True))
    op.add_column("statement_versions", sa.Column("flagged_transaction_count", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_version_expected_tx_count", "statement_versions", "expected_transaction_count IS NULL OR expected_transaction_count > 0")
    op.create_check_constraint("ck_version_recognized_tx_count", "statement_versions", "recognized_transaction_count >= 0")
    op.create_check_constraint("ck_version_confirmed_tx_count", "statement_versions", "confirmed_transaction_count >= 0 AND confirmed_transaction_count <= recognized_transaction_count")
    op.create_check_constraint("ck_version_flagged_tx_count", "statement_versions", "flagged_transaction_count >= 0 AND flagged_transaction_count <= recognized_transaction_count")
    # Existing versions retain unknown counts and their original status; no completion proof is invented.


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade refused: transaction coverage history must be retained")
