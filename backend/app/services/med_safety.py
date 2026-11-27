"""Medication safety (ROADMAP.md Phase 5, memory.md D36). Extends med_intel's DDInter lookup.

THE RULE: the AI can raise a concern but never gives the all-clear, and must never push anyone
to stop a medicine. Nothing here ever says "safe". When nothing fires, the result says exactly
NO_FINDING.

Pairs, per ingredient pair, in order (DDInter always wins; later levels never downgrade it):
  1. Verified: the pair is in DDInter -> its severity.
  2. Official label: code finds label sentences (openFDA, cached) that mention the other drug or
     one of its classes (RxClass). The AI picks one, copies it and explains it; code checks the
     quote is verbatim in the cached label, else uses code's own sentence.
  3. AI flag (unverified): behind MED_AI_FLAGS_ENABLED, for pairs nothing else covered.
Patient-aware (each quoting its source): duplicates across doctors (RxClass), dose timing
(label "N hours" vs the patient's dose times), label warnings matching the record (low sugars,
kidney, liver, potassium), side effects after a start or dose change, alcohol.
"""

import hashlib
import json
import logging
import re
from datetime import date, timedelta
from itertools import combinations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.llm import is_available, llm_json
from app.data.symptom_synonyms import canonical_symptom
from app.models.clinical import Medication, MedicationEvent, VitalReading
from app.models.drugs import MedCheckRun
from app.models.records import Entry, Report
from app.models.reference import DrugInteraction
from app.services import brand_generic, drug_classes, drug_labels, retrieval, rxnorm
from app.services.language_guard import is_diagnostic

logger = logging.getLogger(__name__)

NO_FINDING = "No known interaction found in our sources. Confirm with your pharmacist."
DONT_CHANGE = "Don't stop or change any medicine on your own."
DISCLAIMER = ("These checks use DDInter 2.0, official FDA labels (openFDA) and RxClass. They can miss "
              "things and are not medical advice. " + DONT_CHANGE + " Talk to your pharmacist or doctor.")
DDINTER = {"name": "DDInter 2.0", "url": "https://ddinter2.scbdd.com/"}
LEVEL_LABEL = {"verified": "Verified", "label": "Official label", "ai": "AI flag (unverified)"}
_LABEL_PAIR_SECTIONS = ("drug_interactions", "warnings", "contraindications", "dosage_and_administration")
_UNSAFE_WORDING = re.compile(r"\bsafe(ly)?\b|\bno (known )?interactions?\b|\bnothing to worry\b|"
                             r"\bstop taking\b|\bdiscontinue\b", re.I)
_SYNONYMS = {"acetaminophen": ["paracetamol"], "cholecalciferol": ["vitamin d3", "vitamin d"],
             "levothyroxine": ["thyroxine", "thyroid hormone"], "acetylsalicylic acid": ["aspirin"]}

LABEL_SYSTEM = """You read sentences that code found in official FDA drug labels. They mention the \
other medicine of a pair, or a drug class it belongs to. Pick the ONE sentence that best says how the \
two medicines interact or must be used together, and copy it EXACTLY as given. Explain it for a \
patient in 1-2 plain sentences. Never say the pair is safe or that there is no interaction, never \
tell them to stop or change a medicine; say what to ask about. Write 2 short questions for their \
pharmacist. For a sentence found through a CLASS ("via": "class"), set applies=false only if that \
class clearly does not include the other medicine (for example "calcium channel blockers" is not \
calcium carbonate); otherwise true. Return JSON: {"index": <number>, "quote": "<exact sentence>", \
"applies": true, "explanation": "...", "questions": ["...", "..."]}."""

AI_FLAG_SYSTEM = """You may flag a POSSIBLE concern between pairs of medicines that official \
sources did not flag. Only well-established pharmacology (shared side effects that add up, \
opposite effects, a known class effect); explain the reasoning plainly. Never say a pair is safe or \
has no interaction, never suggest stopping or changing a medicine. Flag nothing you are unsure about. \
Return JSON: {"flags": [{"medicine_1": "...", "medicine_2": "...", "concern": "one sentence", \
"reasoning": "one or two sentences"}]}. An empty list is fine."""

SYMPTOM_LABEL_TERMS: dict[str, list[str]] = {
    "ankle swelling": ["peripheral edema", "edema", "oedema", "swelling"],
    "swelling": ["edema", "oedema", "swelling"],
    "fatigue": ["fatigue", "asthenia", "tiredness"],
    "shakiness": ["tremor"],
    "sweating": ["sweating", "hyperhidrosis", "diaphoresis"],
    "diarrhea": ["diarrhea", "diarrhoea"],
    "muscle pain": ["myalgia", "muscle pain"],
    "heartburn": ["dyspepsia", "heartburn"],
    "stomach pain": ["abdominal pain"],
    "abdominal pain": ["abdominal pain"],
    "dry cough": ["cough"],
}


# --------------------------------------------------------------------------- helpers


def ingredients_of(med: Medication) -> tuple[list[str], bool]:
    """(ingredients, resolved). Confirmed ingredients first, then RxNorm; an unknown name is
    checked as written and reported as unresolved so the UI can ask the user to confirm it."""
    if med.ingredients:
        return list(med.ingredients), True
    found = rxnorm.lookup(med.name)
    if found["status"] == "found":
        return found["ingredients"], True
    return [rxnorm.normalize_ingredient(med.name)], False


def _terms_for(ingredient: str) -> list[str]:
    base = [ingredient, *_SYNONYMS.get(ingredient, [])]
    words = ingredient.split()
    if len(words) > 1 and words[-1] in ("sodium", "hydrochloride", "potassium", "calcium", "besylate"):
        base.append(" ".join(words[:-1]))  # "levothyroxine sodium" -> "levothyroxine"
    return base


def _finding(kind: str, level: str, meds: list[str], title: str, explanation: str, *, quote: str | None = None,
             source: dict | None = None, questions: list[str] | None = None, severity: str | None = None,
             evidence: list[dict] | None = None, extra: dict | None = None) -> dict:
    return {"kind": kind, "level": level, "level_label": LEVEL_LABEL[level], "severity": severity,
            "medicines": meds, "title": title, "explanation": explanation, "quote": quote, "source": source,
            "pharmacist_questions": questions or [], "evidence": evidence or [], **(extra or {})}


def _clean(text: str | None, fallback: str) -> str:
    t = (text or "").strip()
    return fallback if not t or is_diagnostic(t) or _UNSAFE_WORDING.search(t) else t


def _label_source(label) -> dict:
    return {"name": f"FDA label: {label.title or label.ingredient}", "url": drug_labels.source_url(label),
            "note": drug_labels.OPENFDA_DISCLAIMER}


class _Ctx:
    """Everything a run looks up once: meds, their ingredients, labels and classes."""

    def __init__(self, db: Session, patient_id: int, meds: list[Medication]):
        self.db, self.patient_id, self.meds = db, patient_id, meds
        self.ing: dict[int, list[str]] = {}
        self.unresolved: list[str] = []
        for m in meds:
            ings, ok = ingredients_of(m)
            self.ing[m.id] = ings
            if not ok:
                self.unresolved.append(m.name)
        all_ings = sorted({i for v in self.ing.values() for i in v})
        self.labels = {i: drug_labels.get_label(db, i) for i in all_ings}
        self.classes = {i: drug_classes.get_classes(db, i) for i in all_ings}


# --------------------------------------------------------------------------- pair levels


def _ddinter(db: Session, a: str, b: str) -> DrugInteraction | None:
    lo, hi = sorted((a, b))
    return db.scalar(select(DrugInteraction).where(DrugInteraction.drug_lo == lo, DrugInteraction.drug_hi == hi))


def _label_candidates(ctx: _Ctx, a: str, b: str) -> list[dict]:
    out, seen = [], set()
    for own, other in ((a, b), (b, a)):
        label = ctx.labels.get(own)
        by_name = drug_labels.find(label, _terms_for(other), _LABEL_PAIR_SECTIONS)
        by_class = drug_labels.find(label, drug_classes.label_terms(ctx.classes.get(other, [])), _LABEL_PAIR_SECTIONS)
        for via, found in (("name", by_name), ("class", by_class)):
            for c in found:  # labels repeat their Highlights text: keep each sentence once
                if c["quote"] not in seen:
                    seen.add(c["quote"])
                    out.append({**c, "label_of": own, "via": via})
    return out[:8]


def _label_finding(ctx: _Ctx, names: tuple[str, str], a: str, b: str, cands: list[dict]) -> dict | None:
    """Level 2 from code-found sentences. Returns None only if every candidate came through a
    class the AI says doesn't include the other drug."""
    pick, explanation, questions = 0, None, None
    if is_available():
        try:
            res = llm_json("med_label", LABEL_SYSTEM, json.dumps({
                "medicine_1": a, "medicine_2": b,
                "candidates": [{"index": i, "label_of": c["label_of"], "section": c["section"], "via": c["via"],
                                "matched": c["term"], "sentence": c["quote"]} for i, c in enumerate(cands)]}))
            idx = res.get("index")
            if isinstance(idx, int) and 0 <= idx < len(cands):
                pick = idx
            if res.get("applies") is False and cands[pick]["via"] == "class":
                named = [i for i, c in enumerate(cands) if c["via"] == "name"]
                if not named:
                    return None
                pick = named[0]
            quote = str(res.get("quote") or "")
            label = ctx.labels.get(cands[pick]["label_of"])
            if drug_labels.quote_is_verbatim(label, quote) and drug_labels.normalize(quote).lower() in \
                    drug_labels.normalize(cands[pick]["quote"]).lower():
                cands[pick] = {**cands[pick], "quote": drug_labels.normalize(quote)}
            explanation = res.get("explanation")
            questions = [q for q in res.get("questions") or [] if isinstance(q, str) and not is_diagnostic(q)][:3]
        except Exception:
            logger.warning("label reading failed for %s + %s; using code's sentence", a, b, exc_info=True)
    c = cands[pick]
    label = ctx.labels[c["label_of"]]
    other = b if c["label_of"] == a else a
    fallback = (f"The official label for {c['label_of']} mentions {other if c['via'] == 'name' else c['term']} "
                f"in its {c['section'].replace('_', ' ')} section. Ask your pharmacist what it means for you.")
    return _finding(
        "interaction", "label", list(names), f"{names[0]} + {names[1]}: mentioned in the official label",
        _clean(explanation, fallback), quote=c["quote"], source=_label_source(label),
        questions=questions or [f"Does the label note about {c['label_of']} and {other} apply to my doses?",
                                "Should these be taken at different times?"],
        extra={"via": c["via"], "section": c["section"]})


def _ai_flags(pairs: list[tuple[tuple[str, str], str, str]], ctx: _Ctx) -> list[dict]:
    if not pairs or not get_settings().MED_AI_FLAGS_ENABLED or not is_available():
        return []
    wanted = {frozenset((a, b)): names for names, a, b in pairs}
    try:
        res = llm_json("med_ai_flag", AI_FLAG_SYSTEM, json.dumps({"pairs": [
            {"medicine_1": a, "medicine_2": b,
             "classes_1": [c["name"] for c in ctx.classes.get(a, []) if c["type"] != "ATC"][:6],
             "classes_2": [c["name"] for c in ctx.classes.get(b, []) if c["type"] != "ATC"][:6]}
            for _n, a, b in pairs]}))
    except Exception:
        logger.warning("AI flag check failed", exc_info=True)
        return []
    out = []
    for f in res.get("flags") or []:
        key = frozenset((str(f.get("medicine_1", "")).lower(), str(f.get("medicine_2", "")).lower()))
        concern, reasoning = str(f.get("concern") or ""), str(f.get("reasoning") or "")
        if key not in wanted or not concern or any(is_diagnostic(t) or _UNSAFE_WORDING.search(t)
                                                   for t in (concern, reasoning)):
            continue
        names = wanted[key]
        out.append(_finding("interaction", "ai", list(names), f"{names[0]} + {names[1]}: possible concern",
                            f"{concern} {reasoning} Unverified, ask your pharmacist. {DONT_CHANGE}",
                            source={"name": "AI flag (not from a database or label)", "url": None},
                            questions=[f"Is there anything to watch for when taking {names[0]} with {names[1]}?"]))
    return out


def pair_findings(ctx: _Ctx, med_pairs: list[tuple[Medication, Medication]]) -> tuple[list[dict], list[dict]]:
    """(findings, per-pair results) for the given medicine pairs."""
    findings: list[dict] = []
    results: list[dict] = []
    leftover: list[tuple[tuple[str, str], str, str]] = []
    for ma, mb in med_pairs:
        names = (ma.name, mb.name)
        before = len(findings)
        for a in ctx.ing[ma.id]:
            for b in ctx.ing[mb.id]:
                if a == b:
                    findings.append(_finding(
                        "duplicate", "verified", list(names), f"{names[0]} and {names[1]} contain the same medicine",
                        f"Both contain {a} (RxNorm), so together they may add up to more than intended. "
                        "Check with your pharmacist or doctor.", source={"name": "RxNorm", "url": "https://www.nlm.nih.gov/research/umls/rxnorm/"},
                        questions=[f"Am I meant to take {a} from both {names[0]} and {names[1]}?"]))
                    continue
                row = _ddinter(ctx.db, a, b)
                if row is not None:  # level 1 wins for this ingredient pair
                    findings.append(_finding(
                        "interaction", "verified", list(names), f"{names[0]} + {names[1]}: {row.level.lower()} interaction",
                        f"DDInter lists an interaction between {a} and {b} (severity: {row.level}). "
                        "Ask your pharmacist or doctor how it applies to you.",
                        severity=row.level, source=DDINTER,
                        questions=[f"How does the {a}-{b} interaction apply to my doses?",
                                   "Is there anything I should watch for?"]))
                    continue
                cands = _label_candidates(ctx, a, b)
                lf = _label_finding(ctx, names, a, b, cands) if cands else None
                if lf:
                    findings.append(lf)
                else:
                    leftover.append((names, a, b))
        results.append({"medicines": list(names), "found": len(findings) > before})
    ai = _ai_flags(leftover, ctx)
    findings += ai
    flagged = {frozenset(f["medicines"]) for f in ai}
    for r in results:
        if not r["found"] and frozenset(r["medicines"]) in flagged:
            r["found"] = True
    for r in results:
        r["message"] = None if r["found"] else NO_FINDING
    return findings, results


# --------------------------------------------------------------------------- patient-aware


def _duplicates_across_doctors(ctx: _Ctx) -> list[dict]:
    out = []
    for ma, mb in combinations(ctx.meds, 2):
        if not ma.prescriber or not mb.prescriber or ma.prescriber.strip().lower() == mb.prescriber.strip().lower():
            continue
        shared = set.intersection(*[set().union(*(drug_classes.epc_names(ctx.classes.get(i, [])) for i in ctx.ing[m.id]))
                                    for m in (ma, mb)])
        for cls in sorted(shared):
            out.append(_finding(
                "duplicate", "verified", [ma.name, mb.name], f"Two {cls.lower()} medicines from different doctors",
                f"{ma.name} ({ma.prescriber}) and {mb.name} ({mb.prescriber}) are both in the class "
                f"\"{cls}\" (RxClass). Each doctor may not know about the other's prescription.",
                source={"name": drug_classes.SOURCE, "url": drug_classes.SOURCE_URL},
                questions=[f"Do I need both {ma.name} and {mb.name}?", "Do both of my doctors know about each other's prescriptions?"]))
    return out


def _minutes(hhmm: str) -> int | None:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", hhmm or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _timing(ctx: _Ctx) -> list[dict]:
    out = []
    for ma, mb in combinations(ctx.meds, 2):
        for a in ctx.ing[ma.id]:
            for b in ctx.ing[mb.id]:
                for own, other, m_own, m_other in ((a, b, ma, mb), (b, a, mb, ma)):
                    label = ctx.labels.get(own)
                    terms = _terms_for(other) + drug_classes.label_terms(ctx.classes.get(other, []))
                    for c in drug_labels.find(label, terms, ("dosage_and_administration", "drug_interactions")):
                        h = re.search(r"(\d+)\s*hours?\b", c["quote"], re.I)
                        if not h and c.get("next"):  # "...(e.g., calcium carbonate)... Administer 4 hours apart."
                            h = re.search(r"(\d+)\s*hours?\b", c["next"], re.I)
                            if h and len(c["next"]) < 300:
                                c = {**c, "quote": f"{c['quote']} {c['next']}"}
                            else:
                                h = None
                        if not h:
                            continue
                        hours = int(h.group(1))
                        gaps = [abs(x - y) for t1 in m_own.dose_times or [] for t2 in m_other.dose_times or []
                                if (x := _minutes(t1)) is not None and (y := _minutes(t2)) is not None]
                        if gaps and min(gaps) < hours * 60:
                            close = min(gaps)
                            out.append(_finding(
                                "timing", "label", [m_own.name, m_other.name],
                                f"{m_own.name} and {m_other.name} are scheduled close together",
                                f"The official label for {own} says to keep it {hours} hours apart from "
                                f"{other if c['term'] in _terms_for(other) else c['term']}; your schedule has them "
                                f"{close // 60} h {close % 60:02d} min apart ({', '.join(m_own.dose_times)} and "
                                f"{', '.join(m_other.dose_times)}). Ask your pharmacist about the best times.",
                                quote=c["quote"], source=_label_source(label),
                                questions=[f"What times should I take {m_own.name} and {m_other.name}?"]))
                            return out  # one timing note per run keeps it readable
    return out


def _latest_lab_flag(db: Session, pid: int, tests: list[str], flag: str) -> list[dict]:
    out = []
    for t in tests:
        series = retrieval.lab_series(db, pid, t)
        if series and series[-1].get("flag") == flag:
            out.append(series[-1])
    return out


def _low_glucose(db: Session, pid: int) -> list[dict]:
    since = clock.now() - timedelta(days=180)
    rows = db.scalars(select(VitalReading).where(
        VitalReading.patient_id == pid, VitalReading.vital_type == "blood_glucose", VitalReading.value < 70,
        VitalReading.recorded_at >= since).order_by(VitalReading.recorded_at)).all()
    return [retrieval.reading_item(r) for r in rows]


CONDITIONS = [
    {"key": "low_sugar", "topic": "low blood sugar", "terms": ["hypoglycemia", "hypoglycaemia", "low blood sugar"],
     "record": _low_glucose, "shows": "glucose readings below 70 mg/dL"},
    {"key": "kidney", "topic": "kidney function", "terms": ["renal impairment", "renal function", "egfr", "kidney function"],
     "record": lambda db, pid: _latest_lab_flag(db, pid, ["eGFR"], "low") + _latest_lab_flag(db, pid, ["Creatinine"], "high"),
     "shows": "a recent kidney result outside its range"},
    {"key": "liver", "topic": "liver function", "terms": ["hepatic impairment", "liver function", "hepatotoxicity"],
     "record": lambda db, pid: _latest_lab_flag(db, pid, ["ALT", "AST"], "high"),
     "shows": "a recent liver enzyme above its range"},
    {"key": "potassium", "topic": "high potassium", "terms": ["hyperkalemia", "hyperkalaemia"],
     "record": lambda db, pid: _latest_lab_flag(db, pid, ["Potassium"], "high"),
     "shows": "a recent potassium result above its range"},
]


def _conditions(ctx: _Ctx) -> list[dict]:
    out = []
    for rule in CONDITIONS:
        evidence = rule["record"](ctx.db, ctx.patient_id)
        if not evidence:
            continue
        for m in ctx.meds:
            for ing in ctx.ing[m.id]:
                label = ctx.labels.get(ing)
                hits = drug_labels.find(label, rule["terms"], ("warnings", "contraindications"))
                if not hits:
                    continue
                dates = ", ".join(e["date"] for e in evidence[-3:])
                out.append(_finding(
                    "condition", "label", [m.name], f"{m.name}: label warning about {rule['topic']}",
                    f"The official label for {ing} has a warning about {rule['topic']}, and your record shows "
                    f"{rule['shows']} ({dates}). Worth mentioning to your doctor.",
                    quote=hits[0]["quote"], source=_label_source(label), evidence=evidence[-3:],
                    questions=[f"Does the {rule['topic']} warning for {m.name} matter for me, given my results?"]))
                break
    return out


def _symptom_onsets(db: Session, pid: int) -> dict[str, dict]:
    """First time each symptom was logged (main name or named alongside it)."""
    first: dict[str, dict] = {}
    rows = db.scalars(select(Entry).where(Entry.patient_id == pid, Entry.type == "symptom")
                      .order_by(Entry.occurred_at)).all()
    for e in rows:
        s = e.structured or {}
        for name in [s.get("name"), *(s.get("other_symptoms") or [])]:
            n = canonical_symptom(name) if name else None
            if n and n not in first:
                first[n] = retrieval.entry_item(e)
    return first


def side_effects(ctx: _Ctx, symptom: str | None = None) -> list[dict]:
    """A symptom whose first log came 1-120 days after a medicine was started or its dose
    changed, where that medicine's label lists it (adverse reactions or warnings)."""
    onsets = _symptom_onsets(ctx.db, ctx.patient_id)
    if symptom:
        onsets = {k: v for k, v in onsets.items() if k == canonical_symptom(symptom)}
    events = ctx.db.scalars(select(MedicationEvent).where(
        MedicationEvent.patient_id == ctx.patient_id, MedicationEvent.event_type.in_(("start", "dose_change")))
        .order_by(MedicationEvent.event_date)).all()
    by_med = {m.id: m for m in ctx.meds}
    out = []
    for name, first in onsets.items():
        day = date.fromisoformat(first["date"])
        for ev in events:
            m = by_med.get(ev.medication_id)
            gap = (day - ev.event_date).days
            if m is None or not 1 <= gap <= 120:
                continue
            for ing in ctx.ing[m.id]:
                label = ctx.labels.get(ing)
                hits = drug_labels.find(label, SYMPTOM_LABEL_TERMS.get(name, [name]), ("adverse_reactions", "warnings"))
                if not hits:
                    continue
                what = "the dose change" if ev.event_type == "dose_change" else "you started it"
                change = f" ({ev.old_dose} to {ev.new_dose})" if ev.event_type == "dose_change" and ev.old_dose else ""
                out.append(_finding(
                    "side_effect", "label", [m.name], f"{name.capitalize()} after {m.name}",
                    f"{name.capitalize()} is listed in {ing}'s official label, and yours was first logged "
                    f"{gap} days after {what}{change} on {ev.event_date.isoformat()}. Worth mentioning to your doctor.",
                    quote=hits[0]["quote"], source=_label_source(label), evidence=[first, retrieval.med_event_item(ev)],
                    questions=[f"Could {name} be related to {m.name}?", "Is there anything I should track before my next visit?"],
                    extra={"symptom": name}))
                break
    return out


def _alcohol(ctx: _Ctx) -> list[dict]:
    since = clock.now() - timedelta(days=90)
    rows = ctx.db.scalars(select(Entry).where(Entry.patient_id == ctx.patient_id, Entry.occurred_at >= since)).all()
    logged = [retrieval.entry_item(e) for e in rows if "alcohol" in ((e.structured or {}).get("context_tags") or [])]
    if not logged:
        return []
    out = []
    for m in ctx.meds:
        for ing in ctx.ing[m.id]:
            hits = drug_labels.find(ctx.labels.get(ing), ["alcohol"], ("warnings", "drug_interactions"))
            if hits:
                out.append(_finding(
                    "alcohol", "label", [m.name], f"{m.name} and alcohol",
                    f"The official label for {ing} mentions alcohol, and you logged alcohol on "
                    f"{', '.join(e['date'] for e in logged[-3:])}. Worth asking your pharmacist.",
                    quote=hits[0]["quote"], source=_label_source(ctx.labels[ing]), evidence=logged[-3:],
                    questions=[f"How much alcohol, if any, is OK with {m.name}?"]))
                break
    return out


# --------------------------------------------------------------------------- runs


def _active(db: Session, pid: int) -> list[Medication]:
    return list(db.scalars(select(Medication).where(Medication.patient_id == pid, Medication.active.is_(True))
                           .order_by(Medication.name)).all())


def _number(findings: list[dict]) -> list[dict]:
    order = {"verified": 0, "label": 1, "ai": 2}
    sev = {"Major": 0, "Moderate": 1, "Minor": 2}
    findings.sort(key=lambda f: (order[f["level"]], sev.get(f.get("severity"), 3)))
    return [{**f, "id": f"F{i}"} for i, f in enumerate(findings, start=1)]


def run(db: Session, pid: int) -> dict:
    meds = _active(db, pid)
    ctx = _Ctx(db, pid, meds)
    findings, pairs = pair_findings(ctx, list(combinations(meds, 2)))
    findings += _duplicates_across_doctors(ctx) + _timing(ctx) + _conditions(ctx) + side_effects(ctx) + _alcohol(ctx)
    labels_missing = sorted(i for i, lbl in ctx.labels.items() if lbl is None or not lbl.found)
    return {
        "checked_at": clock.now().isoformat(), "medicines": [m.name for m in meds],
        "findings": _number(findings), "pairs": pairs, "no_finding_message": NO_FINDING,
        "unresolved_medicines": ctx.unresolved, "labels_missing": labels_missing,
        "ai_flags_enabled": get_settings().MED_AI_FLAGS_ENABLED, "disclaimer": DISCLAIMER,
        "sources": [DDINTER, {"name": "openFDA drug labels", "url": "https://open.fda.gov/apis/drug/label/"},
                    {"name": drug_classes.SOURCE, "url": drug_classes.SOURCE_URL}],
    }


def signature(db: Session, pid: int) -> str:
    """Changes whenever anything a run reads changes (medicines, new logs, readings, reports)."""
    meds = [(m.id, m.name, m.ingredients, m.dose, m.dose_times, m.prescriber) for m in _active(db, pid)]
    latest = [db.scalar(select(func.max(t.id)).where(t.patient_id == pid))
              for t in (Entry, VitalReading, Report, MedicationEvent)]
    raw = json.dumps([meds, latest, get_settings().MED_AI_FLAGS_ENABLED, clock.today().isoformat()], default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def latest(db: Session, pid: int, *, force: bool = False) -> dict:
    """The stored result if nothing changed since, else a fresh run (stored)."""
    sig = signature(db, pid)
    row = db.scalar(select(MedCheckRun).where(MedCheckRun.patient_id == pid))
    if row is not None and row.signature == sig and not force:
        return {**row.result, "stale": False}
    result = run(db, pid)
    if row is None:
        row = MedCheckRun(patient_id=pid, signature=sig, result=result)
        db.add(row)
    else:
        row.signature, row.result, row.created_at = sig, result, clock.now()
    db.commit()
    return {**result, "stale": False}


def check_new_medicine(db: Session, pid: int, name: str) -> dict:
    """'Can I take X with my medicines?': X against every current medicine, same three levels.
    Never an all-clear: with nothing found the answer is NO_FINDING."""
    found = rxnorm.lookup(name)
    ingredients, assumed = found["ingredients"], None
    if found["status"] != "found":
        # A brand RxNorm doesn't know: check the AI's suggested generics, and say so.
        res = brand_generic.resolve(name)
        ingredients = [i for s in res["suggestion"] if s["verified"] for i in s["rxnorm_ingredients"]]
        if not ingredients:
            return {"medicine": name, "recognized": False, "findings": [], "pairs": [],
                    "message": f"I couldn't identify \"{name}\", so I can't check it. Ask your pharmacist."}
        assumed = (f"\"{name}\" isn't in RxNorm. Checked as {' + '.join(ingredients)} (an AI suggestion, "
                   "not confirmed): confirm what it contains with your pharmacist.")
    temp = Medication(id=-1, patient_id=pid, name=name, ingredients=ingredients, dose_times=[])
    meds = _active(db, pid)
    ctx = _Ctx(db, pid, [*meds, temp])
    findings, pairs = pair_findings(ctx, [(temp, m) for m in meds])
    return {"medicine": name, "recognized": True, "ingredients": ingredients, "assumed": assumed,
            "findings": [{**f, "id": f"N{i}"} for i, f in enumerate(findings, start=1)], "pairs": pairs,
            "message": None if findings else NO_FINDING}


def side_effects_for(db: Session, pid: int, symptom: str) -> list[dict]:
    ctx = _Ctx(db, pid, _active(db, pid))
    return [{**f, "id": f"S{i}"} for i, f in enumerate(side_effects(ctx, symptom), start=1)]
