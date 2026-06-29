from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, OwnedPatient
from app.models.records import Entry
from app.schemas.clinical_io import SymptomCreate, SymptomOut

# Symptoms are persisted as entries (type='symptom'). entries is append-only,
# so there is no PUT — only create / read / delete.
router = APIRouter(prefix="/patients", tags=["symptoms"])

SYMPTOM = "symptom"


def _get_symptom(db: Session, patient_id: int, symptom_id: int) -> Entry:
    entry = db.get(Entry, symptom_id)
    if entry is None or entry.patient_id != patient_id or entry.type != SYMPTOM:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Symptom not found"
        )
    return entry


@router.post(
    "/{patient_id}/symptoms",
    response_model=SymptomOut,
    status_code=status.HTTP_201_CREATED,
)
def create_symptom(
    patient: OwnedPatient, payload: SymptomCreate, db: DbSession
) -> Entry:
    entry = Entry(
        patient_id=patient.id,
        type=SYMPTOM,
        raw_text=payload.raw_text,
        structured=payload.structured,
        source=payload.source,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/{patient_id}/symptoms", response_model=list[SymptomOut])
def list_symptoms(patient: OwnedPatient, db: DbSession) -> list[Entry]:
    return list(
        db.scalars(
            select(Entry)
            .where(Entry.patient_id == patient.id, Entry.type == SYMPTOM)
            .order_by(Entry.created_at)
        ).all()
    )


@router.get("/{patient_id}/symptoms/{symptom_id}", response_model=SymptomOut)
def get_symptom(patient: OwnedPatient, symptom_id: int, db: DbSession) -> Entry:
    return _get_symptom(db, patient.id, symptom_id)


@router.delete(
    "/{patient_id}/symptoms/{symptom_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_symptom(patient: OwnedPatient, symptom_id: int, db: DbSession) -> None:
    entry = _get_symptom(db, patient.id, symptom_id)
    db.delete(entry)
    db.commit()
