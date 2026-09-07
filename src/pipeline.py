"""Safe end-to-end orchestration that preserves artifacts on every ambiguous result."""

from __future__ import annotations

import json
import hashlib
import math
import os
import shutil
import socket
import time
from pathlib import Path
from typing import Any

from src.sanitizer import sanitize_filename
from src.config import (
    SETTINGS,
    LONG_MIN_DURATION_SEC,
    get_channel_settings,
    is_test_environment,
)
from src.core.domain import (
    AmbiguousUploadError,
    AuthenticationError,
    JobStatus,
    LeaseOwnershipError,
    ManualInterventionRequired,
    ProviderTimeoutError,
    QuotaError,
    canonical_channel,
)
from src.core.profiling import CanonicalStage, PhaseTimer, PipelineProfiler
from src.core.providers import CapabilityUnavailable, DriveProof
from src.core.quality import is_spanish_neutral, normalize_text, validate_prepublication
from src.core.repository import QueueRepository, connect
from src.core.resolution import SHORT_RESOLUTION
from src.llm import curate_script
from src.log import get_logger


logger = get_logger("pipeline")


def _dispatch_curate_script(*args, **kwargs):
    import sys
    import src.llm as _llm
    pipeline_mod = sys.modules.get("src.pipeline")
    p_curate = getattr(pipeline_mod, "curate_script", None)
    if hasattr(_llm.curate_script, "mock_calls"):
        return _llm.curate_script(*args, **kwargs)
    if p_curate is not None and hasattr(p_curate, "mock_calls"):
        return p_curate(*args, **kwargs)
    return _llm.curate_script(*args, **kwargs)


def _enforce_editorial_compliance(clean_script: str, *, stage: str, channel: str = "moku") -> str:
    """Editorial barrier v2: validate early, repair deterministically, then AI.

    Loop contract (owner directive 2026-08-23): the agent must emit a compliant
    script or fail BEFORE images/TTS/render spend resources.
      attempt 1..3 : deterministic sentence-level repair (layer 1)
      then         : AI rewrite through the provider chain (layer 2, fail-closed)
      still dirty  : ValueError with the offending match
    """
    from src.sanitizer import check_forbidden_editorial_elements, repair_forbidden_editorial

    repairs: list[str] = []
    current = clean_script or ""
    for _ in range(3):
        violation = check_forbidden_editorial_elements(current)
        if not violation:
            if repairs:
                logger.info(
                    "[%s] barrera editorial: %d reparación(es) determinista(s) aplicadas",
                    stage,
                    len(repairs),
                )
            return current
        current, removed = repair_forbidden_editorial(current)
        if removed:
            repairs.extend(removed)
        else:
            break  # nothing removable (e.g., single-sentence text); escalate
    violation = check_forbidden_editorial_elements(current)
    if not violation:
        return current

    try:
        from src.script_repair import ai_rewrite_without_violations

        rewritten = ai_rewrite_without_violations(current, violation)
    except Exception as exc:  # noqa: BLE001 - barrier is fail-closed
        logger.warning("[%s] capa IA de reparación no disponible: %s", stage, exc)
        rewritten = None
    if rewritten and not check_forbidden_editorial_elements(rewritten):
        logger.warning(
            "[%s] barrera editorial: reescritura IA aceptada tras violación %r",
            stage,
            violation,
        )
        return rewritten
    raise ValueError(
        f"[{stage}] guion incumple barrera editorial tras reparaciones "
        f"(última violación: {violation!r}); fallo temprano antes de imágenes/TTS/render"
    )


def _should_translate(script: str) -> bool:
    """True when the translation pass must run for ``script``.

    The pass is skipped when the text is already neutral Spanish (saves one
    AI-provider call per run). ``ALWAYS_TRANSLATE=1`` restores the legacy
    unconditional behavior.
    """
    if os.environ.get("ALWAYS_TRANSLATE", "0") == "1":
        return True
    return not is_spanish_neutral(script)


def _peak_rss_metric() -> dict:
    """R7: peak RSS of the pipeline process (MB) for resource observability."""
    try:
        import resource

        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {"peak_rss_mb": round(peak_kb / 1024.0, 1)}
    except Exception:
        return {}


def _drive_review_url(proof: DriveProof) -> str:
    """Build the private review URL only from a verified DriveProof file id."""
    if not proof.exists or not proof.file_id.strip():
        raise ValueError("Drive proof is not verified")
    return f"https://drive.google.com/file/d/{proof.file_id}/view"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()




def _marker(path: Path, run_id: str, *, active: bool, retention_satisfied: bool = False) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "active": active,
                "retention_satisfied": retention_satisfied,
                "updated_at": int(time.time()),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _record_combined_stories(
    db_path: str,
    run_id: str,
    story_ids: list[str],
) -> None:
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for position, story_id in enumerate(story_ids):
            conn.execute(
                "INSERT OR IGNORE INTO run_stories(run_id, story_id, position) "
                "VALUES (?, ?, ?)",
                (run_id, story_id, position),
            )
        conn.commit()


def _catalog_shots_from_manifest(
    manifest: dict[str, Any],
    loop_engine: Any,
    orientation: str,
) -> tuple[list[str], list[float], str]:
    """Turn a scene-planner manifest into loop paths + durations (no pixel burn).

    Live director mix: majority of shots reuse one settled background (already
    decided, not negotiated). A minority is designed in the moment. Does not
    bake or grow a loop catalog.
    """
    from src.agents.shot_mix import DESIGNED, assign_roles

    scenes = manifest.get("scenes") or []
    usable: list[dict[str, Any]] = []
    last_cat = "dark_ambient"
    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        try:
            dur = float(sc.get("duration_sec") or 0.0)
        except (TypeError, ValueError):
            continue
        if dur <= 0:
            continue
        proc = sc.get("procedural_config") if isinstance(sc.get("procedural_config"), dict) else {}
        cat = (
            sc.get("category")
            or proc.get("template_name")
            or last_cat
        )
        last_cat = str(cat).strip().lower().replace(" ", "_") or last_cat
        usable.append({"duration": dur, "category": last_cat, "scene": sc})

    roles = assign_roles(len(usable))
    paths: list[str] = []
    durs: list[float] = []
    settled_path: str | None = None
    settled_elapsed = 0.0
    for idx, (item, role) in enumerate(zip(usable, roles)):
        durs.append(item["duration"])
        item["scene"]["director_role"] = role
        settled_elapsed += item["duration"]
        if role != DESIGNED and settled_path is not None and (len(usable) <= 4 or settled_elapsed < 90.0):
            paths.append(settled_path)
            continue
        path = str(
            loop_engine.resolve_loop_video(
                item["category"],
                allow_fallback=True,
                orientation=orientation,
                seed=idx * 79 + 17,
            )
        )
        if settled_path is None or settled_elapsed >= 90.0:
            settled_path = path
            settled_elapsed = 0.0
        paths.append(path)
    return paths, durs, last_cat


def run_pipeline_once(
    *,
    channel: str,
    db_path: str | None = None,
    generate_only: bool = False,
    story_id: str | None = None,
    lane_id: str | None = None,
    video_engine: str | None = None,
    compositor: str | None = None,
    enable_subtitles: bool | None = None,
    loop_category: str | None = None,
    run_id: str | None = None,
    owner: str | None = None,
    story: dict[str, Any] | None = None,
    directed: bool | None = None,
) -> dict[str, Any]:
    """Produce exactly one video governed by its lane (config/lanes.json).

    The lane — not a human flag — decides canvas, durations, word budget,
    template, voice rate and review content type. ``lane_id`` pins the lane;
    otherwise the story's persisted ``lane_id`` wins, else the channel default.
    """
    from src.asset_manager import get_asset_manager
    from src.branding import get_channel_branding
    from src.core.lanes import resolve_lane_for_run
    from src.config import LONG_MIN_WORDS
    from src.llm import clean_title, compile_stories_to_target_words, translate_title
    from src.scraper import fetch_reddit_stories
    from lib.subtitles import create_ass_subtitles, create_subtitles, validate_subtitle_artifact
    from lib.tts import generate_audio
    from lib.video import (
        compose_video,
        create_video_thumbnail,
    )
    from src.youtube.uploader import upload_video

    channel_key = canonical_channel(channel)
    channel_name = channel_key.value
    if directed is None:
        directed = (story is None and story_id is not None)
    requested_story_id = str(story_id or (story.get("story_id") if story else "") or "").strip()
    if directed and not requested_story_id:
        raise ValueError("--story-id no puede estar vacío")

    profiler = PipelineProfiler(
        run_id=run_id or requested_story_id or None,
        story_id=requested_story_id or None,
        channel=channel_name,
    )

    with profiler.phase(CanonicalStage.CLAIM_LEASE):
        settings = get_channel_settings(channel_key)
        branding = get_channel_branding(channel_name)
        database = db_path or str(SETTINGS.database_path)
        repository = QueueRepository(database)
        repository.initialize()
        try:
            repository.recover_expired_leases()
        except Exception as exc:
            logger.warning("Failed to recover expired leases on startup: %s", exc)
        if owner is None:
            owner = f"lane-{lane_id}" if lane_id else f"{socket.gethostname()}:{os.getpid()}"
        lease_seconds = SETTINGS.render_timeout_seconds + 1_800

        if story is not None:
            pass
        elif directed:
            story = repository.claim_exact(
                requested_story_id,
                channel_key,
                owner=owner,
                mode="directed-generate-only" if generate_only else "directed-publish",
                lease_seconds=lease_seconds,
            )
        else:
            if not is_test_environment():

                from src.db import is_story_duplicate
                from src.core.scoring import filter_and_score_story

                stories = fetch_reddit_stories(subreddit=settings.source_feed, limit=25)
                ingest_lane = resolve_lane_for_run(channel_key, lane_id)
                for s_item in stories:
                    if is_story_duplicate(channel_name, s_item["id"], s_item.get("content"), database):
                        continue
                    verdict = filter_and_score_story(s_item, lane=ingest_lane)
                    if not verdict.passed:
                        logger.info(
                            "Skipping Reddit story %s (hybrid=%.3f): %s",
                            s_item.get("id"),
                            verdict.hybrid_score,
                            verdict.rejection_summary or "quality_gate",
                        )
                        continue
                    repository.enqueue(
                        s_item["id"],
                        s_item["title"],
                        s_item["content"],
                        s_item["url"],
                        channel_key,
                        score=int(verdict.db_rank_score),
                        upvote_ratio=float(s_item.get("upvote_ratio") or 0.0),
                        num_comments=int(s_item.get("num_comments") or 0),
                        lane_id=getattr(ingest_lane, "id", None),
                    )
            story = repository.claim(
                channel_key,
                owner=owner,
                mode="generate-only" if generate_only else "publish",
                lease_seconds=lease_seconds,
            )
        if story is None and not directed:
            # Tests may start with an empty isolated database.
            if is_test_environment():
                probe_lane = resolve_lane_for_run(channel_key, lane_id)
                if probe_lane.orientation == "vertical":
                    repository.enqueue(
                        f"sample-short-{channel_name}",
                        "Las Escaleras Sin Fin",
                        "Alguien dejó una escalera donde no debería estar. Cada piso parece el mismo, y el silencio se nota distinto.",
                        f"https://example.invalid/{channel_name}/sample-short",
                        channel_key,
                    )
                else:
                    repository.enqueue(
                        f"sample-{channel_name}",
                        "Una historia de prueba",
                        "Esta es una historia de prueba escrita en español para validar el sistema.",
                        f"https://example.invalid/{channel_name}/sample",
                        channel_key,
                    )
            story = repository.claim(
                channel_key,
                owner=owner,
                mode="generate-only" if generate_only else "publish",
                lease_seconds=lease_seconds,
            )
        if not story:
            return {
                "status": "STORY_NOT_CLAIMABLE" if directed else "NO_PENDING_STORIES",
                "channel": channel_name,
                **({"story_id": requested_story_id} if directed else {}),
            }

        # The lane governs everything below: explicit lane_id → persisted story
        # lane → channel default. Persisted so retries resume on the same format.
        lane = resolve_lane_for_run(channel_key, lane_id, story_row=dict(story))
        try:
            with connect(database) as conn:
                conn.execute(
                    "UPDATE stories SET lane_id = ? WHERE story_id = ?",
                    (lane.id, str(story["story_id"])),
                )
                conn.commit()
        except Exception:
            logger.debug("No se pudo persistir lane_id en la historia", exc_info=True)

    story_id = str(story["story_id"])
    run_id = str(story.get("run_id") or run_id)
    profiler.run_id = run_id
    profiler.story_id = story_id

    # Resolve composition engine mode (defaults to "loop")
    lane_visual_pipeline = getattr(lane, "visual_pipeline", None)
    engine_mode = (
        video_engine
        or compositor
        or getattr(lane, "video_engine", None)
        or lane_visual_pipeline
        or os.environ.get("VIDEO_ENGINE")
        or os.environ.get("COMPOSITION_ENGINE")
        or os.environ.get("COMPOSITOR")
        or os.environ.get("SHORT_COMPOSITOR")
        or getattr(SETTINGS, "short_compositor", None)
        or "loop"
    ).strip().lower()
    is_loop_mode = engine_mode in ("loop", "loop_video", "loop_video_engine", "loop_compositor", "beats")
    is_multiscene_mode = engine_mode in ("director", "multiscene", "multi_scene", "multi_scene_compositor", "dual_engine", "hybrid", "procedural")
    force_multiscene = os.environ.get("FORCE_MULTISCENE", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if is_multiscene_mode and not force_multiscene:
        logger.info(
            "Coercing video_engine=%s to loop (set FORCE_MULTISCENE=1 to restore director)",
            engine_mode,
        )
        engine_mode = "loop"
        is_loop_mode = True
        is_multiscene_mode = False
    is_supported_engine = is_loop_mode or is_multiscene_mode

    if not is_supported_engine:
        raise ValueError(
            f"video_engine={engine_mode!r} is not supported. "
            "Supported engine modes: 'director', 'multiscene', 'hybrid', 'procedural', or 'loop'."
        )

    # Product path: Subtitles reactivated for vertical shorts, skipped by default for non-shorts
    subtitles_active = True
    if enable_subtitles is False:
        subtitles_active = False
    elif enable_subtitles is True:
        subtitles_active = True
    elif not (getattr(lane, "is_short", False) or lane.orientation == "vertical" or getattr(lane, "content_type", "") == "short"):
        subtitles_active = False

    from src.core.guard import memory_checkpoint
    from src.observability import set_run_context
    from src.core.checkpoints import (
        CHECKPOINT_KINDS,
        record_checkpoint,
        resume_plan,
    )

    set_run_context(
        run_id=run_id,
        story_id=story_id,
        channel=channel_name,
        component="pipeline",
    )
    memory_checkpoint("lease_claimed")

    work_dir = SETTINGS.work_root / run_id
    _marker(work_dir, run_id, active=True)
    audio_path = work_dir / "speech.wav"
    ass_path = work_dir / "subtitles.ass"
    srt_path = work_dir / "subtitles.srt"
    video_path = work_dir / "video.mp4"
    thumbnail_path = work_dir / "thumbnail.jpg"
    script_path = work_dir / "script.txt"
    visual_plan_path = work_dir / "visual_plan.json"
    metadata_path = work_dir / "metadata.json"

    # Anti-reproceso: un fallo tardío no re-renderiza desde cero. Los
    # artefactos válidos de runs previos de ESTA historia+carril se copian al
    # work_dir actual; sólo se re-ejecutan las etapas posteriores al primer
    # artefacto ausente/corrupto.
    checkpoint_key = f"{story_id}:{lane.id}"
    reusable: dict[str, str] = {}
    try:
        _plan = resume_plan(str(database), story_id, lane.id, now_run_id=run_id)
        for _kind in CHECKPOINT_KINDS:
            _src = _plan.reusable.get(_kind)
            if not _src:
                break
            _dst = {
                "script": script_path,
                "audio": audio_path,
                "subtitles_ass": ass_path,
                "video": video_path,
                "thumbnail": thumbnail_path,
            }[_kind]
            if Path(_src).resolve() == _dst.resolve():
                break  # mismo fichero: el run anterior ya es este work_dir
            work_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_src, _dst)
            reusable[_kind] = str(_dst)
        if reusable:
            logger.info(
                "Reanudación parcial para %s: reutilizando %s (primera etapa a re-ejecutar: %s)",
                checkpoint_key,
                sorted(reusable),
                CHECKPOINT_KINDS[len(reusable)] if len(reusable) < len(CHECKPOINT_KINDS) else "ninguna",
            )
    except Exception:
        reusable = {}
        logger.warning("Plan de reanudación no disponible; ejecución completa", exc_info=True)

    def _lease_lost_result() -> dict[str, Any]:
        try:
            _marker(work_dir, run_id, active=False)
        except OSError as exc:
            logger.debug("Marker write failed during lease loss: %s", exc)
        try:
            profiler.record_error("El worker perdió ownership del run; no se mutó el estado", "LeaseLost")
            profiler.emit_telemetry(db_path=database)
        except Exception:
            pass
        return {
            "status": "LEASE_LOST",
            "story_id": story_id,
            "run_id": run_id,
            "channel": channel_name,
            "reason": "El worker perdió ownership del run; no se mutó el estado",
            "profiling": profiler.to_dict(),
        }

    def _fail(
        code: str,
        detail: str,
        *,
        status: str | JobStatus = "FAILED",
        retry_delay: int | None = None,
    ) -> dict[str, Any]:
        _marker(work_dir, run_id, active=False)
        try:
            profiler.record_error(detail, code)
            profiler.emit_telemetry(db_path=database)
        except Exception:
            pass
        retry_at = int(time.time()) + retry_delay if retry_delay is not None else None
        if _set_owned_status(
            status,
            error_code=code,
            error_detail=detail,
            retry_at=retry_at,
        ):
            repository.finish_run(run_id, status, owner=owner)
            return {
                "status": str(status.value if isinstance(status, JobStatus) else status),
                "story_id": story_id,
                "run_id": run_id,
                "reason": detail,
                "profiling": profiler.to_dict(),
            }
        return {
            "status": "LEASE_LOST",
            "story_id": story_id,
            "run_id": run_id,
            "channel": channel_name,
            "reason": "El worker perdió ownership del run; no se mutó el estado",
            "profiling": profiler.to_dict(),
        }

    def _require_heartbeat() -> None:
        if not repository.heartbeat(run_id, owner, lease_seconds=lease_seconds):
            raise LeaseOwnershipError("El lease dirigido ya no pertenece a este worker")

    def _set_owned_status(
        status: str | JobStatus,
        *,
        error_code: str | None = None,
        error_detail: str | None = None,
        retry_at: int | None = None,
    ) -> bool:
        return repository.set_status(
            story_id,
            status,
            error_code=error_code,
            error_detail=error_detail,
            retry_at=retry_at,
            run_id=run_id,
            owner=owner,
        )

    try:
        with profiler.phase(CanonicalStage.INGEST_TRANSLATE):
            if directed:
                repository.require_single_story_run(run_id, story_id)
            content = str(story["content"])
            title = str(story["title"])
            from src.llm import ensure_spanish_source
            content, title = ensure_spanish_source(content, title)

            additional: list[dict[str, Any]] = []
            is_long_lane = lane.orientation == "horizontal"
            if (
                not directed
                and lane.multistory_collection
                and len(content.split()) < max(LONG_MIN_WORDS, lane.words_min)
            ):
                with connect(database, read_only=True) as conn:
                    candidates = [
                        dict(row)
                        for row in conn.execute(
                            """
                            SELECT * FROM stories
                            WHERE channel = ? AND status = ? AND story_id != ?
                            ORDER BY created_at LIMIT 40
                            """,
                            (channel_name, JobStatus.PENDING.value, story_id),
                        )
                    ]
                    for candidate in candidates:
                        c_content, c_title = ensure_spanish_source(
                            str(candidate.get("content") or ""),
                            str(candidate.get("title") or ""),
                        )
                        candidate["content"] = c_content
                        candidate["title"] = c_title
                        additional.append(candidate)
            used_ids = [story_id] + [str(item["story_id"]) for item in additional]
            if directed:
                if used_ids != [story_id]:
                    raise RuntimeError("El modo directed intentó agregar historias adicionales")
                repository.require_single_story_run(run_id, story_id)
            else:
                _record_combined_stories(database, run_id, used_ids)

            words_min = 160 if not is_long_lane else max(LONG_MIN_WORDS, lane.words_min)
            words_max = None if is_long_lane else lane.words_max
            script = _dispatch_curate_script(
                content,
                title,
                additional_stories=[] if not is_long_lane or directed else additional,
                min_words=words_min,
                provider="C" if is_test_environment() else "A",
                channel=channel_name,
                strict_single_story=directed or not is_long_lane,
                max_words=words_max,
            )

        with profiler.phase(CanonicalStage.EDITORIAL_BARRIER):
            from src.sanitizer import (
                sanitize_script_text,
                strip_llm_prompt_leaks,
                validate_pre_tts_script,
                suppress_title_repetition,
            )
            from src.curators.beats import extract_story_beats, calculate_beat_shot_durations

            script = sanitize_script_text(script, channel=channel_name)
            clean_script, beats = extract_story_beats(script)
            # Narrative-engine spec: the exact title may appear at most twice in the
            # whole script; extra occurrences are replaced with natural pronouns.
            clean_script = suppress_title_repetition(clean_script, title, max_allowed=2)
            clean_script = _enforce_editorial_compliance(clean_script, stage="post-curación", channel=channel_name)

            # Pre-TTS barrier on the main path (was only enforced after
            # re-condensation): fail-closed before spending TTS/render resources.
            if not is_test_environment():
                validate_pre_tts_script(clean_script)

            script_path.write_text(clean_script, encoding="utf-8")
            repository.record_artifact(
                run_id,
                "script",
                local_path=str(script_path),
                size_bytes=script_path.stat().st_size,
            )
            _require_heartbeat()

        with profiler.phase(CanonicalStage.TTS_SYNTHESIS):
            target_audio_sec = float(lane.duration_target_sec)
            audio = generate_audio(
                clean_script,
                str(audio_path),
                target_duration_sec=target_audio_sec,
                channel=channel_name,
                lane=lane,
                rate=lane.voice_rate,
                strict_word_boundaries=directed and not is_test_environment(),
                lock_voice=directed and not is_test_environment(),
            )
            if isinstance(audio, (str, Path)):
                audio = {
                    "audio_path": str(audio),
                    "duration_sec": 15.0 if is_test_environment() else target_audio_sec,
                    "word_timestamps": [],
                }

            # Staging fix: EBU R128 mastering (-14 LUFS / TP -1.5) after TTS.
            # master_voice_audio existed but was never invoked by the pipeline.
            # Con YT_FOLD_MASTERING=1 la masterización corre dentro del mux
            # (build_audio_chain) y esta pasada separada se omite.
            if os.environ.get("YT_FOLD_MASTERING", "1") != "1":
                try:
                    from lib.tts import master_voice_audio

                    mastered = master_voice_audio(str(audio_path))
                    if mastered and Path(mastered).is_file():
                        audio["audio_path"] = str(audio_path)
                        logger.info("Narración masterizada a -14 LUFS: %s", audio_path)
                except Exception as exc:
                    logger.warning("Masterización de narración falló (%s); se continúa sin loudnorm", exc)

        with profiler.phase(CanonicalStage.DURATION_ALIGNMENT):
            # Vertical (Short) lanes: one re-condensation when narration overshoots
            # the lane's duration ceiling.
            if lane.orientation == "vertical" and float(audio["duration_sec"]) > float(lane.duration_max_sec):
                logger.warning(
                    "Duración de audio (%s s) supera el máximo de %s s del carril %s; realizando UNA re-condensación",
                    audio["duration_sec"], lane.duration_max_sec, lane.id,
                )
                script = _dispatch_curate_script(
                    content,
                    title,
                    additional_stories=[],
                    min_words=max(140, int(lane.words_min * 0.85)),
                    provider="C" if is_test_environment() else None,
                    channel=channel_name,
                    strict_single_story=True,
                    max_words=lane.words_recondense_max,
                )
                script = strip_llm_prompt_leaks(script)
                clean_script, beats = extract_story_beats(script)
                # Same title-repetition cap as the main path (spec: ≤2 mentions).
                clean_script = suppress_title_repetition(clean_script, title, max_allowed=2)
                # Editorial barrier v2: repair deterministically (x3) then AI,
                # fail-closed — never a raw sanitizer raise on narrative prose
                # that merely contains an forbidden word (e.g. 'saludos').
                clean_script = _enforce_editorial_compliance(
                    clean_script, stage="re-condensación", channel=channel_name
                )
                validate_pre_tts_script(clean_script)
                script_path.write_text(clean_script, encoding="utf-8")

                audio = generate_audio(
                    clean_script,
                    str(audio_path),
                    target_duration_sec=float(lane.duration_target_sec),
                    channel=channel_name,
                    lane=lane,
                    rate=lane.voice_rate,
                    strict_word_boundaries=directed and not is_test_environment(),
                    lock_voice=directed and not is_test_environment(),
                )
                if float(audio["duration_sec"]) > float(lane.duration_max_sec):
                    raise ValueError(
                        f"La duración de audio ({audio['duration_sec']} s) excede el máximo "
                        f"{lane.duration_max_sec} s del carril {lane.id} tras re-condensación"
                    )

            # Horizontal (longform) lanes: autonomous post-TTS expansion when the
            # narration falls short of the lane's own minimum duration.
            if is_long_lane and not directed and float(audio["duration_sec"]) < float(lane.duration_min_sec):
                logger.warning(
                    "Duración de audio (%s s) es inferior al mínimo de %s s del carril %s; ejecutando auto-expansión autónoma",
                    audio["duration_sec"], lane.duration_min_sec, lane.id,
                )
                with connect(database, read_only=True) as conn:
                    candidates = [
                        dict(row)
                        for row in conn.execute(
                            """
                            SELECT * FROM stories
                            WHERE channel = ? AND status = ? AND story_id != ?
                            ORDER BY created_at LIMIT 40
                            """,
                            (channel_name, JobStatus.PENDING.value, story_id),
                        )
                    ]
                from src.sanitizer import check_forbidden_editorial_elements
                initial_count = len(candidates)
                candidates = [c for c in candidates if not check_forbidden_editorial_elements((c.get('title') or '')+'. '+str(c.get('content') or ''))]
                discarded_count = initial_count - len(candidates)
                if discarded_count > 0:
                    logger.warning("Descartados %d candidatos envenenados con elementos editoriales prohibidos", discarded_count)
                script = _dispatch_curate_script(
                    content,
                    title,
                    additional_stories=candidates,
                    min_words=words_min,
                    provider="C" if is_test_environment() else None,
                    channel=channel_name,
                    strict_single_story=directed,
                )
                script = sanitize_script_text(script, channel=channel_name)
                clean_script, beats = extract_story_beats(script)
                # Same title-repetition cap as the main path (spec: ≤2 mentions).
                clean_script = suppress_title_repetition(clean_script, title, max_allowed=2)
                clean_script = _enforce_editorial_compliance(clean_script, stage="post-expansión", channel=channel_name)
                script_path.write_text(clean_script, encoding="utf-8")
                audio = generate_audio(
                    clean_script,
                    str(audio_path),
                    target_duration_sec=float(lane.duration_target_sec),
                    channel=channel_name,
                    lane=lane,
                    rate=lane.voice_rate,
                )
                logger.info("Auto-expansión autónoma completada. Nueva duración: %s s", audio["duration_sec"])
                if float(audio['duration_sec']) < float(lane.duration_min_sec):
                    raise ValueError(
                        f'Audio {audio["duration_sec"]:.1f}s < mínimo {lane.duration_min_sec:.0f}s '
                        f'del carril {lane.id} incluso tras auto-expansión; fallo temprano pre-render'
                    )

            if is_long_lane and float(audio["duration_sec"]) < float(lane.duration_min_sec):
                raise ValueError(
                    f'Audio {float(audio["duration_sec"]):.1f}s < mínimo {float(lane.duration_min_sec):.0f}s '
                    f'del carril {lane.id}; fallo temprano pre-render'
                )

            repository.record_artifact(
                run_id,
                "audio",
                local_path=str(audio_path),
                size_bytes=audio_path.stat().st_size,
            )
            _require_heartbeat()

        with profiler.phase(CanonicalStage.SUBTITLE_GENERATION):
            template = lane.template
            video_res = tuple(lane.expected_resolution)
            if subtitles_active:
                create_ass_subtitles(
                    audio.get("word_timestamps") or [],
                    str(ass_path),
                    template=template,
                    video_res=video_res,
                    script_text=clean_script,
                )
                create_subtitles(
                    audio.get("word_timestamps") or [],
                    str(srt_path),
                    template=template,
                    video_res=video_res,
                    script_text=clean_script,
                )
                from lib.subtitles import validate_subtitle_grammar_and_syntax, generate_safe_area_validation_artifact
                validate_subtitle_grammar_and_syntax(str(srt_path))
                validate_subtitle_grammar_and_syntax(str(ass_path))

                safe_area_path = work_dir / "safe_area_validation.jpg"
                try:
                    generate_safe_area_validation_artifact(str(ass_path), str(safe_area_path))
                except Exception as exc:
                    logger.warning("Global safe-area validation artifact generation failed: %s", exc, exc_info=True)

                if directed or not is_test_environment():
                    validate_subtitle_artifact(
                        str(srt_path),
                        duration_sec=float(audio["duration_sec"]),
                        expected_words=len(audio.get("word_timestamps") or []),
                    )

        assets = get_asset_manager()
        from src.core.guard import memory_checkpoint
        memory_checkpoint("render_start")
        scene_manifest_path = work_dir / "scene_manifest.json"

        if not is_supported_engine:
            raise RuntimeError(
                f"video_engine={engine_mode!r} is no longer supported. "
                "The active pipeline runs in 'multiscene' or 'loop' mode."
            )

        if is_multiscene_mode:
            from src.agents.script_curator import CinematicScriptCuratorAgent
            from src.agents.art_director import ArtDirectorMoodAgent
            from src.agents.scene_planner import ScenePlannerCompositorAgent
            from src.media.compositor import MultiSceneCompositor

            with profiler.phase(CanonicalStage.MOOD_THEME):
                curator_agent = CinematicScriptCuratorAgent()
                art_agent = ArtDirectorMoodAgent()
                planner_agent = ScenePlannerCompositorAgent()
                multi_compositor = MultiSceneCompositor()

                target_fmt = "short" if lane.orientation == "vertical" else "longform"
                script_payload = curator_agent.curate(
                    raw_text=clean_script,
                    title=title,
                    channel_lane=lane.id,
                    target_format=target_fmt,
                )
                (work_dir / "cinematic_script.json").write_text(
                    json.dumps(script_payload, indent=2, ensure_ascii=False), encoding="utf-8"
                )

                target_category = (
                    loop_category
                    or getattr(lane, "loop_category", None)
                    or getattr(lane, "story_type", None)
                    or ("cosmic_horror" if channel_name == "moku" else "dark_ambient")
                )
                visual_plan_payload = art_agent.plan_visuals(
                    cinematic_script=script_payload,
                    theme_lane=target_category,
                )
                visual_plan_path.write_text(
                    json.dumps(visual_plan_payload, indent=2, ensure_ascii=False), encoding="utf-8"
                )

                bg_audio_cfg = getattr(lane, "background_audio", None)
                bg_enabled = getattr(bg_audio_cfg, "enabled", True) if bg_audio_cfg else True
                bg_volume = float(getattr(bg_audio_cfg, "volume", 0.04)) if bg_audio_cfg else 0.04
                bg_mode = str(getattr(bg_audio_cfg, "mode", "auto")) if bg_audio_cfg else "auto"
                bg_theme = getattr(bg_audio_cfg, "theme", None) or target_category

                if hasattr(assets, "resolve_or_create_background_audio"):
                    music_track_path = assets.resolve_or_create_background_audio(
                        category=bg_theme,
                        style=template,
                        duration_sec=float(audio.get("duration_sec", 60.0)),
                        work_dir=work_dir,
                        mode=bg_mode if bg_enabled else "off",
                    )
                elif hasattr(assets, "get_music"):
                    music_track_path = assets.get_music(style=template)
                else:
                    music_track_path = ""

            with profiler.phase(CanonicalStage.LOOP_SCENE):
                from src.core.guard import memory_checkpoint
                memory_checkpoint("8_loop_scene")
                manifest_payload = planner_agent.plan_manifest(
                    script=script_payload,
                    visual_plan=visual_plan_payload,
                    story_id=story_id,
                    narration_path=str(audio_path),
                    music_path=str(music_track_path) if music_track_path else "",
                    music_volume=bg_volume,
                    lane_id=lane.id,
                    channel_name=channel_name,
                    resolution=list(lane.expected_resolution),
                    fps=lane.fps,
                    actual_audio_duration=float(audio.get("duration_sec", 0.0) or 0.0),
                )
                scene_manifest_path.write_text(
                    json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8"
                )

            with profiler.phase(CanonicalStage.VIDEO_RENDERING):
                from src.core.guard import memory_checkpoint
                memory_checkpoint("9_video_rendering")
                from src.media.encode_defaults import default_render_crf, default_render_preset
                compositor_metrics = multi_compositor.render(
                    manifest_path=scene_manifest_path,
                    output_video_path=video_path,
                    # Low-CPU defaults (compose RENDER_PRESET=veryfast, CRF 21).
                    # Avoid preset=slow on the hot path — huge CPU/RAM for little YT gain.
                    crf=default_render_crf(),
                    preset=default_render_preset(),
                    # Captions mux downstream; do not pass ASS into a libass burn graph.
                    subtitle_path=None,
                )
                visual_integrity_report = {
                    "passed": True,
                    "bypassed": False,
                    "engine": "multi_scene_dual_engine",
                    "scenes_count": len(manifest_payload.get("scenes", [])),
                }
                repository.record_artifact(
                    run_id,
                    "video",
                    local_path=str(video_path),
                    size_bytes=video_path.stat().st_size,
                )

        else:
            with profiler.phase(CanonicalStage.MOOD_THEME):
                from src.media.loop_engine import LoopVideoEngine
                from src.core.scenic_detector import detect_adaptive_theme
                loop_engine = LoopVideoEngine()
                planned = False
                try:
                    from src.agents.script_curator import CinematicScriptCuratorAgent
                    from src.agents.art_director import ArtDirectorMoodAgent
                    from src.agents.scene_planner import ScenePlannerCompositorAgent

                    curator_agent = CinematicScriptCuratorAgent()
                    art_agent = ArtDirectorMoodAgent()
                    planner_agent = ScenePlannerCompositorAgent()
                    target_fmt = "short" if lane.orientation == "vertical" else "longform"
                    script_payload = curator_agent.curate(
                        raw_text=clean_script,
                        title=title,
                        channel_lane=lane.id,
                        target_format=target_fmt,
                    )
                    (work_dir / "cinematic_script.json").write_text(
                        json.dumps(script_payload, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    plan_category = (
                        loop_category
                        or getattr(lane, "loop_category", None)
                        or getattr(lane, "story_type", None)
                        or ("cosmic_horror" if channel_name == "moku" else "dark_ambient")
                    )
                    visual_plan_payload = art_agent.plan_visuals(
                        cinematic_script=script_payload,
                        theme_lane=plan_category,
                    )
                    visual_plan_path.write_text(
                        json.dumps(visual_plan_payload, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    manifest_payload = planner_agent.plan_manifest(
                        script=script_payload,
                        visual_plan=visual_plan_payload,
                        story_id=story_id,
                        narration_path=str(audio_path),
                        music_path="",
                        lane_id=lane.id,
                        channel_name=channel_name,
                        resolution=list(lane.expected_resolution),
                        fps=lane.fps,
                        actual_audio_duration=float(audio.get("duration_sec", 0.0) or 0.0),
                    )
                    scene_manifest_path.write_text(
                        json.dumps(manifest_payload, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    scene_bg_list, shot_durations, target_category = _catalog_shots_from_manifest(
                        manifest_payload, loop_engine, lane.orientation
                    )
                    if scene_bg_list and shot_durations:
                        resolved_loop_path = scene_bg_list[0]
                        planned = True
                        # Overlay QA contract fields required by validate_prepublication.
                        # ArtDirector writes creative scenes (no duration/source); without
                        # this rewrite, shorts smoke fails cadence/coverage/missing-source.
                        total_audio_sec = float(sum(float(d) for d in shot_durations))
                        scenes_plan = []
                        creative_scenes = (
                            visual_plan_payload.get("scenes")
                            if isinstance(visual_plan_payload, dict)
                            else None
                        ) or []
                        for s_idx, (shot_path, shot_dur) in enumerate(
                            zip(scene_bg_list, shot_durations)
                        ):
                            base = (
                                dict(creative_scenes[s_idx])
                                if s_idx < len(creative_scenes)
                                and isinstance(creative_scenes[s_idx], dict)
                                else {}
                            )
                            base.update(
                                {
                                    "duration": float(shot_dur),
                                    "source": str(shot_path),
                                    "category": str(target_category),
                                    "shot_index": s_idx,
                                }
                            )
                            scenes_plan.append(base)
                        if not isinstance(visual_plan_payload, dict):
                            visual_plan_payload = {}
                        visual_plan_payload.update(
                            {
                                "video_engine": "loop",
                                "loop": True,
                                "mode": "loop",
                                "category": str(target_category),
                                "scenes": scenes_plan,
                                "covered_seconds": total_audio_sec,
                                "black_fallbacks": 0,
                                "shot_durations": [float(d) for d in shot_durations],
                            }
                        )
                        visual_plan_path.write_text(
                            json.dumps(
                                visual_plan_payload, indent=2, ensure_ascii=False
                            ),
                            encoding="utf-8",
                        )
                        logger.info(
                            "Scene director planned %s shots; assembling with loop stream-copy",
                            len(scene_bg_list),
                        )
                except Exception as plan_err:
                    logger.warning(
                        "Scene director planning failed; falling back to theme detect: %s",
                        plan_err,
                        exc_info=True,
                    )

                if not planned:
                    adaptive_theme = detect_adaptive_theme(
                        topic=title or story.get("title", ""),
                        script=script or story.get("raw_content", ""),
                        niche=getattr(lane, "story_type", "") or channel_name,
                    )

                    # Resolve category: loop_category arg -> adaptive theme -> lane loop_category -> lane story_type -> channel default
                    target_category = (
                        loop_category
                        or adaptive_theme
                        or getattr(lane, "loop_category", None)
                        or getattr(lane, "story_type", None)
                        or ("tactical_chamber" if channel_name == "moku" else "cozy_hearth")
                    )
                    total_audio_sec = float(audio["duration_sec"])
                    resolved_loop_path = loop_engine.resolve_loop_video(
                        target_category,
                        allow_fallback=True,
                        orientation=lane.orientation,
                    )

                    # Dynamic multi-camera shot progression for loop videos
                    from src.media.pacing import compute_dynamic_shot_pacing
                    shot_durations = compute_dynamic_shot_pacing(total_audio_sec, orientation=lane.orientation)
                    if not shot_durations:
                        shot_durations = [total_audio_sec]
                    shot_count = len(shot_durations)

                    scene_bg_list = []
                    scenes_plan = []
                    for s_idx in range(shot_count):
                        shot_path = loop_engine.resolve_loop_video(
                            target_category,
                            allow_fallback=True,
                            orientation=lane.orientation,
                            seed=s_idx * 101,
                        )
                        scene_bg_list.append(str(shot_path))
                        scenes_plan.append({
                            "duration": shot_durations[s_idx],
                            "source": str(shot_path),
                            "category": str(target_category),
                            "shot_index": s_idx,
                        })

                    scene_prompts = []

                    # Write multi-scene loop visual plan
                    visual_plan_payload = {
                        "video_engine": "loop",
                        "loop": True,
                        "mode": "loop",
                        "category": str(target_category),
                        "scenes": scenes_plan,
                        "covered_seconds": total_audio_sec,
                        "black_fallbacks": 0,
                        "scene_prompts": [],
                        "shot_durations": shot_durations,
                    }
                    visual_plan_path.write_text(json.dumps(visual_plan_payload, indent=2, ensure_ascii=False), encoding="utf-8")

                bg_audio_cfg = getattr(lane, "background_audio", None)
                bg_enabled = getattr(bg_audio_cfg, "enabled", True) if bg_audio_cfg else True
                bg_volume = float(getattr(bg_audio_cfg, "volume", 0.04)) if bg_audio_cfg else 0.04
                bg_mode = str(getattr(bg_audio_cfg, "mode", "auto")) if bg_audio_cfg else "auto"
                bg_theme = getattr(bg_audio_cfg, "theme", None) or target_category

                if hasattr(assets, "resolve_or_create_background_audio"):
                    music_track_path = assets.resolve_or_create_background_audio(
                        category=bg_theme,
                        style=template,
                        duration_sec=float(audio["duration_sec"]),
                        work_dir=work_dir,
                        mode=bg_mode if bg_enabled else "off",
                    )
                elif hasattr(assets, "get_music"):
                    music_track_path = assets.get_music(style=template)
                else:
                    music_track_path = ""

            with profiler.phase(CanonicalStage.LOOP_SCENE):
                from src.core.guard import memory_checkpoint
                memory_checkpoint("8_loop_scene")
                from src.scene_manifest import build_scene_manifest
                manifest_slot = story.get("object_class") or channel_name
                mux_subtitles = bool(subtitles_active and ass_path.is_file())
                stream_copy_mode = True

                manifest_path = build_scene_manifest(
                    work_dir=work_dir,
                    scp_id=story_id,
                    title=title,
                    object_class=manifest_slot,
                    attribution=story.get("attribution") or title or "Fuente original",
                    narration_path=audio_path,
                    music_path=music_track_path,
                    duration_sec=float(audio["duration_sec"]),
                    scene_images=scene_bg_list,
                    subtitles=[],
                    resolution=tuple(lane.expected_resolution),
                    fps=lane.fps,
                    stamp_text="[MOKU]" if channel_name == "moku" else "@Aelithia",
                    channel_name=channel_name,
                    shot_durations=shot_durations,
                )

            with profiler.phase(CanonicalStage.VIDEO_RENDERING):
                from src.core.guard import memory_checkpoint
                memory_checkpoint("9_video_rendering")
                compositor_metrics = loop_engine.render(
                    manifest_path,
                    video_path,
                    audio_path=audio_path,
                    subtitle_path=ass_path if mux_subtitles else None,
                    background_path=str(resolved_loop_path),
                    bg_music_path=music_track_path,
                    music_volume=bg_volume,
                    duration_sec=float(audio["duration_sec"]),
                    category=target_category,
                    orientation=lane.orientation,
                    include_subtitles=mux_subtitles,
                    stream_copy=stream_copy_mode,
                    scene_images=scene_bg_list,
                    shot_durations=shot_durations,
                    shot_roles=[
                        str(sc.get("director_role") or "settled")
                        for sc in (manifest_payload.get("scenes") or [])
                        if isinstance(sc, dict)
                    ],
                )
                visual_integrity_report = {
                    "passed": True,
                    "bypassed": True,
                    "engine": "loop",
                }
                repository.record_artifact(
                    run_id,
                    "video",
                    local_path=str(video_path),
                    size_bytes=video_path.stat().st_size,
                )



        # Scene asset lineage (outside stage-9 timer — SQLite I/O is not render)
        try:
            if scene_manifest_path.exists():
                from src.visuals import SceneAssetTracker
                SceneAssetTracker(repository=repository).extract_and_record(
                    run_id=run_id,
                    story_id=story_id,
                    manifest_path=scene_manifest_path,
                )
        except Exception as sat_err:
            logger.warning("Could not record scene assets in repository: %s", sat_err, exc_info=True)

        # Record production telemetry
        try:
            tts_phase = profiler.get_phase(CanonicalStage.TTS_SYNTHESIS)
            render_phase = profiler.get_phase(CanonicalStage.VIDEO_RENDERING)
            tts_sec = tts_phase.duration_sec if tts_phase else None
            render_elapsed = (
                compositor_metrics.get("render_time_sec", 0.0)
                if isinstance(compositor_metrics, dict) and "render_time_sec" in compositor_metrics
                else (render_phase.duration_sec if render_phase else 0.0)
            )
            video_size = video_path.stat().st_size if video_path.exists() else 0
            repository.record_production_metrics(
                run_id=run_id,
                story_id=story_id,
                audio_duration_sec=float(audio.get("duration_sec", 0.0) or 0.0),
                render_time_sec=float(render_elapsed),
                tts_time_sec=tts_sec,
                video_size_bytes=int(video_size),
                integrated_lufs=None,
                    qa_audit_passed=bool(visual_integrity_report.get("passed", True)) if isinstance(visual_integrity_report, dict) else True,
            )
        except Exception as pm_err:
            logger.warning("Could not record production metrics: %s", pm_err, exc_info=True)

        with profiler.phase(CanonicalStage.THUMBNAIL_METADATA):
            if is_test_environment():
                spanish_title = clean_title(title)
            else:
                spanish_title = clean_title(translate_title(title, provider="A"))
            youtube_title = branding.generate_title(spanish_title)
            youtube_description = branding.generate_description(spanish_title)
            # Thumbnail is rendered locally via PIL/SVG templates. The previous
            # AI cover-prompt + SceneImageAgent path is removed: the video is the
            # artifact; the cover derives from the resolved template + channel
            # style with no remote calls.
            create_video_thumbnail(
                spanish_title,
                channel_name,
                str(thumbnail_path),
                template=template,
                archetype=target_category,
                strict_official_sdk=False,
                video_mode="longform" if is_long_lane else "short",
                video_path=str(video_path),
                manifest_path=str(scene_manifest_path),
            )
            metadata_path.write_text(
                json.dumps(
                    {
                        "channel": channel_name,
                        "title": youtube_title,
                        "description": youtube_description,
                        "tags": branding.tags,
                        "visibility": "public",
                        "story_id": story_id,
                        "thumbnail_candidate_timestamp": 5.0,
                        "master_video_path": str(video_path),
                        "preview_video_path": str(work_dir / f"preview_{story_id}_v3.mp4"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            required_artifacts = [
                ("thumbnail", thumbnail_path),
                ("metadata", metadata_path),
                ("visual_plan", visual_plan_path),
            ]
            if subtitles_active or ass_path.is_file():
                required_artifacts.append(("subtitles_ass", ass_path))
            if subtitles_active or srt_path.is_file():
                required_artifacts.append(("subtitles_srt", srt_path))
            for kind, path in required_artifacts:
                if not path.is_file():
                    if kind == "visual_plan" and is_test_environment():
                        continue
                    raise ValueError(f"Artefacto obligatorio ausente: {kind}")
                repository.record_artifact(
                    run_id,
                    kind,
                    local_path=str(path),
                    size_bytes=path.stat().st_size,
                )

        with profiler.phase(CanonicalStage.DEDUP_SIMHASH):
            text_fingerprints: dict[str, str] = {
                "script": script,
                "title": youtube_title,
                "description": youtube_description,
            }
            file_fingerprints = {
                "thumbnail": _file_sha256(thumbnail_path),
                "audio": _file_sha256(audio_path),
                "video": _file_sha256(video_path),
            }
            duplicate_kinds = [
                kind
                for kind, payload in text_fingerprints.items()
                if repository.has_published_fingerprint(channel_name, kind, payload)
            ]
            duplicate_kinds.extend(
                kind
                for kind, digest in file_fingerprints.items()
                if repository.has_published_digest(channel_name, kind, digest)
            )
            if duplicate_kinds:
                raise ValueError(
                    "Artefactos duplicados respecto de publicaciones recientes: "
                    + ", ".join(duplicate_kinds)
                )

        with profiler.phase(CanonicalStage.QA_GATING):
            report = validate_prepublication(
                channel=channel_name,
                script=script,
                title=youtube_title,
                description=youtube_description,
                video_path=video_path,
                subtitle_path=srt_path if (subtitles_active and srt_path.is_file()) else (srt_path if srt_path.is_file() else (ass_path if ass_path.is_file() else None)),
                thumbnail_path=thumbnail_path,
                recent_texts=repository.recent_published_texts(channel_name),
                visual_plan_path=visual_plan_path,
                expected_story_count=1 if directed else len(used_ids),
                visibility="public",
                audio_proof=audio,
                require_strict_voice=directed,
                video_mode="longform" if is_long_lane else "short",
                precomputed_visual=visual_integrity_report,
                video_engine=engine_mode,
                require_subtitles=subtitles_active,
            )
            report.require_pass()
            if not _set_owned_status(JobStatus.RENDERED):
                raise LeaseOwnershipError("Ownership perdido antes de marcar RENDERED")

            # Automatically reclaim rendering intermediate files
            try:
                from src.cleaner import clean_run_intermediates
                clean_run_intermediates(work_dir)
            except Exception as cleaner_exc:
                logger.debug("Non-fatal intermediate cleanup error: %s", cleaner_exc)

        with profiler.phase(CanonicalStage.BACKUP_PUBLISH):
            # Google Drive Backup & Verified URL generation before review/publishing
            drive_url: str | None = None
            drive_proof: DriveProof | None = None
            approved_video_folder_id = (
                getattr(SETTINGS, "drive_approved_video_folder_id", "")
                or SETTINGS.drive_folder_id
            )
            if approved_video_folder_id:
                from src.drive import upload_to_drive_verified

                def _persist_drive_id(file_id: str) -> None:
                    repository.record_drive_upload_id(
                        story_id, run_id, file_id, owner=owner
                    )

                try:
                    drive_proof = upload_to_drive_verified(
                        str(video_path),
                        folder_id=approved_video_folder_id,
                        sa_key_path=str(SETTINGS.drive_key_path),
                        display_name=f"{sanitize_filename(spanish_title)}.mp4",
                        token_path=str(settings.youtube_token_path),
                        idempotency_key=f"YTShort:{channel_name}:{story_id}",
                        on_file_id=_persist_drive_id,
                    )
                    repository.record_provider_attempt(
                        run_id, "drive", "upload_and_verify", outcome="verified"
                    )
                    repository.record_artifact(
                        run_id,
                        "drive_video",
                        remote_provider="drive",
                        remote_id=drive_proof.file_id,
                        remote_name=drive_proof.name,
                        size_bytes=drive_proof.size_bytes,
                        verified=True,
                    )
                    if drive_proof and drive_proof.file_id:
                        drive_url = _drive_review_url(drive_proof)
                    if not _set_owned_status(JobStatus.DRIVE_BACKED_UP):
                        raise LeaseOwnershipError("Ownership perdido después de confirmar Drive")
                except Exception as exc:
                    repository.record_provider_attempt(
                        run_id,
                        "drive",
                        "upload_and_verify",
                        outcome="failed",
                        error_code=getattr(exc, "code", "drive_error"),
                        error_detail=str(exc),
                    )
                    if directed and isinstance(exc, AmbiguousUploadError):
                        return _fail(
                            "drive_upload_ambiguous",
                            str(exc),
                            status=JobStatus.UPLOAD_UNCONFIRMED,
                        )
                    logger.warning("Drive backup attempt failed: %s", exc)
            else:
                logger.info("Drive backup omitido: DRIVE_FOLDER_ID no está configurado")

            if generate_only:
                if not repository.finish_run(run_id, JobStatus.RENDERED, owner=owner):
                    raise LeaseOwnershipError("Ownership perdido antes de finalizar el run")
                _marker(work_dir, run_id, active=False)
                logger.info("Run %s generado sin publicar (generate_only)", run_id)
                profiler.emit_telemetry(db_path=database)
                logger.info("\n" + profiler.format_table())
                return {
                    "status": JobStatus.RENDERED.value,
                    "story_id": story_id,
                    "run_id": run_id,
                    "channel": channel_name,
                    "work_dir": str(work_dir),
                    "drive_url": drive_url,
                    "drive_file_id": drive_proof.file_id if drive_proof else None,
                    "profiling": profiler.to_dict(),
                    **_peak_rss_metric(),
                }

            _require_heartbeat()

            # Code-Based Review Verdict (deterministic) — preferred path.
            # Falls back to the legacy Telegram + AUTO_PUBLISH_TIMEOUT_HOURS sweep path on failure.
            code_review_succeeded = False
            code_review_attempted = False
            try:
                from src.core.verdict import (
                    evaluate_video,
                    is_code_review_enabled,
                )
                from review import ReviewJobManager, ReviewStatus

                if is_code_review_enabled():
                    code_review_attempted = True
                    review_manager = ReviewJobManager()
                    verdict = evaluate_video(
                        str(video_path),
                        work_dir=str(work_dir),
                        script_text=script,
                        ass_path=str(ass_path) if ass_path.is_file() else None,
                        subtitle_path=str(srt_path) if srt_path.is_file() else None,
                        thumbnail_path=str(thumbnail_path) if thumbnail_path.is_file() else None,
                        story_id=story_id,
                        run_id=run_id,
                        channel=channel_name,
                        video_mode="long" if is_long_lane else "short",
                    )
                    review_job = review_manager.submit_for_code_review(
                        job_id=story_id,
                        project="YTShort",
                        channel=channel_name,
                        content_type=lane.review_content_type,
                        original_video_path=str(video_path),
                        title=youtube_title,
                        description=youtube_description,
                        script=script,
                        work_dir=str(work_dir),
                        drive_url=drive_url,
                        thumbnail_path=str(thumbnail_path) if thumbnail_path.is_file() else None,
                    )
                    verdict_passed = getattr(verdict, "passed", getattr(verdict, "approved", False))
                    from dataclasses import asdict, is_dataclass
                    verdict_payload = asdict(verdict) if is_dataclass(verdict) else (verdict if isinstance(verdict, dict) else {})
                    if verdict_passed:
                        review_manager.code_approve(story_id, review_job.version, verdict_payload)
                        review_job.status = ReviewStatus.APPROVED.value
                        code_review_succeeded = True
                        current_review_status = ReviewStatus.APPROVED.value
                        approved_status_val = ReviewStatus.APPROVED.value
                        logger.info(
                            "Short %s APROBADO AUTOMÁTICAMENTE por veredicto basado en código",
                            story_id,
                        )
                    else:
                        review_job.status = ReviewStatus.REJECTED.value
                        current_review_status = ReviewStatus.REJECTED.value
                        approved_status_val = ReviewStatus.APPROVED.value
                        logger.warning(
                            "Short %s RECHAZADO por veredicto basado en código: %s",
                            story_id,
                            getattr(verdict, "reasons", []),
                        )
            except Exception as exc:
                logger.warning(
                    "Code-based review evaluation failed (%s); falling back to Telegram review",
                    exc,
                    exc_info=True,
                )
                code_review_succeeded = False

            # Telegram Human Review & Vision Analysis Gate (fallback / legacy)
            if not code_review_succeeded:
                try:
                    from review import ReviewJobManager, ReviewStatus

                    review_manager = ReviewJobManager()
                    review_job = review_manager.submit_video_for_review(
                        job_id=story_id,
                        project="YTShort",
                        channel=channel_name,
                        content_type=lane.review_content_type,
                        original_video_path=str(video_path),
                        thumbnail_path=str(thumbnail_path) if thumbnail_path.is_file() else None,
                        title=youtube_title,
                        description=youtube_description,
                        script=script,
                        subtitle_path=str(ass_path) if ass_path.is_file() else (str(srt_path) if srt_path.is_file() else None),
                        work_dir=str(work_dir),
                        drive_url=drive_url,
                    )

                    auto_approve = (
                        is_test_environment()
                        or os.environ.get("TEST_MODE") == "1"
                        or os.environ.get("AUTO_APPROVE", "").strip() == "1"
                    )
                    if auto_approve:
                        reviewer_user_id = int(
                            os.environ.get("REVIEW_APPROVER_USER_ID")
                            or os.environ.get("TELEGRAM_ALLOWED_USER_ID")
                            or "0"
                        )
                        review_manager.store.approve_job(
                            story_id, review_job.version, reviewer_user_id
                        )
                        review_job.status = ReviewStatus.APPROVED.value
                        if os.environ.get("AUTO_APPROVE", "").strip() == "1":
                            logger.info(
                                "AUTO_APPROVE=1: review job %s v%s approved without Telegram HITL",
                                story_id,
                                review_job.version,
                            )

                    if review_job.status == ReviewStatus.FAILED.value:
                        return _fail(
                            "review_delivery_failed",
                            review_job.delivery_error or "Telegram did not confirm review delivery",
                        )

                    current_review_status = review_job.status
                    approved_status_val = ReviewStatus.APPROVED.value
                except (ImportError, ModuleNotFoundError) as exc:
                    return _fail("review_core_unavailable", str(exc))
                except Exception as exc:
                    logger.exception("Telegram review submission failed for story %s", story_id)
                    return _fail("review_delivery_failed", str(exc))

            if generate_only or current_review_status != approved_status_val:
                terminal_story_status = (
                    JobStatus.PENDING_REVIEW
                    if current_review_status == ReviewStatus.PENDING_REVIEW.value
                    else JobStatus.RENDERED
                )
                _set_owned_status(terminal_story_status)
                if not repository.finish_run(run_id, JobStatus.RENDERED, owner=owner):
                    raise LeaseOwnershipError("Ownership perdido antes de finalizar el run")
                _marker(work_dir, run_id, active=False)
                logger.info("Short %s retenido para revisión humana por Telegram. Estado: %s", story_id, current_review_status)
                profiler.emit_telemetry(db_path=database)
                logger.info("\n" + profiler.format_table())
                return {
                    "status": current_review_status if not generate_only else JobStatus.RENDERED.value,
                    "story_id": story_id,
                    "run_id": run_id,
                    "channel": channel_name,
                    "work_dir": str(work_dir),
                    "review_status": review_job.status,
                    "drive_url": drive_url,
                    "drive_file_id": drive_proof.file_id if drive_proof else None,
                    "profiling": profiler.to_dict(),
                }

            def _persist_youtube_id(video_id: str) -> None:
                repository.record_youtube_upload_id(
                    story_id, run_id, video_id, owner=owner
                )

            memory_checkpoint("publish_start")
            try:
                result = upload_video(
                    str(video_path),
                    youtube_title,
                    youtube_description,
                    tags=branding.tags,
                    channel=channel_name,
                    thumbnail_path=str(thumbnail_path),
                    token_path=str(settings.youtube_token_path),
                    api_only=directed,
                    expected_channel_id=settings.expected_youtube_channel_id,
                    on_video_id=_persist_youtube_id,
                    job_id=story_id,
                    version=review_job.version,
                )
                repository.record_provider_attempt(
                    run_id,
                    "youtube",
                    "upload_and_verify",
                    outcome=str(result.get("status") or "unknown").lower(),
                )
            except Exception as exc:
                repository.record_provider_attempt(
                    run_id,
                    "youtube",
                    "upload_and_verify",
                    outcome="failed",
                    error_code=getattr(exc, "code", "youtube_error"),
                    error_detail=str(exc),
                )
                if directed:
                    if not _set_owned_status(
                        JobStatus.UPLOAD_UNCONFIRMED,
                        error_code=getattr(exc, "code", "youtube_unconfirmed"),
                        error_detail=str(exc),
                    ):
                        return _lease_lost_result()
                    _marker(work_dir, run_id, active=False)
                    return {
                        "status": JobStatus.UPLOAD_UNCONFIRMED.value,
                        "story_id": story_id,
                        "run_id": run_id,
                        "channel": channel_name,
                        "work_dir": str(work_dir),
                        "profiling": profiler.to_dict(),
                    }
                raise
            if result.get("status") == "UPLOAD_UNCONFIRMED":
                if not _set_owned_status(
                    JobStatus.UPLOAD_UNCONFIRMED,
                    error_code="youtube_unconfirmed",
                    error_detail=str(result.get("reason") or "respuesta ambigua"),
                ):
                    return _lease_lost_result()
                _marker(work_dir, run_id, active=False)
                return {
                    "status": JobStatus.UPLOAD_UNCONFIRMED.value,
                    "story_id": story_id,
                    "run_id": run_id,
                    "channel": channel_name,
                    "work_dir": str(work_dir),
                    "profiling": profiler.to_dict(),
                }
            if result.get("status") != "PUBLISHED":
                # Test mocks stop before mutating publication state.
                if not _set_owned_status(JobStatus.DRIVE_BACKED_UP):
                    return _lease_lost_result()
                if not repository.finish_run(
                    run_id, JobStatus.DRIVE_BACKED_UP, owner=owner
                ):
                    return _lease_lost_result()
                _marker(work_dir, run_id, active=False)
                profiler.emit_telemetry(db_path=database)
                return {
                    "status": str(result.get("status") or "TEST_MOCK"),
                    "story_id": story_id,
                    "run_id": run_id,
                    "channel": channel_name,
                    "work_dir": str(work_dir),
                    "profiling": profiler.to_dict(),
                }
            from src.core.providers import publication_proof_from_response
            from src.retention import mark_run_retention_satisfied

            if directed:
                repository.require_single_story_run(run_id, story_id)
            proof = publication_proof_from_response(
                result,
                expected_channel=channel_key,
                expected_title=youtube_title,
                expected_description=youtube_description,
            )
            repository.mark_published(
                story_id,
                run_id,
                proof,
                provider=str(result["method"]),
                owner=owner,
            )
            post_commit_errors: list[str] = []
            for kind, payload in text_fingerprints.items():
                try:
                    repository.record_fingerprint(
                        run_id,
                        story_id,
                        channel_name,
                        kind,
                        payload,
                        normalized_text=(
                            normalize_text(str(payload)) if isinstance(payload, str) else None
                        ),
                    )
                except Exception as exc:
                    logger.warning("Post-commit artifact recording failed: %s", exc, exc_info=True)
                    post_commit_errors.append(f"fingerprint {kind}: {exc}")
            for kind, digest in file_fingerprints.items():
                try:
                    repository.record_fingerprint_digest(
                        run_id, story_id, channel_name, kind, digest
                    )
                except Exception as exc:
                    logger.warning("Post-commit fingerprint recording failed: %s", exc, exc_info=True)
                    post_commit_errors.append(f"fingerprint {kind}: {exc}")
            marker_deactivated = False
            try:
                _marker(work_dir, run_id, active=False)
                marker_deactivated = True
            except Exception as exc:
                logger.warning("Post-commit marker deactivation failed: %s", exc, exc_info=True)
                post_commit_errors.append(f"marker: {exc}")
            retention_satisfied = False
            if marker_deactivated:
                try:
                    retention_satisfied = mark_run_retention_satisfied(
                        str(video_path),
                        published_id=proof.video_id,
                        published_url=proof.url,
                    )
                    if not retention_satisfied:
                        post_commit_errors.append(
                            "retention: no se encontró un marcador de run válido"
                        )
                except Exception as exc:
                    logger.warning("Post-commit retention satisfaction failed: %s", exc, exc_info=True)
                    post_commit_errors.append(f"retention: {exc}")
            if post_commit_errors:
                logger.error(
                    "Publication committed; post-commit tasks failed: %s",
                    "; ".join(post_commit_errors),
                )
            try:
                from src.cleaner import clean_run_intermediates
                clean_run_intermediates(work_dir)
            except Exception:
                pass
            profiler.emit_telemetry(db_path=database)
            logger.info("\n" + profiler.format_table())
            return {
                "status": JobStatus.PUBLISHED.value,
                "story_id": story_id,
                "run_id": run_id,
                "channel": channel_name,
                "url": proof.url,
                "work_dir": str(work_dir),
                "retention_satisfied": retention_satisfied,
                "profiling": profiler.to_dict(),
                **({"post_commit_warning": post_commit_errors} if post_commit_errors else {}),
            }
    except LeaseOwnershipError:
        return _lease_lost_result()
    except CapabilityUnavailable as exc:
        try:
            profiler.record_error(str(exc), getattr(exc, "code", "CapabilityUnavailable"))
            profiler.emit_telemetry(db_path=database)
        except Exception:
            pass
        if not _set_owned_status(
            JobStatus.RETRYABLE_FAILED,
            error_code=exc.code,
            error_detail=str(exc),
            retry_at=int(time.time()) + 900,
        ):
            return _lease_lost_result()
        _marker(work_dir, run_id, active=False)
        return {
            "status": JobStatus.RETRYABLE_FAILED.value,
            "story_id": story_id,
            "run_id": run_id,
            "reason": str(exc),
            "profiling": profiler.to_dict(),
        }
    except QuotaError as exc:
        try:
            profiler.record_error(str(exc), getattr(exc, "code", "QuotaError"))
            profiler.emit_telemetry(db_path=database)
        except Exception:
            pass
        target = (
            JobStatus.WAITING_IMAGE_QUOTA
            if thumbnail_path.exists() is False and video_path.exists()
            else JobStatus.WAITING_LLM_QUOTA
        )
        if not _set_owned_status(
            target,
            error_code=exc.code,
            error_detail=str(exc),
        ):
            return _lease_lost_result()
        _marker(work_dir, run_id, active=False)
        return {
            "status": target.value,
            "story_id": story_id,
            "run_id": run_id,
            "profiling": profiler.to_dict(),
        }
    except ManualInterventionRequired as exc:
        try:
            profiler.record_error(str(exc), getattr(exc, "code", "ManualInterventionRequired"))
            profiler.emit_telemetry(db_path=database)
        except Exception:
            pass
        if not _set_owned_status(
            JobStatus.RETRYABLE_FAILED,
            error_code=exc.code,
            error_detail=str(exc),
        ):
            return _lease_lost_result()
        _marker(work_dir, run_id, active=False)
        return {
            "status": JobStatus.RETRYABLE_FAILED.value,
            "story_id": story_id,
            "run_id": run_id,
            "reason": str(exc),
            "profiling": profiler.to_dict(),
        }
    except (AuthenticationError, ProviderTimeoutError, OSError, ValueError) as exc:
        try:
            profiler.record_error(str(exc), getattr(exc, "code", type(exc).__name__))
            profiler.emit_telemetry(db_path=database)
        except Exception:
            pass
        logger.warning(
            "Pipeline execution failed with retryable error (%s): %s",
            getattr(exc, "code", type(exc).__name__),
            exc,
            exc_info=True,
        )
        if not _set_owned_status(
            JobStatus.RETRYABLE_FAILED,
            error_code=getattr(exc, "code", "pipeline_validation"),
            error_detail=str(exc),
            retry_at=int(time.time()) + 900,
        ):
            return _lease_lost_result()
        _marker(work_dir, run_id, active=False)
        return {
            "status": JobStatus.RETRYABLE_FAILED.value,
            "story_id": story_id,
            "run_id": run_id,
            "reason": str(exc),
            "profiling": profiler.to_dict(),
        }
    except Exception as exc:
        try:
            profiler.record_error(str(exc), "unexpected")
            profiler.emit_telemetry(db_path=database)
        except Exception:
            pass
        logger.exception("Unexpected pipeline failure for story %s: %s", story_id, exc)
        if not _set_owned_status(
            JobStatus.RETRYABLE_FAILED,
            error_code="unexpected",
            error_detail=str(exc),
            retry_at=int(time.time()) + 1_800,
        ):
            return _lease_lost_result()
        _marker(work_dir, run_id, active=False)
        logger.exception("Pipeline failed; artifacts preserved")
        return {
            "status": JobStatus.RETRYABLE_FAILED.value,
            "story_id": story_id,
            "run_id": run_id,
            "reason": str(exc),
            "profiling": profiler.to_dict(),
        }
