"""
Unit tests for GraphicsBank (Local Video Graphics Bank & Manifest SSOT).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.media.graphics_bank import (
    BankValidationReport,
    GraphicAsset,
    GraphicCategory,
    GraphicChannelAffinity,
    GraphicsBank,
    get_graphics_bank,
)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def bank(repo_root: Path) -> GraphicsBank:
    return GraphicsBank(base_dir=repo_root)


def test_manifest_loading_happy_path(bank: GraphicsBank):
    """Validates that GraphicsBank.load_manifest() parses assets/graphics_manifest.json into immutable GraphicAsset records,
    verifies count (at least 16 assets: 8 atmospheric + 8 dynamic vector HUDs), field types, and heap memory footprint (< 2.0 MiB)."""
    assert len(bank.assets) >= 16
    for asset_id, asset in bank.assets.items():
        assert isinstance(asset_id, str)
        assert isinstance(asset, GraphicAsset)
        assert isinstance(asset.id, str)
        assert isinstance(asset.name, str)
        assert isinstance(asset.category, GraphicCategory)
        assert isinstance(asset.channel_affinity, GraphicChannelAffinity)
        assert isinstance(asset.aspect_ratios, tuple)
        assert isinstance(asset.relative_path, str)
        assert isinstance(asset.safe_zone_compliant, bool)
        assert isinstance(asset.default_opacity, float)
        assert isinstance(asset.dynamic_params, dict)
        assert isinstance(asset.tags, tuple)

    # Memory footprint check (< 2.0 MiB)
    import sys
    total_size = sum(sys.getsizeof(a) for a in bank.assets.values())
    assert total_size < 2 * 1024 * 1024


def test_manifest_missing_required_field_rejection(tmp_path: Path):
    """Asserts that an entry lacking mandatory fields (category or relative_path) raises a descriptive ValueError."""
    bad_manifest = {
        "version": "1.0.0",
        "assets": [
            {
                "id": "missing_cat",
                "name": "Missing Category",
                # missing "category"
                "channel_affinity": "all",
                "aspect_ratios": ["9:16", "16:9"],
                "relative_path": "assets/overlays/static/dark_vignette.png",
                "safe_zone_compliant": True,
                "default_opacity": 0.25,
            }
        ],
    }
    p = tmp_path / "bad_manifest.json"
    p.write_text(json.dumps(bad_manifest), encoding="utf-8")
    bank = GraphicsBank(base_dir=tmp_path)
    with pytest.raises(ValueError, match="category"):
        bank.load_manifest(p)


def test_manifest_duplicate_id_rejection(tmp_path: Path):
    """Asserts that duplicate asset identifiers in the manifest raise ValueError."""
    dup_manifest = {
        "version": "1.0.0",
        "assets": [
            {
                "id": "dark_vignette",
                "name": "Dark Vignette 1",
                "category": "atmospheric",
                "channel_affinity": "all",
                "aspect_ratios": ["9:16", "16:9"],
                "relative_path": "assets/overlays/static/dark_vignette.png",
                "safe_zone_compliant": True,
                "default_opacity": 0.25,
            },
            {
                "id": "dark_vignette",
                "name": "Dark Vignette Duplicate",
                "category": "atmospheric",
                "channel_affinity": "all",
                "aspect_ratios": ["9:16", "16:9"],
                "relative_path": "assets/overlays/static/dark_vignette.png",
                "safe_zone_compliant": True,
                "default_opacity": 0.25,
            },
        ],
    }
    p = tmp_path / "dup_manifest.json"
    p.write_text(json.dumps(dup_manifest), encoding="utf-8")
    bank = GraphicsBank(base_dir=tmp_path)
    with pytest.raises(ValueError, match="(?i)duplicate.*dark_vignette"):
        bank.load_manifest(p)


def test_manifest_invalid_enum_rejection(tmp_path: Path):
    """Asserts that unsupported categories (e.g. 'unsupported_3d') or channel affinities (e.g. 'vlog') raise ValueError."""
    bad_cat = {
        "version": "1.0.0",
        "assets": [
            {
                "id": "bad_cat_asset",
                "name": "Bad Category",
                "category": "unsupported_3d",
                "channel_affinity": "all",
                "aspect_ratios": ["9:16"],
                "relative_path": "assets/test.png",
                "safe_zone_compliant": True,
                "default_opacity": 0.2,
            }
        ],
    }
    p1 = tmp_path / "bad_cat.json"
    p1.write_text(json.dumps(bad_cat), encoding="utf-8")
    bank1 = GraphicsBank(base_dir=tmp_path)
    with pytest.raises(ValueError, match="category"):
        bank1.load_manifest(p1)

    bad_aff = {
        "version": "1.0.0",
        "assets": [
            {
                "id": "bad_aff_asset",
                "name": "Bad Affinity",
                "category": "atmospheric",
                "channel_affinity": "vlog",
                "aspect_ratios": ["9:16"],
                "relative_path": "assets/test.png",
                "safe_zone_compliant": True,
                "default_opacity": 0.2,
            }
        ],
    }
    p2 = tmp_path / "bad_aff.json"
    p2.write_text(json.dumps(bad_aff), encoding="utf-8")
    bank2 = GraphicsBank(base_dir=tmp_path)
    with pytest.raises(ValueError, match="channel_affinity"):
        bank2.load_manifest(p2)


def test_manifest_path_traversal_rejection(tmp_path: Path):
    """Asserts that relative paths attempting directory traversal (e.g. ../../etc/passwd) or absolute paths are rejected with ValueError (TM-01)."""
    traversal_manifest = {
        "version": "1.0.0",
        "assets": [
            {
                "id": "traversal_asset",
                "name": "Traversal Asset",
                "category": "atmospheric",
                "channel_affinity": "all",
                "aspect_ratios": ["9:16"],
                "relative_path": "../../etc/passwd",
                "safe_zone_compliant": True,
                "default_opacity": 0.2,
            }
        ],
    }
    p = tmp_path / "traversal.json"
    p.write_text(json.dumps(traversal_manifest), encoding="utf-8")
    bank = GraphicsBank(base_dir=tmp_path)
    with pytest.raises(ValueError, match="traversal|relative|outside"):
        bank.load_manifest(p)

    # Invalid ID with path traversal
    bad_id_manifest = {
        "version": "1.0.0",
        "assets": [
            {
                "id": "../malicious_id",
                "name": "Bad ID",
                "category": "atmospheric",
                "channel_affinity": "all",
                "aspect_ratios": ["9:16"],
                "relative_path": "assets/test.png",
                "safe_zone_compliant": True,
                "default_opacity": 0.2,
            }
        ],
    }
    p2 = tmp_path / "bad_id.json"
    p2.write_text(json.dumps(bad_id_manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="id"):
        bank.load_manifest(p2)


def test_query_by_category_and_channel(bank: GraphicsBank):
    """Validates conjunction filtering across categories and channel niches (horror, drama, scifi)."""
    horror_huds = bank.query(category=GraphicCategory.VECTOR_HUD, channel="horror")
    assert len(horror_huds) > 0
    for h in horror_huds:
        assert h.category == GraphicCategory.VECTOR_HUD
        assert h.channel_affinity in (GraphicChannelAffinity.HORROR, GraphicChannelAffinity.ALL)

    drama_typog = bank.query(category=GraphicCategory.TYPOGRAPHY, channel="drama")
    assert len(drama_typog) > 0
    for d in drama_typog:
        assert d.category == GraphicCategory.TYPOGRAPHY
        assert d.channel_affinity in (GraphicChannelAffinity.DRAMA, GraphicChannelAffinity.ALL)


def test_query_channel_wildcard(bank: GraphicsBank):
    """Verifies assets with channel_affinity == 'all' (such as dark_vignette) match queries for any specific channel."""
    all_horror = bank.query(channel="horror")
    all_drama = bank.query(channel="drama")
    all_scifi = bank.query(channel="scifi")

    vignette = bank.get_asset("dark_vignette")
    assert vignette is not None
    assert vignette.channel_affinity == GraphicChannelAffinity.ALL
    assert vignette in all_horror
    assert vignette in all_drama
    assert vignette in all_scifi


def test_query_aspect_ratio_filtering(bank: GraphicsBank):
    """Verifies filtering for '9:16' vs '16:9'."""
    vert_assets = bank.query(aspect_ratio="9:16")
    horiz_assets = bank.query(aspect_ratio="16:9")
    assert len(vert_assets) > 0
    assert len(horiz_assets) > 0
    for a in vert_assets:
        assert "9:16" in a.aspect_ratios
    for a in horiz_assets:
        assert "16:9" in a.aspect_ratios


def test_query_tag_filtering(bank: GraphicsBank):
    """Verifies case-insensitive keyword tag filtering ('vhs', 'camcorder')."""
    vhs_assets = bank.query(tag="vhs")
    assert len(vhs_assets) > 0
    assert any(a.id == "rec_analog_hud" for a in vhs_assets)


def test_get_asset_lookup(bank: GraphicsBank):
    """Tests bank.get_asset('rec_analog_hud') returns GraphicAsset and bank.get_asset('unknown_id') returns None."""
    asset = bank.get_asset("rec_analog_hud")
    assert asset is not None
    assert asset.id == "rec_analog_hud"
    assert bank.get_asset("unknown_id_xyz") is None


def test_resolve_atmospheric_path(bank: GraphicsBank):
    """Verifies resolution of physical file paths for vignette, film_grain, particles (with particle_type='embers'), tv_static, and god_rays."""
    vignette_path = bank.resolve_atmospheric_path("vignette")
    assert vignette_path is not None
    assert vignette_path.is_file()
    assert vignette_path.name in ("dark_vignette.png", "vignette.png", "soft_vignette.png")

    grain_path = bank.resolve_atmospheric_path("film_grain")
    assert grain_path is not None
    assert grain_path.is_file()
    assert grain_path.name == "film_grain.png"

    embers_path = bank.resolve_atmospheric_path("particles", particle_type="embers")
    assert embers_path is not None
    assert embers_path.is_file()
    assert embers_path.name == "particles_embers.png"

    static_path = bank.resolve_atmospheric_path("tv_static")
    assert static_path is not None
    assert static_path.is_file()
    assert static_path.name == "tv_static.png"

    rays_path = bank.resolve_atmospheric_path("god_rays")
    assert rays_path is not None
    assert rays_path.is_file()
    assert rays_path.name == "god_rays.png"


def test_clamp_asset_opacity(bank: GraphicsBank):
    """Verifies opacity bounds [0.15, 0.35] on atmospheric assets and passthrough for non-atmospheric assets."""
    # Atmospheric asset clamps to [0.15, 0.35]
    assert bank.clamp_asset_opacity("dark_vignette", 0.05) == 0.15
    assert bank.clamp_asset_opacity("dark_vignette", 0.65) == 0.35
    assert bank.clamp_asset_opacity("dark_vignette", 0.28) == 0.28
    assert bank.clamp_asset_opacity("dark_vignette", 0.0) == 0.0
    assert bank.clamp_asset_opacity("dark_vignette", None) == 0.25

    # Non-atmospheric asset bounds [0.0, 1.0] or defaults
    assert bank.clamp_asset_opacity("rec_analog_hud", 0.8) == 0.8
    assert bank.clamp_asset_opacity("rec_analog_hud", 1.5) == 1.0
    assert bank.clamp_asset_opacity("rec_analog_hud", -0.2) == 0.0
    hud = bank.get_asset("rec_analog_hud")
    assert hud is not None
    assert bank.clamp_asset_opacity("rec_analog_hud", None) == hud.default_opacity


def test_validate_bank_integrity_all_pass(bank: GraphicsBank):
    """Verifies BankValidationReport.valid == True when all registered files exist on disk with valid headers."""
    report = bank.validate_bank()
    assert isinstance(report, BankValidationReport)
    assert report.valid is True
    assert report.total_assets >= 16
    assert report.verified_assets == report.total_assets
    assert len(report.missing_assets) == 0
    assert len(report.corrupted_assets) == 0
    assert len(report.oversized_assets) == 0
    assert len(report.errors) == 0


def test_validate_bank_missing_file_detection(tmp_path: Path):
    """Verifies missing on-disk files are flagged in missing_assets with valid == False."""
    missing_manifest = {
        "version": "1.0.0",
        "assets": [
            {
                "id": "missing_ghost_file",
                "name": "Ghost File",
                "category": "atmospheric",
                "channel_affinity": "all",
                "aspect_ratios": ["9:16"],
                "relative_path": "assets/overlays/static/nonexistent_ghost.png",
                "safe_zone_compliant": True,
                "default_opacity": 0.25,
            }
        ],
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(missing_manifest), encoding="utf-8")
    bank = GraphicsBank(base_dir=tmp_path, manifest_path=p)
    report = bank.validate_bank()
    assert report.valid is False
    assert "missing_ghost_file" in report.missing_assets


def test_validate_bank_oversized_file_detection(tmp_path: Path):
    """Verifies assets exceeding 200 KB (PNG) or 500 KB (SVG) are captured in oversized_assets."""
    png_path = tmp_path / "assets" / "large.png"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    # Write > 200 KB dummy file
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (205 * 1024))

    oversized_manifest = {
        "version": "1.0.0",
        "assets": [
            {
                "id": "large_png",
                "name": "Large PNG",
                "category": "atmospheric",
                "channel_affinity": "all",
                "aspect_ratios": ["9:16"],
                "relative_path": "assets/large.png",
                "safe_zone_compliant": True,
                "default_opacity": 0.25,
            }
        ],
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(oversized_manifest), encoding="utf-8")
    bank = GraphicsBank(base_dir=tmp_path, manifest_path=p)
    report = bank.validate_bank()
    assert report.valid is False
    assert "large_png" in report.oversized_assets


def test_singleton_get_graphics_bank():
    """Verifies singleton helper get_graphics_bank returns consistent instance."""
    b1 = get_graphics_bank()
    b2 = get_graphics_bank()
    assert b1 is b2
