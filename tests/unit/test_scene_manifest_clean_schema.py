"""Tests verifying clean scene manifest schema and validation.

Enforces:
1. Rejection of legacy procedural fields: 'procedural_config', 'uniforms'.
2. Rejection of retired engine types (e.g., 'pure_procedural_webgl').
3. Strict enforcement of allowed engine types: 'catalog_loop', 'static_matte', 'hybrid_cinematic_ai'.
4. Consistent behavior between Draft-07 JSON Schema and Pydantic v2 models.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from jsonschema import Draft7Validator, ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError

from src.scene_manifest import (
    SceneManifestV2,
    SceneConfig,
    validate_scene_manifest,
    parse_scene_manifest_model,
    SCHEMA_FILE_PATH,
)


@pytest.fixture
def base_manifest_dict():
    return {
        "manifest_version": "2.0",
        "story_id": "test_clean_schema_001",
        "lane_id": "moku",
        "channel_name": "moku",
        "resolution": [1080, 1920],
        "safe_area": {
            "margin_top": 100,
            "margin_bottom": 100,
            "margin_left": 50,
            "margin_right": 50,
        },
        "fps": 30,
        "total_duration_sec": 4.0,
        "audio_tracks": {
            "narration_path": "audio/narration.mp3",
        },
        "scenes": [
            {
                "scene_index": 1,
                "scene_id": "sc_001",
                "engine_type": "catalog_loop",
                "start_sec": 0.0,
                "duration_sec": 4.0,
                "tension_level": 2,
                "environment_name": "dark_forest",
            }
        ],
    }


def test_schema_file_exists_and_loads():
    """Verify that schemas/scene_manifest.schema.json exists and is valid JSON."""
    assert SCHEMA_FILE_PATH.is_file()
    schema_data = json.loads(SCHEMA_FILE_PATH.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema_data)


def test_valid_manifest_passes_schema_and_pydantic(base_manifest_dict):
    """A clean manifest with catalog_loop passes both schema and Pydantic validation."""
    schema_data = json.loads(SCHEMA_FILE_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema_data)
    validator.validate(base_manifest_dict)

    model = SceneManifestV2.model_validate(base_manifest_dict)
    assert model.scenes[0].engine_type == "catalog_loop"
    assert validate_scene_manifest(base_manifest_dict) is True


@pytest.mark.parametrize("forbidden_engine", [
    "pure_procedural_webgl",
    "procedural",
    "webgpu",
    "canvas2d",
    "software_pillow",
])
def test_schema_and_pydantic_reject_legacy_engines(base_manifest_dict, forbidden_engine):
    """Engine types outside of catalog_loop/static_matte/hybrid_cinematic_ai must be rejected."""
    base_manifest_dict["scenes"][0]["engine_type"] = forbidden_engine
    schema_data = json.loads(SCHEMA_FILE_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema_data)

    with pytest.raises(JsonSchemaValidationError):
        validator.validate(base_manifest_dict)

    with pytest.raises(PydanticValidationError):
        SceneManifestV2.model_validate(base_manifest_dict)


def test_schema_and_pydantic_reject_procedural_config(base_manifest_dict):
    """Manifests with 'procedural_config' must fail validation."""
    base_manifest_dict["scenes"][0]["procedural_config"] = {
        "template_name": "arctic_desolation",
        "parameters": {"speed": 1.0},
    }
    schema_data = json.loads(SCHEMA_FILE_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema_data)

    with pytest.raises(JsonSchemaValidationError):
        validator.validate(base_manifest_dict)

    with pytest.raises(PydanticValidationError):
        SceneManifestV2.model_validate(base_manifest_dict)


def test_schema_and_pydantic_reject_uniforms(base_manifest_dict):
    """Manifests with 'uniforms' must fail validation."""
    base_manifest_dict["scenes"][0]["uniforms"] = {
        "u_speed": 1.5,
        "u_intensity": 0.8,
    }
    schema_data = json.loads(SCHEMA_FILE_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema_data)

    with pytest.raises(JsonSchemaValidationError):
        validator.validate(base_manifest_dict)

    with pytest.raises(PydanticValidationError):
        SceneManifestV2.model_validate(base_manifest_dict)
