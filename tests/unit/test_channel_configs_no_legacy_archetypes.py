"""Tests verifying channel configurations contain zero legacy archetypes, HTML, or WGSL."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHANNELS_DIR = REPO_ROOT / "config" / "channels"

PURGED_WGSL_SHADERS = {
    "arcade_vector_flight",
    "arctic_desolation",
    "cosmic_singularity",
    "cozy_hearth",
    "maritime_lighthouse",
    "parkour_runner",
    "synaptic_network",
}


def test_channel_configs_exist():
    """Verify that config/channels contains json files."""
    assert CHANNELS_DIR.is_dir()
    channel_files = list(CHANNELS_DIR.glob("*.json"))
    assert len(channel_files) >= 3, f"Expected at least 3 channel configs, found {len(channel_files)}"


def test_channel_configs_valid_json_and_no_legacy_references():
    """Verify all channel configs are valid JSON with 0 .html templates and 0 purged WGSL shader names."""
    channel_files = list(CHANNELS_DIR.glob("*.json"))
    violations = []

    for cfile in channel_files:
        text = cfile.read_text(encoding="utf-8")
        rel_path = cfile.relative_to(REPO_ROOT)

        # 1. Must parse cleanly
        try:
            data = json.loads(text)
        except Exception as e:
            violations.append(f"{rel_path}: Invalid JSON - {e}")
            continue

        # 2. Check entire JSON string for .html
        if ".html" in text.lower():
            violations.append(f"{rel_path}: Contains legacy '.html' reference")

        # 3. Check entire JSON string for purged shader names
        for shader in PURGED_WGSL_SHADERS:
            if shader in text:
                violations.append(f"{rel_path}: Contains purged WGSL shader name '{shader}'")

        # 4. Check for pure_procedural_webgl or procedural engine types
        if "pure_procedural_webgl" in text or "procedural_config" in text:
            violations.append(f"{rel_path}: Contains legacy procedural engine configuration")

    assert not violations, f"Channel config governance violations found:\n" + "\n".join(violations)


def test_channel_configs_have_valid_editorial_structure():
    """Verify each channel config defines expected editorial and visual structure."""
    channel_files = list(CHANNELS_DIR.glob("*.json"))
    required_keys = {"id", "enabled", "editorial", "visual", "audio"}

    for cfile in channel_files:
        data = json.loads(cfile.read_text(encoding="utf-8"))
        assert required_keys.issubset(data.keys()), f"{cfile.name} missing required keys"
        assert isinstance(data["editorial"], dict), f"{cfile.name} 'editorial' must be a dict"
        assert isinstance(data["visual"], dict), f"{cfile.name} 'visual' must be a dict"
        assert isinstance(data["audio"], dict), f"{cfile.name} 'audio' must be a dict"
