"""One canonical name per symptom, so "headache", "headaches" and "head pain" are tracked
as one problem. Deliberately small and conservative: only true equivalents map together.
Related but different symptoms stay apart (a migraine is not a headache; one-sided
weakness is not fatigue). Extend it as real logs show new variants.
"""

SYNONYMS: dict[str, str] = {
    # headache
    "headaches": "headache", "head ache": "headache", "head pain": "headache",
    "pain in head": "headache", "head hurts": "headache", "sore head": "headache",
    # migraine (kept separate from headache)
    "migraines": "migraine", "migraine headache": "migraine", "migraine attack": "migraine",
    # stomach
    "tummy ache": "abdominal pain", "stomach ache": "abdominal pain", "stomachache": "abdominal pain",
    "stomach pain": "abdominal pain", "belly pain": "abdominal pain", "abdomen pain": "abdominal pain",
    "throwing up": "vomiting", "threw up": "vomiting", "puking": "vomiting", "vomit": "vomiting",
    "nauseous": "nausea", "queasy": "nausea", "feeling sick": "nausea",
    "loose motions": "diarrhea", "loose stools": "diarrhea", "diarrhoea": "diarrhea",
    # energy
    "tired": "fatigue", "tiredness": "fatigue", "exhaustion": "fatigue", "exhausted": "fatigue",
    "low energy": "fatigue", "lethargy": "fatigue", "feeling tired": "fatigue",
    # dizziness
    "dizzy": "dizziness", "light headed": "dizziness", "lightheaded": "dizziness",
    "lightheadedness": "dizziness", "giddiness": "dizziness", "giddy": "dizziness",
    # breathing and heart
    "short of breath": "shortness of breath", "breathlessness": "shortness of breath",
    "breathless": "shortness of breath", "difficulty breathing": "shortness of breath",
    "tight chest": "chest tightness", "chest feels tight": "chest tightness",
    "heart racing": "palpitations", "racing heart": "palpitations",
    "heart pounding": "palpitations", "pounding heart": "palpitations",
    # low-sugar-like symptoms (named as reported, not interpreted)
    "shaky": "shakiness", "shaking": "shakiness", "trembling": "shakiness", "jittery": "shakiness",
    "sweaty": "sweating", "sweats": "sweating", "cold sweat": "sweating", "cold sweats": "sweating",
    # throat and nose
    "throat pain": "sore throat", "scratchy throat": "sore throat",
    "running nose": "runny nose", "blocked nose": "nasal congestion", "stuffy nose": "nasal congestion",
    # back and joints
    "backache": "back pain", "back ache": "back pain",
    # swelling
    "swollen ankles": "ankle swelling", "ankles swollen": "ankle swelling",
    "swelling in ankles": "ankle swelling", "puffy ankles": "ankle swelling",
    # thyroid-story symptoms (Priya)
    "hair fall": "hair loss", "hair falling": "hair loss", "losing hair": "hair loss",
    "always cold": "feeling cold", "cold all the time": "feeling cold",
    "gained weight": "weight gain", "put on weight": "weight gain",
}

CANONICAL: frozenset[str] = frozenset(SYNONYMS.values())


def canonical_symptom(name: str | None) -> str:
    """Canonical lowercase name for a symptom; unknown names come back tidied, unchanged."""
    n = " ".join((name or "").lower().replace("-", " ").split()).strip(" .")
    if n in SYNONYMS:
        return SYNONYMS[n]
    if n.endswith("s") and n[:-1] in CANONICAL:  # simple plural of a known name
        return n[:-1]
    return n
