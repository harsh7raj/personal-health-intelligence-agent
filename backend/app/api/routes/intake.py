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


def _run(patient_id: int, text: str) -> IntakeOut:
    try:
        result = graph.invoke({"patient_id": patient_id, "raw_input": text})
    except Exception as exc:  # pipeline-level failure (e.g. store outage)
        logger.exception("intake pipeline failed for patient %s", patient_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not process this entry right now. Please try again.",
        ) from exc
    if _get(result, "needs_clarification"):
        return IntakeOut(
            status="clarification_needed", question=_get(result, "pending_question")
        )
    return IntakeOut(
        status="processed",
        new_entry=_get(result, "new_entry"),
        context_bundle=_get(result, "context_bundle"),
    )


@router.post("/{patient_id}/intake", response_model=IntakeOut)
def intake(patient: OwnedPatient, payload: IntakeIn) -> IntakeOut:
    return _run(patient.id, payload.raw_text)


@router.post("/{patient_id}/intake/answer", response_model=IntakeOut)
def intake_answer(patient: OwnedPatient, payload: IntakeAnswerIn) -> IntakeOut:
    combined = f"{payload.raw_text}\nAdditional info: {payload.answer}"
    return _run(patient.id, combined)
