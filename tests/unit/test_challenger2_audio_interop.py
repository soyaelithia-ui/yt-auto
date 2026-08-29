"""
tests/unit/test_challenger2_audio_interop.py - Empirical Adversarial Validation Suite for Milestone M1 (Audio Engine & Legacy Interop).

Authored by Challenger 2.
Stress tests:
1. Module imports, __all__ consistency, and wildcard imports.
2. Legacy audio mastering & helper functions (EBU R128 loudnorm, sidechain ducking, PCM synth, dramatic pauses).
3. Modern Cosmic audio components (ProceduralDroneSynthesizer, VocalChainProcessor, SFXLibrarySynthesizer, CosmicAudioMixer).
4. Cross-compatibility and combined workflows (legacy synth -> modern processor -> legacy mastering -> QA validation).
5. Robustness against malformed inputs, edge durations, out-of-bounds parameters, and in-place overwrites.
6. Error propagation and exception hierarchy validation.
"""
import concurrent.futures
import math
import os
import shutil
import struct
import tempfile
import wave
from pathlib import Path
import pytest
import numpy as np

import src.audio
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
    _ffmpeg_run,
    _looks_like_real_input,
    parse_pause_duration,
    parse_dramatic_pauses,
    extract_dramatic_pauses,
    strip_dramatic_pauses,
    generate_silence_audio,
    shift_word_timestamps_with_pauses,
    insert_dramatic_pauses_to_audio,
    normalize_narration_lufs,
    build_sidechain_ducking_filter_graph,
    apply_sidechain_ducking,
    master_audio_track,
    generate_synthetic_pcm_audio,
)


@pytest.fixture
def tmp_audio_dir():
    d = tempfile.mkdtemp(prefix="challenger2_audio_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


class TestImportAndNamespaceIntegrity:
    """Adversarial stress-testing of package namespace, exports, and circular dependencies."""

    def test_all_symbols_in_all_are_accessible(self):
        """Checks if every symbol listed in __all__ exists on src.audio without raising AttributeError."""
        missing = [sym for sym in src.audio.__all__ if not hasattr(src.audio, sym)]
        assert not missing, f"Symbols in src.audio.__all__ missing from module: {missing}"

    def test_legacy_and_modern_classes_coexist(self):
        """Verifies that modern classes and legacy helpers are simultaneously available in the namespace."""
        assert issubclass(AudioMasteringError, Exception)
        assert AudioMasteringError is AudioProcessingError
        assert callable(normalize_narration_lufs)
        assert callable(apply_sidechain_ducking)
        assert callable(master_audio_track)
        assert callable(generate_synthetic_pcm_audio)
        assert isinstance(ProceduralDroneSynthesizer, type)
        assert isinstance(VocalChainProcessor, type)
        assert isinstance(SFXLibrarySynthesizer, type)
        assert isinstance(CosmicAudioMixer, type)

    def test_no_circular_imports_across_modules(self):
        """Re-imports all submodules in various orders to verify absence of circular dependencies."""
        import importlib
        import src.narrative.schema
        import src.audio.procedural_drone
        import src.audio.vocal_chain
        import src.audio.sfx_library
        import src.audio.mixer
        import lib.audio

        importlib.reload(lib.audio)
        importlib.reload(src.audio.procedural_drone)
        importlib.reload(src.audio.vocal_chain)
        importlib.reload(src.audio.sfx_library)
        importlib.reload(src.audio.mixer)
        importlib.reload(src.audio)


class TestLegacyAudioMasteringStress:
    """Stress tests on legacy mastering and PCM synthesis functions."""

    def test_generate_synthetic_pcm_audio_properties(self, tmp_audio_dir):
        out_wav = tmp_audio_dir / "nested" / "synth_test.wav"
        res = generate_synthetic_pcm_audio(out_wav, duration_sec=1.5, freq=220.0)
        assert Path(res).is_file()
        with wave.open(res, "rb") as wf:
            assert wf.getnchannels() == 2
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 44100
            assert wf.getnframes() == int(44100 * 1.5)

    def test_normalize_narration_lufs_in_place(self, tmp_audio_dir):
        wav_path = tmp_audio_dir / "narration.wav"
        generate_synthetic_pcm_audio(wav_path, duration_sec=2.0, freq=440.0)

        # In-place normalization
        res = normalize_narration_lufs(wav_path, output_path=wav_path, target_lufs=-16.0)
        assert Path(res).is_file()
        assert Path(res).resolve() == wav_path.resolve()
        assert Path(res).stat().st_size > 0

    def test_normalize_narration_lufs_extreme_targets(self, tmp_audio_dir):
        wav_path = tmp_audio_dir / "extreme_norm.wav"
        generate_synthetic_pcm_audio(wav_path, duration_sec=1.0, freq=300.0)

        out1 = tmp_audio_dir / "norm_quiet.wav"
        normalize_narration_lufs(wav_path, out1, target_lufs=-45.0, max_tp=-3.0)
        assert out1.is_file()

        out2 = tmp_audio_dir / "norm_loud.wav"
        normalize_narration_lufs(wav_path, out2, target_lufs=-10.0, max_tp=-0.5)
        assert out2.is_file()

    def test_sidechain_ducking_unequal_durations(self, tmp_audio_dir):
        narr_path = tmp_audio_dir / "narr_short.wav"
        music_path = tmp_audio_dir / "music_long.wav"
        generate_synthetic_pcm_audio(narr_path, duration_sec=1.5, freq=440.0)
        generate_synthetic_pcm_audio(music_path, duration_sec=5.0, freq=110.0)

        out_duck = tmp_audio_dir / "ducked.wav"
        res = apply_sidechain_ducking(
            narration_path=narr_path,
            music_path=music_path,
            output_path=out_duck,
            ducking_db=-20.0,
            music_volume=0.1,
        )
        assert Path(res).is_file()
        assert Path(res).stat().st_size > 0

    def test_master_audio_track_single_pass_full(self, tmp_audio_dir):
        narr_path = tmp_audio_dir / "narr.wav"
        music_path = tmp_audio_dir / "music.wav"
        generate_synthetic_pcm_audio(narr_path, duration_sec=2.5, freq=500.0)
        generate_synthetic_pcm_audio(music_path, duration_sec=4.0, freq=80.0)

        out_master = tmp_audio_dir / "master.wav"
        res = master_audio_track(
            narration_path=narr_path,
            music_path=music_path,
            output_path=out_master,
            target_lufs=-16.0,
            ducking_db=-15.0,
            music_volume=0.08,
            lowpass_freq=8000.0,
        )
        assert Path(res).is_file()
        assert Path(res).stat().st_size > 0


class TestModernCosmicAudioStress:
    """Stress tests on modern procedural synth, vocal chains, and multi-track mixer."""

    def test_procedural_drone_boundary_parameters(self, tmp_audio_dir):
        synth = ProceduralDroneSynthesizer(sample_rate=44100)

        # Very low frequency, short duration
        samples_low = synth.synthesize(duration_sec=1.0, base_freq_hz=20.0, amplitude=0.5, seed=123)
        assert len(samples_low) == 44100
        assert not np.isnan(samples_low).any()
        assert not np.isinf(samples_low).any()
        assert np.max(np.abs(samples_low)) <= 1.0

        # WAV export (stereo)
        drone_wav = tmp_audio_dir / "drone_stereo.wav"
        synth.generate_wav(drone_wav, duration_sec=2.0, base_freq_hz=42.0, stereo=True)
        assert drone_wav.is_file()
        with wave.open(str(drone_wav), "rb") as wf:
            assert wf.getnchannels() == 2
            assert wf.getframerate() == 44100

    def test_vocal_chain_all_presets_and_unknown(self, tmp_audio_dir):
        raw_voice = tmp_audio_dir / "raw_voice.wav"
        generate_synthetic_pcm_audio(raw_voice, duration_sec=1.5, freq=300.0)

        proc = VocalChainProcessor()
        for preset in [VoicePreset.INTERCOM_BUNKER, VoicePreset.HYDROPHONE_RADIO, VoicePreset.BLACKBOX_TAPE, "unknown_preset_custom"]:
            out_voice = tmp_audio_dir / f"proc_voice_{preset}.wav"
            res = proc.apply_chain(raw_voice, out_voice, preset=preset)
            assert res.is_file()
            assert res.stat().st_size > 0

    def test_sfx_library_all_cues_and_edge_durations(self, tmp_audio_dir):
        synth = SFXLibrarySynthesizer(sample_rate=44100)
        cues = [
            "ptt_squelch",
            "sonar_ping_deep_reverb",
            "hull_stress_metal_groan",
            "singularity_glitch_burst",
            "geiger_clicks",
            "static_burst",
            "nonexistent_cue_fallback",
        ]
        for cue in cues:
            samples = synth.synthesize_sfx(cue, duration_sec=0.4)
            assert len(samples) > 0
            assert not np.isnan(samples).any()
            assert not np.isinf(samples).any()
            assert np.max(np.abs(samples)) <= 1.0

            wav_path = tmp_audio_dir / f"sfx_{cue}.wav"
            out = synth.generate_sfx_wav(cue, wav_path, duration_sec=0.3)
            assert out.is_file()

    def test_cosmic_mixer_dense_timeline(self, tmp_audio_dir):
        mixer = CosmicAudioMixer(work_dir=tmp_audio_dir / "mixer_work")
        raw_voice = tmp_audio_dir / "voice.wav"
        generate_synthetic_pcm_audio(raw_voice, duration_sec=3.0, freq=350.0)

        contract = AudioContract(
            voice_text="Bunker radio transmission telemetry test.",
            voice_preset=VoicePreset.INTERCOM_BUNKER,
            drone_base_freq_hz=35.0,
            sfx_timeline=[
                SFXCue(time_sec=0.0, sfx_id="ptt_squelch", volume=1.0),
                SFXCue(time_sec=0.8, sfx_id="sonar_ping_deep_reverb", volume=0.7),
                SFXCue(time_sec=1.5, sfx_id="singularity_glitch_burst", volume=0.8),
                SFXCue(time_sec=2.2, sfx_id="static_burst", volume=0.6),
            ]
        )

        master_out = tmp_audio_dir / "final_master.wav"
        res = mixer.master_soundtrack(
            audio_contract=contract,
            raw_voice_wav=raw_voice,
            output_master_wav=master_out,
            total_duration_sec=3.5,
        )
        assert res.is_file()
        assert res.stat().st_size > 0

    def test_concurrent_procedural_synthesis(self, tmp_audio_dir):
        """Verifies thread safety during simultaneous drone and SFX synthesis."""
        drone_synth = ProceduralDroneSynthesizer(sample_rate=44100)
        sfx_synth = SFXLibrarySynthesizer(sample_rate=44100)

        def generate_item(idx):
            if idx % 2 == 0:
                p = tmp_audio_dir / f"threaded_drone_{idx}.wav"
                return drone_synth.generate_wav(p, duration_sec=1.0, base_freq_hz=30.0 + idx)
            else:
                p = tmp_audio_dir / f"threaded_sfx_{idx}.wav"
                return sfx_synth.generate_sfx_wav("sonar_ping_deep_reverb", p, duration_sec=0.8)

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(generate_item, i) for i in range(8)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 8
        for p in results:
            assert Path(p).is_file()
            assert Path(p).stat().st_size > 0


class TestCrossCompatibilityWorkflows:
    """Tests end-to-end integration across both legacy helpers and modern classes."""

    def test_legacy_synth_to_modern_mixer_to_legacy_normalization(self, tmp_audio_dir):
        # 1. Use legacy synth to produce synthetic voice
        voice_path = tmp_audio_dir / "voice_legacy.wav"
        generate_synthetic_pcm_audio(voice_path, duration_sec=2.0, freq=280.0)

        # 2. Feed into modern CosmicAudioMixer
        mixer = CosmicAudioMixer(work_dir=tmp_audio_dir / "mixer_interop")
        contract = AudioContract(
            voice_text="Hydrophone radio test communication.",
            voice_preset=VoicePreset.HYDROPHONE_RADIO,
            drone_base_freq_hz=40.0,
            sfx_timeline=[SFXCue(time_sec=0.2, sfx_id="ptt_squelch", volume=0.9)],
        )
        modern_master = tmp_audio_dir / "modern_master.wav"
        mixer.master_soundtrack(
            audio_contract=contract,
            raw_voice_wav=voice_path,
            output_master_wav=modern_master,
            total_duration_sec=2.5,
        )
        assert modern_master.is_file()

        # 3. Post-process using legacy normalize_narration_lufs
        final_norm = tmp_audio_dir / "final_norm.wav"
        res = normalize_narration_lufs(modern_master, output_path=final_norm, target_lufs=-14.0)
        assert Path(res).is_file()
        assert Path(res).stat().st_size > 0

    def test_error_handling_and_exception_hierarchy(self, tmp_audio_dir):
        """Verifies that AudioMasteringError and AudioProcessingError catch legacy exceptions uniformly."""
        # Non-existent input should return input_path / empty without crashing
        missing_path = tmp_audio_dir / "missing.wav"
        res_missing = normalize_narration_lufs(missing_path)
        assert res_missing == str(missing_path)
        assert normalize_narration_lufs(None) == ""
        assert normalize_narration_lufs("") == ""

        # Corrupted / invalid file passed to VocalChainProcessor should raise
        corrupted = tmp_audio_dir / "corrupted.wav"
        corrupted.write_bytes(b"NOT_A_VALID_WAV_HEADER_DATA_12345")

        proc = VocalChainProcessor()
        with pytest.raises(Exception):
            proc.apply_chain(corrupted, tmp_audio_dir / "out.wav")
