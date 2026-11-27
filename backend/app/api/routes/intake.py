import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.api.deps import OwnedPatient
from app.graph.graph import graph
from app.schemas.intake import IntakeAnswerIn, IntakeIn, IntakeOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/patients", tags=["intake"])


def _get(result: Any, key: str) -> Any:
    if isinstance(result, dict):
        return result.get(key)
    return getattr(result, key, None)


def _run(patient_id: int, text: str, *, skip_router: bool = False) -> IntakeOut:
    try:
        result = graph.invoke(
            {"patient_id": patient_id, "raw_input": text, "skip_router": skip_router}
        )
    except Exception as exc:  # pipeline-level failure (e.g. store outage)
        logger.exception("intake pipeline failed for patient %s", patient_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not process this entry right now. Please try again.",
        ) from exc
    kind = _get(result, "message_kind")
    if kind == "question":  # not saved; answered by the assistant (Phase 2)
        return IntakeOut(
            status="question",
            reply=_get(result, "assistant_reply"),
            user_question=_get(result, "user_question"),
        )
    if _get(result, "needs_clarification"):
        return IntakeOut(
            status="clarification_needed", question=_get(result, "pending_question")
        )
    return IntakeOut(
        status="processed",
        new_entry=_get(result, "new_entry"),
        context_bundle=_get(result, "context_bundle"),
        reasoning_summary=_get(result, "reasoning_summary"),
        user_question=_get(result, "user_question") if kind == "both" else None,
    )


@router.post("/{patient_id}/intake", response_model=IntakeOut)
def intake(patient: OwnedPatient, payload: IntakeIn) -> IntakeOut:
    return _run(patient.id, payload.raw_text)


@router.post("/{patient_id}/intake/answer", response_model=IntakeOut)
def intake_answer(patient: OwnedPatient, payload: IntakeAnswerIn) -> IntakeOut:
    combined = f"{payload.raw_text}\nAdditional info: {payload.answer}"
    return _run(patient.id, combined, skip_router=True)  # answering a clarifying question
