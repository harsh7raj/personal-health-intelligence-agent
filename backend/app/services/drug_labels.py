"""Official drug labels from openFDA, cached per ingredient (ROADMAP.md Phase 5, memory.md D35).

The safety checks quote these sections verbatim; nothing here interprets them. openFDA's own
notice applies: the data is not meant for making medical decisions on its own."""

import logging
import re
import urllib.parse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.models.drugs import DrugLabel
from app.services import http

logger = logging.getLogger(__name__)

OPENFDA_DISCLAIMER = ("Label text from openFDA (U.S. FDA). openFDA notes its data should not be "
                      "relied on to make medical decisions; confirm with your pharmacist or doctor.")
_URL = "https://api.fda.gov/drug/label.json"
# Our section -> openFDA fields, in order of preference.
SECTIONS: dict[str, tuple[str, ...]] = {
    "drug_interactions": ("drug_interactions",),
    "warnings": ("boxed_warning", "warnings_and_cautions", "warnings", "precautions"),
    "contraindications": ("contraindications",),
    "adverse_reactions": ("adverse_reactions",),
    "dosage_and_administration": ("dosage_and_administration",),
}
_MAX_SECTION = 40_000  # characters kept per section


def _pick(results: list[dict], ingredient: str) -> dict | None:
    """Prefer a single-ingredient label whose substance matches; else the first result."""
    want = ingredient.lower()

    def single(r: dict) -> bool:
        subs = [s.lower() for s in (r.get("openfda") or {}).get("substance_name") or []]
        return len(subs) == 1 and want in subs[0]

    return next((r for r in results if single(r)), results[0] if results else None)


def _fetch(ingredient: str) -> dict | None:
    """{'found': bool, ...} from openFDA, or None if it couldn't be reached."""
    q = urllib.parse.quote(f'openfda.generic_name:"{ingredient}"')
    key = get_settings().OPENFDA_API_KEY
    url = f"{_URL}?search={q}&limit=10" + (f"&api_key={urllib.parse.quote(key)}" if key else "")
    try:
        data = http.get_json(url, timeout=10.0)
    except http.NotFound:  # openFDA answers 404 when nothing matches
        return {"found": False}
    if data is None:
        return None
    r = _pick(data.get("results") or [], ingredient)
    if r is None:
        return {"found": False}
    sections = {}
    for ours, fields in SECTIONS.items():
        text = " ".join(" ".join(r.get(f) or []) for f in fields).strip()
        if text:
            sections[ours] = text[:_MAX_SECTION]
    brand = ", ".join(((r.get("openfda") or {}).get("brand_name") or [])[:2])
    generic = ", ".join(((r.get("openfda") or {}).get("generic_name") or [])[:1])
    return {"found": True, "set_id": r.get("set_id"), "title": f"{generic} ({brand})" if brand else generic,
            "sections": sections}


def get_label(db: Session, ingredient: str, *, refresh: bool = False) -> DrugLabel | None:
    """The cached label for an ingredient, fetching it once. None if openFDA is unreachable
    and nothing is cached; a row with found=False if openFDA has no label for it."""
    ingredient = (ingredient or "").strip().lower()
    if not ingredient:
        return None
    row = db.scalar(select(DrugLabel).where(DrugLabel.ingredient == ingredient))
    if row is not None and not refresh:
        return row
    fetched = _fetch(ingredient)
    if fetched is None:
        return row  # offline: keep whatever we had
    if row is None:
        row = DrugLabel(ingredient=ingredient)
        db.add(row)
    row.found = fetched["found"]
    row.set_id = fetched.get("set_id")
    row.title = fetched.get("title")
    row.sections = fetched.get("sections") or {}
    row.fetched_at = clock.now()
    db.flush()
    return row


def source_url(label: DrugLabel | None) -> str | None:
    if label is None or not label.set_id:
        return None
    return f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={label.set_id}"


def normalize(text: str) -> str:
    return " ".join((text or "").split())


def sentences(text: str) -> list[str]:
    """Label text split into sentences (labels have no reliable line breaks)."""
    # Not split at ":" so a heading stays with its sentence ("Hypoglycemia: All sulfonylureas...").
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z(•\d])", normalize(text))
    return [p for p in parts if len(p) >= 40]  # skip bare headings and cross-references


def _window(sentence: str, term_at: int, size: int = 420) -> str:
    """A verbatim excerpt of a long sentence (label tables run on), centred on the match."""
    if len(sentence) <= size:
        return sentence
    start = max(0, min(term_at - size // 3, len(sentence) - size))
    return sentence[start:start + size].strip()


def find(label: DrugLabel | None, terms: list[str], sections: tuple[str, ...]) -> list[dict]:
    """Verbatim sentences in `sections` that mention any of `terms` (whole words, any case):
    [{'section', 'quote', 'term', 'next'}], at most 3 per section. `next` is the following
    sentence when `quote` is a whole sentence (so quote + " " + next is still verbatim)."""
    if label is None or not label.found:
        return []
    pats = [(t, re.compile(rf"\b{re.escape(t)}", re.I)) for t in dict.fromkeys(terms) if t and len(t) > 2]
    out: list[dict] = []
    for sec in sections:
        found = 0
        sents = sentences(label.sections.get(sec) or "")
        for i, sent in enumerate(sents):
            for term, pat in pats:
                m = pat.search(sent)
                if m:
                    quote = _window(sent, m.start())
                    nxt = sents[i + 1] if quote == sent and i + 1 < len(sents) else None
                    out.append({"section": sec, "quote": quote, "term": term, "next": nxt})
                    found += 1
                    break
            if found >= 3:
                break
    return out


def quote_is_verbatim(label: DrugLabel | None, quote: str) -> bool:
    """Code's check that a quoted sentence really is in the cached label text."""
    if label is None or not quote or len(quote.strip()) < 15:
        return False
    q = normalize(quote).lower().strip(" .…")
    return any(q in normalize(t).lower() for t in label.sections.values())
