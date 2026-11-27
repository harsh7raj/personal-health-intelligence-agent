"""Doctor visits, saved questions, reminders and the pre-visit brief (Phase 3, memory.md D37)."""

import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, OwnedPatient
from app.core import llm
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.visits import Reminder, SavedQuestion, Visit
from app.services import med_safety, visits

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/patients", tags=["visits"])
_AUDIO = {".webm", ".ogg", ".mp3", ".m4a", ".wav", ".mp4", ".mpeg", ".mpga", ".flac"}


class VisitUpdate(BaseModel):
    doctor_name: Optional[str] = None
    specialty: Optional[str] = None
    visit_date: Optional[date] = None
    structured: Optional[dict[str, Any]] = None


class QuestionIn(BaseModel):
    text: str = Field(min_length=3, max_length=1000)
    doctor_name: Optional[str] = None
    source: str = "manual"
    source_id: Optional[int] = None


def _visit_out(db: Session, pid: int, v: Visit) -> dict:
    s = v.structured or {}
    out = {"id": v.id, "doctor_name": v.doctor_name, "specialty": v.specialty, "visit_date": v.visit_date.isoformat(),
           "source": v.source, "status": v.status, "transcript": v.transcript, "structured": s,
           "has_audio": bool(v.audio_path), "created_at": v.created_at.isoformat(),
           "confirmed_at": v.confirmed_at.isoformat() if v.confirmed_at else None}
    if v.status == "draft":  # the review screen's checks, recomputed from the current list
        out["medicine_checks"] = [c["check"] for c in visits.checked_changes(db, pid, s)]
    return out


def _get_visit(db: Session, pid: int, vid: int) -> Visit:
    v = db.get(Visit, vid)
    if v is None or v.patient_id != pid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")
    return v


def _recheck(pid: int) -> None:
    try:
        with SessionLocal() as db:
            med_safety.latest(db, pid)
    except Exception:
        logger.warning("medication safety re-check after a visit failed", exc_info=True)


@router.get("/{patient_id}/visits")
def list_visits(patient: OwnedPatient, db: DbSession) -> list[dict]:
    rows = db.scalars(select(Visit).where(Visit.patient_id == patient.id)
                      .order_by(Visit.visit_date.desc(), Visit.id.desc())).all()
    return [{"id": v.id, "doctor_name": v.doctor_name, "specialty": v.specialty, "visit_date": v.visit_date.isoformat(),
             "status": v.status, "source": v.source, "reason": (v.structured or {}).get("reason")} for v in rows]


@router.post("/{patient_id}/visits", status_code=status.HTTP_201_CREATED)
def create_visit(
    patient: OwnedPatient, db: DbSession,
    doctor_name: str = Form(..., min_length=2, max_length=255),
    visit_date: date = Form(...),
    specialty: Optional[str] = Form(None),
    source: str = Form("typed"),
    transcript: Optional[str] = Form(None),
    doctor_consented: bool = Form(False),
    audio: Optional[UploadFile] = File(None),
) -> dict:
    """A recap, typed or as audio (Whisper transcribes it), structured into a DRAFT note.
    Recording the consultation itself needs the doctor's agreement (source=recording)."""
    if source not in ("typed", "voice", "recording"):
        raise HTTPException(status_code=422, detail="source must be typed, voice or recording")
    if source == "recording" and not doctor_consented:
        raise HTTPException(status_code=400, detail="Ask your doctor before recording the consultation.")
    audio_path = None
    text = (transcript or "").strip()
    if audio is not None:
        suffix = Path(audio.filename or "recap.webm").suffix.lower() or ".webm"
        if suffix not in _AUDIO:
            raise HTTPException(status_code=422, detail=f"Unsupported audio type {suffix}")
        dest = Path(get_settings().UPLOAD_DIR) / str(patient.id) / "visits" / f"{uuid.uuid4().hex}{suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(audio.file.read())
        audio_path = str(dest)
        try:
            text = llm.transcribe(dest)
        except Exception as exc:
            logger.warning("transcription failed", exc_info=True)
            raise HTTPException(status_code=502, detail="Couldn't transcribe the audio. Try typing the recap.") from exc
    if not text:
        raise HTTPException(status_code=422, detail="Type the recap or attach audio.")
    structured, generated_by = visits.structure(text, doctor_name.strip(), visit_date)
    v = Visit(patient_id=patient.id, doctor_name=doctor_name.strip(), specialty=(specialty or "").strip() or None,
              visit_date=visit_date, source=source if audio is not None or source == "typed" else "typed",
              transcript=text, audio_path=audio_path, structured=structured, status="draft")
    db.add(v)
    db.commit()
    db.refresh(v)
    return {**_visit_out(db, patient.id, v), "generated_by": generated_by}


# Literal paths before "/{visit_id}".
@router.get("/{patient_id}/visits/doctors")
def list_doctors(patient: OwnedPatient, db: DbSession) -> list[dict]:
    return visits.doctors(db, patient.id)


@router.get("/{patient_id}/visits/brief")
def pre_visit_brief(patient: OwnedPatient, db: DbSession, doctor: str = Query(..., min_length=2)) -> dict:
    return visits.brief(db, patient.id, doctor)


@router.get("/{patient_id}/visits/{visit_id}")
def get_visit(patient: OwnedPatient, visit_id: int, db: DbSession) -> dict:
    return _visit_out(db, patient.id, _get_visit(db, patient.id, visit_id))


@router.put("/{patient_id}/visits/{visit_id}")
def update_visit(patient: OwnedPatient, visit_id: int, payload: VisitUpdate, db: DbSession) -> dict:
    """Edit a draft on the review screen. A confirmed note is not edited."""
    v = _get_visit(db, patient.id, visit_id)
    if v.status != "draft":
        raise HTTPException(status_code=409, detail="This note is already confirmed")
    for field in ("doctor_name", "specialty", "visit_date"):
        if getattr(payload, field) is not None:
            setattr(v, field, getattr(payload, field))
    if payload.structured is not None:
        v.structured = visits.normalize_edit(payload.structured, v.doctor_name, v.visit_date)
    db.commit()
    db.refresh(v)
    return _visit_out(db, patient.id, v)


@router.post("/{patient_id}/visits/{visit_id}/preview")
def preview_visit(patient: OwnedPatient, visit_id: int, db: DbSession) -> dict:
    """Clashes the new or changed medicines would raise with the others (other doctors'
    included), before anything is saved."""
    out = visits.preview_clashes(db, patient.id, _get_visit(db, patient.id, visit_id))
    db.commit()  # keep any labels/classes fetched (reference data only)
    return out


@router.post("/{patient_id}/visits/{visit_id}/confirm")
def confirm_visit(patient: OwnedPatient, visit_id: int, db: DbSession, background: BackgroundTasks) -> dict:
    v = _get_visit(db, patient.id, visit_id)
    if v.status != "draft":
        raise HTTPException(status_code=409, detail="This note is already confirmed")
    try:
        result = visits.confirm(db, patient.id, v)
    except visits.NeedsReview as exc:
        raise HTTPException(status_code=409, detail=f"Please check these medicine names first: {exc}") from exc
    background.add_task(_recheck, patient.id)
    db.refresh(v)
    return {**_visit_out(db, patient.id, v), **result}


@router.delete("/{patient_id}/visits/{visit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_visit(patient: OwnedPatient, visit_id: int, db: DbSession) -> None:
    v = _get_visit(db, patient.id, visit_id)
    if v.status != "draft":
        raise HTTPException(status_code=409, detail="Confirmed notes are kept")
    if v.audio_path:
        Path(v.audio_path).unlink(missing_ok=True)
    db.delete(v)
    db.commit()


# ---------------------------------------------------------------- saved questions, reminders


@router.get("/{patient_id}/questions")
def list_questions(patient: OwnedPatient, db: DbSession, include_done: bool = False) -> list[dict]:
    q = select(SavedQuestion).where(SavedQuestion.patient_id == patient.id)
    if not include_done:
        q = q.where(SavedQuestion.done.is_(False))
    return [{"id": r.id, "text": r.text, "doctor_name": r.doctor_name, "source": r.source, "source_id": r.source_id,
             "done": r.done, "created_at": r.created_at.isoformat()}
            for r in db.scalars(q.order_by(SavedQuestion.created_at)).all()]


@router.post("/{patient_id}/questions", status_code=status.HTTP_201_CREATED)
def save_questions(patient: OwnedPatient, payload: list[QuestionIn], db: DbSession) -> dict:
    """Save questions for the next visit (from the report explainer, a visit, or typed)."""
    existing = {r.text.strip().lower() for r in db.scalars(
        select(SavedQuestion).where(SavedQuestion.patient_id == patient.id, SavedQuestion.done.is_(False))).all()}
    added = 0
    for q in payload:
        if q.text.strip().lower() in existing:
            continue
        db.add(SavedQuestion(patient_id=patient.id, text=q.text.strip(), doctor_name=q.doctor_name,
                             source=q.source if q.source in ("report", "visit", "manual") else "manual",
                             source_id=q.source_id))
        added += 1
    db.commit()
    return {"added": added}


@router.post("/{patient_id}/questions/{question_id}/done")
def question_done(patient: OwnedPatient, question_id: int, db: DbSession) -> dict:
    q = db.get(SavedQuestion, question_id)
    if q is None or q.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Question not found")
    q.done = True
    db.commit()
    return {"id": q.id, "done": True}


@router.get("/{patient_id}/reminders")
def list_reminders(patient: OwnedPatient, db: DbSession) -> list[dict]:
    rows = db.scalars(select(Reminder).where(Reminder.patient_id == patient.id, Reminder.done.is_(False))
                      .order_by(Reminder.due_date.nulls_last(), Reminder.id)).all()
    return [{"id": r.id, "kind": r.kind, "text": r.text, "doctor_name": r.doctor_name, "visit_id": r.visit_id,
             "due_date": r.due_date.isoformat() if r.due_date else None} for r in rows]


@router.post("/{patient_id}/reminders/{reminder_id}/done")
def reminder_done(patient: OwnedPatient, reminder_id: int, db: DbSession) -> dict:
    r = db.get(Reminder, reminder_id)
    if r is None or r.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Reminder not found")
    r.done = True
    db.commit()
    return {"id": r.id, "done": True}
