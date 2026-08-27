"""Regression tests: oversized HITL deliveries travel as a review proxy.

Production incident 2026-08-23 (run be966912): a healthy 66.9 MB longform
master was rejected by the cloud Bot API 50 MB preflight and the run ended
FAILED — no local Bot API server exists on this host. send_video_review must
now produce a deterministic compressed proxy for the review copy while the
untouched master remains the publication artifact, and stay fail-closed when
no compliant proxy can be produced.
"""

import os
import subprocess
from unittest.mock import patch

from review.domain import DeliveryResult
from review.telegram_bot import (
    TelegramReviewBot,
    _build_review_proxy,
    _validate_file_preflight,
)

_LIMIT_1MB = 1024 * 1024


def _render_clip(tmp_path, seconds: int = 4) -> str:
    """Real H.264/AAC clip used as a fake oversized master."""
    path = tmp_path / "master.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"testsrc=size=640x360:rate=30:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=1000:duration={seconds}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return str(path)


def _bot_with_limit(max_bytes: int) -> TelegramReviewBot:
    bot = TelegramReviewBot.__new__(TelegramReviewBot)
    bot.token = "test-token"
    bot.chat_id = "123"
    bot.base_url = "https://api.telegram.org"
    bot.max_file_size_bytes = max_bytes
    bot.req_timeout, bot.media_timeout = 10, 60
    return bot


class TestBuildReviewProxy:
    def test_small_file_needs_no_proxy(self, tmp_path):
        small = tmp_path / "small.mp4"
        small.write_bytes(b"\x00" * 1024)
        assert _build_review_proxy(str(small), _LIMIT_1MB * 100) is None

    def test_real_transcode_fits_budget(self, tmp_path):
        master = _render_clip(tmp_path)
        master_size = os.path.getsize(master)
        target_limit = master_size // 2
        # Force the proxy branch with an artificially reduced limit.
        proxy = _build_review_proxy(master, target_limit)
        assert proxy is not None
        assert os.path.basename(proxy).startswith("review_proxy_master")
        assert os.path.getsize(proxy) <= target_limit
        # Master untouched.
        assert os.path.exists(master)

    def test_fail_closed_when_ffmpeg_fails(self, tmp_path):
        master = _render_clip(tmp_path)
        with patch(
            "lib.ffmpeg.run_ffmpeg",
            side_effect=RuntimeError("boom"),
        ):
            assert _build_review_proxy(master, 100 * 1024) is None


class TestSendVideoReviewProxyPath:
    def _prepare(self, monkeypatch, tmp_path, master: str):
        # Bypass the test-environment mock so the real delivery path runs.
        monkeypatch.setattr("lib.video.is_test_environment", lambda: False)
        monkeypatch.setattr(
            "review.telegram_bot._get_video_duration",
            lambda _p: 4.0,
        )
        captured = {}

        def fake_send_video(self, **kwargs):
            captured["video_path"] = kwargs["video_path"]
            captured["caption"] = kwargs.get("caption")
            return DeliveryResult(ok=True, message_id=999)

        monkeypatch.setattr(TelegramReviewBot, "send_video", fake_send_video)
        return captured

    def test_oversized_master_travels_as_proxy(self, monkeypatch, tmp_path):
        master = _render_clip(tmp_path)
        master_size = os.path.getsize(master)
        target_limit = master_size // 2
        captured = self._prepare(monkeypatch, tmp_path, master)
        bot = _bot_with_limit(target_limit)

        res = bot.send_video_review(
            video_path=master,
            caption="Review: longform de prueba",
            job_id="job-proxy-1",
        )
        assert res.ok
        sent = captured["video_path"]
        assert sent != master
        assert os.path.basename(sent).startswith("review_proxy_")
        assert os.path.getsize(sent) <= target_limit
        assert "máster original se conserva" in (captured["caption"] or "")

    def test_unproxyable_file_stays_fail_closed(self, monkeypatch, tmp_path):
        monkeypatch.setattr("lib.video.is_test_environment", lambda: False)
        monkeypatch.setattr(
            "review.telegram_bot._get_video_duration",
            lambda _p: 90.0,
        )
        big = tmp_path / "big.mp4"
        big.write_bytes(b"\x00" * (2 * _LIMIT_1MB))
        with patch(
            "review.telegram_bot._build_review_proxy",
            return_value=None,
        ):
            bot = _bot_with_limit(_LIMIT_1MB)
            res = bot.send_video_review(
                video_path=str(big),
                caption="Review",
                job_id="job-failclosed",
            )
        assert not res.ok
        assert "50 MB" in (res.error or "") or "exceeds" in (res.error or "")


def test_preflight_error_mentions_size():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "x.bin")
        with open(p, "wb") as fh:
            fh.write(b"\x00" * 2048)
        err = _validate_file_preflight(p, 1024)
        assert err and ("size" in err.lower() or "exceeds" in err.lower())
