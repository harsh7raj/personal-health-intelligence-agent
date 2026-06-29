from typing import Any, Optional

from pydantic import BaseModel


class GraphState(BaseModel):
    """Shared state passed between LangGraph nodes for one intake run."""

    patient_id: int
    raw_input: str = ""

    # set by intake_node
    new_entry: Optional[dict[str, Any]] = None
    needs_clarification: bool = False
    pending_question: Optional[str] = None
    clarification_answer: Optional[str] = None

    # set by memory_node
    context_bundle: Optional[dict[str, Any]] = None

    # set by reasoning_node
    reasoning_summary: Optional[dict[str, Any]] = None

    # set by response_node (Phase 6)
    output_type: Optional[str] = None
