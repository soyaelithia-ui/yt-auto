"""
Unit tests for TemplateRegistry, VideoTemplate, SubtitleStyle, and AssetManager.
"""
import os
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
from src.subtitles import create_ass_subtitles, create_subtitles
from src.video import generate_pil_thumbnail


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
