"""Safety-boundary tests for medication intelligence: interactions must come ONLY
from the local DDInter table, a missing pair must read 'no known interaction found'
(never 'safe'), and a disclaimer must always accompany the output."""

from app.models.clinical import Medication
from app.models.patient import Patient
from app.models.reference import DrugInteraction
from app.models.user import User
from app.services.med_intel import build_medication_intelligence

_c = {"n": 0}


def _patient_with_meds(db, names: list[str]) -> int:
    _c["n"] += 1
    u = User(email=f"med{_c['n']}@x.com", password_hash="x", role="patient")
    db.add(u)
    db.flush()
    p = Patient(user_id=u.id, name="Med Test")
    db.add(p)
    db.flush()
    for n in names:
        db.add(Medication(patient_id=p.id, name=n, active=True))
    db.flush()
    return p.id


def test_known_interaction_is_sourced_and_unknown_pair_is_not_called_safe(db, monkeypatch):
    # No network: normalization is just lowercasing here.
    monkeypatch.setattr(
        "app.services.med_intel.normalize_ingredient", lambda n: n.strip().lower()
    )
    # Keep tests offline: no LLM fallback calls for uncurated drugs.
    monkeypatch.setattr("app.services.med_intel.ai_reference", lambda n: None)
    # The ONLY interaction the system knows about is the one we put in the table.
    db.add(
        DrugInteraction(
            drug_lo="amlodipine", drug_hi="simvastatin",
            name_a="Amlodipine", name_b="Simvastatin", level="Major", source="DDInter 2.0",
        )
    )
    pid = _patient_with_meds(db, ["Amlodipine", "Simvastatin", "Vitamin D"])
    db.flush()

    out = build_medication_intelligence(db, pid)
    by_pair = {frozenset((i["drug_a"], i["drug_b"])): i for i in out["interactions"]}

    known = by_pair[frozenset(("Amlodipine", "Simvastatin"))]
    assert known["status"] == "known"
    assert known["level"] == "Major"
    assert known["source"] == "DDInter 2.0"

    # A pair with no row must be explicit "no known interaction" — never "safe".
    unknown = by_pair[frozenset(("Amlodipine", "Vitamin D"))]
    assert unknown["status"] == "none_known"
    assert "no known interaction found in ddinter" in unknown["note"].lower()
    assert "safe" not in unknown["note"].lower()

    assert out["known_interaction_count"] == 1
    assert out["disclaimer"] and "not medical advice" in out["disclaimer"].lower()


def test_brand_names_canonicalize_before_lookup(db):
    """Regression: brand names must resolve to their ingredient via the offline alias
    map BEFORE the DDInter lookup, so 'Xanax'=='Alprazolam' (same drug) and a brand
    pair surfaces the real sourced severity instead of 'no known interaction'."""
    db.add(
        DrugInteraction(
            drug_lo="amlodipine", drug_hi="simvastatin",
            name_a="Amlodipine", name_b="Simvastatin", level="Major", source="DDInter 2.0",
        )
    )
    pid = _patient_with_meds(db, ["Xanax", "Alprazolam", "Norvasc", "Zocor"])
    db.flush()
    out = build_medication_intelligence(db, pid)
    by_pair = {frozenset((i["drug_a"], i["drug_b"])): i for i in out["interactions"]}

    # Brand vs generic of the same drug → recognized as same drug, NOT a flaggable pair.
    assert by_pair[frozenset(("Xanax", "Alprazolam"))]["status"] == "same_drug"

    # Brand names (Norvasc=amlodipine, Zocor=simvastatin) resolve and match the sourced row.
    branded = by_pair[frozenset(("Norvasc", "Zocor"))]
    assert branded["status"] == "known"
    assert branded["level"] == "Major"


def test_no_interaction_is_ever_invented(db, monkeypatch):
    # Empty interaction table → every pair must come back none_known, never fabricated.
    monkeypatch.setattr(
        "app.services.med_intel.normalize_ingredient", lambda n: n.strip().lower()
    )
    # Keep tests offline: no LLM fallback calls for uncurated drugs.
    monkeypatch.setattr("app.services.med_intel.ai_reference", lambda n: None)
    pid = _patient_with_meds(db, ["DrugX", "DrugY"])
    db.flush()
    out = build_medication_intelligence(db, pid)
    assert out["known_interaction_count"] == 0
    assert all(i["status"] == "none_known" for i in out["interactions"])


# ---------- Part 2: LLM fallback for per-drug REFERENCE info only ----------


def _stub_llm(monkeypatch, payload: dict):
    """Make the stubbed LLM return `payload`, and reset the module cache so the stub is
    actually exercised instead of a prior result. conftest runs with no LLM configured
    (offline), so we also satisfy the availability check inside ai_reference."""
    import app.services.drug_reference_ai as ai

    ai._cache.clear()
    monkeypatch.setattr(ai, "is_available", lambda: True)
    monkeypatch.setattr(ai, "llm_json", lambda task, system, user, **_kw: payload)


def test_ai_reference_used_only_for_uncurated_drug_and_clearly_labelled(db, monkeypatch):
    """A curated drug keeps its MedlinePlus provenance; an uncurated drug falls through
    to the LLM reference, which is labelled provenance='ai' with a distinct source."""
    monkeypatch.setattr(
        "app.services.med_intel.normalize_ingredient", lambda n: n.strip().lower()
    )
    _stub_llm(
        monkeypatch,
        {
            "used_for": "commonly used for nerve pain and seizures",
            "timing": "usually taken with food",
            "considerations": "drowsiness is a common general consideration",
        },
    )
    # amlodipine = curated (MedlinePlus); gabapentin = not curated → LLM fallback.
    pid = _patient_with_meds(db, ["amlodipine", "gabapentin"])
    db.flush()
    out = build_medication_intelligence(db, pid)
    refs = {m["name"]: m["reference"] for m in out["medications"]}

    assert refs["amlodipine"]["provenance"] == "medlineplus"
    assert "MedlinePlus" in refs["amlodipine"]["source"]

    ai_ref = refs["gabapentin"]
    assert ai_ref["provenance"] == "ai"
    assert "AI-generated" in ai_ref["source"]
    assert ai_ref["source"] != refs["amlodipine"]["source"]
    assert ai_ref["used_for"] == "commonly used for nerve pain and seizures"


def test_ai_reference_drops_diagnostic_sounding_content(db, monkeypatch):
    """The non-diagnostic guard applies to LLM output too: diagnostic phrasing is
    dropped rather than shown, leaving the medication with no reference."""
    monkeypatch.setattr(
        "app.services.med_intel.normalize_ingredient", lambda n: n.strip().lower()
    )
    _stub_llm(
        monkeypatch,
        {
            "used_for": "used to treat your high blood pressure",  # diagnostic/personalized
            "timing": "take once a day",
            "considerations": "you should take this every morning",
        },
    )
    pid = _patient_with_meds(db, ["gabapentin"])
    db.flush()
    out = build_medication_intelligence(db, pid)
    assert out["medications"][0]["reference"] is None


def test_llm_never_supplies_interaction_verdicts(db, monkeypatch):
    """Hard boundary: even with the LLM returning content, interactions come solely from
    DDInter. An uncurated pair with no DDInter row stays 'none_known', never invented."""
    monkeypatch.setattr(
        "app.services.med_intel.normalize_ingredient", lambda n: n.strip().lower()
    )
    _stub_llm(
        monkeypatch,
        {
            "used_for": "commonly used for nerve pain",
            "timing": "usually taken with food",
            "considerations": "a common general consideration",
        },
    )
    pid = _patient_with_meds(db, ["gabapentin", "sertraline"])
    db.flush()
    out = build_medication_intelligence(db, pid)
    assert out["known_interaction_count"] == 0
    assert all(i["status"] == "none_known" for i in out["interactions"])
    assert all(i["source"] != "AI" for i in out["interactions"])
