"""Doctor consultation summary PDF (ReportLab, deterministic: no LLM wording at all).

Everything on it is read from the record or computed in code, in the order a doctor would want it:
what to discuss, current medicines (with changes and adherence), medication findings, readings,
lab results, problems, recent visits and the patient's questions. Each page carries the patient,
a page number and the "not a diagnosis" note."""

from datetime import date, datetime, timedelta
from io import BytesIO
from statistics import mean

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.models.clinical import Medication, MedicationEvent, Problem
from app.models.drugs import MedCheckRun
from app.models.intelligence import Alert
from app.models.patient import MedicalBackground, Patient
from app.models.visits import Reminder, SavedQuestion
from app.services import recurrence, report_explainer, retrieval
from app.services.med_schedule import build_med_calendar
from app.services.visits import visit_items

ACCENT = colors.HexColor("#0d9488")
INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#e2e8f0")
SOFT = colors.HexColor("#f0fdfa")
AMBER = colors.HexColor("#b45309")
RED = colors.HexColor("#b91c1c")
BLUE = colors.HexColor("#1d4ed8")

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Normal"], fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.white)
HSUB = ParagraphStyle("hsub", parent=_ss["Normal"], fontSize=9, leading=12, textColor=colors.white)
SEC = ParagraphStyle("sec", parent=_ss["Normal"], fontName="Helvetica-Bold", fontSize=11.5, leading=14,
                     textColor=ACCENT, spaceBefore=9, spaceAfter=4)
BODY = ParagraphStyle("body", parent=_ss["Normal"], fontSize=9, leading=12.5, textColor=INK)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10.5, textColor=MUTED)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.5, leading=11)
CELLR = ParagraphStyle("cellr", parent=CELL, alignment=TA_RIGHT)
HEAD = ParagraphStyle("head", parent=CELL, fontName="Helvetica-Bold", textColor=MUTED, fontSize=7.5)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=9, bulletIndent=0, spaceAfter=2.5)

VITAL_LABELS = {"blood_glucose": ("Blood glucose", "mg/dL"), "bp_systolic": ("BP systolic", "mmHg"),
                "bp_diastolic": ("BP diastolic", "mmHg"), "weight": ("Weight", "kg"),
                "heart_rate": ("Heart rate", "bpm"), "spo2": ("SpO2", "%"), "temperature": ("Temperature", "")}
_PAGE_W = A4[0] - 30 * mm


def _fmt(d: datetime | date) -> str:
    # "%-d" (no zero padding) is Unix-only and raises on Windows; build it portably.
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _day(iso: str | None) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {d.strftime('%b')} {d.year}" if d.year != clock.today().year else f"{d.day} {d.strftime('%b')}"


def _t(text) -> str:
    """Safe for Helvetica: escape markup and replace characters the base fonts lack."""
    s = "" if text is None else str(text)
    for a, b in {"&": "&amp;", "<": "&lt;", ">": "&gt;", " ": " ", " ": " ", " ": " ",
                 "‑": "-", "‐": "-", "−": "-", "≈": "~", "→": "->", "↑": "up",
                 "↓": "down", "µ": "u", "≤": "<=", "≥": ">="}.items():
        s = s.replace(a, b)
    return s


def _num(v) -> str:
    if v is None:
        return "-"
    return f"{v:g}" if isinstance(v, (int, float)) else _t(v)


def _table(rows: list[list], widths: list[float], header: bool = True, zebra: bool = True) -> Table:
    data = [[c if not isinstance(c, str) else Paragraph(c, HEAD if (header and i == 0) else CELL) for c in r]
            for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3.5),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5), ("LEFTPADDING", (0, 0), (-1, -1), 4),
             ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE)]
    if header:
        style += [("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT)]
    if zebra:
        style += [("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f8fafc")) for r in range(2, len(rows), 2)]
    t.setStyle(TableStyle(style))
    return t


def _section(title: str, body: list) -> list:
    return [KeepTogether([Paragraph(_t(title), SEC), *body[:1]]), *body[1:]] if body else []


# --------------------------------------------------------------------------- content


def _recurrences(db: Session, pid: int, problems: list[Problem]) -> dict[str, dict]:
    """recurrence.detect for every open problem (one episode count used everywhere)."""
    return {p.name: recurrence.detect(db, pid, p.name, exclude_entry_id=None) for p in problems}


def _discussion(db: Session, pid: int, recs: dict[str, dict], findings: list[dict], labs: list[dict]) -> list[str]:
    """Code-built points, most important first. Each is a fact with dates, never a conclusion."""
    points: list[str] = []
    since = (clock.today() - timedelta(days=180)).isoformat()
    ranked = sorted(recs.items(), key=lambda kv: (
        -len([e for e in kv[1]["prior_episodes"] if e["date"] >= since]),
        -max([0, *(1 for f in kv[1]["shared_factors"] if not f["factor"].startswith("dose:"))])))
    for name, r in ranked:
        eps = [e for e in r["prior_episodes"] if e["date"] >= since]
        if len(eps) < 2:
            continue
        txt = f"<b>{_t(name.capitalize())}</b>: {len(eps)} episodes in 6 months ({', '.join(_day(e['date']) for e in eps[-5:])})"
        # A daily medicine taken that day is always true, so it isn't worth a doctor's attention.
        shared = [f for f in r["shared_factors"] if not f["factor"].startswith("dose:") and f["count"] >= 2]
        if shared:
            txt += "; " + "; ".join(f"{f['count']} of {f['of']} with {_t(f['label'])}" for f in shared[:2])
        for ch in r["all_after_medication_change"]:
            first = date.fromisoformat(eps[0]["date"])
            if ch["event"] == "dose_change" and 0 <= (first - date.fromisoformat(ch["date"])).days <= 90:
                txt += (f"; all after {_t(ch['medication'])} went from {_t(ch['old_dose'])} to {_t(ch['new_dose'])} "
                        f"on {_day(ch['date'])}")
                break
        points.append(txt + ".")
        if len(points) >= 3:
            break
    for v in labs:
        if v["flag"] in ("high", "low") and v.get("critical"):
            points.append(f"<b><font color='#b91c1c'>Critical lab value</font></b>: {_t(v['critical']['message'])}")
    out_of_range = [v for v in labs if v["flag"] in ("high", "low")]
    if out_of_range:
        points.append("<b>Latest labs outside the printed range</b>: " + "; ".join(
            f"{_t(v['display_name'])} {_num(v['value'])} {_t(v.get('unit') or '')} ({v['flag']}, range {_t(v.get('reference_range') or '-')})"
            for v in out_of_range[:4]) + ".")
    for f in [f for f in findings if f["level"] != "ai"][:3]:
        lvl = f["level_label"] + (f" {f['severity']}" if f.get("severity") else "")
        points.append(f"<b>Medicines ({_t(lvl)})</b>: {_t(f['title'])}.")
    alerts = db.scalars(select(Alert).where(Alert.patient_id == pid, Alert.created_at >= clock.now() - timedelta(days=90))
                        .order_by(Alert.created_at.desc())).all()
    if alerts:
        points.append("<b>Alerts in the last 90 days</b>: " + "; ".join(
            f"{_t(a.message)} ({_day(clock.to_local(a.created_at).date().isoformat())})" for a in alerts[:3]) + ".")
    overdue = db.scalars(select(Reminder).where(Reminder.patient_id == pid, Reminder.done.is_(False),
                                                Reminder.due_date < clock.today())).all()
    for r in overdue[:2]:
        points.append(f"<b>Overdue</b>: {_t(r.text)} (was due {_day(r.due_date.isoformat())}).")
    return points


def _medicines(db: Session, pid: int) -> list[list]:
    meds = db.scalars(select(Medication).where(Medication.patient_id == pid, Medication.active.is_(True))
                      .order_by(Medication.name)).all()
    cal = build_med_calendar(db, pid)
    taken: dict[int, list[int]] = {}
    for day in cal["days"]:
        if day["is_future"]:
            continue
        for s in day["slots"]:
            t = taken.setdefault(s["medication_id"], [0, 0])
            t[1] += 1
            t[0] += 1 if s["taken"] else 0
    rows = [["Medicine", "Dose and times", "Prescriber", "Since / last change", "Taken, last 14 days"]]
    for m in meds:
        name = f"<b>{_t(m.name)}</b>"
        if m.ingredients and " + ".join(m.ingredients).lower() != m.name.lower():
            name += f"<br/><font color='#64748b'>{_t(' + '.join(m.ingredients))}</font>"
        ev = db.scalars(select(MedicationEvent).where(MedicationEvent.medication_id == m.id,
                                                      MedicationEvent.event_type == "dose_change")
                        .order_by(MedicationEvent.event_date.desc())).first()
        since = _day(m.started_on.isoformat()) if m.started_on else "-"
        if ev:
            since += f"<br/>{_t(ev.old_dose)} -> {_t(ev.new_dose)} on {_day(ev.event_date.isoformat())}"
        t = taken.get(m.id, [0, 0])
        rows.append([name, f"{_t(m.dose or '-')}<br/><font color='#64748b'>{_t(', '.join(m.dose_times or []) or m.frequency or '')}</font>",
                     _t(m.prescriber or "-"), since, f"{t[0]} of {t[1]}" if t[1] else "-"])
    return rows


def _readings(db: Session, pid: int) -> list[list]:
    rows = [["Reading", "Latest", "Last 90 days: average (range)", "Previous 90 days: average", "Change"]]
    for vt, (label, unit) in VITAL_LABELS.items():
        recent = retrieval.vital_series(db, pid, vt, days=90)
        older = [r for r in retrieval.vital_series(db, pid, vt, days=180) if r not in recent]
        if not recent:
            continue
        avg = mean(r["value"] for r in recent)
        prev = mean(r["value"] for r in older) if older else None
        change = "-"
        if prev:
            pct = (avg - prev) / prev * 100
            change = f"<font color='{'#b45309' if pct > 3 else '#1d4ed8' if pct < -3 else '#64748b'}'>{pct:+.1f}%</font>"
        latest = recent[-1]
        rows.append([f"<b>{label}</b> <font color='#64748b'>{unit}</font>",
                     f"{_num(latest['value'])} <font color='#64748b'>({_day(latest['date'])})</font>",
                     f"{avg:.1f} ({_num(min(r['value'] for r in recent))}-{_num(max(r['value'] for r in recent))}), n={len(recent)}",
                     f"{prev:.1f}" if prev else "-", change])
    return rows


def _labs(db: Session, pid: int) -> tuple[list[dict], str | None]:
    reps = db.scalars(select(Report).where(Report.patient_id == pid, Report.status == "parsed")
                      .order_by(Report.test_date.desc().nullslast(), Report.id.desc())).all()
    seen, out = set(), []
    for rep in reps[:6]:
        for v in report_explainer.value_rows(db, pid, rep):
            key = v["test_key"] or v["test_name"]
            if key in seen or v["value"] in (None, ""):
                continue
            seen.add(key)
            out.append({**v, "report_date": report_explainer._report_day(rep)})
    return out, None


def build_pdf(db: Session, patient_id: int) -> bytes:
    patient = db.get(Patient, patient_id)
    bg = db.scalar(select(MedicalBackground).where(MedicalBackground.patient_id == patient_id))
    problems = db.scalars(select(Problem).where(Problem.patient_id == patient_id, Problem.status != "resolved")
                          .order_by(Problem.last_seen.desc().nullslast())).all()
    run = db.scalar(select(MedCheckRun).where(MedCheckRun.patient_id == patient_id))
    findings = ((run.result if run else {}) or {}).get("findings", [])
    labs, _ = _labs(db, patient_id)
    recs = _recurrences(db, patient_id, problems)
    today = clock.today()

    story: list = []
    who = " · ".join(_t(x) for x in [patient.name, f"Age {patient.age}" if patient.age else None, patient.sex,
                                      f"Blood group {patient.blood_group}" if patient.blood_group else None] if x)
    conditions = ", ".join(_t(c) for c in ((bg.conditions if bg else []) or [])) or "None recorded"
    allergies = ", ".join(_t(a) for a in ((bg.allergies if bg else []) or [])) or "None recorded"
    head = Table([[Paragraph("Consultation summary", H1)],
                  [Paragraph(f"{who}<br/>Prepared {_fmt(today)} from the patient's own records", HSUB)]],
                 colWidths=[_PAGE_W])
    head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                              ("TOPPADDING", (0, 0), (-1, 0), 9), ("BOTTOMPADDING", (0, -1), (-1, -1), 9)]))
    story += [head, Spacer(1, 6)]
    facts = Table([[Paragraph(f"<b>Conditions</b><br/>{conditions}", CELL),
                    Paragraph(f"<b>Allergies</b><br/>{allergies}", CELL)]], colWidths=[_PAGE_W * 0.62, _PAGE_W * 0.38])
    facts.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(facts)

    points = _discussion(db, patient_id, recs, findings, labs)
    story += _section("Points to discuss", [Paragraph(p, BULLET, bulletText="•") for p in points]
                      or [Paragraph("Nothing flagged by the record.", SMALL)])

    med_rows = _medicines(db, patient_id)
    if len(med_rows) > 1:
        story += _section("Current medicines", [_table(med_rows, [w * _PAGE_W for w in (0.27, 0.19, 0.17, 0.22, 0.15)])])

    shown = [f for f in findings if f["level"] != "ai"][:6]
    if shown:
        rows = [["Level", "Finding", "Source"]]
        for f in shown:
            lvl = f["level_label"] + (f"<br/><font color='#b45309'>{_t(f['severity'])}</font>" if f.get("severity") else "")
            body = f"<b>{_t(f['title'])}</b>"
            if f.get("quote"):
                body += f"<br/><font color='#64748b'><i>\"{_t(f['quote'][:220])}{'...' if len(f['quote']) > 220 else ''}\"</i></font>"
            rows.append([lvl, body, _t((f.get("source") or {}).get("name") or "-")])
        story += _section("Medication safety findings", [
            _table(rows, [w * _PAGE_W for w in (0.14, 0.62, 0.24)]),
            Paragraph("Verified = DDInter 2.0 database; Official label = quoted from the FDA label (openFDA). "
                      "No finding is not the same as safe: confirm with a pharmacist.", SMALL)])

    read_rows = _readings(db, patient_id)
    if len(read_rows) > 1:
        story += _section("Readings", [_table(read_rows, [w * _PAGE_W for w in (0.2, 0.2, 0.3, 0.17, 0.13)])])

    if labs:
        rows = [["Test", "Latest", "Range", "Flag", "Previous", "Change"]]
        for v in labs[:12]:
            flag = v["flag"]
            fc = "#b45309" if flag == "high" else "#1d4ed8" if flag == "low" else "#64748b"
            prev = f"{_num(v['previous']['value'])} ({_day(v['previous']['date'])})" if v.get("previous") else "-"
            ch = f"{v['change']['amount']:+g}" if v.get("change") else "-"
            rows.append([f"<b>{_t(v['display_name'])}</b>",
                         f"{_num(v['value'])} {_t(v.get('unit') or '')} <font color='#64748b'>({_day(v['report_date'])})</font>",
                         _t(v.get("reference_range") or "-"),
                         f"<font color='{fc}'>{'' if flag == 'unknown' else flag}</font>", prev, ch])
        story += _section("Lab results (latest of each test)", [_table(rows, [w * _PAGE_W for w in (0.22, 0.24, 0.16, 0.08, 0.2, 0.1)])])

    if problems:
        rows = [["Problem", "Severity", "Episodes logged", "First / last logged", "Trend"]]
        problems = sorted(problems, key=lambda p: -len(recs[p.name]["prior_episodes"]))
        for p in problems[:8]:
            tc = "#b45309" if p.trend == "increasing" else "#1d4ed8" if p.trend == "decreasing" else "#64748b"
            first = _day(clock.to_local(p.first_seen).date().isoformat()) if p.first_seen else "-"
            last = _day(clock.to_local(p.last_seen).date().isoformat()) if p.last_seen else "-"
            n = len(recs[p.name]["prior_episodes"])
            rows.append([f"<b>{_t(p.name.capitalize())}</b>", _t(p.severity or "-"), str(n or "-"),
                         f"{first} / {last}", f"<font color='{tc}'>{_t(p.trend or '-')}</font>"])
        story += _section("Problems", [_table(rows, [w * _PAGE_W for w in (0.24, 0.16, 0.2, 0.26, 0.14)])])

    visits = visit_items(db, patient_id, limit=2)
    if visits:
        body = []
        for v in visits:
            body.append(Paragraph(f"<b>{_day(v['date'])}, {_t(v['doctor'])}</b>"
                                  + (f" ({_t(v['specialty'])})" if v.get("specialty") else "")
                                  + (f": {_t(v['reason'])}" if v.get("reason") else ""), BODY))
            body += [Paragraph(_t(s), BULLET, bulletText="•") for s in v["doctor_said"][:4]]
        story += _section("Recent visits (as recorded by the patient)", body)

    questions = db.scalars(select(SavedQuestion).where(SavedQuestion.patient_id == patient_id,
                                                       SavedQuestion.done.is_(False))
                           .order_by(SavedQuestion.created_at)).all()
    if questions:
        story += _section("The patient's questions", [Paragraph(_t(q.text), BULLET, bulletText=f"{i}.")
                                                       for i, q in enumerate(questions[:8], start=1)])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(15 * mm, 12 * mm, A4[0] - 15 * mm, 12 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(15 * mm, 8 * mm, f"{patient.name} · consultation summary · {_fmt(today)}")
        canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"Page {doc.page}")
        canvas.drawCentredString(A4[0] / 2, 4.5 * mm, "Observations from the patient's records, not a diagnosis. "
                                 "Sources: DDInter 2.0, openFDA, RxNorm/RxClass.")
        canvas.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=13 * mm,
                            bottomMargin=17 * mm, title=f"Consultation summary - {patient.name}")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


from app.models.records import Report  # noqa: E402  (kept at the end: avoids a cycle at import time)
