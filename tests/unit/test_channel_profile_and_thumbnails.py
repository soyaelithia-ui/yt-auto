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
    assert moku.id == "horror"
    assert moku.editorial.public_name == "Expedientes de Terror"
    assert moku.visual.palette.accent == "#00FF66"
    assert "horror" in moku.visual.palette.lut_profile

    aelithia = ChannelProfileRegistry.get_channel("aelithia")
    assert aelithia.id == "drama"
    assert aelithia.editorial.public_name == "Dilemas Morales"
    assert aelithia.visual.palette.accent == "#FF4081"

    # Alias normalization
    assert ChannelProfileRegistry.get_channel("channel1").id == "horror"
    assert ChannelProfileRegistry.get_channel("channel2").id == "drama"
    assert ChannelProfileRegistry.get_channel("aita").id == "drama"
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


def test_former_scp_lane_falls_back_to_general_cinematic_vertical():
    from src.media.thumbnails.layouts.base import LayoutRegistry
    from src.media.thumbnails.layouts.cinematic import GeneralCinematicLayout

    layout = LayoutRegistry.get_layout(channel_id="moku-scp-shorts", archetype="scp")
    assert isinstance(layout, GeneralCinematicLayout)
    canvas = Image.new("RGB", (1080, 1920), (15, 20, 25))
    safe_zone = AspectLayoutManager.get_safe_zone(1080, 1920)

    result = layout.apply_layout(
        canvas=canvas,
        title="SCP-173 BRECHA DE CONTENCIÓN",
        channel_id="moku-scp-shorts",
        safe_zone=safe_zone,
        metadata={"hazard_level": "EUCLID", "site": "SITE-19"},
    )

    assert result.size == (1080, 1920)
    diff = sum(c1 != c2 for c1, c2 in zip(canvas.tobytes(), result.tobytes()))
    assert diff > 500
    assert safe_zone.bottom <= 1920 - 450


def test_former_reddit_lane_falls_back_to_general_cinematic_horizontal():
    from src.media.thumbnails.layouts.base import LayoutRegistry
    from src.media.thumbnails.layouts.cinematic import GeneralCinematicLayout

    layout = LayoutRegistry.get_layout(channel_id="aelithia-aita-long", archetype="aita")
    assert isinstance(layout, GeneralCinematicLayout)
    canvas = Image.new("RGB", (1920, 1080), (25, 25, 30))
    safe_zone = AspectLayoutManager.get_safe_zone(1920, 1080)

    result = layout.apply_layout(
        canvas=canvas,
        title="¿SOY LA MALA POR ARRUINAR LA BODA?",
        channel_id="aelithia-aita-long",
        safe_zone=safe_zone,
        metadata={"subreddit": "r/AmItheAsshole", "upvotes": "28.4k"},
    )

    assert result.size == (1920, 1080)
    diff = sum(c1 != c2 for c1, c2 in zip(canvas.tobytes(), result.tobytes()))
    assert diff > 500
    assert safe_zone.right <= 1920 * 0.88
    assert safe_zone.bottom <= 1080 * 0.90


def test_niche_layout_analog_horror_vhs_horizontal():
    from src.media.thumbnails.layouts.analog_horror import AnalogHorrorVhsLayout

    layout = AnalogHorrorVhsLayout()
    canvas = Image.new("RGB", (1920, 1080), (10, 12, 16))
    safe_zone = AspectLayoutManager.get_safe_zone(1920, 1080)

    result = layout.apply_layout(
        canvas=canvas,
        title="TRANSMISIÓN NO AUTORIZADA",
        channel_id="moku",
        safe_zone=safe_zone,
        metadata={"tape_id": "TAPE-04", "channel_tag": "CH 03"},
    )

    assert result.size == (1920, 1080)
    diff = sum(c1 != c2 for c1, c2 in zip(canvas.tobytes(), result.tobytes()))
    assert diff > 1000


def test_niche_layout_general_cinematic_fallback():
    from src.media.thumbnails.layouts.cinematic import GeneralCinematicLayout

    layout = GeneralCinematicLayout()
    canvas = Image.new("RGB", (1920, 1080), (18, 18, 18))
    safe_zone = AspectLayoutManager.get_safe_zone(1920, 1080)

    result = layout.apply_layout(
        canvas=canvas,
        title="EL MISTERIO DEL TIEMPO",
        channel_id="unknown_lane",
        safe_zone=safe_zone,
        metadata={},
    )

    assert result.size == (1920, 1080)
    diff = sum(c1 != c2 for c1, c2 in zip(canvas.tobytes(), result.tobytes()))
    assert diff > 500


def test_layout_registry_dispatch():
    from src.media.thumbnails.layouts.base import LayoutRegistry
    from src.media.thumbnails.layouts.analog_horror import AnalogHorrorVhsLayout
    from src.media.thumbnails.layouts.cinematic import GeneralCinematicLayout

    # Former scp/reddit modules removed — fall back to GeneralCinematicLayout
    layout_scp = LayoutRegistry.get_layout(channel_id="moku-scp-shorts", archetype="scp")
    assert isinstance(layout_scp, GeneralCinematicLayout)

    layout_reddit = LayoutRegistry.get_layout(channel_id="aelithia-aita-long", archetype="aita")
    assert isinstance(layout_reddit, GeneralCinematicLayout)

    layout_horror = LayoutRegistry.get_layout(channel_id="moku-horror-long", archetype="horror")
    assert isinstance(layout_horror, AnalogHorrorVhsLayout)

    layout_fallback = LayoutRegistry.get_layout(channel_id="unregistered_channel", archetype="other")
    assert isinstance(layout_fallback, GeneralCinematicLayout)


def test_typography_draw_text_with_effects_3d():
    canvas = Image.new("RGB", (1920, 1080), (10, 10, 15))
    safe_zone = AspectLayoutManager.get_safe_zone(1920, 1080)

    result = DynamicTypographyEngine.draw_text_with_effects(
        canvas=canvas,
        text="PELIGRO BIOLÓGICO EXTREMO",
        pos_x=safe_zone.left + 50,
        pos_y=safe_zone.top + 100,
        max_width=safe_zone.width - 100,
        font_name="Montserrat-Black.ttf",
        fill_color="#FFE600",
        stroke_color="#000000",
        stroke_width=12,
        shadow_offset=(8, 12),
        shadow_blur=4,
        glow_color="#FF003B",
        glow_radius=8,
        tilt_angle=-3.0,
    )

    assert result.size == (1920, 1080)
    diff = sum(c1 != c2 for c1, c2 in zip(canvas.tobytes(), result.tobytes()))
    assert diff > 1000


def test_typography_multiline_safe_splitting():
    # Long text over 30 chars with question/exclamation marks
    long_title = "¿POR QUÉ NADIE QUIERE DECIR LA VERDAD SOBRE ESTO?"
    lines = DynamicTypographyEngine.split_title_to_safe_lines(long_title, max_chars_per_line=20)
    assert len(lines) <= 2
    orig_words = long_title.split()
    for line in lines:
        for word in line.replace("…", "").split():
            assert word in orig_words
    assert " ".join(lines).split() == orig_words

    # Very long title over 60 chars
    extra_long = "¿POR QUÉ NADIE QUIERE DECIR LA VERDAD SOBRE EL EXPERIMENTO SECRETO?"
    lines_extra = DynamicTypographyEngine.split_title_to_safe_lines(extra_long, max_chars_per_line=20)
    assert len(lines_extra) <= 2
    extra_words = extra_long.split()
    for line in lines_extra:
        for word in line.replace("…", "").split():
            assert word in extra_words
    assert " ".join(lines_extra).split() == extra_words


def test_thematic_asset_resolver_hierarchy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from src.media.thumbnails.asset_resolver import ThematicAssetResolver

    # Tier 1: Explicit path
    explicit_file = tmp_path / "explicit_backdrop.png"
    img = Image.new("RGB", (1920, 1080), (120, 50, 80))
    img.save(explicit_file)

    resolved_t1 = ThematicAssetResolver.resolve_base_image(
        channel_id="moku",
        archetype="scp",
        target_size=(1920, 1080),
        explicit_path=explicit_file,
    )
    assert resolved_t1.size == (1920, 1080)
    # Check color matches explicit file
    assert resolved_t1.getpixel((100, 100)) == (120, 50, 80)

    # Tier 2: Asset bank resolution (seeded templates)
    resolved_t2_scp = ThematicAssetResolver.resolve_base_image(
        channel_id="moku-scp-shorts",
        archetype="scp",
        target_size=(1080, 1920),
    )
    assert resolved_t2_scp.size == (1080, 1920)

    resolved_t2_aita = ThematicAssetResolver.resolve_base_image(
        channel_id="aelithia",
        archetype="aita",
        target_size=(1920, 1080),
    )
    assert resolved_t2_aita.size == (1920, 1080)

    # Tier 3: Climax keyframe fallback from video when archetype not in template bank
    mock_vid = tmp_path / "synthetic_video.mp4"
    mock_vid.touch()
    mock_cand = tmp_path / "mock_climax_frame.png"
    Image.new("RGB", (1920, 1080), (33, 77, 99)).save(mock_cand)

    from src.media.thumbnails.extractor import ClimaxFrameExtractor
    monkeypatch.setattr(ClimaxFrameExtractor, "resolve_climax_timestamp", lambda self, **kw: 5.0)
    monkeypatch.setattr(ClimaxFrameExtractor, "extract_candidate_frames", lambda self, **kw: [mock_cand])
    monkeypatch.setattr(ClimaxFrameExtractor, "select_best_frame", lambda self, frames: mock_cand)

    resolved_t3 = ThematicAssetResolver.resolve_base_image(
        channel_id="custom_channel",
        archetype="cyberpunk_heist",
        target_size=(1920, 1080),
        video_path=mock_vid,
    )
    assert resolved_t3.size == (1920, 1080)
    pix = resolved_t3.getpixel((100, 100))
    assert abs(pix[0] - 33) <= 1 and abs(pix[1] - 77) <= 1 and abs(pix[2] - 99) <= 1

    # Tier 4: Fallback when no explicit, no asset bank match, and no video
    resolved_fallback = ThematicAssetResolver.resolve_base_image(
        channel_id="completely_new_niche",
        archetype="unknown_x",
        target_size=(1920, 1080),
    )
    assert resolved_fallback.size == (1920, 1080)


def test_qa_auditor_aspect_ratio_16_9_and_9_16(tmp_path: Path):
    from src.agents.qa_auditor import VisualAudioQAAuditorAgent

    auditor = VisualAudioQAAuditorAgent()
    engine = ThumbnailEngine()

    # 16:9 thumbnail
    thumb_16_9 = tmp_path / "valid_16_9.jpg"
    cfg_16_9 = ThumbnailConfig(
        title="INCIDENTE EN EL SECTOR 19",
        channel_id="moku",
        output_path=thumb_16_9,
        width=1920,
        height=1080,
    )
    engine.generate(config=cfg_16_9)
    passed_16_9, errs_16_9 = auditor.audit_thumbnail(thumb_16_9)
    assert passed_16_9 is True, f"16:9 audit failed: {errs_16_9}"

    # 9:16 thumbnail
    thumb_9_16 = tmp_path / "valid_9_16.jpg"
    cfg_9_16 = ThumbnailConfig(
        title="LA ENTIDAD DEL PANTANO",
        channel_id="moku-scp-shorts",
        output_path=thumb_9_16,
        width=1080,
        height=1920,
    )
    engine.generate(config=cfg_9_16)
    passed_9_16, errs_9_16 = auditor.audit_thumbnail(thumb_9_16)
    assert passed_9_16 is True, f"9:16 audit failed: {errs_9_16}"


def test_qa_auditor_rejects_low_contrast_or_small_file(tmp_path: Path):
    from src.agents.qa_auditor import VisualAudioQAAuditorAgent

    auditor = VisualAudioQAAuditorAgent()

    # Low contrast / flat image
    bad_img = Image.new("RGB", (1920, 1080), (128, 128, 128))
    bad_path = tmp_path / "low_contrast.jpg"
    bad_img.save(bad_path, "JPEG", quality=20)

    passed, errs = auditor.audit_thumbnail(bad_path)
    assert passed is False
    assert any("low contrast" in e.lower() or "size" in e.lower() for e in errs)


def test_qa_auditor_safe_zone_violation(tmp_path: Path):
    from src.agents.qa_auditor import VisualAudioQAAuditorAgent

    auditor = VisualAudioQAAuditorAgent()
    engine = ThumbnailEngine()

    thumb_path = tmp_path / "safe_zone_test.jpg"
    cfg = ThumbnailConfig(
        title="TITULO DE PRUEBA",
        output_path=thumb_path,
        width=1920,
        height=1080,
    )
    engine.generate(config=cfg)

    # Element explicitly penetrating timestamp zone [1570, 930, 1920, 1080]
    bad_elements = [(1600, 950, 1850, 1020)]
    passed, errs = auditor.audit_thumbnail(thumb_path, elements=bad_elements)
    assert passed is False
    assert any("safe-zone" in e.lower() for e in errs)


def test_qa_gatekeeper_thumbnail_wiring(tmp_path: Path):
    from lib.qa_gatekeeper import QAGatekeeper
    from src.agents.qa_auditor import VisualAudioQAAuditorAgent

    gk = QAGatekeeper(strict_mode=True)
    engine = ThumbnailEngine()

    good_thumb = tmp_path / "gk_good_thumb.jpg"
    engine.generate(ThumbnailConfig(title="PRUEBA GATEKEEPER", output_path=good_thumb))

    issues = []
    gk._audit_thumbnail_artifact(str(good_thumb), issues)
    assert len(issues) == 0

    # Bad thumbnail: flat grey image
    bad_thumb = tmp_path / "gk_bad_thumb.jpg"
    Image.new("RGB", (1920, 1080), (50, 50, 50)).save(bad_thumb, quality=30)

    issues_bad = []
    gk._audit_thumbnail_artifact(str(bad_thumb), issues_bad)
    assert len(issues_bad) > 0
    assert any(i.code == "ERR_QA_THUMBNAIL_DEFECT" for i in issues_bad)


def test_typography_auto_fit_downscale():
    canvas = Image.new("RGB", (1920, 1080), (10, 10, 10))
    # Render very long words in narrow width (500px)
    narrow_w = 500
    res = DynamicTypographyEngine.draw_text_with_effects(
        canvas=canvas,
        text="EXTRAORDINARIAMENTE PELIGROSO E INCONTROLABLE",
        pos_x=100,
        pos_y=200,
        max_width=narrow_w,
        font_size=110,
        tilt_angle=0.0,
    )
    assert res.size == (1920, 1080)
    # Ensure drawing succeeded and mutated canvas
    diff = sum(c1 != c2 for c1, c2 in zip(canvas.tobytes(), res.tobytes()))
    assert diff > 500


def test_general_cinematic_custom_metadata_and_colors():
    from src.media.thumbnails.layouts.cinematic import GeneralCinematicLayout

    safe_zone = AspectLayoutManager.get_safe_zone(1920, 1080)
    canvas = Image.new("RGB", (1920, 1080), (20, 20, 20))

    cinematic = GeneralCinematicLayout()
    res_h = cinematic.apply_layout(
        canvas=canvas,
        title="MI HISTORIA",
        channel_id="aelithia",
        safe_zone=safe_zone,
        metadata={
            "quote": "Descubrió la verdad oculta durante 10 años",
            "category": "CONFESIÓN ANÓNIMA",
            "primary_color": "#00FFCC",
            "accent_color": "#FF9900",
        },
    )
    assert res_h.size == (1920, 1080)

    scp_safe = AspectLayoutManager.get_safe_zone(1080, 1920)
    canvas_v = Image.new("RGB", (1080, 1920), (10, 15, 20))
    res_v = cinematic.apply_layout(
        canvas=canvas_v,
        title="SCP-096",
        channel_id="moku",
        safe_zone=scp_safe,
        metadata={
            "hazard_level": "EUCLID",
            "cam": "LONG-IDENTIFIER-SECURITY-CAM-SECTOR-09",
            "primary_color": "#00FFCC",
            "accent_color": "#FF003B",
        },
    )
    assert res_v.size == (1080, 1920)


def test_moku_lane_aspect_ratio_dispatch_and_asset_resolution():
    from PIL import ImageOps
    from src.media.thumbnails.layouts.base import LayoutRegistry
    from src.media.thumbnails.layouts.analog_horror import AnalogHorrorVhsLayout
    from src.media.thumbnails.layouts.cinematic import GeneralCinematicLayout
    from src.media.thumbnails.asset_resolver import ThematicAssetResolver, TEMPLATES_DIR

    # 1. Moku horizontal 16:9 -> AnalogHorrorVhsLayout and horror backdrop
    layout_h = LayoutRegistry.get_layout(channel_id="moku", is_vertical=False)
    assert isinstance(layout_h, AnalogHorrorVhsLayout)

    res_h = ThematicAssetResolver.resolve_base_image(channel_id="moku", archetype=None, target_size=(1920, 1080))
    assert res_h.size == (1920, 1080)
    horror_ref = Image.open(TEMPLATES_DIR / "horror" / "master_backdrop.jpg")
    fit_h = ImageOps.fit(horror_ref, (1920, 1080))
    assert sum(abs(c1 - c2) for c1, c2 in zip(res_h.getpixel((500, 500)), fit_h.getpixel((500, 500)))) == 0

    # 2. Moku vertical 9:16: former scp layout removed — cinematic fallback via channel key "moku"
    # (analog also registers "moku"; exact key match prefers AnalogHorrorVhsLayout)
    layout_v = LayoutRegistry.get_layout(channel_id="moku", is_vertical=True)
    assert isinstance(layout_v, (AnalogHorrorVhsLayout, GeneralCinematicLayout))

    res_v = ThematicAssetResolver.resolve_base_image(channel_id="moku", archetype=None, target_size=(1080, 1920))
    assert res_v.size == (1080, 1920)
    scp_ref = Image.open(TEMPLATES_DIR / "scp" / "master_backdrop.jpg")
    fit_v = ImageOps.fit(scp_ref, (1080, 1920))
    assert sum(abs(c1 - c2) for c1, c2 in zip(res_v.getpixel((500, 500)), fit_v.getpixel((500, 500)))) <= 5

    # Explicit former scp/reddit lane ids -> GeneralCinematicLayout
    assert isinstance(
        LayoutRegistry.get_layout(channel_id="moku-scp-shorts", archetype="scp"),
        GeneralCinematicLayout,
    )
    assert isinstance(
        LayoutRegistry.get_layout(channel_id="aelithia-aita-long", archetype="aita"),
        GeneralCinematicLayout,
    )


def test_qa_auditor_rejects_9_16_shorts_safe_zone_violations(tmp_path: Path):
    from src.agents.qa_auditor import VisualAudioQAAuditorAgent

    auditor = VisualAudioQAAuditorAgent()
    engine = ThumbnailEngine()

    # Generate a valid 9:16 thumbnail
    valid_path = tmp_path / "valid_shorts.jpg"
    engine.generate(ThumbnailConfig(
        title="TITULO SEGURO SHORTS",
        channel_id="moku-scp-shorts",
        output_path=valid_path,
        width=1080,
        height=1920,
    ))

    # 1. Element penetrating bottom 450px: y from 1600 to 1750
    bad_bot_elements = [(200, 1600, 600, 1750)]
    passed_bot, errs_bot = auditor.audit_thumbnail(valid_path, elements=bad_bot_elements)
    assert passed_bot is False
    assert any("shorts" in e.lower() for e in errs_bot)

    # 2. Element penetrating right 120px interaction rail: x from 980 to 1050
    bad_right_elements = [(980, 600, 1050, 750)]
    passed_right, errs_right = auditor.audit_thumbnail(valid_path, elements=bad_right_elements)
    assert passed_right is False
    assert any("shorts" in e.lower() for e in errs_right)

    # 3. Out-of-canvas element must NOT cause false positive
    out_elements = [(2000, 2000, 2100, 2100)]
    passed_out, errs_out = auditor.audit_thumbnail(valid_path, elements=out_elements)
    assert passed_out is True
    assert len(errs_out) == 0

    # 4. Pixel-level inspection: draw text in bottom 450px without passing elements
    viol_img = Image.open(valid_path).copy()
    from PIL import ImageDraw
    draw = ImageDraw.Draw(viol_img)
    draw.text((150, 1650), "TEXT IN FORBIDDEN OVERLAY", fill=(255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0))
    viol_path = tmp_path / "violating_shorts.jpg"
    viol_img.save(viol_path, "JPEG", quality=95)

    passed_pixel, errs_pixel = auditor.audit_thumbnail(viol_path)
    assert passed_pixel is False
    assert any("shorts bottom ui overlay" in e.lower() for e in errs_pixel)


def test_typography_left_align_with_rotation():
    canvas = Image.new("RGB", (1920, 1080), (0, 0, 0))
    # Should render cleanly with left alignment and tilt angle
    res = DynamicTypographyEngine.draw_text_with_effects(
        canvas=canvas,
        text="LEFT ALIGNED TITLE",
        pos_x=120,
        pos_y=150,
        max_width=600,
        align="left",
        tilt_angle=-3.5,
    )
    assert res.size == (1920, 1080)
    bbox = res.getbbox()
    assert bbox is not None
    # X coordinate must stay near pos_x (120) with padding margin
    assert 60 <= bbox[0] <= 140


def test_qa_gatekeeper_auto_discovers_thumbnail_artifact(tmp_path: Path):
    from lib.qa_gatekeeper import QAGatekeeper

    gk = QAGatekeeper(strict_mode=True)
    engine = ThumbnailEngine()

    # Create dummy video folder with video and thumbnail.jpg
    vid_dir = tmp_path / "production_out"
    vid_dir.mkdir()
    vid_path = vid_dir / "rendered_video.mp4"
    vid_path.touch()

    thumb_path = vid_dir / "thumbnail.jpg"
    engine.generate(ThumbnailConfig(title="VALID DISCOVERY THUMB", output_path=thumb_path))

    # Audit video without passing thumbnail_path - should auto-discover and succeed
    import unittest.mock as mock
    with mock.patch("lib.qa_gatekeeper.ffprobe") as mock_ffprobe, \
         mock.patch("lib.qa_gatekeeper.has_faststart", return_value=True), \
         mock.patch.object(gk, "_audit_audio_silence_and_volume", return_value=(0.0, -18.0, -1.0)), \
         mock.patch.object(gk, "_audit_freeze_and_black_frames", return_value=(0.0, 0.0)), \
         mock.patch.object(gk, "_audit_ebu_r128_loudness", return_value=(-14.0, -1.0, 5.0)):

        mock_ffprobe.return_value = {
            "format": {"duration": "10.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "profile": "Main", "pix_fmt": "yuv420p", "width": 1920, "height": 1080, "duration": "10.0"},
                {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": "48000", "duration": "10.0"},
            ]
        }
        report = gk.audit_video(video_path=str(vid_path), video_mode="longform")
        # Verify thumbnail was auto-discovered, audited, and passed
        assert not any(i.code == "ERR_QA_THUMBNAIL_DEFECT" for i in report.issues)


def test_parametric_cinematic_layout_text_box_styles(tmp_path: Path):
    from src.media.thumbnails.layouts.cinematic import GeneralCinematicLayout
    layout = GeneralCinematicLayout()
    safe_zone = AspectLayoutManager.get_safe_zone(1280, 720)
    canvas = Image.new("RGB", (1280, 720), (20, 24, 30))

    styles = ["badge", "boxed", "outline", "banner", "minimal"]
    for style in styles:
        out_img = layout.apply_layout(
            canvas=canvas,
            title=f"TEST STYLE {style.upper()}",
            channel_id="moku",
            safe_zone=safe_zone,
            metadata={"text_box_style": style},
        )
        assert out_img.size == (1280, 720)
        p = tmp_path / f"thumb_style_{style}.jpg"
        out_img.save(p, "JPEG", quality=95)
        assert p.stat().st_size > 10000


def test_parametric_channel_palette_resolution():
    from src.media.thumbnails.layouts.cinematic import GeneralCinematicLayout

    # 1. Existing channels
    pal_moku = GeneralCinematicLayout.resolve_channel_palette("moku")
    assert pal_moku["accent"] == "#00FF66"

    pal_aelithia = GeneralCinematicLayout.resolve_channel_palette("aelithia")
    assert pal_aelithia["accent"] == "#FF4081"

    pal_scifi = GeneralCinematicLayout.resolve_channel_palette("scifi")
    assert pal_scifi["accent"] == "#00F0FF"

    # 2. Metadata overrides
    pal_override = GeneralCinematicLayout.resolve_channel_palette(
        "moku", metadata={"accent_color": "#FFCC00", "primary_color": "#FFFFFF"}
    )
    assert pal_override["accent"] == "#FFCC00"
    assert pal_override["primary"] == "#FFFFFF"

    # 3. Non-existent channel -> degrades to neutral high-contrast
    pal_unknown = GeneralCinematicLayout.resolve_channel_palette("unknown_nonexistent_channel")
    assert pal_unknown["accent"] == "#FF003B"
    assert pal_unknown["primary"] == "#FFE600"

    # 4. Invalid hex in metadata -> degrades to channel or neutral
    pal_invalid = GeneralCinematicLayout.resolve_channel_palette(
        "moku", metadata={"accent_color": "not-a-color-123"}
    )
    assert pal_invalid["accent"] == "#00FF66"


def test_parametric_subject_contrast():
    from src.media.thumbnails.layouts.cinematic import GeneralCinematicLayout
    layout = GeneralCinematicLayout()
    safe_zone = AspectLayoutManager.get_safe_zone(1280, 720)
    canvas = Image.new("RGB", (1280, 720), (50, 60, 70))

    img_low = layout.apply_layout(
        canvas=canvas,
        title="CONTRAST TEST",
        channel_id="moku",
        safe_zone=safe_zone,
        metadata={"subject_contrast": 0.5},
    )

    img_high = layout.apply_layout(
        canvas=canvas,
        title="CONTRAST TEST",
        channel_id="moku",
        safe_zone=safe_zone,
        metadata={"subject_contrast": 2.0},
    )

    # Pixel distributions must differ due to contrast alteration
    assert img_low.tobytes() != img_high.tobytes()


def test_safe_zone_1280x720_and_1080x1920_qa_auditor_compliance(tmp_path: Path):
    from src.agents.qa_auditor import VisualAudioQAAuditorAgent
    auditor = VisualAudioQAAuditorAgent()
    engine = ThumbnailEngine()

    # 1. 1280x720 Longform
    p_720 = tmp_path / "thumb_1280x720.jpg"
    engine.generate(ThumbnailConfig(
        title="EXPEDICIÓN AL NÚCLEO SUBTERRÁNEO",
        channel_id="scifi",
        output_path=p_720,
        width=1280,
        height=720,
        text_box_style="boxed",
    ))
    passed_720, errs_720 = auditor.audit_thumbnail(p_720)
    assert passed_720 is True, f"1280x720 QA audit failed: {errs_720}"

    # 2. 1080x1920 Shorts
    p_1080_1920 = tmp_path / "thumb_1080x1920.jpg"
    engine.generate(ThumbnailConfig(
        title="EL SECRETO QUE OCULTABAN BAJO EL HIELO",
        channel_id="aelithia",
        output_path=p_1080_1920,
        width=1080,
        height=1920,
        text_box_style="banner",
    ))
    passed_shorts, errs_shorts = auditor.audit_thumbnail(p_1080_1920)
    assert passed_shorts is True, f"1080x1920 Shorts QA audit failed: {errs_shorts}"


def test_resilient_safeguard_on_missing_or_corrupt_asset(tmp_path: Path):
    from src.agents.qa_auditor import VisualAudioQAAuditorAgent
    auditor = VisualAudioQAAuditorAgent()
    engine = ThumbnailEngine()

    # 1. Corrupt asset file (random junk bytes, not an image)
    corrupt_file = tmp_path / "corrupt_bg.jpg"
    corrupt_file.write_bytes(b"\x00\xFF\xAA\x55GARBAGE_NOT_A_JPEG" * 50)

    thumb_corrupt = tmp_path / "thumb_from_corrupt.jpg"
    cfg_corrupt = ThumbnailConfig(
        title="SEÑAL DESCONOCIDA EN EL ESPACIO",
        channel_id="scifi",
        output_path=thumb_corrupt,
        width=1280,
        height=720,
    )
    # Must NOT crash, falls back to controlled noise atmospheric gradient
    res_corrupt = engine.generate(config=cfg_corrupt, base_image_path=corrupt_file)
    assert Path(res_corrupt).is_file()
    passed_c, errs_c = auditor.audit_thumbnail(thumb_corrupt)
    assert passed_c is True, f"Audit failed on corrupt asset fallback: {errs_c}"

    # 2. Missing asset file path
    non_existent = tmp_path / "does_not_exist_image.jpg"
    thumb_missing = tmp_path / "thumb_from_missing.jpg"
    cfg_missing = ThumbnailConfig(
        title="CRÓNICAS DE LA CIUDAD PERDIDA",
        channel_id="unknown_channel",
        output_path=thumb_missing,
        width=1280,
        height=720,
    )
    res_missing = engine.generate(config=cfg_missing, base_image_path=non_existent)
    assert Path(res_missing).is_file()
    passed_m, errs_m = auditor.audit_thumbnail(thumb_missing)
    assert passed_m is True, f"Audit failed on missing asset fallback: {errs_m}"


def test_atypical_text_strings_graceful_degradation(tmp_path: Path):
    engine = ThumbnailEngine()

    test_titles = [
        "",  # Empty string
        "    ",  # Whitespace only
        "A" * 250,  # Extreme length string
        "🚨🔥 ¡¿VERDAD O MENTIRA?! 😱 [CLASIFICADO] #1 // @TEST",  # Emojis & special symbols
        "Línea uno\n\n\nLínea dos\nLínea tres con tildes áéíóú y diéresis ü",  # Multiline + accents
    ]

    for idx, title in enumerate(test_titles):
        out_p = tmp_path / f"atypical_{idx}.jpg"
        cfg = ThumbnailConfig(
            title=title,
            channel_id="moku",
            output_path=out_p,
            width=1280,
            height=720,
        )
        res = engine.generate(config=cfg)
        assert Path(res).is_file()
        assert Path(res).stat().st_size > 10000


def test_thumbnail_engine_lane_id_and_asset_path_dispatch(tmp_path: Path):
    engine = ThumbnailEngine()

    dummy_asset = tmp_path / "valid_explicit_bg.png"
    Image.new("RGB", (1280, 720), (40, 50, 60)).save(dummy_asset)

    out_p = tmp_path / "lane_dispatch.jpg"
    cfg = ThumbnailConfig(
        title="INVESTIGACIÓN DE CAMPO",
        channel_id="moku",
        lane_id="moku-scp-shorts",
        output_path=out_p,
        width=1080,
        height=1920,
        text_box_style="boxed",
    )

    res = engine.generate(config=cfg, base_image_path=dummy_asset)
    assert Path(res).is_file()

    img = Image.open(res)
    assert img.size == (1080, 1920)





