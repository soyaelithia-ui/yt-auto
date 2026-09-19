"""Stage 5: Voice audio generation via TTS and optional EBU R128 mastering."""

from __future__ import annotations

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
        max_allowed_words = getattr(ctx.lane, "words_max", None) or getattr(ctx.lane, "words_recondense_max", None)
        if max_allowed_words and ctx.lane.orientation == "vertical":
            cur_words = ctx.clean_script.split()
            if len(cur_words) > int(max_allowed_words * 1.15):
                from src.llm import _trim_script_to_max_words

                logger.info(
                    "Guion preliminar (%d palabras) excede presupuesto del carril (%d palabras); pre-recortando antes de TTS",
                    len(cur_words),
                    max_allowed_words,
                )
                ctx.clean_script = _trim_script_to_max_words(ctx.clean_script, max_allowed_words)
                ctx.script_path.write_text(ctx.clean_script, encoding="utf-8")

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

        if os.environ.get("MASTER_AUDIO_R128", "1") == "1":
            try:
                mastered = lib.tts.master_voice_audio(
                    ctx.audio_path,
                    target_lufs=-16.0,
                    true_peak_dbtp=-1.5,
                )
                if mastered != ctx.audio_path:
                    logger.info("Audio masterizado a EBU R128: %s", ctx.audio_path)
            except Exception as exc:
                logger.warning("Fallo en masterización EBU R128 (no crítico): %s", exc)
