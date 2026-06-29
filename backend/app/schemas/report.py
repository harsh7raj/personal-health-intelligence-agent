from datetime import datetime
from typing import Optional

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
