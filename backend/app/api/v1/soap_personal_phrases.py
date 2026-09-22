"""Doctor-specific SOAP phrases: "My Phrases" (favorites) and "Recently used" (Task #2 enhancement).

Siblings of `GET /consultations/soap-suggestions` (which is unchanged). Every
endpoint requires the Doctor role AND a linked `doctor_id`, and is scoped to that
Doctor within their clinic - Receptionist, Nurse, Owner, Administrator and every
other role get a 403, and one Doctor can never read or change another's phrases.
Responses carry phrase text only (never a patient, consultation or visit id).
Included BEFORE the consultations router so the literal paths are not swallowed by
`/consultations/{consultation_id}/...`.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_clinic_context, require_roles
from app.models.user import User
from app.schemas.soap_suggestions import (
    SoapFavoriteCreate,
    SoapFavoriteRead,
    SoapPersonalSuggestionsResponse,
    SoapSuggestion,
)
from app.services.soap_personal_phrase_service import (
    DEFAULT_RECENT_LIMIT,
    MAX_FAVORITES_PER_FIELD,
    FavoritesLimitReached,
    InvalidPhrase,
    SoapPersonalPhraseService,
    is_supported_field,
)

router = APIRouter(prefix="/consultations", tags=["consultations"])

_require_doctor = require_roles("Doctor")


async def require_doctor_with_profile(current_user: User = Depends(_require_doctor)) -> User:
    """Doctor role + a linked Doctor record; the personal phrases belong to that Doctor."""
    if current_user.doctor_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to perform this action.")
    return current_user


def _require_supported(field: str) -> None:
    if not is_supported_field(field):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported suggestion field '{field}'.")


@router.get("/soap-suggestions/personal", response_model=SoapPersonalSuggestionsResponse)
async def get_personal_suggestions(
    field: str = Query(..., description="One of the allowlisted SOAP/diagnosis fields."),
    q: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=DEFAULT_RECENT_LIMIT, ge=1, le=20, description="Maximum 'recent' phrases."),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_with_profile),
) -> SoapPersonalSuggestionsResponse:
    _require_supported(field)
    favorites, recent = await SoapPersonalPhraseService(db).personal(
        clinic_id=clinic_id, doctor_id=current_user.doctor_id, field=field, q=q, limit=limit
    )
    return SoapPersonalSuggestionsResponse(
        field=field,
        favorites=[SoapSuggestion(text=t) for t in favorites],
        recent=[SoapSuggestion(text=t) for t in recent],
    )


@router.post("/soap-suggestions/favorites", response_model=SoapFavoriteRead)
async def add_favorite_phrase(
    payload: SoapFavoriteCreate,
    response: Response,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_with_profile),
) -> SoapFavoriteRead:
    """201 when a new phrase is saved; 200 (same body) when it was already a favorite."""
    _require_supported(payload.field)
    try:
        text, created = await SoapPersonalPhraseService(db).add_favorite(
            clinic_id=clinic_id, doctor_id=current_user.doctor_id, field=payload.field, text=payload.text
        )
    except InvalidPhrase as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except FavoritesLimitReached as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You can save up to {MAX_FAVORITES_PER_FIELD} phrases per field. Remove one first.",
        ) from exc
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return SoapFavoriteRead(field=payload.field, text=text)


@router.delete("/soap-suggestions/favorites", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite_phrase(
    field: str = Query(...),
    text: str = Query(..., max_length=200),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_with_profile),
) -> Response:
    _require_supported(field)
    removed = await SoapPersonalPhraseService(db).remove_favorite(
        clinic_id=clinic_id, doctor_id=current_user.doctor_id, field=field, text=text
    )
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phrase not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
