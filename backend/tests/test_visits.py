"""Doctor visit recaps (D37): structuring with attribution, dates in code, misheard medicine
names, clash preview, confirm applying changes as the doctor's, reminders, saved questions,
recall by the assistant, the pre-visit brief, and transcription. LLM/network always stubbed."""

from datetime import date
from types import SimpleNamespace

import pytest

import app.services.visits as vs
from app.core import llm
from app.models.clinical import Medication, MedicationEvent
from app.models.reference import DrugInteraction
from app.models.visits import Reminder, SavedQuestion

VISIT_DAY = date(2026, 11, 20)
KNOWN = {"glimepiride": ["glimepiride"], "glipizide": ["glipizide"], "metformin": ["metformin"],
         "amlodipine": ["amlodipine"], "atorvastatin": ["atorvastatin"]}


def _lookup(name):
    key = name.lower().split()[0]
    return {"status": "found", "ingredients": KNOWN[key]} if key in KNOWN else {"status": "not_found", "ingredients": []}


@pytest.fixture(autouse=True)
def offline_rxnorm(monkeypatch):
    monkeypatch.setattr(vs.rxnorm, "lookup", _lookup)
    monkeypatch.setattr(vs.brand_generic.rxnorm, "lookup", _lookup)
    monkeypatch.setattr(vs.med_safety.rxnorm, "lookup", _lookup)
    monkeypatch.setattr(vs.brand_generic, "is_available", lambda: False)


RAW = {
    "reason": "Review of low sugars",
    "discussed": ["Sugar diary", "The lows are caused by glimepiride"],
    "doctor_said": ["Reduce glimepiride to 1 mg because of the lows", "Dr. Rao said keep a sugar diary"],
    "medicine_changes": [{"action": "change", "name": "glimepiride", "dose": "1 mg", "frequency": None,
                          "reason": "because of the lows"}, {"action": "weird", "name": "  "}],
    "tests_ordered": [{"name": "HbA1c", "when": "in 3 months"}],
    "follow_up": {"when": "review in six weeks"},
    "watch_for": ["shakiness or sweating"],
    "questions_next_time": ["Is 1 mg enough?"],
}


def test_normalize_attributes_the_doctor_and_counts_dates_in_code():
    n = vs.normalize(RAW, "Dr. Rao", VISIT_DAY)
    assert n["doctor_said"][0] == "Dr. Rao said: reduce glimepiride to 1 mg because of the lows"
    assert n["doctor_said"][1] == "Dr. Rao said keep a sugar diary"
    # A cause written as a plain fact is moved into the doctor's words.
    assert n["discussed"] == ["Sugar diary"] and "Dr. Rao said: the lows are caused by glimepiride" in n["doctor_said"]
    assert [c["name"] for c in n["medicine_changes"]] == ["glimepiride"]
    assert n["tests_ordered"][0]["due_date"] == "2027-02-18"  # 3 x 30 days
    assert n["follow_up"] == {"when": "review in six weeks", "date": "2027-01-01"}
    assert vs.due_date("next Tuesday", VISIT_DAY) is None


def test_without_an_llm_the_recap_is_left_to_edit(monkeypatch):
    monkeypatch.setattr(vs, "is_available", lambda: False)
    s, by = vs.structure("Saw Dr. Rao, all fine", "Dr. Rao", VISIT_DAY)
    assert by == "fallback" and s["discussed"] == ["Saw Dr. Rao, all fine"] and s["medicine_changes"] == []


def _patient(client, email):
    client.post("/api/auth/register", json={"email": email, "password": "pw123456"})
    tok = client.post("/api/auth/login", data={"username": email, "password": "pw123456"}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    return h, client.post("/api/patients", json={"name": "Visitor"}, headers=h).json()["id"]


def test_misheard_medicine_names_are_flagged(db, client):
    h, pid = _patient(client, "mishear@x.com")
    db.add(Medication(patient_id=pid, name="Glimepiride", dose="2 mg", ingredients=["glimepiride"], prescriber="Dr. Rao"))
    db.commit()
    c = vs.check_change(db, pid, {"action": "change", "name": "glipizide", "dose": "1 mg"})
    assert c["status"] == "please_check" and "Did you mean Glimepiride" in c["note"]
    assert c["medication_id"] is not None  # the likely medicine is pre-selected for the user to confirm
    ok = vs.check_change(db, pid, {"action": "change", "name": "Glimepiride", "dose": "1 mg"})
    assert ok["status"] == "ok" and ok["matched_name"] == "Glimepiride"
    unknown = vs.check_change(db, pid, {"action": "start", "name": "Zzyzx 5"})
    assert unknown["status"] == "please_check" and "isn't in RxNorm" in unknown["note"]
    stop_missing = vs.check_change(db, pid, {"action": "stop", "name": "Metformin"})
    assert stop_missing["status"] == "please_check" and "isn't on your medicine list" in stop_missing["note"]


def test_full_visit_flow(db, client, monkeypatch):
    h, pid = _patient(client, "visit@x.com")
    base = f"/api/patients/{pid}"
    glim = client.post(f"{base}/medications", headers=h, json={
        "name": "Glimepiride", "dose": "2 mg", "prescriber": "Dr. Rao", "ingredients": ["glimepiride"]}).json()
    client.post(f"{base}/medications", headers=h, json={
        "name": "Amlodipine", "dose": "5 mg", "prescriber": "Dr. Mehta", "ingredients": ["amlodipine"]})
    db.add(DrugInteraction(drug_lo="amlodipine", drug_hi="atorvastatin", name_a="a", name_b="b", level="Moderate"))
    db.commit()
    raw = {**RAW, "medicine_changes": [
        {"action": "change", "name": "glipizide", "dose": "1 mg", "reason": "because of the lows"},
        {"action": "start", "name": "Atorvastatin", "dose": "10 mg", "frequency": "once daily"}]}
    monkeypatch.setattr(vs, "is_available", lambda: True)
    monkeypatch.setattr(vs, "llm_json", lambda *a, **k: raw)
    monkeypatch.setattr(vs.med_safety, "is_available", lambda: False)

    # Recording the consultation needs the doctor's agreement; the self-recap doesn't.
    form = {"doctor_name": "Dr. Rao", "visit_date": VISIT_DAY.isoformat(), "specialty": "Endocrinology"}
    r = client.post(f"{base}/visits", headers=h, data={**form, "source": "recording", "transcript": "x"})
    assert r.status_code == 400 and "Ask your doctor" in r.json()["detail"]
    v = client.post(f"{base}/visits", headers=h, data={**form, "transcript": "Saw Dr. Rao. Glipizide down..."}).json()
    assert v["status"] == "draft" and v["generated_by"] == "llm"
    checks = v["medicine_checks"]
    assert checks[0]["status"] == "please_check" and checks[0]["suggested_medication_id"] == glim["id"]
    assert checks[1]["status"] == "ok"

    # Clash preview: Dr. Rao's new atorvastatin vs Dr. Mehta's amlodipine (DDInter).
    prev = client.post(f"{base}/visits/{v['id']}/preview", headers=h).json()
    assert prev["findings"][0]["severity"] == "Moderate" and "Atorvastatin" in prev["findings"][0]["medicines"]

    # Not applied until the misheard name is checked.
    assert client.post(f"{base}/visits/{v['id']}/confirm", headers=h).status_code == 409
    s = v["structured"]
    s["medicine_changes"][0].update(name="Glimepiride", medication_id=glim["id"], confirmed=True)
    v = client.put(f"{base}/visits/{v['id']}", headers=h, json={"structured": s}).json()
    assert v["medicine_checks"][0]["status"] == "ok"
    done = client.post(f"{base}/visits/{v['id']}/confirm", headers=h).json()
    assert done["status"] == "confirmed" and done["applied"] == ["Changed Glimepiride", "Started Atorvastatin"]

    db.expire_all()
    med = db.get(Medication, glim["id"])
    assert med.dose == "1 mg" and med.prescriber == "Dr. Rao"
    ev = db.query(MedicationEvent).filter_by(medication_id=glim["id"], event_type="dose_change").one()
    assert (ev.source, ev.old_dose, ev.new_dose, ev.event_date) == ("visit_note", "2 mg", "1 mg", VISIT_DAY)
    ator = db.query(Medication).filter_by(patient_id=pid, name="Atorvastatin").one()
    assert ator.prescriber == "Dr. Rao" and ator.started_on == VISIT_DAY and ator.ingredients == ["atorvastatin"]
    assert {r.kind for r in db.query(Reminder).filter_by(patient_id=pid)} == {"test", "follow_up"}
    assert db.query(SavedQuestion).filter_by(patient_id=pid).one().text == "Is 1 mg enough?"
    assert client.put(f"{base}/visits/{v['id']}", headers=h, json={"specialty": "x"}).status_code == 409

    # The assistant can quote the doctor; the brief has the visit, questions and reminders.
    notes = vs.retrieval.visit_notes(db, pid)
    assert notes[0]["id"] == f"D{v['id']}" and notes[0]["doctor_said"][0].startswith("Dr. Rao said")
    client.post(f"{base}/questions", headers=h, json=[{"text": "Why is my HbA1c 6.9?", "source": "report"},
                                                       {"text": "Is 1 mg enough?"}])
    b = client.get(f"{base}/visits/brief", headers=h, params={"doctor": "dr rao"}).json()
    assert b["last_visit"]["id"] == f"D{v['id']}"
    assert [q["text"] for q in b["questions"]] == ["Is 1 mg enough?", "Why is my HbA1c 6.9?"]  # no duplicate
    assert {r["kind"] for r in b["reminders"]} == {"test", "follow_up"}
    assert b["current_medicines"][0]["name"] == "Amlodipine"
    assert {d["name"] for d in client.get(f"{base}/visits/doctors", headers=h).json()} == {"Dr. Rao", "Dr. Mehta"}
    mehta = client.get(f"{base}/visits/brief", headers=h, params={"doctor": "Dr. Mehta"}).json()
    assert any(c["medication"] == "Glimepiride" for c in mehta["other_doctors_changes"])  # Dr. Rao's change


def test_transcribe_uses_groq_whisper_and_the_demo_cache(monkeypatch, tmp_path):
    calls = []

    class FakeAudio:
        class transcriptions:  # noqa: N801
            @staticmethod
            def create(**kw):
                calls.append(kw)
                return "Saw Dr. Rao today."

    monkeypatch.setattr(llm, "_client", lambda provider: SimpleNamespace(audio=FakeAudio))
    monkeypatch.setattr(llm.get_settings(), "FALLBACK_API_KEY", "test-key")
    audio = tmp_path / "recap.webm"
    audio.write_bytes(b"fake audio")
    with llm.response_cache(tmp_path / "cache"):
        assert llm.transcribe(audio) == "Saw Dr. Rao today."
        assert llm.transcribe(audio) == "Saw Dr. Rao today."
    assert len(calls) == 1 and calls[0]["model"] == llm.get_settings().STT_MODEL
    monkeypatch.setattr(llm.get_settings(), "FALLBACK_API_KEY", "")
    with pytest.raises(llm.LLMUnavailable):
        llm.transcribe(audio)
