"""Unit tests for Daemon 24h Maintenance Sweep (src/daemon.py)."""
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.repository.migrations import connect, migrate_database
from src.daemon import _run_24h_maintenance_sweep


def test_maintenance_sweep_updates_scheduler_state():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        migrate_database(db_path)

        with connect(db_path) as conn:
            # Check initial last_24h_sweep_at is None or 0
            row = conn.execute("SELECT last_24h_sweep_at FROM scheduler_state WHERE scheduler_id = 1").fetchone()
            initial_val = row["last_24h_sweep_at"] if row else None

        # Execute maintenance sweep in dry_run mode
        with patch("src.analytics.scoring.YouTubeAnalyticsSyncer") as mock_syncer:
            mock_instance = MagicMock()
            mock_instance.fetch_video_statistics.return_value = {
                "view_count": 100,
                "like_count": 5,
                "comment_count": 1,
                "retention_rate_pct": 50.0,
            }
            mock_syncer.return_value = mock_instance

            res = _run_24h_maintenance_sweep(db_path=db_path, channel="all", dry_run=True)
            assert res["ok"] is True

        with connect(db_path) as conn:
            row_after = conn.execute("SELECT last_24h_sweep_at FROM scheduler_state WHERE scheduler_id = 1").fetchone()
            assert row_after is not None
            assert row_after["last_24h_sweep_at"] is not None
            assert int(row_after["last_24h_sweep_at"]) > 0


def test_maintenance_sweep_graceful_on_exception():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        migrate_database(db_path)

        # Mock failure in scoring sync
        with patch("src.analytics.scoring.sync_and_score_channel_publications", side_effect=RuntimeError("YouTube Outage")):
            # Should NOT raise unhandled exception
            res = _run_24h_maintenance_sweep(db_path=db_path, channel="moku", dry_run=True)
            assert res["ok"] is False
            assert "YouTube Outage" in str(res.get("error", ""))


def test_maintenance_sweep_channel_none_resolves_all_active_channels():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        migrate_database(db_path)

        with patch("src.analytics.scoring.YouTubeAnalyticsSyncer") as mock_syncer:
            mock_instance = MagicMock()
            mock_instance.fetch_video_statistics.return_value = {
                "view_count": 0,
                "like_count": 0,
                "comment_count": 0,
                "retention_rate_pct": 0.0,
            }
            mock_syncer.return_value = mock_instance

            # channel=None should process all active channels without ValueError
            from src.core.channel_profile import ChannelProfileRegistry
            expected_channels = list(ChannelProfileRegistry.list_active_channel_ids())
            res = _run_24h_maintenance_sweep(db_path=db_path, channel=None, dry_run=True)
            assert res["ok"] is True
            assert "channels" in res
            assert res["channels"] == expected_channels


def test_handle_sweep_24h_live_flag_propagates_dry_run_false():
    import argparse
    from src.cli.handlers.analytics import handle_sweep_24h

    args_live = argparse.Namespace(
        channel="moku",
        db_path=":memory:",
        live=True,
        force=True,
    )
    with patch("src.cli.handlers.analytics._run_24h_maintenance_sweep") as mock_sweep:
        mock_sweep.return_value = {"ok": True}
        ret = handle_sweep_24h(args_live)
        assert ret == 0
        mock_sweep.assert_called_once_with(
            db_path=":memory:",
            channel="moku",
            dry_run=False,
            force=True,
        )

    args_default = argparse.Namespace(
        channel="moku",
        db_path=":memory:",
        force=True,
    )
    with patch("src.cli.handlers.analytics._run_24h_maintenance_sweep") as mock_sweep:
        mock_sweep.return_value = {"ok": True}
        ret = handle_sweep_24h(args_default)
        assert ret == 0
        mock_sweep.assert_called_once_with(
            db_path=":memory:",
            channel="moku",
            dry_run=True,
            force=True,
        )
