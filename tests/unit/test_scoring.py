"""Comprehensive Unit Tests for src/core/scoring.py (Milestone M2 - R2).

Tests:
1. Fast Heuristics:
   - Normalized engagement metrics (score, ratio, comment volume, comment velocity).
   - Opening hook detection (high-tension questions, in medias res, stakes vs conversational greeting/preamble penalties).
   - Retention length scoring (Gaussian/trapezoidal fit against lane word budgets).
   - Fast rejection gate.
2. Semantic / Viral LLM Evaluation:
   - Deterministic offline fallback evaluation for horror vs drama channels.
   - Tone alignment and twist/surprise factor detection.
   - Mock LLM clients (sync and async) with JSON extraction and graceful error recovery.
3. Hybrid Score Synthesis & Quality Gate:
   - Weighted alpha blend and db_rank integer [0, 1000] mapping.
   - Threshold enforcement and short-circuit verification.
   - Dataclass serialization (.to_dict()).
"""

import asyncio
import json
import time
import pytest
from types import SimpleNamespace
from typing import Any, Dict

from src.core.scoring import (
    HeuristicScoreReport,
    SemanticScoreReport,
    StoryScoringVerdict,
    detect_opening_hook_strength,
    evaluate_retention_length_score,
    evaluate_fast_heuristics,
    evaluate_semantic_viral_potential,
    async_evaluate_semantic_viral_potential,
    compute_hybrid_story_score,
    filter_and_score_story,
    async_filter_and_score_story,
    DEFAULT_HEURISTIC_THRESHOLD,
    DEFAULT_SEMANTIC_THRESHOLD,
    DEFAULT_HYBRID_THRESHOLD,
    DEFAULT_ALPHA,
)
from src.core.lanes import LaneProfile, CanonicalChannel


# ===========================================================================
# 1. Opening Hook Detection Tests
# ===========================================================================
class TestOpeningHookDetection:
    """Test suite for detect_opening_hook_strength."""

    def test_empty_and_whitespace_input(self):
        score, pos, neg = detect_opening_hook_strength("", "")
        assert score == 0.0
        assert pos == []
        assert "empty_input" in neg

        score, pos, neg = detect_opening_hook_strength("   ", "\n\t  ")
        assert score == 0.0
        assert "empty_input" in neg

    def test_strong_question_dilemma_hook(self):
        title = "¿Soy el malo por negarme a pagar la boda de mi hermana?"
        content = "Mi hermana me exigió 10,000 dólares para su boda..."
        score, pos, neg = detect_opening_hook_strength(title, content)

        assert score >= 0.75
        assert any("question" in p for p in pos)
        assert len(neg) == 0

    def test_strong_horror_in_medias_res_hook(self):
        title = "El sótano del Sitio 19"
        content = "A las 3 AM escuché golpes violentos dentro de las paredes de mi departamento. Solo hay una regla..."
        score, pos, neg = detect_opening_hook_strength(title, content)

        assert score >= 0.85
        assert any("in_medias_res" in p for p in pos)
        assert any("stakes" in p or "time" in p for p in pos)
        assert len(neg) == 0

    def test_high_tension_keywords_bonus(self):
        title = "Expediente Clasificado"
        content = "Descubrí un secreto prohibido sobre la muerte de mi hermano y la sangre en el búnker."
        score, pos, neg = detect_opening_hook_strength(title, content)

        assert score >= 0.80
        assert any("high_tension" in p for p in pos)

    def test_conversational_greeting_penalties(self):
        title = "Mi extraña experiencia"
        content = "Hola a todos, este es mi primer post en Reddit. Espero que les guste mucho mi historia..."
        score, pos, neg = detect_opening_hook_strength(title, content)

        assert score <= 0.25
        assert any("conversational_greeting" in n for n in neg)
        assert any("exposition_or_meta_preamble" in n for n in neg)

    def test_exposition_delay_preamble_penalty(self):
        title = "Un día en mi pueblo"
        content = "Siempre he sido una persona normal que vive en un pueblo común sin nada especial que contar..."
        score, pos, neg = detect_opening_hook_strength(title, content)

        assert score <= 0.35
        assert any("exposition_or_meta_preamble" in n for n in neg)

    def test_english_hook_markers(self):
        title = "AITA for telling my wife the truth?"
        content = "I woke up at 3 AM to find my door unlocked. Only one rule was broken..."
        score, pos, neg = detect_opening_hook_strength(title, content)

        assert score >= 0.85
        assert any("question" in p for p in pos)

    def test_accents_and_case_insensitivity(self):
        title = "¿ESTÁS SEGURO DE QUE DESEAS ENTRAR?"
        content = "¡¡PELIGRO MORTAL!! UN CADÁVER FUE DESCUBIERTO EN EL BÚNKER."
        score, pos, neg = detect_opening_hook_strength(title, content)

        assert score >= 0.80
        assert any("question" in p for p in pos)
        assert any("high_tension" in p for p in pos)

    def test_mixed_greeting_and_question(self):
        title = "¿Soy el malo por esto?"
        content = "Hola a todos, este es un post largo. Me gustaría saber su opinión."
        score, pos, neg = detect_opening_hook_strength(title, content)

        # Question gives +0.25, greetings/preamble give -0.40 -0.35 -> net negative
        assert score < 0.50
        assert len(pos) > 0
        assert len(neg) > 0


# ===========================================================================
# 2. Retention Length Scoring Tests
# ===========================================================================
class TestRetentionLengthScoring:
    """Test suite for evaluate_retention_length_score."""

    def test_zero_and_negative_words(self):
        assert evaluate_retention_length_score(0) == 0.0
        assert evaluate_retention_length_score(-50) == 0.0

    def test_under_minimum_words_penalty(self):
        # min=160, words=80 -> (80/160)*0.5 = 0.25
        score = evaluate_retention_length_score(word_count=80, words_min=160, words_max=340, words_target=250)
        assert score == 0.25

    def test_exact_target_words_optimal(self):
        # target=250 -> 1.0
        score = evaluate_retention_length_score(word_count=250, words_min=160, words_max=340, words_target=250)
        assert score == 1.0

    def test_within_bounds_smooth_scoring(self):
        # min=160, max=340, target=250. At bounds (160 and 340), score should be 0.80
        score_min = evaluate_retention_length_score(word_count=160, words_min=160, words_max=340, words_target=250)
        score_max = evaluate_retention_length_score(word_count=340, words_min=160, words_max=340, words_target=250)
        assert score_min == 0.80
        assert score_max == 0.80

        # Intermediate value
        score_mid = evaluate_retention_length_score(word_count=205, words_min=160, words_max=340, words_target=250)
        assert 0.80 < score_mid < 1.0

    def test_over_maximum_words_gradual_decay(self):
        # max=340, words=680 -> 1.0 - 0.5 * (340/340) = 0.50
        score = evaluate_retention_length_score(word_count=680, words_min=160, words_max=340, words_target=250)
        assert score == 0.50

        # extreme over-length -> 0.0
        score_extreme = evaluate_retention_length_score(word_count=2000, words_min=160, words_max=340, words_target=250)
        assert score_extreme == 0.0

    def test_open_ended_longform_budget(self):
        # words_max is None (longform)
        score_target = evaluate_retention_length_score(word_count=3000, words_min=2600, words_max=None, words_target=3000)
        assert score_target == 1.0

        score_above = evaluate_retention_length_score(word_count=5000, words_min=2600, words_max=None, words_target=3000)
        assert score_above == 1.0

        score_between = evaluate_retention_length_score(word_count=2800, words_min=2600, words_max=None, words_target=3000)
        assert 0.80 <= score_between <= 1.0

    def test_custom_bounds_and_parameters(self):
        score = evaluate_retention_length_score(word_count=500, words_min=400, words_max=600, words_target=500)
        assert score == 1.0


# ===========================================================================
# 3. Fast Heuristics Orchestration Tests
# ===========================================================================
class TestFastHeuristicsOrchestration:
    """Test suite for evaluate_fast_heuristics."""

    def test_high_engagement_and_good_narrative_passes(self):
        title = "¿Soy la mala por no dejar que mi suegra viva con nosotros?"
        content = " ".join(["palabra"] * 250)  # 250 words
        content = "A las 3 AM descubrí un secreto... " + content

        report = evaluate_fast_heuristics(
            title=title,
            content=content,
            score=600,
            upvote_ratio=0.95,
            num_comments=150,
            lane=None,
            min_heuristic_threshold=0.40,
        )

        assert report.passed_stage1 is True
        assert report.composite_heuristic_score >= 0.80
        assert report.engagement_score >= 0.90
        assert report.hook_score >= 0.70
        assert len(report.rejection_reasons) == 0

    def test_low_engagement_greeting_fluff_fails(self):
        title = "Una duda rápida"
        content = "Hola a todos, este es mi primer post en el sub... " + " ".join(["hola"] * 50)

        report = evaluate_fast_heuristics(
            title=title,
            content=content,
            score=2,
            upvote_ratio=0.50,
            num_comments=1,
            lane=None,
            min_heuristic_threshold=0.40,
        )

        assert report.passed_stage1 is False
        assert report.composite_heuristic_score < 0.40
        assert "composite_heuristic_score_below_threshold" in report.rejection_reasons
        assert any("conversational_greeting" in r for r in report.rejection_reasons)

    def test_comment_velocity_enhances_score(self):
        title = "AITA for leaving the room?"
        content = " ".join(["palabra"] * 250)
        now = time.time()
        one_hour_ago = now - 3600  # 1 hour ago with 50 comments -> 25 comments/hour

        report_with_vel = evaluate_fast_heuristics(
            title=title,
            content=content,
            score=100,
            upvote_ratio=0.85,
            num_comments=50,
            created_utc=one_hour_ago,
        )

        report_no_vel = evaluate_fast_heuristics(
            title=title,
            content=content,
            score=100,
            upvote_ratio=0.85,
            num_comments=50,
            created_utc=None,
        )

        assert report_with_vel.engagement_score >= report_no_vel.engagement_score

    def test_extreme_and_negative_metrics_clamping(self):
        report_extreme = evaluate_fast_heuristics(
            title="Extreme test",
            content=" ".join(["palabra"] * 250),
            score=1_000_000,
            upvote_ratio=2.5,
            num_comments=50_000,
        )
        assert report_extreme.engagement_score == 1.0

        report_neg = evaluate_fast_heuristics(
            title="Negative test",
            content=" ".join(["palabra"] * 250),
            score=-500,
            upvote_ratio=-0.5,
            num_comments=-10,
        )
        assert report_neg.engagement_score == 0.0

    def test_future_timestamp_handling(self):
        now = time.time()
        future_ts = now + 7200  # 2 hours in future
        report = evaluate_fast_heuristics(
            title="Future test",
            content=" ".join(["palabra"] * 250),
            score=100,
            upvote_ratio=0.8,
            num_comments=20,
            created_utc=future_ts,
        )
        assert report.engagement_score > 0.0

    def test_lane_profile_integration(self):
        lane = SimpleNamespace(
            words_min=200,
            words_max=400,
            duration_target_sec=180,
            id="test-shorts-lane",
        )
        content = " ".join(["palabra"] * 300)
        report = evaluate_fast_heuristics(
            title="¿Qué harías en mi lugar?",
            content=content,
            score=300,
            upvote_ratio=0.90,
            num_comments=80,
            lane=lane,
        )

        assert report.retention_length_score == 1.0
        assert report.passed_stage1 is True


# ===========================================================================
# 4. Semantic / Viral Potential Tests
# ===========================================================================
class TestSemanticViralPotential:
    """Test suite for evaluate_semantic_viral_potential and async equivalent."""

    def test_deterministic_horror_alignment(self):
        title = "El Anómalo Incidente en el Sitio 19"
        content = (
            "La contención de la entidad falló a las 03:00 horas. "
            "El espécimen SCP rompió las compuertas de seguridad con un grito aterrador. "
            "Descubrí que la sangre en el búnker pertenecía al personal científico. "
            "Resultó que la pesadilla solo acababa de comenzar."
        )

        report = evaluate_semantic_viral_potential(
            title=title,
            content=content,
            channel_lane="moku-horror-long",
            target_format="longform",
        )

        assert report.dramatic_potential >= 7.0
        assert report.tone_alignment >= 8.0
        assert report.surprise_factor >= 5.0
        assert report.verdict == "ACCEPTED"
        assert report.hook_quality in ("strong", "excellent", "acceptable")
        assert "horror_atmospheric_alignment" in report.detected_viral_hooks

    def test_deterministic_drama_alignment(self):
        title = "¿Soy el malo por exigirle a mi hermano que me devuelva la herencia?"
        content = (
            "Mi familia entró en un conflicto destructivo tras la boda. "
            "Mi esposa y yo descubrimos una infidelidad y engaño financiero. "
            "La discusión escaló cuando me reclamó y exigió más dinero. "
            "Resultó que toda mi familia sabía del plan y la deuda secreta."
        )

        report = evaluate_semantic_viral_potential(
            title=title,
            content=content,
            channel_lane="aelithia-aita-long",
            target_format="longform",
        )

        assert report.dramatic_potential >= 7.0
        assert report.tone_alignment >= 8.0
        assert report.verdict == "ACCEPTED"
        assert "moral_drama_alignment" in report.detected_viral_hooks

    def test_custom_semantic_threshold(self):
        content = "Un relato simple sin grandes giros dramáticos."
        report_strict = evaluate_semantic_viral_potential(
            title="Relato Simple",
            content=content,
            min_semantic_threshold=0.95,
        )
        assert report_strict.verdict == "REJECTED"

        report_lenient = evaluate_semantic_viral_potential(
            title="Relato Simple",
            content=content,
            min_semantic_threshold=0.30,
        )
        assert report_lenient.verdict == "ACCEPTED"

    def test_mock_llm_client_sync(self):
        class MockLLMClient:
            def generate_content(self, prompt: str):
                return SimpleNamespace(
                    text=json.dumps({
                        "dramatic_potential": 9.0,
                        "viewer_retention": 8.5,
                        "surprise_factor": 8.0,
                        "tone_alignment": 9.5,
                        "verdict": "ACCEPTED",
                        "hook_quality": "excellent",
                        "key_strengths": ["High stakes", "Great twist"],
                        "rejection_reasons": []
                    })
                )

        report = evaluate_semantic_viral_potential(
            title="Test Story",
            content="Some narrative content here...",
            client=MockLLMClient(),
        )

        assert report.dramatic_potential == 9.0
        assert report.viewer_retention == 8.5
        assert report.overall_semantic_score >= 0.85
        assert report.verdict == "ACCEPTED"
        assert report.hook_quality == "excellent"

    def test_mock_llm_client_markdown_fences(self):
        class MockMarkdownLLMClient:
            def generate_content(self, prompt: str):
                return SimpleNamespace(
                    text="""```json
                    {
                        "dramatic_potential": 8.0,
                        "viewer_retention": 8.0,
                        "surprise_factor": 7.5,
                        "tone_alignment": 8.5,
                        "verdict": "ACCEPTED",
                        "hook_quality": "strong",
                        "key_strengths": ["Solid arc"],
                        "rejection_reasons": []
                    }
                    ```"""
                )

        report = evaluate_semantic_viral_potential(
            title="Test Story",
            content="Content...",
            client=MockMarkdownLLMClient(),
        )

        assert report.dramatic_potential == 8.0
        assert report.verdict == "ACCEPTED"

    def test_mock_llm_client_error_fallback_deterministic(self):
        class BrokenLLMClient:
            def generate_content(self, prompt: str):
                raise RuntimeError("503 Service Unavailable / Rate Limit Exceeded")

        # Must not raise exception, but fallback seamlessly
        report = evaluate_semantic_viral_potential(
            title="Relato de Miedo",
            content="Un monstruo apareció en el bosque oscuro y rompió la contención.",
            client=BrokenLLMClient(),
        )

        assert report is not None
        assert report.overall_semantic_score > 0.0

    def test_async_evaluate_semantic_viral_potential(self):
        class AsyncMockLLMClient:
            async def generate_content(self, prompt: str):
                await asyncio.sleep(0.01)
                return SimpleNamespace(
                    text=json.dumps({
                        "dramatic_potential": 8.8,
                        "viewer_retention": 9.1,
                        "surprise_factor": 8.2,
                        "tone_alignment": 9.0,
                        "verdict": "ACCEPTED",
                        "hook_quality": "excellent",
                        "key_strengths": ["Async hook"],
                        "rejection_reasons": []
                    })
                )

        report = asyncio.run(
            async_evaluate_semantic_viral_potential(
                title="Async Test Story",
                content="Content...",
                client=AsyncMockLLMClient(),
            )
        )

        assert report.dramatic_potential == 8.8
        assert report.viewer_retention == 9.1
        assert report.verdict == "ACCEPTED"


# ===========================================================================
# 5. Hybrid Scoring Synthesis & Quality Gate Tests
# ===========================================================================
class TestHybridScoringSynthesis:
    """Test suite for compute_hybrid_story_score and filter_and_score_story."""

    def test_compute_hybrid_story_score_formula(self):
        heur = HeuristicScoreReport(
            engagement_score=0.80,
            retention_length_score=0.90,
            hook_score=0.85,
            composite_heuristic_score=0.85,
            passed_stage1=True,
        )
        sem = SemanticScoreReport(
            dramatic_potential=9.0,
            viewer_retention=8.0,
            surprise_factor=8.0,
            tone_alignment=9.0,
            overall_semantic_score=0.85,
            verdict="ACCEPTED",
            hook_quality="excellent",
        )

        # alpha = 0.30 -> 0.30 * 0.85 + 0.70 * 0.85 = 0.85 -> 850 db_rank
        verdict = compute_hybrid_story_score(
            heuristic=heur,
            semantic=sem,
            alpha=0.30,
            hybrid_threshold=0.60,
            story_id="story-123",
        )

        assert verdict.story_id == "story-123"
        assert verdict.passed is True
        assert verdict.hybrid_score == 0.85
        assert verdict.db_rank_score == 850
        assert verdict.rejection_summary == ""

    def test_compute_hybrid_story_score_stage1_failed(self):
        heur = HeuristicScoreReport(
            engagement_score=0.10,
            retention_length_score=0.20,
            hook_score=0.10,
            composite_heuristic_score=0.135,
            passed_stage1=False,
            rejection_reasons=("composite_heuristic_score_below_threshold",),
        )

        verdict = compute_hybrid_story_score(
            heuristic=heur,
            semantic=None,
            alpha=0.30,
            hybrid_threshold=0.60,
            story_id="story-fail",
        )

        assert verdict.passed is False
        assert verdict.hybrid_score == 0.135
        assert verdict.db_rank_score == 135
        assert "composite_heuristic_score_below_threshold" in verdict.rejection_summary

    def test_custom_alpha_weights(self):
        heur = HeuristicScoreReport(
            engagement_score=1.0,
            retention_length_score=1.0,
            hook_score=1.0,
            composite_heuristic_score=1.0,
            passed_stage1=True,
        )
        sem = SemanticScoreReport(
            dramatic_potential=5.0,
            viewer_retention=5.0,
            surprise_factor=5.0,
            tone_alignment=5.0,
            overall_semantic_score=0.50,
            verdict="ACCEPTED",
            hook_quality="acceptable",
        )

        # Pure heuristic (alpha=1.0)
        v_heur = compute_hybrid_story_score(heur, sem, alpha=1.0)
        assert v_heur.hybrid_score == 1.0
        assert v_heur.db_rank_score == 1000

        # Pure semantic (alpha=0.0)
        v_sem = compute_hybrid_story_score(heur, sem, alpha=0.0)
        assert v_sem.hybrid_score == 0.50
        assert v_sem.db_rank_score == 500

    def test_filter_and_score_story_short_circuits_stage2(self):
        class MockClientSpy:
            def __init__(self):
                self.called = False

            def generate_content(self, prompt: str):
                self.called = True
                return SimpleNamespace(text="{}")

        spy = MockClientSpy()
        bad_story = {
            "id": "bad-1",
            "title": "Hola",
            "content": "Hola a todos este es mi primer post...",
            "score": 1,
            "upvote_ratio": 0.3,
            "num_comments": 0,
        }

        verdict = filter_and_score_story(
            story=bad_story,
            llm_client=spy,
            heuristic_threshold=0.40,
        )

        assert verdict.passed is False
        assert verdict.semantic_report is None
        # Verify spy was NOT invoked due to short circuit!
        assert spy.called is False

    def test_filter_and_score_story_full_pipeline_pass_shorts(self):
        good_story = {
            "id": "good-101",
            "title": "¿Soy el malo por negarme a vender la casa que heredé de mi abuelo?",
            "content": (
                "A las 3 AM recibí una llamada de mi hermano exigiendo que firmara los papeles. "
                "Descubrí que había acumulado una deuda secreta y planeaba una traición familiar. "
                "La discusión escaló y toda mi familia me presionó para ceder ante la amenaza. "
                "Resultó que toda mi familia sabía del plan y querían engañarme. "
                + " ".join(["Palabras adicionales de contexto sobre el conflicto familiar y la herencia."] * 18)
            ),
            "score": 850,
            "upvote_ratio": 0.94,
            "num_comments": 220,
        }

        verdict = filter_and_score_story(
            story=good_story,
            lane="aelithia-aita-shorts",
            heuristic_threshold=0.40,
            semantic_threshold=0.65,
            hybrid_threshold=0.60,
        )

        assert verdict.passed is True
        assert verdict.hybrid_score >= 0.65
        assert verdict.db_rank_score >= 650
        assert verdict.heuristic_report.passed_stage1 is True
        assert verdict.semantic_report is not None
        assert verdict.semantic_report.verdict == "ACCEPTED"

    def test_filter_and_score_story_full_pipeline_pass_longform(self):
        long_content = (
            "A las 3 AM escuché ruidos inquietantes provenientes del búnker subterráneo del Sitio 19. "
            "La contención de la entidad falló repentinamente provocando una emergencia crítica y sangre en las paredes. "
            "El informe clasificado reveló secretos oscuros sobre el origen del monstruo. "
            "Resultó que la pesadilla era mucho más aterradora de lo que imaginamos. "
            + " ".join(["Registro detallado de los eventos de contención y testimonios del personal científico."] * 280)
        )
        good_story = {
            "id": "good-long-1",
            "title": "El Incidente SCP en el Búnker 19",
            "content": long_content,
            "score": 950,
            "upvote_ratio": 0.96,
            "num_comments": 350,
        }

        verdict = filter_and_score_story(
            story=good_story,
            lane="moku-horror-long",
            heuristic_threshold=0.40,
            semantic_threshold=0.65,
            hybrid_threshold=0.60,
        )

        assert verdict.passed is True
        assert verdict.hybrid_score >= 0.70
        assert verdict.db_rank_score >= 700
        assert verdict.heuristic_report.passed_stage1 is True
        assert verdict.semantic_report.verdict == "ACCEPTED"

    def test_filter_and_score_story_reddit_key_aliases(self):
        story_reddit = {
            "id": "reddit-key-1",
            "title": "¿Soy el malo por esto?",
            "selftext": (
                "A las 3 AM descubrí una traición y secretos en la familia tras la boda. "
                "La discusión escaló cuando me exigieron dinero. "
                + " ".join(["Detalles adicionales del relato familiar."] * 20)
            ),
            "ups": 700,
            "upvote_ratio": 0.92,
            "comments": 120,
            "created": time.time() - 3600,
        }

        verdict = filter_and_score_story(
            story=story_reddit,
            lane="drama-drama-shorts",
        )

        assert verdict.passed is True
        assert verdict.story_id == "reddit-key-1"
        assert verdict.heuristic_report.engagement_score > 0.80

    def test_filter_and_score_story_with_lane_profile(self):
        lane_obj = LaneProfile(
            id="horror-scp-shorts",
            channel=CanonicalChannel.HORROR,
            story_type="scp",
            orientation="vertical",
            duration_min_sec=60,
            duration_target_sec=150,
            duration_max_sec=180,
            words_min=160,
            words_max=340,
            words_recondense_max=300,
            template="shorts_creepypasta",
            voice_rate="+20%",
            cadence_min_gap_seconds=300,
        )

        story = {
            "id": "scp-lane-1",
            "title": "¿Qué harías si escucharas ruidos en el Sitio 19?",
            "content": (
                "A las 3 AM la anomalía SCP rompió la contención en el búnker. "
                "Descubrí un informe clasificado con sangre fresca. "
                "Resultó que la entidad nunca estuvo segura. "
                + " ".join(["Reporte del investigador en la zona de contención."] * 18)
            ),
            "score": 800,
            "upvote_ratio": 0.95,
            "num_comments": 180,
        }

        verdict = filter_and_score_story(story, lane=lane_obj)
        assert verdict.passed is True
        assert verdict.heuristic_report.retention_length_score >= 0.80

    def test_async_filter_and_score_story(self):
        good_story = {
            "id": "async-good-1",
            "title": "¿Qué harías si descubrieras una anomalía en tu sótano?",
            "content": (
                "A las 3 AM escuché ruidos extraños detrás del muro de contención en el búnker. "
                "Descubrí un informe clasificado SCP con sangre fresca y una amenaza aterradora. "
                "Resultó que la entidad nunca estuvo contenida y la pesadilla comenzó. "
                + " ".join(["Investigación nocturna sobre el espécimen peligroso en el complejo."] * 18)
            ),
            "score": 650,
            "upvote_ratio": 0.92,
            "num_comments": 140,
        }

        verdict = asyncio.run(
            async_filter_and_score_story(
                story=good_story,
                lane="moku-scp-shorts",
            )
        )

        assert verdict.passed is True
        assert verdict.story_id == "async-good-1"
        assert verdict.db_rank_score >= 600

    def test_dataclass_to_dict_serialization(self):
        story = {
            "id": "ser-1",
            "title": "¿Soy el malo?",
            "content": "Contenido de prueba...",
            "score": 100,
            "upvote_ratio": 0.8,
            "num_comments": 20,
        }
        verdict = filter_and_score_story(story)
        v_dict = verdict.to_dict()

        assert isinstance(v_dict, dict)
        assert "story_id" in v_dict
        assert "db_rank_score" in v_dict
        assert "heuristic_report" in v_dict
        # Verify JSON serializable
        json_str = json.dumps(v_dict)
        assert len(json_str) > 0


# ===========================================================================
# 6. Adversarial and Boundary Edge Cases
# ===========================================================================
class TestScoringAdversarialAndBoundaries:
    """Stress tests for edge cases, unicode, large payloads, and missing fields."""

    def test_missing_fields_in_story_dict(self):
        incomplete_story = {}
        verdict = filter_and_score_story(incomplete_story)
        assert verdict.passed is False
        assert verdict.story_id == ""

    def test_giant_story_content(self):
        giant_content = "Palabra clave de terror en el búnker. " * 5000  # ~35,000 words
        story = {
            "id": "giant-1",
            "title": "Historia Gigante",
            "content": giant_content,
            "score": 500,
            "upvote_ratio": 0.9,
            "num_comments": 100,
        }
        verdict = filter_and_score_story(story, lane="moku-scp-shorts")
        # Over word count for shorts should penalize retention length
        assert verdict.heuristic_report.retention_length_score <= 0.50

    def test_unicode_and_emojis(self):
        title = "😱🔥 ¿Soy el malo por negarme a cuidar a mi sobrino? 😈💀"
        content = "Descubrí un secreto familiar terrible y una infidelidad... 👻"
        score, pos, neg = detect_opening_hook_strength(title, content)
        assert score >= 0.70
        assert any("question" in p for p in pos)


# ===========================================================================
# 7. Modular Submodules Decomposition Tests
# ===========================================================================
class TestScoringDecompositionSubmodules:
    """Verifies that subpackage modules models, heuristics, and semantic exist and operate correctly."""

    def test_models_contracts(self):
        from src.core.scoring.models import (
            HeuristicScoreReport,
            SemanticScoreReport,
            StoryScoringVerdict,
            DEFAULT_HEURISTIC_THRESHOLD,
        )
        h = HeuristicScoreReport(
            engagement_score=0.8,
            retention_length_score=0.9,
            hook_score=0.85,
            composite_heuristic_score=0.85,
            passed_stage1=True,
        )
        assert h.passed_stage1 is True
        s = SemanticScoreReport(
            dramatic_potential=8.0,
            viewer_retention=8.0,
            surprise_factor=7.0,
            tone_alignment=8.5,
            overall_semantic_score=0.8,
            verdict="ACCEPTED",
            hook_quality="strong",
        )
        v = StoryScoringVerdict(
            story_id="test-1",
            passed=True,
            hybrid_score=0.82,
            db_rank_score=820,
            heuristic_report=h,
            semantic_report=s,
        )
        assert v.db_rank_score == 820
        assert v.to_dict()["db_rank_score"] == 820

    def test_heuristics_submodule(self):
        from src.core.scoring.heuristics import (
            detect_opening_hook_strength,
            estimate_spoken_seconds,
            evaluate_fast_heuristics,
            evaluate_retention_length_score,
        )
        secs = estimate_spoken_seconds("Esto es una prueba de narración corta.")
        assert secs > 0
        h_score, pos, neg = detect_opening_hook_strength(
            "¿Soy la mala por rechazar la herencia?",
            "Descubrí un secreto terrible sobre mi familia...",
        )
        assert h_score > 0.6
        rep = evaluate_fast_heuristics(
            title="¿Soy la mala?",
            content="Descubrí un secreto terrible... " * 20,
            score=100,
            upvote_ratio=0.9,
            num_comments=30,
        )
        assert rep.passed_stage1 is True

    def test_semantic_submodule(self):
        from src.core.scoring.semantic import (
            evaluate_semantic_viral_potential,
            _evaluate_semantic_deterministically,
        )
        rep = _evaluate_semantic_deterministically(
            title="SCP-173 Brecha de contención",
            content="La criatura anómala escapó del búnker y causó pánico.",
            channel_lane="horror-scp-shorts",
        )
        assert rep.dramatic_potential >= 5.0
        assert rep.tone_alignment >= 5.0

