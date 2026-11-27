"""suggested_actions dismissed_at

When a suggestion was dismissed, so the same suggestion isn't re-added for a while
(14 days) right after the user dismissed it.

Revision ID: 4c29f0f2bfd0
Revises: f3501e2ab2f5
Create Date: 2026-11-27 23:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c29f0f2bfd0'
down_revision: Union[str, None] = 'f3501e2ab2f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "suggested_actions", sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("suggested_actions", "dismissed_at")
