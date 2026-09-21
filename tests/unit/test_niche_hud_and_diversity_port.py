"""Ported product value from PR #2 onto cheap-director main: niche HUDs + shorts diversity."""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lib.qa.diversity_gate import audit_scene_diversity, evaluate_scene_diversity
from src.media.encode_defaults import default_render_crf, default_render_preset
from src.media.multi_act_renderer import (
    HUD_BORDERW,
    HUD_FONT_META,
    HUD_FONT_PRIMARY,
    HUD_FONT_SECONDARY,
    MultiActVideoRenderer,
    NarrativeSceneAct,
    NicheHudConfig,
    build_niche_hud_filter,
    hud_safe_margins,
    niche_hud_from_act,
    niche_hud_from_mapping,
    resolve_hud_accent_color,
    _escape_ffmpeg_color,
)
from src.media.manifest_compiler import validate_hex_color
from src.media.thumbnails.asset_resolver import ThematicAssetResolver
from src.media.thumbnails.layout import AspectLayoutManager


def test_niche_hud_top_bar_filter_escaping():
    renderer = MultiActVideoRenderer()
    scp_cfg = NicheHudConfig(
        lane_id="moku-scp-shorts",
        story_type="scp",
        hud_layout="top_bar",
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


def test_niche_hud_card_and_bottom_bar_layouts():
    renderer = MultiActVideoRenderer()
    reddit = renderer.build_scene_hud_filter(
        1920,
        1080,
        NicheHudConfig(
            story_type="reddit_aita",
            hud_layout="card",
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
            hud_layout="bottom_bar",
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
    assert default_render_crf() == 19


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


def test_shorts_min_scenes_is_four_aligned_with_dominance():
    """Conservative policy: min_short_scenes=4 so equal cuts stay ≤25% dominance.

    With 3 equal scenes each is ~33% > 25%; requiring ≥4 keeps min-count and
    the 25% dominance ceiling coherent (4 × 25% passes strict ``> 0.25``).
    Dominance still applies to shorts (not longform-only).
    """
    three = {
        "duration_sec": 45.0,
        "scenes": [
            {"duration_sec": 15.0, "image_path": f"/s{i}.mp4"} for i in range(3)
        ],
    }
    passed, code, msg, _ = audit_scene_diversity(three, duration_sec=45.0, is_short=True)
    assert not passed
    assert code == "ERR_QA_SHORT_DIVERSITY_INSUFFICIENT"
    assert "at least 4" in msg

    four = {
        "duration_sec": 50.0,
        "scenes": [
            {"duration_sec": 12.5, "image_path": f"/s{i}.mp4"} for i in range(4)
        ],
    }
    passed, code, _, _ = audit_scene_diversity(four, duration_sec=50.0, is_short=True)
    assert passed
    assert code == "OK_SCENE_DIVERSITY"


def test_asset_dominance_applies_without_longform_floor():
    """Dominance applies to shorts too (any length when runtime known)."""
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


def test_qa_gatekeeper_diversity_audit_fails_closed_in_strict(tmp_path, monkeypatch):
    """Silent except-return is forbidden: strict mode must surface audit failures."""
    from lib.qa_gatekeeper import QAGatekeeper

    mpath = tmp_path / "scene_manifest.json"
    mpath.write_text("{not-json", encoding="utf-8")
    gk = QAGatekeeper(strict_mode=True)
    issues: list = []
    gk._audit_scene_diversity(str(mpath), "short", issues)
    assert any(i.code == "ERR_QA_SCENE_DIVERSITY_AUDIT_FAILED" for i in issues)
    assert any(i.severity == "CRITICAL" for i in issues)


def test_niche_hud_prefers_planner_mapping_on_act():
    planner = {
        "lane_id": "moku-scp-shorts",
        "story_type": "scp",
        "hud_layout": "top_bar",
        "hud_badge": "NIVEL 5 // KETER",
        "hud_site": "SITIO-19",
        "telemetry_label": "CAM-07",
        "accent_color_hex": "#00FF66",
        "tension_level": 5,
    }
    mapped = niche_hud_from_mapping(planner)
    assert mapped.story_type == "scp"
    assert mapped.hud_layout == "top_bar"
    act = NarrativeSceneAct(
        act_index=0,
        start_sec=0.0,
        duration_sec=10.0,
        title="t",
        theme_category="reddit_aita",
        niche_hud=planner,
    )
    cfg = niche_hud_from_act(act)
    assert cfg.story_type == "scp"
    assert cfg.hud_layout == "top_bar"
    assert cfg.hud_site == "SITIO-19"
    assert cfg.tension_level == 5


def test_niche_hud_from_act_does_not_map_theme_to_layout():
    act = NarrativeSceneAct(
        act_index=0,
        start_sec=0.0,
        duration_sec=10.0,
        title="t",
        theme_category="reddit_aita",
        hud_badge="BADGE",
        hud_site="SITE",
        hud_telemetry="TEL",
        color_hex="#ABCDEF",
    )
    cfg = niche_hud_from_act(act)
    assert cfg.story_type == "reddit_aita"  # free label preserved
    assert cfg.hud_layout == "top_bar"  # default; not card from theme keyword
    assert cfg.hud_badge == "BADGE"


def test_hud_geometry_ignores_story_type_strings():
    """story_type containing scp/aita/reddit must not select geometry."""
    renderer = MultiActVideoRenderer()
    # story_type looks like scp but layout is card -> card geometry (centered card, not full-width top bar)
    card = renderer.build_scene_hud_filter(
        1920,
        1080,
        NicheHudConfig(
            story_type="scp_found_footage",
            hud_layout="card",
            hud_badge="B",
            hud_site="S",
            telemetry_label="T",
            accent_color_hex="#FF4500",
        ),
        10.0,
    )
    boxes = _hud_boxes(card)
    assert boxes
    # card width is min(content_w, 860) — narrower than full safe content width
    assert any(bw <= 860 for _, _, bw, _ in boxes)
    # story_type looks like reddit but layout is top_bar -> full-width top bar
    top = renderer.build_scene_hud_filter(
        1920,
        1080,
        NicheHudConfig(
            story_type="reddit_aita_drama",
            hud_layout="top_bar",
            hud_badge="B",
            hud_site="S",
            telemetry_label="T",
            accent_color_hex="#00FF66",
            tension_level=1,
        ),
        10.0,
    )
    top_boxes = _hud_boxes(top)
    assert top_boxes
    assert any(bw > 860 for _, _, bw, _ in top_boxes)


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
    import src.media.thumbnails.asset_resolver as ar
    monkeypatch.setattr(ar, "REPO_ROOT", tmp_path)

    class FakeRepo:
        def get_best_loop(self, **kwargs):
            return None

    monkeypatch.setattr(
        "src.core.catalog.LoopCatalogRepository",
        lambda *a, **k: FakeRepo(),
        raising=False,
    )

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
    """Title-card orphans live in quarantine; scenery stays clean; templates remain."""
    templates = Path("assets/thumbnails/templates")
    for p in (
        templates / "aita" / "master_backdrop.jpg",
        templates / "horror" / "master_backdrop.jpg",
        templates / "scp" / "master_backdrop.jpg",
    ):
        assert p.is_file() and p.stat().st_size > 1000

    root = Path("assets/visual_bank")
    if not root.exists():
        return
    quarantine = root / "_quarantine_title_cards"
    # Must NOT reappear under scenery/ (would freeze as video backgrounds)
    for banned in (
        root / "aelithia" / "scenery" / "dna_secret.jpg",
        root / "moku" / "scenery" / "abyssal_creature.jpg",
        root / "moku" / "scenery" / "scp_3008_infinite.jpg",
        root / "moku" / "scenery" / "scp_containment.jpg",
    ):
        assert not banned.is_file(), f"title card leaked back into scenery: {banned}"
    quarantined = [
        quarantine / "aelithia" / "dna_secret.jpg",
        quarantine / "moku" / "abyssal_creature.jpg",
        quarantine / "moku" / "scp_3008_infinite.jpg",
        quarantine / "moku" / "scp_containment.jpg",
    ]
    for p in quarantined:
        assert p.is_file() and p.stat().st_size > 1000


def test_scene_config_does_not_widen_extra_allow():
    from src.scene_manifest import SceneConfig
    # Unknown keys ignored (default), known niche fields accepted — no extra="allow".
    sc = SceneConfig(
        scene_index=1,
        scene_id="s1",
        start_sec=0.0,
        duration_sec=5.0,
        tension_level=2,
        engine_type="catalog_loop",
        niche_hud={"story_type": "scp"},
        image_path="/x.jpg",
        asset_path="/x.jpg",
        totally_unknown_field="drop-me",  # type: ignore[call-arg]
    )
    assert sc.niche_hud["story_type"] == "scp"
    assert not hasattr(sc, "totally_unknown_field")
    src = Path("src/scene_manifest.py").read_text(encoding="utf-8")
    assert "model_config = ConfigDict(extra=" not in src
    assert 'ConfigDict(extra="allow")' not in src


def _hud_boxes(filter_str: str):
    return [
        tuple(map(int, m.groups()))
        for m in re.finditer(r"drawbox=x=(\d+):y=(\d+):w=(\d+):h=(\d+)", filter_str)
    ]


def test_shorts_hud_respects_thumbnail_safe_zone_all_layouts():
    """Shorts HUD bars/cards must stay inside AspectLayoutManager safe-zone."""
    w, h = 1080, 1920
    safe = AspectLayoutManager.get_safe_zone(w, h)
    renderer = MultiActVideoRenderer()
    niches = [
        NicheHudConfig(
            lane_id="moku-scp-shorts",
            story_type="scp",
            hud_layout="top_bar",
            hud_badge="NIVEL 5",
            hud_site="SITIO-19",
            telemetry_label="CAM-01",
            accent_color_hex="#00FF66",
            tension_level=4,
        ),
        NicheHudConfig(
            lane_id="aelithia-aita-shorts",
            story_type="reddit_aita",
            hud_layout="card",
            hud_badge="r/AmItheAsshole",
            hud_site="OP: u/test",
            telemetry_label="1.2k upvotes",
            accent_color_hex="#FF4081",
        ),
        NicheHudConfig(
            lane_id="moku-horror-shorts",
            story_type="horror",
            hud_layout="bottom_bar",
            hud_badge="ABYSSAL",
            hud_site="PROFUNDIDAD: 4000M",
            telemetry_label="ECO",
            accent_color_hex="#00FF66",
        ),
    ]
    for cfg in niches:
        filt = renderer.build_scene_hud_filter(w, h, cfg, 12.0)
        boxes = _hud_boxes(filt)
        assert boxes, cfg.hud_layout
        for x, y, bw, bh in boxes:
            assert x >= safe.left - 1, (cfg.hud_layout, x, safe.left)
            assert x + bw <= safe.right + 1, (cfg.hud_layout, x + bw, safe.right)
            assert y >= safe.top - 1, (cfg.hud_layout, y, safe.top)
            assert y + bh <= safe.bottom + 1, (cfg.hud_layout, y + bh, safe.bottom)
        # Must not sit in the Shorts bottom UI collision band
        assert all(y + bh < int(h * 0.75) for _, y, _, bh in boxes)


def test_hud_font_stroke_consistent_across_niches():
    renderer = MultiActVideoRenderer()
    sizes = {
        HUD_FONT_PRIMARY,
        HUD_FONT_PRIMARY + 2,  # vertical bump
        HUD_FONT_SECONDARY,
        HUD_FONT_META,
    }
    for layout, lane in (("top_bar", "moku-scp-shorts"), ("card", "aelithia"), ("bottom_bar", "moku")):
        filt = renderer.build_scene_hud_filter(
            1080,
            1920,
            NicheHudConfig(
                lane_id=lane,
                story_type="label-only",
                hud_layout=layout,
                hud_badge="BADGE",
                hud_site="SITE",
                telemetry_label="TEL",
                accent_color_hex="#ABCDEF",
            ),
            10.0,
        )
        assert f"borderw={HUD_BORDERW}" in filt
        found = {int(m.group(1)) for m in re.finditer(r"fontsize=(\d+)", filt)}
        assert found, layout
        assert found <= sizes, (layout, found, sizes)


def test_resolve_hud_accent_from_channel_when_missing():
    # Code default -> channel palette (moku / aelithia)
    assert resolve_hud_accent_color("#00FF88", lane_id="moku-scp-shorts", story_type="scp") == "#00FF66"
    assert resolve_hud_accent_color("", lane_id="aelithia-aita-long", story_type="reddit_aita") == "#FF4081"
    # Explicit non-default accent is preserved
    assert resolve_hud_accent_color("#112233", lane_id="moku", story_type="scp") == "#112233"


def test_hud_safe_margins_match_thumbnail_layout():
    for w, h in ((1080, 1920), (1920, 1080)):
        safe = AspectLayoutManager.get_safe_zone(w, h)
        m = hud_safe_margins(w, h)
        assert m["left"] == safe.left
        assert m["top"] == safe.top
        assert m["bottom"] == safe.bottom
        assert m["right"] == safe.right


def test_build_niche_hud_filter_module_api_matches_renderer():
    cfg = NicheHudConfig(
        story_type="scp",
        hud_layout="top_bar",
        hud_badge="B",
        hud_site="S",
        accent_color_hex="#00FF66",
    )
    a = build_niche_hud_filter(1080, 1920, cfg, 8.0)
    b = MultiActVideoRenderer().build_scene_hud_filter(1080, 1920, cfg, 8.0)
    assert a == b


def test_escape_ffmpeg_color_rejects_corrupt_hex():
    assert _escape_ffmpeg_color("#00FF66") == "#00FF66"
    assert _escape_ffmpeg_color("#ff4081") == "#FF4081"
    assert _escape_ffmpeg_color("0x00F0FF") == "#00F0FF"
    assert _escape_ffmpeg_color("malicious:box=1", default="#00FF88") == "#00FF88"
    assert validate_hex_color("bad", default="#AABBCC") == "#AABBCC"


def test_corrupt_accent_does_not_leak_into_ffmpeg_filter():
    filt = MultiActVideoRenderer().build_scene_hud_filter(
        1080,
        1920,
        NicheHudConfig(
            hud_layout="top_bar",
            hud_badge="TEST",
            hud_site="SITE",
            telemetry_label="TEL",
            accent_color_hex="malicious:box=1;rm",
        ),
        10.0,
    )
    assert "malicious" not in filt
    assert "#00FF88" in filt
