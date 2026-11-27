"""LLM-authored observations. Strictly observational — never diagnostic."""

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.llm import is_available, llm_json
from app.models.clinical import Problem, SymptomCluster, VitalSummary
from app.models.intelligence import Observation
from app.services.language_guard import is_diagnostic

logger = logging.getLogger(__name__)

_SYSTEM = """You write SHORT, factual, NON-DIAGNOSTIC observations about patterns in a \
patient's longitudinal health data. HARD RULES: never state or imply a diagnosis; never name a \
disease/condition as fact; never assert a cause ("caused by", "due to", "because of"); never \
recommend treatment or medication. CRITICAL: use ONLY the problems, vitals, lab report findings, \
related past entries and clusters present in the provided JSON — NEVER invent a symptom, reading, \
value, date, or event that is not explicitly in the data. Only describe observed patterns/trends/\
frequencies. When a lab report finding is relevant, cite it (test name, value, and that it came from a \
report/lab panel). When a related past entry is relevant, say when it was logged using its date \
(e.g. "a similar headache was logged on 2026-03-02"). GOOD: "Headache \
episodes have increased to 3 in two months." GOOD: "LDL Cholesterol was 158 mg/dL on the latest lipid \
panel and has trended upward across reports." BAD (invented): "Chest heaviness has been reported." \
BAD (diagnostic): "You have migraines", "This is caused by stress". Return JSON: {"observations": \
[strings]} with 0 to 3 short items; empty list if nothing noteworthy."""


RELATED_MAX_DISTANCE = 1.0  # same "close enough" cut-off the Log page uses
RELATED_LIMIT = 5


def related_past_entries(context_bundle: dict | None) -> list[dict]:
    """The close past entries the Memory agent retrieved, with their IST date and id, so an
    observation can say when something happened before (and the evidence can cite it)."""
    out: list[dict] = []
    for m in (context_bundle or {}).get("semantic_matches", []):
        meta = (m or {}).get("metadata") or {}
        if not m.get("text") or (m.get("distance") or 0) >= RELATED_MAX_DISTANCE:
            continue
        try:
            day = clock.to_local(datetime.fromisoformat(meta["date"])).date().isoformat()
        except (KeyError, TypeError, ValueError):
            day = None
        out.append({"entry_id": meta.get("entry_id"), "date": day, "text": m["text"]})
    return out[:RELATED_LIMIT]


def _for_llm(payload: dict) -> dict:
    """What the model sees: the evidence minus database ids (it cites by date). Keeps the
    prompt identical across demo re-seeds, so cached answers are reused."""
    related = [{k: v for k, v in r.items() if k != "entry_id"} for r in payload["related_past_entries"]]
    return {**payload, "related_past_entries": related}


def generate_observations(
    db: Session, patient_id: int, new_entry: dict, context_bundle: dict | None
) -> list[str]:
    if not is_available():
        return []

    active = [
        {"name": p.name, "trend": p.trend, "frequency": p.frequency, "severity": p.severity}
        for p in db.scalars(
            select(Problem).where(
                Problem.patient_id == patient_id,
                Problem.status.in_(["active", "managed"]),
            ).order_by(Problem.name)
        ).all()
    ]
    all_summaries = db.scalars(
        select(VitalSummary).where(VitalSummary.patient_id == patient_id).order_by(VitalSummary.vital_type)
    ).all()
    # Split real vital signs from report-derived lab series (namespaced "lab_*") so the
    # LLM can tell "your BP" apart from "your LDL from the lipid panel".
    vitals = [
        {"vital_type": v.vital_type, "latest": v.latest, "trend": v.trend, "delta_pct": v.delta_pct}
        for v in all_summaries
        if not (v.vital_type or "").startswith("lab_")
    ]
    lab_trends = [
        {
            "test": (v.vital_type or "")[len("lab_"):].replace("_", " "),
            "latest": v.latest,
            "trend": v.trend,
            "delta_pct": v.delta_pct,
        }
        for v in all_summaries
        if (v.vital_type or "").startswith("lab_")
    ]
    clusters = [
        {"symptoms": c.symptoms, "occurrences": c.occurrences}
        for c in db.scalars(
            select(SymptomCluster).where(SymptomCluster.patient_id == patient_id).order_by(SymptomCluster.id)
        ).all()
    ]
    # Report chunks the Memory agent retrieved for this entry (lab values, summaries).
    report_findings = [
        {"text": m.get("text"), "report_type": (m.get("metadata") or {}).get("report_type")}
        for m in (context_bundle or {}).get("report_matches", [])
        if isinstance(m, dict) and m.get("text")
    ][:5]
    payload = {
        "new_entry": {"type": new_entry.get("type"), "name": new_entry.get("name")},
        "active_problems": active,
        "vital_trends": vitals,
        "lab_report_trends": lab_trends,
        "lab_report_findings": report_findings,
        "related_past_entries": related_past_entries(context_bundle),
        "symptom_clusters": clusters,
    }

    try:
        res = llm_json("observations", _SYSTEM, json.dumps(_for_llm(payload)))
    except Exception:
        logger.warning("observation generation failed", exc_info=True)
        return []

    created: list[str] = []
    for text in (res.get("observations") or [])[:3]:
        if not isinstance(text, str) or not text.strip():
            continue
        clean = text.strip()
        if is_diagnostic(clean):  # runtime non-diagnostic guard (Phase 8)
            logger.warning("dropped diagnostic-sounding observation: %s", clean)
            continue
        db.add(Observation(patient_id=patient_id, text=clean, evidence=payload))
        created.append(clean)
    return created
