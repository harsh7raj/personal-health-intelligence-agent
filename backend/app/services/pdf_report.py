"""Doctor consultation summary PDF — deterministic ReportLab template (no LLM for layout).
Reads the same assemble_state() as snapshot/story, plus the narrative from build_story(),
so the document leads with framing and stays consistent with the rest of the app."""

from datetime import datetime, timezone
from io import BytesIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.clinical import Medication, VitalReading
from app.models.intelligence import Alert
from app.models.records import Entry
from app.schemas.health_state import PatientHealthState
from app.services.state_assembler import assemble_state
from app.services.story import build_story

# Deliberate palette (shared with the frontend): deep teal accent + slate ink.
ACCENT = colors.HexColor("#0d9488")
INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
ROW_ALT = colors.HexColor("#f1f5f9")
AMBER = colors.HexColor("#b45309")
BLUE = colors.HexColor("#1d4ed8")

_styles = getSampleStyleSheet()
_TITLE = ParagraphStyle("phiaTitle", parent=_styles["Title"], fontSize=19, textColor=colors.white, alignment=0, spaceAfter=0)
_SUB = ParagraphStyle("phiaSub", parent=_styles["Normal"], fontSize=10, textColor=MUTED)
_SECTION = ParagraphStyle("phiaSection", parent=_styles["Heading2"], fontSize=13, textColor=INK, spaceBefore=4, spaceAfter=4)
_BODY = ParagraphStyle("phiaBody", parent=_styles["Normal"], fontSize=10, leading=15, textColor=INK)
_BULLET = ParagraphStyle("phiaBullet", parent=_BODY, leftIndent=10, spaceAfter=2)
_ITALIC = ParagraphStyle("phiaItalic", parent=_styles["Italic"], fontSize=9, textColor=MUTED)


def _earliest(db: Session, patient_id: int) -> datetime | None:
    e = db.scalar(select(func.min(Entry.created_at)).where(Entry.patient_id == patient_id))
    v = db.scalar(select(func.min(VitalReading.recorded_at)).where(VitalReading.patient_id == patient_id))
    dates = [d for d in (e, v) if d is not None]
    return min(dates) if dates else None


def _fmt(d: datetime) -> str:
    return d.strftime("%b %-d, %Y")


def _trend_color(trend: str | None):
    if trend in ("rising", "increasing"):
        return AMBER
    if trend == "falling":
        return BLUE
    return MUTED


def _section(title: str) -> list:
    return [Spacer(1, 12), Paragraph(title, _SECTION), HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceAfter=8)]


def _styled_table(rows: list[list], width: float, trend_col: int | None = None) -> Table:
    t = Table(rows, hAlign="LEFT", colWidths=[width / len(rows[0])] * len(rows[0]))
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if trend_col is not None:
        for r in range(1, len(rows)):
            style.append(("TEXTCOLOR", (trend_col, r), (trend_col, r), _trend_color(str(rows[r][trend_col]))))
    t.setStyle(TableStyle(style))
    return t


def _trend_hex(trend: str | None) -> str:
    if trend in ("rising", "increasing"):
        return "#b45309"
    if trend == "falling":
        return "#1d4ed8"
    return "#475569"


def _reason_for_review(state: PatientHealthState) -> str:
    """Chief-complaint-style line synthesized from existing data (non-diagnostic)."""
    bits: list[str] = []
    if any(v.trend == "rising" and vt.startswith("bp") for vt, v in state.vital_summary.items()):
        bits.append("rising blood pressure")
    for vt, v in state.vital_summary.items():
        if v.trend == "rising" and not vt.startswith("bp"):
            bits.append(f"rising {vt.replace('_', ' ')}")
    for p in state.active_problems:
        if p.trend in ("increasing", "rising"):
            bits.append(f"increasing {p.name} frequency")
    if not bits and state.active_problems:
        bits.append(f"ongoing {state.active_problems[0].name}")
    seen: list[str] = []
    for b in bits:
        if b not in seen:
            seen.append(b)
    if not seen:
        return "Routine longitudinal review; no active concerns flagged."
    return "Review prompted by " + ", ".join(seen[:3]) + "."


def _problem_pattern(db: Session, patient_id: int, name: str) -> str | None:
    """Derive episode frequency/spacing from the patient's symptom entries (no fabrication)."""
    rows = db.scalars(
        select(Entry).where(Entry.patient_id == patient_id, Entry.type == "symptom")
    ).all()
    norm = name.strip().lower()
    dates = sorted(
        e.created_at
        for e in rows
        if e.created_at and str((e.structured or {}).get("name", "")).strip().lower() == norm
    )
    if len(dates) < 2:
        return None
    n = len(dates)
    span_days = (dates[-1] - dates[0]).days
    avg = span_days / (n - 1) if n > 1 else 0
    weeks = max(1, round(avg / 7))
    cadence = f"≈ every {weeks} wk" + ("s" if weeks != 1 else "")
    recent_gap = (dates[-1] - dates[-2]).days
    note = "; more frequent recently" if avg and recent_gap < avg * 0.7 else ""
    return f"{n} episodes since {dates[0].strftime('%b %Y')} ({cadence}{note})"


def build_pdf(db: Session, patient_id: int) -> bytes:
    state = assemble_state(db, patient_id)
    idn = state.identity
    start = _earliest(db, patient_id)
    end = datetime.now(timezone.utc)
    date_range = f"Summary covering {_fmt(start)} – {_fmt(end)}" if start else f"Generated {_fmt(end)}"

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter, title="Consultation Summary",
        topMargin=0.6 * inch, bottomMargin=0.6 * inch, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    )
    width = doc.width
    e: list = []

    # Header band
    band = Table([[Paragraph("Health Consultation Summary", _TITLE)]], colWidths=[width])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    e.append(band)
    e.append(Spacer(1, 6))
    e.append(Paragraph(
        f"<b>{idn.name or 'Patient'}</b> &nbsp;·&nbsp; Age {idn.age if idn.age is not None else '?'} "
        f"&nbsp;·&nbsp; {idn.sex or '?'} &nbsp;·&nbsp; Blood group {idn.blood_group or '?'}", _SUB))
    e.append(Paragraph(date_range, _SUB))

    # Reason for review (chief-complaint style, synthesized from existing data)
    e.append(Spacer(1, 8))
    callout = Table([[Paragraph(f"<b>Reason for Review:</b> {_reason_for_review(state)}", _BODY)]], colWidths=[width])
    callout.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ecfdf5")),
        ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    e.append(callout)

    # Lead narrative (from the health story)
    e += _section("Clinical Summary")
    story = build_story(db, patient_id)["story"]
    for para in [p for p in story.split("\n\n") if p.strip()]:
        e.append(Paragraph(para.strip(), _BODY))
        e.append(Spacer(1, 4))

    # Active problems with derived frequency/spacing detail
    e += _section("Active Problems")
    if state.active_problems:
        for p in state.active_problems:
            hexc = _trend_hex(p.trend)
            e.append(Paragraph(
                f'<b>{p.name}</b> &nbsp;—&nbsp; {p.severity or "unspecified severity"} '
                f'&nbsp;·&nbsp; <font color="{hexc}"><b>{p.trend or "stable"}</b></font>', _BODY))
            detail = _problem_pattern(db, patient_id, p.name) or p.frequency
            if detail:
                e.append(Paragraph(detail, _ITALIC))
            e.append(Spacer(1, 6))
    else:
        e.append(Paragraph("None recorded.", _BODY))

    # Current medications — what the patient is already taking
    e += _section("Current Medications")
    meds = list(db.scalars(
        select(Medication).where(Medication.patient_id == patient_id).order_by(Medication.name)
    ).all())
    if meds:
        rows = [["Medication", "Dose", "Frequency", "Status"]]
        rows += [[m.name, m.dose or "-", m.frequency or "-", "active" if m.active else "inactive"] for m in meds]
        e.append(_styled_table(rows, width))
    else:
        e.append(Paragraph("None recorded.", _BODY))

    # Vital trends
    e += _section("Vital Trends")
    if state.vital_summary:
        rows = [["Vital", "Latest", "Change", "Trend"]]
        for vt, v in state.vital_summary.items():
            change = f"{v.delta_pct * 100:+.0f}%" if v.delta_pct is not None else "-"
            rows.append([vt, str(v.latest) if v.latest is not None else "-", change, v.trend or "stable"])
        e.append(_styled_table(rows, width, trend_col=3))
    else:
        e.append(Paragraph("None recorded.", _BODY))

    # AI observations — doctor framing, not a raw bullet dump
    e += _section("AI-Surfaced Patterns")
    e.append(Paragraph(
        "Data-derived patterns from the patient's longitudinal record, provided as context only "
        "(informational, non-diagnostic):", _ITALIC))
    e.append(Spacer(1, 4))
    if state.ai_observations:
        for o in state.ai_observations:
            e.append(Paragraph(f"•&nbsp; {o.text}", _BULLET))
    else:
        e.append(Paragraph("No notable patterns surfaced.", _BODY))

    # Suggested actions — what the system already flagged as worth discussing
    if state.suggested_next_actions:
        e += _section("Prompts for Discussion")
        e.append(Paragraph(
            "Items the system flagged as worth raising with the patient (non-diagnostic):", _ITALIC))
        e.append(Spacer(1, 4))
        for a in state.suggested_next_actions:
            e.append(Paragraph(f"•&nbsp; {a.text}", _BULLET))

    # Recent alerts
    recent_alerts = list(db.scalars(
        select(Alert).where(Alert.patient_id == patient_id).order_by(Alert.created_at.desc())
    ).all())[:6]
    if recent_alerts:
        e += _section("Recent Alerts")
        for a in recent_alerts:
            col = "#b91c1c" if a.severity == "critical" else "#b45309"
            e.append(Paragraph(f'<font color="{col}">●</font>&nbsp; {a.message}', _BULLET))

    if state.missing_information:
        e += _section("Information Gaps")
        for m in state.missing_information:
            e.append(Paragraph(f"•&nbsp; {m.description}", _BULLET))

    e.append(Spacer(1, 18))
    e.append(Paragraph(
        f"Generated {end.strftime('%Y-%m-%d %H:%M UTC')} · AI-generated informational summary, not a diagnosis.",
        _ITALIC))

    doc.build(e)
    return buf.getvalue()
