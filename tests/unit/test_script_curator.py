"""
tests/unit/test_script_curator.py - Unit tests for CinematicScriptCuratorAgent (Agent 1).

Covers all 3 thematic curation lanes:
1. SCP Shorts (horror-scp-shorts) - 60-180s total, 8-15s per scene, 4 acts, clinical 0-3s hook.
2. Horror Longform (horror-horror-long) - >=600s total, 45-90s per scene, 4 acts, 1-5 progressive tension curve, audio pacing cues.
3. Reddit AITA Longform (drama-aita-long) - >=600s total, 45-90s per scene, 4 acts, moral dilemma hook, reflection question & update.
4. Schema validation with Draft-07 validator against schemas/script_curator.schema.json.
5. Sentence-aware boundary slicing, abbreviation protection, and fallback engine.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
import jsonschema
from jsonschema import Draft7Validator, validate, ValidationError

from src.curators.text_splitter import (
    CinematicScriptCuratorAgent,
    LANE_CURATION_CONFIGS,
    VALID_AUDIO_PACING_CUES,
)

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "script_curator.schema.json"


@pytest.fixture(scope="module")
def curator_schema() -> dict:
    assert SCHEMA_PATH.is_file(), f"Schema file not found at {SCHEMA_PATH}"
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def agent() -> CinematicScriptCuratorAgent:
    return CinematicScriptCuratorAgent()


@pytest.fixture
def sample_scp_text() -> str:
    return (
        "Ítem #: SCP-173. Clasificación de Objeto: Euclid. "
        "Procedimientos Especiales de Contención: El ítem debe permanecer encerrado en un contenedor sellado de hormigón reforzado en todo momento. "
        "Cuando el personal deba ingresar al contenedor de SCP-173, no menos de tres personas pueden entrar a la vez y la puerta debe cerrarse tras ellos. "
        "Dos personas deben mantener contacto visual constante con SCP-173 hasta que todos hayan salido y el contenedor esté asegurado. "
        "Descripción: Trasladado al Sitio-19 en 1993. Origen desconocido. Está construido de hormigón y varillas de refuerzo con pintura Krylon. "
        "Es animado y extremadamente hostil. El objeto no puede moverse mientras esté dentro de una línea de visión directa. "
        "El contacto visual no debe romperse en ningún momento con SCP-173. El personal debe alertar antes de pestañear. "
        "Se reporta que el ataque se realiza rompiendo el cuello desde la base del cráneo. "
        "El personal reporta el sonido de raspado de piedra cuando nadie está presente en la celda."
    )


@pytest.fixture
def sample_horror_text() -> str:
    return (
        "A las tres de la madrugada, las alertas de la estación de monitoreo solitaria registraron una oscilación electromagnética imposible. "
        "La niebla densa cubría los pinos centenarios mientras el frío glacial congelaba el vaho de mi respiración en la cabina de control. "
        "El zumbido en los receptores de radio analógicos aumentó de intensidad, modulando una frecuencia que no pertenecía a ninguna estación civil ni militar. "
        "Al revisar los archivadores de acero, encontré los diarios de guardia de operadores desaparecidos que describían exactamente las mismas señales y advertían no responder a la radio. "
        "La caligrafía de Miller en 1989 advertía que cuando la frecuencia imitaba tu propia voz, la entidad ya se encontraba dentro del perímetro de seguridad. "
        "Una sombra alargada comenzó a deslizarse bajo el umbral de la puerta blindada mientras los altavoces repetían mi propio nombre en tiempo real. "
        "El pomo de la puerta de acero comenzó a descender lentamente con una fuerza fría y calculada. "
        "El cristal del ventanal estalló en pedazos ante una manifestación no euclidiana que me obligó a detonar la bengala de emergencia y huir a toda velocidad por el sendero forestal. "
        "El fulgor rojo cegador del fósforo iluminó una silueta colosal que retrocedió hacia la penumbra del bosque. "
        "Llegué al puesto de guardia de la autopista con las primeras luces del amanecer, con las ropas rasgadas y las manos entumecidas por el frío. "
        "Las autoridades forestales acordonaron la zona bajo el pretexto de un rayo globular, pero confiscaron todas mis cintas de grabación y mi bitácora personal. "
        "Hoy vivo en la ciudad, pero cada vez que una radio emite estática sé que la presencia sigue esperando en el valle y que la conexión jamás se rompió."
    )


@pytest.fixture
def sample_aita_text() -> str:
    return (
        "¿Soy la mala por negarme a entregar los ahorros de toda mi vida a mi hermana tras descubrir lo que planeaba en su fiesta de compromiso? "
        "Durante diez años trabajé turnos dobles como enfermera para comprar mi primera vivienda propia, viviendo con extrema frugalidad. "
        "Mi hermana y su prometido, en cambio, siempre vivieron por encima de sus posibilidades con préstamos y tarjetas de crédito al límite. "
        "Durante una cena familiar, mi madre anunció ante todos los invitados que yo pagaría la fiesta de bodas en un hotel de lujo como mi regalo fraternal. "
        "Cuando respondí con calma: 'No puedo costear una fiesta ajena mientras estoy comprando mi casa', la mesa se convirtió en un campo de batalla. "
        "Mi hermana comenzó a llorar acusándome de arruinar su gran día, y mi madre me gritó: '¡La familia siempre se sacrifica por la familia!'. "
        "Durante las tres semanas siguientes, recibí decenas de llamadas y mensajes de parientes lejanos acusándome de egoísta y amenazando con expulsarme de las fiestas. "
        "Descubrí además que mi hermana había intentado consultar a un gestor financiero con mis datos personales para solicitar un adelanto a mi nombre. "
        "Fui directamente a su casa, cancelé cualquier comunicación y les advertí que si volvían a usar mis documentos presentaría una denuncia formal por fraude. "
        "La boda finalmente se redujo a una ceremonia modesta y desde entonces mis padres se niegan a dirigirme la palabra. "
        "¿Qué habrías hecho tú en mi lugar? ¿Fui demasiado lejos al poner este límite definitivo? "
        "Seis meses después, firmé las escrituras de mi nuevo departamento y disfruto de una paz mental que ningún chantaje familiar podrá arrebatarme."
    )


# ============================================================================
# 1. SCP SHORTS TESTS (horror-scp-shorts)
# ============================================================================

class TestSCPShortsCuration:
    """Tests for SCP Shorts formula: 60-180s, 8-15s/scene, 4 acts, clinical hook."""

    def test_scp_shorts_schema_validation(self, agent, curator_schema, sample_scp_text):
        script = agent.curate(
            raw_text=sample_scp_text,
            title="SCP-173 La Escultura",
            channel_lane="horror-scp-shorts",
            target_format="short",
        )
        Draft7Validator.check_schema(curator_schema)
        validate(instance=script, schema=curator_schema)
        assert script["version"] == "2.0"
        assert script["metadata"]["channel_lane"] == "horror-scp-shorts"
        assert script["metadata"]["target_format"] == "short"

    def test_scp_shorts_timing_and_scene_duration_bounds(self, agent, sample_scp_text):
        script = agent.curate(
            raw_text=sample_scp_text,
            title="SCP-173 La Escultura",
            channel_lane="horror-scp-shorts",
            target_format="short",
        )
        total_dur = script["metadata"]["estimated_duration_sec"]
        assert 60.0 <= total_dur <= 180.0, f"Total duration {total_dur} out of bounds [60, 180]"

        all_scenes = [sc for act in script["acts"] for sc in act["scenes"]]
        assert 4 <= len(all_scenes) <= 12, f"Scene count {len(all_scenes)} out of bounds [4, 12]"

        for sc in all_scenes:
            dur = sc["estimated_duration_sec"]
            assert 8.0 <= dur <= 15.0, f"Scene {sc['scene_id']} duration {dur} out of bounds [8.0, 15.0]"
            assert sc["audio_pacing_cue"] in VALID_AUDIO_PACING_CUES
            assert 1 <= sc["tension_level"] <= 5
            assert len(sc["narration_text"].strip()) > 0
            assert sc["word_count"] >= 1

    def test_scp_shorts_four_acts_and_dramatic_roles(self, agent, sample_scp_text):
        script = agent.curate(
            raw_text=sample_scp_text,
            title="SCP-173 La Escultura",
            channel_lane="horror-scp-shorts",
            target_format="short",
        )
        assert len(script["acts"]) == 4
        expected_roles = [
            "exposition_inception",
            "rising_action_dread",
            "climax_confrontation",
            "aftermath_revelation",
        ]
        actual_roles = [act["dramatic_role"] for act in script["acts"]]
        assert actual_roles == expected_roles

        # Verify sequential act numbering
        for i, act in enumerate(script["acts"], start=1):
            assert act["act_number"] == i
            assert len(act["scenes"]) >= 1

    def test_scp_shorts_hook_and_pacing_cues(self, agent, sample_scp_text):
        script = agent.curate(
            raw_text=sample_scp_text,
            title="SCP-173 La Escultura",
            channel_lane="horror-scp-shorts",
            target_format="short",
        )
        hook = script["metadata"]["hook_summary"]
        assert "SCP" in hook or "clasificado" in hook.lower()

        # Act 4 should include whispered_grave or calm_slow
        act4_cues = [sc["audio_pacing_cue"] for sc in script["acts"][3]["scenes"]]
        assert any(cue in ("whispered_grave", "steady_dramatic", "calm_slow") for cue in act4_cues)


# ============================================================================
# 2. HORROR LONGFORM TESTS (horror-horror-long)
# ============================================================================

class TestHorrorLongformCuration:
    """Tests for Horror Longform formula: >=600s, 45-90s/scene, 4 acts, 1-5 tension."""

    def test_horror_longform_schema_validation(self, agent, curator_schema, sample_horror_text):
        script = agent.curate(
            raw_text=sample_horror_text,
            title="La Frecuencia Prohibida",
            channel_lane="horror-horror-long",
            target_format="longform",
        )
        validate(instance=script, schema=curator_schema)
        assert script["version"] == "2.0"
        assert script["metadata"]["channel_lane"] == "horror-horror-long"
        assert script["metadata"]["target_format"] == "longform"

    def test_horror_longform_duration_and_scene_bounds(self, agent, sample_horror_text):
        script = agent.curate(
            raw_text=sample_horror_text,
            title="La Frecuencia Prohibida",
            channel_lane="horror-horror-long",
            target_format="longform",
        )
        total_dur = script["metadata"]["estimated_duration_sec"]
        assert total_dur >= 600.0, f"Total duration {total_dur} must be >= 600s"

        all_scenes = [sc for act in script["acts"] for sc in act["scenes"]]
        assert 5 <= len(all_scenes) <= 24, f"Scene count {len(all_scenes)} out of bounds [5, 24]"

        for sc in all_scenes:
            dur = sc["estimated_duration_sec"]
            assert 45.0 <= dur <= 150.0, f"Scene {sc['scene_id']} duration {dur} out of bounds [45.0, 150.0]"
            assert sc["audio_pacing_cue"] in VALID_AUDIO_PACING_CUES
            assert 1 <= sc["tension_level"] <= 5

    def test_horror_longform_progressive_tension_curve(self, agent, sample_horror_text):
        script = agent.curate(
            raw_text=sample_horror_text,
            title="La Frecuencia Prohibida",
            channel_lane="horror-horror-long",
            target_format="longform",
        )
        tension_curve = script["metadata"]["tension_curve"]
        assert len(tension_curve) >= 5

        # Curve should start low (1-2), peak at 5 in Act 3, and descend in Act 4 (<=3)
        assert tension_curve[0] in (1, 2)
        assert max(tension_curve) == 5

        # Check peak in Act 3
        act3_tensions = [sc["tension_level"] for sc in script["acts"][2]["scenes"]]
        assert 5 in act3_tensions

        # Check resolution in Act 4
        act4_tensions = [sc["tension_level"] for sc in script["acts"][3]["scenes"]]
        assert all(t <= 3 for t in act4_tensions)

    def test_horror_longform_whispered_grave_in_epilogue(self, agent, sample_horror_text):
        script = agent.curate(
            raw_text=sample_horror_text,
            title="La Frecuencia Prohibida",
            channel_lane="horror-horror-long",
            target_format="longform",
        )
        act4_scenes = script["acts"][3]["scenes"]
        cues = [sc["audio_pacing_cue"] for sc in act4_scenes]
        assert "whispered_grave" in cues


# ============================================================================
# 3. REDDIT AITA LONGFORM TESTS (drama-aita-long)
# ============================================================================

class TestRedditAITALongformCuration:
    """Tests for Reddit AITA Longform formula: >=600s, 45-90s/scene, moral dilemma hook."""

    def test_aita_longform_schema_validation(self, agent, curator_schema, sample_aita_text):
        script = agent.curate(
            raw_text=sample_aita_text,
            title="Conflicto de Herencia Familiar",
            channel_lane="drama-aita-long",
            target_format="longform",
        )
        validate(instance=script, schema=curator_schema)
        assert script["version"] == "2.0"
        assert script["metadata"]["channel_lane"] == "drama-aita-long"
        assert script["metadata"]["target_format"] == "longform"

    def test_aita_longform_duration_and_scenes(self, agent, sample_aita_text):
        script = agent.curate(
            raw_text=sample_aita_text,
            title="Conflicto de Herencia Familiar",
            channel_lane="drama-aita-long",
            target_format="longform",
        )
        total_dur = script["metadata"]["estimated_duration_sec"]
        assert total_dur >= 600.0

        all_scenes = [sc for act in script["acts"] for sc in act["scenes"]]
        assert 5 <= len(all_scenes) <= 24

        for sc in all_scenes:
            dur = sc["estimated_duration_sec"]
            assert 45.0 <= dur <= 150.0
            assert sc["audio_pacing_cue"] in VALID_AUDIO_PACING_CUES
            assert 1 <= sc["tension_level"] <= 5

    def test_aita_longform_moral_dilemma_hook_and_four_acts(self, agent, sample_aita_text):
        script = agent.curate(
            raw_text=sample_aita_text,
            title="Conflicto de Herencia Familiar",
            channel_lane="drama-aita-long",
            target_format="longform",
        )
        hook = script["metadata"]["hook_summary"]
        assert "moral" in hook.lower() or "dilema" in hook.lower() or "mala" in hook.lower()

        assert len(script["acts"]) == 4
        assert script["acts"][0]["dramatic_role"] == "exposition_inception"
        assert script["acts"][1]["dramatic_role"] == "rising_action_dread"
        assert script["acts"][2]["dramatic_role"] == "climax_confrontation"
        assert script["acts"][3]["dramatic_role"] == "aftermath_revelation"


# ============================================================================
# 4. SENTENCE SLICING & ABBREVIATION PROTECTION TESTS
# ============================================================================

class TestSentenceAwareSlicing:
    """Tests sentence boundary splitting and abbreviation protection."""

    def test_abbreviations_not_split(self, agent):
        text = (
            "El Dr. Miller y la Dra. Gómez visitaron la celda de SCP-173 a las 3:00 a.m. "
            "El personal de Clase-D ingresó al Nivel 4 con el protocolo núm. 12. "
            "La criatura se movió a 3.5 metros por segundo."
        )
        sentences = agent._split_into_sentences(text)
        assert len(sentences) == 3
        assert "Dr. Miller" in sentences[0]
        assert "SCP-173" in sentences[0]
        assert "Clase-D" in sentences[1]
        assert "Nivel 4" in sentences[1]
        assert "3.5 metros" in sentences[2]

    def test_scene_slicing_respects_scene_bounds(self, agent):
        text = (
            "Primera oración completa del relato de prueba. "
            "Segunda oración que aporta más contexto y ambientación. "
            "Tercera oración con tensión creciente en el laboratorio. "
            "Cuarta oración donde ocurre la manifestación anómala. "
            "Quinta oración con el desenlace y protocolo de cierre."
        )
        scenes = agent._slice_into_scenes(
            clean_text=text,
            target_scene_dur=10.0,
            min_scene_dur=8.0,
            max_scene_dur=15.0,
            wpm=160.0,
            min_scenes=4,
            max_scenes=12,
            target_format="short",
        )
        assert len(scenes) >= 4


# ============================================================================
# 5. DETERMINISTIC FALLBACK & ZERO-QUOTA SYNTHESIS TESTS
# ============================================================================

class TestDeterministicFallback:
    """Tests fallback generation when input text is empty or minimal."""

    @pytest.mark.parametrize(
        "lane_id,target_fmt,min_dur,max_dur",
        [
            ("horror-scp-shorts", "short", 60.0, 180.0),
            ("horror-horror-long", "longform", 600.0, 1800.0),
            ("drama-aita-long", "longform", 600.0, 1800.0),
        ],
    )
    def test_empty_raw_text_produces_valid_script(
        self, agent, curator_schema, lane_id, target_fmt, min_dur, max_dur
    ):
        script = agent.curate(
            raw_text="",
            title="Historia Autogenerada",
            channel_lane=lane_id,
            target_format=target_fmt,
        )
        validate(instance=script, schema=curator_schema)
        assert len(script["acts"]) == 4
        dur = script["metadata"]["estimated_duration_sec"]
        assert min_dur <= dur <= max_dur

    def test_canonical_scp_lore_lookup_integration(self, agent, curator_schema):
        script = agent.curate(
            raw_text="",
            title="SCP-087",
            channel_lane="horror-scp-shorts",
            target_format="short",
        )
        validate(instance=script, schema=curator_schema)
        all_text = " ".join(sc["narration_text"] for act in script["acts"] for sc in act["scenes"])
        assert "087" in all_text or "escalera" in all_text.lower()


# ============================================================================
# 6. CANONICAL THEMATIC LANES & DECOMPOSED MODULES TESTS
# ============================================================================

class TestCanonicalThematicLanesAndDecomposition:
    """Tests canonical thematic lane resolution and modular curator components."""

    @pytest.mark.parametrize(
        "canonical_lane,expected_channel,expected_fmt",
        [
            ("horror-scp-shorts", "horror", "short"),
            ("horror-horror-long", "horror", "longform"),
            ("drama-drama-shorts", "drama", "short"),
            ("drama-aita-long", "drama", "longform"),
            ("scifi-singularity-shorts", "scifi", "short"),
            ("scifi-singularity-long", "scifi", "longform"),
        ],
    )
    def test_canonical_lane_profiles_exist_and_validate(
        self, agent, curator_schema, canonical_lane, expected_channel, expected_fmt
    ):
        from src.curators.curation_profiles import resolve_lane_config, LANE_CURATION_CONFIGS
        assert canonical_lane in LANE_CURATION_CONFIGS
        resolved_key, cfg = resolve_lane_config(canonical_lane, expected_fmt)
        assert cfg["channel"] == expected_channel
        assert cfg["target_format"] == expected_fmt

        script = agent.curate(
            raw_text="",
            title=f"Test {canonical_lane}",
            channel_lane=canonical_lane,
            target_format=expected_fmt,
        )
        validate(instance=script, schema=curator_schema)
        assert len(script["acts"]) == 4

    def test_abbreviation_splitting_expanded(self):
        from src.curators.segmentation import split_into_sentences
        text = (
            "El Sr. López y el Dr. Jones examinaron el ítem SCP-096. "
            "P.D. Se notificó al Cap. Ramírez a las 4:30 p.m. "
            "La anomalía reaccionó de inmediato."
        )
        sentences = split_into_sentences(text)
        assert len(sentences) == 3
        assert "Sr. López" in sentences[0]
        assert "Dr. Jones" in sentences[0]
        assert "SCP-096" in sentences[0]
        assert "P.D." in sentences[1]
        assert "Cap. Ramírez" in sentences[1]

    def test_progressive_tension_and_pacing_resolution(self):
        from src.curators.tension import interpolate_tension, resolve_audio_pacing_cue
        # 4 scenes in act with [1, 2] profile
        tensions = [interpolate_tension([1, 2], i, 4) for i in range(4)]
        assert tensions[0] == 1
        assert tensions[-1] == 2
        for t in tensions:
            assert 1 <= t <= 5

        # Peak act tension
        peak_tension = interpolate_tension([5], 0, 1)
        assert peak_tension == 5

        # Pacing cue
        cue_climax = resolve_audio_pacing_cue("horror-scp-shorts", act_num=3, tension=5, offset=0, total_in_act=1)
        assert cue_climax == "intense_urgent"

        cue_epilogue = resolve_audio_pacing_cue("horror-scp-shorts", act_num=4, tension=2, offset=0, total_in_act=1)
        assert cue_epilogue in ("whispered_grave", "calm_slow")

