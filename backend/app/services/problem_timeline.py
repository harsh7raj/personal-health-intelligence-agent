"""Per-problem sub-timeline — one problem's chronological evidence trail assembled
from PRIMARY data only (the matched symptom entries + any vital readings that belong
to it + the problem row's own milestones). Deliberately excludes standalone AI
observations: those are present-tense, whole-history syntheses generated 'now', so
pinning them to a single dated point would falsely backdate them and risk duplication
(the windowing lesson). The problem's *current* trend/frequency is a fact carried on
the problem row and surfaced in the header, not as a dated event."""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.clinical import Problem, VitalReading
from app.models.records import Entry

# Symptom-named problems that also have a numeric series worth showing inline.
# A problem can override/extend this via attributes.vital_types = [...].
_PROBLEM_VITALS: dict[str, list[str]] = {
    "hypertension": ["bp_systolic", "bp_diastolic"],
    "high blood pressure": ["bp_systolic", "bp_diastolic"],
    "elevated blood pressure": ["bp_systolic", "bp_diastolic"],
    "prediabetes": ["blood_glucose"],
    "elevated blood glucose": ["blood_glucose"],
    "high blood glucose": ["blood_glucose"],
}

_VITAL_LABEL = {
    "bp_systolic": "Systolic BP",
    "bp_diastolic": "Diastolic BP",
    "blood_glucose": "Blood glucose",
    "heart_rate": "Heart rate",
    "weight": "Weight",
    "spo2": "SpO₂",
}


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _names_for(problem: Problem) -> set[str]:
    """The set of entry names that belong to this problem: its own name plus any
    aliases recorded on the row (handles e.g. problem 'strep throat' ↔ entry
    'sore throat' where the parsed symptom name differs from the clinical label)."""
    names = {_norm(problem.name)}
    for a in (problem.attributes or {}).get("aliases", []) or []:
        names.add(_norm(a))
    return {n for n in names if n}


def _vital_types_for(problem: Problem) -> list[str]:
    override = (problem.attributes or {}).get("vital_types")
    if isinstance(override, list) and override:
        return [str(v) for v in override]
    return _PROBLEM_VITALS.get(_norm(problem.name), [])


def build_problem_timeline(
    db: Session, patient_id: int, problem_id: int
) -> Optional[dict]:
    problem = db.get(Problem, problem_id)
    if problem is None or problem.patient_id != patient_id:
        return None

    names = _names_for(problem)
    entries: list[Entry] = []
    if names:
        entries = list(
            db.scalars(
                select(Entry)
                .where(
                    Entry.patient_id == patient_id,
                    func.lower(Entry.structured["name"].astext).in_(names),
                )
                .order_by(Entry.created_at)
            ).all()
        )

    vital_types = _vital_types_for(problem)
    readings: list[VitalReading] = []
    if vital_types:
        readings = list(
            db.scalars(
                select(VitalReading)
                .where(
                    VitalReading.patient_id == patient_id,
                    VitalReading.vital_type.in_(vital_types),
                )
                .order_by(VitalReading.recorded_at)
            ).all()
        )

    points: list[dict] = []

    # Episodes (one per matched entry). Tag the earliest as the first report so we
    # don't also emit a redundant first_seen milestone on the same day.
    first_episode_date = entries[0].created_at if entries else None
    for i, e in enumerate(entries):
        sev = (e.structured or {}).get("attributes", {}).get("severity")
        first = i == 0
        points.append(
            {
                "date": e.created_at,
                "kind": "episode",
                "label": ("First reported · " if first else "") + (problem.name),
                "detail": (e.raw_text or "").strip() or None,
                "severity": sev,
                "entry_id": e.id,
            }
        )

    # Vital readings tied to the problem.
    for r in readings:
        lbl = _VITAL_LABEL.get(r.vital_type, r.vital_type.replace("_", " "))
        points.append(
            {
                "date": r.recorded_at,
                "kind": "reading",
                "label": f"{lbl} {r.value:g}{(' ' + r.unit) if r.unit else ''}",
                "detail": None,
                "severity": None,
                "entry_id": None,
            }
        )

    # Derived trend-change marker: the upsert rule flips trend → 'increasing' at the
    # 3rd episode. Surface that same deterministic moment (no new logic, no guessing).
    if len(entries) >= 3:
        third = entries[2]
        points.append(
            {
                "date": third.created_at,
                "kind": "trend_change",
                "label": "Pattern became recurrent (3rd episode → increasing)",
                "detail": None,
                "severity": None,
                "entry_id": None,
            }
        )

    # first_seen milestone — only if nothing already anchors the start (e.g. a
    # managed problem with no symptom entries, like vitamin D deficiency).
    if problem.first_seen is not None and (
        first_episode_date is None or problem.first_seen.date() < first_episode_date.date()
    ):
        points.append(
            {
                "date": problem.first_seen,
                "kind": "first_seen",
                "label": "First recorded",
                "detail": None,
                "severity": None,
                "entry_id": None,
            }
        )

    if problem.status == "resolved" and problem.resolved_at is not None:
        points.append(
            {
                "date": problem.resolved_at,
                "kind": "resolved",
                "label": "Marked resolved",
                "detail": None,
                "severity": None,
                "entry_id": None,
            }
        )

    points.sort(key=lambda p: p["date"])

    return {
        "problem": {
            "id": problem.id,
            "name": problem.name,
            "status": problem.status,
            "severity": problem.severity,
            "frequency": problem.frequency,
            "trend": problem.trend,
            "first_seen": problem.first_seen,
            "last_seen": problem.last_seen,
            "resolved_at": problem.resolved_at,
            "episode_count": int((problem.attributes or {}).get("episode_count", len(entries) or 1)),
        },
        "points": points,
    }
