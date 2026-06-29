import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, OwnedPatient
from app.models.access import DoctorAccess
from app.schemas.outputs import DoctorAccessCreate, DoctorAccessOut

router = APIRouter(prefix="/patients", tags=["doctor-access"])


@router.post(
    "/{patient_id}/doctor-access",
    response_model=DoctorAccessOut,
    status_code=status.HTTP_201_CREATED,
)
def create_token(
    patient: OwnedPatient, payload: DoctorAccessCreate, db: DbSession
) -> DoctorAccess:
    da = DoctorAccess(
        patient_id=patient.id,
        token=secrets.token_urlsafe(32),
        doctor_label=payload.doctor_label,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=payload.expires_in_days),
    )
    db.add(da)
    db.commit()
    db.refresh(da)
    return da


@router.get("/{patient_id}/doctor-access", response_model=list[DoctorAccessOut])
def list_tokens(patient: OwnedPatient, db: DbSession) -> list[DoctorAccess]:
    return list(
        db.scalars(
            select(DoctorAccess)
            .where(DoctorAccess.patient_id == patient.id)
            .order_by(DoctorAccess.id)
        ).all()
    )


@router.delete(
    "/{patient_id}/doctor-access/{token_id}", status_code=status.HTTP_204_NO_CONTENT
)
def revoke_token(patient: OwnedPatient, token_id: int, db: DbSession) -> None:
    da = db.get(DoctorAccess, token_id)
    if da is None or da.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Token not found"
        )
    da.revoked = True
    db.commit()
