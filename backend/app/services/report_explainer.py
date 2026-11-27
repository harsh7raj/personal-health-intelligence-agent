"""Report explainer (ROADMAP.md Phase 4, memory.md D34): the Phase 2 assistant with a report
pinned. Code builds everything the explanation may say (values against their printed range,
how far outside, the previous value and the change, glossary text, related logs and medicines),
each with an id. The LLM only words it and cites ids; the same checks as the chat apply.
"""

import json
import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.llm import is_available, llm_json, llm_text
from app.data.lab_glossary import GLOSSARY, key_for
from app.models.clinical import Medication
from app.models.patient import MedicalBackground
from app.models.records import Entry, Report
from app.services import lab_values, retrieval
from app.services.language_guard import is_diagnostic

logger = logging.getLogger(__name__)

_GLOSSARY_IDS = {key: f"G{i}" for i, key in enumerate(GLOSSARY, start=1)}  # stable, citable

EXPLAIN_SYSTEM = """You explain the user's own lab report in plain language, using ONLY the JSON \
evidence pack. Cite facts with their ids in square brackets exactly as given (the app turns them \
into clickable chips); write "[R12]" instead of the report's date and "[V40]" instead of an \
earlier value's date.
If "critical" is not empty, the app shows that warning above your text in its own words: don't \
repeat it, and never soften it.
Cover, briefly:
1. what the report covers (one sentence);
2. each value outside its printed range, with how far outside (from "outside_by");
3. how each repeated test changed since the previous value ("previous", "change");
4. what each flagged test measures, from its glossary entry (cite its [G..] id);
5. logged symptoms or current medicines in the pack that may be worth discussing together with \
their doctor. Present them as things to talk over, NEVER as a cause or explanation.
HARD RULES: never diagnose or name a condition the user has; never say a result is good, bad, \
fine or worrying; never explain WHY their value is high or low; never suggest treatment, diet \
changes or dose changes; never interpret beyond the printed range and their record. Say \
"outside the printed range" or "above the range", not "abnormal".
Finish by suggesting they go over the report with their doctor.
Write 4 to 8 short sentences (a short list is fine), addressed to the user ("you"). Plain text, \
no markdown: no ** or #; a list item starts its line with "- ".
Return only the explanation text, with its [ids]."""

FOLLOW_UP_RULES = """When "focused_report" or "glossary" is in the pack: explain what a test \
measures only from its glossary entry (cite its [G..] id). For "is this bad?" say where the value \
sits against its printed range and how it has moved, and that their doctor can say what it means \
for them; never give a good/bad verdict. For "why could this be high/low?" give the glossary's \
general reasons as general possibilities ("in general, X can be higher with ..."), never "yours is \
high because". For "how does this compare to last time?" use "previous" and "change". Never \
interpret beyond the printed range and their record."""

QUESTIONS_SYSTEM = """From the JSON evidence pack about the user's lab report, write 3 to 5 short \
questions the user could ask their doctor at their next visit. Base them only on the pack: values \
outside their printed range, changes since the previous report, and logged symptoms or medicines \
worth discussing together. Phrase them as the user's own questions ("Could my ... be related to \
...?" is fine; stating a cause is not). Never diagnose, never suggest a treatment or dose change. \
Return JSON: {"questions": ["...", "..."]}."""


def _report_day(report: Report) -> str:
    if report.test_date:
        return report.test_date.isoformat()
    return clock.to_local(report.created_at).date().isoformat() if report.created_at else ""


def report_item(report: Report) -> dict:
    return {"id": f"R{report.id}", "kind": "report", "report_id": report.id,
            "report_type": report.report_type, "date": _report_day(report), "filename": report.filename}


def glossary_item(key: str) -> dict:
    e = GLOSSARY[key]
    return {"id": _GLOSSARY_IDS[key], "kind": "glossary", "test_key": key, "name": e["name"],
            "measures": e["measures"], "general_reasons_high": e["high"], "general_reasons_low": e["low"],
            "units": e["units"], "url": e["url"]}


def value_rows(db: Session, patient_id: int, report: Report) -> list[dict]:
    """Every value of the report, decided in code: range as numbers, flag, how far outside,
    critical finding, the previous value of the same test and the change since then."""
    this_day = _report_day(report)
    rows: list[dict] = []
    series_cache: dict[str, list[dict]] = {}
    for raw in report.extracted_values or []:
        # Reports parsed before D33 lack the code-decided fields: compute them now.
        v = raw if "test_key" in raw else lab_values.enrich([raw])[0]
        key = v.get("test_key") or key_for(v.get("test_name"))
        num = lab_values.to_number(v.get("value"))
        previous = change = None
        if num is not None and v.get("test_name"):
            vt = key or v["test_name"]
            if vt not in series_cache:
                series_cache[vt] = retrieval.lab_series(db, patient_id, v["test_name"])
            earlier = [s for s in series_cache[vt] if s.get("report_id") != report.id and s["date"] < this_day]
            if earlier:
                p = earlier[-1]
                previous = {"id": p["id"], "kind": "lab", "vital_type": p["vital_type"], "value": p["value"],
                            "unit": p.get("unit"), "date": p["date"], "report_id": p.get("report_id"),
                            "test": v["test_name"]}
                delta = round(num - p["value"], 2)
                change = {"amount": delta, "percent": round(delta / p["value"] * 100, 1) if p["value"] else None,
                          "direction": "up" if delta > 0 else "down" if delta < 0 else "same"}
        rows.append({
            "test_name": v.get("test_name"), "display_name": lab_values.display_name(key, v.get("test_name")),
            "test_key": key, "value": v.get("value"), "unit": v.get("unit"),
            "reference_range": v.get("reference_range"), "range_low": v.get("range_low"),
            "range_high": v.get("range_high"), "flag": v.get("flag") or "unknown",
            "outside_by": lab_values.outside_by(v), "critical": v.get("critical"),
            "previous": previous, "change": change,
            "glossary_id": _GLOSSARY_IDS.get(key) if key else None,
        })
    return rows


def build_report_pack(db: Session, patient_id: int, report: Report) -> tuple[dict, dict[str, dict]]:
    """(facts for the LLM, {evidence id: item}) for one report."""
    items: dict[str, dict] = {}

    def keep(item: dict) -> dict:
        items[item["id"]] = item
        return item

    rep = keep(report_item(report))
    rows = value_rows(db, patient_id, report)
    for r in rows:
        if r["previous"]:
            keep(r["previous"])
    flagged = [r for r in rows if r["flag"] in ("high", "low")]
    keys = [r["test_key"] for r in flagged + rows if r["test_key"]]
    glossary = [keep(glossary_item(k)) for k in dict.fromkeys(keys)][:12]

    day = date.fromisoformat(rep["date"]) if rep["date"] else clock.today()

    def start(d: date) -> datetime:
        return datetime.combine(d, time.min, tzinfo=clock.local_tz())

    entries = db.scalars(
        select(Entry).where(Entry.patient_id == patient_id, Entry.type == "symptom",
                            Entry.occurred_at >= start(day - timedelta(days=90)),
                            Entry.occurred_at < start(day + timedelta(days=15)))
        .order_by(Entry.occurred_at.desc()).limit(8)
    ).all()
    meds = db.scalars(select(Medication).where(Medication.patient_id == patient_id,
                                               Medication.active.is_(True))).all()
    background = db.scalar(select(MedicalBackground).where(MedicalBackground.patient_id == patient_id))

    pack = {
        "today": clock.today().isoformat(),
        "report": {**rep, "values": [{k: r[k] for k in ("test_name", "value", "unit", "reference_range", "flag",
                                                         "outside_by", "previous", "change", "glossary_id")}
                                     for r in rows]},
        "critical": [r["critical"]["message"] for r in rows if r["critical"]],
        "glossary": glossary,
        "logged_symptoms_around_report": [keep(retrieval.entry_item(e)) for e in reversed(entries)],
        "current_medicines": [{"name": m.name, "dose": m.dose, "purpose": m.purpose,
                               "started_on": m.started_on.isoformat() if m.started_on else None} for m in meds],
        "conditions": (background.conditions if background else []) or [],
        "report_text_excerpt": (report.extracted_text or "")[:3000],
    }
    return pack, items


def _fallback(pack: dict) -> str:
    """Plain facts from code, used when there is no LLM or its text fails a check."""
    rep = pack["report"]
    lines = [f"Your {rep.get('report_type') or 'report'} [{rep['id']}] has {len(rep['values'])} results."]
    for v in rep["values"]:
        o = v.get("outside_by")
        if o:
            lines.append(f"{v['test_name']} is {v['value']} {v.get('unit') or ''}, {o['amount']:g} {o['direction']} "
                         f"the printed range ({v.get('reference_range')}).".replace("  ", " "))
        if v.get("previous") and v.get("change"):
            p = v["previous"]
            lines.append(f"{v['test_name']} was {p['value']:g} on [{p['id']}], so it went {v['change']['direction']} "
                         f"by {abs(v['change']['amount']):g}.")
    if not any(v.get("outside_by") for v in rep["values"]):
        lines.append("All the values with a numeric range are inside their printed ranges.")
    lines.append("Worth going over with your doctor, who can say what these mean for you.")
    return " ".join(lines)


def _checked(text: str, items: dict[str, dict]) -> str | None:
    from app.services.assistant import check_reply

    problem = check_reply(text, items)
    if problem:
        logger.warning("report explanation rejected (%s); using the fact list", problem)
        return None
    return text


def explain(db: Session, patient_id: int, report: Report) -> dict:
    """The explainer's opening message: {reply, evidence, critical, generated_by}."""
    from app.services.assistant import cited_evidence

    pack, items = build_report_pack(db, patient_id, report)
    reply, generated_by = None, "fallback"
    if is_available():
        try:
            reply = _checked(llm_text("report_explainer", EXPLAIN_SYSTEM, json.dumps(pack), max_tokens=2500), items)
            generated_by = "llm" if reply else "fallback"
        except Exception:
            logger.warning("report explainer LLM call failed; using the fact list", exc_info=True)
    if reply is None:
        reply = _fallback(pack)
    if pack["critical"]:  # code's own words lead, before anything the model wrote
        reply = " ".join(pack["critical"]) + "\n\n" + reply
    return {"reply": reply, "evidence": cited_evidence(reply, items), "critical": pack["critical"],
            "generated_by": generated_by}


def _fallback_questions(pack: dict) -> list[str]:
    qs = []
    for v in pack["report"]["values"]:
        if v.get("outside_by"):
            qs.append(f"My {v['test_name']} was {v['value']} {v.get('unit') or ''} (range {v.get('reference_range')}). "
                      "What does this mean for me, and when should it be rechecked?".replace("  ", " "))
        elif v.get("change") and v["change"]["direction"] != "same" and v.get("previous"):
            qs.append(f"My {v['test_name']} went {v['change']['direction']} since {v['previous']['date']}. "
                      "Is that change something to act on?")
    return (qs or ["Is there anything in this report you would like me to keep an eye on?"])[:5]


def doctor_questions(db: Session, patient_id: int, report: Report) -> dict:
    """3-5 questions for the next visit: {questions, generated_by}."""
    pack, _items = build_report_pack(db, patient_id, report)
    if is_available():
        try:
            res = llm_json("report_questions", QUESTIONS_SYSTEM, json.dumps(pack))
            qs = [q.strip() for q in res.get("questions") or [] if isinstance(q, str) and q.strip()]
            clean = [q for q in qs if not is_diagnostic(q)][:5]
            if clean:
                return {"questions": clean, "generated_by": "llm"}
        except Exception:
            logger.warning("doctor questions LLM call failed; using the fallback", exc_info=True)
    return {"questions": _fallback_questions(pack), "generated_by": "fallback"}
