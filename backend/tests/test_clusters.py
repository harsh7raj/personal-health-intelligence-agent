"""Symptom pairs within 48h (by when they happened), counted once per episode."""

from datetime import datetime, timedelta, timezone

from app.models.clinical import SymptomCluster
from app.models.patient import Patient
from app.models.records import Entry
from app.models.user import User
from app.services.clusters import pair_episodes, update_clusters

T0 = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
WINDOW = timedelta(hours=48)


def at(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


def test_two_symptoms_within_the_window_make_one_pair():
    assert pair_episodes([("headache", at(0)), ("nausea", at(1))], WINDOW) == {
        ("headache", "nausea"): (1, at(1))
    }


def test_a_third_symptom_adds_pairs_instead_of_a_new_set():
    pairs = pair_episodes([("headache", at(0)), ("nausea", at(1)), ("fatigue", at(5))], WINDOW)
    assert set(pairs) == {("headache", "nausea"), ("fatigue", "headache"), ("fatigue", "nausea")}
    assert all(count == 1 for count, _ in pairs.values())


def test_repeated_logs_in_one_window_count_once():
    events = [("headache", at(0)), ("nausea", at(1)), ("headache", at(30)), ("nausea", at(31))]
    assert pair_episodes(events, WINDOW)[("headache", "nausea")][0] == 1


def test_the_same_pair_a_week_later_is_a_second_episode():
    events = [("headache", at(0)), ("nausea", at(2)), ("headache", at(168)), ("nausea", at(170))]
    assert pair_episodes(events, WINDOW)[("headache", "nausea")] == (2, at(170))


def test_far_apart_or_same_symptom_is_not_a_pair():
    assert pair_episodes([("headache", at(0)), ("nausea", at(49))], WINDOW) == {}
    assert pair_episodes([("headache", at(0)), ("headache", at(1))], WINDOW) == {}


def test_order_of_logging_does_not_matter():
    events = [("headache", at(168)), ("nausea", at(2)), ("nausea", at(170)), ("headache", at(0))]
    assert pair_episodes(events, WINDOW)[("headache", "nausea")] == (2, at(170))


def test_update_clusters_syncs_rows_and_drops_stale_sets(db):
    user = User(email="pairs@x.com", password_hash="x", role="patient")
    db.add(user)
    db.flush()
    patient = Patient(user_id=user.id, name="Pairs")
    db.add(patient)
    db.flush()
    # A leftover 3-symptom set from the old logic, plus entries under variant names.
    db.add(SymptomCluster(patient_id=patient.id, symptoms=["a", "b", "c"], occurrences=4))
    for name, hours in (("headaches", 0), ("nausea", 3), ("Headache", 168), ("nausea", 169)):
        db.add(Entry(patient_id=patient.id, type="symptom", structured={"name": name},
                     occurred_at=at(hours)))
    db.flush()

    update_clusters(db, patient.id)
    db.flush()
    rows = db.query(SymptomCluster).filter_by(patient_id=patient.id).all()
    assert [(r.symptoms, r.occurrences) for r in rows] == [(["headache", "nausea"], 2)]
