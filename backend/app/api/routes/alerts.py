from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, OwnedPatient
from app.models.clinical import VitalReading
from app.models.intelligence import Alert
from app.schemas.outputs import AlertContextOut, AlertOut
from app.services.alerts import (
    BP_VITAL_TYPE,
    THRESHOLD_DESCRIPTIONS,
    check_bp_alert,
    check_vital_alert,
)

router = APIRouter(prefix="/patients", tags=["alerts"])


@router.get("/{patient_id}/alerts", response_model=list[AlertOut])
def list_alerts(
    patient: OwnedPatient, db: DbSession, unacknowledged: bool = False
) -> list[Alert]:
    q = select(Alert).where(Alert.patient_id == patient.id)
    if unacknowledged:
        q = q.where(Alert.acknowledged.is_(False))
    return list(db.scalars(q.order_by(Alert.created_at.desc())).all())


@router.get("/{patient_id}/alerts/{alert_id}/context", response_model=AlertContextOut)
def alert_context(
    patient: OwnedPatient,
    alert_id: int,
    db: DbSession,
    limit: int = Query(5, ge=1, le=20),
) -> dict:
    """Why this alert fired: the recent readings of the alert's vital_type up to when
    it was raised, plus the crossed threshold. Grounds the one-line message in the
    actual numbers."""
    alert = db.get(Alert, alert_id)
    if alert is None or alert.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )

    def recent(vital_type: str) -> list[VitalReading]:
        rows = list(
            db.scalars(
                select(VitalReading)
                .where(
                    VitalReading.patient_id == patient.id,
                    VitalReading.vital_type == vital_type,
                    VitalReading.recorded_at <= alert.created_at,
                )
                .order_by(VitalReading.recorded_at.desc())
                .limit(limit)
            ).all()
        )
        rows.reverse()  # oldest → newest for display
        return rows

    out_readings: list[dict] = []
    if alert.vital_type == BP_VITAL_TYPE:
        # Whole BP readings: each systolic paired with the diastolic taken at the same time.
        diastolic = {r.recorded_at: r.value for r in recent("bp_diastolic")}
        for r in recent("bp_systolic"):
            dia = diastolic.get(r.recorded_at)
            breaches = (
                check_bp_alert(r.value, dia) if dia is not None
                else check_vital_alert(r.vital_type, r.value)
            ) is not None
            out_readings.append({
                "id": r.id,
                "vital_type": BP_VITAL_TYPE,
                "value": r.value,
                "unit": r.unit,
                "recorded_at": r.recorded_at,
                "breaches": breaches,
                "display": f"{r.value:g}/{dia:g}" if dia is not None else f"{r.value:g}",
            })
    elif alert.vital_type:
        out_readings = [
            {
                "id": r.id,
                "vital_type": r.vital_type,
                "value": r.value,
                "unit": r.unit,
                "recorded_at": r.recorded_at,
                "breaches": check_vital_alert(r.vital_type, r.value) is not None,
            }
            for r in recent(alert.vital_type)
        ]
    return {
        "alert": alert,
        "threshold": THRESHOLD_DESCRIPTIONS.get(alert.kind),
        "readings": out_readings,
    }


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
