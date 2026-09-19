"""
tests/unit/test_template_loader.py - Comprehensive Unit Tests for Template Loader.

Verifies LRU caching, path traversal prevention, error handling,
and robust paragraph rendering.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.templates.loader import (
    TEMPLATES_DIR,
    clear_template_cache,
    load_template_json,
    render_paragraphs,
)


class TestTemplateLoader:
    def setup_method(self) -> None:
        clear_template_cache()

    def teardown_method(self) -> None:
        clear_template_cache()

    def test_load_template_json_success(self) -> None:
        """Valid JSON template loads as dict with expected keys."""
        data = load_template_json("narratives_scifi.json")
        assert isinstance(data, dict)
        assert "short_hook" in data
        assert "longform_paragraphs" in data

    def test_load_template_json_lru_caching(self) -> None:
        """Subsequent loads of the same template hit the in-memory LRU cache."""
        clear_template_cache()
        load_template_json("narratives_scifi.json")
        info1 = load_template_json.cache_info()
        assert info1.hits == 0

        load_template_json("narratives_scifi.json")
        info2 = load_template_json.cache_info()
        assert info2.hits == 1

    def test_load_template_json_missing_file_raises_not_found(self) -> None:
        """Attempting to load a non-existent template raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Template file not found"):
            load_template_json("non_existent_story_template_xyz123.json")

    def test_load_template_json_path_traversal_blocked(self) -> None:
        """Attempting to traverse outside config/templates/ raises ValueError."""
        with pytest.raises(ValueError, match="path traversal"):
            load_template_json("../../etc/passwd")

        with pytest.raises(ValueError, match="path traversal"):
            load_template_json("../config.py")

    def test_load_template_json_invalid_json_raises_value_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Corrupted JSON files raise an informative ValueError."""
        fake_templates_dir = tmp_path / "templates"
        fake_templates_dir.mkdir(parents=True)
        bad_json_file = fake_templates_dir / "broken.json"
        bad_json_file.write_text("{ unclosed json: ", encoding="utf-8")

        monkeypatch.setattr("src.templates.loader.TEMPLATES_DIR", fake_templates_dir)
        clear_template_cache()

        with pytest.raises(ValueError, match="contains invalid JSON"):
            load_template_json("broken.json")

    def test_clear_template_cache_resets_lru(self) -> None:
        """clear_template_cache resets LRU cache statistics."""
        load_template_json("narratives_scifi.json")
        load_template_json("narratives_scifi.json")
        assert load_template_json.cache_info().hits >= 1

        clear_template_cache()
        assert load_template_json.cache_info().hits == 0
        assert load_template_json.cache_info().currsize == 0


class TestRenderParagraphs:
    def test_render_paragraphs_basic_substitution(self) -> None:
        """Substitutes placeholders cleanly."""
        paras = ["Hello {name}!", "Welcome to {place}."]
        result = render_paragraphs(paras, {"name": "Alice", "place": "Wonderland"})
        assert result == "Hello Alice!\n\nWelcome to Wonderland."

    def test_render_paragraphs_multiple_occurrences(self) -> None:
        """Replaces all occurrences of the same placeholder in a paragraph."""
        paras = ["{topic} is great. Truly {topic}."]
        result = render_paragraphs(paras, {"topic": "Science"})
        assert result == "Science is great. Truly Science."

    def test_render_paragraphs_empty_or_none(self) -> None:
        """Empty or None paragraph sequences return empty string."""
        assert render_paragraphs([], {"topic": "test"}) == ""
        assert render_paragraphs(None, {"topic": "test"}) == ""

    def test_render_paragraphs_handles_none_and_non_string_elements(self) -> None:
        """None elements in paragraph list are skipped and non-strings coerced."""
        paras = ["First line.", None, 42, "Last line."]
        result = render_paragraphs(paras, {})
        assert result == "First line.\n\n42\n\nLast line."

    def test_render_paragraphs_preserves_unmatched_placeholders(self) -> None:
        """Unmatched curly brace expressions are preserved without raising KeyError."""
        paras = ["This has {unknown_key} and {0} formatted text."]
        result = render_paragraphs(paras, {"topic": "Astrophysics"})
        assert "{unknown_key}" in result
        assert "{0}" in result
