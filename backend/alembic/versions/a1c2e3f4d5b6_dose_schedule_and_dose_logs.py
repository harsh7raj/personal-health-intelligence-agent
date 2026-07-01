"""dose schedule columns + dose_logs adherence table

Revision ID: a1c2e3f4d5b6
Revises: 977d1af8bd80
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1c2e3f4d5b6'
down_revision: Union[str, None] = '977d1af8bd80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'medications',
        sa.Column(
            'dose_times',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        'medications',
        sa.Column('purpose', sa.String(length=128), nullable=True),
    )
    op.create_table(
        'dose_logs',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('patient_id', sa.BigInteger(), nullable=False),
        sa.Column('medication_id', sa.BigInteger(), nullable=False),
        sa.Column('scheduled_date', sa.Date(), nullable=False),
        sa.Column('scheduled_time', sa.String(length=5), nullable=False),
        sa.Column(
            'taken_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['medication_id'], ['medications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'medication_id', 'scheduled_date', 'scheduled_time', name='uq_dose_log_slot'
        ),
    )
    op.create_index('ix_dose_logs_patient_id', 'dose_logs', ['patient_id'])
    op.create_index('ix_dose_logs_medication_id', 'dose_logs', ['medication_id'])


def downgrade() -> None:
    op.drop_index('ix_dose_logs_medication_id', table_name='dose_logs')
    op.drop_index('ix_dose_logs_patient_id', table_name='dose_logs')
    op.drop_table('dose_logs')
    op.drop_column('medications', 'purpose')
    op.drop_column('medications', 'dose_times')
