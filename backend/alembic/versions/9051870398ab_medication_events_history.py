"""medication_events history

Start / stop / dose-change history per medicine (the medications row only holds the
current state, so dose changes used to overwrite the old dose).

Revision ID: 9051870398ab
Revises: 3e19f634c1f5
Create Date: 2026-11-27 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9051870398ab'
down_revision: Union[str, None] = '3e19f634c1f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "medication_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("patient_id", sa.BigInteger(), nullable=False),
        sa.Column("medication_id", sa.BigInteger(), nullable=False),
        sa.Column("medication_name", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("old_dose", sa.String(length=128), nullable=True),
        sa.Column("new_dose", sa.String(length=128), nullable=True),
        sa.Column("prescriber", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "event_type in ('start','stop','dose_change')", name="ck_med_events_type"
        ),
        sa.CheckConstraint("source in ('manual','visit_note')", name="ck_med_events_source"),
        sa.ForeignKeyConstraint(["medication_id"], ["medications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_med_events_patient_date", "medication_events", ["patient_id", "event_date"])
    op.create_index(
        op.f("ix_medication_events_medication_id"), "medication_events", ["medication_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_medication_events_medication_id"), table_name="medication_events")
    op.drop_index("ix_med_events_patient_date", table_name="medication_events")
    op.drop_table("medication_events")
