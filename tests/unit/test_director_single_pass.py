"""Unit tests for DIRECTOR_SINGLE_PASS."""
from unittest.mock import MagicMock
from pathlib import Path
import pytest
from src.media.director_single_pass import (
    build_scale_concat_video_filters, build_xfade_video_filters,
    count_director_video_encodes, director_single_pass_enabled, director_xfade_enabled,
    is_procedural_engine_type, manifest_eligible_for_loop_single_pass,
)
from src.media.multi_act_renderer import MultiActVideoRenderer, NarrativeSceneAct, calculate_xfade_duration

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
    acts = [NarrativeSceneAct(0,0.0,2.0,"A","scp"), NarrativeSceneAct(1,2.0,2.0,"B","scp")]
    r.composite_multi_act_video(acts, audio, out, calculate_xfade_duration([2.0,2.0],0.75))
    fc = captured["cmd"][captured["cmd"].index("-filter_complex")+1]
    assert "xfade=transition=fade" in fc and "concat=n=" not in fc

def test_compositor_stream_copy(tmp_path, monkeypatch):
    from src.media.compositor import MultiSceneCompositor
    from src.scene_manifest import ProceduralConfig, SceneConfig, SceneManifestV2, AudioTracks, SafeArea
    loop = tmp_path / "cat.mp4"; loop.write_bytes(b"\0"*64)
    vs = MagicMock(width=1280, height=720); probe = MagicMock(video_streams=[vs], primary_video=vs)
    cmds = []
    def fake_run(cmd, **kw):
        cmds.append(list(cmd)); Path(cmd[-1]).write_bytes(b"mp4"); return MagicMock(returncode=0)
    monkeypatch.setattr("src.media.compositor.probe_media", lambda *a, **k: probe)
    monkeypatch.setattr("src.media.compositor.run_ffmpeg", fake_run)
    monkeypatch.setenv("DIRECTOR_SINGLE_PASS","1"); monkeypatch.setenv("DIRECTOR_XFADE","0")
    comp = MultiSceneCompositor()
    scene = SceneConfig(scene_index=1, scene_id="s1", start_sec=0.0, duration_sec=1.0, tension_level=2, engine_type="pure_procedural_webgl", procedural_config=ProceduralConfig())
    scene2 = scene.model_copy(update={"scene_index":2,"scene_id":"s2","start_sec":1.0})
    manifest = SceneManifestV2(story_id="t", lane_id="lane", channel_name="moku", resolution=[1280,720], fps=30, total_duration_sec=2.0, scenes=[scene,scene2], audio_tracks=AudioTracks(narration_path=str(tmp_path/"n.wav")), safe_area=SafeArea())
    (tmp_path/"n.wav").write_bytes(b"RIFF"+b"\0"*40)
    monkeypatch.setattr(comp, "_resolve_procedural_loop_path", lambda *a, **k: loop)
    ok = comp._assemble_procedural_loops_single_pass(manifest=manifest, output_mp4=tmp_path/"a.mp4", width=1280, height=720, fps=30, crf=26, preset="ultrafast", tmp_dir=tmp_path)
    assert ok and comp._last_assembly_plan.mode == "loop_stream_copy"
    assert sum(1 for c in cmds if "-stream_loop" in c and "-c:v" in c and c[c.index("-c:v")+1]=="copy") == 2
