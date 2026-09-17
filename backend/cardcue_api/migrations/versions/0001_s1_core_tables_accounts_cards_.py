"""S1 core tables: accounts, cards, statements, statement_versions, payments

Revision ID: 0001
Revises: 
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- accounts ---
    op.create_table(
        "accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("bank", sa.String(100), nullable=False),
        sa.Column("alias", sa.String(100), nullable=True, comment="User-chosen display name"),
        sa.Column("reference", sa.String(100), nullable=True, comment="Account reference from bank email"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- cards ---
    op.create_table(
        "cards",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("tail", sa.String(10), nullable=False, comment="Last 4 digits; NOT a unique key"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- statement_versions (created before statements to allow FK) ---
    op.create_table(
        "statement_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("statement_id", UUID(as_uuid=True), nullable=False),  # FK added after statements
        sa.Column("version_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("amount_minor", sa.BigInteger, nullable=False, comment="Total bill in minor currency units"),
        sa.Column("minimum_minor", sa.BigInteger, nullable=True, comment="Minimum payment in minor units"),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual", comment="manual / email / model"),
        sa.Column("reason", sa.String(200), nullable=True, comment="Why this version was created"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.String(100), nullable=True, comment="device id or system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("amount_minor >= 0", name="ck_version_amount_nonneg"),
        sa.CheckConstraint("minimum_minor IS NULL OR minimum_minor >= 0", name="ck_version_minimum_nonneg"),
        sa.CheckConstraint("minimum_minor IS NULL OR minimum_minor <= amount_minor", name="ck_version_minimum_le_amount"),
    )

    # --- statements ---
    op.create_table(
        "statements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, comment="ISO 4217"),
        sa.Column("statement_date", sa.Date, nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("current_version_id", UUID(as_uuid=True), sa.ForeignKey("statement_versions.id"), nullable=True,
                  comment="Points to the currently effective version"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("account_id", "currency", "statement_date", name="uq_statement_account_currency_period"),
        sa.CheckConstraint("due_date >= statement_date", name="ck_statement_due_after_start"),
    )

    # Now add the FK from statement_versions.statement_id -> statements.id
    op.create_foreign_key(
        "fk_version_statement", "statement_versions", "statements",
        ["statement_id"], ["id"],
    )
    op.create_unique_constraint("uq_version_per_statement", "statement_versions", ["statement_id", "version_number"])

    # --- payments ---
    op.create_table(
        "payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("statement_id", UUID(as_uuid=True), sa.ForeignKey("statements.id"), nullable=False),
        sa.Column("amount_minor", sa.BigInteger, nullable=False, comment="Payment in minor units"),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(200), nullable=True),
        sa.CheckConstraint("amount_minor > 0", name="ck_payment_amount_positive"),
    )
    op.create_index("ix_payment_statement", "payments", ["statement_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_statement", table_name="payments")
    op.drop_table("payments")
    op.drop_constraint("fk_version_statement", "statement_versions", type_="foreignkey")
    op.drop_constraint("uq_version_per_statement", "statement_versions", type_="unique")
    op.drop_table("statements")
    op.drop_table("statement_versions")
    op.drop_table("cards")
    op.drop_table("accounts")
