"""
Unit tests for Canonical SCP Lore Knowledge Base & Grounding Engine (Feature F2).
Verifies canonical SCP lookup, alias resolution, normalization, keyword verification,
misconception detection, and genre pollution barrier.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.core.scp_lore import (
    SCP_LORE_DATABASE,
    get_all_canonical_scps,
    get_scp_canonical_lore,
    get_scp_opening_hook,
    get_scp_visual_descriptors,
    is_scp_topic,
    normalize_scp_lookup_key,
    validate_scp_lore,
)
from src.agents.story_director import StoryDirectorAgent, StoryInvestigatorAgent


class TestSCPLoreDatabase(unittest.TestCase):
    """Test the completeness and structural integrity of the canonical SCP database."""

    def test_database_contains_13_canonical_scps(self):
        scps = get_all_canonical_scps()
        expected = [
            "SCP-049",
            "SCP-055",
            "SCP-087",
            "SCP-093",
            "SCP-096",
            "SCP-106",
            "SCP-173",
            "SCP-3000",
            "SCP-3008",
            "SCP-4666",
            "SCP-5000",
            "SCP-682",
            "SCP-999",
        ]
        self.assertEqual(scps, sorted(expected))
        self.assertEqual(len(scps), 13)

    def test_every_scp_entry_has_required_fields(self):
        for scp_id, entry in SCP_LORE_DATABASE.items():
            d = entry.to_dict()
            self.assertEqual(d["scp_id"], scp_id)
            self.assertIn("es", d["canonical_name"])
            self.assertIn("en", d["canonical_name"])
            self.assertIn(d["object_class"], ["Safe", "Euclid", "Keter", "Thaumiel", "Apollyon"])
            self.assertGreater(len(d["key_facts"]), 0, f"{scp_id} key_facts is empty")
            self.assertIn("visual", d["sensory_cues"])
            self.assertIn("auditory", d["sensory_cues"])
            self.assertIn("tactile", d["sensory_cues"])
            self.assertGreater(len(d["visual_descriptors"]), 0, f"{scp_id} visual_descriptors is empty")
            self.assertGreater(len(d["required_keywords"]), 0, f"{scp_id} required_keywords is empty")
            self.assertGreater(len(d["narrative_hooks"]), 0, f"{scp_id} narrative_hooks is empty")
            self.assertTrue(bool(d["containment_summary"]), f"{scp_id} containment_summary is empty")


class TestSCPLookupAndNormalization(unittest.TestCase):
    """Test query normalization and alias resolution."""

    def test_get_scp_canonical_lore_by_exact_id(self):
        for scp_id in ["SCP-087", "SCP-096", "SCP-173", "SCP-049", "SCP-3008", "SCP-682", "SCP-106"]:
            lore = get_scp_canonical_lore(scp_id)
            self.assertIsNotNone(lore, f"Failed to retrieve lore for {scp_id}")
            self.assertEqual(lore["scp_id"], scp_id)

    def test_lookup_by_loose_numbers(self):
        test_cases = [
            ("87", "SCP-087"),
            ("087", "SCP-087"),
            ("scp87", "SCP-087"),
            ("scp-87", "SCP-087"),
            ("96", "SCP-096"),
            ("173", "SCP-173"),
            ("3008", "SCP-3008"),
            ("682", "SCP-682"),
            ("49", "SCP-049"),
            ("999", "SCP-999"),
            ("55", "SCP-055"),
            ("3000", "SCP-3000"),
            ("5000", "SCP-5000"),
            ("4666", "SCP-4666"),
        ]
        for query, expected_id in test_cases:
            lore = get_scp_canonical_lore(query)
            self.assertIsNotNone(lore, f"Query '{query}' failed to resolve to {expected_id}")
            self.assertEqual(lore["scp_id"], expected_id)

    def test_lookup_by_spanish_and_english_aliases(self):
        alias_tests = [
            ("The Stairwell", "SCP-087"),
            ("El Pozo de las Escaleras", "SCP-087"),
            ("escalera infinita", "SCP-087"),
            ("The Shy Guy", "SCP-096"),
            ("el chico timido", "SCP-096"),
            ("The Sculpture", "SCP-173"),
            ("la escultura", "SCP-173"),
            ("peanut", "SCP-173"),
            ("el cacahuate", "SCP-173"),
            ("Plague Doctor", "SCP-049"),
            ("el doctor de la peste", "SCP-049"),
            ("infinite ikea", "SCP-3008"),
            ("ikea infinito", "SCP-3008"),
            ("Hard-to-Destroy Reptile", "SCP-682"),
            ("el reptil indestructible", "SCP-682"),
            ("The Old Man", "SCP-106"),
            ("el anciano", "SCP-106"),
            ("Red Sea Object", "SCP-093"),
            ("el objeto del mar rojo", "SCP-093"),
            ("The Tickle Monster", "SCP-999"),
            ("el monstruo de las cosquillas", "SCP-999"),
            ("Anantashesha", "SCP-3000"),
            ("Pietro Wilson", "SCP-5000"),
            ("The Yule Man", "SCP-4666"),
            ("el hombre de navidad", "SCP-4666"),
        ]
        for alias, expected_id in alias_tests:
            lore = get_scp_canonical_lore(alias)
            self.assertIsNotNone(lore, f"Alias '{alias}' failed to resolve to {expected_id}")
            self.assertEqual(lore["scp_id"], expected_id)

    def test_unknown_topic_returns_none(self):
        self.assertIsNone(get_scp_canonical_lore("SCP-99999"))
        self.assertIsNone(get_scp_canonical_lore("Herencia Familiar"))
        self.assertIsNone(get_scp_canonical_lore(""))
        self.assertIsNone(get_scp_canonical_lore(None))

    def test_is_scp_topic(self):
        self.assertTrue(is_scp_topic("SCP-087"))
        self.assertTrue(is_scp_topic("scp-999"))
        self.assertTrue(is_scp_topic("The Stairwell"))
        self.assertTrue(is_scp_topic("IKEA infinito"))
        self.assertFalse(is_scp_topic("Drama de pareja en la boda"))
        self.assertFalse(is_scp_topic(""))
        self.assertFalse(is_scp_topic(None))

    def test_get_scp_opening_hook_and_visual_descriptors(self):
        hook = get_scp_opening_hook("SCP-087")
        self.assertIsNotNone(hook)
        self.assertIn("escalera", hook.lower())

        descriptors = get_scp_visual_descriptors("SCP-087")
        self.assertIsInstance(descriptors, list)
        self.assertGreater(len(descriptors), 0)
        self.assertTrue(any("stairwell" in d.lower() or "dark" in d.lower() for d in descriptors))


class TestSCPLoreValidator(unittest.TestCase):
    """Test validation of generated scripts against canonical facts and genre isolation."""

    def test_validate_passing_script(self):
        valid_script = (
            "En las profundidades de la universidad, el descenso por la escalera de SCP-087 es una pesadilla de oscuridad absoluta. "
            "Cada peldaño devora la luz de la linterna y los llantos distantes de un niño resuenan sin cesar. "
            "De pronto, en la penumbra se manifiesta el rostro flotante de 087-1 mirándote fijamente."
        )
        is_valid, issues = validate_scp_lore(valid_script, "SCP-087")
        self.assertTrue(is_valid, f"Expected valid script to pass, but got issues: {issues}")
        self.assertEqual(len(issues), 0)

    def test_validate_missing_keywords(self):
        generic_script = (
            "Había una vez un misterio muy grande en una habitación donde ocurrieron cosas extrañas y todo el mundo tuvo miedo."
        )
        is_valid, issues = validate_scp_lore(generic_script, "SCP-087", min_keyword_matches=2)
        self.assertFalse(is_valid)
        self.assertTrue(any("Missing core canonical lore elements" in issue for issue in issues))

    def test_validate_forbidden_misconception_scp173(self):
        misconception_script = (
            "La estatua de hormigón y barras de metal se mueve mientras lo miras fijamente a los ojos, persiguiendo a todos en la sala. "
            "El parpadeo y la mirada no le importan porque ataca sin parar."
        )
        is_valid, issues = validate_scp_lore(misconception_script, "SCP-173")
        self.assertFalse(is_valid)
        self.assertTrue(any("Lore contradiction detected for SCP-173" in issue for issue in issues))
        self.assertTrue(any("inmóvil bajo la mirada directa" in issue for issue in issues))

    def test_validate_forbidden_misconception_scp096(self):
        misconception_script = (
            "Al entrar a la celda de SCP-096, la criatura de piel pálida ataca a ciegas a todo el personal con su enorme mandíbula. "
            "Nadie miró su rostro ni vio una fotografía, pero el monstruo enfureció igual."
        )
        is_valid, issues = validate_scp_lore(misconception_script, "SCP-096")
        self.assertFalse(is_valid)
        self.assertTrue(any("Lore contradiction detected for SCP-096" in issue for issue in issues))
        self.assertTrue(any("solo ataca a quien ha visto su rostro" in issue for issue in issues))

    def test_validate_genre_pollution_rejection(self):
        polluted_script = (
            "Bajando por la escalera de SCP-087 en plena oscuridad escuché un llanto y pensé: ¿soy el malo por huir y dejar a mi suegra atrás? "
            "En este hilo de reddit les cuento cómo la herencia familiar provocó que termináramos en esta anomalía."
        )
        is_valid, issues = validate_scp_lore(polluted_script, "SCP-087", strict_genre_check=True)
        self.assertFalse(is_valid)
        self.assertTrue(any("Genre pollution detected" in issue for issue in issues))

    def test_validate_empty_or_invalid_text(self):
        is_valid, issues = validate_scp_lore("", "SCP-087")
        self.assertFalse(is_valid)
        self.assertEqual(issues, ["Script text is empty or invalid."])

    def test_validate_uncatalogued_scp_passes_with_notice(self):
        is_valid, issues = validate_scp_lore("Un guion sobre un SCP desconocido.", "SCP-8888")
        self.assertTrue(is_valid)
        self.assertTrue(any("not in curated canonical database" in issue for issue in issues))


class TestStoryInvestigatorLoreIntegration(unittest.TestCase):
    """Test StoryInvestigatorAgent integration with canonical SCP lore."""

    @patch.object(StoryInvestigatorAgent, "consume")
    @patch.object(StoryInvestigatorAgent, "run")
    def test_story_investigator_generates_grounded_script(self, mock_run, mock_consume):
        mock_run.return_value = "/tmp/mock_result.json"
        mock_consume.return_value = {
            "output": {
                "structured_output": {
                    "title": "El Secreto del Pozo de las Escaleras",
                    "script": (
                        "¿Bajarías una escalera infinita donde los llantos nunca se acercan? "
                        "El descenso por SCP-087 devora la luz de tu linterna en una oscuridad impenetrable. "
                        "En el descanso siguiente, el rostro pálido de 087-1 surge de la penumbra."
                    ),
                    "visual_metadata": ["dark concrete stairwell", "pale face in shadows"],
                }
            }
        }

        agent = StoryInvestigatorAgent()
        result = agent.generate_script("SCP-087")

        self.assertIn("title", result)
        self.assertIn("script", result)
        self.assertEqual(result.get("is_lore_valid"), True)
        self.assertNotIn("lore_warnings", result)
        self.assertIn("dark concrete stairwell", result["visual_metadata"])

        # Verify prompt contained canonical lore requirements
        prompt_arg = mock_run.call_args[0][0]
        self.assertIn("CANON OFICIAL SCP REQUERIDO (SCP-087", prompt_arg)
        self.assertIn("Euclid", prompt_arg)
        self.assertIn("escalera", prompt_arg)


if __name__ == "__main__":
    unittest.main()
