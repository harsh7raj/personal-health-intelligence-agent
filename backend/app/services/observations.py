"""LLM-authored observations (Groq). Strictly observational — never diagnostic."""

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.llm import groq_json
from app.models.clinical import Problem, SymptomCluster, VitalSummary
from app.models.intelligence import Observation
from app.services.language_guard import is_diagnostic

logger = logging.getLogger(__name__)
settings = get_settings()

_SYSTEM = """You write SHORT, factual, NON-DIAGNOSTIC observations about patterns in a \
patient's longitudinal health data. HARD RULES: never state or imply a diagnosis; never name a \
disease/condition as fact; never assert a cause ("caused by", "due to", "because of"); never \
recommend treatment or medication. CRITICAL: use ONLY the problems, vitals, and clusters present in \
the provided JSON — NEVER invent a symptom, reading, value, or event that is not explicitly in the data. \
Only describe observed patterns/trends/frequencies. GOOD: "Headache episodes have increased to 3 in two \
months." BAD (invented): "Chest heaviness has been reported." BAD (diagnostic): "You have migraines", \
"This is caused by stress". Return JSON: {"observations": [strings]} with 0 to 3 short items; empty list \
if nothing noteworthy."""


def generate_observations(
    db: Session, patient_id: int, new_entry: dict, context_bundle: dict | None
) -> list[str]:
    if not settings.GROQ_API_KEY:
        return []

    active = [
        {"name": p.name, "trend": p.trend, "frequency": p.frequency, "severity": p.severity}
        for p in db.scalars(
            select(Problem).where(
                Problem.patient_id == patient_id,
                Problem.status.in_(["active", "managed"]),
            )
        ).all()
    ]
    vitals = [
        {"vital_type": v.vital_type, "latest": v.latest, "trend": v.trend, "delta_pct": v.delta_pct}
        for v in db.scalars(
            select(VitalSummary).where(VitalSummary.patient_id == patient_id)
        ).all()
    ]
    clusters = [
        {"symptoms": c.symptoms, "occurrences": c.occurrences}
        for c in db.scalars(
            select(SymptomCluster).where(SymptomCluster.patient_id == patient_id)
        ).all()
    ]
    payload = {
        "new_entry": {"type": new_entry.get("type"), "name": new_entry.get("name")},
        "active_problems": active,
        "vital_trends": vitals,
        "symptom_clusters": clusters,
    }

    try:
        res = groq_json(_SYSTEM, json.dumps(payload), model=settings.REASONING_MODEL)
    except Exception:
        logger.warning("observation generation failed", exc_info=True)
        return []

    created: list[str] = []
    for text in (res.get("observations") or [])[:3]:
        if not isinstance(text, str) or not text.strip():
            continue
        clean = text.strip()
        if is_diagnostic(clean):  # runtime non-diagnostic guard (Phase 8)
            logger.warning("dropped diagnostic-sounding observation: %s", clean)
            continue
        db.add(Observation(patient_id=patient_id, text=clean, evidence=payload))
        created.append(clean)
    return created
