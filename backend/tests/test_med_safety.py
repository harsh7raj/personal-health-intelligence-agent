"""Medication safety (D35, D36): three levels with DDInter winning, verbatim label quotes, the AI
flag switch, never an all-clear, and the patient-aware checks. Labels/classes are inserted as
cached rows; LLM and network are always stubbed."""

from datetime import date, datetime, time, timedelta, timezone

import pytest

import app.services.brand_generic as bg
import app.services.med_safety as ms
from app.core import clock
from app.core.config import get_settings
from app.models.clinical import Medication, MedicationEvent, VitalReading
from app.models.drugs import DrugClassInfo, DrugLabel, MedCheckRun
from app.models.patient import Patient
from app.models.records import Entry
from app.models.reference import DrugInteraction
from app.models.user import User

LEVO_INTERACTIONS = (
    "7 DRUG INTERACTIONS Many drugs can exert effects on thyroid hormone pharmacokinetics and metabolism. "
    "Drug or Drug Class Effect Phosphate Binders (e.g., calcium carbonate, ferrous sulfate, sevelamer) "
    "Phosphate binders may bind to levothyroxine. Administer levothyroxine sodium tablets at least 4 hours "
    "apart from these agents. Orlistat Monitor patients treated concomitantly with orlistat."
)


def _patient(db, email="ms@x.com") -> int:
    u = User(email=email, password_hash="x", role="patient")
    db.add(u)
    db.flush()
    p = Patient(user_id=u.id, name="Med")
    db.add(p)
    db.flush()
    return p.id


def _label(db, ingredient, **sections):
    db.add(DrugLabel(ingredient=ingredient, found=True, set_id=f"set-{ingredient}", title=ingredient.upper(),
                     sections=sections))


def _classes(db, ingredient, *classes):
    db.add(DrugClassInfo(ingredient=ingredient, classes=[{"id": n, "name": n, "type": t} for t, n in classes]))


def _med(db, pid, name, ingredients, times=(), prescriber=None, started=None) -> Medication:
    m = Medication(patient_id=pid, name=name, ingredients=list(ingredients), dose_times=list(times),
                   prescriber=prescriber, started_on=started)
    db.add(m)
    db.flush()
    return m


@pytest.fixture
def no_llm(monkeypatch):
    monkeypatch.setattr(ms, "is_available", lambda: False)


@pytest.fixture
def llm(monkeypatch):
    replies: dict = {}
    monkeypatch.setattr(ms, "is_available", lambda: True)
    monkeypatch.setattr(ms, "llm_json", lambda task, system, user, **k: replies[task](user))
    return replies


def _all_text(result) -> str:
    return " ".join(str(v) for f in result["findings"] for v in (f["explanation"], f["title"], f["quote"]))


def test_ddinter_wins_over_the_label(db, no_llm):
    pid = _patient(db)
    _label(db, "levothyroxine", drug_interactions=LEVO_INTERACTIONS)
    db.add(DrugInteraction(drug_lo="calcium carbonate", drug_hi="levothyroxine", name_a="a", name_b="b",
                           level="Moderate"))
    _med(db, pid, "Thyronorm 75", ["levothyroxine"])
    _med(db, pid, "Shelcal 500", ["calcium carbonate"])
    r = ms.run(db, pid)
    [f] = [f for f in r["findings"] if f["kind"] == "interaction"]
    assert f["level"] == "verified" and f["severity"] == "Moderate" and f["source"]["name"] == "DDInter 2.0"
    assert r["pairs"][0]["message"] is None


def test_label_level_quotes_code_found_text_and_rejects_invented_quotes(db, llm):
    pid = _patient(db)
    _label(db, "levothyroxine", drug_interactions=LEVO_INTERACTIONS)
    _med(db, pid, "Thyronorm 75", ["levothyroxine"])
    _med(db, pid, "Shelcal 500", ["calcium carbonate"])
    llm["med_label"] = lambda _u: {"index": 0, "quote": "Calcium carbonate is completely safe with levothyroxine.",
                                    "applies": True, "explanation": "These are safe together.",
                                    "questions": ["Should I space them out?"]}
    [f] = [f for f in ms.run(db, pid)["findings"] if f["kind"] == "interaction"]
    assert f["level"] == "label" and "Phosphate binders may bind to levothyroxine" in f["quote"]
    assert "safe" not in f["explanation"].lower()  # unsafe wording replaced by code's own
    assert f["source"]["url"].endswith("setid=set-levothyroxine")
    # A real verbatim excerpt from the AI is accepted.
    llm["med_label"] = lambda _u: {"index": 0, "quote": "Phosphate binders may bind to levothyroxine.",
                                    "applies": True, "explanation": "Calcium can reduce how much thyroid medicine "
                                    "is absorbed.", "questions": ["Should I space them out?"]}
    [f] = [f for f in ms.run(db, pid)["findings"] if f["kind"] == "interaction"]
    assert f["quote"] == "Phosphate binders may bind to levothyroxine." and "absorbed" in f["explanation"]


def test_class_matches_can_be_dropped_only_by_the_ai(db, llm, monkeypatch):
    pid = _patient(db)
    _label(db, "simvastatin", drug_interactions="Avoid use with strong CYP3A4 inhibitors because of muscle risk.")
    _classes(db, "clarithromycin", ("MOA", "Cytochrome P450 3A4 Inhibitors"))
    _med(db, pid, "Simvastatin", ["simvastatin"])
    _med(db, pid, "Clarithromycin", ["clarithromycin"])
    llm["med_label"] = lambda _u: {"index": 0, "quote": "", "applies": True, "explanation": "", "questions": []}
    [f] = [f for f in ms.run(db, pid)["findings"] if f["kind"] == "interaction"]
    assert f["via"] == "class" and "CYP3A4 inhibitors" in f["quote"]
    llm["med_label"] = lambda _u: {"index": 0, "applies": False}
    r = ms.run(db, pid)
    assert [f for f in r["findings"] if f["kind"] == "interaction"] == []
    assert r["pairs"][0]["message"] == ms.NO_FINDING


def test_ai_flags_are_switchable_unverified_and_never_an_all_clear(db, llm, monkeypatch):
    pid = _patient(db)
    _med(db, pid, "Aspirin", ["aspirin"])
    _med(db, pid, "Fish oil", ["omega-3 acid ethyl esters"])
    llm["med_ai_flag"] = lambda _u: {"flags": [
        {"medicine_1": "aspirin", "medicine_2": "omega-3 acid ethyl esters", "concern": "Both can affect bleeding.",
         "reasoning": "Effects on clotting may add up."}]}
    monkeypatch.setattr(get_settings(), "MED_AI_FLAGS_ENABLED", False)
    r = ms.run(db, pid)
    assert r["findings"] == [] and r["pairs"][0]["message"] == "No known interaction found in our sources. " \
                                                               "Confirm with your pharmacist."
    monkeypatch.setattr(get_settings(), "MED_AI_FLAGS_ENABLED", True)
    [f] = ms.run(db, pid)["findings"]
    assert f["level"] == "ai" and f["level_label"] == "AI flag (unverified)"
    assert "Unverified, ask your pharmacist" in f["explanation"] and ms.DONT_CHANGE in f["explanation"]
    llm["med_ai_flag"] = lambda _u: {"flags": [{"medicine_1": "aspirin", "medicine_2": "omega-3 acid ethyl esters",
                                                 "concern": "These are safe to take together.", "reasoning": "x"}]}
    r = ms.run(db, pid)
    assert r["findings"] == [] and r["pairs"][0]["message"] == ms.NO_FINDING  # the all-clear is dropped


def test_duplicates_timing_conditions_side_effects_and_alcohol(db, no_llm):
    pid = _patient(db)
    today = clock.today()
    _label(db, "levothyroxine", drug_interactions=LEVO_INTERACTIONS)
    _label(db, "glimepiride",
           warnings="5 WARNINGS AND PRECAUTIONS Hypoglycemia: All sulfonylureas, including glimepiride, can cause "
                    "severe hypoglycemia.",
           adverse_reactions="In clinical trials, the most common adverse reactions with glimepiride were "
                             "hypoglycemia, dizziness, asthenia, headache, and nausea.")
    _label(db, "metformin", warnings="Alcohol is known to potentiate the effect of metformin on lactate metabolism.")
    _classes(db, "amlodipine", ("EPC", "Calcium Channel Blocker"))
    _classes(db, "nifedipine", ("EPC", "Calcium Channel Blocker"))
    _med(db, pid, "Thyronorm 75", ["levothyroxine"], times=["07:30"])
    _med(db, pid, "Shelcal 500", ["calcium carbonate"], times=["09:00"])
    _med(db, pid, "Amlodipine", ["amlodipine"], prescriber="Dr. Rao")
    _med(db, pid, "Nifedipine", ["nifedipine"], prescriber="Dr. Mehta")
    glim = _med(db, pid, "Glimepiride", ["glimepiride"], started=today - timedelta(days=400))
    _med(db, pid, "Metformin", ["metformin"])
    changed = today - timedelta(days=60)
    db.add(MedicationEvent(patient_id=pid, medication_id=glim.id, medication_name="Glimepiride",
                           event_type="dose_change", event_date=changed, old_dose="1 mg", new_dose="2 mg",
                           source="manual"))
    when = datetime.combine(changed + timedelta(days=30), time(15), tzinfo=timezone.utc)
    db.add(Entry(patient_id=pid, type="symptom", raw_text="shaky and dizzy", occurred_at=when,
                 structured={"name": "shakiness", "other_symptoms": ["dizziness"]}))
    db.add(Entry(patient_id=pid, type="note", raw_text="two beers", occurred_at=when,
                 structured={"context_tags": ["alcohol"]}))
    db.add(VitalReading(patient_id=pid, vital_type="blood_glucose", value=62, unit="mg/dL", recorded_at=when))
    db.flush()

    r = ms.run(db, pid)
    kinds = {f["kind"]: f for f in r["findings"]}
    dup = next(f for f in r["findings"] if f["kind"] == "duplicate")
    assert "Calcium Channel Blocker" in dup["explanation"] and "Dr. Rao" in dup["explanation"]
    t = kinds["timing"]
    assert "4 hours apart" in t["explanation"] and "1 h 30 min" in t["explanation"]
    assert "calcium carbonate" in t["quote"] and "at least 4 hours apart" in t["quote"]
    assert kinds["condition"]["quote"].startswith("5 WARNINGS AND PRECAUTIONS Hypoglycemia: All sulfonylureas")
    assert kinds["condition"]["evidence"][0]["value"] == 62
    se = kinds["side_effect"]
    assert se["symptom"] == "dizziness" and "30 days after the dose change (1 mg to 2 mg)" in se["explanation"]
    assert "alcohol" in kinds["alcohol"]["quote"].lower()
    assert all(f["id"].startswith("F") for f in r["findings"])
    assert "safe" not in _all_text(r).lower()
    assert ms.side_effects_for(db, pid, "dizzy")[0]["id"] == "S1"


def test_check_new_medicine_and_brands(db, no_llm, monkeypatch):
    pid = _patient(db)
    _med(db, pid, "Metformin", ["metformin"])
    db.add(DrugInteraction(drug_lo="ibuprofen", drug_hi="metformin", name_a="a", name_b="b", level="Moderate"))
    db.flush()
    known = {"ibuprofen": ["ibuprofen"], "calcium carbonate": ["calcium carbonate"]}
    monkeypatch.setattr(ms.rxnorm, "lookup", lambda n: {"status": "found", "ingredients": known[n.lower()]}
                        if n.lower() in known else {"status": "not_found", "ingredients": []})
    monkeypatch.setattr(bg.rxnorm, "lookup", ms.rxnorm.lookup)
    out = ms.check_new_medicine(db, pid, "Ibuprofen")
    assert out["findings"][0]["severity"] == "Moderate" and out["message"] is None
    assert ms.check_new_medicine(db, pid, "Mystery Brand")["recognized"] is False
    # An unknown brand is checked through the AI's verified suggestion, and says so.
    monkeypatch.setattr(bg, "is_available", lambda: True)
    monkeypatch.setattr(bg, "llm_json", lambda *a, **k: {"ingredients": [{"name": "calcium carbonate",
                                                                            "strength": "500 mg"}]})
    out = ms.check_new_medicine(db, pid, "Shelcal 500")
    assert out["recognized"] and "AI suggestion" in out["assumed"] and out["message"] == ms.NO_FINDING
    res = bg.resolve("Shelcal 500")
    assert res["status"] == "suggested" and res["needs_confirmation"] and res["suggestion"][0]["verified"]
    assert bg.confirmed_ingredients(["Calcium Carbonate", "made-up"]) == ["calcium carbonate", "made-up"]


def test_api_resolve_create_safety_and_check(client, db, monkeypatch):
    client.post("/api/auth/register", json={"email": "msapi@x.com", "password": "pw123456"})
    tok = client.post("/api/auth/login", data={"username": "msapi@x.com", "password": "pw123456"}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    pid = client.post("/api/patients", json={"name": "Api"}, headers=h).json()["id"]
    monkeypatch.setattr(bg, "is_available", lambda: True)
    monkeypatch.setattr(bg, "llm_json", lambda *a, **k: {"ingredients": [{"name": "levothyroxine", "strength": "75 mcg"}]})
    r = client.post(f"/api/patients/{pid}/medications/resolve-name", json={"name": "Thyronorm 75"}, headers=h).json()
    assert r["status"] == "suggested" and r["needs_confirmation"]  # offline RxNorm: unverified suggestion
    # Nothing is stored until the user sends the confirmed ingredients back.
    m = client.post(f"/api/patients/{pid}/medications", headers=h, json={
        "name": "Thyronorm 75", "dose": "75 mcg", "ingredients": ["levothyroxine"], "brand_name": "Thyronorm 75"}).json()
    assert m["ingredients"] == ["levothyroxine"] and m["brand_name"] == "Thyronorm 75"
    plain = client.post(f"/api/patients/{pid}/medications", headers=h, json={"name": "Unknownol"}).json()
    assert plain["ingredients"] == []  # never guessed

    monkeypatch.setattr(ms, "is_available", lambda: False)
    first = client.get(f"/api/patients/{pid}/medications/safety", headers=h).json()
    assert first["medicines"] == ["Thyronorm 75", "Unknownol"] and first["unresolved_medicines"] == ["Unknownol"]
    assert first["pairs"][0]["message"] == ms.NO_FINDING and first["disclaimer"]
    stored = db.query(MedCheckRun).filter_by(patient_id=pid).one().created_at
    client.get(f"/api/patients/{pid}/medications/safety", headers=h)
    db.expire_all()
    assert db.query(MedCheckRun).filter_by(patient_id=pid).one().created_at == stored  # reused
    client.get(f"/api/patients/{pid}/medications/safety?refresh=true", headers=h)
    db.expire_all()
    assert db.query(MedCheckRun).filter_by(patient_id=pid).one().created_at > stored
    out = client.post(f"/api/patients/{pid}/medications/check", json={"name": "Whatever"}, headers=h).json()
    assert out["recognized"] is False and "pharmacist" in out["message"]
    assert date.today()  # keep the import honest


def test_assistant_med_check_pinned_finding_and_side_effects(db, no_llm, monkeypatch):
    import app.services.assistant as assistant

    pid = _patient(db, "msa@x.com")
    _med(db, pid, "Metformin", ["metformin"])
    db.add(DrugInteraction(drug_lo="ibuprofen", drug_hi="metformin", name_a="a", name_b="b", level="Moderate"))
    db.flush()
    monkeypatch.setattr(ms.rxnorm, "lookup", lambda n: {"status": "found", "ingredients": [n.lower()]})
    monkeypatch.setattr(assistant, "is_available", lambda: False)

    pack, items = assistant.build_pack(db, pid, message="Can I take ibuprofen with my medicines?", kind="question",
                                       new_entry=None, context_bundle=None)
    [f] = pack["med_check"]["findings"]
    assert f["id"] == "N1" and f["id"] in items and f["severity"] == "Moderate"
    reply = assistant._fallback(pack, items)
    assert "Verified" in reply and "[N1]" in reply and ms.DONT_CHANGE in reply and "safe" not in reply.lower()

    # Nothing found: the exact sentence, never an all-clear.
    pack, items = assistant.build_pack(db, pid, message="can I take paracetamol?", kind="question",
                                       new_entry=None, context_bundle=None)
    assert pack["med_check"]["message"] == ms.NO_FINDING and ms.NO_FINDING in assistant._fallback(pack, items)

    # A finding pinned from the Medications page comes from the stored run, by id.
    stored = ms.latest(db, pid)
    db.add(Medication(patient_id=pid, name="Ibuprofen", ingredients=["ibuprofen"]))
    db.flush()
    stored = ms.latest(db, pid)
    fid = stored["findings"][0]["id"]
    pack, items = assistant.build_pack(db, pid, message="what does this mean?", kind="question", new_entry=None,
                                       context_bundle=None, focus={"type": "med_finding", "id": fid})
    assert pack["pinned_finding"]["id"] == fid and fid in items
    assert "Never say medicines are safe together" in assistant.SYSTEM
