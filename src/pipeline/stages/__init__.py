"""Pipeline stages decomposition package."""

from src.pipeline.stages.stage_01_lease import stage_01_claim_lease
from src.pipeline.stages.stage_02_ingest import stage_02_ingest_translate
from src.pipeline.stages.stage_03_editorial import stage_03_editorial_barrier
from src.pipeline.stages.stage_04_mood import stage_04_mood_theme
from src.pipeline.stages.stage_05_tts import stage_05_tts_synthesis
from src.pipeline.stages.stage_06_alignment import stage_06_duration_alignment
from src.pipeline.stages.stage_07_subtitles import stage_07_subtitle_generation
from src.pipeline.stages.stage_08_loop import stage_08_loop_scene
from src.pipeline.stages.stage_09_render import stage_09_video_rendering
from src.pipeline.stages.stage_10_qa import stage_10_qa_gating
from src.pipeline.stages.stage_11_metadata import stage_11_thumbnail_metadata
from src.pipeline.stages.stage_12_simhash import stage_12_dedup_simhash
from src.pipeline.stages.stage_13_publish import stage_13_backup_publish

__all__ = [
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
]
