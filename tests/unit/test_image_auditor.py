"""Unit tests for ImageAuditorAgent (Agent 5 - Anti-Filler & Visual Asset Vetting)."""
import unittest
import jsonschema

from src.agents.image_auditor import ImageAuditorAgent, SCHEMA_PATH


class TestImageAuditorAgent(unittest.TestCase):

    def setUp(self):
        self.auditor = ImageAuditorAgent()

    def test_schema_validity(self):
        """Image auditor schema itself must be a valid Draft-07 schema."""
        self.assertTrue(SCHEMA_PATH.is_file())
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            import json
            schema = json.load(f)
        jsonschema.Draft7Validator.check_schema(schema)

    def test_generic_filler_photo_discarded(self):
        """Generic filler and stock photos must be strictly rejected with DISCARDED_GENERIC_FILLER."""
        candidates = [
            {
                "id": "asset_filler_01",
                "name": "Shocked Face Stock Photo",
                "source_type": "generic_filler_photo",
            }
        ]
        report = self.auditor.audit_candidates("Cualquier Tema", candidates)
        self.assertEqual(report["total_candidates"], 1)
        self.assertEqual(report["approved_count"], 0)
        self.assertEqual(report["discarded_count"], 1)
        verdict = report["verdicts"][0]
        self.assertEqual(verdict["verdict"], "DISCARDED_GENERIC_FILLER")
        self.assertEqual(verdict["badge_render_type"], "none")
        self.assertGreaterEqual(verdict["confidence_score"], 0.95)

    def test_official_scp_emblem_approved(self):
        """Relevant official SCP emblem must be APPROVED_REFERENCE with canvas_procedural_emblem."""
        candidates = [
            {
                "id": "asset_scp_01",
                "name": "SCP Foundation Official Insignia",
                "source_type": "official_emblem",
            }
        ]
        report = self.auditor.audit_candidates("SCP-2000: Deus Ex Machina", candidates)
        self.assertEqual(report["approved_count"], 1)
        verdict = report["verdicts"][0]
        self.assertEqual(verdict["verdict"], "APPROVED_REFERENCE")
        self.assertEqual(verdict["badge_render_type"], "canvas_procedural_emblem")

    def test_unrelated_brand_rejected(self):
        """Brand logos unrelated to the topic must be REJECTED_LOW_RELEVANCE."""
        candidates = [
            {
                "id": "asset_brand_01",
                "name": "Bakery Flour Mill Logo",
                "source_type": "brand_logo",
            }
        ]
        report = self.auditor.audit_candidates("SCP-2000: Deus Ex Machina", candidates)
        self.assertEqual(report["discarded_count"], 1)
        verdict = report["verdicts"][0]
        self.assertEqual(verdict["verdict"], "REJECTED_LOW_RELEVANCE")
        self.assertEqual(verdict["badge_render_type"], "none")

    def test_full_report_validates_against_json_schema(self):
        """Generated report must fully conform to schemas/image_auditor.schema.json."""
        candidates = [
            {"id": "cand_1", "name": "SCP Foundation Insignia", "source_type": "official_emblem"},
            {"id": "cand_2", "name": "Generic Stock Photo", "source_type": "generic_filler_photo"},
            {"id": "cand_3", "name": "DeepMind Logo", "source_type": "brand_logo"},
        ]
        report = self.auditor.audit_candidates("Tecnología e Inteligencia Artificial", candidates)
        self.auditor.validate_report(report)
        self.assertEqual(report["version"], "2.0")


if __name__ == "__main__":
    unittest.main()
