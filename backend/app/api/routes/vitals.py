
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.api.deps import DbSession, OwnedPatient
from app.models.clinical import VitalReading, VitalSummary
from app.schemas.clinical_io import VitalCreate, VitalOut
from app.schemas.outputs import VitalSummaryOut
from app.services.alerts import create_alerts_for_readings
from app.services.vitals_trend import recompute_summary

router = APIRouter(prefix="/patients", tags=["vitals"])


def _get_vital(db: Session, patient_id: int, vital_id: int) -> VitalReading:
    vital = db.get(VitalReading, vital_id)
    if vital is None or vital.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vital reading not found"
        )
    return vital


@router.post(
    "/{patient_id}/vitals",
    response_model=VitalOut,
    status_code=status.HTTP_201_CREATED,
)
def create_vital(
    patient: OwnedPatient, payload: VitalCreate, db: DbSession
) -> VitalReading:
    data = payload.model_dump()
    if data.get("recorded_at") is None:
        data["recorded_at"] = clock.now()
    vital = VitalReading(patient_id=patient.id, **data)
    db.add(vital)
    db.commit()
    db.refresh(vital)
    # Keep the vital summary + alerts consistent with intake-driven readings (Phase 8).
    recompute_summary(db, patient.id, vital.vital_type)
    create_alerts_for_readings(db, patient.id, [(vital.vital_type, vital.value, vital.unit)])
    db.commit()
    return vital


@router.get("/{patient_id}/vitals", response_model=list[VitalOut])
def list_vitals(patient: OwnedPatient, db: DbSession) -> list[VitalReading]:
    return list(
        db.scalars(
            select(VitalReading)
            .where(VitalReading.patient_id == patient.id)
            .order_by(VitalReading.recorded_at)
        ).all()
    )


# Declared before /{vital_id} so the literal "summary" matches first.
@router.get("/{patient_id}/vitals/summary", response_model=list[VitalSummaryOut])
def vitals_summary(patient: OwnedPatient, db: DbSession) -> list[VitalSummary]:
    return list(
        db.scalars(
            select(VitalSummary).where(VitalSummary.patient_id == patient.id)
        ).all()
    )


@router.get("/{patient_id}/vitals/{vital_id}", response_model=VitalOut)
def get_vital(patient: OwnedPatient, vital_id: int, db: DbSession) -> VitalReading:
    return _get_vital(db, patient.id, vital_id)


@router.delete(
    "/{patient_id}/vitals/{vital_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_vital(patient: OwnedPatient, vital_id: int, db: DbSession) -> None:
    vital = _get_vital(db, patient.id, vital_id)
    db.delete(vital)
    db.commit()
