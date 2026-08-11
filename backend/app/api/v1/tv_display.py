"""TV Display administration + public display endpoints (Phase 13).

Two distinct security models on this one router:

- `/tv-displays*` and `/announcements/*` - standard JWT-protected,
  Owner/Administrator-only (reusing `require_config_manage_role`, the same
  gate used for every other "clinic configuration" module) for
  create/update/delete; broader `require_config_view_role` for read/preview.
- `GET /public/tv-display/{public_slug}` - **deliberately bypasses
  `get_current_user`/`oauth2_scheme` entirely**. It takes no
  Authorization header at all. Its only "credential" is the unguessable
  `public_slug` itself (192 bits of randomness, see
  `models/tv_display_config.py::generate_public_slug`), which
  `TvDisplayConfigRepository.get_by_public_slug` resolves to exactly one
  clinic's display scope - there is no clinic_id parameter on this route,
  so there is no way to widen the query to another tenant's data. This is
  safe to expose without auth because the only data it returns is queue
  number + patient initials + doctor name + room + clinic/branch name +
  announcements - never full patient names, contact info, or medical data
  (see docs/API.md for the explicit callout).

`POST /tv-info-content/{content_id}/image` is, like `migration.py`'s
`/batches/{id}/upload`, one of the few endpoints in this codebase that
actually relays real file bytes rather than minting a presigned-URL stub
(see `app/core/upload_validation.py`'s docstring for why every other
upload flow is a stub) - appropriate here because the TV Display has a
hard "no cloud dependency, works fully offline" requirement, so a
Supabase-presigned-URL flow would not work for it anyway. Files are
written to local disk under `var/tv_info_content_images/` (same
`var/`-relative-to-backend-root convention as `migration.py`'s
`UPLOAD_ROOT`) and served back out via a `StaticFiles` mount at
`/media/tv-info-content` (see `app/main.py`) - unauthenticated, same as
the public TV display endpoint itself, since these are clinic-facing
marketing/informational images meant to be shown on an unauthenticated
public TV, never sensitive data.
"""

import uuid
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    User,
    get_current_user,
    get_db,
    require_config_manage_role,
    require_config_view_role,
)
from app.core.upload_validation import IMAGE_EXTENSIONS, MAX_IMAGE_SIZE_BYTES
from app.schemas.tv_display import (
    TvAnnouncementCreate,
    TvAnnouncementRead,
    TvAnnouncementUpdate,
    TvDisplayConfigCreate,
    TvDisplayConfigRead,
    TvDisplayConfigUpdate,
    TvDisplayData,
    TvInfoContentCreate,
    TvInfoContentRead,
    TvInfoContentUpdate,
)
from app.services.tv_display_service import TvDisplayService

router = APIRouter(prefix="/tv-displays", tags=["tv-display"])
info_content_router = APIRouter(prefix="/tv-info-content", tags=["tv-display"])

# Mirrors migration.py's UPLOAD_ROOT convention: parents[3] from
# app/api/v1/tv_display.py resolves to the backend project root.
TV_INFO_CONTENT_UPLOAD_ROOT = Path(__file__).resolve().parents[3] / "var" / "tv_info_content_images"
TV_INFO_CONTENT_MEDIA_URL_PREFIX = "/media/tv-info-content"
public_router = APIRouter(tags=["tv-display-public"])


@router.post("", response_model=TvDisplayConfigRead, status_code=status.HTTP_201_CREATED)
async def create_tv_display(
    payload: TvDisplayConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> TvDisplayConfigRead:
    service = TvDisplayService(db)
    config = await service.create_config(current_user.clinic_id, payload, current_user.id)
    return TvDisplayConfigRead.model_validate(config)


@router.get("", response_model=list[TvDisplayConfigRead])
async def list_tv_displays(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_view_role),
) -> list[TvDisplayConfigRead]:
    service = TvDisplayService(db)
    configs = await service.list_configs(current_user.clinic_id)
    return [TvDisplayConfigRead.model_validate(c) for c in configs]


@router.get("/{tv_display_id}", response_model=TvDisplayConfigRead)
async def get_tv_display(
    tv_display_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_view_role),
) -> TvDisplayConfigRead:
    service = TvDisplayService(db)
    config = await service.get_config(current_user.clinic_id, tv_display_id)
    return TvDisplayConfigRead.model_validate(config)


@router.get("/{tv_display_id}/preview", response_model=TvDisplayData)
async def preview_tv_display(
    tv_display_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_view_role),
) -> TvDisplayData:
    """Authenticated equivalent of the public snapshot endpoint - lets staff
    preview/use a private-mode display without needing its public slug."""
    service = TvDisplayService(db)
    return await service.get_display_data_for_authenticated_user(current_user.clinic_id, tv_display_id)


@router.patch("/{tv_display_id}", response_model=TvDisplayConfigRead)
async def update_tv_display(
    tv_display_id: UUID,
    payload: TvDisplayConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> TvDisplayConfigRead:
    service = TvDisplayService(db)
    config = await service.update_config(current_user.clinic_id, tv_display_id, payload, current_user.id)
    return TvDisplayConfigRead.model_validate(config)


@router.delete("/{tv_display_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tv_display(
    tv_display_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = TvDisplayService(db)
    await service.delete_config(current_user.clinic_id, tv_display_id, current_user.id)


@router.post("/{tv_display_id}/announcements", response_model=TvAnnouncementRead, status_code=status.HTTP_201_CREATED)
async def create_announcement(
    tv_display_id: UUID,
    payload: TvAnnouncementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> TvAnnouncementRead:
    payload = payload.model_copy(update={"tv_display_config_id": tv_display_id})
    service = TvDisplayService(db)
    announcement = await service.create_announcement(current_user.clinic_id, tv_display_id, payload, current_user.id)
    return TvAnnouncementRead.model_validate(announcement)


@router.get("/{tv_display_id}/announcements", response_model=list[TvAnnouncementRead])
async def list_announcements(
    tv_display_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_view_role),
) -> list[TvAnnouncementRead]:
    service = TvDisplayService(db)
    announcements = await service.list_announcements(current_user.clinic_id, tv_display_id)
    return [TvAnnouncementRead.model_validate(a) for a in announcements]


announcements_router = APIRouter(prefix="/announcements", tags=["tv-display"])


@announcements_router.patch("/{announcement_id}", response_model=TvAnnouncementRead)
async def update_announcement(
    announcement_id: UUID,
    payload: TvAnnouncementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> TvAnnouncementRead:
    service = TvDisplayService(db)
    announcement = await service.update_announcement(current_user.clinic_id, announcement_id, payload, current_user.id)
    return TvAnnouncementRead.model_validate(announcement)


@announcements_router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_announcement(
    announcement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = TvDisplayService(db)
    await service.delete_announcement(current_user.clinic_id, announcement_id, current_user.id)


@info_content_router.post("", response_model=TvInfoContentRead, status_code=status.HTTP_201_CREATED)
async def create_info_content(
    payload: TvInfoContentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> TvInfoContentRead:
    service = TvDisplayService(db)
    content = await service.create_info_content(current_user.clinic_id, payload, current_user.id)
    return TvInfoContentRead.model_validate(content)


@info_content_router.get("", response_model=list[TvInfoContentRead])
async def list_info_content(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_view_role),
) -> list[TvInfoContentRead]:
    service = TvDisplayService(db)
    content = await service.list_info_content(current_user.clinic_id)
    return [TvInfoContentRead.model_validate(c) for c in content]


@info_content_router.patch("/{content_id}", response_model=TvInfoContentRead)
async def update_info_content(
    content_id: UUID,
    payload: TvInfoContentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> TvInfoContentRead:
    service = TvDisplayService(db)
    content = await service.update_info_content(current_user.clinic_id, content_id, payload, current_user.id)
    return TvInfoContentRead.model_validate(content)


@info_content_router.delete("/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_info_content(
    content_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> None:
    service = TvDisplayService(db)
    await service.delete_info_content(current_user.clinic_id, content_id, current_user.id)


@info_content_router.post("/{content_id}/image", response_model=TvInfoContentRead)
async def upload_info_content_image(
    content_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> TvInfoContentRead:
    service = TvDisplayService(db)
    await service.get_info_content_or_404(current_user.clinic_id, content_id)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext or '(none)'}' is not allowed. Allowed types: {', '.join(sorted(IMAGE_EXTENSIONS))}.",
        )
    content_bytes = await file.read()
    if len(content_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File is too large. Maximum allowed size is {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB.",
        )
    if len(content_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")

    clinic_dir = TV_INFO_CONTENT_UPLOAD_ROOT / str(current_user.clinic_id)
    clinic_dir.mkdir(parents=True, exist_ok=True)
    # Remove any previously-uploaded image for this item first, in case a
    # re-upload changes extension (e.g. .png -> .jpg) - otherwise the old
    # file would linger as an orphan alongside the new one.
    for existing in clinic_dir.glob(f"{content_id}-*"):
        existing.unlink(missing_ok=True)
    # Random suffix, not just `{content_id}{ext}`, so a stale cached copy of
    # the previous image (same URL) isn't served to an already-open kiosk
    # tab that hasn't re-fetched `TvDisplayData` yet.
    filename = f"{content_id}-{uuid.uuid4().hex[:8]}{ext}"
    (clinic_dir / filename).write_bytes(content_bytes)

    image_url = f"{TV_INFO_CONTENT_MEDIA_URL_PREFIX}/{current_user.clinic_id}/{filename}"
    content = await service.set_info_content_image(current_user.clinic_id, content_id, image_url, current_user.id)
    return TvInfoContentRead.model_validate(content)


@info_content_router.delete("/{content_id}/image", response_model=TvInfoContentRead)
async def delete_info_content_image(
    content_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_config_manage_role),
) -> TvInfoContentRead:
    service = TvDisplayService(db)
    existing = await service.get_info_content_or_404(current_user.clinic_id, content_id)
    if existing.image_url and existing.image_url.startswith(TV_INFO_CONTENT_MEDIA_URL_PREFIX):
        clinic_dir = TV_INFO_CONTENT_UPLOAD_ROOT / str(current_user.clinic_id)
        for existing_file in clinic_dir.glob(f"{content_id}-*"):
            existing_file.unlink(missing_ok=True)
    content = await service.set_info_content_image(current_user.clinic_id, content_id, None, current_user.id)
    return TvInfoContentRead.model_validate(content)


@public_router.get("/public/tv-display/{public_slug}", response_model=TvDisplayData)
async def public_tv_display(public_slug: str, db: AsyncSession = Depends(get_db)) -> TvDisplayData:
    """No authentication of any kind - not even an optional bearer token is
    read here. See module docstring for the full security-model rationale."""
    service = TvDisplayService(db)
    return await service.get_public_display_data(public_slug)
