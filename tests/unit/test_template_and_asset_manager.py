"""
Unit tests for TemplateRegistry, VideoTemplate, SubtitleStyle, and AssetManager.
"""
import os
from pathlib import Path
import pytest
from src.templates import (
    VideoTemplate,
    SubtitleStyle,
    AudioStyle,
    VisualEffectStyle,
    ThumbnailStyle,
    TemplateRegistry,
    get_template,
)
from src.asset_manager import AssetManager, get_asset_manager
from lib.subtitles import create_ass_subtitles, create_subtitles
from lib.video import generate_pil_thumbnail


class TestTemplateAndAssetManager:

    def test_default_template_registry_presets(self):
        reg = TemplateRegistry()
        templates = reg.list_templates()
        assert "creepypasta" in templates
        assert "aita" in templates
        assert "cyberpunk" in templates
        assert "documentary" in templates

        creepypasta = reg.get_template("creepypasta")
        assert creepypasta.name == "creepypasta"
        assert creepypasta.audio.lowpass_freq == 3000
        assert creepypasta.subtitles.primary_color == "&H0000FFFF"

        aita = reg.get_template("aita")
        assert aita.name == "aita"
        assert aita.audio.lowpass_freq == 0
        assert aita.thumbnail.layout_type == "reddit_card"

    def test_get_template_fallback(self):
        tpl = get_template("non_existent_preset_name")
        assert tpl is not None
        assert tpl.name == "creepypasta"

    def test_shorts_and_scp_presets_declare_768x1360(self):
        reg = TemplateRegistry()
        short_presets = (
            "scp_classified",
            "shorts_creepypasta",
            "shorts_aita",
            "shorts_cyberpunk",
            "shorts_documentary",
        )
        for name in short_presets:
            tpl = reg.get_template(name)
            assert tpl.name == name, f"template {name} not registered"
            assert tpl.visual.resolution in ("720x1280", "768x1360"), f"{name} declares {tpl.visual.resolution}"

    def test_custom_template_registration(self):
        custom = VideoTemplate(
            name="sci_fi_horror",
            description="Custom sci-fi horror preset",
            subtitles=SubtitleStyle(font_size=90, primary_color="&H0000FF00"),
            audio=AudioStyle(music_volume=0.03)
        )
        reg = TemplateRegistry()
        reg.register_template(custom)
        fetched = reg.get_template("sci_fi_horror")
        assert fetched.name == "sci_fi_horror"
        assert fetched.subtitles.font_size == 90
        assert fetched.audio.music_volume == 0.03

    def test_asset_manager_indexing_and_retrieval(self, tmp_path):
        # Create temporary assets structure
        lib = tmp_path / "assets" / "library"
        (lib / "backgrounds" / "horror").mkdir(parents=True)
        (lib / "music" / "horror").mkdir(parents=True)
        (lib / "ambient" / "horror").mkdir(parents=True)

        bg1 = lib / "backgrounds" / "horror" / "scene1.jpg"
        bg1.write_bytes(b"fake_jpg_content")
        bg2 = lib / "backgrounds" / "horror" / "scene2.jpg"
        bg2.write_bytes(b"fake_jpg_content_2")
        bg3 = lib / "backgrounds" / "horror" / "scene3.jpg"
        bg3.write_bytes(b"fake_jpg_content_3")

        mus1 = lib / "music" / "horror" / "track1.mp3"
        mus1.write_bytes(b"fake_mp3_content")

        mgr = AssetManager(root_dir=str(tmp_path / "assets"))
        
        bg = mgr.get_background(category="horror", style="creepypasta")
        assert bg in (str(bg1), str(bg2), str(bg3))

        seq = mgr.get_background_sequence(category="horror", style="creepypasta", count=3)
        assert len(seq) == 3
        for item in seq:
            assert item in (str(bg1), str(bg2), str(bg3))

        track = mgr.get_music(category="horror")
        assert track == str(mus1)


    def test_gifs_and_overlays_excluded_from_background_index(self, tmp_path):
        assets = tmp_path / "assets"
        scenery = assets / "visual_bank" / "moku" / "scenery"
        gifs = assets / "visual_bank" / "moku" / "ambient_gifs"
        overlays = assets / "visual_bank" / "moku" / "overlays"
        scenery.mkdir(parents=True)
        gifs.mkdir(parents=True)
        overlays.mkdir(parents=True)

        gif = gifs / "creepy_fog.gif"
        gif.write_bytes(b"GIF89a_fake")
        overlay = overlays / "vignette.png"
        overlay.write_bytes(b"fake_png")
        jpg = scenery / "fog_still.jpg"
        jpg.write_bytes(b"fake_jpg")
        mp4 = scenery / "pan.mp4"
        mp4.write_bytes(b"fake_mp4")

        mgr = AssetManager(root_dir=str(assets))

        all_bgs = []
        for paths in mgr._index["backgrounds"].values():
            all_bgs.extend(paths)

        assert str(jpg) in all_bgs
        assert str(mp4) in all_bgs
        assert not any(p.lower().endswith(".gif") for p in all_bgs)
        assert str(overlay) not in all_bgs

        def _parts(path: str):
            return {part.lower() for part in Path(path).parts}

        assert not any("ambient_gifs" in _parts(p) for p in all_bgs)
        assert not any("overlays" in _parts(p) for p in all_bgs)
        assert not any("_quarantine_title_cards" in _parts(p) for p in all_bgs)

        for _ in range(20):
            bg = mgr.get_background(category="moku", style="creepypasta")
            assert not bg.lower().endswith(".gif"), bg
            assert "overlays" not in _parts(bg)
            assert "ambient_gifs" not in _parts(bg)

        seq = mgr.get_background_sequence(category="moku", style="creepypasta", count=5)
        assert seq
        assert not any(p.lower().endswith(".gif") for p in seq)

    def test_title_cards_excluded_from_background_index(self, tmp_path):
        """Quarantined baked-text covers must never re-enter the background pool."""
        from src.asset_manager import is_eligible_background_asset

        assets = tmp_path / "assets"
        scenery = assets / "visual_bank" / "moku" / "scenery"
        quarantine = assets / "visual_bank" / "_quarantine_title_cards" / "moku"
        scenery.mkdir(parents=True)
        quarantine.mkdir(parents=True)

        clean = scenery / "fog_clean.jpg"
        clean.write_bytes(b"clean_scenery")
        title_card = quarantine / "abyssal_creature.jpg"
        title_card.write_bytes(b"baked_title_card")

        assert is_eligible_background_asset(str(clean))
        assert not is_eligible_background_asset(str(title_card))
        assert not is_eligible_background_asset(str(quarantine / "x.gif"))

        mgr = AssetManager(root_dir=str(assets))
        all_bgs = [p for paths in mgr._index["backgrounds"].values() for p in paths]
        assert str(clean) in all_bgs
        assert str(title_card) not in all_bgs
        assert not any("_quarantine_title_cards" in p for p in all_bgs)

        for _ in range(15):
            bg = mgr.get_background(category="moku", style="creepypasta")
            assert "_quarantine_title_cards" not in bg
            assert bg == str(clean)


    def test_create_ass_subtitles_with_template(self, tmp_path):
        out_ass = str(tmp_path / "test_subs.ass")
        words = [
            {"word": "HISTORIA", "start": 0.0, "end": 0.5},
            {"word": "DE", "start": 0.5, "end": 0.8},
            {"word": "TERROR", "start": 0.8, "end": 1.2}
        ]

        tpl = get_template("cyberpunk")
        create_ass_subtitles(words, out_ass, template=tpl)

        assert os.path.exists(out_ass)
        with open(out_ass, "r", encoding="utf-8") as f:
            content = f.read()

        assert "Montserrat Black" in content
        assert "Style: Default" in content
        assert "\\kf" in content

    def test_generate_pil_thumbnail_with_template(self, tmp_path):
        out_thumb = str(tmp_path / "thumbnail.jpg")
        tpl = get_template("creepypasta")
        generate_pil_thumbnail("LA CASA MALDITA", out_thumb, template=tpl)

        assert os.path.exists(out_thumb)
        assert os.path.getsize(out_thumb) > 1000
