"""report extraction fields (status, test_date, extracted text/values, parse_error)

Revision ID: c3e4f5a6b7d8
Revises: b2d3f4a5c6e7
Create Date: 2026-07-01 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c3e4f5a6b7d8'
down_revision: Union[str, None] = 'b2d3f4a5c6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'reports',
        sa.Column(
            'status',
            sa.String(length=32),
            server_default=sa.text("'uploaded'"),
            nullable=False,
        ),
    )
    op.add_column('reports', sa.Column('test_date', sa.Date(), nullable=True))
    op.add_column('reports', sa.Column('extracted_text', sa.Text(), nullable=True))
    op.add_column(
        'reports',
        sa.Column(
            'extracted_values',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column('reports', sa.Column('parse_error', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('reports', 'parse_error')
    op.drop_column('reports', 'extracted_values')
    op.drop_column('reports', 'extracted_text')
    op.drop_column('reports', 'test_date')
    op.drop_column('reports', 'status')
