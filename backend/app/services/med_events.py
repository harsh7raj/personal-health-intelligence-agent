"""Medication history (memory.md D20): every start, stop and dose change as a dated row,
so the assistant and the side-effect check can line symptoms up against changes."""

from datetime import date

from sqlalchemy.orm import Session

from app.core import clock
from app.models.clinical import Medication, MedicationEvent


def record(
    db: Session,
    med: Medication,
    event_type: str,
    *,
    event_date: date | None = None,
    old_dose: str | None = None,
    new_dose: str | None = None,
    source: str = "manual",
    note: str | None = None,
) -> MedicationEvent:
    event = MedicationEvent(
        patient_id=med.patient_id,
        medication_id=med.id,
        medication_name=med.name,
        event_type=event_type,
        event_date=event_date or clock.today(),
        old_dose=old_dose,
        new_dose=new_dose,
        prescriber=med.prescriber,
        source=source,
        note=note,
    )
    db.add(event)
    return event


def snapshot(med: Medication) -> dict:
    """The fields whose changes become events, taken before an update."""
    return {"dose": med.dose, "active": med.active}


def record_changes(
    db: Session, med: Medication, before: dict, *, event_date: date | None = None,
    source: str = "manual",
) -> list[MedicationEvent]:
    """Events implied by an update, comparing `before` (snapshot()) with the med now."""
    if before["active"] and not med.active:
        return [record(db, med, "stop", event_date=event_date, old_dose=before["dose"], source=source)]
    if not before["active"] and med.active:
        return [record(db, med, "start", event_date=event_date, new_dose=med.dose, source=source)]
    if med.active and (before["dose"] or "") != (med.dose or ""):
        return [
            record(
                db, med, "dose_change", event_date=event_date,
                old_dose=before["dose"], new_dose=med.dose, source=source,
            )
        ]
    return []
