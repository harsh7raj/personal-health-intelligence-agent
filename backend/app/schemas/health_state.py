"""PatientHealthState: the in-memory shared state passed between LangGraph nodes.

NOT a DB table and NOT an API request/response DTO. Mirrors memory.md section 3.
A brand-new patient produces a fully-valid empty state.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.enums import OutputType, ProblemStatus


class Identity(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    blood_group: Optional[str] = None
    contact: Optional[str] = None


class MedicalBackground(BaseModel):
    conditions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    family_history: list[str] = Field(default_factory=list)
    surgical_history: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    lifestyle: dict[str, Any] = Field(default_factory=dict)


class ProblemView(BaseModel):
    """One problem; the same shape covers active and resolved (filtered by status)."""

    name: str
    severity: Optional[str] = None
    frequency: Optional[str] = None
    trend: Optional[str] = None  # free-form ('increasing'/'stable'/...) from reasoning
    status: ProblemStatus = ProblemStatus.active
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class VitalSummaryItem(BaseModel):
    vital_type: str
    latest: Optional[float] = None
    recent_avg: Optional[float] = None
    baseline_avg: Optional[float] = None
    delta_pct: Optional[float] = None
    trend: Optional[str] = None


class SymptomClusterItem(BaseModel):
    symptoms: list[str] = Field(default_factory=list)
    occurrences: int = 0
    last_seen: Optional[datetime] = None


class ObservationItem(BaseModel):
    text: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class MissingInfoItem(BaseModel):
    description: str
    related_to: Optional[str] = None


class SuggestedActionItem(BaseModel):
    text: str


class PatientHealthState(BaseModel):
    patient_id: Optional[int] = None

    identity: Identity = Field(default_factory=Identity)
    medical_background: MedicalBackground = Field(default_factory=MedicalBackground)
    active_problems: list[ProblemView] = Field(default_factory=list)
    resolved_problems: list[ProblemView] = Field(default_factory=list)
    vital_summary: dict[str, VitalSummaryItem] = Field(default_factory=dict)
    symptom_clusters: list[SymptomClusterItem] = Field(default_factory=list)
    trend_analysis: list[str] = Field(default_factory=list)
    ai_observations: list[ObservationItem] = Field(default_factory=list)
    missing_information: list[MissingInfoItem] = Field(default_factory=list)
    suggested_next_actions: list[SuggestedActionItem] = Field(default_factory=list)

    # --- pipeline runtime fields (populated as the graph executes) ---
    new_entry: Optional[dict[str, Any]] = None
    context_bundle: Optional[dict[str, Any]] = None
    output_type: Optional[OutputType] = None
    pending_question: Optional[str] = None
