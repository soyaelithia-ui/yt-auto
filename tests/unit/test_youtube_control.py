"""Unit tests for the YouTube control plane (delete / privacy / stats)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.youtube import control as ctl


@pytest.fixture
def fake_service():
    """A youtube service mock with videos().list/delete/update wired."""
    service = MagicMock()
    videos = service.videos.return_value
    videos.list.return_value.execute.return_value = {
        "items": [
            {
                "snippet": {"channelId": "UC_expected", "title": "Historia de terror"},
                "status": {"privacyStatus": "public", "uploadStatus": "processed"},
                "statistics": {"viewCount": "1234", "likeCount": "56", "commentCount": "7"},
            }
        ]
    }
    return service


def _patch_service(fake_service):
    return patch.object(ctl, "_service_for_channel", return_value=fake_service)


def _patch_channel_id(monkeypatch, value="UC_expected"):
    monkeypatch.setattr(
        ctl,
        "expected_channel_id",
        lambda channel: value,
    )


def test_delete_video_success_verifies_ownership(fake_service, monkeypatch):
    _patch_channel_id(monkeypatch)
    with _patch_service(fake_service):
        result = ctl.delete_video("abc123", channel="moku")
    assert result == {"ok": True, "action": "deleted", "video_id": "abc123", "channel": "moku"}
    fake_service.videos.return_value.delete.assert_called_once_with(id="abc123")


def test_delete_rejects_foreign_channel(fake_service, monkeypatch):
    _patch_channel_id(monkeypatch, value="UC_other")
    with _patch_service(fake_service):
        result = ctl.delete_video("abc123", channel="moku")
    assert result["ok"] is False
    assert "no al canal" in result["error"]
    fake_service.videos.return_value.delete.assert_not_called()


def test_delete_rejects_unknown_video(fake_service, monkeypatch):
    _patch_channel_id(monkeypatch)
    fake_service.videos.return_value.list.return_value.execute.return_value = {"items": []}
    with _patch_service(fake_service):
        result = ctl.delete_video("ghost", channel="moku")
    assert result["ok"] is False
    assert "no encontrado" in result["error"].lower()


def test_delete_requires_video_id():
    assert ctl.delete_video("")["ok"] is False


def test_privacy_change_success(fake_service, monkeypatch):
    _patch_channel_id(monkeypatch)
    with _patch_service(fake_service):
        result = ctl.set_video_privacy("abc123", "private", channel="moku")
    assert result["ok"] is True
    assert result["previous"] == "public"
    assert result["privacyStatus"] == "private"
    fake_service.videos.return_value.update.assert_called_once_with(
        part="status",
        body={"id": "abc123", "status": {"privacyStatus": "private"}},
    )


def test_privacy_noop_when_already_set(fake_service, monkeypatch):
    _patch_channel_id(monkeypatch)
    fake_service.videos.return_value.list.return_value.execute.return_value["items"][0][
        "status"
    ]["privacyStatus"] = "private"
    with _patch_service(fake_service):
        result = ctl.set_video_privacy("abc123", "private", channel="moku")
    assert result["ok"] is True
    assert result["action"] == "noop"
    fake_service.videos.return_value.update.assert_not_called()


def test_privacy_rejects_invalid_value():
    assert ctl.set_video_privacy("abc", "stealth")["ok"] is False


def test_stats_snapshot(fake_service, monkeypatch):
    _patch_channel_id(monkeypatch)
    with _patch_service(fake_service):
        result = ctl.get_video_stats("abc123", channel="moku")
    assert result["ok"] is True
    assert result["views"] == 1234
    assert result["likes"] == 56
    assert result["comments"] == 7
    assert result["privacyStatus"] == "public"


def test_stats_api_error_is_contained(fake_service, monkeypatch):
    _patch_channel_id(monkeypatch)
    fake_service.videos.return_value.list.return_value.execute.side_effect = RuntimeError("boom")
    with _patch_service(fake_service):
        result = ctl.get_video_stats("abc123", channel="moku")
    assert result["ok"] is False
    assert "boom" in result["error"]


def test_verify_ownership_direct_import_and_execution(fake_service, monkeypatch):
    """Direct verification of _verify_ownership without mock patching."""
    _patch_channel_id(monkeypatch, value="UC_expected")
    item = ctl._verify_ownership(fake_service, "abc123", "moku")
    assert item["snippet"]["channelId"] == "UC_expected"

    # Mismatch raises PermissionError
    _patch_channel_id(monkeypatch, value="UC_different")
    with pytest.raises(PermissionError, match="no al canal configurado"):
        ctl._verify_ownership(fake_service, "abc123", "moku")

    # Not found raises LookupError
    fake_service.videos.return_value.list.return_value.execute.return_value = {"items": []}
    with pytest.raises(LookupError, match="Video no encontrado"):
        ctl._verify_ownership(fake_service, "missing_vid", "moku")

