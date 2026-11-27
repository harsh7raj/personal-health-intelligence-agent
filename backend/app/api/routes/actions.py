from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, OwnedPatient
from app.models.intelligence import SuggestedAction
from app.schemas.outputs import SuggestedActionOut
from app.services.missing_info import dismiss_action

router = APIRouter(prefix="/patients", tags=["suggested-actions"])


@router.get("/{patient_id}/suggested-actions", response_model=list[SuggestedActionOut])
def list_suggested_actions(patient: OwnedPatient, db: DbSession) -> list[SuggestedAction]:
    """Open suggestions (not dismissed), newest first, with ids so they can be dismissed."""
    return list(
        db.scalars(
            select(SuggestedAction)
            .where(SuggestedAction.patient_id == patient.id, SuggestedAction.dismissed.is_(False))
            .order_by(SuggestedAction.created_at.desc())
        ).all()
    )


@router.post(
    "/{patient_id}/suggested-actions/{action_id}/dismiss", response_model=SuggestedActionOut
)
def dismiss_suggested_action(
    patient: OwnedPatient, action_id: int, db: DbSession
) -> SuggestedAction:
    action = db.get(SuggestedAction, action_id)
    if action is None or action.patient_id != patient.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    if not action.dismissed:
        dismiss_action(action)
        db.commit()
        db.refresh(action)
    return action
