"""
tests/unit/test_channel_profile_and_thumbnails.py - Unit tests for ChannelProfileRegistry and ThumbnailEngine.
"""
from pathlib import Path
import pytest
from PIL import Image

from src.core.channel_profile import ChannelProfileRegistry, ChannelProfile
from src.media.thumbnails.engine import ThumbnailConfig, ThumbnailEngine
from src.media.thumbnails.layout import AspectLayoutManager
from src.media.thumbnails.extractor import ClimaxFrameExtractor
from src.media.thumbnails.grading import ChiaroscuroColorGrader
from src.media.thumbnails.subject_extractor import RimLightCompositor
from src.media.thumbnails.typography import DynamicTypographyEngine


def test_channel_profile_registry_loads_all_channels():
    channels = ChannelProfileRegistry.list_active_channels()
    assert len(channels) >= 2
    
    moku = ChannelProfileRegistry.get_channel("moku")
    assert moku.id == "moku"
    assert moku.editorial.public_name == "Moku"
    assert moku.visual.palette.accent == "#00FF66"
    assert "horror" in moku.visual.palette.lut_profile

    aelithia = ChannelProfileRegistry.get_channel("aelithia")
    assert aelithia.id == "aelithia"
    assert aelithia.editorial.public_name == "Aelithia"
    assert aelithia.visual.palette.accent == "#FF4081"

    # Alias normalization
    assert ChannelProfileRegistry.get_channel("channel1").id == "moku"
    assert ChannelProfileRegistry.get_channel("channel2").id == "aelithia"
    assert ChannelProfileRegistry.get_channel("aita").id == "aelithia"
    assert ChannelProfileRegistry.get_channel("scifi").id == "scifi"


def test_aspect_layout_safe_zones():
    # Longform 16:9
    safe_16_9 = AspectLayoutManager.get_safe_zone(1920, 1080)
    assert safe_16_9.width > 1200
    assert safe_16_9.height > 700

    # Short 9:16
    safe_9_16 = AspectLayoutManager.get_safe_zone(1080, 1920)
    assert safe_9_16.width > 700
    assert safe_9_16.height > 1000
    assert safe_9_16.bottom < 1920 * 0.75  # Kept above bottom UI overlay


def test_thumbnail_engine_generation_horizontal_and_vertical(tmp_path: Path):
    engine = ThumbnailEngine()

    # 1. Horizontal Longform 16:9
    out_h = tmp_path / "thumb_16_9.jpg"
    cfg_h = ThumbnailConfig(
        title="INCIDENTE EN EL FARO DE LA FOSA 14",
        channel_id="moku",
        output_path=out_h,
        width=1920,
        height=1080,
    )
    res_h = engine.generate(config=cfg_h)
    assert Path(res_h).is_file()
    assert Path(res_h).stat().st_size > 10000

    img_h = Image.open(res_h)
    assert img_h.size == (1920, 1080)

    # 2. Vertical Short 9:16
    out_v = tmp_path / "thumb_9_16.jpg"
    cfg_v = ThumbnailConfig(
        title="LO QUE VIO EL FARERO ANTES DEL APAGÓN",
        channel_id="moku",
        output_path=out_v,
        width=1080,
        height=1920,
    )
    res_v = engine.generate(config=cfg_v)
    assert Path(res_v).is_file()
    assert Path(res_v).stat().st_size > 10000

    img_v = Image.open(res_v)
    assert img_v.size == (1080, 1920)


def test_climax_frame_extractor_timestamp():
    extractor = ClimaxFrameExtractor()
    manifest_dummy = {
        "scenes": [
            {"scene_id": "s1", "start_sec": 0.0, "duration_sec": 5.0, "tension_level": 1},
            {"scene_id": "s2", "start_sec": 5.0, "duration_sec": 6.0, "tension_level": 3},
            {"scene_id": "s3", "start_sec": 11.0, "duration_sec": 8.0, "tension_level": 5},
            {"scene_id": "s4", "start_sec": 19.0, "duration_sec": 4.0, "tension_level": 2},
        ]
    }
    t = extractor.resolve_climax_timestamp(manifest_data=manifest_dummy)
    # Scene 3 has tension 5, start 11.0, dur 8.0 -> 11.0 + (8.0 * 0.45) = 14.6
    assert 14.0 <= t <= 15.0
