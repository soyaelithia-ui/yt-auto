"""
src/audio - Cosmic & Analog Horror Audio Engine package.
Exposes modern Cosmic audio classes and re-exports legacy audio mastering utilities for backward compatibility.
"""
from __future__ import annotations

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

from src.config import EBU_R128_TARGET_LUFS

# Backward-compatibility alias
AudioMasteringError = AudioProcessingError

# Default Mastering Constants
DEFAULT_TARGET_LUFS: float = EBU_R128_TARGET_LUFS
DEFAULT_MAX_TP: float = -1.5
DEFAULT_MAX_LRA: float = 11.0


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
]

