"""Cached drug reference data (Phase 5, memory.md D35) and the latest medication safety run.

Labels and classes are public reference data, cached per ingredient with a fetched date so the
app (and the demo) works offline once warmed. Not patient-owned, except MedCheckRun."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db.base import Base


class DrugLabel(Base):
    """One openFDA label per ingredient: the sections the safety checks read."""

    __tablename__ = "drug_labels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingredient: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    found: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    set_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # {"drug_interactions": "...", "warnings": "...", "contraindications": "...",
    #  "adverse_reactions": "...", "dosage_and_administration": "..."}
    sections: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=clock.now)


class DrugClassInfo(Base):
    """RxClass classes for one ingredient: pharmacologic class (EPC), mechanism (MOA), ATC."""

    __tablename__ = "drug_classes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingredient: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # [{"id": "N0000175566", "name": "Calcium Channel Blocker", "type": "EPC"}, ...]
    classes: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=clock.now)


class MedCheckRun(Base):
    """The latest safety check for a patient. `signature` hashes everything the check reads
    from the patient's medicines; a different signature means the stored result is stale."""

    __tablename__ = "med_check_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=clock.now)
