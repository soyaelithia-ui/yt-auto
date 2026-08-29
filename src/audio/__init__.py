"""
src/audio - Cosmic & Analog Horror Audio Engine package.
Exposes modern Cosmic audio classes and re-exports legacy audio mastering utilities for backward compatibility.
"""
from __future__ import annotations

import math
import os
import struct
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Modern Cosmic Audio Components
from src.audio.procedural_drone import ProceduralDroneSynthesizer, apply_butterworth_4th_lowpass_50hz
from src.audio.vocal_chain import VocalChainProcessor, VOCAL_FILTERGRAPHS
from src.audio.sfx_library import SFXLibrarySynthesizer
from src.audio.mixer import CosmicAudioMixer
from src.narrative.schema import VoicePreset, AudioContract, SFXCue

# Legacy Audio Mastering Re-exports from lib.audio
from lib.audio import (
    AudioProcessingError,
    FFmpegExecutionError,
    DEFAULT_BACKGROUND_AUDIO_VOLUME,
    DEFAULT_DUCKING_DB,
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
)

# Backward-compatibility alias
AudioMasteringError = AudioProcessingError

# Default Mastering Constants
DEFAULT_TARGET_LUFS: float = -14.0
DEFAULT_MAX_TP: float = -1.5
DEFAULT_MAX_LRA: float = 11.0


def generate_synthetic_pcm_audio(out_path: Union[str, Path], duration_sec: float = 5.0, freq: float = 440.0) -> str:
    """Generates valid 16-bit PCM WAV audio for test environments."""
    sample_rate = 44100
    num_samples = int(sample_rate * duration_sec)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = []
        for i in range(num_samples):
            value = int(16000 * math.sin(2 * math.pi * freq * i / sample_rate))
            frames.append(struct.pack("<hh", value, value))
        wav_file.writeframes(b"".join(frames))
    return str(out_path)


__all__ = [
    # Modern Cosmic Audio
    "ProceduralDroneSynthesizer",
    "apply_butterworth_4th_lowpass_50hz",
    "VocalChainProcessor",
    "VOCAL_FILTERGRAPHS",
    "SFXLibrarySynthesizer",
    "CosmicAudioMixer",
    "VoicePreset",
    "AudioContract",
    "SFXCue",
    # Legacy Audio Engine Re-exports
    "AudioMasteringError",
    "AudioProcessingError",
    "FFmpegExecutionError",
    "DEFAULT_BACKGROUND_AUDIO_VOLUME",
    "DEFAULT_DUCKING_DB",
    "DEFAULT_TARGET_LUFS",
    "DEFAULT_MAX_TP",
    "DEFAULT_MAX_LRA",
    "_ffmpeg_run",
    "_looks_like_real_input",
    "parse_pause_duration",
    "parse_dramatic_pauses",
    "extract_dramatic_pauses",
    "strip_dramatic_pauses",
    "generate_silence_audio",
    "shift_word_timestamps_with_pauses",
    "insert_dramatic_pauses_to_audio",
    "normalize_narration_lufs",
    "build_sidechain_ducking_filter_graph",
    "apply_sidechain_ducking",
    "master_audio_track",
    "generate_synthetic_pcm_audio",
]

