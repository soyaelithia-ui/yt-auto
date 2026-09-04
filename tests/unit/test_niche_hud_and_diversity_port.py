"""Ported product value from PR #2 onto cheap-director main: niche HUDs + shorts diversity."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.media.multi_act_renderer import MultiActVideoRenderer, NicheHudConfig
from lib.qa.diversity_gate import audit_scene_diversity, evaluate_scene_diversity
from src.media.thumbnails.asset_resolver import ThematicAssetResolver
from src.media.encode_defaults import default_render_crf, default_render_preset


def test_niche_hud_scp_filter_escaping():
    renderer = MultiActVideoRenderer()
    scp_cfg = NicheHudConfig(
        lane_id="moku-scp-shorts",
        story_type="scp",
        hud_badge="NIVEL 5 // 'EUCLID': CLASIFICADO",
        hud_site="SITIO-19: SECTOR-04",
        telemetry_label="CAM-02: CONTENCIÓN PRIMARIA",
        accent_color_hex="#00FF66",
        tension_level=4,
    )
    filter_str = renderer.build_scene_hud_filter(1080, 1920, scp_cfg, 12.0)
    assert "drawbox=" in filter_str
    assert "drawtext=" in filter_str
    assert "#00FF66" in filter_str
    assert "ALERT" in filter_str or "alert" in filter_str.lower()
    # Colons in drawtext text values must be escaped
    assert "SITIO-19\\:" in filter_str or "SITIO-19\\\\:" in filter_str


def test_niche_hud_reddit_and_abyssal_lanes():
    renderer = MultiActVideoRenderer()
    reddit = renderer.build_scene_hud_filter(
        1920,
        1080,
        NicheHudConfig(
            story_type="reddit_aita",
            hud_badge="r/AmItheAsshole",
            hud_site="OP: u/throwaway_dinner",
            telemetry_label="14.8k upvotes",
            accent_color_hex="#FF4500",
        ),
        15.0,
    )
    assert "r/AmItheAsshole" in reddit
    assert "drawbox=" in reddit

    horror = renderer.build_scene_hud_filter(
        1920,
        1080,
        NicheHudConfig(
            story_type="horror",
            hud_badge="EXPEDICIÓN ABISAL",
            hud_site="FOSA DE LAS MARIANAS",
            telemetry_label="PROFUNDIDAD: 4820m",
            accent_color_hex="#00D4FF",
        ),
        18.0,
    )
    assert "4820m" in horror
    assert "#00D4FF" in horror


def test_multiact_hud_reencode_uses_encode_defaults(monkeypatch):
    monkeypatch.delenv("RENDER_PRESET", raising=False)
    monkeypatch.delenv("RENDER_CRF", raising=False)
    src = Path("src/media/multi_act_renderer.py").read_text(encoding="utf-8")
    assert "default_render_preset()" in src
    assert "default_render_crf()" in src
    assert '"-crf", "19"' not in src
    assert default_render_preset() == "veryfast"
    assert default_render_crf() == 21


def test_shorts_diversity_insufficient_scenes():
    manifest = {
        "duration_sec": 45.0,
        "scenes": [
            {"duration_sec": 22.5, "image_path": "/a.mp4"},
            {"duration_sec": 22.5, "image_path": "/b.mp4"},
        ],
    }
    passed, code, msg, _ = audit_scene_diversity(manifest, duration_sec=45.0, is_short=True)
    assert not passed
    assert code == "ERR_QA_SHORT_DIVERSITY_INSUFFICIENT"


def test_shorts_diversity_passes_with_three_scenes():
    # 4 distinct assets × 12.5s = 50s → 25% each (dominance uses strict > 0.25)
    manifest = {
        "duration_sec": 50.0,
        "scenes": [
            {"duration_sec": 12.5, "image_path": f"/s{i}.mp4"} for i in range(4)
        ],
    }
    passed, code, _, _ = audit_scene_diversity(manifest, duration_sec=50.0, is_short=True)
    assert passed
    assert code == "OK_SCENE_DIVERSITY"


def test_asset_dominance_applies_without_longform_floor():
    """Mission: block if one asset >25% runtime (any length when evaluated)."""
    manifest = {
        "duration_sec": 80.0,
        "scenes": [
            {"duration_sec": 50.0, "image_path": "/dom.mp4"},
            {"duration_sec": 10.0, "image_path": "/a.mp4"},
            {"duration_sec": 10.0, "image_path": "/b.mp4"},
            {"duration_sec": 10.0, "image_path": "/c.mp4"},
        ],
    }
    passed, code, msg, _ = audit_scene_diversity(manifest, duration_sec=80.0, is_short=True)
    assert not passed
    assert code == "ERR_QA_ASSET_DOMINANCE_EXCEEDED"


def test_evaluate_scene_diversity_dict_api():
    res = evaluate_scene_diversity(
        {"duration_sec": 600.0, "scenes": [{"duration_sec": 150.0, "asset_path": f"/x{i}.mp4"} for i in range(4)]},
        is_short=False,
    )
    assert res["is_passed"] is False
    assert res["failure_code"] == "ERR_QA_SCENE_DIVERSITY_INSUFFICIENT"


def test_qa_gatekeeper_wires_scene_diversity(tmp_path, monkeypatch):
    from lib.qa_gatekeeper import QAGatekeeper, QualityReportIssue

    manifest = {
        "duration_sec": 45.0,
        "scenes": [
            {"duration_sec": 22.5, "image_path": "/a.mp4"},
            {"duration_sec": 22.5, "image_path": "/b.mp4"},
        ],
    }
    mpath = tmp_path / "scene_manifest.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    video = tmp_path / "out.mp4"
    video.write_bytes(b"\x00" * 64)

    gk = QAGatekeeper(strict_mode=True)
    issues: list = []
    gk._audit_scene_diversity(str(mpath), "short", issues)
    assert any(i.code == "ERR_QA_SHORT_DIVERSITY_INSUFFICIENT" for i in issues)


def test_thematic_asset_resolver_scene_rotation(tmp_path, monkeypatch):
    bank = tmp_path / "visual_bank" / "moku" / "scenery"
    bank.mkdir(parents=True)
    paths = []
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        p = bank / name
        p.write_bytes(b"fake")
        paths.append(p)

    monkeypatch.setattr(
        "src.media.thumbnails.asset_resolver.VISUAL_BANK_DIR",
        tmp_path / "visual_bank",
    )
    monkeypatch.setattr(
        "src.media.thumbnails.asset_resolver.TEMPLATES_DIR",
        tmp_path / "templates",
    )
    (tmp_path / "templates").mkdir()

    p1 = ThematicAssetResolver.resolve_scene_asset_path(
        channel_id="moku-scp", archetype="scp", scene_idx=1
    )
    p2 = ThematicAssetResolver.resolve_scene_asset_path(
        channel_id="moku-scp", archetype="scp", scene_idx=2
    )
    p3 = ThematicAssetResolver.resolve_scene_asset_path(
        channel_id="moku-scp", archetype="scp", scene_idx=3
    )
    assert p1 != p2 or p2 != p3
    assert p1.parent == bank
    assert ThematicAssetResolver.resolve_scene_asset_path(
        channel_id="moku", archetype="scp", scene_idx=4
    ) == p1  # rotation wraps


def test_visual_bank_scenery_assets_present():
    root = Path("assets/visual_bank")
    expected = [
        root / "aelithia" / "scenery" / "dna_secret.jpg",
        root / "aelithia" / "scenery" / "wedding_drama.jpg",
        root / "moku" / "scenery" / "abyssal_creature.jpg",
        root / "moku" / "scenery" / "radio_station.jpg",
        root / "moku" / "scenery" / "scp_3008_infinite.jpg",
        root / "moku" / "scenery" / "scp_containment.jpg",
    ]
    for p in expected:
        assert p.is_file() and p.stat().st_size > 1000
