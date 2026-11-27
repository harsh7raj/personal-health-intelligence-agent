"""Retrieval functions for the assistant (memory.md D28). Plain Python, no LLM: every
item comes back with a stable evidence id ("E12" entry, "V5" reading, "M3" medicine
event, "R2" report, "D7" dose log) and an IST date, so a reply can cite it and the UI can
link it. Searches ALL history, not just the memory window.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.data.symptom_synonyms import canonical_symptom
from app.models.clinical import DoseLog, Medication, MedicationEvent, Problem, VitalReading
from app.models.records import Entry, Report
from app.services.med_schedule import normalize_dose_times
from app.services.problems import episode_entries, names_for
from app.services.vitals_trend import lab_vital_type
from app.vectorstore.collections import get_entries_collection, get_reports_collection


def _day(when: datetime) -> str:
    return clock.to_local(when).date().isoformat()


def _iso_day(value: str | None) -> str:
    try:
        return _day(datetime.fromisoformat(value or ""))
    except ValueError:
        return (value or "")[:10]


def _hhmm(when: datetime) -> str:
    return clock.to_local(when).strftime("%H:%M")


def entry_item(e: Entry) -> dict:
    s = e.structured or {}
    return {
        "id": f"E{e.id}", "kind": "entry", "entry_id": e.id, "type": e.type,
        "date": _day(e.occurred_at), "time": _hhmm(e.occurred_at),
        "name": s.get("name"), "text": e.raw_text, "tags": s.get("context_tags") or [],
        "severity": (s.get("attributes") or {}).get("severity"),
    }


def reading_item(r: VitalReading) -> dict:
    return {
        "id": f"V{r.id}", "kind": "reading", "vital_type": r.vital_type, "value": r.value,
        "unit": r.unit, "date": _day(r.recorded_at), "time": _hhmm(r.recorded_at),
    }


def med_event_item(ev: MedicationEvent) -> dict:
    return {
        "id": f"M{ev.id}", "kind": "medication_event", "medication": ev.medication_name,
        "event": ev.event_type, "date": ev.event_date.isoformat(), "old_dose": ev.old_dose,
        "new_dose": ev.new_dose, "prescriber": ev.prescriber, "source": ev.source,
    }


def symptom_history(db: Session, patient_id: int, name: str) -> list[dict]:
    """Every past episode of a symptom: canonical name, synonyms and the matching
    problem's aliases. Oldest first."""
    canonical = canonical_symptom(name)
    names = {canonical}
    for p in db.scalars(select(Problem).where(Problem.patient_id == patient_id)).all():
        own = names_for(p.name, p.attributes)
        if canonical in own:
            names |= own
    return [entry_item(e) for e in episode_entries(db, patient_id, names)]


def around(db: Session, patient_id: int, when: datetime, hours: int = 48) -> dict:
    """What else was logged near a moment: entries, readings, medicine events, doses."""
    lo, hi = when - timedelta(hours=hours), when + timedelta(hours=hours)
    entries = db.scalars(
        select(Entry).where(Entry.patient_id == patient_id, Entry.occurred_at.between(lo, hi))
        .order_by(Entry.occurred_at)
    ).all()
    readings = db.scalars(
        select(VitalReading).where(
            VitalReading.patient_id == patient_id, VitalReading.recorded_at.between(lo, hi)
        ).order_by(VitalReading.recorded_at)
    ).all()
    lo_day, hi_day = clock.to_local(lo).date(), clock.to_local(hi).date()
    events = db.scalars(
        select(MedicationEvent).where(
            MedicationEvent.patient_id == patient_id,
            MedicationEvent.event_date.between(lo_day, hi_day),
        )
    ).all()
    doses = db.scalars(
        select(DoseLog).where(
            DoseLog.patient_id == patient_id, DoseLog.scheduled_date.between(lo_day, hi_day)
        )
    ).all()
    med_names = {m.id: m.name for m in db.scalars(
        select(Medication).where(Medication.patient_id == patient_id)).all()}
    return {
        "entries": [entry_item(e) for e in entries],
        "readings": [reading_item(r) for r in readings],
        "medication_events": [med_event_item(ev) for ev in events],
        "doses_taken": [
            {"id": f"D{d.id}", "kind": "dose", "medication": med_names.get(d.medication_id),
             "date": d.scheduled_date.isoformat(), "time": d.scheduled_time}
            for d in doses
        ],
    }


def vital_series(db: Session, patient_id: int, vital_type: str, days: int = 90) -> list[dict]:
    since = clock.now() - timedelta(days=days)
    rows = db.scalars(
        select(VitalReading).where(
            VitalReading.patient_id == patient_id, VitalReading.vital_type == vital_type,
            VitalReading.recorded_at >= since,
        ).order_by(VitalReading.recorded_at)
    ).all()
    return [reading_item(r) for r in rows]


def lab_series(db: Session, patient_id: int, test: str) -> list[dict]:
    rows = db.scalars(
        select(VitalReading).where(
            VitalReading.patient_id == patient_id, VitalReading.vital_type == lab_vital_type(test)
        ).order_by(VitalReading.recorded_at)
    ).all()
    return [
        {**reading_item(r), "kind": "lab", "test": (r.attributes or {}).get("test_name") or test,
         "reference_range": (r.attributes or {}).get("reference_range"),
         "flag": (r.attributes or {}).get("flag"), "report_id": (r.attributes or {}).get("report_id")}
        for r in rows
    ]


def medication_events(db: Session, patient_id: int, days: int | None = None) -> list[dict]:
    q = select(MedicationEvent).where(MedicationEvent.patient_id == patient_id)
    if days is not None:
        q = q.where(MedicationEvent.event_date >= clock.today() - timedelta(days=days))
    return [med_event_item(ev) for ev in db.scalars(q.order_by(MedicationEvent.event_date)).all()]


def missed_doses(db: Session, patient_id: int, days: int = 14) -> list[dict]:
    """Scheduled doses in the past `days` with no "taken" mark. Described as "not marked
    taken": the record can't tell a missed dose from one that wasn't ticked."""
    today = clock.today()
    taken = {
        (d.medication_id, d.scheduled_date, d.scheduled_time)
        for d in db.scalars(select(DoseLog).where(
            DoseLog.patient_id == patient_id, DoseLog.scheduled_date >= today - timedelta(days=days)
        )).all()
    }
    out: list[dict] = []
    for m in db.scalars(select(Medication).where(
        Medication.patient_id == patient_id, Medication.active.is_(True)
    )).all():
        anchor = m.started_on or clock.to_local(m.created_at).date()
        interval = max(1, m.interval_days or 1)
        for back in range(1, days + 1):  # past days only; today may still be ahead
            day: date = today - timedelta(days=back)
            if day < anchor or (day - anchor).days % interval:
                continue
            for t in normalize_dose_times(m.dose_times):
                if (m.id, day, t) not in taken:
                    out.append({"kind": "dose_not_marked", "medication": m.name,
                                "date": day.isoformat(), "time": t})
    return sorted(out, key=lambda d: (d["date"], d["time"]))


def reports(db: Session, patient_id: int, report_type: str | None = None) -> list[dict]:
    q = select(Report).where(Report.patient_id == patient_id, Report.status == "parsed")
    if report_type:
        q = q.where(Report.report_type == report_type)
    return [
        {"id": f"R{r.id}", "kind": "report", "report_id": r.id, "report_type": r.report_type,
         "date": (r.test_date.isoformat() if r.test_date else _day(r.created_at)),
         "summary": r.ai_summary, "values": r.extracted_values or []}
        for r in db.scalars(q.order_by(Report.test_date.desc().nullslast(), Report.id.desc())).all()
    ]


def visit_notes(db: Session, patient_id: int, doctor: str | None = None) -> list[dict]:
    """Confirmed doctor-visit notes. The visits table arrives in Phase 3."""
    return []


def search(patient_id: int, text: str, k: int = 5) -> list[dict]:
    """Semantic search over entries and report chunks (Chroma)."""
    out: list[dict] = []
    for coll, kind in ((get_entries_collection, "entry"), (get_reports_collection, "report")):
        try:
            res = coll().query(query_texts=[text], n_results=k, where={"patient_id": patient_id})
        except Exception:
            continue
        for doc, meta, dist in zip(
            (res.get("documents") or [[]])[0], (res.get("metadatas") or [[]])[0],
            (res.get("distances") or [[]])[0],
        ):
            ident = f"E{meta.get('entry_id')}" if kind == "entry" else f"R{meta.get('report_id')}"
            out.append({"id": ident, "kind": kind, "text": doc, "distance": dist,
                        "date": _iso_day(meta.get("date"))})
    return sorted(out, key=lambda x: x["distance"])[:k]
