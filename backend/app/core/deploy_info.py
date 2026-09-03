"""Reads generated, gitignored deployment metadata (`backend/deploy_info.json`)
so `/health` and `/system/status` can report the Git commit actually running
on this machine.

Deliberately NOT part of `backend/.env` / `Settings` - that file is
human-managed production configuration (secrets, `DATABASE_URL`,
`JWT_SECRET_KEY`, CORS, ...) that must survive code updates completely
unchanged. Deployment metadata (which commit, when) is the opposite: it is
*regenerated on every deploy* and contains no secrets at all, so mixing the
two would mean either (a) the update script has to edit a file it must never
touch, or (b) a human has to remember to hand-edit a config file every
release. `deploy_info.json` avoids both - it's written by
`scripts/write_deploy_info.py` (invoked from `deploy/windows/update_server.bat`)
and is otherwise never read by anything except this module.

The file simply not existing (a fresh checkout, a dev machine, or any
install that has never run `update_server.bat` yet) is a normal, expected
state, not an error - every field then reports as `None`. Nothing here ever
fabricates a commit SHA.
"""

import json
from pathlib import Path

# backend/app/core/deploy_info.py -> backend/deploy_info.json
_DEPLOY_INFO_PATH = Path(__file__).resolve().parent.parent.parent / "deploy_info.json"


def get_deploy_info() -> dict[str, str | None]:
    """Returns `{"git_commit": ..., "git_commit_short": ..., "deployed_at": ...}`,
    each `None` if `deploy_info.json` is missing, unreadable, or malformed -
    this must never raise and never block `/health`/`/system/status` from
    responding just because deployment metadata happens to be absent."""
    try:
        data = json.loads(_DEPLOY_INFO_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        data = {}
    return {
        "git_commit": data.get("git_commit"),
        "git_commit_short": data.get("git_commit_short"),
        "deployed_at": data.get("deployed_at"),
    }
