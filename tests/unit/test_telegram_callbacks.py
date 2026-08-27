import json
from unittest.mock import patch

from review.db import ReviewStateStore
from review.domain import ReviewJob, ReviewStatus
from review.telegram_bot import TelegramReviewBot


class _TelegramResponse:
    status_code = 200
    text = ""

    @staticmethod
    def json():
        return {"ok": True, "result": {"message_id": 77}}


def _job(store, chat_id=123):
    return store.create_job(
        ReviewJob(
            job_id="run-001",
            channel="moku",
            title="Historia",
            original_video_path="/tmp/video.mp4",
            status=ReviewStatus.PENDING_REVIEW.value,
            telegram_chat_id=chat_id,
            telegram_message_id=55,
        )
    )


def _update(data, chat_id=123, user_id=456):
    return {
        "update_id": 10,
        "callback_query": {
            "id": "callback-1",
            "data": data,
            "from": {"id": user_id},
            "message": {"message_id": 55, "chat": {"id": chat_id}},
        },
    }


def test_review_video_sends_inline_keyboard(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")
    monkeypatch.setattr("lib.video.is_test_environment", lambda: False)
    bot = TelegramReviewBot(token="token", chat_id="123")

    with patch("review.telegram_bot.requests.post", return_value=_TelegramResponse()) as post:
        result = bot.send_video_review(str(video), caption="Historia", job_id="run-001")

    assert result.ok
    keyboard = json.loads(post.call_args.kwargs["data"]["reply_markup"])
    assert [button["callback_data"] for button in keyboard["inline_keyboard"][0]] == [
        "approve:run-001",
        "redo:run-001",
        "reject:run-001",
        "info:run-001",
    ]


def test_reject_callback_is_authorized_and_transitions_job(tmp_path, monkeypatch):
    store = ReviewStateStore(str(tmp_path / "review.db"))
    _job(store)
    monkeypatch.setenv("VIDEO_REVIEW_DB_PATH", str(tmp_path / "review.db"))
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "456")
    bot = TelegramReviewBot(token="token", chat_id="123")

    with patch("review.telegram_bot.requests.post", return_value=_TelegramResponse()):
        result = bot.handle_callback_query(_update("reject:run-001"))

    assert result.ok
    assert store.get_job("run-001").status == ReviewStatus.REJECTED.value


def test_callback_from_other_chat_fails_closed(tmp_path, monkeypatch):
    store = ReviewStateStore(str(tmp_path / "review.db"))
    _job(store)
    monkeypatch.setenv("VIDEO_REVIEW_DB_PATH", str(tmp_path / "review.db"))
    bot = TelegramReviewBot(token="token", chat_id="123")

    with patch("review.telegram_bot.requests.post", return_value=_TelegramResponse()):
        result = bot.handle_callback_query(_update("approve:run-001", chat_id=999))

    assert not result.ok
    assert store.get_job("run-001").status == ReviewStatus.PENDING_REVIEW.value


def test_redo_callback_does_not_mutate_job(tmp_path, monkeypatch):
    store = ReviewStateStore(str(tmp_path / "review.db"))
    _job(store)
    monkeypatch.setenv("VIDEO_REVIEW_DB_PATH", str(tmp_path / "review.db"))
    bot = TelegramReviewBot(token="token", chat_id="123")

    with patch("review.telegram_bot.requests.post", return_value=_TelegramResponse()):
        result = bot.handle_callback_query(_update("redo:run-001"))

    assert not result.ok
    assert store.get_job("run-001").status == ReviewStatus.PENDING_REVIEW.value
