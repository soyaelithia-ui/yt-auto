"""Comprehensive tests for yt-auto v3.1 architectural components."""

import os
import sqlite3
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.cookies import (
    SessionHealthResult,
    SessionHealthValidator,
    SessionStatus,
)
from src.youtube.session_uploader import (
    SessionUploader,
    SessionUploadError,
    upload_video_via_session,
)
from src.audio.tts_router import (
    TTSRouter,
    TTSResponse,
    ProviderCircuitBreaker,
    route_tts,
)
from src.core.lease_reaper import (
    LeaseReaper,
    is_pid_alive,
    extract_pid_from_owner,
    is_local_hostname,
)
from src.core.db_reconciler import (
    DBReconciler,
    ReconciliationError,
)
from src.core.gpu_detector import (
    has_hardware_acceleration_support,
    resolve_chromium_gpu_flags,
    get_gpu_environment_status,
)
from lib.audio import _get_ram_temp_dir
from lib.subtitles import estimate_text_width_px, get_font_metrics


# ============================================================================
# 1. Session Health & Session Uploader Tests
# ============================================================================

def test_session_health_validator_expiring_soon():
    now = time.time()
    # Cookie expiring in 24 hours (< 48h)
    cookies = [
        {"name": "LOGIN_INFO", "value": "xyz123", "expires": now + 86400},
        {"name": "SID", "value": "sid123", "expires": now + 86400},
    ]
    res = SessionHealthValidator.validate(cookies, expiring_soon_hours=48.0)
    assert res.status == SessionStatus.EXPIRING_SOON
    assert res.days_left is not None
    assert res.days_left < 2.0


def test_session_health_validator_expired():
    now = time.time()
    cookies = [
        {"name": "LOGIN_INFO", "value": "xyz123", "expires": now - 3600},
        {"name": "SID", "value": "sid123", "expires": now - 3600},
    ]
    res = SessionHealthValidator.validate(cookies)
    assert res.status == SessionStatus.EXPIRED


def test_session_health_validator_incomplete():
    cookies = [{"name": "random_cookie", "value": "123"}]
    res = SessionHealthValidator.validate(cookies)
    assert res.status == SessionStatus.INCOMPLETE
    assert "LOGIN_INFO" in res.missing_tokens


def test_session_uploader_dry_run(tmp_path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"dummy video bytes 12345")

    uploader = SessionUploader(channel="moku")
    with patch.object(uploader, "check_health") as mock_health:
        mock_health.return_value = SessionHealthResult(status=SessionStatus.HEALTHY, detail="OK")
        res = uploader.upload(
            video_path=dummy_video,
            title="Short Title Test",
            description="Short Description",
            dry_run=True,
        )
        assert res["status"] == "DRY_RUN"
        assert res["method"] == "SESSION_PLAYWRIGHT"
        assert "video_id" in res


def test_session_uploader_fails_closed_when_invalid(tmp_path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"dummy video bytes 12345")

    uploader = SessionUploader(channel="moku")
    with patch.object(uploader, "check_health") as mock_health:
        mock_health.return_value = SessionHealthResult(status=SessionStatus.INVALID, detail="Corrupted")
        with pytest.raises(SessionUploadError) as exc_info:
            uploader.upload(
                video_path=dummy_video,
                title="Test",
                description="Test",
                dry_run=False,
            )
        assert exc_info.value.status == SessionStatus.INVALID


# ============================================================================
# 2. TTS Router & Multi-Tier Fallback Tests
# ============================================================================

def test_tts_router_tier1_success(tmp_path):
    out_audio = tmp_path / "narration.wav"
    with patch("lib.tts.generate_audio") as mock_gen:
        mock_gen.return_value = {
            "audio_path": str(out_audio),
            "duration_sec": 10.0,
            "word_timestamps": [{"word": "hola", "start": 0.0, "end": 0.5}],
            "provider": "edge-tts",
        }
        res = TTSRouter.synthesize(
            script_text="Hola mundo de prueba",
            output_audio_path=out_audio,
            target_duration_sec=10.0,
        )
        assert isinstance(res, TTSResponse)
        assert res.provider == "edge-tts"
        assert res.duration_sec == 10.0


def test_tts_router_fallback_to_tier2_on_tier1_failure(tmp_path):
    out_audio = tmp_path / "narration_fallback.wav"
    with patch("lib.tts.generate_audio", side_effect=RuntimeError("Edge-TTS connection reset")):
        res = TTSRouter.synthesize(
            script_text="Texto narrado en contingencia",
            output_audio_path=out_audio,
            target_duration_sec=5.0,
        )
        assert isinstance(res, TTSResponse)
        assert res.provider in ("local-offline-synthesizer", "emergency-anchor")
        assert Path(res.audio_path).is_file()
        assert res.duration_sec > 0


def test_tts_circuit_breaker():
    cb = ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=60.0)
    assert not cb.is_open()
    cb.record_failure()
    assert not cb.is_open()
    cb.record_failure()
    assert cb.is_open()
    cb.reset()
    assert not cb.is_open()


# ============================================================================
# 3. Lease Reaper & PID Monitoring Tests
# ============================================================================

def test_extract_pid_from_owner():
    assert extract_pid_from_owner("localhost:12345") == 12345
    assert extract_pid_from_owner("worker:999") == 999
    assert extract_pid_from_owner("server_node_42") == 42
    assert extract_pid_from_owner("invalid_owner_no_pid") is None


def test_is_pid_alive():
    current_pid = os.getpid()
    assert is_pid_alive(current_pid) is True
    # Non-existent high PID
    assert is_pid_alive(9999999) is False


def test_lease_reaper_clears_dead_worker(tmp_path):
    db_file = tmp_path / "shorts_queue.db"
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("""
            CREATE TABLE stories (story_id TEXT PRIMARY KEY, status TEXT, run_id TEXT, error_msg TEXT, published_at TEXT)
        """)
        conn.execute("""
            CREATE TABLE runs (run_id TEXT PRIMARY KEY, status TEXT, finished_at TEXT, error_code TEXT)
        """)
        conn.execute("""
            CREATE TABLE leases (job_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)
        """)
        conn.execute("""
            CREATE TABLE lane_leases (lane_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)
        """)

        # Dead PID lease
        dead_pid = 9999999
        conn.execute(
            "INSERT INTO stories (story_id, status, run_id) VALUES ('job_1', 'CLAIMED', 'run_1')"
        )
        conn.execute(
            "INSERT INTO runs (run_id, status) VALUES ('run_1', 'RUNNING')"
        )
        conn.execute(
            "INSERT INTO leases (job_id, channel, owner, run_id, acquired_at, heartbeat_at, expires_at) "
            "VALUES ('job_1', 'moku', ?, 'run_1', 100, 100, 1000)",
            (f"worker:{dead_pid}",),
        )
        conn.commit()

    reaper = LeaseReaper(db_path=db_file)
    reaped = reaper.reap_once()
    assert reaped == 1

    with sqlite3.connect(str(db_file)) as conn:
        remaining_leases = conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0]
        story_status = conn.execute("SELECT status FROM stories WHERE story_id = 'job_1'").fetchone()[0]
        assert remaining_leases == 0
        assert story_status == "RETRYABLE_FAILED"


# ============================================================================
# 4. 2PC Atomic DB Reconciler Tests
# ============================================================================

def test_db_reconciler_publication(tmp_path):
    queue_db = tmp_path / "shorts_queue.db"
    review_db = tmp_path / "review_state.db"

    # Setup Queue DB
    with sqlite3.connect(str(queue_db)) as conn:
        conn.execute("CREATE TABLE stories (story_id TEXT PRIMARY KEY, status TEXT, published_at TEXT, error_msg TEXT)")
        conn.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, status TEXT, finished_at TEXT, error_code TEXT)")
        conn.execute("CREATE TABLE leases (job_id TEXT, run_id TEXT)")
        conn.execute("CREATE TABLE lane_leases (run_id TEXT)")
        conn.execute("INSERT INTO stories VALUES ('job_abc', 'APPROVED', NULL, NULL)")
        conn.execute("INSERT INTO runs VALUES ('run_abc', 'RUNNING', NULL, NULL)")
        conn.execute("INSERT INTO leases VALUES ('job_abc', 'run_abc')")
        conn.commit()

    # Setup Review DB
    with sqlite3.connect(str(review_db)) as conn:
        conn.execute("""
            CREATE TABLE review_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT,
                reviewed_at TEXT,
                published_id TEXT,
                published_url TEXT,
                publication_consumed INTEGER DEFAULT 0,
                delivery_error TEXT
            )
        """)
        conn.execute("INSERT INTO review_jobs VALUES ('job_abc', 'WAITING_REVIEW', NULL, NULL, NULL, 0, NULL)")
        conn.commit()

    reconciler = DBReconciler(queue_db_path=queue_db, review_db_path=review_db)
    res = reconciler.reconcile_publication(
        job_id="job_abc",
        run_id="run_abc",
        video_id="yt_vid_999",
    )
    assert res["status"] == "SUCCESS"
    assert res["video_id"] == "yt_vid_999"

    # Verify atomic update in both DBs
    with sqlite3.connect(str(review_db)) as conn:
        row = conn.execute("SELECT status, published_id FROM review_jobs WHERE job_id = 'job_abc'").fetchone()
        assert row[0] == "PUBLISHED"
        assert row[1] == "yt_vid_999"

    with sqlite3.connect(str(queue_db)) as conn:
        s_row = conn.execute("SELECT status FROM stories WHERE story_id = 'job_abc'").fetchone()
        assert s_row[0] == "PUBLISHED"
        leases_count = conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0]
        assert leases_count == 0

    # Idempotent re-run
    res_idempotent = reconciler.reconcile_publication(
        job_id="job_abc",
        run_id="run_abc",
        video_id="yt_vid_999",
    )
    assert res_idempotent["status"] == "ALREADY_PUBLISHED"


# ============================================================================
# 5. GPU & Chromium Detector Tests
# ============================================================================

def test_gpu_detector_headless_defaults():
    flags = resolve_chromium_gpu_flags(force_software=True)
    assert "--disable-gpu" in flags

    status = get_gpu_environment_status()
    assert "has_hardware_gpu" in status
    assert "recommended_flags" in status


# ============================================================================
# 6. Audio & Subtitles Geometry Tests
# ============================================================================

def test_ram_temp_dir():
    d = _get_ram_temp_dir()
    assert d.exists()
    assert os.access(d, os.W_OK)


def test_estimate_text_width_px():
    w1 = estimate_text_width_px("Corta", font_size=40)
    w2 = estimate_text_width_px("Esta es una frase significativamente más larga en español", font_size=40)
    assert w2 > w1
    assert w1 > 0
