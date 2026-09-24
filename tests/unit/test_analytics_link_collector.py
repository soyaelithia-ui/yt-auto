"""Unit tests for YouTube link collection and harvesting (src/analytics/link_collector.py)."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.analytics.link_collector import (
    _fetch_channel_uploads_playlist_id,
    _fetch_video_details_batch,
    _harvest_playlist_video_ids,
    _resolve_channel_youtube_client,
    build_video_urls,
    collect_all_channel_links,
    collect_channel_links,
)
from src.core.inventory import get_published_inventory, record_published_inventory
from src.core.repository.migrations import migrate_database


def test_build_video_urls():
    urls = build_video_urls("xyz123")
    assert urls["watch"] == "https://www.youtube.com/watch?v=xyz123"
    assert urls["short"] == "https://youtu.be/xyz123"
    assert urls["shorts"] == "https://www.youtube.com/shorts/xyz123"


def test_harvest_playlist_video_ids():
    mock_youtube = MagicMock()
    mock_pl = MagicMock()
    mock_youtube.playlistItems.return_value = mock_pl

    # First page returns 2 items with nextPageToken, second page returns 1 item without token
    mock_pl.list.side_effect = [
        MagicMock(execute=MagicMock(return_value={
            "items": [
                {"contentDetails": {"videoId": "vid_1"}, "snippet": {"title": "Title 1", "description": "Desc 1", "publishedAt": "2026-01-01"}},
                {"contentDetails": {"videoId": "vid_2"}, "snippet": {"title": "Title 2", "description": "Desc 2", "publishedAt": "2026-01-02"}},
            ],
            "nextPageToken": "token_page_2",
        })),
        MagicMock(execute=MagicMock(return_value={
            "items": [
                {"contentDetails": {"videoId": "vid_3"}, "snippet": {"title": "Title 3", "description": "Desc 3", "publishedAt": "2026-01-03"}},
            ],
            "nextPageToken": None,
        })),
    ]

    items = _harvest_playlist_video_ids(mock_youtube, uploads_id="uploads_123", max_items=0)
    assert len(items) == 3
    assert [it["video_id"] for it in items] == ["vid_1", "vid_2", "vid_3"]


def test_fetch_video_details_batch():
    mock_youtube = MagicMock()
    mock_videos = MagicMock()
    mock_youtube.videos.return_value = mock_videos

    mock_videos.list.return_value.execute.return_value = {
        "items": [
            {"id": "v1", "statistics": {"viewCount": "100"}},
            {"id": "v2", "statistics": {"viewCount": "200"}},
        ]
    }

    details = _fetch_video_details_batch(mock_youtube, ["v1", "v2"])
    assert "v1" in details
    assert "v2" in details
    assert details["v1"]["statistics"]["viewCount"] == "100"


def test_fetch_channel_uploads_playlist_id():
    mock_youtube = MagicMock()
    mock_channels = MagicMock()
    mock_youtube.channels.return_value = mock_channels

    mock_channels.list.return_value.execute.return_value = {
        "items": [
            {"contentDetails": {"relatedPlaylists": {"uploads": "UU_test_uploads"}}}
        ]
    }
    uploads_id = _fetch_channel_uploads_playlist_id(mock_youtube)
    assert uploads_id == "UU_test_uploads"

    # Test error handling
    mock_channels.list.return_value.execute.side_effect = Exception("API error")
    assert _fetch_channel_uploads_playlist_id(mock_youtube) is None


def test_collect_channel_links_mock_environment():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name

        # In test environment, collect_channel_links generates mock items and persists them
        res = collect_channel_links(channel="horror", max_items=3, db_path=db_path, dry_run=False)

        assert res["ok"] is True
        assert res["channel"] == "horror"
        assert res["synced_count"] == 3
        assert len(res["items"]) == 3

        first_item = res["items"][0]
        assert "urls" in first_item
        assert "watch" in first_item["urls"]
        assert "shorts" in first_item["urls"]
        assert first_item["views"] >= 0
        assert first_item["comment_level"] in ("none", "low", "high")

        # Verify DB records
        records = get_published_inventory(db_path=db_path, channel="horror")
        assert len(records) == 3
        vids = {r.video_id for r in records}
        assert vids == {"mock_horror_001", "mock_horror_002", "mock_horror_003"}
        assert first_item["video_id"] in vids


def test_collect_channel_links_dry_run_no_db_write():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        migrate_database(db_path)

        res = collect_channel_links(channel="drama", max_items=2, db_path=db_path, dry_run=True)
        assert res["ok"] is True
        assert res["dry_run"] is True

        records = get_published_inventory(db_path=db_path, channel="drama")
        assert len(records) == 0


def test_collect_channel_links_live_mocked_youtube():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name

        mock_yt = MagicMock()
        mock_yt.channels.return_value.list.return_value.execute.return_value = {
            "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU_live_123"}}}]
        }
        mock_yt.playlistItems.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "contentDetails": {"videoId": "live_vid_99"},
                    "snippet": {"title": "Live Title", "description": "Live Desc", "publishedAt": "2026-03-01T00:00:00Z"},
                }
            ],
            "nextPageToken": None,
        }
        mock_yt.videos.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "live_vid_99",
                    "snippet": {"title": "Live Title", "description": "Live Desc"},
                    "statistics": {"viewCount": "5000", "likeCount": "250", "commentCount": "35"},
                    "contentDetails": {"duration": "PT45S"},
                }
            ]
        }

        with patch("src.analytics.link_collector.is_test_environment", return_value=False), \
             patch.dict(os.environ, {"TEST_MODE": "0"}), \
             patch("src.analytics.link_collector._resolve_channel_youtube_client", return_value=mock_yt):
            res = collect_channel_links(channel="horror", db_path=db_path, dry_run=False)

            assert res["ok"] is True
            assert res["synced_count"] == 1
            item = res["items"][0]
            assert item["video_id"] == "live_vid_99"
            assert item["views"] == 5000
            assert item["likes"] == 250
            assert item["comments"] == 35
            assert item["comment_level"] == "high"  # 35 comments >= 6 is high
            assert item["score"] > 50.0


def test_collect_all_channel_links():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name

        res = collect_all_channel_links(channels=["horror", "drama"], max_items_per_channel=2, db_path=db_path, dry_run=True)
        assert res["ok"] is True
        assert "horror" in res["channels"]
        assert "drama" in res["channels"]
        assert res["total_synced"] > 0


def test_collect_channel_links_mock_respects_max_items():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        migrate_database(db_path)

        res1 = collect_channel_links(channel="horror", max_items=1, db_path=db_path, dry_run=True)
        assert res1["ok"] is True
        assert len(res1["items"]) == 1

        res2 = collect_channel_links(channel="horror", max_items=2, db_path=db_path, dry_run=True)
        assert res2["ok"] is True
        assert len(res2["items"]) == 2


def test_collect_channel_links_preserves_rich_inventory_fields():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        migrate_database(db_path)

        # 1. Create an initial publication record with rich metadata
        initial_record = record_published_inventory(
            db_path=db_path,
            run_id="run-original-1234",
            story_id="story-original-5678",
            video_id="mock_horror_001",
            url="https://www.youtube.com/watch?v=mock_horror_001",
            channel="horror",
            title="Historia del Bosque",
            description="Una historia escalofriante",
            full_script="Este es el guion completo que no debe ser sobreescrito ni eliminado.",
            video_sha256="sha256_mock_horror_001_hash",
            drive_video_id="drive_mock_file_001",
            drive_backup_metadata={"drive_id": "drive_mock_file_001", "size": 1024},
            used_resources={"music": "creepy_ambient.mp3", "voice": "es-ES-AlvaroNeural"},
            music_track="creepy_ambient.mp3",
            pinned_comment="¿Qué harías en este bosque?",
            comment_status="pinned",
            comment_error=None,
            predictive_success_score=0.88,
            score_rationale="Gancho fuerte de suspenso",
        )

        assert initial_record.publication_id > 0
        assert initial_record.full_script == "Este es el guion completo que no debe ser sobreescrito ni eliminado."
        assert initial_record.video_sha256 == "sha256_mock_horror_001_hash"
        assert initial_record.used_resources == {"music": "creepy_ambient.mp3", "voice": "es-ES-AlvaroNeural"}
        assert initial_record.pinned_comment == "¿Qué harías en este bosque?"
        assert initial_record.comment_status == "pinned"
        assert initial_record.run_id == "run-original-1234"
        assert initial_record.story_id == "story-original-5678"

        # 2. Re-collect channel links (which generates mock_horror_001 and calls record_published_inventory
        # without full_script, video_sha256, used_resources, or pinned_comment)
        res = collect_channel_links(channel="horror", max_items=1, db_path=db_path, dry_run=False)
        assert res["ok"] is True
        assert res["synced_count"] == 1

        # 3. Query inventory to verify rich fields were completely preserved
        records = get_published_inventory(db_path=db_path, channel="horror")
        assert len(records) == 1
        updated = records[0]

        assert updated.video_id == "mock_horror_001"
        assert updated.full_script == "Este es el guion completo que no debe ser sobreescrito ni eliminado."
        assert updated.video_sha256 == "sha256_mock_horror_001_hash"
        assert updated.used_resources == {"music": "creepy_ambient.mp3", "voice": "es-ES-AlvaroNeural"}
        assert updated.music_track == "creepy_ambient.mp3"
        assert updated.pinned_comment == "¿Qué harías en este bosque?"
        assert updated.comment_status == "pinned"
        assert updated.drive_video_id == "drive_mock_file_001"
        assert updated.drive_backup_metadata == {"drive_id": "drive_mock_file_001", "size": 1024}
        assert updated.run_id == "run-original-1234"
        assert updated.story_id == "story-original-5678"
        assert updated.predictive_success_score == 0.88
        assert updated.score_rationale == "Gancho fuerte de suspenso"

        # Metrics should have been updated by link collection
        assert updated.view_count > 0
        assert updated.actual_success_score > 0.0
