"""entries occurred_at (backdating)

When a logged thing actually happened ("I had a migraine yesterday"), separate from
created_at (when it was typed). Existing rows are backfilled with created_at.

Revision ID: f3501e2ab2f5
Revises: d4f5a6b7c8e9
Create Date: 2026-11-27 22:12:02.199394

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3501e2ab2f5'
down_revision: Union[str, None] = 'd4f5a6b7c8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("entries", sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE entries SET occurred_at = created_at")
    op.alter_column(
        "entries", "occurred_at", nullable=False, server_default=sa.text("now()")
    )
    op.create_index("ix_entries_patient_occurred", "entries", ["patient_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_entries_patient_occurred", table_name="entries")
    op.drop_column("entries", "occurred_at")
