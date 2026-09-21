"""Unit tests for DIRECTOR_SINGLE_PASS."""
from unittest.mock import MagicMock
from pathlib import Path
import pytest
from src.media.director_single_pass import (
    build_scale_concat_video_filters, build_xfade_video_filters,
    count_director_video_encodes, director_single_pass_enabled, director_xfade_enabled,
    is_procedural_engine_type, manifest_eligible_for_loop_single_pass,
)
from src.media.multi_act_renderer import (
    MultiActVideoRenderer,
    NarrativeSceneAct,
    calculate_xfade_duration,
    clamp_transition_duration,
    multiact_xfade_enabled,
)

def test_single_pass_defaults_on(monkeypatch):
    monkeypatch.delenv("DIRECTOR_SINGLE_PASS", raising=False)
    assert director_single_pass_enabled() is True
    monkeypatch.setenv("DIRECTOR_SINGLE_PASS", "0")
    assert director_single_pass_enabled() is False

def test_xfade_defaults_off(monkeypatch):
    monkeypatch.delenv("DIRECTOR_XFADE", raising=False)
    assert director_xfade_enabled() is False

def test_eligibility():
    assert manifest_eligible_for_loop_single_pass([MagicMock(engine_type="pure_procedural_webgl")])
    assert not manifest_eligible_for_loop_single_pass([MagicMock(engine_type="hybrid_cinematic_ai")])
    assert not is_procedural_engine_type("hybrid_cinematic_ai")

def test_encode_counts():
    legacy = count_director_video_encodes(n_scenes=5, single_pass=False, use_xfade=False, needs_scale=False)
    assert legacy.total_video_encodes(has_ass_burn=False) == 5
    sp = count_director_video_encodes(n_scenes=5, single_pass=True, use_xfade=False, needs_scale=False)
    assert sp.mode == "loop_stream_copy" and sp.total_video_encodes(has_ass_burn=False) == 0

def test_filters():
    parts, out = build_scale_concat_video_filters(3, 1920, 1080, 30)
    assert "concat=n=3" in ";".join(parts) and out == "[vout]"
    parts, out, dur = build_xfade_video_filters([10,10,10], 1280, 720, 30, 0.75)
    assert "xfade=transition=fade" in ";".join(parts) and dur == pytest.approx(28.5)

def test_multiact_xfade(tmp_path, monkeypatch):
    loop = tmp_path / "loop.mp4"; loop.write_bytes(b"\0"*32)
    audio = tmp_path / "a.wav"; audio.write_bytes(b"RIFF"+b"\0"*40)
    out = tmp_path / "out.mp4"; captured = {}
    def fake_run(cmd, check=True, **kw):
        captured["cmd"] = list(cmd); out.write_bytes(b"mp4"); return MagicMock(returncode=0)
    r = MultiActVideoRenderer(loops_dir=tmp_path)
    monkeypatch.setattr(r, "resolve_loop_for_theme", lambda *a, **k: loop)
    monkeypatch.setattr("src.media.multi_act_renderer.run_ffmpeg", fake_run)
    monkeypatch.setenv("MULTIACT_XFADE", "1")
    acts = [NarrativeSceneAct(0,0.0,2.0,"A","scp"), NarrativeSceneAct(1,2.0,2.0,"B","scp")]
    expected = calculate_xfade_duration([2.0, 2.0], 0.75)
    r.composite_multi_act_video(acts, audio, out, expected)
    fc = captured["cmd"][captured["cmd"].index("-filter_complex")+1]
    assert "xfade=transition=fade" in fc and "concat=n=" not in fc

def test_multiact_av_t_align_contract(tmp_path, monkeypatch):
    """A/V share one -t equal to calculate_xfade_duration (no silent mismatch)."""
    loop = tmp_path / "loop.mp4"; loop.write_bytes(b"\0"*32)
    audio = tmp_path / "a.wav"; audio.write_bytes(b"RIFF"+b"\0"*40)
    out = tmp_path / "out.mp4"; captured = {}
    def fake_run(cmd, check=True, **kw):
        captured["cmd"] = list(cmd); out.write_bytes(b"mp4"); return MagicMock(returncode=0)
    r = MultiActVideoRenderer(loops_dir=tmp_path)
    monkeypatch.setattr(r, "resolve_loop_for_theme", lambda *a, **k: loop)
    monkeypatch.setattr("src.media.multi_act_renderer.run_ffmpeg", fake_run)
    monkeypatch.setenv("MULTIACT_XFADE", "1")
    acts = [
        NarrativeSceneAct(0, 0.0, 2.0, "A", "scp"),
        NarrativeSceneAct(1, 2.0, 2.0, "B", "scp"),
        NarrativeSceneAct(2, 4.0, 3.0, "C", "scp"),
    ]
    durs = [a.duration_sec for a in acts]
    contract = calculate_xfade_duration(durs, 0.75)
    # Intentionally pass a wrong total to ensure renderer prefers contract duration.
    r.composite_multi_act_video(acts, audio, out, total_duration=sum(durs))
    cmd = captured["cmd"]
    # Output -t is the last -t (inputs also pass -t for loop length).
    out_t = float([cmd[i + 1] for i, x in enumerate(cmd) if x == "-t"][-1])
    assert out_t == pytest.approx(contract)
    # One output -t after both -map v and -map a → A/V share the same trim.
    map_idxs = [i for i, x in enumerate(cmd) if x == "-map"]
    t_idxs = [i for i, x in enumerate(cmd) if x == "-t"]
    assert len(map_idxs) >= 2
    assert t_idxs[-1] > map_idxs[0] and t_idxs[-1] > map_idxs[1]

def test_multiact_xfade_opt_out_uses_concat(tmp_path, monkeypatch):
    loop = tmp_path / "loop.mp4"; loop.write_bytes(b"\0"*32)
    audio = tmp_path / "a.wav"; audio.write_bytes(b"RIFF"+b"\0"*40)
    out = tmp_path / "out.mp4"; captured = {}
    def fake_run(cmd, check=True, **kw):
        captured["cmd"] = list(cmd); out.write_bytes(b"mp4"); return MagicMock(returncode=0)
    r = MultiActVideoRenderer(loops_dir=tmp_path)
    monkeypatch.setattr(r, "resolve_loop_for_theme", lambda *a, **k: loop)
    monkeypatch.setattr("src.media.multi_act_renderer.run_ffmpeg", fake_run)
    monkeypatch.setenv("MULTIACT_XFADE", "0")
    assert multiact_xfade_enabled() is False
    acts = [NarrativeSceneAct(0,0.0,2.0,"A","scp"), NarrativeSceneAct(1,2.0,2.0,"B","scp")]
    r.composite_multi_act_video(acts, audio, out, total_duration=4.0)
    cmd = captured["cmd"]
    fc = cmd[cmd.index("-filter_complex")+1]
    assert "concat=n=2" in fc and "xfade=" not in fc
    # Last -t is the output duration (inputs also use -t).
    out_t = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-t"][-1]
    assert float(out_t) == pytest.approx(4.0)

def test_compositor_stream_copy(tmp_path, monkeypatch):
    from src.media.compositor import MultiSceneCompositor
    from src.scene_manifest import SceneConfig, SceneManifestV2, AudioTracks, SafeArea
    loop = tmp_path / "cat.mp4"; loop.write_bytes(b"\0"*64)
    vs = MagicMock(width=1280, height=720, codec_name="h264", pix_fmt="yuv420p")
    probe = MagicMock(
        video_streams=[vs],
        primary_video=vs,
        raw_payload={"streams": [{"codec_type": "video", "time_base": "1/90000"}]},
    )
    cmds = []
    def fake_run(cmd, **kw):
        cmds.append(list(cmd)); Path(cmd[-1]).write_bytes(b"mp4"); return MagicMock(returncode=0)
    monkeypatch.setattr("src.media.compositor.probe_media", lambda *a, **k: probe)
    monkeypatch.setattr("src.media.compositor.run_ffmpeg", fake_run)
    monkeypatch.setenv("DIRECTOR_SINGLE_PASS","1"); monkeypatch.setenv("DIRECTOR_XFADE","0")
    comp = MultiSceneCompositor()
    scene = SceneConfig(scene_index=1, scene_id="s1", start_sec=0.0, duration_sec=1.0, tension_level=2, engine_type="catalog_loop")
    scene2 = scene.model_copy(update={"scene_index":2,"scene_id":"s2","start_sec":1.0})
    manifest = SceneManifestV2(story_id="t", lane_id="lane", channel_name="moku", resolution=[1280,720], fps=30, total_duration_sec=2.0, scenes=[scene,scene2], audio_tracks=AudioTracks(narration_path=str(tmp_path/"n.wav")), safe_area=SafeArea())
    (tmp_path/"n.wav").write_bytes(b"RIFF"+b"\0"*40)
    monkeypatch.setattr(comp, "_resolve_procedural_loop_path", lambda *a, **k: loop)
    ok = comp._assemble_procedural_loops_single_pass(manifest=manifest, output_mp4=tmp_path/"a.mp4", width=1280, height=720, fps=30, crf=26, preset="ultrafast", tmp_dir=tmp_path)
    assert ok and comp._last_assembly_plan.mode == "loop_stream_copy"
    assert sum(1 for c in cmds if "-stream_loop" in c and "-c:v" in c and c[c.index("-c:v")+1]=="copy") == 2

def test_compositor_inhomogeneous_falls_back_to_scale_concat(tmp_path, monkeypatch):
    """Mismatched codec/pix_fmt/time_base must NOT stream-copy; use scale+concat encode."""
    from src.media.compositor import MultiSceneCompositor
    from src.scene_manifest import SceneConfig, SceneManifestV2, AudioTracks, SafeArea
    loop_a = tmp_path / "a.mp4"; loop_a.write_bytes(b"\0"*64)
    loop_b = tmp_path / "b.mp4"; loop_b.write_bytes(b"\0"*64)
    vs_a = MagicMock(width=1280, height=720, codec_name="h264", pix_fmt="yuv420p")
    vs_b = MagicMock(width=1280, height=720, codec_name="h264", pix_fmt="yuv422p")
    probes = {
        str(loop_a.resolve()): MagicMock(
            video_streams=[vs_a], primary_video=vs_a,
            raw_payload={"streams": [{"codec_type": "video", "time_base": "1/90000"}]},
        ),
        str(loop_b.resolve()): MagicMock(
            video_streams=[vs_b], primary_video=vs_b,
            raw_payload={"streams": [{"codec_type": "video", "time_base": "1/90000"}]},
        ),
    }
    cmds = []
    def fake_probe(p, **kw):
        return probes[str(Path(p).resolve())]
    def fake_run(cmd, **kw):
        cmds.append(list(cmd)); Path(cmd[-1]).write_bytes(b"mp4"); return MagicMock(returncode=0)
    monkeypatch.setattr("src.media.compositor.probe_media", fake_probe)
    monkeypatch.setattr("src.media.compositor.run_ffmpeg", fake_run)
    monkeypatch.setenv("DIRECTOR_SINGLE_PASS","1"); monkeypatch.setenv("DIRECTOR_XFADE","0")
    comp = MultiSceneCompositor()
    scene = SceneConfig(scene_index=1, scene_id="s1", start_sec=0.0, duration_sec=1.0, tension_level=2, engine_type="catalog_loop")
    scene2 = scene.model_copy(update={"scene_index":2,"scene_id":"s2","start_sec":1.0})
    manifest = SceneManifestV2(story_id="t", lane_id="lane", channel_name="moku", resolution=[1280,720], fps=30, total_duration_sec=2.0, scenes=[scene,scene2], audio_tracks=AudioTracks(narration_path=str(tmp_path/"n.wav")), safe_area=SafeArea())
    (tmp_path/"n.wav").write_bytes(b"RIFF"+b"\0"*40)
    paths = [loop_a, loop_b]
    monkeypatch.setattr(comp, "_resolve_procedural_loop_path", lambda *a, **k: paths.pop(0))
    ok = comp._assemble_procedural_loops_single_pass(manifest=manifest, output_mp4=tmp_path/"a.mp4", width=1280, height=720, fps=30, crf=26, preset="ultrafast", tmp_dir=tmp_path)
    assert ok and comp._last_assembly_plan.mode == "loop_filter_concat"
    assert any("-filter_complex" in c for c in cmds)
    assert not any("-c:v" in c and c[c.index("-c:v")+1]=="copy" and "-stream_loop" in c for c in cmds)

def test_resolve_loop_no_glob_fallback(tmp_path, monkeypatch):
    """Arbitrary sorted(glob('*.mp4'))[0] must not be used; return None → multi-pass."""
    from src.media.compositor import MultiSceneCompositor
    from src.scene_manifest import SceneConfig
    cat = tmp_path / "assets" / "loops" / "web_procedural" / "dark_forest"
    cat.mkdir(parents=True)
    (cat / "wrong_loop.mp4").write_bytes(b"\0"*32)
    monkeypatch.chdir(tmp_path)
    comp = MultiSceneCompositor()
    eng = MagicMock()
    eng.catalog.get_best_loop.return_value = None
    eng.resolve_loop_video.return_value = None
    eng._resolve_category.return_value = "dark_forest"
    comp.loop_engine = eng
    scene = SceneConfig(
        scene_index=1, scene_id="s1", start_sec=0.0, duration_sec=1.0, tension_level=2,
        engine_type="catalog_loop",
        environment_name="dark_forest",
    )
    assert comp._resolve_procedural_loop_path(scene, width=1280, height=720, lane_id="lane") is None

def test_encode_counts_hud_forces_one_assembly_encode():
    no_hud = count_director_video_encodes(
        n_scenes=5, single_pass=True, use_xfade=False, needs_scale=False, has_hud=False
    )
    assert no_hud.mode == "loop_stream_copy"
    assert no_hud.total_video_encodes(has_ass_burn=False) == 0
    hud = count_director_video_encodes(
        n_scenes=5, single_pass=True, use_xfade=False, needs_scale=False, has_hud=True
    )
    assert hud.mode == "loop_filter_hud"
    assert hud.assembly_video_encodes == 1
    assert hud.scene_video_encodes == 0
    assert hud.total_video_encodes(has_ass_burn=False) == 1


def test_hud_concat_graph_is_one_filter_not_n_encodes():
    from src.media.director_single_pass import build_hud_concat_video_filters
    snippets = ["drawbox=x=0:y=0:w=10:h=10:color=red:t=fill,drawtext=text='SITIO'", None]
    parts, out = build_hud_concat_video_filters(2, snippets)
    joined = ";".join(parts)
    assert "concat=n=2" in joined and out == "[vout]"
    assert "drawtext=" in joined and "drawbox=" in joined
    assert joined.count("drawtext=") == 1  # HUD on the scene that provided it, still one graph


def _homogeneous_probe(width=1280, height=720):
    vs = MagicMock(width=width, height=height, codec_name="h264", pix_fmt="yuv420p")
    return MagicMock(
        video_streams=[vs],
        primary_video=vs,
        raw_payload={"streams": [{"codec_type": "video", "time_base": "1/90000"}]},
    )


def test_compositor_single_pass_burns_niche_hud(tmp_path, monkeypatch):
    """Planner niche_hud is burned on DIRECTOR_SINGLE_PASS via one FFmpeg HUD filter."""
    from src.media.compositor import MultiSceneCompositor
    from src.media.encode_defaults import default_render_crf, default_render_preset
    from src.scene_manifest import SceneConfig, SceneManifestV2, AudioTracks, SafeArea

    monkeypatch.delenv("RENDER_PRESET", raising=False)
    monkeypatch.delenv("RENDER_CRF", raising=False)
    loop = tmp_path / "cat.mp4"; loop.write_bytes(b"\0"*64)
    cmds = []
    def fake_run(cmd, **kw):
        cmds.append(list(cmd)); Path(cmd[-1]).write_bytes(b"mp4"); return MagicMock(returncode=0)
    monkeypatch.setattr("src.media.compositor.probe_media", lambda *a, **k: _homogeneous_probe())
    monkeypatch.setattr("src.media.compositor.run_ffmpeg", fake_run)
    monkeypatch.setenv("DIRECTOR_SINGLE_PASS", "1")
    monkeypatch.setenv("DIRECTOR_XFADE", "0")
    hud = {
        "lane_id": "moku-scp-shorts",
        "story_type": "scp",
        "hud_badge": "NIVEL 5 // KETER",
        "hud_site": "SITIO-19",
        "telemetry_label": "CAM-01",
        "accent_color_hex": "#00FF66",
        "tension_level": 5,
    }
    scene = SceneConfig(
        scene_index=1, scene_id="s1", start_sec=0.0, duration_sec=1.0, tension_level=5,
        engine_type="catalog_loop", niche_hud=hud,
    )
    scene2 = scene.model_copy(update={"scene_index": 2, "scene_id": "s2", "start_sec": 1.0})
    manifest = SceneManifestV2(
        story_id="t", lane_id="moku-scp-shorts", channel_name="moku",
        resolution=[1280, 720], fps=30, total_duration_sec=2.0, scenes=[scene, scene2],
        audio_tracks=AudioTracks(narration_path=str(tmp_path / "n.wav")), safe_area=SafeArea(),
    )
    (tmp_path / "n.wav").write_bytes(b"RIFF" + b"\0" * 40)
    comp = MultiSceneCompositor()
    monkeypatch.setattr(comp, "_resolve_procedural_loop_path", lambda *a, **k: loop)
    ok = comp._assemble_procedural_loops_single_pass(
        manifest=manifest, output_mp4=tmp_path / "a.mp4", width=1280, height=720, fps=30,
        crf=26, preset="ultrafast", tmp_dir=tmp_path,
    )
    assert ok and comp._last_assembly_plan.mode == "loop_filter_hud"
    fc_cmds = [c for c in cmds if "-filter_complex" in c]
    assert len(fc_cmds) == 1
    fc = fc_cmds[0][fc_cmds[0].index("-filter_complex") + 1]
    assert "drawtext=" in fc and "drawbox=" in fc
    assert "SITIO-19" in fc
    assert "concat=n=2" in fc
    assert fc_cmds[0][fc_cmds[0].index("-c:v") + 1] == "libx264"
    assert fc_cmds[0][fc_cmds[0].index("-preset") + 1] == default_render_preset() == "veryfast"
    assert fc_cmds[0][fc_cmds[0].index("-crf") + 1] == str(default_render_crf()) == "19"
    # Not N per-scene copy trims / not N encodes
    assert not any("-c:v" in c and c[c.index("-c:v") + 1] == "copy" and "-stream_loop" in c for c in cmds)


def test_compositor_no_hud_still_stream_copy_when_geometry_matches(tmp_path, monkeypatch):
    """No niche_hud → homogeneous loops still use -c:v copy (existing single-pass contract)."""
    from src.media.compositor import MultiSceneCompositor
    from src.scene_manifest import SceneConfig, SceneManifestV2, AudioTracks, SafeArea
    loop = tmp_path / "cat.mp4"; loop.write_bytes(b"\0"*64)
    cmds = []
    def fake_run(cmd, **kw):
        cmds.append(list(cmd)); Path(cmd[-1]).write_bytes(b"mp4"); return MagicMock(returncode=0)
    monkeypatch.setattr("src.media.compositor.probe_media", lambda *a, **k: _homogeneous_probe())
    monkeypatch.setattr("src.media.compositor.run_ffmpeg", fake_run)
    monkeypatch.setenv("DIRECTOR_SINGLE_PASS", "1")
    monkeypatch.setenv("DIRECTOR_XFADE", "0")
    scene = SceneConfig(
        scene_index=1, scene_id="s1", start_sec=0.0, duration_sec=1.0, tension_level=2,
        engine_type="catalog_loop",
    )
    assert scene.niche_hud is None
    scene2 = scene.model_copy(update={"scene_index": 2, "scene_id": "s2", "start_sec": 1.0})
    manifest = SceneManifestV2(
        story_id="t", lane_id="lane", channel_name="moku", resolution=[1280, 720], fps=30,
        total_duration_sec=2.0, scenes=[scene, scene2],
        audio_tracks=AudioTracks(narration_path=str(tmp_path / "n.wav")), safe_area=SafeArea(),
    )
    (tmp_path / "n.wav").write_bytes(b"RIFF" + b"\0" * 40)
    comp = MultiSceneCompositor()
    monkeypatch.setattr(comp, "_resolve_procedural_loop_path", lambda *a, **k: loop)
    ok = comp._assemble_procedural_loops_single_pass(
        manifest=manifest, output_mp4=tmp_path / "a.mp4", width=1280, height=720, fps=30,
        crf=26, preset="ultrafast", tmp_dir=tmp_path,
    )
    assert ok and comp._last_assembly_plan.mode == "loop_stream_copy"
    assert not any("-filter_complex" in c for c in cmds)
    assert sum(1 for c in cmds if "-stream_loop" in c and "-c:v" in c and c[c.index("-c:v")+1]=="copy") == 2


def test_single_pass_hud_has_no_browser_or_wgpu_imports():
    """HUD burn must stay FFmpeg-only (no Playwright, wgpu, per-frame Pillow)."""
    import ast
    files = [
        Path("src/media/compositor.py"),
        Path("src/media/director_single_pass.py"),
        Path("src/media/multi_act_renderer.py"),
    ]
    banned_mods = {"playwright", "chromium", "wgpu", "PIL", "PIL.Image", "PIL.ImageDraw"}
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
                    imported.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
                imported.add(node.module)
        hits = imported & banned_mods
        assert not hits, f"{f} imports {hits}"


def test_multiact_stream_copy_when_homogeneous_no_hud(tmp_path, monkeypatch):
    """MultiActVideoRenderer executes stream-copy when DIRECTOR_SINGLE_PASS=1, MULTIACT_XFADE=0, and no HUD."""
    loop = tmp_path / "loop.mp4"
    loop.write_bytes(b"\0" * 64)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF" + b"\0" * 40)
    out = tmp_path / "out.mp4"
    cmds = []

    def fake_run(cmd, check=True, **kw):
        cmds.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"mp4")
        return MagicMock(returncode=0)

    monkeypatch.setattr("src.media.multi_act_renderer.probe_media", lambda *a, **k: _homogeneous_probe(1920, 1080))
    monkeypatch.setattr("src.media.multi_act_renderer.run_ffmpeg", fake_run)
    monkeypatch.setenv("DIRECTOR_SINGLE_PASS", "1")
    monkeypatch.setenv("MULTIACT_XFADE", "0")

    r = MultiActVideoRenderer(loops_dir=tmp_path)
    monkeypatch.setattr(r, "resolve_loop_for_theme", lambda *a, **k: loop)

    acts = [
        NarrativeSceneAct(0, 0.0, 2.0, "A", "scp", hud_badge="", hud_site="", hud_telemetry="", niche_hud={"hud_enabled": False}),
        NarrativeSceneAct(1, 2.0, 3.0, "B", "scp", hud_badge="", hud_site="", hud_telemetry="", niche_hud={"hud_layout": "none"}),
    ]
    r.composite_multi_act_video(acts, audio, out, total_duration=5.0, is_vertical=False)

    # Must NOT have run any -filter_complex re-encode command
    assert not any("-filter_complex" in c for c in cmds)
    # Must have run 2 trim commands with -c:v copy
    copy_trim_cmds = [c for c in cmds if "-stream_loop" in c and "-c:v" in c and c[c.index("-c:v") + 1] == "copy"]
    assert len(copy_trim_cmds) == 2
    # Must have run 1 mux concat command with -c:v copy
    concat_cmds = [c for c in cmds if "-f" in c and "concat" in c and "-c:v" in c and c[c.index("-c:v") + 1] == "copy"]
    assert len(concat_cmds) == 1
    mux_cmd = concat_cmds[0]
    assert mux_cmd[mux_cmd.index("-c:a") + 1] == "aac"
    assert mux_cmd[mux_cmd.index("-t") + 1] == "5.000"


def test_multiact_filter_complex_has_setsar1_and_no_trailing_comma(tmp_path, monkeypatch):
    """MultiActVideoRenderer includes setsar=1 and avoids trailing commas when mixing acts with/without HUD."""
    from src.media.encode_defaults import default_render_crf, default_render_preset

    loop = tmp_path / "loop.mp4"
    loop.write_bytes(b"\0" * 64)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF" + b"\0" * 40)
    out = tmp_path / "out.mp4"
    captured = {}

    def fake_run(cmd, check=True, **kw):
        captured["cmd"] = list(cmd)
        out.write_bytes(b"mp4")
        return MagicMock(returncode=0)

    monkeypatch.setattr("src.media.multi_act_renderer.run_ffmpeg", fake_run)
    monkeypatch.setenv("MULTIACT_XFADE", "0")
    monkeypatch.delenv("RENDER_PRESET", raising=False)
    monkeypatch.delenv("RENDER_CRF", raising=False)

    r = MultiActVideoRenderer(loops_dir=tmp_path)
    monkeypatch.setattr(r, "resolve_loop_for_theme", lambda *a, **k: loop)

    # Act 0 has HUD, Act 1 has disabled HUD
    acts = [
        NarrativeSceneAct(0, 0.0, 2.0, "A", "scp", hud_badge="BADGE", hud_site="SITE", hud_telemetry="TEL"),
        NarrativeSceneAct(1, 2.0, 2.0, "B", "scp", hud_badge="", hud_site="", hud_telemetry="", niche_hud={"hud_enabled": False}),
    ]
    r.composite_multi_act_video(acts, audio, out, total_duration=4.0, is_vertical=True)

    cmd = captured["cmd"]
    assert "-filter_complex" in cmd
    fc = cmd[cmd.index("-filter_complex") + 1]

    # setsar=1 is present on inputs before drawbox/drawtext
    assert "setsar=1" in fc
    # Act 0 has drawtext
    assert "BADGE" in fc
    # Act 1 has no trailing comma before the output tag
    assert "format=yuv420p[v_act1]" in fc
    assert ",[v_act1]" not in fc

    # Policy checks: FFmpeg-first defaults veryfast and CRF 19
    assert cmd[cmd.index("-preset") + 1] == default_render_preset() == "veryfast"
    assert cmd[cmd.index("-crf") + 1] == str(default_render_crf()) == "19"


def test_scene_planner_hud_disabled_preserves_stream_copy(tmp_path):
    """Scene planner respects hud_enabled: False and hud_layout: 'none' by producing niche_hud=None."""
    from src.media.manifest_compiler import ScenePlannerCompositorAgent
    from src.media.director_single_pass import scenes_have_niche_hud

    agent = ScenePlannerCompositorAgent()

    # 1. Direct palette extraction
    layout, _, _ = agent._extract_channel_palette_and_hud(
        channel_name="moku",
        lane_id="moku-scp-shorts",
        meta={"hud_enabled": False},
        visual_plan={},
    )
    assert layout == "none"

    layout_none, _, _ = agent._extract_channel_palette_and_hud(
        channel_name="moku",
        lane_id="moku-scp-shorts",
        meta={},
        visual_plan={},
        explicit_hud_layout="none",
    )
    assert layout_none == "none"

    # 2. plan_manifest with hud_enabled: False
    dummy_audio = tmp_path / "dummy_narr.wav"
    dummy_audio.write_bytes(b"RIFF" + b"\0" * 40)
    script = {
        "metadata": {
            "channel_lane": "moku-scp-shorts",
            "hud_enabled": False,
            "target_format": "short",
        },
        "acts": [
            {
                "dramatic_role": "intro",
                "scenes": [
                    {"scene_id": "sc_01", "estimated_duration_sec": 3.0, "tension_level": 3},
                ],
            }
        ],
    }
    manifest_dict = agent.plan_manifest(
        script=script,
        visual_plan={},
        story_id="test_story",
        narration_path=str(dummy_audio),
    )
    scenes = manifest_dict["scenes"]
    assert len(scenes) == 1
    assert scenes[0]["niche_hud"] is None

    # scenes_have_niche_hud must be False, preserving loop_stream_copy eligibility
    class MockScene:
        def __init__(self, niche_hud):
            self.niche_hud = niche_hud
    assert not scenes_have_niche_hud([MockScene(None)])


def test_build_hud_concat_video_filters_setsar():
    """build_hud_concat_video_filters ensures setsar=1 is in each input branch."""
    from src.media.director_single_pass import build_hud_concat_video_filters

    parts, out = build_hud_concat_video_filters(2, ["drawtext=text=TEST", None])
    joined = ";".join(parts)
    assert "[0:v]setsar=1,drawtext=text=TEST,format=yuv420p[v0]" in joined
    assert "[1:v]setsar=1,format=yuv420p[v1]" in joined


def _probe(width, height, codec="h264", pix_fmt="yuv420p", time_base="1/90000"):
    vs = MagicMock(width=width, height=height, codec_name=codec, pix_fmt=pix_fmt)
    return MagicMock(
        video_streams=[vs],
        primary_video=vs,
        raw_payload={"streams": [{"codec_type": "video", "time_base": time_base}]},
    )


def test_loops_homogeneous_for_stream_copy_requires_wxh_codec_pixfmt_timebase(tmp_path, monkeypatch):
    """Strict concat-copy gate: any WxH/codec/pix_fmt/time_base mismatch is ineligible."""
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a.write_bytes(b"\0" * 32)
    b.write_bytes(b"\0" * 32)
    r = MultiActVideoRenderer(loops_dir=tmp_path)

    probes = {str(a.resolve()): _probe(1920, 1080), str(b.resolve()): _probe(1920, 1080)}
    monkeypatch.setattr(
        "src.media.multi_act_renderer.probe_media",
        lambda p, **k: probes[str(Path(p).resolve())],
    )
    assert r._loops_homogeneous_for_stream_copy([a, b], 1920, 1080) is True
    assert r._loops_homogeneous_for_stream_copy([a, b], 1080, 1920) is False

    probes[str(b.resolve())] = _probe(1920, 1080, codec="hevc")
    assert r._loops_homogeneous_for_stream_copy([a, b], 1920, 1080) is False
    probes[str(b.resolve())] = _probe(1920, 1080, pix_fmt="yuv422p")
    assert r._loops_homogeneous_for_stream_copy([a, b], 1920, 1080) is False
    probes[str(b.resolve())] = _probe(1920, 1080, time_base="1/30000")
    assert r._loops_homogeneous_for_stream_copy([a, b], 1920, 1080) is False
    probes[str(b.resolve())] = _probe(1280, 720)
    assert r._loops_homogeneous_for_stream_copy([a, b], 1920, 1080) is False


def test_multiact_stream_copy_vertical_when_homogeneous_no_hud(tmp_path, monkeypatch):
    """Vertical 1080x1920 homogeneous loops stream-copy the same as horizontal."""
    loop = tmp_path / "loop.mp4"
    loop.write_bytes(b"\0" * 64)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF" + b"\0" * 40)
    out = tmp_path / "out.mp4"
    cmds = []

    def fake_run(cmd, check=True, **kw):
        cmds.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"mp4")
        return MagicMock(returncode=0)

    monkeypatch.setattr(
        "src.media.multi_act_renderer.probe_media",
        lambda *a, **k: _homogeneous_probe(1080, 1920),
    )
    monkeypatch.setattr("src.media.multi_act_renderer.run_ffmpeg", fake_run)
    monkeypatch.setenv("DIRECTOR_SINGLE_PASS", "1")
    monkeypatch.setenv("MULTIACT_XFADE", "0")

    r = MultiActVideoRenderer(loops_dir=tmp_path)
    monkeypatch.setattr(r, "resolve_loop_for_theme", lambda *a, **k: loop)
    acts = [
        NarrativeSceneAct(0, 0.0, 2.0, "A", "scp", hud_badge="", hud_site="", hud_telemetry="", niche_hud={"hud_enabled": False}),
        NarrativeSceneAct(1, 2.0, 2.0, "B", "scp", hud_badge="", hud_site="", hud_telemetry="", niche_hud={"hud_layout": "none"}),
    ]
    r.composite_multi_act_video(acts, audio, out, total_duration=4.0, is_vertical=True)

    assert not any("-filter_complex" in c for c in cmds)
    assert sum(1 for c in cmds if "-stream_loop" in c and "-c:v" in c and c[c.index("-c:v") + 1] == "copy") == 2
    assert any("-f" in c and "concat" in c and c[c.index("-c:v") + 1] == "copy" for c in cmds)


def test_multiact_inhomogeneous_falls_back_to_veryfast_crf19(tmp_path, monkeypatch):
    """Mismatched pix_fmt must not stream-copy; one veryfast/CRF19 encode with setsar=1."""
    from src.media.encode_defaults import default_render_crf, default_render_preset

    loop_a = tmp_path / "a.mp4"
    loop_b = tmp_path / "b.mp4"
    loop_a.write_bytes(b"\0" * 64)
    loop_b.write_bytes(b"\0" * 64)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF" + b"\0" * 40)
    out = tmp_path / "out.mp4"
    cmds = []
    probes = {
        str(loop_a.resolve()): _probe(1920, 1080),
        str(loop_b.resolve()): _probe(1920, 1080, pix_fmt="yuv422p"),
    }

    def fake_run(cmd, check=True, **kw):
        cmds.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"mp4")
        return MagicMock(returncode=0)

    monkeypatch.setattr(
        "src.media.multi_act_renderer.probe_media",
        lambda p, **k: probes[str(Path(p).resolve())],
    )
    monkeypatch.setattr("src.media.multi_act_renderer.run_ffmpeg", fake_run)
    monkeypatch.setenv("DIRECTOR_SINGLE_PASS", "1")
    monkeypatch.setenv("MULTIACT_XFADE", "0")
    monkeypatch.delenv("RENDER_PRESET", raising=False)
    monkeypatch.delenv("RENDER_CRF", raising=False)

    r = MultiActVideoRenderer(loops_dir=tmp_path)
    paths = [loop_a, loop_b]
    monkeypatch.setattr(r, "resolve_loop_for_theme", lambda *a, **k: paths.pop(0))
    acts = [
        NarrativeSceneAct(0, 0.0, 2.0, "A", "scp", hud_badge="", hud_site="", hud_telemetry="", niche_hud={"hud_enabled": False}),
        NarrativeSceneAct(1, 2.0, 2.0, "B", "scp", hud_badge="", hud_site="", hud_telemetry="", niche_hud={"hud_enabled": False}),
    ]
    r.composite_multi_act_video(acts, audio, out, total_duration=4.0, is_vertical=False)

    assert not any("-c:v" in c and c[c.index("-c:v") + 1] == "copy" for c in cmds)
    fc_cmds = [c for c in cmds if "-filter_complex" in c]
    assert len(fc_cmds) == 1
    cmd = fc_cmds[0]
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "setsar=1" in fc
    assert "concat=n=2" in fc
    assert cmd[cmd.index("-preset") + 1] == default_render_preset() == "veryfast"
    assert cmd[cmd.index("-crf") + 1] == str(default_render_crf()) == "19"
    assert cmd[cmd.index("-c:v") + 1] == "libx264"


def test_multiact_xfade_disparate_durations_offsets_and_t_alignment(tmp_path, monkeypatch):
    """Sequences of 3 or more acts with disparate durations verify continuous offsets and contractual -t."""
    loop = tmp_path / "loop.mp4"
    loop.write_bytes(b"\0" * 64)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF" + b"\0" * 40)
    out = tmp_path / "out.mp4"
    captured = {}

    def fake_run(cmd, check=True, **kw):
        captured["cmd"] = list(cmd)
        out.write_bytes(b"mp4")
        return MagicMock(returncode=0)

    r = MultiActVideoRenderer(loops_dir=tmp_path)
    monkeypatch.setattr(r, "resolve_loop_for_theme", lambda *a, **k: loop)
    monkeypatch.setattr("src.media.multi_act_renderer.run_ffmpeg", fake_run)
    monkeypatch.setenv("MULTIACT_XFADE", "1")

    # 3 acts with disparate durations (>= 2.5s, standard 0.75s transition):
    # Act 0: 5.0s, Act 1: 3.0s, Act 2: 4.0s
    acts = [
        NarrativeSceneAct(0, 0.0, 5.0, "Act 1", "scp"),
        NarrativeSceneAct(1, 5.0, 3.0, "Act 2", "scp"),
        NarrativeSceneAct(2, 8.0, 4.0, "Act 3", "scp"),
    ]
    expected_dur = calculate_xfade_duration([5.0, 3.0, 4.0], 0.75, clamp=True)
    # Expected: 5.0 + (3.0 - 0.75) + (4.0 - 0.75) = 10.500
    assert expected_dur == pytest.approx(10.5)

    # Pass mismatched total_duration to verify contract enforcement and warning
    r.composite_multi_act_video(acts, audio, out, total_duration=12.0)

    cmd = captured["cmd"]
    assert "-filter_complex" in cmd
    fc = cmd[cmd.index("-filter_complex") + 1]

    # Exactly 2 xfade filters chained
    xfade_filters = [p for p in fc.split(";") if "xfade=transition=fade" in p]
    assert len(xfade_filters) == 2

    # Transition 1: [v_act0][v_act1]xfade=transition=fade:duration=0.750:offset=4.250[vx1]
    # offset 0 = 5.0 - 0.75 = 4.250
    assert "[v_act0][v_act1]xfade=transition=fade:duration=0.750:offset=4.250[vx1]" in xfade_filters[0]

    # Transition 2: [vx1][v_act2]xfade=transition=fade:duration=0.750:offset=6.500[v_xfaded]
    # cum = 5.0 + 3.0 - 0.75 = 7.250; offset 1 = 7.250 - 0.75 = 6.500
    assert "[vx1][v_act2]xfade=transition=fade:duration=0.750:offset=6.500[v_xfaded]" in xfade_filters[1]

    # Final output -t matches calculate_xfade_duration
    out_t = float([cmd[i + 1] for i, x in enumerate(cmd) if x == "-t"][-1])
    assert out_t == pytest.approx(expected_dur)

    # Both video and audio mapped before -t
    map_indices = [i for i, x in enumerate(cmd) if x == "-map"]
    t_indices = [i for i, x in enumerate(cmd) if x == "-t"]
    assert len(map_indices) >= 2
    assert t_indices[-1] > map_indices[0] and t_indices[-1] > map_indices[1]


def test_multiact_xfade_short_acts_clamped_transition(tmp_path, monkeypatch):
    """Short acts (< 2.5s) apply 30% clamp_transition_duration rule without exception."""
    # Unit checks on clamp_transition_duration boundary values
    assert clamp_transition_duration(1.0, 2.0, 0.75) == pytest.approx(0.30)
    assert clamp_transition_duration(0.1, 0.1, 0.75) == pytest.approx(0.05)  # min floor 0.05
    assert clamp_transition_duration(5.0, 5.0, 0.75) == pytest.approx(0.75)

    loop = tmp_path / "loop.mp4"
    loop.write_bytes(b"\0" * 64)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF" + b"\0" * 40)
    out = tmp_path / "out.mp4"
    captured = {}

    def fake_run(cmd, check=True, **kw):
        captured["cmd"] = list(cmd)
        out.write_bytes(b"mp4")
        return MagicMock(returncode=0)

    r = MultiActVideoRenderer(loops_dir=tmp_path)
    monkeypatch.setattr(r, "resolve_loop_for_theme", lambda *a, **k: loop)
    monkeypatch.setattr("src.media.multi_act_renderer.run_ffmpeg", fake_run)
    monkeypatch.setenv("MULTIACT_XFADE", "1")

    # Short acts: 2.0s, 1.0s, 2.0s (< 2.5s)
    # Transition 0: min(2.0, 1.0) * 0.30 = 0.300s (< 0.75s)
    # Offset 0: 2.0 - 0.30 = 1.700s, cum after = 2.700s
    # Transition 1: min(1.0, 2.0) * 0.30 = 0.300s
    # Offset 1: 2.700 - 0.30 = 2.400s, cum after = 4.400s
    acts = [
        NarrativeSceneAct(0, 0.0, 2.0, "Short 1", "scp"),
        NarrativeSceneAct(1, 2.0, 1.0, "Short 2", "scp"),
        NarrativeSceneAct(2, 3.0, 2.0, "Short 3", "scp"),
    ]
    expected_dur = calculate_xfade_duration([2.0, 1.0, 2.0], 0.75, clamp=True)
    assert expected_dur == pytest.approx(4.4)

    r.composite_multi_act_video(acts, audio, out, total_duration=expected_dur)

    cmd = captured["cmd"]
    fc = cmd[cmd.index("-filter_complex") + 1]
    xfade_filters = [p for p in fc.split(";") if "xfade=transition=fade" in p]
    assert len(xfade_filters) == 2

    # Clamped duration 0.300s reflected in filtergraph
    assert "duration=0.300:offset=1.700" in xfade_filters[0]
    assert "duration=0.300:offset=2.400" in xfade_filters[1]
    assert "duration=0.750" not in fc

    out_t = float([cmd[i + 1] for i, x in enumerate(cmd) if x == "-t"][-1])
    assert out_t == pytest.approx(4.4)


def test_multiact_stream_copy_homogeneous_multiact_xfade_zero_zero_encodes(tmp_path, monkeypatch):
    """Homogeneous loops with MULTIACT_XFADE=0 assemble via concat demuxer with 0 video re-encodes."""
    loop_a = tmp_path / "a.mp4"
    loop_b = tmp_path / "b.mp4"
    loop_c = tmp_path / "c.mp4"
    for p in (loop_a, loop_b, loop_c):
        p.write_bytes(b"\0" * 64)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF" + b"\0" * 40)
    out = tmp_path / "out.mp4"
    cmds = []

    def fake_run(cmd, check=True, **kw):
        cmds.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"mp4")
        return MagicMock(returncode=0)

    # All 3 loops have identical WxH, codec, pix_fmt, time_base matching target canvas (1920x1080)
    monkeypatch.setattr(
        "src.media.multi_act_renderer.probe_media",
        lambda *a, **k: _probe(1920, 1080, codec="h264", pix_fmt="yuv420p", time_base="1/90000"),
    )
    monkeypatch.setattr("src.media.multi_act_renderer.run_ffmpeg", fake_run)
    monkeypatch.setenv("DIRECTOR_SINGLE_PASS", "1")
    monkeypatch.setenv("MULTIACT_XFADE", "0")

    r = MultiActVideoRenderer(loops_dir=tmp_path)
    paths = [loop_a, loop_b, loop_c]
    monkeypatch.setattr(r, "resolve_loop_for_theme", lambda *a, **k: paths.pop(0))

    acts = [
        NarrativeSceneAct(0, 0.0, 2.0, "Act A", "scp", hud_badge="", hud_site="", hud_telemetry="", niche_hud={"hud_enabled": False}),
        NarrativeSceneAct(1, 2.0, 3.0, "Act B", "scp", hud_badge="", hud_site="", hud_telemetry="", niche_hud={"hud_enabled": False}),
        NarrativeSceneAct(2, 5.0, 2.5, "Act C", "scp", hud_badge="", hud_site="", hud_telemetry="", niche_hud={"hud_enabled": False}),
    ]
    r.composite_multi_act_video(acts, audio, out, total_duration=7.5, is_vertical=False)

    # Strict Zero-Encode assertions:
    # No filter_complex and no libx264
    assert not any("-filter_complex" in c for c in cmds)
    assert not any("libx264" in c for c in cmds)

    # Exactly 3 trim operations using -c:v copy
    trim_cmds = [c for c in cmds if "-stream_loop" in c and "-c:v" in c and c[c.index("-c:v") + 1] == "copy"]
    assert len(trim_cmds) == 3

    # Exactly 1 concat demuxer command using -c:v copy
    concat_cmds = [c for c in cmds if "-f" in c and "concat" in c and "-c:v" in c and c[c.index("-c:v") + 1] == "copy"]
    assert len(concat_cmds) == 1
    mux_cmd = concat_cmds[0]
    assert mux_cmd[mux_cmd.index("-c:v") + 1] == "copy"
    assert mux_cmd[mux_cmd.index("-c:a") + 1] == "aac"
    assert mux_cmd[mux_cmd.index("-t") + 1] == "7.500"


def test_multiact_empty_acts_raises_value_error(tmp_path):
    """Empty acts list immediately raises ValueError without unhandled exceptions."""
    r = MultiActVideoRenderer(loops_dir=tmp_path)
    with pytest.raises(ValueError, match="No acts provided"):
        r.composite_multi_act_video([], tmp_path / "a.wav", tmp_path / "out.mp4", total_duration=0.0)



