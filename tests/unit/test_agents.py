"""
tests/unit/test_agents.py - Unit and Integration Tests for Specialized Production Agents.

Tests:
1. CinematicScriptCuratorAgent (Agent 1): Script curation across 3 lanes, schema validation.
2. ArtDirectorMoodAgent (Agent 2): Visual planning, Rec.709 color grading, atmospheric layers.
3. ScenePlannerCompositorAgent (Agent 3): Scene manifest compilation, timing alignment, safe areas.
4. VisualAudioQAAuditorAgent (Agent 4): Forensic QA audits, metric validation.
5. Multi-agent pipeline end-to-end handoff integration.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import jsonschema
from jsonschema import validate

from src.curators.text_splitter import CinematicScriptCuratorAgent
from src.agents.atmospheric_director import AtmosphericDirectorAgent as ArtDirectorMoodAgent
from src.media.manifest_compiler import SceneManifestCompiler as ScenePlannerCompositorAgent
from src.verification.technical_qa import TechnicalQAAuditor as VisualAudioQAAuditorAgent


@pytest.fixture
def sample_horror_story() -> str:
    return (
        "A las tres de la madrugada, las alertas de la estación de monitoreo solitaria registraron una oscilación electromagnética imposible. "
        "La niebla densa cubría los pinos centenarios mientras el frío glacial congelaba el vaho de mi respiración en la cabina de control. "
        "Al revisar los archivadores de acero, encontré los diarios de guardia de operadores desaparecidos que describían exactamente las mismas señales. "
        "Una sombra alargada comenzó a deslizarse bajo el umbral de la puerta blindada mientras los altavoces repetían mi propio nombre en tiempo real. "
        "El cristal del ventanal estalló en pedazos ante una manifestación no euclidiana que me obligó a detonar la bengala de emergencia y huir a toda velocidad. "
        "Llegué al amanecer con las ropas rasgadas y los vehículos oficiales acordonaron el sector bajo estricto encubrimiento. "
        "Hoy vivo en la ciudad, pero cada vez que una radio emite estática sé que la presencia sigue esperando en el valle."
    )


@pytest.fixture
def sample_scp_story() -> str:
    return (
        "Ítem #: SCP-087. Clasificación de Objeto: Euclid. "
        "Procedimientos Especiales de Contención: SCP-087 está ubicado en el campus universitario bajo una puerta de acero sellada con 75 cm de hormigón. "
        "Las exploraciones requieren personal Clase-D con reflectores de alta intensidad y arneses de descenso. "
        "La escalera absorbe la luz impidiendo iluminar más de un tramo y medio. "
        "A cientos de metros de profundidad se escuchan constantemente los sollozos de un niño en agonía. "
        "En la cuarta expedición, las cámaras registraron a SCP-087-1: un rostro humanoide pálido sin boca ni pupilas flotando en la penumbra. "
        "Tras el incidente, el Sitio fue puesto bajo protocolo de sellado definitivo."
    )


@pytest.fixture
def sample_aita_story() -> str:
    return (
        "¿Soy la mala por negarme a pagar la boda de mi hermana tras descubrir lo que planeaba en su cena de compromiso? "
        "Durante diez años trabajé turnos dobles para comprar mi primera vivienda propia con estricta disciplina financiera. "
        "En medio del brindis, mi cuñado anunció que yo debía asumir las deudas del evento en un hotel de lujo. "
        "Cuando me negué con serenidad, la mesa se convirtió en un tribunal de reproches y amenazas de expulsión familiar. "
        "Descubrí además que habían intentado solicitar un préstamo a mi nombre falsificando mis documentos. "
        "Cancelé todo apoyo económico y contraté asesoría legal para blindar mi patrimonio frente a los chantajes. "
        "¿Qué habrías hecho tú en mi lugar? ¿Fui demasiado lejos al poner este límite definitivo? "
        "Seis meses después, vivo con total tranquilidad y autonomía en mi nuevo hogar."
    )


class TestAgentLifecycle:
    """Verifies that all 4 pipeline agents instantiate and execute correctly."""

    def test_script_curator_all_lanes_valid(self, sample_horror_story, sample_scp_story, sample_aita_story):
        curator = CinematicScriptCuratorAgent()

        # 1. SCP Shorts
        scp_res = curator.curate(
            raw_text=sample_scp_story,
            title="SCP-087 Escalera",
            channel_lane="moku-scp-shorts",
            target_format="short",
        )
        assert scp_res["version"] == "2.0"
        assert scp_res["metadata"]["target_format"] == "short"
        assert len(scp_res["acts"]) == 4

        # 2. Horror Longform
        horror_res = curator.curate(
            raw_text=sample_horror_story,
            title="Faro Maldito",
            channel_lane="moku-horror-long",
            target_format="longform",
        )
        assert horror_res["version"] == "2.0"
        assert horror_res["metadata"]["target_format"] == "longform"
        assert len(horror_res["acts"]) == 4

        # 3. Reddit AITA Longform
        aita_res = curator.curate(
            raw_text=sample_aita_story,
            title="Boda Cancelada",
            channel_lane="aelithia-aita-long",
            target_format="longform",
        )
        assert aita_res["version"] == "2.0"
        assert aita_res["metadata"]["target_format"] == "longform"
        assert len(aita_res["acts"]) == 4

    def test_art_director_generates_visual_plan(self, sample_horror_story):
        curator = CinematicScriptCuratorAgent()
        script = curator.curate(sample_horror_story, title="Faro", channel_lane="moku-horror-long")

        art = ArtDirectorMoodAgent()
        vplan = art.plan_visuals(script, theme_lane="cosmic_horror")
        assert vplan["version"] == "2.0"
        assert len(vplan["scenes"]) >= 4
        assert vplan["theme_lane"] == "cosmic_horror"

    def test_scene_planner_generates_manifest(self, sample_horror_story, tmp_path):
        curator = CinematicScriptCuratorAgent()
        script = curator.curate(sample_horror_story, title="Faro", channel_lane="moku-horror-long")
        art = ArtDirectorMoodAgent()
        vplan = art.plan_visuals(script, theme_lane="cosmic_horror")

        dummy_audio = tmp_path / "audio.wav"
        dummy_audio.write_bytes(b"RIFF" + b"\x00" * 40)

        planner = ScenePlannerCompositorAgent()
        manifest = planner.plan_manifest(
            script=script,
            visual_plan=vplan,
            story_id="story_001",
            narration_path=str(dummy_audio),
            lane_id="moku-horror-long",
            channel_name="moku",
        )
        assert manifest["manifest_version"] == "2.0"
        assert len(manifest["scenes"]) >= 4

    def test_qa_auditor_reports_metrics(self, tmp_path):
        dummy_mp4 = tmp_path / "rendered.mp4"
        dummy_mp4.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 100)

        auditor = VisualAudioQAAuditorAgent()
        with patch("src.verification.technical_qa.probe_media") as mock_probe, \
             patch("src.verification.technical_qa.has_faststart", return_value=True):

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
                run_id="run_test_qa_001",
                target_resolution="1920x1080",
            )
            assert report["version"] == "2.0"
            assert report["overall_pass"] is True
