"""Problem matching: one canonical name per symptom, variants kept as aliases."""

import pytest

from app.data.symptom_synonyms import canonical_symptom
from app.models.patient import Patient
from app.models.records import Entry
from app.models.user import User
from app.services.problem_timeline import build_problem_timeline
from app.services.problems import upsert_problem_from_symptom

_n = {"i": 0}


def _patient(db) -> int:
    _n["i"] += 1
    user = User(email=f"match{_n['i']}@x.com", password_hash="x", role="patient")
    db.add(user)
    db.flush()
    patient = Patient(user_id=user.id, name="Match")
    db.add(patient)
    db.flush()
    return patient.id


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("Headaches", "headache"),
        ("head pain", "headache"),
        ("Head-ache", "headache"),
        ("migraine", "migraine"),  # related, but not the same symptom
        ("Migraines", "migraine"),
        ("giddiness", "dizziness"),
        ("running nose", "runny nose"),
        ("ankles swollen", "ankle swelling"),
        ("hair fall", "hair loss"),
        ("left knee pain", "left knee pain"),  # unknown names pass through, tidied
    ],
)
def test_canonical_names(raw, canonical):
    assert canonical_symptom(raw) == canonical


def _symptom(name: str) -> dict:
    return {"type": "symptom", "name": name, "structured": {"name": name}}


def test_variants_become_one_problem_with_aliases(db):
    pid = _patient(db)
    first = upsert_problem_from_symptom(db, pid, _symptom("headache"))
    db.flush()
    for variant in ("headaches", "head pain", "Head-ache"):
        assert upsert_problem_from_symptom(db, pid, _symptom(variant)).id == first.id
        db.flush()
    assert first.name == "headache"
    assert first.attributes["episode_count"] == 4
    assert set(first.attributes["aliases"]) == {"headaches", "head pain", "head-ache"}

    other = upsert_problem_from_symptom(db, pid, _symptom("migraine"))
    db.flush()
    assert other.id != first.id


def test_intake_stores_canonical_name_and_keeps_the_users_words(client, monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.intake.parse_entry",
        lambda text: {"type": "symptom", "name": "Head pain", "attributes": {}, "complete": True},
    )
    client.post("/api/auth/register", json={"email": "canon@x.com", "password": "pw123456"})
    tok = client.post("/api/auth/login", data={"username": "canon@x.com", "password": "pw123456"})
    h = {"Authorization": f"Bearer {tok.json()['access_token']}"}
    pid = client.post("/api/patients", json={"name": "Canon"}, headers=h).json()["id"]

    r = client.post(f"/api/patients/{pid}/intake", json={"raw_text": "my head hurts"}, headers=h)
    structured = r.json()["new_entry"]["structured"]
    assert structured["name"] == "headache"
    assert structured["reported_name"] == "Head pain"
    assert [p["name"] for p in client.get(f"/api/patients/{pid}/problems", headers=h).json()] == [
        "headache"
    ]


def test_sub_timeline_links_entries_logged_under_old_variant_names(db):
    pid = _patient(db)
    db.add(Entry(patient_id=pid, type="symptom", raw_text="bad one", structured={"name": "headaches"}))
    db.flush()
    problem = upsert_problem_from_symptom(db, pid, _symptom("headache"))
    db.flush()
    timeline = build_problem_timeline(db, pid, problem.id)
    episodes = [p for p in timeline["points"] if p["kind"] == "episode"]
    assert [p["detail"] for p in episodes] == ["bad one"]
