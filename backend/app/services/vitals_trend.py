"""Vital reading extraction + rolling-average trend (decision D1)."""

import re
from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clinical import VitalReading, VitalSummary

# Lab test series reuse the SAME vital_readings/vital_summary tables and the SAME
# rolling-average trend math as vitals — they're just namespaced so they never collide
# with real vital signs. "LDL Cholesterol" -> "lab_ldl_cholesterol".
LAB_PREFIX = "lab_"

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


def lab_vital_type(test_name: str) -> str:
    """Namespace a lab test_name into a vital_type, e.g. 'LDL Cholesterol' ->
    'lab_ldl_cholesterol'. Collapses non-alphanumerics so the same test from different
    reports maps to one series."""
    slug = re.sub(r"[^a-z0-9]+", "_", (test_name or "").lower()).strip("_")
    return f"{LAB_PREFIX}{slug}" if slug else f"{LAB_PREFIX}unknown"


def is_lab_vital_type(vital_type: str) -> bool:
    return (vital_type or "").startswith(LAB_PREFIX)


def record_lab_readings_and_recompute(
    db: Session,
    patient_id: int,
    report_id: int,
    values: list[dict],
    recorded_at: datetime,
) -> list[str]:
    """Treat each numeric lab result as a point in a per-test time series and run the
    SAME rolling-average-delta trend (recompute_summary) used for vitals. Recurring tests
    (e.g. LDL across 3 panels) therefore get a trend exactly like a vital does.

    Idempotent per report: prior readings tagged with this report_id are removed first, so
    re-parsing a report never double-counts. recorded_at should be the report's test_date
    so cross-report ordering is chronological.
    """
    # Drop any prior readings from this same report (idempotent re-parse).
    existing = db.scalars(
        select(VitalReading).where(
            VitalReading.patient_id == patient_id,
            VitalReading.attributes["report_id"].astext == str(report_id),
        )
    ).all()
    for row in existing:
        db.delete(row)
    db.flush()

    affected: set[str] = set()
    for item in values or []:
        val = _to_float(item.get("value"))
        if val is None:
            continue  # non-numeric labs can't trend
        vt = lab_vital_type(item.get("test_name", ""))
        db.add(
            VitalReading(
                patient_id=patient_id,
                vital_type=vt,
                value=val,
                unit=item.get("unit"),
                recorded_at=recorded_at,
                attributes={
                    "report_id": report_id,
                    "test_name": item.get("test_name"),
                    "reference_range": item.get("reference_range"),
                    "flag": item.get("flag"),
                    "source": "report",
                },
            )
        )
        affected.add(vt)
    db.flush()
    for vt in affected:
        recompute_summary(db, patient_id, vt)
    return sorted(affected)
