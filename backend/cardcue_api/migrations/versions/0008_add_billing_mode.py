"""Add billing_mode and billing_mode_source to accounts table.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-28

P0-01: Unified billing accounts, rules & migration design.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE accounts "
        "ADD COLUMN IF NOT EXISTS billing_mode VARCHAR(20)"
    )
    op.execute(
        "ALTER TABLE accounts "
        "ADD COLUMN IF NOT EXISTS billing_mode_source VARCHAR(20)"
    )
    # Add CHECK constraints for valid values
    op.execute(
        "ALTER TABLE accounts "
        "ADD CONSTRAINT ck_account_billing_mode "
        "CHECK (billing_mode IS NULL OR billing_mode IN ('per_card', 'consolidated'))"
    )
    op.execute(
        "ALTER TABLE accounts "
        "ADD CONSTRAINT ck_account_billing_mode_source "
        "CHECK (billing_mode_source IS NULL OR billing_mode_source IN ('bank_default', 'manual_override'))"
    )
    # If billing_mode is set, source must also be set (and vice versa)
    op.execute(
        "ALTER TABLE accounts "
        "ADD CONSTRAINT ck_account_billing_mode_source_consistent "
        "CHECK ((billing_mode IS NULL AND billing_mode_source IS NULL) "
        "OR (billing_mode IS NOT NULL AND billing_mode_source IS NOT NULL))"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrade refused. "
        "Restore a verified backup using the documented recovery procedure."
    )
