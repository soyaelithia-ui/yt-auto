"""
tests/unit/test_visual_integrity.py - Unit tests for VisualIntegrityVerifier.
"""
import math
import pytest
from pathlib import Path
from PIL import Image, ImageDraw

from src.visual_integrity import VisualIntegrityVerifier


def test_visual_integrity_normal_image():
    verifier = VisualIntegrityVerifier()
    # Create image with high contrast and geometric patterns
    img = Image.new("RGB", (200, 200), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i in range(0, 200, 10):
        draw.line([(0, i), (200, 200 - i)], fill=(255, 255, 255), width=2)

    metrics = verifier.analyze_frame_roi(img)
    assert "entropy" in metrics
    assert "edge_density" in metrics
    assert metrics["entropy"] > 0.0
    assert metrics["edge_density"] > 0.0
    assert not math.isnan(metrics["entropy"])
    assert not math.isnan(metrics["edge_density"])


def test_visual_integrity_solid_black():
    verifier = VisualIntegrityVerifier()
    img = Image.new("RGB", (100, 100), (0, 0, 0))
    metrics = verifier.analyze_frame_roi(img)
    assert metrics["entropy"] == 0.0
    assert metrics["edge_density"] == 0.0


def test_visual_integrity_solid_white():
    verifier = VisualIntegrityVerifier()
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    metrics = verifier.analyze_frame_roi(img)
    assert metrics["entropy"] == 0.0
    assert 0.0 <= metrics["edge_density"] < 15.0


def test_visual_integrity_none_input():
    verifier = VisualIntegrityVerifier()
    metrics = verifier.analyze_frame_roi(None)
    assert metrics == {"entropy": 0.0, "edge_density": 0.0}


def test_visual_integrity_empty_image():
    verifier = VisualIntegrityVerifier()
    img = Image.new("RGB", (0, 0))
    metrics = verifier.analyze_frame_roi(img)
    assert metrics == {"entropy": 0.0, "edge_density": 0.0}


def test_visual_integrity_extract_frames_invalid_paths(tmp_path: Path):
    verifier = VisualIntegrityVerifier()
    # None video path
    assert verifier.extract_frames(None, tmp_path) == []

    # None or empty output_dir
    valid_stub = tmp_path / "valid_stub.mp4"
    valid_stub.write_bytes(b"dummy")
    assert verifier.extract_frames(valid_stub, None) == []
    assert verifier.extract_frames(valid_stub, "") == []

    # Non-existent path
    assert verifier.extract_frames(tmp_path / "nonexistent.mp4", tmp_path) == []

    # 0-byte file
    zero_file = tmp_path / "empty.mp4"
    zero_file.write_bytes(b"")
    assert verifier.extract_frames(zero_file, tmp_path) == []


def test_visual_integrity_non_image_input():
    verifier = VisualIntegrityVerifier()
    # Pass unexpected types to ensure exception containment
    assert verifier.analyze_frame_roi("not_an_image") == {"entropy": 0.0, "edge_density": 0.0}
    assert verifier.analyze_frame_roi(12345) == {"entropy": 0.0, "edge_density": 0.0}
    assert verifier.analyze_frame_roi({"image": "none"}) == {"entropy": 0.0, "edge_density": 0.0}

