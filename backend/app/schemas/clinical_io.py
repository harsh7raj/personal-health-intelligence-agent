from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# --- Medications ---
class MedicationCreate(BaseModel):
    name: str
    dose: Optional[str] = None
    frequency: Optional[str] = None
    dose_times: list[str] = Field(default_factory=list)
    interval_days: Optional[int] = None
    purpose: Optional[str] = None
    prescriber: Optional[str] = None  # doctor's name
    prescriber_specialty: Optional[str] = None
    started_on: Optional[date] = None
    active: bool = True
    attributes: dict[str, Any] = Field(default_factory=dict)


class MedicationUpdate(BaseModel):
    name: Optional[str] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    dose_times: Optional[list[str]] = None
    interval_days: Optional[int] = None
    purpose: Optional[str] = None
    prescriber: Optional[str] = None  # doctor's name
    prescriber_specialty: Optional[str] = None
    started_on: Optional[date] = None
    active: Optional[bool] = None
    attributes: Optional[dict[str, Any]] = None
    # When this change happened (dose change / stop / restart); defaults to today.
    changed_on: Optional[date] = None


class MedicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    name: str
    dose: Optional[str] = None
    frequency: Optional[str] = None
    dose_times: list[str] = Field(default_factory=list)
    interval_days: int = 1
    purpose: Optional[str] = None
    prescriber: Optional[str] = None  # doctor's name
    prescriber_specialty: Optional[str] = None
    started_on: Optional[date] = None
    active: bool
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class MedicationEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    medication_id: int
    medication_name: str
    event_type: str  # start | stop | dose_change
    event_date: date
    old_dose: Optional[str] = None
    new_dose: Optional[str] = None
    prescriber: Optional[str] = None
    source: str  # manual | visit_note
    note: Optional[str] = None
    created_at: datetime


# --- Dose log (adherence tracking) ---
class DoseMark(BaseModel):
    scheduled_date: date
    scheduled_time: str  # "HH:MM"


# --- Vitals (raw readings) ---
class VitalCreate(BaseModel):
    vital_type: str
    value: float
    unit: Optional[str] = None
    recorded_at: Optional[datetime] = None  # defaults to now() if omitted
    attributes: dict[str, Any] = Field(default_factory=dict)


class VitalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    vital_type: str
    value: float
    unit: Optional[str] = None
    recorded_at: datetime
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# --- Symptoms (stored as entries, type='symptom') ---
class SymptomCreate(BaseModel):
    raw_text: str
    structured: dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = "api"


class SymptomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    type: str
    raw_text: Optional[str] = None
    structured: dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None
    created_at: datetime  # when it was logged
    occurred_at: datetime  # when it happened (backdated)


# --- Entries (full append-only history, all types) ---
class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    type: str
    raw_text: Optional[str] = None
    structured: dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None
    created_at: datetime  # when it was logged
    occurred_at: datetime  # when it happened (backdated)
