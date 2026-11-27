"""Missing info resolves when the data arrives; suggestions can be dismissed and stay
dismissed for 14 days."""

from datetime import timedelta

from app.core import clock
from app.models.intelligence import SuggestedAction
from app.models.patient import Patient
from app.models.user import User
from app.services.missing_info import LOG_BP_ACTION, dismiss_action, suggested_actions

DISCUSS_BP = "Consider discussing your recent blood pressure readings with a doctor"


def _auth(client, email: str) -> dict:
    client.post("/api/auth/register", json={"email": email, "password": "pw123456"})
    r = client.post("/api/auth/login", data={"username": email, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _hypertensive_patient(client, email: str) -> tuple[dict, int]:
    h = _auth(client, email)
    pid = client.post("/api/patients", json={"name": "Gap"}, headers=h).json()["id"]
    client.put(f"/api/patients/{pid}/background", json={"conditions": ["Hypertension"]}, headers=h)
    return h, pid


def test_bp_gap_and_its_suggestion_clear_once_a_reading_is_logged(client):
    h, pid = _hypertensive_patient(client, "gap@x.com")
    client.post(f"/api/patients/{pid}/intake", json={"raw_text": "bad headache today"}, headers=h)

    snap = client.get(f"/api/patients/{pid}/snapshot", headers=h).json()
    assert any("blood pressure" in m for m in snap["missing_information"])
    actions = client.get(f"/api/patients/{pid}/suggested-actions", headers=h).json()
    assert [a["text"] for a in actions] == [LOG_BP_ACTION]

    # Logged through the vitals form (not intake): the gap must still close.
    r = client.post(
        f"/api/patients/{pid}/vitals",
        json={"vital_type": "bp_systolic", "value": 128, "unit": "mmHg"},
        headers=h,
    )
    assert r.status_code == 201
    snap = client.get(f"/api/patients/{pid}/snapshot", headers=h).json()
    assert snap["missing_information"] == []
    assert client.get(f"/api/patients/{pid}/suggested-actions", headers=h).json() == []


def test_dismissing_a_suggestion(client):
    h, pid = _hypertensive_patient(client, "dismiss@x.com")
    client.post(f"/api/patients/{pid}/intake", json={"raw_text": "blood pressure 150 over 95"}, headers=h)
    actions = client.get(f"/api/patients/{pid}/suggested-actions", headers=h).json()
    target = next(a for a in actions if a["text"] == DISCUSS_BP)

    r = client.post(f"/api/patients/{pid}/suggested-actions/{target['id']}/dismiss", headers=h)
    assert r.status_code == 200 and r.json()["dismissed"] is True and r.json()["dismissed_at"]
    remaining = client.get(f"/api/patients/{pid}/suggested-actions", headers=h).json()
    assert DISCUSS_BP not in [a["text"] for a in remaining]
    snap = client.get(f"/api/patients/{pid}/snapshot", headers=h).json()
    assert DISCUSS_BP not in snap["suggested_next_actions"]

    other = _auth(client, "other@x.com")
    r = client.post(f"/api/patients/{pid}/suggested-actions/{target['id']}/dismiss", headers=other)
    assert r.status_code == 403
    r = client.post(f"/api/patients/{pid}/suggested-actions/999999/dismiss", headers=h)
    assert r.status_code == 404


def test_a_dismissed_suggestion_stays_away_for_14_days(db):
    user = User(email="cooldown@x.com", password_hash="x", role="patient")
    db.add(user)
    db.flush()
    patient = Patient(user_id=user.id, name="Cooldown")
    db.add(patient)
    db.flush()
    high_bp = [{"kind": "high_bp"}]

    assert suggested_actions(db, patient.id, high_bp, []) == [DISCUSS_BP]
    db.flush()
    action = db.query(SuggestedAction).filter_by(patient_id=patient.id).one()
    dismiss_action(action)
    db.flush()

    assert suggested_actions(db, patient.id, high_bp, []) == []  # dismissed just now
    with clock.frozen_at(clock.now() + timedelta(days=13)):
        assert suggested_actions(db, patient.id, high_bp, []) == []
    with clock.frozen_at(clock.now() + timedelta(days=15)):
        assert suggested_actions(db, patient.id, high_bp, []) == [DISCUSS_BP]
