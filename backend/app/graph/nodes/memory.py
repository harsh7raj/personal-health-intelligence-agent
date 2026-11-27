from datetime import timedelta

from sqlalchemy import select

from app.core import clock
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.graph.state import GraphState
from app.models.clinical import Medication, Problem, VitalSummary
from app.models.records import Entry, MemoryLog
from app.vectorstore.collections import get_entries_collection, get_reports_collection

settings = get_settings()


def _semantic_matches(patient_id: int, entry_id: int | None, text: str) -> list[dict]:
    if not text:
        return []
    where: dict = {"patient_id": patient_id}
    if entry_id is not None:
        where = {"$and": [{"patient_id": patient_id}, {"entry_id": {"$ne": entry_id}}]}
    try:
        res = get_entries_collection().query(
            query_texts=[text], n_results=settings.MEMORY_TOPK, where=where
        )
    except Exception:
        return []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    return [
        {"text": d, "metadata": m, "distance": dist}
        for d, m, dist in zip(docs, metas, dists)
    ]


def _report_matches(patient_id: int, text: str) -> list[dict]:
    """Retrieve top-k report chunks from the patient_reports collection.

    Reports are embedded in a SEPARATE collection (memory.md section 5), so the entries
    query above never sees them — this is the step that actually surfaces report findings
    (lab values, whole-report summaries) into the Reasoning agent's context.
    """
    if not text:
        return []
    try:
        res = get_reports_collection().query(
            query_texts=[text],
            n_results=settings.MEMORY_TOPK,
            where={"patient_id": patient_id},
        )
    except Exception:
        return []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    return [
        {"text": d, "metadata": m, "distance": dist}
        for d, m, dist in zip(docs, metas, dists)
    ]


def memory_node(state: GraphState) -> dict:
    ne = state.new_entry or {}
    entry_id = ne.get("entry_id")
    text = ne.get("raw_text") or state.raw_input or ""  # a question has no entry
    pid = state.patient_id

    semantic = _semantic_matches(pid, entry_id, text)
    report_hits = _report_matches(pid, text)

    with SessionLocal() as db:
        active_problems = db.scalars(
            select(Problem).where(
                Problem.patient_id == pid,
                Problem.status.in_(["active", "managed"]),
            )
        ).all()
        vitals = db.scalars(
            select(VitalSummary).where(VitalSummary.patient_id == pid)
        ).all()
        meds = db.scalars(
            select(Medication).where(
                Medication.patient_id == pid, Medication.active.is_(True)
            )
        ).all()
        cutoff = clock.now() - timedelta(days=settings.RECENT_WINDOW_DAYS)
        recent = db.scalars(
            select(Entry)
            .where(Entry.patient_id == pid, Entry.occurred_at >= cutoff)
            .order_by(Entry.occurred_at.desc())
        ).all()

        context_bundle = {
            "semantic_matches": semantic,
            "report_matches": report_hits,
            "lab_trends": [
                {"vital_type": v.vital_type, "latest": v.latest, "trend": v.trend,
                 "delta_pct": v.delta_pct}
                for v in vitals
                if (v.vital_type or "").startswith("lab_")
            ],
            "active_problems": [
                {
                    "id": p.id,
                    "name": p.name,
                    "status": p.status,
                    "severity": p.severity,
                    "trend": p.trend,
                }
                for p in active_problems
            ],
            "vital_summary": [
                {"vital_type": v.vital_type, "latest": v.latest, "trend": v.trend}
                for v in vitals
            ],
            "medications": [
                {"id": m.id, "name": m.name, "dose": m.dose} for m in meds
            ],
            "recent_entries": [
                {
                    "id": e.id,
                    "type": e.type,
                    "raw_text": e.raw_text,
                    "date": e.occurred_at.isoformat() if e.occurred_at else None,
                }
                for e in recent
            ],
        }

        # Memory Agent 'writes JSON logs' — audit row (raw_entry is a snapshot, not truth).
        db.add(
            MemoryLog(
                patient_id=pid,
                entry_id=entry_id,
                raw_entry=ne,
                context_bundle=context_bundle,
            )
        )
        db.commit()

    return {"context_bundle": context_bundle}
