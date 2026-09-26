"""Guards: baked title cards cannot re-enter video background / scenery pools."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.asset_manager import AssetManager, is_eligible_background_asset
from src.core.catalog import LoopRecord
from src.media.thumbnails.asset_resolver import (
    ThematicAssetResolver,
    _is_clean_visual_candidate,
)


REPO = Path(__file__).resolve().parents[2]
QUARANTINE = REPO / "assets" / "visual_bank" / "_quarantine_title_cards"
SCENERY_HORROR = REPO / "assets" / "visual_bank" / "horror" / "scenery"
SCENERY_DRAMA = REPO / "assets" / "visual_bank" / "drama" / "scenery"


def test_repo_quarantine_layout_and_empty_scenery():
    if not QUARANTINE.exists():
        assert not QUARANTINE.exists()
        assert not SCENERY_HORROR.exists()
        assert not SCENERY_DRAMA.exists()
        return
    assert (QUARANTINE / "README.md").is_file()
    for name in ("abyssal_creature.jpg", "scp_3008_infinite.jpg", "scp_containment.jpg"):
        assert (QUARANTINE / "horror" / name).is_file()
        assert not (SCENERY_HORROR / name).is_file()
    assert (QUARANTINE / "drama" / "dna_secret.jpg").is_file()
    assert not (SCENERY_DRAMA / "dna_secret.jpg").is_file()
    # scenery dirs may only contain keepers / clean assets
    for folder in (SCENERY_HORROR, SCENERY_DRAMA):
        for p in folder.iterdir():
            if p.name.startswith("."):
                continue
            assert _is_clean_visual_candidate(p)
            assert is_eligible_background_asset(str(p))


def test_index_json_scenery_empty_of_quarantined_files():
    idx_p = REPO / "assets" / "visual_bank" / "index.json"
    if not idx_p.exists():
        return
    index = json.loads(idx_p.read_text(encoding="utf-8"))
    for ch, data in index["channels"].items():
        for entry in data["categories"].get("scenery", []):
            path = entry.get("path", "")
            assert "_quarantine" not in path
            assert Path(path).is_file() if path else True
            fname = entry.get("file", "")
            assert fname not in {
                "abyssal_creature.jpg",
                "scp_3008_infinite.jpg",
                "scp_containment.jpg",
                "dna_secret.jpg",
            }


def test_live_asset_manager_excludes_quarantine_and_gifs():
    mgr = AssetManager(root_dir=str(REPO / "assets"))
    all_bgs = [p for paths in mgr._index["backgrounds"].values() for p in paths]
    assert not any("_quarantine_title_cards" in p for p in all_bgs)
    assert not any(p.lower().endswith(".gif") for p in all_bgs)
    assert not any("/overlays/" in p.replace("\\", "/") for p in all_bgs)
    assert not any("ambient_gifs" in p for p in all_bgs)


def test_resolve_scene_skips_quarantine_prefers_motion(tmp_path, monkeypatch):
    bank = tmp_path / "visual_bank"
    scenery = bank / "horror" / "scenery"
    quarantine = bank / "_quarantine_title_cards" / "horror"
    scenery.mkdir(parents=True)
    quarantine.mkdir(parents=True)
    (quarantine / "abyssal_creature.jpg").write_bytes(b"title")
    # No clean scenery — resolver must not pick quarantine
    templates = tmp_path / "templates" / "scp"
    templates.mkdir(parents=True)
    (templates / "master_backdrop.jpg").write_bytes(b"template")

    # resolve_scene looks under REPO_ROOT/assets/loops/web_procedural
    loops_dir = tmp_path / "assets" / "loops" / "web_procedural" / "atmospheric_landscape"
    loops_dir.mkdir(parents=True)
    loop = loops_dir / "loop.mp4"
    loop.write_bytes(b"fake_mp4")

    monkeypatch.setattr(
        "src.media.thumbnails.asset_resolver.VISUAL_BANK_DIR", bank
    )
    monkeypatch.setattr(
        "src.media.thumbnails.asset_resolver.TEMPLATES_DIR", tmp_path / "templates"
    )
    import src.media.thumbnails.asset_resolver as ar
    monkeypatch.setattr(ar, "REPO_ROOT", tmp_path)

    from src.core.catalog import LoopRecord

    class FakeRepo:
        def get_best_loop(self, **kwargs):
            return LoopRecord(
                loop_id="fake_loop",
                category="atmospheric_landscape",
                technology="web",
                orientation="vertical",
                width=1080,
                height=1920,
                duration_sec=10.0,
                fps=30,
                file_path=str(loop),
                file_size_bytes=100,
                sha256="abc",
            )

    monkeypatch.setattr(
        "src.core.catalog.LoopCatalogRepository",
        lambda *a, **k: FakeRepo(),
        raising=False,
    )

    resolved = ThematicAssetResolver.resolve_scene_asset_path(
        channel_id="horror-scp", archetype="scp", scene_idx=1, is_vertical=True
    )
    assert "_quarantine_title_cards" not in str(resolved)
    assert resolved == loop or resolved.suffix.lower() in {".mp4", ".webm", ".jpg", ".png"}
    # Prefer motion loop over static template when available
    assert resolved == loop


def test_resolve_scene_uses_clean_scenery_motion_first(tmp_path, monkeypatch):
    bank = tmp_path / "visual_bank"
    scenery = bank / "horror" / "scenery"
    scenery.mkdir(parents=True)
    still = scenery / "fog.jpg"
    motion = scenery / "fog_pan.mp4"
    still.write_bytes(b"still")
    motion.write_bytes(b"motion")

    monkeypatch.setattr(
        "src.media.thumbnails.asset_resolver.VISUAL_BANK_DIR", bank
    )
    monkeypatch.setattr(
        "src.media.thumbnails.asset_resolver.TEMPLATES_DIR", tmp_path / "templates"
    )
    (tmp_path / "templates").mkdir()

    resolved = ThematicAssetResolver.resolve_scene_asset_path(
        channel_id="horror", archetype="horror", scene_idx=1
    )
    assert resolved == motion


def test_bitacora_advertencia_paths_never_eligible():
    from src.asset_manager import is_eligible_background_asset

    bad = [
        "/assets/visual_bank/horror/scenery/BITÁCORA_perdida.jpg",
        "/assets/visual_bank/horror/scenery/bitacora_faro.png",
        "/tmp/ADVERTENCIA_tape04.jpg",
        "assets/visual_bank/horror/scenery/advertencia_ui.jpg",
    ]
    for p in bad:
        assert not is_eligible_background_asset(p), p
        assert not _is_clean_visual_candidate(Path(p)), p


def test_empty_scenery_falls_through_to_motion_loop(tmp_path, monkeypatch):
    """Empty scenery must never freeze on a baked title card / static thumbnail."""
    bank = tmp_path / "visual_bank"
    scenery = bank / "horror" / "scenery"
    quarantine = bank / "_quarantine_title_cards" / "horror"
    scenery.mkdir(parents=True)
    quarantine.mkdir(parents=True)
    (quarantine / "abyssal_creature.jpg").write_bytes(b"title")

    templates = tmp_path / "templates" / "scp"
    templates.mkdir(parents=True)
    (templates / "master_backdrop.jpg").write_bytes(b"template")

    loops_dir = tmp_path / "assets" / "loops" / "web_procedural" / "dark_ambient"
    loops_dir.mkdir(parents=True)
    loop = loops_dir / "loop.mp4"
    loop.write_bytes(b"fake_mp4")

    monkeypatch.setattr("src.media.thumbnails.asset_resolver.VISUAL_BANK_DIR", bank)
    monkeypatch.setattr("src.media.thumbnails.asset_resolver.TEMPLATES_DIR", tmp_path / "templates")
    import src.media.thumbnails.asset_resolver as ar
    monkeypatch.setattr(ar, "REPO_ROOT", tmp_path)

    from src.core.catalog import LoopRecord

    class FakeRepo:
        def get_best_loop(self, **kwargs):
            return LoopRecord(
                loop_id="fake_loop",
                category="dark_ambient",
                technology="web",
                orientation="vertical",
                width=1080,
                height=1920,
                duration_sec=10.0,
                fps=30,
                file_path=str(loop),
                file_size_bytes=100,
                sha256="abc",
            )

    monkeypatch.setattr(
        "src.core.catalog.LoopCatalogRepository",
        lambda *a, **k: FakeRepo(),
        raising=False,
    )

    resolved = ThematicAssetResolver.resolve_scene_asset_path(
        channel_id="horror-scp", archetype="scp", scene_idx=1, is_vertical=True
    )
    assert resolved == loop
    assert "_quarantine_title_cards" not in str(resolved)
    assert "master_backdrop" not in str(resolved)


def test_stills_only_scenery_prefers_loop_catalog(tmp_path, monkeypatch):
    """If scenery has only stills, prefer catalog/procedural loop before returning a still."""
    bank = tmp_path / "visual_bank"
    scenery = bank / "horror" / "scenery"
    scenery.mkdir(parents=True)
    still = scenery / "fog.jpg"
    still.write_bytes(b"still")

    loops_dir = tmp_path / "assets" / "loops" / "web_procedural" / "atmospheric_landscape"
    loops_dir.mkdir(parents=True)
    loop = loops_dir / "loop.mp4"
    loop.write_bytes(b"fake_mp4")

    monkeypatch.setattr("src.media.thumbnails.asset_resolver.VISUAL_BANK_DIR", bank)
    monkeypatch.setattr("src.media.thumbnails.asset_resolver.TEMPLATES_DIR", tmp_path / "templates")
    (tmp_path / "templates").mkdir()
    import src.media.thumbnails.asset_resolver as ar
    monkeypatch.setattr(ar, "REPO_ROOT", tmp_path)

    class FakeRepo2:
        def get_best_loop(self, **kwargs):
            return LoopRecord(
                loop_id="fake_loop",
                category="atmospheric_landscape",
                technology="web",
                orientation="horizontal",
                width=1920,
                height=1080,
                duration_sec=10.0,
                fps=30,
                file_path=str(loop),
                file_size_bytes=100,
                sha256="abc",
            )

    monkeypatch.setattr(
        "src.core.catalog.LoopCatalogRepository",
        lambda *a, **k: FakeRepo2(),
        raising=False,
    )

    resolved = ThematicAssetResolver.resolve_scene_asset_path(
        channel_id="horror", archetype="horror", scene_idx=1
    )
    assert resolved == loop
    assert resolved != still


def test_overlays_and_gifs_excluded_from_clean_candidates(tmp_path):
    bank = tmp_path / "visual_bank" / "horror"
    overlays = bank / "overlays"
    gifs = bank / "ambient_gifs"
    scenery = bank / "scenery"
    overlays.mkdir(parents=True)
    gifs.mkdir(parents=True)
    scenery.mkdir(parents=True)
    ov = overlays / "vignette.png"
    gf = gifs / "fog.gif"
    st = scenery / "clean.jpg"
    ov.write_bytes(b"ov")
    gf.write_bytes(b"GIF")
    st.write_bytes(b"ok")

    assert not _is_clean_visual_candidate(ov)
    assert not _is_clean_visual_candidate(gf)
    assert _is_clean_visual_candidate(st)
    assert not is_eligible_background_asset(str(ov))
    assert not is_eligible_background_asset(str(gf))
    assert is_eligible_background_asset(str(st))
