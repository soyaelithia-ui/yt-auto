"""tests/unit/test_modular_sanitizer_scraper.py - Unit tests verifying Phase 2 modular packages."""

import pytest
from src.sanitizer.editorial import (
    check_forbidden_editorial_elements,
    repair_forbidden_editorial,
    sanitize_llm_script,
    suppress_title_repetition,
)
from src.sanitizer.filesystem import sanitize_filename
from src.sanitizer.hashing import compute_simhash_64, evaluate_script_simhash, hamming_distance_64
from src.sanitizer.linguistic import (
    TextSanitizer,
    filter_orphan_english_blocks,
    normalize_spanglish_terms,
    sanitize_html_entities,
    sanitize_text,
)
from src.sanitizer.security import (
    PromptLeakError,
    extract_script_from_reasoning,
    strip_llm_prompt_leaks,
    validate_semantic_barrier,
)
from src.sanitizer.tts import (
    limpiar_texto_para_tts,
    sanitize_scp_acronyms_for_tts,
    standardize_timestamp_format,
    strip_act_chapter_headers,
    strip_ass_tags,
    validate_pre_tts_script,
)
from src.scrapers.common import AsyncRateLimiter, _run_sync, _to_float, _to_int
from src.scrapers.local import PRESET_CANONICAL_STORIES, _load_canonical_stories, _parse_frontmatter
from src.scrapers.models import ScrapedStory
from src.scrapers.reddit import (
    DEFAULT_USER_AGENT,
    USER_AGENTS,
    async_fetch_reddit_stories,
    fetch_reddit_stories,
    is_high_quality_story,
)
from src.scrapers.replenisher import (
    async_ensure_queue_depth,
    async_replenish_queue,
    ensure_queue_depth,
    replenish_queue,
)
from src.scrapers.scp import (
    CANONICAL_SCP_STORIES,
    DEFAULT_LICENSE,
    async_fetch_scp_by_item,
    async_fetch_top_scp_articles,
    fetch_scp_by_item,
    fetch_top_scp_articles,
    parse_scp_text,
    parse_scp_wikidot_html,
)


class TestModularSanitizerPackage:
    """Test suite directly importing and verifying src.sanitizer submodules."""

    def test_filesystem_sanitizer(self):
        cleaned = sanitize_filename("my / invalid : file * name ?.txt")
        assert "/" not in cleaned
        assert ":" not in cleaned
        assert "*" not in cleaned
        assert "?" not in cleaned
        assert len(cleaned) <= 100

    def test_hashing_submodule(self):
        text1 = "El bosque estaba cubierto por una densa niebla."
        text2 = "El bosque estaba cubierto por una densa niebla oscura."
        h1 = compute_simhash_64(text1)
        h2 = compute_simhash_64(text2)
        dist = hamming_distance_64(h1, h2)
        assert isinstance(dist, int)
        assert evaluate_script_simhash(text1, history_hashes=[h2], min_hamming_distance=100) is False
        assert evaluate_script_simhash(text1, history_hashes=[h2], min_hamming_distance=0) is True

    def test_security_submodule(self):
        with pytest.raises(PromptLeakError):
            validate_semantic_barrier("Aquí tienes tu guion para el locutor")
        assert validate_semantic_barrier("Una historia normal y limpia.") is True

        reasoning = "<think>Analizando el prompt...</think>La criatura surgió de la oscuridad."
        extracted = extract_script_from_reasoning(reasoning)
        assert "Analizando" not in extracted
        assert "La criatura surgió" in extracted

    def test_tts_submodule(self):
        ass_text = r"{\pos(100,200)\k50}Texto con subtitulos"
        assert strip_ass_tags(ass_text) == "Texto con subtitulos"

        scp_text = "SCP-173 y SCP-096 fueron contenidos."
        assert sanitize_scp_acronyms_for_tts(scp_text) == "S-C-P 173 y S-C-P 096 fueron contenidos."

        cleaned_tts = limpiar_texto_para_tts("### Capítulo 1: El Inicio\nTexto de narración.")
        assert "Capítulo 1" not in cleaned_tts
        assert "Texto de narración." in cleaned_tts

    def test_editorial_submodule(self):
        text_with_cues = "Bienvenidos a mi canal. La noche era oscura. Suscríbete y dale like."
        repaired, dropped = repair_forbidden_editorial(text_with_cues)
        assert "Bienvenidos" not in repaired
        assert "Suscríbete" not in repaired
        assert "La noche era oscura." in repaired
        assert len(dropped) >= 2

    def test_linguistic_submodule(self):
        html_input = "Texto con &nbsp; y &amp; m&aacute;s."
        cleaned_html = sanitize_html_entities(html_input)
        assert "&nbsp;" not in cleaned_html
        assert "&amp;" not in cleaned_html

        spanglish_input = "La holding cell tenía concreto reinforced."
        normalized = normalize_spanglish_terms(spanglish_input)
        assert "celda de contención" in normalized
        assert "concreto reforzado" in normalized


class TestModularScraperPackage:
    """Test suite directly importing and verifying src.scrapers submodules."""

    def test_scraped_story_model_and_dict_conversion(self):
        story = ScrapedStory(
            id="test_001",
            title="A horrifying night",
            content="Full story body content text.",
            score=500,
            upvote_ratio=0.98,
        )
        assert story.story_id == "test_001"
        assert story.selftext == "Full story body content text."

        story_dict = story.to_dict()
        assert story_dict["id"] == "test_001"
        assert story_dict["score"] == 500
        assert story_dict["format"] == "short"

        reconstructed = ScrapedStory.from_dict(story_dict)
        assert reconstructed.id == story.id
        assert reconstructed.title == story.title
        assert reconstructed.content == story.content

    def test_common_converters_and_rate_limiter(self):
        assert _to_int("42") == 42
        assert _to_int("invalid", default=10) == 10
        assert _to_float("3.14") == 3.14
        assert _to_float(None, default=1.0) == 1.0

        limiter = AsyncRateLimiter(max_concurrent=2, rate_limit_per_second=100.0)
        assert limiter.rate_limit == 100.0

    def test_local_canonical_loader(self):
        stories = _load_canonical_stories(min_length=10, limit=50)
        assert len(stories) > 2  # Proves real disk files from data/worksets/canonical/ were loaded, not just presets
        assert "title" in stories[0]
        assert "content" in stories[0]

    def test_scp_parser_and_canonical(self):
        assert len(CANONICAL_SCP_STORIES) >= 5
        raw = "Ítem #: SCP-999\nClase de Objeto: Safe\n\nProcedimientos Especiales de Contención:\nLibre.\n\nDescripción:\nGelatina naranja."
        parsed = parse_scp_text(raw)
        assert parsed["id"] == "SCP-999"
        assert parsed["object_class"] == "Safe"
        assert "Gelatina" in parsed["description"]
