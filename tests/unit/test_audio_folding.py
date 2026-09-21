"""Unit and integration tests for Audio Mastering Folding and Sidechain Ducking (R2).

Validates:
1. Fast bypass of standalone FFmpeg voice mastering in lib/tts.py when YT_FOLD_MASTERING=1 (default).
2. Forced and configured FFmpeg voice mastering when force=True or YT_FOLD_MASTERING=0.
3. Stage 5 skipping master_voice_audio call under folded mastering.
4. LoopAudioMixin.build_audio_filter filtergraph assembly with sidechain ducking and composite LUFS/TP loudnorm.
5. build_stream_copy_composition_cmd parameter alignment (-14.0 LUFS, -1.5 dB TP, music volume).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

import lib.tts
from lib.tts import master_voice_audio
from src.core.profiling import PipelineProfiler
from src.media.loop.audio import LoopAudioMixin
from src.media.loop_engine import LoopVideoEngine
from src.pipeline.context import PipelineContext
from src.pipeline.stages.stage_05_tts import stage_05_tts_synthesis


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mock_profiler() -> PipelineProfiler:
    return PipelineProfiler("test_audio_folding_run")


@pytest.fixture
def dummy_wav(tmp_path: Path) -> Path:
    wav_path = tmp_path / "voice_input.wav"
    wav_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00" + b"\x00" * 40)
    return wav_path


@pytest.fixture
def dummy_bgm(tmp_path: Path) -> Path:
    bgm_path = tmp_path / "bg_music.mp3"
    bgm_path.write_bytes(b"\xff\xfb\x90\x44" + b"\x00" * 400)
    return bgm_path


@pytest.fixture
def stage_05_context(tmp_path: Path, mock_profiler: PipelineProfiler, dummy_wav: Path) -> PipelineContext:
    lane = MagicMock()
    lane.id = "test-vertical-short"
    lane.orientation = "vertical"
    lane.duration_target_sec = 55.0
    lane.duration_max_sec = 60.0
    lane.duration_min_sec = 45.0
    lane.words_max = 135
    lane.words_min = 100
    lane.words_recondense_max = 125
    lane.voice_rate = "+0%"

    script_file = tmp_path / "script.txt"
    script_file.write_text("Texto de prueba para síntesis.", encoding="utf-8")

    ctx = PipelineContext(
        story={"title": "Test Story", "content": "Texto de prueba"},
        story_id="story_af_1",
        run_id="run_af_1",
        channel_name="moku",
        channel_key="moku",
        lane=lane,
        repository=MagicMock(),
        database=":memory:",
        owner="test_worker",
        lease_seconds=300,
        settings=MagicMock(),
        branding=MagicMock(),
        profiler=mock_profiler,
        directed=False,
        generate_only=False,
        engine_mode="loop",
        is_loop_mode=True,
        is_multiscene_mode=False,
        subtitles_active=False,
        work_dir=tmp_path,
        audio_path=dummy_wav,
        ass_path=tmp_path / "subs.ass",
        srt_path=tmp_path / "subs.srt",
        video_path=tmp_path / "video.mp4",
        thumbnail_path=tmp_path / "thumb.jpg",
        script_path=script_file,
        visual_plan_path=tmp_path / "plan.json",
        metadata_path=tmp_path / "meta.json",
        scene_manifest_path=tmp_path / "manifest.json",
    )
    ctx.clean_script = "Texto de prueba para síntesis."
    ctx.script = ctx.clean_script
    ctx.title = "Test Story"
    ctx.content = ctx.clean_script
    return ctx


# ===========================================================================
# 1. lib/tts.py: master_voice_audio Fast Bypass Tests
# ===========================================================================

class TestMasterVoiceAudioBypass:
    """Validates the fast folded mastering bypass in lib/tts.py."""

    def test_master_voice_audio_bypasses_ffmpeg_by_default(
        self, dummy_wav: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """By default (YT_FOLD_MASTERING unset or '1'), master_voice_audio returns in <1ms without FFmpeg."""
        monkeypatch.delenv("YT_FOLD_MASTERING", raising=False)

        mock_subproc = MagicMock()
        monkeypatch.setattr("lib.tts._run_subproc", mock_subproc)
        monkeypatch.setattr("subprocess.run", mock_subproc)

        t_start = time.perf_counter()
        result = master_voice_audio(str(dummy_wav), force=False)
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        assert result == str(dummy_wav), f"Expected returned path {dummy_wav}, got {result}"
        assert not mock_subproc.called, "Subprocess must NOT be invoked when YT_FOLD_MASTERING=1 by default"
        assert elapsed_ms < 5.0, f"Bypass must be instantaneous (<5ms), took {elapsed_ms:.3f}ms"

    def test_master_voice_audio_bypasses_ffmpeg_when_fold_mastering_explicitly_one(
        self, dummy_wav: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When YT_FOLD_MASTERING=1, master_voice_audio immediately bypasses FFmpeg."""
        monkeypatch.setenv("YT_FOLD_MASTERING", "1")

        mock_subproc = MagicMock()
        monkeypatch.setattr("lib.tts._run_subproc", mock_subproc)
        monkeypatch.setattr("subprocess.run", mock_subproc)

        result = master_voice_audio(str(dummy_wav), force=False)
        assert result == str(dummy_wav)
        assert not mock_subproc.called

    def test_master_voice_audio_executes_ffmpeg_when_forced(
        self, dummy_wav: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When force=True, master_voice_audio executes FFmpeg even if YT_FOLD_MASTERING=1."""
        monkeypatch.setenv("YT_FOLD_MASTERING", "1")

        captured_cmds: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            captured_cmds.append(cmd)
            # Create the temporary output file so os.replace succeeds
            tmp_target = cmd[-1]
            Path(tmp_target).write_bytes(b"RIFF_MASTERED_DATA")
            res = MagicMock()
            res.returncode = 0
            return res

        monkeypatch.setattr("lib.tts._run_subproc", fake_run)

        result = master_voice_audio(str(dummy_wav), force=True)
        assert result == str(dummy_wav)
        assert len(captured_cmds) == 1, "FFmpeg must be executed when force=True"

        cmd = captured_cmds[0]
        assert "ffmpeg" in cmd
        assert "-af" in cmd
        af_str = cmd[cmd.index("-af") + 1]
        assert "equalizer=f=120" in af_str, "Missing 120 Hz equalizer cut in filter string"
        assert "loudnorm=I=-14.0" in af_str, "Missing -14.0 LUFS loudnorm target in filter string"
        assert "TP=-1.5" in af_str, "Missing -1.5 dB True Peak target in filter string"

    def test_master_voice_audio_executes_ffmpeg_when_fold_mastering_is_zero(
        self, dummy_wav: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When YT_FOLD_MASTERING=0, master_voice_audio executes FFmpeg even if force=False."""
        monkeypatch.setenv("YT_FOLD_MASTERING", "0")

        captured_cmds: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            captured_cmds.append(cmd)
            Path(cmd[-1]).write_bytes(b"RIFF_MASTERED_DATA")
            res = MagicMock()
            res.returncode = 0
            return res

        monkeypatch.setattr("lib.tts._run_subproc", fake_run)

        result = master_voice_audio(str(dummy_wav), force=False)
        assert result == str(dummy_wav)
        assert len(captured_cmds) == 1, "FFmpeg must be executed when YT_FOLD_MASTERING=0"

    def test_master_voice_audio_honors_custom_lufs_and_true_peak(
        self, dummy_wav: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Custom target_lufs and true_peak_dbtp parameters are correctly interpolated into filtergraph."""
        monkeypatch.setenv("YT_FOLD_MASTERING", "0")

        captured_cmds: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            captured_cmds.append(cmd)
            Path(cmd[-1]).write_bytes(b"RIFF_MASTERED_DATA")
            res = MagicMock()
            res.returncode = 0
            return res

        monkeypatch.setattr("lib.tts._run_subproc", fake_run)

        master_voice_audio(str(dummy_wav), target_lufs=-12.5, true_peak_dbtp=-2.0, force=False)
        assert len(captured_cmds) == 1
        af_str = captured_cmds[0][captured_cmds[0].index("-af") + 1]
        assert "loudnorm=I=-12.5:TP=-2.0:LRA=11" in af_str


# ===========================================================================
# 2. Stage 5: Skip Calling master_voice_audio Under Folded Mastering
# ===========================================================================

class TestStage05MasteringBypass:
    """Validates that Stage 5 skips invoking master_voice_audio when folded mastering is active."""

    def test_stage_05_skips_master_voice_audio_when_fold_mastering_is_one(
        self, stage_05_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When YT_FOLD_MASTERING=1 (default), stage_05_tts_synthesis does not invoke master_voice_audio."""
        monkeypatch.setenv("YT_FOLD_MASTERING", "1")
        monkeypatch.setenv("MASTER_AUDIO_R128", "1")

        mock_master = MagicMock(return_value=str(stage_05_context.audio_path))
        monkeypatch.setattr("lib.tts.master_voice_audio", mock_master)

        def fake_generate(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            return {"audio_path": output_path, "duration_sec": 55.0, "word_timestamps": []}

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate)

        stage_05_tts_synthesis(stage_05_context)
        assert not mock_master.called, (
            "Stage 5 must completely skip calling master_voice_audio when YT_FOLD_MASTERING=1"
        )

    def test_stage_05_calls_master_voice_audio_when_fold_mastering_is_zero(
        self, stage_05_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When YT_FOLD_MASTERING=0 and MASTER_AUDIO_R128=1, stage_05_tts_synthesis calls master_voice_audio."""
        monkeypatch.setenv("YT_FOLD_MASTERING", "0")
        monkeypatch.setenv("MASTER_AUDIO_R128", "1")

        mock_master = MagicMock(return_value=str(stage_05_context.audio_path))
        monkeypatch.setattr("lib.tts.master_voice_audio", mock_master)

        def fake_generate(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            return {"audio_path": output_path, "duration_sec": 55.0, "word_timestamps": []}

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate)

        stage_05_tts_synthesis(stage_05_context)
        assert mock_master.called, (
            "Stage 5 must invoke master_voice_audio when YT_FOLD_MASTERING=0 and MASTER_AUDIO_R128=1"
        )
        assert mock_master.call_args[0][0] == stage_05_context.audio_path
        assert mock_master.call_args[1].get("target_lufs") == -14.0
        assert mock_master.call_args[1].get("true_peak_dbtp") == -1.5

    def test_stage_05_skips_master_voice_audio_when_master_audio_r128_is_zero(
        self, stage_05_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When MASTER_AUDIO_R128=0, stage_05_tts_synthesis never calls master_voice_audio."""
        monkeypatch.setenv("YT_FOLD_MASTERING", "0")
        monkeypatch.setenv("MASTER_AUDIO_R128", "0")

        mock_master = MagicMock()
        monkeypatch.setattr("lib.tts.master_voice_audio", mock_master)

        def fake_generate(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            return {"audio_path": output_path, "duration_sec": 55.0, "word_timestamps": []}

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate)

        stage_05_tts_synthesis(stage_05_context)
        assert not mock_master.called


# ===========================================================================
# 3. src/media/loop/audio.py: LoopAudioMixin.build_audio_filter Tests
# ===========================================================================

class TestLoopAudioFiltergraph:
    """Validates LoopAudioMixin.build_audio_filter filtergraph assembly and parameter alignment."""

    def test_build_audio_filter_contains_sidechaincompress_and_composite_loudnorm(self) -> None:
        """Audio filtergraph ducks BGM via voice sidechain and applies -14 LUFS loudnorm to composite bus."""
        mixin = LoopAudioMixin()
        graph = mixin.build_audio_filter(
            has_music=True,
            music_volume=0.04,
            ducking_threshold=0.035,
            ducking_ratio=8.0,
            ducking_attack_ms=20.0,
            ducking_release_ms=350.0,
            lowpass_freq=12000,
            master_loudness=True,
            target_lufs=-14.0,
            max_tp=-1.5,
            lra=11.0,
        )

        # 1. Voice splitting into sidechain trigger and speech mix
        assert "[1:a]aresample=44100,asplit=2[speech_sc][speech_mix]" in graph

        # 2. BGM filtering and volume
        assert "lowpass=f=12000,volume=0.0400[music_in]" in graph

        # 3. Sidechain compression ducking
        assert (
            "sidechaincompress=threshold=0.035:ratio=8.0:attack=20.0:release=350.0:makeup=1[music_ducked]"
            in graph
        )

        # 4. Amix combines voice and ducked music
        assert "[speech_mix][music_ducked]amix=inputs=2:duration=first:normalize=0[amixed]" in graph

        # 5. Composite bus normalization on [amixed]
        assert "[amixed]loudnorm=I=-14.0:TP=-1.5:LRA=11.0" in graph
        assert "[aout]" in graph

    def test_build_audio_filter_default_target_lufs_is_minus_14(self) -> None:
        """LoopAudioMixin.build_audio_filter defaults target_lufs to -14.0 and max_tp to -1.5."""
        mixin = LoopAudioMixin()
        # Call with minimal arguments to test method defaults
        graph = mixin.build_audio_filter(has_music=True)

        assert "loudnorm=I=-14.0" in graph, "Default target_lufs must be aligned to -14.0 LUFS (EBU R128)"
        assert "TP=-1.5" in graph, "Default max_tp must be aligned to -1.5 dB True Peak"

    def test_build_audio_filter_default_music_volume_is_0_04(self) -> None:
        """LoopAudioMixin.build_audio_filter defaults music_volume to 0.04."""
        mixin = LoopAudioMixin()
        graph = mixin.build_audio_filter(has_music=True)
        assert "volume=0.0400" in graph

    def test_build_audio_filter_custom_parameters(self) -> None:
        """LoopAudioMixin.build_audio_filter honors custom LUFS, TP, and ducking parameters."""
        mixin = LoopAudioMixin()
        graph = mixin.build_audio_filter(
            has_music=True,
            music_volume=0.06,
            ducking_threshold=0.05,
            ducking_ratio=10.0,
            ducking_attack_ms=15.0,
            ducking_release_ms=400.0,
            target_lufs=-12.0,
            max_tp=-2.0,
        )
        assert "volume=0.0600" in graph
        assert "threshold=0.05:ratio=10.0:attack=15.0:release=400.0" in graph
        assert "loudnorm=I=-12.0:TP=-2.0" in graph

    def test_build_audio_filter_without_music(self) -> None:
        """When has_music=False, filtergraph passes voice directly to -14.0 LUFS loudnorm without amix."""
        mixin = LoopAudioMixin()
        graph = mixin.build_audio_filter(has_music=False, target_lufs=-14.0, max_tp=-1.5)

        assert "sidechaincompress" not in graph
        assert "amix" not in graph
        assert "[1:a]aresample=44100,loudnorm=I=-14.0:TP=-1.5:LRA=11.0" in graph
        assert "[aout]" in graph


# ===========================================================================
# 4. src/media/loop/stream_copy.py: build_stream_copy_composition_cmd Tests
# ===========================================================================

class TestStreamCopyCompositionAudioIntegration:
    """Validates audio filtergraph assembly and parameter alignment in stream_copy composition."""

    def test_stream_copy_cmd_uses_target_lufs_minus_14_and_max_tp_minus_1_5(
        self, tmp_path: Path, dummy_wav: Path, dummy_bgm: Path
    ) -> None:
        """build_stream_copy_composition_cmd invokes build_audio_filter with target_lufs=-14.0 and max_tp=-1.5."""
        engine = LoopVideoEngine()
        concat_list = tmp_path / "concat.txt"
        concat_list.write_text("ffconcat version 1.0\nfile 'loop.mp4'\n", encoding="utf-8")
        out_video = tmp_path / "out.mp4"

        cmd = engine.build_stream_copy_composition_cmd(
            concat_list_path=concat_list,
            audio_path=dummy_wav,
            bgm_path=dummy_bgm,
            duration_sec=30.0,
            output_video_path=out_video,
        )

        assert "-filter_complex" in cmd, "Stream copy command must include -filter_complex for audio chain"
        fc_idx = cmd.index("-filter_complex")
        filter_graph = cmd[fc_idx + 1]

        # Check sidechain compression presence
        assert "sidechaincompress" in filter_graph, "Filtergraph must include sidechain ducking"

        # Check loudness mastering on composite bus
        assert "loudnorm=I=-14.0" in filter_graph, "Composite bus must master to -14.0 LUFS"
        assert "TP=-1.5" in filter_graph, "Composite bus must limit to -1.5 dB TP"

        # Check output audio map
        assert "-map" in cmd
        assert "[aout]" in cmd

    def test_stream_copy_cmd_music_volume_parameter(
        self, tmp_path: Path, dummy_wav: Path, dummy_bgm: Path
    ) -> None:
        """build_stream_copy_composition_cmd passes music_volume to the audio filtergraph."""
        engine = LoopVideoEngine()
        concat_list = tmp_path / "concat.txt"
        concat_list.write_text("ffconcat version 1.0\nfile 'loop.mp4'\n", encoding="utf-8")
        out_video = tmp_path / "out.mp4"

        cmd = engine.build_stream_copy_composition_cmd(
            concat_list_path=concat_list,
            audio_path=dummy_wav,
            bgm_path=dummy_bgm,
            duration_sec=30.0,
            output_video_path=out_video,
            music_volume=0.04,
        )

        fc_idx = cmd.index("-filter_complex")
        filter_graph = cmd[fc_idx + 1]
        assert "volume=0.0400" in filter_graph

    def test_stream_copy_cmd_without_music_uses_target_lufs_minus_14(
        self, tmp_path: Path, dummy_wav: Path
    ) -> None:
        """When bgm_path is None, stream_copy command normalizes narration to -14.0 LUFS and -1.5 dB TP."""
        engine = LoopVideoEngine()
        concat_list = tmp_path / "concat.txt"
        concat_list.write_text("ffconcat version 1.0\nfile 'loop.mp4'\n", encoding="utf-8")
        out_video = tmp_path / "out.mp4"

        cmd = engine.build_stream_copy_composition_cmd(
            concat_list_path=concat_list,
            audio_path=dummy_wav,
            bgm_path=None,
            duration_sec=30.0,
            output_video_path=out_video,
        )

        cmd_str = " ".join(cmd)
        assert "loudnorm=I=-14.0:TP=-1.5" in cmd_str
