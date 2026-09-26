"""Unit tests for the review bundle and the vision QA agent (offline)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.observability.bundle import build_review_bundle


def _seed_run(tmp_path: Path, *, with_video: bool = True) -> tuple[str, Path]:
    """Create a migrated DB + minimal run/artifact rows; return (run_id, video_path)."""
    from src.core.repository import QueueRepository

    repo = QueueRepository(str(tmp_path / "queue.db"))
    repo.initialize()
    run_id = "runtest0001"
    conn = None
    from src.core.repository import connect

    with connect(repo.db_path) as db:
        db.execute(
            """
            INSERT INTO runs(run_id, channel, story_id, mode, status, owner,
                             started_at, heartbeat_at)
            VALUES (?, 'horror', NULL, 'publish', 'RETRYABLE_FAILED', 'tester',
                    '2026-08-22T00:00:00+00:00', '2026-08-22T00:00:00+00:00')
            """,
            (run_id,),
        )
        video_path = tmp_path / "video.mp4"
        if with_video:
            video_path.write_bytes(b"\x00\x01\x02fake")  # not a real mp4
        db.execute(
            """
            INSERT INTO artifacts(run_id, kind, local_path, size_bytes, created_at)
            VALUES (?, 'video', ?, 3, '2026-08-22T00:00:00+00:00')
            """,
            (run_id, str(video_path)),
        )
        db.commit()
    return run_id, video_path


def test_bundle_contains_diagnostics_and_degrades_without_ffmpeg(tmp_path):
    run_id, video_path = _seed_run(tmp_path, with_video=True)
    bundle_root = tmp_path / "bundles"
    summary = build_review_bundle(
        run_id,
        db_path=str(tmp_path / "queue.db"),
        bundle_root=bundle_root,
        include_contact_sheet=True,
    )
    assert Path(summary["bundle_dir"]).is_dir()
    diagnostics = json.loads(
        Path(summary["diagnostics_json"]).read_text(encoding="utf-8")
    )
    # run row recovered
    assert diagnostics["run"]["run_id"] == run_id
    assert diagnostics["run"]["status"] == "RETRYABLE_FAILED"
    # artifact path resolved
    assert diagnostics["video_path"] == str(video_path)
    # contact sheet fails on fake video → recorded as collection error, not fatal
    sources = {err["source"] for err in (diagnostics["bundle"]["collection_errors"] or [])}
    assert "contact_sheet" in sources
    assert summary["contact_sheet"] is None


def test_bundle_works_without_any_video(tmp_path):
    run_id, _ = _seed_run(tmp_path, with_video=False)
    summary = build_review_bundle(
        run_id,
        db_path=str(tmp_path / "queue.db"),
        bundle_root=tmp_path / "bundles",
        include_contact_sheet=False,
    )
    assert summary["video_path"] is None
    diagnostics = json.loads(
        Path(summary["diagnostics_json"]).read_text(encoding="utf-8")
    )
    assert diagnostics["run"]["run_id"] == run_id


def test_bundle_for_unknown_run_still_writes_diagnostics(tmp_path):
    summary = build_review_bundle(
        "ghost_run",
        db_path=str(tmp_path / "missing.db"),
        bundle_root=tmp_path / "bundles",
        include_contact_sheet=False,
    )
    assert Path(summary["diagnostics_json"]).is_file()


def test_agent_schema_and_role():
    from src.agents.video_qa import SYSTEM_INSTRUCTIONS, VIDEO_QA_SCHEMA

    assert VIDEO_QA_SCHEMA["required"] == ["overall_pass", "findings"]
    finding_schema = VIDEO_QA_SCHEMA["properties"]["findings"]["items"]
    categories = set(finding_schema["properties"]["category"]["enum"])
    assert categories == {"visual", "subtitles", "audio", "pacing", "other"}
    severities = set(finding_schema["properties"]["severity"]["enum"])
    assert severities == {"low", "medium", "high"}
    assert "JSON" in SYSTEM_INSTRUCTIONS


def test_run_video_qa_persists_findings(tmp_path, monkeypatch):
    """Offline: mock the harness call; verify event persistence + report."""
    from src.agents.video_qa import run_video_qa
    from src.core.repository import QueueRepository

    run_id, _ = _seed_run(tmp_path)
    repo = QueueRepository(str(tmp_path / "queue.db"))
    monkeypatch.setenv("YT_EVENTS_LOG_PATH", str(tmp_path / "m.jsonl"))

    canned = {
        "result": "SUCCESS",
        "output": {
            "structured_output": {
                "overall_pass": False,
                "summary": "subtítulos cortados al final",
                "findings": [
                    {
                        "severity": "high",
                        "category": "subtitles",
                        "timecode": "00:00:50",
                        "description": "última línea fuera de pantalla",
                        "suggested_fix": "reducir font size",
                    }
                ],
            }
        },
    }

    class FakeAgent:
        def run(self, task, task_result_path=None):
            path = Path(task_result_path or "task_result.json")
            path.write_text(json.dumps(canned), encoding="utf-8")
            return path

    report = run_video_qa(
        run_id,
        db_path=repo.db_path,
        bundle_root=tmp_path / "bundles",
        agent=FakeAgent(),
    )
    assert report["overall_pass"] is False
    assert len(report["findings"]) == 1
    events = repo.query_system_events(event_type="agent_finding")
    assert len(events) == 1
    details = json.loads(events[0]["details_json"])
    assert details["overall_pass"] is False
    assert details["findings"][0]["severity"] == "high"
