"""Pathologist model - clinic master data for Laboratory Report signatories.

A Pathologist is deliberately NOT a `User`/login account (per product
decision - see the Round 6 signatories feature investigation): pathologists
are selected from a clinic-configured list at Laboratory result release
time, the same way a Laboratory template or a Doctor record is master data,
not something that logs in. If a clinic's pathologist ever needs their own
authenticated login in the future, that is a separate, additive extension -
this table stays the source of truth for name/license/signature/active
state either way, mirroring `Doctor`'s minimal signature-relevant shape
(see `doctor.py`) without duplicating a person/account structure.
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Pathologist(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "pathologists"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    license_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    signature_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Pathologist id={self.id} name={self.name!r}>"
