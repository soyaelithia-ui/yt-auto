"""Stage 7: Subtitle creation (ASS & SRT) and grammar/syntax validation if active."""

from __future__ import annotations

from src.core.profiling import CanonicalStage
from src.log import get_logger
from src.pipeline.context import PipelineContext
from src.pipeline.utils import is_pipeline_test_environment as is_test_environment

logger = get_logger("pipeline.stages.stage_07_subtitles")


def stage_07_subtitle_generation(ctx: PipelineContext) -> None:
    """Stage 7: Subtitle creation (ASS & SRT) and grammar/syntax validation if active."""
    with ctx.profiler.phase(CanonicalStage.SUBTITLE_GENERATION):
        if ctx.subtitles_active:
            from lib.subtitles import (
                create_ass_subtitles,
                create_subtitles,
                validate_subtitle_artifact,
                validate_subtitle_grammar_and_syntax,
            )

            template = ctx.lane.template
            video_res = tuple(ctx.lane.expected_resolution)
            create_ass_subtitles(
                ctx.audio.get("word_timestamps") or [],
                str(ctx.ass_path),
                template=template,
                video_res=video_res,
                script_text=ctx.clean_script,
            )
            create_subtitles(
                ctx.audio.get("word_timestamps") or [],
                str(ctx.srt_path),
                template=template,
                video_res=video_res,
                script_text=ctx.clean_script,
            )
            validate_subtitle_grammar_and_syntax(str(ctx.srt_path))
            validate_subtitle_grammar_and_syntax(str(ctx.ass_path))

            if ctx.directed or not is_test_environment():
                validate_subtitle_artifact(
                    str(ctx.srt_path),
                    duration_sec=float(ctx.audio["duration_sec"]),
                    expected_words=len(ctx.audio.get("word_timestamps") or []),
                )
