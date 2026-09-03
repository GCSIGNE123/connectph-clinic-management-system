"""Writes `backend/deploy_info.json` - generated, gitignored deployment
metadata (Git commit + deploy timestamp), regenerated on every
`deploy/windows/update_server.bat` run.

Deliberately separate from `backend/.env` (see `app/core/deploy_info.py`'s
module docstring for the full rationale) - this file is build/deploy
metadata, never application configuration, and contains no secrets. Safe to
delete or regenerate at any time; its absence just means `/health` and
`/system/status` report `git_commit: null` instead of a real SHA.

Usage (run from `backend/`, using the same venv the app runs in - matches
`backup_and_prune.py`'s own invocation convention):

    python scripts/write_deploy_info.py --commit <full-git-sha>

`update_server.bat` calls this once per run, after any required service
restarts have already succeeded and just before the final health check -
passing the freshly-updated `git rev-parse HEAD`. This script never calls
git itself, so it has no opinion about *which* commit is "deployed"; it
only records whatever commit it's told, exactly once, at that point.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

# backend/scripts/write_deploy_info.py -> backend/deploy_info.json
_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "deploy_info.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit", required=True, help="Full (or short) Git commit SHA that was just deployed."
    )
    args = parser.parse_args()

    commit = args.commit.strip().lower()
    if not _SHA_RE.match(commit):
        print(f"[ERROR] '{args.commit}' does not look like a Git commit SHA - refusing to write")
        print("        deploy_info.json. Pass the exact output of `git rev-parse HEAD`.")
        return 1

    info = {
        "git_commit": commit,
        "git_commit_short": commit[:7],
        "deployed_at": datetime.now(UTC).isoformat(),
    }
    _OUTPUT_PATH.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {_OUTPUT_PATH}: {info}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
