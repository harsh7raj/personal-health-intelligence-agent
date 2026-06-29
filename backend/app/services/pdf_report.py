"""Doctor consultation summary PDF — deterministic ReportLab template (no LLM).
Reads the same assemble_state() as snapshot/story, so all three stay consistent."""

from datetime import datetime, timezone
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.intelligence import Alert
from app.services.state_assembler import assemble_state

_HEADER_BG = colors.HexColor("#34495e")


def _table(data: list[list[str]]) -> Table:
    t = Table(data, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f4f6")]),
            ]
        )
    )
    return t


def build_pdf(db: Session, patient_id: int) -> bytes:
    state = assemble_state(db, patient_id)
    styles = getSampleStyleSheet()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title="Consultation Summary")
    e: list = []

    e.append(Paragraph("Health Consultation Summary", styles["Title"]))
    idn = state.identity
    e.append(
        Paragraph(
            f"{idn.name or 'Patient'} — Age {idn.age if idn.age is not None else '?'}, "
            f"Sex {idn.sex or '?'}, Blood group {idn.blood_group or '?'}",
            styles["Normal"],
        )
    )
    e.append(
        Paragraph(
            "AI-generated informational summary — observations only, not a diagnosis.",
            styles["Italic"],
        )
    )
    e.append(Spacer(1, 14))

    e.append(Paragraph("Active Problems", styles["Heading2"]))
    if state.active_problems:
        rows = [["Problem", "Severity", "Frequency", "Trend"]]
        rows += [
            [p.name, p.severity or "-", p.frequency or "-", p.trend or "-"]
            for p in state.active_problems
        ]
        e.append(_table(rows))
    else:
        e.append(Paragraph("None recorded.", styles["Normal"]))
    e.append(Spacer(1, 12))

    e.append(Paragraph("Vital Trends", styles["Heading2"]))
    if state.vital_summary:
        rows = [["Vital", "Latest", "Trend", "Change"]]
        for vt, v in state.vital_summary.items():
            delta = f"{v.delta_pct * 100:+.0f}%" if v.delta_pct is not None else "-"
            rows.append([vt, str(v.latest) if v.latest is not None else "-", v.trend or "-", delta])
        e.append(_table(rows))
    else:
        e.append(Paragraph("None recorded.", styles["Normal"]))
    e.append(Spacer(1, 12))

    e.append(Paragraph("AI Observations", styles["Heading2"]))
    if state.ai_observations:
        for o in state.ai_observations:
            e.append(Paragraph(f"• {o.text}", styles["Normal"]))
    else:
        e.append(Paragraph("None.", styles["Normal"]))
    e.append(Spacer(1, 12))

    recent_alerts = list(
        db.scalars(
            select(Alert)
            .where(Alert.patient_id == patient_id)
            .order_by(Alert.created_at.desc())
        ).all()
    )[:5]
    e.append(Paragraph("Recent Alerts", styles["Heading2"]))
    if recent_alerts:
        for a in recent_alerts:
            e.append(Paragraph(f"• [{a.severity or 'info'}] {a.message}", styles["Normal"]))
    else:
        e.append(Paragraph("None.", styles["Normal"]))
    e.append(Spacer(1, 12))

    if state.missing_information:
        e.append(Paragraph("Missing Information", styles["Heading2"]))
        for m in state.missing_information:
            e.append(Paragraph(f"• {m.description}", styles["Normal"]))
    e.append(Spacer(1, 16))

    e.append(
        Paragraph(
            f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}",
            styles["Italic"],
        )
    )

    doc.build(e)
    return buf.getvalue()
