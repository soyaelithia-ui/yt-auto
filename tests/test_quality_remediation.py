import os
import pytest
from pathlib import Path
from PIL import Image

from src.media.thumbnail_engine import ResilientThumbnailEngine
from src.audio_processor import sanitize_script_for_tts
from src.agents.seo_optimizer import SeoOptimizerAgent
from src.agents.qa_auditor import VisualAudioQAAuditorAgent


def test_thumbnail_engine_generates_valid_image(tmp_path):
    engine = ResilientThumbnailEngine()
    out_file = tmp_path / "test_thumb.jpg"
    res = engine.generate(
        output_path=out_file,
        title_main="SCP-2000",
        title_sub="DEUS EX MACHINA",
        highlight_box="EL REINICIO DE LA HUMANIDAD",
        badge_text="NIVEL 5 // CLASIFICADO",
    )
    assert res.is_file()
    assert res.stat().st_size > 30 * 1024  # Size > 30 KB
    img = Image.open(res)
    assert img.size == (1280, 720)
    assert img.mode == "RGB"


def test_sanitize_script_for_tts():
    raw = """
    Acto Uno: La Ciudadela Olvidada en las Profundidades.
    En el Sitio SCP-2000, las unidades BZHR y los estabilizadores XACTS operan bajo orden del Consejo O5 en un escenario XK.
    Capítulo 2: La Clonación Masiva.
    """
    cleaned = sanitize_script_for_tts(raw)
    assert "Acto Uno:" not in cleaned
    assert "Capítulo 2:" not in cleaned
    assert "S-C-P 2000" in cleaned
    assert "B-Z-H-R" in cleaned
    assert "X-ACTS" in cleaned
    assert "O-5" in cleaned
    assert "X-K" in cleaned


def test_seo_synchronized_timestamps():
    acts = [
        {"start_sec": 0.0, "title": "Acto 1: Introducción al Búnker"},
        {"start_sec": 120.0, "title": "Acto 2: Clonación BZHR"},
        {"start_sec": 300.0, "title": "Acto 3: Conclusión"},
        {"start_sec": 900.0, "title": "Acto 4: Fuera de rango"},
    ]
    total_dur = 400.0
    synced = SeoOptimizerAgent.build_synchronized_timestamps(acts, total_dur)
    assert "00:00 - Introducción al Búnker" in synced
    assert "02:00 - Clonación BZHR" in synced
    assert "05:00 - Conclusión" in synced
    assert "15:00" not in synced  # 900s should be excluded because > 400s

    valid, errors = SeoOptimizerAgent.validate_description_timestamps(synced, total_dur)
    assert valid is True
    assert len(errors) == 0

    bad_description = "TIMESTAMPS:\n00:00 Inicio\n10:00 Fuera de tiempo"
    valid_bad, errors_bad = SeoOptimizerAgent.validate_description_timestamps(bad_description, 300.0)
    assert valid_bad is False
    assert len(errors_bad) == 1


def test_qa_auditor_thumbnail_and_timestamps(tmp_path):
    auditor = VisualAudioQAAuditorAgent()
    engine = ResilientThumbnailEngine()
    thumb_path = tmp_path / "valid_thumb.jpg"
    engine.generate(output_path=thumb_path, title_main="TEST SCP")

    t_pass, t_errs = auditor.audit_thumbnail(thumb_path)
    assert t_pass is True
    assert len(t_errs) == 0

    # Test invalid timestamp audit
    desc = "TIMESTAMPS:\n00:00 Inicio\n15:30 Final"
    ts_pass, ts_errs = auditor.audit_description_timestamps(desc, 600.0)
    assert ts_pass is False
    assert len(ts_errs) > 0