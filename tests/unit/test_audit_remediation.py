"""Unit and regression tests for system flaws audit remediation."""
from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.repository import (
    compute_simhash_64 as repo_simhash,
    hamming_distance_64 as repo_hamming,
)
from src.daemon import (
    compute_simhash_64 as daemon_simhash,
    hamming_distance_64 as daemon_hamming,
)
from src.sanitizer import (
    check_forbidden_editorial_elements,
    compute_simhash_64 as sanitizer_simhash,
    hamming_distance_64 as sanitizer_hamming,
)
from src.llm import is_spanish_text
from src.media.loop_engine import (
    LoopVideoEngine,
    _load_rotation_state,
    _save_rotation_state,
)
from lib.video import validate_video_format
from src.core.verdict import _roi_gate


class TestAuditRemediation:
    """Validates the fixes implemented during the system audit remediation."""

    def test_simhash_consistency_across_modules(self):
        """BUG-03: SimHash must be mathematically identical across repository, daemon, and sanitizer."""
        sample_texts = [
            "SCP-173 debe permanecer en una celda sellada.",
            "Había una vez en un bosque oscuro y desolado...",
            "Short story about cosmic dread and an ancient forgotten entity.",
            "El suspenso aumentaba conforme caía la noche en la montaña.",
            "A completely distinct narrative with different keywords and topics.",
        ]
        for text in sample_texts:
            h_repo = repo_simhash(text)
            h_daemon = daemon_simhash(text)
            h_sanitizer = sanitizer_simhash(text)

            assert h_repo == h_daemon == h_sanitizer, f"SimHash mismatch for text: {text[:30]}"
            assert isinstance(h_repo, int)
            assert h_repo != 0

            # Hamming distance must also match
            d_repo = repo_hamming(h_repo, 0)
            d_daemon = daemon_hamming(h_daemon, 0)
            d_sanitizer = sanitizer_hamming(h_sanitizer, 0)
            assert d_repo == d_daemon == d_sanitizer

    def test_drive_proof_escaped_folder_scope(self, tmp_path: Path):
        """BUG-01: _proof() must not fail with NameError on escaped_folder."""
        from src.drive import upload_to_drive_verified

        dummy_file = tmp_path / "test_video.mp4"
        dummy_file.write_bytes(b"dummy mp4 video content")

        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_service.files.return_value = mock_files

        mock_list_search = MagicMock()
        mock_list_search.execute.return_value = {
            "files": [{"id": "drive_file_123", "name": "test_video.mp4", "size": str(dummy_file.stat().st_size)}]
        }

        mock_list_proof = MagicMock()
        mock_list_proof.execute.return_value = {
            "files": [{"id": "drive_file_123", "parents": ["test_folder_id"]}]
        }

        mock_files.list.side_effect = [mock_list_search, mock_list_proof]

        with patch("src.drive._mock_enabled", return_value=False), \
             patch("src.drive._drive_service", return_value=mock_service):
            dummy_key = tmp_path / "sa.json"
            dummy_key.write_text("{}")
            proof = upload_to_drive_verified(
                str(dummy_file),
                folder_id="test_folder_id",
                sa_key_path=str(dummy_key),
            )

        assert proof is not None
        assert proof.file_id == "drive_file_123"
        assert proof.folder_id == "test_folder_id"
        assert proof.exists is True
        # Verify that list was called with escaped folder query in parents check
        proof_call = mock_files.list.call_args_list[1]
        assert "q" in proof_call.kwargs
        assert "'test_folder_id' in parents" in proof_call.kwargs["q"]

    def test_spanish_detection_does_not_false_positive_on_english(self):
        """LLM: is_spanish_text must not falsely classify English as Spanish due to short words."""
        english_samples = [
            "No way out, no escape, no hope for survival.",
            "This is my story about what happened in the dark.",
            "No one knew what was lurking behind the locked door.",
            "It was me, alone in the room with no light.",
        ]
        for en_text in english_samples:
            assert is_spanish_text(en_text) is False, f"False positive Spanish detection on: '{en_text}'"

        spanish_samples = [
            "Había una criatura en el bosque que no dejaba de acechar.",
            "La puerta estaba cerrada pero el silencio era total en la casa.",
            "No pude moverme cuando la sombra apareció frente a mí.",
        ]
        for es_text in spanish_samples:
            assert is_spanish_text(es_text) is True, f"Failed to detect Spanish text: '{es_text}'"

    def test_stream_copy_accepts_h264_high_and_main_profiles(self, tmp_path: Path):
        """BOTTLE-01: Both Main and High profiles are accepted without ValueError."""
        video_main = tmp_path / "video_main.mp4"
        video_main.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 2000)

        video_high = tmp_path / "video_high.mp4"
        video_high.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 2000)

        def fake_ffprobe(cmd, **kwargs):
            p = str(cmd[-1])
            profile = "Main" if "main" in p else "High"
            payload = {
                "format": {"duration": "10.0", "format_name": "mov,mp4"},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264", "profile": profile, "pix_fmt": "yuv420p", "width": 1080, "height": 1920},
                    {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": 44100},
                ],
            }
            res = MagicMock()
            res.returncode = 0
            res.stdout = json.dumps(payload)
            return res

        with patch("subprocess.run", side_effect=fake_ffprobe), \
             patch("lib.video.has_faststart", return_value=True):
            # Neither Main nor High should raise ValueError
            assert validate_video_format(str(video_main), min_duration=0.0) is True
            assert validate_video_format(str(video_high), min_duration=0.0) is True

        # And ensure_h264_main_profile treats High as no-op
        eng = LoopVideoEngine()
        with patch("src.media.loop_engine.probe_media") as pm, \
             patch("src.media.loop_engine.run_ffmpeg") as rf:
            from lib.ffmpeg import MediaProbeResult, VideoStreamInfo
            pm.return_value = MediaProbeResult(
                format_name="mp4", duration=10.0, size_bytes=2000,
                video_streams=[VideoStreamInfo(codec_name="h264", width=1080, height=1920, fps=30.0, pix_fmt="yuv420p", duration=10.0, profile="High")],
            )
            out = eng.ensure_h264_main_profile(video_high)
            assert out == video_high
            rf.assert_not_called()

    def test_loop_rotation_state_thread_safety(self, tmp_path: Path):
        """RACE-01: Concurrent reads and writes to loop rotation state do not corrupt data."""
        state_file = tmp_path / "loop_rotation_state.json"
        with patch("src.media.loop_engine._ROTATION_STATE_FILE", state_file):
            _save_rotation_state({"shorts": 0, "longs": 0})

            def worker(worker_id: int):
                for _ in range(25):
                    idx = LoopVideoEngine.get_rotation_index("shorts", total_files=10, persist=True)
                    assert 0 <= idx < 10

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(worker, i) for i in range(8)]
                concurrent.futures.wait(futures)
                for f in futures:
                    assert f.exception() is None

            final_state = _load_rotation_state()
            assert isinstance(final_state.get("shorts"), int)
            assert 1 <= final_state["shorts"] <= 10

    def test_youtube_upload_timeout_preserves_video_id(self, tmp_path: Path):
        """BUG-04: If verification times out, upload_video_via_api returns unconfirmed with video_id without raising."""
        from src.youtube.uploader import upload_video_via_api

        mock_youtube = MagicMock()
        mock_videos = MagicMock()
        mock_youtube.videos.return_value = mock_videos

        # Mock videos().insert().execute() succeeding
        mock_insert = MagicMock()
        mock_insert.execute.return_value = {
            "id": "yt_vid_success_999",
            "snippet": {"channelId": "UC_TEST_123"},
        }
        mock_videos.insert.return_value = mock_insert

        # Mock thumbnails().set().execute()
        mock_thumb = MagicMock()
        mock_youtube.thumbnails.return_value = mock_thumb
        mock_thumb.set.return_value.execute.return_value = {"status": "ok"}

        video_file = tmp_path / "vid.mp4"
        video_file.write_bytes(b"x" * 100)
        thumb_file = tmp_path / "thumb.jpg"
        thumb_file.write_bytes(b"x" * 100)
        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        # Mock _verify_uploaded_video raising RuntimeError (timeout)
        with patch("src.youtube.uploader._youtube_service", return_value=mock_youtube), \
             patch("googleapiclient.http.MediaFileUpload"), \
             patch("src.youtube.uploader._verify_uploaded_video", side_effect=RuntimeError("Verification timed out")):
            res = upload_video_via_api(
                str(video_file),
                title="Una criatura en el bosque oscuro y desolado",
                description="Esta es una historia de terror donde una presencia acecha en la oscuridad total.",
                thumbnail_path=str(thumb_file),
                token_path=str(token_file),
            )

            # Must preserve the uploaded video_id rather than throwing an exception
            assert res["status"] == "UPLOAD_UNCONFIRMED"
            assert res["video_id"] == "yt_vid_success_999"
            assert "https://www.youtube.com/watch?v=yt_vid_success_999" in res["url"]
            assert res["verified"] is False

    def test_precomputed_visual_bypasses_frame_extraction(self, tmp_path: Path):
        """BOTTLE-02: Stage 13 code review skips extracting 12 PNG frames if Stage 10 visual audit passed."""
        video_file = tmp_path / "valid.mp4"
        video_file.write_bytes(b"x" * 2000)

        precomputed = {
            "passed": True,
            "longest_black_seconds": 0.0,
            "perceptual_luminance": 85.0,
        }

        # Calling _roi_gate directly with precomputed_visual
        with patch("src.visual_integrity.VisualIntegrityVerifier.extract_frames") as mock_extract:
            gate_res = _roi_gate(str(video_file), precomputed_visual=precomputed)
            assert gate_res.passed is True
            assert gate_res.code == "OK_ROI_PRECOMPUTED"
            mock_extract.assert_not_called()
