"""Backdating end to end: "a migraine yesterday" is stored, dated and tracked as yesterday."""

from datetime import datetime, timedelta, timezone

from app.core import clock
from app.models.patient import Patient
from app.models.user import User
from app.services.problems import upsert_problem_from_symptom

NOW = datetime(2026, 3, 18, 4, 30, tzinfo=timezone.utc)  # Wednesday 10:00 in India
YESTERDAY_NOON_IST = datetime(2026, 3, 17, 6, 30, tzinfo=timezone.utc)
THIS_MORNING_IST = datetime(2026, 3, 18, 2, 30, tzinfo=timezone.utc)  # 08:00 IST


def _auth(client, email: str) -> dict:
    client.post("/api/auth/register", json={"email": email, "password": "pw123456"})
    r = client.post("/api/auth/login", data={"username": email, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_intake_backdates_the_entry_problem_and_timeline(client):
    h = _auth(client, "backdate@x.com")
    pid = client.post("/api/patients", json={"name": "Backdate"}, headers=h).json()["id"]
    url = f"/api/patients/{pid}/intake"
    with clock.frozen_at(NOW):
        r = client.post(url, json={"raw_text": "I had a bad migraine yesterday"}, headers=h)
        assert r.json()["status"] == "processed"
        assert _ts(r.json()["new_entry"]["occurred_at"]) == YESTERDAY_NOON_IST
        client.post(url, json={"raw_text": "migraine again this morning"}, headers=h)

    entries = {e["raw_text"]: e for e in client.get(f"/api/patients/{pid}/entries", headers=h).json()}
    first = entries["I had a bad migraine yesterday"]
    assert _ts(first["occurred_at"]) == YESTERDAY_NOON_IST  # when it happened
    assert _ts(first["created_at"]) == NOW  # when it was logged

    problems = client.get(f"/api/patients/{pid}/problems", headers=h).json()
    migraine = next(p for p in problems if p["name"] == "migraine")
    assert _ts(migraine["first_seen"]) == YESTERDAY_NOON_IST
    assert _ts(migraine["last_seen"]) == THIS_MORNING_IST

    detail = client.get(
        f"/api/patients/{pid}/timeline/2026-03-17/detail?window_days=0", headers=h
    ).json()
    assert [e["raw_text"] for e in detail["entries"]] == ["I had a bad migraine yesterday"]


def test_a_late_logged_older_episode_widens_first_seen(db):
    user = User(email="widen@x.com", password_hash="x", role="patient")
    db.add(user)
    db.flush()
    patient = Patient(user_id=user.id, name="Widen")
    db.add(patient)
    db.flush()

    def episode(when: datetime) -> dict:
        return {"type": "symptom", "name": "headache", "structured": {}, "occurred_at": when.isoformat()}

    problem = upsert_problem_from_symptom(db, patient.id, episode(NOW))
    db.flush()
    upsert_problem_from_symptom(db, patient.id, episode(NOW - timedelta(days=3)))
    db.flush()
    assert problem.first_seen == NOW - timedelta(days=3)
    assert problem.last_seen == NOW
