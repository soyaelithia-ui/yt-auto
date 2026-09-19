"""Stage 6: Re-condensation (shorts) or auto-expansion (longform) to align duration."""

from __future__ import annotations

import os
import sys

import lib.tts
from src.core.domain import JobStatus
from src.core.profiling import CanonicalStage
from src.core.repository import connect
from src.curators.beats import extract_story_beats
from src.log import get_logger
from src.pipeline.context import PipelineContext
from src.pipeline.utils import (
    _dispatch_curate_script,
    _enforce_editorial_compliance as default_enforce,
    is_pipeline_test_environment as is_test_environment,
)
from src.sanitizer import (
    sanitize_script_text,
    strip_llm_prompt_leaks,
    suppress_title_repetition,
    validate_pre_tts_script,
)

logger = get_logger("pipeline.stages.stage_06_alignment")


def _reprocess_script(ctx: PipelineContext, new_raw: str, stage_tag: str, enforcer: Any) -> None:
    """Sanitize, beat-extract, pre-validate, write and re-synthesize TTS audio for script."""
    clean = (
        strip_llm_prompt_leaks(new_raw)
        if stage_tag == "re-condensación"
        else sanitize_script_text(new_raw, channel=ctx.channel_name)
    )
    clean, ctx.beats = extract_story_beats(clean)
    clean = suppress_title_repetition(clean, ctx.title, max_allowed=2)
    ctx.clean_script = enforcer(clean, stage=stage_tag, channel=ctx.channel_name)
    validate_pre_tts_script(ctx.clean_script)
    ctx.script_path.write_text(ctx.clean_script, encoding="utf-8")
    ctx.audio = lib.tts.generate_audio(
        ctx.clean_script,
        str(ctx.audio_path),
        target_duration_sec=float(ctx.lane.duration_target_sec),
        channel=ctx.channel_name,
        lane=ctx.lane,
        rate=ctx.lane.voice_rate,
        strict_word_boundaries=ctx.directed and not is_test_environment(),
        lock_voice=ctx.directed and not is_test_environment(),
    )


def _align_vertical_overduration(ctx: PipelineContext, enforcer: Any) -> None:
    """Re-condense or trim short audio if duration exceeds lane maximum."""
    if not (ctx.lane.orientation == "vertical" and float(ctx.audio["duration_sec"]) > float(ctx.lane.duration_max_sec)):
        return

    logger.warning(
        "Duración de audio (%s s) supera el máximo de %s s del carril %s; realizando UNA re-condensación",
        ctx.audio["duration_sec"],
        ctx.lane.duration_max_sec,
        ctx.lane.id,
    )
    raw = _dispatch_curate_script(
        ctx.content,
        ctx.title,
        additional_stories=[],
        min_words=max(140, int(ctx.lane.words_min * 0.85)),
        provider="C" if is_test_environment() else None,
        channel=ctx.channel_name,
        strict_single_story=True,
        max_words=ctx.lane.words_recondense_max,
    )
    _reprocess_script(ctx, raw, "re-condensación", enforcer)
    if float(ctx.audio["duration_sec"]) > float(ctx.lane.duration_max_sec):
        cur_words = ctx.clean_script.split()
        ratio = max(0.5, (float(ctx.lane.duration_max_sec) - 10.0) / float(ctx.audio["duration_sec"]))
        target_count = max(int(ctx.lane.words_min), int(len(cur_words) * ratio))
        from src.llm import _trim_script_to_max_words

        trimmed = _trim_script_to_max_words(ctx.clean_script, target_count)
        _reprocess_script(ctx, trimmed, "re-condensación", enforcer)
    if float(ctx.audio["duration_sec"]) > float(ctx.lane.duration_max_sec):
        raise ValueError(
            f"La duración de audio ({ctx.audio['duration_sec']} s) excede el máximo {ctx.lane.duration_max_sec} s del carril {ctx.lane.id} tras re-condensación"
        )


def _align_vertical_underduration(ctx: PipelineContext, enforcer: Any) -> None:
    """Re-curate short audio if duration falls below lane minimum."""
    if not (
        ctx.lane.orientation == "vertical"
        and not is_test_environment()
        and not os.environ.get("PYTEST_CURRENT_TEST")
        and float(ctx.audio["duration_sec"]) < float(ctx.lane.duration_min_sec)
    ):
        return

    logger.warning(
        "Duración de audio (%s s) es inferior al mínimo de %s s del carril %s; re-curando para alcanzar presupuesto editorial",
        ctx.audio["duration_sec"],
        ctx.lane.duration_min_sec,
        ctx.lane.id,
    )
    raw = _dispatch_curate_script(
        ctx.content,
        ctx.title,
        additional_stories=[],
        min_words=max(int(ctx.lane.words_min), 210),
        provider="C" if is_test_environment() else None,
        channel=ctx.channel_name,
        strict_single_story=True,
        max_words=ctx.lane.words_max,
    )
    _reprocess_script(ctx, raw, "re-expansión-short", enforcer)
    if float(ctx.audio["duration_sec"]) < float(ctx.lane.duration_min_sec):
        raise ValueError(
            f"Audio {float(ctx.audio['duration_sec']):.1f}s < mínimo {float(ctx.lane.duration_min_sec):.0f}s del carril {ctx.lane.id} tras re-expansión; fallo temprano pre-render"
        )


def _align_longform_underduration(ctx: PipelineContext, enforcer: Any) -> None:
    """Expand longform audio with multi-story candidates if below minimum duration."""
    if not (
        ctx.is_long_lane
        and not ctx.directed
        and float(ctx.audio["duration_sec"]) < float(ctx.lane.duration_min_sec)
    ):
        return

    logger.warning(
        "Duración de audio (%s s) es inferior al mínimo de %s s del carril %s; ejecutando auto-expansión autónoma",
        ctx.audio["duration_sec"],
        ctx.lane.duration_min_sec,
        ctx.lane.id,
    )
    with connect(ctx.database, read_only=True) as conn:
        candidates = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM stories WHERE channel = ? AND status = ? AND story_id != ? ORDER BY created_at LIMIT 40",
                (ctx.channel_name, JobStatus.PENDING.value, ctx.story_id),
            )
        ]
    from src.sanitizer import check_forbidden_editorial_elements

    candidates = [
        c
        for c in candidates
        if not check_forbidden_editorial_elements((c.get("title") or "") + ". " + str(c.get("content") or ""))
    ]
    raw = _dispatch_curate_script(
        ctx.content,
        ctx.title,
        additional_stories=candidates,
        min_words=ctx.words_min,
        provider="C" if is_test_environment() else None,
        channel=ctx.channel_name,
        strict_single_story=ctx.directed,
    )
    _reprocess_script(ctx, raw, "post-expansión", enforcer)
    logger.info("Auto-expansión autónoma completada. Nueva duración: %s s", ctx.audio["duration_sec"])
    if float(ctx.audio["duration_sec"]) < float(ctx.lane.duration_min_sec):
        raise ValueError(
            f'Audio {ctx.audio["duration_sec"]:.1f}s < mínimo {ctx.lane.duration_min_sec:.0f}s del carril {ctx.lane.id} incluso tras auto-expansión; fallo temprano pre-render'
        )


def stage_06_duration_alignment(ctx: PipelineContext) -> None:
    """Stage 6: Re-condensation (shorts) or auto-expansion (longform) to align duration."""
    with ctx.profiler.phase(CanonicalStage.DURATION_ALIGNMENT):
        pipe_mod = sys.modules.get("src.pipeline")
        enforcer = getattr(pipe_mod, "_enforce_editorial_compliance", default_enforce)

        _align_vertical_overduration(ctx, enforcer)
        _align_vertical_underduration(ctx, enforcer)
        _align_longform_underduration(ctx, enforcer)

        if ctx.is_long_lane and float(ctx.audio["duration_sec"]) < float(ctx.lane.duration_min_sec):
            raise ValueError(
                f'Audio {float(ctx.audio["duration_sec"]):.1f}s < mínimo {float(ctx.lane.duration_min_sec):.0f}s del carril {ctx.lane.id}; fallo temprano pre-render'
            )

        ctx.repository.record_artifact(
            ctx.run_id, "audio", local_path=str(ctx.audio_path), size_bytes=ctx.audio_path.stat().st_size
        )
        ctx.require_heartbeat()
