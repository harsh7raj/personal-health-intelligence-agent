from datetime import date as date_type
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


# ---------- Timeline point detail (assembled full context for a date window) ----------


class TimelineEntryDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    raw_text: Optional[str] = None
    structured: dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None
    created_at: datetime


class TimelineVitalDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vital_type: str
    value: float
    unit: Optional[str] = None
    recorded_at: datetime


class TimelineObservationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    created_at: datetime


class TimelineAlertDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    message: str
    severity: Optional[str] = None
    vital_type: Optional[str] = None
    created_at: datetime


class TimelineDetailOut(BaseModel):
    date: date_type
    window_days: int
    entries: list[TimelineEntryDetail]
    vital_readings: list[TimelineVitalDetail]
    observations: list[TimelineObservationDetail]
    alerts: list[TimelineAlertDetail]


# ---------- Alert context (which readings/threshold triggered an alert) ----------


class AlertContextReading(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vital_type: str
    value: float
    unit: Optional[str] = None
    recorded_at: datetime
    breaches: bool = False  # True if this reading on its own crosses the threshold


class AlertContextOut(BaseModel):
    alert: AlertOut
    threshold: Optional[str] = None  # human-readable description of the crossed rule
    readings: list[AlertContextReading]


# ---------- Per-problem sub-timeline ----------


class ProblemTimelineProblem(BaseModel):
    id: int
    name: str
    status: str
    severity: Optional[str] = None
    frequency: Optional[str] = None
    trend: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    episode_count: int


class ProblemTimelinePoint(BaseModel):
    date: datetime
    kind: str  # first_seen | episode | reading | trend_change | resolved
    label: str
    detail: Optional[str] = None
    severity: Optional[str] = None
    entry_id: Optional[int] = None


class ProblemTimelineOut(BaseModel):
    problem: ProblemTimelineProblem
    points: list[ProblemTimelinePoint]
