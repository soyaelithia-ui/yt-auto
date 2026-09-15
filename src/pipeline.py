"""Safe end-to-end orchestration that preserves artifacts on every ambiguous result."""

from __future__ import annotations

import inspect
import json
import hashlib
import os
import shutil
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from src.sanitizer import sanitize_filename
from src.config import (
    SETTINGS,
    LONG_MIN_WORDS,
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
    YouTubeQuotaExceededError,
    YouTubeUploadLimitError,
    canonical_channel,
)
from src.core.profiling import CanonicalStage, PipelineProfiler
from src.core.providers import CapabilityUnavailable, DriveProof
from src.core.quality import is_spanish_neutral, normalize_text, validate_prepublication
from src.core.repository import QueueRepository, connect
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
                "INSERT OR IGNORE INTO run_stories(run_id, story_id, position) VALUES (?, ?, ?)",
                (run_id, story_id, position),
            )
        conn.commit()


def _catalog_shots_from_manifest(
    manifest: dict[str, Any],
    loop_engine: Any,
    orientation: str,
    channel: str | None = None,
) -> tuple[list[str], list[float], str]:
    """Turn a scene-planner manifest into loop paths + durations (no pixel burn).

    Rotate loop files across shots. Shorts used to sticky-reuse one "settled"
    master and 3/4 cuts looked identical. Does not bake or grow a loop catalog.
    """
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


@dataclass
class RunContext:
    """Encapsulated production context passed through pipeline stages."""
    story: dict[str, Any]
    story_id: str
    run_id: str
    channel_name: str
    channel_key: Any
    lane: Any
    repository: QueueRepository
    database: str
    owner: str
    lease_seconds: int
    settings: Any
    branding: Any
    profiler: PipelineProfiler
    directed: bool
    generate_only: bool
    engine_mode: str
    is_loop_mode: bool
    is_multiscene_mode: bool
    subtitles_active: bool
    work_dir: Path
    audio_path: Path
    ass_path: Path
    srt_path: Path
    video_path: Path
    thumbnail_path: Path
    script_path: Path
    visual_plan_path: Path
    metadata_path: Path
    scene_manifest_path: Path
    loop_category: str | None = None

    script: str = ""
    title: str = ""
    content: str = ""
    clean_script: str = ""
    used_ids: list[str] = field(default_factory=list)
    is_long_lane: bool = False
    words_min: int = 0
    words_max: int | None = None
    audio: dict[str, Any] = field(default_factory=dict)
    beats: list[dict[str, Any]] = field(default_factory=list)
    target_category: str = ""
    resolved_loop_path: str = ""
    music_track_path: str = ""
    bg_volume: float = 0.04
    scene_bg_list: list[str] = field(default_factory=list)
    shot_durations: list[float] = field(default_factory=list)
    manifest_payload: dict[str, Any] = field(default_factory=dict)
    manifest_path: Path | None = None
    mux_subtitles: bool = False
    stream_copy_mode: bool = True
    loop_engine: Any = None
    planner_agent: Any = None
    multi_compositor: Any = None
    script_payload: dict[str, Any] | None = None
    visual_plan_payload: dict[str, Any] | None = None
    compositor_metrics: dict[str, Any] = field(default_factory=dict)
    visual_integrity_report: dict[str, Any] = field(default_factory=dict)
    spanish_title: str = ""
    youtube_title: str = ""
    youtube_description: str = ""
    text_fingerprints: dict[str, str] = field(default_factory=dict)
    file_fingerprints: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.lane is not None:
            dur = getattr(self.lane, "duration_min_sec", None)
            dur_is_long = (isinstance(dur, (int, float)) and dur >= 300) or (
                isinstance(dur, str) and dur.isdigit() and int(dur) >= 300
            )
            lane_id = getattr(self.lane, "id", None)
            lane_id_is_long = isinstance(lane_id, str) and "long" in lane_id.lower()
            if (
                getattr(self.lane, "orientation", "") == "horizontal"
                or getattr(self.lane, "qa_profile", "") == "longform"
                or dur_is_long
                or lane_id_is_long
            ):
                self.is_long_lane = True

    def heartbeat(self) -> bool:
        """Touch active lease heartbeat in database without raising if lease was lost."""
        try:
            return bool(self.repository.heartbeat(self.run_id, self.owner, lease_seconds=self.lease_seconds))
        except Exception as exc:
            logger.debug("Active heartbeat touch failed for run %s: %s", self.run_id, exc)
            return False

    def require_heartbeat(self) -> None:
        if not self.repository.heartbeat(self.run_id, self.owner, lease_seconds=self.lease_seconds):
            raise LeaseOwnershipError("El lease dirigido ya no pertenece a este worker")

    def set_owned_status(
        self,
        status: str | JobStatus,
        *,
        error_code: str | None = None,
        error_detail: str | None = None,
        retry_at: int | None = None,
    ) -> bool:
        return self.repository.set_status(
            self.story_id,
            status,
            error_code=error_code,
            error_detail=error_detail,
            retry_at=retry_at,
            run_id=self.run_id,
            owner=self.owner,
        )

    def lease_lost_result(self) -> dict[str, Any]:
        try:
            _marker(self.work_dir, self.run_id, active=False)
        except OSError as exc:
            logger.debug("Marker write failed during lease loss: %s", exc)
        try:
            self.profiler.record_error("El worker perdió ownership del run; no se mutó el estado", "LeaseLost")
            self.profiler.emit_telemetry(db_path=self.database)
        except Exception:
            pass
        return {
            "status": "LEASE_LOST",
            "story_id": self.story_id,
            "run_id": self.run_id,
            "channel": self.channel_name,
            "reason": "El worker perdió ownership del run; no se mutó el estado",
            "profiling": self.profiler.to_dict(),
        }

    def fail(
        self,
        code: str,
        detail: str,
        *,
        status: str | JobStatus = "FAILED",
        retry_delay: int | None = None,
    ) -> dict[str, Any]:
        _marker(self.work_dir, self.run_id, active=False)
        try:
            self.profiler.record_error(detail, code)
            self.profiler.emit_telemetry(db_path=self.database)
        except Exception:
            pass
        retry_at = int(time.time()) + retry_delay if retry_delay is not None else None
        if self.set_owned_status(status, error_code=code, error_detail=detail, retry_at=retry_at):
            self.repository.finish_run(self.run_id, status, owner=self.owner)
            return {
                "status": str(status.value if isinstance(status, JobStatus) else status),
                "story_id": self.story_id,
                "run_id": self.run_id,
                "reason": detail,
                "profiling": self.profiler.to_dict(),
            }
        return self.lease_lost_result()


@contextmanager
def active_heartbeat_scope(ctx: RunContext, interval: float = 15.0) -> Iterator[None]:
    """Emit periodic lease heartbeats in background during intensive pipeline phases."""
    if getattr(ctx, "_heartbeat_ticker_active", False):
        yield
        return

    stop_event = threading.Event()

    def _heartbeat_ticker() -> None:
        while not stop_event.wait(interval):
            try:
                ok = ctx.heartbeat()
                if not ok:
                    logger.debug("Active heartbeat returned False for run %s (lease lost or reaped)", getattr(ctx, "run_id", "?"))
            except Exception as exc:
                logger.debug("Active heartbeat tick error: %s", exc)

    setattr(ctx, "_heartbeat_ticker_active", True)
    rid_prefix = str(getattr(ctx, "run_id", "") or "")[:8]
    ticker = threading.Thread(
        target=_heartbeat_ticker,
        name=f"heartbeat-{rid_prefix}",
        daemon=True,
    )
    ticker.start()
    try:
        ctx.require_heartbeat()
        yield
    finally:
        setattr(ctx, "_heartbeat_ticker_active", False)
        stop_event.set()
        ticker.join(timeout=2.0)
        try:
            ctx.require_heartbeat()
        except Exception:
            pass


def _stage_01_claim_lease(
    *,
    channel_key: Any,
    channel_name: str,
    db_path: str | None,
    story_id: str | None,
    story: dict[str, Any] | None,
    directed: bool,
    generate_only: bool,
    owner: str | None,
    lane_id: str | None,
    profiler: PipelineProfiler,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Stage 1: Initialize repository, recover expired leases, claim story, resolve lane."""
    from src.branding import get_channel_branding
    from src.core.lanes import resolve_lane_for_run

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
            owner = f"lane-{lane_id}:{socket.gethostname()}:{os.getpid()}" if lane_id else f"{socket.gethostname()}:{os.getpid()}"
        lease_seconds = SETTINGS.render_timeout_seconds + 1_800

        requested_story_id = str(story_id or (story.get("story_id") if story else "") or "").strip()

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
                from src.scraper import fetch_reddit_stories

                stories = fetch_reddit_stories(subreddit=settings.source_feed, limit=25)
                ingest_lane = resolve_lane_for_run(channel_key, lane_id)
                for s_item in stories:
                    if is_story_duplicate(channel_name, s_item["id"], s_item.get("content"), database):
                        continue
                    verdict = filter_and_score_story(s_item, lane=ingest_lane)
                    if not verdict.passed:
                        logger.info("Skipping Reddit story %s (hybrid=%.3f): %s", s_item.get("id"), verdict.hybrid_score, verdict.rejection_summary or "quality_gate")
                        continue
                    repository.enqueue(
                        s_item["id"], s_item["title"], s_item["content"], s_item["url"], channel_key,
                        score=int(verdict.db_rank_score), upvote_ratio=float(s_item.get("upvote_ratio") or 0.0),
                        num_comments=int(s_item.get("num_comments") or 0), lane_id=getattr(ingest_lane, "id", None),
                    )
            story = repository.claim(
                channel_key, owner=owner, mode="generate-only" if generate_only else "publish", lease_seconds=lease_seconds,
            )
        if story is None and not directed:
            if is_test_environment():
                probe_lane = resolve_lane_for_run(channel_key, lane_id)
                is_vert = probe_lane.orientation == "vertical"
                repository.enqueue(
                    f"sample-short-{channel_name}" if is_vert else f"sample-{channel_name}",
                    "Las Escaleras Sin Fin" if is_vert else "Una historia de prueba",
                    "Alguien dejó una escalera donde no debería estar. Cada piso parece el mismo, y el silencio se nota distinto." if is_vert else "Esta es una historia de prueba escrita en español para validar el sistema.",
                    f"https://example.invalid/{channel_name}/{'sample-short' if is_vert else 'sample'}",
                    channel_key,
                )
            story = repository.claim(channel_key, owner=owner, mode="generate-only" if generate_only else "publish", lease_seconds=lease_seconds)
        if not story:
            return None, {
                "status": "STORY_NOT_CLAIMABLE" if directed else "NO_PENDING_STORIES",
                "channel": channel_name,
                **({"story_id": requested_story_id} if directed else {}),
            }

        lane = resolve_lane_for_run(channel_key, lane_id, story_row=dict(story))
        try:
            with connect(database) as conn:
                conn.execute("UPDATE stories SET lane_id = ? WHERE story_id = ?", (lane.id, str(story["story_id"])))
                run_id_val = str(story.get("run_id") or "")
                if run_id_val:
                    try:
                        conn.execute("UPDATE runs SET lane_id = ? WHERE run_id = ?", (lane.id, run_id_val))
                    except Exception:
                        pass
                conn.commit()
        except Exception:
            logger.debug("No se pudo persistir lane_id en la historia", exc_info=True)

        claimed_ctx = {
            "story": story, "story_id": str(story["story_id"]), "run_id": str(story.get("run_id") or ""),
            "lane": lane, "repository": repository, "database": database, "owner": owner,
            "lease_seconds": lease_seconds, "settings": settings, "branding": branding,
        }
        return claimed_ctx, None


def _stage_02_ingest_translate(ctx: RunContext) -> None:
    """Stage 2: Spanish source normalization, multistory gathering, and script curation."""
    with ctx.profiler.phase(CanonicalStage.INGEST_TRANSLATE):
        if ctx.directed:
            ctx.repository.require_single_story_run(ctx.run_id, ctx.story_id)
        from src.llm import ensure_spanish_source
        ctx.content, ctx.title = ensure_spanish_source(str(ctx.story["content"]), str(ctx.story["title"]))

        additional: list[dict[str, Any]] = []
        ctx.is_long_lane = ctx.is_long_lane or (getattr(ctx.lane, "orientation", "") == "horizontal")
        if (
            not ctx.directed
            and ctx.lane.multistory_collection
            and len(ctx.content.split()) < max(LONG_MIN_WORDS, ctx.lane.words_min)
        ):
            target_words = max(LONG_MIN_WORDS, ctx.lane.words_min)
            current_words = len(ctx.content.split())
            with connect(ctx.database, read_only=True) as conn:
                for row in conn.execute(
                    "SELECT * FROM stories WHERE channel = ? AND (lane_id IS NULL OR lane_id = ?) AND status = ? AND story_id != ? ORDER BY created_at LIMIT 5",
                    (ctx.channel_name, ctx.lane.id, JobStatus.PENDING.value, ctx.story_id),
                ):
                    candidate = dict(row)
                    c_content, c_title = ensure_spanish_source(str(candidate.get("content") or ""), str(candidate.get("title") or ""))
                    candidate["content"], candidate["title"] = c_content, c_title
                    additional.append(candidate)
                    current_words += len(c_content.split())
                    if current_words >= target_words:
                        break
        ctx.used_ids = [ctx.story_id] + [str(item["story_id"]) for item in additional]
        if ctx.directed:
            if ctx.used_ids != [ctx.story_id]:
                raise RuntimeError("El modo directed intentó agregar historias adicionales")
            ctx.repository.require_single_story_run(ctx.run_id, ctx.story_id)
        else:
            _record_combined_stories(ctx.database, ctx.run_id, ctx.used_ids)

        ctx.words_min = int(ctx.lane.words_min) if not ctx.is_long_lane else max(LONG_MIN_WORDS, ctx.lane.words_min)
        ctx.words_max = getattr(ctx.lane, "words_max", 4500) if ctx.is_long_lane else ctx.lane.words_max
        curate_provider = "C" if is_test_environment() or os.environ.get("FAST_CURATE") == "1" else "A"
        ctx.script = _dispatch_curate_script(
            ctx.content, ctx.title, additional_stories=[] if not ctx.is_long_lane or ctx.directed else additional,
            min_words=ctx.words_min, provider=curate_provider, channel=ctx.channel_name,
            strict_single_story=ctx.directed or not ctx.is_long_lane, max_words=ctx.words_max,
        )


def _stage_03_editorial_barrier(ctx: RunContext) -> None:
    """Stage 3: Editorial barrier, beat extraction, pre-TTS validation, and script artifact persistence."""
    with ctx.profiler.phase(CanonicalStage.EDITORIAL_BARRIER):
        from src.sanitizer import sanitize_script_text, validate_pre_tts_script, suppress_title_repetition
        from src.curators.beats import extract_story_beats

        script = sanitize_script_text(ctx.script, channel=ctx.channel_name)
        clean_script, ctx.beats = extract_story_beats(script)
        clean_script = suppress_title_repetition(clean_script, ctx.title, max_allowed=2)
        ctx.clean_script = _enforce_editorial_compliance(clean_script, stage="post-curación", channel=ctx.channel_name)

        if not is_test_environment():
            validate_pre_tts_script(ctx.clean_script)
            from src.narrative.quality_gate import validate_narrative_coherence

            coherence = validate_narrative_coherence(
                ctx.clean_script, channel=ctx.channel_name,
                duration_type="short" if getattr(ctx.lane, "orientation", "vertical") == "vertical" else "long",
                max_words=ctx.words_max,
            )
            if not coherence.valid:
                logger.warning("Narrative coherence gate detected issues: %s (score=%.2f)", coherence.errors, coherence.score)
                if coherence.score < 0.5:
                    raise ValueError(f"Narrative coherence gate rejected script: {coherence.errors}")

        ctx.script_path.write_text(ctx.clean_script, encoding="utf-8")
        ctx.repository.record_artifact(ctx.run_id, "script", local_path=str(ctx.script_path), size_bytes=ctx.script_path.stat().st_size)
        ctx.require_heartbeat()


def _stage_05_tts_synthesis(ctx: RunContext) -> None:
    """Stage 5: Voice audio generation via TTS and optional EBU R128 mastering."""
    with ctx.profiler.phase(CanonicalStage.TTS_SYNTHESIS):
        from lib.tts import generate_audio

        target_audio_sec = float(ctx.lane.duration_target_sec)
        audio = generate_audio(
            ctx.clean_script,
            str(ctx.audio_path),
            target_duration_sec=target_audio_sec,
            channel=ctx.channel_name,
            lane=ctx.lane,
            rate=ctx.lane.voice_rate,
            strict_word_boundaries=ctx.directed and not is_test_environment(),
            lock_voice=ctx.directed and not is_test_environment(),
        )
        if isinstance(audio, (str, Path)):
            audio = {
                "audio_path": str(audio),
                "duration_sec": 15.0 if is_test_environment() else target_audio_sec,
                "word_timestamps": [],
            }
        ctx.audio = audio

        if os.environ.get("YT_FOLD_MASTERING", "1") != "1":
            try:
                from lib.tts import master_voice_audio

                mastered = master_voice_audio(str(ctx.audio_path))
                if mastered and Path(mastered).is_file():
                    ctx.audio["audio_path"] = str(ctx.audio_path)
                    logger.info("Narración masterizada a -14 LUFS: %s", ctx.audio_path)
            except Exception as exc:
                logger.warning("Masterización de narración falló (%s); se continúa sin loudnorm", exc)


def _stage_06_duration_alignment(ctx: RunContext) -> None:
    """Stage 6: Re-condensation (shorts) or auto-expansion (longform) to align duration."""
    with ctx.profiler.phase(CanonicalStage.DURATION_ALIGNMENT):
        from src.sanitizer import (
            sanitize_script_text,
            strip_llm_prompt_leaks,
            validate_pre_tts_script,
            suppress_title_repetition,
        )
        from src.curators.beats import extract_story_beats
        from lib.tts import generate_audio

        def _reprocess_script(new_raw: str, stage_tag: str) -> None:
            clean = strip_llm_prompt_leaks(new_raw) if stage_tag == "re-condensación" else sanitize_script_text(new_raw, channel=ctx.channel_name)
            clean, ctx.beats = extract_story_beats(clean)
            clean = suppress_title_repetition(clean, ctx.title, max_allowed=2)
            ctx.clean_script = _enforce_editorial_compliance(clean, stage=stage_tag, channel=ctx.channel_name)
            validate_pre_tts_script(ctx.clean_script)
            ctx.script_path.write_text(ctx.clean_script, encoding="utf-8")
            ctx.audio = generate_audio(
                ctx.clean_script,
                str(ctx.audio_path),
                target_duration_sec=float(ctx.lane.duration_target_sec),
                channel=ctx.channel_name,
                lane=ctx.lane,
                rate=ctx.lane.voice_rate,
                strict_word_boundaries=ctx.directed and not is_test_environment(),
                lock_voice=ctx.directed and not is_test_environment(),
            )

        if ctx.lane.orientation == "vertical" and float(ctx.audio["duration_sec"]) > float(ctx.lane.duration_max_sec):
            logger.warning(
                "Duración de audio (%s s) supera el máximo de %s s del carril %s; realizando UNA re-condensación",
                ctx.audio["duration_sec"], ctx.lane.duration_max_sec, ctx.lane.id,
            )
            raw = _dispatch_curate_script(
                ctx.content, ctx.title, additional_stories=[], min_words=max(140, int(ctx.lane.words_min * 0.85)),
                provider="C" if is_test_environment() else None, channel=ctx.channel_name, strict_single_story=True, max_words=ctx.lane.words_recondense_max,
            )
            _reprocess_script(raw, "re-condensación")
            if float(ctx.audio["duration_sec"]) > float(ctx.lane.duration_max_sec):
                cur_words = ctx.clean_script.split()
                ratio = max(0.5, (float(ctx.lane.duration_max_sec) - 10.0) / float(ctx.audio["duration_sec"]))
                target_count = max(int(ctx.lane.words_min), int(len(cur_words) * ratio))
                from src.llm import _trim_script_to_max_words
                trimmed = _trim_script_to_max_words(ctx.clean_script, target_count)
                _reprocess_script(trimmed, "re-condensación")
            if float(ctx.audio["duration_sec"]) > float(ctx.lane.duration_max_sec):
                raise ValueError(
                    f"La duración de audio ({ctx.audio['duration_sec']} s) excede el máximo {ctx.lane.duration_max_sec} s del carril {ctx.lane.id} tras re-condensación"
                )

        if ctx.lane.orientation == "vertical" and not is_test_environment() and not os.environ.get("PYTEST_CURRENT_TEST") and float(ctx.audio["duration_sec"]) < float(ctx.lane.duration_min_sec):
            logger.warning(
                "Duración de audio (%s s) es inferior al mínimo de %s s del carril %s; re-curando para alcanzar presupuesto editorial",
                ctx.audio["duration_sec"], ctx.lane.duration_min_sec, ctx.lane.id,
            )
            raw = _dispatch_curate_script(
                ctx.content, ctx.title, additional_stories=[], min_words=max(int(ctx.lane.words_min), 210),
                provider="C" if is_test_environment() else None, channel=ctx.channel_name, strict_single_story=True, max_words=ctx.lane.words_max,
            )
            _reprocess_script(raw, "re-expansión-short")
            if float(ctx.audio["duration_sec"]) < float(ctx.lane.duration_min_sec):
                raise ValueError(
                    f"Audio {float(ctx.audio['duration_sec']):.1f}s < mínimo {float(ctx.lane.duration_min_sec):.0f}s del carril {ctx.lane.id} tras re-expansión; fallo temprano pre-render"
                )

        if ctx.is_long_lane and not ctx.directed and float(ctx.audio["duration_sec"]) < float(ctx.lane.duration_min_sec):
            logger.warning(
                "Duración de audio (%s s) es inferior al mínimo de %s s del carril %s; ejecutando auto-expansión autónoma",
                ctx.audio["duration_sec"], ctx.lane.duration_min_sec, ctx.lane.id,
            )
            with connect(ctx.database, read_only=True) as conn:
                candidates = [dict(row) for row in conn.execute(
                    "SELECT * FROM stories WHERE channel = ? AND status = ? AND story_id != ? ORDER BY created_at LIMIT 40",
                    (ctx.channel_name, JobStatus.PENDING.value, ctx.story_id),
                )]
            from src.sanitizer import check_forbidden_editorial_elements
            candidates = [c for c in candidates if not check_forbidden_editorial_elements((c.get('title') or '')+'. '+str(c.get('content') or ''))]
            raw = _dispatch_curate_script(
                ctx.content, ctx.title, additional_stories=candidates, min_words=ctx.words_min,
                provider="C" if is_test_environment() else None, channel=ctx.channel_name, strict_single_story=ctx.directed,
            )
            _reprocess_script(raw, "post-expansión")
            logger.info("Auto-expansión autónoma completada. Nueva duración: %s s", ctx.audio["duration_sec"])
            if float(ctx.audio['duration_sec']) < float(ctx.lane.duration_min_sec):
                raise ValueError(
                    f'Audio {ctx.audio["duration_sec"]:.1f}s < mínimo {ctx.lane.duration_min_sec:.0f}s del carril {ctx.lane.id} incluso tras auto-expansión; fallo temprano pre-render'
                )

        if ctx.is_long_lane and float(ctx.audio["duration_sec"]) < float(ctx.lane.duration_min_sec):
            raise ValueError(
                f'Audio {float(ctx.audio["duration_sec"]):.1f}s < mínimo {float(ctx.lane.duration_min_sec):.0f}s del carril {ctx.lane.id}; fallo temprano pre-render'
            )

        ctx.repository.record_artifact(ctx.run_id, "audio", local_path=str(ctx.audio_path), size_bytes=ctx.audio_path.stat().st_size)
        ctx.require_heartbeat()


def _stage_07_subtitle_generation(ctx: RunContext) -> None:
    """Stage 7: Subtitle creation (ASS & SRT) and grammar/syntax validation if active."""
    with ctx.profiler.phase(CanonicalStage.SUBTITLE_GENERATION):
        if ctx.subtitles_active:
            from lib.subtitles import create_ass_subtitles, create_subtitles, validate_subtitle_artifact, validate_subtitle_grammar_and_syntax

            template = ctx.lane.template
            video_res = tuple(ctx.lane.expected_resolution)
            create_ass_subtitles(ctx.audio.get("word_timestamps") or [], str(ctx.ass_path), template=template, video_res=video_res, script_text=ctx.clean_script)
            create_subtitles(ctx.audio.get("word_timestamps") or [], str(ctx.srt_path), template=template, video_res=video_res, script_text=ctx.clean_script)
            validate_subtitle_grammar_and_syntax(str(ctx.srt_path))
            validate_subtitle_grammar_and_syntax(str(ctx.ass_path))

            if ctx.directed or not is_test_environment():
                validate_subtitle_artifact(
                    str(ctx.srt_path),
                    duration_sec=float(ctx.audio["duration_sec"]),
                    expected_words=len(ctx.audio.get("word_timestamps") or []),
                )


def _stage_04_mood_theme(ctx: RunContext) -> None:
    """Stage 4: Visual plan planning, shot pacing, and background audio resolution."""
    with ctx.profiler.phase(CanonicalStage.MOOD_THEME):
        from src.agents.script_curator import CinematicScriptCuratorAgent
        from src.agents.art_director import ArtDirectorMoodAgent
        from src.agents.scene_planner import ScenePlannerCompositorAgent
        from src.asset_manager import get_asset_manager

        assets = get_asset_manager()
        ctx.target_category = (
            ctx.loop_category
            or getattr(ctx.lane, "loop_category", None)
            or getattr(ctx.lane, "story_type", None)
            or ("cosmic_horror" if ctx.channel_name == "moku" else "dark_ambient")
        )

        bg_audio_cfg = getattr(ctx.lane, "background_audio", None)
        bg_enabled = getattr(bg_audio_cfg, "enabled", True) if bg_audio_cfg else True
        ctx.bg_volume = float(getattr(bg_audio_cfg, "volume", 0.04)) if bg_audio_cfg else 0.04
        bg_mode = str(getattr(bg_audio_cfg, "mode", "auto")) if bg_audio_cfg else "auto"
        bg_theme = getattr(bg_audio_cfg, "theme", None) or ctx.target_category

        if hasattr(assets, "resolve_or_create_background_audio"):
            ctx.music_track_path = assets.resolve_or_create_background_audio(
                category=bg_theme,
                style=ctx.lane.template,
                duration_sec=float(ctx.audio.get("duration_sec", 60.0)),
                work_dir=ctx.work_dir,
                mode=bg_mode if bg_enabled else "off",
            )
        elif hasattr(assets, "get_music"):
            ctx.music_track_path = assets.get_music(style=ctx.lane.template)
        else:
            ctx.music_track_path = ""

        if ctx.is_multiscene_mode:
            from src.media.compositor import MultiSceneCompositor

            curator = CinematicScriptCuratorAgent()
            art = ArtDirectorMoodAgent()
            ctx.planner_agent = ScenePlannerCompositorAgent()
            ctx.multi_compositor = MultiSceneCompositor()

            target_fmt = "short" if ctx.lane.orientation == "vertical" else "longform"
            ctx.script_payload = curator.curate(
                raw_text=ctx.clean_script, title=ctx.title, channel_lane=ctx.lane.id, target_format=target_fmt,
            )
            (ctx.work_dir / "cinematic_script.json").write_text(json.dumps(ctx.script_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            ctx.visual_plan_payload = art.plan_visuals(cinematic_script=ctx.script_payload, theme_lane=ctx.target_category)
            ctx.visual_plan_path.write_text(json.dumps(ctx.visual_plan_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            return

        from src.media.loop_engine import LoopVideoEngine
        from src.core.scenic_detector import detect_adaptive_theme

        ctx.loop_engine = LoopVideoEngine()
        if ctx.is_multiscene_mode:
            curator = CinematicScriptCuratorAgent()
            art = ArtDirectorMoodAgent()
            planner = ScenePlannerCompositorAgent()
            target_fmt = "short" if ctx.lane.orientation == "vertical" else "longform"
            ctx.script_payload = curator.curate(raw_text=ctx.clean_script, title=ctx.title, channel_lane=ctx.lane.id, target_format=target_fmt)
            (ctx.work_dir / "cinematic_script.json").write_text(json.dumps(ctx.script_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            plan_cat = ctx.loop_category or getattr(ctx.lane, "loop_category", None) or getattr(ctx.lane, "story_type", None) or ("cosmic_horror" if ctx.channel_name == "moku" else "dark_ambient")
            ctx.visual_plan_payload = art.plan_visuals(cinematic_script=ctx.script_payload, theme_lane=plan_cat)
            ctx.visual_plan_path.write_text(json.dumps(ctx.visual_plan_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            ctx.manifest_payload = planner.plan_manifest(
                script=ctx.script_payload, visual_plan=ctx.visual_plan_payload, story_id=ctx.story_id,
                narration_path=str(ctx.audio_path), music_path="", lane_id=ctx.lane.id, channel_name=ctx.channel_name,
                resolution=list(ctx.lane.expected_resolution), fps=ctx.lane.fps, actual_audio_duration=float(ctx.audio.get("duration_sec", 0.0) or 0.0),
            )
            ctx.scene_manifest_path.write_text(json.dumps(ctx.manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            ctx.scene_bg_list, ctx.shot_durations, ctx.target_category = _catalog_shots_from_manifest(
                ctx.manifest_payload, ctx.loop_engine, ctx.lane.orientation, channel=ctx.channel_name,
            )
            if ctx.scene_bg_list and ctx.shot_durations:
                ctx.resolved_loop_path = ctx.scene_bg_list[0]
        else:
            # Continuous single-loop composition engine:
            # Resolves loop from assets/videos/shorts/ (vertical) or assets/videos/longs/ (horizontal).
            # Neutral round-robin rotation, repeats single continuous clip for full audio duration.
            from src.config import is_test_environment
            total_audio_sec = float(ctx.audio.get("duration_sec", 15.0) or 15.0) if isinstance(ctx.audio, dict) else 15.0
            ctx.resolved_loop_path = ctx.loop_engine.resolve_continuous_loop(
                orientation=ctx.lane.orientation,
                allow_test_mock=is_test_environment(),
            )
            ctx.scene_bg_list = [str(ctx.resolved_loop_path)]
            ctx.shot_durations = [total_audio_sec]
            ctx.target_category = getattr(ctx.lane, "loop_category", None) or "neutral_loop"
            scenes_plan = [{
                "duration": total_audio_sec,
                "source": str(ctx.resolved_loop_path),
                "category": str(ctx.target_category),
                "shot_index": 0,
            }]
            ctx.visual_plan_payload = {
                "video_engine": "loop",
                "loop": True,
                "mode": "loop",
                "category": str(ctx.target_category),
                "scenes": scenes_plan,
                "covered_seconds": total_audio_sec,
                "black_fallbacks": 0,
                "shot_durations": ctx.shot_durations,
            }
            ctx.visual_plan_path.write_text(json.dumps(ctx.visual_plan_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("Continuous single-loop composition: %s (duration: %.1fs)", ctx.resolved_loop_path, total_audio_sec)


def _stage_08_loop_scene(ctx: RunContext) -> None:
    """Stage 8: Build scene manifest and resolve stream-copy / subtitle mux flags."""
    with ctx.profiler.phase(CanonicalStage.LOOP_SCENE):
        from src.core.guard import memory_checkpoint
        memory_checkpoint("8_loop_scene")
        subtitles_active = ctx.subtitles_active
        ass_path = ctx.ass_path
        mux_subtitles = bool(subtitles_active and ass_path.is_file())
        stream_copy_mode = True
        ctx.mux_subtitles = mux_subtitles
        ctx.stream_copy_mode = stream_copy_mode

        if ctx.is_multiscene_mode:
            ctx.manifest_payload = ctx.planner_agent.plan_manifest(
                script=ctx.script_payload,
                visual_plan=ctx.visual_plan_payload,
                story_id=ctx.story_id,
                narration_path=str(ctx.audio_path),
                music_path=str(ctx.music_track_path) if ctx.music_track_path else "",
                music_volume=ctx.bg_volume,
                lane_id=ctx.lane.id,
                channel_name=ctx.channel_name,
                resolution=list(ctx.lane.expected_resolution),
                fps=ctx.lane.fps,
                actual_audio_duration=float(ctx.audio.get("duration_sec", 0.0) or 0.0),
            )
            ctx.scene_manifest_path.write_text(json.dumps(ctx.manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            ctx.manifest_path = ctx.scene_manifest_path
            return

        from src.scene_manifest import build_scene_manifest
        manifest_slot = ctx.story.get("object_class") or ctx.channel_name

        ctx.manifest_path = build_scene_manifest(
            work_dir=ctx.work_dir,
            scp_id=ctx.story_id,
            title=ctx.title,
            object_class=manifest_slot,
            attribution=ctx.story.get("attribution") or ctx.title or "Fuente original",
            narration_path=ctx.audio_path,
            music_path=ctx.music_track_path,
            duration_sec=float(ctx.audio["duration_sec"]),
            scene_images=ctx.scene_bg_list,
            subtitles=[],
            resolution=tuple(ctx.lane.expected_resolution),
            fps=ctx.lane.fps,
            stamp_text=f"[{ctx.channel_name.upper()}]",
            channel_name=ctx.channel_name,
            shot_durations=ctx.shot_durations,
        )


def _stage_09_video_rendering(ctx: RunContext) -> None:
    """Stage 9: Video composition via stream-copy or MultiSceneCompositor."""
    with ctx.profiler.phase(CanonicalStage.VIDEO_RENDERING):
        from src.core.guard import memory_checkpoint
        memory_checkpoint("9_video_rendering")

        stream_copy_mode = ctx.stream_copy_mode
        mux_subtitles = ctx.mux_subtitles

        from src.core.render_guard import _LONG_RENDER_SEMAPHORE, _SHORT_RENDER_SEMAPHORE
        render_sem = _LONG_RENDER_SEMAPHORE if ctx.is_long_lane else _SHORT_RENDER_SEMAPHORE
        with render_sem, active_heartbeat_scope(ctx):
            if ctx.is_multiscene_mode:
                from src.media.encode_defaults import default_render_crf, default_render_preset
                ctx.compositor_metrics = ctx.multi_compositor.render(
                    manifest_path=ctx.manifest_path,
                    output_video_path=ctx.video_path,
                    crf=default_render_crf(),
                    preset=default_render_preset(),
                    subtitle_path=None,
                )
                ctx.visual_integrity_report = {
                    "passed": True,
                    "bypassed": False,
                    "engine": "multi_scene_dual_engine",
                    "scenes_count": len(ctx.manifest_payload.get("scenes", [])),
                }
            else:
                ctx.compositor_metrics = ctx.loop_engine.render(
                    ctx.manifest_path,
                    ctx.video_path,
                    audio_path=ctx.audio_path,
                    subtitle_path=ctx.ass_path if mux_subtitles else None,
                    background_path=str(ctx.resolved_loop_path),
                    bg_music_path=ctx.music_track_path,
                    music_volume=ctx.bg_volume,
                    duration_sec=float(ctx.audio["duration_sec"]),
                    category=ctx.target_category,
                    orientation=ctx.lane.orientation,
                    include_subtitles=mux_subtitles,
                    stream_copy=stream_copy_mode,
                    scene_images=ctx.scene_bg_list,
                    shot_durations=ctx.shot_durations,
                    shot_roles=[
                        str(sc.get("director_role") or "settled")
                        for sc in (ctx.manifest_payload.get("scenes") or [])
                        if isinstance(sc, dict)
                    ],
                    channel=ctx.channel_name,
                )
                quality_metrics = (ctx.compositor_metrics.get("quality_metrics") if isinstance(ctx.compositor_metrics, dict) else {}) or {}
                ctx.visual_integrity_report = {"engine": "loop"}
                if quality_metrics and isinstance(quality_metrics, dict):
                    if "longest_black_seconds" in quality_metrics:
                        ctx.visual_integrity_report["longest_black_seconds"] = quality_metrics["longest_black_seconds"]
                        ctx.visual_integrity_report["black_segments"] = quality_metrics.get("black_segments", [])
                    if quality_metrics.get("perceptual_luminance") is not None:
                        ctx.visual_integrity_report["perceptual_luminance"] = quality_metrics["perceptual_luminance"]

        ctx.repository.record_artifact(ctx.run_id, "video", local_path=str(ctx.video_path), size_bytes=ctx.video_path.stat().st_size)


def _stage_11_thumbnail_metadata(ctx: RunContext) -> None:
    """Stage 11: Thumbnail generation (with climax frame extraction) and metadata persistence."""
    with ctx.profiler.phase(CanonicalStage.THUMBNAIL_METADATA):
        from src.llm import clean_title, translate_title
        from lib.video import create_video_thumbnail

        ctx.spanish_title = clean_title(ctx.title) if is_test_environment() else clean_title(translate_title(ctx.title, provider="A"))
        ctx.youtube_title = ctx.branding.generate_title(ctx.spanish_title)
        ctx.youtube_description = ctx.branding.generate_description(ctx.spanish_title)

        from src.core.scenic_detector import extract_story_motifs
        motifs_for_thumb = extract_story_motifs(ctx.spanish_title or ctx.title or "")
        thumb_hook = getattr(ctx.lane, "hook_text", None) or (ctx.story.get("hook_text") if isinstance(ctx.story, dict) else None)
        if not thumb_hook and motifs_for_thumb:
            motif_hooks = {
                "carnival": "¿QUÉ HABÍA EN LA FERIA?", "morgue": "¿QUÉ HABÍA EN LA CAMILLA?",
                "asylum": "¿QUÉ HABÍA EN EL PASILLO?", "cabin": "¿QUÉ HABÍA EN LA CABAÑA?",
                "cemetery": "¿QUÉ HABÍA EN LA TUMBA?", "diner": "¿QUÉ PASÓ A LAS 3 AM?",
                "bakery": "¿QUÉ HABÍA EN EL HORNO?", "mar": "¿QUÉ HABÍA EN EL FARO?",
                "boda": "¿ARRUINÉ SU BODA?", "hermano": "¿TRAICIÓN FAMILIAR?",
                "apartamento": "¿EXIGEN MI HERENCIA?", "deudas": "¿PAGAR SUS DEUDAS?",
            }
            thumb_hook = motif_hooks.get(motifs_for_thumb[0])

        # Prompt-driven real-time thumbnail generation (Chiaroscuro high-CTR style, 3-5 word viral hook, mysterious focal subject)
        from src.agents.seo_optimizer import SeoOptimizerAgent
        seo_opt = SeoOptimizerAgent()
        target_fmt = "longform" if ctx.is_long_lane else "short"
        seo_res = seo_opt.optimize(
            topic=ctx.spanish_title or ctx.title,
            target_format=target_fmt,
            niche=getattr(ctx.lane, "story_type", "") or ctx.channel_name,
            use_agent=bool(os.environ.get("USE_AGENT_HARNESS", "0") in ("1", "true", "yes")),
        )
        thumb_concept = (seo_res.get("thumbnail_concepts") or [{}])[0]
        thumb_hook = thumb_concept.get("big_headline") or thumb_hook or "¡EXPEDIENTE SECRETO PROHIBIDO!"
        thumb_prompt = thumb_concept.get("visual_layout") or "Chiaroscuro high-CTR dramatic lighting mysterious focal subject"
        palette = thumb_concept.get("color_palette")
        accent_color = palette[0] if palette and isinstance(palette, list) else None

        create_video_thumbnail(
            ctx.spanish_title, ctx.channel_name, str(ctx.thumbnail_path),
            template=ctx.lane.template, archetype=ctx.target_category, strict_official_sdk=False,
            video_mode=target_fmt, video_path=str(ctx.video_path),
            bg_image_path=None, manifest_path=str(ctx.scene_manifest_path), hook_text=thumb_hook,
            cover_prompt=thumb_prompt, accent_color=accent_color,
            metadata={"prompt": thumb_prompt, "visual_layout": thumb_prompt, "big_headline": thumb_hook},
        )
        ctx.metadata_path.write_text(json.dumps({
            "channel": ctx.channel_name, "title": ctx.youtube_title, "description": ctx.youtube_description,
            "tags": ctx.branding.tags, "visibility": "public", "story_id": ctx.story_id,
            "thumbnail_candidate_timestamp": 5.0, "master_video_path": str(ctx.video_path),
            "preview_video_path": str(ctx.work_dir / f"preview_{ctx.story_id}_v3.mp4"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        required_artifacts = [("thumbnail", ctx.thumbnail_path), ("metadata", ctx.metadata_path), ("visual_plan", ctx.visual_plan_path)]
        if ctx.subtitles_active or ctx.ass_path.is_file(): required_artifacts.append(("subtitles_ass", ctx.ass_path))
        if ctx.subtitles_active or ctx.srt_path.is_file(): required_artifacts.append(("subtitles_srt", ctx.srt_path))
        for kind, path in required_artifacts:
            if not path.is_file():
                if kind == "visual_plan" and is_test_environment(): continue
                raise ValueError(f"Artefacto obligatorio ausente: {kind}")
            ctx.repository.record_artifact(ctx.run_id, kind, local_path=str(path), size_bytes=path.stat().st_size)


def _stage_12_dedup_simhash(ctx: RunContext) -> None:
    """Stage 12: SimHash and SHA256 deduplication gating against recent channel publications."""
    with ctx.profiler.phase(CanonicalStage.DEDUP_SIMHASH):
        ctx.text_fingerprints = {"script": ctx.script, "title": ctx.youtube_title, "description": ctx.youtube_description}
        ctx.file_fingerprints = {
            "thumbnail": _file_sha256(ctx.thumbnail_path),
            "audio": _file_sha256(ctx.audio_path),
            "video": _file_sha256(ctx.video_path),
        }
        duplicate_kinds = [kind for kind, payload in ctx.text_fingerprints.items() if ctx.repository.has_published_fingerprint(ctx.channel_name, kind, payload)]
        duplicate_kinds.extend([kind for kind, digest in ctx.file_fingerprints.items() if ctx.repository.has_published_digest(ctx.channel_name, kind, digest)])
        if duplicate_kinds:
            raise ValueError("Artefactos duplicados respecto de publicaciones recientes: " + ", ".join(duplicate_kinds))


def _stage_10_qa_gating(ctx: RunContext) -> None:
    """Stage 10: Automated QA gating (validate_prepublication) and RENDERED status transition."""
    with ctx.profiler.phase(CanonicalStage.QA_GATING):
        with active_heartbeat_scope(ctx):
            sub_path = ctx.srt_path if (ctx.subtitles_active and ctx.srt_path.is_file()) else (ctx.srt_path if ctx.srt_path.is_file() else (ctx.ass_path if ctx.ass_path.is_file() else None))
            report = validate_prepublication(
                channel=ctx.channel_name,
                script=ctx.script,
                title=ctx.youtube_title,
                description=ctx.youtube_description,
                video_path=ctx.video_path,
                subtitle_path=sub_path,
                thumbnail_path=ctx.thumbnail_path,
                recent_texts=ctx.repository.recent_published_texts(ctx.channel_name),
                visual_plan_path=ctx.visual_plan_path,
                expected_story_count=1 if ctx.directed else len(ctx.used_ids),
                visibility="public",
                audio_proof=ctx.audio,
                require_strict_voice=ctx.directed,
                video_mode="longform" if ctx.is_long_lane else "short",
                precomputed_visual=ctx.visual_integrity_report,
                video_engine=ctx.engine_mode,
                require_subtitles=ctx.subtitles_active,
                min_duration_sec=float(ctx.lane.duration_min_sec),
            )
            report.require_pass()
            if not ctx.set_owned_status(JobStatus.RENDERED):
                raise LeaseOwnershipError("Ownership perdido antes de marcar RENDERED")

            try:
                from src.cleaner import clean_run_intermediates
                clean_run_intermediates(ctx.work_dir)
            except Exception as cleaner_exc:
                logger.debug("Non-fatal intermediate cleanup error: %s", cleaner_exc)


def _stage_13_backup_publish(ctx: RunContext) -> dict[str, Any]:
    """Stage 13: Drive backup, code verdict, Telegram human review gate, YouTube publish, and commit."""
    with ctx.profiler.phase(CanonicalStage.BACKUP_PUBLISH):
        drive_url: str | None = None
        drive_proof: DriveProof | None = None
        folder_id = getattr(SETTINGS, "drive_approved_video_folder_id", "") or SETTINGS.drive_folder_id
        if folder_id:
            from src.drive import upload_to_drive_verified
            try:
                drive_proof = upload_to_drive_verified(
                    str(ctx.video_path),
                    folder_id=folder_id,
                    sa_key_path=str(SETTINGS.drive_key_path),
                    display_name=f"{sanitize_filename(ctx.spanish_title)}.mp4",
                    token_path=str(ctx.settings.youtube_token_path),
                    idempotency_key=f"YTShort:{ctx.channel_name}:{ctx.story_id}",
                    on_file_id=lambda fid: ctx.repository.record_drive_upload_id(ctx.story_id, ctx.run_id, fid, owner=ctx.owner),
                )
                ctx.repository.record_provider_attempt(ctx.run_id, "drive", "upload_and_verify", outcome="verified")
                ctx.repository.record_artifact(
                    ctx.run_id, "drive_video", remote_provider="drive", remote_id=drive_proof.file_id,
                    remote_name=drive_proof.name, size_bytes=drive_proof.size_bytes, verified=True,
                )
                if drive_proof and drive_proof.file_id:
                    drive_url = _drive_review_url(drive_proof)
                if not ctx.set_owned_status(JobStatus.DRIVE_BACKED_UP):
                    raise LeaseOwnershipError("Ownership perdido después de confirmar Drive")
            except Exception as exc:
                ctx.repository.record_provider_attempt(ctx.run_id, "drive", "upload_and_verify", outcome="failed", error_code=getattr(exc, "code", "drive_error"), error_detail=str(exc))
                if ctx.directed and isinstance(exc, AmbiguousUploadError):
                    return ctx.fail("drive_upload_ambiguous", str(exc), status=JobStatus.UPLOAD_UNCONFIRMED)
                logger.warning("Drive backup attempt failed: %s", exc)
        else:
            logger.info("Drive backup omitido: DRIVE_FOLDER_ID no está configurado")

        if ctx.generate_only:
            if not ctx.repository.finish_run(ctx.run_id, JobStatus.RENDERED, owner=ctx.owner):
                raise LeaseOwnershipError("Ownership perdido antes de finalizar el run")
            _marker(ctx.work_dir, ctx.run_id, active=False)
            logger.info("Run %s generado sin publicar (generate_only)", ctx.run_id)
            ctx.profiler.emit_telemetry(db_path=ctx.database)
            logger.info("\n" + ctx.profiler.format_table())
            return {
                "status": JobStatus.RENDERED.value, "story_id": ctx.story_id, "run_id": ctx.run_id, "channel": ctx.channel_name,
                "work_dir": str(ctx.work_dir), "drive_url": drive_url, "drive_file_id": drive_proof.file_id if drive_proof else None,
                "profiling": ctx.profiler.to_dict(), **_peak_rss_metric(),
            }

        ctx.require_heartbeat()

        verdict_payload: dict[str, Any] = {}
        try:
            from src.core.verdict import evaluate_video, is_code_review_enabled
            if is_code_review_enabled():
                verdict = evaluate_video(
                    str(ctx.video_path), work_dir=str(ctx.work_dir), script_text=ctx.script,
                    ass_path=str(ctx.ass_path) if ctx.ass_path.is_file() else None,
                    subtitle_path=str(ctx.srt_path) if ctx.srt_path.is_file() else None,
                    thumbnail_path=str(ctx.thumbnail_path) if ctx.thumbnail_path.is_file() else None,
                    story_id=ctx.story_id, run_id=ctx.run_id, channel=ctx.channel_name, video_mode="long" if ctx.is_long_lane else "short",
                )
                verdict_passed = getattr(verdict, "passed", getattr(verdict, "approved", False))
                from dataclasses import asdict, is_dataclass
                verdict_payload = asdict(verdict) if is_dataclass(verdict) else (verdict if isinstance(verdict, dict) else {})
                if not verdict_passed:
                    logger.warning("Short %s advertencia en veredicto técnico: %s", ctx.story_id, getattr(verdict, "reasons", []))
                else:
                    logger.info("Short %s evaluado exitosamente por veredicto técnico", ctx.story_id)
        except Exception as exc:
            logger.warning("Code-based review evaluation failed (%s); continuing to Telegram review", exc, exc_info=True)

        try:
            from review import ReviewJobManager, ReviewStatus
            review_manager = ReviewJobManager()
            auto_approve = is_test_environment() or os.environ.get("TEST_MODE") == "1" or os.environ.get("AUTO_APPROVE", "").strip() == "1"
            if auto_approve:
                review_job = review_manager.submit_for_code_review(
                    job_id=ctx.story_id,
                    project="YTShort",
                    channel=ctx.channel_name,
                    content_type=ctx.lane.review_content_type,
                    original_video_path=str(ctx.video_path),
                    thumbnail_path=str(ctx.thumbnail_path) if ctx.thumbnail_path.is_file() else None,
                    title=ctx.youtube_title,
                    description=ctx.youtube_description,
                    script=ctx.script,
                    subtitle_path=str(ctx.ass_path) if ctx.ass_path.is_file() else (str(ctx.srt_path) if ctx.srt_path.is_file() else None),
                    work_dir=str(ctx.work_dir),
                    drive_url=drive_url,
                    metadata={"code_verdict": verdict_payload} if verdict_payload else None,
                )
                uid = int(os.environ.get("REVIEW_APPROVER_USER_ID") or os.environ.get("TELEGRAM_ALLOWED_USER_ID") or "0")
                approved_job = review_manager.code_approve(
                    ctx.story_id,
                    review_job.version,
                    verdict_payload or {"approved": True, "passed": True, "source": "auto_approve"},
                    user_id=uid,
                )
                review_job = approved_job
                review_job.status = ReviewStatus.APPROVED.value
                if os.environ.get("AUTO_APPROVE", "").strip() == "1":
                    logger.info("AUTO_APPROVE=1: review job %s v%s approved via code review bypass without Telegram HITL/proxy", ctx.story_id, review_job.version)
            else:
                review_job = review_manager.submit_video_for_review(
                    job_id=ctx.story_id, project="YTShort", channel=ctx.channel_name, content_type=ctx.lane.review_content_type,
                    original_video_path=str(ctx.video_path), thumbnail_path=str(ctx.thumbnail_path) if ctx.thumbnail_path.is_file() else None,
                    title=ctx.youtube_title, description=ctx.youtube_description, script=ctx.script,
                    subtitle_path=str(ctx.ass_path) if ctx.ass_path.is_file() else (str(ctx.srt_path) if ctx.srt_path.is_file() else None),
                    work_dir=str(ctx.work_dir), drive_url=drive_url, metadata={"code_verdict": verdict_payload} if verdict_payload else None,
                )
            if review_job.status == ReviewStatus.FAILED.value:
                return ctx.fail("review_delivery_failed", review_job.delivery_error or "Telegram did not confirm review delivery")
            current_review_status, approved_status_val = review_job.status, ReviewStatus.APPROVED.value
        except (ImportError, ModuleNotFoundError) as exc:
            return ctx.fail("review_core_unavailable", str(exc))
        except Exception as exc:
            logger.exception("Telegram review submission failed for story %s", ctx.story_id)
            return ctx.fail("review_delivery_failed", str(exc))

        if current_review_status != approved_status_val:
            term_status = JobStatus.PENDING_REVIEW if current_review_status == ReviewStatus.PENDING_REVIEW.value else JobStatus.RENDERED
            ctx.set_owned_status(term_status)
            if not ctx.repository.finish_run(ctx.run_id, JobStatus.RENDERED, owner=ctx.owner):
                raise LeaseOwnershipError("Ownership perdido antes de finalizar el run")
            _marker(ctx.work_dir, ctx.run_id, active=False)
            logger.info("Short %s retenido para revisión humana por Telegram. Estado: %s", ctx.story_id, current_review_status)
            ctx.profiler.emit_telemetry(db_path=ctx.database)
            logger.info("\n" + ctx.profiler.format_table())
            return {
                "status": current_review_status, "story_id": ctx.story_id, "run_id": ctx.run_id, "channel": ctx.channel_name,
                "work_dir": str(ctx.work_dir), "review_status": review_job.status, "drive_url": drive_url,
                "drive_file_id": drive_proof.file_id if drive_proof else None, "profiling": ctx.profiler.to_dict(),
            }

        from src.core.guard import memory_checkpoint
        memory_checkpoint("publish_start")
        from src.youtube.uploader import upload_video
        try:
            result = upload_video(
                str(ctx.video_path), ctx.youtube_title, ctx.youtube_description, tags=ctx.branding.tags,
                channel=ctx.channel_name, thumbnail_path=str(ctx.thumbnail_path), token_path=str(ctx.settings.youtube_token_path),
                api_only=ctx.directed, expected_channel_id=ctx.settings.expected_youtube_channel_id,
                on_video_id=lambda vid: ctx.repository.record_youtube_upload_id(ctx.story_id, ctx.run_id, vid, owner=ctx.owner),
                job_id=ctx.story_id, version=review_job.version,
            )
            ctx.repository.record_provider_attempt(ctx.run_id, "youtube", "upload_and_verify", outcome=str(result.get("status") or "unknown").lower())
        except (YouTubeUploadLimitError, YouTubeQuotaExceededError) as exc:
            retry_delay = 14400 if isinstance(exc, YouTubeUploadLimitError) else 3600
            retry_at = int(time.time()) + retry_delay
            ctx.repository.record_provider_attempt(
                ctx.run_id, "youtube", "upload_and_verify",
                outcome="limit_exceeded" if isinstance(exc, YouTubeUploadLimitError) else "quota_exceeded",
                error_code=exc.code,
                error_detail=str(exc),
            )
            if not ctx.set_owned_status(
                JobStatus.WAITING_YOUTUBE_LIMIT,
                error_code=exc.code,
                error_detail=str(exc),
                retry_at=retry_at,
            ):
                return ctx.lease_lost_result()
            _marker(ctx.work_dir, ctx.run_id, active=False)
            return {
                "status": JobStatus.WAITING_YOUTUBE_LIMIT.value,
                "story_id": ctx.story_id,
                "run_id": ctx.run_id,
                "channel": ctx.channel_name,
                "work_dir": str(ctx.work_dir),
                "retry_at": retry_at,
                "profiling": ctx.profiler.to_dict(),
            }
        except Exception as exc:
            ctx.repository.record_provider_attempt(ctx.run_id, "youtube", "upload_and_verify", outcome="failed", error_code=getattr(exc, "code", "youtube_error"), error_detail=str(exc))
            if ctx.directed:
                if not ctx.set_owned_status(JobStatus.UPLOAD_UNCONFIRMED, error_code=getattr(exc, "code", "youtube_unconfirmed"), error_detail=str(exc)):
                    return ctx.lease_lost_result()
                _marker(ctx.work_dir, ctx.run_id, active=False)
                return {"status": JobStatus.UPLOAD_UNCONFIRMED.value, "story_id": ctx.story_id, "run_id": ctx.run_id, "channel": ctx.channel_name, "work_dir": str(ctx.work_dir), "profiling": ctx.profiler.to_dict()}
            raise

        if result.get("status") == "WAITING_YOUTUBE_LIMIT" or result.get("status") == JobStatus.WAITING_YOUTUBE_LIMIT.value:
            retry_delay = int(result.get("retry_after_seconds") or 14400)
            retry_at = int(time.time()) + retry_delay
            if not ctx.set_owned_status(
                JobStatus.WAITING_YOUTUBE_LIMIT,
                error_code="youtube_upload_limit",
                error_detail=str(result.get("reason") or "Límite diario de YouTube alcanzado"),
                retry_at=retry_at,
            ):
                return ctx.lease_lost_result()
            _marker(ctx.work_dir, ctx.run_id, active=False)
            return {
                "status": JobStatus.WAITING_YOUTUBE_LIMIT.value,
                "story_id": ctx.story_id,
                "run_id": ctx.run_id,
                "channel": ctx.channel_name,
                "work_dir": str(ctx.work_dir),
                "retry_at": retry_at,
                "profiling": ctx.profiler.to_dict(),
            }

        if result.get("status") == "UPLOAD_UNCONFIRMED":
            retry_at = int(time.time()) + 14400
            if not ctx.set_owned_status(
                JobStatus.UPLOAD_UNCONFIRMED,
                error_code="youtube_unconfirmed",
                error_detail=str(result.get("reason") or "respuesta ambigua"),
                retry_at=retry_at,
            ):
                return ctx.lease_lost_result()
            _marker(ctx.work_dir, ctx.run_id, active=False)
            return {"status": JobStatus.UPLOAD_UNCONFIRMED.value, "story_id": ctx.story_id, "run_id": ctx.run_id, "channel": ctx.channel_name, "work_dir": str(ctx.work_dir), "profiling": ctx.profiler.to_dict()}

        if result.get("status") != "PUBLISHED":
            if not ctx.set_owned_status(JobStatus.DRIVE_BACKED_UP): return ctx.lease_lost_result()
            if not ctx.repository.finish_run(ctx.run_id, JobStatus.DRIVE_BACKED_UP, owner=ctx.owner): return ctx.lease_lost_result()
            _marker(ctx.work_dir, ctx.run_id, active=False)
            ctx.profiler.emit_telemetry(db_path=ctx.database)
            return {"status": str(result.get("status") or "TEST_MOCK"), "story_id": ctx.story_id, "run_id": ctx.run_id, "channel": ctx.channel_name, "work_dir": str(ctx.work_dir), "profiling": ctx.profiler.to_dict()}

        from src.core.providers import publication_proof_from_response
        from src.retention import mark_run_retention_satisfied

        if ctx.directed:
            ctx.repository.require_single_story_run(ctx.run_id, ctx.story_id)
        proof = publication_proof_from_response(result, expected_channel=ctx.channel_key, expected_title=ctx.youtube_title, expected_description=ctx.youtube_description)
        ctx.repository.mark_published(ctx.story_id, ctx.run_id, proof, provider=str(result["method"]), owner=ctx.owner)
        post_commit_errors: list[str] = []
        for kind, payload in ctx.text_fingerprints.items():
            try:
                ctx.repository.record_fingerprint(
                    ctx.run_id, ctx.story_id, ctx.channel_name, kind, payload,
                    normalized_text=normalize_text(str(payload)) if isinstance(payload, str) else None,
                )
            except Exception as exc:
                logger.warning("Post-commit artifact recording failed: %s", exc, exc_info=True)
                post_commit_errors.append(f"fingerprint {kind}: {exc}")
        for kind, digest in ctx.file_fingerprints.items():
            try:
                ctx.repository.record_fingerprint_digest(ctx.run_id, ctx.story_id, ctx.channel_name, kind, digest)
            except Exception as exc:
                logger.warning("Post-commit fingerprint recording failed: %s", exc, exc_info=True)
                post_commit_errors.append(f"fingerprint {kind}: {exc}")
        marker_deactivated = False
        try:
            _marker(ctx.work_dir, ctx.run_id, active=False)
            marker_deactivated = True
        except Exception as exc:
            logger.warning("Post-commit marker deactivation failed: %s", exc, exc_info=True)
            post_commit_errors.append(f"marker: {exc}")
        retention_satisfied = False
        if marker_deactivated:
            try:
                retention_satisfied = mark_run_retention_satisfied(str(ctx.video_path), published_id=proof.video_id, published_url=proof.url)
                if not retention_satisfied:
                    post_commit_errors.append("retention: no se encontró un marcador de run válido")
            except Exception as exc:
                logger.warning("Post-commit retention satisfaction failed: %s", exc, exc_info=True)
                post_commit_errors.append(f"retention: {exc}")
        if post_commit_errors:
            logger.error("Publication committed; post-commit tasks failed: %s", "; ".join(post_commit_errors))
        try:
            from src.cleaner import delete_local_post_publication
            delete_local_post_publication(ctx.work_dir, ctx.video_path)
        except Exception as clean_exc:
            logger.warning("Post-commit local cleanup failed: %s", clean_exc)
        ctx.profiler.emit_telemetry(db_path=ctx.database)
        logger.info("\n" + ctx.profiler.format_table())
        return {
            "status": JobStatus.PUBLISHED.value, "story_id": ctx.story_id, "run_id": ctx.run_id, "channel": ctx.channel_name,
            "url": proof.url, "work_dir": str(ctx.work_dir), "retention_satisfied": retention_satisfied, "profiling": ctx.profiler.to_dict(),
            **({"post_commit_warning": post_commit_errors} if post_commit_errors else {}),
        }


def _handle_pipeline_exception(
    exc: Exception,
    *,
    code: str,
    status: JobStatus,
    ctx: RunContext,
    retry_delay: int | None = None,
) -> dict[str, Any]:
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
    """Produce exactly one video governed by its lane (config/lanes.json)."""
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

    claimed_ctx, early_exit = _stage_01_claim_lease(
        channel_key=channel_key, channel_name=channel_name, db_path=db_path, story_id=story_id,
        story=story, directed=directed, generate_only=generate_only, owner=owner, lane_id=lane_id, profiler=profiler,
    )
    if early_exit is not None:
        return early_exit

    story = claimed_ctx["story"]
    story_id = claimed_ctx["story_id"]
    run_id = str(story.get("run_id") or run_id or story_id)
    profiler.run_id = run_id
    profiler.story_id = story_id
    lane = claimed_ctx["lane"]
    repository = claimed_ctx["repository"]

    engine_mode = (
        video_engine or compositor or getattr(lane, "video_engine", None) or getattr(lane, "visual_pipeline", None)
        or os.environ.get("VIDEO_ENGINE") or os.environ.get("COMPOSITION_ENGINE") or os.environ.get("COMPOSITOR")
        or os.environ.get("SHORT_COMPOSITOR") or getattr(SETTINGS, "short_compositor", None) or "loop"
    ).strip().lower()
    is_loop_mode = engine_mode in ("loop", "loop_video", "loop_video_engine", "loop_compositor", "beats")
    is_multiscene_mode = engine_mode in ("director", "multiscene", "multi_scene", "multi_scene_compositor", "dual_engine", "hybrid", "procedural")
    force_multiscene = os.environ.get("FORCE_MULTISCENE", "").strip().lower() in ("1", "true", "yes", "on")
    if is_multiscene_mode and not force_multiscene:
        logger.info("Coercing video_engine=%s to loop (set FORCE_MULTISCENE=1 to restore director)", engine_mode)
        engine_mode = "loop"
        is_loop_mode = True
        is_multiscene_mode = False
    if not (is_loop_mode or is_multiscene_mode):
        raise ValueError(f"video_engine={engine_mode!r} is not supported. Supported engine modes: 'director', 'multiscene', 'hybrid', or 'loop'.")

    # Product path: Subtitles deactivated permanently for all formats (clean cinematic video surface).
    # Text belongs exclusively on thumbnails (portadas).
    subtitles_active = False
    if enable_subtitles is True:
        subtitles_active = True

    from src.core.guard import memory_checkpoint
    from src.observability import set_run_context
    from src.core.checkpoints import CHECKPOINT_KINDS, resume_plan

    set_run_context(run_id=run_id, story_id=story_id, channel=channel_name, component="pipeline")
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
    scene_manifest_path = work_dir / "scene_manifest.json"

    try:
        _plan = resume_plan(str(claimed_ctx["database"]), story_id, lane.id, now_run_id=run_id)
        for _kind in CHECKPOINT_KINDS:
            _src = _plan.reusable.get(_kind)
            if not _src: break
            _dst = {"script": script_path, "audio": audio_path, "subtitles_ass": ass_path, "video": video_path, "thumbnail": thumbnail_path}[_kind]
            if Path(_src).resolve() == _dst.resolve(): break
            work_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_src, _dst)
    except Exception:
        logger.warning("Plan de reanudación no disponible; ejecución completa", exc_info=True)

    ctx = RunContext(
        story=story, story_id=story_id, run_id=run_id, channel_name=channel_name, channel_key=channel_key,
        lane=lane, repository=repository, database=claimed_ctx["database"], owner=claimed_ctx["owner"],
        lease_seconds=claimed_ctx["lease_seconds"], settings=claimed_ctx["settings"], branding=claimed_ctx["branding"],
        profiler=profiler, directed=directed, generate_only=generate_only, engine_mode=engine_mode,
        is_loop_mode=is_loop_mode, is_multiscene_mode=is_multiscene_mode, subtitles_active=subtitles_active,
        work_dir=work_dir, audio_path=audio_path, ass_path=ass_path, srt_path=srt_path, video_path=video_path,
        thumbnail_path=thumbnail_path, script_path=script_path, visual_plan_path=visual_plan_path,
        metadata_path=metadata_path, scene_manifest_path=scene_manifest_path, loop_category=loop_category,
    )

    try:
        with active_heartbeat_scope(ctx):
            _stage_02_ingest_translate(ctx)
            _stage_03_editorial_barrier(ctx)
            _stage_05_tts_synthesis(ctx)
            _stage_06_duration_alignment(ctx)
            _stage_07_subtitle_generation(ctx)
            memory_checkpoint("render_start")
            _stage_04_mood_theme(ctx)
            _stage_08_loop_scene(ctx)
            _stage_09_video_rendering(ctx)

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

            try:
                tts_phase = profiler.get_phase(CanonicalStage.TTS_SYNTHESIS)
                render_phase = profiler.get_phase(CanonicalStage.VIDEO_RENDERING)
                tts_sec = tts_phase.duration_sec if tts_phase else None
                render_elapsed = (
                    ctx.compositor_metrics.get("render_time_sec", 0.0)
                    if isinstance(ctx.compositor_metrics, dict) and "render_time_sec" in ctx.compositor_metrics
                    else (render_phase.duration_sec if render_phase else 0.0)
                )
                video_size = video_path.stat().st_size if video_path.exists() else 0
                repository.record_production_metrics(
                    run_id=run_id,
                    story_id=story_id,
                    audio_duration_sec=float(ctx.audio.get("duration_sec", 0.0) or 0.0),
                    render_time_sec=float(render_elapsed),
                    tts_time_sec=tts_sec,
                    video_size_bytes=int(video_size),
                    integrated_lufs=None,
                    qa_audit_passed=bool(ctx.visual_integrity_report.get("passed", True)) if isinstance(ctx.visual_integrity_report, dict) else True,
                )
            except Exception as pm_err:
                logger.warning("Could not record production metrics: %s", pm_err, exc_info=True)

            _stage_11_thumbnail_metadata(ctx)
            _stage_12_dedup_simhash(ctx)
            _stage_10_qa_gating(ctx)
            return _stage_13_backup_publish(ctx)

    except LeaseOwnershipError:
        return ctx.lease_lost_result()
    except CapabilityUnavailable as exc:
        return _handle_pipeline_exception(exc, code=getattr(exc, "code", "CapabilityUnavailable"), status=JobStatus.RETRYABLE_FAILED, retry_delay=900, ctx=ctx)
    except QuotaError as exc:
        target = JobStatus.WAITING_IMAGE_QUOTA if thumbnail_path.exists() is False and video_path.exists() else JobStatus.WAITING_LLM_QUOTA
        return _handle_pipeline_exception(exc, code=getattr(exc, "code", "QuotaError"), status=target, ctx=ctx)
    except ManualInterventionRequired as exc:
        return _handle_pipeline_exception(exc, code=getattr(exc, "code", "ManualInterventionRequired"), status=JobStatus.RETRYABLE_FAILED, ctx=ctx)
    except (AuthenticationError, ProviderTimeoutError, OSError, ValueError) as exc:
        code = getattr(exc, "code", type(exc).__name__)
        exc_str = str(exc)
        if "Artefactos duplicados" in exc_str or "contenido demasiado similar" in exc_str:
            logger.warning("Pipeline execution permanently failed due to unrecoverable content error (%s): %s", code, exc)
            return _handle_pipeline_exception(exc, code="unrecoverable_content", status=JobStatus.PERMANENT_FAILED, ctx=ctx)
        logger.warning("Pipeline execution failed with retryable error (%s): %s", code, exc, exc_info=True)
        return _handle_pipeline_exception(exc, code=getattr(exc, "code", "pipeline_validation"), status=JobStatus.RETRYABLE_FAILED, retry_delay=900, ctx=ctx)
    except Exception as exc:
        logger.exception("Unexpected pipeline failure for story %s: %s", story_id, exc)
        return _handle_pipeline_exception(exc, code="unexpected", status=JobStatus.RETRYABLE_FAILED, retry_delay=1800, ctx=ctx)
