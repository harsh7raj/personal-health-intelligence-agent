from datetime import date
from typing import Any

from sqlalchemy import BigInteger, Date, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import CreatedAtMixin


class Entry(CreatedAtMixin, Base):
    """Append-only source of truth: what the patient submitted + how Intake parsed it."""

    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)

    memory_logs: Mapped[list["MemoryLog"]] = relationship(back_populates="entry")


class Report(CreatedAtMixin, Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    report_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Report extraction pipeline (Part 1). Lifecycle:
    #   uploaded -> parsing -> parsed | failed
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="uploaded", server_default=text("'uploaded'")
    )
    test_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Raw text pulled from the file (PDF/plain text). Feeds Chroma embedding in Part 2.
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Structured lab values [{test_name, value, unit, reference_range, flag}, ...].
    extracted_values: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # 1-2 sentence plain-language, non-diagnostic takeaway generated at parse time.
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class MemoryLog(CreatedAtMixin, Base):
    """Memory Agent 'writes JSON logs' — audit of each retrieval (context bundle)."""

    __tablename__ = "memory_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("entries.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Denormalized snapshot of the triggering entry (NOT a source of truth).
    raw_entry: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    context_bundle: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    entry: Mapped["Entry | None"] = relationship(back_populates="memory_logs")
