"""AUTO_APPROVE path: allowed with review secrets; does not bypass publish creds."""
from __future__ import annotations

import os

import pytest


def test_auto_approve_allowed_when_review_secrets_present(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_MODE", "0")
    monkeypatch.setenv("AUTO_APPROVE", "1")
    monkeypatch.setenv("ENABLE_AUTO_PUBLISH_SWEEP", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:fake")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "456")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "123")
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    monkeypatch.setenv("VIDEO_REVIEW_DB_PATH", str(review_dir / "review.db"))

    import src.config as cfg

    # Should not raise solely due to AUTO_APPROVE / sweep flags
    cfg.validate_runtime_config(require_review=True)


def test_test_mode_still_blocked_in_production_review(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("AUTO_APPROVE", "0")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:fake")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "456")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "123")
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    monkeypatch.setenv("VIDEO_REVIEW_DB_PATH", str(review_dir / "review.db"))

    import src.config as cfg

    with pytest.raises(RuntimeError, match="TEST_MODE"):
        cfg.validate_runtime_config(require_review=True)
