"""PlatformConfig model - simple key/value platform settings store.

Real CRUD, but deliberately NOT wired to any real email/SMS/AI/storage
provider integration in this phase - configuration-value storage only.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PlatformConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_config"

    config_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    config_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_admin_users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PlatformConfig key={self.config_key!r}>"
