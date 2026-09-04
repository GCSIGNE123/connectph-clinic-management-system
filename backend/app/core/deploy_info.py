"""Reports the Git commit actually running on this machine, so `/health` and
`/system/status` can answer "what's deployed here" - via one of two sources,
depending on which production architecture this instance is:

- **Docker Server PC** (`docker/docker-compose.prod.yml`, run via the
  repo-root `deploy.cmd`): the commit is baked into the image itself at
  `docker build` time (`ARG GIT_COMMIT` in `docker/Dockerfile.backend`,
  passed through as `${GIT_COMMIT}` by the compose file's `build.args`),
  which sets a `GIT_COMMIT` environment variable inside the running
  container. This is checked FIRST and, when present, wins outright - it is
  the more trustworthy source for this architecture, because it can only
  ever change when a NEW image is actually built and the container
  recreated from it. A plain `git pull`/`git merge --ff-only` on the host
  changes nothing this reads - which is exactly the "repository state vs.
  running deployment state" distinction the Docker updater needs: HEAD
  advancing does not, by itself, mean the running container is serving that
  commit.
- **NSSM/manual Windows-service Server PC** (`deploy/windows/
  update_server.bat`): falls back to `backend/deploy_info.json` - a
  generated, gitignored file (no secrets) written by
  `scripts/write_deploy_info.py` right before that script's health check.

Deliberately NOT part of `backend/.env` / `Settings` in either case - that
file is human-managed production configuration (secrets, `DATABASE_URL`,
`JWT_SECRET_KEY`, CORS, ...) that must survive code updates completely
unchanged. Deployment metadata (which commit, when) is the opposite: it is
*regenerated on every deploy* and contains no secrets at all, so mixing the
two would mean either (a) the updater has to edit a file it must never
touch, or (b) a human has to remember to hand-edit a config file every
release.

Neither source existing (a fresh checkout, a dev machine, or any install
that has never been through either updater yet) is a normal, expected
state, not an error - every field then reports as `None`. Nothing here ever
fabricates a commit SHA.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

# backend/app/core/deploy_info.py -> backend/deploy_info.json
_DEPLOY_INFO_PATH = Path(__file__).resolve().parent.parent.parent / "deploy_info.json"

# Captured once, at import time (i.e. process start) - used as `deployed_at`
# for the Docker/env-var source only, which has no timestamp of its own
# baked into the image. Approximates "when this running instance came up",
# which for a container recreated on every deploy is a reasonable proxy for
# "when this commit was actually deployed" - not exact to the second the
# `docker compose up -d` command was run, but never wrong by more than the
# process's own brief startup time.
_PROCESS_STARTED_AT = datetime.now(UTC).isoformat()

# Dockerfile.backend's `ARG GIT_COMMIT=unknown` default - treated the same
# as "not set at all" (an image built without `--build-arg GIT_COMMIT=...`,
# e.g. a plain local `docker build`), so it correctly falls through to the
# file-based source instead of reporting the literal string "unknown".
_UNSET_SENTINEL = "unknown"


def get_deploy_info() -> dict[str, str | None]:
    """Returns `{"git_commit": ..., "git_commit_short": ..., "deployed_at": ...}`.
    Checks the `GIT_COMMIT` environment variable first (Docker architecture);
    falls back to `deploy_info.json` (NSSM architecture) when that's unset
    or still the Dockerfile's `unknown` placeholder. Never raises and never
    blocks `/health`/`/system/status` from responding just because
    deployment metadata happens to be absent from both sources."""
    env_commit = os.environ.get("GIT_COMMIT", "").strip().lower()
    if env_commit and env_commit != _UNSET_SENTINEL:
        return {
            "git_commit": env_commit,
            "git_commit_short": env_commit[:7],
            "deployed_at": _PROCESS_STARTED_AT,
        }

    try:
        data = json.loads(_DEPLOY_INFO_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        data = {}
    return {
        "git_commit": data.get("git_commit"),
        "git_commit_short": data.get("git_commit_short"),
        "deployed_at": data.get("deployed_at"),
    }
