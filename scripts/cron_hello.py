"""Heartbeat cron — connects to the DB, writes a pipeline_runs row, exits.

Proves the GitHub Actions -> Postgres plumbing works end-to-end before any
LLM logic is layered on top. Invoked daily from .github/workflows/daily.yml.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from polyforecast.storage.base import session_scope
from polyforecast.storage.models import PipelineRun, PipelineRunStatus


def main() -> int:
    started = datetime.now(UTC)
    with session_scope() as session:
        run = PipelineRun(
            started_at=started,
            finished_at=datetime.now(UTC),
            status=PipelineRunStatus.SUCCESS,
            git_sha=os.environ.get("GITHUB_SHA"),
            notes="hello-world heartbeat",
        )
        session.add(run)
    print(f"pipeline_run inserted; started_at={started.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
