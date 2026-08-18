"""Doctor E-Signature: snapshot columns on doctor-issued documents.

Adds `doctor_signature_snapshot_url` (nullable `String(500)`, storing a
stored-filename reference under `var/doctor_signatures/{clinic_id}/
{doctor_id}/`, same convention as `ConsultationAttachment.file_url` - never
image bytes) to:

- `prescriptions`
- `referrals`
- `medical_certificates`

Product decision (approved): a signature is a deliberate, scoped exception
to this codebase's existing live-join convention for doctor identity on
these documents (see `MedicalCertificate`'s model docstring - PRC/PTR/name
are pulled live at print time, not stored). A signature represents what was
actually applied to a document at issue time, so it is captured once, at
issue/finalize, into these new columns and never re-resolved afterward -
replacing or removing the doctor's current signature (`doctors.signature_url`,
already an existing unused column - no migration needed for that one) must
never alter a previously-issued document's rendering.

No new table for `Doctor.signature_url` itself - it already exists
(unused) on the `doctors` table since an earlier phase.

Revision ID: 0036_doctor_signature_snapshots
Revises: 0035_medical_certificates
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_doctor_signature_snapshots"
down_revision: str | None = "0035_medical_certificates"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("prescriptions", sa.Column("doctor_signature_snapshot_url", sa.String(length=500), nullable=True))
    op.add_column("referrals", sa.Column("doctor_signature_snapshot_url", sa.String(length=500), nullable=True))
    op.add_column("medical_certificates", sa.Column("doctor_signature_snapshot_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("medical_certificates", "doctor_signature_snapshot_url")
    op.drop_column("referrals", "doctor_signature_snapshot_url")
    op.drop_column("prescriptions", "doctor_signature_snapshot_url")
