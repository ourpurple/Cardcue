"""S1 device auth and change log tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- devices ---
    op.create_table(
        "devices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False, comment="User-visible device name"),
        sa.Column("token_hash", sa.String(128), nullable=False, comment="SHA-256 of bearer token"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("paired_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_device_token_hash", "devices", ["token_hash"], unique=True)

    # --- change_log ---
    op.execute("CREATE SEQUENCE IF NOT EXISTS change_seq START 1 INCREMENT 1")
    op.create_table(
        "change_log",
        sa.Column("id", sa.BigInteger, primary_key=True, server_default=sa.text("nextval('change_seq')")),
        sa.Column("entity_type", sa.String(50), nullable=False, comment="account / card / statement / version / payment"),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(20), nullable=False, comment="create / update / delete"),
        sa.Column("snapshot", JSONB, nullable=True, comment="Entity state after change"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_changelog_entity", "change_log", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_index("ix_changelog_entity", table_name="change_log")
    op.drop_table("change_log")
    op.execute("DROP SEQUENCE IF EXISTS change_seq")
    op.drop_index("ix_device_token_hash", table_name="devices")
    op.drop_table("devices")
