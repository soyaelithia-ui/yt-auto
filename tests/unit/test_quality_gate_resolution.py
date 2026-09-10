"""
Gate resolution tests: the prepublication quality gate must treat 1080x1920 as the
canonical short-mode resolution (test scale 540x960), require longform 1920x1080
(LONGFORM_RESOLUTION since c60effa), and require shorts ASS PlayRes 1080/1920.

Mock pattern follows tests/unit/test_directed_story_safety.py:790-833
(ffprobe / has_faststart / detect_long_black_frames + PIL thumbnail) — no real encodes.
"""
import json

import pytest
from PIL import Image

from src.core.quality import validate_prepublication

SPANISH_SCRIPT = (
    "Esta es una historia en español porque la protagonista llegó a la casa y no sabía "
    "qué hacer cuando todos estaban allí, pero decidió contar toda la verdad."
)
SPANISH_DESCRIPTION = (
    "Esta es una descripción completa en español para la historia de terror que se publica hoy."
)


def _visual_plan_json(duration_sec: float, scene_duration: float, count: int, source) -> str:
    scenes = [
        {"duration": scene_duration, "source": str(source)}
        for _ in range(count)
    ]
    return json.dumps(
        {
            "covered_seconds": duration_sec,
            "black_fallbacks": 0,
            "scenes": scenes,
        }
    )


def _build_gate_inputs(tmp_path, duration_sec, ass_playres, scene_duration, scene_count):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"ftypmoovmdat")
    subtitle = tmp_path / "subtitles.ass"
    subtitle.write_text(
        f"[Script Info]\nPlayResX: {ass_playres[0]}\nPlayResY: {ass_playres[1]}\n",
        encoding="utf-8",
    )
    thumbnail = tmp_path / "thumbnail.jpg"
    Image.new("RGB", (1280, 720), "red").save(thumbnail)
    source = tmp_path / "scene.jpg"
    source.write_bytes(b"image")
    plan = tmp_path / "visual_plan.json"
    plan.write_text(
        _visual_plan_json(duration_sec, scene_duration, scene_count, source),
        encoding="utf-8",
    )
    return {
        "channel": "moku",
        "script": SPANISH_SCRIPT,
        "title": "La casa donde nadie debía entrar",
        "description": SPANISH_DESCRIPTION,
        "video_path": video,
        "subtitle_path": subtitle,
        "thumbnail_path": thumbnail,
        "visual_plan_path": plan,
        "expected_story_count": 1,
        "visibility": "public",
    }


def _mock_probe_helpers(monkeypatch, width, height, duration_sec):
    monkeypatch.setattr(
        "src.core.quality.ffprobe",
        lambda _path: {
            "format": {"duration": str(duration_sec)},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": width,
                    "height": height,
                    "pix_fmt": "yuv420p",
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        },
    )
    monkeypatch.setattr("src.core.quality.has_faststart", lambda _path: True)
    monkeypatch.setattr("src.core.quality.detect_long_black_frames", lambda _path: (0.0, []))


class TestShortModeResolutionGate:

    def test_short_720x1280_with_playres_720_passes(self, monkeypatch, tmp_path):
        _mock_probe_helpers(monkeypatch, width=1080, height=1920, duration_sec=90.0)
        kwargs = _build_gate_inputs(tmp_path, 90.0, ass_playres=(1080, 1920), scene_duration=10.0, scene_count=9)
        report = validate_prepublication(**kwargs, video_mode="short")
        assert report.passed, report.issues

    def test_short_legacy_768x1360_is_rejected(self, monkeypatch, tmp_path):
        _mock_probe_helpers(monkeypatch, width=768, height=1360, duration_sec=90.0)
        kwargs = _build_gate_inputs(tmp_path, 90.0, ass_playres=(1080, 1920), scene_duration=10.0, scene_count=9)
        report = validate_prepublication(**kwargs, video_mode="short")
        assert any("resolución de video distinta de 1080x1920" in issue for issue in report.issues)

    def test_short_test_scale_360x640_accepted(self, monkeypatch, tmp_path):
        _mock_probe_helpers(monkeypatch, width=540, height=960, duration_sec=90.0)
        kwargs = _build_gate_inputs(tmp_path, 90.0, ass_playres=(1080, 1920), scene_duration=10.0, scene_count=9)
        report = validate_prepublication(**kwargs, video_mode="short")
        assert not any("resolución de video" in issue for issue in report.issues)
        assert report.passed, report.issues

    def test_short_playres_768_1360_rejected(self, monkeypatch, tmp_path):
        _mock_probe_helpers(monkeypatch, width=1080, height=1920, duration_sec=90.0)
        kwargs = _build_gate_inputs(tmp_path, 90.0, ass_playres=(768, 1360), scene_duration=10.0, scene_count=9)
        report = validate_prepublication(**kwargs, video_mode="short")
        assert any("resolución ASS no es 1080x1920" in issue for issue in report.issues)


class TestLongformResolutionCurrent:
    """Longform contract since c60effa: renderer default is 1920x1080.

    The legacy 1280x720 acceptance was tied to the pre-1080p renderer and
    rejected a correct production render (run 8a30d658, incident 2026-08-23);
    the gate now expects LONGFORM_RESOLUTION.
    """

    def test_longform_1920x1080_with_playres_1920_passes(self, monkeypatch, tmp_path):
        _mock_probe_helpers(monkeypatch, width=1920, height=1080, duration_sec=600.0)
        # 30 scenes x 20.0s = 600s, all within [15.0, 45.0] cadence
        kwargs = _build_gate_inputs(tmp_path, 600.0, ass_playres=(1920, 1080), scene_duration=20.0, scene_count=30)
        report = validate_prepublication(**kwargs, video_mode="longform")
        assert report.passed, report.issues
        assert not any("resolución ASS" in issue for issue in report.issues)

    def test_longform_legacy_1280x720_is_rejected(self, monkeypatch, tmp_path):
        _mock_probe_helpers(monkeypatch, width=1280, height=720, duration_sec=600.0)
        kwargs = _build_gate_inputs(tmp_path, 600.0, ass_playres=(1280, 720), scene_duration=20.0, scene_count=30)
        report = validate_prepublication(**kwargs, video_mode="longform")
        assert any(
            "resolución de video distinta de 1920x1080" in issue for issue in report.issues
        )


class TestPrecomputedVisualQualityMetrics:
    """Verifies that precomputed blackdetect and luminance metrics in precomputed_visual
    are respected without calling detect_long_black_frames or analyze_perceptual_luminance."""

    def test_precomputed_visual_bypasses_expensive_analysis(self, monkeypatch, tmp_path):
        _mock_probe_helpers(monkeypatch, width=1920, height=1080, duration_sec=600.0)

        # Make detect_long_black_frames and analyze_perceptual_luminance fail if called
        def _fail_black(_):
            raise AssertionError("detect_long_black_frames should not be called")

        def _fail_lum(_):
            raise AssertionError("analyze_perceptual_luminance should not be called")

        monkeypatch.setattr("src.core.quality.detect_long_black_frames", _fail_black)
        monkeypatch.setattr("src.core.quality.analyze_perceptual_luminance", _fail_lum)

        kwargs = _build_gate_inputs(tmp_path, 600.0, ass_playres=(1920, 1080), scene_duration=20.0, scene_count=30)
        from src.core.quality import luminance_params_fingerprint, LUMINANCE_SAMPLE_FPS
        precomputed = {
            "passed": True,
            "bypassed": True,
            "engine": "loop",
            "longest_black_seconds": 0.0,
            "black_segments": [],
            "perceptual_luminance": {
                "avg_luminance": 75.0,
                "dark_ratio": 0.0,
                "passed": True,
                "luminance_params": luminance_params_fingerprint(LUMINANCE_SAMPLE_FPS),
            },
        }
        report = validate_prepublication(**kwargs, video_mode="longform", precomputed_visual=precomputed)
        assert report.passed, report.issues
        assert report.facts.get("black_source") == "precomputed_visual"
        assert report.facts.get("luminance_source") == "precomputed_visual"
        assert report.facts.get("longest_black_seconds") == 0.0


class TestShortDurationGating:
    def test_short_substandard_44s_rejected_in_production(self, monkeypatch, tmp_path):
        monkeypatch.setattr("src.core.quality.is_test_environment", lambda: False)
        _mock_probe_helpers(monkeypatch, width=1080, height=1920, duration_sec=44.0)
        kwargs = _build_gate_inputs(tmp_path, 44.0, ass_playres=(1080, 1920), scene_duration=11.0, scene_count=4)
        report = validate_prepublication(**kwargs, video_mode="short")
        assert not report.passed
        assert any("duración editorial fuera de rango para Short (60s-180s)" in issue for issue in report.issues)

    def test_short_lane_min_duration_sec_enforced(self, monkeypatch, tmp_path):
        monkeypatch.setattr("src.core.quality.is_test_environment", lambda: False)
        _mock_probe_helpers(monkeypatch, width=1080, height=1920, duration_sec=55.0)
        kwargs = _build_gate_inputs(tmp_path, 55.0, ass_playres=(1080, 1920), scene_duration=11.0, scene_count=5)
        report = validate_prepublication(**kwargs, video_mode="short", min_duration_sec=60.0)
        assert not report.passed
        assert any("duración editorial fuera de rango para Short (60s-180s)" in issue for issue in report.issues)

    def test_short_65s_accepted_in_production(self, monkeypatch, tmp_path):
        monkeypatch.setattr("src.core.quality.is_test_environment", lambda: False)
        _mock_probe_helpers(monkeypatch, width=1080, height=1920, duration_sec=65.0)
        kwargs = _build_gate_inputs(tmp_path, 65.0, ass_playres=(1080, 1920), scene_duration=13.0, scene_count=5)
        report = validate_prepublication(**kwargs, video_mode="short", min_duration_sec=60.0)
        assert not any("duración editorial" in issue for issue in report.issues)


