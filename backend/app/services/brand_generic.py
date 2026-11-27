"""Brand name -> generic ingredients (ROADMAP.md Phase 5, memory.md D35).

RxNorm first. Indian brands ("Thyronorm 75", "Shelcal") are mostly unknown to RxNorm, so
Haiku suggests the generics, each is checked against RxNorm, and the user must confirm before
anything is saved (ground rule: nothing medical is saved unconfirmed)."""

import logging

from app.core.llm import is_available, llm_json
from app.services import rxnorm

logger = logging.getLogger(__name__)

_SYSTEM = """You map a medicine name as a patient wrote it (often an Indian brand, possibly with \
a strength) to its generic active ingredients. Return JSON: {"ingredients": [{"name": "generic \
ingredient in lowercase, no salt unless it is part of the usual name", "strength": "e.g. 75 mcg or \
null"}], "confidence": "high" | "low"}. Examples: "Thyronorm 75" -> levothyroxine 75 mcg; \
"Shelcal 500" -> calcium carbonate 500 mg + cholecalciferol 250 IU; "Glycomet GP 1" -> metformin + \
glimepiride. If you don't recognise the name, return {"ingredients": [], "confidence": "low"}. \
Never guess a medicine you don't know."""


def resolve(name: str) -> dict:
    """{"status": "rxnorm" | "suggested" | "unknown" | "offline", "ingredients": [...],
    "suggestion": [{"name", "strength", "rxnorm_ingredients", "verified"}], "needs_confirmation"}."""
    found = rxnorm.lookup(name)
    if found["status"] == "found":
        return {"status": "rxnorm", "ingredients": found["ingredients"], "suggestion": [],
                "needs_confirmation": False}
    suggestion: list[dict] = []
    if is_available():
        try:
            res = llm_json("brand_generic", _SYSTEM, f"Medicine: {name}")
            for item in (res.get("ingredients") or [])[:5]:
                gname = str((item or {}).get("name") or "").strip().lower()
                if not gname:
                    continue
                check = rxnorm.lookup(gname)
                suggestion.append({
                    "name": gname, "strength": (item or {}).get("strength"),
                    "rxnorm_ingredients": check["ingredients"], "verified": check["status"] == "found",
                })
        except Exception:
            logger.warning("brand->generic suggestion failed for %s", name, exc_info=True)
    status = "suggested" if suggestion else ("offline" if found["status"] == "offline" else "unknown")
    return {"status": status, "ingredients": [], "suggestion": suggestion, "needs_confirmation": bool(suggestion)}


def confirmed_ingredients(chosen: list[str]) -> list[str]:
    """The ingredients to store once the user confirms: RxNorm's names where it knows them."""
    out: list[str] = []
    for c in chosen:
        c = (c or "").strip().lower()
        if not c:
            continue
        check = rxnorm.lookup(c)
        out += check["ingredients"] if check["status"] == "found" else [c]
    return list(dict.fromkeys(out))
