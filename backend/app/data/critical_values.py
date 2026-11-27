"""Lab values that warrant contacting a doctor the same day (ROADMAP.md Phase 4, memory.md D33).

Decided in code, never by the LLM. Limits are in the listed unit; `lab_values.to_unit`
converts what the lab printed. These follow common laboratory critical-value lists, set on the
cautious side because the banner only says "contact your doctor today".
PENDING REVIEW: get these checked by the project guide or a doctor before the demo.
"""

CRITICAL: dict[str, dict] = {
    "potassium": {"unit": "mmol/L", "low": 3.0, "high": 6.0},
    "sodium": {"unit": "mmol/L", "low": 125, "high": 155},
    "fasting_glucose": {"unit": "mg/dL", "low": 54, "high": 400},
    "random_glucose": {"unit": "mg/dL", "low": 54, "high": 400},
    "postprandial_glucose": {"unit": "mg/dL", "low": 54, "high": 400},
    "hemoglobin": {"unit": "g/dL", "low": 7.0, "high": None},
    "platelet_count": {"unit": "/µL", "low": 50_000, "high": None},
}

MESSAGE = ("{test} is {value} {unit}, beyond the level where labs advise contacting a doctor "
           "the same day. Please contact your doctor today.")
