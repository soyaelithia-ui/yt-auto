"""Zero-dependency synthetic audio generator for tests."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Union


def generate_synthetic_pcm_audio(
    out_path: Union[str, Path],
    duration_sec: float = 5.0,
    freq: float = 440.0,
) -> str:
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
