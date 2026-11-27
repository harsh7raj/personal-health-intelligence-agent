"""Recurrence detector (memory.md D29). No LLM: code finds the pattern, the assistant only
words it.

For a symptom it returns the episodes (dates, gaps), the circumstances shared by at least
two of them, and medicine changes that every episode came after. Circumstances are only
things the record shows; nothing here says one thing caused another.
"""

from collections import Counter
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.models.clinical import DoseLog, Medication, MedicationEvent, VitalReading
from app.models.records import Entry
from app.services.retrieval import symptom_history

TAG_WINDOW = timedelta(hours=6)  # "skipped lunch" logged up to 6h before the episode counts
GLUCOSE_WINDOW = timedelta(hours=24)
LOW_GLUCOSE = 70  # mg/dL, same line as the low_glucose alert

_TAG_LABELS = {
    "skipped_meal": "a skipped meal within 6 hours before",
    "delayed_meal": "a delayed meal within 6 hours before",
    "poor_sleep": "poor sleep logged within 6 hours before",
    "stress": "stress logged within 6 hours before",
    "missed_dose": "a missed dose logged within 6 hours before",
    "alcohol": "alcohol logged within 6 hours before",
    "exercise": "exercise logged within 6 hours before",
    "travel": "travel logged within 6 hours before",
}


def _episode_factors(db: Session, patient_id: int, entry: Entry) -> dict[str, str]:
    """{factor key: human label} for one episode."""
    t = entry.occurred_at
    factors: dict[str, str] = {}
    nearby = db.scalars(
        select(Entry).where(
            Entry.patient_id == patient_id, Entry.occurred_at.between(t - TAG_WINDOW, t)
        )
    ).all()
    for e in [entry, *nearby]:
        for tag in (e.structured or {}).get("context_tags") or []:
            if tag in _TAG_LABELS:
                factors[f"tag:{tag}"] = _TAG_LABELS[tag]
    low = db.scalars(
        select(VitalReading).where(
            VitalReading.patient_id == patient_id, VitalReading.vital_type == "blood_glucose",
            VitalReading.recorded_at.between(t - GLUCOSE_WINDOW, t + GLUCOSE_WINDOW),
            VitalReading.value < LOW_GLUCOSE,
        )
    ).all()
    if low:
        factors["glucose_below_70"] = f"a glucose reading below {LOW_GLUCOSE} mg/dL within 24 hours"
    local = clock.to_local(t)
    doses = db.scalars(
        select(DoseLog).where(DoseLog.patient_id == patient_id, DoseLog.scheduled_date == local.date())
    ).all()
    names = {m.id: m.name for m in db.scalars(
        select(Medication).where(Medication.patient_id == patient_id)).all()}
    for d in doses:
        if d.scheduled_time <= local.strftime("%H:%M"):
            med = names.get(d.medication_id, "a medicine")
            factors[f"dose:{med.lower()}"] = f"a {med} dose marked taken earlier that day"
    return factors


def detect(db: Session, patient_id: int, name: str, exclude_entry_id: int | None = None) -> dict:
    history = symptom_history(db, patient_id, name)
    episodes = [h for h in history if h["entry_id"] != exclude_entry_id]
    rows = {e.id: e for e in db.scalars(
        select(Entry).where(Entry.id.in_([h["entry_id"] for h in history]))).all()}

    per_episode = {h["id"]: _episode_factors(db, patient_id, rows[h["entry_id"]]) for h in history}
    counts: Counter[str] = Counter(k for f in per_episode.values() for k in f)
    labels = {k: v for f in per_episode.values() for k, v in f.items()}
    shared = [
        {"factor": k, "label": labels[k], "count": n, "of": len(history),
         "episodes": [eid for eid, f in per_episode.items() if k in f]}
        for k, n in counts.most_common() if n >= 2
    ]

    times = [rows[h["entry_id"]].occurred_at for h in history]
    gaps = [round((b - a).total_seconds() / 86400, 1) for a, b in zip(times, times[1:])]

    after_change: list[dict] = []
    if len(history) >= 2:
        first_day = clock.to_local(min(times)).date()
        for ev in db.scalars(select(MedicationEvent).where(
            MedicationEvent.patient_id == patient_id,
            MedicationEvent.event_type.in_(["start", "dose_change"]),
            MedicationEvent.event_date <= first_day,
        ).order_by(MedicationEvent.event_date.desc())).all():
            after_change.append({
                "id": f"M{ev.id}", "medication": ev.medication_name, "event": ev.event_type,
                "date": ev.event_date.isoformat(), "old_dose": ev.old_dose, "new_dose": ev.new_dose,
                "days_to_first_episode": (first_day - ev.event_date).days,
            })
            break  # the most recent change before the first episode

    return {
        "symptom": history[0]["name"] if history else name,
        "episode_count": len(history),
        "prior_episodes": episodes,
        "gaps_days": gaps,
        "shared_factors": shared,
        "all_after_medication_change": after_change,
    }
