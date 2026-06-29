from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SnapshotOut(BaseModel):
    patient_id: int
    active_problems: list[dict]
    recent_changes: list[str]
    observations: list[str]
    missing_information: list[str]
    suggested_next_actions: list[str]


class StoryOut(BaseModel):
    story: str
    generated_by: str  # "llm" | "fallback"


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    message: str
    severity: Optional[str] = None
    vital_type: Optional[str] = None
    acknowledged: bool
    created_at: datetime


class DoctorAccessCreate(BaseModel):
    doctor_label: Optional[str] = None
    expires_in_days: int = 7


class DoctorAccessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    token: str
    doctor_label: Optional[str] = None
    expires_at: datetime
    revoked: bool
    created_at: datetime


class ProblemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    severity: Optional[str] = None
    frequency: Optional[str] = None
    trend: Optional[str] = None
    status: str
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class VitalSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vital_type: str
    latest: Optional[float] = None
    recent_avg: Optional[float] = None
    baseline_avg: Optional[float] = None
    delta_pct: Optional[float] = None
    trend: Optional[str] = None


class ObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    created_at: datetime
