"""
tests/unit/test_narrative_scripting.py - Unit tests for SCP/Horror high-retention scripting.
"""
import pytest
from src.curators.moku_horror import MokuHorrorCurator
from src.agents.script_curator import CinematicScriptCuratorAgent
from src.narrative.engine import CosmicNarrativeEngine, segment_narration_into_scenes
from src.narrative.schema import VideoFormat, NarrativeArchetype


class TestMokuHorrorCurator:
    @pytest.fixture
    def curator(self):
        return MokuHorrorCurator()

    @pytest.mark.parametrize("topic", [
        "SCP-027",
        "SCP-001",
        "SCP-096",
        "SCP-1048",
        "SCP-049",
        "SCP-3008",
        "Incidente SCP-096-1-A",
        "Incidente Clef-Kondraki",
        "la criatura del sotano",
    ])
    def test_short_narrative_word_count_and_retention(self, curator, topic):
        script = curator.build_short_narrative(topic=topic)
        words = script.split()
        word_count = len(words)
        
        # Must strictly be within 180-320 words for 65-115s Short @ 165 WPM
        assert 180 <= word_count <= 320, f"Topic '{topic}' word count {word_count} out of [180, 320] bounds"
        
        # Must NOT contain disruptive channel outro CTAs that cause swipe drop-off
        assert "@moku" not in script.lower(), "Short script must not contain channel handle outro"
        assert "suscríbete" not in script.lower(), "Short script must not contain subscribe CTA"
        assert "deja tu like" not in script.lower(), "Short script must not contain like CTA"
        assert "bajo una universidad ordinaria" not in script.lower(), "Boilerplate intro must not be used"

    def test_seamless_loop_connectors(self, curator):
        for topic in ["SCP-027", "SCP-1048", "SCP-096"]:
            script = curator.build_short_narrative(topic=topic)
            # Must end with an open connector ending in '...' or matching a loop connector
            assert "..." in script or script.strip().endswith(":"), f"Script for '{topic}' must have open loop connector"


class TestCinematicScriptCuratorAgent:
    @pytest.fixture
    def agent(self):
        return CinematicScriptCuratorAgent()

    def test_curate_moku_scp_shorts(self, agent):
        raw_text = (
            "Imaginen un tierno oso de peluche que se pasea libre por la base haciéndose amigo de todos. "
            "Pero todo cambió cuando las cámaras descubrieron que estaba construyendo réplicas en secreto. "
            "Una noche encontraron a SCP-1048-A en la cafetería, una copia hecha enteramente con orejas humanas vivas. "
            "La entidad emitió un chillido ultrasónico que destruyó los tímpanos del escuadrón. "
            "El oso original sigue suelto en la ventilación, por eso si alguna vez visitas el Sitio..."
        )
        res = agent.curate(
            raw_text=raw_text,
            title="SCP-1048 The Builder Bear",
            channel_lane="moku-scp-shorts",
            target_format="short",
        )
        
        assert res["version"] == "2.0"
        assert res["metadata"]["channel_lane"] == "moku-scp-shorts"
        assert res["metadata"]["target_format"] == "short"
        assert len(res["acts"]) == 4
        
        # Check all scenes adhere to short duration bounds
        for act in res["acts"]:
            for sc in act["scenes"]:
                assert 5.0 <= sc["estimated_duration_sec"] <= 16.0


class TestCosmicNarrativeEngine:
    @pytest.fixture
    def engine(self):
        return CosmicNarrativeEngine()

    def test_generate_script_shorts_timing_and_sfx(self, engine):
        contract = engine.generate_script(
            topic="SCP-027 Infestacion",
            archetype=NarrativeArchetype.SPECULATIVE_BIOLOGICAL_DOSSIER,
            video_format=VideoFormat.SHORT_VERTICAL,
            duration_sec=45.0,
        )
        
        assert contract.format == VideoFormat.SHORT_VERTICAL
        assert len(contract.scenes) >= 3
        assert contract.audio.sfx_timeline is not None
        assert len(contract.audio.sfx_timeline) >= 2
        assert contract.loop_continuity_phrase is not None
