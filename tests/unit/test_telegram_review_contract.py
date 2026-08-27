from pathlib import Path
from unittest.mock import MagicMock, patch

from review import DeliveryResult
from src.telegram.notifier import send_video_for_review
from src.core.providers import DriveProof
from src.pipeline import _drive_review_url


def test_notifier_is_a_thin_core_adapter(tmp_path):
    video = tmp_path / "short.mp4"
    video.write_bytes(b"video")
    from src.integrity import compute_file_sha256
    sha = compute_file_sha256(video)
    with patch("src.telegram.notifier.TelegramReviewBot") as bot_cls, \
         patch("src.integrity.verify_media_integrity") as mock_verify:
        mock_verify.return_value = {"passed": True, "sha256_hash": sha}
        bot_cls.return_value.send_video_for_review.return_value = DeliveryResult(
            ok=True, message_id=12, job_id="short-1"
        )
        result = send_video_for_review(
            str(video),
            {"job_id": "short-1", "project": "YTShort", "sha256_hash": sha},
            chat_id="-1001",
        )
    assert result.ok
    assert bot_cls.call_args.kwargs["allowed_chat_id"] == -1001


def test_pipeline_and_uploader_are_fail_closed_by_contract():
    root = Path(__file__).resolve().parents[2]
    pipeline = (root / "src/pipeline.py").read_text(encoding="utf-8")
    uploader = (root / "src/youtube_uploader.py").read_text(encoding="utf-8")
    assert 'current_review_status = "APPROVED"' not in pipeline
    assert "proceeding as APPROVED" not in pipeline
    assert "PublicationGate" in uploader
    assert "Publication gate requires job_id" in uploader
    assert "single atomic publication claim" in uploader


def test_successful_drive_proof_builds_review_url():
    proof = DriveProof(
        file_id="verified-drive-id",
        name="short.mp4",
        size_bytes=5,
        folder_id="reviews",
        exists=True,
    )
    assert _drive_review_url(proof) == (
        "https://drive.google.com/file/d/verified-drive-id/view"
    )
