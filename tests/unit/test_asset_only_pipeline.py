from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from src.core.lanes import ALLOWED_VISUAL_PIPELINES, load_lanes
from src.media.interface import get_compositor
from src.media.loop_engine import LoopVideoEngine
from src.media.thumbnails.ai_bank import LocalAIThumbnailBank
from src.media.thumbnails.engine import ThumbnailConfig, ThumbnailEngine


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_production_lanes_use_only_local_asset_pipelines():
    lanes = load_lanes(PROJECT_ROOT / "config" / "lanes.json")
    assert ALLOWED_VISUAL_PIPELINES == {"director", "video_loop"}
    assert {lane.visual_pipeline for lane in lanes} <= ALLOWED_VISUAL_PIPELINES


def test_legacy_compositor_alias_resolves_to_local_loop():
    assert isinstance(get_compositor("multiscene"), LoopVideoEngine)
    assert isinstance(get_compositor("video_loop"), LoopVideoEngine)


def test_local_ai_bank_rejects_declared_text_assets(tmp_path: Path):
    root = tmp_path / "bank"
    root.mkdir()
    clean = root / "horror" / "scene_001.png"
    clean.parent.mkdir()
    Image.new("RGB", (32, 32), (20, 30, 40)).save(clean)
    (clean.with_suffix(clean.suffix + ".json")).write_text(
        json.dumps({"text_free": True}), encoding="utf-8"
    )
    bad = root / "horror" / "scene_title.png"
    Image.new("RGB", (32, 32), (20, 30, 40)).save(bad)
    (bad.with_suffix(bad.suffix + ".json")).write_text(
        json.dumps({"text_free": False}), encoding="utf-8"
    )

    candidates = LocalAIThumbnailBank(root).candidates(channel_id="horror")
    assert candidates == [clean]


def test_thumbnail_engine_exports_without_text_layout(tmp_path: Path):
    root = tmp_path / "bank"
    folder = root / "horror"
    folder.mkdir(parents=True)
    source = folder / "scene_001.png"
    Image.new("RGB", (64, 64), (30, 40, 50)).save(source)
    (source.with_suffix(source.suffix + ".json")).write_text(
        json.dumps({"text_free": True}), encoding="utf-8"
    )
    out = tmp_path / "thumbnail.jpg"
    engine = ThumbnailEngine(LocalAIThumbnailBank(root))
    result = engine.generate(
        ThumbnailConfig(
            title="Ignored metadata title",
            channel_id="horror",
            archetype="horror",
            output_path=out,
            width=128,
            height=72,
        )
    )
    assert result == out.resolve()
    assert engine.last_asset == source
    with Image.open(result) as image:
        assert image.size == (128, 72)
