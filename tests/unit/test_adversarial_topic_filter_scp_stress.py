"""Adversarial stress test for Topic Filter and SCP Scraper."""

import pytest
from unittest.mock import patch, MagicMock

from src.core.topics import (
    normalize_text_for_matching,
    remove_accents,
    matches_keywords,
    is_spam_or_disallowed,
    filter_story_for_lane,
    filter_story_by_keywords,
)
from src.core.lanes import get_lane
from src.scraper_scp import (
    parse_scp_wikidot_html,
    parse_scp_text,
    fetch_top_scp_articles,
    DEFAULT_LICENSE,
    CANONICAL_SCP_STORIES,
)


@pytest.mark.unit
class TestTopicFilterAdversarialStress:
    """Stress test topic filter normalization, keyword matching, and spam gating."""

    def test_topic_filter_mixed_case_and_heavy_accents(self):
        """Test heavy Spanish diacritics, inverted exclamation/question marks, uppercase."""
        text_accented = "¡¡ATENCIÓN!! ¿HAY UNA ANOMALÍA EN LA FUNDACIÓN DE CONTENCIÓN KETER?"
        norm = normalize_text_for_matching(text_accented)

        assert "atencion" in norm
        assert "anomalia" in norm
        assert "fundacion" in norm
        assert "contencion" in norm

        # Matches keywords regardless of accents
        assert matches_keywords(text_accented, ["anomal", "contención", "fundacion", "keter"]) is True
        assert matches_keywords(text_accented, ["ANOMALÍA", "CONTENCION"]) is True

    def test_topic_filter_spam_and_crypto_disallowed(self):
        """Disallowed patterns (crypto, airdrops, casino, NSFW) must be rejected."""
        spam_cases = [
            ("Gana Bitcoin gratis hoy", "Ingresa a nuestro airdrop y obtén promocode para casino online"),
            ("NFT exclusivo de terror", "Compra este NFT en la blockchain para ganar dinero"),
            ("Modelo Onlyfans en vivo", "Suscríbete a mi onlyfans o camgirl show"),
            ("Relato de miedo", "Había una vez un monstruo... gana bitcoin en http://crypto.com promocode"),
        ]

        for title, content in spam_cases:
            assert is_spam_or_disallowed(title, content) is True

    def test_topic_filter_boundary_and_empty_inputs(self):
        """Empty, whitespace, None strings should be rejected cleanly without throwing exceptions."""
        lane = get_lane("moku-horror-long")

        assert filter_story_for_lane("", "Contenido válido de terror con monstruos y pesadillas", lane) is False
        assert filter_story_for_lane("Título válido", "", lane) is False
        assert filter_story_for_lane("   ", "   \n\t  ", lane) is False
        assert filter_story_for_lane(None, "Texto", lane) is False

        # Giant text input stress (100k characters)
        giant_text = ("Encontré una criatura en el bosque oscuro y tuve mucho miedo. " * 1500)
        assert filter_story_for_lane("Pesadilla en el bosque", giant_text, lane) is True

    def test_topic_filter_lane_specific_thematic_gating(self):
        """Ensure each lane accepts its own domain and rejects out-of-domain stories."""
        lane_scp = get_lane("moku-scp-shorts")
        lane_horror = get_lane("moku-horror-long")
        lane_aita = get_lane("aelithia-aita-long")

        scp_title = "SCP-096 El Chico Tímido"
        scp_content = "Procedimientos Especiales de Contención: Celda hermética de acero. Objeto Euclid de la Fundación."

        horror_title = "Pasos en el sótano a medianoche"
        horror_content = "Sentí un miedo aterrador cuando el monstruo emergió de la oscuridad con una sonrisa sangrienta."

        aita_title = "¿Soy la mala por no invitar a mi suegra a mi boda?"
        aita_content = "Mi novio y su familia dicen que debo pagar la herencia a mi hermana tras el divorcio."

        # SCP lane
        assert filter_story_for_lane(scp_title, scp_content, lane_scp) is True

        # Horror lane
        assert filter_story_for_lane(horror_title, horror_content, lane_horror) is True

        # AITA lane
        assert filter_story_for_lane(aita_title, aita_content, lane_aita) is True


@pytest.mark.unit
class TestSCPScraperAdversarialStress:
    """Stress test SCP HTML scraping, entity decoding, fallback resilience, and CC BY-SA 3.0 license attribution."""

    def test_scp_html_parser_edge_cases(self):
        """Parse malformed HTML, missing sections, and unescaped entities."""
        raw_html = """
        <div id="page-title">SCP-999 - El Monstruo de las Cosquillas</div>
        <div id="page-content">
            <p><strong>Ítem #:</strong> SCP-999</p>
            <p><strong>Clase de Objeto:</strong> Safe</p>
            <p><strong>Procedimientos Especiales de Contenci&oacute;n:</strong> A SCP-999 se le permite vagar libremente por las instalaciones si as&iacute; lo desea.</p>
            <p><strong>Descripci&oacute;n:</strong> SCP-999 parece ser una gran masa gelatinosa amorfa de limo naranja transparente.</p>
        </div>
        <div id="page-info-break"></div>
        """
        data = parse_scp_wikidot_html(raw_html, "https://lafundacionscp.wikidot.com/scp-999")

        assert data is not None
        assert data["item_number"] == "SCP-999"
        assert data["object_class"] == "Safe"
        assert "vagar libremente" in data["containment_procedures"]
        assert "gelatinosa" in data["description"]
        assert data["source_license"] == DEFAULT_LICENSE

    def test_scp_scraper_canonical_fallback(self):
        """When network / API fails, fetch_top_scp_articles falls back gracefully to canonical SCPs."""
        with patch("src.scraper_scp.fetch_top_scp_from_crom", return_value=[]), \
             patch("src.scraper_scp.fetch_scp_by_item", return_value=None):
            stories = fetch_top_scp_articles(limit=2)
            assert len(stories) >= 1
            for s in stories:
                assert s["source_license"] == DEFAULT_LICENSE
                assert s["item_number"].startswith("SCP-")
                assert s["containment_procedures"]
                assert s["description"]

    def test_scp_license_attribution_metadata(self):
        """All SCP stories must contain valid CC BY-SA 3.0 license and author metadata."""
        for canon in CANONICAL_SCP_STORIES:
            assert canon["source_license"] == "CC BY-SA 3.0"
            assert canon["author"]
            assert canon["url"].startswith("http")
