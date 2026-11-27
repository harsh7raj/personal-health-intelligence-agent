"""Doctor visit recaps (ROADMAP.md Phase 3, memory.md D37).

recap (typed or transcribed) -> Sonnet structures it (the doctor's words attributed) -> code checks
every medicine name (RxNorm; misheard names) and previews clashes with other doctors' medicines ->
the user edits and confirms -> code applies the medicine changes as this doctor's, creates
reminders, saves the questions, embeds the note, and re-runs the medication safety check.
Nothing is applied before the user confirms (ground rule)."""

import difflib
import json
import logging
import re
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.llm import is_available, llm_json
from app.data.symptom_synonyms import canonical_symptom
from app.models.clinical import Medication, MedicationEvent
from app.models.drugs import MedCheckRun
from app.models.intelligence import Alert
from app.models.records import Entry
from app.models.visits import Reminder, SavedQuestion, Visit
from app.services import brand_generic, med_events, med_safety, retrieval, rxnorm
from app.services.language_guard import is_diagnostic
from app.services.med_schedule import default_dose_times

logger = logging.getLogger(__name__)

ACTIONS = ("start", "stop", "change")
LIST_FIELDS = ("discussed", "doctor_said", "watch_for", "questions_next_time")

STRUCTURE_SYSTEM = """You turn a patient's own recap of a doctor visit into a structured note. Use ONLY \
what the recap says; never add advice, a diagnosis, a cause or an interpretation of your own. Anything \
the doctor said (a diagnosis, a cause, an instruction, a warning) goes in "doctor_said", worded as the \
doctor's: "Dr. Rao said ...". Medicine names: write them exactly as heard.
Return JSON with exactly these keys:
{"reason": "why the visit happened, one sentence, or null",
 "discussed": ["short points"],
 "doctor_said": ["Dr. X said ..."],
 "medicine_changes": [{"action": "start" | "stop" | "change", "name": "...", "dose": "new dose or null",
   "frequency": "e.g. once daily, or null", "reason": "the doctor's reason as said, or null"}],
 "tests_ordered": [{"name": "...", "when": "as said, or null"}],
 "follow_up": {"when": "as said, e.g. in 6 weeks, or null"},
 "watch_for": ["things the doctor asked them to watch for"],
 "questions_next_time": ["questions the patient wants to ask next time"]}
Use [] or null when the recap doesn't say."""

_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8, "ten": 10,
        "twelve": 12}


def due_date(when: str | None, visit_date: date) -> date | None:
    """'in 6 weeks' / 'after two months' / '10 days' -> a date counted from the visit (code, not AI)."""
    m = re.search(r"\b(\d+|a|an|one|two|three|four|five|six|eight|ten|twelve)\s*(day|week|month)s?\b",
                  (when or "").lower())
    if not m:
        return None
    n = int(m.group(1)) if m.group(1).isdigit() else _NUM[m.group(1)]
    days = {"day": 1, "week": 7, "month": 30}[m.group(2)] * n
    return visit_date + timedelta(days=days)


def _str_list(v) -> list[str]:
    return [str(x).strip() for x in v if isinstance(x, (str, int, float)) and str(x).strip()] if isinstance(v, list) else []


def _attributed(text: str, doctor: str) -> str:
    t = text.strip()
    if re.match(r"^(dr\.?\s|doctor\b|the doctor\b|my doctor\b|" + re.escape(doctor.lower()) + ")", t.lower()):
        return t
    return f"{doctor} said: {t[0].lower() + t[1:] if t else t}"


def normalize(raw: dict, doctor: str, visit_date: date) -> dict:
    """Clean the model's JSON: known keys only, attributed doctor statements, dates in code.
    A diagnosis or cause written outside "doctor_said" is moved there, attributed."""
    out = {k: _str_list(raw.get(k)) for k in LIST_FIELDS}
    out["reason"] = (str(raw.get("reason")).strip() or None) if raw.get("reason") else None
    out["doctor_said"] = [_attributed(t, doctor) for t in out["doctor_said"]]
    for key in ("discussed", "watch_for"):
        keep = []
        for t in out[key]:
            (out["doctor_said"].append(_attributed(t, doctor)) if is_diagnostic(t) else keep.append(t))
        out[key] = keep
    if out["reason"] and is_diagnostic(out["reason"]):
        out["doctor_said"].append(_attributed(out["reason"], doctor))
        out["reason"] = None
    changes = []
    for c in raw.get("medicine_changes") or []:
        if not isinstance(c, dict) or not str(c.get("name") or "").strip():
            continue
        action = str(c.get("action") or "").lower()
        changes.append({"action": action if action in ACTIONS else "change", "name": str(c["name"]).strip(),
                        "dose": (str(c["dose"]).strip() or None) if c.get("dose") else None,
                        "frequency": (str(c["frequency"]).strip() or None) if c.get("frequency") else None,
                        "reason": (str(c["reason"]).strip() or None) if c.get("reason") else None})
    out["medicine_changes"] = changes
    tests = []
    for t in raw.get("tests_ordered") or []:
        name = str((t or {}).get("name") or "").strip() if isinstance(t, dict) else str(t).strip()
        when = (t or {}).get("when") if isinstance(t, dict) else None
        if name:
            d = due_date(when, visit_date)
            tests.append({"name": name, "when": when, "due_date": d.isoformat() if d else None})
    out["tests_ordered"] = tests
    fu = raw.get("follow_up") if isinstance(raw.get("follow_up"), dict) else {}
    when = fu.get("when")
    d = due_date(when, visit_date)
    out["follow_up"] = {"when": when, "date": d.isoformat() if d else None} if when else None
    return out


def structure(transcript: str, doctor: str, visit_date: date) -> tuple[dict, str]:
    """(structured note, generated_by). Without an LLM the recap lands in "discussed" to edit."""
    if is_available() and transcript.strip():
        try:
            raw = llm_json("visit_structure", STRUCTURE_SYSTEM, json.dumps(
                {"doctor": doctor, "visit_date": visit_date.isoformat(), "recap": transcript}))
            return normalize(raw, doctor, visit_date), "llm"
        except Exception:
            logger.warning("visit structuring failed; leaving the recap to edit", exc_info=True)
    empty = {"reason": None, "medicine_changes": [], "tests_ordered": [], "follow_up": None,
             **{k: [] for k in LIST_FIELDS}}
    empty["discussed"] = [transcript.strip()] if transcript.strip() else []
    return empty, "fallback"


def normalize_edit(edited: dict, doctor: str, visit_date: date) -> dict:
    """The user's edits on the review screen: same shape as normalize(), keeping the user's
    choices on each medicine change (which listed medicine it is, confirmed ingredients)."""
    out = normalize(edited, doctor, visit_date)
    for mine, theirs in zip(out["medicine_changes"], edited.get("medicine_changes") or []):
        if isinstance(theirs, dict):
            if isinstance(theirs.get("medication_id"), int):
                mine["medication_id"] = theirs["medication_id"]
            if isinstance(theirs.get("ingredients"), list):
                mine["ingredients"] = [str(i).strip().lower() for i in theirs["ingredients"] if str(i).strip()]
            if theirs.get("confirmed") is True:
                mine["confirmed"] = True
    for t_out, t_in in zip(out["tests_ordered"], edited.get("tests_ordered") or []):
        if isinstance(t_in, dict) and t_in.get("due_date"):
            t_out["due_date"] = str(t_in["due_date"])[:10]
    fu = edited.get("follow_up")
    if isinstance(fu, dict) and fu.get("date"):
        out["follow_up"] = {"when": fu.get("when") or fu["date"], "date": str(fu["date"])[:10]}
    return out


# --------------------------------------------------------------------------- medicine checks


def _active(db: Session, pid: int) -> list[Medication]:
    return list(db.scalars(select(Medication).where(Medication.patient_id == pid, Medication.active.is_(True))).all())


def _similar(name: str, meds: list[Medication]) -> Medication | None:
    n = name.lower().split()[0] if name.strip() else ""
    best, score = None, 0.0
    for m in meds:
        for cand in [m.name, *(m.ingredients or [])]:
            c = cand.lower().split()[0]
            r = difflib.SequenceMatcher(None, n, c).ratio()
            if r > score and n[:2] == c[:2]:
                best, score = m, r
    return best if score >= 0.55 else None


def check_change(db: Session, pid: int, change: dict) -> dict:
    """Is this name a real medicine, and which current medicine does it refer to? Flags names
    to "please check": not in RxNorm, not on the list for a stop/change, or close to a listed
    medicine with a different ingredient (speech-to-text: glipizide vs glimepiride)."""
    meds = _active(db, pid)
    found = rxnorm.lookup(change["name"])
    ingredients = change.get("ingredients") or found["ingredients"]
    match = next((m for m in meds if m.id == change.get("medication_id")), None)
    if match is None and ingredients:
        match = next((m for m in meds if set(m.ingredients or []) & set(ingredients)), None)
    if match is None:
        match = next((m for m in meds if m.name.lower() == change["name"].lower()), None)
    out = {"status": "ok", "ingredients": ingredients, "rxnorm": found["status"],
           "medication_id": match.id if match else None, "matched_name": match.name if match else None,
           "note": None, "suggestion": []}
    if found["status"] != "found" and not change.get("ingredients"):
        res = brand_generic.resolve(change["name"])
        out.update(status="please_check", suggestion=res["suggestion"],
                   note=f"\"{change['name']}\" isn't in RxNorm"
                        + (f". It may be {' + '.join(s['name'] for s in res['suggestion'])} (AI suggestion)."
                           if res["suggestion"] else ". Check the spelling on the prescription."))
    near = _similar(change["name"], meds) if match is None else None
    if near is not None:
        out.update(status="please_check", medication_id=near.id if change["action"] != "start" else None,
                   suggested_medication_id=near.id, matched_name=near.name,
                   note=f"Did you mean {near.name} (on your list)? Speech-to-text can mishear medicine names.")
    elif change["action"] in ("stop", "change") and match is None:
        out.update(status="please_check", note=f"{change['name']} isn't on your medicine list.")
    return out


def checked_changes(db: Session, pid: int, structured: dict) -> list[dict]:
    return [{**c, "check": check_change(db, pid, c)} for c in structured.get("medicine_changes") or []]


def preview_clashes(db: Session, pid: int, visit: Visit) -> dict:
    """What the new or changed medicines would raise against everything else (other doctors'
    medicines included), before anything is saved."""
    meds = _active(db, pid)
    proposed, replaced = [], set()
    for i, c in enumerate(checked_changes(db, pid, visit.structured)):
        if c["check"]["medication_id"]:
            replaced.add(c["check"]["medication_id"])
        if c["action"] in ("start", "change") and c["check"]["ingredients"]:
            proposed.append(Medication(id=-(i + 1), patient_id=pid, name=c["name"], ingredients=c["check"]["ingredients"],
                                       dose_times=[], prescriber=visit.doctor_name))
    others = [m for m in meds if m.id not in replaced]
    if not proposed:
        return {"findings": [], "message": None}
    ctx = med_safety._Ctx(db, pid, [*others, *proposed])
    pairs = [(p, o) for p in proposed for o in others] + [
        (a, b) for i, a in enumerate(proposed) for b in proposed[i + 1:]]
    findings, results = med_safety.pair_findings(ctx, pairs)
    findings += med_safety._duplicates_across_doctors(ctx)
    return {"findings": [{**f, "id": f"P{i}"} for i, f in enumerate(findings, start=1)],
            "message": None if findings else med_safety.NO_FINDING}


# --------------------------------------------------------------------------- confirm


def note_text(visit: Visit) -> str:
    s = visit.structured
    parts = [f"Visit with {visit.doctor_name} on {visit.visit_date.isoformat()}."]
    if s.get("reason"):
        parts.append(f"Reason: {s['reason']}")
    parts += s.get("doctor_said") or []
    for c in s.get("medicine_changes") or []:
        parts.append(f"Medicine {c['action']}: {c['name']} {c.get('dose') or ''}".strip())
    if s.get("follow_up"):
        parts.append(f"Follow-up: {s['follow_up'].get('when')}")
    return " ".join(parts)


class NeedsReview(Exception):
    """Some medicine names still need the user's check before the note can be applied."""


def confirm(db: Session, pid: int, visit: Visit, *, apply_medicines: bool = True) -> dict:
    """Apply a reviewed note. apply_medicines=False keeps the medicine changes in the note only
    (the demo replay, whose script records those changes with their own dates)."""
    changes = checked_changes(db, pid, visit.structured)
    pending = [c["name"] for c in changes if c["check"]["status"] == "please_check" and not c.get("confirmed")]
    if pending and apply_medicines:
        raise NeedsReview(", ".join(pending))
    applied: list[str] = []
    for c in changes if apply_medicines else []:
        mid = c.get("medication_id") or c["check"]["medication_id"]
        note = f"Visit with {visit.doctor_name}" + (f": {c['reason']}" if c.get("reason") else "")
        if c["action"] == "start":
            ingredients = brand_generic.confirmed_ingredients(c.get("ingredients") or c["check"]["ingredients"])
            med = Medication(patient_id=pid, name=c["name"], dose=c.get("dose"), frequency=c.get("frequency"),
                             dose_times=default_dose_times(c.get("frequency")), prescriber=visit.doctor_name,
                             prescriber_specialty=visit.specialty, started_on=visit.visit_date,
                             ingredients=ingredients, brand_name=c["name"] if c.get("ingredients") else None)
            db.add(med)
            db.flush()
            med_events.record(db, med, "start", event_date=visit.visit_date, new_dose=med.dose,
                              source="visit_note", note=note)
            applied.append(f"Started {med.name}")
            continue
        med = db.get(Medication, mid) if mid else None
        if med is None or med.patient_id != pid:
            continue
        before = med_events.snapshot(med)
        if c["action"] == "stop":
            med.active = False
        elif c.get("dose"):
            med.dose = c["dose"]
        if c.get("frequency"):
            med.frequency = c["frequency"]
        med.prescriber, med.prescriber_specialty = visit.doctor_name, visit.specialty or med.prescriber_specialty
        for ev in med_events.record_changes(db, med, before, event_date=visit.visit_date, source="visit_note"):
            ev.note = note
        applied.append(f"{'Stopped' if c['action'] == 'stop' else 'Changed'} {med.name}")
    s = visit.structured
    for t in s.get("tests_ordered") or []:
        db.add(Reminder(patient_id=pid, visit_id=visit.id, kind="test", text=f"Test: {t['name']}",
                        doctor_name=visit.doctor_name,
                        due_date=date.fromisoformat(t["due_date"]) if t.get("due_date") else None))
    fu = s.get("follow_up")
    if fu:
        db.add(Reminder(patient_id=pid, visit_id=visit.id, kind="follow_up",
                        text=f"Follow-up with {visit.doctor_name}" + (f" ({fu['when']})" if fu.get("when") else ""),
                        doctor_name=visit.doctor_name,
                        due_date=date.fromisoformat(fu["date"]) if fu.get("date") else None))
    for q in s.get("questions_next_time") or []:
        db.add(SavedQuestion(patient_id=pid, text=q, doctor_name=visit.doctor_name, source="visit", source_id=visit.id))
    visit.status, visit.confirmed_at = "confirmed", clock.now()
    visit.structured = {**s, "medicine_changes": [{k: v for k, v in c.items() if k != "check"} for c in changes]}
    db.commit()
    try:  # so the assistant's semantic search can recall it too
        from app.vectorstore.collections import get_entries_collection

        get_entries_collection().upsert(documents=[note_text(visit)], ids=[f"visit_{visit.id}"], metadatas=[{
            "patient_id": pid, "type": "visit_note", "visit_id": visit.id, "date": visit.visit_date.isoformat()}])
    except Exception:
        logger.warning("could not embed visit %s", visit.id, exc_info=True)
    return {"applied": applied}


# --------------------------------------------------------------------------- recall + brief


def _same_doctor(a: str | None, b: str | None) -> bool:
    norm = lambda s: re.sub(r"^dr\.?\s*", "", (s or "").strip().lower())  # noqa: E731
    return bool(a and b) and norm(a) == norm(b)


def visit_items(db: Session, pid: int, doctor: str | None = None, limit: int = 5) -> list[dict]:
    """Confirmed visit notes as citable evidence (ids D<visit id>), newest first."""
    rows = db.scalars(select(Visit).where(Visit.patient_id == pid, Visit.status == "confirmed")
                      .order_by(Visit.visit_date.desc(), Visit.id.desc())).all()
    out = []
    for v in rows:
        if doctor and not _same_doctor(v.doctor_name, doctor):
            continue
        s = v.structured or {}
        out.append({"id": f"D{v.id}", "kind": "visit_note", "visit_id": v.id, "date": v.visit_date.isoformat(),
                    "doctor": v.doctor_name, "specialty": v.specialty, "reason": s.get("reason"),
                    "doctor_said": s.get("doctor_said") or [], "medicine_changes": s.get("medicine_changes") or [],
                    "tests_ordered": s.get("tests_ordered") or [], "follow_up": s.get("follow_up"),
                    "watch_for": s.get("watch_for") or [], "text": " ".join(s.get("doctor_said") or [])[:400]})
        if len(out) >= limit:
            break
    return out


def doctors(db: Session, pid: int) -> list[dict]:
    """Doctors from visits and prescriptions, with their last visit."""
    seen: dict[str, dict] = {}
    for v in db.scalars(select(Visit).where(Visit.patient_id == pid).order_by(Visit.visit_date)).all():
        seen[v.doctor_name.strip().lower()] = {"name": v.doctor_name, "specialty": v.specialty,
                                               "last_visit": v.visit_date.isoformat()}
    for m in _active(db, pid):
        if m.prescriber and m.prescriber.strip().lower() not in seen:
            seen[m.prescriber.strip().lower()] = {"name": m.prescriber, "specialty": m.prescriber_specialty,
                                                  "last_visit": None}
    return sorted(seen.values(), key=lambda d: d["name"])


def brief(db: Session, pid: int, doctor: str) -> dict:
    """Everything worth bringing to the next visit with `doctor`, built in code (no LLM)."""
    last = (visit_items(db, pid, doctor, limit=1) or [None])[0]
    since = date.fromisoformat(last["date"]) if last else clock.today() - timedelta(days=90)
    entries = db.scalars(select(Entry).where(Entry.patient_id == pid, Entry.type == "symptom")
                         .order_by(Entry.occurred_at)).all()
    symptoms: dict[str, dict] = {}
    for e in entries:
        day = clock.to_local(e.occurred_at).date()
        if day < since:
            continue
        name = canonical_symptom((e.structured or {}).get("name") or "") or "symptom"
        s = symptoms.setdefault(name, {"name": name, "count": 0, "dates": []})
        s["count"] += 1
        s["dates"].append(day.isoformat())
    readings = {}
    days = max(1, (clock.today() - since).days)
    for vt in ("blood_glucose", "bp_systolic", "bp_diastolic", "weight"):
        series = [r for r in retrieval.vital_series(db, pid, vt, days=days)]
        if series:
            vals = [r["value"] for r in series]
            readings[vt] = {"count": len(vals), "latest": series[-1], "lowest": min(vals), "highest": max(vals),
                            "average": round(sum(vals) / len(vals), 1)}
    alerts = db.scalars(select(Alert).where(Alert.patient_id == pid).order_by(Alert.created_at.desc())).all()
    alerts = [{"date": clock.to_local(a.created_at).date().isoformat(), "message": a.message}
              for a in alerts if clock.to_local(a.created_at).date() >= since][:10]
    reports = [{"id": r["id"], "report_id": r["report_id"], "type": r["report_type"], "date": r["date"],
                "outside_range": [{k: v.get(k) for k in ("test_name", "value", "unit", "reference_range", "flag")}
                                  for v in r["values"] if v.get("flag") in ("high", "low")]}
               for r in retrieval.reports(db, pid) if r["date"] and r["date"] >= since.isoformat()]
    not_marked = retrieval.missed_doses(db, pid, days=min(days, 60))
    adherence: dict[str, int] = {}
    for d in not_marked:
        adherence[d.get("medication") or d.get("name") or "medicine"] = adherence.get(d.get("medication") or
                                                                                    d.get("name") or "medicine", 0) + 1
    events = db.scalars(select(MedicationEvent).where(MedicationEvent.patient_id == pid,
                                                      MedicationEvent.event_date >= since)
                        .order_by(MedicationEvent.event_date)).all()
    other_changes = [retrieval.med_event_item(ev) for ev in events if not _same_doctor(ev.prescriber, doctor)]
    run = db.scalar(select(MedCheckRun).where(MedCheckRun.patient_id == pid))
    findings = (run.result or {}).get("findings", []) if run else []
    questions = db.scalars(select(SavedQuestion).where(SavedQuestion.patient_id == pid, SavedQuestion.done.is_(False))
                           .order_by(SavedQuestion.created_at)).all()
    reminders = db.scalars(select(Reminder).where(Reminder.patient_id == pid, Reminder.done.is_(False))
                           .order_by(Reminder.due_date.nulls_last())).all()
    meds = [{"name": m.name, "dose": m.dose, "frequency": m.frequency, "prescriber": m.prescriber}
            for m in sorted(_active(db, pid), key=lambda m: m.name)]
    return {
        "doctor": doctor, "generated_on": clock.today().isoformat(), "since": since.isoformat(),
        "last_visit": last, "current_medicines": meds,
        "symptoms_since": sorted(symptoms.values(), key=lambda s: -s["count"])[:8],
        "readings_since": readings, "alerts_since": alerts, "reports_since": reports,
        "doses_not_marked": {"days": min(days, 60), "count": len(not_marked), "by_medicine": adherence},
        "other_doctors_changes": other_changes,
        "medication_findings": [{k: f.get(k) for k in ("id", "level_label", "severity", "title", "explanation",
                                                       "quote", "source", "medicines")} for f in findings],
        "questions": [{"id": q.id, "text": q.text, "source": q.source, "doctor_name": q.doctor_name}
                      for q in questions if q.doctor_name is None or _same_doctor(q.doctor_name, doctor)],
        "reminders": [{"id": r.id, "kind": r.kind, "text": r.text,
                       "due_date": r.due_date.isoformat() if r.due_date else None}
                      for r in reminders if r.doctor_name is None or _same_doctor(r.doctor_name, doctor)],
        "visit_count": db.scalar(select(func.count(Visit.id)).where(Visit.patient_id == pid,
                                                                    Visit.status == "confirmed")),
    }
