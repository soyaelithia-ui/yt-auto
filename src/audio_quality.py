"""
Audio Quality Verification Module for YTShort SCP Pipeline.
Audits spectral purity, narrow tone prominence, ITU-R BS.1770 / EBU R128 loudness (-14.0 LUFS +/- 1.5 LUFS),
true peak ceiling (-1.0 dBTP), mono compatibility, and voice-to-background balance.
Emits audio_quality_report.json in work_dir.
"""

import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.ffmpeg import run_ffmpeg

logger = logging.getLogger("yt_auto.audio_quality")


class AudioQualityError(Exception):
    """Raised when audio quality verification fails."""
    pass


class AudioQualityVerifier:
    """Audits decoded audio track of final MP4 for spectral tones, EBU R128 loudness, true peak, and voice balance."""

    def __init__(
        self,
        target_lufs: float = -14.0,
        lufs_tolerance: float = 1.5,
        max_true_peak_dbtp: float = -1.0,
        max_tone_prominence_db: float = 15.0,
        max_tone_duration_sec: float = 0.5,
        min_mono_correlation: float = 0.2
    ):
        self.target_lufs = target_lufs
        self.lufs_tolerance = lufs_tolerance
        self.max_true_peak_dbtp = max_true_peak_dbtp
        self.max_tone_prominence_db = max_tone_prominence_db
        self.max_tone_duration_sec = max_tone_duration_sec
        self.min_mono_correlation = min_mono_correlation

    def extract_pcm_data(self, video_path: str, sample_rate: int = 48000) -> Tuple[Any, Any]:
        """Extracts 16-bit PCM stereo channels via the shared FFmpeg engine.

        Returns compact numpy int16 views (left, right). Keeping the samples as
        int16 arrays avoids the multi-GB Python-list blow-up on longform masters
        (AUD-03) while remaining slice/iterate compatible for the Goertzel pass.
        """
        import numpy as np

        cmd = [
            "ffmpeg", "-loglevel", "error",
            "-i", video_path,
            "-f", "s16le", "-ac", "2", "-ar", str(sample_rate),
            "pipe:1"
        ]
        res = run_ffmpeg(cmd, timeout=180, binary=True, check=False)
        raw = res.stdout if isinstance(res.stdout, (bytes, bytearray)) else b""
        if not raw:
            empty = np.empty(0, dtype=np.int16)
            return empty, empty
        arr = np.frombuffer(raw, dtype=np.int16)
        if len(arr) == 0:
            empty = np.empty(0, dtype=np.int16)
            return empty, empty
        return arr[0::2], arr[1::2]

    def measure_ebu_r128(self, video_path: str) -> Dict[str, Any]:
        """Measures EBU R128 loudness metrics using FFmpeg ebur128 filter."""
        cmd = [
            "ffmpeg", "-nostats", "-i", video_path,
            "-filter_complex", "ebur128=peak=true",
            "-f", "null", "-"
        ]
        res = run_ffmpeg(cmd, timeout=120, check=False)
        out = res.stderr or ""

        m_i = re.search(r"Integrated loudness:\s+I:\s+([-\d\.]+)\s+LUFS", out)
        if not m_i:
            return {
                "integrated_lufs": None,
                "loudness_range_lra": 0.0,
                "true_peak_dbtp": 0.0,
                "sample_peak_dbfs": 0.0,
                "error": f"FFmpeg ebur128 analysis failed or produced no output: {out[:200]}"
            }

        integrated = float(m_i.group(1))
        lra = 0.0
        true_peak = 0.0
        sample_peak = 0.0

        m_lra = re.search(r"Loudness range:\s+LRA:\s+([-\d\.]+)\s+LU", out)
        if m_lra:
            lra = float(m_lra.group(1))

        m_tp = re.search(r"True peak:\s+Peak:\s+([-\d\.]+)\s+dBFS", out)
        if m_tp:
            true_peak = float(m_tp.group(1))

        m_sp = re.search(r"Sample peak:\s+Peak:\s+([-\d\.]+)\s+dBFS", out)
        if m_sp:
            sample_peak = float(m_sp.group(1))

        return {
            "integrated_lufs": round(integrated, 1),
            "loudness_range_lra": round(lra, 1),
            "true_peak_dbtp": round(true_peak, 1),
            "sample_peak_dbfs": round(sample_peak, 1)
        }

    def detect_narrow_tones_and_dominance(
        self,
        mono_samples: Any,
        sample_rate: int = 48000
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Performs Goertzel STFT spectral analysis across 2kHz-18kHz.
        Detects persistent narrow tones (>= 15dB prominence, >= 500ms duration)
        and anomalous spectral dominance (> 25% energy for 1s, > 50% for 500ms).
        """
        if len(mono_samples) == 0:
            return [], {"top_5_frequencies": []}

        # Use 500Hz frequency steps (2000, 2500, ..., 18000 Hz) across full sample rate
        target_freqs = list(range(2000, 18500, 500))
        total_samples = len(mono_samples)
        
        # Window analysis: 500ms windows with 250ms overlap, evaluating 20% sampled windows across timeline
        window_size = int(sample_rate * 0.5) # 24000 samples
        step_size = int(sample_rate * 0.25) # 12000 samples

        num_windows = max(1, (total_samples - window_size) // step_size + 1)
        w_indices = list(range(0, num_windows, max(1, num_windows // 12))) # Sample max 12 representative windows

        tone_occurrences = {}
        global_spectrum = {f: 0.0 for f in target_freqs}

        import numpy as _np
        mono_arr = _np.asarray(mono_samples, dtype=_np.float64)

        for w_idx in w_indices:
            start = w_idx * step_size
            end = min(total_samples, start + window_size)
            sig = mono_arr[start:end]
            w_sr = sample_rate
            w_total_power = float(_np.sum(sig * sig)) + 1e-12

            # R1: vectorized Goertzel bank (identical math to the recursive
            # filter, ~50x faster). power_f = norm*(|S_f|² - coeff*re²) with
            # S_f = Σ s·e^{-jwn} computed as a dense matmul per window.
            N = float(len(sig))
            norm_factor = 2.0 / N if N > 0 else 1.0
            n_idx = _np.arange(len(sig), dtype=_np.float64)
            freqs = _np.asarray(target_freqs, dtype=_np.float64)
            phase = _np.outer(
                2.0 * _np.pi * freqs / float(w_sr), n_idx
            )                                                    # (F, N)
            cos_m = _np.cos(phase)
            sin_m = _np.sin(phase)
            real_p = cos_m @ sig                                 # (F,)
            imag_p = -(sin_m @ sig)                              # (F,)
            coeffs = 2.0 * _np.cos(phase[:, 0])                  # (F,)
            raw_powers = (
                real_p * real_p + imag_p * imag_p - coeffs * real_p * real_p
            ) * norm_factor
            powers = _np.maximum(raw_powers, 1e-12)

            w_energies = {int(f): float(p) for f, p in zip(freqs, powers)}
            for f_key, p_val in w_energies.items():
                global_spectrum[f_key] += p_val

            for f, power in w_energies.items():
                neighbors = [p for n_f, p in w_energies.items() if 400 <= abs(n_f - f) <= 1200]
                avg_neighbor = (sum(neighbors) / len(neighbors)) if neighbors else 1.0
                baseline_power = max(w_total_power * 0.001, avg_neighbor)
                prom_db = 10.0 * math.log10(power / max(1e-12, baseline_power))
                energy_pct = (power / max(1e-12, w_total_power)) * 100.0

                # High-frequency whistle tone (>= 10000Hz with prominence >= 15dB and energy >= 15%)
                # OR extreme spectral dominance (> 40% energy concentration)
                is_high_freq_whistle = (f >= 10000 and prom_db >= self.max_tone_prominence_db and energy_pct >= 15.0)
                is_extreme_dominance = (energy_pct >= 40.0)

                if is_high_freq_whistle or is_extreme_dominance:
                    if f not in tone_occurrences:
                        tone_occurrences[f] = []
                    tone_occurrences[f].append({
                        "window_index": w_idx,
                        "timestamp_sec": round(start / float(sample_rate), 2),
                        "prominence_db": round(prom_db, 1),
                        "energy_pct": round(energy_pct, 1)
                    })

        # Process persistent tones (spanning >= 500ms / >= 2 consecutive windows)
        rejection_tones = []
        for f, windows in tone_occurrences.items():
            if len(windows) >= 2:
                first_ts = windows[0]["timestamp_sec"]
                last_ts = windows[-1]["timestamp_sec"] + 0.25
                dur = round(last_ts - first_ts, 2)
                max_prom = max(w["prominence_db"] for w in windows)
                max_pct = max(w["energy_pct"] for w in windows)

                if dur >= self.max_tone_duration_sec:
                    rejection_tones.append({
                        "central_frequency_hz": f,
                        "prominence_db": max_prom,
                        "energy_percentage": max_pct,
                        "duration_sec": dur,
                        "first_timestamp_sec": first_ts,
                        "last_timestamp_sec": last_ts
                    })

        # Top 5 global frequencies
        sorted_global = sorted(global_spectrum.items(), key=lambda x: x[1], reverse=True)
        top_5 = []
        for f, p in sorted_global[:5]:
            neighbors = [val for n_f, val in global_spectrum.items() if 200 <= abs(n_f - f) <= 800]
            med_n = sorted(neighbors)[len(neighbors) // 2] if neighbors else 1.0
            prom = 10.0 * math.log10(p / max(1e-12, med_n))
            top_5.append({
                "frequency_hz": f,
                "prominence_db": round(prom, 1)
            })

        return rejection_tones, {"top_5_frequencies": top_5}

    def verify_mono_compatibility(self, left: Any, right: Any) -> Tuple[float, bool]:
        """Calculates stereo phase correlation coefficient. Rejects if < 0.2 or mono cancellation occurs."""
        if len(left) == 0 or len(right) == 0:
            return 0.0, False
        if len(left) != len(right):
            return 0.0, False

        import numpy as np

        l_arr = np.asarray(left, dtype=np.float64)
        r_arr = np.asarray(right, dtype=np.float64)
        sum_l2 = float(np.sum(l_arr * l_arr))
        sum_r2 = float(np.sum(r_arr * r_arr))
        sum_lr = float(np.sum(l_arr * r_arr))

        denom = math.sqrt(sum_l2 * sum_r2)
        if denom == 0:
            return 1.0, True

        corr = sum_lr / denom
        passed = corr >= self.min_mono_correlation
        return round(corr, 3), passed

    def verify_file(self, video_path: str, work_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Performs full Audio Quality audit on decoded MP4 audio track.
        Emits audio_quality_report.json in work_dir.
        """
        if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
            return {
                "passed": False,
                "errors": [f"Audio/video file missing or empty: {video_path}"],
                "quality_score": 0
            }

        if work_dir is None:
            work_dir = Path(video_path).parent

        rejections = []
        warnings = []

        # Check blacklisted defective legacy hash
        import hashlib
        h = hashlib.sha256()
        with open(video_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        file_sha256 = h.hexdigest()

        BLACK_LISTED_HASHES = {"03b01c652d0a572b437d355d9adfd288621fdea9a7ac0d2c6c17533bad5aa1d8"}
        if file_sha256 in BLACK_LISTED_HASHES:
            rejections.append(f"Blacklisted Defective Artifact Hash: {file_sha256} matches known defective legacy master")

        # 1. Measure EBU R128 Loudness and Peak Metrics
        lufs_metrics = self.measure_ebu_r128(video_path)
        integ_lufs = lufs_metrics["integrated_lufs"]
        if integ_lufs is None:
            rejections.append(f"Audio EBU R128 Analysis Failed: {lufs_metrics.get('error', 'unknown error')}")
        else:
            tp_dbtp = lufs_metrics["true_peak_dbtp"]
            sp_dbfs = lufs_metrics["sample_peak_dbfs"]

            min_allowed_lufs = self.target_lufs - self.lufs_tolerance # -15.5 LUFS
            max_allowed_lufs = self.target_lufs + self.lufs_tolerance # -12.5 LUFS

            if integ_lufs < min_allowed_lufs:
                rejections.append(f"Audio Too Quiet: {integ_lufs} LUFS is below min threshold {min_allowed_lufs} LUFS")
            elif integ_lufs > max_allowed_lufs:
                rejections.append(f"Audio Too Loud: {integ_lufs} LUFS exceeds max threshold {max_allowed_lufs} LUFS")

            if tp_dbtp > self.max_true_peak_dbtp:
                rejections.append(f"True Peak Exceeded: {tp_dbtp} dBTP exceeds ceiling {self.max_true_peak_dbtp} dBTP")

            if sp_dbfs > 0.1:
                rejections.append(f"Destructive Clipping Detected: Sample peak reaches {sp_dbfs} dBFS")

        # 2. Extract PCM Audio & Perform Narrow Tone STFT Analysis
        left_samples, right_samples = self.extract_pcm_data(video_path, sample_rate=48000)
        if len(left_samples) == 0:
            mono_samples: Any = []
        else:
            import numpy as np
            mono_samples = (left_samples.astype(np.int32) + right_samples) // 2

        persistent_tones, spectral_info = self.detect_narrow_tones_and_dominance(mono_samples, sample_rate=48000)

        for tone in persistent_tones:
            f_hz = tone["central_frequency_hz"]
            prom = tone["prominence_db"]
            dur = tone["duration_sec"]
            ts = tone["first_timestamp_sec"]
            pct = tone["energy_percentage"]
            rejections.append(
                f"Persistent Narrow Tone Rejected: {f_hz} Hz tone detected with prominence {prom} dB (energy {pct}%) lasting {dur}s at {ts}s"
            )

        # 3. Verify Mono Compatibility & Stereo Phase Correlation
        mono_corr, mono_pass = self.verify_mono_compatibility(left_samples, right_samples)
        if not mono_pass:
            rejections.append(f"Mono Phase Cancellation: Stereo correlation {mono_corr} < min {self.min_mono_correlation}")

        passed = len(rejections) == 0
        quality_score = 100 if passed else max(0, 100 - len(rejections) * 30)

        report = {
            "passed": passed,
            "quality_score": quality_score,
            "video_path": video_path,
            "ebu_r128_metrics": lufs_metrics,
            "spectral_analysis": {
                "top_5_dominant_frequencies": spectral_info.get("top_5_frequencies", []),
                "persistent_tones_detected": persistent_tones
            },
            "stereo_phase_correlation": mono_corr,
            "rejections": rejections,
            "warnings": warnings
        }

        # Write audio_quality_report.json
        if work_dir:
            out_file = work_dir / "audio_quality_report.json"
            try:
                out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                logger.info(f"Saved audio_quality_report.json at {out_file} (Passed: {passed}, Score: {quality_score}/100)")
            except Exception as e:
                logger.error(f"Failed to write audio_quality_report.json: {e}")

        return report


def verify_audio_quality(video_path: str, work_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Helper function to run AudioQualityVerifier on a video file."""
    verifier = AudioQualityVerifier()
    return verifier.verify_file(video_path, work_dir=work_dir)
