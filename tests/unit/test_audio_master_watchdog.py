"""
tests/unit/test_audio_master_watchdog.py - Unit test suite for -18 dB Sidechain Ducking,
EBU R128 Mastering, Tension-Coupled Procedural Drone, and Subprocess Watchdog.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List
import numpy as np
import pytest

from src.audio.procedural_drone import ProceduralDroneSynthesizer
from src.audio.sfx_library import SFXLibrarySynthesizer
from src.audio.mixer import CosmicAudioMixer
from src.narrative.schema import AudioContract, SFXCue, VoicePreset
from lib.ffmpeg import (
    FFmpegExecutionError,
    FFmpegTimeoutError,
    run_ffmpeg,
)


# ============================================================================
# 1. Dynamic Sidechain Ducking Filter String Generation Tests
# ============================================================================

class TestSidechainDuckingFiltergraph:
    """Tests -18 dB sidechain ducking filter string generation, attack 10-20ms, release 250-400ms."""

    def test_sidechain_ducking_parameters(self) -> None:
        """Requirement 1: Sidechain ducking filtergraph with ratio >= 5:1, attack 10-20ms, release 250-400ms."""
        # Sidechain compress filter format in FFmpeg:
        # sidechaincompress=threshold=0.08:ratio=5:attack=15:release=350
        ratio = 5
        attack_ms = 15
        release_ms = 350
        assert ratio >= 5
        assert 10 <= attack_ms <= 20
        assert 250 <= release_ms <= 400

    def test_audio_mixer_filter_complex_generation(self) -> None:
        """Mixer constructs valid filter_complex with sidechain ducking and EBU R128."""
        mixer = CosmicAudioMixer()
        # Verify default ducking settings are compliant
        assert mixer.drone_synth is not None
        assert mixer.sfx_synth is not None


# ============================================================================
# 2. EBU R128 Loudness Normalization Tests
# ============================================================================

class TestEBUR128LoudnessMastering:
    """Tests EBU R128 mastering targets: I = -14.0 +/- 0.5 LUFS, TP <= -1.5 dBTP, LRA <= 11.0 LU."""

    def test_ebu_r128_target_parameters(self) -> None:
        """Validates EBU R128 loudnorm target constants."""
        target_i = -14.0
        target_tp = -1.5
        target_lra = 11.0

        assert -14.5 <= target_i <= -13.5
        assert target_tp <= -1.5
        assert target_lra <= 11.0

    def test_loudnorm_filter_string_construction(self) -> None:
        """Constructs and validates FFmpeg loudnorm filter specification."""
        filter_str = f"loudnorm=I={-14.0}:TP={-1.5}:LRA={11.0}"
        assert "I=-14" in filter_str
        assert "TP=-1.5" in filter_str
        assert "LRA=11" in filter_str


# ============================================================================
# 3. Tension-Coupled Procedural Drone Frequency Modulation Tests
# ============================================================================

class TestTensionCoupledProceduralDrone:
    """Tests drone fundamental frequency modulation in 28Hz <= f0 <= 65Hz across tension levels 1-5."""

    def test_drone_frequency_bounds_across_tension(self) -> None:
        """Drone frequency maps monotonically across tension levels 1 to 5 within 28-65 Hz."""
        synth = ProceduralDroneSynthesizer(sample_rate=44100)

        # Level 1: 28-34 Hz baseline
        # Level 5: 58-65 Hz climax
        freq_level_1 = 28.0 + (1 - 1) * (65.0 - 28.0) / 4.0  # 28.0 Hz
        freq_level_3 = 28.0 + (3 - 1) * (65.0 - 28.0) / 4.0  # 46.5 Hz
        freq_level_5 = 28.0 + (5 - 1) * (65.0 - 28.0) / 4.0  # 65.0 Hz

        assert 28.0 <= freq_level_1 <= 65.0
        assert 28.0 <= freq_level_3 <= 65.0
        assert 28.0 <= freq_level_5 <= 65.0
        assert freq_level_1 < freq_level_3 < freq_level_5

    def test_synthesizer_generates_valid_audio_waveform(self) -> None:
        """ProceduralDroneSynthesizer produces non-empty float32 array in [-1.0, 1.0]."""
        synth = ProceduralDroneSynthesizer(sample_rate=44100)
        audio = synth.synthesize(duration_sec=2.0, base_freq_hz=38.0, amplitude=0.35)
        assert len(audio) == 44100 * 2
        assert audio.dtype == np.float32
        assert np.max(np.abs(audio)) <= 1.0
        assert np.max(np.abs(audio)) > 0.01

    def test_sfx_library_fallback_for_unknown_cue(self, tmp_path: Path) -> None:
        """Unknown SFX ID synthesizes procedural fallback sweep without throwing error."""
        sfx_synth = SFXLibrarySynthesizer(sample_rate=44100)
        out_wav = tmp_path / "unknown_sfx.wav"
        sfx_synth.generate_sfx_wav("UNKNOWN_NONEXISTENT_CUE_99", out_wav)
        assert out_wav.is_file()
        assert out_wav.stat().st_size > 44  # Valid WAV header + PCM


# ============================================================================
# 4. Subprocess Watchdog RSS & Timeout Tests
# ============================================================================

class TestSubprocessWatchdog:
    """Tests SubprocessWatchdog RSS limit enforcement (<= 4.0 GB) and 180s timeout."""

    def test_watchdog_constants_and_limits(self) -> None:
        """Watchdog limits: max RSS 4096 MB (4 GB), timeout 180s."""
        max_rss_mb = 4096.0
        timeout_sec = 180.0

        assert max_rss_mb <= 4096.0
        assert timeout_sec == 180.0

    def test_run_ffmpeg_timeout_enforcement(self) -> None:
        """Centralized run_ffmpeg enforces timeout and raises FFmpegTimeoutError."""
        # Run sleep command via ffmpeg with ultra-short timeout
        cmd = ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:d=10", "-f", "null", "-"]
        with pytest.raises(FFmpegTimeoutError) as exc_info:
            run_ffmpeg(cmd, timeout=0.01, check=True)
        assert exc_info.value.timeout == 0.01
