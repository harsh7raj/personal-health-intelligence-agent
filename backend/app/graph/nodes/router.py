"""Router: is this message a log, a question, or both? (memory.md D21)

Runs before intake. A question is not saved; it goes to the assistant (Phase 2; until
then it gets a short holding reply). "both" is logged and its question passed along.
Uses the fast LLM tier when available, else a deterministic heuristic.
"""

import logging
import re

from app.core.llm import is_available, llm_json
from app.graph.state import GraphState

logger = logging.getLogger(__name__)

KINDS = ("log", "question", "both")

# Until the Phase 2 assistant exists, questions get this instead of an answer.
QUESTION_HOLDING_REPLY = (
    "That sounds like a question, so I haven't logged anything from it. Answers from "
    "your history are coming soon; for now you can browse your Dashboard, Vitals and "
    "Reports pages."
)

_SYSTEM = """You sort messages sent to a personal health log app. Return ONLY JSON:
{"kind": "log" | "question" | "both", "question": string or null}
- "log": the user records something (a symptom, reading, medicine, event, how they feel).
- "question": the user only asks something (about their history, reports, medicines...).
- "both": the user records something AND asks something; put the asked part in "question".
Never answer the question. When unsure, choose "log"."""

# A sentence reads as a question if it ends with "?" or starts in question form. Bare
# "have"/"when" also start plenty of logs ("Have been dizzy", "When I woke up..."), so
# auxiliaries need a subject after them and wh-words need question syntax.
_INTERROGATIVE = re.compile(
    r"^(?:"
    r"(?:what|when|why|where|who|how)\s+(?:is|are|was|were|do|does|did|has|have|had|can|"
    r"could|should|will|would|am|many|much|often|long|about|else)\b"
    r"|(?:which|whose)\s+\w+"
    r"|(?:is|are|was|were|do|does|did|can|could|should|would|will|has|have|am)\s+"
    r"(?:i|my|it|this|that|these|those|you|we|there|the|me)\b"
    r"|tell me|show me|remind me|explain\b"
    r")",
    re.IGNORECASE,
)
_READING = re.compile(r"\b\d{2,3}\s*(?:/|over)\s*\d{2,3}\b|\b\d+(?:\.\d+)?\s*(?:mg/dl|kg|bpm|%)", re.I)


def heuristic_kind(text: str) -> tuple[str, str | None]:
    """Offline fallback: sentence-level question marks / question words."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]
    questions = [s for s in sentences if s.endswith("?") or _INTERROGATIVE.match(s)]
    if not questions:
        return "log", None
    asked = " ".join(questions)
    statements = [s for s in sentences if s not in questions]
    # "Is it bad that my BP is 150/95?" still carries a reading worth logging.
    if statements or any(_READING.search(q) for q in questions):
        return "both", asked
    return "question", asked


def _clear_cut(text: str, kind: str) -> bool:
    """The heuristic is reliable for plain logs (no question signal at all) and for a message
    that is one question sentence; only mixed or unclear messages need the LLM router."""
    if kind == "log":
        return True
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]
    return kind == "question" and len(sentences) == 1


def classify_message(text: str) -> tuple[str, str | None]:
    guess = heuristic_kind(text)
    if _clear_cut(text, guess[0]):
        return guess  # saves a model call (~1 s) on most messages
    if is_available():
        try:
            res = llm_json("router", _SYSTEM, text)
            kind = res.get("kind")
            if kind in KINDS:
                question = res.get("question") if kind != "log" else None
                return kind, (question if isinstance(question, str) and question.strip() else None)
            logger.warning("router returned an unknown kind %r; using the heuristic", kind)
        except Exception:
            logger.warning("router LLM call failed; using the heuristic", exc_info=True)
    return heuristic_kind(text)


def router_node(state: GraphState) -> dict:
    if state.skip_router:  # answers to a clarifying question are always part of a log
        return {"message_kind": "log", "user_question": None}
    kind, question = classify_message(state.raw_input or "")
    return {"message_kind": kind, "user_question": question}


def question_node(state: GraphState) -> dict:
    # Phase 2 replaces this with the assistant's answer (memory -> response).
    return {"assistant_reply": QUESTION_HOLDING_REPLY}
