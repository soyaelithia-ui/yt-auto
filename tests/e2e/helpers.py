"""
Helper utilities for E2E Tests in yt-auto Visual Pipeline.
Provides deterministic, offline asset synthesis (WAV, RGBA buffers, timestamps)
and media probing functions.
"""

from __future__ import annotations

import json
import math
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


def generate_synthetic_wav(
    output_path: Path,
    duration_sec: float = 1.0,
    frequency: float = 440.0,
    sample_rate: int = 44100,
    channels: int = 2,
    amplitude: float = 0.5,
) -> Path:
    """Generate a clean synthetic sine-wave WAV file using standard Python wave library."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    num_samples = int(sample_rate * duration_sec)
    
    with wave.open(str(output_path), "w") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(sample_rate)
        
        frames = bytearray()
        for i in range(num_samples):
            t = float(i) / sample_rate
            # Sine wave sample in range [-32767, 32767]
            val = int(32767.0 * amplitude * math.sin(2.0 * math.pi * frequency * t))
            sample_bytes = struct.pack("<h", val)
            for _ in range(channels):
                frames.extend(sample_bytes)
        
        wav_file.writeframes(frames)
    
    return output_path


def generate_synthetic_rgba_frame(
    width: int = 1080,
    height: int = 1920,
    color: Tuple[int, int, int, int] = (128, 64, 32, 255),
) -> np.ndarray:
    """Generate a contiguous uint8 RGBA numpy array of shape (height, width, 4)."""
    frame = np.zeros((height, width, 4), dtype=np.uint8)
    frame[:, :, 0] = color[0]
    frame[:, :, 1] = color[1]
    frame[:, :, 2] = color[2]
    frame[:, :, 3] = color[3]
    return frame


def generate_sample_word_timestamps(
    words: Optional[List[str]] = None,
    start_offset: float = 0.5,
    word_duration: float = 0.25,
    inter_word_gap: float = 0.05,
) -> List[Dict[str, Any]]:
    """Generate deterministic word-level timestamp entries for subtitle testing."""
    if words is None:
        words = [
            "The", "cosmic", "singularity", "expanded", "across",
            "the", "event", "horizon", "revealing", "secrets",
        ]
    
    timestamps: List[Dict[str, Any]] = []
    current_time = start_offset
    
    for word in words:
        end_time = current_time + word_duration
        timestamps.append({
            "word": word,
            "start": round(current_time, 3),
            "end": round(end_time, 3),
            "confidence": 0.99,
        })
        current_time = end_time + inter_word_gap
        
    return timestamps


def ffprobe_media_file(media_path: Path) -> Dict[str, Any]:
    """Inspect media file using ffprobe and return parsed JSON metadata."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(media_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


def check_faststart_moov_atom(mp4_path: Path) -> bool:
    """Verify if the MP4 file has faststart enabled (moov atom before mdat atom)."""
    with open(mp4_path, "rb") as f:
        data = f.read(1024 * 1024)  # Read first 1MB
    
    moov_pos = data.find(b"moov")
    mdat_pos = data.find(b"mdat")
    
    if moov_pos != -1 and mdat_pos != -1:
        return moov_pos < mdat_pos
    elif moov_pos != -1:
        return True
    return False
