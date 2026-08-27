"""Unit tests for admin text commands on the Telegram review bot."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from review.telegram_bot import TelegramReviewBot


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "42")
    instance = TelegramReviewBot(token="tok", chat_id="100")
    return instance


def _update(text: str, user_id: str = "42") -> dict:
    return {"message": {"chat": {"id": "100"}, "from": {"id": user_id}, "text": text}}


def test_rejects_unauthorized_user(bot):
    result = bot.handle_text_command(_update("/stats abc", user_id="999"))
    assert result.ok is False
    assert "Unauthorized" in (result.error or "")


def test_rejects_unauthorized_chat(bot):
    update = {
        "message": {
            "chat": {"id": "777"},
            "from": {"id": "42"},
            "text": "/stats abc",
        }
    }
    assert bot.handle_text_command(update).ok is False


def test_ignores_non_commands(bot):
    assert bot.handle_text_command(_update("hola")).ok is False


def test_unknown_command_lists_help(bot):
    with patch(
        "review.telegram_bot.send_telegram_message"
    ) as send:
        send.return_value = MagicMock(ok=True)
        bot.handle_text_command(_update("/nope"))
    body = send.call_args.kwargs.get("message", "")
    assert "Comando desconocido" in body


def test_missing_video_id_prompts_usage(bot):
    with patch(
        "review.telegram_bot.send_telegram_message"
    ) as send:
        send.return_value = MagicMock(ok=True)
        bot.handle_text_command(_update("/stats"))
    assert "Falta <video_id>" in send.call_args.kwargs.get("message", "")


def test_stats_command_formats_snapshot(bot):
    with (
        patch(
            "review.telegram_bot.send_telegram_message"
        ) as send,
        patch("src.youtube.control.get_video_stats") as stats,
    ):
        stats.return_value = {
            "ok": True,
            "video_id": "abc",
            "title": "Título",
            "views": 10,
            "likes": 2,
            "comments": 1,
            "privacyStatus": "public",
            "uploadStatus": "processed",
        }
        send.return_value = MagicMock(ok=True)
        bot.handle_text_command(_update("/stats abc aelithia"))
    stats.assert_called_once_with("abc", "aelithia")
    body = send.call_args.kwargs.get("message", "")
    assert "Título" in body and "👁 10" in body


def test_del_requires_explicit_confirmation(bot):
    """`/del` must only preview; only `/delsi` may call delete_video."""
    with (
        patch("review.telegram_bot.send_telegram_message") as send,
        patch("src.youtube.control.delete_video") as delete,
        patch("src.youtube.control.get_video_stats") as stats,
    ):
        stats.return_value = {"ok": True, "title": "X"}
        send.return_value = MagicMock(ok=True)
        bot.handle_text_command(_update("/del abc moku"))
    delete.assert_not_called()
    body = send.call_args.kwargs.get("message", "")
    assert "/delsi abc moku" in body


def test_delsi_executes_delete(bot):
    with (
        patch("review.telegram_bot.send_telegram_message") as send,
        patch("src.youtube.control.delete_video") as delete,
    ):
        delete.return_value = {"ok": True, "video_id": "abc"}
        send.return_value = MagicMock(ok=True)
        bot.handle_text_command(_update("/delsi abc moku"))
    delete.assert_called_once_with("abc", "moku")


# ---------------------------------------------------------------------------
# Button flow (inline keyboards)
# ---------------------------------------------------------------------------

def _cbq(data: str, user_id: str = "42") -> dict:
    return {
        "callback_query": {
            "id": "cbid",
            "from": {"id": user_id},
            "data": data,
            "message": {"chat": {"id": "100"}, "message_id": 55},
        }
    }


def test_menu_button_shows_action_keyboard(bot):
    with (
        patch("review.telegram_bot.send_telegram_message") as send,
        patch.object(bot, "answer_callback_query"),
    ):
        send.return_value = MagicMock(ok=True)
        result = bot.handle_control_callback(_cbq("ctl:menu"))
    assert result.ok is True
    markup = send.call_args.kwargs.get("reply_markup")
    actions = [btn["callback_data"] for row in markup["inline_keyboard"] for btn in row]
    assert actions == ["ctl:act:stats", "ctl:act:priv", "ctl:act:pub", "ctl:act:unlist", "ctl:act:del"]


def test_act_lists_recent_videos_as_buttons(bot):
    videos = [
        {"story_id": "s1", "video_id": "vid1", "channel": "moku", "title": "Historia uno"},
        {"story_id": "s2", "video_id": "vid2", "channel": "aelithia", "title": "Drama dos"},
    ]
    with (
        patch.object(TelegramReviewBot, "_recent_publications", return_value=videos),
        patch.object(bot, "edit_message_text") as edit,
        patch.object(bot, "answer_callback_query"),
    ):
        result = bot.handle_control_callback(_cbq("ctl:act:priv"))
    assert result.ok is True
    markup = edit.call_args.kwargs.get("reply_markup")
    datas = [btn["callback_data"] for row in markup["inline_keyboard"] for btn in row]
    assert "ctl:go:priv:vid1:moku" in datas
    assert "ctl:go:priv:vid2:aelithia" in datas


def test_go_privacy_executes_directly(bot):
    with (
        patch.object(bot, "edit_message_text") as edit,
        patch.object(bot, "answer_callback_query"),
        patch("src.youtube.control.set_video_privacy") as privacy,
    ):
        privacy.return_value = {
            "ok": True, "action": "privacy", "video_id": "vid1",
            "previous": "public", "privacyStatus": "private",
        }
        bot.handle_control_callback(_cbq("ctl:go:priv:vid1:moku"))
    privacy.assert_called_once_with("vid1", "private", "moku")


def test_del_previews_and_yes_deletes_via_buttons(bot):
    with (
        patch.object(bot, "edit_message_text") as edit,
        patch.object(bot, "answer_callback_query"),
        patch("src.youtube.control.get_video_stats") as stats,
    ):
        stats.return_value = {"ok": True, "title": "Historia uno"}
        bot.handle_control_callback(_cbq("ctl:go:del:vid1:moku"))
    body = edit.call_args.args[0] if edit.call_args.args else edit.call_args.kwargs.get("body", "")
    markup = edit.call_args.kwargs.get("reply_markup")
    confirm_datas = [btn["callback_data"] for row in markup["inline_keyboard"] for btn in row]
    assert "ctl:yes:vid1:moku" in confirm_datas

    with (
        patch.object(bot, "edit_message_text") as edit2,
        patch.object(bot, "answer_callback_query"),
        patch("src.youtube.control.delete_video") as delete,
    ):
        delete.return_value = {"ok": True, "video_id": "vid1"}
        bot.handle_control_callback(_cbq("ctl:yes:vid1:moku"))
    delete.assert_called_once_with("vid1", "moku")
    assert edit2.called


def test_control_callbacks_reject_unauthorized_user(bot):
    result = bot.handle_control_callback(_cbq("ctl:menu", user_id="999"))
    assert result.ok is False


def test_cancel_button_replies_cancelled(bot):
    with (
        patch.object(bot, "edit_message_text") as edit,
        patch.object(bot, "answer_callback_query"),
    ):
        result = bot.handle_control_callback(_cbq("ctl:cancel"))
    assert result.ok is True
    body = edit.call_args.args[0] if edit.call_args.args else ""
    assert "Cancelado" in body
