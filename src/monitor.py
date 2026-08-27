"""Read-mostly operational monitor with lease-aware recovery only."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from src.config import DEFAULT_DB_PATH
from src.core.domain import JobStatus
from src.core.repository import QueueRepository, connect


def _service_state() -> str:
    result = subprocess.run(
        ["systemctl", "is-active", "youtube_daemon.service"],
        shell=False,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def diagnose_failure_and_fix(db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Recover only expired leases; never restart services or reset global rows."""
    repository = QueueRepository(db_path)
    repository.initialize()
    recovered = repository.recover_expired_leases()
    with connect(db_path, read_only=True) as conn:
        failures = [
            dict(row)
            for row in conn.execute(
                """
                SELECT story_id, channel, status, failure_code, error_msg, updated_at
                FROM stories
                WHERE status IN (?, ?, ?, ?, ?, ?)
                ORDER BY updated_at DESC LIMIT 50
                """,
                (
                    JobStatus.RETRYABLE_FAILED.value,
                    JobStatus.PERMANENT_FAILED.value,
                    JobStatus.UPLOAD_UNCONFIRMED.value,
                    JobStatus.WAITING_LLM_QUOTA.value,
                    JobStatus.WAITING_IMAGE_QUOTA.value,
                    JobStatus.WAITING_YOUTUBE_LIMIT.value,
                ),
            )
        ]
        controls = [
            dict(row)
            for row in conn.execute(
                "SELECT channel, paused, reason, updated_at FROM channel_controls"
            )
        ]
    return {
        "actions_taken": (
            [f"Recovered {recovered} expired lease(s)"] if recovered else []
        ),
        "recovered_expired_leases": recovered,
        "service": _service_state(),
        "failures": failures,
        "controls": controls,
        "manual_intervention_required": any(
            row.get("failure_code") in {"authentication", "manual_intervention"}
            or row.get("status")
            in {
                JobStatus.PERMANENT_FAILED.value,
                JobStatus.UPLOAD_UNCONFIRMED.value,
            }
            for row in failures
        ),
    }


def run_publication_check(db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Return only independently verified publication records."""
    diagnostic = diagnose_failure_and_fix(db_path)
    with connect(db_path, read_only=True) as conn:
        publications = [
            dict(row)
            for row in conn.execute(
                """
                SELECT story_id, video_id, url, channel, visibility, title,
                       thumbnail_confirmed, verified_at
                FROM publications ORDER BY verified_at DESC LIMIT 20
                """
            )
        ]
    return {
        "status": (
            "MANUAL_INTERVENTION_REQUIRED"
            if diagnostic["manual_intervention_required"]
            else "OK"
        ),
        "published": bool(publications),
        "published_videos": publications,
        "diagnostic": diagnostic,
    }


def generate_suspension_report(
    suspensions: list[dict[str, Any]],
    *,
    output_path: str | Path | None = None,
) -> str:
    """Compatibility helper that writes a sanitized manual-action report."""
    target = Path(output_path or "logs/reports/manual_intervention.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"manual_intervention": suspensions}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(target)


if __name__ == "__main__":
    print(json.dumps(run_publication_check(), ensure_ascii=False, indent=2))
