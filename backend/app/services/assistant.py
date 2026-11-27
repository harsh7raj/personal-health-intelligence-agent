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
from app.core.llm import is_available, llm_text
from app.data.lab_glossary import mentioned as mentioned_tests
from app.data.symptom_synonyms import SYNONYMS, canonical_symptom
from app.models.clinical import Medication, Problem
from app.models.records import ChatMessage, Report
from app.models.drugs import MedCheckRun
from app.services import med_safety, red_flags, report_explainer, retrieval
from app.services.language_guard import is_diagnostic
from app.services.recurrence import detect
from app.services.vitals_trend import extract_readings

logger = logging.getLogger(__name__)

_CITE = re.compile(r"\[([A-Z]\d+)\]")
_TOPICS = {  # words in a question -> vital series worth showing
    "blood_glucose": ("sugar", "glucose", "hba1c", "diabet", "hypoglyc", "hyperglyc", "lows", "shaky"),
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
Use ONLY the facts in the JSON evidence pack. Cite each fact with its id in square brackets exactly \
as given. The app shows every [id] to the user as a clickable DATE, so write the id instead of the \
date: "a similar episode on [E12]", not "on 2026-07-01 [E12]". Mention at most 5 dated facts, the \
most relevant ones. Never cite an id that is not in the pack, and never invent dates, numbers or \
events. Quote a doctor's instruction only from "doctor_instructions", \
and say it is the doctor's ("Dr. Rao said on ..."). Refer to a doctor by name every time, never \
as he or she: the record doesn't say.
When "recurrence" shows earlier episodes, mention their dates, each shared circumstance it lists \
(including medicine doses marked taken earlier that day; as circumstances, not causes) and a \
medicine change they all came after, then suggest practical \
next steps the record supports: checking and logging a reading, and raising the pattern with \
their doctor. If the pack does not answer a question, say so plainly.
Write 2 to 6 short sentences in plain language, addressed to the user ("you").
Return only the reply text, with its [ids].
""" + report_explainer.FOLLOW_UP_RULES + """
MEDICINES: speak about medicine safety only from "med_check", "possible_side_effects", \
"medication_findings" or "pinned_finding". When a symptom is logged and "medication_findings" is present, \
mention the most relevant finding briefly (its level and [id]) as something to ask their pharmacist about, \
never as the cause. If a medicine was started or changed shortly before the recent episodes, say when, as a \
circumstance. Before saying a test result is missing, check "reports". Never say the record has no \
readings, symptoms or results of some kind: the pack holds only a selection, so say what it does show. Name each finding's level as given (Verified / Official label / AI flag \
(unverified)) and cite its [id]; quote label text only from its "quote". Never say medicines are \
safe together or that there is no interaction: when "med_check" has a "message", say exactly that \
message. Never suggest stopping, skipping or changing a medicine; when there is a concern, add \
"Don't stop or change any medicine on your own" and suggest asking their pharmacist or doctor."""

_CAN_I_TAKE = re.compile(
    r"\b(?:can|could|should|may) i (?:take|have|use|start)\s+(?:a |an |some )?(.+?)"
    r"(?:\s+(?:with|along|alongside|together|while|if|for|now|today)\b|[?.!,]|$)|"
    r"\bis it (?:ok|okay|fine|safe) to (?:take|have|use)\s+(?:a |an |some )?(.+?)(?:\s+with\b|[?.!,]|$)",
    re.IGNORECASE,
)


def asked_medicine(message: str) -> str | None:
    """The medicine in "Can I take X with my medicines?" (or "is it ok to take X?")."""
    m = _CAN_I_TAKE.search(message or "")
    name = (m.group(1) or m.group(2)).strip() if m else ""
    return name if 2 < len(name) <= 60 and not re.search(r"\b(my|medicines?|pills?|tablets?)\b", name, re.I) else None


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

    focused = None
    if (focus or {}).get("type") == "report":
        focused = db.get(Report, focus.get("id"))
        if focused is None or focused.patient_id != patient_id or focused.status != "parsed":
            focused = None
    if focused is not None:  # the report explainer's follow-ups (Phase 4)
        rp, rp_items = report_explainer.build_report_pack(db, patient_id, focused)
        items.update(rp_items)
        pack["focused_report"] = {k: rp[k] for k in ("report", "critical", "glossary",
                                                      "logged_symptoms_around_report", "conditions")}
        pack["current_medicines_with_purpose"] = rp["current_medicines"]
    else:  # the latest results, so the reply never says a test is missing when it isn't
        reps = retrieval.reports(db, patient_id)[: 3 if any(w in text for w in _REPORT_WORDS) else 2]
        if reps:
            pack["reports"] = [keep(r) for r in reps]
    asked = mentioned_tests(message)
    if asked:  # "what is TSH?": its glossary entry, citable
        have = {g["test_key"] for g in (pack.get("focused_report") or {}).get("glossary", [])}
        pack["glossary"] = [keep(report_explainer.glossary_item(k)) for k in asked if k not in have][:4]

    # Medicine safety tools (Phase 5, D36): the same three levels as the Medications page.
    def keep_finding(f: dict) -> dict:
        for e in f.get("evidence") or []:  # the readings/logs a finding rests on are citable too
            if isinstance(e, dict) and e.get("id"):
                keep(e)
        return keep(f)

    asked = asked_medicine(message)
    if asked:
        check = med_safety.check_new_medicine(db, patient_id, asked)
        pack["med_check"] = {k: check.get(k) for k in ("medicine", "recognized", "assumed", "message")}
        pack["med_check"]["findings"] = [keep_finding(f) for f in check["findings"][:6]]
    if (focus or {}).get("type") == "med_finding":
        run = db.scalar(select(MedCheckRun).where(MedCheckRun.patient_id == patient_id))
        pinned = next((f for f in ((run.result if run else {}) or {}).get("findings", [])
                       if f["id"] == focus.get("id")), None)
        if pinned:
            pack["pinned_finding"] = keep_finding(pinned)
    if symptoms and not pack.get("pinned_finding"):
        run = db.scalar(select(MedCheckRun).where(MedCheckRun.patient_id == patient_id))
        stored = [f for f in ((run.result if run else {}) or {}).get("findings", [])
                  if f["kind"] in ("timing", "side_effect", "condition") and f["level"] != "ai"]
        if stored:
            pack["medication_findings"] = [keep_finding(f) for f in stored[:3]]
    for name in symptoms[:2]:
        found = med_safety.side_effects_for(db, patient_id, name)
        if found:
            pack.setdefault("possible_side_effects", []).extend(keep_finding(f) for f in found[:2])

    notes = retrieval.visit_notes(db, patient_id)
    if notes:
        pack["doctor_instructions"] = [keep(n) for n in notes]

    history = db.scalars(
        select(ChatMessage).where(ChatMessage.patient_id == patient_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(7)
    ).all()
    for h in history:  # ids cited in earlier turns stay citable in follow-ups
        for item in h.evidence or []:
            if isinstance(item, dict) and item.get("id") and item["id"] not in items:
                keep(item)
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
    for n in (pack.get("doctor_instructions") or [])[:1]:
        if n.get("doctor_said"):
            lines.append(f"At your visit on {n['date']} [{n['id']}]: " + " ".join(n["doctor_said"][:3]))
    if pack.get("focused_report"):
        lines.append(report_explainer._fallback(pack["focused_report"]))
    for g in pack.get("glossary", []):
        lines.append(f"{g['name']} [{g['id']}]: {g['measures']}")
    for rep in pack.get("reports", [])[:1]:
        lines.append(f"Latest report: {rep['report_type']} on {rep['date']} [{rep['id']}].")
    if pack.get("recurrence"):
        lines.append("These are patterns in your records, not a diagnosis. Worth raising with your doctor.")
    mc = pack.get("med_check")
    if mc:
        if mc.get("assumed"):
            lines.append(mc["assumed"])
        for f in mc.get("findings", []):
            lines.append(f"{f['level_label']}: {f['explanation']} [{f['id']}]")
        if mc.get("message"):
            lines.append(mc["message"])
    for f in [*([pack["pinned_finding"]] if pack.get("pinned_finding") else []), *pack.get("possible_side_effects", [])]:
        lines.append(f"{f['level_label']}: {f['explanation']} [{f['id']}]")
    if mc or pack.get("pinned_finding") or pack.get("possible_side_effects"):
        lines.append(med_safety.DONT_CHANGE)
    if not lines:
        lines.append("I couldn't find anything about that in your records yet.")
    return " ".join(lines)


# Medicine all-clears and stop/change advice never reach the user (ROADMAP ground rules).
_ALL_CLEAR = re.compile(
    r"\b(?:are|is|it's|they're) (?:completely |perfectly |totally )?safe (?:to take |to use )?(?:together|with)\b"
    r"|\bsafe(?:ly)? (?:to )?(?:combine|take them together)\b|\bsafe combination\b"
    r"|\bno (?:known )?interactions?\b(?! found in our sources)|\bnothing to worry about\b"
    r"|(?<!don't )(?<!do not )(?<!not )\bstop taking\b|\bdiscontinue\b",
    re.IGNORECASE,
)


def check_reply(reply: str, items: dict[str, dict]) -> str | None:
    """Why a reply must be rejected, or None if it passes."""
    if not reply.strip():
        return "empty"
    unknown = [c for c in _CITE.findall(reply) if c not in items]
    if unknown:
        return f"cites ids not in the pack: {unknown}"
    m = _ALL_CLEAR.search(reply)
    if m:
        return f"all-clear or stop wording: {m.group(0)!r}"
    if is_diagnostic(reply):
        from app.services.language_guard import violations

        return f"diagnostic wording: {violations(reply)}"
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
            candidate = llm_text(
                "assistant", SYSTEM, json.dumps({"user_message": message, "evidence": pack}),
                # The visible reply is short, but the model's hidden reasoning counts against
                # this too: 600 cut replies off mid-sentence (measured on Harsh's climax).
                max_tokens=2000,
            )
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
