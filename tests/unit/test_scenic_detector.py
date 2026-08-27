"""Unit tests for scenic loop and subtitle style detector."""
import unittest

from src.core.scenic_detector import detect_scenic_loop, detect_subtitle_style, SCENIC_THEMES


class TestScenicDetector(unittest.TestCase):

    def test_all_seven_environments_present(self):
        """All 7 procedural 3D environments must be defined with keywords."""
        expected_keys = {
            "scp_facility",
            "jurassic_dino",
            "eerie_forest",
            "rose_garden",
            "cosmic_nebula",
            "cyber_matrix",
            "deep_ocean",
        }
        self.assertEqual(set(SCENIC_THEMES.keys()), expected_keys)

    def test_scp_classification(self):
        self.assertEqual(detect_scenic_loop("SCP-2000: Deus Ex Machina"), "scp_facility")
        self.assertEqual(detect_scenic_loop("Búnker subterráneo de contención"), "scp_facility")
        self.assertEqual(detect_scenic_loop("Entidad de Clase Thaumiel"), "scp_facility")

    def test_jurassic_classification(self):
        self.assertEqual(detect_scenic_loop("El último T-Rex del Cretácico"), "jurassic_dino")
        self.assertEqual(detect_scenic_loop("Fósil de dinosaurio gigante"), "jurassic_dino")

    def test_eerie_forest_classification(self):
        self.assertEqual(detect_scenic_loop("Pesadilla en el bosque tétrico"), "eerie_forest")
        self.assertEqual(detect_scenic_loop("Terror gótico en la niebla"), "eerie_forest")

    def test_rose_garden_classification(self):
        self.assertEqual(detect_scenic_loop("Poesía de amor y rosas rojas"), "rose_garden")
        self.assertEqual(detect_scenic_loop("Meditación de paz y flores"), "rose_garden")

    def test_cosmic_nebula_classification(self):
        self.assertEqual(detect_scenic_loop("Agujeros negros en el cosmos"), "cosmic_nebula")
        self.assertEqual(detect_scenic_loop("Vórtice cuántico en la galaxia"), "cosmic_nebula")

    def test_cyber_matrix_classification(self):
        self.assertEqual(detect_scenic_loop("Programación de redes neuronales e IA"), "cyber_matrix")
        self.assertEqual(detect_scenic_loop("Seguridad de software y algoritmos"), "cyber_matrix")

    def test_deep_ocean_classification(self):
        self.assertEqual(detect_scenic_loop("Criaturas del océano abisal"), "deep_ocean")
        self.assertEqual(detect_scenic_loop("El misterio del tiburón gigante"), "deep_ocean")

    def test_subtitle_style_detection(self):
        self.assertEqual(detect_subtitle_style("short", "moku-scp-shorts"), "vertical_lift")
        self.assertEqual(detect_subtitle_style("short", "general"), "tiktok_bounce")
        self.assertEqual(detect_subtitle_style("longform", "cyber-tech"), "karaoke_glow")
        self.assertEqual(detect_subtitle_style("longform", "general"), "cinematic_fade")


if __name__ == "__main__":
    unittest.main()
