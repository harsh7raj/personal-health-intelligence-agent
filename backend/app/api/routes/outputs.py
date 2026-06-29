from typing import Optional

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.api.deps import DbSession, OwnedPatient
from app.models.clinical import Problem
from app.models.intelligence import Observation
from app.schemas.outputs import ObservationOut, ProblemOut, SnapshotOut, StoryOut
from app.services.pdf_report import build_pdf
from app.services.snapshot import build_snapshot
from app.services.story import build_story

router = APIRouter(prefix="/patients", tags=["outputs"])


@router.get("/{patient_id}/snapshot", response_model=SnapshotOut)
def snapshot(patient: OwnedPatient, db: DbSession) -> dict:
    return build_snapshot(db, patient.id)


@router.get("/{patient_id}/story", response_model=StoryOut)
def story(patient: OwnedPatient, db: DbSession) -> dict:
    return build_story(db, patient.id)


@router.get("/{patient_id}/consultation/pdf")
def consultation_pdf(patient: OwnedPatient, db: DbSession) -> Response:
    pdf = build_pdf(db, patient.id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="consultation_{patient.id}.pdf"'
        },
    )


@router.get("/{patient_id}/problems", response_model=list[ProblemOut])
def list_problems(
    patient: OwnedPatient, db: DbSession, status: Optional[str] = Query(None)
) -> list[Problem]:
    q = select(Problem).where(Problem.patient_id == patient.id)
    if status:
        q = q.where(Problem.status == status)
    return list(db.scalars(q.order_by(Problem.id)).all())


@router.get("/{patient_id}/observations", response_model=list[ObservationOut])
def list_observations(patient: OwnedPatient, db: DbSession) -> list[Observation]:
    return list(
        db.scalars(
            select(Observation)
            .where(Observation.patient_id == patient.id)
            .order_by(Observation.created_at.desc())
        ).all()
    )
