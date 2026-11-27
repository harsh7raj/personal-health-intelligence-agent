"""Drug classes from RxClass (NLM), cached per ingredient (ROADMAP.md Phase 5, memory.md D35).

Kept: the established pharmacologic class (EPC, e.g. "Sulfonylurea"), mechanisms (MOA, e.g.
"Cytochrome P450 3A4 Inhibitors") and single-drug ATC classes. EPC finds duplicates across
doctors; EPC and MOA names are matched against label text ("strong CYP3A4 inhibitors")."""

import re
import urllib.parse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.models.drugs import DrugClassInfo
from app.services import http

_URL = "https://rxnav.nlm.nih.gov/REST/rxclass/class/byDrugName.json"
SOURCE = "RxClass (U.S. National Library of Medicine)"
SOURCE_URL = "https://mor.nlm.nih.gov/RxClass/"


def _keep(item: dict) -> dict | None:
    c = item.get("rxclassMinConceptItem") or {}
    ctype, rela, name = c.get("classType"), (item.get("rela") or "").lower(), c.get("className") or ""
    if ctype == "EPC" and rela == "has_epc" or ctype == "MOA" and rela == "has_moa":
        return {"id": c.get("classId"), "name": name, "type": ctype}
    if ctype == "ATC1-4" and "combination" not in name.lower() and " and " not in name.lower():
        return {"id": c.get("classId"), "name": name, "type": "ATC"}
    return None


def _fetch(ingredient: str) -> list[dict] | None:
    try:
        data = http.get_json(f"{_URL}?drugName={urllib.parse.quote(ingredient)}", timeout=8.0)
    except http.NotFound:
        return []
    if data is None:
        return None
    seen, out = set(), []
    for item in (data.get("rxclassDrugInfoList") or {}).get("rxclassDrugInfo") or []:
        kept = _keep(item)
        if kept and kept["id"] not in seen:
            seen.add(kept["id"])
            out.append(kept)
    return out


def get_classes(db: Session, ingredient: str) -> list[dict]:
    ingredient = (ingredient or "").strip().lower()
    if not ingredient:
        return []
    row = db.scalar(select(DrugClassInfo).where(DrugClassInfo.ingredient == ingredient))
    if row is not None:
        return row.classes
    fetched = _fetch(ingredient)
    if fetched is None:
        return []  # offline: try again next time
    db.add(DrugClassInfo(ingredient=ingredient, classes=fetched, fetched_at=clock.now()))
    db.flush()
    return fetched


def label_terms(classes: list[dict]) -> list[str]:
    """How a label would mention these classes: 'Cytochrome P450 3A4 Inhibitors' ->
    'CYP3A4 inhibitor', 'cytochrome P450 3A4 inhibitor'; 'Sulfonylurea' -> 'sulfonylurea'."""
    terms: list[str] = []
    for c in classes:
        if c["type"] not in ("EPC", "MOA"):
            continue
        name = c["name"].lower().strip()
        name = re.sub(r"\s*\[.*?\]", "", name)
        singular = re.sub(r"s$", "", name)
        terms += [singular, re.sub(r"cytochrome p450 (\w+)", r"cyp\1", singular)]
    return [t for t in dict.fromkeys(terms) if len(t) > 4]


def epc_names(classes: list[dict]) -> set[str]:
    return {c["name"] for c in classes if c["type"] == "EPC"}
