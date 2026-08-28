"""
tests/unit/test_audio_synth.py - Unit tests for Procedural Drone, Vocal Chain, SFX Library, and Multi-track Mixer.
"""
import wave
from pathlib import Path
import pytest
import numpy as np

from src.audio.procedural_drone import ProceduralDroneSynthesizer, apply_butterworth_4th_lowpass_50hz
from src.audio.sfx_library import SFXLibrarySynthesizer
from src.audio.vocal_chain import VocalChainProcessor
from src.audio.mixer import CosmicAudioMixer
from src.narrative.schema import AudioContract, SFXCue, VoicePreset


def test_butterworth_4th_lowpass_filter() -> None:
    sample_rate = 44100
    t = np.arange(sample_rate) / float(sample_rate)
    # High frequency 500 Hz tone vs low frequency 20 Hz tone
    sig_low = np.sin(2.0 * np.pi * 20.0 * t)
    sig_high = np.sin(2.0 * np.pi * 500.0 * t)
    sig_mix = sig_low + sig_high

    filtered = apply_butterworth_4th_lowpass_50hz(sig_mix, sample_rate=sample_rate, cutoff_hz=50.0)

    # High frequency amplitude should be heavily attenuated
    assert len(filtered) == len(sig_mix)
    assert np.max(np.abs(filtered[2000:])) < np.max(np.abs(sig_mix))


def test_procedural_drone_synthesizer(tmp_path: Path) -> None:
    synth = ProceduralDroneSynthesizer(sample_rate=44100)
    samples = synth.synthesize(duration_sec=2.0, base_freq_hz=38.0, amplitude=0.3)
    assert len(samples) == 44100 * 2
    assert np.max(np.abs(samples)) <= 1.0

    wav_file = tmp_path / "drone_test.wav"
    synth.generate_wav(wav_file, duration_sec=2.0, base_freq_hz=38.0)
    assert wav_file.is_file()
    assert wav_file.stat().st_size > 0

    with wave.open(str(wav_file), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 44100
        assert wf.getsampwidth() == 2


def test_sfx_library_synthesizer(tmp_path: Path) -> None:
    synth = SFXLibrarySynthesizer(sample_rate=44100)
    sfx_ids = [
        "ptt_squelch",
        "sonar_ping_deep_reverb",
        "hull_stress_metal_groan",
        "singularity_glitch_burst",
        "geiger_clicks",
        "static_burst",
    ]

    for sid in sfx_ids:
        wav_path = tmp_path / f"{sid}.wav"
        synth.generate_sfx_wav(sid, wav_path)
        assert wav_path.is_file()
        assert wav_path.stat().st_size > 0


def test_audio_mixer_end_to_end(tmp_path: Path) -> None:
    # 1. Create a dummy dry voice file
    voice_wav = tmp_path / "voice_dry.wav"
    sample_rate = 44100
    duration = 3.0
    t = np.arange(int(sample_rate * duration)) / float(sample_rate)
    voice_samples = (0.5 * np.sin(2.0 * np.pi * 220.0 * t) * 32767.0).astype(np.int16)
    with wave.open(str(voice_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(voice_samples.tobytes())

    # 2. Setup mixer
    mixer = CosmicAudioMixer(work_dir=tmp_path / "work")
    audio_contract = AudioContract(
        voice_text="Prueba de audio en búnker subterráneo...",
        voice_preset=VoicePreset.INTERCOM_BUNKER,
        drone_base_freq_hz=38.0,
        sfx_timeline=[
            SFXCue(time_sec=0.0, sfx_id="ptt_squelch", volume=1.0),
            SFXCue(time_sec=1.5, sfx_id="sonar_ping_deep_reverb", volume=0.8),
        ],
    )

    master_wav = tmp_path / "master_soundtrack.wav"
    out_res = mixer.master_soundtrack(
        audio_contract=audio_contract,
        raw_voice_wav=voice_wav,
        output_master_wav=master_wav,
        total_duration_sec=3.0,
    )

    assert out_res.is_file()
    assert out_res.stat().st_size > 0
    with wave.open(str(out_res), "rb") as wf:
        assert wf.getframerate() == 44100
