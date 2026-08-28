"""
src/narrative/archetypes.py - Archetypal story templates and tension progression structures.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from src.narrative.schema import (
    AudioContract,
    CosmicScriptContract,
    NarrativeArchetype,
    SceneContract,
    SFXCue,
    VideoFormat,
    VoicePreset,
)

ARCHETYPE_PRESETS: Dict[NarrativeArchetype, Dict[str, Any]] = {
    NarrativeArchetype.HYDROACOUSTIC_TELEMETRY: {
        "title_template": "REGISTRO HIDROACÚSTICO // SECTOR FO-73",
        "voice_preset": VoicePreset.HYDROPHONE_RADIO,
        "drone_freq": 34.0,
        "shader_sequence": ["RADAR_HYDROACOUSTIC", "MONOLITHS_RAYMARCHING", "RADAR_HYDROACOUSTIC"],
        "hud_baseline": "SONAR PASIVO: FRECUENCIA NOMINAL",
        "hud_escalation": "ANOMALÍA BAROMÉTRICA: -11,400 METROS",
        "hud_climax": "ECO MASIVO NO BIOLÓGICO DETECTADO",
        "hud_expunged": "SEÑAL PERDIDA // TELEMETRÍA CORRUPTA",
        "phases": {
            "p1_baseline": "Registro hidroacústico automatizado a once mil doscientos metros de profundidad. Presión barométrica estacional dentro de parámetros estándar.",
            "p2_micro": "A las cero tres cuarenta UTC, las boyas sumergidas registraron una fluctuación rítmica de seis hercios... sin origen biológico conocido.",
            "p3_escalation": "La compresión estructural del casco aumentó un cuarenta por ciento en diez segundos. Los hidrófonos no detectan agua desplazada... sino agua comprimida hacia un punto focal.",
            "p4_climax": "La masa sumergida supera las cuatrocientas megatoneladas. No tiene firma térmica... pero absorbe activamente las ondas del sonar de barrido.",
            "p5_loop": "Cierre de escotillas de emergencia y purga de transmisión. Si estás escuchando este registro...",
        },
        "loop_connector": "...es porque el sensor del abismo volvió a activarse...",
    },
    NarrativeArchetype.PROCEDURAL_INSTITUTIONAL_MANUAL: {
        "title_template": "PROTOCOLO DE CONTENCIÓN // DIRECTIVA C-88",
        "voice_preset": VoicePreset.INTERCOM_BUNKER,
        "drone_freq": 48.0,
        "shader_sequence": ["MONOLITHS_RAYMARCHING", "RADAR_HYDROACOUSTIC", "GRAVITATIONAL_SINGULARITY"],
        "hud_baseline": "NIVEL DE ACCESO 5 // BÚNKER SUBTERRÁNEO",
        "hud_escalation": "RESONANCIA DIMENSIONAL ELEVADA",
        "hud_climax": "FALLO EN EL ANCLAJE TEMPORAL",
        "hud_expunged": "DIRECTIVA 99 EJECUTADA // [EXPURGADO]",
        "phases": {
            "p1_baseline": "Directiva institucional para el personal de guardia en la bóveda subterránea número cuatro. Verifique la integridad de los sellos de plomo cada doce minutos.",
            "p2_micro": "Si percibe una ligera variación en la temperatura del aire o escucha su propio nombre susurrado desde el conducto de ventilación... no responda.",
            "p3_escalation": "El protocolo prohíbe mirar directamente hacia las esquinas del techo cuando la iluminación de emergencia cambie a verde fósforo.",
            "p4_climax": "A las cero cuatro doce, la geometría del pasillo principal se duplicó sobre sí misma. La puerta exterior ahora conduce al mismo punto de partida.",
            "p5_loop": "Activación inmediata del procedimiento de cuarentena total. Recuerde que todo lo que acaba de presenciar...",
        },
        "loop_connector": "...comienza de nuevo cuando suena la primera alarma...",
    },
    NarrativeArchetype.SPECULATIVE_BIOLOGICAL_DOSSIER: {
        "title_template": "EXPEDIENTE ANATÓMICO // ENTIDAD LEVIATÁN-0",
        "voice_preset": VoicePreset.BLACKBOX_TAPE,
        "drone_freq": 32.0,
        "shader_sequence": ["GRAVITATIONAL_SINGULARITY", "MONOLITHS_RAYMARCHING", "GRAVITATIONAL_SINGULARITY"],
        "hud_baseline": "REGISTRO DE DISECCIÓN // CRÍPTICO",
        "hud_escalation": "DISTORSIÓN LOCAL DEL ESPACIO",
        "hud_climax": "SINGULARIDAD ORGÁNICA ACTIVA",
        "hud_expunged": "ARCHIVO CENSURADO // PROTOCOLO FINAL",
        "phases": {
            "p1_baseline": "Análisis morfológico de la muestra biológica recuperada en la fosa mesoatlántica. Tejido celular de densidad variable y pigmentación refractaria.",
            "p2_micro": "Durante la microsección quirúrgica, las fibras no se cortaron... sino que se curvaron alejándose del escalpelo de titanio.",
            "p3_escalation": "El campo gravitacional circundante sufre una atracción centrípeta hacia el núcleo celular. Los instrumentos de precisión registran dilatación temporal en un radio de dos metros.",
            "p4_climax": "No se trata de un organismo vivo en nuestro espacio tridimensional... sino de la sombra proyectada de una estructura infinitamente más masiva.",
            "p5_loop": "Muestra sellada en contenedor no magnético. Si el operador experimenta mareo gravitatorio...",
        },
        "loop_connector": "...debe reiniciar la telemetría antes de que la masa colapse...",
    },
}
