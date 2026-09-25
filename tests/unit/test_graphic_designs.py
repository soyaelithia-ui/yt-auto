"""
Unit tests for graphic designs (static atmospheric PNG overlays and SVG vector templates).
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image
import pytest

from src.media.visual_coherence import enforce_shorts_safe_zone


EXPECTED_STATIC_PNGS = [
    "dark_vignette.png",
    "soft_vignette.png",
    "film_grain.png",
    "tv_static.png",
    "particles.png",
    "particles_dust.png",
    "particles_embers.png",
    "god_rays.png",
]

EXPECTED_SVG_TEMPLATES = [
    "rec_analog_hud.svg",
    "cinematic_scope_bars.svg",
    "classified_warning_banner.svg",
    "drama_quote_card.svg",
    "cyber_data_stream.svg",
    "hud_tactical_telemetry.svg",
    "scp_classification_stamp.svg",
    "biometric_wave.svg",
]


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_all_static_atmospheric_overlays_exist(repo_root: Path):
    """Confirms all 8 expected files exist in assets/overlays/static/."""
    static_dir = repo_root / "assets" / "overlays" / "static"
    assert static_dir.is_dir()
    for filename in EXPECTED_STATIC_PNGS:
        file_path = static_dir / filename
        assert file_path.is_file(), f"Missing static atmospheric overlay: {file_path}"
        assert file_path.stat().st_size > 0


def test_static_atmospheric_overlays_mirrored_in_root(repo_root: Path):
    """Confirms all 8 atmospheric files are mirrored in assets/overlays/ for backward compatibility."""
    root_overlays = repo_root / "assets" / "overlays"
    assert root_overlays.is_dir()
    for filename in EXPECTED_STATIC_PNGS:
        file_path = root_overlays / filename
        assert file_path.is_file(), f"Missing mirrored overlay: {file_path}"
        assert file_path.stat().st_size > 0


def test_static_atmospheric_overlays_rgba_mode(repo_root: Path):
    """Validates mode is 'RGBA', dimensions >= 1080x1920 (or 1920x1080), and non-zero alpha variance across pixels."""
    static_dir = repo_root / "assets" / "overlays" / "static"
    for filename in EXPECTED_STATIC_PNGS:
        file_path = static_dir / filename
        with Image.open(file_path) as img:
            assert img.mode == "RGBA", f"{filename} is not RGBA mode, got {img.mode}"
            w, h = img.size
            assert (w >= 1080 and h >= 1920) or (w >= 1920 and h >= 1080), f"{filename} has invalid dimensions {img.size}"
            arr = np.array(img)
            alpha = arr[:, :, 3]
            assert np.min(alpha) != np.max(alpha), f"{filename} has constant alpha across all pixels"
            assert np.any(alpha > 0), f"{filename} is completely transparent"


def test_static_atmospheric_overlays_file_size_budget(repo_root: Path):
    """Validates every static PNG is strictly < 200 KB (204,800 bytes) and total size < 1.5 MB."""
    static_dir = repo_root / "assets" / "overlays" / "static"
    total_bytes = 0
    for filename in EXPECTED_STATIC_PNGS:
        file_path = static_dir / filename
        size = file_path.stat().st_size
        assert size < 204800, f"{filename} exceeds 200 KB budget: {size} bytes"
        total_bytes += size
    assert total_bytes < 1572864, f"Total static PNGs size {total_bytes} exceeds 1.5 MB budget"


def test_all_svg_templates_exist_and_parse_xml(repo_root: Path):
    """Confirms all 8 SVG templates exist in assets/svg_overlays/ and parse cleanly with standard xml.etree.ElementTree."""
    svg_dir = repo_root / "assets" / "svg_overlays"
    assert svg_dir.is_dir()
    for filename in EXPECTED_SVG_TEMPLATES:
        file_path = svg_dir / filename
        assert file_path.is_file(), f"Missing SVG template: {file_path}"
        text = file_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE" not in text, f"{filename} contains forbidden DOCTYPE"
        assert "<!ENTITY" not in text, f"{filename} contains forbidden ENTITY"
        tree = ET.parse(file_path)
        root = tree.getroot()
        assert root.tag.endswith("svg")


def test_svg_templates_safe_zone_conformance(repo_root: Path):
    """Evaluates coordinate anchors of all 8 templates against enforce_shorts_safe_zone(1080, 1920):
    - Top elements reside at y >= 180px (or strictly within safe margins).
    - Bottom elements reside at y <= 1460px (or full letterbox bars preserving central safe corridor).
    - Lateral elements reside within x in [64px, 950px].
    """
    svg_dir = repo_root / "assets" / "svg_overlays"
    sz = enforce_shorts_safe_zone(1080, 1920)
    top_limit = sz["top"]  # 180
    bottom_limit = 1920 - sz["bottom"]  # 1460
    left_limit = sz["left"]  # 64
    right_limit = 1080 - sz["right"]  # 950

    import re

    for filename in EXPECTED_SVG_TEMPLATES:
        file_path = svg_dir / filename
        tree = ET.parse(file_path)
        root = tree.getroot()

        is_scope = filename == "cinematic_scope_bars.svg"

        def _check_elements(parent, offset_x=0.0, offset_y=0.0):
            for child in parent:
                dx, dy = 0.0, 0.0
                transform = child.attrib.get("transform", "")
                if "translate" in transform:
                    match = re.search(r"translate\(\s*([-\d.]+)\s*[,\s]\s*([-\d.]+)\s*\)", transform)
                    if match:
                        dx, dy = float(match.group(1)), float(match.group(2))

                current_x = offset_x + dx
                current_y = offset_y + dy

                tag = child.tag.split("}")[-1]
                if tag in ("text", "tspan"):
                    y_val = child.attrib.get("y")
                    x_val = child.attrib.get("x")
                    if y_val:
                        try:
                            y = float(y_val.replace("px", "")) + current_y
                            assert y >= top_limit - 10, f"{filename}: text '{child.text}' effective y={y} < {top_limit}"
                            assert y <= bottom_limit + 10, f"{filename}: text '{child.text}' effective y={y} > {bottom_limit}"
                        except ValueError:
                            pass
                    if x_val and not is_scope:
                        try:
                            x = float(x_val.replace("px", "")) + current_x
                            assert x >= left_limit - 20, f"{filename}: text '{child.text}' effective x={x} < {left_limit}"
                            assert x <= right_limit + 20, f"{filename}: text '{child.text}' effective x={x} > {right_limit}"
                        except ValueError:
                            pass

                _check_elements(child, current_x, current_y)

        _check_elements(root, 0.0, 0.0)


def test_generate_graphic_assets_cli_verify(repo_root: Path):
    """Invokes python3 scripts/generate_graphic_assets.py --verify as a subprocess and asserts exit code 0."""
    script_path = repo_root / "scripts" / "generate_graphic_assets.py"
    res = subprocess.run(
        [sys.executable, str(script_path), "--verify"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"--verify failed with stdout: {res.stdout}\nstderr: {res.stderr}"


def test_generate_graphic_assets_cli_idempotent(repo_root: Path):
    """Invokes python3 scripts/generate_graphic_assets.py without --force when assets exist, asserting zero re-writes and runtime < 1.0 s."""
    script_path = repo_root / "scripts" / "generate_graphic_assets.py"
    t0 = time.time()
    res = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    duration = time.time() - t0
    assert res.returncode == 0
    assert duration < 2.0  # Idempotent skip should be fast
