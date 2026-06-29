"""Doctor-facing, token-gated, READ-ONLY views. Reuse the exact same builders as the
patient endpoints (build_snapshot/build_story/build_pdf); only the gate differs (token vs JWT)."""

from fastapi import APIRouter, Response

from app.api.deps import DbSession, TokenPatient
from app.schemas.outputs import SnapshotOut, StoryOut
from app.services.pdf_report import build_pdf
from app.services.snapshot import build_snapshot
from app.services.story import build_story

router = APIRouter(prefix="/shared", tags=["shared"])


@router.get("/{token}/snapshot", response_model=SnapshotOut)
def shared_snapshot(patient: TokenPatient, db: DbSession) -> dict:
    return build_snapshot(db, patient.id)


@router.get("/{token}/story", response_model=StoryOut)
def shared_story(patient: TokenPatient, db: DbSession) -> dict:
    return build_story(db, patient.id)


@router.get("/{token}/consultation/pdf")
def shared_pdf(patient: TokenPatient, db: DbSession) -> Response:
    pdf = build_pdf(db, patient.id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="consultation_{patient.id}.pdf"'
        },
    )
