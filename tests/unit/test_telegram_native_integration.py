"""Unit tests verifying native integration and standardization of Telegram Bot."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from review import DeliveryResult, TelegramReviewBot
from review.telegram_bot import is_local_bot_api, get_telegram_max_file_size
from src.core.scheduler import AutoPilotScheduler
from src.telegram import (
    InteractiveTelegramBot,
    PollerHeartbeat,
    TelegramNotifier,
    poll_callbacks,
    send_telegram_message,
    send_video_for_review,
)


class MockResponse:
    def __init__(self, status_code: int = 200, json_data: dict = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data or {"ok": True, "result": {"message_id": 12345}}
        self.text = text or json.dumps(self._json_data)

    def json(self):
        return self._json_data


def test_telegram_facade_exports():
    """Verify all canonical components are cleanly exported from src.telegram."""
    assert TelegramNotifier is not None
    assert TelegramReviewBot is not None
    assert InteractiveTelegramBot is not None
    assert callable(send_telegram_message)
    assert callable(send_video_for_review)
    assert callable(poll_callbacks)
    assert PollerHeartbeat is not None


def test_welcome_menu_reflects_local_server_mode(monkeypatch):
    """Verify welcome menu dynamically displays 2000 MB when local server is active."""
    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)
    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "http://telegram-bot-api:8081")
    monkeypatch.setenv("TELEGRAM_LOCAL", "true")

    bot = TelegramReviewBot(token="token", chat_id="12345")
    assert is_local_bot_api(bot.base_url) is True

    with patch("review.telegram_bot.requests.post", return_value=MockResponse()) as post:
        res = bot.send_welcome_menu()

    assert res.ok is True
    call_payload = post.call_args.kwargs.get("json") or json.loads(post.call_args.kwargs.get("data", "{}"))
    assert "2000 MB" in call_payload["text"]
    assert "inline_keyboard" in call_payload.get("reply_markup", {})


def test_handle_text_command_status_and_health(monkeypatch):
    """Verify /status and /health slash commands via unified router."""
    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)
    bot = TelegramReviewBot(token="token", chat_id="12345")

    # /status command
    with patch("review.telegram_bot.requests.post", return_value=MockResponse()) as post:
        upd = {
            "message": {
                "chat": {"id": 12345},
                "from": {"id": 12345},
                "text": "/status",
            }
        }
        res = bot.handle_text_command(upd)
        assert res.ok is True
        payload = post.call_args.kwargs.get("json") or json.loads(post.call_args.kwargs.get("data", "{}"))
        assert "AutoPilot 24/7" in payload["text"]
        assert "Servidor Bot API" in payload["text"]

    # /health command
    with patch("review.telegram_bot.requests.post", return_value=MockResponse()) as post:
        with patch("src.api_health.check_all") as mock_health:
            mock_health.return_value = {
                "youtube": {"ok": True, "details": "Active"},
                "drive": {"ok": True, "details": "Connected"},
                "cookies": {"ok": True, "details": "Valid"},
            }
            upd = {
                "message": {
                    "chat": {"id": 12345},
                    "from": {"id": 12345},
                    "text": "/health moku",
                }
            }
            res = bot.handle_text_command(upd)
            assert res.ok is True


def test_handle_text_command_autopilot_toggle(monkeypatch):
    """Verify /autopilot command starts/stops AutoPilotScheduler."""
    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)
    bot = TelegramReviewBot(token="token", chat_id="12345")
    scheduler = AutoPilotScheduler.instance()
    scheduler.stop()
    assert scheduler.is_active() is False

    # Turn ON
    with patch("review.telegram_bot.requests.post", return_value=MockResponse()):
        upd = {
            "message": {
                "chat": {"id": 12345},
                "from": {"id": 12345},
                "text": "/autopilot",
            }
        }
        res = bot.handle_text_command(upd)
        assert res.ok is True
        assert scheduler.is_active() is True

    # Turn OFF
    with patch("review.telegram_bot.requests.post", return_value=MockResponse()):
        res = bot.handle_text_command(upd)
        assert res.ok is True
        assert scheduler.is_active() is False


def test_interactive_callbacks_handling(monkeypatch):
    """Verify interactive callback queries dispatch correctly."""
    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)
    bot = TelegramReviewBot(token="token", chat_id="12345")

    bot.register_job("job_999", {
        "id": "job_999",
        "topic": "IA del Futuro",
        "script": {"title": "Guión IA", "scenes": [{"scene": 1, "text": "Hola mundo"}]},
        "seo": {"selected_title": "Título Viral", "tags": ["ia", "tech"], "pinned_comment": "Opina!"},
        "audits": {"verdicts": [{"entity_name": "Logo", "verdict": "APPROVED_REFERENCE", "reasoning": "Valid"}]},
    })

    with patch("review.telegram_bot.requests.post", return_value=MockResponse()) as post:
        # Script inspect
        upd_script = {
            "callback_query": {
                "id": "cb1",
                "chat_instance": "1",
                "message": {"chat": {"id": 12345}, "message_id": 1},
                "from": {"id": 12345},
                "data": "view_script_job_999",
            }
        }
        res = bot.handle_callback_query(upd_script)
        assert res.ok is True

        # SEO inspect
        upd_seo = {
            "callback_query": {
                "id": "cb2",
                "chat_instance": "1",
                "message": {"chat": {"id": 12345}, "message_id": 1},
                "from": {"id": 12345},
                "data": "view_seo_job_999",
            }
        }
        res = bot.handle_callback_query(upd_seo)
        assert res.ok is True

        # Audits inspect
        upd_audits = {
            "callback_query": {
                "id": "cb3",
                "chat_instance": "1",
                "message": {"chat": {"id": 12345}, "message_id": 1},
                "from": {"id": 12345},
                "data": "view_audits_job_999",
            }
        }
        res = bot.handle_callback_query(upd_audits)
        assert res.ok is True


def test_notifier_flexible_signatures(tmp_path, monkeypatch):
    """Verify TelegramNotifier handles dict, str, and kwargs in send_video_preview & send_video."""
    fake_video = tmp_path / "test_video.mp4"
    fake_video.write_bytes(b"\x00\x00\x00 ftypmp42\x00\x00\x00\x00" + b"A" * 200)

    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)
    monkeypatch.setattr("src.integrity.verify_media_integrity", lambda p: {"passed": True, "sha256_hash": "abc12345"})
    monkeypatch.setattr("src.integrity.compute_file_sha256", lambda p: "abc12345")

    notifier = TelegramNotifier(bot_token="token", chat_id="12345")

    with patch.object(notifier.bot, "send_video_for_review", return_value=DeliveryResult(ok=True, message_id=555)) as mock_send_review:
        # Case 1: metadata dict
        res1 = notifier.send_video_preview(str(fake_video), metadata={"title": "Test 1"})
        assert res1.ok is True
        assert mock_send_review.call_args[0][1]["title"] == "Test 1"

        # Case 2: metadata string
        res2 = notifier.send_video_preview(str(fake_video), metadata="Test 2")
        assert res2.ok is True
        assert mock_send_review.call_args[0][1]["title"] == "Test 2"

        # Case 3: caption kwarg
        res3 = notifier.send_video_preview(str(fake_video), caption="Test 3")
        assert res3.ok is True
        assert mock_send_review.call_args[0][1]["caption"] == "Test 3"

    with patch.object(notifier.bot, "send_video", return_value=DeliveryResult(ok=True, message_id=777)) as mock_send_video:
        res4 = notifier.send_video(str(fake_video), caption="Direct Video")
        assert res4.ok is True
        mock_send_video.assert_called_once()


def test_interactive_telegram_bot_delegation(tmp_path, monkeypatch):
    """Verify InteractiveTelegramBot cleanly wraps TelegramReviewBot."""
    bot = InteractiveTelegramBot(token="token", chat_id="12345")
    assert bot.token == "token"
    assert bot.default_chat_id == "12345"

    with patch.object(bot.bot, "handle_text_command", return_value=DeliveryResult(ok=True)) as mock_cmd:
        bot.handle_command("12345", "/help")
        mock_cmd.assert_called_once()

    with patch.object(bot.bot, "handle_callback_query", return_value=DeliveryResult(ok=True)) as mock_cb:
        bot.handle_callback_query("cb_1", "12345", "show_status")
        mock_cb.assert_called_once()
