"""Web administration, non-destructive upgrade from 0004."""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create tables and indices if they do not exist
    op.execute("""
CREATE TABLE IF NOT EXISTS admin_jobs (
    id UUID NOT NULL, 
    kind VARCHAR(30) NOT NULL, 
    target_id UUID NOT NULL, 
    payload JSON NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    attempts INTEGER NOT NULL, 
    cancel_requested BOOLEAN NOT NULL, 
    lease_owner VARCHAR(64), 
    lease_until TIMESTAMP WITH TIME ZONE, 
    result JSON, 
    error_code VARCHAR(100), 
    available_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id)
)
""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_jobs_status ON admin_jobs (status)")

    op.execute("""
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID NOT NULL, 
    username VARCHAR(100) NOT NULL, 
    password_hash TEXT NOT NULL, 
    active BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (username)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS audit_events (
    id UUID NOT NULL, 
    actor VARCHAR(100) NOT NULL, 
    action VARCHAR(80) NOT NULL, 
    target VARCHAR(100), 
    detail JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS command_receipts (
    id UUID NOT NULL, 
    fingerprint VARCHAR(64) NOT NULL, 
    result JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS login_guards (
    key VARCHAR(64) NOT NULL, 
    attempts INTEGER NOT NULL, 
    reset_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (key)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS model_profiles (
    id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS pairing_codes (
    code_hash VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    used_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (code_hash)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS runtime_settings (
    key VARCHAR(50) NOT NULL, 
    value JSON NOT NULL, 
    PRIMARY KEY (key)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS model_revisions (
    id UUID NOT NULL, 
    profile_id UUID NOT NULL, 
    number INTEGER NOT NULL, 
    parameters JSON NOT NULL, 
    encrypted_key TEXT NOT NULL, 
    tested_at TIMESTAMP WITH TIME ZONE, 
    test_error VARCHAR(100), 
    revoked BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_model_revision UNIQUE (profile_id, number), 
    FOREIGN KEY(profile_id) REFERENCES model_profiles (id)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS web_sessions (
    token_hash VARCHAR(64) NOT NULL, 
    admin_id UUID NOT NULL, 
    csrf_token VARCHAR(100) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    verified_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (token_hash), 
    FOREIGN KEY(admin_id) REFERENCES admin_users (id)
)
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS model_calls (
    id UUID NOT NULL, 
    revision_id UUID NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    usage JSON, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(revision_id) REFERENCES model_revisions (id)
)
""")

    # 2. Add columns if not exist
    op.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE cards ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE statement_drafts ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS settings_json JSON NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS tested_revision INTEGER")
    op.execute("ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS pending_config JSON")
    op.execute("ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS pending_token TEXT")
    op.execute("ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMP WITH TIME ZONE")

    # 3. Insert default settings idempotently
    op.execute("INSERT INTO runtime_settings (key, value) VALUES ('model', '{}') ON CONFLICT (key) DO NOTHING")


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade refused. Restore a verified backup using the documented recovery procedure.")
