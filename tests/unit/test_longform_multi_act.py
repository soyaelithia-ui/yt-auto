"""
tests/unit/test_longform_multi_act.py - Unit tests for Hybrid Multi-Act Director pipeline.

Validates:
1. Act narrative contracts (4-8 acts, progressive tension, zero temporal drift).
2. Thematic horizontal catalog loop resolution, modulo fallback, and killswitch.
3. Stream-copy concatenation assembly, -c:s mov_text soft-muxing, work refusal.
4. YouTube interactive chapter formatting and .srt sidecar persistence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List
import pytest

from src.curators.text_splitter import TextSegmentationEngine
from src.curators.curation_profiles import ActNarrativePlan, LANE_CURATION_CONFIGS


def _generate_synthetic_narrative(target_word_count: int = 3000, theme: str = "horror") -> str:
    """Generates synthetic narrative text with valid paragraph structure and word count."""
    if theme == "horror":
        sentences = [
            "La estación de monitoreo en la cumbre nevada emitía un zumbido electromagnético anómalo a medianoche.",
            "Los sensores térmicos perimetrales registraron oscilaciones gélidas que no correspondían a la fauna del bosque.",
            "Al revisar los archivadores oxidados de Miller, encontré advertencias de que las voces imitaban a los propios guardias.",
            "El cristal blindado de la cúpula tembló con violencia ante una masa informe que bloqueó las luces de señalización.",
            "Detoné la bengala roja de auxilio antes de evacuar por el túnel auxiliar hacia la carretera desierta.",
            "Las autoridades aseguraron la zona bajo estricto secreto pero las frecuencias siguen activas en el receptor.",
        ]
    else:
        sentences = [
            "Durante diez años trabajé como enfermera en turnos dobles para comprar mi primera vivienda sin ayuda familiar.",
            "En la cena de compromiso, mi madre anunció sin consultarme que yo pagaría la fiesta de lujo de mi hermana.",
            "Me negué rotundamente a financiar caprichos ajenos cuando estoy pagando la hipoteca de mi propio hogar.",
            "Toda la familia extendida me atacó llamándome egoísta y amenazando con expulsarme de las celebraciones.",
            "Descubrí que intentaron tramitar un préstamo fraudulento utilizando mis documentos personales.",
            "Corté comunicación definitiva con mis padres y hoy disfruto de una tranquilidad inquebrantable en mi departamento.",
        ]

    narrative = []
    current_words = 0
    idx = 0
    while current_words < target_word_count:
        sent = sentences[idx % len(sentences)]
        narrative.append(sent)
        current_words += len(sent.split())
        idx += 1
        if idx % 4 == 0:
            narrative.append("\n\n")

    return " ".join(narrative)


# ============================================================================
# PHASE 1: FOUNDATION & ACT NARRATIVE CONTRACTS
# ============================================================================

class TestMultiActNarrativeCuration:
    """Unit tests for Phase 1: 4-8 act dynamic narrative decomposition and timing."""

    @pytest.mark.parametrize("lane_id", ["horror-horror-long", "drama-aita-long"])
    def test_act_partitioning_4_to_8_acts(self, lane_id: str):
        """
        Synthesizes a 10-30 min narrative (2600-4800 words), verifying that
        TextSegmentationEngine.curate dynamically emits 4 to 8 acts with progressive tension.
        """
        engine = TextSegmentationEngine()
        raw_text = _generate_synthetic_narrative(target_word_count=3200, theme="horror" if "horror" in lane_id else "drama")

        payload = engine.curate(
            raw_text=raw_text,
            title="Crónica de la Señal Perdida" if "horror" in lane_id else "El Dilema de la Boda",
            channel_lane=lane_id,
            target_format="longform",
        )

        acts = payload.get("acts", [])
        num_acts = len(acts)
        assert 4 <= num_acts <= 8, f"Expected 4-8 acts for longform lane {lane_id}, got {num_acts}"

        allowed_roles = {
            "exposition_inception",
            "rising_action_dread",
            "confrontation_crisis",
            "climax_confrontation",
            "climax_breaking_point",
            "aftermath_revelation",
        }

        tensions = []
        for i, act in enumerate(acts, start=1):
            assert act.get("act_number") == i
            assert act.get("act_title") and len(act["act_title"].strip()) > 0
            assert act.get("dramatic_role") in allowed_roles, f"Invalid role: {act.get('dramatic_role')}"
            
            # Tension level must be present and between 1 and 5
            tension = act.get("tension_level")
            if tension is None and act.get("scenes"):
                tension = max(s.get("tension_level", 1) for s in act["scenes"])
            assert tension is not None and 1 <= tension <= 5
            tensions.append(tension)
            assert len(act.get("scenes", [])) >= 1

        # Assert progressive tension curve culminating in peak tension >= 4 before resolution
        assert max(tensions) >= 4, f"Expected peak tension >= 4, got max={max(tensions)} in {tensions}"
        peak_idx = tensions.index(max(tensions))
        # Ensure peak does not only appear at the very first act
        assert peak_idx > 0, f"Peak tension should not occur at Act 1: {tensions}"

    def test_proportional_duration_scaling_zero_drift(self):
        """
        Given a voiceover duration T = 845.60s, assert calculated act durations
        sum to T ± 0.1s, each act is >= 30.0s, and total drift is clamped strictly to 0.0s.
        """
        engine = TextSegmentationEngine()
        total_duration = 845.60
        raw_durations = [140.0, 160.0, 220.0, 180.0, 150.0]

        scaled_durations = engine.scale_act_durations(raw_durations, total_duration, min_act_duration=30.0)

        assert len(scaled_durations) == len(raw_durations)
        assert sum(scaled_durations) == pytest.approx(total_duration, abs=0.1)

        for dur in scaled_durations:
            assert dur >= 30.0, f"Act duration {dur} below minimum 30.0s"

        # Assert final act is clamped so total drift is strictly 0.0s
        total_sum = round(sum(scaled_durations), 4)
        drift = round(total_sum - total_duration, 4)
        assert drift == 0.0, f"Cumulative drift was {drift}, expected 0.0s"

    def test_short_narrative_subdivision(self):
        """
        Given a shorter narrative yielding only 3 raw sections, assert the engine
        subdivides the longest section at semantic paragraph/sentence breaks to emit >= 4 acts.
        """
        engine = TextSegmentationEngine()
        short_text = (
            "El faro de Isla Negra permaneció incomunicado durante tres semanas de temporal constante. "
            "El operador Miller reportó luces anómalas sumergidas que ascendían contra la corriente. "
            "Al llegar los inspectores, la linterna continuaba girando pero no había rastro del personal de guardia."
        )

        payload = engine.curate(
            raw_text=short_text,
            title="Isla Negra",
            channel_lane="horror-horror-long",
            target_format="longform",
        )

        acts = payload.get("acts", [])
        assert len(acts) >= 4, f"Expected at least 4 subdivided acts, got {len(acts)}"
        for act in acts:
            assert len(act.get("scenes", [])) >= 1
            assert act.get("act_title")
            assert act.get("dramatic_role")


# ============================================================================
# PHASE 2: STAGE 04 THEMATIC LOOP RESOLUTION & ENGINE ROUTING
# ============================================================================

from unittest.mock import MagicMock
from src.core.lanes import get_lane
from src.core.profiling import PipelineProfiler
from src.media.loop_engine import LoopVideoEngine
from src.pipeline.context import PipelineContext
from src.pipeline.stages.stage_04_mood import stage_04_mood_theme
from src.pipeline.utils import _resolve_engine_mode


class TestThematicLoopResolutionAndEngineRouting:
    """Unit tests for Phase 2: Engine mode routing, thematic multi-loop selection, and modulo fallback."""

    @pytest.mark.parametrize("lane_id", ["horror-horror-long", "drama-aita-long"])
    def test_engine_resolution_director_mode(self, lane_id: str):
        """
        Given a lane with orientation='horizontal' and visual_pipeline='director',
        assert _resolve_engine_mode resolves to director without requiring FORCE_MULTISCENE=1.
        """
        lane = get_lane(lane_id)
        assert lane is not None
        assert lane.orientation == "horizontal"
        assert lane.visual_pipeline == "director"

        engine_mode, is_loop_mode, is_multiscene_mode = _resolve_engine_mode(
            lane, video_engine="director", compositor=None
        )
        assert engine_mode == "director"
        assert is_multiscene_mode is True
        assert is_loop_mode is False

    def test_resolve_multi_act_loops_thematic(self, tmp_path: Path):
        """
        Given a 5-act narrative with tension ratings [1, 2, 3, 5, 2] for lane horror-horror-long,
        assert stage_04_mood_theme resolves at least 3 distinct video loops, the act 4 loop
        matches high-intensity tags, and shot_durations contains 5 elements matching act durations.
        """
        lane = get_lane("horror-horror-long")
        assert lane is not None

        acts = [
            {"act_number": 1, "act_title": "Incepción Sensorial", "dramatic_role": "exposition_inception", "tension_level": 1, "target_duration_sec": 120.0},
            {"act_number": 2, "act_title": "Advertencias Ignoradas", "dramatic_role": "rising_action_dread", "tension_level": 2, "target_duration_sec": 180.0},
            {"act_number": 3, "act_title": "Escalada Inexorable", "dramatic_role": "rising_action_dread", "tension_level": 3, "target_duration_sec": 240.0},
            {"act_number": 4, "act_title": "Confrontación Crítica", "dramatic_role": "climax_confrontation", "tension_level": 5, "target_duration_sec": 300.0},
            {"act_number": 5, "act_title": "Secuela Psicológica", "dramatic_role": "aftermath_revelation", "tension_level": 2, "target_duration_sec": 160.0},
        ]
        total_audio = sum(a["target_duration_sec"] for a in acts)

        mock_profiler = PipelineProfiler("test_multi_act_profiler")
        repo = MagicMock()
        script_file = tmp_path / "script.txt"
        script_file.write_text("Test script content", encoding="utf-8")
        audio_file = tmp_path / "speech.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 40)

        ctx = PipelineContext(
            story={"title": "Horror Longform Test", "content": "Test"},
            story_id="story_multi_act_1",
            run_id="run_multi_act_1",
            channel_name="moku",
            channel_key="moku",
            lane=lane,
            repository=repo,
            database=":memory:",
            owner="test_worker",
            lease_seconds=300,
            settings=MagicMock(),
            branding=MagicMock(),
            profiler=mock_profiler,
            directed=False,
            generate_only=False,
            engine_mode="director",
            is_loop_mode=False,
            is_multiscene_mode=True,
            subtitles_active=False,
            work_dir=tmp_path,
            audio_path=audio_file,
            ass_path=tmp_path / "subs.ass",
            srt_path=tmp_path / "subs.srt",
            video_path=tmp_path / "video.mp4",
            thumbnail_path=tmp_path / "thumb.jpg",
            script_path=script_file,
            visual_plan_path=tmp_path / "visual_plan.json",
            metadata_path=tmp_path / "metadata.json",
            scene_manifest_path=tmp_path / "scene_manifest.json",
        )
        ctx.clean_script = "Test script"
        ctx.audio = {"duration_sec": total_audio}
        ctx.script_payload = {"acts": acts}

        stage_04_mood_theme(ctx)

        assert len(ctx.scene_bg_list) == 5
        for p in ctx.scene_bg_list:
            assert Path(p).is_file()

        # At least 3 distinct video loops assigned across 5 acts
        distinct_loops = set(ctx.scene_bg_list)
        assert len(distinct_loops) >= 3, f"Expected >= 3 distinct loops, got {len(distinct_loops)}"

        # Act 4 (tension 5) matches high-intensity tags
        act_4_loop = ctx.scene_bg_list[3].lower()
        assert any(tag in act_4_loop for tag in ("containment", "facility", "emergency", "crisis")), f"Act 4 loop {act_4_loop} missing high-intensity tags"

        # ctx.shot_durations contains 5 duration elements matching act durations
        assert len(ctx.shot_durations) == 5
        assert ctx.shot_durations == pytest.approx([120.0, 180.0, 240.0, 300.0, 160.0], abs=0.1)

    def test_catalog_shortage_modulo_fallback(self):
        """
        Given a 6-act narrative and a mock catalog with only 2 matching horizontal loops,
        assert resolve_multi_act_loops cyclically rotates loops using modulo and consecutive
        acts do not share identical loops.
        """
        engine = LoopVideoEngine()
        acts = [
            {"act_number": i + 1, "act_title": f"Act {i+1}", "dramatic_role": "rising_action_dread", "tension_level": 2, "target_duration_sec": 60.0}
            for i in range(6)
        ]
        mock_candidates = [Path("/mock/loop_alpha.mp4"), Path("/mock/loop_beta.mp4")]

        loop_paths, durations = engine.resolve_multi_act_loops(
            acts=acts,
            orientation="horizontal",
            channel="moku",
            category="horror",
            allow_test_mock=True,
            candidate_pool=mock_candidates,
        )

        assert len(loop_paths) == 6
        assert len(durations) == 6

        # Assert cyclic rotation and no consecutive identical loops
        for i in range(len(loop_paths) - 1):
            assert loop_paths[i] != loop_paths[i + 1], f"Consecutive identical loops at index {i} and {i+1}: {loop_paths[i]}"

    def test_force_single_loop_killswitch(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """
        When FORCE_SINGLE_LOOP=1 is set, stage_04_mood_theme falls back to a single continuous loop.
        """
        monkeypatch.setenv("FORCE_SINGLE_LOOP", "1")
        lane = get_lane("horror-horror-long")
        assert lane is not None

        mock_profiler = PipelineProfiler("test_killswitch_profiler")
        repo = MagicMock()
        script_file = tmp_path / "script.txt"
        script_file.write_text("Test script", encoding="utf-8")
        audio_file = tmp_path / "speech.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 40)

        ctx = PipelineContext(
            story={"title": "Killswitch Test", "content": "Test"},
            story_id="story_killswitch_1",
            run_id="run_killswitch_1",
            channel_name="moku",
            channel_key="moku",
            lane=lane,
            repository=repo,
            database=":memory:",
            owner="test_worker",
            lease_seconds=300,
            settings=MagicMock(),
            branding=MagicMock(),
            profiler=mock_profiler,
            directed=False,
            generate_only=False,
            engine_mode="director",
            is_loop_mode=False,
            is_multiscene_mode=True,
            subtitles_active=False,
            work_dir=tmp_path,
            audio_path=audio_file,
            ass_path=tmp_path / "subs.ass",
            srt_path=tmp_path / "subs.srt",
            video_path=tmp_path / "video.mp4",
            thumbnail_path=tmp_path / "thumb.jpg",
            script_path=script_file,
            visual_plan_path=tmp_path / "visual_plan.json",
            metadata_path=tmp_path / "metadata.json",
            scene_manifest_path=tmp_path / "scene_manifest.json",
        )
        ctx.clean_script = "Test script"
        ctx.audio = {"duration_sec": 600.0}
        ctx.script_payload = {
            "acts": [
                {"act_number": 1, "act_title": "Act I", "dramatic_role": "exposition_inception", "tension_level": 1, "target_duration_sec": 300.0},
                {"act_number": 2, "act_title": "Act II", "dramatic_role": "climax_confrontation", "tension_level": 5, "target_duration_sec": 300.0},
            ]
        }

        stage_04_mood_theme(ctx)

        assert len(ctx.scene_bg_list) == 1
        assert len(ctx.shot_durations) == 1
        assert ctx.shot_durations[0] == pytest.approx(600.0, abs=0.1)


# ============================================================================
# PHASE 3: STAGE 09 CONCAT ASSEMBLY & SUBTITLE MUXING
# ============================================================================

from src.core.contracts import RenderSpec
from src.media.loop.stream_copy import LoopStreamCopyMixin
from src.pipeline.stages.stage_08_loop import stage_08_loop_scene
from src.pipeline.stages.stage_09_render import stage_09_video_rendering, _render_video_loop


class TestStreamCopyConcatAndSubtitleMuxing:
    """Unit tests for Phase 3: Concat manifest generation, stream-copy commands, and soft-muxing."""

    def test_build_multi_scene_concat_list_longform_durations(self, tmp_path: Path):
        """
        Given a 4-act narrative with durations [180.0, 240.0, 360.0, 120.0] and 6.0s loop clips,
        assert repetitions are calculated from explicit act durations rather than clamped 12.0s beats,
        and entries in ffconcat are grouped by act covering total target duration 900.0s.
        """
        concat_file = tmp_path / "test_concat.txt"
        v1 = tmp_path / "act1.mp4"
        v2 = tmp_path / "act2.mp4"
        v3 = tmp_path / "act3.mp4"
        v4 = tmp_path / "act4.mp4"
        for v in (v1, v2, v3, v4):
            v.write_bytes(b"mock_video")

        valid_scenes = [(v1, 180.0), (v2, 240.0), (v3, 360.0), (v4, 120.0)]
        clip_durations = {str(v): 6.0 for v in (v1, v2, v3, v4)}
        total_duration = 900.0

        LoopStreamCopyMixin._build_multi_scene_concat_list(
            valid_scenes=valid_scenes,
            valid_scene_videos=[v1, v2, v3, v4],
            clip_durations=clip_durations,
            duration_sec=total_duration,
            concat_list_path=concat_file,
        )

        assert concat_file.is_file()
        content = concat_file.read_text(encoding="utf-8").strip().splitlines()
        assert content[0] == "ffconcat version 1.0"

        # Count occurrences per video
        lines = [line for line in content if line.startswith("file '")]
        v1_count = sum(1 for line in lines if "act1.mp4" in line)
        v2_count = sum(1 for line in lines if "act2.mp4" in line)
        v3_count = sum(1 for line in lines if "act3.mp4" in line)
        v4_count = sum(1 for line in lines if "act4.mp4" in line)

        # Repetitions: 180/6 = 30, 240/6 = 40, 360/6 = 60, 120/6 = 20
        assert v1_count == pytest.approx(30, abs=1)
        assert v2_count == pytest.approx(40, abs=1)
        assert v3_count == pytest.approx(60, abs=1)
        assert v4_count == pytest.approx(20, abs=1)

        # Entries must be grouped sequentially by act
        v1_indices = [i for i, line in enumerate(lines) if "act1.mp4" in line]
        v2_indices = [i for i, line in enumerate(lines) if "act2.mp4" in line]
        v3_indices = [i for i, line in enumerate(lines) if "act3.mp4" in line]
        v4_indices = [i for i, line in enumerate(lines) if "act4.mp4" in line]

        assert max(v1_indices) < min(v2_indices)
        assert max(v2_indices) < min(v3_indices)
        assert max(v3_indices) < min(v4_indices)

        # Total coverage
        total_covered = (v1_count + v2_count + v3_count + v4_count) * 6.0
        assert total_covered >= total_duration

    def test_render_video_loop_stream_copy_director(self, tmp_path: Path):
        """
        Verify that stream-copy composition command for horizontal director lanes contains
        -f concat -safe 0 and -c:v copy, and does not contain libx264, zoompan, or video filters.
        """
        engine = LoopVideoEngine()
        concat_file = tmp_path / "concat.txt"
        concat_file.write_text("ffconcat version 1.0\nfile 'mock.mp4'\n", encoding="utf-8")
        audio_file = tmp_path / "speech.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 40)
        output_file = tmp_path / "out.mp4"

        cmd = engine.build_stream_copy_composition_cmd(
            concat_list_path=concat_file,
            audio_path=audio_file,
            bgm_path=None,
            duration_sec=600.0,
            output_video_path=output_file,
        )

        cmd_str = " ".join(cmd)
        assert "-f concat -safe 0" in cmd_str
        assert "-c:v copy" in cmd_str
        assert "libx264" not in cmd_str
        assert "zoompan" not in cmd_str
        assert "-threads 2" in cmd_str

    def test_soft_subtitle_muxing_mov_text(self, tmp_path: Path):
        """
        Given subtitles are active and subtitles.ass is present, composition command
        must contain -c:s mov_text and -metadata:s:s:0 language=spa, and not libass or subtitles=.
        """
        engine = LoopVideoEngine()
        concat_file = tmp_path / "concat.txt"
        concat_file.write_text("ffconcat version 1.0\nfile 'mock.mp4'\n", encoding="utf-8")
        audio_file = tmp_path / "speech.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 40)
        sub_file = tmp_path / "subtitles.ass"
        sub_file.write_text(
            "[Script Info]\nTitle: Test\n[V4+ Styles]\n[Events]\nDialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hola mundo\n",
            encoding="utf-8",
        )
        output_file = tmp_path / "out.mp4"

        cmd = engine.build_stream_copy_composition_cmd(
            concat_list_path=concat_file,
            audio_path=audio_file,
            bgm_path=None,
            duration_sec=600.0,
            output_video_path=output_file,
            subtitle_path=sub_file,
        )

        cmd_str = " ".join(cmd)
        assert "-c:s mov_text" in cmd_str
        assert "-metadata:s:s:0 language=spa" in cmd_str
        assert "libass" not in cmd_str
        assert "subtitles=" not in cmd_str

    def test_work_refusal_on_libass_horizontal_longform(self, tmp_path: Path):
        """
        Given a composition request for lane horror-horror-long with libass burning enabled,
        stage_09_video_rendering must trigger Resource Work Refusal and raise ValueError.
        """
        lane = get_lane("horror-horror-long")
        assert lane is not None

        mock_profiler = PipelineProfiler("test_refusal_profiler")
        repo = MagicMock()
        script_file = tmp_path / "script.txt"
        script_file.write_text("Test", encoding="utf-8")
        audio_file = tmp_path / "speech.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 40)

        ctx = PipelineContext(
            story={"title": "Test Refusal", "content": "Test"},
            story_id="story_refusal_1",
            run_id="run_refusal_1",
            channel_name="moku",
            channel_key="moku",
            lane=lane,
            repository=repo,
            database=":memory:",
            owner="test_worker",
            lease_seconds=300,
            settings=MagicMock(),
            branding=MagicMock(),
            profiler=mock_profiler,
            directed=False,
            generate_only=False,
            engine_mode="director",
            is_loop_mode=False,
            is_multiscene_mode=True,
            subtitles_active=True,
            work_dir=tmp_path,
            audio_path=audio_file,
            ass_path=tmp_path / "subs.ass",
            srt_path=tmp_path / "subs.srt",
            video_path=tmp_path / "video.mp4",
            thumbnail_path=tmp_path / "thumb.jpg",
            script_path=script_file,
            visual_plan_path=tmp_path / "visual_plan.json",
            metadata_path=tmp_path / "metadata.json",
            scene_manifest_path=tmp_path / "scene_manifest.json",
        )
        ctx.burn_subtitles = True

        with pytest.raises(ValueError, match="RESOURCE WORK REFUSAL"):
            stage_09_video_rendering(ctx)


# ============================================================================
# PHASE 4: STAGE 11 YOUTUBE CHAPTERS METADATA & SIDECAR
# ============================================================================

from src.pipeline.stages.stage_11_metadata import (
    YouTubeChapterEntry,
    YouTubeChapterSpec,
    build_youtube_chapter_spec,
    stage_11_thumbnail_metadata,
)


class TestYouTubeChaptersMetadata:
    """Unit tests for Phase 4: Stage 11 YouTube chapters formatting, merging, and sidecars."""

    def test_youtube_chapters_generation_happy_path(self):
        """
        Given 4 acts with durations [255.0, 310.0, 480.0, 355.0] seconds,
        assert chapters start at 00:00, intervals are >= 10s, and formatted description
        contains expected chapter timestamps and titles.
        """
        titles = [
            "Acto I: Incepción Sensorial y Aislamiento",
            "Acto II: Advertencias Ignoradas y Señales",
            "Acto III: Confrontación Inexplicable y Ruptura",
            "Acto IV: Secuela Psicológica y Trauma",
        ]
        durations = [255.0, 310.0, 480.0, 355.0]

        spec = build_youtube_chapter_spec(titles, durations)
        assert spec.is_valid()
        assert len(spec.chapters) == 4

        # First chapter must start strictly at 00:00
        assert spec.chapters[0].formatted_time in ("00:00", "0:00")
        assert spec.chapters[1].formatted_time == "04:15"
        assert spec.chapters[2].formatted_time == "09:25"
        assert spec.chapters[3].formatted_time == "17:25"

        block = spec.format_description_block()
        assert "Capítulos:" in block
        assert "00:00 - Acto I: Incepción Sensorial y Aislamiento" in block
        assert "04:15 - Acto II: Advertencias Ignoradas y Señales" in block
        assert "09:25 - Acto III: Confrontación Inexplicable y Ruptura" in block
        assert "17:25 - Acto IV: Secuela Psicológica y Trauma" in block

    def test_short_act_merging(self):
        """
        Given an act sequence where Act 2 has duration 8.0s (< 10s),
        assert Act 2 is merged into Act 1 and resulting chapters maintain compliance.
        """
        titles = [
            "Acto I: Introducción",
            "Acto II: Transición Corta",
            "Acto III: Nudo Central",
            "Acto IV: Desenlace",
        ]
        durations = [120.0, 8.0, 300.0, 200.0]

        spec = build_youtube_chapter_spec(titles, durations)
        assert spec.is_valid()
        # Act 2 (8s) should be merged into Act 1, leaving 3 chapters
        assert len(spec.chapters) == 3
        assert spec.chapters[0].formatted_time in ("00:00", "0:00")
        # Next chapter should start at 120.0 + 8.0 = 128.0s -> 02:08
        assert spec.chapters[1].formatted_time == "02:08"

    def test_insufficient_chapters_suppressed(self):
        """
        Given a narrative yielding only 2 valid acts,
        assert chapter block is suppressed (empty string) and spec is invalid.
        """
        titles = ["Acto I: Inicio", "Acto II: Final"]
        durations = [300.0, 300.0]

        spec = build_youtube_chapter_spec(titles, durations)
        assert not spec.is_valid()
        assert spec.format_description_block() == ""

    def test_srt_artifact_registration(self, tmp_path: Path):
        """
        Assert .srt subtitle file is recorded in ctx.repository and registered in metadata.json.
        """
        lane = get_lane("horror-horror-long")
        assert lane is not None

        mock_profiler = PipelineProfiler("test_srt_profiler")
        repo = MagicMock()
        script_file = tmp_path / "script.txt"
        script_file.write_text("Test script", encoding="utf-8")
        audio_file = tmp_path / "speech.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 40)
        ass_file = tmp_path / "subs.ass"
        ass_file.write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")
        srt_file = tmp_path / "subtitles.srt"
        srt_file.write_text("1\n00:00:01,000 --> 00:00:03,000\nHola mundo\n", encoding="utf-8")
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"mock_video")
        thumb_file = tmp_path / "thumbnail.jpg"
        thumb_file.write_bytes(b"mock_thumb")
        visual_plan_file = tmp_path / "visual_plan.json"
        visual_plan_file.write_text("{}", encoding="utf-8")
        meta_file = tmp_path / "metadata.json"

        ctx = PipelineContext(
            story={"title": "Test SRT Registration", "content": "Test"},
            story_id="story_srt_1",
            run_id="run_srt_1",
            channel_name="moku",
            channel_key="moku",
            lane=lane,
            repository=repo,
            database=":memory:",
            owner="test_worker",
            lease_seconds=300,
            settings=MagicMock(),
            branding=MagicMock(),
            profiler=mock_profiler,
            directed=False,
            generate_only=False,
            engine_mode="director",
            is_loop_mode=False,
            is_multiscene_mode=True,
            subtitles_active=True,
            work_dir=tmp_path,
            audio_path=audio_file,
            ass_path=tmp_path / "subs.ass",
            srt_path=srt_file,
            video_path=video_file,
            thumbnail_path=thumb_file,
            script_path=script_file,
            visual_plan_path=visual_plan_file,
            metadata_path=meta_file,
            scene_manifest_path=tmp_path / "scene_manifest.json",
        )
        ctx.title = "Test SRT Registration"
        ctx.script = "Test script"
        ctx.shot_durations = [255.0, 310.0, 480.0, 355.0]
        ctx.script_payload = {
            "acts": [
                {"act_number": 1, "act_title": "Acto I: Incepción", "target_duration_sec": 255.0},
                {"act_number": 2, "act_title": "Acto II: Señales", "target_duration_sec": 310.0},
                {"act_number": 3, "act_title": "Acto III: Ruptura", "target_duration_sec": 480.0},
                {"act_number": 4, "act_title": "Acto IV: Trauma", "target_duration_sec": 355.0},
            ]
        }

        stage_11_thumbnail_metadata(ctx)

        # Assert repository recorded subtitles_srt
        recorded_kinds = [call[0][1] for call in repo.record_artifact.call_args_list]
        assert "subtitles_srt" in recorded_kinds

        # Assert metadata.json contains chapters and srt reference
        assert meta_file.is_file()
        meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
        assert "chapters" in meta_data
        assert len(meta_data["chapters"]) == 4
        assert "srt_path" in meta_data or "subtitles_srt" in meta_data



