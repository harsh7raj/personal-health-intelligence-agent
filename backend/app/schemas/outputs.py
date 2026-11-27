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
    occurred_at: datetime


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


# ---------- Medication intelligence (reference info + sourced interactions) ----------


class DrugReference(BaseModel):
    used_for: str
    timing: str
    considerations: str
    source: str
    provenance: str = "medlineplus"  # "medlineplus" | "ai"


class MedIntelMedication(BaseModel):
    id: int
    name: str
    dose: Optional[str] = None
    normalized: str
    reference: Optional[DrugReference] = None


class MedIntelInteraction(BaseModel):
    drug_a: str
    drug_b: str
    status: str  # "known" | "none_known"
    level: Optional[str] = None  # Major|Moderate|Minor|Unknown (when known)
    source: str
    advice: Optional[str] = None
    note: Optional[str] = None


class MedIntelOut(BaseModel):
    medications: list[MedIntelMedication]
    interactions: list[MedIntelInteraction]
    known_interaction_count: int
    pairs_checked: int
    disclaimer: str
    interaction_source: str
    reference_source_url: str


# ---------- Medication dose tracker (2-week rolling calendar) ----------


class DoseSlot(BaseModel):
    medication_id: int
    name: str
    dose: Optional[str] = None
    time: str  # "HH:MM"
    timing: Optional[str] = None  # reused per-drug reference guidance ("with food")
    taken: bool
    markable: bool  # past/today slots can be marked; future slots cannot


class CalendarDay(BaseModel):
    date: date_type
    is_today: bool
    is_future: bool
    slots: list[DoseSlot]


class CalendarMedication(BaseModel):
    id: int
    name: str
    dose: Optional[str] = None
    purpose: str
    color_index: int


class CalendarGroup(BaseModel):
    purpose: str
    medications: list[CalendarMedication]


class MedCalendarOut(BaseModel):
    start_date: date_type
    end_date: date_type
    today: date_type
    days: list[CalendarDay]
    groups: list[CalendarGroup]
    medication_count: int
    disclaimer: str
