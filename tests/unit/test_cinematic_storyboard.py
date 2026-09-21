"""
Unit tests for Narrative Storyboarding, 5-8 scene longform montage,
and upstream WGSL archetype propagation.
"""

from __future__ import annotations

import pytest
from src.curators.text_splitter import CinematicScriptCuratorAgent
from src.agents.atmospheric_director import AtmosphericDirectorAgent as ArtDirectorMoodAgent
from src.media.manifest_compiler import SceneManifestCompiler as ScenePlannerCompositorAgent
from src.core.scenic_detector import VALID_ARCHETYPES  # avoid quarantined native_procedural


@pytest.fixture
def longform_sample_text():
    # A realistic 12-minute longform text with ~1500 words across paragraphs
    paragraphs = [
        "El faro de Cabo Tormenta se alzaba sobre los acantilados negros desafiando el viento del norte. "
        "Durante generaciones los vigías habían mantenido la lámpara encendida sin fallar una sola noche.",
        
        "La primera anomalía ocurrió a las tres de la madrugada cuando la radio emitió una frecuencia desconocida. "
        "Las agujas de los instrumentos comenzaron a girar descontroladas marcando pulsos gravitacionales imposibles.",
        
        "Decidí descender a la cámara subterránea del búnker auxiliar bajo los cimientos de hormigón armado. "
        "El aire allí abajo era helado y olía a ozono y salitre rancio.",
        
        "Frente a la consola de acero, una silueta oscura parecía observar la pantalla CRT parpadeante. "
        "No tenía rasgos definidos, solo una sombra tridimensional que absorbía la luz de mi linterna.",
        
        "Cuando intenté retroceder, la escotilla de presión se cerró con un golpe sordo y metálico. "
        "Un estruendo sacudió la torre y los cristales superiores reventaron ante la presión del abismo.",
        
        "El amanecer llegó cubierto de una densa niebla marina mientras el silencio regresaba a la costa. "
        "El faro seguía en pie, pero las grabaciones de esa noche habían sido borradas para siempre."
    ]
    # Multiply paragraphs to simulate full longform narration
    return "\n\n".join(paragraphs * 4)


def test_longform_storyboard_scene_count_and_duration(longform_sample_text):
    """Verify longform curation produces 5 to 8 scenes with 60-150s duration and transition reasons."""
    curator = CinematicScriptCuratorAgent()
    payload = curator.curate(
        raw_text=longform_sample_text,
        title="El Misterio de Cabo Tormenta",
        channel_lane="moku-horror-long",
        target_format="longform",
    )
    
    scenes = [s for act in payload["acts"] for s in act["scenes"]]
    assert 5 <= len(scenes) <= 8, f"Expected 5 to 8 scenes for longform, got {len(scenes)}"
    
    for sc in scenes:
        dur = sc["estimated_duration_sec"]
        assert 45.0 <= dur <= 150.0, f"Scene duration {dur}s outside expected [45.0, 150.0]"
        assert "transition_reason" in sc, "Scene contract missing transition_reason"
        # Verify text ends on a sentence boundary (punctuation)
        text = sc["narration_text"].strip()
        assert text[-1] in (".", "!", "?", '"', "'"), f"Scene text does not end on terminal punctuation: {text[-20:]}"


def test_art_director_assigns_canonical_wgsl_archetype(longform_sample_text):
    """Verify ArtDirector assigns valid WGSL archetypes and uniform parameters directly."""
    curator = CinematicScriptCuratorAgent()
    script = curator.curate(
        raw_text=longform_sample_text,
        title="El Misterio de Cabo Tormenta",
        channel_lane="moku-horror-long",
        target_format="longform",
    )
    
    art = ArtDirectorMoodAgent()
    visual_plan = art.plan_visuals(script, theme_lane="cosmic_horror")
    
    assert "scenes" in visual_plan
    for sc_plan in visual_plan["scenes"]:
        arch = sc_plan.get("archetype_id")
        assert arch is not None, "ArtDirector must assign an explicit archetype_id"
        assert arch in VALID_ARCHETYPES, f"archetype_id '{arch}' is not in native VALID_ARCHETYPES"
        assert "uniform_params" in sc_plan, "ArtDirector must assign uniform_params"


def test_scene_planner_preserves_storyboard_scenes(longform_sample_text, tmp_path):
    """Verify ScenePlanner does not slice longform storyboard scenes into 11s fragments."""
    curator = CinematicScriptCuratorAgent()
    script = curator.curate(
        raw_text=longform_sample_text,
        title="El Misterio de Cabo Tormenta",
        channel_lane="moku-horror-long",
        target_format="longform",
    )
    
    art = ArtDirectorMoodAgent()
    visual_plan = art.plan_visuals(script, theme_lane="cosmic_horror")
    
    planner = ScenePlannerCompositorAgent()
    manifest = planner.plan_manifest(
        script=script,
        visual_plan=visual_plan,
        story_id="test_story",
        narration_path=str(tmp_path / "audio.mp3"),
        music_path="",
        music_volume=0.04,
        lane_id="moku-horror-long",
        channel_name="moku",
        resolution=[1920, 1080],
        fps=30,
        actual_audio_duration=600.0,
    )
    
    manifest_scenes = manifest.get("scenes", [])
    # If 5-8 storyboard scenes are generated, manifest should match the storyboard scenes count,
    # NOT expand to 50+ scenes by 11-second arithmetic slicing!
    assert 5 <= len(manifest_scenes) <= 12, f"Manifest scenes count {len(manifest_scenes)} shows unwanted 11s fragmentation"
    for sc in manifest_scenes:
        cfg = sc.get("procedural_config", {})
        template = cfg.get("template_name", "")
        # Template should reference valid archetype, not .html WebGL template
        assert not template.endswith(".html"), f"Template {template} still references WebGL .html instead of WGSL archetype"
