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


from src.verification.guardrails import (
    CheckResult,
    ImportScanner,
    IntegrityReport,
    check_agent_homes_and_secrets,
    check_anti_bloat,
    check_architecture_docs,
    check_git_hooks,
    check_legacy_subsystems,
    check_mcp_sync,
    check_test_collectability,
    check_worktrees,
    check_zero_browser_policy,
    check_zero_procedural_math,
    run_integrity_audit,
    scan_module_imports,
    scan_source_imports,
)


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

    def test_reg13_pipeline_never_burns_captions(self, tmp_path: Path) -> None:
        """Assert pipeline stages enforce stream-copy and soft muxing without subtitle burn."""
        from unittest.mock import MagicMock, patch
        from src.pipeline.stages.stage_08_loop import stage_08_loop_scene
        from src.pipeline.stages.stage_09_render import stage_09_video_rendering

        # 1. Verify stage 08 configures stream-copy mode and soft muxing
        ctx8 = MagicMock()
        ctx8.profiler.phase.return_value.__enter__ = MagicMock()
        ctx8.profiler.phase.return_value.__exit__ = MagicMock()
        ctx8.subtitles_active = True
        sub_file = tmp_path / "test.ass"
        sub_file.write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")
        ctx8.ass_path = sub_file
        ctx8.is_multiscene_mode = False
        ctx8.work_dir = tmp_path
        ctx8.story = {}
        ctx8.channel_name = "test_channel"
        ctx8.title = "Test Story"
        ctx8.audio_path = tmp_path / "audio.wav"
        ctx8.music_track_path = None
        ctx8.audio = {"duration_sec": 10.0}
        ctx8.scene_bg_list = []
        with patch("src.scene_manifest.build_scene_manifest", return_value=tmp_path / "manifest.json"):
            stage_08_loop_scene(ctx8)

        assert ctx8.stream_copy_mode is True, "REG-13 VIOLATION: stage_08 did not enable stream_copy_mode"
        assert ctx8.mux_subtitles is True, "REG-13 VIOLATION: stage_08 did not enable mux_subtitles"

        # 2. Verify stage 09 passes stream_copy=True and soft muxing to loop engine without burn_subtitles
        ctx9 = MagicMock()
        ctx9.profiler.phase.return_value.__enter__ = MagicMock()
        ctx9.profiler.phase.return_value.__exit__ = MagicMock()
        ctx9.is_long_lane = False
        ctx9.is_multiscene_mode = False
        ctx9.stream_copy_mode = True
        ctx9.mux_subtitles = True
        ctx9.manifest_path = tmp_path / "manifest.json"
        video_out = tmp_path / "video.mp4"
        video_out.write_bytes(b"dummy_video")
        ctx9.video_path = video_out
        ctx9.audio_path = tmp_path / "audio.wav"
        ctx9.ass_path = sub_file
        ctx9.resolved_loop_path = tmp_path / "loop.mp4"
        ctx9.music_track_path = None
        ctx9.bg_volume = 0.04
        ctx9.audio = {"duration_sec": 10.0}
        ctx9.target_category = "dark_ambient"
        ctx9.channel_name = "test_channel"
        ctx9.run_id = "test_run_reg13"
        ctx9.lane.orientation = "vertical"
        ctx9.lane.target_duration_sec = 10.0

        stage_09_video_rendering(ctx9)

        assert ctx9.loop_engine.render.called, "REG-13 VIOLATION: loop_engine.render was not invoked"
        call_kwargs = ctx9.loop_engine.render.call_args[1]
        assert call_kwargs.get("stream_copy") is True, (
            "REG-13 VIOLATION: loop render did not enable stream_copy"
        )
        assert call_kwargs.get("include_subtitles") is True
        assert "burn_subtitles" not in call_kwargs, (
            "REG-13 VIOLATION: burn_subtitles parameter reintroduced in render invocation"
        )

    def test_reg13_stream_copy_cmd_muxes_not_libass(self, tmp_path: Path) -> None:
        """Assert stream-copy FFmpeg command uses -c:v copy and mov_text muxing, never libass burn."""
        from src.media.loop_engine import LoopVideoEngine

        engine = LoopVideoEngine()
        sub_file = tmp_path / "subs.ass"
        sub_file.write_text(
            "[Script Info]\nTitle: Test\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Caption test\n",
            encoding="utf-8",
        )
        concat_list = tmp_path / "concat.txt"
        concat_list.write_text("ffconcat version 1.0\nfile 'loop.mp4'\n", encoding="utf-8")
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 40)
        out_video = tmp_path / "output.mp4"

        cmd = engine.build_stream_copy_composition_cmd(
            concat_list_path=concat_list,
            audio_path=audio_file,
            bgm_path=None,
            duration_sec=10.0,
            output_video_path=out_video,
            subtitle_path=sub_file,
        )

        cmd_str = " ".join(cmd)
        # 1. Video stream is copied without re-encoding
        assert "-c:v" in cmd, "REG-13 VIOLATION: -c:v missing from stream-copy command"
        assert cmd[cmd.index("-c:v") + 1] == "copy", (
            f"REG-13 VIOLATION: video codec is {cmd[cmd.index('-c:v') + 1]!r}, expected 'copy'"
        )
        assert "libx264" not in cmd, "REG-13 VIOLATION: libx264 re-encode found on stream-copy path"

        # 2. Subtitles are muxed via mov_text, never burned with libass
        assert "-c:s" in cmd, "REG-13 VIOLATION: subtitle codec -c:s missing"
        assert cmd[cmd.index("-c:s") + 1] == "mov_text", (
            f"REG-13 VIOLATION: subtitle codec is {cmd[cmd.index('-c:s') + 1]!r}, expected 'mov_text'"
        )
        assert "ass=" not in cmd_str, "REG-13 VIOLATION: stream-copy cmd injects libass burn filter"
        assert "subtitles=" not in cmd_str, "REG-13 VIOLATION: stream-copy cmd injects subtitles burn filter"
        assert str(sub_file) in cmd, "REG-13 VIOLATION: subtitle file not included as input for muxing"

    def test_reg13_compose_does_not_disable_copy_when_captions_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Assert LoopVideoEngine.compose preserves stream-copy when captions are active."""
        from src.media.loop_engine import LoopVideoEngine
        from unittest.mock import MagicMock

        engine = LoopVideoEngine()
        sub_file = tmp_path / "subs.ass"
        sub_file.write_text(
            "[Script Info]\nTitle: Test\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello world\n",
            encoding="utf-8",
        )
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 40)
        out_video = tmp_path / "output.mp4"

        stream_copy_flow_called: list[tuple[Any, dict[str, Any]]] = []

        def spy_stream_copy_flow(*args: Any, **kwargs: Any) -> str:
            stream_copy_flow_called.append((args, kwargs))
            out_video.write_bytes(b"dummy_mp4")
            return str(out_video)

        monkeypatch.setattr(engine, "_try_stream_copy_flow", spy_stream_copy_flow)
        monkeypatch.setattr(
            "src.media.loop.stream_copy._probe_media",
            lambda p: MagicMock(duration=10.0, video_streams=[MagicMock(width=1080, height=1920)]),
        )
        monkeypatch.setattr(engine, "resolve_continuous_loop", lambda **kw: tmp_path / "loop.mp4")

        result = engine.compose(
            audio_path=audio_file,
            output_video_path=out_video,
            subtitle_path=sub_file,
            include_subtitles=True,
            stream_copy=True,
            orientation="vertical",
            duration_sec=10.0,
        )

        assert len(stream_copy_flow_called) == 1, (
            "REG-13 VIOLATION: _try_stream_copy_flow was not called when captions were active"
        )
        call_kwargs = stream_copy_flow_called[0][1]
        assert call_kwargs.get("mux_path") == sub_file, (
            "REG-13 VIOLATION: mux_path was not forwarded to stream-copy flow"
        )
        assert result == str(out_video)


class TestResourceTargetGovernanceGuardrails:
    """Enforce strict 2 Cores and 2 GB RAM target governance in AGENTS.md and technical documentation."""

    def test_reg14_agents_governance_contains_resource_target(self) -> None:
        agents_doc = REPO_ROOT / "AGENTS.md"
        assert agents_doc.exists(), "AGENTS.md must exist in repo root"
        content = agents_doc.read_text(encoding="utf-8")
        assert "Strict Resource Target & Performance Budget (2 Cores, 2 GB RAM)" in content, (
            "REG-14 VIOLATION: Section 5 Resource Target & Performance Budget missing in AGENTS.md"
        )
        assert "≤ 2 CPU Cores" in content, (
            "REG-14 VIOLATION: Target ceiling of ≤ 2 CPU Cores missing in AGENTS.md"
        )
        assert "≤ 2.0 GiB RAM" in content, (
            "REG-14 VIOLATION: Target ceiling of ≤ 2.0 GiB RAM missing in AGENTS.md"
        )
        assert "Resource Work Refusal" in content, (
            "REG-14 VIOLATION: Resource Work Refusal policy missing in AGENTS.md"
        )

    def test_reg14_ffmpeg_low_cpu_documents_resource_target(self) -> None:
        doc = REPO_ROOT / "docs" / "FFMPEG_LOW_CPU.md"
        assert doc.exists(), "docs/FFMPEG_LOW_CPU.md must exist"
        content = doc.read_text(encoding="utf-8")
        assert "Target Resource Envelope (≤ 2 Cores CPU, ≤ 2.0 GiB RAM)" in content, (
            "REG-14 VIOLATION: Target Resource Envelope rule missing in docs/FFMPEG_LOW_CPU.md"
        )


# =============================================================================
# Streamlined Integrity Engine & Unified Guardrails Core
# =============================================================================

class TestVerificationCoreModule:
    """Tests for src/verification/guardrails.py SSOT module."""

    def test_import_scanner_ast_parsing_and_docstring_immunity(self, tmp_path: Path) -> None:
        """Assert ImportScanner captures aliased and multiline imports while ignoring comments and docstrings."""
        from src.verification.guardrails import ImportScanner, scan_module_imports, scan_source_imports

        snippet = '''# A comment mentioning import playwright
"""
Docstring with from src.rendering import ObsoleteRenderer
"""
import os
import sys as system
from pathlib import Path
from src.media import (
    subtitles_ass,
    proc_engine,
)
from src import compositing
'''
        test_file = tmp_path / "test_snippet.py"
        test_file.write_text(snippet, encoding="utf-8")

        imports = scan_module_imports(test_file)
        assert "os" in imports
        assert "sys" in imports
        assert "pathlib" in imports
        assert "src.media" in imports
        assert "src.media.proc_engine" in imports
        assert "src.compositing" in imports

        # Ensure comments and docstrings are ignored
        assert not any("playwright" in imp for imp in imports)
        assert not any("src.rendering" in imp for imp in imports)

        # scan_source_imports should return the same
        src_imports = scan_source_imports(snippet)
        assert "src.media.proc_engine" in src_imports
        assert not any("playwright" in imp for imp in src_imports)

    def test_verify_integrity_cli_safe_subprocesses_and_metacharacters(self) -> None:
        """Threat Matrix: subprocess execution boundary - metacharacters are safely handled without shell injection."""
        import subprocess
        import sys

        script = REPO_ROOT / "scripts" / "verify_integrity.py"
        assert script.exists(), "scripts/verify_integrity.py must exist"

        proc = subprocess.run(
            [sys.executable, str(script), ";", "echo", "PWNED"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            shell=False,
        )
        assert "PWNED" not in proc.stdout
        assert proc.returncode != 0

    def test_staged_mode_handles_spaces_and_unicode_paths(self, tmp_path: Path) -> None:
        """Threat Matrix: git cached path parsing boundary - handles spaces and unicode characters."""
        from src.verification.guardrails import run_integrity_audit

        arch_file = tmp_path / "docs" / "architecture" / "01_diseño obsoleto.md"
        arch_file.parent.mkdir(parents=True, exist_ok=True)
        arch_file.write_text("obsolete", encoding="utf-8")

        staged_paths = [
            "docs/architecture/01_diseño obsoleto.md",
            "src/valid path with spaces.py",
        ]
        report = run_integrity_audit(tmp_path, staged=True, staged_paths=staged_paths)
        assert report.healthy is False
        assert report.exit_code == 1
        assert any("01_diseño obsoleto.md" in err["message"] or any("01_diseño obsoleto.md" in d for d in err.get("details", [])) for err in report.checks_failed)

    def test_staged_mode_empty_index_exits_under_50ms(self) -> None:
        """Threat Matrix: commit state boundary - empty index exits immediately with code 0 in < 50ms."""
        import time
        from src.verification.guardrails import run_integrity_audit

        t0 = time.time()
        report = run_integrity_audit(REPO_ROOT, staged=True, staged_paths=[])
        elapsed_ms = (time.time() - t0) * 1000

        assert report.healthy is True
        assert report.exit_code == 0
        assert elapsed_ms < 50.0

    def test_shell_shim_forwards_arguments_with_spaces_intact(self) -> None:
        """Threat Matrix: shell script arguments boundary - forwards arguments with spaces intact."""
        import subprocess

        shim = REPO_ROOT / "scripts" / "verify_integrity.sh"
        assert shim.exists(), "scripts/verify_integrity.sh must exist"

        # Pass an argument containing spaces; python runner should see the intact argument string
        proc = subprocess.run(
            [str(shim), "--bogus arg with spaces"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 2, f"Expected argparse exit 2, got {proc.returncode}"
        assert "--bogus arg with spaces" in (proc.stderr + proc.stdout)

    def test_exit_code_propagation_on_invariant_violations(self) -> None:
        """Threat Matrix: exit code propagation boundary - invariant violations exit with status code 1."""
        import subprocess
        import sys

        py_script = REPO_ROOT / "scripts" / "verify_integrity.py"
        sh_script = REPO_ROOT / "scripts" / "verify_integrity.sh"

        test_doc = REPO_ROOT / "docs" / "architecture" / "09_temporary_test_violation.md"
        try:
            test_doc.parent.mkdir(parents=True, exist_ok=True)
            test_doc.write_text("violation", encoding="utf-8")

            # Python runner must exit 1
            py_proc = subprocess.run(
                [sys.executable, str(py_script), "--fast"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
            )
            assert py_proc.returncode == 1, f"Python runner returned {py_proc.returncode}, expected 1"

            # Shell shim must exit 1
            sh_proc = subprocess.run(
                [str(sh_script), "--fast"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
            )
            assert sh_proc.returncode == 1, f"Shell shim returned {sh_proc.returncode}, expected 1"
        finally:
            if test_doc.exists():
                test_doc.unlink()

    @pytest.mark.asyncio
    async def test_mcp_tool_parses_structured_json_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Assert MCP tool verify_integrity consumes structured JSON without scraping stdout emojis."""
        import json
        import subprocess
        from unittest.mock import MagicMock
        from mcp.server.mcpserver import MCPServer
        from src.mcp.tools.verify_integrity import register_verify_integrity_tool

        sample_json = json.dumps({
            "healthy": True,
            "status": "HEALTHY",
            "exit_code": 0,
            "checks_passed": ["Zero-Browser Policy: zero Playwright imports in media and pipeline."],
            "checks_failed": [],
            "commit_count": 325,
            "duration_ms": 42,
        })

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = sample_json
        mock_proc.stderr = ""

        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_proc)

        server = MCPServer("test")
        register_verify_integrity_tool(server)

        result = await server.call_tool("verify_integrity", {"fast": True})
        content_text = result[0].text if isinstance(result, list) else result.content[0].text
        data = json.loads(content_text)
        assert data["healthy"] is True
        assert data.get("duration_ms") == 42
        assert data["checks_passed"] == ["Zero-Browser Policy: zero Playwright imports in media and pipeline."]

    def test_guardrail_check_functions_direct_invocation(self) -> None:
        """Affirm REG-01 through REG-14 invariants by calling guardrail check functions directly."""
        res_wt = check_worktrees(REPO_ROOT)
        assert res_wt.passed is True, f"Worktree check failed: {res_wt.message}"

        res_docs = check_architecture_docs(REPO_ROOT)
        assert res_docs.passed is True, f"Architecture docs check failed: {res_docs.message}"

        res_subsys = check_legacy_subsystems(REPO_ROOT)
        assert res_subsys.passed is True, f"Legacy subsystems check failed: {res_subsys.message}"

        res_browser = check_zero_browser_policy(REPO_ROOT)
        assert res_browser.passed is True, f"Zero browser check failed: {res_browser.message}"

        res_proc = check_zero_procedural_math(REPO_ROOT)
        assert res_proc.passed is True, f"Zero procedural math check failed: {res_proc.message}"

        res_hooks = check_git_hooks(REPO_ROOT)
        assert res_hooks.passed is True, f"Git hooks check failed: {res_hooks.message}"

        res_bloat = check_anti_bloat(REPO_ROOT)
        assert res_bloat.passed is True, f"Anti-bloat check failed: {res_bloat.message}"

        res_secrets = check_agent_homes_and_secrets(REPO_ROOT)
        assert res_secrets.passed is True, f"Agent homes and secrets check failed: {res_secrets.message}"

        res_tests = check_test_collectability(REPO_ROOT)
        assert res_tests.passed is True, f"Test collectability check failed: {res_tests.message}"

    def test_full_integrity_audit_passes_cleanly(self) -> None:
        """Verify full run_integrity_audit produces a 100% HEALTHY report with exit code 0."""
        report = run_integrity_audit(REPO_ROOT, fast=True)
        assert report.healthy is True
        assert report.status == "HEALTHY"
        assert report.exit_code == 0
        assert len(report.checks_failed) == 0
        assert len(report.checks_passed) >= 8







