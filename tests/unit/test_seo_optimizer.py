"""Unit tests for SeoOptimizerAgent (Agent 6 - SEO & Viral Metadata Optimizer)."""
import unittest
import jsonschema

from src.agents.seo_optimizer import SeoOptimizerAgent, SCHEMA_PATH


class TestSeoOptimizerAgent(unittest.TestCase):

    def setUp(self):
        self.optimizer = SeoOptimizerAgent()

    def test_schema_validity(self):
        """SEO schema itself must be a valid Draft-07 JSON schema."""
        self.assertTrue(SCHEMA_PATH.is_file())
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            import json
            schema = json.load(f)
        jsonschema.Draft7Validator.check_schema(schema)

    def test_optimize_short_format(self):
        """Short format optimization must return valid titles, tags, hashtags and conform to schema."""
        data = self.optimizer.optimize("Curiosidades del Espacio Exterior", target_format="short")
        self.assertEqual(data["version"], "2.0")
        self.assertEqual(data["target_format"], "short")
        self.assertGreaterEqual(len(data["viral_title_options"]), 3)
        self.assertTrue(data["selected_title"])
        self.assertGreaterEqual(len(data["tags"]), 3)
        self.assertGreaterEqual(len(data["hashtags"]), 2)
        for h in data["hashtags"]:
            self.assertTrue(h.startswith("#"))
        self.assertTrue(data["pinned_comment"])
        self.assertGreaterEqual(len(data["thumbnail_concepts"]), 1)
        self.optimizer.validate_metadata(data)

    def test_optimize_scp_content(self):
        """SCP topic must produce specialized classified titles and containment keywords."""
        data = self.optimizer.optimize("SCP-2000: Deus Ex Machina", target_format="short")
        self.optimizer.validate_metadata(data)
        self.assertIn("scp", [t.lower() for t in data["tags"]])
        self.assertTrue(any("scp" in h.lower() for h in data["hashtags"]))
        self.assertTrue(any("scp" in t.lower() for t in data["viral_title_options"]))


    def test_optimize_long_topic_never_exceeds_100_chars(self):
        """Long topics (e.g. Reddit AITA questions > 80 chars) must strictly never exceed 100 chars."""
        long_drama = "¿Soy la mala por negarme a prestar mis ahorros para un viaje familiar después de que me excluyeron de todas las decisiones?"
        data = self.optimizer.optimize(long_drama, target_format="short", niche="drama")
        self.optimizer.validate_metadata(data)
        self.assertLessEqual(len(data["selected_title"]), 100)
        for t in data["viral_title_options"]:
            self.assertLessEqual(len(t), 100)

        long_scp = "El horror acecha en laboratorios biológicos subterráneos en cuarentena durante la noche en una base polar desconocida"
        data_scp = self.optimizer.optimize(long_scp, target_format="short", niche="scp")
        self.optimizer.validate_metadata(data_scp)
        self.assertLessEqual(len(data_scp["selected_title"]), 100)
        for t in data_scp["viral_title_options"]:
            self.assertLessEqual(len(t), 100)


if __name__ == "__main__":
    unittest.main()
