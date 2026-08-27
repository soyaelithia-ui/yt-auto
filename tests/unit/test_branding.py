import unittest
from src.branding import (
    ChannelBranding,
    get_channel_branding,
    resolve_channel_key,
    _CHANNEL_BRANDING_REGISTRY,
)


class TestBrandingEngine(unittest.TestCase):
    def test_resolve_channel_key_aliases(self):
        self.assertEqual(resolve_channel_key("terror"), "moku")
        self.assertEqual(resolve_channel_key("mokuredit"), "moku")
        self.assertEqual(resolve_channel_key("aelithia"), "aelithia")
        self.assertEqual(resolve_channel_key("soy_el_malo"), "aelithia")
        self.assertEqual(resolve_channel_key("soy-el-malo"), "aelithia")
        self.assertEqual(resolve_channel_key("yo_soy_el_malo"), "aelithia")
        self.assertEqual(resolve_channel_key("aelithia-c1f"), "aelithia")
        with self.assertRaises(ValueError):
            resolve_channel_key(None)
        with self.assertRaises(ValueError):
            resolve_channel_key("unknown_channel")

    def test_get_channel_branding_moku_from_legacy_alias(self):
        b = get_channel_branding("terror")
        self.assertEqual(b.channel_key, "moku")
        self.assertEqual(b.display_name, "Moku")
        self.assertEqual(b.handle, "@MokuRedit")
        self.assertEqual(b.channel_url, "https://www.youtube.com/@MokuRedit")
        self.assertEqual(b.voice_name, "es-MX-JorgeNeural")
        self.assertIn("historias de terror", b.tags)
        self.assertEqual(b.outro_cta_template, "")

    def test_get_channel_branding_aelithia(self):
        b = get_channel_branding("aelithia")
        self.assertEqual(b.channel_key, "aelithia")
        self.assertEqual(b.display_name, "Aelithia")
        self.assertEqual(b.handle, "@Aelithia-c1f")
        self.assertEqual(b.channel_url, "https://www.youtube.com/@Aelithia-c1f")
        self.assertEqual(b.voice_name, "es-MX-DaliaNeural")
        self.assertIn("aelithia", b.tags)
        self.assertEqual(b.outro_cta_template, "")

    def test_generate_title_and_description_moku(self):
        b = get_channel_branding("terror")
        title = b.generate_title("La Casa Embrujada")
        self.assertIn("[RELATO DE TERROR]", title)
        self.assertIn("Moku", title)

        desc = b.generate_description("La Casa Embrujada", "Resumen de prueba")
        self.assertIn("Moku", desc)
        self.assertIn("@MokuRedit", desc)
        self.assertIn("https://www.youtube.com/@MokuRedit", desc)
        self.assertIn("#HistoriasDeTerror", desc)

    def test_generate_title_and_description_aelithia(self):
        b = get_channel_branding("aelithia")
        title = b.generate_title("¿Soy el malo por irme?")
        self.assertIn("Aelithia", title)

        desc = b.generate_description("¿Soy el malo por irme?", "Resumen drama")
        self.assertIn("Aelithia", desc)
        self.assertIn("@Aelithia-c1f", desc)
        self.assertIn("https://www.youtube.com/@Aelithia-c1f", desc)
        self.assertIn("#Aelithia", desc)


if __name__ == "__main__":
    unittest.main()
