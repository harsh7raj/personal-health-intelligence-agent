"""Groq fallback for per-drug REFERENCE info only (Part 2).

Used ONLY when the curated MedlinePlus table has no entry for a drug. This is
general, non-diagnostic reference content — the same risk tier as the system's
existing observations — so an LLM is acceptable here. It is clearly labelled as
AI-generated in the output (provenance='ai') so the UI never conflates it with the
sourced MedlinePlus entries.

HARD SCOPE: this NEVER touches interaction checking. Drug-drug interactions come
solely from the local DDInter table; no LLM verdict about interactions, ever.
"""

import logging

from app.core.config import get_settings
from app.core.llm import groq_json
from app.services.language_guard import is_diagnostic

logger = logging.getLogger(__name__)
settings = get_settings()

AI_SOURCE = "AI-generated general reference — verify with a pharmacist"

_SYSTEM = """You provide SHORT, general, NON-DIAGNOSTIC reference information about a \
single medication, like the general-information blurb on a consumer drug leaflet.
Return JSON: {"used_for": string, "timing": string, "considerations": string}.
HARD RULES: general information only — never personalize, never diagnose, never tell the \
user what THEY should do, never give a specific dose for a person, never assert a cause, \
and never state a drug-drug interaction verdict. Keep each field to one short sentence.
WORDING: write "commonly used for ..." — never write "used to treat", "treatment for", \
"to treat", "prescribed for", or "you should". Describe, don't instruct.
- used_for: what this medication is typically used for.
- timing: common timing/food guidance (e.g. with food, on an empty stomach, time of day).
- considerations: one common general consideration.
If you do not recognize the drug, return empty strings for all fields."""

_cache: dict[str, dict | None] = {}


def ai_reference(name: str) -> dict | None:
    """General reference info for `name` via Groq, or None if unavailable/unclean.
    Result shape matches the curated table, with provenance='ai'."""
    key = (name or "").strip().lower()
    if not key:
        return None
    if key in _cache:
        return _cache[key]
    if not settings.GROQ_API_KEY:
        _cache[key] = None
        return None

    try:
        res = groq_json(_SYSTEM, f"Medication: {name}", model=settings.REASONING_MODEL)
    except Exception:
        # Transient failure — do NOT cache, so a later view can retry.
        logger.warning("AI drug reference generation failed for %s", name, exc_info=True)
        return None

    used_for = (res.get("used_for") or "").strip()
    timing = (res.get("timing") or "").strip()
    considerations = (res.get("considerations") or "").strip()
    fields = [used_for, timing, considerations]
    result: dict | None = None
    if any(is_diagnostic(f) for f in fields):
        logger.warning("dropped diagnostic-sounding AI drug reference for %s", name)
    elif all(fields):
        result = {
            "used_for": used_for,
            "timing": timing,
            "considerations": considerations,
            "source": AI_SOURCE,
            "provenance": "ai",
        }
    # Cache only deterministic outcomes (real content, empty, or guard-dropped).
    _cache[key] = result
    return result
