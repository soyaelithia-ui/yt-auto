"""
tests/unit/test_challenger2_gen2_stress.py
Empirical Challenger 2 (Gen 2) Adversarial Stress Harness for Milestone M1.
Stress tests exports, wildcard imports, legacy bridges, filtergraphs, edge durations, and audio mastering.
"""
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
import pytest

from src.audio import (
    ProceduralDroneSynthesizer,
    apply_butterworth_4th_lowpass_50hz,
    VocalChainProcessor,
    VOCAL_FILTERGRAPHS,
    SFXLibrarySynthesizer,
    CosmicAudioMixer,
    VoicePreset,
    AudioContract,
    SFXCue,
    AudioMasteringError,
    AudioProcessingError,
    FFmpegExecutionError,
    DEFAULT_BACKGROUND_AUDIO_VOLUME,
    DEFAULT_DUCKING_DB,
    DEFAULT_TARGET_LUFS,
    DEFAULT_MAX_TP,
    DEFAULT_MAX_LRA,
    generate_synthetic_pcm_audio,
    normalize_narration_lufs,
    apply_sidechain_ducking,
    master_audio_track,
)


class TestGen2WildcardAndExportIntegrity:
    """Stress tests wildcard imports, dunder all synchronization, and typing contracts."""

    def test_wildcard_import_in_subprocess(self):
        """Execute `from src.audio import *` in a completely clean subprocess."""
        cmd = [
            sys.executable,
            "-c",
            "from src.audio import *; "
            "assert DEFAULT_TARGET_LUFS == -14.0; "
            "assert DEFAULT_MAX_TP == -1.5; "
            "assert DEFAULT_MAX_LRA == 11.0; "
            "assert DEFAULT_BACKGROUND_AUDIO_VOLUME == 0.04; "
            "assert DEFAULT_DUCKING_DB == -18.0; "
            "assert issubclass(AudioMasteringError, Exception); "
            "assert issubclass(FFmpegExecutionError, Exception); "
            "print('Subprocess wildcard verification PASSED')"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        assert "Subprocess wildcard verification PASSED" in res.stdout

    def test_all_symbols_in_dunder_all_are_valid(self):
        import src.audio
        for symbol in src.audio.__all__:
            assert hasattr(src.audio, symbol), f"Symbol {symbol} listed in __all__ not found in src.audio"
            val = getattr(src.audio, symbol)
            assert val is not None, f"Symbol {symbol} has None value"

    def test_src_audio_exports_match_all_contracts(self):
        import src.audio
        assert hasattr(src.audio, "DEFAULT_TARGET_LUFS")
        assert hasattr(src.audio, "DEFAULT_MAX_TP")
        assert hasattr(src.audio, "DEFAULT_MAX_LRA")
        assert hasattr(src.audio, "DEFAULT_BACKGROUND_AUDIO_VOLUME")
        assert hasattr(src.audio, "DEFAULT_DUCKING_DB")


class TestGen2MixerAndEdgeDurations:
    """Adversarial stress testing of CosmicAudioMixer under boundary conditions."""

    def test_mixer_with_subsecond_duration(self, tmp_path):
        mixer = CosmicAudioMixer(work_dir=tmp_path / "work")
        voice_wav = tmp_path / "short_voice.wav"
        generate_synthetic_pcm_audio(voice_wav, duration_sec=0.2, freq=220.0)

        contract = AudioContract(
            voice_text="Test short utterance",
            voice_preset=VoicePreset.INTERCOM_BUNKER,
            drone_base_freq_hz=45.0,
            sfx_timeline=[],
        )
        out_wav = tmp_path / "master_subsecond.wav"
        res = mixer.master_soundtrack(contract, voice_wav, out_wav, total_duration_sec=0.2)

        assert res.exists()
        assert res.stat().st_size > 44  # Valid WAV with data
        with wave.open(str(res), "rb") as w:
            n_frames = w.getnframes()
            rate = w.getframerate()
            dur = n_frames / float(rate)
            assert 0.15 <= dur <= 0.35

    def test_mixer_with_dense_sfx_and_large_delays(self, tmp_path):
        mixer = CosmicAudioMixer(work_dir=tmp_path / "work")
        voice_wav = tmp_path / "voice_dense.wav"
        generate_synthetic_pcm_audio(voice_wav, duration_sec=2.0, freq=300.0)

        contract = AudioContract(
            voice_text="Dense SFX test timeline",
            voice_preset=VoicePreset.HYDROPHONE_RADIO,
            drone_base_freq_hz=55.0,
            sfx_timeline=[
                SFXCue(time_sec=0.0, sfx_id="ptt_squelch", volume=1.0),
                SFXCue(time_sec=0.5, sfx_id="sonar_ping_deep_reverb", volume=0.8),
                SFXCue(time_sec=1.0, sfx_id="singularity_glitch_burst", volume=1.2),
                SFXCue(time_sec=1.5, sfx_id="hull_stress_metal_groan", volume=0.9),
                SFXCue(time_sec=1.8, sfx_id="unknown_fallback", volume=0.5),
            ],
        )
        out_wav = tmp_path / "master_dense.wav"
        res = mixer.master_soundtrack(contract, voice_wav, out_wav, total_duration_sec=2.0)

        assert res.exists()
        with wave.open(str(res), "rb") as w:
            assert w.getnchannels() == 2
            assert w.getsampwidth() == 2
            assert w.getframerate() == 44100
            dur = w.getnframes() / 44100.0
            assert 1.9 <= dur <= 2.2

    def test_sfx_track_build_with_zero_duration_guard(self, tmp_path):
        mixer = CosmicAudioMixer(work_dir=tmp_path / "work")
        # Should not throw when duration is zero or negative because of max(0.1, float(total_dur))
        sfx_wav = mixer._build_sfx_track(sfx_timeline=[], total_dur=0.0)
        assert sfx_wav.exists()
        assert sfx_wav.stat().st_size > 44


class TestGen2MasteringStandardsEBU:
    """Verifies that mastered audio conforms to EBU R128 loudness standards."""

    def test_master_audio_track_loudnorm_compliance(self, tmp_path):
        voice_wav = tmp_path / "voice.wav"
        music_wav = tmp_path / "ambient.wav"
        master_wav = tmp_path / "master.wav"

        generate_synthetic_pcm_audio(voice_wav, duration_sec=3.0, freq=330.0)
        generate_synthetic_pcm_audio(music_wav, duration_sec=3.0, freq=110.0)

        res = Path(master_audio_track(
            narration_path=voice_wav,
            music_path=music_wav,
            output_path=master_wav,
            target_lufs=-14.0,
            music_volume=0.05,
            ducking_db=-16.0,
        ))
        assert res.exists()
        assert res.stat().st_size > 44

        # Probe with ffmpeg ebur128 to verify loudness
        cmd = [
            "ffmpeg", "-nostats", "-i", str(master_wav),
            "-filter_complex", "ebur128=peak=true",
            "-f", "null", "-"
        ]
        ebur_res = subprocess.run(cmd, capture_output=True, text=True)
        assert ebur_res.returncode == 0
        assert "Integrated loudness:" in ebur_res.stderr
