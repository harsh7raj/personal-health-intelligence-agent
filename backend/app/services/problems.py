"""Active/Resolved problem maintenance from symptom entries (D3 single table)."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.data.symptom_synonyms import canonical_symptom
from app.models.clinical import Problem
from app.models.records import Entry

settings = get_settings()

_ACTIVE = ["active", "managed"]


def names_for(name: str | None, attributes: dict | None) -> set[str]:
    """Canonical names that belong to a problem: its own name plus recorded aliases."""
    aliases = (attributes or {}).get("aliases") or []
    names = {canonical_symptom(name)} | {canonical_symptom(a) for a in aliases}
    return {n for n in names if n}


def problem_names(problem: Problem) -> set[str]:
    return names_for(problem.name, problem.attributes)


def episode_entries(db: Session, patient_id: int, names: set[str]) -> list[Entry]:
    """Symptom entries logged under any of `names`, oldest first by when they happened."""
    rows = db.scalars(
        select(Entry)
        .where(Entry.patient_id == patient_id, Entry.type == "symptom")
        .order_by(Entry.occurred_at)
    ).all()
    return [e for e in rows if canonical_symptom((e.structured or {}).get("name")) in names]


def entries_for_problem(db: Session, patient_id: int, problem: Problem) -> list[Entry]:
    return episode_entries(db, patient_id, problem_names(problem))


def _remember_alias(problem: Problem, reported: str | None) -> None:
    """Keep the user's own wording ("head pain") on the problem it was matched to."""
    variant = " ".join((reported or "").lower().split())
    attrs = dict(problem.attributes or {})
    aliases = list(attrs.get("aliases") or [])
    if variant and variant != (problem.name or "").lower() and variant not in aliases:
        attrs["aliases"] = [*aliases, variant]
        problem.attributes = attrs  # reassign so the JSONB change is saved


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
    raw_name = new_entry.get("name") or s.get("name") or "unspecified symptom"
    name = canonical_symptom(raw_name) or "unspecified symptom"
    reported = s.get("reported_name") or raw_name
    attrs = s.get("attributes", {}) or {}
    severity = attrs.get("severity")
    when = occurred_at(new_entry)

    # Match on canonical name or any alias ("headaches" / "head pain" -> headache).
    existing = next(
        (
            p
            for p in db.scalars(
                select(Problem).where(
                    Problem.patient_id == patient_id, Problem.status.in_(_ACTIVE)
                )
            ).all()
            if name in problem_names(p)
        ),
        None,
    )

    if existing is not None:
        _remember_alias(existing, reported)
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
    _remember_alias(prob, reported)
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
