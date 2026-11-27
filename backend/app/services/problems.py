"""Active/Resolved problem maintenance from symptom entries (D3 single table)."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.models.clinical import Problem

settings = get_settings()

_ACTIVE = ["active", "managed"]


def _norm(name: str | None) -> str:
    return (name or "").strip().lower()


def occurred_at(new_entry: dict) -> datetime:
    """When the episode happened (backdated by intake), else now."""
    raw = new_entry.get("occurred_at")
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return clock.now()


def upsert_problem_from_symptom(db: Session, patient_id: int, new_entry: dict) -> Problem:
    s = new_entry.get("structured", {}) or {}
    name = new_entry.get("name") or s.get("name") or "unspecified symptom"
    attrs = s.get("attributes", {}) or {}
    severity = attrs.get("severity")
    when = occurred_at(new_entry)
    norm = _norm(name)

    existing = next(
        (
            p
            for p in db.scalars(
                select(Problem).where(
                    Problem.patient_id == patient_id, Problem.status.in_(_ACTIVE)
                )
            ).all()
            if _norm(p.name) == norm
        ),
        None,
    )

    if existing is not None:
        count = int((existing.attributes or {}).get("episode_count", 1)) + 1
        existing.attributes = {**(existing.attributes or {}), "episode_count": count}
        # A backdated episode can be older than what we've seen; widen both ends.
        existing.last_seen = max(existing.last_seen, when) if existing.last_seen else when
        existing.first_seen = min(existing.first_seen, when) if existing.first_seen else when
        existing.frequency = f"{count} episodes"
        existing.trend = "increasing" if count >= 3 else "stable"
        if severity:
            existing.severity = severity
        return existing

    prob = Problem(
        patient_id=patient_id,
        name=name,
        status="active",
        severity=severity,
        frequency="1 episode",
        trend=None,
        first_seen=when,
        last_seen=when,
        attributes={"episode_count": 1},
    )
    db.add(prob)
    return prob


def auto_resolve(db: Session, patient_id: int) -> list[str]:
    cutoff = clock.now() - timedelta(days=settings.RESOLVE_AFTER_DAYS)
    now = clock.now()
    resolved: list[str] = []
    for p in db.scalars(
        select(Problem).where(
            Problem.patient_id == patient_id, Problem.status.in_(_ACTIVE)
        )
    ).all():
        if p.last_seen is not None and p.last_seen < cutoff:
            p.status = "resolved"
            p.resolved_at = now
            resolved.append(p.name)
    return resolved
