"""Health Story — LLM narrative (D15) with a deterministic fallback."""

import json
import logging
import re

from sqlalchemy.orm import Session

from app.core.llm import is_available, llm_json
from app.schemas.health_state import PatientHealthState
from app.services.state_assembler import assemble_state, derive_recent_changes

logger = logging.getLogger(__name__)

_SYSTEM = """You write a clear, specific, NON-DIAGNOSTIC health narrative from a patient's longitudinal data.
Write EXACTLY THREE short paragraphs, separated by a blank line (\\n\\n):
- Paragraph 1 — Headline: the single most notable trend right now, stated specifically with the numbers.
- Paragraph 2 — Connections: thoughtfully relate the findings to one another. Note where different patterns
  have developed over the same period, recur together, or move in the same direction, and reflect on why they
  may be worth watching together. Be substantive and specific — this is the most important paragraph.
- Paragraph 3 — Stable & to track: what has stayed steady or reassuring (including resolved issues), and what
  is missing or worth tracking next.
HARD NON-DIAGNOSTIC RULES: never state or imply a diagnosis; never name a disease/condition as a new fact;
never claim a medical cause (do NOT use "caused by", "due to", "because of", "leads to", "results in");
never recommend treatment or medication. You MAY describe temporal/associative patterns ("have risen over the
same months", "have appeared together", "are worth monitoring together") — as observations, not causal claims.
Use the actual numbers; avoid generic filler. Return JSON: {"story": "<three paragraphs separated by \\n\\n>"}."""


def _payload(state: PatientHealthState) -> dict:
    return {
        "known_conditions": state.medical_background.conditions,
        "active_problems": [
            {"name": p.name, "frequency": p.frequency, "trend": p.trend, "severity": p.severity}
            for p in state.active_problems
        ],
        "resolved_problems": [p.name for p in state.resolved_problems],
        "vital_trends": [
            {
                "vital_type": vt,
                "latest": v.latest,
                "trend": v.trend,
                "change_pct": round(v.delta_pct * 100, 1) if v.delta_pct is not None else None,
            }
            for vt, v in state.vital_summary.items()
        ],
        "symptom_clusters": [
            {"symptoms": c.symptoms, "occurrences": c.occurrences}
            for c in state.symptom_clusters
        ],
        "observations": [o.text for o in state.ai_observations],
        "recent_changes": derive_recent_changes(state),
        "missing_information": [m.description for m in state.missing_information],
    }


def _has_substantive_data(state: PatientHealthState) -> bool:
    """True only if there's real recorded data to narrate. Prevents the LLM from
    hallucinating a plausible-but-fabricated story from an empty payload (a brand-new
    account otherwise gets invented vitals, trends, etc.)."""
    return bool(
        state.active_problems
        or state.resolved_problems
        or state.vital_summary
        or state.symptom_clusters
        or state.ai_observations
        or state.medical_background.conditions
    )


def _fallback_story(state: PatientHealthState) -> str:
    parts: list[str] = []
    if state.active_problems:

        def describe(p) -> str:
            details = [d for d in (p.frequency, p.trend) if d]  # never print "None"
            return f"{p.name} ({', '.join(details)})" if details else p.name

        parts.append(f"Active problems: {', '.join(describe(p) for p in state.active_problems)}.")
    changes = derive_recent_changes(state)
    if changes:
        parts.append("Recent changes: " + "; ".join(changes) + ".")
    if state.ai_observations:
        parts.append("Observations: " + " ".join(o.text for o in state.ai_observations[:3]))
    if not parts:
        parts.append("No significant health data has been recorded yet.")
    return "\n\n".join(parts)


def build_story(db: Session, patient_id: int) -> dict:
    state = assemble_state(db, patient_id)
    # No real data yet → don't let the LLM invent one; return the deterministic fallback.
    if not _has_substantive_data(state):
        return {"story": _fallback_story(state), "generated_by": "fallback"}
    if is_available():
        try:
            res = llm_json("story", _SYSTEM, json.dumps(_payload(state)))
            story = (res.get("story") or "").strip()
            story = re.sub(r"[ \t]+\n", "\n", story)  # trim trailing spaces on lines
            story = re.sub(r"\n{3,}", "\n\n", story)  # collapse to single blank-line paragraph breaks
            if story:
                return {"story": story, "generated_by": "llm"}
        except Exception:
            logger.warning("story generation failed; using fallback", exc_info=True)
    return {"story": _fallback_story(state), "generated_by": "fallback"}



# --------------------------------------------------------------------------- detailed story

DETAILED_SYSTEM = """You write a patient's detailed health story from their own records (the JSON), for the \
patient to read. Use ONLY what the JSON contains, with the real numbers and dates; never invent anything.
Write these sections, each 3 to 6 sentences, skipping a section only if the JSON has nothing for it:
1. "Where things stand": the big picture right now (conditions, the most important trends, with numbers).
2. "Recurring patterns": each recurring symptom with its dates and the circumstances its episodes share (as
   circumstances, never causes), and any medicine change they all came after.
3. "Medicines and changes": current medicines, who prescribed them, dose changes with dates, and doses marked
   taken over the last 30 days.
4. "Readings and lab results": home readings (latest, range, direction) and lab values against their printed
   range and how they moved between reports.
5. "What your doctors said": the doctor's own words from confirmed visit notes, attributed ("Dr. Rao said ...").
6. "Steady or resolved": what has been stable or reassuring, and what has resolved.
7. "Worth tracking next": practical things to log or bring up at the next visit (open reminders, questions).
HARD RULES: never diagnose or say the person has a condition beyond their own listed conditions; never claim a
cause ("caused by", "due to", "because of", "leads to"); never recommend a treatment or dose change; never say
medicines are safe together. Refer to doctors by name, never as he or she. Address the reader as "you". \
For their listed conditions write "your record lists ..." (never "you have ...").
Return JSON: {"sections": [{"title": "...", "body": "..."}]}"""


def _detailed_payload(db: Session, patient_id: int, state: PatientHealthState) -> dict:
    from datetime import timedelta

    from sqlalchemy import select

    from app.core import clock
    from app.models.clinical import Medication
    from app.models.visits import Reminder, SavedQuestion
    from app.services import recurrence, report_explainer, retrieval
    from app.services.med_schedule import build_med_calendar
    from app.services.visits import visit_items

    base = _payload(state)
    today = clock.today()
    recurring = []
    counts = {}
    for p in state.active_problems:
        r = recurrence.detect(db, patient_id, p.name, exclude_entry_id=None)
        counts[p.name] = r["episode_count"]
        if r["episode_count"] >= 2:
            recurring.append({
                "symptom": r["symptom"], "dates": [e["date"] for e in r["prior_episodes"]][-6:],
                "shared": [f"{f['count']} of {f['of']} with {f['label']}" for f in r["shared_factors"]
                           if not f["factor"].startswith("dose:")][:3],
                "all_after": [f"{c['medication']} {c['event']} {c.get('old_dose') or ''} -> {c.get('new_dose') or ''} "
                              f"on {c['date']}" for c in r["all_after_medication_change"]][:2]})
    meds = db.scalars(select(Medication).where(Medication.patient_id == patient_id, Medication.active.is_(True))).all()
    cal = build_med_calendar(db, patient_id, today - timedelta(days=29), today)
    adherence: dict[int, list[int]] = {}
    for day in cal["days"]:
        for sl in day["slots"]:
            a = adherence.setdefault(sl["medication_id"], [0, 0])
            a[1] += 1
            a[0] += 1 if sl["taken"] else 0
    readings = {}
    for vt in ("blood_glucose", "bp_systolic", "bp_diastolic", "weight"):
        series = retrieval.vital_series(db, patient_id, vt, days=120)
        if series:
            vals = [x["value"] for x in series]
            readings[vt] = {"latest": series[-1]["value"], "latest_date": series[-1]["date"], "lowest": min(vals),
                            "highest": max(vals), "first_in_period": series[0]["value"], "count": len(vals)}
    labs = []
    for rep in retrieval.reports(db, patient_id)[:4]:
        from app.models.records import Report

        row = db.get(Report, rep["report_id"])
        for v in report_explainer.value_rows(db, patient_id, row):
            labs.append({"report_date": rep["date"], "test": v["display_name"], "value": v["value"], "unit": v["unit"],
                         "range": v["reference_range"], "flag": v["flag"],
                         "previous": v["previous"]["value"] if v["previous"] else None})
    # One count per symptom, and nothing listed as both active and resolved (stale summary fields).
    base["active_problems"] = [{"name": p.name, "episodes": counts.get(p.name), "trend": p.trend,
                                "severity": p.severity} for p in state.active_problems]
    # "(diagnosed 2018)" is the record's own wording, but it reads as a diagnosis in a narrative.
    base["known_conditions"] = [re.sub(r"\s*\((?:diagnosed|dx)[^)]*\)", "", str(c), flags=re.I).strip()
                                for c in base["known_conditions"] or []]
    active_names = {p.name.lower() for p in state.active_problems}
    base["resolved_problems"] = [n for n in base["resolved_problems"] if n.lower() not in active_names]
    return {**base, "today": today.isoformat(),
            "recurring_patterns": recurring,
            "medicines": [{"name": m.name, "dose": m.dose, "times": m.dose_times, "prescriber": m.prescriber,
                           "started_on": m.started_on.isoformat() if m.started_on else None,
                           "doses_marked_taken_last_30_days": f"{adherence.get(m.id, [0, 0])[0]} of "
                                                              f"{adherence.get(m.id, [0, 0])[1]}"} for m in meds],
            "medicine_changes": retrieval.medication_events(db, patient_id, days=400)[-8:],
            "home_readings_last_120_days": readings,
            "lab_results": labs[:16],
            "doctor_visits": [{"date": v["date"], "doctor": v["doctor"], "said": v["doctor_said"],
                               "watch_for": v["watch_for"]} for v in visit_items(db, patient_id, limit=3)],
            "open_reminders": [r.text for r in db.scalars(select(Reminder).where(
                Reminder.patient_id == patient_id, Reminder.done.is_(False))).all()],
            "saved_questions": [q.text for q in db.scalars(select(SavedQuestion).where(
                SavedQuestion.patient_id == patient_id, SavedQuestion.done.is_(False))).all()][:6]}


_detailed_cache: dict[int, tuple[str, dict]] = {}


def build_detailed_story(db: Session, patient_id: int, *, refresh: bool = False) -> dict:
    """The Story page's detailed version (sections). Cached until the record changes; the
    short build_story() stays as it is for the consultation PDF."""
    import hashlib

    from app.core import clock
    from app.services.language_guard import is_diagnostic
    from app.services.med_safety import signature

    state = assemble_state(db, patient_id)
    if not _has_substantive_data(state):
        return {"sections": [{"title": "Your story", "body": _fallback_story(state)}], "generated_by": "fallback",
                "generated_at": clock.now().isoformat()}
    key = hashlib.sha256(signature(db, patient_id).encode()).hexdigest()
    cached = _detailed_cache.get(patient_id)
    if cached and cached[0] == key and not refresh:
        return cached[1]
    payload = _detailed_payload(db, patient_id, state)
    sections, by = [], "fallback"
    if is_available():
        try:
            res = llm_json("story", DETAILED_SYSTEM, json.dumps(payload, default=str))
            for sec in res.get("sections") or []:
                title, body = str(sec.get("title") or "").strip(), str(sec.get("body") or "").strip()
                if title and body and not is_diagnostic(body, allow_attributed=title.startswith("What your doctor")):
                    sections.append({"title": title, "body": body})
            by = "llm" if sections else "fallback"
        except Exception:
            logger.warning("detailed story failed; using the short version", exc_info=True)
    if not sections:
        sections = [{"title": "Your story", "body": _fallback_story(state)}]
    out = {"sections": sections, "generated_by": by, "generated_at": clock.now().isoformat(),
           "based_on": {"problems": len(state.active_problems), "medicines": len(payload["medicines"]),
                        "lab_results": len(payload["lab_results"]), "visits": len(payload["doctor_visits"])}}
    if by == "llm":
        _detailed_cache[patient_id] = (key, out)
    return out
