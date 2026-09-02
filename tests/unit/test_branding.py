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
        self.assertEqual(resolve_channel_key("scifi"), "scifi")
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
    def test_channel_branding_defaults_have_no_hardcoded_moku_watermark(self):
        cb = ChannelBranding(
            channel_key="custom",
            display_name="Custom Channel",
            handle="@CustomChannel",
            channel_url="https://youtube.com/@CustomChannel",
            voice_name="es-ES-AlvaroNeural",
            default_title_fallback="Historia",
            narration_style="sobrio",
            intro_hook_template="",
            outro_cta_template="",
            tags=["custom"],
        )
        self.assertEqual(cb.watermark_text, "")

    def test_lazy_registry_delegation(self):
        from src.core.domain import CanonicalChannel
        self.assertIn("moku", _CHANNEL_BRANDING_REGISTRY)
        self.assertIn("aelithia", _CHANNEL_BRANDING_REGISTRY)
        self.assertIn(CanonicalChannel.MOKU, _CHANNEL_BRANDING_REGISTRY)
        self.assertNotIn("non_existent_random_channel", _CHANNEL_BRANDING_REGISTRY)
        b = _CHANNEL_BRANDING_REGISTRY["moku"]
        self.assertEqual(b.channel_key, "moku")
        b_enum = _CHANNEL_BRANDING_REGISTRY[CanonicalChannel.MOKU]
        self.assertEqual(b_enum.channel_key, "moku")
        self.assertIsNone(_CHANNEL_BRANDING_REGISTRY.get("non_existent_random_channel"))

    def test_generate_shorts_metadata_dynamic_branding(self):
        b_moku = get_channel_branding("moku")
        shorts_moku = b_moku.generate_shorts_metadata("SCP-5000", "Resumen SCP")
        self.assertIn("#Shorts", shorts_moku["title"])
        self.assertIn(b_moku.handle, shorts_moku["description"])
        self.assertIn("#Moku", shorts_moku["description"])

        b_aelithia = get_channel_branding("aelithia")
        shorts_ae = b_aelithia.generate_shorts_metadata("Confesión impactante", "Resumen drama")
        self.assertIn("#Shorts", shorts_ae["title"])
        self.assertIn(b_aelithia.handle, shorts_ae["description"])
        self.assertIn("#Aelithia", shorts_ae["description"])

    def test_generate_title_and_description_scifi_generic_channel(self):
        b_scifi = get_channel_branding("scifi")
        title = b_scifi.generate_title("Paradoja Temporal")
        self.assertIn("Singularidad Sci-Fi", title)
        self.assertNotIn("Moku", title)

        desc = b_scifi.generate_description("Paradoja Temporal", "Exploración del horizonte de sucesos")
        self.assertIn("Singularidad Sci-Fi", desc)
        self.assertIn("@SingularidadSciFi", desc)
        self.assertNotIn("Moku", desc)

    def test_dynamic_env_overrides_in_titles_and_descriptions(self):
        import os
        from unittest.mock import patch
        from src.core.channel_profile import ChannelProfileRegistry

        with patch.dict(os.environ, {"MOKU_HANDLE": "@MokuCustomDev", "MOKU_NAME": "MokuNuevo"}):
            ChannelProfileRegistry._ensure_loaded(force_reload=True)
            b = get_channel_branding("moku")
            title = b.generate_title("Historia Fantasmal")
            self.assertIn("MokuNuevo", title)
            desc = b.generate_description("Historia Fantasmal")
            self.assertIn("MokuNuevo", desc)
            self.assertIn("@MokuCustomDev", desc)
            shorts = b.generate_shorts_metadata("Historia Fantasmal")
            self.assertIn("#MokuNuevo", shorts["description"])
            self.assertIn("@MokuCustomDev", shorts["description"])

        # Reload after test to restore standard configuration
        ChannelProfileRegistry._ensure_loaded(force_reload=True)


if __name__ == "__main__":
    unittest.main()
