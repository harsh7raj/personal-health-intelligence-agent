"""Observations now see the dated past entries the Memory agent retrieved."""

import json

import app.services.observations as obs
from app.models.intelligence import Observation
from app.models.patient import Patient
from app.models.user import User

BUNDLE = {
    "semantic_matches": [
        {"text": "migraine behind one eye", "distance": 0.42,
         "metadata": {"entry_id": 11, "date": "2026-03-01T20:00:00+00:00"}},  # 2 Mar in IST
        {"text": "throbbing migraine", "distance": 0.8,
         "metadata": {"entry_id": 12, "date": "2026-02-10T06:30:00+00:00"}},
        {"text": "sprained ankle", "distance": 1.4,  # not close enough
         "metadata": {"entry_id": 13, "date": "2026-01-05T06:30:00+00:00"}},
    ]
}


def test_close_matches_become_dated_related_entries():
    assert obs.related_past_entries(BUNDLE) == [
        {"entry_id": 11, "date": "2026-03-02", "text": "migraine behind one eye"},
        {"entry_id": 12, "date": "2026-02-10", "text": "throbbing migraine"},
    ]
    assert obs.related_past_entries(None) == []


def test_payload_and_evidence_carry_the_related_entries(db, monkeypatch):
    user = User(email="obs@x.com", password_hash="x", role="patient")
    db.add(user)
    db.flush()
    patient = Patient(user_id=user.id, name="Obs")
    db.add(patient)
    db.flush()

    seen: dict = {}

    def fake_llm(task, system, user_text, **_kw):
        seen["task"], seen["payload"] = task, json.loads(user_text)
        return {"observations": ["A similar migraine was logged on 2026-03-02."]}

    monkeypatch.setattr(obs, "is_available", lambda: True)
    monkeypatch.setattr(obs, "llm_json", fake_llm)

    created = obs.generate_observations(
        db, patient.id, {"type": "symptom", "name": "migraine"}, BUNDLE
    )
    db.flush()
    assert seen["task"] == "observations"
    # The model gets dates (it cites by date), not database ids: keeps the prompt stable
    # across demo re-seeds. The stored evidence keeps the ids.
    assert [e["date"] for e in seen["payload"]["related_past_entries"]] == ["2026-03-02", "2026-02-10"]
    assert all("entry_id" not in e for e in seen["payload"]["related_past_entries"])
    assert created == ["A similar migraine was logged on 2026-03-02."]
    stored = db.query(Observation).filter_by(patient_id=patient.id).one()
    assert stored.evidence["related_past_entries"][0] == {
        "entry_id": 11, "date": "2026-03-02", "text": "migraine behind one eye"}
