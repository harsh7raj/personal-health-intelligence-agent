from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, OwnedPatient
from app.models.patient import MedicalBackground
from app.schemas.patient import BackgroundOut, BackgroundUpdate

# /history is a documented alias for /background (same medical_background row).
router = APIRouter(prefix="/patients", tags=["background"])


def _get_background(db: Session, patient_id: int) -> MedicalBackground | None:
    return db.scalar(
        select(MedicalBackground).where(MedicalBackground.patient_id == patient_id)
    )


@router.get("/{patient_id}/background", response_model=BackgroundOut)
@router.get("/{patient_id}/history", response_model=BackgroundOut)
def get_background(patient: OwnedPatient, db: DbSession) -> BackgroundOut:
    bg = _get_background(db, patient.id)
    if bg is None:
        # No background recorded yet — return an empty, unsaved view.
        return BackgroundOut(patient_id=patient.id)
    return BackgroundOut.model_validate(bg)


@router.put("/{patient_id}/background", response_model=BackgroundOut)
@router.put("/{patient_id}/history", response_model=BackgroundOut)
def upsert_background(
    patient: OwnedPatient, payload: BackgroundUpdate, db: DbSession
) -> BackgroundOut:
    bg = _get_background(db, patient.id)
    if bg is None:
        bg = MedicalBackground(patient_id=patient.id)
        db.add(bg)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(bg, field, value)
    db.commit()
    db.refresh(bg)
    return BackgroundOut.model_validate(bg)
