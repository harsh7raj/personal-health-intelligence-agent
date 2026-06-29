from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, OwnedPatient
from app.models.intelligence import Alert
from app.schemas.outputs import AlertOut

router = APIRouter(prefix="/patients", tags=["alerts"])


@router.get("/{patient_id}/alerts", response_model=list[AlertOut])
def list_alerts(
    patient: OwnedPatient, db: DbSession, unacknowledged: bool = False
) -> list[Alert]:
    q = select(Alert).where(Alert.patient_id == patient.id)
    if unacknowledged:
        q = q.where(Alert.acknowledged.is_(False))
    return list(db.scalars(q.order_by(Alert.created_at.desc())).all())


@router.post("/{patient_id}/alerts/{alert_id}/ack", response_model=AlertOut)
def ack_alert(patient: OwnedPatient, alert_id: int, db: DbSession) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None or alert.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )
    alert.acknowledged = True
    db.commit()
    db.refresh(alert)
    return alert
