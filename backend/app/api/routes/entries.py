from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DbSession, OwnedPatient
from app.models.records import Entry
from app.schemas.clinical_io import EntryOut

router = APIRouter(prefix="/patients", tags=["entries"])


@router.get("/{patient_id}/entries", response_model=list[EntryOut])
def list_entries(
    patient: OwnedPatient,
    db: DbSession,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[Entry]:
    """Full append-only entry history (all types), newest-first, paginated.
    Read-only projection of the `entries` table — the Log thread renders it."""
    return list(
        db.scalars(
            select(Entry)
            .where(Entry.patient_id == patient.id)
            .order_by(Entry.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
