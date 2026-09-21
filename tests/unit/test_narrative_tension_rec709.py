"""
tests/unit/test_narrative_tension_rec709.py - Unit test suite for 5-Phase Tension Curve,
WPM Scene Segmentation, and Rec.709 Color-Palette Generation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
import jsonschema
import pytest

from src.narrative.schema import (
    AudioContract,
    CameraTransform,
    CosmicScriptContract,
    NarrativeArchetype,
    Rec709Palette,
    SceneContract,
    SceneContractV2,
    TensionLevel,
    VideoFormat,
    VoicePreset,
)
from src.narrative.archetypes import (
    ARCHETYPE_PRESETS,
    REC709_PALETTE_TABLES,
    resolve_archetype_for_topic,
)
from src.narrative.engine import (
    CosmicNarrativeEngine,
    clamp_and_smooth_tension_curve,
    score_5phase_tension_curve,
    segment_narration_into_scenes,
)
from src.curators.text_splitter import CinematicScriptCuratorAgent
from src.agents.atmospheric_director import THEME_PALETTES, AtmosphericDirectorAgent as ArtDirectorMoodAgent
from src.media.manifest_compiler import SceneManifestCompiler as ScenePlannerCompositorAgent


SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"
ART_DIRECTOR_SCHEMA_PATH = SCHEMA_DIR / "art_director.schema.json"
SCRIPT_CURATOR_SCHEMA_PATH = SCHEMA_DIR / "script_curator.schema.json"


# ============================================================================
# 1. 5-Phase Tension Curve Scoring Tests
# ============================================================================

class Test5PhaseTensionCurve:
    """Tests 5-phase tension curve scoring: Baseline (1-2), Micro-anomaly (2-3),
    Escalation (3-4), Climax (5), and Loop Hook (2-3)."""

    def test_5phase_tension_progression_bounds(self) -> None:
        """Requirement 2: 5-Phase Tension Curve Scoring (Levels 1-5)."""
        curve = score_5phase_tension_curve(num_scenes=5)
        assert len(curve) == 5
        assert curve[0] in (1, 2), f"Phase 1 (Baseline) must be 1-2, got {curve[0]}"
        assert curve[1] in (2, 3), f"Phase 2 (Micro-anomaly) must be 2-3, got {curve[1]}"
        assert curve[2] in (3, 4), f"Phase 3 (Escalation) must be 3-4, got {curve[2]}"
        assert curve[3] == 5, f"Phase 4 (Climax) must be 5, got {curve[3]}"
        assert curve[4] in (2, 3), f"Phase 5 (Loop Hook) must be 2-3, got {curve[4]}"

    def test_5phase_tension_4_scenes(self) -> None:
        """Validates 4-scene pacing reaching climax 5 before loop resolution."""
        curve = score_5phase_tension_curve(num_scenes=4)
        assert len(curve) == 4
        assert curve[0] in (1, 2)
        assert curve[1] in (2, 3, 4)
        assert curve[2] == 5  # Climax
        assert curve[3] in (2, 3)  # Loop hook

    def test_5phase_tension_custom_scene_counts(self) -> None:
        """Validates tension curve scaling across arbitrary scene counts."""
        for n in range(3, 10):
            curve = score_5phase_tension_curve(num_scenes=n)
            assert len(curve) == n
            assert all(1 <= t <= 5 for t in curve)
            assert 5 in curve, f"Climax tension 5 must be present in curve of length {n}"
            # Climax should be near the end but before final loop resolution
            climax_idx = curve.index(5)
            assert climax_idx >= n - 2
            # Final scene de-escalates to 2 or 3
            assert curve[-1] in (2, 3)

    def test_narrative_engine_generates_5phase_tension_scenes(self) -> None:
        """Engine synthesizes script with tension scores complying with 5-phase curve."""
        engine = CosmicNarrativeEngine()
        script = engine.generate_script(
            topic="Deep sea seismic resonance anomaly detected at Mariana Trench",
            video_format=VideoFormat.SHORT_VERTICAL,
            duration_sec=35.0,
        )
        assert len(script.scenes) >= 3
        tensions = [
            getattr(s, "tension_level", s.shader_params.get("uTension", 0))
            for s in script.scenes
        ]
        # In integer scale or mapped float
        assert any(t == 5 or t == 1.0 for t in tensions)


# ============================================================================
# 2. Monotonic Tension Smoothing and Clamping Tests
# ============================================================================

class TestTensionSmoothingAndClamping:
    """Tests clamping erratic or out-of-range tension scores and monotonic smoothing."""

    def test_clamping_out_of_range_scores(self) -> None:
        """Scores outside [1, 5] must be clamped strictly to [1, 5]."""
        raw_scores = [-5, 0, 1, 3, 7, 10]
        smoothed = clamp_and_smooth_tension_curve(raw_scores)
        assert all(1 <= t <= 5 for t in smoothed)
        assert smoothed[0] >= 1
        assert smoothed[-1] <= 5

    def test_smoothing_abrupt_step_jumps(self) -> None:
        """Abrupt step jumps (Delta T > 2) must be smoothed to preserve dramatic pacing."""
        erratic = [1, 5, 1, 5]
        smoothed = clamp_and_smooth_tension_curve(erratic)
        assert all(1 <= t <= 5 for t in smoothed)
        for i in range(len(smoothed) - 1):
            delta = abs(smoothed[i + 1] - smoothed[i])
            assert delta <= 2, f"Step jump between index {i} and {i+1} was {delta} > 2 in {smoothed}"

    def test_inverted_tension_curve_normalization(self) -> None:
        """Inverted tension inputs like [5, 4, 3, 2, 1] are normalized to escalation arc."""
        inverted = [5, 4, 3, 2, 1]
        normalized = clamp_and_smooth_tension_curve(inverted, enforce_climax=True)
        assert all(1 <= t <= 5 for t in normalized)
        assert 5 in normalized
        assert normalized[-1] in (2, 3)


# ============================================================================
# 3. Semantic Scene Duration Bounds & Orphan Merging Tests
# ============================================================================

class TestSemanticSceneDurationBounds:
    """Tests scene duration bounds (8.0s <= t <= 15.0s at 150-175 WPM) and orphan merging."""

    def test_wpm_scene_segmentation_bounds(self) -> None:
        """Requirement 3: Every scene duration must satisfy 8.0s <= duration <= 15.0s."""
        # 120 words at 160 WPM = 45 seconds total
        words = ["palabra" for _ in range(120)]
        narration = ". ".join([" ".join(words[i:i + 15]) for i in range(0, 120, 15)]) + "."
        
        scenes = segment_narration_into_scenes(
            narration_text=narration,
            wpm=160.0,
            min_scene_dur=8.0,
            max_scene_dur=15.0,
        )
        assert 3 <= len(scenes) <= 5
        total_dur = sum(s["duration_sec"] for s in scenes)
        assert abs(total_dur - 45.0) <= 1.0

        for s in scenes:
            dur = s["duration_sec"]
            assert 8.0 <= dur <= 15.0, f"Scene duration {dur:.2f}s violated [8.0s, 15.0s] bounds"

    def test_short_orphan_clause_merging(self) -> None:
        """A short trailing phrase (e.g. 4 words / 1.5s) must merge with previous scene without exceeding 15s."""
        main_text = "El registro del sensor submarino confirmó una anomalía colosal en la fosa mesoatlántica durante la medianoche."
        trailing_orphan = "Fin del registro."  # 3 words ~ 1.1s

        full_text = f"{main_text} {trailing_orphan}"
        scenes = segment_narration_into_scenes(
            narration_text=full_text,
            wpm=160.0,
            min_scene_dur=8.0,
            max_scene_dur=15.0,
        )
        # All scenes must be >= 8.0s
        for s in scenes:
            assert s["duration_sec"] >= 8.0, f"Orphan sub-8s scene was generated: {s}"
            assert s["duration_sec"] <= 15.0, f"Scene exceeded 15.0s ceiling: {s}"

    def test_script_curator_enforces_shorts_scene_bounds(self) -> None:
        """CinematicScriptCuratorAgent generates scenes conforming to 8.0-15.0s bounds."""
        curator = CinematicScriptCuratorAgent()
        raw_text = (
            "Registro de telemetría número cuarenta y cuatro. "
            "A las tres de la madrugada los sensores detectaron una masa no identificada. "
            "La presión del casco aumentó un cincuenta por ciento en diez segundos. "
            "Las compuertas de seguridad se sellaron automáticamente ante el colapso. "
            "Si escuchas este mensaje el protocolo de cuarentena ha comenzado."
        )
        result = curator.curate(
            raw_text=raw_text,
            title="Telemetría Abisal",
            channel_lane="moku-scp-shorts",
            target_format="short",
            words_per_minute=160.0,
        )
        assert result["version"] == "2.0"
        all_scenes = [s for act in result["acts"] for s in act["scenes"]]
        for sc in all_scenes:
            dur = sc["estimated_duration_sec"]
            assert 8.0 <= dur <= 15.0, f"Scene {sc['scene_id']} duration {dur}s not in [8.0, 15.0]"


# ============================================================================
# 4. Rec.709 Color Palette & Schema Validation Tests
# ============================================================================

class TestRec709PaletteAndSchemaValidation:
    """Tests Rec.709 palette generation, Kelvin calibration (3000K-7000K), and schema compliance."""

    def test_rec709_palette_dataclass_contract(self) -> None:
        """Validates Rec709Palette schema contract attributes and defaults."""
        palette = Rec709Palette(
            primary="#041421",
            secondary="#0a2233",
            accent="#00e5a3",
            shadow="#000305",
            highlight="#b0fff1",
            kelvin=6500,
            lut_profile="cosmic_abyss_rec709",
        )
        assert palette.primary == "#041421"
        assert 3000 <= palette.kelvin <= 7000
        assert palette.lut_profile == "cosmic_abyss_rec709"
        
        p_dict = palette.to_dict()
        assert p_dict["kelvin"] == 6500
        assert p_dict["accent"] == "#00e5a3"

    def test_scene_contract_v2_dataclass(self) -> None:
        """Validates SceneContractV2 dataclass with Rec709Palette and CameraTransform."""
        palette = Rec709Palette(
            primary="#041421",
            secondary="#0a2233",
            accent="#00e5a3",
            shadow="#000305",
            highlight="#b0fff1",
            kelvin=6500,
        )
        transform = CameraTransform(offset_x=0.02, offset_y=-0.03, rotation_deg=0.8, zoom_scale=1.05)
        scene = SceneContractV2(
            start_sec=0.0,
            end_sec=11.5,
            tension_level=TensionLevel.CLIMAX if hasattr(TensionLevel, "CLIMAX") else 5,
            shader_id="MONOLITHS_RAYMARCHING",
            palette=palette,
            camera_transform=transform,
        )
        assert scene.start_sec == 0.0
        assert scene.end_sec == 11.5
        assert int(scene.tension_level) == 5
        assert scene.palette.kelvin == 6500

    def test_art_director_generates_valid_rec709_plan(self) -> None:
        """ArtDirectorMoodAgent outputs visual plan strictly complying with schemas/art_director.schema.json."""
        curator = CinematicScriptCuratorAgent()
        script = curator.curate(
            raw_text="Anomalía biológica en fosa abisal con distorsión del espacio.",
            title="Dossier Abisal",
            channel_lane="moku-horror-long",
            target_format="longform",
        )
        art_director = ArtDirectorMoodAgent()
        visual_plan = art_director.plan_visuals(script, theme_lane="cosmic_horror")

        assert visual_plan["version"] == "2.0"
        assert visual_plan["global_color_grade"]["color_space"] == "Rec.709"

        if ART_DIRECTOR_SCHEMA_PATH.is_file():
            with open(ART_DIRECTOR_SCHEMA_PATH, "r", encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.validate(instance=visual_plan, schema=schema)

        # Check Kelvin color temp calibration (3000K <= K <= 7000K)
        for sc in visual_plan["scenes"]:
            k = sc["lighting"]["color_temp_kelvin"]
            assert 1800 <= k <= 10000
            assert 3000 <= k <= 7000, f"Expected Kelvin temp in [3000K, 7000K] standard range, got {k}K"
            # Validate hex colors
            for key, hex_code in sc["palette"].items():
                assert hex_code.startswith("#")
                assert len(hex_code) == 7

    def test_unknown_theme_lane_fallback_to_canonical(self) -> None:
        """Unmapped custom theme falls back gracefully to canonical cosmic_horror."""
        art_director = ArtDirectorMoodAgent()
        curator = CinematicScriptCuratorAgent()
        script = curator.curate(
            raw_text="Experimento secreto en base dimensional.",
            title="Experimento Secreto",
            channel_lane="cyber_dystopia_unknown",
        )
        visual_plan = art_director.plan_visuals(script, theme_lane="cyber_dystopia_unknown")
        assert visual_plan["theme_lane"] in ("cosmic_horror", "scp_foundation", "creepypasta", "drama_aita")
        if ART_DIRECTOR_SCHEMA_PATH.is_file():
            with open(ART_DIRECTOR_SCHEMA_PATH, "r", encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.validate(instance=visual_plan, schema=schema)

    def test_open_domain_topic_synthesis_without_static_templates(self) -> None:
        """Open-domain prompt dynamically resolves archetype and generates compliant script."""
        engine = CosmicNarrativeEngine()
        script = engine.generate_script(
            topic="Quantum foam fluctuation detected in orbital particle collider",
            video_format=VideoFormat.SHORT_VERTICAL,
        )
        assert script.title == "Quantum foam fluctuation detected in orbital particle collider"
        assert len(script.scenes) >= 3

    def test_empty_or_whitespace_topic_fallback_to_default(self) -> None:
        """Empty or whitespace topic falls back cleanly to canonical default."""
        engine = CosmicNarrativeEngine()
        script_empty = engine.generate_script(topic="", video_format=VideoFormat.SHORT_VERTICAL)
        assert script_empty.title != ""
        assert len(script_empty.scenes) >= 3

        script_none = engine.generate_script(topic=None, video_format=VideoFormat.SHORT_VERTICAL)
        assert script_none.title != ""
