"""Shared utility functions and helpers for the video production pipeline."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from src.config import SETTINGS
from src.core.domain import JobStatus
from src.core.providers import DriveProof
from src.core.quality import is_spanish_neutral
from src.core.repository import connect
from src.log import get_logger
from src.pipeline.context import PipelineContext

logger = get_logger("pipeline.utils")


def _file_sha256(path: Path) -> str:
    """Compute SHA256 digest of file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _marker(path: Path, run_id: str, *, active: bool, retention_satisfied: bool = False) -> None:
    """Write run status marker JSON to directory."""
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
    """Record multi-story combination mapping in SQLite."""
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for position, story_id in enumerate(story_ids):
            conn.execute(
                "INSERT OR IGNORE INTO run_stories(run_id, story_id, position) VALUES (?, ?, ?)",
                (run_id, story_id, position),
            )
        conn.commit()


def _peak_rss_metric() -> dict:
    """Peak RSS of the pipeline process in MB for resource observability."""
    try:
        import resource

        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {"peak_rss_mb": round(peak_kb / 1024.0, 1)}
    except Exception:
        return {}


def _drive_review_url(proof: DriveProof) -> str:
    """Build private review URL only from a verified DriveProof file id."""
    if not proof.exists or not proof.file_id.strip():
        raise ValueError("Drive proof is not verified")
    return f"https://drive.google.com/file/d/{proof.file_id}/view"


def _should_translate(script: str) -> bool:
    """True when translation pass must run for script."""
    if os.environ.get("ALWAYS_TRANSLATE", "0") == "1":
        return True
    import sys
    pipe_mod = sys.modules.get("src.pipeline")
    checker = getattr(pipe_mod, "is_spanish_neutral", is_spanish_neutral)
    return not checker(script)


def is_pipeline_test_environment() -> bool:
    """Check if executing in test environment, honoring src.pipeline monkeypatches."""
    import sys
    from src.config import is_test_environment as _default_is_test
    pipe_mod = sys.modules.get("src.pipeline")
    checker = getattr(pipe_mod, "is_test_environment", _default_is_test)
    return bool(checker())


def _dispatch_curate_script(*args, **kwargs):
    """Dynamic dispatcher for curate_script supporting test mock injection."""
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
    """Editorial barrier v2: validate early, repair deterministically, then AI."""
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
            break
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


def _catalog_shots_from_manifest(
    manifest: dict[str, Any],
    loop_engine: Any,
    orientation: str,
    channel: str | None = None,
) -> tuple[list[str], list[float], str]:
    """Turn a scene-planner manifest into loop paths + durations (no pixel burn)."""
    from src.agents.shot_mix import assign_roles

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
        cat = sc.get("category") or last_cat
        last_cat = str(cat).strip().lower().replace(" ", "_") or last_cat
        usable.append({"duration": dur, "category": last_cat, "scene": sc})

    roles = assign_roles(len(usable))
    paths: list[str] = []
    durs: list[float] = []
    asset_durations: dict[str, float] = {}
    is_horizontal = str(orientation).strip().lower() in ("horizontal", "16:9", "longform")

    story_meta = manifest.get("story") if isinstance(manifest.get("story"), dict) else {}
    topic = str(
        manifest.get("title")
        or manifest.get("topic")
        or story_meta.get("title")
        or story_meta.get("attribution")
        or manifest.get("hook_text")
        or ""
    )
    scene_text = " ".join(str(sc.get("description") or sc.get("narration") or "") for sc in scenes)
    try:
        from src.core.scenic_detector import extract_story_motifs

        story_motifs = extract_story_motifs(topic, scene_text)
    except Exception:
        story_motifs = []

    for idx, (item, role) in enumerate(zip(usable, roles)):
        dur = float(item["duration"])
        durs.append(dur)
        item["scene"]["director_role"] = role

        exclude = list(asset_durations.keys())
        resolve_kwargs: dict[str, Any] = {
            "allow_fallback": True,
            "orientation": orientation,
            "seed": idx * 79 + 17 if not is_horizontal else idx,
            "exclude_loop_ids": exclude,
        }
        sig = inspect.signature(loop_engine.resolve_loop_video)
        if "channel" in sig.parameters:
            resolve_kwargs["channel"] = channel
        if "motifs" in sig.parameters and story_motifs:
            resolve_kwargs["motifs"] = story_motifs
        if "topic" in sig.parameters and topic:
            resolve_kwargs["topic"] = topic
        if "exclude_loop_ids" not in sig.parameters:
            resolve_kwargs.pop("exclude_loop_ids", None)

        try:
            path = str(loop_engine.resolve_loop_video(item["category"], **resolve_kwargs))
        except TypeError:
            resolve_kwargs.pop("exclude_loop_ids", None)
            resolve_kwargs.pop("channel", None)
            resolve_kwargs.pop("motifs", None)
            resolve_kwargs.pop("topic", None)
            path = str(loop_engine.resolve_loop_video(item["category"], **resolve_kwargs))

        video_exts = getattr(loop_engine, "SUPPORTED_VIDEO_EXTENSIONS", (".mp4", ".webm", ".mov", ".mkv", ".avi"))
        if not is_horizontal:
            if Path(path).suffix.lower() not in video_exts:
                retry_kwargs = dict(resolve_kwargs)
                retry_kwargs.pop("exclude_loop_ids", None)
                try:
                    alt_video = str(loop_engine.resolve_loop_video(item["category"], **retry_kwargs))
                    if Path(alt_video).suffix.lower() in video_exts:
                        path = alt_video
                except Exception:
                    pass
            if Path(path).suffix.lower() not in video_exts and paths:
                video_paths = [p for p in paths if Path(p).suffix.lower() in video_exts]
                if video_paths:
                    path = video_paths[idx % len(video_paths)]

        if paths and path == paths[-1]:
            resolve_kwargs["seed"] = resolve_kwargs.get("seed", idx) + 1
            try:
                alt_path = str(loop_engine.resolve_loop_video(item["category"], **resolve_kwargs))
            except TypeError:
                alt_path = path
            if alt_path == path and channel:
                try:
                    alt_kwargs = dict(resolve_kwargs)
                    if "channel" in sig.parameters:
                        alt_kwargs["channel"] = channel
                    alt_path = str(loop_engine.resolve_loop_video(channel, **alt_kwargs))
                except TypeError:
                    pass
            if alt_path != path:
                if not is_horizontal:
                    if Path(alt_path).suffix.lower() in video_exts:
                        path = alt_path
                else:
                    path = alt_path

        if not is_horizontal:
            offset = float(asset_durations.get(path, 0.0))
            item["scene"]["time_offset"] = offset

        asset_durations[path] = asset_durations.get(path, 0.0) + dur
        paths.append(path)
    return paths, durs, last_cat


def _handle_pipeline_exception(
    exc: Exception,
    *,
    code: str,
    status: JobStatus,
    ctx: PipelineContext,
    retry_delay: int | None = None,
) -> dict[str, Any]:
    """Handle fatal pipeline exceptions with structured error recording."""
    try:
        ctx.profiler.record_error(str(exc), code)
        ctx.profiler.emit_telemetry(db_path=ctx.database)
    except Exception:
        pass
    retry_at = int(time.time()) + retry_delay if retry_delay is not None else None
    if not ctx.set_owned_status(status, error_code=code, error_detail=str(exc), retry_at=retry_at):
        return ctx.lease_lost_result()
    _marker(ctx.work_dir, ctx.run_id, active=False)
    return {
        "status": status.value,
        "story_id": ctx.story_id,
        "run_id": ctx.run_id,
        "reason": str(exc),
        "error": str(exc),
        "error_msg": str(exc),
        "profiling": ctx.profiler.to_dict(),
    }


def _resolve_engine_mode(
    lane: Any,
    video_engine: str | None = None,
    compositor: str | None = None,
) -> tuple[str, bool, bool]:
    """Resolve video composition engine and validate supported modes."""
    engine_mode = (
        video_engine
        or compositor
        or getattr(lane, "video_engine", None)
        or getattr(lane, "visual_pipeline", None)
        or os.environ.get("VIDEO_ENGINE")
        or os.environ.get("COMPOSITION_ENGINE")
        or os.environ.get("COMPOSITOR")
        or os.environ.get("SHORT_COMPOSITOR")
        or getattr(SETTINGS, "short_compositor", None)
        or "loop"
    ).strip().lower()
    is_loop_mode = engine_mode in ("loop", "loop_video", "loop_video_engine", "loop_compositor", "beats")
    is_multiscene_mode = engine_mode in (
        "director",
        "multiscene",
        "multi_scene",
        "multi_scene_compositor",
        "dual_engine",
        "hybrid",
        "procedural",
    )
    force_multiscene = os.environ.get("FORCE_MULTISCENE", "").strip().lower() in ("1", "true", "yes", "on")
    if is_multiscene_mode and not force_multiscene:
        logger.info("Coercing video_engine=%s to loop (set FORCE_MULTISCENE=1 to restore director)", engine_mode)
        engine_mode = "loop"
        is_loop_mode = True
        is_multiscene_mode = False
    if not (is_loop_mode or is_multiscene_mode):
        raise ValueError(
            f"video_engine={engine_mode!r} is not supported. Supported engine modes: 'director', 'multiscene', 'hybrid', or 'loop'."
        )
    return engine_mode, is_loop_mode, is_multiscene_mode


def _prepare_pipeline_paths(run_id: str) -> dict[str, Path]:
    """Resolve canonical filesystem paths for a given pipeline run."""
    work_dir = SETTINGS.work_root / run_id
    return {
        "work_dir": work_dir,
        "audio_path": work_dir / "speech.wav",
        "ass_path": work_dir / "subtitles.ass",
        "srt_path": work_dir / "subtitles.srt",
        "video_path": work_dir / "video.mp4",
        "thumbnail_path": work_dir / "thumbnail.jpg",
        "script_path": work_dir / "script.txt",
        "visual_plan_path": work_dir / "visual_plan.json",
        "metadata_path": work_dir / "metadata.json",
        "scene_manifest_path": work_dir / "scene_manifest.json",
    }


def _apply_resume_plan_checkpoints(
    database: str,
    story_id: str,
    lane_id: str,
    run_id: str,
    paths: dict[str, Path],
) -> None:
    """Inspect and reuse valid checkpoint artifacts from prior runs."""
    try:
        from src.core.checkpoints import CHECKPOINT_KINDS, resume_plan

        plan = resume_plan(str(database), story_id, lane_id, now_run_id=run_id)
        for kind in CHECKPOINT_KINDS:
            src = plan.reusable.get(kind)
            if not src:
                break
            dst = {
                "script": paths["script_path"],
                "audio": paths["audio_path"],
                "subtitles_ass": paths["ass_path"],
                "video": paths["video_path"],
                "thumbnail": paths["thumbnail_path"],
            }[kind]
            if Path(src).resolve() == dst.resolve():
                break
            paths["work_dir"].mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    except Exception:
        logger.warning("Plan de reanudación no disponible; ejecución completa", exc_info=True)

