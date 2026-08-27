"""Unit tests for Telegram large file uploads (up to 2 GB) via Local Bot API Server."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from review.domain import DeliveryResult
from review.telegram_bot import (
    DEFAULT_CLOUD_MAX_SIZE_BYTES,
    DEFAULT_LOCAL_MAX_SIZE_BYTES,
    TelegramHttpClient,
    TelegramReviewBot,
    get_telegram_api_base_url,
    get_telegram_max_file_size,
    is_local_bot_api,
)


class MockResponse:
    def __init__(self, status_code: int = 200, json_data: dict = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data or {"ok": True, "result": {"message_id": 9999}}
        self.text = text or json.dumps(self._json_data)

    def json(self):
        return self._json_data


def test_is_local_bot_api_detection(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "http://telegram-bot-api:8081")
    assert is_local_bot_api() is True

    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "http://localhost:8081")
    assert is_local_bot_api() is True

    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org")
    monkeypatch.delenv("TELEGRAM_LOCAL", raising=False)
    assert is_local_bot_api() is False

    monkeypatch.setenv("TELEGRAM_LOCAL", "true")
    assert is_local_bot_api() is True


def test_max_file_size_resolution(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "http://telegram-bot-api:8081")
    monkeypatch.setenv("TELEGRAM_LOCAL", "true")
    assert get_telegram_max_file_size() == DEFAULT_LOCAL_MAX_SIZE_BYTES  # 2000 MB

    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org")
    monkeypatch.setenv("TELEGRAM_LOCAL", "false")
    assert get_telegram_max_file_size() == DEFAULT_CLOUD_MAX_SIZE_BYTES  # 50 MB

    monkeypatch.setenv("TELEGRAM_MAX_FILE_SIZE_MB", "1500")
    assert get_telegram_max_file_size() == 1500 * 1024 * 1024


def test_send_video_2gb_local_uri_strategy(tmp_path, monkeypatch):
    """Verify that a 1.5 GB video is sent via file:// URI in local mode without network buffer overhead."""
    video = tmp_path / "large_video_1_5gb.mp4"
    with open(video, "wb") as f:
        f.truncate(1500 * 1024 * 1024)  # 1.5 GB sparse file

    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "http://telegram-bot-api:8081")
    monkeypatch.setenv("TELEGRAM_LOCAL", "true")
    monkeypatch.setenv("TELEGRAM_USE_LOCAL_FILES", "1")
    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)

    bot = TelegramReviewBot(token="test-token", chat_id="123456")

    with patch.object(bot.client, "request", return_value=MockResponse()) as mock_req:
        result = bot.send_video(
            video_path=str(video),
            caption="Large 1.5 GB Video Review",
            chat_id="123456",
        )

    assert result.ok is True
    assert result.message_id == 9999
    assert mock_req.called

    call_kwargs = mock_req.call_args.kwargs
    assert mock_req.call_args.args[0] == "POST"
    assert mock_req.call_args.args[1] == "sendVideo"
    data = call_kwargs.get("data", {})
    assert data.get("video") == f"file://{os.path.abspath(video)}"
    assert data.get("chat_id") == "123456"
    assert "files" not in call_kwargs or call_kwargs.get("files") is None


def test_send_video_streamed_multipart_fallback(tmp_path, monkeypatch):
    """Verify streamed multipart upload when local URI is disabled."""
    video = tmp_path / "stream_video.mp4"
    video.write_bytes(b"test video payload")

    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "http://telegram-bot-api:8081")
    monkeypatch.setenv("TELEGRAM_LOCAL", "true")
    monkeypatch.setenv("TELEGRAM_USE_LOCAL_FILES", "0")
    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)

    bot = TelegramReviewBot(token="test-token", chat_id="123456")

    with patch.object(bot.client, "request", return_value=MockResponse()) as mock_req:
        result = bot.send_video(
            video_path=str(video),
            caption="Streamed Video",
            chat_id="123456",
        )

    assert result.ok is True
    assert mock_req.called
    call_kwargs = mock_req.call_args.kwargs
    assert "files" in call_kwargs
    assert "video" in call_kwargs["files"]


def test_send_document_large_file(tmp_path, monkeypatch):
    """Verify sending document files up to 2 GB."""
    doc = tmp_path / "large_archive.zip"
    with open(doc, "wb") as f:
        f.truncate(800 * 1024 * 1024)  # 800 MB

    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "http://telegram-bot-api:8081")
    monkeypatch.setenv("TELEGRAM_LOCAL", "true")
    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)

    bot = TelegramReviewBot(token="test-token", chat_id="123456")

    with patch.object(bot.client, "request", return_value=MockResponse()) as mock_req:
        result = bot.send_document(
            document_path=str(doc),
            caption="Production Archive",
        )

    assert result.ok is True
    assert mock_req.call_args.args[1] == "sendDocument"


def test_send_photo_endpoint(tmp_path, monkeypatch):
    """Verify sending photo."""
    photo = tmp_path / "cover.jpg"
    photo.write_bytes(b"fake jpeg content")

    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)
    bot = TelegramReviewBot(token="test-token", chat_id="123456")

    with patch.object(bot.client, "request", return_value=MockResponse()) as mock_req:
        result = bot.send_photo(
            photo_path=str(photo),
            caption="Cover artwork",
        )

    assert result.ok is True
    assert mock_req.call_args.args[1] == "sendPhoto"


def test_preflight_rejection_for_over_2gb_file(tmp_path, monkeypatch):
    """Verify fail-fast preflight rejection for files > 2000 MB."""
    video = tmp_path / "oversize_2_1gb.mp4"
    with open(video, "wb") as f:
        f.truncate(2050 * 1024 * 1024)  # 2050 MB (> 2000 MB)

    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "http://telegram-bot-api:8081")
    monkeypatch.setenv("TELEGRAM_LOCAL", "true")
    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)

    bot = TelegramReviewBot(token="test-token", chat_id="123456")

    with patch.object(bot.client, "request") as mock_req:
        result = bot.send_video(video_path=str(video), caption="Oversize")

    assert result.ok is False
    assert "exceeds" in (result.error or "") and "limit" in (result.error or "")
    assert not mock_req.called


def test_rate_limit_429_backoff_and_retry(tmp_path, monkeypatch):
    """Verify HTTP 429 rate-limiting retry_after handling."""
    photo = tmp_path / "thumb.jpg"
    photo.write_bytes(b"jpeg")

    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)
    bot = TelegramReviewBot(token="test-token", chat_id="123456")

    resp_429 = MockResponse(
        status_code=429,
        json_data={"ok": False, "error_code": 429, "parameters": {"retry_after": 1}},
    )
    resp_200 = MockResponse(status_code=200, json_data={"ok": True, "result": {"message_id": 888}})

    with patch("review.telegram_bot.requests.post", side_effect=[resp_429, resp_200]) as mock_post, \
         patch("time.sleep") as mock_sleep:
        result = bot.send_photo(photo_path=str(photo))

    assert result.ok is True
    assert result.message_id == 888
    assert mock_post.call_count == 2
    mock_sleep.assert_called_with(1)


def test_server_5xx_retry_and_recovery(monkeypatch):
    """Verify retry on 502/503 status code."""
    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)
    bot = TelegramReviewBot(token="test-token", chat_id="123456")

    resp_502 = MockResponse(status_code=502, text="Bad Gateway")
    resp_200 = MockResponse(status_code=200, json_data={"ok": True, "result": {"message_id": 777}})

    with patch("review.telegram_bot.requests.post", side_effect=[resp_502, resp_200]) as mock_post, \
         patch("time.sleep"):
        result = bot.edit_message_text(text="Updated text", message_id=100)

    assert result.ok is True
    assert result.message_id == 777
    assert mock_post.call_count == 2
