"""Non-diagnostic language guard. The system observes & explains — it never diagnoses,
asserts a condition as fact, states causation, or recommends treatment. Conservative
denylist so legitimate trend/pattern observations are not dropped."""

import re

# Case-insensitive phrase patterns that indicate diagnosis / prescription / causation.
_DENY_PATTERNS: list[str] = [
    r"\byou have\b",
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
    r"\byou (?:likely |probably |may )?have\b",
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


def violations(text: str) -> list[str]:
    """Return the matched denylist snippets in `text` (empty if clean)."""
    if not text:
        return []
    return [m.group(0) for pat in _COMPILED for m in [pat.search(text)] if m]


def is_diagnostic(text: str) -> bool:
    return bool(violations(text))


def filter_observations(texts: list[str]) -> list[str]:
    """Drop any observation that reads as a diagnosis/prescription."""
    return [t for t in texts if not is_diagnostic(t)]
