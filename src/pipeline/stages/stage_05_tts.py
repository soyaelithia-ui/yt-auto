"""Stage 5: Voice audio generation via TTS and optional EBU R128 mastering."""

from __future__ import annotations

import math
import os
from pathlib import Path

import lib.tts
from src.core.profiling import CanonicalStage
from src.log import get_logger
from src.pipeline.context import PipelineContext
from src.pipeline.utils import is_pipeline_test_environment as is_test_environment

logger = get_logger("pipeline.stages.stage_05_tts")


def stage_05_tts_synthesis(ctx: PipelineContext) -> None:
    """Stage 5: Voice audio generation via TTS and optional EBU R128 mastering."""
    with ctx.profiler.phase(CanonicalStage.TTS_SYNTHESIS):
        target_audio_sec = float(ctx.lane.duration_target_sec)
        audio = lib.tts.generate_audio(
            ctx.clean_script,
            str(ctx.audio_path),
            target_duration_sec=target_audio_sec,
            channel=ctx.channel_name,
            lane=ctx.lane,
            rate=ctx.lane.voice_rate,
            strict_word_boundaries=ctx.directed and not is_test_environment(),
            lock_voice=ctx.directed and not is_test_environment(),
        )
        if isinstance(audio, (str, Path)):
            ctx.audio = {"duration_sec": 0.0, "word_timestamps": []}
        else:
            ctx.audio = audio

        max_lane_sec = float(getattr(ctx.lane, "duration_max_sec", 0.0) or 0.0)
        curr_dur = float(ctx.audio.get("duration_sec", 0.0) or 0.0)
        if (
            getattr(ctx.lane, "orientation", "") == "vertical"
            and max_lane_sec > 0
            and curr_dur > max_lane_sec
            and not is_test_environment()
        ):
            excess_ratio = (curr_dur - max_lane_sec) / max_lane_sec
            if 0.0 < excess_ratio < 0.08:
                base_rate_str = str(getattr(ctx.lane, "voice_rate", "+0%") or "+0%").replace("%", "").strip()
                base_rate_int = int(base_rate_str) if base_rate_str.lstrip("+-").isdigit() else 0
                delta_boost = min(10, max(4, int(math.ceil(excess_ratio * 100)) + 2))
                mod_rate_int = base_rate_int + delta_boost
                mod_rate = f"+{mod_rate_int}%" if mod_rate_int >= 0 else f"{mod_rate_int}%"
                logger.info(
                    "Audio duration (%.2fs) exceeds lane max (%.2fs) by %.1f%% (<8%%). Modulating Edge TTS rate to %s",
                    curr_dur,
                    max_lane_sec,
                    excess_ratio * 100,
                    mod_rate,
                )
                audio_mod = lib.tts.generate_audio(
                    ctx.clean_script,
                    str(ctx.audio_path),
                    target_duration_sec=target_audio_sec,
                    channel=ctx.channel_name,
                    lane=ctx.lane,
                    rate=mod_rate,
                    strict_word_boundaries=ctx.directed and not is_test_environment(),
                    lock_voice=ctx.directed and not is_test_environment(),
                )
                if isinstance(audio_mod, (str, Path)):
                    ctx.audio = {"duration_sec": 0.0, "word_timestamps": []}
                else:
                    ctx.audio = audio_mod

        if (
            os.environ.get("YT_FOLD_MASTERING", "1") != "1"
            and os.environ.get("MASTER_AUDIO_R128", "1") == "1"
        ):
            try:
                mastered = lib.tts.master_voice_audio(
                    ctx.audio_path,
                    target_lufs=-14.0,
                    true_peak_dbtp=-1.5,
                )
                if mastered != ctx.audio_path:
                    logger.info("Audio masterizado a EBU R128: %s", ctx.audio_path)
            except Exception as exc:
                logger.warning("Fallo en masterización EBU R128 (no crítico): %s", exc)
