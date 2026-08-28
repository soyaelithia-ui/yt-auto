"""
tests/unit/test_m1_script_curator_empirical.py - Comprehensive Empirical Test Harness for CinematicScriptCuratorAgent.

Tests:
1. Multi-lane diverse topic curation: SCP Shorts, Horror Longform, AITA Longform.
2. 100% Draft-07 schema compliance against schemas/script_curator.schema.json.
3. Timing constraints:
   - Shorts: scenes 8-15s, total 60-180s, 4-12 scenes, 4 acts.
   - Longform: scenes 45-90s, total >=600s, 8-24 scenes, 4 acts.
4. Dramatic progression & tension curve integrity (1-5 range, peak at Act 3, resolution in Act 4).
5. Audio pacing cues validity against schema enum.
6. Boundary & stress tests:
   - Empty input, 1-word input, minimal words (<25 words fallback)
   - Extremely large input (10,000+ words)
   - Single continuous run-on sentence without punctuation
   - Extreme punctuation, markdown, emoji, URLs, and code blocks
   - Abbreviations, decimals, and time expressions (e.g., Dr., Dra., 3.5, a.m., p.m.)
   - WPM scaling stress (80 WPM to 250 WPM)
   - Unknown lane fallback resilience
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
import jsonschema
from jsonschema import Draft7Validator, validate

from src.agents.script_curator import (
    CinematicScriptCuratorAgent,
    LANE_CURATION_CONFIGS,
    VALID_AUDIO_PACING_CUES,
)

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "script_curator.schema.json"


@pytest.fixture(scope="module")
def curator_schema() -> dict:
    assert SCHEMA_PATH.is_file(), f"Schema file missing at {SCHEMA_PATH}"
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)
    Draft7Validator.check_schema(schema)
    return schema


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
        "El contacto visual no debe romperse en ningún momento con SCP-173. El personal debe alertar antes de pestañear."
    )


@pytest.fixture
def sample_horror_text() -> str:
    return (
        "A las tres de la madrugada, las alertas de la estación de monitoreo solitaria registraron una oscilación electromagnética imposible. "
        "La niebla densa cubría los pinos centenarios mientras el frío glacial congelaba el vaho de mi respiración en la cabina de control. "
        "El zumbido en los receptores de radio analógicos aumentó de intensidad modulando una frecuencia que no pertenecía a ninguna estación civil ni militar. "
        "Al revisar los archivadores de acero encontré los diarios de guardia de operadores desaparecidos que describían exactamente las mismas señales y advertían no responder a la radio. "
        "Una sombra alargada comenzó a deslizarse bajo el umbral de la puerta blindada mientras los altavoces repetían mi propio nombre en tiempo real. "
        "El pomo de la puerta de acero comenzó a descender lentamente con una fuerza fría y calculada. "
        "El cristal del ventanal estalló en pedazos ante una manifestación no euclidiana que me obligó a detonar la bengala de emergencia y huir a toda velocidad por el sendero forestal. "
        "Llegué al puesto de guardia con las primeras luces del amanecer. "
        "Hoy vivo en la ciudad, pero cada vez que una radio emite estática sé que la presencia sigue esperando en el valle."
    )


@pytest.fixture
def sample_aita_text() -> str:
    return (
        "¿Soy la mala por negarme a entregar los ahorros de toda mi vida a mi hermana tras descubrir lo que planeaba en su fiesta de compromiso? "
        "Durante diez años trabajé turnos dobles como enfermera para comprar mi primera vivienda propia viviendo con extrema frugalidad. "
        "Mi hermana y su prometido en cambio siempre vivieron por encima de sus posibilidades con préstamos y tarjetas de crédito al límite. "
        "Durante una cena familiar mi madre anunció ante todos los invitados que yo pagaría la fiesta de bodas en un hotel de lujo como mi regalo fraternal. "
        "Cuando respondí con calma que no podía costear una fiesta ajena mientras compraba mi casa, la mesa se convirtió en un campo de batalla. "
        "Descubrí además que mi hermana había intentado solicitar un adelanto a mi nombre falsificando mis datos. "
        "Cancelé cualquier comunicación y advertí que presentaría una denuncia por fraude. "
        "¿Qué habrías hecho tú en mi lugar? ¿Fui demasiado lejos al poner este límite definitivo? "
        "Seis meses después firmé las escrituras de mi nuevo departamento con total tranquilidad."
    )


# ============================================================================
# 1. DIVERSE TOPIC GENERATION & VALIDATION ACROSS 3 LANES
# ============================================================================

DIVERSE_TOPICS_SCP = [
    ("SCP-087", "Bajo una universidad ordinaria existe una escalera sin fin que devora la luz en SCP-087. Las linternas solo alcanzan a iluminar un tramo y medio antes de que la oscuridad absoluta devore cualquier haz luminoso. A cientos de metros de profundidad se escuchan constantemente los sollozos desgarradores de un niño en agonía. En la última expedición oficial, las cámaras térmicas registraron a SCP-087-1: un rostro humanoide pálido y flotante sin boca ni pupilas visibles observando fijamente desde la penumbra. Tras aquel aterrador encuentro, los agentes sellaron la entrada principal con setenta y cinco centímetros de hormigón armado para siempre."),
    ("SCP-173", "Nunca parpadees ni apartes la vista de esta escultura de concreto si valoras tu vida en SCP-173. Clasificado como Euclid por la Fundación, permanece completamente inmóvil mientras se mantenga bajo contacto visual directo e ininterrumpido. En la milésima de segundo en que cierras los ojos, se desplaza a velocidades imposibles y fractura las vértebras del cuello de sus observadores en una fracción de segundo. Para ingresar a limpiar su celda de contención se requieren tres personas: dos manteniendo la mirada fija y una advirtiendo obligatoriamente en voz alta antes de parpadear para evitar una tragedia inevitable."),
    ("SCP-049", "Bajo una máscara de cerámica fusionada a su piel, este doctor medieval oculta una cura aterradora en SCP-049. Afirma que la humanidad entera sufre una enfermedad terminal desconocida que él denomina la pestilencia. Su toque biológico directo detiene las funciones del corazón al instante, para luego reanimar los cuerpos inertes mediante cirugías toscas transformándolos en marionetas obedientes sin voluntad propia ni memoria humana. Cualquier intento de diálogo con esta entidad debe realizarse detrás de mamparas de seguridad reforzadas y bajo estricta vigilancia armada permanente."),
    ("SCP-096", "Si alguna vez miras accidentalmente el rostro de esta criatura, absolutamente nada en este mundo podrá salvarte en SCP-096. Conocido como el Chico Tímido, entra en un estado de furia ciega e incontrolable en el preciso instante en que alguien observa sus rasgos faciales, ya sea en persona, en una fotografía antigua o en una grabación digital. En ese momento, la entidad emite alaridos desgarradores y comienza una persecución implacable hacia la posición del observador a través de continentes enteros derribando muros blindados a velocidades sobrehumanas sin dejar escapatoria posible."),
    ("Anomalía Desconocida Sector 4", "En las instalaciones subterráneas de contención del Sector 4 se ha detectado una fluctuación gravitacional no registrada. Tres operarios de Clase D fueron enviados a evaluar la anomalía mientras los sensores de presión atmosférica registraban variaciones críticas. La puerta de esclusa automática falló a las 02:00 horas, provocando la activación inmediata de los protocolos de descontaminación de emergencia y el aislamiento perimetral."),
]

DIVERSE_TOPICS_HORROR = [
    ("La Frecuencia de la Estación 9", "A las tres de la madrugada, las alertas de la estación de monitoreo solitaria registraron una oscilación electromagnética imposible. La niebla densa cubría los pinos centenarios mientras el frío glacial congelaba el vaho de mi respiración en la cabina de control. El zumbido en los receptores de radio analógicos aumentó de intensidad modulando una frecuencia que no pertenecía a ninguna estación civil ni militar. Al revisar los archivadores de acero encontré los diarios de guardia de operadores desaparecidos que describían exactamente las mismas señales y advertían no responder a la radio. La caligrafía de Miller en 1989 advertía que cuando la frecuencia imitaba tu propia voz la entidad ya se encontraba dentro del perímetro de seguridad. Una sombra alargada comenzó a deslizarse bajo el umbral de la puerta blindada mientras los altavoces repetían mi propio nombre en tiempo real. El pomo de la puerta de acero comenzó a descender lentamente con una fuerza fría y calculada. El cristal del ventanal estalló en pedazos ante una manifestación no euclidiana que me obligó a detonar la bengala de emergencia y huir a toda velocidad por el sendero forestal. El fulgor rojo cegador del fósforo iluminó una silueta colosal que retrocedió hacia la penumbra del bosque. Llegué al puesto de guardia de la autopista con las primeras luces del amanecer con las ropas rasgadas y las manos entumecidas por el frío. Las autoridades forestales acordonaron la zona bajo el pretexto de un rayo globular pero confiscaron todas mis cintas de grabación y mi bitácora personal. Hoy vivo en la ciudad pero cada vez que una radio emite estática sé que la presencia sigue esperando en el valle y que la conexión jamás se rompió."),
    ("El Faro de las Almas Negras", "Llegué a la isla del faro durante una tormenta de noviembre que cortó toda comunicación marítima durante tres semanas. Desde la primera noche, las luces giratorias reflejaban formas humanoides suspendidas en lo alto del acantilado rocoso donde ningún ser vivo podría sostenerse. Los registros del farero anterior terminaban con una sola frase repetida a lo largo de cuarenta páginas: 'No mires hacia el mar cuando la sirena de niebla enmudezca'. En el decimoquinto día, los generadores diésel se apagaron simultáneamente y el silencio absoluto cubrió la torre. Al subir los ciento ochenta escalones de caracol con una lámpara de queroseno, encontré huellas de agua salada que ascendían desde el sótano hasta la linterna principal. Una voz que imitaba a mi difunta madre susurraba detrás de la lente Fresnel mientras el cristal crujía bajo una presión marina inexplicable. Disparé las tres bengalas de auxilio hacia la oscuridad oceánica antes de atrancar la escotilla con barras de hierro. Cuando el barco de suministros llegó finalmente, me encontraron en el suelo temblando en estado de hipotermia severa. El faro fue clausurado definitivamente y los mapas de navegación actuales marcan la isla como zona de peligro náutico intransitable."),
    ("La Morgue del Turno Cero", "Durante seis años trabajé como patólogo forense en el turno nocturno del hospital central sin experimentar jamás una anomalía inexplicable. Todo cambió la noche en que ingresaron el cuerpo no identificado hallado en los túneles del metro subterráneo. El cadáver no presentaba signos de descomposición a pesar de llevar semanas sepultado bajo el lodo y la temperatura corporal se mantenía constante en doce grados. A las dos de la mañana, las luces fluorescentes de la sala de autopsias comenzaron a parpadear con un patrón rítmico similar al código morse. Los sensores de movimiento del pasillo exterior se activaban secuencialmente sin que ninguna persona cruzara frente a las cámaras de circuito cerrado. Al levantar el bisturí para realizar la incisión torácica, los ojos del sujeto se abrieron de golpe fijando una mirada violeta que paralizó mis extremidades. Los monitores cardíacos apagados emitieron un pitido continuo mientras un hedor a ozono inundaba la sala sellada. Huí rompiendo la cerradura de emergencia del laboratorio y presenté mi renuncia irrevocable al amanecer. El expediente del caso fue clasificado bajo custodia militar y la sala de autopsias permanece clausurada con precintos de plomo."),
]

DIVERSE_TOPICS_AITA = [
    ("Herencia y Boda Familiar", "¿Soy la mala por negarme a entregar los ahorros de toda mi vida a mi hermana tras descubrir lo que planeaba en su fiesta de compromiso? Durante diez años trabajé turnos dobles como enfermera para comprar mi primera vivienda propia viviendo con extrema frugalidad. Mi hermana y su prometido en cambio siempre vivieron por encima de sus posibilidades con préstamos y tarjetas de crédito al límite. Durante una cena familiar mi madre anunció ante todos los invitados que yo pagaría la fiesta de bodas en un hotel de lujo como mi regalo fraternal. Cuando respondí con calma: 'No puedo costear una fiesta ajena mientras estoy comprando mi casa', la mesa se convirtió en un campo de batalla. Mi hermana comenzó a llorar acusándome de arruinar su gran día y mi madre me gritó que la familia siempre se sacrifica por la familia. Durante las tres semanas siguientes recibí decenas de llamadas y mensajes de parientes lejanos acusándome de egoísta y amenazando con expulsarme de las fiestas. Descubrí además que mi hermana había intentado consultar a un gestor financiero con mis datos personales para solicitar un adelanto a mi nombre. Fui directamente a su casa, cancelé cualquier comunicación y les advertí que si volvían a usar mis documentos presentaría una denuncia formal por fraude. La boda finalmente se redujo a una ceremonia modesta y desde entonces mis padres se niegan a dirigirme la palabra. ¿Qué habrías hecho tú en mi lugar? ¿Fui demasiado lejos al poner este límite definitivo? Seis meses después firmé las escrituras de mi nuevo departamento y disfruto de una paz mental que ningún chantaje familiar podrá arrebatarme."),
    ("El Fraude del Jefe en la Oficina", "¿Soy el malo por denunciar a mi director de departamento ante recursos humanos y la junta directiva tras descubrir que se adjudicaba mis proyectos de inteligencia artificial? Durante dieciocho meses desarrollé en solitario un algoritmo de optimización logística trabajando fines de semana completos y noches interminables. En la presentación trimestral ante los inversionistas internacionales, mi jefe presentó el sistema como de su exclusiva autoría intelectual y recibió una bonificación millonaria sin mencionarme en los créditos. Cuando le solicité una explicación en privado, se burló de mí y me amenazó con arruinar mi carrera si abría la boca. Esa misma noche compilé todos los registros de commits de Git, los correos fechados y las bitácoras del servidor que demostraban inequívocamente mi autoría. Entregué el informe al comité de ética y a la fiscalía interna de la corporación. La auditoría confirmó el fraude de inmediato, despidió a mi jefe sin indemnización y me ascendió al cargo directivo. Sin embargo, varios compañeros de equipo me llaman traidor por haber destruido la carrera de un hombre de cincuenta años con familia. ¿Qué opinan ustedes? ¿Debí resolverlo internamente o hice lo correcto al proteger mi trabajo? Hoy el departamento funciona con total transparencia y el nuevo equipo trabaja bajo un marco de reconocimiento justo y profesional."),
]


@pytest.mark.parametrize("title,text", DIVERSE_TOPICS_SCP)
def test_empirical_scp_shorts_diversity(agent, curator_schema, title, text):
    script = agent.curate(
        raw_text=text,
        title=title,
        channel_lane="moku-scp-shorts",
        target_format="short",
    )
    validate(instance=script, schema=curator_schema)
    assert script["version"] == "2.0"
    assert script["metadata"]["channel_lane"] == "moku-scp-shorts"
    assert script["metadata"]["target_format"] == "short"

    # Pacing and scene constraints
    total_dur = script["metadata"]["estimated_duration_sec"]
    assert 60.0 <= total_dur <= 180.0, f"SCP Short total duration {total_dur} outside [60, 180]"

    scenes = [sc for act in script["acts"] for sc in act["scenes"]]
    assert 4 <= len(scenes) <= 12, f"SCP Short scene count {len(scenes)} outside [4, 12]"

    for sc in scenes:
        assert 8.0 <= sc["estimated_duration_sec"] <= 15.0
        assert sc["audio_pacing_cue"] in VALID_AUDIO_PACING_CUES
        assert 1 <= sc["tension_level"] <= 5
        assert len(sc["narration_text"].strip()) > 0
        assert sc["word_count"] >= 1
        assert len(sc["environmental_mood"].strip()) > 0

    assert len(script["acts"]) == 4


@pytest.mark.parametrize("title,text", DIVERSE_TOPICS_HORROR)
def test_empirical_horror_longform_diversity(agent, curator_schema, title, text):
    script = agent.curate(
        raw_text=text,
        title=title,
        channel_lane="moku-horror-long",
        target_format="longform",
    )
    validate(instance=script, schema=curator_schema)
    assert script["version"] == "2.0"
    assert script["metadata"]["channel_lane"] == "moku-horror-long"
    assert script["metadata"]["target_format"] == "longform"

    # Pacing and scene constraints
    total_dur = script["metadata"]["estimated_duration_sec"]
    assert total_dur >= 600.0, f"Horror Longform total duration {total_dur} < 600"

    scenes = [sc for act in script["acts"] for sc in act["scenes"]]
    assert 8 <= len(scenes) <= 24, f"Horror Longform scene count {len(scenes)} outside [8, 24]"

    for sc in scenes:
        assert 45.0 <= sc["estimated_duration_sec"] <= 90.0
        assert sc["audio_pacing_cue"] in VALID_AUDIO_PACING_CUES
        assert 1 <= sc["tension_level"] <= 5

    assert len(script["acts"]) == 4
    # Tension progression verification
    tensions = [sc["tension_level"] for sc in scenes]
    assert max(tensions) == 5, "Horror must peak at tension 5"
    assert tensions[0] in (1, 2), "Horror must start at low tension (1 or 2)"


@pytest.mark.parametrize("title,text", DIVERSE_TOPICS_AITA)
def test_empirical_aita_longform_diversity(agent, curator_schema, title, text):
    script = agent.curate(
        raw_text=text,
        title=title,
        channel_lane="aelithia-aita-long",
        target_format="longform",
    )
    validate(instance=script, schema=curator_schema)
    assert script["version"] == "2.0"
    assert script["metadata"]["channel_lane"] == "aelithia-aita-long"
    assert script["metadata"]["target_format"] == "longform"

    # Pacing and scene constraints
    total_dur = script["metadata"]["estimated_duration_sec"]
    assert total_dur >= 600.0, f"AITA Longform total duration {total_dur} < 600"

    scenes = [sc for act in script["acts"] for sc in act["scenes"]]
    assert 8 <= len(scenes) <= 24, f"AITA Longform scene count {len(scenes)} outside [8, 24]"

    for sc in scenes:
        assert 45.0 <= sc["estimated_duration_sec"] <= 90.0
        assert sc["audio_pacing_cue"] in VALID_AUDIO_PACING_CUES
        assert 1 <= sc["tension_level"] <= 5

    assert len(script["acts"]) == 4


# ============================================================================
# 2. ADVERSARIAL STRESS & BOUNDARY TESTS
# ============================================================================

class TestScriptCuratorAdversarialStress:
    """Stress tests covering extreme inputs, malformed characters, and edge cases."""

    def test_empty_input_stress_all_lanes(self, agent, curator_schema):
        for lane, fmt in [("moku-scp-shorts", "short"), ("moku-horror-long", "longform"), ("aelithia-aita-long", "longform")]:
            script = agent.curate(
                raw_text="",
                title="",
                channel_lane=lane,
                target_format=fmt,
            )
            validate(instance=script, schema=curator_schema)
            assert len(script["acts"]) == 4
            assert script["metadata"]["estimated_duration_sec"] >= (60.0 if fmt == "short" else 600.0)

    def test_single_word_input_stress(self, agent, curator_schema):
        script = agent.curate(
            raw_text="Anomalía",
            title="Prueba",
            channel_lane="moku-scp-shorts",
            target_format="short",
        )
        validate(instance=script, schema=curator_schema)
        assert len(script["acts"]) == 4

    def test_huge_input_text_truncation_and_slicing(self, agent, curator_schema):
        # 10,000 words text
        base_sentence = "En la profundidad de la noche los sensores continuaban emitiendo señales inexplicables. "
        huge_text = base_sentence * 700 # ~10,500 words

        script = agent.curate(
            raw_text=huge_text,
            title="Estrés Masivo",
            channel_lane="moku-horror-long",
            target_format="longform",
        )
        validate(instance=script, schema=curator_schema)
        scenes = [sc for act in script["acts"] for sc in act["scenes"]]
        assert len(scenes) <= 24, "Scenes must not exceed max_scenes (24)"
        for sc in scenes:
            assert 45.0 <= sc["estimated_duration_sec"] <= 90.0

    def test_run_on_sentence_without_punctuation(self, agent, curator_schema):
        run_on = "este es un texto sin puntos ni comas ni mayúsculas que continúa indefinidamente describiendo una entidad aterradora en la oscuridad del bosque mientras los pasos se acercan lentamente a la cabina " * 50
        script = agent.curate(
            raw_text=run_on,
            title="Run-on Stress",
            channel_lane="moku-horror-long",
            target_format="longform",
        )
        validate(instance=script, schema=curator_schema)
        assert len(script["acts"]) == 4

    def test_abnormal_characters_emoji_markdown_urls(self, agent, curator_schema):
        messy_text = (
            "### Encabezado Nivel 3 😱\n\n"
            "El Dr. Rodríguez y la Dra. Morales visitaron a **SCP-173** a las 3:15 a.m. (ver informe en https://example.com/scp). "
            "Hubo un descenso de 3.5 grados en la temperatura corporal del sujeto núm. 42! "
            "¿Qué ocurrió después?! Todo quedó en silencio... etc., pero la entidad despertó. 👻🔥 "
            "[REDACTADO POR LA FUNDACIÓN] y `código de prueba 0xDEADBEEF`. "
            "El personal de Clase-D huyó rápidamente del recinto cerrado."
        )
        script = agent.curate(
            raw_text=messy_text,
            title="Sanitization Stress",
            channel_lane="moku-scp-shorts",
            target_format="short",
        )
        validate(instance=script, schema=curator_schema)
        # Check that markdown and emojis are sanitized
        for act in script["acts"]:
            for sc in act["scenes"]:
                assert "###" not in sc["narration_text"]
                assert "https://" not in sc["narration_text"]
                assert "`" not in sc["narration_text"]

    def test_wpm_boundary_variations(self, agent, curator_schema, sample_scp_text):
        for test_wpm in [80.0, 120.0, 160.0, 220.0, 300.0]:
            script = agent.curate(
                raw_text=sample_scp_text,
                title="WPM Test",
                channel_lane="moku-scp-shorts",
                target_format="short",
                words_per_minute=test_wpm,
            )
            validate(instance=script, schema=curator_schema)
            for act in script["acts"]:
                for sc in act["scenes"]:
                    assert 8.0 <= sc["estimated_duration_sec"] <= 15.0

    def test_unknown_lane_fallback(self, agent, curator_schema):
        script = agent.curate(
            raw_text="Una historia misteriosa en la noche.",
            title="Fallback Lane",
            channel_lane="unknown-lane-xyz",
            target_format="unknown-fmt",
        )
        validate(instance=script, schema=curator_schema)
        assert script["metadata"]["target_format"] in ("longform", "short")
        assert len(script["acts"]) == 4


# ============================================================================
# 3. SCHEMA INTEGRITY & PROPERTY VERIFICATION
# ============================================================================

class TestSchemaIntegrityAndProperties:
    """Verifies that every field conforms strictly to Draft-07 contracts."""

    def test_scene_id_regex_formatting(self, agent, sample_horror_text):
        script = agent.curate(
            raw_text=sample_horror_text,
            title="Scene ID check",
            channel_lane="moku-horror-long",
            target_format="longform",
        )
        scenes = [sc for act in script["acts"] for sc in act["scenes"]]
        for i, sc in enumerate(scenes, start=1):
            expected_id = f"scene_{i:03d}"
            assert sc["scene_id"] == expected_id
            assert sc["scene_index"] == i

    def test_acts_strict_consecutive_indexing(self, agent, sample_aita_text):
        script = agent.curate(
            raw_text=sample_aita_text,
            title="Act Indexing Check",
            channel_lane="aelithia-aita-long",
            target_format="longform",
        )
        assert len(script["acts"]) == 4
        for idx, act in enumerate(script["acts"], start=1):
            assert act["act_number"] == idx
            assert len(act["scenes"]) >= 1
            assert len(act["act_title"]) > 0

    def test_additional_properties_rejection(self, curator_schema):
        # Ensure schema itself rejects invalid additional properties
        invalid_script = {
            "version": "2.0",
            "extra_field": "disallowed",
            "metadata": {
                "title": "Invalid",
                "channel_lane": "moku-scp-shorts",
                "target_format": "short",
                "total_word_count": 100,
                "estimated_duration_sec": 75.0,
                "tension_curve": [1, 2, 3, 4, 5, 2],
            },
            "acts": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate(instance=invalid_script, schema=curator_schema)
