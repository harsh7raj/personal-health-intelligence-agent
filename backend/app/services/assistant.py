"""The chat assistant's reply (memory.md D31). Code builds an evidence pack (facts with ids),
the LLM only words it and must cite ids; a reply citing anything outside the pack, or one the
language guard flags, is replaced by a plain list of the facts. Red flags skip the LLM.
"""

import json
import logging
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.llm import is_available, llm_json
from app.data.symptom_synonyms import SYNONYMS, canonical_symptom
from app.models.clinical import Medication, Problem
from app.models.records import ChatMessage
from app.services import red_flags, retrieval
from app.services.language_guard import is_diagnostic
from app.services.recurrence import detect
from app.services.vitals_trend import extract_readings

logger = logging.getLogger(__name__)

_CITE = re.compile(r"\[([A-Z]\d+)\]")
_TOPICS = {  # words in a question -> vital series worth showing
    "blood_glucose": ("sugar", "glucose", "hba1c", "diabet"),
    "bp_systolic": ("bp", "blood pressure", "pressure"),
    "bp_diastolic": ("bp", "blood pressure", "pressure"),
    "weight": ("weight", "kg"),
    "heart_rate": ("heart rate", "pulse"),
    "spo2": ("oxygen", "spo2"),
}
_REPORT_WORDS = ("report", "test", "lab", "result", "tsh", "thyroid", "cholesterol", "ldl", "hba1c", "panel")
_MED_WORDS = ("medicine", "medication", "tablet", "dose", "pill", "drug")

SYSTEM = """You are a personal health record assistant. You OBSERVE and EXPLAIN the user's own \
records; you never diagnose, never name a cause, never advise treatment or dose changes, and \
never say medicines are "safe" together.
Use ONLY the facts in the JSON evidence pack. After every fact you mention, cite its id in square \
brackets exactly as given, e.g. "on 2026-07-01 [E12]". Never cite an id that is not in the pack, and \
never invent dates, numbers or events. Quote a doctor's instruction only from "doctor_instructions", \
and say it is the doctor's ("Dr. Rao said on ...").
When "recurrence" shows earlier episodes, mention their dates, any shared circumstances (as \
circumstances, not causes) and a medicine change they all came after, then suggest practical \
next steps the record supports: checking and logging a reading, and raising the pattern with \
their doctor. If the pack does not answer a question, say so plainly.
Write 2 to 6 short sentences in plain language, addressed to the user ("you"). Use dates as written.
Return ONLY a JSON object, with no text before or after it: {"reply": "<text with [ids]>"}"""


def _mentioned_symptoms(db: Session, patient_id: int, text: str) -> list[str]:
    t = (text or "").lower()
    names = set()
    for p in db.scalars(select(Problem).where(Problem.patient_id == patient_id)).all():
        for n in [p.name, *((p.attributes or {}).get("aliases") or [])]:
            if n and re.search(rf"\b{re.escape(n.lower())}s?\b", t):
                names.add(canonical_symptom(p.name))
    for variant, canonical in SYNONYMS.items():
        if re.search(rf"\b{re.escape(variant)}\b", t):
            names.add(canonical)
    return sorted(names)


def _summarize_reading_series(items: list[dict]) -> dict | None:
    if not items:
        return None
    values = [i["value"] for i in items]
    return {"count": len(items), "first": items[0], "latest": items[-1],
            "lowest": min(items, key=lambda i: i["value"]), "highest": max(items, key=lambda i: i["value"]),
            "average": round(sum(values) / len(values), 1)}


def build_pack(
    db: Session, patient_id: int, *, message: str, kind: str, new_entry: dict | None,
    context_bundle: dict | None, focus: dict | None = None,
) -> tuple[dict, dict[str, dict]]:
    """(facts for the LLM, {evidence id: item}). Only what code found; nothing inferred."""
    items: dict[str, dict] = {}

    def keep(item: dict) -> dict:
        if item.get("id"):
            items[item["id"]] = item
        return item

    text = message.lower()
    pack: dict = {"today": clock.today().isoformat(), "message_kind": kind}

    if new_entry:
        s = new_entry.get("structured") or {}
        occurred = new_entry.get("occurred_at")
        pack["logged_now"] = keep({
            "id": f"E{new_entry['entry_id']}", "kind": "entry", "entry_id": new_entry["entry_id"],
            "name": new_entry.get("name"), "type": new_entry.get("type"),
            "date": clock.to_local(datetime.fromisoformat(occurred)).date().isoformat() if occurred else None,
            "tags": s.get("context_tags") or [], "text": new_entry.get("raw_text"),
        })

    symptoms = _mentioned_symptoms(db, patient_id, message)
    if new_entry and new_entry.get("type") == "symptom" and new_entry.get("name"):
        symptoms = sorted({canonical_symptom(new_entry["name"]), *symptoms})
    exclude = new_entry.get("entry_id") if new_entry else None
    recurrences = []
    for name in symptoms[:3]:
        r = detect(db, patient_id, name, exclude_entry_id=exclude)
        if r["episode_count"]:
            for ep in r["prior_episodes"]:
                keep(ep)
            for ch in r["all_after_medication_change"]:
                keep({**ch, "kind": "medication_event"})
            recurrences.append(r)
    if recurrences:
        pack["recurrence"] = recurrences

    related = []
    for m in (context_bundle or {}).get("semantic_matches", [])[:5]:
        meta = m.get("metadata") or {}
        if (m.get("distance") or 9) < 1.0 and meta.get("entry_id"):
            date = retrieval._iso_day(meta.get("date"))
            related.append(keep({"id": f"E{meta['entry_id']}", "kind": "entry", "entry_id": meta["entry_id"],
                                 "date": date, "text": m.get("text")}))
    if related:
        pack["related_past_entries"] = related

    series = {}
    for vital_type, words in _TOPICS.items():
        if any(w in text for w in words) or (new_entry and new_entry.get("type") == "vital"
                                             and vital_type in {r[0] for r in extract_readings(new_entry)}):
            readings = retrieval.vital_series(db, patient_id, vital_type, days=180)
            for r in readings[-12:]:
                keep(r)
            summary = _summarize_reading_series(readings)
            if summary:
                for key in ("first", "latest", "lowest", "highest"):
                    keep(summary[key])  # anything shown must be citable
                series[vital_type] = {"summary": summary, "recent": readings[-12:]}
    if series:
        pack["readings"] = series

    meds = db.scalars(select(Medication).where(Medication.patient_id == patient_id,
                                               Medication.active.is_(True))).all()
    if meds:
        pack["current_medicines"] = [{"name": m.name, "dose": m.dose, "prescriber": m.prescriber} for m in meds]
    events = retrieval.medication_events(db, patient_id, days=365)
    if events and (recurrences or any(w in text for w in _MED_WORDS)):
        pack["medication_changes"] = [keep(e) for e in events[-8:]]
    if any(w in text for w in _MED_WORDS + ("skip", "miss", "forgot")):
        not_marked = retrieval.missed_doses(db, patient_id, days=14)
        pack["doses_not_marked_taken_last_14_days"] = {"count": len(not_marked), "examples": not_marked[:6]}

    if any(w in text for w in _REPORT_WORDS) or (focus or {}).get("type") == "report":
        reps = retrieval.reports(db, patient_id)
        if (focus or {}).get("type") == "report":
            reps = [r for r in reps if r["report_id"] == focus.get("id")] or reps
        pack["reports"] = [keep(r) for r in reps[:3]]

    notes = retrieval.visit_notes(db, patient_id)
    if notes:
        pack["doctor_instructions"] = [keep(n) for n in notes]

    history = db.scalars(
        select(ChatMessage).where(ChatMessage.patient_id == patient_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(7)
    ).all()
    pack["recent_chat"] = [{"role": h.role, "text": h.content[:400]} for h in reversed(history)][:-1]
    return pack, items


def _fallback(pack: dict, items: dict[str, dict]) -> str:
    """Plain facts only, used when there is no LLM or its reply fails a check."""
    lines: list[str] = []
    logged = pack.get("logged_now")
    if logged:
        when = f" for {logged['date']}" if logged.get("date") and logged["date"] != pack["today"] else ""
        lines.append(f"Logged: {logged.get('name') or 'your entry'}{when} [{logged['id']}].")
    for r in pack.get("recurrence", []):
        prior = r["prior_episodes"]
        if prior:
            dates = ", ".join(f"{p['date']} [{p['id']}]" for p in prior[-5:])
            lines.append(f"Earlier {r['symptom']} entries: {dates}.")
        for f in r["shared_factors"][:3]:
            lines.append(f"{f['count']} of {f['of']} of these had {f['label']}.")
        for ch in r["all_after_medication_change"]:
            change = f"{ch['old_dose']} to {ch['new_dose']}" if ch["event"] == "dose_change" else "start"
            lines.append(f"All of them came after the {ch['medication']} {change} on {ch['date']} [{ch['id']}].")
    for vital_type, s in (pack.get("readings") or {}).items():
        latest = s["summary"]["latest"]
        lines.append(f"Latest {vital_type.replace('_', ' ')}: {latest['value']:g} on {latest['date']} [{latest['id']}] "
                     f"(average {s['summary']['average']:g} across {s['summary']['count']} readings).")
    for rep in pack.get("reports", [])[:1]:
        lines.append(f"Latest report: {rep['report_type']} on {rep['date']} [{rep['id']}].")
    if pack.get("recurrence"):
        lines.append("These are patterns in your records, not a diagnosis. Worth raising with your doctor.")
    if not lines:
        lines.append("I couldn't find anything about that in your records yet.")
    return " ".join(lines)


def check_reply(reply: str, items: dict[str, dict]) -> str | None:
    """Why a reply must be rejected, or None if it passes."""
    if not reply.strip():
        return "empty"
    unknown = [c for c in _CITE.findall(reply) if c not in items]
    if unknown:
        return f"cites ids not in the pack: {unknown}"
    if is_diagnostic(reply):
        return "diagnostic wording"
    return None


def cited_evidence(reply: str, items: dict[str, dict]) -> list[dict]:
    seen: list[str] = []
    for c in _CITE.findall(reply):
        if c in items and c not in seen:
            seen.append(c)
    return [items[c] for c in seen]


def respond(
    db: Session, patient_id: int, *, message: str, kind: str, new_entry: dict | None,
    context_bundle: dict | None, focus: dict | None = None,
) -> dict:
    readings = [(vt, v) for vt, v, _u in extract_readings(new_entry)] if new_entry else []
    escalation = red_flags.check(message, readings)  # code first, before any LLM
    pack, items = build_pack(db, patient_id, message=message, kind=kind, new_entry=new_entry,
                             context_bundle=context_bundle, focus=focus)
    if escalation:
        logged = pack.get("logged_now")
        reply = (f"I've logged this [{logged['id']}]. " if logged else "") + (
            "Because you described " + "; ".join(escalation["reasons"]) + ", please don't wait: "
            + ("call Tele-MANAS on 14416 or 112 now." if escalation["kind"] == "mental_health"
               else "get medical help now (call 112). Your doctor summary is ready to share if it helps.")
        )
        escalation = {**escalation, "offer": ["consultation_pdf", "share_link"]}
        return {"reply": reply, "evidence": cited_evidence(reply, items), "escalation": escalation,
                "generated_by": "rules"}

    reply, generated_by = None, "fallback"
    if is_available():
        try:
            res = llm_json("assistant", SYSTEM, json.dumps({"user_message": message, "evidence": pack}))
            candidate = str(res.get("reply") or "").strip()
            problem = check_reply(candidate, items)
            if problem:
                logger.warning("assistant reply rejected (%s); using the fact list", problem)
            else:
                reply, generated_by = candidate, "llm"
        except Exception:
            logger.warning("assistant LLM call failed; using the fact list", exc_info=True)
    if reply is None:
        reply = _fallback(pack, items)
    return {"reply": reply, "evidence": cited_evidence(reply, items), "escalation": None,
            "generated_by": generated_by}
