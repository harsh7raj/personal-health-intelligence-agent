"""Medication dose tracker — a rolling 14-day calendar of scheduled doses plus the
patient's adherence record.

TRACKING ONLY (do not weaken): this surface records when doses fall and whether the
patient marked them taken. It is NOT medical advice. No LLM verdicts are produced here;
the only generated text is the per-drug *timing* guidance reused from the existing
non-diagnostic reference layer (MedlinePlus / labelled AI fallback). A gap in the record
is never written as a row and is never framed as a missed-dose judgement.
"""

import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.drug_reference import get_reference
from app.models.clinical import DoseLog, Medication
from app.services.drug_reference_ai import ai_reference
from app.services.rxnorm import normalize_ingredient

# Rolling window: a week of history (markable adherence) + the coming week (planning).
DAYS_BACK = 7
DAYS_FORWARD = 6  # inclusive → 7 back + today + 6 forward = 14 days

DISCLAIMER = (
    "For tracking only — not medical advice. Doses marked taken or left unmarked here are "
    "just a personal record; an unmarked dose is not a medical judgement. Talk to your "
    "doctor or pharmacist about your medication schedule."
)

# label → default "HH:MM" slots, used ONLY to pre-fill dose_times on create (editable after).
_FREQ_DEFAULTS: list[tuple[tuple[str, ...], list[str]]] = [
    (("four times", "4 times", "qid"), ["08:00", "12:00", "16:00", "20:00"]),
    (("three times", "3 times", "tid", "thrice"), ["08:00", "14:00", "20:00"]),
    (("twice", "two times", "2 times", "bid"), ["09:00", "21:00"]),
    (("once", "one time", "1 time", "daily", "qd", "every day"), ["09:00"]),
]


def default_dose_times(frequency: str | None) -> list[str]:
    """Best-effort default schedule from a free-text frequency label. Only used to seed
    dose_times when none were supplied; the user can edit afterwards."""
    f = (frequency or "").strip().lower()
    if not f:
        return ["09:00"]
    for needles, times in _FREQ_DEFAULTS:
        if any(n in f for n in needles):
            return times
    return ["09:00"]


# Accepts "9", "9:30", "09:30", "9am", "9 PM", "9:00 a.m." → canonical 24h "HH:MM".
_TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?\s*$|^\s*(\d{1,2})(?::(\d{2}))?\s*$", re.I)


def normalize_time(value: str) -> str | None:
    """Coerce one free-form time into canonical 24h "HH:MM", or None if unparseable.
    Guarantees a 5-char string so it always fits dose_logs.scheduled_time and matches
    the slot it was generated from."""
    m = _TIME_RE.match(str(value or ""))
    if not m:
        return None
    if m.group(1) is not None:  # 12h form with am/pm
        h, minute, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
        if ap == "a":
            h = 0 if h == 12 else h
        else:  # pm
            h = 12 if h == 12 else h + 12
    else:  # 24h form
        h, minute = int(m.group(4)), int(m.group(5) or 0)
    if not (0 <= h <= 23 and 0 <= minute <= 59):
        return None
    return f"{h:02d}:{minute:02d}"


def normalize_dose_times(raw: list[str] | None) -> list[str]:
    """Canonicalize, drop unparseable entries, de-duplicate, and sort a dose schedule."""
    out = [t for t in (normalize_time(v) for v in (raw or [])) if t]
    return sorted(dict.fromkeys(out))


_EVERY_N_DAYS = re.compile(r"every\s+(\d+)\s*day", re.I)
_EVERY_N_WEEKS = re.compile(r"every\s+(\d+)\s*week", re.I)


def parse_interval_days(frequency: str | None) -> int:
    """How many days apart the schedule repeats, parsed from the free-text frequency.
    1 = daily (default). Handles 'every 3 days', 'every other day', 'weekly', 'every 2
    weeks'. dose_times still controls how many doses fall on each *active* day."""
    f = (frequency or "").strip().lower()
    if not f:
        return 1
    if "every other day" in f or "alternate" in f:
        return 2
    m = _EVERY_N_WEEKS.search(f)
    if m:
        return max(1, int(m.group(1))) * 7
    if "weekly" in f or "every week" in f or "once a week" in f or "per week" in f:
        return 7
    m = _EVERY_N_DAYS.search(f)
    if m:
        return max(1, int(m.group(1)))
    return 1


def _timing_for(name: str) -> str | None:
    """Reuse the Part 1/2 per-drug reference timing guidance ('with food'). Curated
    MedlinePlus first, labelled AI fallback second. No new lookups, no interaction logic."""
    ingredient = normalize_ingredient(name)
    ref = get_reference(ingredient) or ai_reference(ingredient)
    return ref.get("timing") if ref else None


def build_med_calendar(db: Session, patient_id: int) -> dict:
    today = date.today()
    start = today - timedelta(days=DAYS_BACK)
    end = today + timedelta(days=DAYS_FORWARD)

    meds = list(
        db.scalars(
            select(Medication)
            .where(Medication.patient_id == patient_id, Medication.active.is_(True))
            .order_by(Medication.id)
        ).all()
    )

    # Stable per-med color index (by sorted id) so the legend and every slot agree.
    color_index = {m.id: i for i, m in enumerate(meds)}
    timing = {m.id: _timing_for(m.name) for m in meds}
    # Per-med repeat interval + the anchor day its schedule is phased from, so a med
    # taken "every 3 days" only lands on every third day (not every day).
    interval = {m.id: max(1, m.interval_days or 1) for m in meds}
    anchor = {m.id: (m.started_on or (m.created_at.date() if m.created_at else today)) for m in meds}

    # Adherence overlay: which (med, date, time) slots are marked taken in this window.
    taken_rows = db.scalars(
        select(DoseLog).where(
            DoseLog.patient_id == patient_id,
            DoseLog.scheduled_date >= start,
            DoseLog.scheduled_date <= end,
        )
    ).all()
    taken = {(r.medication_id, r.scheduled_date, r.scheduled_time) for r in taken_rows}

    days: list[dict] = []
    d = start
    while d <= end:
        is_future = d > today
        slots: list[dict] = []
        for m in meds:
            # Skip days that aren't "on" for a multi-day schedule (every-N-days).
            if interval[m.id] > 1 and (d - anchor[m.id]).days % interval[m.id] != 0:
                continue
            # Canonicalize here too, so even meds saved before normalization render
            # "HH:MM" slots that match (and fit) the dose_logs they write.
            for t in normalize_dose_times(m.dose_times):
                slots.append(
                    {
                        "medication_id": m.id,
                        "name": m.name,
                        "dose": m.dose,
                        "time": t,
                        "timing": timing[m.id],
                        "taken": (m.id, d, t) in taken,
                        # Only past/today slots are markable — you can't pre-mark a future dose.
                        "markable": not is_future,
                    }
                )
        slots.sort(key=lambda s: (s["time"], s["name"]))
        days.append(
            {
                "date": d,
                "is_today": d == today,
                "is_future": is_future,
                "slots": slots,
            }
        )
        d += timedelta(days=1)

    # Group meds by purpose ("Other" when unset) for the legend / clustering.
    groups: dict[str, list[dict]] = {}
    for m in meds:
        purpose = (m.purpose or "").strip() or "Other"
        groups.setdefault(purpose, []).append(
            {
                "id": m.id,
                "name": m.name,
                "dose": m.dose,
                "purpose": purpose,
                "color_index": color_index[m.id],
            }
        )
    group_list = [
        {"purpose": p, "medications": ms} for p, ms in sorted(groups.items())
    ]

    return {
        "start_date": start,
        "end_date": end,
        "today": today,
        "days": days,
        "groups": group_list,
        "medication_count": len(meds),
        "disclaimer": DISCLAIMER,
    }
