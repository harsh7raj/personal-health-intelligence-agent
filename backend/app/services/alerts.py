"""Threshold-based alerts (OQ2). Flags only — never diagnoses."""

from sqlalchemy.orm import Session

from app.models.intelligence import Alert

# Human-readable description of the rule behind each alert kind (for the
# "why did this fire" expand). Mirrors the thresholds in check_vital_alert / OQ2.
THRESHOLD_DESCRIPTIONS: dict[str, str] = {
    "critical_bp": "Systolic ≥ 180 or diastolic ≥ 120 mmHg",
    "high_bp": "Systolic ≥ 140 or diastolic ≥ 90 mmHg",
    "high_glucose": "Blood glucose ≥ 200 mg/dL",
    "low_glucose": "Blood glucose ≤ 70 mg/dL",
    "low_spo2": "SpO₂ < 92%",
    "tachycardia": "Heart rate > 100 bpm",
    "bradycardia": "Heart rate < 50 bpm",
}


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


BP_VITAL_TYPE = "blood_pressure"  # vital_type of a combined systolic/diastolic alert


def check_bp_alert(systolic: float, diastolic: float) -> tuple[str, str, str] | None:
    """One (kind, severity, message) for a whole BP reading, or None. The more severe
    half decides the level: "BP 147/92 is above the alert threshold"."""
    hits = [
        r
        for r in (
            check_vital_alert("bp_systolic", systolic),
            check_vital_alert("bp_diastolic", diastolic),
        )
        if r is not None
    ]
    if not hits:
        return None
    if any(kind == "critical_bp" for kind, _, _ in hits):
        return ("critical_bp", "critical", f"BP {systolic:g}/{diastolic:g} is above the critical threshold")
    return ("high_bp", "high", f"BP {systolic:g}/{diastolic:g} is above the alert threshold")


def create_alerts_for_readings(
    db: Session, patient_id: int, readings: list[tuple[str, float, str | None]]
) -> list[dict]:
    created: list[dict] = []
    values = {vt: val for vt, val, _unit in readings}
    if "bp_systolic" in values and "bp_diastolic" in values:
        # Both halves of one reading -> one alert, not one per number.
        res = check_bp_alert(values["bp_systolic"], values["bp_diastolic"])
        if res is not None:
            kind, severity, message = res
            db.add(
                Alert(
                    patient_id=patient_id,
                    kind=kind,
                    message=message,
                    severity=severity,
                    vital_type=BP_VITAL_TYPE,
                )
            )
            created.append({"kind": kind, "vital_type": BP_VITAL_TYPE, "message": message})
        readings = [r for r in readings if r[0] not in ("bp_systolic", "bp_diastolic")]
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
