"""Threshold-based alerts (OQ2). Flags only — never diagnoses."""

from sqlalchemy.orm import Session

from app.models.intelligence import Alert


def check_vital_alert(vital_type: str, value: float) -> tuple[str, str, str] | None:
    """Return (kind, severity, message) if a threshold is crossed, else None."""
    v = value
    if vital_type == "bp_systolic":
        if v >= 180:
            return ("critical_bp", "critical", f"Systolic BP {v:g} is very high")
        if v >= 140:
            return ("high_bp", "high", f"Systolic BP {v:g} is elevated")
    elif vital_type == "bp_diastolic":
        if v >= 120:
            return ("critical_bp", "critical", f"Diastolic BP {v:g} is very high")
        if v >= 90:
            return ("high_bp", "high", f"Diastolic BP {v:g} is elevated")
    elif vital_type == "blood_glucose":
        if v >= 200:
            return ("high_glucose", "high", f"Blood glucose {v:g} is high")
        if v <= 70:
            return ("low_glucose", "high", f"Blood glucose {v:g} is low")
    elif vital_type == "spo2":
        if v < 92:
            return ("low_spo2", "high", f"SpO2 {v:g}% is low")
    elif vital_type == "heart_rate":
        if v > 100:
            return ("tachycardia", "moderate", f"Heart rate {v:g} is elevated")
        if v < 50:
            return ("bradycardia", "moderate", f"Heart rate {v:g} is low")
    return None


def create_alerts_for_readings(
    db: Session, patient_id: int, readings: list[tuple[str, float, str | None]]
) -> list[dict]:
    created: list[dict] = []
    for vt, val, _unit in readings:
        res = check_vital_alert(vt, val)
        if res is None:
            continue
        kind, severity, message = res
        db.add(
            Alert(
                patient_id=patient_id,
                kind=kind,
                message=message,
                severity=severity,
                vital_type=vt,
            )
        )
        created.append({"kind": kind, "vital_type": vt, "message": message})
    return created
