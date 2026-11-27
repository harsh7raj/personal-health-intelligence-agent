from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base
from app.models.mixins import CreatedAtMixin, TimestampMixin


class Medication(TimestampMixin, Base):
    __tablename__ = "medications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dose: Mapped[str | None] = mapped_column(String(128), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Structured dose schedule: list of "HH:MM" strings the dose-tracker calendar
    # expands into per-day slots. `frequency` stays as the human-readable label.
    dose_times: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # How many days apart the schedule repeats: 1 = every day, 2 = every other day,
    # 3 = every 3 days, 7 = weekly. The calendar phases doses off the start anchor
    # (started_on, else the row's creation date) so "once every 3 days" lands correctly.
    interval_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    # Free-text grouping ("eye strain", "blood pressure") used to cluster meds in the
    # tracker. Null is rendered as "Other".
    purpose: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Who prescribed it (e.g. "Dr. Rao", "Endocrinology"), to spot clashes between doctors.
    prescriber: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prescriber_specialty: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class DoseLog(CreatedAtMixin, Base):
    """Adherence record — one row per dose the patient marked 'taken'. Distinct from the
    medications table: this accrues over time. A row present means that scheduled slot was
    taken; absence simply means not-yet-taken (no 'missed' rows are ever written, so the
    tracker never frames a gap as a medical judgement)."""

    __tablename__ = "dose_logs"
    __table_args__ = (
        UniqueConstraint(
            "medication_id",
            "scheduled_date",
            "scheduled_time",
            name="uq_dose_log_slot",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    medication_id: Mapped[int] = mapped_column(
        ForeignKey("medications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_time: Mapped[str] = mapped_column(String(5), nullable=False)  # "HH:MM"
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=clock.now, server_default=func.now(), nullable=False
    )


class Problem(TimestampMixin, Base):
    """Active AND resolved problems in one table, discriminated by `status`."""

    __tablename__ = "problems"
    __table_args__ = (
        CheckConstraint(
            "status in ('active','managed','resolved')", name="ck_problems_status"
        ),
        Index("ix_problems_patient_status", "patient_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trend: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set only when status flips to 'resolved'; NULL otherwise.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class VitalReading(CreatedAtMixin, Base):
    """Raw numeric time series; immutable once recorded."""

    __tablename__ = "vital_readings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    vital_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class VitalSummary(TimestampMixin, Base):
    """Computed per-vital summary (rolling-average trend). One row per (patient, vital)."""

    __tablename__ = "vital_summary"
    __table_args__ = (
        UniqueConstraint("patient_id", "vital_type", name="uq_vital_summary_patient_vital"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    vital_type: Mapped[str] = mapped_column(String(64), nullable=False)
    latest: Mapped[float | None] = mapped_column(Float, nullable=True)
    recent_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend: Mapped[str | None] = mapped_column(String(32), nullable=True)


class SymptomCluster(TimestampMixin, Base):
    __tablename__ = "symptom_clusters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    symptoms: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    occurrences: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
