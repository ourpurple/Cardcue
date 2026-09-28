"""Preserve existing account modes pending a reviewed historical migration.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-28

P0-02: Set billing_mode for existing accounts based on their bank name
using the canonical bank rules. Accounts with unknown banks or ambiguous
modes are left as NULL (pending manual review).
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# Inline bank defaults so the migration is self-contained and won't break
# if domain.bank_rules is refactored later.
_PER_CARD_BANKS = [
    "农行", "中国农业银行", "农业银行",
    "建行", "中国建设银行", "建设银行",
    "中行", "中国银行",
    "中信", "中信银行",
    "邮储", "中国邮政储蓄银行", "邮储银行",
    "工行", "中国工商银行", "工商银行",
    "交行", "交通银行",
    "兴业", "兴业银行",
    "广发", "广发银行",
]

_CONSOLIDATED_BANKS = [
    "浦发", "上海浦东发展银行", "浦发银行",
    "华夏", "华夏银行",
    "招商", "招商银行",
    "民生", "民生银行",
]


def upgrade() -> None:
    # Intentionally leave existing account modes NULL. Historical multi-card
    # ownership and statement versions need an explicit preview/confirmation;
    # bank-name defaults alone cannot validate their historical attribution.
    pass


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrade refused. "
        "Restore a verified backup using the documented recovery procedure."
    )
