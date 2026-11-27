"""Non-diagnostic language guard. The system observes & explains — it never diagnoses,
asserts a condition as fact, states causation, or recommends treatment. Conservative
denylist so legitimate trend/pattern observations are not dropped."""

import re

# Words that make "you have ..." a diagnosis rather than a count ("you have logged 3").
_CONDITION = (
    r"(?:diseases?|disorders?|syndromes?|conditions?|infections?|deficienc(?:y|ies)|cancer|"
    r"tumou?rs?|diabetes|prediabetes|pre-diabetes|hypertension|hypotension|hypothyroidism|"
    r"hyperthyroidism|an(?:a)?emia|migraines?|asthma|arthritis|depression|pneumonia|ulcers?|"
    r"covid|flu|hypoglyc(?:a)?emia|hyperglyc(?:a)?emia|neuropathy|insulin resistance|"
    r"high blood pressure|high cholesterol|low blood sugar)"
)
# "you have logged / had / recorded ..." describes the user's own data: never a diagnosis.
_NOT_A_CONDITION_NEXT = (
    r"(?!(?:logged|had|recorded|noted|reported|mentioned|been|seen|tracked|entered|taken|"
    r"added|shared|uploaded|told|said|described|experienced|felt|missed|skipped|kept|done|"
    r"made|asked|any|no|not)\b)"
)
_YOU_HAVE_CONDITION = (
    r"\byou (?:likely |probably |may |might |could |must )?have (?:got )?"
    rf"{_NOT_A_CONDITION_NEXT}(?:a |an )?(?:[\w-]+ ){{0,2}}{_CONDITION}\b"
)

# Case-insensitive phrase patterns that indicate diagnosis / prescription / causation.
_DENY_PATTERNS: list[str] = [
    _YOU_HAVE_CONDITION,
    r"\byou are (?:suffering|experiencing a condition)\b",
    r"\bsuffering from\b",
    r"\bdiagnos(?:is|ed|e)\b",
    r"\bis a sign of\b",
    r"\bis a symptom of\b",
    r"\bindicat(?:es|ive of)\b.*\b(?:disease|disorder|condition|cancer|diabetes|hypertension)\b",
    r"\bis caused by\b",
    r"\bare caused by\b",
    r"\bcaused by\b",
    r"\bdue to (?:your|the|an?)\b",
    r"\bprescrib",
    r"\byou should take\b",
    r"\byou must take\b",
    r"\bstart taking\b",
    r"\btreatment for\b",
    r"\bto treat\b",
    r"\bwill cure\b",
    r"\bcure for\b",
    r"\byou need (?:medication|to take)\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _DENY_PATTERNS]

# A sentence that clearly relays a doctor's own words ("Dr. Rao diagnosed...",
# "According to your doctor..."). Only exempt when the caller opts in (visit notes).
_ATTRIBUTED = re.compile(
    r"^\s*(?:on [^,]{1,40},\s*)?(?:dr\s+[a-z][\w'-]*(?:\s+[a-z][\w'-]*){0,2}|(?:your|the) doctor)"
    r"\s+(?:has\s+|had\s+)?(?:said|says|told|diagnosed|prescribed|advised|recommended|noted|"
    r"mentioned|explained|asked|started|increased|reduced|stopped|changed|wrote|ordered|"
    r"confirmed)\b"
    r"|\baccording to (?:dr\s+[a-z][\w'-]*|(?:your|the) doctor)\b",
    re.IGNORECASE,
)


def _without_attributed_sentences(text: str) -> str:
    normalized = re.sub(r"\bdr\.", "dr", text, flags=re.IGNORECASE)  # "Dr." isn't a sentence end
    sentences = re.split(r"(?<=[.!?])\s+|\n+", normalized)
    return " ".join(s for s in sentences if not _ATTRIBUTED.search(s))


# Who prescribed a medicine is a fact from the record, not the AI prescribing (Phase 5):
# "Dr. Rao prescribes", "your doctor prescribed", "prescribed by Dr. Rao", "prescriber".
_PRESCRIBER_FACT = re.compile(
    r"\b(?:dr\.?\s+[a-z][\w'-]*|(?:your|the|a|their|his|her) doctor)\s+(?:has\s+|had\s+|who\s+)?prescrib\w*"
    r"|\bprescribed by\b|\bprescribers?\b",
    re.IGNORECASE,
)


def violations(text: str, *, allow_attributed: bool = False) -> list[str]:
    """Return the matched denylist snippets in `text` (empty if clean).

    allow_attributed=True skips sentences that clearly relay a doctor's statement. Use it
    only for text that IS the doctor's words (a confirmed visit note), never for AI text."""
    if not text:
        return []
    if allow_attributed:
        text = _without_attributed_sentences(text)
    text = _PRESCRIBER_FACT.sub(" ", text)
    return [m.group(0) for pat in _COMPILED for m in [pat.search(text)] if m]


def is_diagnostic(text: str, *, allow_attributed: bool = False) -> bool:
    return bool(violations(text, allow_attributed=allow_attributed))


def filter_observations(texts: list[str]) -> list[str]:
    """Drop any observation that reads as a diagnosis/prescription."""
    return [t for t in texts if not is_diagnostic(t)]
