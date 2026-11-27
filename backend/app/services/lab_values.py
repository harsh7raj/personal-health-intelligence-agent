"""Lab values in code (memory.md D33): canonical test keys, printed reference ranges as numbers,
flags computed from them, critical values, and how far a value sits outside its range.
The LLM extracts what is printed; everything decided about a value is decided here."""

import re

from app.data.critical_values import CRITICAL, MESSAGE
from app.data.lab_glossary import GLOSSARY, key_for

_N = r"\d+(?:\.\d+)?"


def to_number(value: object) -> float | None:
    """'142', '1,50,000', '6.9 %' -> float; '<0.5', 'Nil', 'Positive' -> None."""
    if isinstance(value, (int, float)):
        return float(value)
    m = re.fullmatch(rf"\s*({_N})\s*[a-zA-Z%/µ^0-9.]*\s*", str(value or "").replace(",", ""))
    return float(m.group(1)) if m else None


def _one_range(t: str) -> tuple[float | None, float | None] | None:
    if m := re.search(rf"({_N})\s*(?:-|to)\s*({_N})", t):
        return float(m.group(1)), float(m.group(2))
    if m := re.search(rf"(?:<=?|≤|up\s*to|less than|below)\s*({_N})", t, re.IGNORECASE):
        return None, float(m.group(1))
    if m := re.search(rf"(?:>=?|≥|more than|greater than|above)\s*({_N})", t, re.IGNORECASE):
        return float(m.group(1)), None
    return None


def parse_range(text: str | None) -> tuple[float | None, float | None]:
    """A printed reference range as (low, high); (None, None) if it can't be read safely.

    '4.0 - 5.6' -> (4.0, 5.6); '<200' -> (None, 200); '>40' -> (40, None). A range with
    several bands ('Desirable <200; Borderline 200-239; High >=240') uses the band marked
    normal/desirable/optimal, and is skipped if none is marked."""
    if not text:
        return None, None
    t = text.replace("–", "-").replace("—", "-").replace(",", "")
    bands = [b for b in re.split(r"[;\n|]", t) if b.strip()]
    if len(bands) > 1 or len(re.findall(_N, t)) > 2:
        marked = [b for b in bands if re.search(r"normal|desirable|optimal|non.?diabetic|reference", b, re.I)]
        if len(marked) != 1:
            return None, None
        t = marked[0]
    return _one_range(t) or (None, None)


def code_flag(value: float | None, low: float | None, high: float | None) -> str | None:
    if value is None or (low is None and high is None):
        return None
    if low is not None and value < low:
        return "low"
    if high is not None and value > high:
        return "high"
    return "normal"


def to_unit(key: str, value: float, unit: str | None) -> float | None:
    """`value` in the unit CRITICAL lists for `key`, or None if the printed unit is unclear."""
    u = (unit or "").lower().replace(" ", "").replace("μ", "µ")
    if key.endswith("glucose"):
        return value * 18 if "mmol" in u else value
    if key in ("potassium", "sodium"):
        return value
    if key == "hemoglobin":
        return value / 10 if u in ("g/l", "gm/l") else value
    if key == "platelet_count":
        if "lakh" in u:
            return value * 100_000
        if any(s in u for s in ("10^3", "10³", "x103", "thou", "k/", "10^9", "10*3", "10e3")):
            return value * 1000
        return value if value >= 1000 else None
    return value


def critical_check(key: str | None, value: float | None, unit: str | None, name: str) -> dict | None:
    limits = CRITICAL.get(key or "")
    if not limits or value is None:
        return None
    v = to_unit(key, value, unit)
    if v is None:
        return None
    if limits["low"] is not None and v < limits["low"]:
        direction = "low"
    elif limits["high"] is not None and v > limits["high"]:
        direction = "high"
    else:
        return None
    shown = f"{value:g}"
    return {"direction": direction, "limit": limits[direction], "limit_unit": limits["unit"],
            "message": MESSAGE.format(test=name, value=shown, unit=unit or "").replace("  ", " ")}


def enrich(values: list[dict]) -> list[dict]:
    """Add test_key, range_low/high, a code-computed flag and any critical finding to each
    extracted value. The LLM's flag is kept only when the range can't be read as numbers."""
    out: list[dict] = []
    for v in values:
        key = key_for(v.get("test_name"))
        low, high = parse_range(v.get("reference_range"))
        num = to_number(v.get("value"))
        flag = code_flag(num, low, high) or v.get("flag") or "unknown"
        out.append({**v, "test_key": key, "range_low": low, "range_high": high, "flag": flag,
                    "critical": critical_check(key, num, v.get("unit"), v.get("test_name") or "")})
    return out


def outside_by(v: dict) -> dict | None:
    """How far a value sits outside its numeric range: {'direction', 'amount', 'percent'}."""
    num = to_number(v.get("value"))
    low, high = v.get("range_low"), v.get("range_high")
    if num is None:
        return None
    if high is not None and num > high:
        return {"direction": "above", "amount": round(num - high, 2),
                "percent": round((num - high) / high * 100, 1) if high else None}
    if low is not None and num < low:
        return {"direction": "below", "amount": round(low - num, 2),
                "percent": round((low - num) / low * 100, 1) if low else None}
    return None


def display_name(key: str | None, printed: str | None) -> str:
    return GLOSSARY[key]["name"] if key in GLOSSARY else (printed or "Test")
