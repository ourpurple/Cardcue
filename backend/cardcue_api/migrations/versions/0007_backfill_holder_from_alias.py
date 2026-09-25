"""Back-fill holder from alias parenthesised name.

Populates the `holder` column for existing accounts where it is NULL
but the alias contains a Chinese name in parentheses, e.g. "(牛鋆辉)".
This is a one-time data-fixup; it never overwrites a non-NULL holder.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-25
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extract name from parenthesised suffix like "信用卡 (张三)" or "信用卡(张三)"
    # Uses PostgreSQL regexp_replace to pull out the value inside the last pair
    # of parentheses (Chinese full-width or ASCII half-width).
    op.execute(r"""
        UPDATE accounts
        SET holder = trim(both from sub.extracted)
        FROM (
            SELECT id,
                   coalesce(
                       substring(alias FROM '\(([^)]+)\)\s*$'),
                       substring(alias FROM '\uff08([^\uff09]+)\uff09\s*$')
                   ) AS extracted
            FROM accounts
            WHERE holder IS NULL
              AND alias IS NOT NULL
        ) sub
        WHERE accounts.id = sub.id
          AND sub.extracted IS NOT NULL
          AND length(trim(both from sub.extracted)) BETWEEN 2 AND 10
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrade refused. Restore a verified backup using the documented recovery procedure."
    )
