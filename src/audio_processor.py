import os
import re
import signal
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union
from src.log import get_logger

logger = get_logger("scp_audio_processor")

from lib.ffmpeg import run_ffmpeg, FFmpegExecutionError, FFmpegTimeoutError
from lib.audio import (
    normalize_narration_lufs,
    apply_sidechain_ducking,
    master_audio_track,
    parse_dramatic_pauses,
    extract_dramatic_pauses,
    strip_dramatic_pauses,
    generate_silence_audio,
    shift_word_timestamps_with_pauses,
    insert_dramatic_pauses_to_audio,
)


def _run_subproc(cmd: List[str], timeout: float = 60, **kwargs) -> Any:
    return run_ffmpeg(cmd, timeout=timeout, check=kwargs.get("check", True))


class AudioProcessor:
    """Handles audio normalization (-14.0 LUFS, -1.5 dBTP), sidechain ducking (-18dB, 350ms release), dramatic pauses, and concatenation."""

    def normalize_loudness(
        self,
        input_audio_path: str,
        output_audio_path: str,
        target_lufs: float = -14.0
    ) -> str:
        """
        Normalizes audio narration to -16.0 LUFS integrated loudness (+/- 1.5 LUFS) and -1.5 dBTP true peak using FFmpeg loudnorm
        and applies highpass (80Hz) and lowpass (12000Hz) filtering.
        """
        return normalize_narration_lufs(
            input_path=input_audio_path,
            output_path=output_audio_path,
            target_lufs=target_lufs,
            max_tp=-1.5,
            apply_lowpass=False,
            lowpass_freq=0,
        )

    def mix_background_ambient(
        self,
        narration_path: str,
        output_path: str,
        ambient_volume: float = 0.04,
        ambient_track_path: Optional[str] = None,
        ducking_db: float = -18.0,
        theme: str = "horror",
    ) -> str:
        """
        Mixes subtle ambient audio bed with automatic voice sidechain ducking (-18dB, 350ms release).
        During dramatic pauses in speech, the ambient audio naturally rises to fill the silence.
        """
        try:
            track = ambient_track_path
            if not track or not os.path.exists(track):
                from src.asset_manager import get_asset_manager
                track = get_asset_manager().get_ambient(category=theme)

            if not track or not os.path.exists(track):
                # Synthesize on-the-fly procedural ambient bed
                from src.media.procedural_audio import get_procedural_audio_engine
                from lib.ffmpeg import probe_media
                try:
                    probe = probe_media(narration_path)
                    dur = max(5.0, float(probe.duration or 30.0))
                except Exception:
                    dur = 30.0
                gen_path = Path(output_path).parent / f"procedural_ambient_{theme}.wav"
                get_procedural_audio_engine().generate_ambient_track(
                    output_path=gen_path,
                    theme=theme,
                    duration_sec=dur,
                )
                if gen_path.is_file():
                    track = str(gen_path)

            if not track or not os.path.exists(track):
                return narration_path

            from lib.audio import build_sidechain_ducking_filter_graph
            threshold = max(0.001, 10 ** (max(ducking_db, -60) / 20))
            filter_complex = build_sidechain_ducking_filter_graph(
                speech_label="0:a",
                music_label="1:a",
                out_label="aout",
                music_volume=ambient_volume,
                ducking_threshold=threshold,
                ducking_ratio=8.0,
                ducking_attack_ms=20.0,
                ducking_release_ms=350.0,
                lowpass_freq=12000.0,
                master_loudness=False,
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", narration_path,
                "-stream_loop", "-1", "-i", track,
                "-filter_complex", filter_complex,
                "-map", "[aout]",
                "-c:a", "libmp3lame", "-b:a", "192k",
                output_path
            ]
            _run_subproc(cmd, capture_output=True, text=True, check=True, timeout=60, start_new_session=True)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
            logger.warning("Ambient mixing produced empty or missing artifact at %s, returning narration path", output_path)
            return narration_path
        except Exception as e:
            logger.warning("Ambient mixing fallback (%s).", e, exc_info=True)
            return narration_path

    def parse_dramatic_pauses(self, script_text: str) -> list[dict[str, Any]]:
        """Parses script text for dramatic pause tags ([PAUSA: <dur>], [PAUSE: <dur>], [SILENCE: <dur>])."""
        return parse_dramatic_pauses(script_text)

    def apply_sidechain_ducking(
        self,
        speech_path: str | Path,
        music_path: str | Path,
        output_path: str | Path,
        ducking_db: float = -18.0,
    ) -> str:
        """Applies sidechain ducking filter to lower background music below narration."""
        return apply_sidechain_ducking(
            narration_path=speech_path,
            music_path=music_path,
            output_path=output_path,
            ducking_db=ducking_db,
        )

    def insert_dramatic_pauses(
        self,
        audio_segments: list[str],
        pause_durations: list[float],
        output_path: str,
        word_timestamps_per_chunk: list[list[dict]] | None = None,
    ) -> tuple[str, list[dict]]:
        """Inserts calibrated silence intervals into narration audio with monotonic word boundary offset shifting."""
        return insert_dramatic_pauses_to_audio(
            audio_paths=audio_segments,
            pause_durations=pause_durations,
            output_path=output_path,
            word_timestamps_per_chunk=word_timestamps_per_chunk,
        )

    def concat_crossfade_audio(
        self,
        clip_paths: List[str],
        output_path: str,
        crossfade_sec: float = 0.1
    ) -> Tuple[str, List[float]]:
        """
        Concatenates TTS narration audio clips using FFmpeg filter acrossfade=d=crossfade_sec:c1=tri:c2=tri,
        eliminating micro-pauses between scenes. Recalculates and returns (output_path, scene_durations).
        """
        from typing import List, Tuple
        from lib.tts import get_wav_duration

        valid_clips = [p for p in clip_paths if p and os.path.exists(p)]
        if not valid_clips:
            return (output_path, [])

        orig_durs = [max(0.1, get_wav_duration(p)) for p in valid_clips]

        if len(valid_clips) == 1:
            try:
                import shutil
                shutil.copy(valid_clips[0], output_path)
            except (shutil.Error, OSError) as exc:
                logger.error("Single clip copy failed: %s", exc, exc_info=True)
                raise
            return (output_path, orig_durs)

        n = len(valid_clips)
        inputs_cmd = []
        for p in valid_clips:
            inputs_cmd.extend(["-i", p])

        if n == 2:
            filter_graph = f"[0:a][1:a]acrossfade=d={crossfade_sec}:c1=tri:c2=tri[aout]"
        else:
            filter_parts = [f"[0:a][1:a]acrossfade=d={crossfade_sec}:c1=tri:c2=tri[a1]"]
            for i in range(2, n):
                in_label = f"[a{i-1}]"
                out_label = "[aout]" if i == n - 1 else f"[a{i}]"
                filter_parts.append(f"{in_label}[{i}:a]acrossfade=d={crossfade_sec}:c1=tri:c2=tri{out_label}")
            filter_graph = ";".join(filter_parts)

        cmd = [
            "ffmpeg", "-y"
        ] + inputs_cmd + [
            "-filter_complex", filter_graph,
            "-map", "[aout]",
            "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100",
            output_path
        ]

        try:
            res = _run_subproc(cmd, capture_output=True, text=True, check=True, timeout=120, start_new_session=True)
            logger.info(f"Successfully concatenated {n} audio clips with acrossfade=d={crossfade_sec}s into {output_path}")
        except Exception as e:
            logger.warning("FFmpeg acrossfade concatenation fallback (%s). Using FFmpeg concat filter fallback.", e, exc_info=True)
            try:
                concat_filter = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[aout]"
                fallback_cmd = [
                    "ffmpeg", "-y"
                ] + inputs_cmd + [
                    "-filter_complex", concat_filter,
                    "-map", "[aout]",
                    "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100",
                    output_path
                ]
                _run_subproc(fallback_cmd, capture_output=True, text=True, check=True, timeout=120, start_new_session=True)
            except Exception as fb_err:
                logger.error("FFmpeg concat filter fallback failed (%s).", fb_err, exc_info=True)

        # Recalculate per-scene durations accounting for crossfade overlaps
        scene_durations = []
        if n == 1:
            scene_durations = [orig_durs[0]]
        else:
            for idx in range(n):
                if idx == n - 1:
                    dur = max(0.1, round(orig_durs[n - 1], 3))
                else:
                    dur = max(0.1, round(orig_durs[idx] - crossfade_sec, 3))
                scene_durations.append(dur)

        # Validate concatenated output file existence
        if not (os.path.exists(output_path) and os.path.getsize(output_path) > 0):
            raise RuntimeError(f"Audio concatenation failed to produce output artifact at {output_path}")

        return (output_path, scene_durations)


def sanitize_script_for_tts(raw_text: str) -> str:
    """
    Cleans script for TTS synthesis:
    1. Removes editorial chapter/act headings (e.g. "Acto Uno: ...", "Capítulo 1: ...", "Parte 2: ...").
    2. Formats technical acronyms phonetically for clear neutral Spanish TTS.
    3. Normalizes punctuation spacing.
    """
    if not raw_text:
        return ""
    from src.sanitizer import (
        RE_ACT_CHAPTER_LINE,
        RE_ACT_CHAPTER_LABELS,
        sanitize_scp_acronyms_for_tts,
    )
    # Strip line-leading Act/Chapter labels
    cleaned = RE_ACT_CHAPTER_LINE.sub("", raw_text)
    # Strip inline Act/Chapter announcements
    cleaned = RE_ACT_CHAPTER_LABELS.sub("", cleaned)
    # Acronym phonetic formatting
    cleaned = sanitize_scp_acronyms_for_tts(cleaned)
    # Clean redundant blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
