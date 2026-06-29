"""Vital reading extraction + rolling-average trend (decision D1)."""

import re
from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clinical import VitalReading, VitalSummary

# Matches "130 over 85" or "130/85" (two 2-3 digit numbers).
_BP_RE = re.compile(r"(\d{2,3})\s*(?:/|over)\s*(\d{2,3})")

_VITAL_MAP = {
    "heart rate": "heart_rate",
    "pulse": "heart_rate",
    "hr": "heart_rate",
    "weight": "weight",
    "body weight": "weight",
    "blood glucose": "blood_glucose",
    "glucose": "blood_glucose",
    "blood sugar": "blood_glucose",
    "sugar": "blood_glucose",
    "spo2": "spo2",
    "oxygen": "spo2",
    "oxygen saturation": "spo2",
    "o2": "spo2",
    "o2 sat": "spo2",
    "temperature": "temperature",
    "temp": "temperature",
}


def _map_vital_type(name: str) -> str:
    n = (name or "").lower().strip()
    if n in _VITAL_MAP:
        return _VITAL_MAP[n]
    for k, v in _VITAL_MAP.items():
        if k in n:
            return v
    return n.replace(" ", "_") or "vital"


def _to_float(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def extract_readings(new_entry: dict) -> list[tuple[str, float, str | None]]:
    """Pull numeric (vital_type, value, unit) tuples from a parsed vital entry.
    Blood pressure yields two readings (bp_systolic + bp_diastolic)."""
    s = new_entry.get("structured", {}) or {}
    attrs = s.get("attributes", {}) or {}
    name = (new_entry.get("name") or s.get("name") or "").lower()
    raw = new_entry.get("raw_text") or ""

    sys_v = _to_float(attrs.get("systolic"))
    dia_v = _to_float(attrs.get("diastolic"))
    is_bp = "blood pressure" in name or name.strip() == "bp" or (
        sys_v is not None and dia_v is not None
    )
    if is_bp:
        # The LLM is inconsistent on BP; recover both numbers from the raw text
        # ("X over Y" / "X/Y") when attributes are incomplete.
        if sys_v is None or dia_v is None:
            m = _BP_RE.search(raw)
            if m:
                sys_v = sys_v if sys_v is not None else _to_float(m.group(1))
                dia_v = dia_v if dia_v is not None else _to_float(m.group(2))
        if sys_v is None:
            sys_v = _to_float(s.get("value"))  # lone number is the systolic
        bp: list[tuple[str, float, str | None]] = []
        if sys_v is not None:
            bp.append(("bp_systolic", sys_v, "mmHg"))
        if dia_v is not None:
            bp.append(("bp_diastolic", dia_v, "mmHg"))
        return bp  # never fall through to a generic 'blood_pressure' series

    value = _to_float(s.get("value"))
    if value is None:
        value = _to_float(attrs.get("value"))
    if value is None:
        return []
    unit = s.get("unit") or attrs.get("unit")
    return [(_map_vital_type(name), value, unit)]


def _trend(delta_pct: float | None) -> str:
    if delta_pct is None:
        return "stable"
    if delta_pct > 0.05:
        return "rising"
    if delta_pct < -0.05:
        return "falling"
    return "stable"


def recompute_summary(db: Session, patient_id: int, vital_type: str) -> None:
    vals = list(
        db.scalars(
            select(VitalReading.value)
            .where(
                VitalReading.patient_id == patient_id,
                VitalReading.vital_type == vital_type,
            )
            .order_by(VitalReading.recorded_at)
        ).all()
    )
    if not vals:
        return
    recent = vals[-3:]
    baseline = vals[-6:-3] if len(vals) >= 6 else vals[:-3]
    recent_avg = mean(recent)
    baseline_avg = mean(baseline) if baseline else None
    delta = (recent_avg - baseline_avg) / baseline_avg if baseline_avg else None

    summary = db.scalar(
        select(VitalSummary).where(
            VitalSummary.patient_id == patient_id,
            VitalSummary.vital_type == vital_type,
        )
    )
    if summary is None:
        summary = VitalSummary(patient_id=patient_id, vital_type=vital_type)
        db.add(summary)
    summary.latest = vals[-1]
    summary.recent_avg = recent_avg
    summary.baseline_avg = baseline_avg
    summary.delta_pct = delta
    summary.trend = _trend(delta)


def record_vital_and_recompute(
    db: Session, patient_id: int, new_entry: dict
) -> list[tuple[str, float, str | None]]:
    readings = extract_readings(new_entry)
    now = datetime.now(timezone.utc)
    for vt, val, unit in readings:
        db.add(
            VitalReading(
                patient_id=patient_id,
                vital_type=vt,
                value=val,
                unit=unit,
                recorded_at=now,
            )
        )
    db.flush()
    for vt in {r[0] for r in readings}:
        recompute_summary(db, patient_id, vt)
    return readings
