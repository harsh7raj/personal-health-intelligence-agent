"""Red flags, checked in code BEFORE any LLM call (memory.md D30). When one fires, the chat
shows a fixed escalation banner above the reply. Rules come from ROADMAP.md Phase 2; the
helpline numbers (112, Tele-MANAS 14416) must be re-verified before the demo.
"""

import re

EMERGENCY_NUMBER = "112"  # India's single emergency number
TELE_MANAS_NUMBER = "14416"  # Tele-MANAS, national mental-health helpline (24x7, free)

MEDICAL_MESSAGE = (
    "This could need urgent care. Get medical help now: call 112, or go to the nearest "
    "emergency department. Don't wait to see if it passes."
)
MENTAL_HEALTH_MESSAGE = (
    "You don't have to go through this alone. Please talk to someone now: call Tele-MANAS "
    "on 14416 (free, any time), or 112 if you are in immediate danger."
)

_EXERTION = r"(?:stairs?|climb\w*|walk\w*|exert\w*|exercis\w*|running|jogg\w*|gym|cycling|lift\w*)"
_CHEST_WORDS = r"(?:pain\w*|tight\w*|pressure|heav\w*|hurt\w*|ache\w*)"
_CHEST = rf"(?:chest\W+(?:\w+\W+){{0,3}}?{_CHEST_WORDS}|{_CHEST_WORDS}\W+(?:\w+\W+){{0,3}}?chest)"
_RULES: list[tuple[str, str, str]] = [
    ("chest_on_exertion", "chest pain or tightness on exertion",
     rf"{_CHEST}[^.]{{0,60}}\b{_EXERTION}|\b{_EXERTION}[^.]{{0,60}}{_CHEST}"),
    ("chest_pain_warning_signs", "chest pain with warning signs",
     rf"\bcrushing\b[^.]{{0,40}}\bchest\b|{_CHEST}[^.]{{0,80}}\b(?:arm|jaw|neck|sweat\w*|breathless\w*"
     r"|short of breath|nause\w*|vomit\w*)\b"
     rf"|\b(?:arm|jaw)\b[^.]{{0,40}}{_CHEST}"),
    ("fainting", "fainting",
     r"\b(?:faint(?:ed|ing)?|passed out|blacked out|black out|lost consciousness|collapsed)\b"),
    ("stroke_signs", "one-sided weakness, face droop or slurred speech",
     r"\b(?:one side|one-sided|left side|right side)\b[^.]{0,30}\b(?:weak\w*|numb\w*)"
     r"|\b(?:weak\w*|numb\w*)\b[^.]{0,30}\b(?:one side|left side|right side)\b"
     r"|\bface\b[^.]{0,20}\bdroop\w*|\bdroop\w*\b[^.]{0,20}\bface\b|\bslurr\w*\b"),
    ("severe_breathlessness", "severe breathlessness",
     r"\b(?:can'?t|cannot|can not|unable to|struggling to|hard to) (?:breathe|catch my breath)\b"
     r"|\bgasping\b|\bsevere(?:ly)? (?:breathless|short of breath)\b"),
    ("low_sugar_confusion", "low-sugar symptoms with confusion",
     r"\b(?:shak\w*|sweat\w*|dizz\w*|trembl\w*)\b[^.]{0,80}\b(?:confus\w*|disorient\w*|can'?t think)"
     r"|\b(?:confus\w*|disorient\w*)\b[^.]{0,80}\b(?:shak\w*|sweat\w*|low sugar)"),
]
_SELF_HARM = re.compile(
    r"\b(?:kill(?:ing)? myself|suicid\w*|end(?:ing)? my life|self[- ]?harm\w*|hurt(?:ing)? myself"
    r"|don'?t want to (?:live|be alive)|want to die|no reason to live)\b",
    re.IGNORECASE,
)
_COMPILED = [(k, label, re.compile(p, re.IGNORECASE)) for k, label, p in _RULES]

_BP = re.compile(r"\b(\d{2,3})\s*(?:/|over)\s*(\d{2,3})\b")
_GLUCOSE = re.compile(r"\b(?:sugar|glucose|bg|gl)\D{0,12}(\d{2,3})\b", re.IGNORECASE)
_SPO2 = re.compile(r"\b(?:spo2|sp02|oxygen|o2|sat\w*)\D{0,12}(\d{2,3})\b", re.IGNORECASE)


def _reading_flags(text: str, readings: list[tuple[str, float]]) -> list[tuple[str, str]]:
    values: dict[str, list[float]] = {}
    for vt, v in readings:
        values.setdefault(vt, []).append(v)
    for m in _BP.finditer(text):  # also read numbers straight from the text (no LLM needed)
        values.setdefault("bp_systolic", []).append(float(m.group(1)))
        values.setdefault("bp_diastolic", []).append(float(m.group(2)))
    for m in _GLUCOSE.finditer(text):
        values.setdefault("blood_glucose", []).append(float(m.group(1)))
    for m in _SPO2.finditer(text):
        values.setdefault("spo2", []).append(float(m.group(1)))
    hits: list[tuple[str, str]] = []
    if any(v >= 180 for v in values.get("bp_systolic", [])) or any(
        v >= 120 for v in values.get("bp_diastolic", [])
    ):
        hits.append(("bp_180_120", "blood pressure at or above 180/120"))
    if any(v < 54 for v in values.get("blood_glucose", [])):
        hits.append(("glucose_below_54", "blood glucose below 54 mg/dL"))
    if any(50 <= v < 92 for v in values.get("spo2", [])):  # <50 is almost surely not SpO2
        hits.append(("spo2_below_92", "oxygen saturation below 92%"))
    return hits


def check(text: str, readings: list[tuple[str, float]] | None = None) -> dict | None:
    """Escalation for a message (+ readings parsed from it), or None.
    {"kind": "medical"|"mental_health", "reasons": [...], "message": str, "call": str}"""
    t = text or ""
    if _SELF_HARM.search(t):
        return {"kind": "mental_health", "reasons": ["thoughts of self-harm"],
                "message": MENTAL_HEALTH_MESSAGE, "call": TELE_MANAS_NUMBER}
    reasons = [label for _k, label, pat in _COMPILED if pat.search(t)]
    reasons += [label for _k, label in _reading_flags(t, readings or [])]
    if not reasons:
        return None
    return {"kind": "medical", "reasons": reasons, "message": MEDICAL_MESSAGE,
            "call": EMERGENCY_NUMBER}
