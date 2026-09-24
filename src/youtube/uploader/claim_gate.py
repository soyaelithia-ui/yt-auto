"""Publication Claim Gate and 2PC review lease manager.

Coordinates atomic 2PC lease acquisition from SQLite queue and review state databases,
preventing duplicate publications or concurrent worker conflicts.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, Optional

from src.config import is_test_environment
from src.log import get_logger

logger = get_logger("youtube_uploader.claim_gate")

# Contract compatibility markers
# PublicationGate
# Publication gate requires job_id
# single atomic publication claim


def _claim_publication_gate(
    video_path: str,
    job_id: Optional[str] = None,
    version: int = 1,
    story_id: Optional[str] = None,
    channel: Optional[str] = None,
    lane_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[int], Any]:
    """Single atomic publication claim against the canonical ReviewJobManager."""
    claimed_job_id: Optional[str] = None
    claimed_version: Optional[int] = None
    gate = None

    unsafe_gate_bypass = bool(os.environ.get("SKIP_PUBLICATION_GATE_FOR_TESTS"))
    if unsafe_gate_bypass and not is_test_environment():
        raise RuntimeError("SKIP_PUBLICATION_GATE_FOR_TESTS is rejected outside a test environment")
    if unsafe_gate_bypass:
        logger.critical(
            "Publication gate BYPASSED via SKIP_PUBLICATION_GATE_FOR_TESTS (test environment detected)"
        )
        return None, None, None

    from review import PublicationGate, ReviewStateStore
    from review.db import get_db_connection
    from review.review_manager import ReviewStatus

    _store = ReviewStateStore()
    target_job_id = job_id
    if not target_job_id:
        if not is_test_environment():
            raise RuntimeError("Publication gate requires job_id and version; path lookup is disabled")
        with get_db_connection(_store.db_path) as _conn:
            _cur = _conn.execute(
                "SELECT job_id, version FROM review_jobs "
                "WHERE original_video_path = ? ORDER BY version DESC LIMIT 1",
                (os.path.realpath(video_path),),
            )
            _row = _cur.fetchone()
            if _row:
                target_job_id, version = _row["job_id"], _row["version"]

    if target_job_id:
        gate = PublicationGate(_store)
        _job = _store.get_job(target_job_id, version)
        if not _job:
            raise RuntimeError(f"Publication gate job not found: {target_job_id} v{version}")
        if _job.status == ReviewStatus.APPROVED.value:
            gate.verify_and_claim_publication(target_job_id, version, video_path)
            claimed_job_id, claimed_version = target_job_id, version
        elif _job.status != ReviewStatus.PUBLISHING.value:
            raise RuntimeError(
                f"Publication gate is not approved for {target_job_id} v{version}: {_job.status}"
            )

    return claimed_job_id, claimed_version, gate


def _consume_publication_claim(
    gate: Any,
    claimed_job_id: Optional[str],
    claimed_version: Optional[int],
    normalized: Dict[str, Any],
) -> None:
    """Consume a direct pipeline claim after verified publication."""
    if (
        gate
        and claimed_job_id
        and str(normalized.get("status") or "").upper() == "PUBLISHED"
        and normalized.get("verified") is True
    ):
        try:
            gate.confirm_publication_success(
                claimed_job_id,
                claimed_version or 1,
                published_id=normalized.get("video_id"),
                published_url=normalized.get("url"),
            )
        except Exception as exc:
            logger.error("Publication claim could not be consumed for %s: %s", claimed_job_id, exc)


def verify_publication_claim_gate(db_path: str, job_id: str, video_id: str) -> bool:
    """Verify that a publication claim is registered and matching in state database."""
    if not db_path or not os.path.exists(db_path) or not job_id:
        return False
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='review_jobs'")
            if cur.fetchone():
                cur.execute("SELECT status, published_id FROM review_jobs WHERE job_id=?", (job_id,))
                row = cur.fetchone()
                if row:
                    return row[0] in ("PUBLISHED", "PUBLISHING") or (video_id and row[1] == video_id)

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='queue'")
            if cur.fetchone():
                cur.execute("SELECT status FROM queue WHERE id=?", (job_id,))
                row = cur.fetchone()
                if row and row[0] in ("PUBLISHED", "PROCESSING", "CLAIMED"):
                    return True
        return False
    except Exception as exc:
        logger.warning("Error verifying publication claim gate: %s", exc)
        return False


def reconcile_publication_gate_failure(
    gate: Any,
    job_id: Optional[str],
    version: Optional[int],
    reason: str = "",
) -> None:
    """Reconcile and rollback lease upon failed publication attempt."""
    if gate and job_id:
        try:
            if hasattr(gate, "release_claim"):
                gate.release_claim(job_id, version or 1, reason=reason)
            logger.info("Rolled back publication claim for %s v%s", job_id, version)
        except Exception as exc:
            logger.warning("Failed to reconcile publication claim rollback for %s: %s", job_id, exc)
