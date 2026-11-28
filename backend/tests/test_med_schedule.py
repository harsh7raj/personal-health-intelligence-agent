"""Tests for the medication dose tracker (Part 3): dose_times expand into per-day slots
across a rolling 14-day window, meds group by purpose, and the adherence record
(mark/unmark) is idempotent. Tracking only — no advice text is asserted because none is
produced. Offline: per-drug timing reuse is stubbed so no network/LLM is touched."""

from datetime import date, datetime, timedelta, timezone

from app.core import clock
from app.models.clinical import DoseLog, Medication
from app.models.patient import Patient
from app.models.user import User
from app.services.med_schedule import (
    DAYS_BACK,
    DAYS_FORWARD,
    build_med_calendar,
    default_dose_times,
    normalize_dose_times,
    normalize_time,
)

_c = {"n": 0}


def _patient(db) -> int:
    _c["n"] += 1
    u = User(email=f"sched{_c['n']}@x.com", password_hash="x", role="patient")
    db.add(u)
    db.flush()
    p = Patient(user_id=u.id, name="Sched Test")
    db.add(p)
    db.flush()
    return p.id


def _add_med(db, pid, name, **kw) -> Medication:
    m = Medication(patient_id=pid, name=name, active=True, **kw)
    db.add(m)
    db.flush()
    return m


def test_default_dose_times_from_frequency():
    assert default_dose_times("once daily") == ["09:00"]
    assert default_dose_times("twice daily") == ["09:00", "21:00"]
    assert default_dose_times("three times daily") == ["08:00", "14:00", "20:00"]
    assert default_dose_times(None) == ["09:00"]  # unknown → single sensible default
    assert default_dose_times("") == ["09:00"]


def test_normalize_time_coerces_freeform_into_canonical_hhmm():
    assert normalize_time("9:00 AM") == "09:00"
    assert normalize_time("9:00 PM") == "21:00"
    assert normalize_time("12:00 AM") == "00:00"
    assert normalize_time("12:00 PM") == "12:00"
    assert normalize_time("9") == "09:00"
    assert normalize_time("21:30") == "21:30"
    assert normalize_time("8am") == "08:00"
    assert normalize_time("nonsense") is None
    assert normalize_time("25:00") is None
    # Every canonical result is exactly 5 chars → always fits dose_logs.scheduled_time.
    for v in ("9:00 AM", "9", "21:30", "8am"):
        assert len(normalize_time(v)) == 5


def test_normalize_dose_times_dedupes_sorts_and_drops_garbage():
    assert normalize_dose_times(["9:00 PM", "9:00 AM", "9am", "bad"]) == ["09:00", "21:00"]
    assert normalize_dose_times(None) == []


def test_calendar_canonicalizes_legacy_freeform_times(db, monkeypatch):
    """Regression: a med saved with a free-form time ('9:00 AM', 7 chars) must render a
    canonical 5-char slot so marking it taken fits dose_logs.scheduled_time (was a 500)."""
    monkeypatch.setattr("app.services.med_schedule._timing_for", lambda name: None)
    pid = _patient(db)
    _add_med(db, pid, "Paracetamol", dose_times=["9:00 AM", "9:00 PM"])
    db.flush()
    cal = build_med_calendar(db, pid)
    times = {s["time"] for day in cal["days"] for s in day["slots"]}
    assert times == {"09:00", "21:00"}
    assert all(len(t) == 5 for t in times)


def test_window_is_14_days_and_dose_times_expand_into_slots(db, monkeypatch):
    monkeypatch.setattr("app.services.med_schedule._timing_for", lambda name: "with food")
    pid = _patient(db)
    _add_med(db, pid, "Amlodipine", dose="5mg", dose_times=["09:00", "21:00"])
    db.flush()

    cal = build_med_calendar(db, pid)
    assert len(cal["days"]) == DAYS_BACK + DAYS_FORWARD + 1 == 14
    assert cal["start_date"] == clock.today() - timedelta(days=DAYS_BACK)
    assert cal["end_date"] == clock.today() + timedelta(days=DAYS_FORWARD)

    # Two dose_times → two slots every day, carrying the reused timing guidance.
    for day in cal["days"]:
        assert len(day["slots"]) == 2
        assert {s["time"] for s in day["slots"]} == {"09:00", "21:00"}
        assert all(s["timing"] == "with food" for s in day["slots"])


def test_future_slots_not_markable_past_and_today_markable(db, monkeypatch):
    monkeypatch.setattr("app.services.med_schedule._timing_for", lambda name: None)
    pid = _patient(db)
    _add_med(db, pid, "Metformin", dose_times=["08:00"])
    db.flush()
    cal = build_med_calendar(db, pid)
    today = clock.today()
    for day in cal["days"]:
        for s in day["slots"]:
            assert s["markable"] == (day["date"] <= today)


def test_grouping_by_purpose_with_other_fallback_and_stable_colors(db, monkeypatch):
    monkeypatch.setattr("app.services.med_schedule._timing_for", lambda name: None)
    pid = _patient(db)
    a = _add_med(db, pid, "Drop A", purpose="Eye strain", dose_times=["09:00"])
    b = _add_med(db, pid, "Drop B", purpose="Eye strain", dose_times=["09:00"])
    c = _add_med(db, pid, "Amlodipine", purpose=None, dose_times=["09:00"])
    db.flush()
    cal = build_med_calendar(db, pid)
    groups = {g["purpose"]: g for g in cal["groups"]}

    assert {m["name"] for m in groups["Eye strain"]["medications"]} == {"Drop A", "Drop B"}
    assert {m["name"] for m in groups["Other"]["medications"]} == {"Amlodipine"}

    # Color index is stable per med (assigned by sorted id) and unique across the set.
    colors = {m["id"]: m["color_index"] for g in cal["groups"] for m in g["medications"]}
    assert colors[a.id] == 0 and colors[b.id] == 1 and colors[c.id] == 2
    assert len(set(colors.values())) == 3


def test_adherence_overlay_marks_taken(db, monkeypatch):
    monkeypatch.setattr("app.services.med_schedule._timing_for", lambda name: None)
    pid = _patient(db)
    m = _add_med(db, pid, "Metformin", dose_times=["08:00", "20:00"])
    db.flush()
    today = clock.today()
    db.add(
        DoseLog(
            patient_id=pid, medication_id=m.id,
            scheduled_date=today, scheduled_time="08:00",
        )
    )
    db.flush()

    cal = build_med_calendar(db, pid)
    today_day = next(d for d in cal["days"] if d["date"] == today)
    by_time = {s["time"]: s for s in today_day["slots"]}
    assert by_time["08:00"]["taken"] is True
    assert by_time["20:00"]["taken"] is False


def test_today_is_the_ist_calendar_day_not_the_utc_one(db, monkeypatch):
    """20:00 UTC on 14 Mar is already 01:30 on 15 Mar in India: the tracker's today is the 15th."""
    monkeypatch.setattr("app.services.med_schedule._timing_for", lambda name: None)
    pid = _patient(db)
    _add_med(db, pid, "Metformin", dose_times=["08:00"])
    db.flush()
    with clock.frozen_at(datetime(2026, 3, 14, 20, 0, tzinfo=timezone.utc)):
        cal = build_med_calendar(db, pid)
    assert cal["today"] == date(2026, 3, 15)
    assert [d["date"] for d in cal["days"] if d["is_today"]] == [date(2026, 3, 15)]


def test_any_date_range_and_no_doses_before_the_start_date(db):
    pid = _patient(db)
    today = clock.today()
    _add_med(db, pid, "New Med", dose_times=["09:00"], started_on=today - timedelta(days=3))
    cal = build_med_calendar(db, pid, today - timedelta(days=10), today + timedelta(days=4))
    assert len(cal["days"]) == 15 and cal["start_date"] == today - timedelta(days=10)
    with_doses = [d["date"] for d in cal["days"] if d["slots"]]
    assert min(with_doses) == today - timedelta(days=3)  # nothing before it was started
    assert all(not s["markable"] for d in cal["days"] if d["is_future"] for s in d["slots"])
    month = build_med_calendar(db, pid, today - timedelta(days=100), today)  # capped
    assert len(month["days"]) == 62
