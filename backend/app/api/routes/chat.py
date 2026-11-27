"""The assistant chat (Phase 2, memory.md D31): one endpoint that logs, answers and
remembers. Logs: router -> intake -> memory -> reasoning -> response.
Questions: router -> memory -> response."""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DbSession, OwnedPatient
from app.db.session import SessionLocal
from app.graph.graph import graph
from app.models.records import ChatMessage
from app.services.observations import generate_observations

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/patients", tags=["chat"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    # Open the assistant with something pinned, e.g. {"type": "report", "id": 12} (Phase 4/5).
    focus: Optional[dict[str, Any]] = None


class ChatOut(BaseModel):
    message_id: int
    reply: str
    evidence: list[dict[str, Any]] = []
    logged_entry: Optional[dict[str, Any]] = None
    escalation: Optional[dict[str, Any]] = None
    needs_clarification: bool = False
    generated_by: Optional[str] = None  # llm | fallback | rules | clarify


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    evidence: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}
    created_at: datetime


def _logged_tag(new_entry: dict | None) -> dict | None:
    if not new_entry:
        return None
    s = new_entry.get("structured") or {}
    return {
        "entry_id": new_entry.get("entry_id"), "type": new_entry.get("type"),
        "name": new_entry.get("name"), "severity": (s.get("attributes") or {}).get("severity"),
        "tags": s.get("context_tags") or [], "occurred_at": new_entry.get("occurred_at"),
    }


def _observe_later(patient_id: int, new_entry: dict, context_bundle: dict | None) -> None:
    """Dashboard observations for a chat log, after the reply has gone out."""
    try:
        with SessionLocal() as db:
            generate_observations(db, patient_id, new_entry, context_bundle)
            db.commit()
    except Exception:
        logger.warning("deferred observations failed for patient %s", patient_id, exc_info=True)


@router.post("/{patient_id}/chat", response_model=ChatOut)
def chat(
    patient: OwnedPatient, payload: ChatIn, db: DbSession, background: BackgroundTasks
) -> ChatOut:
    text, skip_router = payload.message.strip(), False
    last = db.scalar(
        select(ChatMessage).where(ChatMessage.patient_id == patient.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(1)
    )
    pending = (last.meta or {}).get("clarify_for") if last and last.role == "assistant" else None
    if pending:  # this message answers the assistant's clarifying question
        text, skip_router = f"{pending}\nAdditional info: {text}", True

    report_id = (payload.focus or {}).get("id") if (payload.focus or {}).get("type") == "report" else None
    thread = {"report_id": report_id} if report_id else {}  # the report explainer's thread
    user_msg = ChatMessage(patient_id=patient.id, role="user", content=payload.message.strip(),
                           meta={"focus": payload.focus, **thread} if payload.focus else {})
    db.add(user_msg)
    db.commit()

    try:
        result = graph.invoke({
            "patient_id": patient.id, "raw_input": text, "chat": True,
            "focus": payload.focus, "skip_router": skip_router, "defer_observations": True,
        })
    except Exception as exc:
        logger.exception("chat pipeline failed for patient %s", patient.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not process this message right now. Please try again.",
        ) from exc
    get = result.get if isinstance(result, dict) else lambda k: getattr(result, k, None)

    if get("needs_clarification"):
        reply = get("pending_question") or "Could you add a bit more detail?"
        out = ChatOut(message_id=0, reply=reply, needs_clarification=True, generated_by="clarify")
        meta: dict = {"clarify_for": text, **thread}
    else:
        logged = _logged_tag(get("new_entry"))
        out = ChatOut(
            message_id=0, reply=get("reply") or "", evidence=get("evidence") or [],
            logged_entry=logged, escalation=get("escalation"), generated_by=get("generated_by"),
        )
        meta = {k: v for k, v in {"logged_entry": logged, "escalation": out.escalation,
                                  "generated_by": out.generated_by, **thread}.items() if v}
        if logged:
            user_msg.entry_id = logged["entry_id"]
            background.add_task(_observe_later, patient.id, get("new_entry"), get("context_bundle"))

    reply_msg = ChatMessage(patient_id=patient.id, role="assistant", content=out.reply,
                            evidence=out.evidence, meta=meta)
    db.add(reply_msg)
    db.commit()
    out.message_id = reply_msg.id
    return out


@router.get("/{patient_id}/chat", response_model=list[ChatMessageOut])
def chat_history(
    patient: OwnedPatient, db: DbSession, limit: int = Query(50, ge=1, le=200),
    report_id: Optional[int] = Query(None, description="only the thread pinned to this report"),
) -> list[ChatMessage]:
    q = select(ChatMessage).where(ChatMessage.patient_id == patient.id)
    if report_id is not None:
        q = q.where(ChatMessage.meta["report_id"].astext == str(report_id))
    rows = db.scalars(q.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(limit)).all()
    return list(reversed(rows))
