"""Unit tests for src/core/topic_filter.py."""

import pytest
from src.core.lanes import LaneProfile, LaneSources, parse_lane
from src.core.topics import (
    count_keyword_matches,
    filter_story_by_keywords,
    filter_story_for_lane,
    get_default_keywords_for_story_type,
    is_spam_or_disallowed,
    is_story_appropriate_for_theme,
    matches_keywords,
    normalize_text_for_matching,
    remove_accents,
    score_story_relevance,
)


@pytest.fixture
def scp_lane():
    return parse_lane({
        "id": "moku-scp-shorts",
        "channel": "moku",
        "story_type": "scp",
        "orientation": "vertical",
        "duration": {"min_sec": 60, "target_sec": 150, "max_sec": 180},
        "words": {"min": 160, "max": 340, "recondense_max": 300},
        "template": "shorts_creepypasta",
        "voice_rate": "+20%",
        "cadence": {"min_gap_seconds": 300},
        "sources": {
            "kind": "reddit",
            "subreddits": ["SCP", "SCPDeclassified"],
            "listing_categories": [["hot", "day"], ["top", "week"]],
        },
        "topic_filter": {
            "mode": "keyword",
            "keywords": ["scp", "anomal", "contención", "fundación"],
        },
    })


@pytest.fixture
def aita_lane():
    return parse_lane({
        "id": "aelithia-aita-long",
        "channel": "aelithia",
        "story_type": "reddit_aita",
        "orientation": "horizontal",
        "duration": {"min_sec": 600, "target_sec": 600, "max_sec": 1800},
        "words": {"min": 2600, "max": None},
        "template": "aita",
        "voice_rate": "+0%",
        "cadence": {"min_gap_seconds": 1800},
        "sources": {
            "kind": "reddit",
            "subreddits": ["AmItheAsshole", "TrueOffMyChest"],
        },
        "topic_filter": {
            "mode": "keyword",
            "keywords": ["aita", "wibta", "soy el malo", "familia", "boda", "herencia"],
        },
    })


@pytest.fixture
def horror_lane_off():
    return parse_lane({
        "id": "moku-horror-long",
        "channel": "moku",
        "story_type": "horror",
        "orientation": "horizontal",
        "duration": {"min_sec": 600, "target_sec": 600, "max_sec": 1800},
        "words": {"min": 2600, "max": None},
        "template": "creepypasta",
        "voice_rate": "+0%",
        "cadence": {"min_gap_seconds": 1800},
        "sources": {
            "kind": "reddit",
            "subreddits": ["nosleep"],
        },
        "topic_filter": {
            "mode": "off",
        },
    })


class TestTopicFilterNormalization:
    def test_remove_accents(self):
        assert remove_accents("Contención") == "Contencion"
        assert remove_accents("anomalía") == "anomalia"
        assert remove_accents("¿Él está aquí?") == "¿El esta aqui?"

    def test_normalize_text_for_matching(self):
        assert normalize_text_for_matching("¡SCP-096 Contención!") == "scp-096 contencion"
        assert normalize_text_for_matching("¿Soy el malo?") == "soy el malo"
        assert normalize_text_for_matching("") == ""


class TestKeywordMatching:
    def test_matches_keywords_positive(self):
        text = "El objeto fue trasladado a la celda de contención de la Fundación."
        assert matches_keywords(text, ["contención", "scp"])
        assert matches_keywords(text, ["contencion"])  # Accent-insensitive

    def test_matches_keywords_negative(self):
        text = "Una simple receta de cocina para hacer panqueques."
        assert not matches_keywords(text, ["scp", "anomalia", "keter"])

    def test_count_keyword_matches(self):
        text = "SCP-173 es una anomalía Keter que requiere contención en la Fundación."
        keywords = ["scp", "anomal", "keter", "contención", "fundación", "inexistente"]
        count = count_keyword_matches(text, keywords)
        assert count == 5

    def test_score_story_relevance_weights_title_higher(self):
        title_with_keyword = "SCP-096: Informe de la Fundación"
        content_generic = "Texto largo sobre un experimento en el laboratorio subterráneo."
        score1 = score_story_relevance(title_with_keyword, content_generic, ["scp", "fundación"])

        title_generic = "Informe de laboratorio"
        content_with_keywords = "SCP y fundación mencionados solo aquí."
        score2 = score_story_relevance(title_generic, content_with_keywords, ["scp", "fundación"])

        # Title match (2 keywords * 3.0 = 6.0) > content match (2 keywords * 1.0 = 2.0)
        assert score1 > score2


class TestFilterStoryForLane:
    def test_filter_story_for_lane_off_mode_accepts_valid_story(self, horror_lane_off):
        title = "El sonido bajo mi cama"
        content = "Era medianoche cuando escuché un rasguño inquietante."
        assert filter_story_for_lane(title, content, horror_lane_off) is True

    def test_filter_story_for_lane_empty_rejected(self, horror_lane_off):
        assert filter_story_for_lane("", "Contenido", horror_lane_off) is False
        assert filter_story_for_lane("Título", "", horror_lane_off) is False

    def test_filter_story_for_lane_spam_rejected(self, horror_lane_off):
        title = "Claim your free Bitcoin crypto airdrop now!"
        content = "Visit casino promocode link below."
        assert filter_story_for_lane(title, content, horror_lane_off) is False

    def test_filter_story_for_scp_lane_matching(self, scp_lane):
        title = "SCP-096: Procedimientos de Contención"
        content = "La entidad anómala se encuentra asegurada en el Sitio-19."
        assert filter_story_for_lane(title, content, scp_lane) is True

    def test_filter_story_for_scp_lane_non_matching(self, scp_lane):
        title = "Mi novio olvidó mi cumpleaños"
        content = "Tuvimos una discusión sobre la cena familiar."
        assert filter_story_for_lane(title, content, scp_lane) is False

    def test_filter_story_for_aita_lane_matching(self, aita_lane):
        title = "¿Soy el malo por negarme a pagar la boda de mi hermana?"
        content = "Mi familia dice que soy egoísta con el dinero de la herencia."
        assert filter_story_for_lane(title, content, aita_lane) is True

    def test_filter_story_for_aita_lane_non_matching(self, aita_lane):
        title = "Criatura acechando en el bosque"
        content = "Un monstruo con garras apareció entre la niebla."
        assert filter_story_for_lane(title, content, aita_lane) is False


class TestStoryThemeAppropriateness:
    def test_is_story_appropriate_for_theme_scp(self):
        assert is_story_appropriate_for_theme("Informe SCP-682", "Criatura Keter hostil", "scp")
        assert not is_story_appropriate_for_theme("Receta de pastel", "Ingredientes para tarta", "scp")

    def test_is_story_appropriate_for_theme_aita(self):
        assert is_story_appropriate_for_theme("AITA for leaving the party", "My spouse was mad", "reddit_aita")
        assert not is_story_appropriate_for_theme("The dark forest", "A shadow appeared in the graveyard", "reddit_aita")

    def test_is_story_appropriate_for_theme_horror(self):
        assert is_story_appropriate_for_theme("La pesadilla del cementerio", "Había sangre y oscuridad", "horror")
        assert not is_story_appropriate_for_theme("Consejos de finanzas", "Cómo ahorrar dinero", "horror")
