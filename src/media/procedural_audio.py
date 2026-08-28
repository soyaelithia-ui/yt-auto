"""
src/media/procedural_audio.py - Procedural Ambient Soundscape Synthesis Engine.

Generates broadcast-ready, seamless, low-amplitude ambient background audio tracks
for video production lanes (horror, cosmic horror, drama, AITA, SCP, and neutral ambient)
without external network dependencies or API quota consumption.
"""
from __future__ import annotations

import math
import os
import random
import struct
import wave
from pathlib import Path
from typing import Optional, Union

from src.log import get_logger

logger = get_logger("procedural_audio")


class ProceduralAudioEngine:
    """Synthesizes theme-specific procedural ambient beds in 48kHz 16-bit stereo PCM."""

    SAMPLE_RATE: int = 48000
    CHANNELS: int = 2
    SAMPLE_WIDTH: int = 2  # 16-bit signed integer

    # Base harmonic frequencies (Hz) per theme
    THEME_FREQUENCIES: dict[str, list[float]] = {
        "horror": [45.0, 53.5, 90.0, 108.0],
        "cosmic_horror": [38.0, 48.0, 76.0, 114.0],
        "creepypasta": [45.0, 55.0, 90.0, 110.0],
        "drama": [130.81, 164.81, 196.00, 261.63],  # C3 major triad warm pad
        "aita": [130.81, 155.56, 196.00, 261.63],   # C3 minor triad introspective pad
        "reddit_aita": [130.81, 155.56, 196.00, 261.63],
        "scp": [50.0, 60.0, 120.0, 180.0],          # Mains hum & laboratory background
        "tactical": [50.0, 60.0, 100.0, 150.0],
        "default": [65.41, 98.00, 130.81, 196.00],   # C2 warm root fifth
        "neutral": [65.41, 98.00, 130.81, 196.00],
    }

    def __init__(self, sample_rate: int = 48000) -> None:
        self.sample_rate = sample_rate

    def _normalize_theme(self, theme: Optional[str]) -> str:
        if not theme:
            return "default"
        t = str(theme).lower().strip()
        if "cosmic" in t or "horror" in t or "creepypasta" in t or "nosleep" in t or "dark" in t:
            return "cosmic_horror" if "cosmic" in t else "horror"
        if "drama" in t or "aita" in t or "malo" in t or "relaciones" in t:
            return "drama"
        if "scp" in t or "contencion" in t or "containment" in t:
            return "scp"
        return "default"

    def synthesize_ambient_pcm(
        self,
        theme: str = "horror",
        duration_sec: float = 30.0,
        base_amplitude: float = 0.25,
        seed: Optional[int] = None,
    ) -> bytes:
        """
        Generates raw 16-bit stereo PCM byte array for the specified theme.

        - Horror / Cosmic: Deep sub-bass drones + detuned low oscillators + soft brownian noise.
        - Drama / AITA: Soft harmonic chord pad with gentle LFO breathing.
        - SCP / Tactical: Mains hum / lab ventilation ambient drone.
        - Default: Soft warm ambient bed.
        """
        duration_sec = max(1.0, float(duration_sec))
        norm_theme = self._normalize_theme(theme)
        freqs = self.THEME_FREQUENCIES.get(norm_theme, self.THEME_FREQUENCIES["default"])

        try:
            import numpy as np

            rng = random.Random(seed if seed is not None else 42)
            np_rng = np.random.default_rng(seed if seed is not None else 42)
            num_samples = int(self.sample_rate * duration_sec)

            t = np.arange(num_samples, dtype=np.float32) / float(self.sample_rate)

            # Fade envelope
            fade = np.ones(num_samples, dtype=np.float32)
            fade_len = int(self.sample_rate * min(1.5, duration_sec * 0.1))
            if fade_len > 0:
                ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(fade_len, dtype=np.float32) / fade_len))
                fade[:fade_len] = ramp
                fade[-fade_len:] = ramp[::-1]

            # LFO modulators
            lfo1 = 0.75 + 0.25 * np.sin(2.0 * np.pi * 0.08 * t)
            lfo2 = 0.75 + 0.25 * np.cos(2.0 * np.pi * 0.12 * t + (np.pi / 4.0))

            left_sample = np.zeros(num_samples, dtype=np.float32)
            right_sample = np.zeros(num_samples, dtype=np.float32)

            for idx, f in enumerate(freqs):
                init_phase = rng.uniform(0.0, 2.0 * math.pi)
                weight = 1.0 / (idx + 1.2)
                osc = np.sin((2.0 * np.pi * f * t) + init_phase) * weight
                if idx % 2 == 0:
                    left_sample += osc * 0.9
                    right_sample += osc * 0.6
                else:
                    left_sample += osc * 0.6
                    right_sample += osc * 0.9

            # Brownian noise bed
            white_l = np_rng.uniform(-0.04, 0.04, size=num_samples).astype(np.float32)
            white_r = np_rng.uniform(-0.04, 0.04, size=num_samples).astype(np.float32)
            brown_l = np.cumsum(white_l * 0.02)
            brown_r = np.cumsum(white_r * 0.02)
            b_scale = max(1e-4, float(np.max(np.abs(brown_l))), float(np.max(np.abs(brown_r))))
            brown_l = (brown_l / b_scale) * 0.05
            brown_r = (brown_r / b_scale) * 0.05

            left_sample = (left_sample * lfo1 + brown_l * 0.3) * fade
            right_sample = (right_sample * lfo2 + brown_r * 0.3) * fade

            target_peak = 32767.0 * min(1.0, max(0.01, base_amplitude))
            s_left = np.clip(left_sample * target_peak * 0.6, -32767, 32767).astype(np.int16)
            s_right = np.clip(right_sample * target_peak * 0.6, -32767, 32767).astype(np.int16)

            interleaved = np.empty((num_samples, 2), dtype=np.int16)
            interleaved[:, 0] = s_left
            interleaved[:, 1] = s_right
            return interleaved.tobytes()
        except ImportError:
            rng = random.Random(seed if seed is not None else 42)
            num_samples = int(self.sample_rate * duration_sec)
            phase_incs = [2.0 * math.pi * f / self.sample_rate for f in freqs]
            phases = [rng.uniform(0.0, 2.0 * math.pi) for _ in freqs]
            lfo_inc_1 = 2.0 * math.pi * 0.08 / self.sample_rate
            lfo_inc_2 = 2.0 * math.pi * 0.12 / self.sample_rate
            lfo_phase_1 = 0.0
            lfo_phase_2 = math.pi / 4.0
            brown_left = 0.0
            brown_right = 0.0
            target_peak = 32767.0 * min(1.0, max(0.01, base_amplitude))
            frames: list[bytes] = []
            for i in range(num_samples):
                fade = 1.0
                fade_len = int(self.sample_rate * min(1.5, duration_sec * 0.1))
                if i < fade_len:
                    fade = 0.5 * (1.0 - math.cos(math.pi * i / fade_len))
                elif i > num_samples - fade_len:
                    fade = 0.5 * (1.0 - math.cos(math.pi * (num_samples - i) / fade_len))
                lfo1 = 0.75 + 0.25 * math.sin(lfo_phase_1)
                lfo2 = 0.75 + 0.25 * math.cos(lfo_phase_2)
                left_sample = 0.0
                right_sample = 0.0
                for idx, p_inc in enumerate(phase_incs):
                    weight = 1.0 / (idx + 1.2)
                    osc = math.sin(phases[idx]) * weight
                    if idx % 2 == 0:
                        left_sample += osc * 0.9
                        right_sample += osc * 0.6
                    else:
                        left_sample += osc * 0.6
                        right_sample += osc * 0.9
                    phases[idx] = (phases[idx] + p_inc) % (2.0 * math.pi)
                white_l = rng.uniform(-0.04, 0.04)
                white_r = rng.uniform(-0.04, 0.04)
                brown_left = (brown_left + (0.02 * white_l)) / 1.02
                brown_right = (brown_right + (0.02 * white_r)) / 1.02
                left_sample = (left_sample * lfo1 + brown_left * 0.3) * fade
                right_sample = (right_sample * lfo2 + brown_right * 0.3) * fade
                s_left = int(max(-32767, min(32767, left_sample * target_peak * 0.6)))
                s_right = int(max(-32767, min(32767, right_sample * target_peak * 0.6)))
                frames.append(struct.pack("<hh", s_left, s_right))
                lfo_phase_1 = (lfo_phase_1 + lfo_inc_1) % (2.0 * math.pi)
                lfo_phase_2 = (lfo_phase_2 + lfo_inc_2) % (2.0 * math.pi)
            return b"".join(frames)

    def generate_ambient_track(
        self,
        output_path: Union[str, Path],
        theme: str = "horror",
        duration_sec: float = 30.0,
        volume: float = 0.25,
        seed: Optional[int] = None,
    ) -> Path:
        """
        Saves a synthesized WAV ambient track to the specified output path.
        """
        out_p = Path(output_path).expanduser().resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        pcm_data = self.synthesize_ambient_pcm(
            theme=theme,
            duration_sec=duration_sec,
            base_amplitude=volume,
            seed=seed,
        )

        with wave.open(str(out_p), "wb") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.SAMPLE_WIDTH)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_data)

        logger.info(
            "ProceduralAudioEngine synthesized %s ambient track (%.1fs) at %s (%d bytes)",
            theme,
            duration_sec,
            out_p.name,
            len(pcm_data),
        )
        return out_p


# Global singleton instance
_default_procedural_audio_engine = ProceduralAudioEngine()


def get_procedural_audio_engine() -> ProceduralAudioEngine:
    return _default_procedural_audio_engine
