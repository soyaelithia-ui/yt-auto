"""Anti-regression: native_procedural/wgpu stay quarantined under src.media._legacy."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MEDIA_DIR = REPO_ROOT / "src" / "media"
LEGACY_DIR = MEDIA_DIR / "_legacy"
PROD_HOT_PATH = [
    MEDIA_DIR / "compositor.py",
    MEDIA_DIR / "loop_worker.py",
    MEDIA_DIR / "hybrid_engine.py",
    MEDIA_DIR / "proc_engine.py",
    MEDIA_DIR / "multi_act_renderer.py",
    REPO_ROOT / "src" / "pipeline.py",
]


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


def test_legacy_quarantine_layout_exists():
    assert (LEGACY_DIR / "native_procedural.py").is_file()
    assert (LEGACY_DIR / "shaders").is_dir()
    assert (LEGACY_DIR / "README.md").is_file()
    assert any((LEGACY_DIR / "shaders").glob("*.wgsl"))


def test_production_shaders_path_removed():
    assert not (MEDIA_DIR / "shaders").exists(), (
        "src/media/shaders must remain quarantined under src/media/_legacy/shaders"
    )


def test_shim_exists_and_is_deprecated():
    shim = (MEDIA_DIR / "native_procedural.py").read_text(encoding="utf-8")
    assert "DEPRECATED" in shim
    assert "_legacy" in shim
    assert "_guard_production_import" in shim


def test_hot_path_modules_have_no_module_level_native_or_wgpu_imports():
    forbidden_prefixes = (
        "wgpu",
        "src.media.native_procedural",
        "src.media._legacy.native_procedural",
        "src.media._legacy",
    )
    violations: list[str] = []
    for path in PROD_HOT_PATH:
        if not path.is_file():
            continue
        for imp in _module_level_imports(path):
            if any(imp == p or imp.startswith(p + ".") for p in forbidden_prefixes):
                violations.append(f"{path.relative_to(REPO_ROOT)} top-level imports {imp!r}")
    assert not violations, "hot-path top-level wgpu/native imports:\n" + "\n".join(violations)


def test_enable_native_procedural_defaults_off(monkeypatch):
    monkeypatch.delenv("ENABLE_NATIVE_PROCEDURAL", raising=False)
    for key in list(sys.modules):
        if key == "src.media.compositor" or key.startswith("src.media.compositor."):
            del sys.modules[key]
    from src.media.compositor import _native_procedural_hot_path_enabled

    assert _native_procedural_hot_path_enabled() is False
    monkeypatch.setenv("ENABLE_NATIVE_PROCEDURAL", "0")
    assert _native_procedural_hot_path_enabled() is False


def test_compositor_default_does_not_load_legacy_or_wgpu(monkeypatch):
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
        if key in ("src.media.compositor", "src.media.proc_engine", "src.media.hybrid_engine"):
            del sys.modules[key]

    from src.media.compositor import MultiSceneCompositor

    compositor = MultiSceneCompositor()
    assert compositor.procedural_engine.renderer is None
    assert "src.media.native_procedural" not in sys.modules
    assert "src.media._legacy.native_procedural" not in sys.modules
    assert "wgpu" not in sys.modules


def test_shim_guard_blocks_fake_compositor_import(monkeypatch):
    monkeypatch.delenv("ENABLE_NATIVE_PROCEDURAL", raising=False)
    for key in list(sys.modules):
        if key == "src.media.native_procedural" or key.startswith("src.media.native_procedural."):
            del sys.modules[key]
        if key == "src.media._legacy.native_procedural" or key.startswith(
            "src.media._legacy.native_procedural."
        ):
            del sys.modules[key]

    ns: dict = {"__name__": "src.media.compositor"}
    with pytest.raises(RuntimeError, match="quarantined|ENABLE_NATIVE_PROCEDURAL"):
        exec(
            compile(
                "from src.media.native_procedural import VALID_ARCHETYPES",
                "src/media/compositor.py",
                "exec",
            ),
            ns,
        )


def test_shim_allows_import_with_opt_in(monkeypatch):
    monkeypatch.setenv("ENABLE_NATIVE_PROCEDURAL", "1")
    for key in list(sys.modules):
        if key == "src.media.native_procedural" or key.startswith("src.media.native_procedural."):
            del sys.modules[key]
    ns: dict = {"__name__": "src.media.compositor"}
    with pytest.warns(DeprecationWarning):
        exec(
            compile(
                "from src.media.native_procedural import VALID_ARCHETYPES",
                "src/media/compositor.py",
                "exec",
            ),
            ns,
        )
    assert "dark_forest" in ns["VALID_ARCHETYPES"]


def test_user_facing_docs_do_not_pitch_native_as_active_ssot():
    for rel in ("README.md", "PROJECT.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8").lower()
        if "native_procedural" in text or "wgpu" in text:
            assert (
                "quarantine" in text
                or "quarantined" in text
                or "_legacy" in text
                or "not ssot" in text
                or "no ssot" in text
            ), f"{rel} still presents wgpu/native without quarantine framing"
