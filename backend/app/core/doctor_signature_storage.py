"""Shared path resolution for doctor e-signature files on local disk.

Real, locally-stored PNG signature images - a sensitive doctor credential,
so NEVER served via an unauthenticated static mount. Same clinic-then-
entity-scoped directory convention as `CONSULTATION_ATTACHMENTS_UPLOAD_ROOT`
(see `api/v1/consultations.py`). Factored out of `api/v1/doctors.py` so the
Prescription/Referral/Medical Certificate print-signature file endpoints
(which serve a SNAPSHOTTED filename, not necessarily the doctor's current
one - see migration 0036) can resolve the same path without a circular
import between API routers.
"""

from pathlib import Path
from uuid import UUID

DOCTOR_SIGNATURES_UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "var" / "doctor_signatures"


def resolve_doctor_signature_path(clinic_id: UUID, doctor_id: UUID, stored_filename: str) -> Path:
    return DOCTOR_SIGNATURES_UPLOAD_ROOT / str(clinic_id) / str(doctor_id) / stored_filename
