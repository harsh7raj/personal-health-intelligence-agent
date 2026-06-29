"""Health snapshot — deterministic, template-based (no LLM)."""

from sqlalchemy.orm import Session

from app.services.state_assembler import assemble_state, derive_recent_changes


def build_snapshot(db: Session, patient_id: int) -> dict:
    state = assemble_state(db, patient_id)
    return {
        "patient_id": patient_id,
        "active_problems": [
            {
                "name": p.name,
                "severity": p.severity,
                "frequency": p.frequency,
                "trend": p.trend,
            }
            for p in state.active_problems
        ],
        "recent_changes": derive_recent_changes(state),
        "observations": [o.text for o in state.ai_observations],
        "missing_information": [m.description for m in state.missing_information],
        "suggested_next_actions": [a.text for a in state.suggested_next_actions],
    }
