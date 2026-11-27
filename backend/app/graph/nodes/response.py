from app.db.session import SessionLocal
from app.graph.state import GraphState
from app.services.assistant import respond


def response_node(state: GraphState) -> dict:
    """The assistant reply (Phase 2, D31) for chat turns. The /intake endpoint (no chat)
    still passes straight through; snapshot/story/PDF are separate REST outputs."""
    if not state.chat:
        return {}
    with SessionLocal() as db:
        out = respond(
            db,
            state.patient_id,
            message=state.raw_input,
            kind=state.message_kind or "log",
            new_entry=state.new_entry,
            context_bundle=state.context_bundle,
            focus=state.focus,
        )
    return {
        "reply": out["reply"],
        "evidence": out["evidence"],
        "escalation": out["escalation"],
        "generated_by": out["generated_by"],
    }
