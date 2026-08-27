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
from datetime import date
from pathlib import Path as FsPath
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_user,
    get_db,
    require_clinic_context,
    require_lab_manage_role,
    require_lab_template_manage_role,
    require_lab_view_role,
)
from app.core.doctor_signature_storage import resolve_pathologist_signature_path, resolve_user_signature_path
from app.core.upload_validation import validate_document_upload, validate_image_upload
from app.models.clinic import Clinic
from app.models.laboratory_attachment import LaboratoryAttachmentType
from app.models.user import User
from app.schemas.laboratory import (
    LaboratoryAttachmentRead,
    LaboratoryOrderRead,
    LaboratoryReferenceRangeCreate,
    LaboratoryReferenceRangeRead,
    LaboratoryReferenceRangeUpdate,
    LaboratoryReleaseRequest,
    LaboratoryResultsSubmit,
    LaboratoryTemplateCreate,
    LaboratoryTemplateRead,
    LaboratoryTemplateUpdate,
)
from app.schemas.laboratory_template_import import ImportCommitRead, ImportPreviewRead
from app.services.laboratory_service import LaboratoryService, attachment_to_read
from app.services.laboratory_template_import_export import (
    WorkbookStructureError,
    build_blank_import_workbook,
)

MAX_IMPORT_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB - generous for a template catalog spreadsheet

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
    order = await LaboratoryService(db).get(laboratory_order_id, clinic_id=clinic_id)
    # Phase 4G: report/print header branding - same one-line lookup
    # `GET /billing/invoices/{id}/receipt` already uses for `clinic_name`.
    # Only this single-order fetch populates it (the report view's data
    # source); list/action endpoints are unaffected.
    clinic = await db.get(Clinic, clinic_id)
    order.clinic_name = clinic.name if clinic else None
    # Round 5: same join convention `MedicalCertificateService._to_detail`
    # already uses for `clinic_address` - existing columns, no new ones.
    order.clinic_address = ", ".join(filter(None, [clinic.address, clinic.city, clinic.province])) or None if clinic else None
    order.clinic_phone = (clinic.telephone or clinic.mobile) if clinic else None
    order.clinic_email = clinic.email if clinic else None
    # Round 7: same shared `Clinic.logo_url` branding value the TV Display
    # header now reads (see `TvDisplayService._build_display_data`) - live
    # configuration, not snapshotted (see the Round 7 implementation
    # report's snapshot-decision section for why).
    order.clinic_logo_url = clinic.logo_url if clinic else None
    return order


@router.get("/orders/{laboratory_order_id}/med-tech-signature/file")
async def get_med_tech_signature_file(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_lab_view_role),
) -> FileResponse:
    """Serves the SNAPSHOTTED Med Tech In Charge signature captured at
    `release_results()` time, never the releasing user's current one - same
    convention as the Doctor E-Signature snapshot endpoints (migration
    0036)."""
    order = await LaboratoryService(db).get(laboratory_order_id, clinic_id=clinic_id)
    if not order.med_tech_signature_snapshot_url or not order.released_by:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This order has no Med Tech signature.")
    file_path = resolve_user_signature_path(clinic_id, order.released_by, order.med_tech_signature_snapshot_url)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signature file not found")
    return FileResponse(file_path, media_type="image/png", filename="signature.png")


@router.get("/orders/{laboratory_order_id}/pathologist-signature/file")
async def get_pathologist_signature_snapshot_file(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_lab_view_role),
) -> FileResponse:
    """Serves the SNAPSHOTTED Pathologist signature captured at
    `release_results()` time, never the Pathologist's current one."""
    order = await LaboratoryService(db).get(laboratory_order_id, clinic_id=clinic_id)
    if not order.pathologist_signature_snapshot_url or not order.pathologist_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This order has no Pathologist signature.")
    file_path = resolve_pathologist_signature_path(clinic_id, order.pathologist_id, order.pathologist_signature_snapshot_url)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signature file not found")
    return FileResponse(file_path, media_type="image/png", filename="signature.png")


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
    return await LaboratoryService(db).enter_results(
        laboratory_order_id, results, clinic_id=clinic_id, actor_id=current_user.id,
        expected_updated_at=payload.expected_updated_at,
    )


@router.post("/orders/{laboratory_order_id}/release", response_model=LaboratoryOrderRead)
async def release_results(
    laboratory_order_id: UUID,
    payload: LaboratoryReleaseRequest | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryOrderRead:
    return await LaboratoryService(db).release_results(
        laboratory_order_id, clinic_id=clinic_id, actor_id=current_user.id,
        pathologist_id=payload.pathologist_id if payload else None,
    )


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


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_template_manage_role),
) -> None:
    """Soft delete only - see `LaboratoryService.delete_template`'s
    docstring. The template row and its parameters are never physically
    removed, so every existing laboratory order/result/report that
    references this template keeps working unchanged."""
    await LaboratoryService(db).delete_template(
        template_id, clinic_id=clinic_id, actor_id=current_user.id
    )


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


# --- Import / Export (bulk Excel maintenance) ---
# Export/download-blank are read-only (same LAB_VIEW_ROLES gate as
# `list_templates` - "View users may export only if current permissions
# permit viewing configuration"). Preview/Commit both mutate-adjacent
# (Preview reads the DB to validate but writes nothing; Commit writes) so
# both use the same Administrator-only gate as create/update.

@router.get("/templates/export")
async def export_templates(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> Response:
    content = await LaboratoryService(db).export_templates_workbook(clinic_id=clinic_id)
    filename = f"laboratory-templates-{date.today().isoformat()}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/templates/import/blank")
async def download_blank_import_template(
    clinic_id: UUID = Depends(require_clinic_context),
    current_user: User = Depends(require_lab_template_manage_role),
) -> Response:
    return Response(
        content=build_blank_import_workbook(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                'attachment; filename="laboratory-templates-import-template.xlsx"'
            )
        },
    )


@router.post("/templates/import/preview", response_model=ImportPreviewRead)
async def preview_template_import(
    file: UploadFile = File(...),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_template_manage_role),
) -> ImportPreviewRead:
    """Read-only: parses + validates the uploaded workbook against this
    clinic's existing templates and returns a preview (counts, per-template
    +/~/- parameter diffs, errors, warnings). Never writes to the
    database."""
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")
    if len(content) > MAX_IMPORT_FILE_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is too large.")
    try:
        return await LaboratoryService(db).preview_import(content, clinic_id=clinic_id)
    except WorkbookStructureError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/templates/import/commit", response_model=ImportCommitRead)
async def commit_template_import(
    file: UploadFile = File(...),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_template_manage_role),
) -> ImportCommitRead:
    """Re-parses and re-validates the SAME file independently (never trusts
    a client-held preview) before writing anything. Rejects with 400 if any
    validation error exists - the same "no partial import" guarantee as the
    Preview step, now enforced server-side regardless of what the client's
    UI already showed the user."""
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")
    if len(content) > MAX_IMPORT_FILE_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is too large.")
    try:
        return await LaboratoryService(db).commit_import(
            content, clinic_id=clinic_id, actor_id=current_user.id
        )
    except WorkbookStructureError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# --- Reference Ranges (Phase 2A - Structured Result Backend Foundation) ---
# Administrator-only mutation, same role gate as template management -
# these rows configure a template parameter's demographic-specific ranges,
# not yet consumed by the live result-entry flow (foundation only).

@router.post(
    "/templates/parameters/{template_parameter_id}/reference-ranges",
    response_model=LaboratoryReferenceRangeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_reference_range(
    template_parameter_id: UUID,
    payload: LaboratoryReferenceRangeCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_template_manage_role),
) -> LaboratoryReferenceRangeRead:
    reference_range = await LaboratoryService(db).create_reference_range(
        template_parameter_id, payload.model_dump(), clinic_id=clinic_id, actor_id=current_user.id
    )
    return LaboratoryReferenceRangeRead.model_validate(reference_range, from_attributes=True)


@router.get(
    "/templates/parameters/{template_parameter_id}/reference-ranges",
    response_model=list[LaboratoryReferenceRangeRead],
)
async def list_reference_ranges(
    template_parameter_id: UUID,
    active_only: bool = False,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> list[LaboratoryReferenceRangeRead]:
    rows = await LaboratoryService(db).list_reference_ranges(
        template_parameter_id, clinic_id=clinic_id, active_only=active_only
    )
    return [LaboratoryReferenceRangeRead.model_validate(r, from_attributes=True) for r in rows]


@router.patch("/reference-ranges/{reference_range_id}", response_model=LaboratoryReferenceRangeRead)
async def update_reference_range(
    reference_range_id: UUID,
    payload: LaboratoryReferenceRangeUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_template_manage_role),
) -> LaboratoryReferenceRangeRead:
    if payload.is_active is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update.")
    reference_range = await LaboratoryService(db).set_reference_range_active(
        reference_range_id, payload.is_active, clinic_id=clinic_id, actor_id=current_user.id
    )
    return LaboratoryReferenceRangeRead.model_validate(reference_range, from_attributes=True)


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
