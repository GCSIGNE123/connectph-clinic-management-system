"""SOAP / diagnosis learned-suggestions endpoint (Task #2, extended by Task #6).

`GET /consultations/soap-suggestions?field=<field>&q=<query>` - read-only and
clinic-scoped. Doctor, Owner and Administrator (the SOAP edit roles) may ask for
any allowlisted field. Task #6: Receptionist and Nurse - who may write only the
Subjective/Objective pre-entry fields - may ask ONLY for the suggestion fields
inside that scope (`RECEPTION_SUGGESTION_FIELDS`); every Doctor-only field
(physical examination, findings, Assessment, Plan, ICD-10) is a 403 for them.
This router is included BEFORE the consultations router so the literal path is
not swallowed by `GET /consultations/{consultation_id}`.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    CONSULTATION_EDIT_ROLES,
    get_db,
    require_clinic_context,
    require_soap_subjective_objective_role,
)
from app.models.user import User
from app.schemas.soap_suggestions import SoapSuggestion, SoapSuggestionsResponse
from app.services.soap_suggestion_service import DEFAULT_LIMIT, SoapSuggestionService

router = APIRouter(prefix="/consultations", tags=["consultations"])

# Suggestion fields that fall inside the Receptionist/Nurse Subjective/Objective scope.
# (physical_examination and clinical_findings are Doctor-only, as are Assessment/Plan/ICD-10.)
RECEPTION_SUGGESTION_FIELDS = {"chief_complaint"}


@router.get("/soap-suggestions", response_model=SoapSuggestionsResponse)
async def get_soap_suggestions(
    field: str = Query(..., description="One of the allowlisted SOAP/diagnosis fields."),
    q: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=20),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_soap_subjective_objective_role),
) -> SoapSuggestionsResponse:
    service = SoapSuggestionService(db)
    if not service.is_supported(field):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported suggestion field '{field}'.")
    role_name = current_user.role.name if current_user.role is not None else None
    if role_name not in CONSULTATION_EDIT_ROLES and field not in RECEPTION_SUGGESTION_FIELDS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to perform this action.")
    texts = await service.suggestions(clinic_id=clinic_id, field=field, q=q, limit=limit)
    return SoapSuggestionsResponse(field=field, suggestions=[SoapSuggestion(text=t) for t in texts])
