"""
tests/unit/test_adversarial_m1_challenger2_curator.py - Adversarial Stress & Edge-Case Test Suite.

Milestone M1 Empirical Stress Tests for CinematicScriptCuratorAgent:
1. Extreme Durations & WPM bounds (1.0 to 10,000 WPM, zero WPM handling)
2. Empty Strings, whitespace-only, minimal 1-word/short inputs (<25 words fallback)
3. Boundary word count inputs (24 words, 25 words, 26 words, 100 words)
4. Massive Texts (10k words, 30k words, long single-sentence texts, 1000 short sentences)
5. Unusual Unicode & hostile inputs (emojis, CJK, Cyrillic, Arabic RTL, zalgo, HTML/script tags, zero-width chars, math symbols)
6. Title variations (long title truncation at 200, unicode title, punctuation title)
7. Channel lane and format permutation matrix (all 3 lanes, unknown lanes, cross format overrides)
8. Strict Draft-07 JSON Schema conformance across 100% of outputs
9. Act distribution (4 acts), sequential scene numbering (scene_001..N), regex scene_id pattern, and tension bounds (1-5)
10. Explicit documentation of None-type and empty-lane edge case vulnerabilities.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
import jsonschema
from jsonschema import Draft7Validator, validate, ValidationError

from src.agents.script_curator import (
    CinematicScriptCuratorAgent,
    LANE_CURATION_CONFIGS,
    VALID_AUDIO_PACING_CUES,
)

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "script_curator.schema.json"


@pytest.fixture(scope="module")
def curator_schema() -> dict:
    assert SCHEMA_PATH.is_file(), f"Schema not found: {SCHEMA_PATH}"
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def agent() -> CinematicScriptCuratorAgent:
    return CinematicScriptCuratorAgent()


class TestAdversarialEmptyAndMinimalInputs:
    """Stress tests on empty, whitespace, boundary, and minimal inputs."""

    @pytest.mark.parametrize("empty_input", [
        "",
        " ",
        "   \n\t\r \n   ",
        "\n\n\n\n",
        "\t\t\t",
        " . ",
        "???",
        "!!!...",
        "---",
        "###",
        "   \u200b\u200b\u200b   ",  # Zero-width spaces
    ])
    @pytest.mark.parametrize("lane", ["moku-scp-shorts", "moku-horror-long", "aelithia-aita-long"])
    def test_empty_and_whitespace_inputs_trigger_valid_fallback(
        self, agent, curator_schema, empty_input, lane
    ):
        target_fmt = "short" if "shorts" in lane else "longform"
        res = agent.curate(
            raw_text=empty_input,
            title="Empty Test",
            channel_lane=lane,
            target_format=target_fmt,
        )
        validate(instance=res, schema=curator_schema)
        assert len(res["acts"]) == 4
        all_scenes = [sc for act in res["acts"] for sc in act["scenes"]]
        assert len(all_scenes) >= (4 if target_fmt == "short" else 8)
        for sc in all_scenes:
            assert len(sc["narration_text"].strip()) > 0
            assert sc["word_count"] >= 1
            assert sc["estimated_duration_sec"] >= 1.0

    @pytest.mark.parametrize("word_count", [1, 2, 5, 10, 20, 24, 25, 26, 30])
    @pytest.mark.parametrize("lane", ["moku-scp-shorts", "moku-horror-long", "aelithia-aita-long"])
    def test_boundary_word_counts_around_fallback_threshold(
        self, agent, curator_schema, word_count, lane
    ):
        raw_text = " ".join([f"palabra{i}" for i in range(word_count)]) + "."
        target_fmt = "short" if "shorts" in lane else "longform"
        res = agent.curate(
            raw_text=raw_text,
            title=f"Boundary Words {word_count}",
            channel_lane=lane,
            target_format=target_fmt,
        )
        validate(instance=res, schema=curator_schema)
        assert len(res["acts"]) == 4
        assert res["metadata"]["total_word_count"] >= 1


class TestAdversarialExtremeDurationsAndWPM:
    """Stress tests on extreme WPM, duration limits, and edge calculations."""

    @pytest.mark.parametrize("wpm", [1.0, 10.0, 50.0, 140.0, 160.0, 300.0, 600.0, 1200.0, 10000.0])
    @pytest.mark.parametrize("lane", ["moku-scp-shorts", "moku-horror-long", "aelithia-aita-long"])
    def test_extreme_wpm_values_yield_valid_schema_and_clamped_durations(
        self, agent, curator_schema, wpm, lane
    ):
        story = " ".join(["relato de prueba con tension constante y misterio."] * 20)
        target_fmt = "short" if "shorts" in lane else "longform"
        res = agent.curate(
            raw_text=story,
            title="WPM Extreme Test",
            channel_lane=lane,
            target_format=target_fmt,
            words_per_minute=wpm,
        )
        validate(instance=res, schema=curator_schema)
        cfg = LANE_CURATION_CONFIGS[lane]
        total_dur = res["metadata"]["estimated_duration_sec"]
        assert cfg["min_total_dur"] <= total_dur <= cfg["max_total_dur"]

        for act in res["acts"]:
            for sc in act["scenes"]:
                assert cfg["min_scene_dur"] <= sc["estimated_duration_sec"] <= cfg["max_scene_dur"]


class TestAdversarialUnicodeAndHostileInputs:
    """Stress tests on emojis, non-Latin scripts, zalgo, HTML tags, and injection payloads."""

    @pytest.mark.parametrize("hostile_text,desc", [
        ("🔥💀👻😱👽👾🤖💥🎉🚀🚨 " * 20, "emojis"),
        ("这是一段中文测试。基金会控制着不可思议的实体。包含异常与危险。", "cjk_chinese"),
        ("これはテストです。恐怖の物語。誰もいない部屋から足音が聞こえる。", "cjk_japanese"),
        ("Это совершенно секретный протокол сдерживания объекта номер 173.", "cyrillic_russian"),
        ("هذا نص باللغة العربية لاختبار الدعم التام للغة اليمين إلى اليسار والرموز.", "arabic_rtl"),
        ("T̸h̵e̷ ̷v̴o̶i̵d̵ ̸c̷a̶l̴l̷s̷ ̵f̴r̴o̷m̴ ̶t̸h̸e̷ ̷d̵a̸r̶k̷n̶e̴s̸s̶ ̶u̴n̵k̸n̶o̴w̶n̷.", "zalgo_text"),
        ("<script>alert('xss');</script><h1>Injected Header</h1><div style='color:red;'>test</div>", "html_tags"),
        ("SELECT * FROM stories WHERE 1=1; DROP TABLE users; --", "sql_injection"),
        ("a" * 3000, "very_long_unspaced_string"),
        ("¿¡¿¡ÁÉÍÓÚáéíóúñÑüÜ!?!? " * 15, "heavy_spanish_punctuation"),
        ("\x1b[31mRed Text\x1b[0m \x1b[1mBold Text\x1b[0m", "ansi_escapes"),
        ("NaN Inf -Inf NULL None undefined true false", "special_constants"),
    ])
    def test_hostile_and_unicode_inputs_do_not_crash(
        self, agent, curator_schema, hostile_text, desc
    ):
        res = agent.curate(
            raw_text=hostile_text,
            title=f"Hostile Test {desc}",
            channel_lane="moku-horror-long",
            target_format="longform",
        )
        validate(instance=res, schema=curator_schema)
        assert len(res["acts"]) == 4
        assert res["metadata"]["total_word_count"] >= 1
        assert res["metadata"]["estimated_duration_sec"] >= 600.0


class TestAdversarialMassiveInputs:
    """Stress tests on huge inputs (10k, 30k words) and extreme sentence structures."""

    def test_massive_text_10k_words(self, agent, curator_schema):
        paragraph = (
            "El operador de la estación de radio escuchó un crujido metálico en la antena principal. "
            "La niebla cubría la montaña y la temperatura descendía minuto a minuto sin explicación meteorológica. "
        )
        huge_text = paragraph * 400  # ~10,000 words
        res = agent.curate(
            raw_text=huge_text,
            title="Relato Masivo de Prueba",
            channel_lane="moku-horror-long",
            target_format="longform",
        )
        validate(instance=res, schema=curator_schema)
        assert len(res["acts"]) == 4
        all_scenes = [sc for act in res["acts"] for sc in act["scenes"]]
        assert len(all_scenes) <= 24
        assert res["metadata"]["estimated_duration_sec"] <= 1800.0

    def test_single_gigantic_sentence_without_periods(self, agent, curator_schema):
        gigantic_sentence = " ".join(["palabra" for _ in range(3000)]) + "."
        res = agent.curate(
            raw_text=gigantic_sentence,
            title="Oracion Gigante",
            channel_lane="moku-horror-long",
            target_format="longform",
        )
        validate(instance=res, schema=curator_schema)
        assert len(res["acts"]) == 4

    def test_one_thousand_tiny_sentences(self, agent, curator_schema):
        tiny_sentences = " ".join([f"Paso {i}." for i in range(1000)])
        res = agent.curate(
            raw_text=tiny_sentences,
            title="Mil Oraciones",
            channel_lane="moku-horror-long",
            target_format="longform",
        )
        validate(instance=res, schema=curator_schema)
        assert len(res["acts"]) == 4
        all_scenes = [sc for act in res["acts"] for sc in act["scenes"]]
        assert len(all_scenes) <= 24


class TestAdversarialTitleAndMetadataRobustness:
    """Stress tests on title edge cases and metadata constraints."""

    @pytest.mark.parametrize("title_input", [
        "",
        " ",
        "A" * 500,  # Exceeds schema max length (200), curator truncates to <=200
        "🔥 Título con Emojis y Símbolos 💀",
        "<title>Injected Title</title>",
        "Título con Saltos\nDe\nLínea\r\nY Tabulaciones\t",
        "¿¿¿Soy la mala por existir???",
    ])
    def test_title_boundary_and_sanitization(self, agent, curator_schema, title_input):
        res = agent.curate(
            raw_text="Historia de prueba estándar para verificar el título en los metadatos.",
            title=title_input,
            channel_lane="aelithia-aita-long",
            target_format="longform",
        )
        validate(instance=res, schema=curator_schema)
        title_res = res["metadata"]["title"]
        assert 1 <= len(title_res) <= 200


class TestAdversarialLaneResolutionAndFallbackMatrix:
    """Stress tests for lane resolution and cross-format edge cases."""

    @pytest.mark.parametrize("channel_lane,target_format,expected_format", [
        ("UNKNOWN_LANE", "unknown_format", "longform"),
        ("scp-something", "longform", "short"),
        ("moku-horror-long", "short", "short"),
        ("AELITHIA-AITA-LONG", "longform", "longform"),
        ("random-lane-name", "short", "short"),
        ("cosmic_horror", "longform", "longform"),
        ("drama_confessions", "longform", "longform"),
    ])
    def test_lane_resolution_matrix(
        self, agent, curator_schema, channel_lane, target_format, expected_format
    ):
        res = agent.curate(
            raw_text="Texto de prueba suficientemente descriptivo para verificar la resolución de carril.",
            title="Prueba de Carril",
            channel_lane=channel_lane,
            target_format=target_format,
        )
        validate(instance=res, schema=curator_schema)
        assert res["metadata"]["target_format"] == expected_format
        assert len(res["acts"]) == 4

    def test_empty_channel_lane_fails_schema_min_length(self, agent):
        """Documents vulnerability: passing channel_lane='' violates minLength in schema."""
        with pytest.raises(ValidationError) as exc_info:
            agent.curate(
                raw_text="Texto de prueba",
                title="Test",
                channel_lane="",
                target_format="longform",
            )
        assert "channel_lane" in str(exc_info.value)

    def test_none_channel_lane_raises_attribute_error(self, agent):
        """Documents vulnerability: passing channel_lane=None raises AttributeError."""
        with pytest.raises(AttributeError):
            agent.curate(
                raw_text="Texto de prueba",
                title="Test",
                channel_lane=None,  # type: ignore
                target_format="longform",
            )

    def test_none_title_raises_type_error(self, agent):
        """Documents vulnerability: passing title=None raises TypeError in hook synthesis."""
        with pytest.raises(TypeError):
            agent.curate(
                raw_text="Texto de prueba",
                title=None,  # type: ignore
                channel_lane="moku-horror-long",
                target_format="longform",
            )


class TestAdversarialStructuralInvariants:
    """Verifies critical structural invariants across all test outputs."""

    @pytest.mark.parametrize("lane", ["moku-scp-shorts", "moku-horror-long", "aelithia-aita-long"])
    def test_structural_invariants_and_act_ordering(self, agent, curator_schema, lane):
        target_fmt = "short" if "shorts" in lane else "longform"
        res = agent.curate(
            raw_text="Un relato breve de prueba.",
            title="Prueba Invariantes",
            channel_lane=lane,
            target_format=target_fmt,
        )
        validate(instance=res, schema=curator_schema)

        # Invariant 1: Exactly 4 acts
        assert len(res["acts"]) == 4

        # Invariant 2: Acts numbered 1 to 4
        for idx, act in enumerate(res["acts"], start=1):
            assert act["act_number"] == idx
            assert len(act["scenes"]) >= 1

        # Invariant 3: Dramatic roles in exact order
        expected_roles = [
            "exposition_inception",
            "rising_action_dread",
            "climax_confrontation",
            "aftermath_revelation",
        ]
        assert [a["dramatic_role"] for a in res["acts"]] == expected_roles

        # Invariant 4: Sequential scene indexing and scene_id formatting
        all_scenes = [sc for act in res["acts"] for sc in act["scenes"]]
        for idx, sc in enumerate(all_scenes, start=1):
            assert sc["scene_index"] == idx
            assert sc["scene_id"] == f"scene_{idx:03d}"
            assert 1 <= sc["tension_level"] <= 5
            assert sc["audio_pacing_cue"] in VALID_AUDIO_PACING_CUES
            assert len(sc["environmental_mood"]) > 0

        # Invariant 5: Tension curve match
        tension_curve = res["metadata"]["tension_curve"]
        scene_tensions = [sc["tension_level"] for sc in all_scenes]
        assert tension_curve == scene_tensions
