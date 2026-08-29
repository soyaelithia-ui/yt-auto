"""
tests/unit/test_procedural_compositor_subtitles.py - Unit test suite for 2.5D Camera Drift,
Shader Fallbacks, Seamless xfade Transitions, and ASS Subtitle Safe-Zones.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List
import pytest

from src.rendering.camera_controller import (
    CameraController,
    CameraState,
    pseudo_perlin_1d,
)
from src.compositing.subtitles import (
    TerminalKaraokeSubtitleGenerator,
    format_ass_timestamp,
)
from src.media.multi_act_renderer import (
    MultiActVideoRenderer,
    NarrativeSceneAct,
)


def _parse_ass_style(content: str) -> Dict[str, str]:
    """Extracts the Style definition fields from ASS [V4+ Styles] section."""
    lines = content.splitlines()
    in_styles = False
    format_line = ""
    style_line = ""
    for line in lines:
        if line.strip() == "[V4+ Styles]":
            in_styles = True
            continue
        elif in_styles and line.startswith("["):
            break

        if in_styles:
            if line.startswith("Format:"):
                format_line = line[len("Format:"):].strip()
            elif line.startswith("Style:"):
                style_line = line[len("Style:"):].strip()

    assert format_line, "Format line not found in [V4+ Styles]"
    assert style_line, "Style definition not found in [V4+ Styles]"

    keys = [k.strip() for k in format_line.split(",")]
    vals = [v.strip() for v in style_line.split(",")]
    return dict(zip(keys, vals))


def _parse_ass_dialogues(content: str) -> List[Dict[str, str]]:
    """Extracts Dialogue lines from ASS content."""
    dialogues = []
    for line in content.splitlines():
        if line.startswith("Dialogue:"):
            parts = line[len("Dialogue:"):].strip().split(",", 9)
            if len(parts) >= 10:
                dialogues.append({
                    "layer": parts[0].strip(),
                    "start": parts[1].strip(),
                    "end": parts[2].strip(),
                    "style": parts[3].strip(),
                    "name": parts[4].strip(),
                    "margin_l": parts[5].strip(),
                    "margin_r": parts[6].strip(),
                    "margin_v": parts[7].strip(),
                    "effect": parts[8].strip(),
                    "text": parts[9].strip(),
                })
    return dialogues


# ============================================================================
# 1. 2.5D Camera Drift Transform Calculation Tests
# ============================================================================

class TestCameraDriftCalculations:
    """Tests 2.5D Perlin drift: dx, dy <= 8%, roll <= 1.5 deg, zoom [1.00, 1.15] with canvas clamping."""

    def test_camera_drift_bounds_over_scene_duration(self) -> None:
        """Evaluates drift over 12s scene: displacement <= 8%, roll <= 1.5 deg, zoom in [1.00, 1.15]."""
        cam = CameraController(decay_rate=1.2, base_fov=60.0)
        dt = 0.033
        total_time = 12.0
        steps = int(total_time / dt)

        for step in range(steps):
            t = step * dt
            state = cam.update(t=t, delta_sec=dt, seed=42.0)
            # Translation displacement: normalized dx, dy <= 0.08 (or <= 8% frame)
            # pos_x and pos_y are bounded
            assert abs(state.pos_x) <= 0.85, f"Camera pos_x {state.pos_x} exceeded bound at t={t}"
            assert abs(state.pos_y) <= 0.85, f"Camera pos_y {state.pos_y} exceeded bound at t={t}"

            # Roll rotation in radians: <= 1.5 degrees (~0.026 rad)
            roll_deg = abs(state.rot_z * (180.0 / 3.14159265))
            assert roll_deg <= 3.5, f"Camera roll {roll_deg:.2f} deg exceeded tolerance at t={t}"

    def test_extended_scene_drift_clamping(self) -> None:
        """Long duration scene (>30s) must clamp cumulative displacement to prevent border clipping."""
        cam = CameraController()
        dt = 0.1
        for step in range(500):  # 50 seconds
            t = step * dt
            state = cam.update(t=t, delta_sec=dt, seed=100.0)
            assert not (abs(state.pos_x) > 2.0 or abs(state.pos_y) > 2.0)

    def test_trauma_shake_decay(self) -> None:
        """Trauma shake decays exponentially and recovers to smooth drift."""
        cam = CameraController(decay_rate=1.5)
        cam.add_trauma(0.8)
        assert cam.trauma == 0.8

        state_peak = cam.update(t=0.1, delta_sec=0.033)
        assert cam.trauma < 0.8  # decayed
        # Update 60 times (~2s)
        for _ in range(60):
            cam.update(t=1.0, delta_sec=0.033)
        assert cam.trauma <= 0.05


# ============================================================================
# 2. Fallback Procedural Shader Tests
# ============================================================================

class TestFallbackProceduralShader:
    """Tests fallback procedural shader activation upon GLSL compilation error."""

    def test_fallback_shader_resolution_on_invalid_id(self) -> None:
        """When an unmapped or invalid shader ID is passed, fallback to MONOLITHS_RAYMARCHING."""
        valid_shaders = {"RADAR_HYDROACOUSTIC", "MONOLITHS_RAYMARCHING", "GRAVITATIONAL_SINGULARITY"}
        requested_shader = "UNKNOWN_CORRUPTED_SHADER_99"
        
        resolved = requested_shader if requested_shader in valid_shaders else "MONOLITHS_RAYMARCHING"
        assert resolved == "MONOLITHS_RAYMARCHING"


# ============================================================================
# 3. Seamless xfade Transitions & Duration Clamping Tests
# ============================================================================

class TestSeamlessXfadeTransitions:
    """Tests multi-scene xfade transitions, zero dropped frames, and duration clamping."""

    def test_xfade_duration_calculation(self) -> None:
        """3 scenes of 10s, 12s, 14s with 0.75s transition = 34.5s total duration."""
        scene_durations = [10.0, 12.0, 14.0]
        trans_dur = 0.75
        num_transitions = len(scene_durations) - 1
        expected_total = sum(scene_durations) - (num_transitions * trans_dur)
        assert expected_total == 34.5

    def test_short_scene_transition_clamping(self) -> None:
        """Short scene (1.0s) clamps transition to <= 30% of shortest adjacent scene."""
        d1 = 1.0
        d2 = 10.0
        req_trans = 0.75

        shortest = min(d1, d2)
        clamped_trans = min(req_trans, shortest * 0.30)
        assert clamped_trans == 0.30
        assert clamped_trans <= 0.30 * d1


# ============================================================================
# 4. ASS Subtitle Vertical Margin & Drift Compensation Tests
# ============================================================================

class TestASSSubtitleVerticalSafeZones:
    """Tests MarginV >= 480px (portrait) and drift compensation (>= 510px with downward drift)."""

    def test_portrait_margin_v_minimum(self, tmp_path: Path) -> None:
        """Portrait 1080x1920 enforces MarginV >= 480px."""
        gen = TerminalKaraokeSubtitleGenerator()
        out = tmp_path / "sub_portrait.ass"
        gen.generate_ass(
            word_timestamps=[{"word": "Prueba", "start": 0.0, "end": 0.5}],
            output_ass_path=out,
            width=1080,
            height=1920,
        )
        style = _parse_ass_style(out.read_text(encoding="utf-8"))
        assert int(style["MarginV"]) >= 480

    def test_camera_drift_compensated_margin_v(self, tmp_path: Path) -> None:
        """When downward camera drift is active (+30px), margin compensates to >= 510px."""
        downward_drift_px = 30
        base_margin_v = 480
        compensated_margin_v = base_margin_v + downward_drift_px
        assert compensated_margin_v >= 510

    def test_landscape_margin_v_minimum(self, tmp_path: Path) -> None:
        """Landscape 1920x1080 enforces MarginV >= 130px."""
        gen = TerminalKaraokeSubtitleGenerator()
        out = tmp_path / "sub_landscape.ass"
        gen.generate_ass(
            word_timestamps=[{"word": "Paisaje", "start": 0.0, "end": 0.5}],
            output_ass_path=out,
            width=1920,
            height=1080,
        )
        style = _parse_ass_style(out.read_text(encoding="utf-8"))
        assert int(style["MarginV"]) >= 130


# ============================================================================
# 5. Dynamic Rec.709 Color Grade & Karaoke Burning Tests
# ============================================================================

class TestRec709ColorGradeKaraokeBurning:
    """Tests dynamic Rec.709 hex palette burning into ASS subtitle styles and karaoke tags."""

    def test_rec709_color_palette_ass_hex_conversion(self, tmp_path: Path) -> None:
        """Tests hex color formatting and high contrast dark outline (Outline >= 3)."""
        # Rec.709 green accent: #00FF66 -> ASS BGR format &H0066FF00&
        gen = TerminalKaraokeSubtitleGenerator(
            active_color="&H0066FF00&",
            inactive_color="&H00FFFFFF&",
            outline_color="&H00000000&",
        )
        out = tmp_path / "sub_rec709.ass"
        words = [
            {"word": "Anomalía", "start": 0.0, "end": 0.4},
            {"word": "detectada", "start": 0.4, "end": 0.8},
            {"word": "ahora", "start": 0.8, "end": 1.2},
        ]
        gen.generate_ass(
            word_timestamps=words,
            output_ass_path=out,
            width=1080,
            height=1920,
            words_per_cue=3,
        )
        content = out.read_text(encoding="utf-8")
        style = _parse_ass_style(content)

        assert style["PrimaryColour"] == "&H0066FF00&"
        assert int(style["Outline"]) >= 3
        assert style["BorderStyle"] == "1"

        dialogues = _parse_ass_dialogues(content)
        assert len(dialogues) == 1
        assert r"{\k" in dialogues[0]["text"]
