"""Shared path resolution for e-signature files on local disk.

Real, locally-stored PNG signature images - a sensitive credential, so
NEVER served via an unauthenticated static mount. Same clinic-then-
entity-scoped directory convention as `CONSULTATION_ATTACHMENTS_UPLOAD_ROOT`
(see `api/v1/consultations.py`). Factored out of `api/v1/doctors.py` so the
Prescription/Referral/Medical Certificate print-signature file endpoints
(which serve a SNAPSHOTTED filename, not necessarily the doctor's current
one - see migration 0036) can resolve the same path without a circular
import between API routers.

Round 6 (Laboratory Report Signatories) generalizes this same convention -
one root directory per signatory entity type - to two more entity kinds
(Pathologist master-data records, and Laboratory-role Users acting as Med
Tech In Charge) rather than inventing a separate storage mechanism.
"""

from pathlib import Path
from uuid import UUID

_VAR_ROOT = Path(__file__).resolve().parents[2] / "var"

DOCTOR_SIGNATURES_UPLOAD_ROOT = _VAR_ROOT / "doctor_signatures"
PATHOLOGIST_SIGNATURES_UPLOAD_ROOT = _VAR_ROOT / "pathologist_signatures"
USER_SIGNATURES_UPLOAD_ROOT = _VAR_ROOT / "user_signatures"


def resolve_doctor_signature_path(clinic_id: UUID, doctor_id: UUID, stored_filename: str) -> Path:
    return DOCTOR_SIGNATURES_UPLOAD_ROOT / str(clinic_id) / str(doctor_id) / stored_filename


def resolve_pathologist_signature_path(clinic_id: UUID, pathologist_id: UUID, stored_filename: str) -> Path:
    return PATHOLOGIST_SIGNATURES_UPLOAD_ROOT / str(clinic_id) / str(pathologist_id) / stored_filename


def resolve_user_signature_path(clinic_id: UUID, user_id: UUID, stored_filename: str) -> Path:
    return USER_SIGNATURES_UPLOAD_ROOT / str(clinic_id) / str(user_id) / stored_filename
