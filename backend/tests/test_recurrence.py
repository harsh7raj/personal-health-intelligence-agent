"""Recurrence detector + retrieval, on a Harsh-style history: three shaky episodes on days he
skipped lunch after his morning glimepiride, two with low readings, all after a dose increase."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core import clock
from app.models.clinical import DoseLog, Medication, MedicationEvent, VitalReading
from app.models.patient import Patient
from app.models.records import Entry
from app.models.user import User
from app.services import retrieval
from app.services.recurrence import detect

IST = ZoneInfo("Asia/Kolkata")
DAYS = [date(2026, 7, 1), date(2026, 8, 3), date(2026, 9, 20)]


def _ist(d: date, h: int, m: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, m, tzinfo=IST)


def _harsh(db) -> tuple[int, list[Entry]]:
    user = User(email="harsh-rec@x.com", password_hash="x", role="patient")
    db.add(user)
    db.flush()
    p = Patient(user_id=user.id, name="Harsh")
    db.add(p)
    db.flush()
    med = Medication(patient_id=p.id, name="Glimepiride", dose="2 mg", dose_times=["08:00"],
                     prescriber="Dr. Rao")
    db.add(med)
    db.flush()
    db.add(MedicationEvent(patient_id=p.id, medication_id=med.id, medication_name="Glimepiride",
                           event_type="dose_change", event_date=date(2026, 6, 10),
                           old_dose="1 mg", new_dose="2 mg", prescriber="Dr. Rao"))
    episodes = []
    for i, d in enumerate(DAYS):
        db.add(DoseLog(patient_id=p.id, medication_id=med.id, scheduled_date=d, scheduled_time="08:00"))
        # "skipped lunch" logged separately 2h before the first two; tagged on the third itself
        if i < 2:
            db.add(Entry(patient_id=p.id, type="note", raw_text="skipped lunch, back-to-back calls",
                         structured={"name": "note", "context_tags": ["skipped_meal"]},
                         occurred_at=_ist(d, 13)))
        e = Entry(patient_id=p.id, type="symptom", raw_text="shaky and sweaty, heart racing",
                  structured={"name": "shakiness",
                              "context_tags": ["skipped_meal"] if i == 2 else []},
                  occurred_at=_ist(d, 15))
        db.add(e)
        episodes.append(e)
        if i < 2:
            db.add(VitalReading(patient_id=p.id, vital_type="blood_glucose", value=62 + 4 * i,
                                unit="mg/dL", recorded_at=_ist(d, 15, 20)))
    db.flush()
    return p.id, episodes


def test_recurrence_finds_dates_shared_circumstances_and_the_dose_change(db):
    pid, episodes = _harsh(db)
    r = detect(db, pid, "shaky")  # canonical: shakiness
    assert r["episode_count"] == 3
    assert [e["date"] for e in r["prior_episodes"]] == [d.isoformat() for d in DAYS]
    assert r["gaps_days"] == [33.0, 48.0]
    shared = {f["factor"]: (f["count"], f["of"]) for f in r["shared_factors"]}
    assert shared["tag:skipped_meal"] == (3, 3)
    assert shared["dose:glimepiride"] == (3, 3)
    assert shared["glucose_below_70"] == (2, 3)
    change = r["all_after_medication_change"][0]
    assert (change["medication"], change["old_dose"], change["new_dose"]) == ("Glimepiride", "1 mg", "2 mg")
    assert change["days_to_first_episode"] == 21

    latest = detect(db, pid, "shakiness", exclude_entry_id=episodes[-1].id)
    assert len(latest["prior_episodes"]) == 2  # "prior" leaves out the one just logged


def test_retrieval_functions(db):
    pid, episodes = _harsh(db)
    hist = retrieval.symptom_history(db, pid, "trembling")
    assert [h["id"] for h in hist] == [f"E{e.id}" for e in episodes]
    assert hist[0]["date"] == "2026-07-01" and hist[0]["time"] == "15:00"

    near = retrieval.around(db, pid, episodes[0].occurred_at, hours=6)
    assert {e["type"] for e in near["entries"]} == {"note", "symptom"}
    assert [r["value"] for r in near["readings"]] == [62]
    assert [d["medication"] for d in near["doses_taken"]] == ["Glimepiride"]

    events = retrieval.medication_events(db, pid)
    assert [(e["event"], e["date"]) for e in events] == [("dose_change", "2026-06-10")]


def test_missed_doses_are_scheduled_slots_not_marked_taken(db):
    user = User(email="doses@x.com", password_hash="x", role="patient")
    db.add(user)
    db.flush()
    p = Patient(user_id=user.id, name="Doses")
    db.add(p)
    db.flush()
    today = date(2026, 6, 20)
    med = Medication(patient_id=p.id, name="Metformin", dose_times=["08:00"],
                     started_on=today - timedelta(days=5))
    db.add(med)
    db.flush()
    for back in (1, 2, 4):
        db.add(DoseLog(patient_id=p.id, medication_id=med.id,
                       scheduled_date=today - timedelta(days=back), scheduled_time="08:00"))
    db.flush()
    with clock.frozen_at(_ist(today, 10)):
        missed = retrieval.missed_doses(db, p.id, days=7)
    assert [m["date"] for m in missed] == ["2026-06-15", "2026-06-17"]
