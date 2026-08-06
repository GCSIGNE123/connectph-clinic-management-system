"""Real file-type/size validation for every attachment/photo upload endpoint.

Every upload flow in this codebase (patient photo, doctor photo, clinic
branding assets, consultation attachments) is a presigned-URL *request*
endpoint - the actual file bytes never pass through this backend, the
client uploads directly to Supabase Storage using the returned
`upload_url`. That architecture is correct and unchanged by Phase 16 (see
docs/ARCHITECTURE.md's storage section). What was previously missing,
confirmed by reading every one of these four endpoints/services
(`app/services/{patient,doctor,clinic_settings,consultation}_service.py`)
before this phase: none of them validated the client-declared `file_name`
extension or `file_size_bytes` against any allow-list/limit before minting
a presigned URL - a client could request (and a compromised/buggy client
would receive) an upload URL for a `.exe` or a 500MB file with zero
server-side pushback. This module adds that real, enforced validation at
request time - it can't stop a client from lying and uploading a different
file to the presigned URL afterward (that's Supabase Storage's own
bucket-policy job, out of scope for an app-layer change), but it does stop
the declared metadata from getting a rubber-stamp presigned URL, and is
the correct place to add real magic-byte/content-type verification later
if a body-relaying endpoint is ever added instead of direct-to-storage
presigned uploads.
"""

from fastapi import HTTPException, status

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx"}

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB - patient/doctor photos, branding assets
MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB - consultation attachments (lab scans, referral letters, etc.)


def _extension_of(file_name: str) -> str:
    if "." not in file_name:
        return ""
    return "." + file_name.rsplit(".", 1)[-1].lower()


def validate_upload_request(
    *, file_name: str, file_size_bytes: int | None, allowed_extensions: set[str], max_size_bytes: int
) -> None:
    """Raise HTTP 400 if the declared file name/size don't pass validation.

    Called before minting a presigned upload URL for any attachment/photo
    endpoint. Both checks are best-effort against client-declared metadata
    (there is no file body at this point in a presigned-URL flow), but a
    well-behaved client (the only one this app ships) will always be
    caught here rather than silently getting an unrestricted URL.
    """
    ext = _extension_of(file_name)
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File type '{ext or '(none)'}' is not allowed. "
                f"Allowed types: {', '.join(sorted(allowed_extensions))}."
            ),
        )
    if file_size_bytes is not None and file_size_bytes > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File is too large ({file_size_bytes} bytes). "
                f"Maximum allowed size is {max_size_bytes} bytes ({max_size_bytes // (1024 * 1024)} MB)."
            ),
        )
    if file_size_bytes is not None and file_size_bytes <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File size must be greater than zero.")


def validate_image_upload(*, file_name: str, file_size_bytes: int | None) -> None:
    validate_upload_request(
        file_name=file_name,
        file_size_bytes=file_size_bytes,
        allowed_extensions=IMAGE_EXTENSIONS,
        max_size_bytes=MAX_IMAGE_SIZE_BYTES,
    )


def validate_document_upload(*, file_name: str, file_size_bytes: int | None) -> None:
    validate_upload_request(
        file_name=file_name,
        file_size_bytes=file_size_bytes,
        allowed_extensions=DOCUMENT_EXTENSIONS,
        max_size_bytes=MAX_DOCUMENT_SIZE_BYTES,
    )
