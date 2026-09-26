"""Guardrail test suite: Zero Procedural & Mathematical Video Generation Policy.

Inviolable Policy:
1. Zero procedural/mathematical video engines (wgpu, pygfx, WGSL shaders, lavfi gradients/noise).
2. Zero Pillow rawvideo frame loops pumping software-rendered video frames into FFmpeg pipes.
3. Zero WGSL shader files or legacy shader directories in the repository.
4. 100% composition must rely on pre-rendered assets (catalog loops, real stills, real overlays).
"""

from __future__ import annotations

import ast
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


import json

def test_zero_legacy_dirs_and_wgsl_files():
    """Verify src/media/_legacy is completely deleted and no *.wgsl files exist."""
    legacy_dir = REPO_ROOT / "src" / "media" / "_legacy"
    assert not legacy_dir.exists(), f"Found forbidden legacy directory: {legacy_dir}"

    svg_overlays_dir = REPO_ROOT / "assets" / "svg_overlays"
    assert not svg_overlays_dir.exists(), f"Found forbidden svg_overlays directory: {svg_overlays_dir}"

    overlays_dir = REPO_ROOT / "assets" / "overlays"
    assert not overlays_dir.exists(), f"Found forbidden overlays directory: {overlays_dir}"

    wgsl_files = list(REPO_ROOT.glob("**/*.wgsl"))
    assert len(wgsl_files) == 0, f"Found forbidden WGSL shader files: {wgsl_files}"

    proc_engine_file = REPO_ROOT / "src" / "media" / "proc_engine.py"
    assert not proc_engine_file.exists(), f"Found forbidden proc_engine.py: {proc_engine_file}"

    native_proc_file = REPO_ROOT / "src" / "media" / "native_procedural.py"
    assert not native_proc_file.exists(), f"Found forbidden native_procedural.py: {native_proc_file}"

    lavfi_palettes_file = REPO_ROOT / "src" / "media" / "lavfi_palettes.py"
    assert not lavfi_palettes_file.exists(), f"Found forbidden lavfi_palettes.py: {lavfi_palettes_file}"


def test_zero_shader_remnants_in_schemas():
    """Verify schemas contain no shader remnants, uniform params, or diffusion prompts."""
    art_schema_path = REPO_ROOT / "schemas" / "art_director.schema.json"
    assert art_schema_path.exists()
    art_schema = json.loads(art_schema_path.read_text(encoding="utf-8"))

    art_scene_props = art_schema.get("properties", {}).get("scenes", {}).get("items", {}).get("properties", {})
    assert "image_prompts" not in art_scene_props, "Found forbidden 'image_prompts' in art_director schema"
    assert "archetype_id" not in art_scene_props, "Found forbidden 'archetype_id' in art_director schema"
    assert "uniform_params" not in art_scene_props, "Found forbidden 'uniform_params' in art_director schema"

    scene_schema_path = REPO_ROOT / "schemas" / "scene_planner.schema.json"
    assert scene_schema_path.exists()
    scene_schema = json.loads(scene_schema_path.read_text(encoding="utf-8"))

    scene_props = scene_schema.get("properties", {}).get("scenes", {}).get("items", {}).get("properties", {})
    engine_config_props = scene_props.get("engine_config", {}).get("properties", {})
    assert "shader_seed" not in engine_config_props, "Found forbidden 'shader_seed' in scene_planner schema"
    volumetric = engine_config_props.get("volumetric_lighting", {}).get("properties", {})
    assert "shader" not in volumetric, "Found forbidden 'shader' under volumetric_lighting in scene_planner schema"


def test_zero_wgpu_pygfx_imports_in_media_and_narrative():
    """Verify no wgpu, pygfx, or web_renderer imports exist in src/media, src/pipeline.py, src/narrative."""
    forbidden_modules = {"wgpu", "pygfx", "web_renderer"}
    target_paths = [
        *list((REPO_ROOT / "src" / "media").glob("*.py")),
        REPO_ROOT / "src" / "pipeline.py",
        *list((REPO_ROOT / "src" / "narrative").glob("*.py")),
        *list((REPO_ROOT / "src" / "agents").glob("*.py")),
    ]

    violations = []
    for py_file in target_paths:
        if not py_file.is_file():
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as err:
            violations.append(f"Failed to parse {py_file}: {err}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod in forbidden_modules:
                        violations.append(f"{py_file.relative_to(REPO_ROOT)}:{node.lineno} imports '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod in forbidden_modules:
                        violations.append(f"{py_file.relative_to(REPO_ROOT)}:{node.lineno} imports from '{node.module}'")

    assert not violations, f"Forbidden procedural module imports detected:\n" + "\n".join(violations)


def test_zero_pillow_rawvideo_frame_loops_in_media():
    """Verify that Pillow rawvideo frame loops and mathematical particle simulations are purged from src/media."""
    media_dir = REPO_ROOT / "src" / "media"
    violations = []

    for py_file in media_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        rel_path = py_file.relative_to(REPO_ROOT)

        # Check for purged methods and flags
        if "_render_scene_pillow_rawvideo" in text:
            violations.append(f"{rel_path} references '_render_scene_pillow_rawvideo'")
        if "force_pillow_rawvideo" in text:
            violations.append(f"{rel_path} references 'force_pillow_rawvideo'")
        if "_init_particle_system" in text:
            violations.append(f"{rel_path} references '_init_particle_system'")
        if "_render_particles" in text:
            violations.append(f"{rel_path} references '_render_particles'")
        if "_create_god_rays_overlay" in text:
            violations.append(f"{rel_path} references '_create_god_rays_overlay'")
        if "ENABLE_NATIVE_PROCEDURAL" in text:
            violations.append(f"{rel_path} references 'ENABLE_NATIVE_PROCEDURAL'")

    assert not violations, "Pillow frame pump or mathematical simulation remnants found:\n" + "\n".join(violations)


def test_zero_mathematical_video_filter_generation():
    """Verify that FFmpeg generative/mathematical video filters are absent from video engines."""
    media_dir = REPO_ROOT / "src" / "media"
    engines = [media_dir / "loop_engine.py", media_dir / "hybrid_engine.py", media_dir / "compositor.py"]
    
    forbidden_math_filters = ["mandelbrot", "cellauto", "life", "gradients="]
    violations = []

    for engine in engines:
        if not engine.exists():
            continue
        text = engine.read_text(encoding="utf-8")
        rel_path = engine.relative_to(REPO_ROOT)
        for flt in forbidden_math_filters:
            if flt in text:
                violations.append(f"{rel_path} contains generative filter '{flt}'")

    assert not violations, "Generative mathematical filters detected in media engines:\n" + "\n".join(violations)
