"""
tests/unit/test_dual_engine_pipeline.py - Zero-Quota Unit & Integration Tests for Dual-Engine Multi-Scene Pipeline.

Tests:
1. CinematicScriptCuratorAgent (Agent 1 - 4 Acts, Tension Curve, Schema validation).
2. ArtDirectorMoodAgent (Agent 2 - Rec.709 Color Palettes, Volumetrics, Schema validation).
3. ScenePlannerCompositorAgent (Agent 3 - Engine Selection, Canonical Manifest validation).
4. VisualAudioQAAuditorAgent (Agent 4 - Forensic L1/L2/L3 Audits, Schema validation).
5. HybridVideoEngine (Layered 2.5D parallax, Ken Burns Bézier, particles).
6. ProceduralVideoEngine (Deterministic procedural scenes).
7. MultiSceneCompositor (Full master assembly with EBU R128 ducking).
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agents.script_curator import CinematicScriptCuratorAgent
from src.agents.art_director import ArtDirectorMoodAgent
from src.agents.scene_planner import ScenePlannerCompositorAgent
from src.agents.qa_auditor import VisualAudioQAAuditorAgent
from src.media.hybrid_engine import HybridVideoEngine, cubic_bezier_ease
from src.media.proc_engine import ProceduralVideoEngine
from src.media.compositor import MultiSceneCompositor
from src.scene_manifest import (
    SceneManifestV2,
    parse_scene_manifest_model,
    validate_scene_manifest,
)


@pytest.fixture
def sample_story_text():
    return (
        "En lo profundo del abismo de las aguas negras, un faro ancestral continuaba girando su linterna esmeralda. "
        "Los pescadores de la costa evitaban acercarse cuando la niebla descendía sobre los riscos. "
        "A las tres de la madrugada, un sonido grave y metálico emergió desde las profundidades del océano. "
        "Colosales siluetas con tentáculos bioluminiscentes rodearon la estructura de piedra mientras los cuervos huían despavoridos. "
        "Nadie sobrevivió a la noche en que el eclipse cósmico abrió la grieta entre las dimensiones."
    )


class TestCinematicScriptCuratorAgent:
    def test_curate_longform_produces_four_acts(self, sample_story_text):
        agent = CinematicScriptCuratorAgent()
        result = agent.curate(
            raw_text=sample_story_text,
            title="El Misterio del Faro Abisal",
            channel_lane="moku-horror-long",
            target_format="longform",
        )

        assert result["version"] == "2.0"
        assert result["metadata"]["target_format"] == "longform"
        assert len(result["acts"]) == 4
        assert result["acts"][0]["dramatic_role"] == "exposition_inception"
        assert result["acts"][2]["dramatic_role"] == "climax_confrontation"
        assert len(result["metadata"]["tension_curve"]) >= 4
        for t in result["metadata"]["tension_curve"]:
            assert 1 <= t <= 5

    def test_curate_short_format(self, sample_story_text):
        agent = CinematicScriptCuratorAgent()
        result = agent.curate(
            raw_text=sample_story_text,
            title="SCP-999 Brecha",
            channel_lane="moku-scp-shorts",
            target_format="short",
        )

        assert result["metadata"]["target_format"] == "short"
        assert len(result["acts"]) >= 1


class TestArtDirectorMoodAgent:
    def test_plan_visuals_cosmic_horror(self, sample_story_text):
        curator = CinematicScriptCuratorAgent()
        script = curator.curate(sample_story_text, title="Faro Cósmico", channel_lane="moku-horror-long")

        art_director = ArtDirectorMoodAgent()
        plan = art_director.plan_visuals(script, theme_lane="cosmic_horror")

        assert plan["version"] == "2.0"
        assert plan["theme_lane"] == "cosmic_horror"
        assert plan["global_color_grade"]["color_space"] == "Rec.709"
        assert len(plan["scenes"]) >= 4

        for sc in plan["scenes"]:
            assert sc["palette"]["primary"].startswith("#")
            assert sc["palette"]["accent"].startswith("#")
            assert len(sc["image_prompts"]["positive_prompt"]) >= 10
            assert "noisy grain" in sc["image_prompts"]["negative_prompt"]


class TestScenePlannerCompositorAgent:
    def test_plan_canonical_manifest(self, sample_story_text, tmp_path):
        curator = CinematicScriptCuratorAgent()
        script = curator.curate(sample_story_text, title="Faro Abisal", channel_lane="moku-horror-long")

        art_director = ArtDirectorMoodAgent()
        visual_plan = art_director.plan_visuals(script, theme_lane="cosmic_horror")

        dummy_audio = tmp_path / "speech.wav"
        dummy_audio.write_bytes(b"RIFF" + b"\x00" * 40)

        planner = ScenePlannerCompositorAgent()
        manifest = planner.plan_manifest(
            script=script,
            visual_plan=visual_plan,
            story_id="story_faro_101",
            narration_path=str(dummy_audio),
            lane_id="moku-horror-long",
            channel_name="moku",
            resolution=[1920, 1080],
            fps=30,
        )

        assert manifest["manifest_version"] == "2.0"
        assert manifest["resolution"] == [1920, 1080]
        assert manifest["audio_tracks"]["ducking"]["enabled"] is True
        assert len(manifest["scenes"]) >= 4

        # Validate against Draft-07 schema
        manifest_file = tmp_path / "scene_manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        assert validate_scene_manifest(manifest_file) is True


class TestVisualAudioQAAuditorAgent:
    def test_audit_video_happy_path(self, tmp_path):
        # Create dummy mp4 file
        dummy_mp4 = tmp_path / "test_video.mp4"
        dummy_mp4.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 100)

        auditor = VisualAudioQAAuditorAgent()
        with patch("src.agents.qa_auditor.probe_media") as mock_probe, \
             patch("src.agents.qa_auditor.has_faststart", return_value=True):

            mock_video = MagicMock()
            mock_video.width = 1920
            mock_video.height = 1080
            mock_video.codec = "h264"
            mock_video.codec_name = "h264"
            mock_video.pixel_format = "yuv420p"
            mock_video.pix_fmt = "yuv420p"
            mock_probe.return_value.primary_video = mock_video
            mock_probe.return_value.video = mock_video

            report = auditor.audit_video(
                video_path=dummy_mp4,
                run_id="run_qa_test_001",
                target_resolution="1920x1080",
            )

            assert report["version"] == "2.0"
            assert report["run_id"] == "run_qa_test_001"
            assert report["overall_pass"] is True
            assert report["tier2_visual_metrics"]["resolution"] == "1920x1080"


class TestDualEnginesAndCompositor:
    def test_cubic_bezier_easing(self):
        assert cubic_bezier_ease(0.0) == 0.0
        assert cubic_bezier_ease(1.0) == 1.0
        mid = cubic_bezier_ease(0.5)
        assert 0.4 <= mid <= 0.6

    def test_multi_scene_compositor_interface(self):
        comp = MultiSceneCompositor()
        assert comp.hybrid_engine is not None
        assert comp.procedural_engine is not None

    def test_hybrid_engine_render_scene_segment(self, tmp_path):
        from src.scene_manifest import SceneConfig, HybridAIConfig, CameraMotionConfig, LightingConfig, ParticleConfig
        engine = HybridVideoEngine()
        sc = SceneConfig(
            scene_index=1,
            scene_id="sc_test_hybrid",
            start_sec=0.0,
            duration_sec=0.5,
            tension_level=4,
            engine_type="hybrid_cinematic_ai",
            hybrid_ai_config=HybridAIConfig(
                camera_motion=CameraMotionConfig(type="ken_burns_3d", pan_direction="center_to_top"),
                lighting=LightingConfig(volumetric_rays=True, intensity=0.4),
                particles=ParticleConfig(type="dust_motes", density=15),
            ),
        )
        out_mp4 = tmp_path / "hybrid_scene.mp4"
        engine.render_scene_segment(
            scene=sc,
            width=320,
            height=180,
            fps=30,
            output_mp4=out_mp4,
            crf=26,
        )
        assert out_mp4.exists()
        assert out_mp4.stat().st_size > 500

    def test_multi_scene_compositor_full_render(self, tmp_path):
        import wave, struct, math
        speech_wav = tmp_path / "speech.wav"
        with wave.open(str(speech_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            for i in range(44100):
                val = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * 440.0 * i / 44100.0))
                wf.writeframes(struct.pack("<h", val))

        curator = CinematicScriptCuratorAgent()
        script = curator.curate(
            "En las profundidades del faro abisal, las sombras bailaban con la luz esmeralda. El mar rugía.",
            title="Prueba Multi-Escena",
            channel_lane="moku-horror-long",
        )
        art = ArtDirectorMoodAgent()
        vplan = art.plan_visuals(script, theme_lane="cosmic_horror")
        planner = ScenePlannerCompositorAgent()
        manifest_data = planner.plan_manifest(
            script=script,
            visual_plan=vplan,
            story_id="test_ms_001",
            narration_path=str(speech_wav),
            resolution=[1280, 720],
            fps=30,
        )
        manifest_data["scenes"] = manifest_data["scenes"][:2]
        for s in manifest_data["scenes"]:
            s["duration_sec"] = 0.3
        manifest_data["total_duration_sec"] = len(manifest_data["scenes"]) * 0.3

        manifest_file = tmp_path / "scene_manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

        out_master = tmp_path / "master_render.mp4"
        comp = MultiSceneCompositor()
        res = comp.render(
            manifest_path=manifest_file,
            output_video_path=out_master,
            crf=26,
            preset="ultrafast",
        )

        assert res["status"] == "success"
        assert out_master.exists()
        assert out_master.stat().st_size > 1000

    def test_multi_scene_compositor_default_preset_and_bounded_threads(self, tmp_path):
        import inspect, wave, struct, math
        comp = MultiSceneCompositor()
        sig = inspect.signature(comp.render)
        assert sig.parameters["preset"].default == "faster"

        speech_wav = tmp_path / "speech_threads.wav"
        with wave.open(str(speech_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            for i in range(44100):
                val = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * 440.0 * i / 44100.0))
                wf.writeframes(struct.pack("<h", val))

        curator = CinematicScriptCuratorAgent()
        script = curator.curate(
            "Un faro ancestral en el abismo.",
            title="Prueba Hilos",
            channel_lane="moku-horror-long",
        )
        art = ArtDirectorMoodAgent()
        vplan = art.plan_visuals(script, theme_lane="cosmic_horror")
        planner = ScenePlannerCompositorAgent()
        manifest_data = planner.plan_manifest(
            script=script,
            visual_plan=vplan,
            story_id="test_threads_001",
            narration_path=str(speech_wav),
            resolution=[1280, 720],
            fps=30,
        )
        manifest_data["scenes"] = manifest_data["scenes"][:1]
        for s in manifest_data["scenes"]:
            s["duration_sec"] = 0.2
        manifest_data["total_duration_sec"] = len(manifest_data["scenes"]) * 0.2

        manifest_file = tmp_path / "manifest_threads.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
        out_p = tmp_path / "out_threads.mp4"

        captured_threads = []
        orig_render = comp.procedural_engine.render_scene_segment

        def mock_render_segment(*args, **kwargs):
            captured_threads.append(kwargs.get("threads"))
            seg_out = kwargs.get("output_mp4")
            if seg_out:
                import subprocess
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1280x720:d=0.2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "0.2", str(seg_out)],
                    check=True,
                    capture_output=True,
                )

        comp.procedural_engine.render_scene_segment = mock_render_segment
        res = comp.render(manifest_path=manifest_file, output_video_path=out_p, crf=28, preset="ultrafast")
        assert res["status"] == "success"
        assert len(captured_threads) >= 1
        for t in captured_threads:
            assert isinstance(t, int)
            assert t >= 1

    def test_procedural_engine_subtitled_single_pass_rendering(self, tmp_path):
        from src.scene_manifest import SceneConfig
        from src.media.subtitles import CodeSubtitleDrawer
        engine = ProceduralVideoEngine()
        sc = SceneConfig(
            scene_index=1,
            scene_id="sc_proc_sub",
            start_sec=0.0,
            duration_sec=0.4,
            tension_level=2,
            engine_type="pure_procedural_webgl",
        )
        words = [
            {"word": "ENTIDAD", "start": 0.0, "end": 0.2},
            {"word": "DETECTADA", "start": 0.2, "end": 0.4},
        ]
        cues = CodeSubtitleDrawer.parse_word_timestamps(words, words_per_cue=2)
        out_sub = tmp_path / "proc_sub_scene.mp4"
        engine.render_scene_segment(
            scene=sc,
            width=320,
            height=180,
            fps=30,
            lane_id="moku-horror-long",
            output_mp4=out_sub,
            crf=28,
            subtitle_cues=cues,
            scene_start_sec=0.0,
            threads=2,
        )
        assert out_sub.exists()
        assert out_sub.stat().st_size > 500


