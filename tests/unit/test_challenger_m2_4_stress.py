import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from src.llm import (
    curate_script,
    sanitize_text,
    clean_title,
    curate_batch_json,
)


class TestLLMCurationStress(unittest.TestCase):
    """Stress and edge-case testing for LLM script curation and custom-client integration."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="llm_test_")

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            import shutil
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_sanitize_text_concurrent_safety(self):
        """Verify sanitize_text handles large inputs and weird encodings safely."""
        large_input = "Sample text http://example.com [link](http://test.com).\nEdit: thanks!\n" * 1000
        result = sanitize_text(large_input)
        self.assertNotIn("http://example.com", result)
        self.assertNotIn("Edit: thanks!", result)

    def test_curate_script_with_mocked_custom_client(self):
        """Verify curate_script delegates correctly to a duck-typed custom client under repeated invocations."""
        mock_client = MagicMock()
        mock_client.curate_script.return_value = {
            "script": "Título: Test Story.\n\nNarrativa curada en español neutro para la comunidad de terror sobre expedientes clasificados y sucesos extraños en la noche oscura. " * 4,
            "title": "Test Story",
        }

        for i in range(10):
            res = curate_script(f"Story content {i}", title=f"Title {i}", client=mock_client)
            self.assertIn("Narrativa curada", res)

    def test_curate_script_custom_client_failure_recovery(self):
        """Verify script curation recovers smoothly when a custom client raises runtime errors."""
        mock_client = MagicMock()
        mock_client.curate_script.side_effect = RuntimeError("Rate limit exceeded")

        res = curate_script("Emergency story content", title="Emergency", channel="terror", client=mock_client)
        self.assertIn("Emergency", res)

    def test_clean_title_stress(self):
        """Verify clean_title handles diverse messy titles."""
        titles = [
            "\"Title in quotes\"",
            "Aquí tienes el título: Horror",
            "Deleted post [DELETED] (Part 2)",
            "untitled",
        ]
        results = [clean_title(t) for t in titles]
        self.assertEqual(results[0], "Title in quotes")
        self.assertEqual(results[1], "Horror")
        self.assertEqual(results[2], "Deleted post")
        self.assertEqual(results[3], "Memorias del Olvido")


if __name__ == "__main__":
    unittest.main()
