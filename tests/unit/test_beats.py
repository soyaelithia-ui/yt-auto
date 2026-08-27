"""
Unit tests for src/curators/beats.py: extract_story_beats, validate_beat_format, and shot duration calculations.
Verifies unbracketed section/chapter header stripping, beat parsing, and timing distribution.
"""

import pytest
from src.curators.beats import (
    extract_story_beats,
    validate_beat_format,
    calculate_beat_shot_durations,
)


def test_extract_story_beats_with_explicit_tags():
    raw_script = (
        "[BEAT 1: ITEM & CLASIFICACION]\n"
        "Archivo SCP Clasificado. SCP-096. Clasificación: Euclídeo.\n\n"
        "[BEAT 2: MECANICA DE LA ANOMALIA]\n"
        "Cualquier persona que observe su rostro activará un estado de agresión extrema.\n\n"
        "[BEAT 3: CONTENCION]\n"
        "Debe estar recluido en una celda de acero hermética."
    )
    clean_script, beats = extract_story_beats(raw_script)

    assert "[BEAT" not in clean_script
    assert len(beats) == 3
    assert beats[0]["label"] == "ITEM & CLASIFICACION"
    assert "Archivo SCP Clasificado" in beats[0]["text"]
    assert "Cualquier persona que observe su rostro" in beats[1]["text"]
    assert "Debe estar recluido" in beats[2]["text"]


def test_extract_story_beats_strips_unbracketed_section_headers():
    raw_script = (
        "Título: Expediente Nocturno.\n\n"
        "Sección Primera: El Descubrimiento Inicial y Primeros Registros.\n\n"
        "Durante la noche del catorce de octubre, los sensores de proximidad registraron una anomalía térmica en el sector cuatro. "
        "El personal de guardia notificó de inmediato al puesto de comando central.\n\n"
        "Sección 2: La Intervención del Equipo Táctico.\n\n"
        "Un destacamento especializado ingresó en la instalación para asegurar el perímetro exterior. "
        "No se encontraron sobrevivientes en el primer nivel.\n\n"
        "Sección Duodécima: Conclusión y Dictamen Final.\n\n"
        "El área fue sellada permanentemente bajo estricto protocolo de cuarentena biológica."
    )
    clean_script, beats = extract_story_beats(raw_script)

    assert "Título:" not in clean_script
    assert "Sección Primera" not in clean_script
    assert "Sección 2" not in clean_script
    assert "Sección Duodécima" not in clean_script
    assert "Durante la noche del catorce de octubre" in clean_script
    assert "Un destacamento especializado ingresó" in clean_script
    assert "El área fue sellada permanentemente" in clean_script
    for b in beats:
        assert "Sección" not in b["text"]
        assert "Título:" not in b["text"]


def test_extract_story_beats_strips_markdown_and_chapter_headers():
    raw_script = (
        "# Capítulo 1: La Llegada al Valle\n\n"
        "El vehículo se detuvo frente a la antigua reja de hierro forjado. "
        "La niebla cubría por completo el sendero principal hacia la mansión abandonada.\n\n"
        "# Capítulo 2: Las Primeras Sombras\n\n"
        "Al cruzar el umbral, una corriente de aire helado apagó las linternas portátiles. "
        "Los susurros comenzaron a resonar detrás de los muros de piedra."
    )
    clean_script, beats = extract_story_beats(raw_script)

    assert "#" not in clean_script
    assert "Capítulo 1" not in clean_script
    assert "Capítulo 2" not in clean_script
    assert "El vehículo se detuvo frente a la antigua reja" in clean_script
    assert "Al cruzar el umbral" in clean_script
    for b in beats:
        assert "Capítulo" not in b["text"]


def test_extract_story_beats_empty_and_fallback():
    clean_empty, beats_empty = extract_story_beats("")
    assert clean_empty == ""
    assert beats_empty == []

    clean_none, beats_none = extract_story_beats(None)
    assert clean_none == ""
    assert beats_none == []


def test_validate_beat_format_valid_and_invalid():
    valid = (
        "[BEAT 1: APERTURA]\n"
        "La criatura permanecía inmóvil en el centro de la cámara de pruebas.\n\n"
        "[BEAT 2: ACCION]\n"
        "Al abrir la compuerta, el espécimen reaccionó con velocidad sobrehumana."
    )
    assert validate_beat_format(valid) is True

    # Missing beat tags
    assert validate_beat_format("Texto corrido sin etiquetas de beats.") is False
    assert validate_beat_format("") is False
    assert validate_beat_format(None) is False

    # Contains system prompt leak
    prompt_leak = (
        "INSTRUCCIÓN CRÍTICA: prohibido resumir el contenido.\n"
        "[BEAT 1: HOOK]\n"
        "La criatura despertó."
    )
    assert validate_beat_format(prompt_leak) is False


def test_calculate_beat_shot_durations_distribution():
    beats = [
        {"label": "BEAT 1", "text": "Uno dos tres cuatro cinco seis siete ocho nueve diez"},
        {"label": "BEAT 2", "text": "Once doce trece catorce quince dieciséis diecisiete dieciocho diecinueve veinte"},
    ]
    word_timestamps = [
        {"word": f"word_{i}", "start": float(i), "end": float(i + 1)}
        for i in range(20)
    ]
    total_audio_duration = 20.0

    durations = calculate_beat_shot_durations(word_timestamps, beats, total_audio_duration)
    assert len(durations) == 2
    assert sum(durations) == pytest.approx(total_audio_duration, abs=0.1)
    assert all(d > 0 for d in durations)
