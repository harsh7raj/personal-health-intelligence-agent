import uuid
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, OwnedPatient
from app.core.config import get_settings
from app.models.records import Report
from app.schemas.report import (
    FlaggedValue,
    ReportDetail,
    ReportListItem,
    ReportOut,
)
from app.services.report_extraction import parse_report

settings = get_settings()
router = APIRouter(prefix="/patients", tags=["reports"])

# Values are shown in the list preview when non-normal; high/low rank above "unknown".
_FLAG_PRIORITY = {"high": 0, "low": 0, "unknown": 1}
_FLAGGED_PREVIEW_CAP = 3


def _get_report(db: Session, patient_id: int, report_id: int) -> Report:
    report = db.get(Report, report_id)
    if report is None or report.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )
    return report


def _flagged_values(report: Report) -> list[dict]:
    """Extracted values whose flag is not 'normal', most-clinically-notable first."""
    flagged = [
        v
        for v in (report.extracted_values or [])
        if str(v.get("flag") or "").lower() != "normal"
    ]
    flagged.sort(key=lambda v: _FLAG_PRIORITY.get(str(v.get("flag") or "").lower(), 2))
    return flagged


def _to_list_item(report: Report) -> ReportListItem:
    flagged = _flagged_values(report)
    return ReportListItem(
        id=report.id,
        patient_id=report.patient_id,
        filename=report.filename,
        status=report.status,
        report_type=report.report_type,
        test_date=report.test_date,
        ai_summary=report.ai_summary,
        flagged_values=[
            FlaggedValue.model_validate(v) for v in flagged[:_FLAGGED_PREVIEW_CAP]
        ],
        flagged_count=len(flagged),
        parse_error=report.parse_error,
        created_at=report.created_at,
    )


def _download_url(patient_id: int, report_id: int) -> str:
    return f"{settings.API_PREFIX}/patients/{patient_id}/reports/{report_id}/file"


@router.post(
    "/{patient_id}/reports",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_report(
    patient: OwnedPatient,
    db: DbSession,
    background: BackgroundTasks,
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
        status="uploaded",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    # Extraction (text + Groq structured parse) runs AFTER the response is sent, so the
    # upload request never blocks on the LLM call. Status flips uploaded -> parsing ->
    # parsed|failed in the background.
    background.add_task(parse_report, report.id)
    return report


@router.get("/{patient_id}/reports", response_model=list[ReportListItem])
def list_reports(patient: OwnedPatient, db: DbSession) -> list[ReportListItem]:
    # Newest first — the report list is a reverse-chronological feed.
    reports = db.scalars(
        select(Report)
        .where(Report.patient_id == patient.id)
        .order_by(Report.id.desc())
    ).all()
    return [_to_list_item(r) for r in reports]


@router.get("/{patient_id}/reports/{report_id}", response_model=ReportDetail)
def get_report(patient: OwnedPatient, report_id: int, db: DbSession) -> ReportDetail:
    report = _get_report(db, patient.id, report_id)
    return ReportDetail(
        id=report.id,
        patient_id=report.patient_id,
        filename=report.filename,
        report_type=report.report_type,
        summary=report.summary,
        status=report.status,
        test_date=report.test_date,
        extracted_values=report.extracted_values or [],
        ai_summary=report.ai_summary,
        parse_error=report.parse_error,
        created_at=report.created_at,
        download_url=_download_url(patient.id, report.id),
    )


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
