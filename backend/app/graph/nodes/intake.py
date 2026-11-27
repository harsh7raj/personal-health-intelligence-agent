import logging

from app.core import clock
from app.core.llm import is_available, llm_json
from app.db.session import SessionLocal
from app.graph.state import GraphState
from app.models.records import Entry
from app.services.onset import resolve_onset
from app.vectorstore.collections import get_entries_collection

logger = logging.getLogger(__name__)

_VALID_TYPES = {"symptom", "vital", "report", "medication", "note"}

_SYSTEM_PROMPT = """You are a medical intake parser. Convert the user's free-text health \
log into a single structured JSON fact. Return ONLY a JSON object with keys:
- type: one of "symptom","vital","report","medication","note"
- name: short normalized name (e.g. "headache", "blood pressure", "amlodipine")
- attributes: object of extracted details (severity, duration, onset, frequency, location, ...). \
"onset" is the user's OWN WORDS for when it started or happened, only if they said it \
(e.g. "yesterday", "last night", "since Monday", "2 days ago"); never turn it into a date.
- value: number for a SINGLE-number vital (heart rate, weight, glucose, SpO2, temperature), else null
- unit: string unit for that single value if present, else null
- complete: boolean — true if clear enough to record; false if a key field is missing
For BLOOD PRESSURE specifically: ALWAYS put both numbers in attributes as "systolic" and \
"diastolic" (as numbers) and leave value and unit null — never collapse BP into the value field.
- clarifying_question: one short question to ask if complete is false, else null
Normalize lay terms (e.g. "tummy ache" -> "abdominal pain"). Record only what the user states; \
NEVER infer or name a diagnosis, disease, cause, or treatment — capture the raw symptom/vital/note only."""


def _fallback_parse(text: str) -> dict:
    # Used when no LLM is configured or reachable (offline runs and tests).
    return {
        "type": "note",
        "name": (text.strip()[:64] or "note"),
        "attributes": {},
        "value": None,
        "unit": None,
        "complete": True,
        "clarifying_question": None,
    }


def parse_entry(text: str) -> dict:
    if not is_available():
        logger.warning("No LLM configured; using the deterministic fallback parser")
        return _fallback_parse(text)
    try:
        fact = llm_json("intake", _SYSTEM_PROMPT, text)
    except Exception:
        logger.warning("intake LLM parse failed — degrading to fallback parser", exc_info=True)
        return _fallback_parse(text)
    if fact.get("type") not in _VALID_TYPES:
        fact["type"] = "note"
    fact.setdefault("complete", True)
    fact.setdefault("clarifying_question", None)
    fact.setdefault("attributes", {})
    return fact


def intake_node(state: GraphState) -> dict:
    text = state.raw_input or ""
    fact = parse_entry(text)

    if not fact.get("complete", True):
        return {
            "needs_clarification": True,
            "pending_question": fact.get("clarifying_question")
            or "Could you provide a bit more detail?",
        }

    # When it happened: the LLM quotes the onset words, code resolves them (D17).
    onset = (fact.get("attributes") or {}).get("onset")
    occurred = (
        resolve_onset(text, phrase=onset if isinstance(onset, str) else None) or clock.now()
    )

    # Persist the entry (append-only source of truth), then embed it.
    with SessionLocal() as db:
        entry = Entry(
            patient_id=state.patient_id,
            type=fact["type"],
            raw_text=text,
            structured=fact,
            source="intake",
            occurred_at=occurred,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        entry_id = entry.id

    get_entries_collection().add(
        documents=[text],
        ids=[f"entry_{entry_id}"],
        metadatas=[
            {
                "patient_id": state.patient_id,
                "entry_id": entry_id,
                "type": fact["type"],
                "date": occurred.isoformat(),
            }
        ],
    )

    return {
        "new_entry": {
            "entry_id": entry_id,
            "type": fact["type"],
            "name": fact.get("name"),
            "structured": fact,
            "raw_text": text,
            "occurred_at": occurred.isoformat(),
        },
        "needs_clarification": False,
        "pending_question": None,
    }
