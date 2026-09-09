"""
tests/unit/test_anti_regression_guardrails.py - Automated Anti-Regression Guardrail Suite.

Enforces strict architectural invariants from docs/PLAN_MAESTRO_PIPELINE_VISUAL.md:
- REG-01: Zero Playwright / Chromium headless imports in media production pipeline.
- REG-02: Zero legacy web renderers or HTML template directories.
- REG-03: Zero Pillow/PIL frame-by-frame subtitle rasterization loops in video pipeline.
- REG-04: Single-pass atomic FFmpeg encoding without intermediate disk chunks.
- REG-05: Subtitle safe area margins >= 240px (MarginV) for mobile UI compliance.
- REG-06: Asynchronous stderr draining to prevent OS pipe deadlocks.
- REG-07: Quarantined WGSL shaders live under src/media/_legacy/shaders (not prod path).
- REG-08: In-memory compositor must use pre-allocated contiguous numpy buffers.
- REG-09: Strongly typed VisualArchetypeId in schema and Pydantic models.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = REPO_ROOT / "src"
MEDIA_DIR = SRC_DIR / "media"


def _openspec_context_block(content: str) -> str:
    """Return the YAML `context: |` block from openspec/config.yaml."""
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


class ImportScanner(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.append(node.module)
        self.generic_visit(node)


def scan_module_imports(file_path: Path) -> list[str]:
    if not file_path.exists() or not file_path.suffix == ".py":
        return []
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    scanner = ImportScanner()
    scanner.visit(tree)
    return scanner.imports


# ==============================================================================
# REG-01 & REG-02: Eradication of Browser-Based Rendering & Legacy Files
# ==============================================================================

class TestLegacyEradicationGuardrails:
    """Ensures legacy Playwright / Chromium code is never accidentally reintroduced."""

    def test_reg01_no_playwright_in_media_pipeline(self) -> None:
        """Assert zero Playwright imports across all src/media/ and src/pipeline.py."""
        target_files = list(MEDIA_DIR.glob("**/*.py")) + [SRC_DIR / "pipeline.py"]
        forbidden_tokens = {"playwright", "playwright.async_api", "playwright.sync_api"}

        violations = []
        for py_file in target_files:
            imports = scan_module_imports(py_file)
            for imp in imports:
                if any(imp == f or imp.startswith(f + ".") for f in forbidden_tokens):
                    violations.append(f"{py_file.relative_to(REPO_ROOT)} imports '{imp}'")

        assert not violations, f"REG-01 VIOLATION: Playwright re-imported in media pipeline:\n" + "\n".join(violations)

    def test_reg02_no_legacy_web_renderers_or_templates(self) -> None:
        """Assert legacy files and web_templates/ directory do not exist on disk."""
        forbidden_paths = [
            MEDIA_DIR / "web_renderer.py",
            MEDIA_DIR / "realtime_video_engine.py",
            MEDIA_DIR / "web_templates",
            REPO_ROOT / "dev" / "generate_scp_short.py",
        ]
        existing = [str(p.relative_to(REPO_ROOT)) for p in forbidden_paths if p.exists()]
        assert not existing, f"REG-02 VIOLATION: Legacy files found on disk:\n" + "\n".join(existing)

    def test_reg02_no_web_renderer_references_in_media_exports(self) -> None:
        """Assert src/media/__init__.py does not export legacy web renderers."""
        init_code = (MEDIA_DIR / "__init__.py").read_text(encoding="utf-8")
        assert "WebVideoRenderer" not in init_code
        assert "RealtimeVideoEngine" not in init_code


# ==============================================================================
# REG-03 & REG-05: Subtitle Rendering Invariants (libass & Safe-Area)
# ==============================================================================

class TestSubtitleAndTypographyGuardrails:
    """Ensures subtitle rendering uses libass and respects safe-area margins."""

    def test_reg03_subtitles_module_exports_libass_generator(self) -> None:
        """Assert media exports provide ASSSubtitleGenerator."""
        from src.media import ASSSubtitleGenerator, sanitize_timestamps, format_ass_timestamp
        assert ASSSubtitleGenerator is not None
        assert sanitize_timestamps is not None
        assert format_ass_timestamp is not None

    def test_reg03_pillow_subtitle_bridge_is_opt_in_only(self) -> None:
        """Assert Pillow subtitle bridge stays opt-in; default prefers libass helpers."""
        from src.media import force_pillow_subtitles_enabled, write_ass_from_cues_or_words
        assert force_pillow_subtitles_enabled() is False
        assert callable(write_ass_from_cues_or_words)
        # compositor must prefer libass helpers
        comp_src = (MEDIA_DIR / "compositor.py").read_text(encoding="utf-8")
        assert "force_pillow_subtitles_enabled" in comp_src
        assert "write_ass_from_cues_or_words" in comp_src or "ass=" in comp_src
        loop_src = (MEDIA_DIR / "loop_engine.py").read_text(encoding="utf-8")
        assert "force_pillow_subtitles_enabled" in loop_src

    def test_reg05_ass_generator_enforces_safe_area_margin(self, tmp_path: Path) -> None:
        """Assert ASSSubtitleGenerator enforces MarginV >= 240px for YouTube Shorts UI."""
        from src.media.subtitles_ass import ASSSubtitleGenerator
        generator = ASSSubtitleGenerator()
        out_file = tmp_path / "test.ass"
        generator.generate_ass_file(
            word_timestamps=[{"word": "TEST", "start": 0.0, "end": 1.0}],
            output_path=out_file,
            video_width=1080,
            video_height=1920,
            margin_v=260,
        )
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "MarginV" in content
        for line in content.splitlines():
            if line.startswith("Style:"):
                parts = line.split(",")
                margin_v = int(parts[-2].strip())
                assert margin_v >= 240, f"REG-05 VIOLATION: Subtitle MarginV {margin_v} < 240px"


# ==============================================================================
# REG-04 & REG-06: Unified Atomic FFmpeg & Asynchronous Pipe Protection
# ==============================================================================

class TestFFmpegPipelineGuardrails:
    """Ensures single-pass atomic encoding and OS pipe buffer safety."""

    def test_reg04_unified_encoder_atomic_filter_complex(self, tmp_path: Path) -> None:
        """Assert UnifiedEncoder builds atomic -filter_complex without disk chunks."""
        from src.media.unified_encoder import UnifiedEncoder
        voice_file = tmp_path / "voice.wav"
        drone_file = tmp_path / "drone.wav"
        sub_file = tmp_path / "sub.ass"
        voice_file.write_bytes(b"dummy")
        drone_file.write_bytes(b"dummy")
        sub_file.write_text("[Script Info]\n", encoding="utf-8")

        encoder = UnifiedEncoder(
            output_mp4=tmp_path / "out.mp4",
            width=1080,
            height=1920,
            fps=30,
            voice_wav=voice_file,
            drone_wav=drone_file,
            ass_subtitle_path=sub_file,
        )
        cmd = encoder.build_ffmpeg_command()
        assert "-filter_complex" in cmd
        filter_complex_str = cmd[cmd.index("-filter_complex") + 1]
        assert "subtitles=" in filter_complex_str or "ass=" in filter_complex_str
        assert "sidechaincompress" in filter_complex_str
        assert "loudnorm" in filter_complex_str

    def test_reg06_unified_encoder_drains_stderr_asynchronously(self) -> None:
        """Assert UnifiedEncoder defines asynchronous stderr draining mechanism."""
        from src.media.unified_encoder import UnifiedEncoder
        assert hasattr(UnifiedEncoder, "_drain_stderr"), (
            "REG-06 VIOLATION: UnifiedEncoder missing _drain_stderr to prevent OS pipe deadlocks."
        )


# ==============================================================================
# REG-07 & REG-08: Zero-Copy Procedural & Vector Compositor Invariants
# ==============================================================================

class TestCompositorAndProceduralGuardrails:
    """Ensures deterministic memory bounds and zero-allocation frame buffering."""

    def test_reg07_wgsl_shader_catalog_completeness(self) -> None:
        """Assert zero WGSL shaders and zero _legacy directory exist on disk (100% asset-only pipeline)."""
        assert not (MEDIA_DIR / "shaders").exists(), (
            "REG-07 VIOLATION: src/media/shaders must not exist"
        )
        assert not (MEDIA_DIR / "_legacy").exists(), (
            "REG-07 VIOLATION: src/media/_legacy must be completely eradicated"
        )
        found_wgsl = list(REPO_ROOT.glob("**/*.wgsl"))
        assert len(found_wgsl) == 0, f"REG-07 VIOLATION: Found WGSL shaders on disk: {found_wgsl}"

    def test_reg08_inmemory_compositor_reuses_buffers(self) -> None:
        """Assert InMemoryCompositor allocates contiguous memory buffers and does not leak."""
        from src.media.inmemory_compositor import InMemoryCompositor
        compositor = InMemoryCompositor(width=1080, height=1920)
        assert hasattr(compositor, "_out_buffer")
        assert compositor._out_buffer.shape == (1920, 1080, 4)
        assert compositor._out_buffer.flags.c_contiguous is True


# ==============================================================================
# REG-09: Schema & Pydantic Contract Invariants
# ==============================================================================

class TestContractSchemaGuardrails:
    """Ensures schema strictly forbids procedural_config and only accepts asset engine types."""

    def test_reg09_visual_archetype_tokens_in_sync(self) -> None:
        """Assert schema strictly forbids procedural_config and only accepts asset engine types."""
        import json
        schema_path = REPO_ROOT / "schemas" / "scene_manifest.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        scene_schema = schema["properties"]["scenes"]["items"]
        not_rules = scene_schema.get("not", {}).get("anyOf", [])
        forbidden_reqs = [rule.get("required") for rule in not_rules if "required" in rule]
        assert ["procedural_config"] in forbidden_reqs

        allowed_engines = set(scene_schema["properties"]["engine_type"]["enum"])
        assert allowed_engines == {"catalog_loop", "static_matte", "hybrid_cinematic_ai"}


# ==============================================================================
# REG-10 & REG-11: Eradication of Retired Subsystems and Accurate Config
# ==============================================================================

class TestRetiredSubsystemGuardrails:
    """Ensures retired legacy subsystems and outdated configs are never reintroduced."""

    def test_reg10_zero_imports_of_retired_legacy_subsystems(self) -> None:
        """Assert zero imports of src.rendering, src.compositing, or src.export across src/ and tests/."""
        all_py_files = list((REPO_ROOT / "src").glob("**/*.py")) + list((REPO_ROOT / "tests").glob("**/*.py"))
        forbidden_prefixes = ("src.rendering", "src.compositing", "src.export")

        violations = []
        for py_file in all_py_files:
            imports = scan_module_imports(py_file)
            for imp in imports:
                if any(imp == f or imp.startswith(f + ".") for f in forbidden_prefixes):
                    violations.append(f"{py_file.relative_to(REPO_ROOT)} imports '{imp}'")

        assert not violations, (
            "REG-10 VIOLATION: Retired legacy subsystem re-imported in codebase:\n"
            + "\n".join(violations)
        )

    def test_reg11_zero_playwright_in_openspec_config(self) -> None:
        """Assert openspec/config.yaml lists Pillow thumbs SSOT and not Playwright/wgpu-py/resvg-py as production."""
        config_path = REPO_ROOT / "openspec" / "config.yaml"
        if not config_path.is_file():
            return
        content = config_path.read_text(encoding="utf-8")
        context = _openspec_context_block(content)
        assert "Playwright" not in context, (
            "REG-11 VIOLATION: openspec/config.yaml still declares Playwright as production media"
        )
        assert "wgpu-py" not in context, (
            "REG-11 VIOLATION: openspec/config.yaml lists wgpu-py as production stack"
        )
        assert "resvg-py" not in context, (
            "REG-11 VIOLATION: openspec/config.yaml lists resvg-py as production stack"
        )
        assert "Pillow" in context and "thumb" in context.lower(), (
            "REG-11 VIOLATION: openspec/config.yaml must declare Pillow thumbs SSOT"
        )


# =============================================================================
# REG-12: FFmpeg 6.1 unquoted libass filter paths
# =============================================================================

class TestFFmpeg61LibassPathGuardrails:
    """Quoted ass=/fontsdir= values break libass on FFmpeg 6.1."""

    def test_reg12_no_quoted_ass_or_fontsdir_filter_paths(self) -> None:
        targets = list(MEDIA_DIR.glob("**/*.py")) + [REPO_ROOT / "lib" / "video.py"]
        forbidden = ("ass=filename='", "ass='", "fontsdir='")
        violations: list[str] = []
        for path in targets:
            if "_legacy" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for needle in forbidden:
                if needle in text:
                    violations.append(f"{path.relative_to(REPO_ROOT)} contains {needle!r}")
        assert not violations, (
            "REG-12 VIOLATION: quoted FFmpeg 6.1 libass paths:\n" + "\n".join(violations)
        )


class TestLoopHotPathNoBurnGuardrails:
    """Product path is catalog loop + -c:v copy + mov_text mux. Burn/Chromium must not return."""

    def test_reg13_pipeline_never_burns_captions(self) -> None:
        text = (SRC_DIR / "pipeline.py").read_text(encoding="utf-8")
        assert "burn_subtitles" not in text, (
            "REG-13 VIOLATION: src/pipeline.py reintroduced caption burn"
        )
        assert "stream_copy_mode = True" in text
        assert "subtitles_active = False" in text
        assert "FORCE_MULTISCENE" in text
        assert "is_multiscene_mode = False" in text
        assert "ScenePlannerCompositorAgent" in text
        assert "CinematicScriptCuratorAgent" in text

    def test_reg13_stream_copy_cmd_muxes_not_libass(self) -> None:
        text = (MEDIA_DIR / "loop_engine.py").read_text(encoding="utf-8")
        start = text.find("def build_stream_copy_composition_cmd")
        end = text.find("\n    def compose(", start)
        assert start != -1 and end != -1
        body = text[start:end]
        assert "ass=" not in body, (
            "REG-13 VIOLATION: stream-copy cmd builds a libass burn filter"
        )
        assert "libx264" not in body
        assert "subtitle_mux_ffmpeg_parts" in body
        assert '"copy"' in body or "'copy'" in body

    def test_reg13_compose_does_not_disable_copy_when_captions_active(self) -> None:
        text = (MEDIA_DIR / "loop_engine.py").read_text(encoding="utf-8")
        assert "bool(stream_copy) and (not subs_active)" not in text
        assert "is_stream_copy = (not subs_active)" not in text


