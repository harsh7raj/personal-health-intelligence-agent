"""Health Story — Groq narrative (D8) with a deterministic fallback."""

import json
import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.llm import groq_json
from app.schemas.health_state import PatientHealthState
from app.services.state_assembler import assemble_state, derive_recent_changes

logger = logging.getLogger(__name__)
settings = get_settings()

_SYSTEM = """You write a SHORT, flowing, NON-DIAGNOSTIC narrative of a patient's health over time. \
Synthesize and weave the provided data into 1-2 short paragraphs of prose. Do NOT enumerate, list, or \
repeat the same point. Never diagnose, never recommend treatment, never name a condition the data does \
not state. Ground every sentence in the provided data. Return JSON: {"story": "..."}."""


def _payload(state: PatientHealthState) -> dict:
    return {
        "active_problems": [
            {"name": p.name, "frequency": p.frequency, "trend": p.trend, "severity": p.severity}
            for p in state.active_problems
        ],
        "vital_trends": [
            {"vital_type": vt, "latest": v.latest, "trend": v.trend, "delta_pct": v.delta_pct}
            for vt, v in state.vital_summary.items()
        ],
        "symptom_clusters": [
            {"symptoms": c.symptoms, "occurrences": c.occurrences}
            for c in state.symptom_clusters
        ],
        "observations": [o.text for o in state.ai_observations],
        "recent_changes": derive_recent_changes(state),
    }


def _fallback_story(state: PatientHealthState) -> str:
    parts: list[str] = []
    if state.active_problems:
        probs = ", ".join(
            f"{p.name}" + (f" ({p.frequency}, {p.trend})" if p.trend else "")
            for p in state.active_problems
        )
        parts.append(f"Active problems: {probs}.")
    changes = derive_recent_changes(state)
    if changes:
        parts.append("Recent changes: " + "; ".join(changes) + ".")
    if state.ai_observations:
        parts.append("Observations: " + " ".join(o.text for o in state.ai_observations[:3]))
    if not parts:
        parts.append("No significant health data has been recorded yet.")
    return " ".join(parts)


def build_story(db: Session, patient_id: int) -> dict:
    state = assemble_state(db, patient_id)
    if settings.GROQ_API_KEY:
        try:
            res = groq_json(_SYSTEM, json.dumps(_payload(state)), model=settings.RESPONSE_MODEL)
            story = (res.get("story") or "").strip()
            if story:
                return {"story": story, "generated_by": "llm"}
        except Exception:
            logger.warning("story generation failed; using fallback", exc_info=True)
    return {"story": _fallback_story(state), "generated_by": "fallback"}
