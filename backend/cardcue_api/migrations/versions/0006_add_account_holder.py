"""Add holder column to accounts table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS holder VARCHAR(50)"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrade refused. Restore a verified backup using the documented recovery procedure."
    )
