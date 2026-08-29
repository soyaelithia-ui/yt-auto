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


def test_vocal_chain_processor_all_presets(tmp_path: Path) -> None:
    proc = VocalChainProcessor()
    sample_rate = 44100
    duration = 1.0
    t = np.arange(int(sample_rate * duration)) / float(sample_rate)
    voice_samples = (0.4 * np.sin(2.0 * np.pi * 440.0 * t) * 32767.0).astype(np.int16)

    voice_wav = tmp_path / "voice_in.wav"
    with wave.open(str(voice_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(voice_samples.tobytes())

    presets = [
        VoicePreset.INTERCOM_BUNKER,
        VoicePreset.HYDROPHONE_RADIO,
        VoicePreset.BLACKBOX_TAPE,
        "intercom_bunker",
        "unknown_preset_fallback",
    ]

    for idx, preset in enumerate(presets):
        out_wav = tmp_path / f"voice_out_{idx}.wav"
        res = proc.apply_chain(voice_wav, out_wav, preset=preset)
        assert res.is_file()
        assert res.stat().st_size > 0
        with wave.open(str(res), "rb") as wf:
            assert wf.getframerate() == 44100
            assert wf.getsampwidth() == 2


def test_vocal_chain_processor_missing_file_raises(tmp_path: Path) -> None:
    proc = VocalChainProcessor()
    missing_wav = tmp_path / "missing.wav"
    out_wav = tmp_path / "out.wav"
    with pytest.raises(FileNotFoundError):
        proc.apply_chain(missing_wav, out_wav)


def test_procedural_drone_synthesizer_stereo_and_determinism(tmp_path: Path) -> None:
    synth = ProceduralDroneSynthesizer(sample_rate=44100)

    # Determinism
    s1 = synth.synthesize(duration_sec=1.0, base_freq_hz=40.0, seed=12345)
    s2 = synth.synthesize(duration_sec=1.0, base_freq_hz=40.0, seed=12345)
    np.testing.assert_array_almost_equal(s1, s2)

    # Stereo WAV export
    stereo_wav = tmp_path / "drone_stereo.wav"
    synth.generate_wav(stereo_wav, duration_sec=1.5, base_freq_hz=40.0, stereo=True)
    assert stereo_wav.is_file()
    with wave.open(str(stereo_wav), "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 44100
        assert wf.getsampwidth() == 2


def test_butterworth_filter_empty_input() -> None:
    empty_arr = np.array([], dtype=np.float32)
    filtered = apply_butterworth_4th_lowpass_50hz(empty_arr)
    assert len(filtered) == 0


def test_sfx_library_fallback_unknown_id(tmp_path: Path) -> None:
    synth = SFXLibrarySynthesizer(sample_rate=44100)
    samples = synth.synthesize_sfx("non_existent_sfx_id", duration_sec=0.3)
    assert len(samples) > 0
    assert np.max(np.abs(samples)) <= 1.0


def test_audio_mixer_empty_sfx_and_missing_voice(tmp_path: Path) -> None:
    mixer = CosmicAudioMixer(work_dir=tmp_path / "work_empty")

    # Missing voice raises FileNotFoundError
    audio_contract = AudioContract(
        voice_text="Test",
        voice_preset=VoicePreset.INTERCOM_BUNKER,
        drone_base_freq_hz=38.0,
        sfx_timeline=[],
    )
    with pytest.raises(FileNotFoundError):
        mixer.master_soundtrack(
            audio_contract=audio_contract,
            raw_voice_wav=tmp_path / "missing_voice.wav",
            output_master_wav=tmp_path / "out_master.wav",
            total_duration_sec=2.0,
        )

    # Valid voice with empty SFX timeline
    voice_wav = tmp_path / "valid_voice.wav"
    sample_rate = 44100
    duration = 2.0
    t = np.arange(int(sample_rate * duration)) / float(sample_rate)
    voice_samples = (0.3 * np.sin(2.0 * np.pi * 300.0 * t) * 32767.0).astype(np.int16)
    with wave.open(str(voice_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(voice_samples.tobytes())

    master_wav = tmp_path / "master_no_sfx.wav"
    res = mixer.master_soundtrack(
        audio_contract=audio_contract,
        raw_voice_wav=voice_wav,
        output_master_wav=master_wav,
        total_duration_sec=2.0,
    )
    assert res.is_file()
    assert res.stat().st_size > 0


def test_src_audio_package_exports_and_synthetic_pcm(tmp_path: Path) -> None:
    import src.audio as audio_pkg
    from tests.helpers.audio import generate_synthetic_pcm_audio

    # Check key exports
    assert hasattr(audio_pkg, "ProceduralDroneSynthesizer")
    assert hasattr(audio_pkg, "VocalChainProcessor")
    assert hasattr(audio_pkg, "SFXLibrarySynthesizer")
    assert hasattr(audio_pkg, "CosmicAudioMixer")
    assert hasattr(audio_pkg, "VoicePreset")
    assert hasattr(audio_pkg, "normalize_narration_lufs")
    assert hasattr(audio_pkg, "apply_sidechain_ducking")
    assert hasattr(audio_pkg, "master_audio_track")
    assert hasattr(audio_pkg, "AudioProcessingError")
    assert hasattr(audio_pkg, "AudioMasteringError")

    pcm_wav = tmp_path / "test_synth_pcm.wav"
    res = generate_synthetic_pcm_audio(str(pcm_wav), duration_sec=1.0, freq=440.0)
    assert Path(res).is_file()
    with wave.open(res, "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 44100
        assert wf.getsampwidth() == 2
        assert wf.getnframes() == 44100


def test_audio_mixer_single_sfx(tmp_path: Path) -> None:
    # 1. Create a dummy dry voice file
    voice_wav = tmp_path / "voice_dry.wav"
    sample_rate = 44100
    duration = 2.0
    t = np.arange(int(sample_rate * duration)) / float(sample_rate)
    voice_samples = (0.5 * np.sin(2.0 * np.pi * 220.0 * t) * 32767.0).astype(np.int16)
    with wave.open(str(voice_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(voice_samples.tobytes())

    mixer = CosmicAudioMixer(work_dir=tmp_path / "work_single_sfx")
    audio_contract = AudioContract(
        voice_text="Prueba de audio con un solo SFX...",
        voice_preset=VoicePreset.INTERCOM_BUNKER,
        drone_base_freq_hz=38.0,
        sfx_timeline=[
            SFXCue(time_sec=0.5, sfx_id="ptt_squelch", volume=1.0),
        ],
    )

    master_wav = tmp_path / "master_single_sfx.wav"
    out_res = mixer.master_soundtrack(
        audio_contract=audio_contract,
        raw_voice_wav=voice_wav,
        output_master_wav=master_wav,
        total_duration_sec=2.0,
    )

    assert out_res.is_file()
    assert out_res.stat().st_size > 0
    with wave.open(str(out_res), "rb") as wf:
        assert wf.getframerate() == 44100

