"""
src/audio/sfx_library.py - Procedural Cosmic & Analog Horror SFX Synthesizer.

Generates broadcast-ready synthesized WAV sound effects without relying on external assets:
- ptt_squelch: Walkie-talkie / intercom mic click and burst
- sonar_ping_deep_reverb: Deep-sea resonant sonar ping with decaying echo
- hull_stress_metal_groan: Low resonant submarine hull groaning under extreme pressure
- singularity_glitch_burst: Spatial tear / black hole frequency shift with static burst
- geiger_clicks: Radiation detector click train
- static_burst: Analog TV / CRT burst
"""
from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Dict, Optional, Union

import numpy as np

from src.log import get_logger

logger = get_logger("sfx_library")


class SFXLibrarySynthesizer:
    """Synthesizes analog/cosmic horror sound effects on demand."""

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate

    def synthesize_sfx(self, sfx_id: str, duration_sec: Optional[float] = None) -> np.ndarray:
        """Returns float32 samples in [-1.0, 1.0] for the requested sfx_id."""
        method_map = {
            "ptt_squelch": self._synth_ptt_squelch,
            "sonar_ping_deep_reverb": self._synth_sonar_ping,
            "hull_stress_metal_groan": self._synth_metal_groan,
            "singularity_glitch_burst": self._synth_singularity_glitch,
            "geiger_clicks": self._synth_geiger_clicks,
            "static_burst": self._synth_static_burst,
        }

        synth_fn = method_map.get(sfx_id, self._synth_static_burst)
        return synth_fn(duration_sec=duration_sec)

    def _synth_ptt_squelch(self, duration_sec: Optional[float] = None) -> np.ndarray:
        """Push-to-talk mic click and noise burst (0.2s)."""
        dur = duration_sec or 0.22
        n_samples = int(self.sample_rate * dur)
        t = np.arange(n_samples) / float(self.sample_rate)

        # Tone beep + noise burst + envelope
        beep = np.sin(2.0 * np.pi * 920.0 * t) * np.exp(-t * 25.0)
        noise = np.random.uniform(-1.0, 1.0, size=n_samples)
        # Bandpass filter on noise using simple FIR
        noise_filtered = np.convolve(noise, np.ones(5) / 5.0, mode="same")
        env = np.exp(-t * 12.0)

        mix = (beep * 0.4 + noise_filtered * 0.6) * env
        return np.clip(mix * 0.7, -1.0, 1.0).astype(np.float32)

    def _synth_sonar_ping(self, duration_sec: Optional[float] = None) -> np.ndarray:
        """Deep resonant submarine sonar ping with reverb tail (3.0s)."""
        dur = duration_sec or 3.0
        n_samples = int(self.sample_rate * dur)
        t = np.arange(n_samples) / float(self.sample_rate)

        # Main ping frequency: 780 Hz + subharmonic 390 Hz
        ping = np.sin(2.0 * np.pi * 780.0 * t) * np.exp(-t * 3.5)
        ping_sub = np.sin(2.0 * np.pi * 390.0 * t) * np.exp(-t * 2.5) * 0.5

        # Reverb multi-tap simulation
        dry = ping + ping_sub
        wet = np.zeros(n_samples, dtype=np.float64)
        delays = [0.12, 0.28, 0.45, 0.72, 1.15, 1.60]
        decays = [0.65, 0.45, 0.30, 0.20, 0.12, 0.05]

        for d_sec, decay in zip(delays, decays):
            d_samples = int(d_sec * self.sample_rate)
            if d_samples < n_samples:
                wet[d_samples:] += dry[:-d_samples] * decay

        mix = dry + wet * 0.75
        return np.clip(mix * 0.85, -1.0, 1.0).astype(np.float32)

    def _synth_metal_groan(self, duration_sec: Optional[float] = None) -> np.ndarray:
        """Submarine hull stress metal groan under high pressure (2.5s)."""
        dur = duration_sec or 2.5
        n_samples = int(self.sample_rate * dur)
        t = np.arange(n_samples) / float(self.sample_rate)

        # Frequency modulated screech / groan around 110-180 Hz
        f_mod = 135.0 + 40.0 * np.sin(2.0 * np.pi * 1.5 * t) + 20.0 * np.cos(2.0 * np.pi * 0.8 * t)
        phase = 2.0 * np.pi * np.cumsum(f_mod) / float(self.sample_rate)
        harm1 = np.sin(phase)
        harm2 = np.sin(phase * 2.01) * 0.4
        harm3 = np.sin(phase * 3.02) * 0.25

        # Non-linear metallic resonance
        metal = np.tanh((harm1 + harm2 + harm3) * 2.5)

        # Amplitude envelope
        env = np.sin(np.pi * t / dur) ** 1.5
        mix = metal * env * 0.65
        return np.clip(mix, -1.0, 1.0).astype(np.float32)

    def _synth_singularity_glitch(self, duration_sec: Optional[float] = None) -> np.ndarray:
        """Cosmic singularity frequency down-sweep with bitcrush distortion (1.8s)."""
        dur = duration_sec or 1.8
        n_samples = int(self.sample_rate * dur)
        t = np.arange(n_samples) / float(self.sample_rate)

        # Exponential pitch drop from 2400 Hz down to 40 Hz
        f_drop = 40.0 + 2360.0 * np.exp(-t * 3.0)
        phase = 2.0 * np.pi * np.cumsum(f_drop) / float(self.sample_rate)
        sweep = np.sin(phase)

        # Bitcrush / distortion
        crushed = np.round(sweep * 6.0) / 6.0

        # Static burst
        noise = np.random.uniform(-0.5, 0.5, size=n_samples) * (1.0 - t / dur)

        env = np.exp(-t * 1.5)
        mix = (crushed * 0.7 + noise * 0.3) * env
        return np.clip(mix * 0.8, -1.0, 1.0).astype(np.float32)

    def _synth_geiger_clicks(self, duration_sec: Optional[float] = None) -> np.ndarray:
        """Geiger-Müller radiation clicks (1.5s)."""
        dur = duration_sec or 1.5
        n_samples = int(self.sample_rate * dur)
        signal = np.zeros(n_samples, dtype=np.float32)

        # Poisson random clicks
        n_clicks = int(dur * 40)
        click_indices = np.random.randint(0, n_samples - 200, size=n_clicks)
        click_shape = np.sin(np.linspace(0, np.pi, 60)) * np.exp(-np.linspace(0, 5, 60))

        for idx in click_indices:
            signal[idx : idx + 60] += click_shape.astype(np.float32) * np.random.uniform(0.5, 1.0)

        return np.clip(signal * 0.8, -1.0, 1.0)

    def _synth_static_burst(self, duration_sec: Optional[float] = None) -> np.ndarray:
        """Analog TV / CRT white static burst (0.5s)."""
        dur = duration_sec or 0.5
        n_samples = int(self.sample_rate * dur)
        t = np.arange(n_samples) / float(self.sample_rate)
        noise = np.random.uniform(-1.0, 1.0, size=n_samples)
        env = np.exp(-t * 6.0)
        mix = noise * env * 0.6
        return np.clip(mix, -1.0, 1.0).astype(np.float32)

    def generate_sfx_wav(self, sfx_id: str, output_path: Union[str, Path], duration_sec: Optional[float] = None) -> Path:
        """Writes the synthesized SFX into a 44.1 kHz WAV file."""
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        samples = self.synthesize_sfx(sfx_id, duration_sec=duration_sec)
        int16_data = (samples * 32767.0).astype(np.int16)

        with wave.open(str(out_p), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(int16_data.tobytes())

        return out_p
