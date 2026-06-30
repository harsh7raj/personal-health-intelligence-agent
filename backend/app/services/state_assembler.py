"""Single source of assembled health state. Snapshot, story, PDF and the doctor
/shared views all read from assemble_state() so they can never drift apart."""

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clinical import Problem, SymptomCluster, VitalSummary
from app.models.intelligence import MissingInformation, Observation, SuggestedAction
from app.models.patient import MedicalBackground, Patient
from app.schemas.health_state import (
    Identity,
    MissingInfoItem,
    ObservationItem,
    PatientHealthState,
    ProblemView,
    SuggestedActionItem,
    SymptomClusterItem,
    VitalSummaryItem,
)
from app.schemas.health_state import MedicalBackground as MBSchema

_WORD = re.compile(r"[a-z0-9]+")
_ACTIVE = ("active", "managed")

_VITAL_LABEL = {
    "bp_systolic": "BP systolic",
    "bp_diastolic": "BP diastolic",
    "heart_rate": "Heart rate",
    "weight": "Weight",
    "blood_glucose": "Blood glucose",
    "spo2": "SpO2",
    "temperature": "Temperature",
}


def _tokens(text: str | None) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedupe_observations(observations: list[Observation], limit: int = 5) -> list[Observation]:
    """Drop near-duplicate observations (Jaccard >= 0.6) and cap to `limit` most recent."""
    kept: list[Observation] = []
    kept_tokens: list[set[str]] = []
    for obs in observations:  # caller passes newest-first
        toks = _tokens(obs.text)
        if any(_jaccard(toks, kt) >= 0.6 for kt in kept_tokens):
            continue
        kept.append(obs)
        kept_tokens.append(toks)
        if len(kept) >= limit:
            break
    return kept


def _problem_view(p: Problem) -> ProblemView:
    return ProblemView(
        name=p.name,
        severity=p.severity,
        frequency=p.frequency,
        trend=p.trend,
        status=p.status,
        first_seen=p.first_seen,
        last_seen=p.last_seen,
        resolved_at=p.resolved_at,
        attributes=p.attributes or {},
    )


def assemble_state(
    db: Session, patient_id: int, obs_limit: int = 5
) -> PatientHealthState:
    patient = db.get(Patient, patient_id)
    bg = db.scalar(
        select(MedicalBackground).where(MedicalBackground.patient_id == patient_id)
    )
    problems = list(
        db.scalars(select(Problem).where(Problem.patient_id == patient_id)).all()
    )
    vitals = list(
        db.scalars(select(VitalSummary).where(VitalSummary.patient_id == patient_id)).all()
    )
    clusters = list(
        db.scalars(
            select(SymptomCluster).where(SymptomCluster.patient_id == patient_id)
        ).all()
    )
    obs_all = list(
        db.scalars(
            select(Observation)
            .where(Observation.patient_id == patient_id)
            .order_by(Observation.created_at.desc())
        ).all()
    )
    obs = dedupe_observations(obs_all, limit=obs_limit)
    missing = list(
        db.scalars(
            select(MissingInformation).where(
                MissingInformation.patient_id == patient_id,
                MissingInformation.resolved.is_(False),
            )
        ).all()
    )
    actions = list(
        db.scalars(
            select(SuggestedAction).where(
                SuggestedAction.patient_id == patient_id,
                SuggestedAction.dismissed.is_(False),
            )
        ).all()
    )

    identity = Identity(
        name=patient.name if patient else None,
        age=patient.age if patient else None,
        sex=patient.sex if patient else None,
        height=patient.height if patient else None,
        weight=patient.weight if patient else None,
        blood_group=patient.blood_group if patient else None,
        contact=patient.contact if patient else None,
    )

    return PatientHealthState(
        patient_id=patient_id,
        identity=identity,
        medical_background=MBSchema(
            conditions=list(bg.conditions) if bg else [],
            allergies=list(bg.allergies) if bg else [],
            family_history=list(bg.family_history) if bg else [],
            surgical_history=list(bg.surgical_history) if bg else [],
            lifestyle=dict(bg.lifestyle) if bg else {},
        ),
        active_problems=[_problem_view(p) for p in problems if p.status in _ACTIVE],
        resolved_problems=[_problem_view(p) for p in problems if p.status == "resolved"],
        vital_summary={
            v.vital_type: VitalSummaryItem(
                vital_type=v.vital_type,
                latest=v.latest,
                recent_avg=v.recent_avg,
                baseline_avg=v.baseline_avg,
                delta_pct=v.delta_pct,
                trend=v.trend,
            )
            for v in vitals
        },
        symptom_clusters=[
            SymptomClusterItem(
                symptoms=list(c.symptoms or []),
                occurrences=c.occurrences or 0,
                last_seen=c.last_seen,
            )
            for c in clusters
        ],
        ai_observations=[
            ObservationItem(text=o.text, evidence=o.evidence or {}, created_at=o.created_at)
            for o in obs
        ],
        missing_information=[
            MissingInfoItem(description=m.description, related_to=m.related_to)
            for m in missing
        ],
        suggested_next_actions=[SuggestedActionItem(text=a.text) for a in actions],
    )


def derive_recent_changes(state: PatientHealthState) -> list[str]:
    """Deterministic short 'what changed' lines from vital trends + recent problems."""
    out: list[str] = []
    for vt, v in state.vital_summary.items():
        if v.trend in ("rising", "falling") and v.delta_pct is not None:
            label = _VITAL_LABEL.get(vt, vt)
            out.append(f"{label} {v.trend} ({v.delta_pct * 100:+.0f}%)")
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    for p in state.active_problems:
        if p.last_seen and p.last_seen >= cutoff:
            trend = f" ({p.trend})" if p.trend else ""
            freq = f" — {p.frequency}" if p.frequency else ""
            out.append(f"{p.name}{freq}{trend}")
    return out
