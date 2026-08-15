"""Laboratory Management endpoints (Phase 10).

Role gating (see `core/dependencies.py`): Doctor still creates Laboratory-
category orders via the unchanged Phase 9 `/consultations/{id}/orders`
endpoint; Laboratory personnel (plus Owner/Administrator) collect/process/
enter-results/release/cancel/attach here; Reception is read-only; Doctor is
read-only on this module's endpoints (they see their own orders' progress
but don't act on the lab workflow itself).
"""

import mimetypes
import uuid
from pathlib import Path as FsPath
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_user,
    get_db,
    require_clinic_context,
    require_lab_manage_role,
    require_lab_template_manage_role,
    require_lab_view_role,
)
from app.core.upload_validation import validate_document_upload, validate_image_upload
from app.models.laboratory_attachment import LaboratoryAttachmentType
from app.models.user import User
from app.schemas.laboratory import (
    LaboratoryAttachmentRead,
    LaboratoryOrderRead,
    LaboratoryResultsSubmit,
    LaboratoryTemplateCreate,
    LaboratoryTemplateRead,
    LaboratoryTemplateUpdate,
)
from app.services.laboratory_service import LaboratoryService, attachment_to_read

router = APIRouter(prefix="/laboratory", tags=["laboratory"])

# Feature 4: real, locally-stored laboratory attachment files (result
# images, scans, PDF reports) - reuses the exact same persistent-storage
# convention `consultations.py` established in Feature 2
# (`CONSULTATION_ATTACHMENTS_UPLOAD_ROOT`): a subdirectory of `var/`, which
# lives inside the SAME existing `backend_var_data` Docker volume mounted
# at `/app/var` (see `docker/docker-compose.prod.yml`) - no second volume
# needed, since the volume covers the whole `/app/var` directory tree, not
# just `var/consultation_attachments`. Never served via an unauthenticated
# static mount - `get_attachment_file` below serves it through the same
# view-permission check as `list_attachments`.
LABORATORY_ATTACHMENTS_UPLOAD_ROOT = FsPath(__file__).resolve().parents[3] / "var" / "laboratory_attachments"


@router.get("/dashboard")
async def get_dashboard(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> dict:
    service = LaboratoryService(db)
    return await service.dashboard_stats(clinic_id=clinic_id)


@router.get("/orders", response_model=list[LaboratoryOrderRead])
async def list_orders(
    visit_id: UUID | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> list[LaboratoryOrderRead]:
    service = LaboratoryService(db)
    if visit_id is not None:
        return await service.list_for_visit(visit_id, clinic_id=clinic_id)
    return await service.list_for_dashboard(clinic_id=clinic_id)


@router.get("/orders/{laboratory_order_id}", response_model=LaboratoryOrderRead)
async def get_order(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> LaboratoryOrderRead:
    return await LaboratoryService(db).get(laboratory_order_id, clinic_id=clinic_id)


@router.post("/orders/{laboratory_order_id}/collect", response_model=LaboratoryOrderRead)
async def collect_specimen(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryOrderRead:
    return await LaboratoryService(db).collect_specimen(laboratory_order_id, clinic_id=clinic_id, actor_id=current_user.id)


@router.post("/orders/{laboratory_order_id}/start-processing", response_model=LaboratoryOrderRead)
async def start_processing(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryOrderRead:
    return await LaboratoryService(db).start_processing(laboratory_order_id, clinic_id=clinic_id, actor_id=current_user.id)


@router.post("/orders/{laboratory_order_id}/results", response_model=LaboratoryOrderRead)
async def enter_results(
    laboratory_order_id: UUID,
    payload: LaboratoryResultsSubmit,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryOrderRead:
    results = [r.model_dump() for r in payload.results]
    return await LaboratoryService(db).enter_results(laboratory_order_id, results, clinic_id=clinic_id, actor_id=current_user.id)


@router.post("/orders/{laboratory_order_id}/release", response_model=LaboratoryOrderRead)
async def release_results(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryOrderRead:
    return await LaboratoryService(db).release_results(laboratory_order_id, clinic_id=clinic_id, actor_id=current_user.id)


@router.post("/orders/{laboratory_order_id}/cancel", response_model=LaboratoryOrderRead)
async def cancel_order(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryOrderRead:
    return await LaboratoryService(db).cancel_order(laboratory_order_id, clinic_id=clinic_id, actor_id=current_user.id)


@router.post("/orders/{laboratory_order_id}/attachments", response_model=LaboratoryAttachmentRead)
async def add_attachment(
    laboratory_order_id: UUID,
    attachment_type: LaboratoryAttachmentType = Form(default=LaboratoryAttachmentType.IMAGE),
    file: UploadFile = File(...),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryAttachmentRead:
    """Feature 4: real upload - relays real file bytes and writes them to
    local disk, the same fix Feature 2 applied to consultation attachments
    (see that endpoint's docstring for why the old presigned-URL-stub
    pattern never actually worked on this app's real deployment target).
    Defaults to `Image` (the primary ask: attaching the clinic's actual
    laboratory result image), validated with the same image allow-list/
    size-limit used for consultation Clinical Images; a non-Image type
    (e.g. a scanned PDF report) uses the broader document allow-list,
    mirroring `consultations.py::upload_attachment`'s same conditional."""
    service = LaboratoryService(db)
    await service.get(laboratory_order_id, clinic_id=clinic_id)  # 404s early if the order doesn't exist/isn't in this clinic

    file_name = file.filename or "attachment"
    content = await file.read()
    if attachment_type == LaboratoryAttachmentType.IMAGE:
        validate_image_upload(file_name=file_name, file_size_bytes=len(content))
    else:
        validate_document_upload(file_name=file_name, file_size_bytes=len(content))
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")

    ext = FsPath(file_name).suffix.lower()
    stored_filename = f"{uuid.uuid4().hex}{ext}"
    order_dir = LABORATORY_ATTACHMENTS_UPLOAD_ROOT / str(clinic_id) / str(laboratory_order_id)
    order_dir.mkdir(parents=True, exist_ok=True)
    (order_dir / stored_filename).write_bytes(content)

    attachment = await service.add_attachment_record(
        laboratory_order_id, clinic_id=clinic_id, actor_id=current_user.id, attachment_type=attachment_type,
        file_name=file_name, stored_filename=stored_filename, file_size_bytes=len(content),
    )
    return attachment_to_read(attachment)


@router.get("/orders/{laboratory_order_id}/attachments", response_model=list[LaboratoryAttachmentRead])
async def list_attachments(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> list[LaboratoryAttachmentRead]:
    rows = await LaboratoryService(db).list_attachments(laboratory_order_id, clinic_id=clinic_id)
    return [attachment_to_read(a) for a in rows]


@router.get("/orders/{laboratory_order_id}/attachments/{attachment_id}/file")
async def get_attachment_file(
    laboratory_order_id: UUID,
    attachment_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> FileResponse:
    """Same authorization as `list_attachments` (lab-view role + this
    specific order's own tenant check) - a laboratory result image is
    never reachable by anyone not already authorized to view that order.
    Not a public/unauthenticated static mount - mirrors
    `consultations.py::get_attachment_file` exactly."""
    service = LaboratoryService(db)
    attachment = await service.get_attachment(laboratory_order_id, attachment_id, clinic_id=clinic_id)
    file_path = LABORATORY_ATTACHMENTS_UPLOAD_ROOT / str(clinic_id) / str(laboratory_order_id) / attachment.file_url
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    media_type, _ = mimetypes.guess_type(attachment.file_name)
    return FileResponse(file_path, media_type=media_type or "application/octet-stream", filename=attachment.file_name)


# --- Templates ---

@router.get("/templates", response_model=list[LaboratoryTemplateRead])
async def list_templates(
    active_only: bool = False,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> list[LaboratoryTemplateRead]:
    return await LaboratoryService(db).list_templates(clinic_id=clinic_id, active_only=active_only)


@router.post("/templates", response_model=LaboratoryTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: LaboratoryTemplateCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_template_manage_role),
) -> LaboratoryTemplateRead:
    data = payload.model_dump()
    data["parameters"] = [p for p in data["parameters"]]
    return await LaboratoryService(db).create_template(data, clinic_id=clinic_id)


@router.patch("/templates/{template_id}", response_model=LaboratoryTemplateRead)
async def update_template(
    template_id: UUID,
    payload: LaboratoryTemplateUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_template_manage_role),
) -> LaboratoryTemplateRead:
    return await LaboratoryService(db).update_template(template_id, payload.model_dump(exclude_unset=True), clinic_id=clinic_id)


@router.post("/templates/seed-defaults", response_model=list[LaboratoryTemplateRead])
async def seed_default_templates(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_template_manage_role),
) -> list[LaboratoryTemplateRead]:
    """Feature 3 starter templates (CBC, Urinalysis structure - no
    reference ranges) - same opt-in pattern as `POST /services/seed-
    defaults`/`POST /departments/seed-defaults`, not auto-run."""
    return await LaboratoryService(db).seed_default_templates(clinic_id=clinic_id, actor_id=current_user.id)


# --- Visit / Patient laboratory history (mounted under their own path prefixes) ---

visit_router = APIRouter(tags=["laboratory"])


@visit_router.get("/visits/{visit_id}/laboratory", response_model=list[LaboratoryOrderRead])
async def get_visit_laboratory(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> list[LaboratoryOrderRead]:
    return await LaboratoryService(db).list_for_visit(visit_id, clinic_id=clinic_id)


@visit_router.get("/patients/{patient_id}/laboratory", response_model=list[LaboratoryOrderRead])
async def get_patient_laboratory(
    patient_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> list[LaboratoryOrderRead]:
    return await LaboratoryService(db).list_for_patient(patient_id, clinic_id=clinic_id)
