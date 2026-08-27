import unittest
from unittest.mock import patch, MagicMock

from src.llm import curate_script


class TestLLMAdversarialEdgeCases(unittest.TestCase):
    """Adversarial edge-case tests for the custom-client provider in src/llm.py."""

    def test_curate_script_end_to_end_graceful_degradation(self):
        """Test curate_script degrades to Provider C (regex) when a custom client fails in test mode."""
        raw_text = "The abandoned mansion stood silent on the hill. Edit: deleted user"
        title = "The Mansion"

        mock_client = MagicMock()
        mock_client.curate_script.side_effect = RuntimeError("API down")

        script = curate_script(raw_text, title=title, client=mock_client)
        self.assertIsNotNone(script)
        self.assertIn("Título: The Mansion.", script)
        self.assertIn("The abandoned mansion stood silent on the hill.", script)
        self.assertNotIn("Edit: deleted user", script)


if __name__ == "__main__":
    unittest.main()
