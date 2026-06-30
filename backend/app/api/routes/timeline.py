from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession, OwnedPatient
from app.schemas.outputs import ProblemTimelineOut, TimelineDetailOut
from app.services.problem_timeline import build_problem_timeline
from app.services.timeline import build_timeline_detail

router = APIRouter(prefix="/patients", tags=["timeline"])


@router.get("/{patient_id}/timeline/{day}/detail", response_model=TimelineDetailOut)
def timeline_detail(
    patient: OwnedPatient,
    day: date,
    db: DbSession,
    window_days: int = Query(1, ge=0, le=14),
    start: Optional[date] = Query(
        None,
        description=(
            "Explicit window start for span/derived events (e.g. a trend's first "
            "contributing reading). When given, the window is [start, day] and "
            "window_days is ignored. Omit for point-in-time events."
        ),
    ),
) -> dict:
    """Assemble the full context for a timeline point: the raw entries the patient
    wrote, vitals/symptoms recorded, and observations/alerts the system generated.

    Point-in-time events use `day ± window_days`; span events (trends) pass an
    explicit `start` so the window covers the period that actually produced them."""
    return build_timeline_detail(db, patient.id, day, window_days, start_day=start)


@router.get(
    "/{patient_id}/problems/{problem_id}/timeline",
    response_model=ProblemTimelineOut,
)
def problem_timeline(patient: OwnedPatient, problem_id: int, db: DbSession) -> dict:
    """One problem's chronological evidence: its matched symptom entries, any vital
    readings tied to it, derived trend-change moments, and first_seen/resolved
    milestones. Factual only — no standalone observations."""
    result = build_problem_timeline(db, patient.id, problem_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found"
        )
    return result
