"""
tests/unit/test_outro_sanitizer.py - Unit tests for deterministic outro & boilerplate script sanitization.
"""
import pytest
from src.sanitizer import (
    FORBIDDEN_EDITORIAL_PATTERNS,
    repair_forbidden_editorial,
    validate_pre_tts_script,
)


class TestOutroSanitizer:
    def test_drops_moku_reddit_archive_outro(self):
        dirty_script = (
            "La criatura permanecía inmóvil en la esquina del túnel. "
            "Sentí cómo el aire se congelaba en mis pulmones. "
            "Todos los expedientes y archivos se encuentran en Moku Reddit*."
        )
        cleaned, _ = repair_forbidden_editorial(dirty_script)
        assert "Moku Reddit" not in cleaned
        assert "expedientes y archivos se encuentran en" not in cleaned
        assert "La criatura permanecía inmóvil" in cleaned

    def test_drops_custody_and_archive_boilerplate(self):
        texts_to_clean = [
            "Permanecen archivados bajo estricta custodia.",
            "Se encuentran archivados bajo estricta custodia en el sitio 19.",
            "Todos los relatos y grabaciones se encuentran en @MokuRedit.",
            "Para más historias síguenos en @Aelithia.",
        ]
        for t in texts_to_clean:
            cleaned, _ = repair_forbidden_editorial(t)
            assert "estricta custodia" not in cleaned
            assert "@MokuRedit" not in cleaned
            assert "@Aelithia" not in cleaned

    def test_drops_hyphenated_and_dynamic_handles(self):
        texts = [
            "Para más relatos suscríbete a @Aelithia-c1f ahora mismo.",
            "Visita @canal-relatos-2026 para el siguiente episodio.",
        ]
        for t in texts:
            cleaned, _ = repair_forbidden_editorial(t)
            assert "@Aelithia-c1f" not in cleaned
            assert "@canal-relatos-2026" not in cleaned

    def test_preserves_valid_narrative_context(self):
        clean_narrative = (
            "El archivo confidencial fue encontrado en el sótano del hospital. "
            "Nadie sobrevivió para contar lo ocurrido esa noche en la estación."
        )
        cleaned, _ = repair_forbidden_editorial(clean_narrative)
        assert "archivo confidencial" in cleaned
        assert "estación" in cleaned

    def test_drops_meta_channel_and_video_references(self):
        dirty_meta = (
            "La puerta blindada cedió lentamente en la oscuridad. "
            "En este video veremos los testimonios más oscuros de nuestro canal. "
            "El silencio se apoderó de los pasillos."
        )
        cleaned, removed = repair_forbidden_editorial(dirty_meta)
        assert "este video" not in cleaned.lower()
        assert "nuestro canal" not in cleaned.lower()
        assert "La puerta blindada cedió lentamente" in cleaned
        assert "El silencio se apoderó de los pasillos" in cleaned
        assert len(removed) == 1

    def test_drops_channel_brand_names_and_contextual_intros(self):
        texts_to_clean = [
            ("Soy Aelithia y hoy les contaré la historia de mi familia.", "Aelithia"),
            ("Bienvenidos a Singularidad Sci-Fi para explorar el cosmos.", "Singularidad Sci-Fi"),
            ("Todos los casos documentados en Moku permanecen sellados.", "Moku"),
        ]
        for text, brand in texts_to_clean:
            cleaned, removed = repair_forbidden_editorial(text)
            assert brand not in cleaned
            assert len(removed) >= 1

    def test_preserves_scientific_common_nouns_like_singularidad(self):
        scientific_script = (
            "La sonda espacial atravesó el disco de acreción sin sufrir daños estructurales. "
            "Al aproximarse a la singularidad del agujero negro, las ecuaciones físicas colapsaron. "
            "El horizonte de sucesos distorsionó la luz de las estrellas circundantes."
        )
        cleaned, removed = repair_forbidden_editorial(scientific_script)
        assert "singularidad del agujero negro" in cleaned
        assert len(removed) == 0
        assert cleaned == scientific_script
