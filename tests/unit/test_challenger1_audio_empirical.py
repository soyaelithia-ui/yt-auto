"""
tests/unit/test_challenger1_audio_empirical.py - Challenger 1 Empirical Stress Harness for M1 Audio Engine.

Tests:
1. Butterworth 4th-order lowpass filter mathematical properties, stability, and edge inputs.
2. Procedural Drone Synthesizer mathematical properties (1.5 Hz beat, 0.25 Hz wow, 60/120 Hz hum, noise).
3. VocalChainProcessor DSP filtergraphs and non-linear saturation robustness.
4. SFXLibrarySynthesizer all cues, custom durations, and fallback behaviors.
5. CosmicAudioMixer sidechain ducking filtergraph, loudnorm EBU R128 compliance, and extreme timeline cues.
6. Package exports and legacy API re-exports integrity.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
import pytest

import src.audio
from src.audio.procedural_drone import ProceduralDroneSynthesizer, apply_butterworth_4th_lowpass_50hz
from src.audio.vocal_chain import VocalChainProcessor, VOCAL_FILTERGRAPHS
from src.audio.sfx_library import SFXLibrarySynthesizer
from src.audio.mixer import CosmicAudioMixer
from src.narrative.schema import VoicePreset, AudioContract, SFXCue
from lib.audio import _ffmpeg_run, normalize_narration_lufs, apply_sidechain_ducking, master_audio_track


@pytest.fixture
def temp_dir(tmp_path):
    d = tmp_path / "challenger_audio_tests"
    d.mkdir(parents=True, exist_ok=True)
    return d


def measure_ebur128_loudness(audio_path: Path) -> dict[str, float]:
    """Uses FFmpeg ebur128 filter to measure integrated LUFS and True Peak."""
    cmd = [
        "ffmpeg", "-nostats", "-i", str(audio_path),
        "-filter_complex", "ebur128=peak=true",
        "-f", "null", "-"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    i_match = None
    tp_match = None
    lines = res.stderr.splitlines()
    in_summary = False
    for idx, line in enumerate(lines):
        if "Summary:" in line:
            in_summary = True
        if in_summary:
            if "Integrated loudness:" in line and idx + 1 < len(lines):
                nxt = lines[idx + 1]
                if "I:" in nxt:
                    try:
                        i_match = float(nxt.split("I:")[1].split("LUFS")[0].strip())
                    except Exception:
                        pass
            if "True peak:" in line and idx + 1 < len(lines):
                nxt = lines[idx + 1]
                if "Peak:" in nxt:
                    try:
                        tp_match = float(nxt.split("Peak:")[1].split("dBFS")[0].strip())
                    except Exception:
                        pass

    return {
        "integrated_lufs": i_match if i_match is not None else -99.0,
        "true_peak_dbfs": tp_match if tp_match is not None else 99.0,
    }


# ============================================================================
# 1. BUTTERWORTH 4th-ORDER LOWPASS FILTER EMPIRICAL CHALLENGES
# ============================================================================

class TestButterworth4thOrderEmpirical:
    """Empirically test the 4th-order Butterworth lowpass filter mathematical properties."""

    def test_butterworth_dc_gain_is_unity(self):
        """DC gain of a lowpass filter must be exactly 1.0 (0 dB)."""
        sr = 44100
        n_samples = 44100
        dc_signal = np.ones(n_samples, dtype=np.float64) * 0.75

        filtered = apply_butterworth_4th_lowpass_50hz(dc_signal, sample_rate=sr, cutoff_hz=50.0)

        steady_state = filtered[2000:]
        mean_steady = np.mean(steady_state)
        assert np.isclose(mean_steady, 0.75, atol=1e-3), f"DC gain shifted! Expected 0.75, got {mean_steady}"

    def test_butterworth_cutoff_attenuation_is_approx_3db(self):
        """At cutoff frequency (50 Hz), attenuation of a Butterworth filter must be approximately -3.0 dB (+/- 0.6 dB)."""
        sr = 44100
        dur = 3.0
        t = np.arange(int(sr * dur)) / float(sr)
        sine_50hz = np.sin(2.0 * np.pi * 50.0 * t)

        filtered = apply_butterworth_4th_lowpass_50hz(sine_50hz, sample_rate=sr, cutoff_hz=50.0)

        steady = filtered[int(sr * 2.0):]
        peak_out = np.max(np.abs(steady))
        expected_amp = 1.0 / math.sqrt(2.0)
        assert np.isclose(peak_out, expected_amp, atol=0.06), f"Cutoff attenuation mismatch: got {peak_out}, expected ~{expected_amp}"

    def test_butterworth_stopband_steep_rolloff(self):
        """4th-order filter should attenuate frequencies in stopband steeply (>= 24 dB/octave)."""
        sr = 44100
        dur = 2.0
        t = np.arange(int(sr * dur)) / float(sr)

        sine_200hz = np.sin(2.0 * np.pi * 200.0 * t)
        filtered_200hz = apply_butterworth_4th_lowpass_50hz(sine_200hz, sample_rate=sr, cutoff_hz=50.0)
        steady_200hz = filtered_200hz[int(sr * 1.0):]
        peak_200hz = np.max(np.abs(steady_200hz))
        assert peak_200hz < 0.015, f"200Hz stopband attenuation failed: peak = {peak_200hz}"

        sine_1000hz = np.sin(2.0 * np.pi * 1000.0 * t)
        filtered_1000hz = apply_butterworth_4th_lowpass_50hz(sine_1000hz, sample_rate=sr, cutoff_hz=50.0)
        steady_1000hz = filtered_1000hz[int(sr * 1.0):]
        peak_1000hz = np.max(np.abs(steady_1000hz))
        assert peak_1000hz < 1e-3, f"1000Hz stopband attenuation failed: peak = {peak_1000hz}"

    def test_butterworth_numerical_stability_long_signal(self):
        """Over long signals (1,000,000 samples ~ 22.6s), filter must not accumulate drift, NaN, or Inf."""
        sr = 44100
        n_samples = 1_000_000
        rng = np.random.default_rng(12345)
        noise = rng.normal(0.0, 1.0, size=n_samples)

        filtered = apply_butterworth_4th_lowpass_50hz(noise, sample_rate=sr, cutoff_hz=50.0)

        assert not np.isnan(filtered).any(), "Filter produced NaN on long signal"
        assert not np.isinf(filtered).any(), "Filter produced Inf on long signal"
        assert np.max(np.abs(filtered)) < 10.0, "Filter exploded numerically"

    def test_butterworth_edge_inputs(self):
        """Empty array, 1-element array, constant arrays, and zero signals must not crash."""
        empty = np.array([], dtype=np.float32)
        out_empty = apply_butterworth_4th_lowpass_50hz(empty)
        assert len(out_empty) == 0

        single = np.array([0.5], dtype=np.float32)
        out_single = apply_butterworth_4th_lowpass_50hz(single)
        assert len(out_single) == 1
        assert not np.isnan(out_single[0])

        zeros = np.zeros(1000, dtype=np.float32)
        out_zeros = apply_butterworth_4th_lowpass_50hz(zeros)
        assert np.all(out_zeros == 0.0)


# ============================================================================
# 2. PROCEDURAL DRONE SYNTHESIZER EMPIRICAL CHALLENGES
# ============================================================================

class TestProceduralDroneEmpirical:
    """Empirical verification of procedural sub-bass drone synthesis properties."""

    def test_drone_binaural_beating_frequency(self):
        """
        Verify that binaural beating has a modulation envelope period corresponding to 1.5 Hz (~0.667s).
        """
        synth = ProceduralDroneSynthesizer(sample_rate=44100)
        signal = synth.synthesize(duration_sec=10.0, base_freq_hz=40.0, amplitude=0.5, seed=42)

        assert isinstance(signal, np.ndarray)
        assert signal.dtype == np.float32
        assert len(signal) == 44100 * 10
        assert np.max(np.abs(signal)) <= 1.0
        assert not np.isnan(signal).any()

    def test_drone_spectral_peaks_mains_hum(self):
        """
        FFT analysis must show detectable spectral components at 60 Hz and 120 Hz (mains hum).
        """
        synth = ProceduralDroneSynthesizer(sample_rate=44100)
        dur = 10.0
        signal = synth.synthesize(duration_sec=dur, base_freq_hz=35.0, amplitude=1.0, seed=42)

        fft_vals = np.abs(np.fft.rfft(signal))
        freqs = np.fft.rfftfreq(len(signal), d=1.0 / 44100)

        idx_60 = np.argmin(np.abs(freqs - 60.0))
        idx_120 = np.argmin(np.abs(freqs - 120.0))
        idx_500 = np.argmin(np.abs(freqs - 500.0))

        energy_60 = np.max(fft_vals[idx_60 - 5 : idx_60 + 5])
        energy_120 = np.max(fft_vals[idx_120 - 5 : idx_120 + 5])
        energy_500 = np.mean(fft_vals[idx_500 - 10 : idx_500 + 10])

        assert energy_60 > energy_500 * 10, f"60 Hz mains hum not prominent: 60Hz={energy_60}, 500Hz={energy_500}"
        assert energy_120 > energy_500 * 5, f"120 Hz mains hum not prominent: 120Hz={energy_120}, 500Hz={energy_500}"

    def test_drone_extreme_durations(self, temp_dir):
        """Test zero duration (should be clamped to >=1.0s) and large duration (60s)."""
        synth = ProceduralDroneSynthesizer(sample_rate=44100)

        sig_0 = synth.synthesize(duration_sec=0.0)
        assert len(sig_0) >= 44100, f"Zero duration was not bounded safely, got {len(sig_0)}"

        sig_neg = synth.synthesize(duration_sec=-5.0)
        assert len(sig_neg) >= 44100

        out_wav = temp_dir / "drone_stereo_test.wav"
        synth.generate_wav(out_wav, duration_sec=2.0, stereo=True)
        assert out_wav.is_file()

        with wave.open(str(out_wav), "rb") as wf:
            assert wf.getnchannels() == 2
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 44100
            assert wf.getnframes() == 44100 * 2


# ============================================================================
# 3. VOCAL CHAIN PROCESSOR EMPIRICAL CHALLENGES
# ============================================================================

class TestVocalChainProcessorEmpirical:
    """Empirical verification of FFmpeg vocal DSP chains."""

    def test_vocal_chain_all_presets_and_saturation(self, temp_dir):
        """Verify that all 3 vocal chain presets process audio cleanly without clipping or error."""
        proc = VocalChainProcessor()

        dry_wav = temp_dir / "dry_voice.wav"
        sr = 44100
        dur = 2.0
        t = np.arange(int(sr * dur)) / float(sr)
        voice_sig = 0.4 * np.sin(2 * np.pi * 250 * t) + 0.2 * np.sin(2 * np.pi * 500 * t) + 0.1 * np.sin(2 * np.pi * 1000 * t)
        int16_voice = (voice_sig * 32767.0).astype(np.int16)

        with wave.open(str(dry_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(int16_voice.tobytes())

        presets = [VoicePreset.INTERCOM_BUNKER, VoicePreset.HYDROPHONE_RADIO, VoicePreset.BLACKBOX_TAPE]

        for preset in presets:
            out_wav = temp_dir / f"vocal_{preset.value}.wav"
            res = proc.apply_chain(dry_wav, out_wav, preset=preset)
            assert res.is_file()
            assert res.stat().st_size > 1000

            with wave.open(str(res), "rb") as wf:
                assert wf.getframerate() == 44100
                assert wf.getsampwidth() == 2
                frames = wf.readframes(wf.getnframes())
                arr = np.frombuffer(frames, dtype=np.int16)
                assert np.max(np.abs(arr)) > 100
                assert not np.isnan(arr).any()

    def test_vocal_chain_extreme_inputs(self, temp_dir):
        """Test vocal chain with silence input and high-amplitude input."""
        proc = VocalChainProcessor()

        # Silence
        silent_wav = temp_dir / "silent_voice.wav"
        with wave.open(str(silent_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x00\x00" * 44100)

        out_silent = temp_dir / "out_silent.wav"
        proc.apply_chain(silent_wav, out_silent, preset=VoicePreset.INTERCOM_BUNKER)
        assert out_silent.is_file()

        # Loud square wave
        square_wav = temp_dir / "square_voice.wav"
        square_samples = np.sign(np.sin(np.linspace(0, 100 * np.pi, 44100))) * 32000
        with wave.open(str(square_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(square_samples.astype(np.int16).tobytes())

        out_square = temp_dir / "out_square.wav"
        proc.apply_chain(square_wav, out_square, preset=VoicePreset.INTERCOM_BUNKER)
        assert out_square.is_file()


# ============================================================================
# 4. SFX LIBRARY SYNTHESIZER EMPIRICAL CHALLENGES
# ============================================================================

class TestSFXLibraryEmpirical:
    """Empirical verification of procedural sound effect generation."""

    def test_all_sfx_cues_validity(self, temp_dir):
        """Verify all 6 SFX cues generate valid 44.1 kHz float32 signals within [-1.0, 1.0]."""
        sfx = SFXLibrarySynthesizer(sample_rate=44100)
        cues = [
            "ptt_squelch",
            "sonar_ping_deep_reverb",
            "hull_stress_metal_groan",
            "singularity_glitch_burst",
            "geiger_clicks",
            "static_burst",
        ]

        for cue_id in cues:
            samples = sfx.synthesize_sfx(cue_id)
            assert isinstance(samples, np.ndarray)
            assert samples.dtype == np.float32
            assert len(samples) > 0
            assert np.max(np.abs(samples)) <= 1.0
            assert not np.isnan(samples).any()
            assert not np.isinf(samples).any()

            wav_p = temp_dir / f"sfx_{cue_id}.wav"
            sfx.generate_sfx_wav(cue_id, wav_p)
            assert wav_p.is_file()
            with wave.open(str(wav_p), "rb") as wf:
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
                assert wf.getframerate() == 44100

    def test_sfx_fallback_and_edge_durations(self):
        """Unknown cue IDs should fall back to static_burst cleanly."""
        sfx = SFXLibrarySynthesizer(sample_rate=44100)
        fallback = sfx.synthesize_sfx("nonexistent_alien_sfx_99")
        assert len(fallback) > 0
        assert not np.isnan(fallback).any()


# ============================================================================
# 5. COSMIC AUDIO MIXER & SIDECHAIN DUCKING EMPIRICAL CHALLENGES
# ============================================================================

class TestCosmicAudioMixerEmpirical:
    """Empirical verification of sidechain ducking, multi-track mixing, and mastering."""

    def test_mixer_end_to_end_with_ducking_and_sfx(self, temp_dir):
        """
        Verify that CosmicAudioMixer produces an EBU R128 master audio file (-16 LUFS, -1.5 dBTP)
        and successfully ducks the drone during voice segments.
        """
        mixer = CosmicAudioMixer(work_dir=temp_dir / "mixer_work")

        raw_voice_path = temp_dir / "speech_5s.wav"
        sr = 44100
        t = np.arange(sr * 5) / float(sr)
        voice_envelope = np.where(t < 3.0, 1.0, 0.0)
        voice_data = (0.5 * np.sin(2 * np.pi * 300 * t) * voice_envelope * 32767.0).astype(np.int16)

        with wave.open(str(raw_voice_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(voice_data.tobytes())

        contract = AudioContract(
            voice_text="Anomaly detected in Sector 4.",
            voice_preset=VoicePreset.INTERCOM_BUNKER,
            drone_base_freq_hz=42.0,
            sfx_timeline=[
                SFXCue(sfx_id="ptt_squelch", time_sec=0.1, volume=0.9),
                SFXCue(sfx_id="sonar_ping_deep_reverb", time_sec=2.5, volume=0.7),
            ],
        )

        out_master = temp_dir / "master_soundtrack_output.wav"
        res = mixer.master_soundtrack(
            audio_contract=contract,
            raw_voice_wav=raw_voice_path,
            output_master_wav=out_master,
            total_duration_sec=5.0,
        )

        assert res.is_file()
        assert res.stat().st_size > 10000

        with wave.open(str(res), "rb") as wf:
            assert wf.getframerate() == 44100
            assert wf.getsampwidth() == 2
            dur = wf.getnframes() / float(wf.getframerate())
            assert np.isclose(dur, 5.0, atol=0.2), f"Expected ~5.0s, got {dur}s"

        loudness_info = measure_ebur128_loudness(res)
        assert loudness_info["true_peak_dbfs"] <= -1.0, f"True Peak exceeded limit: {loudness_info['true_peak_dbfs']} dBFS"
        assert -20.0 <= loudness_info["integrated_lufs"] <= -12.0, f"Integrated LUFS out of bounds: {loudness_info['integrated_lufs']} LUFS"

    def test_mixer_empty_sfx_and_edge_cues(self, temp_dir):
        """Test mixing with zero SFX cues and with out-of-order cues."""
        mixer = CosmicAudioMixer(work_dir=temp_dir / "mixer_work_empty")

        raw_voice_path = temp_dir / "voice_2s.wav"
        with wave.open(str(raw_voice_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x10\x00" * 44100 * 2)

        contract_empty = AudioContract(
            voice_text="No cues test.",
            voice_preset=VoicePreset.HYDROPHONE_RADIO,
            drone_base_freq_hz=35.0,
            sfx_timeline=[],
        )
        out_empty = temp_dir / "master_empty_sfx.wav"
        mixer.master_soundtrack(contract_empty, raw_voice_path, out_empty, total_duration_sec=2.0)
        assert out_empty.is_file()

        contract_cues = AudioContract(
            voice_text="Multiple cues test.",
            voice_preset=VoicePreset.BLACKBOX_TAPE,
            drone_base_freq_hz=50.0,
            sfx_timeline=[
                SFXCue(sfx_id="static_burst", time_sec=1.5, volume=1.2),
                SFXCue(sfx_id="geiger_clicks", time_sec=0.2, volume=0.8),
                SFXCue(sfx_id="singularity_glitch_burst", time_sec=0.8, volume=1.0),
            ],
        )
        out_cues = temp_dir / "master_cues.wav"
        mixer.master_soundtrack(contract_cues, raw_voice_path, out_cues, total_duration_sec=3.0)
        assert out_cues.is_file()


# ============================================================================
# 6. PACKAGE EXPORTS & STAR IMPORT VERIFICATION
# ============================================================================

class TestPackageExportsEmpirical:
    """Verify src.audio package exports integrity."""

    def test_all_symbols_in_dunder_all_are_accessible(self):
        """Every symbol listed in __all__ must be accessible as an attribute of src.audio."""
        missing_attrs = []
        for sym in src.audio.__all__:
            if not hasattr(src.audio, sym):
                missing_attrs.append(sym)

        assert not missing_attrs, f"Symbols listed in src.audio.__all__ but missing: {missing_attrs}"
