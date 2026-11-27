"""Symptom co-occurrence as PAIRS (memory.md D19; window = CLUSTER_WINDOW_HOURS, 48h).

For every pair of different symptoms, count the separate episodes in which both were
logged within the window of each other, by when they happened (occurred_at). Repeated
logs of the same pair inside one window count once, and a third symptom just adds its
own pairs instead of starting a new set. Recomputed from the entries each time, so
backdated or out-of-order logs land in the right episode.
"""

from datetime import datetime, timedelta
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.data.symptom_synonyms import canonical_symptom
from app.models.clinical import SymptomCluster
from app.models.records import Entry

settings = get_settings()

Pair = tuple[str, str]


def pair_episodes(
    events: list[tuple[str, datetime]], window: timedelta
) -> dict[Pair, tuple[int, datetime]]:
    """{(a, b): (episodes, last time both were present)} for symptoms a < b."""
    by_name: dict[str, list[datetime]] = {}
    for name, when in events:
        by_name.setdefault(name, []).append(when)

    result: dict[Pair, tuple[int, datetime]] = {}
    for a, b in combinations(sorted(by_name), 2):
        # Each moment both symptoms were present: the later of two logs within the window.
        moments = sorted(
            max(ta, tb) for ta in by_name[a] for tb in by_name[b] if abs(ta - tb) <= window
        )
        if not moments:
            continue
        episodes, episode_start = 0, None
        for m in moments:
            if episode_start is None or m - episode_start > window:
                episodes, episode_start = episodes + 1, m
        result[(a, b)] = (episodes, moments[-1])
    return result


def update_clusters(db: Session, patient_id: int) -> list[SymptomCluster]:
    """Recompute the patient's symptom pairs and sync the symptom_clusters rows."""
    rows = db.scalars(
        select(Entry).where(Entry.patient_id == patient_id, Entry.type == "symptom")
    ).all()
    events = [
        (name, e.occurred_at)
        for e in rows
        if e.occurred_at and (name := canonical_symptom((e.structured or {}).get("name")))
    ]
    pairs = pair_episodes(events, timedelta(hours=settings.CLUSTER_WINDOW_HOURS))

    existing = {
        tuple(sorted(canonical_symptom(s) for s in (c.symptoms or []))): c
        for c in db.scalars(
            select(SymptomCluster).where(SymptomCluster.patient_id == patient_id)
        ).all()
    }
    kept: list[SymptomCluster] = []
    for pair, (episodes, last_seen) in pairs.items():
        cluster = existing.pop(pair, None)
        if cluster is None:
            cluster = SymptomCluster(patient_id=patient_id, symptoms=list(pair))
            db.add(cluster)
        cluster.occurrences = episodes
        cluster.last_seen = last_seen
        kept.append(cluster)
    for stale in existing.values():  # old multi-symptom sets or pairs no longer present
        db.delete(stale)
    return kept
