"""Stage 12: SimHash and SHA256 deduplication gating against recent channel publications."""

from __future__ import annotations

from src.core.profiling import CanonicalStage
from src.log import get_logger
from src.pipeline.context import PipelineContext
from src.pipeline.utils import _file_sha256

logger = get_logger("pipeline.stages.stage_12_simhash")


def stage_12_dedup_simhash(ctx: PipelineContext) -> None:
    """Stage 12: SimHash and SHA256 deduplication gating against recent channel publications."""
    with ctx.profiler.phase(CanonicalStage.DEDUP_SIMHASH):
        ctx.text_fingerprints = {
            "script": ctx.script,
            "title": ctx.youtube_title,
            "description": ctx.youtube_description,
        }
        ctx.file_fingerprints = {
            "thumbnail": _file_sha256(ctx.thumbnail_path),
            "audio": _file_sha256(ctx.audio_path),
            "video": _file_sha256(ctx.video_path),
        }
        duplicate_kinds = [
            kind
            for kind, payload in ctx.text_fingerprints.items()
            if ctx.repository.has_published_fingerprint(ctx.channel_name, kind, payload)
        ]
        duplicate_kinds.extend(
            [
                kind
                for kind, digest in ctx.file_fingerprints.items()
                if ctx.repository.has_published_digest(ctx.channel_name, kind, digest)
            ]
        )
        if duplicate_kinds:
            raise ValueError(
                "Artefactos duplicados respecto de publicaciones recientes: " + ", ".join(duplicate_kinds)
            )
