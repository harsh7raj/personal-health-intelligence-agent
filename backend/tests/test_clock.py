"""app/core/clock.py: an overridable "now" for the demo replay; auth stays on real time."""

from datetime import datetime, timedelta, timezone

from app.core import clock
from app.core.security import create_access_token, decode_token
from app.models.patient import Patient
from app.models.records import Entry
from app.models.user import User
from app.services.problems import upsert_problem_from_symptom

PAST = datetime(2026, 3, 14, 9, 30, tzinfo=timezone.utc)


def _seconds_from_real_now(t: datetime) -> float:
    return abs((t - datetime.now(timezone.utc)).total_seconds())


def test_now_is_aware_utc_and_real_by_default():
    n = clock.now()
    assert n.utcoffset() == timedelta(0)
    assert _seconds_from_real_now(n) < 5


def test_frozen_at_pins_nests_and_restores():
    with clock.frozen_at(PAST):
        assert clock.now() == PAST
        with clock.frozen_at(PAST + timedelta(days=1)):
            assert clock.now() == PAST + timedelta(days=1)
        assert clock.now() == PAST
    assert _seconds_from_real_now(clock.now()) < 5


def test_naive_times_are_taken_as_utc():
    with clock.frozen_at(datetime(2026, 3, 14, 9, 30)):
        assert clock.now() == PAST


def test_row_defaults_and_services_follow_the_clock(db):
    user = User(email="clock@x.com", password_hash="x", role="patient")
    db.add(user)
    db.flush()
    patient = Patient(user_id=user.id, name="Clock Test")
    db.add(patient)
    db.flush()
    with clock.frozen_at(PAST):
        entry = Entry(patient_id=patient.id, type="symptom", raw_text="headache")
        db.add(entry)
        db.flush()
        problem = upsert_problem_from_symptom(
            db, patient.id, {"type": "symptom", "name": "headache", "structured": {}}
        )
        db.flush()
    assert entry.created_at == PAST  # Python-side default, not Postgres now()
    assert problem.first_seen == PAST and problem.last_seen == PAST


def test_auth_tokens_ignore_the_clock():
    with clock.frozen_at(PAST):  # a token minted during a replay must still be valid now
        token = create_access_token(42)
    assert decode_token(token)["sub"] == "42"
