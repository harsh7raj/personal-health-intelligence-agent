import logging
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, OwnedPatient
from app.core import clock
from app.models.clinical import DoseLog, Medication, MedicationEvent
from app.schemas.clinical_io import (
    DoseMark,
    MedicationCreate,
    MedicationEventOut,
    MedicationOut,
    MedicationUpdate,
)
from app.schemas.outputs import MedCalendarOut, MedIntelOut
from app.db.session import SessionLocal
from app.services import brand_generic, med_events, med_safety, rxnorm
from app.services.med_intel import build_medication_intelligence
from app.services.med_schedule import (
    build_med_calendar,
    default_dose_times,
    normalize_dose_times,
    normalize_time,
    parse_interval_days,
)

router = APIRouter(prefix="/patients", tags=["medications"])
logger = logging.getLogger(__name__)


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


def _recheck(patient_id: int) -> None:
    """Re-run the safety checks after a medicine changes (background; never raises)."""
    try:
        with SessionLocal() as db:
            med_safety.latest(db, patient_id)
    except Exception:
        logger.warning("background medication safety check failed for %s", patient_id, exc_info=True)


def _set_ingredients(med: Medication, ingredients: list[str] | None, brand_name: str | None) -> None:
    """User-confirmed ingredients win (checked against RxNorm); otherwise RxNorm's own match.
    An AI suggestion only ever arrives here after the user confirmed it."""
    if ingredients:
        med.ingredients = brand_generic.confirmed_ingredients(ingredients)
        med.brand_name = brand_name or med.name
        return
    found = rxnorm.lookup(med.name)
    if found["status"] == "found":
        med.ingredients = found["ingredients"]


def _canonical_slot_time(value: str) -> str:
    """Normalize an incoming dose-slot time to canonical "HH:MM" (rejecting garbage with
    422), so it always matches the generated slot and fits dose_logs.scheduled_time."""
    slot = normalize_time(value)
    if slot is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid dose time: {value!r}",
        )
    return slot


def _get_med(db: Session, patient_id: int, med_id: int) -> Medication:
    med = db.get(Medication, med_id)
    if med is None or med.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Medication not found"
        )
    return med


@router.post(
    "/{patient_id}/medications",
    response_model=MedicationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_medication(
    patient: OwnedPatient, payload: MedicationCreate, db: DbSession, background: BackgroundTasks
) -> Medication:
    data = payload.model_dump(exclude={"ingredients", "brand_name"})
    # Canonicalize times to "HH:MM"; fall back to a default schedule from the free-text
    # frequency when none parse, so the tracker always has slots that fit dose_logs.
    data["dose_times"] = normalize_dose_times(data.get("dose_times")) or default_dose_times(
        data.get("frequency")
    )
    # Honor an explicit interval, else derive it from the frequency ("every 3 days" → 3),
    # so multi-day schedules land on the right days instead of every day.
    data["interval_days"] = data.get("interval_days") or parse_interval_days(data.get("frequency"))
    med = Medication(patient_id=patient.id, **data)
    _set_ingredients(med, payload.ingredients, payload.brand_name)
    db.add(med)
    db.flush()
    if med.active:
        med_events.record(db, med, "start", event_date=med.started_on, new_dose=med.dose)
    db.commit()
    db.refresh(med)
    background.add_task(_recheck, patient.id)
    return med


# Literal paths are declared BEFORE "/{med_id}" so they win.
@router.post("/{patient_id}/medications/resolve-name")
def resolve_medicine_name(patient: OwnedPatient, payload: NameIn) -> dict[str, Any]:
    """What's in a medicine: RxNorm's ingredients, or an AI suggestion to CONFIRM (never saved
    until the user sends the ingredients back with the medicine)."""
    return brand_generic.resolve(payload.name)


@router.get("/{patient_id}/medications/safety")
def medication_safety(patient: OwnedPatient, db: DbSession, refresh: bool = False) -> dict[str, Any]:
    """Three-level pair checks plus patient-aware checks (memory.md D36). Reuses the stored
    result unless something changed; refresh=true re-runs it (and re-reads cached labels)."""
    return med_safety.latest(db, patient.id, force=refresh)


@router.post("/{patient_id}/medications/check")
def check_medicine(patient: OwnedPatient, payload: NameIn, db: DbSession) -> dict[str, Any]:
    """'Can I take X with my medicines?' with the same three levels. Never an all-clear."""
    out = med_safety.check_new_medicine(db, patient.id, payload.name)
    db.commit()  # keep any labels/classes fetched along the way
    return out


# Declared BEFORE "/{med_id}" so the literal "intelligence" segment wins.
@router.get("/{patient_id}/medications/intelligence", response_model=MedIntelOut)
def medication_intelligence(patient: OwnedPatient, db: DbSession) -> dict:
    """Per-drug reference info (curated, sourced) + drug-drug interaction flags from
    the local DDInter 2.0 table. No LLM; interactions are surfaced only when present
    in the dataset, never inferred."""
    return build_medication_intelligence(db, patient.id)


# Declared BEFORE "/{med_id}" so the literal "calendar" segment wins.
@router.get("/{patient_id}/medications/calendar", response_model=MedCalendarOut)
def medication_calendar(patient: OwnedPatient, db: DbSession) -> dict:
    """Rolling 14-day dose tracker: scheduled doses (from each med's dose_times) grouped
    by purpose, overlaid with the patient's adherence record. Tracking only — no advice."""
    return build_med_calendar(db, patient.id)


# Declared BEFORE "/{med_id}" so the literal "events" segment wins.
@router.get("/{patient_id}/medications/events", response_model=list[MedicationEventOut])
def medication_events(
    patient: OwnedPatient,
    db: DbSession,
    days: int | None = Query(None, ge=1, le=3650),
    medication_id: int | None = None,
) -> list[MedicationEvent]:
    """Start / stop / dose-change history, newest first. Optional window and medicine."""
    q = select(MedicationEvent).where(MedicationEvent.patient_id == patient.id)
    if days is not None:
        q = q.where(MedicationEvent.event_date >= clock.today() - timedelta(days=days))
    if medication_id is not None:
        q = q.where(MedicationEvent.medication_id == medication_id)
    return list(
        db.scalars(q.order_by(MedicationEvent.event_date.desc(), MedicationEvent.id.desc())).all()
    )


@router.post(
    "/{patient_id}/medications/{med_id}/doses",
    status_code=status.HTTP_204_NO_CONTENT,
)
def mark_dose_taken(
    patient: OwnedPatient, med_id: int, payload: DoseMark, db: DbSession
) -> None:
    """Record a scheduled dose as taken. Idempotent on (med, date, time) — re-marking an
    already-taken slot is a no-op."""
    _get_med(db, patient.id, med_id)  # ownership guard
    slot_time = _canonical_slot_time(payload.scheduled_time)
    existing = db.scalar(
        select(DoseLog).where(
            DoseLog.medication_id == med_id,
            DoseLog.scheduled_date == payload.scheduled_date,
            DoseLog.scheduled_time == slot_time,
        )
    )
    if existing is None:
        db.add(
            DoseLog(
                patient_id=patient.id,
                medication_id=med_id,
                scheduled_date=payload.scheduled_date,
                scheduled_time=slot_time,
            )
        )
        db.commit()


@router.delete(
    "/{patient_id}/medications/{med_id}/doses",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unmark_dose(
    patient: OwnedPatient, med_id: int, payload: DoseMark, db: DbSession
) -> None:
    """Undo a 'taken' mark for a scheduled dose. No-op if it was not marked."""
    _get_med(db, patient.id, med_id)  # ownership guard
    slot_time = _canonical_slot_time(payload.scheduled_time)
    row = db.scalar(
        select(DoseLog).where(
            DoseLog.medication_id == med_id,
            DoseLog.scheduled_date == payload.scheduled_date,
            DoseLog.scheduled_time == slot_time,
        )
    )
    if row is not None:
        db.delete(row)
        db.commit()


@router.get("/{patient_id}/medications", response_model=list[MedicationOut])
def list_medications(patient: OwnedPatient, db: DbSession) -> list[Medication]:
    return list(
        db.scalars(
            select(Medication)
            .where(Medication.patient_id == patient.id)
            .order_by(Medication.id)
        ).all()
    )


@router.get("/{patient_id}/medications/{med_id}", response_model=MedicationOut)
def get_medication(patient: OwnedPatient, med_id: int, db: DbSession) -> Medication:
    return _get_med(db, patient.id, med_id)


@router.put("/{patient_id}/medications/{med_id}", response_model=MedicationOut)
def update_medication(
    patient: OwnedPatient, med_id: int, payload: MedicationUpdate, db: DbSession,
    background: BackgroundTasks,
) -> Medication:
    med = _get_med(db, patient.id, med_id)
    before = med_events.snapshot(med)
    if payload.ingredients is not None or (payload.name and payload.name != med.name):
        if payload.name:
            med.name = payload.name
        _set_ingredients(med, payload.ingredients, payload.brand_name)
    for field, value in payload.model_dump(
        exclude_unset=True, exclude={"changed_on", "ingredients", "brand_name"}
    ).items():
        if field == "dose_times" and value is not None:
            value = normalize_dose_times(value)
        setattr(med, field, value)
    # Keep the history: a dose change / stop / restart becomes a dated event.
    med_events.record_changes(db, med, before, event_date=payload.changed_on)
    db.commit()
    db.refresh(med)
    background.add_task(_recheck, patient.id)
    return med


@router.delete(
    "/{patient_id}/medications/{med_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_medication(patient: OwnedPatient, med_id: int, db: DbSession) -> None:
    med = _get_med(db, patient.id, med_id)
    db.delete(med)
    db.commit()
