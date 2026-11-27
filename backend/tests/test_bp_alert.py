"""One alert per BP reading (not one per number)."""

from app.models.intelligence import Alert
from app.models.patient import Patient
from app.models.user import User
from app.services.alerts import check_bp_alert, create_alerts_for_readings


def test_whole_reading_levels():
    assert check_bp_alert(147, 92) == ("high_bp", "high", "BP 147/92 is above the alert threshold")
    assert check_bp_alert(130, 95)[0] == "high_bp"  # diastolic alone is enough
    assert check_bp_alert(185, 95)[:2] == ("critical_bp", "critical")  # the worse half wins
    assert check_bp_alert(120, 80) is None


def _patient(db, email: str) -> int:
    user = User(email=email, password_hash="x", role="patient")
    db.add(user)
    db.flush()
    patient = Patient(user_id=user.id, name="BP")
    db.add(patient)
    db.flush()
    return patient.id


def test_one_alert_for_both_halves_plus_other_vitals(db):
    pid = _patient(db, "bp1@x.com")
    created = create_alerts_for_readings(
        db, pid, [("bp_systolic", 147, "mmHg"), ("bp_diastolic", 92, "mmHg"), ("heart_rate", 110, "bpm")]
    )
    db.flush()
    assert [a["kind"] for a in created] == ["high_bp", "tachycardia"]
    bp = db.query(Alert).filter_by(patient_id=pid, kind="high_bp").one()
    assert bp.message == "BP 147/92 is above the alert threshold"
    assert bp.vital_type == "blood_pressure"


def test_a_lone_half_still_alerts_on_its_own(db):
    pid = _patient(db, "bp2@x.com")
    created = create_alerts_for_readings(db, pid, [("bp_systolic", 150, "mmHg")])
    assert [(a["kind"], a["vital_type"]) for a in created] == [("high_bp", "bp_systolic")]


def test_intake_reading_gives_one_alert_with_paired_context(client):
    client.post("/api/auth/register", json={"email": "bp3@x.com", "password": "pw123456"})
    tok = client.post("/api/auth/login", data={"username": "bp3@x.com", "password": "pw123456"})
    h = {"Authorization": f"Bearer {tok.json()['access_token']}"}
    pid = client.post("/api/patients", json={"name": "BP"}, headers=h).json()["id"]

    client.post(f"/api/patients/{pid}/intake", json={"raw_text": "blood pressure 150 over 95"}, headers=h)
    alerts = client.get(f"/api/patients/{pid}/alerts", headers=h).json()
    assert [(a["kind"], a["message"]) for a in alerts] == [
        ("high_bp", "BP 150/95 is above the alert threshold")
    ]
    ctx = client.get(f"/api/patients/{pid}/alerts/{alerts[0]['id']}/context", headers=h).json()
    assert [(r["display"], r["breaches"]) for r in ctx["readings"]] == [("150/95", True)]
