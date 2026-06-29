from typing import Any

from fastapi import APIRouter

from app.api.deps import OwnedPatient
from app.graph.graph import graph
from app.schemas.intake import IntakeAnswerIn, IntakeIn, IntakeOut

router = APIRouter(prefix="/patients", tags=["intake"])


def _get(result: Any, key: str) -> Any:
    if isinstance(result, dict):
        return result.get(key)
    return getattr(result, key, None)


def _run(patient_id: int, text: str) -> IntakeOut:
    result = graph.invoke({"patient_id": patient_id, "raw_input": text})
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
