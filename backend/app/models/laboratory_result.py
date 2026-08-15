"""Laboratory Results (Phase 10) - one row per result parameter. A single
lab order (e.g. CBC) produces multiple parameter rows (Hemoglobin, WBC
Count, ...), each independently numeric- or text-valued.

Feature 3 (Automatic Interpretation): `range_low`/`range_high` below are
copied from the matched `LaboratoryTemplateParameter` at submission time
(same denormalization pattern already used for `normal_range`/`units` on
this same model) - so a result's interpretation basis stays stable and
reviewable even if the template's ranges are edited later. Both nullable;
an existing result row (or a newly-entered one with no configured range)
simply has both null, and `interpretation` stays whatever was explicitly
set (manual) or null (never guessed) - see
`app/services/laboratory_interpretation.py`."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class LaboratoryResultType(str, enum.Enum):
    NUMERIC = "Numeric"
    TEXT = "Text"


class LaboratoryInterpretation(str, enum.Enum):
    NORMAL = "Normal"
    LOW = "Low"
    HIGH = "High"
    ABNORMAL = "Abnormal"


class LaboratoryResult(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "laboratory_results"

    laboratory_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("laboratory_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parameter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    result_type: Mapped[LaboratoryResultType] = mapped_column(
        SAEnum(LaboratoryResultType, name="laboratory_result_type_result", values_callable=_enum_values, native_enum=False),
        nullable=False, default=LaboratoryResultType.NUMERIC, server_default=LaboratoryResultType.NUMERIC.value,
    )
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normal_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    units: Mapped[str | None] = mapped_column(String(50), nullable=True)
    range_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    range_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    interpretation: Mapped[LaboratoryInterpretation | None] = mapped_column(
        SAEnum(LaboratoryInterpretation, name="laboratory_interpretation", values_callable=_enum_values, native_enum=False),
        nullable=True,
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    entered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    laboratory_order: Mapped["LaboratoryOrder"] = relationship(back_populates="results")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LaboratoryResult id={self.id} parameter_name={self.parameter_name!r}>"
