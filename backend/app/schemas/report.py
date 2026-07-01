from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ReportOut(BaseModel):
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
