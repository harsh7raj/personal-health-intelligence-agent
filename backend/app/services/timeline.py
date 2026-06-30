"""Timeline point detail — assembles the FULL context for a date window from the
canonical tables (entries, vital_readings, observations, alerts). This is real
backend work: a timeline point on the dashboard only knows a date; this service
pulls everything that actually happened around that date so the detail modal shows
the patient's own words, the numbers recorded, and what the system surfaced — not a
re-derivation of data already on the page."""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clinical import VitalReading
from app.models.intelligence import Alert, Observation
from app.models.records import Entry


def _window_bounds(
    day: date, window_days: int, start_day: date | None
) -> tuple[datetime, datetime]:
    """Half-open UTC bounds [start, end).

    Two modes, picked by the event TYPE the caller is rendering:
    - Point-in-time event (start_day is None): symmetric `day ± window_days`.
    - Span/derived event (start_day given): the explicit evidence range
      [start_day 00:00, day+1 00:00) — e.g. the first→last reading window that
      actually produced a trend. `window_days` is ignored in this mode.
    """
    if start_day is not None:
        lo = min(start_day, day)
        start = datetime.combine(lo, time.min, tzinfo=timezone.utc)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc)
        return start, end
    lo = day - timedelta(days=window_days)
    hi = day + timedelta(days=window_days + 1)
    start = datetime.combine(lo, time.min, tzinfo=timezone.utc)
    end = datetime.combine(hi, time.min, tzinfo=timezone.utc)
    return start, end


def build_timeline_detail(
    db: Session,
    patient_id: int,
    day: date,
    window_days: int = 1,
    start_day: date | None = None,
) -> dict:
    window_days = max(0, window_days)
    start, end = _window_bounds(day, window_days, start_day)

    entries = list(
        db.scalars(
            select(Entry)
            .where(
                Entry.patient_id == patient_id,
                Entry.created_at >= start,
                Entry.created_at < end,
            )
            .order_by(Entry.created_at)
        ).all()
    )
    readings = list(
        db.scalars(
            select(VitalReading)
            .where(
                VitalReading.patient_id == patient_id,
                VitalReading.recorded_at >= start,
                VitalReading.recorded_at < end,
            )
            .order_by(VitalReading.recorded_at)
        ).all()
    )
    observations = list(
        db.scalars(
            select(Observation)
            .where(
                Observation.patient_id == patient_id,
                Observation.created_at >= start,
                Observation.created_at < end,
            )
            .order_by(Observation.created_at)
        ).all()
    )
    alerts = list(
        db.scalars(
            select(Alert)
            .where(
                Alert.patient_id == patient_id,
                Alert.created_at >= start,
                Alert.created_at < end,
            )
            .order_by(Alert.created_at)
        ).all()
    )

    return {
        "date": day,
        "window_days": window_days,
        "entries": entries,
        "vital_readings": readings,
        "observations": observations,
        "alerts": alerts,
    }
