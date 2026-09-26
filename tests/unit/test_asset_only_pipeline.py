from __future__ import annotations

import json
from pathlib import Path
import pytest
from PIL import Image

from src.core.lanes import ALLOWED_VISUAL_PIPELINES, load_lanes
from src.media.interface import get_compositor
from src.media.loop_engine import LoopVideoEngine
from src.media.thumbnail_engine import ResilientThumbnailEngine
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


def test_local_ai_bank_rejects_missing_sidecar(tmp_path: Path):
    root = tmp_path / "bank"
    horror = root / "horror"
    horror.mkdir(parents=True)
    img_no_sidecar = horror / "atmospheric_abyss.png"
    Image.new("RGB", (32, 32), (10, 20, 30)).save(img_no_sidecar)

    bank = LocalAIThumbnailBank(root)
    # A candidate without adjacent .json sidecar must be rejected
    assert not bank.is_text_free(img_no_sidecar)
    assert bank.candidates(channel_id="horror") == []


def test_local_ai_bank_rejects_forbidden_token_filenames(tmp_path: Path):
    root = tmp_path / "bank"
    horror = root / "horror"
    horror.mkdir(parents=True)

    forbidden_tokens = [
        "text", "title", "caption", "subtitle", "badge", "watermark", "logo", "overlay"
    ]
    bank = LocalAIThumbnailBank(root)

    for token in forbidden_tokens:
        img_path = horror / f"scenery_{token}_sample.png"
        Image.new("RGB", (32, 32), (15, 25, 35)).save(img_path)
        # Even if sidecar explicitly claims text_free: true
        sidecar = img_path.with_suffix(img_path.suffix + ".json")
        sidecar.write_text(json.dumps({"text_free": True}), encoding="utf-8")

        assert not bank.is_text_free(img_path), f"Failed to reject forbidden token '{token}' in filename"

    assert bank.candidates(channel_id="horror") == []


def test_local_ai_bank_rejects_sidecar_with_text_free_false(tmp_path: Path):
    root = tmp_path / "bank"
    horror = root / "horror"
    horror.mkdir(parents=True)
    img = horror / "clean_specimen.png"
    Image.new("RGB", (32, 32), (20, 30, 40)).save(img)
    sidecar = img.with_suffix(img.suffix + ".json")
    sidecar.write_text(json.dumps({"text_free": False}), encoding="utf-8")

    bank = LocalAIThumbnailBank(root)
    assert not bank.is_text_free(img)
    assert bank.candidates(channel_id="horror") == []


def test_local_ai_bank_path_traversal_prevention(tmp_path: Path):
    root = tmp_path / "bank"
    horror = root / "horror"
    horror.mkdir(parents=True)
    clean_img = horror / "clean_cover.png"
    Image.new("RGB", (32, 32), (10, 10, 10)).save(clean_img)
    clean_img.with_suffix(clean_img.suffix + ".json").write_text(
        json.dumps({"text_free": True}), encoding="utf-8"
    )

    # Outside file
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir(parents=True)
    outside_img = outside_dir / "secret.png"
    Image.new("RGB", (32, 32), (99, 99, 99)).save(outside_img)
    outside_img.with_suffix(outside_img.suffix + ".json").write_text(
        json.dumps({"text_free": True}), encoding="utf-8"
    )

    bank = LocalAIThumbnailBank(root)
    traversal_candidates = bank.candidates(channel_id="../../outside", archetype="../outside")
    for c in traversal_candidates:
        assert c.resolve().is_relative_to(root.resolve()), f"Candidate escaped bank root: {c}"


def test_thumbnail_engine_pure_text_free_rendering(tmp_path: Path):
    root = tmp_path / "bank"
    horror = root / "horror"
    horror.mkdir(parents=True)
    source = horror / "abyssal_rift.png"
    Image.new("RGB", (64, 64), (10, 20, 30)).save(source)
    source.with_suffix(source.suffix + ".json").write_text(
        json.dumps({"text_free": True}), encoding="utf-8"
    )

    engine = ThumbnailEngine(LocalAIThumbnailBank(root))

    # Reject text_free=False
    with pytest.raises(ValueError, match="text_free must remain true"):
        engine.generate(
            ThumbnailConfig(
                title="Invalid text request",
                channel_id="horror",
                output_path=tmp_path / "invalid.jpg",
                text_free=False,
            )
        )

    # ResilientThumbnailEngine delegates cleanly and strips deprecated text params
    resilient = ResilientThumbnailEngine(custom_font_paths=["/fake/font.ttf"])
    resilient._engine = engine
    out = tmp_path / "resilient_thumb.jpg"
    res_path = resilient.generate(
        output_path=out,
        title_main="TITULO PRINCIPAL",
        title_sub="SUBTITULO",
        highlight_box="CAJA DESTACADA",
        badge_text="BADGE",
        channel_id="horror",
        archetype="horror",
        width=128,
        height=72,
    )
    assert res_path == out.resolve()
    assert out.is_file()
    with Image.open(out) as im:
        assert im.size == (128, 72)
