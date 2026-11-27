"""Symptom co-occurrence clustering (OQ5: within CLUSTER_WINDOW_HOURS, min 2 distinct)."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.models.clinical import SymptomCluster
from app.models.records import Entry

settings = get_settings()


def _norm(name: str | None) -> str:
    return (name or "").strip().lower()


def update_clusters(db: Session, patient_id: int, new_entry: dict) -> SymptomCluster | None:
    window = clock.now() - timedelta(hours=settings.CLUSTER_WINDOW_HOURS)
    rows = db.scalars(
        select(Entry).where(
            Entry.patient_id == patient_id,
            Entry.type == "symptom",
            Entry.occurred_at >= window,
        )
    ).all()

    names = sorted(
        {_norm((e.structured or {}).get("name")) for e in rows if (e.structured or {}).get("name")}
    )
    names = [n for n in names if n]
    if len(names) < 2:
        return None

    now = clock.now()
    for c in db.scalars(
        select(SymptomCluster).where(SymptomCluster.patient_id == patient_id)
    ).all():
        if sorted(_norm(x) for x in (c.symptoms or [])) == names:
            c.occurrences = (c.occurrences or 0) + 1
            c.last_seen = now
            return c

    cluster = SymptomCluster(
        patient_id=patient_id, symptoms=names, occurrences=1, last_seen=now
    )
    db.add(cluster)
    return cluster
