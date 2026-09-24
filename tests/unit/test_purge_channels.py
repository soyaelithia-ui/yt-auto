"""Unit tests for Channel Video Purge and Safety Safeguards."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from src.cli.purge_channels import (
    PurgeItemResult,
    PurgeReport,
    purge_channel_videos,
)


@pytest.fixture(autouse=True)
def mock_expected_channel():
    with patch("src.cli.purge_channels.expected_channel_id") as mock_exp:
        def _get_id(ch):
            val = ch.value if hasattr(ch, "value") else str(ch)
            if val in ("moku", "horror"):
                return "UC8sStaR-cwz-x7MD4XKNUKA"
            return "UC_SCIFI_12345"
        mock_exp.side_effect = _get_id
        yield mock_exp


class TestPurgeChannelsDryRun:
    """Requirement 1: Non-destructive Dry-Run Catalog Inspection."""

    @patch("src.cli.purge_channels._service_for_channel")
    def test_dry_run_lists_candidates_without_deleting(self, mock_service):
        mock_yt = MagicMock()
        mock_service.return_value = mock_yt

        mock_yt.search().list().execute.return_value = {
            "items": [
                {
                    "id": {"videoId": f"vid_{i}"},
                    "snippet": {
                        "title": f"Video {i}",
                        "channelId": "UC8sStaR-cwz-x7MD4XKNUKA",
                    },
                }
                for i in range(5)
            ]
        }

        report = purge_channel_videos(channel="moku", dry_run=True)

        assert isinstance(report, PurgeReport)
        assert report.channel in ("moku", "horror")
        assert report.total_found == 5
        assert report.deleted_count == 0
        assert report.skipped_count == 0
        assert report.failed_count == 0
        assert len(report.items) == 5
        assert all(item.status == "dry_run" for item in report.items)
        assert not mock_yt.videos().delete.called

    @patch("src.cli.purge_channels._service_for_channel")
    def test_dry_run_empty_channel(self, mock_service):
        mock_yt = MagicMock()
        mock_service.return_value = mock_yt
        mock_yt.search().list().execute.return_value = {"items": []}

        report = purge_channel_videos(channel="moku", dry_run=True)
        assert report.total_found == 0
        assert report.deleted_count == 0
        assert len(report.items) == 0


class TestPurgeChannelsConfirmation:
    """Requirement 2: Explicit Confirmation Safeguard (Zero Blocking input())."""

    @patch("src.cli.purge_channels._service_for_channel")
    @patch("builtins.input")
    @patch("time.sleep")
    def test_live_purge_confirmed_with_delete_token(
        self, mock_sleep, mock_input, mock_service
    ):
        mock_yt = MagicMock()
        mock_service.return_value = mock_yt
        mock_yt.search().list().execute.return_value = {
            "items": [
                {
                    "id": {"videoId": "vid_1"},
                    "snippet": {
                        "title": "Video 1",
                        "channelId": "UC8sStaR-cwz-x7MD4XKNUKA",
                    },
                }
            ]
        }
        mock_yt.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "vid_1",
                    "snippet": {
                        "title": "Video 1",
                        "channelId": "UC8sStaR-cwz-x7MD4XKNUKA",
                    },
                }
            ]
        }
        mock_yt.videos().delete().execute.return_value = {}

        report = purge_channel_videos(
            channel="moku",
            dry_run=False,
            force=False,
            confirm_input=lambda _msg: "DELETE",
        )

        assert report.deleted_count == 1
        assert report.items[0].status == "deleted"
        assert mock_yt.videos().delete().execute.called
        mock_input.assert_not_called()

    @patch("src.cli.purge_channels._service_for_channel")
    @patch("builtins.input")
    def test_live_purge_aborted_on_invalid_token(self, mock_input, mock_service):
        mock_yt = MagicMock()
        mock_service.return_value = mock_yt
        mock_yt.search().list().execute.return_value = {
            "items": [
                {
                    "id": {"videoId": "vid_1"},
                    "snippet": {
                        "title": "Video 1",
                        "channelId": "UC8sStaR-cwz-x7MD4XKNUKA",
                    },
                }
            ]
        }

        report = purge_channel_videos(
            channel="moku",
            dry_run=False,
            force=False,
            confirm_input=lambda _msg: "no",
        )

        assert report.deleted_count == 0
        assert report.skipped_count == 1
        assert not mock_yt.videos().delete().execute.called
        mock_input.assert_not_called()

    @patch("src.cli.purge_channels._service_for_channel")
    @patch("builtins.input")
    def test_live_purge_aborted_without_confirm_input_or_force(
        self, mock_input, mock_service
    ):
        mock_yt = MagicMock()
        mock_service.return_value = mock_yt
        mock_yt.search().list().execute.return_value = {
            "items": [
                {
                    "id": {"videoId": "vid_1"},
                    "snippet": {
                        "title": "Video 1",
                        "channelId": "UC8sStaR-cwz-x7MD4XKNUKA",
                    },
                }
            ]
        }

        report = purge_channel_videos(
            channel="moku",
            dry_run=False,
            force=False,
            confirm_input=None,
        )

        assert report.deleted_count == 0
        assert report.skipped_count == 1
        assert report.items[0].status == "skipped"
        assert "Confirmacion requerida" in (report.items[0].error or "")
        assert not mock_yt.videos().delete().execute.called
        mock_input.assert_not_called()


class TestPurgeChannelsOwnershipAndQuota:
    """Requirements 3 & 4: Ownership Validation and Quota Safeguards."""

    @patch("src.cli.purge_channels._service_for_channel")
    @patch("time.sleep")
    def test_ownership_mismatch_skips_item(self, mock_sleep, mock_service):
        mock_yt = MagicMock()
        mock_service.return_value = mock_yt
        # Video belongs to different channel
        mock_yt.search().list().execute.return_value = {
            "items": [
                {
                    "id": {"videoId": "foreign_vid"},
                    "snippet": {
                        "title": "Foreign Video",
                        "channelId": "UC_OTHER_CHANNEL_ID",
                    },
                }
            ]
        }
        mock_yt.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "foreign_vid",
                    "snippet": {
                        "title": "Foreign Video",
                        "channelId": "UC_OTHER_CHANNEL_ID",
                    },
                }
            ]
        }

        report = purge_channel_videos(channel="moku", dry_run=False, force=True)

        assert report.deleted_count == 0
        assert report.skipped_count == 1
        assert report.items[0].status == "skipped"
        assert "pertenece al canal" in (report.items[0].error or "")

    @patch("src.cli.purge_channels._service_for_channel")
    @patch("time.sleep")
    def test_quota_exceeded_stops_further_deletions(
        self, mock_sleep, mock_service
    ):
        from googleapiclient.errors import HttpError
        from httplib2 import Response

        mock_yt = MagicMock()
        mock_service.return_value = mock_yt

        # 5 items
        mock_yt.search().list().execute.return_value = {
            "items": [
                {
                    "id": {"videoId": f"vid_{i}"},
                    "snippet": {
                        "title": f"Video {i}",
                        "channelId": "UC8sStaR-cwz-x7MD4XKNUKA",
                    },
                }
                for i in range(5)
            ]
        }
        mock_yt.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "vid_0",
                    "snippet": {
                        "title": "Video",
                        "channelId": "UC8sStaR-cwz-x7MD4XKNUKA",
                    },
                }
            ]
        }

        # First 2 succeed, 3rd raises 429 quota error
        quota_err = HttpError(
            resp=Response({"status": 429, "reason": "Quota Exceeded"}),
            content=b"Quota Exceeded",
        )
        mock_yt.videos().delete().execute.side_effect = [
            {},
            {},
            quota_err,
        ]

        report = purge_channel_videos(
            channel="moku", dry_run=False, force=True, delay_sec=0.5
        )

        assert report.total_found == 5
        assert report.deleted_count == 2
        assert report.failed_count == 1
        assert report.skipped_count == 2
        assert mock_sleep.call_count >= 2


class TestPurgeChannelsCLI:
    """CLI Argument Parsing and Default Behavior Tests."""

    @patch("src.cli.purge_channels.purge_channel_videos")
    @patch("sys.argv", ["purge_channels", "--channel", "moku"])
    def test_cli_defaults_to_dry_run(self, mock_purge):
        from src.cli.purge_channels import main
        mock_purge.return_value = PurgeReport(
            channel="moku", total_found=0, deleted_count=0, skipped_count=0, failed_count=0
        )
        exit_code = main()
        assert exit_code == 0
        mock_purge.assert_called_once_with(
            channel="moku",
            dry_run=True,
            force=False,
            delay_sec=0.5,
        )

    @patch("src.cli.purge_channels.purge_channel_videos")
    @patch("sys.argv", ["purge_channels", "--channel", "moku", "--execute", "--force"])
    def test_cli_execute_flag_enables_live_purge(self, mock_purge):
        from src.cli.purge_channels import main
        mock_purge.return_value = PurgeReport(
            channel="moku", total_found=0, deleted_count=0, skipped_count=0, failed_count=0
        )
        exit_code = main()
        assert exit_code == 0
        mock_purge.assert_called_once_with(
            channel="moku",
            dry_run=False,
            force=True,
            delay_sec=0.5,
        )

    @patch("src.cli.purge_channels.purge_channel_videos")
    @patch("sys.argv", ["purge_channels"])
    def test_cli_defaults_to_horror_channel(self, mock_purge):
        from src.cli.purge_channels import main
        mock_purge.return_value = PurgeReport(
            channel="horror", total_found=0, deleted_count=0, skipped_count=0, failed_count=0
        )
        exit_code = main()
        assert exit_code == 0
        mock_purge.assert_called_once_with(
            channel="horror",
            dry_run=True,
            force=False,
            delay_sec=0.5,
        )
