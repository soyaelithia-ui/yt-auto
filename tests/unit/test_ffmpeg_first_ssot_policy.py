"""Covering tests for ffmpeg-first-ssot-policy (spec/config ratification).

Asserts OpenSpec context + five main specs match FFmpeg SSOT. Does not invent
wgpu/NativeProceduralEngine renderer suites.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OPENSPEC = REPO_ROOT / "openspec"


def _resolve_ffmpeg_first_change_specs() -> Path:
    active = OPENSPEC / "changes" / "ffmpeg-first-ssot-policy" / "specs"
    if active.is_dir():
        return active
    archive_root = OPENSPEC / "changes" / "archive"
    matches = sorted(archive_root.glob("*-ffmpeg-first-ssot-policy"))
    for match in reversed(matches):
        specs = match / "specs"
        if specs.is_dir():
            return specs
    raise FileNotFoundError("ffmpeg-first-ssot-policy specs not found in active changes or archive")


CHANGE_SPECS = _resolve_ffmpeg_first_change_specs()
MAIN_SPECS = {
    "procedural-scene-compositor": OPENSPEC / "specs" / "procedural-scene-compositor" / "spec.md",
    "media-processing-performance-policy": OPENSPEC
    / "specs"
    / "media-processing-performance-policy"
    / "spec.md",
    "editorial-and-content-policy": OPENSPEC / "specs" / "editorial-and-content-policy" / "spec.md",
    "media-pipeline-hardening": OPENSPEC / "specs" / "media-pipeline-hardening" / "spec.md",
    "legacy-eradication-guardrails": OPENSPEC / "specs" / "legacy-eradication-guardrails" / "spec.md",
}
HOT_PATH = [
    REPO_ROOT / "src" / "media" / "compositor.py",
    REPO_ROOT / "src" / "media" / "loop_worker.py",
    REPO_ROOT / "src" / "media" / "hybrid_engine.py",
    REPO_ROOT / "src" / "media" / "proc_engine.py",
    REPO_ROOT / "src" / "media" / "multi_act_renderer.py",
    REPO_ROOT / "src" / "pipeline.py",
]
FORBIDDEN_PRODUCTION_STACK = ("wgpu-py", "resvg-py")
PRODUCTION_MUST_NEEDLES = (
    "wgpu-py",
    "resvg-py",
    "NativeProceduralEngine",
    "WebGPU",
    "WebGL",
    "Three.js",
)
OUT_OF_SCOPE_SCENARIO_FRAGMENTS = (
    "shader scene rendering",
    "Shader compilation",
    "camera drift",
    "border clipping",
    "particle",
    "crossfade composition",
    "transition duration",
    "luminance floor",
    "Peak highlight",
    "uniform struct",
    "art director",
    "watchdog",
    "Popen",
    "Maritime Narrative Shader",
    "Coastal Story Thumbnail",
    "Unrecognized engine",
    "compositor isolation",
    "fallback procedural shader",
    "frame stream corruption",
)


def _context_block(content: str) -> str:
    lines = content.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("context:"):
            start = i + 1
            break
    if start is None:
        return ""
    collected: list[str] = []
    for line in lines[start:]:
        if line and not line.startswith(" ") and not line.startswith("\t"):
            break
        collected.append(line)
    return "\n".join(collected)


def _requirement_blocks(text: str) -> list[str]:
    parts = re.split(r"\n(?=#{2,3} Requirement)", text)
    return [p for p in parts if re.match(r"#{2,3} Requirement", p)]


def _obligation_mentions_stack_without_opt_in(block: str) -> list[str]:
    """Return stack terms that a requirement MUST as production without opt-in."""
    hits: list[str] = []
    for chunk in block.splitlines():
        if not re.search(r"\bMUST\b", chunk):
            continue
        for term in PRODUCTION_MUST_NEEDLES:
            if term not in chunk:
                continue
            if re.search(rf"MUST NOT\b.*{re.escape(term)}", chunk):
                continue
            if re.search(rf"{re.escape(term)}.*MUST NOT", chunk):
                continue
            if re.search(rf"\bnot\b.*{re.escape(term)}", chunk, re.I):
                continue
            if re.search(rf"without\b.*{re.escape(term)}", chunk, re.I):
                continue
            if "ENABLE_NATIVE_PROCEDURAL" in chunk:
                continue
            if re.search(r"\bopt-?in\b", chunk, re.I):
                continue
            if re.search(r"quarantine", chunk, re.I):
                continue
            hits.append(term)
    return hits


def _module_level_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def _change_scenario_titles() -> list[str]:
    titles: list[str] = []
    for path in sorted(CHANGE_SPECS.rglob("spec.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#### Scenario:"):
                titles.append(line[len("#### Scenario:") :].strip())
    return titles


def test_openspec_config_lists_ffmpeg_and_pillow_thumbs():
    """OpenSpec tech stack validation; Pillow thumbs SSOT is not a retired library."""
    content = (OPENSPEC / "config.yaml").read_text(encoding="utf-8")
    context = _context_block(content)
    assert "FFmpeg" in context
    assert "Pillow" in context
    assert "thumb" in context.lower()
    assert "Playwright" not in context
    for term in FORBIDDEN_PRODUCTION_STACK:
        assert term not in context, f"{term} must not be listed as production stack"


def test_openspec_config_keeps_projects_zero_browser_and_testing_notes():
    content = (OPENSPEC / "config.yaml").read_text(encoding="utf-8")
    assert re.search(r"^projects:", content, re.MULTILINE)
    assert "Zero browser" in content or "zero browser" in content.lower()
    assert "src/youtube" in content
    assert re.search(r"^testing:", content, re.MULTILINE)
    assert "pytest" in content
    assert "Playwright stays off" in content or "Playwright" not in _context_block(content)


def test_five_main_specs_have_no_production_hot_path_must_wgpu():
    """NativeProceduralEngine WebGPU GLSL WebGL remain opt-in only."""
    violations: list[str] = []
    for name, path in MAIN_SPECS.items():
        text = path.read_text(encoding="utf-8")
        for block in _requirement_blocks(text):
            heading = block.splitlines()[0]
            for term in _obligation_mentions_stack_without_opt_in(block):
                violations.append(f"{name}: {heading} MUST {term} without ENABLE_NATIVE_PROCEDURAL/opt-in")
    assert not violations, "production-hot-path MUST stack leaks:\n" + "\n".join(violations)


def test_compositor_keeps_origin_main_hud_safe_zone():
    text = MAIN_SPECS["procedural-scene-compositor"].read_text(encoding="utf-8")
    assert "hud_layout" in text
    assert "top_bar" in text and "card" in text and "bottom_bar" in text
    assert "AspectLayoutManager" in text
    assert "safe-zone" in text or "safe zone" in text.lower()
    assert "typography" in text.lower()
    assert re.search(r"MUST NOT[^\n]*(wgpu|Playwright)", text)


def test_compositor_production_is_ffmpeg_lavfi_stream_copy_director_drawtext():
    """Production compositor uses FFmpeg lavfi stream-copy DIRECTOR_SINGLE_PASS and drawtext."""
    text = MAIN_SPECS["procedural-scene-compositor"].read_text(encoding="utf-8")
    lower = text.lower()
    assert "lavfi" in lower
    assert "stream-copy" in lower or "-c:v copy" in text
    assert "DIRECTOR_SINGLE_PASS" in text
    assert "drawtext" in lower
    assert "ENABLE_NATIVE_PROCEDURAL" in text
    assert "ProceduralVideoEngine" in text


def test_performance_policy_production_video_is_ffmpeg_not_wgpu_py():
    """Procedural Rendering without Browser Subprocesses; Homogeneous beats stay stream-copy."""
    text = MAIN_SPECS["media-processing-performance-policy"].read_text(encoding="utf-8")
    assert re.search(r"MUST use FFmpeg", text)
    assert "wgpu-py" in text and re.search(r"MUST NOT", text)
    assert "resvg-py" in text
    assert "stream_copy_mode" in text
    assert "-c:v copy" in text


def test_editorial_backgrounds_must_be_ffmpeg_loops_not_webgl():
    """Visual Quality Audit; Generic filler still discarded."""
    text = MAIN_SPECS["editorial-and-content-policy"].read_text(encoding="utf-8")
    assert re.search(r"FFmpeg procedural loops", text)
    assert "WebGL" in text and re.search(r"MUST NOT", text)
    assert "Three.js" in text
    assert "DISCARDED_GENERIC_FILLER" in text


def test_hardening_default_procedural_engine_lavfi_rawvideo_opt_in():
    """Production director path does not use rawvideo stdin; Production catalog uses FFmpeg lavfi; Channel with director pipeline defaults to ProceduralVideoEngine."""
    text = MAIN_SPECS["media-pipeline-hardening"].read_text(encoding="utf-8")
    assert "ProceduralVideoEngine()" in text
    assert "ENABLE_NATIVE_PROCEDURAL" in text
    assert "lavfi" in text.lower()
    assert re.search(r"rawvideo", text, re.IGNORECASE)
    assert "NativeProceduralEngine" in text


def test_guardrails_allow_pillow_thumbs_forbid_wgpu_py_production():
    """OpenSpec tech stack validation; Pillow thumbs SSOT is not a retired library."""
    text = MAIN_SPECS["legacy-eradication-guardrails"].read_text(encoding="utf-8")
    assert "Pillow" in text
    assert "thumb" in text.lower()
    assert "wgpu-py" in text
    assert "resvg-py" in text
    assert "Playwright" in text


def test_change_specs_only_in_scope_scenarios():
    titles = _change_scenario_titles()
    assert titles, "change specs must declare native #### Scenario: headings"
    assert len(titles) <= 12, f"change specs have {len(titles)} scenarios; target ≤12: {titles}"
    leaked = [
        title
        for title in titles
        if any(frag.lower() in title.lower() for frag in OUT_OF_SCOPE_SCENARIO_FRAGMENTS)
    ]
    assert not leaked, "change specs restated out-of-scope novels:\n" + "\n".join(leaked)


def test_hot_path_still_has_no_module_level_native_or_wgpu_imports():
    forbidden_prefixes = (
        "wgpu",
        "src.media.native_procedural",
        "src.media._legacy.native_procedural",
        "src.media._legacy",
    )
    violations: list[str] = []
    for path in HOT_PATH:
        if not path.is_file():
            continue
        for imp in _module_level_imports(path):
            if any(imp == p or imp.startswith(p + ".") for p in forbidden_prefixes):
                violations.append(f"{path.relative_to(REPO_ROOT)} top-level imports {imp!r}")
    assert not violations, "hot-path top-level wgpu/native imports:\n" + "\n".join(violations)


def test_compositor_default_still_does_not_load_wgpu(monkeypatch):
    """Compositor uses LoopVideoEngine; does not load wgpu or native procedural."""
    monkeypatch.delenv("ENABLE_NATIVE_PROCEDURAL", raising=False)
    for key in list(sys.modules):
        if (
            key == "wgpu"
            or key.startswith("wgpu.")
            or key == "src.media.native_procedural"
            or key.startswith("src.media.native_procedural.")
            or key == "src.media._legacy.native_procedural"
            or key.startswith("src.media._legacy.native_procedural.")
        ):
            del sys.modules[key]
        if key in ("src.media.compositor", "src.media.proc_engine"):
            del sys.modules[key]

    from src.media.interface import get_compositor
    from src.media.loop_engine import LoopVideoEngine

    compositor = get_compositor()
    assert isinstance(compositor, LoopVideoEngine)
    assert "wgpu" not in sys.modules
