"""Active/Resolved problem maintenance from symptom entries (D3 single table)."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.models.clinical import Problem

settings = get_settings()

_ACTIVE = ["active", "managed"]


def _norm(name: str | None) -> str:
    return (name or "").strip().lower()


def upsert_problem_from_symptom(db: Session, patient_id: int, new_entry: dict) -> Problem:
    s = new_entry.get("structured", {}) or {}
    name = new_entry.get("name") or s.get("name") or "unspecified symptom"
    attrs = s.get("attributes", {}) or {}
    severity = attrs.get("severity")
    now = clock.now()
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
        existing.last_seen = now
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
        first_seen=now,
        last_seen=now,
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
