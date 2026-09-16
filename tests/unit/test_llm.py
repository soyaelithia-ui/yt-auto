import unittest
from unittest.mock import patch, MagicMock

from src.llm import (
    clean_title,
    compile_stories_to_target_words,
    curate_batch_json,
    curate_script,
    sanitize_text,
    translate_title,
)


class TestLLMScriptCuration(unittest.TestCase):
    """Unit tests for Story Curation & Script Generation (src/llm.py) using duck-typed custom clients."""

    def test_sanitize_text_strips_urls_links_and_edits(self):
        """Test sanitize_text removes raw URLs, markdown links, and edit notes."""
        raw_text = (
            "Check out my store at http://example.com [link](http://test.com) "
            "Edit: thanks for gold! The darkness was alive."
        )
        cleaned = sanitize_text(raw_text)
        self.assertNotIn("http://example.com", cleaned)
        self.assertNotIn("http://test.com", cleaned)
        self.assertNotIn("Edit: thanks for gold!", cleaned)
        self.assertIn("The darkness was alive.", cleaned)
        self.assertIn("link", cleaned)

    def test_sanitize_text_edge_cases(self):
        """Test sanitize_text handles None and non-string inputs gracefully."""
        self.assertEqual(sanitize_text(None), "")
        self.assertEqual(sanitize_text(123), "")
        self.assertEqual(sanitize_text(""), "")

    def test_clean_title_edge_cases(self):
        """Test clean_title strips chatter, quotes, reddit markers, and corrupt titles."""
        self.assertEqual(clean_title(None), "Relato Enigmático")
        self.assertEqual(clean_title(""), "Relato Enigmático")
        self.assertEqual(clean_title('"El Bosque Oscuro"'), "El Bosque Oscuro")
        self.assertEqual(clean_title("Aquí tienes el título: El Susurro"), "El Susurro")
        self.assertEqual(clean_title("The Haunted House [OC] (Part 1)"), "The Haunted House")
        self.assertEqual(clean_title("[RELATO DE TERROR] El Susurro | Moku"), "El Susurro")
        self.assertEqual(clean_title("[CONFESIÓN] La Boda Arruinada | Aelithia"), "La Boda Arruinada")
        self.assertEqual(clean_title("[REGISTRO ESTELAR] Paradoja Cuántica | Singularidad Sci-Fi"), "Paradoja Cuántica")
        self.assertEqual(clean_title("[MOKU] La Cabaña Abandonada"), "La Cabaña Abandonada")
        self.assertEqual(clean_title("Cookies!"), "Memorias del Olvido")
        self.assertEqual(clean_title("untitled"), "Memorias del Olvido")

    def test_curate_script_provider_c_fallback(self):
        """Test Provider C regex sanitizer fallback script curation."""
        raw_text = "The cold wind blew through the old shattered window. Edit: thanks for reading!"
        title = "The Shattered Window"

        script = curate_script(raw_text, title=title, provider="C", channel="terror")
        self.assertIn("Título: The Shattered Window.", script)
        self.assertIn("The cold wind blew through the old shattered window.", script)
        self.assertNotIn("Edit: thanks", script)

    def test_curate_script_custom_client_success(self):
        """Test curate_script delegating to a duck-typed custom client."""
        raw_text = "I heard a noise in the attic."
        title = "Attic Noise"
        mock_result = {
            "script": (
                "Título: Attic Noise.\n\n"
                "Escuché un ruido en el ático que me heló la sangre en la noche. "
                "Caminé lentamente hacia las escaleras sin saber qué criatura se ocultaba allí arriba. "
                "El sonido se hacía cada vez más fuerte y amenazante en la oscuridad. "
                "Suscríbete a Moku."
            ),
            "title": "Attic Noise",
        }

        mock_client = MagicMock()
        mock_client.curate_script.return_value = mock_result

        script = curate_script(raw_text, title=title, channel="terror", client=mock_client)
        mock_client.curate_script.assert_called_once()
        self.assertIn("Attic Noise", script)
        self.assertIn("ruido en el ático", script)

    def test_curate_script_custom_client_error_handling(self):
        """Test curate_script falls back to local regex curation when a custom client raises."""
        mock_client = MagicMock()
        mock_client.curate_script.side_effect = RuntimeError("API rate limit exceeded")

        # In test environment, it logs a warning and falls back to regex curation
        script = curate_script("Something happened in the woods", title="The Woods", channel="terror", client=mock_client)
        self.assertIn("The Woods", script)

    def test_translate_title_custom_client_success(self):
        """Test translate_title using a duck-typed custom client."""
        mock_client = MagicMock()
        mock_client.translate_title.return_value = "El Silencio de la Noche"

        res = translate_title("The Silence of the Night", client=mock_client)
        mock_client.translate_title.assert_called_once_with(title="The Silence of the Night")
        self.assertEqual(res, "El Silencio de la Noche")

    def test_translate_title_empty(self):
        """Test translate_title with empty or whitespace input."""
        self.assertEqual(translate_title(""), "Relato Enigmático")
        self.assertEqual(translate_title("   "), "Relato Enigmático")

    def test_multi_story_compilation_under_target_words(self):
        """Test multi-story compilation joining stories when word count < min_words."""
        short_main = "Story 1 text. " * 50  # 100 words
        add_story_1 = {"title": "The Cellar", "content": "Story 2 text. " * 400}  # 800 words
        add_story_2 = {"title": "The Attic", "content": "Story 3 text. " * 400}  # 800 words

        comp_title, comp_content = compile_stories_to_target_words(
            main_title="The Basement",
            main_content=short_main,
            additional_stories=[add_story_1, add_story_2],
            min_words=1500,
            channel="terror"
        )

        words = comp_content.split()
        self.assertGreaterEqual(len(words), 1500)
        self.assertIn("The Cellar", comp_content)
        self.assertIn("The Attic", comp_content)

    def test_curate_batch_json_success(self):
        """Test curate_batch_json builds script and metadata from a duck-typed custom client."""
        mock_client = MagicMock()
        mock_client.curate_script.return_value = {
            "script": (
                "Título: La Casa Maldita.\n\n"
                "El expediente de la Fundación señala que la casa maldita permaneció sellada durante décadas "
                "y que ningún agente está autorizado a ingresar en el perímetro de observación esta noche. "
                "Las grabaciones revelan sonidos inexplicables que se intensifican cuando los visitantes se acercan "
                "a la puerta principal. Nadie debe cruzar el umbral. Suscríbete."
            ),
            "title": "La Casa Maldita",
        }

        res = curate_batch_json("Algo terrible paso...", title="La Casa Maldita", channel="terror", client=mock_client)
        self.assertEqual(res["title"], "La Casa Maldita")
        self.assertIn("script", res)
        self.assertIn("La Casa Maldita", res["script"])
        self.assertTrue(res.get("description"))
        self.assertIn("tags", res)
        self.assertIn("thumbnail_prompt", res)

    def test_curate_batch_json_custom_client_failure(self):
        """Test curate_batch_json degrades gracefully when the custom client raises."""
        mock_client = MagicMock()
        mock_client.curate_script.side_effect = RuntimeError("Service unavailable")

        res = curate_batch_json("Some text", title="Test", channel="terror", client=mock_client)
        self.assertEqual(res["title"], "Test")
        self.assertIn("script", res)
        self.assertIn("Test", res["script"])
        self.assertIsNotNone(res.get("description"))

    def test_curate_script_uses_queued_narrative_when_ab_down(self):
        narrative = (
            "Si ves su cara ya estás muerto. El chico tímido persigue al observador "
            "a través de continentes enteros sin importar el blindaje de acero. "
            "Derribará instalaciones subterráneas enteras a velocidades sobrehumanas "
            "hasta eliminar a su objetivo sin dejar escapatoria posible."
        )
        self.assertGreaterEqual(len(narrative.split()), 40)
        with patch("src.config.is_test_environment", return_value=False), \
             patch("src.llm._curate_with_agent", return_value=None), \
             patch("src.llm._curate_with_gemini", return_value=None):
            script = curate_script(
                narrative,
                title="SCP-096: no lo mires a la cara",
                provider=None,
                channel="moku",
                min_words=40,
            )
        self.assertIn("observador a través", script)
        self.assertNotIn("Edit:", script)
        self.assertFalse(script.startswith("Título:"))

    def test_expand_narrative_to_target_words_scp(self):
        from src.llm import _expand_narrative_to_target_words
        short_text = "SCP-096 es una criatura peligrosa en contención."
        expanded = _expand_narrative_to_target_words(
            main_title="SCP-096",
            main_content=short_text,
            min_words=180,
            max_words=250,
            channel="moku",
        )
        self.assertGreaterEqual(len(expanded.split()), 180)
        self.assertTrue(expanded.startswith(short_text))

    def test_expand_narrative_to_target_words_already_long(self):
        from src.llm import _expand_narrative_to_target_words
        text = " ".join(["palabra"] * 210)
        res = _expand_narrative_to_target_words("SCP-096", text, 200, 250, "moku")
        self.assertEqual(res, text)


if __name__ == "__main__":
    unittest.main()
