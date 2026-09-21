"""Safe end-to-end orchestration that preserves artifacts on every ambiguous result."""

from __future__ import annotations

from src.config import is_test_environment
from src.core.quality import is_spanish_neutral, normalize_text, validate_prepublication
from src.llm import curate_script
from src.pipeline.context import PipelineContext, RunContext, active_heartbeat_scope
from src.pipeline.executor import PipelineExecutor, run_pipeline_once
from src.pipeline.stages import (
    stage_01_claim_lease,
    stage_02_ingest_translate,
    stage_03_editorial_barrier,
    stage_04_mood_theme,
    stage_05_tts_synthesis,
    stage_06_duration_alignment,
    stage_07_subtitle_generation,
    stage_08_loop_scene,
    stage_09_video_rendering,
    stage_10_qa_gating,
    stage_11_thumbnail_metadata,
    stage_12_dedup_simhash,
    stage_13_backup_publish,
)
from src.pipeline.utils import (
    _catalog_shots_from_manifest,
    _dispatch_curate_script,
    _drive_review_url,
    _enforce_editorial_compliance,
    _file_sha256,
    _handle_pipeline_exception,
    _marker,
    _peak_rss_metric,
    _record_combined_stories,
    _should_translate,
)

# Backward-compatible private stage function references
_stage_01_claim_lease = stage_01_claim_lease
_stage_02_ingest_translate = stage_02_ingest_translate
_stage_03_editorial_barrier = stage_03_editorial_barrier
_stage_04_mood_theme = stage_04_mood_theme
_stage_05_tts_synthesis = stage_05_tts_synthesis
_stage_06_duration_alignment = stage_06_duration_alignment
_stage_07_subtitle_generation = stage_07_subtitle_generation
_stage_08_loop_scene = stage_08_loop_scene
_stage_09_video_rendering = stage_09_video_rendering
_stage_10_qa_gating = stage_10_qa_gating
_stage_11_thumbnail_metadata = stage_11_thumbnail_metadata
_stage_12_dedup_simhash = stage_12_dedup_simhash
_stage_13_backup_publish = stage_13_backup_publish

__all__ = [
    "PipelineContext",
    "RunContext",
    "PipelineExecutor",
    "run_pipeline_once",
    "active_heartbeat_scope",
    "stage_01_claim_lease",
    "stage_02_ingest_translate",
    "stage_03_editorial_barrier",
    "stage_04_mood_theme",
    "stage_05_tts_synthesis",
    "stage_06_duration_alignment",
    "stage_07_subtitle_generation",
    "stage_08_loop_scene",
    "stage_09_video_rendering",
    "stage_10_qa_gating",
    "stage_11_thumbnail_metadata",
    "stage_12_dedup_simhash",
    "stage_13_backup_publish",
    "_stage_01_claim_lease",
    "_stage_02_ingest_translate",
    "_stage_03_editorial_barrier",
    "_stage_04_mood_theme",
    "_stage_05_tts_synthesis",
    "_stage_06_duration_alignment",
    "_stage_07_subtitle_generation",
    "_stage_08_loop_scene",
    "_stage_09_video_rendering",
    "_stage_10_qa_gating",
    "_stage_11_thumbnail_metadata",
    "_stage_12_dedup_simhash",
    "_stage_13_backup_publish",
    "_drive_review_url",
    "_enforce_editorial_compliance",
    "_should_translate",
    "_catalog_shots_from_manifest",
    "is_spanish_neutral",
    "normalize_text",
    "validate_prepublication",
    "is_test_environment",
    "curate_script",
    "_dispatch_curate_script",
    "_marker",
    "_file_sha256",
    "_record_combined_stories",
    "_peak_rss_metric",
    "_handle_pipeline_exception",
]
