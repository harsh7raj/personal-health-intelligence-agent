import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, OwnedPatient
from app.core.config import get_settings
from app.models.records import Report
from app.schemas.report import ReportOut

settings = get_settings()
router = APIRouter(prefix="/patients", tags=["reports"])


def _get_report(db: Session, patient_id: int, report_id: int) -> Report:
    report = db.get(Report, report_id)
    if report is None or report.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )
    return report


@router.post(
    "/{patient_id}/reports",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_report(
    patient: OwnedPatient,
    db: DbSession,
    file: UploadFile = File(...),
    report_type: Optional[str] = Form(None),
    summary: Optional[str] = Form(None),
) -> Report:
    dest_dir = Path(settings.UPLOAD_DIR) / str(patient.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload").name
    stored = dest_dir / f"{uuid.uuid4().hex}_{safe_name}"
    with stored.open("wb") as out:
        out.write(file.file.read())
    report = Report(
        patient_id=patient.id,
        filename=safe_name,
        path=str(stored),
        report_type=report_type,
        summary=summary,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("/{patient_id}/reports", response_model=list[ReportOut])
def list_reports(patient: OwnedPatient, db: DbSession) -> list[Report]:
    return list(
        db.scalars(
            select(Report).where(Report.patient_id == patient.id).order_by(Report.id)
        ).all()
    )


@router.get("/{patient_id}/reports/{report_id}", response_model=ReportOut)
def get_report(patient: OwnedPatient, report_id: int, db: DbSession) -> Report:
    return _get_report(db, patient.id, report_id)


@router.get("/{patient_id}/reports/{report_id}/file")
def download_report(
    patient: OwnedPatient, report_id: int, db: DbSession
) -> FileResponse:
    report = _get_report(db, patient.id, report_id)
    if not Path(report.path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report file missing on disk"
        )
    return FileResponse(report.path, filename=report.filename)


@router.delete(
    "/{patient_id}/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_report(patient: OwnedPatient, report_id: int, db: DbSession) -> None:
    report = _get_report(db, patient.id, report_id)
    Path(report.path).unlink(missing_ok=True)
    db.delete(report)
    db.commit()
