"""S3 mail tables: mailboxes, mail_cursors, mail_jobs, email_sources, email_attachments

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- mailboxes ---
    op.create_table(
        "mailboxes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email_address", sa.String(255), nullable=False),
        sa.Column("imap_host", sa.String(255), nullable=False),
        sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"),
        sa.Column("use_ssl", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("encrypted_auth_token", sa.Text(), nullable=False),
        sa.Column("auth_type", sa.String(20), nullable=False, server_default="password"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("check_interval_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_mailboxes_email_address", "mailboxes", ["email_address"], unique=True)

    # --- mail_cursors ---
    op.create_table(
        "mail_cursors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("folder", sa.String(100), nullable=False, server_default="INBOX"),
        sa.Column("uidvalidity", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_uid", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("mailbox_id", "folder", name="uq_mail_cursor_mailbox_folder"),
    )

    # --- mail_jobs ---
    op.create_table(
        "mail_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("emails_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("emails_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("statement_candidates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_mail_jobs_status", "mail_jobs", ["mailbox_id", "status"])

    # --- email_sources ---
    op.create_table(
        "email_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mailbox_id", UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("folder", sa.String(100), nullable=False, server_default="INBOX"),
        sa.Column("uid", sa.BigInteger(), nullable=False),
        sa.Column("uidvalidity", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.String(255), nullable=True),
        sa.Column("subject", sa.Text(), nullable=False, server_default=""),
        sa.Column("sender", sa.String(255), nullable=False, server_default=""),
        sa.Column("recipient", sa.String(255), nullable=False, server_default=""),
        sa.Column("email_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("raw_storage_path", sa.String(500), nullable=True),
        sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_statement_candidate", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("parse_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("mailbox_id", "folder", "uidvalidity", "uid", name="uq_email_source_uid"),
    )
    op.create_index("ix_email_sources_message_id", "email_sources", ["message_id"])
    op.create_index("ix_email_sources_body_hash", "email_sources", ["body_hash"])
    op.create_index("ix_email_sources_candidate", "email_sources", ["is_statement_candidate", "parse_status"])

    # --- email_attachments ---
    op.create_table(
        "email_attachments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email_source_id", UUID(as_uuid=True), sa.ForeignKey("email_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False, server_default="application/octet-stream"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("email_attachments")
    op.drop_table("email_sources")
    op.drop_table("mail_jobs")
    op.drop_table("mail_cursors")
    op.drop_table("mailboxes")
