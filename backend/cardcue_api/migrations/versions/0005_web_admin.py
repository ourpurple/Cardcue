"""Web administration, non-destructive upgrade from 0004."""
from alembic import op
import sqlalchemy as sa
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

def upgrade():
    op.execute('\nCREATE TABLE admin_jobs (\n\tid UUID NOT NULL, \n\tkind VARCHAR(30) NOT NULL, \n\ttarget_id UUID NOT NULL, \n\tpayload JSON NOT NULL, \n\tstatus VARCHAR(30) NOT NULL, \n\tattempts INTEGER NOT NULL, \n\tcancel_requested BOOLEAN NOT NULL, \n\tlease_owner VARCHAR(64), \n\tlease_until TIMESTAMP WITH TIME ZONE, \n\tresult JSON, \n\terror_code VARCHAR(100), \n\tavailable_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id)\n)\n\n')
    op.execute('CREATE INDEX ix_admin_jobs_status ON admin_jobs (status)')
    op.execute('\nCREATE TABLE admin_users (\n\tid UUID NOT NULL, \n\tusername VARCHAR(100) NOT NULL, \n\tpassword_hash TEXT NOT NULL, \n\tactive BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (username)\n)\n\n')
    op.execute('\nCREATE TABLE audit_events (\n\tid UUID NOT NULL, \n\tactor VARCHAR(100) NOT NULL, \n\taction VARCHAR(80) NOT NULL, \n\ttarget VARCHAR(100), \n\tdetail JSON NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n')
    op.execute('\nCREATE TABLE command_receipts (\n\tid UUID NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\tresult JSON NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n')
    op.execute('\nCREATE TABLE login_guards (\n\tkey VARCHAR(64) NOT NULL, \n\tattempts INTEGER NOT NULL, \n\treset_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (key)\n)\n\n')
    op.execute('\nCREATE TABLE model_profiles (\n\tid UUID NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n')
    op.execute('\nCREATE TABLE pairing_codes (\n\tcode_hash VARCHAR(64) NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tused_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (code_hash)\n)\n\n')
    op.execute('\nCREATE TABLE runtime_settings (\n\tkey VARCHAR(50) NOT NULL, \n\tvalue JSON NOT NULL, \n\tPRIMARY KEY (key)\n)\n\n')
    op.execute('\nCREATE TABLE model_revisions (\n\tid UUID NOT NULL, \n\tprofile_id UUID NOT NULL, \n\tnumber INTEGER NOT NULL, \n\tparameters JSON NOT NULL, \n\tencrypted_key TEXT NOT NULL, \n\ttested_at TIMESTAMP WITH TIME ZONE, \n\ttest_error VARCHAR(100), \n\trevoked BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_model_revision UNIQUE (profile_id, number), \n\tFOREIGN KEY(profile_id) REFERENCES model_profiles (id)\n)\n\n')
    op.execute('\nCREATE TABLE web_sessions (\n\ttoken_hash VARCHAR(64) NOT NULL, \n\tadmin_id UUID NOT NULL, \n\tcsrf_token VARCHAR(100) NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tverified_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (token_hash), \n\tFOREIGN KEY(admin_id) REFERENCES admin_users (id)\n)\n\n')
    op.execute('\nCREATE TABLE model_calls (\n\tid UUID NOT NULL, \n\trevision_id UUID NOT NULL, \n\tstatus VARCHAR(30) NOT NULL, \n\tusage JSON, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(revision_id) REFERENCES model_revisions (id)\n)\n\n')
    op.add_column("accounts", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("cards", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("statement_drafts", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("mailboxes", sa.Column("settings_json", sa.JSON(), nullable=False, server_default='{}'))
    op.add_column("mailboxes", sa.Column("revision", sa.Integer(), nullable=False, server_default='1'))
    op.add_column("mailboxes", sa.Column("tested_revision", sa.Integer(), nullable=True))
    op.add_column("mailboxes", sa.Column("pending_config", sa.JSON(), nullable=True))
    op.add_column("mailboxes", sa.Column("pending_token", sa.Text(), nullable=True))
    op.add_column("mailboxes", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("INSERT INTO runtime_settings (key, value) VALUES ('model', '{}')")

def downgrade():
    raise RuntimeError("Destructive downgrade refused. Restore a verified backup using the documented recovery procedure.")
