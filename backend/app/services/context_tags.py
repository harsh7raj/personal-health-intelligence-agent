"""Context tags: the circumstances around a log ("skipped lunch", "slept badly") as
structured fields, so the recurrence detector (Phase 2) can find what episodes share.

A fixed vocabulary. The intake LLM may pick tags from it; this module also finds them
with plain keyword rules (so tags work offline) and drops anything off-vocabulary.
Tags describe circumstances the user stated. They never imply a cause.
"""

import re

CONTEXT_TAGS = (
    "skipped_meal",
    "delayed_meal",
    "poor_sleep",
    "stress",
    "missed_dose",
    "alcohol",
    "exercise",
    "travel",
)

_MEAL = r"(?:breakfast|lunch|dinner|meals?|food)"
_MEDS = r"(?:dose|doses|pills?|tablets?|medicines?|medications?|meds|insulin)"

_RULES: dict[str, list[str]] = {
    "skipped_meal": [
        rf"\b(?:skip(?:ped|ping)?|miss(?:ed|ing)?|no)\s+(?:my\s+)?{_MEAL}\b",
        rf"\b(?:didn'?t|did not|couldn'?t|could not)\s+(?:have|eat|get)\s+(?:my\s+|any\s+)?{_MEAL}\b",
        r"\b(?:haven'?t|have not|didn'?t|did not)\s+eat(?:en)?\b",
        r"\bempty stomach\b",
    ],
    "delayed_meal": [
        rf"\b(?:late|delayed)\s+{_MEAL}\b",
        rf"\b{_MEAL}\s+(?:was\s+)?(?:late|delayed)\b",
    ],
    "poor_sleep": [
        r"\b(?:slept|sleep|sleeping)\s+(?:badly|poorly|very little|little)\b",
        r"\b(?:didn'?t|did not|couldn'?t|could not|can'?t|cannot)\s+sleep\b",
        r"\b(?:no|barely any|hardly any|not enough)\s+sleep\b",
        r"\bslept (?:only|just|barely)\s+\d+",
        r"\b(?:insomnia|sleepless|up all night|bad night)\b",
    ],
    "stress": [
        r"\b(?:stress(?:ed|ful)?|anxious|anxiety|tense|worried|overwhelmed|hectic)\b",
        r"\bdeadlines?\b",
        r"\b(?:work|office) pressure\b|\bpressure at work\b",
    ],
    "missed_dose": [
        rf"\b(?:forgot|forget|missed|skipped|didn'?t take|did not take)\b[^.;]{{0,30}}\b{_MEDS}\b",
        rf"\b{_MEDS}\b[^.;]{{0,20}}\b(?:missed|skipped|forgotten)\b",
    ],
    "alcohol": [
        r"\b(?:alcohol|beers?|wine|whisk(?:e)?y|vodka|rum|cocktails?|hangover|drunk)\b",
        r"\b(?:had|few|couple of|some|two|three)\s+(?:drinks|pegs)\b",
    ],
    "exercise": [
        r"\b(?:exercis(?:e|ed|ing)|work(?:ed)?\s?out|gym|jog(?:ged|ging)?|cycl(?:ed|ing)|swim(?:ming)?|yoga)\b",
        r"\bwent (?:for )?(?:a )?(?:run|jog|walk|swim)\b",
        r"\b(?:long|brisk) walk\b",
        r"\bclimb(?:ed|ing)? (?:the )?stairs\b",
        r"\b(?:played|playing) (?:cricket|football|badminton|tennis|basketball)\b",
    ],
    "travel": [
        r"\b(?:travel(?:l)?(?:ed|ing)?|trip|flight|flew|jet ?lag|journey|road trip|vacation)\b",
    ],
}
_COMPILED = {tag: [re.compile(p) for p in pats] for tag, pats in _RULES.items()}


def keyword_tags(text: str | None) -> set[str]:
    t = (text or "").lower()
    return {tag for tag, pats in _COMPILED.items() if any(p.search(t) for p in pats)}


def merge_tags(llm_tags: object, text: str | None) -> list[str]:
    """LLM-picked tags (kept only if in the vocabulary) plus keyword hits, sorted."""
    picked = {t for t in llm_tags if isinstance(t, str)} if isinstance(llm_tags, list) else set()
    return sorted((picked & set(CONTEXT_TAGS)) | keyword_tags(text))
