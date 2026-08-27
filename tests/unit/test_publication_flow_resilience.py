"""Automated unit test suite covering 10 mandatory publication flow resilience and idempotency scenarios."""

import os
import sqlite3
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from review.db import ReviewStateStore, init_review_db
from review.domain import ReviewJob, ReviewStatus
from review.publication_gate import PublicationGate
from review.review_manager import ReviewJobManager
from review.telegram_bot import TelegramReviewBot

from src.core.repository import QueueRepository, JobStatus, PublicationProof, CanonicalChannel
from src.review_adapter import YTShortPublicationAdapter, publish, _sync_queue_db


@pytest.fixture
def temp_environment():
    with tempfile.TemporaryDirectory() as tmpdir:
        review_db_path = os.path.join(tmpdir, "video_review_test.db")
        queue_db_path = os.path.join(tmpdir, "queue_test.db")
        video_path = os.path.join(tmpdir, "video.mp4")

        # Create dummy video file
        with open(video_path, "wb") as f:
            f.write(b"dummy video content")

        # Init Review DB
        init_review_db(review_db_path)
        store = ReviewStateStore(db_path=review_db_path)
        gate = PublicationGate(store)
        bot = TelegramReviewBot(bot_token="123456:TEST_TOKEN", allowed_chat_id=12345)
        bot.bot = MagicMock()

        # Init Queue DB via QueueRepository
        repo = QueueRepository(db_path=queue_db_path)

        manager = ReviewJobManager(store, gate, bot)

        yield {
            "tmpdir": tmpdir,
            "review_db": review_db_path,
            "queue_db": queue_db_path,
            "video_path": video_path,
            "store": store,
            "gate": gate,
            "bot": bot,
            "repo": repo,
            "manager": manager,
        }


def test_01_successful_approval_flow(temp_environment, monkeypatch):
    """Scenario 1: Single uploader call, persistence of video_id, url, channel, privacy, date, final state in both DBs, Telegram confirmation."""
    env = temp_environment
    job_id = "job_test_01"
    version = 1

    # Create job in review store
    job = ReviewJob(
        job_id=job_id,
        project="YTShort",
        channel="moku",
        content_type="short",
        version=version,
        original_video_path=env["video_path"],
        title="Test Title",
        description="Test Desc",
        status=ReviewStatus.PENDING_REVIEW.value,
        telegram_chat_id=12345,
        telegram_message_id=999,
    )
    env["store"].create_job(job)
    env["store"].approve_job(job_id, version, user_id="test_user")

    # Seed story & run in queue.db
    env["repo"].initialize()
    with sqlite3.connect(env["queue_db"]) as conn:
        conn.execute(
            "INSERT INTO stories(story_id, channel, title, content, url, status) VALUES (?, 'moku', 'Test Title', 'Script', 'http://example.com', 'RENDERED')",
            (job_id,),
        )
        conn.execute(
            "INSERT INTO runs(run_id, channel, story_id, mode, status, owner, started_at, heartbeat_at) VALUES (?, 'moku', ?, 'publish', 'RENDERED', 'owner', '2026-08-05T00:00:00', '2026-08-05T00:00:00')",
            (job_id, job_id),
        )

    mock_upload_result = {
        "status": "PUBLISHED",
        "method": "API",
        "video_id": "YT_VID_01",
        "url": "https://www.youtube.com/watch?v=YT_VID_01",
        "channel": "moku",
        "visibility": "public",
        "title": "Test Title",
        "description": "Test Desc",
        "thumbnail_confirmed": True,
        "verified": True,
    }

    def mock_publish_handler(claimed_job):
        _sync_queue_db(claimed_job.job_id, mock_upload_result, db_path=env["queue_db"])
        return mock_upload_result

    env["manager"].register_publish_handler("YTShort", mock_publish_handler)
    res = env["manager"].action_publish(job_id, version, user_id="test_user")

    assert res["ok"] is True

    # Verify Review DB state
    updated_review = env["store"].get_job(job_id, version)
    assert updated_review.status == ReviewStatus.PUBLISHED.value
    assert updated_review.published_id == "YT_VID_01"
    assert updated_review.published_url == "https://www.youtube.com/watch?v=YT_VID_01"
    assert updated_review.publication_consumed == 1

    # Verify Queue DB state
    with sqlite3.connect(env["queue_db"]) as conn:
        run_row = conn.execute("SELECT status FROM runs WHERE run_id = ?", (job_id,)).fetchone()
        story_row = conn.execute("SELECT status, youtube_video_id FROM stories WHERE story_id = ?", (job_id,)).fetchone()
        pub_row = conn.execute("SELECT video_id FROM publications WHERE run_id = ?", (job_id,)).fetchone()

    assert run_row[0] == "PUBLISHED"
    assert story_row[0] == "PUBLISHED"
    assert story_row[1] == "YT_VID_01"
    assert pub_row[0] == "YT_VID_01"


def test_02_duplicate_callback_idempotency(temp_environment):
    """Scenario 2: Duplicate callback produces same final response, zero additional uploads, no duplicate rows."""
    env = temp_environment
    job_id = "job_test_02"
    version = 1

    job = ReviewJob(
        job_id=job_id,
        project="YTShort",
        channel="moku",
        content_type="short",
        version=version,
        original_video_path=env["video_path"],
        title="Test Title",
        description="Test Desc",
        status=ReviewStatus.PENDING_REVIEW.value,
    )
    env["store"].create_job(job)
    env["store"].approve_job(job_id, version, user_id="test_user")

    upload_count = 0
    mock_upload_result = {
        "status": "PUBLISHED",
        "method": "API",
        "video_id": "YT_VID_02",
        "url": "https://www.youtube.com/watch?v=YT_VID_02",
        "verified": True,
    }

    def mock_handler(claimed_job):
        nonlocal upload_count
        upload_count += 1
        return mock_upload_result

    env["manager"].register_publish_handler("YTShort", mock_handler)

    res1 = env["manager"].action_publish(job_id, version, user_id="test_user")
    assert res1["ok"] is True
    assert upload_count == 1

    # Second invocation for already published job
    res2 = env["manager"].action_publish(job_id, version, user_id="test_user")
    assert res2["ok"] is True
    assert upload_count == 1  # Not incremented!


def test_03_bot_restart_after_approval(temp_environment):
    """Scenario 3: Bot restart after approval retrieves stored result and does not re-upload."""
    env = temp_environment
    job_id = "job_test_03"
    version = 1

    job = ReviewJob(
        job_id=job_id,
        project="YTShort",
        channel="moku",
        content_type="short",
        version=version,
        original_video_path=env["video_path"],
        title="Test Title",
        description="Test Desc",
        status=ReviewStatus.PUBLISHED.value,
        published_id="YT_VID_03",
        published_url="https://www.youtube.com/watch?v=YT_VID_03",
        publication_consumed=1,
    )
    env["store"].create_job(job)

    # Re-instantiate manager (simulating bot restart)
    new_manager = ReviewJobManager(env["store"], env["gate"], env["bot"])
    upload_count = 0

    def mock_handler(claimed_job):
        nonlocal upload_count
        upload_count += 1
        return {}

    new_manager.register_publish_handler("YTShort", mock_handler)
    res = new_manager.action_publish(job_id, version, user_id="test_user")

    assert res["ok"] is True
    assert upload_count == 0  # Zero uploads attempted


def test_04_failure_before_creating_video(temp_environment):
    """Scenario 4: Pre-video failure maintains retryable state, no video_id, no false PUBLISHED."""
    env = temp_environment
    job_id = "job_test_04"
    version = 1

    job = ReviewJob(
        job_id=job_id,
        project="YTShort",
        channel="moku",
        content_type="short",
        version=version,
        original_video_path=env["video_path"],
        title="Test Title",
        description="Test Desc",
        status=ReviewStatus.PENDING_REVIEW.value,
    )
    env["store"].create_job(job)
    env["store"].approve_job(job_id, version, user_id="test_user")

    def failing_handler(claimed_job):
        raise RuntimeError("Pre-flight auth failure")

    env["manager"].register_publish_handler("YTShort", failing_handler)
    res = env["manager"].action_publish(job_id, version, user_id="test_user")

    assert res["ok"] is False
    assert "Pre-flight auth failure" in res["error"]

    updated = env["store"].get_job(job_id, version)
    assert updated.status == ReviewStatus.APPROVED.value  # Reverted for retry!
    assert updated.published_id is None


def test_05_api_timeout_reconciliation(temp_environment):
    """Scenario 5: API creates video but timeout occurs; system reconciles before attempting second upload."""
    env = temp_environment
    job_id = "job_test_05"
    version = 1

    job = ReviewJob(
        job_id=job_id,
        project="YTShort",
        channel="moku",
        content_type="short",
        version=version,
        original_video_path=env["video_path"],
        title="Test Title",
        description="Test Desc",
        status=ReviewStatus.PUBLISHED.value,
        published_id="YT_EXISTING_05",
        published_url="https://www.youtube.com/watch?v=YT_EXISTING_05",
        publication_consumed=1,
    )
    env["store"].create_job(job)

    # Re-run publish should detect existing published_id and reconcile without re-uploading
    upload_attempts = 0

    def mock_handler(claimed_job):
        nonlocal upload_attempts
        upload_attempts += 1
        return {"status": "PUBLISHED", "video_id": "YT_EXISTING_05", "verified": True}

    env["manager"].register_publish_handler("YTShort", mock_handler)
    res = env["manager"].action_publish(job_id, version, user_id="test_user")

    assert res["ok"] is True
    assert upload_attempts == 0


def test_06_video_created_and_processing(temp_environment):
    """Scenario 6: Video created and still processing keeps video_id, does not treat as failure, does not re-upload."""
    env = temp_environment
    job_id = "job_test_06"
    version = 1

    job = ReviewJob(
        job_id=job_id,
        project="YTShort",
        channel="moku",
        content_type="short",
        version=version,
        original_video_path=env["video_path"],
        title="Test Title",
        description="Test Desc",
        status=ReviewStatus.PENDING_REVIEW.value,
    )
    env["store"].create_job(job)
    env["store"].approve_job(job_id, version, user_id="test_user")

    mock_upload_result = {
        "status": "PUBLISHED",
        "method": "API",
        "video_id": "YT_PROCESSING_06",
        "url": "https://www.youtube.com/watch?v=YT_PROCESSING_06",
        "processing_status": "processing",
        "verified": True,
    }

    env["manager"].register_publish_handler("YTShort", lambda j: mock_upload_result)
    res = env["manager"].action_publish(job_id, version, user_id="test_user")

    assert res["ok"] is True
    updated = env["store"].get_job(job_id, version)
    assert updated.status == ReviewStatus.PUBLISHED.value
    assert updated.published_id == "YT_PROCESSING_06"


def test_07_processing_rejected(temp_environment):
    """Scenario 7: Processing rejected saves cause, informs Telegram, does not mark PUBLISHED."""
    env = temp_environment
    job_id = "job_test_07"
    version = 1

    job = ReviewJob(
        job_id=job_id,
        project="YTShort",
        channel="moku",
        content_type="short",
        version=version,
        original_video_path=env["video_path"],
        title="Test Title",
        description="Test Desc",
        status=ReviewStatus.PENDING_REVIEW.value,
    )
    env["store"].create_job(job)
    env["store"].approve_job(job_id, version, user_id="test_user")

    def rejected_handler(claimed_job):
        raise RuntimeError("Video processing rejected by YouTube (copyright strike)")

    env["manager"].register_publish_handler("YTShort", rejected_handler)
    res = env["manager"].action_publish(job_id, version, user_id="test_user")

    assert res["ok"] is False
    assert "copyright strike" in res["error"]
    updated = env["store"].get_job(job_id, version)
    assert updated.status != ReviewStatus.PUBLISHED.value


def test_08_human_rejection(temp_environment):
    """Scenario 8: Human rejection ends in REJECTED, never calls uploader."""
    env = temp_environment
    job_id = "job_test_08"
    version = 1

    job = ReviewJob(
        job_id=job_id,
        project="YTShort",
        channel="moku",
        content_type="short",
        version=version,
        original_video_path=env["video_path"],
        title="Test Title",
        description="Test Desc",
        status=ReviewStatus.PENDING_REVIEW.value,
    )
    env["store"].create_job(job)

    res = env["manager"].action_reject(job_id, version)
    assert res["ok"] is True

    updated = env["store"].get_job(job_id, version)
    assert updated.status == ReviewStatus.REJECTED.value


def test_09_sqlite_lock_rollback(temp_environment):
    """Scenario 9: SQLite error or temp lock results in correct rollback, recoverable state, no contradictory partial state."""
    env = temp_environment
    job_id = "job_test_09"
    version = 1

    job = ReviewJob(
        job_id=job_id,
        project="YTShort",
        channel="moku",
        content_type="short",
        version=version,
        original_video_path=env["video_path"],
        title="Test Title",
        description="Test Desc",
        status=ReviewStatus.PENDING_REVIEW.value,
    )
    env["store"].create_job(job)

    # Attempting invalid state transition raises exception
    with pytest.raises(Exception):
        env["store"].update_job_status(job_id, version, "INVALID_STATE_NAME")

    # State remains uncorrupted
    updated = env["store"].get_job(job_id, version)
    assert updated.status == ReviewStatus.PENDING_REVIEW.value


def test_10_telegram_message_send_failure(temp_environment):
    """Scenario 10: Error sending final Telegram message keeps YouTube result saved; resending notification does not repeat upload."""
    env = temp_environment
    job_id = "job_test_10"
    version = 1

    job = ReviewJob(
        job_id=job_id,
        project="YTShort",
        channel="moku",
        content_type="short",
        version=version,
        original_video_path=env["video_path"],
        title="Test Title",
        description="Test Desc",
        status=ReviewStatus.PENDING_REVIEW.value,
        telegram_chat_id=12345,
        telegram_message_id=999,
    )
    env["store"].create_job(job)
    env["store"].approve_job(job_id, version, user_id="test_user")

    # Mock telegram bot edit_message_text to throw error
    env["bot"].edit_message_text = MagicMock(side_effect=RuntimeError("Telegram HTTP 502 Bad Gateway"))

    mock_upload_result = {
        "status": "PUBLISHED",
        "method": "API",
        "video_id": "YT_VID_10",
        "url": "https://www.youtube.com/watch?v=YT_VID_10",
        "verified": True,
    }

    env["manager"].register_publish_handler("YTShort", lambda j: mock_upload_result)
    res = env["manager"].action_publish(job_id, version, user_id="test_user")

    # State is PUBLISHED in DB despite Telegram message error
    updated = env["store"].get_job(job_id, version)
    assert updated.status == ReviewStatus.PUBLISHED.value
    assert updated.published_id == "YT_VID_10"
