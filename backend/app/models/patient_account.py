"""Patient Portal auth model (Phase 18).

Patients are a THIRD, structurally separate class of principal - not a
clinic staff `User` (app/models/user.py) and not a `PlatformAdminUser`
(Phase 15, app/models/platform_admin_user.py). Following the Phase 15
precedent ("a genuinely separate auth model, not a bolt-on"), this is a new
one-to-one `PatientAccount` table linked by `patient_id`, rather than adding
password columns directly onto the shared `Patient` master record - the
`Patient` model is written/read by clinic staff constantly (registration,
demographics editing) and mixing login-credential columns into that
high-churn table would blur "clinic-managed demographic data" with
"patient-managed login credential data" (different write-paths, different
threat models, different audit requirements). A patient may exist for years
with zero portal usage (walk-in only clinics), so the account row being
optional/nullable-linked (not every Patient has one) also fits better as a
separate table than as nullable columns bolted onto every patient row.

The JWT this issues carries a distinct `"type": "patient_access"` /
`"patient_refresh"` claim (see `app/core/patient_security.py`), and only the
new `get_current_patient` FastAPI dependency (`app/core/dependencies.py`)
accepts it. `get_current_user` (clinic staff) and `get_current_platform_admin`
(Phase 15) do not, and a patient token is rejected by both.

`auth_method` is a plain string column (not yet an enum with more members)
documenting the only implemented method today ("password"); OTP and social
login are architecture notes only for this phase, per spec - future values
would be e.g. "otp_sms", "otp_email", "google", "facebook".
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class PatientAccount(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    """One-to-one login-credential record for a `Patient`.

    `clinic_id` (via TenantMixin) is denormalized from `patient_id` for
    query convenience (matches the pattern used throughout this codebase,
    e.g. `Prescription.patient_id` alongside `Prescription.branch_id`) and
    is always kept in sync with `Patient.clinic_id` - a patient account can
    never point at a different clinic than its own patient record.
    """

    __tablename__ = "patient_accounts"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    # Login identifiers. Both are optional at the DB level (a clinic-created
    # Patient may only have a mobile number, no email) but at least one of
    # email/mobile_number must be present with a password to log in -
    # enforced in `PatientAuthService`, not the DB, since `Patient.email` is
    # already nullable upstream.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_method: Mapped[str] = mapped_column(String(30), nullable=False, default="password", server_default="password")

    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    patient: Mapped["Patient"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PatientAccount id={self.id} patient_id={self.patient_id}>"


class PatientPasswordResetToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single-use, expiring reset token for the patient portal.

    Deliberately a separate table from `PasswordResetToken` (clinic-staff
    reset flow, keyed to `users.id`) - a token minted here is looked up only
    against `patient_accounts`, so it can never be replayed against the
    staff reset endpoint even if the raw token value were somehow guessed,
    because `AuthService.reset_password` queries the *other* table.
    """

    __tablename__ = "patient_password_reset_tokens"

    patient_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PatientPasswordResetToken id={self.id} patient_account_id={self.patient_account_id}>"


class NotificationChannel(str, enum.Enum):
    """Architecture note: only in-app delivery is wired for this phase.
    EMAIL/SMS/PUSH are documented future values with no delivery
    integration - `PatientNotificationPreference` records the patient's
    *preference* so the UI/API shape is stable when real delivery is added."""

    IN_APP = "InApp"
    EMAIL = "Email"
    SMS = "SMS"
    PUSH = "Push"


class PatientNotificationPreference(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    """A simple settings row per patient - no real push/email delivery wiring,
    per phase scope ("architecture placeholder is acceptable")."""

    __tablename__ = "patient_notification_preferences"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    appointment_reminders: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    lab_result_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    billing_notices: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    clinic_announcements: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    # Documented future channel selection; not wired to any real delivery.
    preferred_channel: Mapped[NotificationChannel] = mapped_column(
        SAEnum(NotificationChannel, name="patient_notification_channel", values_callable=_enum_values),
        nullable=False,
        default=NotificationChannel.IN_APP,
        server_default=NotificationChannel.IN_APP.value,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PatientNotificationPreference patient_id={self.patient_id}>"


class PatientNotificationType(str, enum.Enum):
    APPOINTMENT_REMINDER = "AppointmentReminder"
    LAB_RESULT_RELEASED = "LabResultReleased"
    BILLING_NOTICE = "BillingNotice"
    CLINIC_ANNOUNCEMENT = "ClinicAnnouncement"


class PatientNotification(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    """Read-only, in-app notification feed row. No background job/scheduler
    generates these proactively in this phase (none existed for an
    equivalent feature before Phase 18) - rows are created synchronously by
    the relevant service action (e.g. lab release, payment recorded)."""

    __tablename__ = "patient_notifications"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[PatientNotificationType] = mapped_column(
        SAEnum(PatientNotificationType, name="patient_notification_type", values_callable=_enum_values),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PatientNotification id={self.id} type={self.notification_type!r}>"
