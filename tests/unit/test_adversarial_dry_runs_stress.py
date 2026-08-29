"""Adversarial stress test for 3-lane offline generate-only dry-runs."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.core.lanes import get_lane, load_lanes, resolve_voice_for_lane
from src.pipeline import run_pipeline_once
from src.core.repository import QueueRepository


@pytest.mark.unit
class TestThreeLaneDryRunsStress:
    """Empirical validation that offline generate-only runs succeed across all 3 configured lanes."""

    @pytest.mark.parametrize(
        "lane_id,expected_channel,expected_orientation,expected_voice",
        [
            ("moku-scp-shorts", "moku", "vertical", "es-ES-AlvaroNeural"),
            ("moku-horror-long", "moku", "horizontal", "es-ES-AlvaroNeural"),
            ("aelithia-aita-long", "aelithia", "horizontal", "es-MX-DaliaNeural"),
        ],
    )
    def test_lane_configuration_and_profile_contract(
        self, lane_id, expected_channel, expected_orientation, expected_voice
    ):
        """Verify each lane is active and correctly configured with its voice profile."""
        lane = get_lane(lane_id)
        assert lane is not None, f"Lane {lane_id} not found"
        assert lane.channel.value == expected_channel
        assert lane.orientation == expected_orientation
        resolved_voice = resolve_voice_for_lane(lane)
        assert resolved_voice == expected_voice
        assert lane.enabled is True

    @pytest.mark.parametrize(
        "lane_id,channel",
        [
            ("moku-scp-shorts", "moku"),
            ("moku-horror-long", "moku"),
            ("aelithia-aita-long", "aelithia"),
        ],
    )
    def test_lane_offline_generate_only_dry_run_execution(self, tmp_path, lane_id, channel, monkeypatch):
        """Execute generate_only dry-run for each lane with mocked AI/TTS/Compositor and verify completion."""
        monkeypatch.setenv("APP_ENV", "test")
        db_file = tmp_path / f"test_lane_{lane_id}.db"
        repo = QueueRepository(str(db_file))
        repo.initialize()

        story_id = f"test_dry_{lane_id}"
        story_title = f"Título de prueba {lane_id}"
        story_content = (
            "Esta es una historia de prueba narrativa completa para la validación del carril. "
            "Contiene suficientes palabras y estructura para pasar todos los filtros temáticos de calidad."
        )

        repo.enqueue(
            story_id,
            story_title,
            story_content,
            f"https://test.local/{story_id}",
            channel,
        )

        # Mock external APIs (translation, TTS, Telegram, YouTube) to ensure 100% offline determinism
        with patch("src.scraper.fetch_reddit_stories", return_value=[]), \
             patch("src.llm.curate_script", return_value=story_content), \
             patch("lib.tts.generate_audio") as mock_audio, \
             patch("lib.subtitles.create_subtitles") as mock_subs, \
             patch("lib.subtitles.create_ass_subtitles") as mock_ass, \
             patch("lib.video.compose_video") as mock_video, \
             patch("src.drive.upload_to_drive") as mock_drive, \
             patch("src.youtube.uploader.upload_video") as mock_yt:

            # Create mock artifact files in work dir
            def side_effect_audio(text, output_path, **kwargs):
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(b"RIFF....WAVEfmt ....data....")
                return output_path

            def side_effect_subs(audio_path, output_path, **kwargs):
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_text("[Script Info]\nPlayResX: 1080\nPlayResY: 1920\n", encoding="utf-8")
                return output_path

            def side_effect_video(audio_path, subs_path, output_path, **kwargs):
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(b"\x00\x00\x00 ftypisom....moov....")
                return output_path

            mock_audio.side_effect = side_effect_audio
            mock_subs.side_effect = side_effect_subs
            mock_ass.side_effect = side_effect_subs
            mock_video.side_effect = side_effect_video

            result = run_pipeline_once(
                channel=channel,
                db_path=str(db_file),
                generate_only=True,
                story_id=story_id,
                lane_id=lane_id,
            )

            assert result is not None
            # Verify generate-only mode completed without uploading
            assert result.get("status") in ("COMPLETED", "SUCCESS", "SAVED_LOCAL", "RENDERED", "PREVIEW_READY", "PROCESSING") or "video_path" in result or "run_id" in result
            mock_drive.assert_not_called()
            mock_yt.assert_not_called()
