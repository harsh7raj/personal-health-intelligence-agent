"""medication prescriber

Who prescribed each medicine (doctor name and specialty), so duplicates and clashes
between different doctors can be detected (Phase 5).

Revision ID: 3e19f634c1f5
Revises: 4c29f0f2bfd0
Create Date: 2026-11-27 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e19f634c1f5'
down_revision: Union[str, None] = '4c29f0f2bfd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("medications", sa.Column("prescriber", sa.String(length=255), nullable=True))
    op.add_column(
        "medications", sa.Column("prescriber_specialty", sa.String(length=128), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("medications", "prescriber_specialty")
    op.drop_column("medications", "prescriber")
