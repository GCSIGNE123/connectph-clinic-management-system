"""Laboratory Templates (Phase 10): the Administrator-configurable test
catalog that lets new tests (e.g. "HbA1c") be added entirely through the
API/UI, no code changes - see spec's "architecture must support adding new
tests without code changes". `LaboratoryTemplateParameter` rows describe
each result parameter a test produces (a CBC template has ~10 parameters).

Per-sex reference ranges were considered and intentionally simplified to a
single `normal_range` free-text field per parameter (e.g. "12.0-16.0" or
"Negative") rather than separate male/female/general columns - most PH
clinic lab slips print one range per parameter and doctors are used to
reading a combined range; splitting it out is scope creep for this phase
and can be added additively later without a breaking migration.
"""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.laboratory_result import LaboratoryResultType


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class LaboratoryTemplate(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "laboratory_templates"

    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    test_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    specimen_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    default_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    turnaround_time_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    parameters: Mapped[list["LaboratoryTemplateParameter"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="LaboratoryTemplateParameter.display_order"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LaboratoryTemplate id={self.id} test_name={self.test_name!r}>"


class LaboratoryTemplateParameter(UUIDPrimaryKeyMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "laboratory_template_parameters"

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("laboratory_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parameter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    normal_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result_type: Mapped[LaboratoryResultType] = mapped_column(
        SAEnum(LaboratoryResultType, name="laboratory_result_type_param", values_callable=_enum_values, native_enum=False),
        nullable=False, default=LaboratoryResultType.NUMERIC, server_default=LaboratoryResultType.NUMERIC.value,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    template: Mapped["LaboratoryTemplate"] = relationship(back_populates="parameters")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LaboratoryTemplateParameter id={self.id} parameter_name={self.parameter_name!r}>"
