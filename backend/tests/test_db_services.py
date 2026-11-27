from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.clinical import VitalReading, VitalSummary
from app.models.patient import Patient
from app.models.records import Entry
from app.models.user import User
from app.services.clusters import update_clusters
from app.services.problems import auto_resolve, upsert_problem_from_symptom
from app.services.vitals_trend import recompute_summary

_counter = {"n": 0}


def _make_patient(db) -> int:
    _counter["n"] += 1
    u = User(email=f"svc{_counter['n']}@x.com", password_hash="x", role="patient")
    db.add(u)
    db.flush()
    p = Patient(user_id=u.id, name="Svc Test")
    db.add(p)
    db.flush()
    return p.id


def test_recompute_summary_rising(db):
    pid = _make_patient(db)
    base = datetime.now(timezone.utc) - timedelta(days=180)
    for i, v in enumerate([120, 124, 130, 134, 140, 146]):
        db.add(
            VitalReading(
                patient_id=pid, vital_type="bp_systolic", value=v, unit="mmHg",
                recorded_at=base + timedelta(days=i * 30),
            )
        )
    db.flush()
    recompute_summary(db, pid, "bp_systolic")
    db.flush()  # session is autoflush=False; make the upserted summary queryable
    s = db.scalar(select(VitalSummary).where(VitalSummary.patient_id == pid))
    assert s.latest == 146
    assert s.trend == "rising"


def test_problem_increment_and_autoresolve(db):
    pid = _make_patient(db)
    ne = {"type": "symptom", "name": "headache",
          "structured": {"name": "headache", "attributes": {"severity": "moderate"}}}
    p1 = upsert_problem_from_symptom(db, pid, ne)
    db.flush()
    upsert_problem_from_symptom(db, pid, ne)
    db.flush()
    p3 = upsert_problem_from_symptom(db, pid, ne)
    db.flush()
    assert p3.id == p1.id
    assert p3.attributes["episode_count"] == 3
    assert p3.frequency == "3 episodes"  # trend is frequency-based now (test_problem_trend.py)

    p3.last_seen = datetime.now(timezone.utc) - timedelta(days=120)
    db.flush()
    resolved = auto_resolve(db, pid)
    assert "headache" in resolved
    assert p3.status == "resolved"
    assert p3.resolved_at is not None


def test_cluster_forms_from_cooccurring_symptoms(db):
    pid = _make_patient(db)
    db.add(Entry(patient_id=pid, type="symptom", raw_text="headache", structured={"name": "headache"}))
    db.add(Entry(patient_id=pid, type="symptom", raw_text="nausea", structured={"name": "nausea"}))
    db.flush()
    cluster = update_clusters(db, pid, {"type": "symptom", "name": "nausea"})
    assert cluster is not None
    assert sorted(cluster.symptoms) == ["headache", "nausea"]
    assert cluster.occurrences == 1
