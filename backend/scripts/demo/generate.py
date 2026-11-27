"""Expand a demo story script (patients/<key>.yaml) into dated events (memory.md D32).

Deterministic: the same script and run date give the same timeline (seeded noise). Lab
reports become text PDFs with an Indian-lab layout from a fictional lab.
"""

import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import yaml
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core import clock

DEMO_DIR = Path(__file__).resolve().parent
PATIENTS_DIR = DEMO_DIR / "patients"
GENERATED_DIR = DEMO_DIR / "generated"  # gitignored; rebuilt on every reset

# Same-minute ordering: medicine changes, then doses, then readings/reports, then logs.
_ORDER = {"med_change": 0, "dose": 1, "reading": 2, "bp": 2, "report": 3, "entry": 4, "visit": 5}


@dataclass(order=True)
class Event:
    at: datetime
    order: int
    kind: str = field(compare=False)
    data: dict = field(compare=False, default_factory=dict)


def load_script(key: str) -> dict:
    return yaml.safe_load((PATIENTS_DIR / f"{key}.yaml").read_text(encoding="utf-8"))


def available() -> list[str]:
    return sorted(p.stem for p in PATIENTS_DIR.glob("*.yaml"))


def at(today: date, days_ago: int, hhmm: str) -> datetime:
    """That IST calendar day at hh:mm, as UTC."""
    h, m = (int(x) for x in hhmm.split(":"))
    day = today - timedelta(days=days_ago)
    return datetime.combine(day, time(h, m), tzinfo=clock.local_tz()).astimezone(timezone.utc)


def _event(when: datetime, kind: str, **data) -> Event:
    return Event(when, _ORDER[kind], kind, data)


def build_timeline(script: dict, today: date) -> list[Event]:
    rng = random.Random(script.get("adherence", {}).get("seed", 1))
    rate = script.get("adherence", {}).get("rate", 0.95)
    days = script["history_days"]
    events: list[Event] = []

    for ch in script.get("medication_changes", []):
        events.append(_event(at(today, ch["days_ago"], "09:00"), "med_change", **ch))

    # Doses marked taken (with gaps). On a planted episode day the morning dose is taken.
    episode_days = {e["days_ago"] for e in script.get("episodes", [])}
    for d in range(days, 0, -1):
        for med in script["medicines"]:
            if d > med["started_days_ago"]:
                continue
            for t in med["dose_times"]:
                if (d in episode_days and t == "08:00") or rng.random() < rate:
                    taken = at(today, d, t) + timedelta(minutes=rng.randint(0, 25))
                    events.append(_event(taken, "dose", medicine=med["name"],
                                         date=(today - timedelta(days=d)).isoformat(), time=t))

    def series(spec: dict, start: float, end: float, d: int) -> float:
        frac = 1 - d / days  # 0 at the start of the history, 1 today
        return start + (end - start) * frac + rng.gauss(0, spec["noise"])

    readings = script.get("readings", {})
    if "fasting_glucose" in readings:
        g = readings["fasting_glucose"]
        for d in range(days, 0, -g["every_days"]):
            events.append(_event(at(today, d, g["time"]), "reading", vital_type="blood_glucose",
                                 value=round(series(g, g["start"], g["end"], d)), unit="mg/dL"))
    if "bp" in readings:
        b = readings["bp"]
        for d in range(days, 0, -b["every_days"]):
            events.append(_event(at(today, d, b["time"]), "bp",
                                 systolic=round(series(b, *b["systolic"], d)),
                                 diastolic=round(series(b, *b["diastolic"], d))))
    for pt in readings.get("points", []):  # exact values on chosen days
        events.append(_event(at(today, pt["days_ago"], pt["time"]), "reading", vital_type=pt["vital_type"],
                             value=pt["value"], unit=pt.get("unit")))
    if "weight" in readings:
        w = readings["weight"]
        for d in range(days, 0, -w["every_days"]):
            events.append(_event(at(today, d, w["time"]), "reading", vital_type="weight",
                                 value=round(series(w, w["start"], w["end"], d), 1), unit="kg"))

    for i, rep in enumerate(script.get("reports", []), start=1):
        events.append(_event(at(today, rep["days_ago"], "11:00"), "report", index=i, **rep))

    for ep in script.get("episodes", []):
        d = ep["days_ago"]
        events.append(_event(at(today, d, ep["lunch"]["time"]), "entry", text=ep["lunch"]["text"]))
        events.append(_event(at(today, d, ep["episode"]["time"]), "entry", text=ep["episode"]["text"]))
        if ep.get("glucose"):
            g = ep["glucose"]
            events.append(_event(at(today, d, g["time"]), "reading", vital_type="blood_glucose",
                                 value=g["value"], unit="mg/dL"))

    for v in script.get("visits", []):
        events.append(_event(at(today, v["days_ago"], v.get("time", "17:00")), "visit", **v))

    for log in script.get("logs", []):
        events.append(_event(at(today, log["days_ago"], log["time"]), "entry", text=log["text"]))

    return sorted(events)


def make_lab_pdf(path: Path, script: dict, report: dict, sample_day: date) -> Path:
    """A lab report as a text PDF (so pypdf can read it): any panel via `tests`, or Harsh's
    HbA1c panel via `hba1c` / `fasting_glucose`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    lab, pt = script["lab"], script["patient"]
    rows = [["Test", "Result", "Unit", "Biological reference interval"]]
    if report.get("tests"):
        rows += [[t["name"], f"{t['value']}", t.get("unit") or "", t.get("range") or "-"] for t in report["tests"]]
    else:
        hba1c = report["hba1c"]
        eag = round(28.7 * hba1c - 46.7)  # standard HbA1c -> estimated average glucose
        rows += [
            ["HbA1c (Glycated haemoglobin)", f"{hba1c}", "%", "4.0 - 5.6"],
            ["Estimated average glucose (eAG)", f"{eag}", "mg/dL", "-"],
            ["Fasting plasma glucose", f"{report['fasting_glucose']}", "mg/dL", "70 - 100"],
        ]
    table = Table(rows, colWidths=[200, 60, 50, 170])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b57")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    day = f"{sample_day.day} {sample_day.strftime('%b %Y')}"
    story = [
        Paragraph(f"<b>{lab['name']}</b>", styles["Title"]),
        Paragraph(lab["address"], styles["Normal"]),
        Spacer(1, 10),
        Paragraph(f"Patient: <b>{pt['name']}</b> &nbsp; Age/Sex: {pt['age']} / {pt['sex']} &nbsp; "
                  f"Ref. by: Dr. Rao", styles["Normal"]),
        Paragraph(f"Sample collected: {day} &nbsp; Report date: {day} &nbsp; Sample: EDTA whole blood "
                  f"/ fluoride plasma", styles["Normal"]),
        Spacer(1, 12),
        Paragraph(f"<b>{report.get('panel', 'Diabetes Panel').upper()}</b>", styles["Heading3"]),
        table,
        Spacer(1, 14),
        Paragraph(("Method: HbA1c by HPLC (NGSP certified). " if not report.get("tests") else "")
                  + "Computer-generated report. Fictional demo data.", styles["Italic"]),
    ]
    SimpleDocTemplate(str(path), pagesize=A4).build(story)
    return path


def make_photo(pdf: Path, out: Path) -> Path:
    """A phone-style photo of a report: tilted, slightly blurred, on an off-white background."""
    import pypdfium2
    from PIL import ImageFilter

    doc = pypdfium2.PdfDocument(str(pdf))
    try:
        img = doc[0].render(scale=2).to_pil().convert("RGB")
    finally:
        doc.close()
    img = img.rotate(3, expand=True, fillcolor=(235, 232, 225)).filter(ImageFilter.GaussianBlur(0.8))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=82)
    return out


def make_live_files(script: dict, today: date) -> list[Path]:
    """Files kept aside for live uploads in the demo (not replayed): PDFs, or photos of them."""
    out = []
    for rep in script.get("live_reports", []):
        day = today - timedelta(days=rep["days_ago"])
        pdf = make_lab_pdf(GENERATED_DIR / script["key"] / f"{rep['file']}.pdf", script, rep, day)
        out.append(make_photo(pdf, pdf.with_suffix(".jpg")) if rep.get("photo") else pdf)
    return out
