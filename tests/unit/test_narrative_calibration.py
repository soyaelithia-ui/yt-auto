"""Unit and integration tests for Narrative Duration Calibration and Arc Resolution (R1).

Validates:
1. LLM word budget and pacing prompt instruction (2.25 words/s cadence and complete narrative arc mandate).
2. Stage 5 TTS speed modulation on minor audio overshoots (<8% over lane max duration).
3. Stage 6 fallback to standard LLM re-curation on significant overshoots (>=8%).
4. Script terminal punctuation and narrative coherence validation.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from src import llm
from src.core.profiling import CanonicalStage, PipelineProfiler
from src.narrative.quality_gate import validate_narrative_coherence
from src.pipeline.context import PipelineContext
from src.pipeline.stages.stage_05_tts import stage_05_tts_synthesis
from src.pipeline.stages.stage_06_alignment import _align_vertical_overduration
from src.sanitizer import validate_pre_tts_script


# ===========================================================================
# Fixtures & Helpers
# ===========================================================================

@pytest.fixture
def mock_profiler() -> PipelineProfiler:
    return PipelineProfiler("test_narrative_calibration_run")


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
        "Era una noche fría en el bosque cuando las luces se apagaron por completo. "
        "Escuché pasos pesados acercándose a la cabaña y cerré la puerta con seguro. "
        "Al mirar por la ventana, descubrí que la sombra no era humana, sino una criatura imponente. "
        "Finalmente el sol salió y la criatura desapareció entre la densa niebla matutina."
    )
    script_file.write_text(script_text, encoding="utf-8")
    audio_file.write_bytes(b"RIFF" + b"\x00" * 40)

    repo = MagicMock()
    ctx = PipelineContext(
        story={"title": "La Sombra del Bosque", "content": script_text},
        story_id="story_calib_1",
        run_id="run_calib_1",
        channel_name="moku",
        channel_key="moku",
        lane=mock_lane,
        repository=repo,
        database=":memory:",
        owner="test_worker",
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
    ctx.title = "La Sombra del Bosque"
    ctx.content = script_text
    return ctx


# ===========================================================================
# 1. Pacing and Narrative Arc Resolution Instruction Tests (src/llm.py)
# ===========================================================================

class TestWordBudgetPacingInstruction:
    """Validates the 2.25 words/s pacing instruction and complete narrative arc resolution mandate."""

    def test_word_budget_instruction_includes_pacing_and_arc_mandate(self) -> None:
        """Instruction communicates strict 2.25 words/s cadence and complete narrative arc resolution."""
        instruction = llm._word_budget_instruction(max_words=135)
        assert instruction, "Instruction must not be empty when max_words is provided"

        lower_inst = instruction.lower()
        # 1. Check strict cadence of 2.25 words/second
        assert "2.25" in lower_inst, "Missing 2.25 words/second pacing rate in instruction"
        assert "palabras" in lower_inst and ("segundo" in lower_inst or "/s" in lower_inst), (
            "Missing words per second unit in pacing instruction"
        )

        # 2. Check maximum word constraint interpolation
        assert "135" in instruction, "Instruction must include the explicit max_words limit"

        # 3. Check complete narrative arc resolution mandate
        assert any(term in lower_inst for term in ("resuelva", "resolver", "resolución", "remate", "desenlace")), (
            "Instruction must mandate complete resolution of the story within the word budget"
        )
        assert any(term in lower_inst for term in ("clímax", "conflicto", "gancho")), (
            "Instruction must reference narrative progression (hook, conflict, or climax)"
        )
        assert any(
            term in lower_inst for term in ("prohibido", "nunca", "cortad", "incomplet", "mutilar")
        ), "Instruction must prohibit incomplete or cut-off endings"

    def test_word_budget_instruction_none_or_zero_omits_pacing(self) -> None:
        """When max_words is None or <= 0, no max word pacing instruction is generated."""
        assert llm._word_budget_instruction(None) == ""
        assert llm._word_budget_instruction(0) == ""
        assert llm._word_budget_instruction(-20) == ""

    def test_word_budget_instruction_calibrated_for_different_durations(self) -> None:
        """Pacing instruction adapts correctly across different Short durations."""
        # 60-second short -> 135 words (60 * 2.25)
        inst_60 = llm._word_budget_instruction(max_words=135)
        assert "135" in inst_60
        assert "2.25" in inst_60

        # 90-second short -> 202 words (90 * 2.25)
        inst_90 = llm._word_budget_instruction(max_words=202)
        assert "202" in inst_90
        assert "2.25" in inst_90

    def test_word_budget_with_min_words_preserves_both_constraints(self) -> None:
        """Both minimum word threshold and maximum cadence/arc instruction coexist cleanly."""
        inst = llm._word_budget_instruction(max_words=180, min_words=150)
        lower_inst = inst.lower()

        assert "150" in inst, "Minimum word budget must be present"
        assert "180" in inst, "Maximum word budget must be present"
        assert "mínimo" in lower_inst
        assert "2.25" in lower_inst
        assert any(term in lower_inst for term in ("resuelva", "resolver", "desenlace", "remate"))

    def test_build_adaptation_prompt_integrates_cadence_and_arc_mandate(self) -> None:
        """_build_adaptation_prompt embeds pacing and narrative arc mandate into LLM prompt."""
        prompt = llm._build_adaptation_prompt(
            title="Terror en la Estación",
            content="Había algo escondido en la penumbra del andén tres...",
            channel="moku",
            max_words=135,
        )
        lower_prompt = prompt.lower()

        assert "135" in prompt
        assert "2.25" in lower_prompt
        assert "terror en la estación" in prompt
        assert any(term in lower_prompt for term in ("resuelva", "resolver", "desenlace", "remate"))


# ===========================================================================
# 2. Stage 5 TTS Speed Modulation Tests (src/pipeline/stages/stage_05_tts.py)
# ===========================================================================

class TestStage05TTSSpeedModulation:
    """Validates intelligent speed modulation in Stage 5 for minor duration overshoots (<8%)."""

    def test_stage_05_detects_minor_overshoot_and_modulates_tts_rate(
        self, sample_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When audio slightly exceeds duration_max_sec (<8%), TTS rate is modulated without re-curation."""
        # Force production execution path for the speed modulation logic
        monkeypatch.setattr("src.pipeline.stages.stage_05_tts.is_test_environment", lambda: False)

        ctx = sample_context
        # lane.duration_max_sec = 60.0. An audio duration of 63.0s is (63 - 60) / 60 = 5.0% overshoot (< 8%).
        initial_audio = {
            "audio_path": str(ctx.audio_path),
            "duration_sec": 63.0,
            "word_timestamps": [{"word": "test", "start": 0.0, "end": 63.0}],
        }
        modulated_audio = {
            "audio_path": str(ctx.audio_path),
            "duration_sec": 59.2,
            "word_timestamps": [{"word": "test", "start": 0.0, "end": 59.2}],
        }

        generated_rates: list[str] = []

        def fake_generate_audio(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            rate = kwargs.get("rate", "+0%")
            generated_rates.append(rate)
            if len(generated_rates) == 1:
                return initial_audio
            return modulated_audio

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate_audio)

        stage_05_tts_synthesis(ctx)

        # Must have performed a second synthesis pass with modulated rate
        assert len(generated_rates) == 2, (
            f"Expected exactly 2 generate_audio invocations (initial + modulated), got {len(generated_rates)}"
        )
        assert generated_rates[0] == "+0%", f"Initial rate should be base rate, got {generated_rates[0]}"

        # Second rate must be boosted (e.g. +6%, +7%, or +8%)
        second_rate_str = generated_rates[1].replace("%", "").strip()
        second_rate_int = int(second_rate_str) if second_rate_str.lstrip("+-").isdigit() else 0
        assert second_rate_int > 0, f"Modulated rate must be positive speedup, got {generated_rates[1]}"
        assert 4 <= second_rate_int <= 10, f"Speed modulation must be bounded between +4% and +10%, got {second_rate_int}%"

        # Final audio duration recorded in ctx must now be within lane bounds
        assert ctx.audio["duration_sec"] <= ctx.lane.duration_max_sec, (
            f"Duration {ctx.audio['duration_sec']}s not brought within max {ctx.lane.duration_max_sec}s"
        )
        assert ctx.audio["duration_sec"] == 59.2

    def test_stage_05_rate_modulation_boundary_at_7_percent(
        self, sample_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An overshoot of 7.0% (below 8% ceiling) correctly triggers rate modulation."""
        monkeypatch.setattr("src.pipeline.stages.stage_05_tts.is_test_environment", lambda: False)

        ctx = sample_context
        # 60.0s max, 64.2s audio -> (64.2 - 60.0) / 60.0 = 7.0% overshoot
        calls: list[str] = []

        def fake_generate(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            rate = kwargs.get("rate", "+0%")
            calls.append(rate)
            if len(calls) == 1:
                return {"audio_path": str(ctx.audio_path), "duration_sec": 64.2, "word_timestamps": []}
            return {"audio_path": str(ctx.audio_path), "duration_sec": 59.8, "word_timestamps": []}

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate)

        stage_05_tts_synthesis(ctx)
        assert len(calls) == 2, "7% overshoot must trigger speed modulation"
        assert ctx.audio["duration_sec"] <= 60.0

    def test_stage_05_no_modulation_when_within_max_duration(
        self, sample_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When initial audio is within duration_max_sec, no second synthesis or rate modulation occurs."""
        monkeypatch.setattr("src.pipeline.stages.stage_05_tts.is_test_environment", lambda: False)

        ctx = sample_context
        calls: list[str] = []

        def fake_generate(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            rate = kwargs.get("rate", "+0%")
            calls.append(rate)
            return {"audio_path": str(ctx.audio_path), "duration_sec": 58.0, "word_timestamps": []}

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate)

        stage_05_tts_synthesis(ctx)
        assert len(calls) == 1, "Should not modulate rate when duration is already within bounds"
        assert ctx.audio["duration_sec"] == 58.0

    def test_stage_05_no_modulation_for_horizontal_lane(
        self, sample_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Horizontal longform lanes do not apply Short rate modulation even if slightly over."""
        monkeypatch.setattr("src.pipeline.stages.stage_05_tts.is_test_environment", lambda: False)

        ctx = sample_context
        ctx.lane.orientation = "horizontal"
        ctx.lane.duration_max_sec = 600.0

        calls: list[str] = []

        def fake_generate(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs.get("rate", "+0%"))
            return {"audio_path": str(ctx.audio_path), "duration_sec": 620.0, "word_timestamps": []}

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate)

        stage_05_tts_synthesis(ctx)
        assert len(calls) == 1, "Horizontal longform must not trigger Short speed modulation"


# ===========================================================================
# 3. Overshoot Fallback to Standard Re-curation Tests (Stage 5 + Stage 6)
# ===========================================================================

class TestOvershootFallbackToStandardRecuration:
    """Validates that overshoots >=8% bypass speed modulation and fall back to LLM re-curation."""

    def test_stage_05_skips_modulation_for_overshoots_at_or_above_8_percent(
        self, sample_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When overshoot is >= 8% (e.g. 10%), rate modulation is NOT applied in Stage 5."""
        monkeypatch.setattr("src.pipeline.stages.stage_05_tts.is_test_environment", lambda: False)

        ctx = sample_context
        # 60.0s max, 66.0s duration -> 10.0% overshoot (>= 8.0%)
        calls: list[str] = []

        def fake_generate(script: str, output_path: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs.get("rate", "+0%"))
            return {"audio_path": str(ctx.audio_path), "duration_sec": 66.0, "word_timestamps": []}

        monkeypatch.setattr("lib.tts.generate_audio", fake_generate)

        stage_05_tts_synthesis(ctx)

        # Stage 5 should NOT attempt rate modulation for overshoots >= 8%
        assert len(calls) == 1, "Overshoots >=8% must not be modulated via Edge TTS speedup"
        assert ctx.audio["duration_sec"] == 66.0

    def test_stage_06_alignment_invokes_recuration_for_large_overshoot(
        self, sample_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When audio duration remains over max (>=8% overshoot), Stage 6 invokes standard LLM re-curation."""
        ctx = sample_context
        ctx.audio = {"duration_sec": 66.0, "audio_path": str(ctx.audio_path), "word_timestamps": []}

        mock_curate = MagicMock(return_value="Guion condensado por LLM tras re-curación.")
        monkeypatch.setattr("src.pipeline.stages.stage_06_alignment._dispatch_curate_script", mock_curate)

        # Mock reprocess so it updates duration within bounds
        def fake_reprocess(c: PipelineContext, raw: str, tag: str, enforcer: Any) -> None:
            c.clean_script = raw
            c.audio = {"duration_sec": 55.0, "audio_path": str(c.audio_path), "word_timestamps": []}

        monkeypatch.setattr("src.pipeline.stages.stage_06_alignment._reprocess_script", fake_reprocess)

        _align_vertical_overduration(ctx, enforcer=lambda s, **kw: s)

        # Verify _dispatch_curate_script was invoked for re-curation
        assert mock_curate.called, "Standard LLM re-curation must be invoked when audio exceeds max duration by >=8%"
        assert ctx.audio["duration_sec"] <= ctx.lane.duration_max_sec

    def test_minor_overshoot_avoids_recuration_completely(
        self, sample_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When Stage 5 brings minor overshoot within bounds, Stage 6 skips the 12s LLM re-curation entirely."""
        ctx = sample_context
        # Duration was successfully calibrated down to 59.2s in Stage 5
        ctx.audio = {"duration_sec": 59.2, "audio_path": str(ctx.audio_path), "word_timestamps": []}

        mock_curate = MagicMock()
        monkeypatch.setattr("src.pipeline.stages.stage_06_alignment._dispatch_curate_script", mock_curate)

        _align_vertical_overduration(ctx, enforcer=lambda s, **kw: s)

        # Verify re-curation was completely bypassed
        assert not mock_curate.called, "LLM re-curation must NOT be invoked when audio is already within lane max"


# ===========================================================================
# 4. Terminal Punctuation and Narrative Resolution Validation Tests
# ===========================================================================

class TestTerminalPunctuationValidation:
    """Validates that scripts with proper terminal punctuation pass validation and incomplete cuts fail."""

    @pytest.mark.parametrize("terminal_char", [".", "!", "?"])
    def test_script_ending_with_terminal_punctuation_passes_validation(self, terminal_char: str) -> None:
        """Scripts ending with valid sentence terminal punctuation (., !, ?) pass pre-TTS barrier."""
        script = (
            f"El investigador revisó la última cámara de seguridad del piso subterráneo. "
            f"No había señales de intrusos en los pasillos principales. "
            f"Todo parecía en completo orden hasta que la última luz se apagó{terminal_char}"
        )
        assert validate_pre_tts_script(script) is True

        res = validate_narrative_coherence(script, channel="moku", duration_type="short", max_words=135)
        assert res.valid is True
        assert res.score >= 0.75

    def test_script_with_unmatched_inverted_question_mark_fails_coherence(self) -> None:
        """Scripts with opening inverted question mark (¿) without closing (?) fail coherence."""
        script = (
            "El doctor examinó los resultados del laboratorio con evidente nerviosismo. "
            "¿Acaso era posible que la muestra hubiera mutado en menos de una hora. "
            "Nadie en la sala tenía una respuesta lógica ante lo ocurrido."
        )
        res = validate_narrative_coherence(script, channel="moku", duration_type="short", max_words=135)
        assert not res.valid
        assert any("question mark" in err.lower() or "¿" in err for err in res.errors)

    def test_script_with_unmatched_inverted_exclamation_fails_coherence(self) -> None:
        """Scripts with opening inverted exclamation (¡) without closing (!) fail coherence."""
        script = (
            "La alarma del búnker principal comenzó a sonar en todas las frecuencias. "
            "¡Corran hacia la salida de emergencia antes de que sellen la compuerta. "
            "Todos lograron escapar a tiempo antes del colapso definitivo."
        )
        res = validate_narrative_coherence(script, channel="moku", duration_type="short", max_words=135)
        assert not res.valid
        assert any("exclamation" in err.lower() or "¡" in err for err in res.errors)

    def test_empty_or_whitespace_script_fails_pre_tts_barrier(self) -> None:
        """Empty or whitespace scripts fail pre-TTS validation."""
        from src.sanitizer import PromptLeakError

        with pytest.raises(PromptLeakError):
            validate_pre_tts_script("")

        with pytest.raises(PromptLeakError):
            validate_pre_tts_script("   \n\t  ")
