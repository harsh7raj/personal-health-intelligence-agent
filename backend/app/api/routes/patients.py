from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, OwnedPatient
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientOut, PatientUpdate

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientCreate, current_user: CurrentUser, db: DbSession
) -> Patient:
    existing = db.scalar(select(Patient).where(Patient.user_id == current_user.id))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Patient profile already exists for this user",
        )
    patient = Patient(user_id=current_user.id, **payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient: OwnedPatient) -> Patient:
    return patient


@router.put("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient: OwnedPatient, payload: PatientUpdate, db: DbSession
) -> Patient:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    db.commit()
    db.refresh(patient)
    return patient
