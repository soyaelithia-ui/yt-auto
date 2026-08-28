"""
tests/unit/test_adaptive_archetypes.py - Unit tests for universal adaptive visual archetypes.
"""
from pathlib import Path
import pytest
from src.agents.scene_planner import ScenePlannerCompositorAgent
from src.media.web_renderer import WebVideoRenderer, THEMATIC_TEMPLATES
from src.media.proc_engine import ProceduralVideoEngine


class TestUniversalAdaptiveArchetypes:
    def test_all_archetype_template_files_exist(self):
        """Verifies that all 6 universal archetype HTML template files exist on disk."""
        templates_dir = Path("src/media/web_templates")
        expected_templates = [
            "archetype_classified_terminal.html",
            "archetype_atmospheric_landscape.html",
            "archetype_tactical_chamber.html",
            "archetype_synaptic_network.html",
            "archetype_anomaly_silhouette.html",
            "archetype_cosmic_singularity.html",
        ]
        for tmpl in expected_templates:
            tmpl_file = templates_dir / tmpl
            assert tmpl_file.is_file(), f"Expected archetype template {tmpl} to exist in {templates_dir}"

    def test_archetypes_registered_in_web_renderer(self):
        """Verifies that WebVideoRenderer maps all archetypes properly."""
        renderer = WebVideoRenderer()
        for cat in [
            "classified_terminal",
            "atmospheric_landscape",
            "tactical_chamber",
            "synaptic_network",
            "anomaly_silhouette",
            "cosmic_singularity",
        ]:
            tmpl_path = renderer.resolve_template_path(cat)
            assert tmpl_path.is_file(), f"Failed resolving archetype category {cat}"

    def test_resolve_scene_archetype_semantic_adaptation(self):
        """Tests that _resolve_scene_archetype adapts to completely different story themes and moods."""
        # 1. Surveillance / Dossier / Terminal
        cat, tmpl, params = ScenePlannerCompositorAgent._resolve_scene_archetype(
            env_name="Classified Archive Room with Computer Monitors",
            tension=2,
            dramatic_role="exposition_inception",
            lane_id="moku-scp-shorts",
        )
        assert cat == "classified_terminal"
        assert tmpl == "archetype_classified_terminal.html"
        assert "docTitle" in params

        # 2. Brutalist Vault / Subterranean Bunker
        cat, tmpl, params = ScenePlannerCompositorAgent._resolve_scene_archetype(
            env_name="Subterranean Concrete Containment Vault",
            tension=3,
            dramatic_role="rising_action_dread",
            lane_id="moku-horror-long",
        )
        assert cat == "tactical_chamber"
        assert tmpl == "archetype_tactical_chamber.html"
        assert "chamberType" in params

        # 3. Neural Mind / Collective Consciousness / Entity
        cat, tmpl, params = ScenePlannerCompositorAgent._resolve_scene_archetype(
            env_name="Psychological Mind Grid and Neural Entity Domain",
            tension=3,
            dramatic_role="rising_action_dread",
            lane_id="moku-horror-long",
        )
        assert cat == "synaptic_network"
        assert tmpl == "archetype_synaptic_network.html"
        assert "nodeDensity" in params

        # 4. Anomaly / Colossus / Beast Rampage
        cat, tmpl, params = ScenePlannerCompositorAgent._resolve_scene_archetype(
            env_name="Cataclysmic Battlefield with Giant Monster Rampage",
            tension=5,
            dramatic_role="climax_confrontation",
            lane_id="moku-horror-long",
        )
        assert cat == "anomaly_silhouette"
        assert tmpl == "archetype_anomaly_silhouette.html"
        assert params.get("threatLevel") == 5

        # 5. Dimensional Singularity / Cosmic Rift
        cat, tmpl, params = ScenePlannerCompositorAgent._resolve_scene_archetype(
            env_name="Cosmic Event Horizon with Black Hole Singularity",
            tension=4,
            dramatic_role="climax_confrontation",
            lane_id="moku-horror-long",
        )
        assert cat == "cosmic_singularity"
        assert tmpl == "archetype_cosmic_singularity.html"
        assert "swirlSpeed" in params

        # 6. Drama / AITA lane
        cat, tmpl, params = ScenePlannerCompositorAgent._resolve_scene_archetype(
            env_name="Living Room Argument",
            tension=2,
            dramatic_role="exposition",
            lane_id="moku-aita-shorts",
        )
        assert cat == "drama_aita"
        assert tmpl == "drama_waves_canvas.html"

    def test_end_to_end_manifest_generation_with_archetypes(self):
        """Validates that plan_manifest produces valid SceneManifestV2 containing archetypes."""
        planner = ScenePlannerCompositorAgent()
        
        script = {
            "metadata": {
                "story_id": "test_adaptive_001",
                "channel_lane": "moku-horror-long",
                "target_format": "short",
            },
            "acts": [
                {
                    "act_number": 1,
                    "dramatic_role": "exposition_inception",
                    "scenes": [
                        {
                            "scene_id": "scene_001",
                            "scene_index": 1,
                            "environmental_mood": "Classified Terminal Archive",
                            "tension_level": 2,
                            "estimated_duration_sec": 10.0,
                        },
                        {
                            "scene_id": "scene_002",
                            "scene_index": 2,
                            "environmental_mood": "Monster Breach Rampage",
                            "tension_level": 5,
                            "estimated_duration_sec": 10.0,
                        },
                    ],
                }
            ],
        }

        visual_plan = {
            "version": "2.0",
            "theme_lane": "scp_foundation",
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "palette": {"shadow": "#020406", "primary": "#0a1420", "accent": "#00ff66"},
                    "atmosphere": {"particle_layer": "dust_motes"},
                },
                {
                    "scene_id": "scene_002",
                    "palette": {"shadow": "#040100", "primary": "#1a0600", "accent": "#ff3300"},
                    "atmosphere": {"particle_layer": "ember_sparks"},
                },
            ],
        }

        manifest = planner.plan_manifest(
            script=script,
            visual_plan=visual_plan,
            story_id="test_adaptive_001",
            narration_path="audio/narration.mp3",
            actual_audio_duration=20.0,
        )

        assert manifest["story_id"] == "test_adaptive_001"
        assert len(manifest["scenes"]) == 2
        
        # Scene 1 should resolve to classified_terminal archetype
        sc1 = manifest["scenes"][0]
        assert sc1["engine_type"] == "pure_procedural_webgl"
        assert sc1["procedural_config"]["template_name"] == "archetype_classified_terminal.html"
        assert sc1["procedural_config"]["palette"]["accent"] == "#00ff66"

        # Scene 2 should resolve to anomaly_silhouette archetype
        sc2 = manifest["scenes"][1]
        assert sc2["engine_type"] == "pure_procedural_webgl"
        assert sc2["procedural_config"]["template_name"] == "archetype_anomaly_silhouette.html"
