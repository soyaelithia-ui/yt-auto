"""Adversarial stress test for Challenge 4: Schema Validation Across All Schemas."""
import json
from pathlib import Path
import pytest
import jsonschema
from jsonschema import Draft7Validator, validate, ValidationError

SCHEMAS_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"

def get_all_schema_paths():
    files = list(SCHEMAS_DIR.glob("*.schema.json"))
    assert len(files) >= 8, f"Expected at least 8 schemas in {SCHEMAS_DIR}, found {len(files)}"
    return files

def test_all_schemas_are_valid_draft7():
    """Verify that every single .schema.json in schemas/ is a strictly valid Draft-07 JSON Schema."""
    schema_paths = get_all_schema_paths()
    for sp in schema_paths:
        with open(sp, "r", encoding="utf-8") as f:
            data = json.load(f)
        Draft7Validator.check_schema(data)
        assert data.get("$schema") == "http://json-schema.org/draft-07/schema#", f"{sp.name} missing draft-07 $schema"

# ---------------------------------------------------------------------------
# 1. SEO Metadata Schema (seo_metadata.schema.json)
# ---------------------------------------------------------------------------
def test_seo_metadata_schema_valid_and_adversarial():
    with open(SCHEMAS_DIR / "seo_metadata.schema.json", "r") as f:
        schema = json.load(f)

    valid_payload = {
        "version": "2.0",
        "topic": "El Faro Olvidado",
        "target_format": "longform",
        "viral_title_options": [
            "El Misterio del Faro Olvidado",
            "Lo Que el Faro Ocultaba en la Niebla",
            "Nunca Visites Este Faro de Noche"
        ],
        "selected_title": "El Misterio del Faro Olvidado",
        "description": "Una expedición solitaria revela secretos oscuros en las profundidades del océano.",
        "tags": ["terror", "moku", "creepy", "misterio", "oceano"],
        "hashtags": ["#Terror", "#Misterio"],
        "pinned_comment": "¿Te atreverías a pasar una noche en este faro?",
        "thumbnail_concepts": [
            {
                "visual_layout": "Faro a contraluz con sombras gigantes",
                "big_headline": "NO ENTRES",
                "color_palette": ["#0B0B10", "#3A6D7C"]
            }
        ]
    }
    validate(instance=valid_payload, schema=schema)

    # Negative 1: fewer than 3 viral title options
    invalid_payload = json.loads(json.dumps(valid_payload))
    invalid_payload["viral_title_options"] = ["Uno solo"]
    with pytest.raises(ValidationError):
        validate(instance=invalid_payload, schema=schema)

    # Negative 2: invalid hashtag pattern (missing #)
    invalid_payload2 = json.loads(json.dumps(valid_payload))
    invalid_payload2["hashtags"] = ["Terror", "Misterio"]
    with pytest.raises(ValidationError):
        validate(instance=invalid_payload2, schema=schema)

    # Negative 3: target_format invalid enum
    invalid_payload3 = json.loads(json.dumps(valid_payload))
    invalid_payload3["target_format"] = "cinematic_4k"
    with pytest.raises(ValidationError):
        validate(instance=invalid_payload3, schema=schema)

# ---------------------------------------------------------------------------
# 2. Image Auditor Schema (image_auditor.schema.json)
# ---------------------------------------------------------------------------
def test_image_auditor_schema_valid_and_adversarial():
    with open(SCHEMAS_DIR / "image_auditor.schema.json", "r") as f:
        schema = json.load(f)

    valid_payload = {
        "version": "2.0",
        "topic": "SCP-173",
        "channel_lane": "moku-scp-shorts",
        "total_candidates": 2,
        "approved_count": 1,
        "discarded_count": 1,
        "verdicts": [
            {
                "asset_id": "asset_001",
                "source_type": "official_emblem",
                "entity_name": "SCP Foundation",
                "verdict": "APPROVED_REFERENCE",
                "confidence_score": 0.95,
                "reasoning": "Official SCP vector logo conforms to brand rules.",
                "badge_render_type": "svg_vector_badge"
            },
            {
                "asset_id": "asset_002",
                "source_type": "generic_filler_photo",
                "entity_name": "Random Concrete Wall",
                "verdict": "DISCARDED_GENERIC_FILLER",
                "confidence_score": 0.88,
                "reasoning": "Unbranded filler photo lacking narrative tension.",
                "badge_render_type": "none"
            }
        ]
    }
    validate(instance=valid_payload, schema=schema)

    # Negative 1: confidence score > 1.0
    invalid_payload = json.loads(json.dumps(valid_payload))
    invalid_payload["verdicts"][0]["confidence_score"] = 1.5
    with pytest.raises(ValidationError):
        validate(instance=invalid_payload, schema=schema)

    # Negative 2: invalid source_type enum
    invalid_payload2 = json.loads(json.dumps(valid_payload))
    invalid_payload2["verdicts"][0]["source_type"] = "stock_shutterstock"
    with pytest.raises(ValidationError):
        validate(instance=invalid_payload2, schema=schema)

# ---------------------------------------------------------------------------
# 3. Channel Profile Schema (channel_profile.schema.json)
# ---------------------------------------------------------------------------
def test_channel_profile_schema_valid_and_adversarial():
    with open(SCHEMAS_DIR / "channel_profile.schema.json", "r") as f:
        schema = json.load(f)

    valid_payload = {
        "id": "moku_horror",
        "enabled": True,
        "editorial": {
            "public_name": "Moku Historias de Terror",
            "handle": "@mokuhorror",
            "topic": "Horror & SCP stories",
            "tone": "Dark documentary suspense",
            "channel_url": "https://youtube.com/@mokuhorror",
            "persona_system_prompt": "Eres un narrador documental siniestro."
        },
        "visual": {
            "style_id": "dark_cinematic",
            "palette": {
                "primary": "#0B0B10",
                "secondary": "#1C1028",
                "accent": "#12282D",
                "shadow": "#050508",
                "highlight": "#3A6D7C"
            }
        },
        "audio": {
            "default_voice_profile": "es-ES-AlvaroNeural"
        },
        "auth": {
            "expected_youtube_channel_id": "UC1234567890",
            "source_feed": "reddit_nosleep"
        }
    }
    validate(instance=valid_payload, schema=schema)

    # Negative 1: invalid channel id pattern (contains spaces/uppercase)
    invalid_payload = json.loads(json.dumps(valid_payload))
    invalid_payload["id"] = "Moku Horror Channel!"
    with pytest.raises(ValidationError):
        validate(instance=invalid_payload, schema=schema)

    # Negative 2: missing required editorial.tone
    invalid_payload2 = json.loads(json.dumps(valid_payload))
    del invalid_payload2["editorial"]["tone"]
    with pytest.raises(ValidationError):
        validate(instance=invalid_payload2, schema=schema)

    # Negative 3: enabled not boolean
    invalid_payload3 = json.loads(json.dumps(valid_payload))
    invalid_payload3["enabled"] = "true"
    with pytest.raises(ValidationError):
        validate(instance=invalid_payload3, schema=schema)

# ---------------------------------------------------------------------------
# 4. Scene Manifest V2 Schema (scene_manifest.schema.json)
# ---------------------------------------------------------------------------
def test_scene_manifest_v2_schema_valid_and_adversarial():
    with open(SCHEMAS_DIR / "scene_manifest.schema.json", "r") as f:
        schema = json.load(f)

    valid_payload = {
        "manifest_version": "2.0",
        "story_id": "story_001",
        "lane_id": "moku-horror-long",
        "channel_name": "moku",
        "resolution": [1920, 1080],
        "fps": 30,
        "total_duration_sec": 45.0,
        "audio_tracks": {
            "narration_path": "data/worksets/run_001/narration.wav",
            "music_path": "assets/music/track1.mp3",
            "music_volume": 0.15
        },
        "safe_area": {
            "margin_top": 120,
            "margin_bottom": 120,
            "margin_left": 80,
            "margin_right": 80
        },
        "scenes": [
            {
                "scene_index": 1,
                "scene_id": "scene_001",
                "start_sec": 0.0,
                "duration_sec": 45.0,
                "tension_level": 2,
                "engine_type": "hybrid_cinematic_ai",
                "hybrid_ai_config": {
                    "background_image_path": "data/worksets/run_001/scene_001.png"
                },
                "transition_out": {
                    "type": "crossfade",
                    "duration_sec": 1.0
                }
            }
        ],
        "subtitles": [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "La noche era densa y fría."
            }
        ]
    }
    validate(instance=valid_payload, schema=schema)

    # Negative 1: invalid fps enum
    invalid_payload = json.loads(json.dumps(valid_payload))
    invalid_payload["fps"] = 144
    with pytest.raises(ValidationError):
        validate(instance=invalid_payload, schema=schema)

    # Negative 2: resolution items < 640
    invalid_payload2 = json.loads(json.dumps(valid_payload))
    invalid_payload2["resolution"] = [320, 240]
    with pytest.raises(ValidationError):
        validate(instance=invalid_payload2, schema=schema)

    # Negative 3: invalid engine_type enum
    invalid_payload3 = json.loads(json.dumps(valid_payload))
    invalid_payload3["scenes"][0]["engine_type"] = "unreal_engine"
    with pytest.raises(ValidationError):
        validate(instance=invalid_payload3, schema=schema)

if __name__ == "__main__":
    pytest.main(["-v", __file__])
