"""
Adversarial Stress & Runtime Decoupling Test Suite for Milestone 2.
Author: Challenger 2 (Empirical Challenger)
Validates:
- Failure handling across pipeline stages (Stages 1, 3, 5, 6, 9, 10, 11, 12).
- Fail-closed contracts and automatic lease release in QueueRepository upon failure.
- Mid-pipeline lease loss detection via require_heartbeat / LeaseOwnershipError.
- generate_only=True clean halt at RENDERED without remote review/publish calls.
- Zero-Browser policy enforcement: AST scan and subprocess execution monitoring.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.config import SETTINGS
from src.core.domain import CanonicalChannel, JobStatus, LeaseOwnershipError
from src.core.providers import CapabilityUnavailable, QuotaError
from src.core.repository import QueueRepository, connect
from src.media.loop_engine import CatalogAssetNotFoundError
from src.pipeline import run_pipeline_once, _handle_pipeline_exception


def _setup_isolated_pipeline_env(monkeypatch, tmp_path):
    """Sets up a completely isolated workspace, database, and mocked subsystems."""
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    old_work_root = SETTINGS.work_root
    old_art_root = SETTINGS.artifact_root
    old_drive_fid = SETTINGS.drive_folder_id
    old_drive_rfid = SETTINGS.drive_root_folder_id

    object.__setattr__(SETTINGS, "work_root", work_dir)
    object.__setattr__(SETTINGS, "artifact_root", artifacts_dir)
    object.__setattr__(SETTINGS, "drive_folder_id", "")
    object.__setattr__(SETTINGS, "drive_root_folder_id", "")

    def _restore():
        object.__setattr__(SETTINGS, "work_root", old_work_root)
        object.__setattr__(SETTINGS, "artifact_root", old_art_root)
        object.__setattr__(SETTINGS, "drive_folder_id", old_drive_fid)
        object.__setattr__(SETTINGS, "drive_root_folder_id", old_drive_rfid)

    monkeypatch.setenv("WORK_ROOT", str(work_dir))
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_dir))
    monkeypatch.setattr("src.pipeline.is_test_environment", lambda: True)

    db_path = tmp_path / "queue_stress.db"
    repository = QueueRepository(db_path)
    repository.initialize()

    # Base mocks for fast deterministic execution
    monkeypatch.setattr("src.llm.curate_script", lambda *args, **kwargs: (
        "Esta es una historia de misterio y suspenso en español donde la protagonista "
        "investiga una casa abandonada y descubre secretos ocultos tras una puerta sellada."
    ))
    monkeypatch.setattr("src.llm.translate_title", lambda *args, **kwargs: "La Puerta Sellada")
    monkeypatch.setattr("src.llm.clean_title", lambda title: "La Puerta Sellada")
    monkeypatch.setattr("src.pipeline.is_spanish_neutral", lambda *args, **kwargs: True)

    def _mock_audio(output, duration=15.0):
        p = Path(output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"RIFFmockWAVEfmt ")
        return {
            "audio_path": str(p),
            "duration_sec": duration,
            "word_timestamps": [{"word": "Esta", "start": 0.0, "end": 0.5}],
        }

    monkeypatch.setattr(
        "lib.tts.generate_audio",
        lambda script, output, **kwargs: _mock_audio(output),
    )

    def _mock_loop_render(*args, **kwargs):
        out = args[2] if len(args) > 2 else kwargs.get("output_video_path")
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"DUMMY_MP4_DATA")
        return {
            "compositor": "loop",
            "render_time_sec": 0.5,
            "output_path": str(p),
            "quality_metrics": {
                "longest_black_seconds": 0.0,
                "perceptual_luminance": 75.0,
            },
        }

    monkeypatch.setattr("src.media.loop_engine.LoopVideoEngine.render", _mock_loop_render)
    monkeypatch.setattr(
        "src.media.loop_engine.LoopVideoEngine.resolve_loop_video",
        lambda *args, **kwargs: str(tmp_path / "fake_loop.mp4"),
    )

    def _mock_thumb(title, channel, output_path, **kwargs):
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"DUMMY_JPEG_DATA")

    monkeypatch.setattr("lib.video.create_video_thumbnail", _mock_thumb)

    img = tmp_path / "scenery_still.jpg"
    img.write_bytes(b"STILL_IMAGE")
    assets_mock = SimpleNamespace(
        get_background=lambda **kwargs: str(img),
        get_background_sequence=lambda count, **kwargs: [str(img)] * count,
        get_music=lambda **kwargs: "",
        get_ambient=lambda **kwargs: "",
        resolve_or_create_background_audio=lambda **kwargs: "",
    )
    monkeypatch.setattr("src.asset_manager.get_asset_manager", lambda: assets_mock)

    report_mock = MagicMock()
    report_mock.require_pass.return_value = None
    monkeypatch.setattr("src.pipeline.validate_prepublication", lambda **kwargs: report_mock)

    return repository, db_path, work_dir


# =========================================================================
# Stage Failure & Lease Release Tests
# =========================================================================

def test_stage_01_claim_failure_returns_clean_exit(monkeypatch, tmp_path):
    """Stage 1: Non-claimable story returns STORY_NOT_CLAIMABLE and empty ID raises ValueError."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)

    # Directed claim on nonexistent story
    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="nonexistent-story-123",
        directed=True,
    )
    assert res["status"] == "STORY_NOT_CLAIMABLE"
    assert res["story_id"] == "nonexistent-story-123"

    # Empty story-id in directed mode
    with pytest.raises(ValueError, match="--story-id no puede estar vacío"):
        run_pipeline_once(channel="horror", db_path=str(db_path), story_id="", directed=True)


def test_stage_03_editorial_compliance_failure_releases_lease(monkeypatch, tmp_path):
    """Stage 3: Editorial barrier failure fails closed, marks RETRYABLE_FAILED, and releases lease."""
    repository, db_path, work_dir = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-st3", "Misterio", "Contenido seguro", "https://url", "horror")

    # Inject failure into editorial barrier
    def _exploding_editorial(*args, **kwargs):
        raise ValueError("Editorial compliance rejected: prohibited framing detected")

    monkeypatch.setattr("src.pipeline._enforce_editorial_compliance", _exploding_editorial)

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-st3",
        directed=True,
    )

    assert res["status"] == "RETRYABLE_FAILED"
    assert "Editorial compliance rejected" in res["reason"]

    # Verify SQLite lease cleanup
    with connect(str(db_path), read_only=True) as conn:
        leases = conn.execute("SELECT * FROM leases WHERE job_id = 'story-m2-st3'").fetchall()
        lane_leases = conn.execute("SELECT * FROM lane_leases WHERE job_id = 'story-m2-st3'").fetchall()
        story = conn.execute("SELECT status, failure_code FROM stories WHERE story_id = 'story-m2-st3'").fetchone()

    assert len(leases) == 0, f"Lease was not deleted from leases table: {leases}"
    assert len(lane_leases) == 0, f"Lease was not deleted from lane_leases table: {lane_leases}"
    assert story["status"] == JobStatus.RETRYABLE_FAILED.value
    assert story["failure_code"] == "pipeline_validation"

    # Verify marker is deactivated
    marker_path = work_dir / res["run_id"] / ".run.json"
    if marker_path.exists():
        marker_data = json.loads(marker_path.read_text(encoding="utf-8"))
        assert marker_data["active"] is False


def test_stage_05_tts_capability_unavailable_fails_closed(monkeypatch, tmp_path):
    """Stage 5: CapabilityUnavailable in TTS marks RETRYABLE_FAILED and releases lease."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-st5-cap", "Misterio", "Contenido", "https://url", "horror")

    def _exploding_tts(*args, **kwargs):
        raise CapabilityUnavailable("TTS synthesis engine is unreachable")

    monkeypatch.setattr("lib.tts.generate_audio", _exploding_tts)

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-st5-cap",
        directed=True,
    )

    assert res["status"] == "RETRYABLE_FAILED"
    assert "TTS synthesis engine is unreachable" in res["reason"]

    with connect(str(db_path), read_only=True) as conn:
        leases = conn.execute("SELECT * FROM leases WHERE job_id = 'story-m2-st5-cap'").fetchall()
        lane_leases = conn.execute("SELECT * FROM lane_leases WHERE job_id = 'story-m2-st5-cap'").fetchall()
        story = conn.execute("SELECT status, failure_code, next_attempt_at FROM stories WHERE story_id = 'story-m2-st5-cap'").fetchone()

    assert len(leases) == 0
    assert len(lane_leases) == 0
    assert story["status"] == JobStatus.RETRYABLE_FAILED.value
    assert story["failure_code"] == "capability_unavailable"
    assert story["next_attempt_at"] is not None


def test_stage_05_tts_quota_error_routes_to_waiting_llm_quota(monkeypatch, tmp_path):
    """Stage 5: QuotaError before video render routes cleanly to WAITING_LLM_QUOTA and releases lease."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-st5-quota", "Misterio", "Contenido", "https://url", "horror")

    def _quota_tts(*args, **kwargs):
        raise QuotaError("ElevenLabs quota exceeded")

    monkeypatch.setattr("lib.tts.generate_audio", _quota_tts)

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-st5-quota",
        directed=True,
    )

    assert res["status"] == JobStatus.WAITING_LLM_QUOTA.value

    with connect(str(db_path), read_only=True) as conn:
        leases = conn.execute("SELECT * FROM leases WHERE job_id = 'story-m2-st5-quota'").fetchall()
        story = conn.execute("SELECT status, failure_code FROM stories WHERE story_id = 'story-m2-st5-quota'").fetchone()

    assert len(leases) == 0
    assert story["status"] == JobStatus.WAITING_LLM_QUOTA.value
    assert story["failure_code"] == "quota"


def test_stage_06_duration_alignment_failure_fails_closed(monkeypatch, tmp_path):
    """Stage 6: Duration alignment failure when audio duration cannot be salvaged."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-st6", "Misterio", "Contenido", "https://url", "horror")

    # Audio returns 250s which exceeds vertical max (180s) even after re-condensation
    def _long_audio(output):
        p = Path(output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"RIFFlongWAVE")
        return {
            "audio_path": str(p),
            "duration_sec": 250.0,
            "word_timestamps": [],
        }

    monkeypatch.setattr("lib.tts.generate_audio", lambda *args, **kwargs: _long_audio(args[1] if len(args) > 1 else kwargs.get("output")))

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-st6",
        directed=True,
    )

    assert res["status"] == "RETRYABLE_FAILED"
    assert "excede el máximo" in res["reason"]

    with connect(str(db_path), read_only=True) as conn:
        leases = conn.execute("SELECT * FROM leases WHERE job_id = 'story-m2-st6'").fetchall()
    assert len(leases) == 0


def test_stage_09_video_rendering_missing_catalog_fails_closed(monkeypatch, tmp_path):
    """Stage 9: LoopVideoEngine CatalogAssetNotFoundError fails closed and releases lease."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-st9", "Misterio", "Contenido", "https://url", "horror")

    def _exploding_render(*args, **kwargs):
        raise CatalogAssetNotFoundError("No physical loop asset found on disk")

    monkeypatch.setattr("src.media.loop_engine.LoopVideoEngine.render", _exploding_render)

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-st9",
        directed=True,
    )

    assert res["status"] == "RETRYABLE_FAILED"
    assert "No physical loop asset found" in res["reason"]

    with connect(str(db_path), read_only=True) as conn:
        leases = conn.execute("SELECT * FROM leases WHERE job_id = 'story-m2-st9'").fetchall()
    assert len(leases) == 0


def test_stage_10_qa_gating_failure_fails_closed(monkeypatch, tmp_path):
    """Stage 10: validate_prepublication gate failure fails closed without marking RENDERED."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-st10", "Misterio", "Contenido", "https://url", "horror")

    bad_report = MagicMock()
    bad_report.require_pass.side_effect = ValueError("Prepublication QA check failed: black frames detected")
    monkeypatch.setattr("src.pipeline.validate_prepublication", lambda **kwargs: bad_report)

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-st10",
        directed=True,
    )

    assert res["status"] == "RETRYABLE_FAILED"
    assert "Prepublication QA check failed" in res["reason"]

    with connect(str(db_path), read_only=True) as conn:
        leases = conn.execute("SELECT * FROM leases WHERE job_id = 'story-m2-st10'").fetchall()
        story = conn.execute("SELECT status FROM stories WHERE story_id = 'story-m2-st10'").fetchone()

    assert len(leases) == 0
    assert story["status"] == JobStatus.RETRYABLE_FAILED.value


def test_stage_11_missing_required_artifact_fails_closed(monkeypatch, tmp_path):
    """Stage 11: Missing mandatory artifact (e.g. thumbnail creation failed) fails closed."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-st11", "Misterio", "Contenido", "https://url", "horror")

    # create_video_thumbnail is a no-op, so thumbnail.jpg is never created
    monkeypatch.setattr("lib.video.create_video_thumbnail", lambda *args, **kwargs: None)

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-st11",
        directed=True,
    )

    assert res["status"] == "RETRYABLE_FAILED"
    assert "Artefacto obligatorio ausente" in res["reason"]

    with connect(str(db_path), read_only=True) as conn:
        leases = conn.execute("SELECT * FROM leases WHERE job_id = 'story-m2-st11'").fetchall()
    assert len(leases) == 0


def test_stage_12_dedup_simhash_rejects_duplicate_script(monkeypatch, tmp_path):
    """Stage 12: Dedup gating rejects duplicate script fingerprint and fails closed."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-st12", "Misterio", "Contenido", "https://url", "horror")

    # Record fingerprint as already published
    test_script = (
        "Esta es una historia de misterio y suspenso en español donde la protagonista "
        "investiga una casa abandonada y descubre secretos ocultos tras una puerta sellada."
    )
    repository.enqueue("prev-story-999", "Titulo Previo", "Contenido Previo", "https://url-unique-prev-999", "horror")
    repository.record_fingerprint("prev-run-999", "prev-story-999", "horror", "script", test_script)
    with connect(str(db_path)) as conn:
        conn.execute("UPDATE runs SET status = 'PUBLISHED' WHERE run_id = 'prev-run-999'")
        conn.commit()

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-st12",
        directed=True,
    )

    assert res["status"] == "RETRYABLE_FAILED"
    assert "Artefactos duplicados respecto de publicaciones recientes" in res["reason"]

    with connect(str(db_path), read_only=True) as conn:
        leases = conn.execute("SELECT * FROM leases WHERE job_id = 'story-m2-st12'").fetchall()
    assert len(leases) == 0


# =========================================================================
# Heartbeat & Mid-Pipeline Lease Loss Tests
# =========================================================================

def test_heartbeat_lease_lost_mid_pipeline_halts_without_corrupting_story(monkeypatch, tmp_path):
    """If lease is lost mid-pipeline, require_heartbeat raises LeaseOwnershipError -> status: LEASE_LOST."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-heartbeat", "Misterio", "Contenido", "https://url", "horror")

    # Intercept require_heartbeat to simulate lease stolen after stage 3
    original_require_heartbeat = None
    call_count = 0

    from src.pipeline import RunContext
    original_require_heartbeat = RunContext.require_heartbeat

    def _hijacked_heartbeat(self):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise LeaseOwnershipError("El lease dirigido ya no pertenece a este worker")
        return original_require_heartbeat(self)

    monkeypatch.setattr(RunContext, "require_heartbeat", _hijacked_heartbeat)

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-heartbeat",
        directed=True,
    )

    assert res["status"] == "LEASE_LOST"
    assert "El worker perdió ownership del run; no se mutó el estado" in res["reason"]


# =========================================================================
# generate_only=True Contract Tests
# =========================================================================

def test_generate_only_halts_cleanly_at_rendered_without_publishing(monkeypatch, tmp_path):
    """generate_only=True stops at RENDERED, finishes run, releases lease, and NEVER calls review or YouTube."""
    repository, db_path, work_dir = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-genonly", "Misterio", "Contenido", "https://url", "horror")

    mock_review = MagicMock()
    mock_upload = MagicMock()
    monkeypatch.setattr("review.ReviewJobManager", lambda: mock_review)
    monkeypatch.setattr("src.youtube.uploader.upload_video", mock_upload)

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-genonly",
        directed=True,
        generate_only=True,
    )

    assert res["status"] == "RENDERED"
    assert res["story_id"] == "story-m2-genonly"

    # Verify review and upload were NEVER called
    mock_review.assert_not_called()
    mock_upload.assert_not_called()

    # Verify lease is released in SQLite
    with connect(str(db_path), read_only=True) as conn:
        leases = conn.execute("SELECT * FROM leases WHERE job_id = 'story-m2-genonly'").fetchall()
        lane_leases = conn.execute("SELECT * FROM lane_leases WHERE job_id = 'story-m2-genonly'").fetchall()
        runs = conn.execute("SELECT status, finished_at FROM runs WHERE run_id = ?", (res["run_id"],)).fetchone()

    assert len(leases) == 0
    assert len(lane_leases) == 0
    assert runs["status"] == JobStatus.RENDERED.value
    assert runs["finished_at"] is not None

    # Verify marker is deactivated
    marker_path = work_dir / res["run_id"] / ".run.json"
    assert marker_path.exists()
    marker_data = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker_data["active"] is False


def test_generate_only_lease_lost_on_finish_raises_lease_lost(monkeypatch, tmp_path):
    """generate_only=True raises LeaseOwnershipError if lease was lost before finish_run."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-genonly-lost", "Misterio", "Contenido", "https://url", "horror")

    monkeypatch.setattr(QueueRepository, "finish_run", lambda *args, **kwargs: False)

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-genonly-lost",
        directed=True,
        generate_only=True,
    )

    assert res["status"] == "LEASE_LOST"


# =========================================================================
# Zero-Browser Policy & Subprocess Monitoring Tests
# =========================================================================

def test_zero_browser_imports_across_pipeline_and_media():
    """Verify zero imports of playwright or chromium in src/pipeline.py and media/cli/narrative/core."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    check_paths = [
        repo_root / "src" / "pipeline.py",
        repo_root / "src" / "media",
        repo_root / "src" / "cli",
        repo_root / "src" / "narrative",
        repo_root / "src" / "core",
    ]

    violations = []
    for base in check_paths:
        files = [base] if base.is_file() else list(base.rglob("*.py"))
        for py_file in files:
            if "_legacy" in str(py_file):
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "playwright" in alias.name.lower() or "chromium" in alias.name.lower():
                            violations.append((str(py_file), alias.name))
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if "playwright" in mod.lower() or "chromium" in mod.lower():
                        violations.append((str(py_file), mod))

    assert not violations, f"Zero-Browser violations found: {violations}"


def test_runtime_pipeline_never_spawns_browser_processes(monkeypatch, tmp_path):
    """Runtime execution of pipeline monitors all subprocess invocations and confirms zero browsers."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-browser-audit", "Misterio", "Contenido", "https://url", "horror")

    spawned_commands = []
    real_popen = subprocess.Popen
    real_run = subprocess.run

    def audit_popen(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args")
        spawned_commands.append(cmd)
        cmd_str = " ".join(str(c) for c in (cmd if isinstance(cmd, (list, tuple)) else [cmd])).lower()
        assert "playwright" not in cmd_str, f"Forbidden browser process spawned: {cmd}"
        assert "chromium" not in cmd_str, f"Forbidden browser process spawned: {cmd}"
        assert "chrome" not in cmd_str, f"Forbidden browser process spawned: {cmd}"
        return real_popen(*args, **kwargs)

    def audit_run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args")
        spawned_commands.append(cmd)
        cmd_str = " ".join(str(c) for c in (cmd if isinstance(cmd, (list, tuple)) else [cmd])).lower()
        assert "playwright" not in cmd_str, f"Forbidden browser process spawned: {cmd}"
        assert "chromium" not in cmd_str, f"Forbidden browser process spawned: {cmd}"
        assert "chrome" not in cmd_str, f"Forbidden browser process spawned: {cmd}"
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", audit_popen)
    monkeypatch.setattr(subprocess, "run", audit_run)

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-browser-audit",
        directed=True,
        generate_only=True,
    )

    assert res["status"] == "RENDERED"
    # Verify no browser processes were spawned in any subprocess call
    for cmd in spawned_commands:
        cmd_str = " ".join(str(c) for c in (cmd if isinstance(cmd, (list, tuple)) else [cmd])).lower()
        assert "playwright" not in cmd_str
        assert "chromium" not in cmd_str


def test_exception_handling_when_set_owned_status_fails_returns_lease_lost(monkeypatch, tmp_path):
    """When an exception occurs but lease was stolen concurrently, _handle_pipeline_exception returns LEASE_LOST."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-lost-on-exc", "Misterio", "Contenido", "https://url", "horror")

    # Explode in Stage 5
    monkeypatch.setattr("lib.tts.generate_audio", MagicMock(side_effect=RuntimeError("TTS engine failed")))

    # Simulate set_owned_status returning False (lease revoked)
    from src.pipeline import RunContext
    monkeypatch.setattr(RunContext, "set_owned_status", lambda *args, **kwargs: False)

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-lost-on-exc",
        directed=True,
    )

    assert res["status"] == "LEASE_LOST"
    assert "El worker perdió ownership del run; no se mutó el estado" in res["reason"]


def test_invalid_video_engine_raises_value_error(monkeypatch, tmp_path):
    """Invalid video_engine argument raises ValueError fail-closed."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-invalid-eng", "Misterio", "Contenido", "https://url", "horror")

    with pytest.raises(ValueError, match="is not supported"):
        run_pipeline_once(
            channel="horror",
            db_path=str(db_path),
            story_id="story-m2-invalid-eng",
            directed=True,
            video_engine="unsupported_gl_shader",
        )


def test_multiscene_mode_rejected_fail_closed(monkeypatch, tmp_path):
    """Retired video_engine='multiscene' is rejected fail-closed with ValueError."""
    repository, db_path, _ = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-coerce-eng", "Misterio", "Contenido", "https://url", "horror")

    with pytest.raises(ValueError, match="video_engine='multiscene' is not supported"):
        run_pipeline_once(
            channel="horror",
            db_path=str(db_path),
            story_id="story-m2-coerce-eng",
            directed=True,
            video_engine="multiscene",
            generate_only=True,
        )


def test_generate_only_with_subtitles_enabled(monkeypatch, tmp_path):
    """generate_only=True with enable_subtitles=True generates captions and halts cleanly at RENDERED."""
    repository, db_path, work_dir = _setup_isolated_pipeline_env(monkeypatch, tmp_path)
    repository.enqueue("story-m2-subs-genonly", "Misterio", "Contenido", "https://url", "horror")

    def _mock_ass(words, output_path, **kwargs):
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")

    def _mock_srt(words, output_path, **kwargs):
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest\n\n", encoding="utf-8")

    monkeypatch.setattr("lib.subtitles.create_ass_subtitles", _mock_ass)
    monkeypatch.setattr("lib.subtitles.create_subtitles", _mock_srt)
    monkeypatch.setattr("lib.subtitles.validate_subtitle_grammar_and_syntax", lambda *args: True)
    monkeypatch.setattr("lib.subtitles.validate_subtitle_artifact", lambda *args, **kwargs: True)

    res = run_pipeline_once(
        channel="horror",
        db_path=str(db_path),
        story_id="story-m2-subs-genonly",
        directed=True,
        generate_only=True,
        enable_subtitles=True,
    )

    assert res["status"] == "RENDERED"
    run_work = work_dir / res["run_id"]
    assert (run_work / "subtitles.ass").exists()
    assert (run_work / "subtitles.srt").exists()
