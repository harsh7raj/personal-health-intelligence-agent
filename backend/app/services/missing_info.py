"""Gap detection (missing info) + derived suggested actions. Deterministic, dedup'd."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.models.clinical import VitalReading
from app.models.intelligence import MissingInformation, SuggestedAction
from app.models.patient import MedicalBackground

settings = get_settings()


def _add_missing(db: Session, patient_id: int, desc: str, related: str, out: list[str]) -> None:
    existing = db.scalar(
        select(MissingInformation).where(
            MissingInformation.patient_id == patient_id,
            MissingInformation.description == desc,
            MissingInformation.resolved.is_(False),
        )
    )
    if existing is None:
        db.add(
            MissingInformation(
                patient_id=patient_id, description=desc, related_to=related
            )
        )
        out.append(desc)


def check_missing_info(db: Session, patient_id: int) -> list[str]:
    out: list[str] = []
    bg = db.scalar(
        select(MedicalBackground).where(MedicalBackground.patient_id == patient_id)
    )
    conditions = [str(c).lower() for c in (bg.conditions if bg else [])]
    now = clock.now()

    if any("hypertension" in c or "high blood pressure" in c for c in conditions):
        last_bp = db.scalar(
            select(VitalReading)
            .where(
                VitalReading.patient_id == patient_id,
                VitalReading.vital_type == "bp_systolic",
            )
            .order_by(VitalReading.recorded_at.desc())
        )
        cutoff = now - timedelta(days=settings.MISSING_BP_DAYS)
        if last_bp is None or (last_bp.recorded_at and last_bp.recorded_at < cutoff):
            _add_missing(
                db,
                patient_id,
                f"No blood pressure reading in the last {settings.MISSING_BP_DAYS} days "
                f"(known hypertension).",
                "blood pressure",
                out,
            )
    return out


def _add_action(db: Session, patient_id: int, text: str, out: list[str]) -> None:
    existing = db.scalar(
        select(SuggestedAction).where(
            SuggestedAction.patient_id == patient_id,
            SuggestedAction.text == text,
            SuggestedAction.dismissed.is_(False),
        )
    )
    if existing is None:
        db.add(SuggestedAction(patient_id=patient_id, text=text))
        out.append(text)


def suggested_actions(
    db: Session, patient_id: int, alerts: list[dict], missing: list[str]
) -> list[str]:
    out: list[str] = []
    if any("blood pressure" in m.lower() for m in missing):
        _add_action(db, patient_id, "Log today's blood pressure", out)
    if any(a["kind"] in ("high_bp", "critical_bp") for a in alerts):
        _add_action(
            db,
            patient_id,
            "Consider discussing your recent blood pressure readings with a doctor",
            out,
        )
    return out
