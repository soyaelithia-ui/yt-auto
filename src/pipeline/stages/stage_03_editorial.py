"""Stage 3: Editorial barrier, beat extraction, pre-TTS validation, and script artifact persistence."""

from __future__ import annotations

import sys
from src.core.profiling import CanonicalStage
from src.log import get_logger
from src.pipeline.context import PipelineContext
from src.pipeline.utils import (
    _enforce_editorial_compliance as default_enforce,
    is_pipeline_test_environment as is_test_environment,
)

logger = get_logger("pipeline.stages.stage_03_editorial")


def stage_03_editorial_barrier(ctx: PipelineContext) -> None:
    """Stage 3: Editorial barrier, beat extraction, pre-TTS validation, and script artifact persistence."""
    with ctx.profiler.phase(CanonicalStage.EDITORIAL_BARRIER):
        from src.sanitizer import sanitize_script_text, validate_pre_tts_script, suppress_title_repetition
        from src.curators.beats import extract_story_beats

        pipe_mod = sys.modules.get("src.pipeline")
        enforcer = getattr(pipe_mod, "_enforce_editorial_compliance", default_enforce)

        script = sanitize_script_text(ctx.script, channel=ctx.channel_name)
        clean_script, ctx.beats = extract_story_beats(script)
        clean_script = suppress_title_repetition(clean_script, ctx.title, max_allowed=2)
        ctx.clean_script = enforcer(clean_script, stage="post-curación", channel=ctx.channel_name)

        if not is_test_environment():
            validate_pre_tts_script(ctx.clean_script)
            from src.narrative.quality_gate import validate_narrative_coherence

            coherence = validate_narrative_coherence(
                ctx.clean_script,
                channel=ctx.channel_name,
                duration_type="short" if getattr(ctx.lane, "orientation", "vertical") == "vertical" else "long",
                max_words=ctx.words_max,
            )
            if not coherence.valid:
                logger.warning(
                    "Narrative coherence gate detected issues: %s (score=%.2f)", coherence.errors, coherence.score
                )
                if coherence.score < 0.5:
                    raise ValueError(f"Narrative coherence gate rejected script: {coherence.errors}")

        ctx.script_path.write_text(ctx.clean_script, encoding="utf-8")
        ctx.repository.record_artifact(
            ctx.run_id, "script", local_path=str(ctx.script_path), size_bytes=ctx.script_path.stat().st_size
        )
        ctx.require_heartbeat()
