"""
src/curators/curation_profiles.py - Narrative lane profiles and curation configurations.

Provides canonical thematic narrative configs (horror, drama, scifi), Draft-07 schema
pointers, lane alias resolution, and deterministic fallback narrative generation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.log import get_logger

logger = get_logger("cinematic_script_curator.profiles")


@dataclass(slots=True, frozen=True)
class ActNarrativePlan:
    """Strongly typed representation of an individual narrative act."""
    act_index: int                       # 1-based sequential act index (1 <= act_index <= N)
    act_title: str                       # Public title for YouTube chapters
    dramatic_role: str                   # exposition_inception | rising_action_dread | confrontation_crisis | climax_confrontation | climax_breaking_point | aftermath_revelation
    tension_level: int                   # Integer tension score from 1 (ambient) to 5 (peak climax)
    narration_text: str                  # Dialogue and narration sentences allocated to this act
    target_duration_sec: float           # Scaled duration in seconds matching TTS audio
    word_count: int                      # Word count for duration estimation
    environmental_moods: List[str] = field(default_factory=list)  # Thematic environment descriptions for catalog matching


SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "script_curator.schema.json"

# Valid schema Draft-07 audio pacing cues
VALID_AUDIO_PACING_CUES: set[str] = {
    "calm_slow",
    "steady_dramatic",
    "tense_accelerando",
    "intense_urgent",
    "whispered_grave",
}

# ============================================================================
# CANONICAL LANE PROFILES & THEMATIC NARRATIVE FORMULAS
# ============================================================================

LANE_CURATION_CONFIGS: Dict[str, Dict[str, Any]] = {
    "horror-scp-shorts": {
        "channel": "horror",
        "target_format": "short",
        "default_wpm": 165.0,
        "target_scene_dur": 11.0,
        "min_scene_dur": 8.0,
        "max_scene_dur": 15.0,
        "min_total_dur": 60.0,
        "max_total_dur": 180.0,
        "min_scenes": 4,
        "max_scenes": 12,
        "acts": [
            {
                "act_number": 1,
                "act_title": "Acto I: Designación y Procedimientos de Contención",
                "dramatic_role": "exposition_inception",
                "tension_profile": [1, 2],
                "moods": [
                    "Búnker de Contención Subterráneo con Iluminación Fluorescente",
                    "Cámara de Aislamiento de Hormigón Blindado y Titanio",
                    "Laboratorio de Investigación Nivel 4 de la Fundación SCP",
                ],
            },
            {
                "act_number": 2,
                "act_title": "Acto II: Registro de Incidentes y Pruebas no Autorizadas",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [3, 4],
                "moods": [
                    "Sala de Observación con Vidrio Reforzado y Sensores Térmicos",
                    "Pasillo de Acceso Restringido con Luces Intermitentes",
                    "Cámara de Pruebas con Sujetos Clase-D y Monitores Anómalos",
                ],
            },
            {
                "act_number": 3,
                "act_title": "Acto III: Brecha Crítica y Manifestación Hostil",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [5],
                "moods": [
                    "Zona Cero de Ruptura de Contención con Sirenas y Luces Rojas",
                    "Compuertas Hidráulicas Destruidas y Estática en Cámaras",
                    "Manifestación Hostil de la Anomalía en Penumbra Total",
                ],
            },
            {
                "act_number": 4,
                "act_title": "Acto IV: Protocolo de Emergencia y Archivo Clasificado",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [3, 2],
                "moods": [
                    "Terminal de Archivo Clasificado Nivel 5 bajo Protocolo de Bloqueo",
                    "Perímetro de Cuarentena Sellado con Hormigón Armado",
                    "Sala de Monitoreo en Silencio de Emergencia tras la Brecha",
                ],
            },
        ],
    },
    "horror-horror-long": {
        "channel": "horror",
        "target_format": "longform",
        "default_wpm": 140.0,
        "target_scene_dur": 90.0,
        "min_scene_dur": 45.0,
        "max_scene_dur": 150.0,
        "min_total_dur": 600.0,
        "max_total_dur": 1800.0,
        "min_scenes": 5,
        "max_scenes": 8,
        "acts": [
            {
                "act_number": 1,
                "act_title": "Acto I: Incepción Sensorial y Aislamiento",
                "dramatic_role": "exposition_inception",
                "tension_profile": [1, 2],
                "moods": [
                    "Estación de monitoreo aislada rodeada de niebla densa y pinos silenciosos",
                    "Torre de control en penumbra con tenue resplandor verde de cuadrantes analógicos",
                    "Perímetro boscoso exterior con niebla baja y descenso brusco de temperatura",
                ],
            },
            {
                "act_number": 2,
                "act_title": "Acto II: Advertencias Ignoradas y Señales",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [2, 3],
                "moods": [
                    "Consola de radio con luces fluorescentes parpadeando bajo pulso electromagnético",
                    "Sala de archivos con archivadores de acero y libretas de guardias desaparecidos",
                    "Corredor exterior helado con escarcha sobre barandillas metálicas y niebla baja",
                ],
            },
            {
                "act_number": 3,
                "act_title": "Acto III: Escalada Inexorable de la Amenaza",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [3, 4],
                "moods": [
                    "Corredores oscuros con sombras tridimensionales en los ángulos ciegos",
                    "Muros de hormigón agrietados con señales de interferencia biológica",
                    "Perímetro sellado bajo sirenas de emergencia lejanas",
                ],
            },
            {
                "act_number": 4,
                "act_title": "Acto IV: Confrontación Inexplicable y Ruptura",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [4, 5],
                "moods": [
                    "Cúpula de observación quebrada con ventanal astillado y fulgor de bengala roja",
                    "Puerta blindada cediendo con sombra tridimensional proyectada bajo el umbral",
                    "Manifestación anómala violenta en la penumbra del bosque",
                ],
            },
            {
                "act_number": 5,
                "act_title": "Acto V: Clímax Crítico y Desesperación",
                "dramatic_role": "climax_breaking_point",
                "tension_profile": [5],
                "moods": [
                    "Zona cero de brecha total con luces estroboscópicas rojas y estática ensordecedora",
                    "Abismo sensorial con fractura del espacio físico y colapso de mamparas",
                    "Encuentro directo con la entidad en el umbral del refugio",
                ],
            },
            {
                "act_number": 6,
                "act_title": "Acto VI: Secuela Psicológica y Trauma Permanente",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [2, 3],
                "moods": [
                    "Amanecer brumoso desolado sobre carretera forestal con vehículos oficiales",
                    "Apartamento urbano en penumbra nocturna con receptor de radio emitiendo estática",
                    "Expediente sellado bajo reserva oficial y custodia permanente",
                ],
            },
            {
                "act_number": 7,
                "act_title": "Acto VII: Expediente Clasificado y Silencio Oficial",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [2],
                "moods": [
                    "Archivador confidencial sellado con cinta forense bajo luz fluorescente",
                    "Carretera desolada al crepúsculo con patrullas en retirada",
                ],
            },
            {
                "act_number": 8,
                "act_title": "Acto VIII: Ecos del Abismo y Vigilia Eterna",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [1, 2],
                "moods": [
                    "Habitación en penumbra con receptor de onda corta transmitiendo susurros",
                    "Horizonte oscuro donde la niebla nunca termina de disiparse",
                ],
            },
        ],
    },
    "drama-aita-long": {
        "channel": "drama",
        "target_format": "longform",
        "default_wpm": 145.0,
        "target_scene_dur": 90.0,
        "min_scene_dur": 45.0,
        "max_scene_dur": 150.0,
        "min_total_dur": 600.0,
        "max_total_dur": 1800.0,
        "min_scenes": 5,
        "max_scenes": 8,
        "acts": [
            {
                "act_number": 1,
                "act_title": "Acto I: El Dilema Moral y Contexto Familiar",
                "dramatic_role": "exposition_inception",
                "tension_profile": [1, 2],
                "moods": [
                    "Salas de estar cálidas con iluminación hogareña",
                    "Cena familiar cotidiana con ambiente distendido",
                    "Cocina doméstica al atardecer con luz suave",
                ],
            },
            {
                "act_number": 2,
                "act_title": "Acto II: Primeras Fricciones y Demandas Injustas",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [2, 3],
                "moods": [
                    "Mesa de café con murmullos y demandas económicas encubiertas",
                    "Llamadas telefónicas insistentes con tono de exigencia moral",
                    "Sala de estar con miradas esquivas y tensión en el aire",
                ],
            },
            {
                "act_number": 3,
                "act_title": "Acto III: El Detonante y Escalada del Conflicto",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [3, 4],
                "moods": [
                    "Discusión tensa en sala familiar bajo luz tenue",
                    "Mesa de comedor hostil con parientes enfrentados",
                    "Oficina legal con carpetas notariales y contratos",
                ],
            },
            {
                "act_number": 4,
                "act_title": "Acto IV: Punto de Ruptura y Confrontación Directa",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [4, 5],
                "moods": [
                    "Tribunal familiar explosivo con reproches a gritos",
                    "Audiencia judicial conciliatoria con tensión máxima",
                    "Ruptura definitiva en medio de una celebración interrumpida",
                ],
            },
            {
                "act_number": 5,
                "act_title": "Acto V: Juicio Social y Veredicto Comunitario",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [4, 5],
                "moods": [
                    "Mensajes de texto implacables y acusaciones en redes sociales",
                    "Reunión de familiares divididos en bandos irreconciliables",
                    "Asesoría legal notificando límites definitivos y medidas cautelares",
                ],
            },
            {
                "act_number": 6,
                "act_title": "Acto VI: Reflexión Final y Actualización Posterior",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [1, 2],
                "moods": [
                    "Cafetería reflexiva con luz natural",
                    "Amanecer de paz mental e independencia",
                    "Nuevo hogar con tranquilidad",
                ],
            },
            {
                "act_number": 7,
                "act_title": "Acto VII: Consecuencias y Nuevos Límites",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [2, 1],
                "moods": [
                    "Sala de estar ordenada con silencio reparador",
                    "Notificación de cierre de comunicaciones formales",
                ],
            },
            {
                "act_number": 8,
                "act_title": "Acto VIII: Paz Mental y Reconstrucción",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [1],
                "moods": [
                    "Ventanal soleado en un hogar independiente y en calma",
                    "Paseo sereno confirmando la decisión correcta",
                ],
            },
        ],
    },
    "drama-drama-shorts": {
        "channel": "drama",
        "target_format": "short",
        "default_wpm": 165.0,
        "target_scene_dur": 11.0,
        "min_scene_dur": 8.0,
        "max_scene_dur": 15.0,
        "min_total_dur": 60.0,
        "max_total_dur": 180.0,
        "min_scenes": 4,
        "max_scenes": 12,
        "acts": [
            {
                "act_number": 1,
                "act_title": "Acto I: Planteamiento del Conflicto Familiar",
                "dramatic_role": "exposition_inception",
                "tension_profile": [1, 2],
                "moods": [
                    "Cafetería con luz natural y rostros tensos",
                    "Sala de estar moderna al anochecer con atmósfera cargada",
                    "Cocina doméstica con miradas evasivas",
                ],
            },
            {
                "act_number": 2,
                "act_title": "Acto II: La Exigencia Injusta y el Ultimátum",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [3, 4],
                "moods": [
                    "Mesa de comedor con reproches directos",
                    "Pasillo estrecho con tensión creciente",
                    "Llamada telefónica acalorada en automóvil",
                ],
            },
            {
                "act_number": 3,
                "act_title": "Acto III: La Decisión Firme y Ruptura",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [5],
                "moods": [
                    "Confrontación decisiva frente a la familia reunida",
                    "Portazo definitivo y silencio absoluto",
                    "Mirada resuelta ante el espejo",
                ],
            },
            {
                "act_number": 4,
                "act_title": "Acto IV: Reflexión Ética y Veredicto Comunitario",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [3, 2],
                "moods": [
                    "Apartamento en calma con luz matutina",
                    "Ventanal con lluvia suave y paz recobrada",
                    "Paseo solitario con serenidad interior",
                ],
            },
        ],
    },
    "scifi-singularity-shorts": {
        "channel": "scifi",
        "target_format": "short",
        "default_wpm": 160.0,
        "target_scene_dur": 11.0,
        "min_scene_dur": 8.0,
        "max_scene_dur": 15.0,
        "min_total_dur": 60.0,
        "max_total_dur": 180.0,
        "min_scenes": 4,
        "max_scenes": 12,
        "acts": [
            {
                "act_number": 1,
                "act_title": "Acto I: Detección de la Anomalía Cósmica",
                "dramatic_role": "exposition_inception",
                "tension_profile": [1, 2],
                "moods": [
                    "Puente de mando estelar con monitores holográficos y telemetría",
                    "Observatorio orbital sobre el horizonte de un planeta helado",
                    "Antenas parabólicas de radioastronomía bajo cielo nocturno",
                ],
            },
            {
                "act_number": 2,
                "act_title": "Acto II: Colapso de la Física Teórica",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [3, 4],
                "moods": [
                    "Cámara de contención magnética con fluctuaciones del vacío",
                    "Vórtice gravitacional deformando el espacio visible",
                    "Consola de navegación alertando distorsión temporal extrema",
                ],
            },
            {
                "act_number": 3,
                "act_title": "Acto III: Cruce del Horizonte de Sucesos",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [5],
                "moods": [
                    "Horizonte de sucesos brillando con radiación de Hawking",
                    "Disco de acreción gigantesco absorbiendo materia a velocidad lumínica",
                    "Singularidad central con colapso dimensional",
                ],
            },
            {
                "act_number": 4,
                "act_title": "Acto IV: Registro Estelar y Transmisión Final",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [3, 2],
                "moods": [
                    "Sonda espacial emitiendo último paquete de datos criptográficos",
                    "Vasto espacio interestelar con estrellas titilando en la distancia",
                    "Terminal de archivo de la misión con estatus confirmado",
                ],
            },
        ],
    },
    "scifi-singularity-long": {
        "channel": "scifi",
        "target_format": "longform",
        "default_wpm": 140.0,
        "target_scene_dur": 90.0,
        "min_scene_dur": 45.0,
        "max_scene_dur": 150.0,
        "min_total_dur": 600.0,
        "max_total_dur": 1800.0,
        "min_scenes": 5,
        "max_scenes": 8,
        "acts": [
            {
                "act_number": 1,
                "act_title": "Acto I: Incepción Teórica y Enigma Cósmico",
                "dramatic_role": "exposition_inception",
                "tension_profile": [1, 2],
                "moods": [
                    "Complejo de radiotelescopios en el desierto bajo vía láctea brillante",
                    "Sala de control de misión espacial con pantallas orbitales en tiempo real",
                    "Laboratorio de astrofísica con simulaciones computacionales hiperdensas",
                ],
            },
            {
                "act_number": 2,
                "act_title": "Acto II: La Paradoja Gravitacional y Alerta Instrumental",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [2, 3, 4],
                "moods": [
                    "Sonda interestelar cruzando nebulosa oscura con estática de telemetría",
                    "Cámara de interferometría cuántica registrando ondas gravitatorias",
                    "Búnker de procesamiento de datos con alarmas térmicas silenciosas",
                ],
            },
            {
                "act_number": 3,
                "act_title": "Acto III: Punto Crítico y Frontera Relativista",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [4, 5, 5],
                "moods": [
                    "Frontera del agujero negro supermasivo con lente gravitacional extremo",
                    "Chorros relativistas de plasma proyectándose a través de años luz",
                    "Colapso de espacio-tiempo en simulación holográfica inmersiva",
                ],
            },
            {
                "act_number": 4,
                "act_title": "Acto IV: Síntesis Astrofísica y Perspectiva Cósmica",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [3, 2],
                "moods": [
                    "Telescopio espacial flotando en el vacío con la Tierra en el fondo",
                    "Archivo estelar archivando expediente de la singularidad",
                    "Amanecer sobre observatorio de alta montaña",
                ],
            },
        ],
    },
}

# Convenience lane aliases
LANE_CURATION_CONFIGS["horror-long"] = LANE_CURATION_CONFIGS["horror-horror-long"]
LANE_CURATION_CONFIGS["drama-shorts"] = LANE_CURATION_CONFIGS["drama-drama-shorts"]
LANE_CURATION_CONFIGS["drama-long"] = LANE_CURATION_CONFIGS["drama-aita-long"]


def resolve_lane_config(channel_lane: str, target_format: str) -> Tuple[str, Dict[str, Any]]:
    """
    Resolves lane profile and configuration dictionary from canonical ID or legacy alias.
    """
    lane_str = str(channel_lane).strip()
    lane_lower = lane_str.lower()
    fmt_lower = str(target_format).strip().lower()

    if lane_str in LANE_CURATION_CONFIGS:
        return lane_str, LANE_CURATION_CONFIGS[lane_str]
    if lane_lower in LANE_CURATION_CONFIGS:
        return lane_lower, LANE_CURATION_CONFIGS[lane_lower]

    # SciFi matching
    if any(k in lane_lower for k in ("scifi", "singularity", "singularidad")):
        if fmt_lower in ("short", "shorts", "vertical") or "short" in lane_lower:
            return "scifi-singularity-shorts", LANE_CURATION_CONFIGS["scifi-singularity-shorts"]
        return "scifi-singularity-long", LANE_CURATION_CONFIGS["scifi-singularity-long"]

    # Drama matching
    if any(k in lane_lower for k in ("aita", "drama", "confession")):
        if fmt_lower in ("short", "shorts", "vertical") or "short" in lane_lower:
            return "drama-drama-shorts", LANE_CURATION_CONFIGS["drama-drama-shorts"]
        return "drama-aita-long", LANE_CURATION_CONFIGS["drama-aita-long"]

    # Horror / SCP matching
    if "scp" in lane_lower:
        return "horror-scp-shorts", LANE_CURATION_CONFIGS["horror-scp-shorts"]
    if any(k in lane_lower for k in ("horror", "creepy", "cosmic")):
        if fmt_lower in ("short", "shorts", "vertical") or "short" in lane_lower:
            return "horror-scp-shorts", LANE_CURATION_CONFIGS["horror-scp-shorts"]
        return "horror-horror-long", LANE_CURATION_CONFIGS["horror-horror-long"]

    # Default fallback
    if fmt_lower in ("short", "shorts", "vertical"):
        return "horror-scp-shorts", LANE_CURATION_CONFIGS["horror-scp-shorts"]
    return "horror-horror-long", LANE_CURATION_CONFIGS["horror-horror-long"]


def synthesize_hook_summary(title: str, lane_key: str, clean_text: str) -> str:
    """Synthesizes high-retention lane-calibrated hook summary."""
    if "scp" in lane_key:
        try:
            from src.core.scp_lore import lookup_scp
            scp_info = lookup_scp(title) or lookup_scp(clean_text[:100])
            if scp_info:
                scp_id = scp_info.get("scp_id", "SCP")
                obj_class = scp_info.get("object_class", "Euclid")
                return f"Expediente clasificado de la Fundación SCP: Ítem #{scp_id} ({obj_class}) con protocolos de contención primaria y alerta de brecha."
        except Exception:
            pass
        return f"Expediente clasificado de la Fundación SCP sobre '{title[:60]}' con protocolos de contención y alerta de brecha crítica."

    if "aita" in lane_key or "drama" in lane_key:
        first_sent = clean_text.split(".")[0] if "." in clean_text else clean_text[:80]
        if "¿" in first_sent or any(w in first_sent.lower() for w in ("malo", "mala", "culpa")):
            return f"Dilema moral en primera persona: {first_sent.strip()}"
        return f"Dilema moral en primera persona sobre '{title[:60]}': ¿Soy la mala por negarme a ceder ante la presión familiar tras descubrir la verdad?"

    return f"Relato en primera persona sobre '{title[:60]}' con inmersión sensorial inmediata ante anomalía nocturna inexplicable y escalada de dread."


def generate_fallback_narrative(title: str, lane_key: str, existing_text: str) -> str:
    """Generates deterministic, canon-grounded fallback story when input text is minimal."""
    try:
        from src.templates.narratives import (
            build_drama_longform_narrative,
            build_drama_short_narrative,
            build_horror_longform_narrative,
            build_horror_short_narrative,
            build_scifi_longform_narrative,
            build_scifi_short_narrative,
        )

        is_short = "short" in lane_key
        if "scp" in lane_key:
            return build_horror_short_narrative(topic=title or "SCP-087", channel="horror")
        if "aita" in lane_key or "drama" in lane_key:
            if is_short:
                return build_drama_short_narrative(topic=title or "el límite personal frente a la familia", channel="drama")
            return build_drama_longform_narrative(topic=title or "el conflicto de herencia familiar", channel="drama")
        if "scifi" in lane_key or "singularity" in lane_key:
            if is_short:
                return build_scifi_short_narrative(topic=title or "el horizonte de sucesos y la paradoja del tiempo", channel="scifi")
            return build_scifi_longform_narrative(topic=title or "el horizonte de sucesos y la paradoja del tiempo", channel="scifi")
        if is_short:
            return build_horror_short_narrative(topic=title or "la anomalía del bosque", channel="horror")
        return build_horror_longform_narrative(topic=title or "la frecuencia prohibida del bosque", channel="horror")
    except Exception as exc:
        logger.debug("Fallback template invocation notice: %s", exc)

    return _builtin_fallback_text(title, lane_key)


def _builtin_fallback_text(title: str, lane_key: str) -> str:
    """Provides built-in contextual fallback narrative when narrative templates are unavailable."""
    clean_title = re.sub(r"[\"\'\']", "", title or "").strip()
    if "scp" in lane_key:
        return (
            f"Protocolo de contención primaria de la Fundación para {clean_title or 'anomalía no identificada'}. "
            "Los informes perimetrales confirman manifestaciones no euclidianas que alteran la estabilidad del sector subterráneo. "
            "Las unidades móviles de contención desplegadas en el perímetro reportaron fluctuaciones cinéticas y caídas bruscas "
            "de temperatura de más de quince grados en menos de diez segundos. Tres operarios especializados intentaron sellar la compuerta "
            "principal mientras los sensores térmicos registraban una masa oscura desplazándose contra las fuentes lumínicas artificiales. "
            "Las grabaciones de audio recuperadas de las cámaras de seguridad revelaron que la anomalía emite modulaciones complejas "
            "capaces de distorsionar la percepción temporal de quienes permanecen en su radio de influencia inmediata. "
            "Por orden directa del comando de seguridad del Sitio, las instalaciones fueron selladas con mamparas de titanio reforzado "
            "y el acceso a la zona permanece estrictamente restringido a personal con credenciales de nivel cuatro."
        )
    if "aita" in lane_key or "drama" in lane_key:
        return (
            f"¿Soy la persona equivocada por poner límites definitivos en torno a {clean_title or 'este conflicto personal'}? "
            "Durante más de diez años trabajé turnos dobles y sacrifiqué mi tranquilidad para construir una estabilidad propia con esfuerzo honesto. "
            "Sin embargo, mi círculo más cercano organizó una emboscada moral para exigirme que entregara mis ahorros y asumiera deudas ajenas que no me correspondían. "
            "Me dijeron claramente que la familia siempre está por encima de cualquier consideración individual y que mi negativa demostraba egoísmo y falta de afecto. "
            "Cuando me negué con total serenidad diciendo que no estaba dispuesto a financiar malas decisiones ajenas, la reunión se convirtió en un tribunal de reproches amargos y amenazas de exclusión definitiva. "
            "Contraté asesoría legal independiente para proteger mi patrimonio y establecí un distanciamiento tajante frente a las presiones y chantajes emocionales. "
            "Meses después, compruebo que mantener la firmeza en mis convicciones fue la única decisión que me permitió preservar mi paz interior y mi dignidad personal."
        )
    if "scifi" in lane_key or "singularity" in lane_key:
        return (
            f"La misión de exploración cósmica hacia {clean_title or 'el horizonte de sucesos'} marcó un punto de inflexión en la investigación astrofísica. "
            "Al aproximarse al sector anómalo del espacio profundo, los sensores de navegación registraron intensas fluctuaciones gravitacionales "
            "que desafiaban las predicciones de la relatividad general. La tripulación científica observó anomalías en los relojes atómicos "
            "de la nave a medida que la dilatación temporal se hacía más pronunciada en las inmediaciones del disco de acreción. "
            "Las sondas automatizadas enviadas hacia el perímetro transmitieron datos espectroscópicos de alta energía antes de que "
            "sus señales fueran absorbidas por la intensa curvatura del espacio-tiempo. Los análisis térmicos confirmaron la emisión "
            "constante de radiación teórica, corroborando la existencia de fenómenos cuánticos a escala macroscópica. "
            "Ante la inminencia de sobrepasar el radio de no retorno, el comando de vuelo ordenó una maniobra de escape con propulsión máxima, "
            "preservando los valiosos registros telemétricos para el avance del conocimiento humano."
        )
    return (
        f"Una advertencia sobre la investigación de {clean_title or 'la señal no identificada'}. "
        "La niebla densa cubría las laderas circundantes mientras una oscilación electromagnética desconocida saturaba las consolas de control de la estación remota. "
        "Al revisar los registros archivados de los operadores anteriores, comprobé que incidentes idénticos habían sido reportados en décadas pasadas sin que las autoridades ofrecieran jamás una explicación convincente. "
        "Una modulación en los altavoces de emergencia comenzó a repetir frases completas con un timbre metálico y desprovisto de entonación humana. "
        "Al iluminar el corredor exterior, descubrí huellas profundas sobre el piso helado que confirmaban que la presencia ya había ingresado al perímetro de seguridad. "
        "El cristal del ventanal principal vibró intensamente ante una fuerza descomunal que me obligó a activar los protocolos de emergencia y evacuar la cabina sin mirar atrás. "
        "Aunque hoy resido lejos de aquel valle solitario, la certeza de que esa frecuencia continúa activa en la noche me acompaña permanentemente."
    )
