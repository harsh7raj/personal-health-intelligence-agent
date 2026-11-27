from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ReportOut(BaseModel):
    """Full row projection. Returned by the upload endpoint (fresh row, pre-parse)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    filename: str
    path: str
    report_type: Optional[str] = None
    summary: Optional[str] = None
    created_at: datetime

    # Report extraction pipeline (Part 1 + Part 2)
    status: str = "uploaded"
    test_date: Optional[date] = None
    extracted_values: list[dict[str, Any]] = []
    ai_summary: Optional[str] = None
    parse_error: Optional[str] = None


class FlaggedValue(BaseModel):
    """A single non-normal extracted lab value, for the list preview."""

    test_name: str
    value: Optional[str] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    flag: str


class ReportListItem(BaseModel):
    """Trimmed shape for the reports list (GET /reports).

    Carries just enough to render a card: identity, parse status, the AI takeaway,
    and up to 3 flagged (non-normal) values as a preview — not the full value set.
    """

    id: int
    patient_id: int
    filename: str
    status: str
    report_type: Optional[str] = None
    test_date: Optional[date] = None
    ai_summary: Optional[str] = None
    # Non-normal values only (flag != "normal"), capped at 3 for the preview.
    flagged_values: list[FlaggedValue] = []
    # Total flagged count (may exceed the 3 shown above).
    flagged_count: int = 0
    # Values past a critical limit (decided in code, D33): the card shows a banner.
    critical_count: int = 0
    parse_error: Optional[str] = None
    created_at: datetime  # upload date


class ReportDetail(BaseModel):
    """Full detail for one report (GET /reports/{id}): every extracted value + a
    download link to the original file."""

    id: int
    patient_id: int
    filename: str
    report_type: Optional[str] = None
    summary: Optional[str] = None
    status: str
    test_date: Optional[date] = None
    extracted_values: list[dict[str, Any]] = []
    ai_summary: Optional[str] = None
    parse_error: Optional[str] = None
    created_at: datetime
    # Relative API path to download the original uploaded file.
    download_url: str
    # Every value as code sees it: numeric range, flag, how far outside, previous value and
    # change, critical finding, glossary id (Phase 4, memory.md D34).
    values: list[dict[str, Any]] = []
    critical: list[dict[str, Any]] = []


class DoctorQuestions(BaseModel):
    questions: list[str]
    generated_by: str
