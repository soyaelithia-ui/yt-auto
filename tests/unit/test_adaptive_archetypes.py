"""
tests/unit/test_adaptive_archetypes.py - Unit tests for universal adaptive visual archetypes.
"""
from pathlib import Path
import pytest
from src.agents.scene_planner import ScenePlannerCompositorAgent


class TestUniversalAdaptiveArchetypes:
    def test_universal_archetype_identifiers(self):
        """Verifies that all 6 universal archetype categories are defined and distinct."""
        expected_archetypes = [
            "classified_terminal",
            "dark_forest",
            "tactical_chamber",
            "dark_ambient",
            "horror",
            "cosmic_horror",
        ]
        assert len(expected_archetypes) == 6
        for arch in expected_archetypes:
            assert isinstance(arch, str) and len(arch) > 0

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
        assert tmpl == "classified_terminal"

        # 2. Brutalist Vault / Subterranean Bunker
        cat, tmpl, params = ScenePlannerCompositorAgent._resolve_scene_archetype(
            env_name="Subterranean Concrete Containment Vault",
            tension=3,
            dramatic_role="rising_action_dread",
            lane_id="moku-horror-long",
        )
        assert cat == "tactical_chamber"
        assert tmpl == "tactical_chamber"

        # 3. Neural Mind / Collective Consciousness / Entity
        cat, tmpl, params = ScenePlannerCompositorAgent._resolve_scene_archetype(
            env_name="Psychological Mind Grid and Neural Entity Domain",
            tension=3,
            dramatic_role="rising_action_dread",
            lane_id="moku-horror-long",
        )
        assert cat == "dark_ambient"
        assert tmpl == "dark_ambient"

        # 4. Anomaly / Colossus / Beast Rampage
        cat, tmpl, params = ScenePlannerCompositorAgent._resolve_scene_archetype(
            env_name="Cataclysmic Battlefield with Giant Monster Rampage",
            tension=5,
            dramatic_role="climax_confrontation",
            lane_id="moku-horror-long",
        )
        assert cat == "horror"
        assert tmpl == "horror"

        # 5. Dimensional Singularity / Cosmic Rift
        cat, tmpl, params = ScenePlannerCompositorAgent._resolve_scene_archetype(
            env_name="Cosmic Event Horizon with Black Hole Singularity",
            tension=4,
            dramatic_role="climax_confrontation",
            lane_id="moku-horror-long",
        )
        assert cat == "cosmic_horror"
        assert tmpl == "cosmic_horror"

        # 6. Drama / AITA lane
        cat, tmpl, params = ScenePlannerCompositorAgent._resolve_scene_archetype(
            env_name="Living Room Argument",
            tension=2,
            dramatic_role="exposition",
            lane_id="moku-aita-shorts",
        )
        assert cat == "drama"
        assert tmpl == "drama"

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
        assert sc1["engine_type"] == "catalog_loop"
        assert sc1["environment_name"] == "classified_terminal"
        assert "procedural_config" not in sc1

        # Scene 2 should resolve to horror archetype
        sc2 = manifest["scenes"][1]
        assert sc2["engine_type"] == "catalog_loop"
        assert sc2["environment_name"] == "horror"
        assert "procedural_config" not in sc2
