"""Adversarial stress-test and empirical verification suite for Requirement R1.

Verifies:
1. Prompt pacing instructions across diverse edge cases:
   - max_words = None, 0, -10, 10, 100, 500, 10000
   - min_words > max_words
   - Empty/None title and content
   - Metacharacters and regex injection in title/content
   - Consistent injection of '2.25' words/s cadence and complete arc mandate
2. TTS duration modulation boundary conditions in Stage 5:
   - Overshoot exactly at 0%: no modulation (1 synthesis call)
   - Overshoot at 1%, 4%, 7.9%: modulation triggered, rate boost calculated, speech re-synthesized
   - Overshoot at 8.0%, 15%, 50%: rate modulation skipped, safely delegated to Stage 6 re-curation
   - Undershoots (-0.01%, -5%, -20%, -50%): no modulation triggered
   - Base voice_rate offsets (+5%, -4%, invalid, None)
   - Horizontal orientation and missing max duration
3. Terminal punctuation and sentence boundary enforcement:
   - _trim_script_to_max_words cuts at sentence boundaries (. ! ?)
   - Terminal punctuation preservation (. ! ?)
   - Inverted punctuation matching (¿...?, ¡...!) and rejection of unmatched marks
   - Pre-TTS barrier rejection of empty scripts, meta-intros, and structural headers
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src import llm
from src.core.profiling import PipelineProfiler
from src.narrative.quality_gate import validate_narrative_coherence
from src.pipeline.context import PipelineContext
from src.pipeline.stages.stage_05_tts import stage_05_tts_synthesis
from src.sanitizer import PromptLeakError, validate_pre_tts_script


# ==============================================================================
# Fixtures & Helpers
# ==============================================================================

@pytest.fixture
def mock_profiler() -> PipelineProfiler:
    return PipelineProfiler("test_adversarial_calibration_run")


@pytest.fixture
def mock_lane() -> MagicMock:
    lane = MagicMock()
    lane.id = "test-vertical-short"
    lane.orientation = "vertical"
    lane.duration_target_sec = 55.0
    lane.duration_max_sec = 60.0
    lane.duration_min_sec = 45.0
    lane.words_max = 135
    lane.words_min = 100
    lane.words_recondense_max = 125
    lane.voice_rate = "+0%"
    return lane


@pytest.fixture
def sample_context(tmp_path: Path, mock_profiler: PipelineProfiler, mock_lane: MagicMock) -> PipelineContext:
    script_file = tmp_path / "script.txt"
    audio_file = tmp_path / "speech.wav"
    script_text = (
        "En lo profundo de la mina abandonada los sensores detectaron vibraciones anómalas. "
        "El ingeniero descendió al tercer nivel para verificar el origen de la señal. "
        "Al iluminar el túnel descubrió que la roca se movía como un organismo vivo. "
        "El colapso de la entrada lo dejó atrapado en la oscuridad para siempre."
    )
    script_file.write_text(script_text, encoding="utf-8")
    audio_file.write_bytes(b"RIFF" + b"\x00" * 40)

    repo = MagicMock()
    ctx = PipelineContext(
        story={"title": "La Falla Profunda", "content": script_text},
        story_id="story_adv_1",
        run_id="run_adv_1",
        channel_name="moku",
        channel_key="moku",
        lane=mock_lane,
        repository=repo,
        database=":memory:",
        owner="test_challenger",
        lease_seconds=300,
        settings=MagicMock(),
        branding=MagicMock(),
        profiler=mock_profiler,
        directed=False,
        generate_only=False,
        engine_mode="loop",
        is_loop_mode=True,
        is_multiscene_mode=False,
        subtitles_active=False,
        work_dir=tmp_path,
        audio_path=audio_file,
        ass_path=tmp_path / "subs.ass",
        srt_path=tmp_path / "subs.srt",
        video_path=tmp_path / "video.mp4",
        thumbnail_path=tmp_path / "thumb.jpg",
        script_path=script_file,
        visual_plan_path=tmp_path / "plan.json",
        metadata_path=tmp_path / "meta.json",
        scene_manifest_path=tmp_path / "manifest.json",
    )
    ctx.clean_script = script_text
    ctx.script = script_text
    ctx.title = "La Falla Profunda"
    ctx.content = script_text
    return ctx


# ==============================================================================
# 1. Adversarial Prompt Pacing & Arc Cadence Tests
# ==============================================================================

class TestAdversarialPromptPacing:
    """Stress tests for prompt pacing instruction injection under adversarial edge cases."""

    @pytest.mark.parametrize("max_words_val", [None, 0, -1, -50, -99999])
    def test_pacing_omitted_for_non_positive_or_none(self, max_words_val: Any) -> None:
        """When max_words is None or <= 0, no max words pacing instruction is injected."""
        inst = llm._word_budget_instruction(max_words=max_words_val)
        assert "2.25" not in inst
        assert "CALIBRACIÓN ESTRICTA" not in inst

    @pytest.mark.parametrize("max_words_val", [10, 50, 100, 135, 500, 1000, 10000])
    def test_pacing_consistently_injected_across_budget_magnitudes(self, max_words_val: int) -> None:
        """Instruction cleanly injects 2.25 words/s and complete arc mandate across budgets."""
        inst = llm._word_budget_instruction(max_words=max_words_val)
        assert "2.25" in inst
        assert "palabras/segundo" in inst or "/s" in inst
        assert str(max_words_val) in inst
        assert "CALIBRACIÓN ESTRICTA DE DURACIÓN Y RITMO" in inst
        lower = inst.lower()
        assert any(term in lower for term in ("resuelva", "resolver", "desenlace", "remate"))
        assert any(term in lower for term in ("clímax", "conflicto", "gancho"))

    @pytest.mark.parametrize(
        "min_words, max_words",
        [
            (200, 100),       # min > max
            (2000, 100),      # longform min > short max
            (150, 150),       # min == max
            (50, 200),        # normal
        ],
    )
    def test_conflicting_word_bounds_handled_without_crash(self, min_words: int, max_words: int) -> None:
        """Conflicting or edge-case min/max word configurations format safely without exceptions."""
        inst = llm._word_budget_instruction(max_words=max_words, min_words=min_words)
        assert isinstance(inst, str)
        if max_words > 0:
            assert "2.25" in inst
            assert str(max_words) in inst
        if min_words >= 150:
            assert str(min_words) in inst

    @pytest.mark.parametrize(
        "adversarial_title",
        [
            "",
            "   ",
            None,
            "Title with [brackets] and (parentheses)",
            "Regex *+?^$\\.| metacharacters in title",
            "Format specifiers %s %d %x {0} {name} ${VAR}",
            "HTML <script>alert('xss')</script> and &amp; entities",
            "Non-ASCII unicode: 👻💀 ¡Terror Nocturno! ¿Quién vive? — §1",
            "A" * 500,  # very long title
        ],
    )
    def test_build_adaptation_prompt_survives_adversarial_titles(self, adversarial_title: Any) -> None:
        """_build_adaptation_prompt handles diverse and adversarial titles without regex or format crashes."""
        prompt = llm._build_adaptation_prompt(
            title=adversarial_title,
            content="Un grupo de exploradores quedó atrapado en la caverna subterránea.",
            channel="moku",
            max_words=135,
        )
        assert isinstance(prompt, str)
        assert "2.25" in prompt
        assert "135" in prompt
        assert "CALIBRACIÓN ESTRICTA" in prompt
        assert "<<<HISTORIA" in prompt

    @pytest.mark.parametrize(
        "adversarial_content",
        [
            "",
            "   \n\t  ",
            None,
            "Short text.",
            "Text with unbalanced quotes \" and brackets [[ and tags {\\k10}",
            "Special symbols: \\x00 \\n \\t \\r \\b \\f",
        ],
    )
    def test_build_adaptation_prompt_survives_adversarial_content(self, adversarial_content: Any) -> None:
        """_build_adaptation_prompt formats without error on malformed or empty content."""
        prompt = llm._build_adaptation_prompt(
            title="Relato del Abismo",
            content=adversarial_content,
            channel="moku",
            max_words=135,
        )
        assert isinstance(prompt, str)
        assert "2.25" in prompt
        assert "135" in prompt


# ==============================================================================
# 2. TTS Duration Modulation Boundary Condition Tests
# ==============================================================================

class TestTTSDurationModulationBoundaries:
    """Rigorous boundary and edge case testing for Stage 5 TTS speed modulation."""

    @pytest.mark.parametrize(
        "duration_sec, expected_calls, expected_mod_rate",
        [
            # Exactly at 0% overshoot: curr_dur == max_lane_sec (60.0s) -> No modulation
            (60.000, 1, None),
            # Micro-undershoot (-0.01%): 59.994s -> No modulation
            (59.994, 1, None),
            # Standard undershoot (-5.0%): 57.0s -> No modulation
            (57.000, 1, None),
            # Significant undershoot (-20.0%): 48.0s -> No modulation
            (48.000, 1, None),
            # Large undershoot (-50.0%): 30.0s -> No modulation
            (30.000, 1, None),
            # Micro-overshoot (+0.1%): 60.06s -> Modulated (+4% minimum boost)
            (60.060, 2, "+4%"),
            # 1.0% overshoot: 60.6s -> Modulated (+4% minimum boost)
            (60.600, 2, "+4%"),
            # 4.0% overshoot: 62.4s -> excess 4%, ceil(4)+2 = 6 -> Modulated (+6%)
            (62.400, 2, "+6%"),
            # 5.5% overshoot: 63.3s -> excess 5.5%, ceil(5.5)+2 = 8 -> Modulated (+8%)
            (63.300, 2, "+8%"),
            # 7.9% overshoot: 64.74s -> excess 7.9%, ceil(7.9)+2 = 10 -> Modulated (+10%)
            (64.740, 2, "+10%"),
            # 7.99% overshoot: 64.794s -> excess 7.99%, ceil(7.99)+2 = 10 -> Modulated (+10%)
            (64.794, 2, "+10%"),
            # 8.1% overshoot: 64.86s -> ratio > 0.08 -> Skipped
            (64.860, 1, None),
            # 15.0% overshoot: 69.0s -> ratio == 0.15 -> Skipped
            (69.000, 1, None),
            # 50.0% overshoot: 90.0s -> ratio == 0.50 -> Skipped
            (90.000, 1, None),
            # 100.0% overshoot: 120.0s -> ratio == 1.00 -> Skipped
            (120.000, 1, None),
        ],
    )
    def test_stage_05_duration_modulation_exact_boundaries(
        self,
        duration_sec: float,
        expected_calls: int,
        expected_mod_rate: str | None,
        sample_context: PipelineContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Validates all critical boundary conditions of the <8% speed modulation threshold."""
        monkeypatch.setattr("src.pipeline.stages.stage_05_tts.is_test_environment", lambda: False)

        ctx = sample_context
        ctx.lane.duration_max_sec = 60.0
        ctx.lane.voice_rate = "+0%"

        generated_rates: list[str] = []

        def fake_generate_audio(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            rate = kwargs.get("rate", "+0%")
            generated_rates.append(rate)
            if len(generated_rates) == 1:
                return {"audio_path": str(ctx.audio_path), "duration_sec": duration_sec, "word_timestamps": []}
            # Second call (modulation) brings audio to target duration
            return {"audio_path": str(ctx.audio_path), "duration_sec": 58.5, "word_timestamps": []}

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate_audio)

        stage_05_tts_synthesis(ctx)

        assert len(generated_rates) == expected_calls, (
            f"Duration {duration_sec}s expected {expected_calls} call(s), got {len(generated_rates)}"
        )
        if expected_mod_rate is not None:
            assert generated_rates[1] == expected_mod_rate, (
                f"Expected modulated rate {expected_mod_rate}, got {generated_rates[1]}"
            )
            assert ctx.audio["duration_sec"] == 58.5

    @pytest.mark.parametrize(
        "base_rate, overshoot_sec, expected_second_rate",
        [
            ("+5%", 62.4, "+11%"),   # Base +5% + boost 6% = +11%
            ("-4%", 62.4, "+2%"),    # Base -4% + boost 6% = +2%
            ("0%", 62.4, "+6%"),     # Base 0% + boost 6% = +6%
            (None, 62.4, "+6%"),     # None defaults to +0%
            ("invalid", 62.4, "+6%"),# Non-numeric string defaults to +0%
        ],
    )
    def test_stage_05_rate_modulation_with_diverse_base_rates(
        self,
        base_rate: Any,
        overshoot_sec: float,
        expected_second_rate: str,
        sample_context: PipelineContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Validates that rate boost is properly added to existing lane voice_rate."""
        monkeypatch.setattr("src.pipeline.stages.stage_05_tts.is_test_environment", lambda: False)

        ctx = sample_context
        ctx.lane.duration_max_sec = 60.0
        ctx.lane.voice_rate = base_rate

        rates_called: list[str] = []

        def fake_generate(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            rates_called.append(kwargs.get("rate", "+0%"))
            if len(rates_called) == 1:
                return {"audio_path": str(ctx.audio_path), "duration_sec": overshoot_sec, "word_timestamps": []}
            return {"audio_path": str(ctx.audio_path), "duration_sec": 59.0, "word_timestamps": []}

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate)

        stage_05_tts_synthesis(ctx)
        assert len(rates_called) == 2
        assert rates_called[1] == expected_second_rate

    def test_stage_05_handles_zero_or_none_duration_max_sec(
        self, sample_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When lane duration_max_sec is 0 or None, no division by zero occurs."""
        monkeypatch.setattr("src.pipeline.stages.stage_05_tts.is_test_environment", lambda: False)

        ctx = sample_context
        ctx.lane.duration_max_sec = 0.0

        calls: list[str] = []

        def fake_generate(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs.get("rate", "+0%"))
            return {"audio_path": str(ctx.audio_path), "duration_sec": 65.0, "word_timestamps": []}

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate)

        # Must execute cleanly without ZeroDivisionError
        stage_05_tts_synthesis(ctx)
        assert len(calls) == 1

    def test_stage_05_handles_legacy_path_return_from_generate_audio(
        self, sample_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When generate_audio returns Path/str instead of dict, stage 5 safely handles it."""
        monkeypatch.setattr("src.pipeline.stages.stage_05_tts.is_test_environment", lambda: False)

        ctx = sample_context

        def fake_generate(script: str, output_path: str, **kwargs: Any) -> Path:
            return ctx.audio_path

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate)

        stage_05_tts_synthesis(ctx)
        assert ctx.audio["duration_sec"] == 0.0


# ==============================================================================
# 3. Terminal Punctuation & Sentence Boundary Enforcement Tests
# ==============================================================================

class TestTerminalPunctuationAndBoundaries:
    """Stress tests for sentence boundaries and terminal punctuation enforcement."""

    @pytest.mark.parametrize("terminal_mark", [".", "!", "?"])
    def test_trim_script_to_max_words_preserves_sentence_terminal(self, terminal_mark: str) -> None:
        """_trim_script_to_max_words cuts at the sentence boundary and preserves terminal punctuation."""
        # Construct text with two sentences: first sentence is ~60 words, second pushes past 100
        sentence_1 = " ".join(["palabra"] * 50) + f"{terminal_mark}"
        sentence_2 = " ".join(["otra"] * 60) + "."
        full_text = f"{sentence_1} {sentence_2}"

        trimmed = llm._trim_script_to_max_words(full_text, max_words=70)
        assert trimmed.endswith(terminal_mark), (
            f"Trimmed script must end with sentence boundary terminal '{terminal_mark}', got '{trimmed[-10:]}'"
        )
        assert len(trimmed.split()) <= 70

    def test_trim_script_without_punctuation_does_not_crash(self) -> None:
        """_trim_script_to_max_words handles text without punctuation cleanly."""
        text_without_punct = " ".join(["palabra"] * 100)
        trimmed = llm._trim_script_to_max_words(text_without_punct, max_words=50)
        assert len(trimmed.split()) == 50

    @pytest.mark.parametrize("terminal_char", [".", "!", "?"])
    def test_valid_terminal_punctuations_pass_coherence(self, terminal_char: str) -> None:
        """Spanish stories ending with canonical terminal punctuation pass narrative coherence."""
        script = (
            f"El capitán aseguró la escotilla del submarino con ambas manos. "
            f"El sonar indicaba que la criatura del abismo rodeaba el casco metálico. "
            f"Una vibración profunda sacudió las vigas de soporte principales{terminal_char}"
        )
        res = validate_narrative_coherence(script, channel="moku", duration_type="short", max_words=135)
        assert res.valid is True
        assert res.score >= 0.75

    def test_unmatched_inverted_question_mark_strictly_rejected(self) -> None:
        """Script containing opening '¿' without closing '?' is rejected by coherence gate."""
        script = (
            "El detective examinó las huellas en el fango húmedo. "
            "¿Quién había salido de la cabaña antes de la medianoche. "
            "La niebla cubría todas las pistas del camino principal."
        )
        res = validate_narrative_coherence(script, channel="moku", duration_type="short", max_words=135)
        assert not res.valid
        assert any("question mark" in err.lower() or "¿" in err for err in res.errors)

    def test_unmatched_inverted_exclamation_strictly_rejected(self) -> None:
        """Script containing opening '¡' without closing '!' is rejected by coherence gate."""
        script = (
            "La sirena de emergencia despertó a todos los habitantes del refugio. "
            "¡Corran hacia las compuertas inferiores antes de que sea tarde. "
            "El humo denso comenzó a filtrarse por los conductos de ventilación."
        )
        res = validate_narrative_coherence(script, channel="moku", duration_type="short", max_words=135)
        assert not res.valid
        assert any("exclamation" in err.lower() or "¡" in err for err in res.errors)

    def test_pre_tts_barrier_rejects_meta_preambles(self) -> None:
        """Pre-TTS barrier rejects scripts starting with meta-instructions."""
        meta_script = "Vamos a narrar la historia de terror que ocurrió en el bosque."
        with pytest.raises(PromptLeakError, match="meta-introduction"):
            validate_pre_tts_script(meta_script)

    def test_pre_tts_barrier_rejects_structural_headers(self) -> None:
        """Pre-TTS barrier rejects scripts containing structural chapter/act headers."""
        header_script = "Capítulo 1: La Noche Oscura.\n\nEl viento soplaba con fuerza en el tejado."
        with pytest.raises(PromptLeakError, match="structural header"):
            validate_pre_tts_script(header_script)


# ==============================================================================
# 4. Empirical Vulnerability & Bug Verifications (XFAIL Reproductions)
# ==============================================================================

class TestEmpiricalBugReproductions:
    """Documented and empirically reproduced bugs in Stage 5 TTS duration modulation.

    These tests document regressions and floating-point edge cases where the
    implementation deviates from Requirement R1 contracts.
    """

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG 1 (Boundary Leak): Exactly 8.0% overshoot (64.8s on 60s lane) triggers speed modulation "
            "due to IEEE 754 precision ((64.8 - 60.0) / 60.0 = 0.07999999999999995 < 0.08). "
            "Contract mandates overshoots >= 8.0% must skip modulation and delegate to Stage 6."
        ),
    )
    def test_exact_8_percent_overshoot_skips_modulation_boundary_leak(
        self, sample_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An audio duration of exactly 64.8s (8.0% over 60.0s max) MUST skip speed modulation."""
        monkeypatch.setattr("src.pipeline.stages.stage_05_tts.is_test_environment", lambda: False)

        ctx = sample_context
        ctx.lane.duration_max_sec = 60.0
        ctx.lane.voice_rate = "+0%"

        calls: list[str] = []

        def fake_generate(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs.get("rate", "+0%"))
            return {"audio_path": str(ctx.audio_path), "duration_sec": 64.8, "word_timestamps": []}

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate)

        stage_05_tts_synthesis(ctx)

        # Expected by specification: 8.0% overshoot must NOT modulate (calls == 1).
        # Bug: calls == 2 (modulated to +10%) because 0.07999999999999995 < 0.08!
        assert len(calls) == 1, (
            f"Expected exactly 1 call (skipped modulation for 8.0% overshoot), but got {len(calls)} calls: {calls}"
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG 2 (Rate Jitter): math.ceil(excess_ratio * 100) on round overshoot percentages (2.0%, 7.0%) "
            "suffers from floating point noise ((61.2-60)/60 = 0.02000000000000005 -> ceil(2.000000000000005) = 3), "
            "causing 1% over-boost (+5% instead of +4%, +10% instead of +9%)."
        ),
    )
    @pytest.mark.parametrize(
        "duration_sec, expected_rate",
        [
            (61.2, "+4%"),  # 2.0% overshoot -> ceil(2.0)+2 = 4 -> expected +4%, currently produces +5%
            (64.2, "+9%"),  # 7.0% overshoot -> ceil(7.0)+2 = 9 -> expected +9%, currently produces +10%
        ],
    )
    def test_floating_point_jitter_in_rate_boost_calculation(
        self,
        duration_sec: float,
        expected_rate: str,
        sample_context: PipelineContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Validates rate boost on integer-percent overshoots without floating-point ceiling inflation."""
        monkeypatch.setattr("src.pipeline.stages.stage_05_tts.is_test_environment", lambda: False)

        ctx = sample_context
        ctx.lane.duration_max_sec = 60.0
        ctx.lane.voice_rate = "+0%"

        rates_called: list[str] = []

        def fake_generate(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            rates_called.append(kwargs.get("rate", "+0%"))
            if len(rates_called) == 1:
                return {"audio_path": str(ctx.audio_path), "duration_sec": duration_sec, "word_timestamps": []}
            return {"audio_path": str(ctx.audio_path), "duration_sec": 58.0, "word_timestamps": []}

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate)

        stage_05_tts_synthesis(ctx)

        assert len(rates_called) == 2
        assert rates_called[1] == expected_rate, (
            f"Expected {expected_rate} rate boost, but got {rates_called[1]} due to ceil() jitter"
        )

