"""
src/audio/procedural_drone.py - NumPy Sub-Bass Procedural Drone Synthesizer.

Synthesizes broadcast-ready 44.1 kHz 16-bit mono/stereo WAV drones consisting of:
1. Low-frequency binaural beating: S1 = 0.50*sin(2*pi*f_base*t) + 0.40*sin(2*pi*(f_base+1.5)*t)
2. Slow tape wow LFO modulation: 0.25 Hz with +/- 1.2% variation
3. Low-frequency rumble: Brownian noise filtered with 4th-order Butterworth lowpass at 50 Hz
4. Mains hum: 60 Hz (amp 0.035) + 120 Hz (amp 0.018)
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Optional, Union

import numpy as np

from src.log import get_logger

logger = get_logger("procedural_drone")


def apply_butterworth_4th_lowpass_50hz(signal: np.ndarray, sample_rate: int = 44100, cutoff_hz: float = 50.0) -> np.ndarray:
    """
    Applies a 4th-order Butterworth lowpass filter at 50 Hz using a cascade of two biquad IIR filters.
    Pure NumPy implementation without external scipy dependency.
    """
    if len(signal) == 0:
        return signal

    # 4th order Butterworth is formed by 2 second-order sections (biquads)
    # Q factors for 4th order Butterworth
    q_factors = [
        1.0 / (2.0 * math.cos(math.pi / 8.0)),    # ~ 0.5411961
        1.0 / (2.0 * math.cos(3.0 * math.pi / 8.0)) # ~ 1.3065630
    ]

    omega = 2.0 * math.pi * cutoff_hz / float(sample_rate)
    sin_w = math.sin(omega)
    cos_w = math.cos(omega)

    filtered = signal.copy().astype(np.float64)

    for q in q_factors:
        alpha = sin_w / (2.0 * q)
        b0 = (1.0 - cos_w) / 2.0
        b1 = 1.0 - cos_w
        b2 = (1.0 - cos_w) / 2.0
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w
        a2 = 1.0 - alpha

        # Normalized coefficients
        nb0 = b0 / a0
        nb1 = b1 / a0
        nb2 = b2 / a0
        na1 = a1 / a0
        na2 = a2 / a0

        # Direct form II / difference equation pass
        out = np.zeros_like(filtered)
        x1 = x2 = y1 = y2 = 0.0
        for i in range(len(filtered)):
            x0 = filtered[i]
            y0 = nb0 * x0 + nb1 * x1 + nb2 * x2 - na1 * y1 - na2 * y2
            out[i] = y0
            x2, x1 = x1, x0
            y2, y1 = y1, y0
        filtered = out

    return filtered.astype(np.float32)


def map_tension_to_freq(tension_level: int) -> float:
    """Maps tension level (1 to 5) monotonically to fundamental frequency (28.0 Hz to 65.0 Hz)."""
    t_clamped = max(1, min(5, int(tension_level)))
    return 28.0 + (t_clamped - 1) * (65.0 - 28.0) / 4.0


class ProceduralDroneSynthesizer:
    """Synthesizes dark sub-bass atmospheric drones for cosmic horror soundscapes."""

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate

    def synthesize(
        self,
        duration_sec: float = 30.0,
        base_freq_hz: Optional[float] = None,
        amplitude: float = 0.35,
        seed: Optional[int] = 42,
        tension_level: Optional[int] = None,
    ) -> np.ndarray:
        """
        Generates a 1D float32 audio array in [-1.0, 1.0] with:
        - Tension-coupled frequency modulation (28-65 Hz)
        - Binaural beating
        - Wow tape LFO (0.25 Hz +/- 1.2%)
        - 4th-order 50 Hz filtered brown noise
        - 60 Hz and 120 Hz mains hum
        - Overtone saturation and pop-free cosine fades
        """
        if tension_level is not None:
            freq = map_tension_to_freq(tension_level)
        else:
            freq = float(base_freq_hz) if base_freq_hz is not None else 38.0

        dur = max(1.0, float(duration_sec))
        num_samples = int(self.sample_rate * dur)
        t = np.arange(num_samples, dtype=np.float64) / float(self.sample_rate)

        # 1. Wow Tape LFO Modulation (0.25 Hz with +/- 1.2% variation)
        wow_lfo = 1.0 + 0.012 * np.sin(2.0 * np.pi * 0.25 * t)
        inst_phase = 2.0 * np.pi * freq * np.cumsum(wow_lfo) / float(self.sample_rate)
        inst_phase_beat = 2.0 * np.pi * (freq + 1.5) * np.cumsum(wow_lfo) / float(self.sample_rate)

        # 2. Binaural Beating Drone
        s1 = 0.50 * np.sin(inst_phase) + 0.40 * np.sin(inst_phase_beat)

        # 3. Sub-harmonics & overtones for immense cosmic weight (0.5x and 1.5x)
        s_sub = 0.25 * np.sin(inst_phase * 0.5) + 0.15 * np.sin(inst_phase * 1.5)

        # 4. Low-frequency rumble: Brownian noise filtered with 4th-order Butterworth lowpass at 50 Hz
        rng = np.random.default_rng(seed if seed is not None else 42)
        white_noise = rng.normal(0.0, 1.0, size=num_samples).astype(np.float64)
        brown_noise = np.cumsum(white_noise)
        # Remove DC drift
        brown_noise -= np.mean(brown_noise)
        peak = np.max(np.abs(brown_noise))
        if peak > 1e-6:
            brown_noise /= peak

        rumble_filtered = apply_butterworth_4th_lowpass_50hz(brown_noise, sample_rate=self.sample_rate, cutoff_hz=50.0)
        rumble_filtered = rumble_filtered * 0.35

        # 5. Mains hum: 60 Hz (amp 0.035) + 120 Hz (amp 0.018)
        mains_hum = 0.035 * np.sin(2.0 * np.pi * 60.0 * t) + 0.018 * np.sin(2.0 * np.pi * 120.0 * t)

        # 6. Sum components with subtle overtone saturation
        combined = s1 + s_sub + rumble_filtered + mains_hum
        saturated = np.tanh(combined * 1.15) * float(amplitude)

        # Smooth cosine fade-in and fade-out to guarantee click-free boundaries
        fade_samples = int(self.sample_rate * min(1.0, dur * 0.08))
        if fade_samples > 0:
            fade_in = 0.5 * (1.0 - np.cos(np.pi * np.arange(fade_samples) / float(fade_samples)))
            saturated[:fade_samples] *= fade_in
            saturated[-fade_samples:] *= fade_in[::-1]

        return np.clip(saturated, -1.0, 1.0).astype(np.float32)

    def generate_wav(
        self,
        output_path: Union[str, Path],
        duration_sec: float = 30.0,
        base_freq_hz: Optional[float] = None,
        amplitude: float = 0.35,
        stereo: bool = False,
        tension_level: Optional[int] = None,
    ) -> Path:
        """Saves synthesized drone as a 44.1 kHz 16-bit WAV file."""
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        samples = self.synthesize(
            duration_sec=duration_sec,
            base_freq_hz=base_freq_hz,
            amplitude=amplitude,
            tension_level=tension_level,
        )
        int16_samples = (samples * 32767.0).astype(np.int16)

        num_channels = 2 if stereo else 1
        with wave.open(str(out_p), "wb") as wf:
            wf.setnchannels(num_channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            if stereo:
                # Slight phase offset on right channel
                right_samples = np.roll(int16_samples, int(self.sample_rate * 0.015))
                interleaved = np.empty((len(int16_samples), 2), dtype=np.int16)
                interleaved[:, 0] = int16_samples
                interleaved[:, 1] = right_samples
                wf.writeframes(interleaved.tobytes())
            else:
                wf.writeframes(int16_samples.tobytes())

        freq_log = float(base_freq_hz) if base_freq_hz is not None else (map_tension_to_freq(tension_level) if tension_level is not None else 38.0)
        logger.info("Drone sintético generado: %s (%.1fs @ %.1fHz)", out_p.name, duration_sec, freq_log)
        return out_p
