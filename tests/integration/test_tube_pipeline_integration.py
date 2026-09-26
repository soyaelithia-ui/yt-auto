"""Integration tests for El Tubo telemetry, database backup/WAL, and Stage 13 lifecycle safeguards."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from review.domain import ReviewStatus
from src.core.domain import (
    AmbiguousUploadError,
    JobStatus,
    YouTubeQuotaExceededError,
)
from src.core.profiling import PipelineProfiler
from src.core.repository import QueueRepository, backup_database, connect
from src.observability import (
    TubeCollector,
    TubeSnapshot,
    clear_run_context,
    emit_event,
)
from src.pipeline.context import PipelineContext
from src.pipeline.stages.stage_13_publish import stage_13_backup_publish


@pytest.fixture(autouse=True)
def _clean_observability_context():
    clear_run_context()
    yield
    clear_run_context()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> QueueRepository:
    db_path = tmp_path / "test_tube_integration.db"
    r = QueueRepository(db_path)
    r.initialize()
    monkeypatch.setenv("DEFAULT_DB_PATH", str(db_path))
    return r


def _build_test_pipeline_context(
    tmp_path: Path,
    repo: QueueRepository,
    story_id: str,
    run_id: str,
    owner: str = "worker-integration-1",
    directed: bool = False,
) -> PipelineContext:
    work_dir = tmp_path / "runs" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    video_path = work_dir / "rendered_output.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")
    thumbnail_path = work_dir / "thumbnail.jpg"
    thumbnail_path.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01")

    story_data = {
        "story_id": story_id,
        "channel": "horror",
        "title": "La Entidad del Pasillo",
        "content": "Caminaba a solas por el pabellón clausurado cuando la luz parpadeó...",
        "status": "in_progress",
    }
    profiler = PipelineProfiler(run_id)

    lane_mock = MagicMock()
    lane_mock.duration_min_sec = 60
    lane_mock.review_content_type = "short"
    lane_mock.qa_profile = "shorts"

    settings_mock = MagicMock()
    settings_mock.youtube_token_path = tmp_path / "fake_token.json"
    settings_mock.expected_youtube_channel_id = "UC_CANONICAL_HORROR"

    branding_mock = MagicMock()
    branding_mock.tags = ["scp", "terror", "misterio"]

    return PipelineContext(
        story=story_data,
        story_id=story_id,
        run_id=run_id,
        channel_name="horror",
        channel_key="horror",
        lane=lane_mock,
        repository=repo,
        database=str(repo.db_path),
        owner=owner,
        lease_seconds=300,
        settings=settings_mock,
        branding=branding_mock,
        profiler=profiler,
        directed=directed,
        generate_only=False,
        engine_mode="loop",
        is_loop_mode=True,
        is_multiscene_mode=False,
        subtitles_active=False,
        work_dir=work_dir,
        audio_path=work_dir / "audio.mp3",
        ass_path=work_dir / "subs.ass",
        srt_path=work_dir / "subs.srt",
        video_path=video_path,
        thumbnail_path=thumbnail_path,
        script_path=work_dir / "script.txt",
        visual_plan_path=work_dir / "plan.json",
        metadata_path=work_dir / "meta.json",
        scene_manifest_path=work_dir / "scene_manifest.json",
        spanish_title="La Entidad del Pasillo",
        youtube_title="La Entidad del Pasillo #Shorts",
        youtube_description="Historia de terror creepypasta.",
    )


def test_database_backup_and_wal_observability(repo: QueueRepository, tmp_path: Path) -> None:
    """Assert database backup emits telemetry, verifies WAL checkpoints, and reflects in TubeCollector."""
    # 1. Ensure WAL mode and generate transactions
    with connect(repo.db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.commit()

    repo.enqueue(
        story_id="src_backup_001",
        title="Backup Target Story",
        content="Story content for backup transaction test",
        url="https://reddit.com/r/nosleep/comments/backup_001",
        channel="horror",
    )

    # 2. Execute safe SQLite backup
    backup_dest = tmp_path / "backups" / "automated_backup_test.db"
    out_backup = backup_database(repo.db_path, backup_dest)
    assert out_backup.is_file()
    assert out_backup.stat().st_size > 0

    # 3. Assert database_backup_completed event in system_events
    with connect(repo.db_path, read_only=True) as conn:
        ev = conn.execute(
            """
            SELECT * FROM system_events
            WHERE event_type = 'database_backup_completed'
            ORDER BY event_id DESC LIMIT 1
            """
        ).fetchone()
        assert ev is not None
        assert ev["level"] == "INFO"
        details = json.loads(ev["details_json"])
        assert "size_bytes" in details
        assert details["size_bytes"] == out_backup.stat().st_size
        assert "duration_ms" in details
        assert details["duration_ms"] >= 0.0
        assert details["target_path"] == str(out_backup)

        # 4. Verify PRAGMA wal_checkpoint(PASSIVE) execution
        cp = conn.execute("PRAGMA wal_checkpoint(PASSIVE);").fetchone()
        assert cp is not None
        # cp returns (busy: 0 or 1, log: int, checkpointed: int)
        assert len(cp) == 3
        assert cp[0] in (0, 1)

    # 5. Verify TubeCollector database health synthesis
    collector = TubeCollector(db_path=str(repo.db_path))
    db_health = collector.sample_database_health()

    assert db_health.backup_status == "HEALTHY"
    assert db_health.last_backup_size_bytes == out_backup.stat().st_size
    assert db_health.last_backup_age_hours is not None
    assert db_health.last_backup_age_hours < 1.0
    assert db_health.applied_migration_version >= 9
    assert db_health.wal_status in ("OK", "GROWTH_WARNING")
    assert db_health.integrity_check_result == "HEALTHY"


def test_stage_13_youtube_quota_limit_transition(repo: QueueRepository, tmp_path: Path) -> None:
    """Assert Stage 13 handles YouTubeQuotaExceededError by setting WAITING_YOUTUBE_LIMIT and emitting telemetry."""
    # 1. Enqueue and claim a story with active lease
    repo.enqueue(
        story_id="story_quota_e2e_1",
        title="Exceeded Quota Story",
        content="Content for quota saturation scenario",
        url="https://reddit.com/r/nosleep/comments/quota_001",
        channel="horror",
    )
    claimed = repo.claim("horror", owner="worker-quota-1", lease_seconds=300)
    assert claimed is not None
    assert claimed["story_id"] == "story_quota_e2e_1"
    run_id = claimed["run_id"]

    ctx = _build_test_pipeline_context(
        tmp_path,
        repo,
        story_id="story_quota_e2e_1",
        run_id=run_id,
        owner="worker-quota-1",
    )

    review_job_mock = MagicMock()
    review_job_mock.status = ReviewStatus.APPROVED.value
    review_job_mock.version = 1

    # 2. Simulate YouTube API Quota Exceeded during upload
    with patch(
        "src.pipeline.stages.stage_13_publish._handle_drive_backup",
        return_value=(None, None, None),
    ), patch(
        "src.pipeline.stages.stage_13_publish._evaluate_technical_verdict",
        return_value={"approved": True, "passed": True},
    ), patch(
        "src.pipeline.stages.stage_13_publish._handle_review_gate",
        return_value=(review_job_mock, ReviewStatus.APPROVED.value, None),
    ), patch(
        "src.youtube.uploader.upload_video",
        side_effect=YouTubeQuotaExceededError("The request cannot be completed because you have exceeded your quota."),
    ):
        result = stage_13_backup_publish(ctx)

    # 3. Assert stage returned WAITING_YOUTUBE_LIMIT outcome
    assert result["status"] == JobStatus.WAITING_YOUTUBE_LIMIT.value
    assert result["story_id"] == "story_quota_e2e_1"
    assert result["channel"] == "horror"

    # 4. Assert repository story record transitioned
    story_rec = repo.get_story_record("story_quota_e2e_1")
    assert story_rec is not None
    assert story_rec.status == JobStatus.WAITING_YOUTUBE_LIMIT.value
    assert story_rec.failure_code == "youtube_quota_exceeded"
    assert "quota" in (story_rec.error_msg or "").lower()

    # 5. Assert youtube_quota_limit event logged in system_events
    with connect(repo.db_path, read_only=True) as conn:
        ev = conn.execute(
            """
            SELECT * FROM system_events
            WHERE event_type = 'youtube_quota_limit'
            ORDER BY event_id DESC LIMIT 1
            """
        ).fetchone()
        assert ev is not None
        assert ev["level"] == "WARNING"
        assert ev["channel"] == "horror"
        details = json.loads(ev["details_json"])
        assert details["reason"] == "quota_exceeded"
        assert details["estimated_units"] == 1600
        assert details["story_id"] == "story_quota_e2e_1"


def test_stage_13_upload_unconfirmed_safeguard(repo: QueueRepository, tmp_path: Path) -> None:
    """Assert ambiguous network drops trigger UPLOAD_UNCONFIRMED and prevent blind automatic retry."""
    # 1. Enqueue and claim a story in directed mode
    repo.enqueue(
        story_id="story_ambiguous_e2e_1",
        title="Ambiguous Upload Story",
        content="Content for ambiguous network dropout test",
        url="https://reddit.com/r/nosleep/comments/ambiguous_001",
        channel="horror",
    )
    claimed = repo.claim("horror", owner="worker-ambiguous-1", lease_seconds=300)
    assert claimed is not None
    run_id = claimed["run_id"]

    ctx = _build_test_pipeline_context(
        tmp_path,
        repo,
        story_id="story_ambiguous_e2e_1",
        run_id=run_id,
        owner="worker-ambiguous-1",
        directed=True,
    )

    review_job_mock = MagicMock()
    review_job_mock.status = ReviewStatus.APPROVED.value
    review_job_mock.version = 1

    # 2. Simulate connection dropout during binary transmission
    with patch(
        "src.pipeline.stages.stage_13_publish._handle_drive_backup",
        return_value=(None, None, None),
    ), patch(
        "src.pipeline.stages.stage_13_publish._evaluate_technical_verdict",
        return_value={"approved": True, "passed": True},
    ), patch(
        "src.pipeline.stages.stage_13_publish._handle_review_gate",
        return_value=(review_job_mock, ReviewStatus.APPROVED.value, None),
    ), patch(
        "src.youtube.uploader.upload_video",
        side_effect=AmbiguousUploadError("Connection reset by peer during chunk transmission"),
    ):
        result = stage_13_backup_publish(ctx)

    # 3. Assert returned status is UPLOAD_UNCONFIRMED
    assert result["status"] == JobStatus.UPLOAD_UNCONFIRMED.value
    assert result["story_id"] == "story_ambiguous_e2e_1"

    # 4. Assert repository story record transitioned
    story_rec = repo.get_story_record("story_ambiguous_e2e_1")
    assert story_rec is not None
    assert story_rec.status == JobStatus.UPLOAD_UNCONFIRMED.value

    # 5. Assert upload_unconfirmed event emitted in system_events
    with connect(repo.db_path, read_only=True) as conn:
        ev = conn.execute(
            """
            SELECT * FROM system_events
            WHERE event_type = 'upload_unconfirmed'
            ORDER BY event_id DESC LIMIT 1
            """
        ).fetchone()
        assert ev is not None
        assert ev["level"] == "ERROR"
        assert ev["channel"] == "horror"
        details = json.loads(ev["details_json"])
        assert "Ambiguous upload" in ev["message"]
        assert details["story_id"] == "story_ambiguous_e2e_1"

    # 6. Safeguard: Attempting normal claim must NOT claim an UPLOAD_UNCONFIRMED story
    subsequent_claim = repo.claim("horror", owner="worker-secondary-2", lease_seconds=300)
    assert subsequent_claim is None, "UPLOAD_UNCONFIRMED story must not be automatically re-claimed"


def test_full_tube_snapshot_integration(repo: QueueRepository, tmp_path: Path) -> None:
    """Assert TubeCollector compiles unified TubeSnapshot with realistic multi-provider telemetry."""
    # 1. Record realistic multi-provider token burn events
    repo.record_token_burn(
        provider="antigravity_pro",
        model="claude-3-7-sonnet",
        prompt_tokens=10000,
        completion_tokens=2500,
        cost_usd=0.0675,
        channel="horror",
        story_id="story-tube-full-1",
        stage="stage_2_script",
    )
    repo.record_token_burn(
        provider="gemini_rest",
        model="gemini-2.5-flash",
        prompt_tokens=5000,
        completion_tokens=1000,
        cost_usd=0.0008,
        channel="horror",
        story_id="story-tube-full-1",
        stage="stage_3_visual_plan",
    )
    repo.record_token_burn(
        provider="edge_tts",
        model="es-ES-AlvaroNeural",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=1500,
        cost_usd=0.0,
        channel="horror",
        story_id="story-tube-full-1",
        stage="stage_4_audio",
    )

    # 2. Emit operational events
    emit_event(
        "youtube_quota_limit",
        level="WARNING",
        message="Daily YouTube API quota warning",
        details={"reason": "quota_exceeded", "estimated_units": 1600, "channel": "horror"},
        channel="horror",
    )
    emit_event(
        "audio_prompt_leak",
        level="WARNING",
        message="Prompt leak intercepted: as an ai language model",
        details={"pattern": "ai_assistant", "channel": "horror"},
        channel="horror",
    )

    # 3. Perform a database backup and record publication
    repo.enqueue(
        story_id="story-tube-full-1",
        title="Tube Full Test Story",
        content="Sample script",
        url="https://reddit.com/r/nosleep/comments/full_1",
        channel="horror",
    )
    claimed = repo.claim("horror", owner="worker-tube-1", lease_seconds=300)
    assert claimed is not None
    run_id = claimed["run_id"]

    with connect(repo.db_path) as conn:
        conn.execute(
            """
            INSERT INTO publications (
                run_id, story_id, provider, video_id, url, channel, visibility, title, description, thumbnail_confirmed, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                "story-tube-full-1",
                "youtube",
                "VID_TUBE_FULL_1",
                "https://www.youtube.com/watch?v=VID_TUBE_FULL_1",
                "horror",
                "public",
                "Test Title",
                "Test Description",
                1,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()

    backup_dest = tmp_path / "backups" / "full_snapshot_backup.db"
    backup_database(repo.db_path, backup_dest)

    # 4. Measure snapshot performance (< 50ms)
    collector = TubeCollector(db_path=str(repo.db_path))
    t0 = time.perf_counter()
    snapshot = collector.compile_snapshot(channel="horror", window_hours=24)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert elapsed_ms < 50.0, f"compile_snapshot exceeded latency budget: {elapsed_ms:.2f}ms"
    assert isinstance(snapshot, TubeSnapshot)

    # 5. Verify individual subsystem metrics in snapshot
    # Host resources
    assert snapshot.host_resources.ram_rss_mib > 0
    assert snapshot.host_resources.disk_free_gib > 0
    assert snapshot.host_resources.cpu_percent >= 0.0

    # Token burn
    assert snapshot.token_burn.total_tokens >= 20000
    assert snapshot.token_burn.total_prompt_tokens >= 15000
    assert snapshot.token_burn.total_completion_tokens >= 3500
    assert snapshot.token_burn.total_cost_usd > 0.05
    assert "antigravity_pro" in snapshot.token_burn.provider_breakdown
    assert "gemini_rest" in snapshot.token_burn.provider_breakdown

    # YouTube quotas
    assert snapshot.youtube_quotas.estimated_consumed_units >= 1600
    assert snapshot.youtube_quotas.daily_budget_units == 10000
    assert snapshot.youtube_quotas.quota_status in ("WARNING", "EXHAUSTED")

    # Database health
    assert snapshot.database_health.backup_status == "HEALTHY"
    assert snapshot.database_health.applied_migration_version >= 9
    assert snapshot.database_health.integrity_check_result == "HEALTHY"

    # Incidents
    assert len(snapshot.recent_incidents) >= 2
    incident_types = [inc.get("event_type") for inc in snapshot.recent_incidents]
    assert "youtube_quota_limit" in incident_types
    assert "audio_prompt_leak" in incident_types

    # Serialization contract
    payload = snapshot.to_dict()
    assert isinstance(payload, dict)
    serialized = json.dumps(payload)
    assert len(serialized) > 0
