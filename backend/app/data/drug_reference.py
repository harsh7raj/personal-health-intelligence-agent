"""Curated, source-cited per-drug reference information (general, NOT personalized).

Every entry is general consumer reference information drawn from MedlinePlus
(U.S. National Library of Medicine, https://medlineplus.gov/druginformation.html).
It is NOT advice and NOT specific to any patient. Phrasing is kept factual and
non-diagnostic (passes app.services.language_guard). No LLM is involved — this is a
hand-curated lookup keyed by RxNorm-normalized ingredient name.

For drugs not in this table the UI shows: general reference not available — consult
the label or a pharmacist.
"""

SOURCE = "MedlinePlus (U.S. National Library of Medicine)"
SOURCE_URL = "https://medlineplus.gov/druginformation.html"


def _e(used_for: str, timing: str, considerations: str) -> dict:
    return {
        "used_for": used_for,
        "timing": timing,
        "considerations": considerations,
        "source": SOURCE,
        "provenance": "medlineplus",
    }


# Keyed by RxNorm-normalized (lowercased) ingredient name.
DRUG_REFERENCE: dict[str, dict] = {
    "amlodipine": _e(
        "A calcium channel blocker. Commonly used for high blood pressure and certain types of chest pain (angina).",
        "Usually taken once a day, with or without food, at about the same time each day.",
        "Grapefruit can raise its levels in the body. Rising slowly from sitting can help with dizziness.",
    ),
    "simvastatin": _e(
        "A statin. Commonly used to help lower cholesterol and reduce cardiovascular risk.",
        "Usually taken once a day in the evening, with or without food.",
        "Large amounts of grapefruit juice are generally avoided. Unexplained muscle pain or weakness is worth reporting to a clinician.",
    ),
    "atorvastatin": _e(
        "A statin. Commonly used to help lower cholesterol and reduce cardiovascular risk.",
        "Usually taken once a day, with or without food, and can be taken at any time of day.",
        "Large amounts of grapefruit juice are generally limited. Unexplained muscle pain is worth reporting.",
    ),
    "cholecalciferol": _e(
        "A form of vitamin D. Commonly used to support bone health and to address low vitamin D levels.",
        "Often taken with a meal containing some fat, which can aid absorption.",
        "Very high doses over long periods can raise calcium too much; intake is usually kept within recommended limits.",
    ),
    "vitamin d": _e(
        "Vitamin D. Commonly used to support bone health and to address low vitamin D levels.",
        "Often taken with a meal containing some fat, which can aid absorption.",
        "Very high doses over long periods can raise calcium too much; intake is usually kept within recommended limits.",
    ),
    "lisinopril": _e(
        "An ACE inhibitor. Commonly used for high blood pressure and heart failure.",
        "Usually taken once a day, with or without food, at the same time each day.",
        "A dry cough is a known consideration with this class. Potassium-containing salt substitutes are often discussed with a clinician.",
    ),
    "losartan": _e(
        "An angiotensin receptor blocker (ARB). Commonly used for high blood pressure.",
        "Usually taken once a day, with or without food.",
        "Potassium levels are sometimes monitored with this class.",
    ),
    "metformin": _e(
        "Commonly used to help manage blood sugar in type 2 diabetes.",
        "Usually taken with meals to reduce stomach upset.",
        "Mild stomach upset is common at first and often eases over time. Staying hydrated is generally advised.",
    ),
    "hydrochlorothiazide": _e(
        "A thiazide diuretic ('water pill'). Commonly used for high blood pressure and fluid retention.",
        "Usually taken in the morning to avoid nighttime urination, with or without food.",
        "Can affect potassium levels and hydration, which clinicians sometimes monitor.",
    ),
    "levothyroxine": _e(
        "A thyroid hormone. Commonly used for an underactive thyroid (low thyroid hormone).",
        "Usually taken on an empty stomach, 30–60 minutes before breakfast, with water.",
        "Calcium, iron, and some antacids can reduce absorption and are usually spaced several hours apart.",
    ),
    "omeprazole": _e(
        "A proton pump inhibitor. Commonly used for acid reflux and related stomach conditions.",
        "Usually taken before a meal, often 30–60 minutes before breakfast.",
        "Long-term use is periodically reviewed with a clinician.",
    ),
    "acetylsalicylic acid": _e(
        "Commonly used for pain and fever, and at low doses for cardiovascular protection.",
        "Usually taken with food or a full glass of water to reduce stomach irritation.",
        "Can increase bleeding risk, especially alongside other blood thinners.",
    ),
    "aspirin": _e(
        "Commonly used for pain and fever, and at low doses for cardiovascular protection.",
        "Usually taken with food or a full glass of water to reduce stomach irritation.",
        "Can increase bleeding risk, especially alongside other blood thinners.",
    ),
    "ibuprofen": _e(
        "A nonsteroidal anti-inflammatory (NSAID). Commonly used for pain, inflammation, and fever.",
        "Usually taken with food or milk to reduce stomach upset.",
        "Can affect the stomach and kidneys with prolonged or high-dose use.",
    ),
    "warfarin": _e(
        "A blood thinner (anticoagulant). Commonly used to lower the risk of harmful blood clots.",
        "Usually taken once a day at the same time, often in the evening.",
        "Vitamin K intake and many medicines affect it; regular blood tests (INR) are common.",
    ),
    "metoprolol": _e(
        "A beta blocker. Commonly used for high blood pressure, chest pain, and some heart-rhythm conditions.",
        "Often taken with or right after food, at the same time each day.",
        "Stopping suddenly is generally avoided and changes are usually made gradually.",
    ),
}


def get_reference(normalized_name: str) -> dict | None:
    return DRUG_REFERENCE.get((normalized_name or "").strip().lower())
