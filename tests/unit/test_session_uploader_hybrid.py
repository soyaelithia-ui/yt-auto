from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.cookies import SessionHealthResult, SessionStatus
from src.youtube.session_uploader import SessionUploader, upload_video_via_session


def test_session_uploader_innertube_primary_success(tmp_path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"content")

    cookie_file = tmp_path / "cookies_moku.json"
    cookie_file.write_text('[{"name": "LOGIN_INFO", "value": "x"}, {"name": "SAPISID", "value": "y"}]', encoding="utf-8")

    uploader = SessionUploader(channel="moku", secrets_dir=tmp_path)

    fake_health = SessionHealthResult(status=SessionStatus.HEALTHY, detail="OK", total_cookies=2)
    fake_tube_res = {
        "status": "PUBLISHED",
        "method": "INNERTUBE",
        "video_id": "tube123",
        "url": "https://www.youtube.com/watch?v=tube123",
    }

    with patch.object(uploader, "check_health", return_value=fake_health), \
         patch("src.youtube.innertube_uploader.upload_video_via_innertube", return_value=fake_tube_res) as mock_tube, \
         patch("src.youtube.uploader.upload_video_via_playwright") as mock_pw:

        res = uploader.upload(
            video_path=dummy_video,
            title="Title",
            description="Desc",
            expected_channel_id="UC_CHAN_1",
        )

        assert res["status"] == "PUBLISHED"
        assert res["method"] == "INNERTUBE"
        assert res["video_id"] == "tube123"
        mock_tube.assert_called_once()
        mock_pw.assert_not_called()


def test_session_uploader_fallback_to_playwright_on_innertube_failure(tmp_path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"content")

    cookie_file = tmp_path / "cookies_moku.json"
    cookie_file.write_text('[{"name": "LOGIN_INFO", "value": "x"}, {"name": "SAPISID", "value": "y"}]', encoding="utf-8")

    uploader = SessionUploader(channel="moku", secrets_dir=tmp_path)

    fake_health = SessionHealthResult(status=SessionStatus.HEALTHY, detail="OK", total_cookies=2)
    fake_pw_res = {
        "status": "PUBLISHED",
        "method": "PLAYWRIGHT",
        "video_id": "pw456",
        "url": "https://www.youtube.com/watch?v=pw456",
    }

    from src.youtube.innertube_uploader import InnerTubeSecurityChallengeError

    with patch.object(uploader, "check_health", return_value=fake_health), \
         patch("src.youtube.innertube_uploader.upload_video_via_innertube", side_effect=InnerTubeSecurityChallengeError("2FA Required")) as mock_tube, \
         patch("src.youtube.uploader.upload_video_via_playwright", return_value=fake_pw_res) as mock_pw:

        res = uploader.upload(
            video_path=dummy_video,
            title="Title",
            description="Desc",
            expected_channel_id="UC_CHAN_1",
        )

        assert res["status"] == "PUBLISHED"
        assert res["method"] == "PLAYWRIGHT"
        assert res["video_id"] == "pw456"
        mock_tube.assert_called_once()
        mock_pw.assert_called_once()


def test_session_uploader_dry_run(tmp_path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"content")

    uploader = SessionUploader(channel="moku", secrets_dir=tmp_path)
    res = uploader.upload(
        video_path=dummy_video,
        title="Title",
        description="Desc",
        dry_run=True,
    )
    assert res["status"] == "DRY_RUN"
