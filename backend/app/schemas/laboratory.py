"""Pydantic schemas for Laboratory Management (Phase 10)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.laboratory_order import LaboratoryOrderStatus
from app.models.laboratory_result import LaboratoryInterpretation, LaboratoryResultType
from app.models.patient import Gender


# --- Templates ---

class LaboratoryTemplateParameterCreate(BaseModel):
    parameter_name: str = Field(min_length=1, max_length=255)
    unit: str | None = Field(default=None, max_length=50)
    normal_range: str | None = Field(default=None, max_length=100)
    result_type: LaboratoryResultType = LaboratoryResultType.NUMERIC
    display_order: int = 0
    # Feature 3: structured, optional - see laboratory_template.py's module
    # docstring. Numeric parameters use range_low/range_high; qualitative
    # (Text) parameters use expected_normal_text. Left unset (the default
    # for every existing template), auto-interpretation never activates
    # for that parameter.
    range_low: Decimal | None = None
    range_high: Decimal | None = None
    expected_normal_text: str | None = Field(default=None, max_length=100)
    # Phase 2A: additive/optional - see laboratory_template.py's module
    # docstring. `options` holds a Categorical choice list or a Microscopy
    # sub-field definition; `requires_site` flags a per-entry specimen site
    # (e.g. "KOH Mount per site"). Left unset, every existing Numeric/Text
    # parameter is unaffected.
    options: list[Any] | None = None
    requires_site: bool = False
    # Phase 4A: additive/optional generic grouping label (e.g. "Physical
    # Examination") - see laboratory_template.py's module docstring. Null
    # for every existing CBC/Blood Typing parameter and any template with
    # no natural sections.
    section: str | None = Field(default=None, max_length=100)


class LaboratoryTemplateParameterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parameter_name: str
    unit: str | None = None
    normal_range: str | None = None
    result_type: LaboratoryResultType
    display_order: int
    range_low: Decimal | None = None
    range_high: Decimal | None = None
    expected_normal_text: str | None = None
    options: list[Any] | None = None
    requires_site: bool = False
    section: str | None = None


class LaboratoryTemplateCreate(BaseModel):
    test_name: str = Field(min_length=1, max_length=255)
    test_category: str | None = Field(default=None, max_length=100)
    specimen_type: str | None = Field(default=None, max_length=100)
    default_price: Decimal = Decimal("0")
    turnaround_time_hours: int | None = None
    is_active: bool = True
    parameters: list[LaboratoryTemplateParameterCreate] = Field(default_factory=list)


class LaboratoryTemplateUpdate(BaseModel):
    test_name: str | None = Field(default=None, min_length=1, max_length=255)
    test_category: str | None = Field(default=None, max_length=100)
    specimen_type: str | None = Field(default=None, max_length=100)
    default_price: Decimal | None = None
    turnaround_time_hours: int | None = None
    is_active: bool | None = None
    parameters: list[LaboratoryTemplateParameterCreate] | None = None


class LaboratoryTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_name: str
    test_category: str | None = None
    specimen_type: str | None = None
    default_price: Decimal
    turnaround_time_hours: int | None = None
    is_active: bool
    parameters: list[LaboratoryTemplateParameterRead] = Field(default_factory=list)
    created_at: datetime


# --- Results ---

class LaboratoryResultInput(BaseModel):
    parameter_name: str = Field(min_length=1, max_length=255)
    result_type: LaboratoryResultType = LaboratoryResultType.NUMERIC
    numeric_value: Decimal | None = None
    text_value: str | None = None
    normal_range: str | None = Field(default=None, max_length=100)
    units: str | None = Field(default=None, max_length=50)
    interpretation: LaboratoryInterpretation | None = None
    remarks: str | None = None
    # Feature 3: range_low/range_high are persisted on LaboratoryResult
    # (denormalized from the template parameter, same pattern as
    # normal_range/units above). expected_normal_text is NOT persisted -
    # it's only used transiently, server-side, to compute `interpretation`
    # for qualitative (Text) results when the client leaves interpretation
    # unset - see LaboratoryService.enter_results.
    range_low: Decimal | None = None
    range_high: Decimal | None = None
    expected_normal_text: str | None = Field(default=None, max_length=100)
    # Phase 2A: additive/optional. `site` is only meaningful for a parameter
    # with `requires_site=True`; `structured_value` carries Categorical/
    # Microscopy kind-specific fields. numeric_value/text_value stay the
    # storage for Numeric/Text/Titer, unchanged.
    site: str | None = Field(default=None, max_length=100)
    structured_value: dict[str, Any] | None = None


class LaboratoryResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parameter_name: str
    result_type: LaboratoryResultType
    numeric_value: Decimal | None = None
    text_value: str | None = None
    normal_range: str | None = None
    units: str | None = None
    interpretation: LaboratoryInterpretation | None = None
    remarks: str | None = None
    range_low: Decimal | None = None
    range_high: Decimal | None = None
    entered_by: UUID | None = None
    entered_at: datetime | None = None
    site: str | None = None
    structured_value: dict[str, Any] | None = None


class LaboratoryResultsSubmit(BaseModel):
    results: list[LaboratoryResultInput] = Field(min_length=1)
    # Phase 4I: optional optimistic-concurrency guard - the client echoes
    # back the `updated_at` it last saw on `GET .../orders/{id}` (see
    # `LaboratoryOrderRead.updated_at`). `upsert_results` is a full
    # replace-all of the submitted result set (Phase 2A design, unchanged),
    # so two technicians editing the same order from stale form snapshots
    # could otherwise have the second save silently discard the first
    # save's changes (a classic lost-update race) - see
    # `LaboratoryService.enter_results`'s conflict check. Left unset
    # (`None`), the check is skipped entirely - existing callers (and any
    # untemplated/ad-hoc submission flow) are byte-for-byte unaffected.
    expected_updated_at: datetime | None = None


# --- Attachments ---
# Feature 4: real multipart upload (Form + File), same reasoning as
# `ConsultationAttachment`'s Feature 2 fix - no JSON "Create" schema, since
# the request body is `multipart/form-data`, not JSON. See
# `api/v1/laboratory.py::add_attachment`.

class LaboratoryAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attachment_type: str
    file_name: str
    file_url: str
    file_size_bytes: int | None = None
    uploaded_by: UUID | None = None
    created_at: datetime


# --- Orders ---

class LaboratoryOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # None for a walk-in Laboratory queue ticket with no linked Order - see
    # `LaboratoryService.create_from_queue_ticket`.
    order_id: UUID | None = None
    order_number: str | None = None
    visit_id: UUID
    visit_number: str | None = None
    # Reception Queue ticket number for this order's visit (e.g. "L003"),
    # via the existing Visit.queue relationship - None for orders whose
    # visit has no linked queue ticket (e.g. legacy/direct-visit data).
    queue_number: str | None = None
    patient_id: UUID
    patient_name: str | None = None
    doctor_id: UUID | None = None
    doctor_name: str | None = None
    template_id: UUID | None = None
    # Feature 3: the linked template's full definition (including
    # parameters with their configured ranges) - lets the frontend
    # pre-populate Result Entry rows from the template in a single fetch,
    # instead of a second round-trip. None when no template is linked
    # (test_type didn't match any active template's name), unchanged from
    # before.
    template: LaboratoryTemplateRead | None = None
    # Phase 4G: report/print header branding, additive and optional -
    # populated only by `GET /laboratory/orders/{id}` (same one-line
    # `db.get(Clinic, clinic_id)` convention `ReceiptPayload.clinic_name`
    # already uses), left unset (None) everywhere else (list/collect/
    # process/results/release responses), unchanged from before.
    clinic_name: str | None = None
    # Round 5 (report header contact info): same additive/optional,
    # `GET /laboratory/orders/{id}`-only convention as `clinic_name` above -
    # sourced from the existing `Clinic.address`/`city`/`province` and
    # `telephone`/`mobile`/`email` columns (Phase 4 clinic-settings fields),
    # no new database columns. `clinic_address` is pre-joined server-side
    # (same convention `MedicalCertificateService._to_detail` already uses
    # for `clinic_address`); `clinic_phone` prefers `telephone` and falls
    # back to `mobile` when only one is configured.
    clinic_address: str | None = None
    clinic_phone: str | None = None
    clinic_email: str | None = None
    # Round 7: the shared clinic branding logo (`Clinic.logo_url`) - same
    # additive/optional, `GET /laboratory/orders/{id}`-only convention as
    # `clinic_name` above. Live configuration, not a release-time snapshot -
    # see the Round 7 implementation report.
    clinic_logo_url: str | None = None
    # Phase 4I: exposes the existing `TimestampMixin.updated_at` column -
    # the optimistic-concurrency token `LaboratoryResultsSubmit.
    # expected_updated_at` is checked against. No new column.
    updated_at: datetime
    test_type: str
    priority: str | None = None
    status: LaboratoryOrderStatus
    scheduled_date: str | None = None
    collected_at: datetime | None = None
    collected_by: UUID | None = None
    processing_started_at: datetime | None = None
    completed_at: datetime | None = None
    released_at: datetime | None = None
    released_by: UUID | None = None
    # Round 6 (Laboratory Report Signatories): captured ONCE at
    # `release_results()` - see `laboratory_order.py`'s model docstring for
    # the full snapshot rationale. All six are `None` on an order that
    # hasn't been released yet, or was released with no Pathologist
    # selected / no signature configured at that moment (never fabricated).
    # `pathologist_id` is exposed for UI convenience only - report
    # rendering must only ever use the snapshot fields below it.
    pathologist_id: UUID | None = None
    med_tech_name_snapshot: str | None = None
    med_tech_license_snapshot: str | None = None
    med_tech_signature_snapshot_url: str | None = None
    pathologist_name_snapshot: str | None = None
    pathologist_license_snapshot: str | None = None
    pathologist_signature_snapshot_url: str | None = None
    invoice_item_id: UUID | None = None
    created_at: datetime
    results: list[LaboratoryResultRead] = Field(default_factory=list)
    attachments: list[LaboratoryAttachmentRead] = Field(default_factory=list)


class LaboratoryReleaseRequest(BaseModel):
    """Body for `POST /laboratory/orders/{id}/release`. Pathologist
    selection happens HERE (release time), never at print time - see
    `LaboratoryService.release_results`. Deliberately optional: omitting it
    preserves the pre-existing release behavior (a lab order could always
    be released with no pathologist concept at all before this feature)
    rather than introducing a new hard requirement that could block an
    otherwise-legitimate release. See the Round 6 implementation report,
    section F, for the explicit decision this reflects."""

    pathologist_id: UUID | None = None


class LaboratoryDashboardStats(BaseModel):
    pending: int
    collected: int
    processing: int
    completed_today: int
    stat_orders: int
    cancelled: int


# --- Reference Ranges (Phase 2A - Structured Result Backend Foundation) ---
# Additive companion to LaboratoryTemplateParameter's own range_low/
# range_high/expected_normal_text, which remain the default/fallback - see
# laboratory_reference_range.py's module docstring.

class LaboratoryReferenceRangeCreate(BaseModel):
    sex: Gender | None = None
    age_min_years: int | None = Field(default=None, ge=0)
    age_max_years: int | None = Field(default=None, ge=0)
    range_low: Decimal | None = None
    range_high: Decimal | None = None
    qualitative_expected: str | None = Field(default=None, max_length=100)
    # REQUIRES LABORATORY/CLINICAL VALIDATION - never populated by this
    # codebase; only ever used by interpret_result() when configured.
    critical_low: Decimal | None = None
    critical_high: Decimal | None = None
    is_active: bool = True
    effective_from: date | None = None


class LaboratoryReferenceRangeUpdate(BaseModel):
    is_active: bool | None = None


class LaboratoryReferenceRangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_parameter_id: UUID
    sex: Gender | None = None
    age_min_years: int | None = None
    age_max_years: int | None = None
    range_low: Decimal | None = None
    range_high: Decimal | None = None
    qualitative_expected: str | None = None
    critical_low: Decimal | None = None
    critical_high: Decimal | None = None
    is_active: bool
    effective_from: date | None = None
    created_by: UUID | None = None
    created_at: datetime
