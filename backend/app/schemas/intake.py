from typing import Any, Optional

from pydantic import BaseModel


class IntakeIn(BaseModel):
    raw_text: str
    input_hint: Optional[str] = None


class IntakeAnswerIn(BaseModel):
    raw_text: str
    answer: str


class IntakeOut(BaseModel):
    status: str  # "processed" | "clarification_needed"
    question: Optional[str] = None
    new_entry: Optional[dict[str, Any]] = None
    context_bundle: Optional[dict[str, Any]] = None
