import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.youtube.innertube_uploader import (
    InnerTubeSecurityChallengeError,
    InnerTubeUploadError,
    _build_auth_headers,
    _commit_video_metadata,
    _initiate_upload_session,
    _stream_video_chunks,
    upload_video_via_innertube,
)


def test_build_auth_headers_includes_sapisid_and_channel_id():
    headers = _build_auth_headers(
        cookies_header="LOGIN_INFO=xyz; SAPISID=abc",
        sapisid="abc",
        channel_id="UC1234567890",
    )
    assert headers["Authorization"].startswith("SAPISIDHASH ")
    assert headers["Cookie"] == "LOGIN_INFO=xyz; SAPISID=abc"
    assert headers["X-Goog-PageId"] == "UC1234567890"
    assert headers["X-Origin"] == "https://studio.youtube.com"


def test_initiate_upload_session_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"x-goog-upload-url": "https://upload.youtube.com/session/abc123upload"}

    with patch("requests.post", return_value=mock_resp) as mock_post:
        url = _initiate_upload_session(filesize=1024, auth_headers={"Authorization": "SAPISIDHASH test"})
        assert url == "https://upload.youtube.com/session/abc123upload"
        mock_post.assert_called_once()
        call_headers = mock_post.call_args[1]["headers"]
        assert call_headers["x-goog-upload-command"] == "start"
        assert call_headers["x-goog-upload-header-content-length"] == "1024"


def test_initiate_upload_session_security_challenge():
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(InnerTubeSecurityChallengeError, match="InnerTube authentication rejected"):
            _initiate_upload_session(filesize=1024, auth_headers={"Authorization": "SAPISIDHASH test"})


def test_stream_video_chunks_success(tmp_path):
    dummy_video = tmp_path / "sample.mp4"
    dummy_video.write_bytes(b"dummy mp4 video bytes")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "STATUS_SUCCESS", "scottyResourceId": "scotty_res_999"}

    with patch("requests.post", return_value=mock_resp):
        scotty_id = _stream_video_chunks(
            dummy_video,
            upload_url="https://upload.youtube.com/session/upload",
            auth_headers={"Authorization": "SAPISIDHASH test"},
        )
        assert scotty_id == "scotty_res_999"


def test_commit_video_metadata_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"videoId": "yt_vid_success_123"}

    with patch("requests.post", return_value=mock_resp) as mock_post:
        vid = _commit_video_metadata(
            scotty_resource_id="scotty_res_999",
            title="Short Horror Story",
            description="Scary story description",
            auth_headers={"Authorization": "SAPISIDHASH test"},
            tags=["horror", "scp"],
            channel_id="UC_BRAND_ACCOUNT",
        )
        assert vid == "yt_vid_success_123"
        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["resourceId"]["scottyResourceId"]["id"] == "scotty_res_999"
        assert call_payload["initialMetadata"]["title"]["newTitle"] == "Short Horror Story"
        assert call_payload["context"]["user"]["delegatedSessionId"] == "UC_BRAND_ACCOUNT"


def test_upload_video_via_innertube_full_flow(tmp_path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"fake video data")

    cookies = [
        {"name": "LOGIN_INFO", "value": "login123"},
        {"name": "SAPISID", "value": "sapisid456"},
    ]

    with patch.dict("os.environ", {"TEST_MODE": "0", "MOCK_YOUTUBE_UPLOAD": "0"}), \
         patch("src.youtube.innertube_uploader._initiate_upload_session", return_value="https://upload.youtube.com/resumable"), \
         patch("src.youtube.innertube_uploader._stream_video_chunks", return_value="scotty_777"), \
         patch("src.youtube.innertube_uploader._commit_video_metadata", return_value="final_vid_abc"):

        res = upload_video_via_innertube(
            video_path=dummy_video,
            title="My Title",
            description="My Desc",
            cookies=cookies,
            channel_id="UC_TEST",
        )

        assert res["status"] == "PUBLISHED"
        assert res["method"] == "INNERTUBE"
        assert res["video_id"] == "final_vid_abc"
        assert "https://www.youtube.com/watch?v=final_vid_abc" in res["url"]


def test_upload_video_via_innertube_test_mock_env(tmp_path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"fake video data")
    cookies = [{"name": "SAPISID", "value": "sapisid456"}]

    with patch.dict("os.environ", {"TEST_MODE": "1"}):
        res = upload_video_via_innertube(
            video_path=dummy_video,
            title="Mock Env Title",
            description="Mock Env Desc",
            cookies=cookies,
        )
        assert res["status"] == "TEST_MOCK"
        assert res["method"] == "INNERTUBE"


def test_upload_video_via_innertube_dry_run(tmp_path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"fake video data")
    cookies = [{"name": "SAPISID", "value": "sapisid456"}]

    res = upload_video_via_innertube(
        video_path=dummy_video,
        title="Dry Run Title",
        description="Dry Run Desc",
        cookies=cookies,
        dry_run=True,
    )
    assert res["status"] == "DRY_RUN"
    assert res["method"] == "INNERTUBE"
