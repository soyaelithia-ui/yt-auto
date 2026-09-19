"""
tests/unit/test_pipeline_ast_tokens_adversarial.py - Adversarial Challenge Harness.

Milestone 2 Challenge Test Suite:
1. Invariant String Tokens Verification (11 mandatory tokens)
2. Exact Line Formatting Verification (subtitles_active = False on its own line)
3. Zero Prohibited Tokens Verification (burn_subtitles, preset="slow", etc.)
4. Exact Occurrence Count (SceneAssetTracker(repository=repository) == 1)
5. AST Structural Integrity (13 private stage helpers, signatures, CanonicalStage mapping)
6. Stage Helper Execution Sequence inside run_pipeline_once
7. Callable Exports Verification
8. Adversarial Parameter & Edge Case Stress Testing
"""
from __future__ import annotations

import ast
import inspect
import os
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_PATH = REPO_ROOT / "src" / "pipeline.py"


@pytest.fixture(scope="module")
def pipeline_code() -> str:
    """Read the complete source text of src/pipeline.py."""
    assert PIPELINE_PATH.is_file(), f"Missing {PIPELINE_PATH}"
    return PIPELINE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pipeline_ast(pipeline_code: str) -> ast.Module:
    """Parse src/pipeline.py into an AST module."""
    return ast.parse(pipeline_code, filename=str(PIPELINE_PATH))


# ==============================================================================
# 1. Mandatory String Tokens Verification
# ==============================================================================

class TestMandatoryStringTokens:
    """Stress-test that all mandatory tokens are present in executable contexts."""

    PIPELINE_MANDATORY_TOKENS = [
        "subtitles_active = False",
        "FORCE_MULTISCENE",
        "is_multiscene_mode = False",
        "# Scene asset lineage (outside stage-9 timer — SQLite I/O is not render)",
        "SceneAssetTracker(repository=repository)",
    ]

    STAGE_MANDATORY_TOKENS = [
        ("stage_08_loop.py", "stream_copy_mode = True"),
        ("stage_04_mood.py", "ScenePlannerCompositorAgent"),
        ("stage_04_mood.py", "CinematicScriptCuratorAgent"),
        ("stage_09_render.py", "default_render_preset()"),
        ("stage_09_render.py", "stream_copy=stream_copy_mode"),
        ("stage_09_render.py", "include_subtitles=mux_subtitles"),
    ]

    @pytest.mark.parametrize("token", PIPELINE_MANDATORY_TOKENS)
    def test_mandatory_token_present(self, pipeline_code: str, token: str) -> None:
        """Assert each mandatory token appears in src/pipeline.py."""
        assert token in pipeline_code, f"Mandatory token {token!r} missing from src/pipeline.py"

    @pytest.mark.parametrize("stage_file,token", STAGE_MANDATORY_TOKENS)
    def test_stage_mandatory_token_present(self, stage_file: str, token: str) -> None:
        """Assert each mandatory token appears in its corresponding modular stage module."""
        path = REPO_ROOT / "src" / "pipeline" / "stages" / stage_file
        assert path.is_file(), f"Missing stage file: {stage_file}"
        code = path.read_text(encoding="utf-8")
        assert token in code, f"Mandatory token {token!r} missing from {stage_file}"

    def test_coercing_video_engine_token_present(self, pipeline_code: str) -> None:
        """Assert 'Coercing video_engine=' token is present in src/pipeline.py."""
        assert "Coercing video_engine=" in pipeline_code

    def test_stream_copy_mode_ast_assignment(self) -> None:
        """Assert stream_copy_mode = True is an AST Assign node with True constant in stage_08_loop."""
        path = REPO_ROOT / "src" / "pipeline" / "stages" / "stage_08_loop.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "stream_copy_mode":
                        if isinstance(node.value, ast.Constant) and node.value.value is True:
                            found = True
                            break
        assert found, "AST Assignment 'stream_copy_mode = True' not found in stage_08_loop.py"

    def test_is_multiscene_mode_ast_assignment(self, pipeline_ast: ast.Module) -> None:
        """Assert is_multiscene_mode = False is an AST Assign node with False constant."""
        found = False
        for node in ast.walk(pipeline_ast):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "is_multiscene_mode":
                        if isinstance(node.value, ast.Constant) and node.value.value is False:
                            found = True
                            break
        assert found, "AST Assignment 'is_multiscene_mode = False' not found"


# ==============================================================================
# 2. Exact Line Formatting Verification
# ==============================================================================

class TestExactLineFormatting:
    """Stress-test the exact line formatting of 'subtitles_active = False'."""

    def test_subtitles_active_false_on_own_line(self, pipeline_code: str) -> None:
        """Assert 'subtitles_active = False' is on its own line matching regex."""
        # Must match standalone assignment on its own line with indentation
        pattern = re.compile(r"^[ \t]*subtitles_active\s*=\s*False\s*(?:#.*)?$", re.MULTILINE)
        matches = pattern.findall(pipeline_code)
        assert len(matches) >= 1, (
            "Exact line 'subtitles_active = False' not found on its own line in src/pipeline.py"
        )

    def test_subtitles_active_false_ast_assignment(self, pipeline_ast: ast.Module) -> None:
        """Assert AST Assign node target is subtitles_active and value is False."""
        assignments = []
        for node in ast.walk(pipeline_ast):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "subtitles_active":
                        if isinstance(node.value, ast.Constant) and node.value.value is False:
                            assignments.append(node)
        assert len(assignments) >= 1, (
            "AST Assignment 'subtitles_active = False' not found"
        )


# ==============================================================================
# 3. Prohibited String Tokens Verification (Zero Tolerance)
# ==============================================================================

class TestForbiddenStringTokens:
    """Stress-test that prohibited tokens are completely absent from src/pipeline.py."""

    FORBIDDEN_TOKENS = [
        "burn_subtitles",
        'preset="slow"',
        "preset='slow'",
        'current_review_status = "APPROVED"',
        "current_review_status = 'APPROVED'",
        "proceeding as APPROVED",
    ]

    @pytest.mark.parametrize("forbidden", FORBIDDEN_TOKENS)
    def test_forbidden_token_absent(self, pipeline_code: str, forbidden: str) -> None:
        """Assert forbidden token is completely absent from src/pipeline.py."""
        assert forbidden not in pipeline_code, (
            f"FORBIDDEN TOKEN {forbidden!r} found in src/pipeline.py"
        )

    def test_burn_subtitles_case_insensitive_absent(self, pipeline_code: str) -> None:
        """Assert case-insensitive 'burn_subtitles' does not appear anywhere in file."""
        assert "burn_subtitles" not in pipeline_code.lower(), (
            "Case-insensitive 'burn_subtitles' found in src/pipeline.py"
        )

    def test_zero_playwright_in_pipeline(self, pipeline_ast: ast.Module) -> None:
        """Assert zero Playwright or Chromium imports in src/pipeline.py."""
        for node in ast.walk(pipeline_ast):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "playwright" not in alias.name.lower(), f"Playwright import found: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "playwright" not in mod.lower(), f"Playwright from-import found: {mod}"


# ==============================================================================
# 4. Exact Occurrence Count: SceneAssetTracker
# ==============================================================================

class TestSceneAssetTrackerOccurrence:
    """Stress-test exact count of SceneAssetTracker(repository=repository)."""

    def test_exact_count_of_scene_asset_tracker_string(self, pipeline_code: str) -> None:
        """Assert 'SceneAssetTracker(repository=repository)' appears EXACTLY once."""
        needle = "SceneAssetTracker(repository=repository)"
        count = pipeline_code.count(needle)
        assert count == 1, (
            f"Expected exactly 1 occurrence of '{needle}', found {count}"
        )

    def test_scene_asset_tracker_ast_call(self, pipeline_ast: ast.Module) -> None:
        """Assert AST Call to SceneAssetTracker with repository keyword appears exactly once."""
        calls = []
        for node in ast.walk(pipeline_ast):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "SceneAssetTracker":
                    kw_repo = [kw for kw in node.keywords if kw.arg == "repository"]
                    if kw_repo:
                        calls.append(node)
        assert len(calls) == 1, (
            f"Expected exactly 1 AST Call to SceneAssetTracker(repository=...), found {len(calls)}"
        )


# ==============================================================================
# 5. AST Structural Integrity: 13 Stage Helpers
# ==============================================================================

class TestStageHelpersAST:
    """Stress-test AST structure of the 13 canonical private stage helpers."""

    EXPECTED_STAGES = [
        ("01", "_stage_01_claim_lease", "CLAIM_LEASE"),
        ("02", "_stage_02_ingest_translate", "INGEST_TRANSLATE"),
        ("03", "_stage_03_editorial_barrier", "EDITORIAL_BARRIER"),
        ("04", "_stage_04_mood_theme", "MOOD_THEME"),
        ("05", "_stage_05_tts_synthesis", "TTS_SYNTHESIS"),
        ("06", "_stage_06_duration_alignment", "DURATION_ALIGNMENT"),
        ("07", "_stage_07_subtitle_generation", "SUBTITLE_GENERATION"),
        ("08", "_stage_08_loop_scene", "LOOP_SCENE"),
        ("09", "_stage_09_video_rendering", "VIDEO_RENDERING"),
        ("10", "_stage_10_qa_gating", "QA_GATING"),
        ("11", "_stage_11_thumbnail_metadata", "THUMBNAIL_METADATA"),
        ("12", "_stage_12_dedup_simhash", "DEDUP_SIMHASH"),
        ("13", "_stage_13_backup_publish", "BACKUP_PUBLISH"),
    ]

    def test_all_13_stage_helpers_exist(self, pipeline_ast: ast.Module) -> None:
        """Assert all 13 private stage helper functions exist in src/pipeline.py AST."""
        funcs = {
            node.name: node
            for node in ast.walk(pipeline_ast)
            if isinstance(node, ast.FunctionDef)
        }
        for num, fn_name, _ in self.EXPECTED_STAGES:
            assert fn_name in funcs, f"Missing stage helper function: {fn_name}"

    STAGE_MODULE_MAPPING = [
        ("01", "stage_01_lease.py", "CLAIM_LEASE"),
        ("02", "stage_02_ingest.py", "INGEST_TRANSLATE"),
        ("03", "stage_03_editorial.py", "EDITORIAL_BARRIER"),
        ("04", "stage_04_mood.py", "MOOD_THEME"),
        ("05", "stage_05_tts.py", "TTS_SYNTHESIS"),
        ("06", "stage_06_alignment.py", "DURATION_ALIGNMENT"),
        ("07", "stage_07_subtitles.py", "SUBTITLE_GENERATION"),
        ("08", "stage_08_loop.py", "LOOP_SCENE"),
        ("09", "stage_09_render.py", "VIDEO_RENDERING"),
        ("10", "stage_10_qa.py", "QA_GATING"),
        ("11", "stage_11_metadata.py", "THUMBNAIL_METADATA"),
        ("12", "stage_12_simhash.py", "DEDUP_SIMHASH"),
        ("13", "stage_13_publish.py", "BACKUP_PUBLISH"),
    ]

    def test_stage_helpers_canonical_phase_association(self) -> None:
        """Assert each stage module associates with its matching CanonicalStage in stages/."""
        stages_dir = REPO_ROOT / "src" / "pipeline" / "stages"
        for num, mod_name, canonical_attr in self.STAGE_MODULE_MAPPING:
            path = stages_dir / mod_name
            assert path.is_file(), f"Missing stage module: {mod_name}"
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            canon_refs = []
            for n in ast.walk(tree):
                if (
                    isinstance(n, ast.Attribute)
                    and isinstance(n.value, ast.Name)
                    and n.value.id == "CanonicalStage"
                ):
                    canon_refs.append(n.attr)
            assert canonical_attr in canon_refs, (
                f"{mod_name} does not reference CanonicalStage.{canonical_attr}; found: {canon_refs}"
            )

    def test_run_context_parameter_in_stages(self, pipeline_ast: ast.Module) -> None:
        """Assert stages 02 through 13 accept ctx: RunContext as their first parameter."""
        funcs = {
            node.name: node
            for node in ast.walk(pipeline_ast)
            if isinstance(node, ast.FunctionDef)
        }
        for num, fn_name, _ in self.EXPECTED_STAGES:
            if fn_name == "_stage_01_claim_lease":
                continue  # Stage 1 claims the lease before RunContext is constructed
            fn_node = funcs[fn_name]
            args = fn_node.args.args
            assert len(args) >= 1, f"{fn_name} has no parameters"
            assert args[0].arg == "ctx", f"{fn_name} first argument is {args[0].arg}, expected 'ctx'"


# ==============================================================================
# 6. Stage Helper Execution Sequence inside run_pipeline_once
# ==============================================================================

class TestStageExecutionSequence:
    """Stress-test that all 13 stage helpers are invoked in run_pipeline_once."""

    def test_all_13_stages_called_in_run_pipeline_once(self, pipeline_ast: ast.Module) -> None:
        """Assert all 13 stage helpers are called inside run_pipeline_once."""
        funcs = {
            node.name: node
            for node in ast.walk(pipeline_ast)
            if isinstance(node, ast.FunctionDef)
        }
        rpo = funcs["run_pipeline_once"]

        called_stages: list[tuple[int, str]] = []
        for node in ast.walk(rpo):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id.startswith("_stage_")
            ):
                called_stages.append((node.lineno, node.func.id))

        called_stages.sort()
        called_names = [name for _, name in called_stages]

        expected_names = [
            "_stage_01_claim_lease",
            "_stage_02_ingest_translate",
            "_stage_03_editorial_barrier",
            "_stage_05_tts_synthesis",
            "_stage_06_duration_alignment",
            "_stage_07_subtitle_generation",
            "_stage_04_mood_theme",
            "_stage_08_loop_scene",
            "_stage_09_video_rendering",
            "_stage_11_thumbnail_metadata",
            "_stage_12_dedup_simhash",
            "_stage_10_qa_gating",
            "_stage_13_backup_publish",
        ]

        assert called_names == expected_names, (
            f"Mismatch in stage execution sequence.\nExpected: {expected_names}\nActual:   {called_names}"
        )


# ==============================================================================
# 7. Callable Exports Verification
# ==============================================================================

class TestCallableExports:
    """Stress-test that all required public and internal exports exist and are callable."""

    REQUIRED_EXPORTS = [
        "_drive_review_url",
        "_enforce_editorial_compliance",
        "_should_translate",
        "_catalog_shots_from_manifest",
        "is_spanish_neutral",
        "normalize_text",
        "validate_prepublication",
        "is_test_environment",
        "curate_script",
        "run_pipeline_once",
    ]

    @pytest.mark.parametrize("export_name", REQUIRED_EXPORTS)
    def test_export_exists_and_callable(self, export_name: str) -> None:
        """Assert each export is accessible on src.pipeline and is callable."""
        import src.pipeline as pipe
        assert hasattr(pipe, export_name), f"Missing export: {export_name}"
        obj = getattr(pipe, export_name)
        assert callable(obj), f"Export {export_name} is not callable: {type(obj)}"

    def test_run_context_is_dataclass(self) -> None:
        """Assert RunContext is exported and is a valid dataclass."""
        from src.pipeline import RunContext
        import dataclasses
        assert dataclasses.is_dataclass(RunContext), "RunContext is not a dataclass"


# ==============================================================================
# 8. Adversarial Parameter & Edge Case Stress Testing
# ==============================================================================

class TestAdversarialInputsAndEdgeCases:
    """Stress-test edge cases, boundary inputs, and validation gates."""

    def test_directed_run_empty_story_id_raises_value_error(self) -> None:
        """Assert run_pipeline_once raises ValueError when directed=True but story_id is empty."""
        from src.pipeline import run_pipeline_once
        with pytest.raises(ValueError, match="--story-id no puede estar vacío"):
            run_pipeline_once(channel="moku", directed=True, story_id="")

    def test_invalid_video_engine_raises_value_error(self) -> None:
        """Assert unsupported video_engine raises ValueError with supported engines list when lease is active."""
        from src.pipeline import run_pipeline_once
        mock_claimed = {
            "story": {"story_id": "test_inv_engine"},
            "story_id": "test_inv_engine",
            "lane": MagicMock(video_engine="loop"),
            "repository": MagicMock(),
            "database": ":memory:",
            "owner": "test_owner",
            "lease_seconds": 60,
            "settings": MagicMock(),
            "branding": MagicMock(),
        }
        with patch("src.pipeline._stage_01_claim_lease", return_value=(mock_claimed, None)):
            with pytest.raises(ValueError, match="video_engine='unsupported_xyz_engine' is not supported"):
                run_pipeline_once(channel="moku", video_engine="unsupported_xyz_engine")

    def test_director_engine_coerces_to_loop_without_force_multiscene(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Assert director engine is safely coerced to loop when FORCE_MULTISCENE is unset."""
        monkeypatch.delenv("FORCE_MULTISCENE", raising=False)
        from src.pipeline import run_pipeline_once

        # Mock _stage_01_claim_lease to return an early exit immediately so we can observe arguments
        mock_ctx = {
            "story": {"story_id": "test_coercion_123"},
            "story_id": "test_coercion_123",
            "lane": MagicMock(video_engine="director", visual_pipeline="director"),
            "repository": MagicMock(),
            "database": ":memory:",
            "owner": "test_owner",
            "lease_seconds": 60,
            "settings": MagicMock(),
            "branding": MagicMock(),
        }

        with patch("src.pipeline._stage_01_claim_lease", return_value=(mock_ctx, {"status": "EARLY_EXIT_FOR_TEST"})):
            # If coercion fails or raises, this test will fail
            res = run_pipeline_once(channel="moku", video_engine="director")
            assert res == {"status": "EARLY_EXIT_FOR_TEST"}

    def test_subtitles_active_flag_behavior(self) -> None:
        """Assert enable_subtitles properly controls subtitles_active in RunContext."""
        from src.pipeline import run_pipeline_once

        captured_ctx: list[Any] = []

        mock_claimed = {
            "story": {"story_id": "test_sub_story"},
            "story_id": "test_sub_story",
            "lane": MagicMock(video_engine="loop"),
            "repository": MagicMock(),
            "database": ":memory:",
            "owner": "test_owner",
            "lease_seconds": 60,
            "settings": MagicMock(),
            "branding": MagicMock(),
        }

        def mock_stage_02(ctx: Any) -> None:
            captured_ctx.append(ctx)
            raise StopIteration("Intercepted RunContext")

        with patch("src.pipeline._stage_01_claim_lease", return_value=(mock_claimed, None)):
            with patch("src.pipeline._stage_02_ingest_translate", side_effect=mock_stage_02):
                with patch("src.pipeline._marker"):
                    # 1. Default enable_subtitles=None -> subtitles_active must be False
                    captured_ctx.clear()
                    try:
                        run_pipeline_once(channel="moku", enable_subtitles=None)
                    except StopIteration:
                        pass
                    assert len(captured_ctx) == 1
                    assert captured_ctx[0].subtitles_active is False

                    # 2. Explicit enable_subtitles=True -> subtitles_active must be True
                    captured_ctx.clear()
                    try:
                        run_pipeline_once(channel="moku", enable_subtitles=True)
                    except StopIteration:
                        pass
                    assert len(captured_ctx) == 1
                    assert captured_ctx[0].subtitles_active is True

                    # 3. Explicit enable_subtitles=False -> subtitles_active must be False
                    captured_ctx.clear()
                    try:
                        run_pipeline_once(channel="moku", enable_subtitles=False)
                    except StopIteration:
                        pass
                    assert len(captured_ctx) == 1
                    assert captured_ctx[0].subtitles_active is False

    def test_catalog_shots_from_manifest_robustness(self) -> None:
        """Assert _catalog_shots_from_manifest handles empty and valid manifests."""
        from src.pipeline import _catalog_shots_from_manifest

        mock_loop_engine = MagicMock()
        mock_loop_engine.resolve_loop_video.return_value = "/path/to/loop.mp4"

        # None / empty manifest returns empty lists
        paths, durs, cat = _catalog_shots_from_manifest({}, mock_loop_engine, "vertical")
        assert paths == []
        assert durs == []

        # Empty scenes list
        paths, durs, cat = _catalog_shots_from_manifest({"scenes": []}, mock_loop_engine, "vertical")
        assert paths == []
        assert durs == []

        # Valid scenes with duration
        manifest = {
            "scenes": [
                {"duration_sec": 4.5, "category": "dark_ambient"},
                {"duration_sec": 6.0, "category": "horror"},
            ]
        }
        paths, durs, cat = _catalog_shots_from_manifest(manifest, mock_loop_engine, "vertical")
        assert len(paths) == 2
        assert len(durs) == 2
        assert durs == [4.5, 6.0]

    def test_catalog_shots_from_manifest_non_dict_fragility(self) -> None:
        """Empirically prove that non-dict items in scenes cause AttributeError at line 221."""
        from src.pipeline import _catalog_shots_from_manifest

        mock_loop_engine = MagicMock()
        mock_loop_engine.resolve_loop_video.return_value = "/path/to/loop.mp4"

        # When scenes contains a usable scene AND a non-dict item:
        manifest_with_mixed_scenes = {
            "scenes": [
                {"duration_sec": 4.5, "category": "dark_ambient"},
                "malformed_string_scene",
            ]
        }
        with pytest.raises(AttributeError, match="'str' object has no attribute 'get'"):
            _catalog_shots_from_manifest(manifest_with_mixed_scenes, mock_loop_engine, "vertical")

    def test_drive_review_url_handling(self) -> None:
        """Assert _drive_review_url validates DriveProof and builds correct URL."""
        from src.pipeline import _drive_review_url
        from src.drive import DriveProof

        # Non-verified or empty proof raises ValueError
        proof_unverified = DriveProof(file_id="", name="t.mp4", size_bytes=0, folder_id="f", exists=False)
        with pytest.raises(ValueError, match="Drive proof is not verified"):
            _drive_review_url(proof_unverified)

        proof_empty_id = DriveProof(file_id="   ", name="t.mp4", size_bytes=0, folder_id="f", exists=True)
        with pytest.raises(ValueError, match="Drive proof is not verified"):
            _drive_review_url(proof_empty_id)

        # Verified proof builds valid URL
        proof_valid = DriveProof(file_id="1ABCxyz", name="t.mp4", size_bytes=100, folder_id="f", exists=True)
        url = _drive_review_url(proof_valid)
        assert url == "https://drive.google.com/file/d/1ABCxyz/view"

    def test_should_translate_handling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Assert _should_translate honors Spanish neutral detection (>= 20 words) and ALWAYS_TRANSLATE."""
        from src.pipeline import _should_translate

        monkeypatch.delenv("ALWAYS_TRANSLATE", raising=False)

        # Spanish script with >= 20 words conforming to Spanish neutral markers
        spanish_script = (
            "En las profundidades del bosque oscuro, nadie escuchó el eco de los pasos silenciosos que se acercaban lentamente "
            "hacia la vieja cabaña abandonada en medio de la noche fría y sombría."
        )
        assert _should_translate(spanish_script) is False

        # English script with >= 20 words
        english_script = (
            "In the dark depths of the ancient haunted forest, nobody heard the silent creeping steps approaching slowly "
            "towards the abandoned cabin in the middle of the freezing and quiet night."
        )
        assert _should_translate(english_script) is True

        # ALWAYS_TRANSLATE=1 forces translation even for Spanish
        monkeypatch.setenv("ALWAYS_TRANSLATE", "1")
        assert _should_translate(spanish_script) is True


