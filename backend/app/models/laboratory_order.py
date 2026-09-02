"""Laboratory Orders (Phase 10) - the laboratory department's own workflow
record layered 1:1 on top of a Phase 9 `Order` (order_category=Laboratory).
See the migration docstring (`alembic/versions/0011_laboratory_management.py`)
for the full design rationale on why this is a separate table rather than
extending `orders` in place.

Status machine: Requested -> Collected -> Processing -> Completed -> Released,
or -> Cancelled from any non-terminal state. "Released" is the
Laboratory-role-only final step that makes results visible/final to the
doctor and patient history (spec's "Enter Results -> Doctor Reviews" step
order: results are entered while status is Processing/Completed, then
explicitly Released as a distinct action - not automatically final on entry).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class LaboratoryOrderStatus(str, enum.Enum):
    REQUESTED = "Requested"
    COLLECTED = "Collected"
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    RELEASED = "Released"
    CANCELLED = "Cancelled"


LABORATORY_ORDER_STATUS_TRANSITIONS: dict[LaboratoryOrderStatus, set[LaboratoryOrderStatus]] = {
    LaboratoryOrderStatus.REQUESTED: {LaboratoryOrderStatus.COLLECTED, LaboratoryOrderStatus.CANCELLED},
    LaboratoryOrderStatus.COLLECTED: {LaboratoryOrderStatus.PROCESSING, LaboratoryOrderStatus.CANCELLED},
    LaboratoryOrderStatus.PROCESSING: {LaboratoryOrderStatus.COMPLETED, LaboratoryOrderStatus.CANCELLED},
    LaboratoryOrderStatus.COMPLETED: {LaboratoryOrderStatus.RELEASED, LaboratoryOrderStatus.CANCELLED},
    LaboratoryOrderStatus.RELEASED: set(),
    LaboratoryOrderStatus.CANCELLED: set(),
}


class LaboratoryOrder(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "laboratory_orders"

    # Nullable: a walk-in Laboratory-department queue ticket (no doctor, no
    # consultation) has no Phase 9 `orders` row to attach to - see
    # `LaboratoryService.create_from_queue_ticket`. Every doctor-placed lab
    # order still gets one via `create_from_order`, unchanged.
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, unique=True, index=True
    )
    # Client feedback (Laboratory Report printing "Order No. : -" for a
    # walk-in order): a doctor-referred lab order reads its printed order
    # number from `order.order_number` via the `order_id` FK above. A
    # walk-in order has no `Order` row to read one from, so it gets its own
    # number here instead - generated once, at creation
    # (`create_from_queue_ticket`), via the exact same `OrderNumberGenerator`
    # Phase 9 orders use (same `ORD-YYYYMMDD-NNNNNN` format/shared daily
    # counter - the two origins' numbers never collide). Always null for a
    # doctor-referred order (it has `order_id` instead); `_to_read` falls
    # back to this column only when `order_id` is unset.
    standalone_order_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    visit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratory_templates.id", ondelete="SET NULL"), nullable=True)

    test_type: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[LaboratoryOrderStatus] = mapped_column(
        SAEnum(LaboratoryOrderStatus, name="laboratory_order_status", values_callable=_enum_values),
        nullable=False, default=LaboratoryOrderStatus.REQUESTED, server_default=LaboratoryOrderStatus.REQUESTED.value,
    )

    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # `released_by` is also this order's Med Tech In Charge identity source
    # (Round 6: Laboratory Report Signatories) - the Laboratory-role user
    # who performs the release IS the Med Tech in Charge; no separate
    # "med tech" selector/concept was introduced. See
    # `LaboratoryService.release_results` for where the signatory snapshot
    # below is captured, and `med_tech_name_snapshot`/
    # `med_tech_signature_snapshot_url` for why the snapshot exists at all
    # alongside this live FK.
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # --- Round 6: Laboratory Report Signatories ---
    # Pathologist is selected as part of the release workflow (never at
    # print time) and captured with a full identity+signature snapshot at
    # that moment - the same "snapshot, never re-resolve" convention the
    # existing Doctor E-Signature feature already uses for Prescription/
    # Referral/Medical Certificate (see migration 0036 and
    # `MedicalCertificateService.issue`). A later edit to the Pathologist's
    # signature/name, or to the releasing user's own signature/name, or a
    # later change of which Pathologist is currently selected for NEW
    # releases, must never alter an already-released report - only the
    # snapshot columns are ever read for printing; `pathologist_id` is kept
    # solely for traceability/UI convenience (e.g. "who was selected"),
    # never re-joined for report rendering.
    pathologist_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pathologists.id", ondelete="SET NULL"), nullable=True
    )
    med_tech_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    med_tech_license_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Client requirement change: laboratory reports no longer carry a
    # Med Tech In Charge e-signature AT ALL - both MedTechs on a report
    # (this one and the countersigner below) manually sign the printed
    # page. `release_results()` now explicitly writes `None` here for
    # EVERY new release (never reads `User.signature_url` for this
    # purpose again) - the column itself is intentionally NOT dropped/
    # migrated away, because an order released BEFORE this change still
    # has a real value here and must keep printing that historical
    # signature unchanged on reprint (see the implementation report's
    # historical-compatibility section). `LaboratorySignatoryFooter`
    # already renders a blank line whenever this is null - no frontend
    # change was needed to produce the required "blank manual signature
    # line" for new reports.
    med_tech_signature_snapshot_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pathologist_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pathologist_license_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pathologist_signature_snapshot_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Countersigning Med Technologist (client requirement: a second,
    # MANUALLY-signing MedTech, distinct from the Med Tech In Charge above)
    # ---
    # Selected from the clinic's own Laboratory-role Users at release time
    # (see `LaboratoryService.release_results` / `GET /laboratory/
    # med-techs`), snapshotted the same "capture once, never re-resolve"
    # way as the Pathologist/Med Tech In Charge above - a later rename or
    # license change on that user's account must never alter an
    # already-released report. Deliberately has NO
    # `countersigning_med_tech_signature_snapshot_url` column and never
    # will - this person always signs the printed page by hand, so there
    # is nothing to snapshot for it. `countersigning_med_tech_id` is kept
    # for traceability only (same "UI convenience, never re-joined for
    # report rendering" convention as `pathologist_id` above) - report
    # rendering only ever reads the two snapshot columns.
    countersigning_med_tech_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    countersigning_med_tech_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    countersigning_med_tech_license_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)

    invoice_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoice_items.id", ondelete="SET NULL"), nullable=True
    )

    order: Mapped["Order | None"] = relationship()
    visit: Mapped["Visit"] = relationship()
    patient: Mapped["Patient"] = relationship()
    doctor: Mapped["Doctor"] = relationship()
    template: Mapped["LaboratoryTemplate"] = relationship()
    pathologist: Mapped["Pathologist | None"] = relationship()
    countersigning_med_tech: Mapped["User | None"] = relationship(foreign_keys=[countersigning_med_tech_id])
    results: Mapped[list["LaboratoryResult"]] = relationship(back_populates="laboratory_order", cascade="all, delete-orphan")
    attachments: Mapped[list["LaboratoryAttachment"]] = relationship(back_populates="laboratory_order", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LaboratoryOrder id={self.id} test_type={self.test_type!r} status={self.status!r}>"
