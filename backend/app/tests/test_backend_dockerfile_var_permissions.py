"""Guards the fix for a real production bug: on a fresh `backend_var_data`
named volume (docker-compose.prod.yml), the backend container failed with
`PermissionError: [Errno 13] Permission denied: '/app/var/...'` on startup.

Root cause: `var/` is excluded from the Docker build context (see
`backend/.dockerignore`), so `/app/var` didn't exist in the built image.
Docker only copies a mount path's existing ownership into a fresh, empty
named volume on first mount if that path already exists in the image -
without it, Docker creates the mount point itself as root:root, and the
non-root `app` runtime user (Dockerfile.backend) can't write to it.

This can't be verified by actually building/running the image here (no
Docker in this environment - see repo-wide precedent of Docker-dependent
checks being validated on a real Docker host instead), so this is a
static guard against the exact regression: `/app/var` must be created
*before* the ownership is fixed, and that chown must run *before* `USER
app` drops root - if either ordering breaks, the same PermissionError
returns on the next fresh volume.
"""

from pathlib import Path

DOCKERFILE_BACKEND = Path(__file__).resolve().parents[3] / "docker" / "Dockerfile.backend"


def _runtime_stage_lines() -> list[str]:
    content = DOCKERFILE_BACKEND.read_text(encoding="utf-8")
    # Only the runtime stage matters here - the builder stage never runs
    # as the `app` user and never touches /app/var.
    runtime_stage = content.split("FROM python:3.12-slim AS runtime", 1)[1]
    return runtime_stage.splitlines()


def test_dockerfile_backend_exists():
    assert DOCKERFILE_BACKEND.is_file(), f"Expected {DOCKERFILE_BACKEND} to exist"


def test_app_var_is_created_before_ownership_is_fixed():
    lines = _runtime_stage_lines()
    mkdir_idx = next((i for i, line in enumerate(lines) if "mkdir -p /app/var" in line), None)
    chown_idx = next((i for i, line in enumerate(lines) if line.strip().startswith("RUN") and "chown" in line and "/app" in line), None)

    assert mkdir_idx is not None, "Dockerfile.backend must create /app/var before it can be chowned"
    assert chown_idx is not None, "Dockerfile.backend must chown /app (including /app/var) to the app user"
    # Same RUN instruction (mkdir && chown) or mkdir strictly earlier - either
    # way, mkdir must not come after the chown that's supposed to cover it.
    assert mkdir_idx <= chown_idx, (
        "mkdir -p /app/var must happen at or before the chown -R app:app /app "
        "step, or /app/var won't be included in that ownership fix"
    )


def test_ownership_fix_happens_before_dropping_root():
    lines = _runtime_stage_lines()
    chown_idx = next((i for i, line in enumerate(lines) if line.strip().startswith("RUN") and "chown" in line and "/app" in line), None)
    user_app_idx = next((i for i, line in enumerate(lines) if line.strip() == "USER app"), None)

    assert chown_idx is not None, "Dockerfile.backend must chown /app to the app user"
    assert user_app_idx is not None, "Dockerfile.backend must switch to the non-root app user"
    assert chown_idx < user_app_idx, (
        "chown -R app:app /app must run while still root (before USER app) - "
        "chowning as the already-unprivileged app user would fail"
    )


def test_runtime_user_is_still_non_root():
    """Requirement: preserve the non-root runtime user - this fix must not
    reintroduce running the app as root."""
    lines = _runtime_stage_lines()
    assert any(line.strip() == "USER app" for line in lines), "Backend must still run as the non-root 'app' user"
