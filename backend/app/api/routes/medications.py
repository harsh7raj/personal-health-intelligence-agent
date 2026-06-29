from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, OwnedPatient
from app.models.clinical import Medication
from app.schemas.clinical_io import MedicationCreate, MedicationOut, MedicationUpdate

router = APIRouter(prefix="/patients", tags=["medications"])


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
    patient: OwnedPatient, payload: MedicationCreate, db: DbSession
) -> Medication:
    med = Medication(patient_id=patient.id, **payload.model_dump())
    db.add(med)
    db.commit()
    db.refresh(med)
    return med


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
    patient: OwnedPatient, med_id: int, payload: MedicationUpdate, db: DbSession
) -> Medication:
    med = _get_med(db, patient.id, med_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(med, field, value)
    db.commit()
    db.refresh(med)
    return med


@router.delete(
    "/{patient_id}/medications/{med_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_medication(patient: OwnedPatient, med_id: int, db: DbSession) -> None:
    med = _get_med(db, patient.id, med_id)
    db.delete(med)
    db.commit()
