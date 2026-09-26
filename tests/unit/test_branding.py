import unittest
from src.branding import (
    ChannelBranding,
    get_channel_branding,
    resolve_channel_key,
    _CHANNEL_BRANDING_REGISTRY,
)


class TestBrandingEngine(unittest.TestCase):
    def test_resolve_channel_key_aliases(self):
        self.assertEqual(resolve_channel_key("terror"), "horror")
        self.assertEqual(resolve_channel_key("horror"), "horror")
        self.assertEqual(resolve_channel_key("drama"), "drama")
        self.assertEqual(resolve_channel_key("aita"), "drama")
        self.assertEqual(resolve_channel_key("relatos_reddit"), "drama")
        self.assertEqual(resolve_channel_key("scifi"), "scifi")
        with self.assertRaises(ValueError):
            resolve_channel_key(None)
        with self.assertRaises(ValueError):
            resolve_channel_key("unknown_channel")

    def test_get_channel_branding_horror_from_legacy_alias(self):
        b = get_channel_branding("terror")
        self.assertEqual(b.channel_key, "horror")
        self.assertEqual(b.display_name, "Expedientes de Terror")
        self.assertEqual(b.handle, "@expedientesdeterror")
        self.assertEqual(b.channel_url, "https://www.youtube.com")
        self.assertEqual(b.voice_name, "es-MX-JorgeNeural")
        self.assertIn("historias de terror", b.tags)
        self.assertEqual(b.outro_cta_template, "")

    def test_get_channel_branding_drama(self):
        b = get_channel_branding("drama")
        self.assertEqual(b.channel_key, "drama")
        self.assertEqual(b.display_name, "Dilemas Morales")
        self.assertEqual(b.handle, "@dilemasmorales")
        self.assertEqual(b.channel_url, "https://www.youtube.com")
        self.assertEqual(b.voice_name, "es-MX-DaliaNeural")
        self.assertIn("drama", b.tags)
        self.assertEqual(b.outro_cta_template, "")

    def test_generate_title_and_description_horror(self):
        b = get_channel_branding("terror")
        title = b.generate_title("La Casa Embrujada")
        self.assertNotIn("[RELATO DE TERROR]", title)
        self.assertEqual(title, "La Casa Embrujada")

        desc = b.generate_description("La Casa Embrujada", "Resumen de prueba")
        self.assertIn("Expedientes de Terror", desc)
        self.assertIn("@expedientesdeterror", desc)
        self.assertIn("#HistoriasDeTerror", desc)

    def test_generate_title_and_description_drama(self):
        b = get_channel_branding("drama")
        title = b.generate_title("¿Soy el malo por irme?")
        self.assertEqual(title, "¿Soy el malo por irme?")

        desc = b.generate_description("¿Soy el malo por irme?", "Resumen drama")
        self.assertIn("Dilemas Morales", desc)
        self.assertIn("@dilemasmorales", desc)
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
        self.assertIn("horror", _CHANNEL_BRANDING_REGISTRY)
        self.assertIn("drama", _CHANNEL_BRANDING_REGISTRY)
        self.assertIn(CanonicalChannel.HORROR, _CHANNEL_BRANDING_REGISTRY)
        self.assertIn(CanonicalChannel.DRAMA, _CHANNEL_BRANDING_REGISTRY)
        self.assertNotIn("non_existent_random_channel", _CHANNEL_BRANDING_REGISTRY)
        b = _CHANNEL_BRANDING_REGISTRY["horror"]
        self.assertEqual(b.channel_key, "horror")
        b_enum = _CHANNEL_BRANDING_REGISTRY[CanonicalChannel.HORROR]
        self.assertEqual(b_enum.channel_key, "horror")
        self.assertIsNone(_CHANNEL_BRANDING_REGISTRY.get("non_existent_random_channel"))

    def test_generate_shorts_metadata_dynamic_branding(self):
        b_horror = get_channel_branding("horror")
        shorts_horror = b_horror.generate_shorts_metadata("SCP-5000", "Resumen SCP")
        self.assertIn("#Shorts", shorts_horror["title"])
        self.assertIn(b_horror.handle, shorts_horror["description"])
        self.assertIn("#Horror", shorts_horror["description"])

        b_drama = get_channel_branding("drama")
        shorts_ae = b_drama.generate_shorts_metadata("Confesión impactante", "Resumen drama")
        self.assertIn("#Shorts", shorts_ae["title"])
        self.assertIn(b_drama.handle, shorts_ae["description"])
        self.assertIn("#Drama", shorts_ae["description"])

    def test_generate_title_and_description_scifi_generic_channel(self):
        b_scifi = get_channel_branding("scifi")
        title = b_scifi.generate_title("Paradoja Temporal")
        self.assertNotIn("Singularidad Sci-Fi", title)
        self.assertNotIn("Moku", title)
        self.assertEqual(title, "Paradoja Temporal")

        desc = b_scifi.generate_description("Paradoja Temporal", "Exploración del horizonte de sucesos")
        self.assertIn("Singularidad Sci-Fi", desc)
        self.assertIn("@SingularidadSciFi", desc)
        self.assertNotIn("Moku", desc)

    def test_dynamic_env_overrides_in_titles_and_descriptions(self):
        import os
        from unittest.mock import patch
        from src.core.channel_profile import ChannelProfileRegistry

        with patch.dict(os.environ, {"HORROR_HANDLE": "@HorrorCustomDev", "HORROR_NAME": "HorrorNuevo"}):
            ChannelProfileRegistry._ensure_loaded(force_reload=True)
            b = get_channel_branding("horror")
            title = b.generate_title("Historia Fantasmal")
            self.assertNotIn("HorrorNuevo", title)
            self.assertEqual(title, "Historia Fantasmal")
            desc = b.generate_description("Historia Fantasmal")
            self.assertIn("HorrorNuevo", desc)
            self.assertIn("@HorrorCustomDev", desc)
            shorts = b.generate_shorts_metadata("Historia Fantasmal")
            self.assertIn("#HorrorNuevo", shorts["description"])
            self.assertIn("@HorrorCustomDev", shorts["description"])

        # Reload after test to restore standard configuration
        ChannelProfileRegistry._ensure_loaded(force_reload=True)

    def test_truncate_at_word_boundary_never_splits_words(self):
        from src.branding import truncate_at_word_boundary

        text = "¿Soy la mala por negarme a vender mi apartamento heredado para pagar las deudas de mi hermano?"
        res = truncate_at_word_boundary(text, 50)
        self.assertLessEqual(len(res), 50)
        self.assertTrue(res.endswith("...?"))
        self.assertNotIn("apartamento h...", res)
        clean_words = res.replace("...?", "").replace("¿", "").split()
        original_words = text.replace("?", "").replace("¿", "").split()
        for w in clean_words:
            self.assertIn(w, original_words)

    def test_generate_title_word_bounded_spanish_questions(self):
        b = get_channel_branding("aelithia")
        t1 = "¿Soy la mala por negarme a ir a la boda de mi hermana porque invitó a mi agresor y arruinó la relación familiar para siempre?"
        res1 = b.generate_title(t1)
        self.assertLessEqual(len(res1), 100)
        self.assertNotIn("Aelithia", res1)
        self.assertNotIn("hermana p...", res1)

        t2 = "¿Soy la mala por negarme a vender mi apartamento heredado para pagar las deudas de mi hermano?"
        res2 = b.generate_title(t2)
        self.assertLessEqual(len(res2), 100)
        self.assertNotIn("apartamento h...", res2)
        self.assertNotIn("Aelithia", res2)

    def test_generate_title_strips_case_insensitive_suffixes_and_prefixes(self):
        b_moku = get_channel_branding("moku")
        b_aelithia = get_channel_branding("aelithia")
        b_scifi = get_channel_branding("scifi")

        # Uppercase suffix
        self.assertEqual(b_moku.generate_title("La Cabaña del Bosque | MOKU"), "La Cabaña del Bosque")
        # Hyphen separator
        self.assertEqual(b_moku.generate_title("La Cabaña del Bosque - Moku"), "La Cabaña del Bosque")
        # Colon separator
        self.assertEqual(b_aelithia.generate_title("Traición Familiar : Aelithia"), "Traición Familiar")
        # Singularidad variants
        self.assertEqual(b_scifi.generate_title("Paradoja del Tiempo | Singularidad"), "Paradoja del Tiempo")
        self.assertEqual(b_scifi.generate_title("Paradoja del Tiempo | Singularidad SciFi"), "Paradoja del Tiempo")
        self.assertEqual(b_scifi.generate_title("Paradoja del Tiempo | Singularidad Sci Fi"), "Paradoja del Tiempo")
        # Prefix stripping
        self.assertEqual(b_moku.generate_title("[MOKU] La Cabaña del Bosque"), "La Cabaña del Bosque")
        self.assertEqual(b_moku.generate_title("[RELATOS DE TERROR] La Cabaña"), "La Cabaña")
        self.assertEqual(b_moku.generate_title("[REGISTRO CLASIFICADO] SCP-087"), "SCP-087")
        self.assertEqual(b_aelithia.generate_title("[CONFESIÓN] Mi Hermana Arruinó Todo"), "Mi Hermana Arruinó Todo")

    def test_generate_shorts_metadata_strips_brand_from_title(self):
        b_moku = get_channel_branding("moku")
        shorts = b_moku.generate_shorts_metadata("El Susurro Prohibido | Moku")
        self.assertEqual(shorts["title"], "El Susurro Prohibido #Shorts")
        self.assertNotIn("| Moku", shorts["title"])


if __name__ == "__main__":
    unittest.main()
