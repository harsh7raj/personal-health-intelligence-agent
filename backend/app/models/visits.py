"""Doctor visits (ROADMAP.md Phase 3, memory.md D37): the recap, its structured note, the
reminders it creates, and questions saved for the next visit."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, String, Text
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base
from app.models.mixins import TimestampMixin


class Visit(TimestampMixin, Base):
    __tablename__ = "visits"
    __table_args__ = (
        CheckConstraint("source in ('typed','voice','recording')", name="ck_visits_source"),
        CheckConstraint("status in ('draft','confirmed')", name="ck_visits_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    doctor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    specialty: Mapped[str | None] = mapped_column(String(128), nullable=True)
    visit_date: Mapped[date] = mapped_column(Date, nullable=False)
    # typed = the patient typed it; voice = the patient's own spoken recap (default);
    # recording = the consultation itself, only with the doctor's agreement.
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="typed")
    transcript: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # reason, discussed[], doctor_said[], medicine_changes[], tests_ordered[], follow_up,
    # watch_for[], questions_next_time[] (memory.md D37)
    structured: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa_text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Reminder(Base):
    """A test or follow-up the doctor asked for, created when a visit note is confirmed."""

    __tablename__ = "reminders"
    __table_args__ = (CheckConstraint("kind in ('test','follow_up')", name="ck_reminders_kind"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    visit_id: Mapped[int | None] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    doctor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=clock.now)


class SavedQuestion(Base):
    """A question for a doctor, saved from a visit note, the report explainer or by hand.
    The pre-visit brief lists the open ones."""

    __tablename__ = "saved_questions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    doctor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # None: any doctor
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")  # visit | report | manual
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=clock.now)
