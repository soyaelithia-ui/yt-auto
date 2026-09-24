"""Unit tests for YouTube pinned comment dispatcher & lifecycle manager (src/youtube/comments.py)."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.youtube.comments import PinnedCommentResult, post_pinned_comment


def test_pinned_comment_result_to_dict():
    res = PinnedCommentResult(
        video_id="v123",
        status="posted",
        comment_id="c456",
        error=None,
        text="Sample text",
    )
    d = res.to_dict()
    assert d == {
        "video_id": "v123",
        "status": "posted",
        "comment_id": "c456",
        "error": None,
        "text": "Sample text",
    }


def test_post_pinned_comment_empty_inputs():
    res = post_pinned_comment("", "some text")
    assert res.status == "failed"
    assert "Missing video_id" in (res.error or "")

    res2 = post_pinned_comment("v123", "   ")
    assert res2.status == "failed"
    assert "Missing video_id" in (res2.error or "")


def test_post_pinned_comment_mock_environment():
    res = post_pinned_comment("vid_abc", "¿Cuál fue tu parte favorita?")
    assert res.status == "posted"
    assert res.comment_id == "mock_comment_vid_abc"
    assert res.error is None
    assert res.text == "¿Cuál fue tu parte favorita?"


def test_post_pinned_comment_successful_api_call():
    mock_service = MagicMock()
    mock_ct = MagicMock()
    mock_service.commentThreads.return_value = mock_ct
    mock_ct.insert.return_value.execute.return_value = {"id": "comment_real_999"}

    with patch("src.youtube.comments.is_test_environment", return_value=False):
        res = post_pinned_comment(
            video_id="vid_live",
            comment_text="Pinned discussion question",
            youtube_service=mock_service,
        )

    assert res.status == "posted"
    assert res.comment_id == "comment_real_999"
    assert res.error is None
    mock_ct.insert.assert_called_once()


def test_post_pinned_comment_comments_disabled_classification():
    mock_service = MagicMock()
    mock_ct = MagicMock()
    mock_service.commentThreads.return_value = mock_ct
    mock_ct.insert.return_value.execute.side_effect = Exception(
        "<HttpError 403: 'The video has comments disabled. (commentsDisabled)'>"
    )

    with patch("src.youtube.comments.is_test_environment", return_value=False):
        res = post_pinned_comment(
            video_id="vid_disabled",
            comment_text="Pinned text",
            youtube_service=mock_service,
        )

    assert res.status == "disabled"
    assert res.comment_id is None
    assert "commentsDisabled" in (res.error or "")


def test_post_pinned_comment_generic_failure_classification():
    mock_service = MagicMock()
    mock_ct = MagicMock()
    mock_service.commentThreads.return_value = mock_ct
    mock_ct.insert.return_value.execute.side_effect = Exception("quotaExceeded: Daily limit reached")

    with patch("src.youtube.comments.is_test_environment", return_value=False):
        res = post_pinned_comment(
            video_id="vid_quota",
            comment_text="Pinned text",
            youtube_service=mock_service,
        )

    assert res.status == "failed"
    assert res.comment_id is None
    assert "quotaExceeded" in (res.error or "")


def test_post_pinned_comment_no_credentials():
    with patch("src.youtube.comments.is_test_environment", return_value=False), \
         patch.dict(os.environ, {"TEST_MODE": "0", "MOCK_YOUTUBE_UPLOAD": "0"}), \
         patch("src.youtube.comments._resolve_youtube_service", return_value=None):
        res = post_pinned_comment(
            video_id="vid_no_creds",
            comment_text="Pinned text",
            youtube_service=None,
        )

    assert res.status == "failed"
    assert "credentials not found" in (res.error or "")
