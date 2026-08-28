from pathlib import Path
from unittest.mock import patch

from src.telegram.notifier import TelegramNotifier, send_telegram_message


def test_send_status_update_keeps_job_id_and_step():
    with patch("src.telegram.notifier._send_message") as mock_send:
        notifier = TelegramNotifier(bot_token="tok", chat_id="123")
        notifier.send_status_update("cron pipeline ok", job_id="JOB-001", step="compose")
    text = mock_send.call_args.kwargs["message"]
    assert "JOB-001" in text
    assert "compose" in text


def test_send_render_notification_keeps_emoji_and_job_id():
    with patch("src.telegram.notifier._send_message") as mock_send:
        notifier = TelegramNotifier(bot_token="tok", chat_id="123")
        notifier.send_render_notification("JOB-002", "render", "completed")
    text = mock_send.call_args.kwargs["message"]
    assert "✅" in text
    assert "JOB-002" in text


def test_send_render_notification_failure_uses_cross_icon():
    with patch("src.telegram.notifier._send_message") as mock_send:
        notifier = TelegramNotifier(bot_token="tok", chat_id="123")
        notifier.send_render_notification("JOB-003", "render", "failed")
    text = mock_send.call_args.kwargs["message"]
    assert "❌" in text
    assert "JOB-003" in text


def test_send_telegram_message_passes_text_as_message_kwarg():
    """Regression: the body must go to `message`, never land in token/chat_id."""
    with patch("src.telegram.notifier._send_message") as mock_send:
        mock_send.return_value.ok = True
        send_telegram_message(text="Hola pipeline", chat_id="999", bot_token="tok")
    kwargs = mock_send.call_args.kwargs
    assert kwargs.get("message") == "Hola pipeline"
    assert kwargs.get("chat_id") == 999
    assert kwargs.get("bot_token") == "tok"


def test_send_telegram_message_non_numeric_chat_id_is_safe():
    with patch("src.telegram.notifier._send_message") as mock_send:
        mock_send.return_value.ok = True
        send_telegram_message(text="hola", chat_id="no-numerico", bot_token="tok")
    assert mock_send.call_args.kwargs.get("chat_id") is None


def test_review_message_never_leaks_local_paths(tmp_path):
    from review.telegram_bot import _review_message

    msg = _review_message(title="Mi historia", review_window_hours=6)
    assert "Nuevo vídeo para revisión" in msg
    assert "Título: Mi historia" in msg
    assert "Se publicará automáticamente en ~6 h" in msg
    assert "file://" not in msg
    assert str(tmp_path) not in msg


def test_review_message_includes_drive_url_when_provided():
    from review.telegram_bot import _review_message

    msg = _review_message(
        title="Mi historia",
        review_window_hours=6,
        drive_url="https://drive.google.com/file/d/abc/view",
    )
    assert "Drive: https://drive.google.com/file/d/abc/view" in msg


def test_send_video_review_caption_is_clean_and_noise_free(tmp_path, monkeypatch):
    from review.telegram_bot import TelegramReviewBot

    video = tmp_path / "sample.mp4"
    video.write_bytes(b"dummy")
    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)
    bot = TelegramReviewBot(token="tok", chat_id="123")

    with patch("review.telegram_bot.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True, "result": {"message_id": 99}}
        res = bot.send_video_review(
            video_path=str(video),
            caption="Vídeo Asombroso",
            job_id="job-100",
            drive_url="https://drive.google.com/file/d/xyz123/view",
        )

    assert res.ok
    sent_caption = mock_post.call_args.kwargs["data"]["caption"]
    assert "Vídeo Asombroso" in sent_caption
    assert "⏱️ Duración:" in sent_caption
    assert "📁 Drive: https://drive.google.com/file/d/xyz123/view" in sent_caption
    # Noise must be absent
    assert "Cobertura:" not in sent_caption
    assert "Generado:" not in sent_caption


def test_oversize_video_fails_closed_without_sending_a_fallback(tmp_path, monkeypatch):
    from review.telegram_bot import TelegramReviewBot

    video = tmp_path / "big.mp4"
    with open(video, "wb") as f:
        f.truncate(55 * 1024 * 1024)

    # Cloud mode (default 50MB limit)
    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org")
    monkeypatch.setenv("TELEGRAM_LOCAL", "false")
    monkeypatch.delenv("TELEGRAM_MAX_FILE_SIZE_MB", raising=False)
    bot = TelegramReviewBot(token="tok", chat_id="123", base_url="https://api.telegram.org")
    with patch("lib.video.is_test_environment", return_value=False):
        res = bot.send_video_review(video_path=str(video), caption="Mi vídeo grande")

    assert not res.ok
    assert "exceeds" in (res.error or "") and "limit" in (res.error or "")
