"""Problem trend from frequency: last 30 days vs the 30-90 days before (per 30 days)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core import clock
from app.models.clinical import Problem
from app.models.patient import Patient
from app.models.records import Entry
from app.models.user import User
from app.services.problems import problem_trend, refresh_problem_trends

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def ago(*days: int) -> list[datetime]:
    return [NOW - timedelta(days=d) for d in days]


@pytest.mark.parametrize(
    ("times", "expected"),
    [
        ([], None),
        (ago(5), None),  # one episode: nothing to compare yet
        (ago(2, 10, 20, 40, 70), "increasing"),  # 3 recent vs 1/month before
        (ago(40, 70), "decreasing"),  # none recently vs 1/month before
        (ago(10, 40, 70), "stable"),  # 1 recent vs 1/month before
        (ago(5, 25, 35, 45, 50, 60, 70, 85), "decreasing"),  # 2 recent vs 3/month before
        (ago(3, 9, 15, 21, 35, 42, 49, 56, 63, 70, 77, 84), "stable"),  # 4 vs 4/month
        (ago(100, 120), "stable"),  # all older than 90 days
        (ago(30, 31), "decreasing"),  # exactly 30 days ago counts as the earlier window
    ],
)
def test_trend_rule(times, expected):
    assert problem_trend(times, NOW) == expected


def _patient(db, email: str) -> int:
    user = User(email=email, password_hash="x", role="patient")
    db.add(user)
    db.flush()
    patient = Patient(user_id=user.id, name="Trend")
    db.add(patient)
    db.flush()
    return patient.id


def test_trend_comes_back_down_when_episodes_stop(db):
    """The old rule set 'increasing' at the 3rd episode and never went down."""
    pid = _patient(db, "trend1@x.com")
    problem = Problem(patient_id=pid, name="headache", status="active", trend="increasing")
    db.add(problem)
    for t in ago(50, 45, 40):
        db.add(Entry(patient_id=pid, type="symptom", structured={"name": "headache"}, occurred_at=t))
    db.flush()
    with clock.frozen_at(NOW):
        refresh_problem_trends(db, pid)
    assert problem.trend == "decreasing"


def test_problems_without_episodes_keep_their_trend(db):
    pid = _patient(db, "trend2@x.com")
    glucose = Problem(patient_id=pid, name="elevated blood glucose", status="active", trend="rising")
    db.add(glucose)
    db.flush()
    with clock.frozen_at(NOW):
        refresh_problem_trends(db, pid)
    assert glucose.trend == "rising"
