"""Health Story — Groq narrative (D8) with a deterministic fallback."""

import json
import logging
import re

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.llm import groq_json
from app.schemas.health_state import PatientHealthState
from app.services.state_assembler import assemble_state, derive_recent_changes

logger = logging.getLogger(__name__)
settings = get_settings()

_SYSTEM = """You write a clear, specific, NON-DIAGNOSTIC health narrative from a patient's longitudinal data.
Write EXACTLY THREE short paragraphs, separated by a blank line (\\n\\n):
- Paragraph 1 — Headline: the single most notable trend right now, stated specifically with the numbers.
- Paragraph 2 — Connections: thoughtfully relate the findings to one another. Note where different patterns
  have developed over the same period, recur together, or move in the same direction, and reflect on why they
  may be worth watching together. Be substantive and specific — this is the most important paragraph.
- Paragraph 3 — Stable & to track: what has stayed steady or reassuring (including resolved issues), and what
  is missing or worth tracking next.
HARD NON-DIAGNOSTIC RULES: never state or imply a diagnosis; never name a disease/condition as a new fact;
never claim a medical cause (do NOT use "caused by", "due to", "because of", "leads to", "results in");
never recommend treatment or medication. You MAY describe temporal/associative patterns ("have risen over the
same months", "have appeared together", "are worth monitoring together") — as observations, not causal claims.
Use the actual numbers; avoid generic filler. Return JSON: {"story": "<three paragraphs separated by \\n\\n>"}."""


def _payload(state: PatientHealthState) -> dict:
    return {
        "known_conditions": state.medical_background.conditions,
        "active_problems": [
            {"name": p.name, "frequency": p.frequency, "trend": p.trend, "severity": p.severity}
            for p in state.active_problems
        ],
        "resolved_problems": [p.name for p in state.resolved_problems],
        "vital_trends": [
            {
                "vital_type": vt,
                "latest": v.latest,
                "trend": v.trend,
                "change_pct": round(v.delta_pct * 100, 1) if v.delta_pct is not None else None,
            }
            for vt, v in state.vital_summary.items()
        ],
        "symptom_clusters": [
            {"symptoms": c.symptoms, "occurrences": c.occurrences}
            for c in state.symptom_clusters
        ],
        "observations": [o.text for o in state.ai_observations],
        "recent_changes": derive_recent_changes(state),
        "missing_information": [m.description for m in state.missing_information],
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
    return "\n\n".join(parts)


def build_story(db: Session, patient_id: int) -> dict:
    state = assemble_state(db, patient_id)
    if settings.GROQ_API_KEY:
        try:
            res = groq_json(_SYSTEM, json.dumps(_payload(state)), model=settings.RESPONSE_MODEL)
            story = (res.get("story") or "").strip()
            story = re.sub(r"[ \t]+\n", "\n", story)  # trim trailing spaces on lines
            story = re.sub(r"\n{3,}", "\n\n", story)  # collapse to single blank-line paragraph breaks
            if story:
                return {"story": story, "generated_by": "llm"}
        except Exception:
            logger.warning("story generation failed; using fallback", exc_info=True)
    return {"story": _fallback_story(state), "generated_by": "fallback"}
