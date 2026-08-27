"""Review bundle builder: package a finished run for vision-based analysis.

A bundle lives in ``output/agent_review/<run_id>/`` and contains everything
an agent (or a human operator) needs to inspect a video without touching the
production database again:

* ``contact_sheet.jpg`` + ``sheet_frames/`` — visual samples every 5 s.
* ``diagnostics.json`` — run status, error diagnostics, production metrics,
  provider attempts and artifact paths.
* the final video path reference (never copied, to save disk).

Bundles are intentionally self-contained plain files so coding agents
(Antigravity/OpenCode/Codex/Hermes sessions) can read them during debugging.
This module is a standalone diagnostic tool: nothing in the production flow
invokes it automatically.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.repository import QueueRepository
from src.log import get_logger

logger = get_logger("review_bundle")

DEFAULT_BUNDLE_ROOT = Path(
    os.environ.get("YT_AGENT_REVIEW_ROOT")
    or (Path(__file__).resolve().parent.parent.parent / "output" / "agent_review")
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_review_bundle(
    run_id: str,
    *,
    db_path: str | None = None,
    video_path: str | None = None,
    bundle_root: str | os.PathLike | None = None,
    include_contact_sheet: bool = True,
) -> dict[str, Any]:
    """Assemble the review bundle for ``run_id``; returns a summary dict.

    Degrades gracefully: missing metrics/artifacts become ``null`` fields and
    a failed contact sheet only disables that section — the diagnostics are
    always written so debugging can proceed.
    """
    from src.config import DEFAULT_DB_PATH as _DEFAULT_DB

    database = str(db_path or _DEFAULT_DB)
    repository = QueueRepository(database)
    root = Path(bundle_root) if bundle_root else DEFAULT_BUNDLE_ROOT
    bundle_dir = root / str(run_id)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    run_row: dict[str, Any] | None = None
    with_errors: list[dict[str, Any]] = []
    try:
        import sqlite3

        from src.core.repository import connect

        with connect(database, read_only=True) as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (str(run_id),)
            ).fetchone()
            run_row = dict(row) if row else None
            attempts = [
                dict(item)
                for item in conn.execute(
                    """
                    SELECT provider, operation, attempt_no, outcome,
                           error_code, error_detail
                    FROM provider_attempts WHERE run_id = ? ORDER BY attempt_id DESC LIMIT 20
                    """,
                    (str(run_id),),
                )
            ]
            artifacts = [
                dict(item)
                for item in conn.execute(
                    """
                    SELECT kind, local_path, remote_provider, remote_id, size_bytes
                    FROM artifacts WHERE run_id = ?
                    """,
                    (str(run_id),),
                )
            ]
    except Exception as exc:
        with_errors.append({"source": "runs", "error": str(exc)})
        attempts, artifacts = [], []

    metrics: dict[str, Any] | None = None
    try:
        metrics = repository.get_production_metrics(str(run_id))
    except Exception as exc:
        with_errors.append({"source": "production_metrics", "error": str(exc)})

    error_payload: dict[str, Any] | None = None
    if run_row and run_row.get("error_detail"):
        error_payload = {
            "error_code": run_row.get("error_code"),
            "error_detail": run_row.get("error_detail"),
        }

    video_ref: str | None = video_path
    if not video_ref:
        try:
            artifact = repository.get_run_artifact(str(run_id), "video")
            if artifact and artifact.get("local_path"):
                candidate = Path(str(artifact["local_path"]))
                video_ref = str(candidate) if candidate.exists() else None
                if candidate.exists() is False:
                    with_errors.append(
                        {"source": "artifacts", "error": f"video no existe: {candidate}"}
                    )
        except Exception as exc:
            with_errors.append({"source": "artifacts", "error": str(exc)})

    contact_sheet: str | None = None
    frame_count = 0
    if include_contact_sheet and video_ref:
        try:
            from src.verification.sheets import ContactSheetGenerator

            candidate = ContactSheetGenerator().generate_contact_sheet(
                video_ref, bundle_dir
            )
            candidate_path = Path(candidate) if candidate else None
            if candidate_path and candidate_path.is_file() and candidate_path.stat().st_size > 0:
                contact_sheet = str(candidate_path)
                frames_dir = bundle_dir / "sheet_frames"
                frame_count = (
                    len(list(frames_dir.glob("frame_*.jpg")))
                    if frames_dir.is_dir()
                    else 0
                )
            else:
                with_errors.append(
                    {"source": "contact_sheet", "error": "el generador no produjo archivo"}
                )
        except Exception as exc:
            with_errors.append({"source": "contact_sheet", "error": str(exc)})
            logger.warning("contact sheet omitida para %s: %s", run_id, exc)

    diagnostics = {
        "generated_at": _utc_now(),
        "run_id": str(run_id),
        "run": run_row,
        "last_error": error_payload,
        "production_metrics": metrics,
        "provider_attempts": attempts,
        "artifacts": artifacts,
        "video_path": video_ref,
        "bundle": {
            "dir": str(bundle_dir),
            "contact_sheet": contact_sheet,
            "frame_count": frame_count,
            "collection_errors": with_errors or None,
        },
    }
    diagnostics_path = bundle_dir / "diagnostics.json"
    diagnostics_path.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    logger.info(
        "Bundle de revisión listo: %s (frames=%d, errores_recoleccion=%d)",
        bundle_dir,
        frame_count,
        len(with_errors),
    )
    return {
        "bundle_dir": str(bundle_dir),
        "diagnostics_json": str(diagnostics_path),
        "contact_sheet": contact_sheet,
        "frame_count": frame_count,
        "video_path": video_ref,
        "collection_errors": with_errors,
    }


def clean_agent_review_bundles(*, max_age_hours: int | None = None) -> dict[str, int]:
    """Delete bundles older than the retention window; returns report."""
    now = datetime.now(timezone.utc).timestamp()
    hours = (
        max_age_hours
        if max_age_hours is not None
        else int(os.environ.get("YT_AGENT_REVIEW_RETENTION_HOURS", "72"))
    )
    removed = 0
    freed_files = 0
    if not DEFAULT_BUNDLE_ROOT.is_dir():
        return {"removed_bundles": 0, "freed_files": 0}
    cutoff = now - max(0, hours) * 3600
    for entry in DEFAULT_BUNDLE_ROOT.iterdir():
        if not entry.is_dir() or entry.is_symlink():
            continue
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
            freed_files += sum(1 for f in entry.rglob("*") if f.is_file())
            shutil.rmtree(entry)
            removed += 1
        except OSError as exc:
            logger.debug("No se pudo eliminar bundle %s: %s", entry, exc)
    return {"removed_bundles": removed, "freed_files": freed_files}
