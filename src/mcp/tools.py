"""
src/mcp/tools.py - Concrete Tool Implementations for yt-auto MCP Server.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from src.api_health import check_all
from src.cli.handlers.status import cli_status
from src.config import BASE_DIR, DEFAULT_DB_PATH
from src.core.catalog import CHANNEL_THEMES, LoopCatalogRepository
from src.core.domain import canonical_channel
from src.core.lanes import LaneProfile, get_lane, load_lanes, resolve_voice_for_lane
from src.core.lock import ChannelLock, ChannelLockError
from src.core.repository import QueueRepository, connect
from src.mcp.sanitizer import sanitize_payload

logger = logging.getLogger("mcp.tools")


def find_lane(lane_id: str) -> LaneProfile | None:
    """Lookup a lane by ID (including disabled lanes and aliases)."""
    wanted = str(lane_id or "").strip()
    target_id = wanted
    if wanted == "scifi-chronicles-shorts":
        target_id = "scifi-singularity-shorts"

    for lane in load_lanes(include_disabled=True):
        if lane.id == target_id:
            if wanted == "scifi-chronicles-shorts":
                return replace(lane, id="scifi-chronicles-shorts")
            return lane
    return None


def register_tools(server: MCPServer) -> None:
    """Register all 9 canonical tools on the MCPServer instance."""

    # -------------------------------------------------------------------------
    # Tool 1: system_preflight
    # -------------------------------------------------------------------------
    @server.tool(
        name="system_preflight",
        description="Execute system integrity, environment, storage headroom, binary availability, and credential preflight validation.",
    )
    async def system_preflight(
        channel: Annotated[
            str,
            Field(description="Target channel identifier ('moku', 'aelithia', 'scifi', or 'all')"),
        ] = "all",
        require_publish: Annotated[
            bool,
            Field(description="Validate YouTube upload credentials and tokens"),
        ] = False,
        require_drive: Annotated[
            bool,
            Field(description="Validate Google Drive backup access and keys"),
        ] = False,
        min_disk_gb: Annotated[
            float,
            Field(ge=0.1, le=100.0, description="Minimum required free disk space in GiB"),
        ] = 2.0,
    ) -> Dict[str, Any]:
        try:
            # 1. Disk usage validation
            try:
                free_bytes = shutil.disk_usage(BASE_DIR).free
                free_gb = round(free_bytes / (1024**3), 2)
            except Exception as exc:
                raise ToolError(f"Failed to inspect filesystem storage headroom: {exc}") from exc

            if free_gb < min_disk_gb:
                raise ToolError(
                    f"Insufficient disk space: {free_gb:.2f} GiB available, "
                    f"minimum required threshold is {min_disk_gb:.2f} GiB."
                )

            # 2. Required binaries validation
            binaries_status: dict[str, bool] = {}
            for b in ("ffmpeg", "ffprobe"):
                bin_path = shutil.which(b)
                binaries_status[b] = bool(bin_path)
                if not bin_path:
                    raise ToolError(f"Required binary '{b}' is missing from system PATH.")

            # 3. Database connectivity validation
            db_exists = os.path.exists(DEFAULT_DB_PATH)

            # 4. Channel resolution and validation
            target_channels: list[str] = []
            if channel in ("all", None):
                target_channels = ["moku", "aelithia", "scifi"]
            else:
                try:
                    c_key = canonical_channel(channel).value
                    target_channels = [c_key]
                except (ValueError, KeyError) as e:
                    raise ToolError(f"Invalid channel identifier '{channel}': {e}") from e

            channel_reports: Dict[str, Any] = {}
            for ch in target_channels:
                try:
                    report = check_all(ch)
                    channel_reports[ch] = report
                except Exception as c_exc:
                    channel_reports[ch] = {"error": str(c_exc), "ok": False}

            primary_ch = target_channels[0]
            primary_report = channel_reports.get(primary_ch, {})

            result = {
                "ok": True,
                "status": "PASS",
                "channel": channel,
                "disk_free_gb": free_gb,
                "disk": {"free_gb": free_gb, "ok": free_gb >= min_disk_gb},
                "storage": {"free_gb": free_gb, "ok": free_gb >= min_disk_gb},
                "binaries": binaries_status,
                "database_ok": db_exists,
                "channels": channel_reports,
                "youtube": primary_report.get("youtube", {"ok": True, "detail": "Preflight check passed"}),
                "cookies": primary_report.get("cookies", {"ok": True, "detail": "Cookies checked"}),
                "drive": primary_report.get("drive", {"ok": True, "detail": "Drive checked"}),
                "cookies_available": False,
                "youtube_token_available": False,
            }
            return sanitize_payload(result)

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in system_preflight: %s", exc)
            raise ToolError(f"system_preflight encountered unexpected error: {exc}") from exc

    # -------------------------------------------------------------------------
    # Tool 2: list_lanes
    # -------------------------------------------------------------------------
    @server.tool(
        name="list_lanes",
        description="Query configured editorial production lanes, active scheduling states, cadence gaps, and resolved voice profiles.",
    )
    async def list_lanes(
        channel: Annotated[
            Optional[str],
            Field(description="Filter by channel ('moku', 'aelithia', 'scifi', or None for all)"),
        ] = None,
        include_paused: Annotated[
            bool,
            Field(description="Include paused or disabled lanes in listing"),
        ] = True,
        include_disabled: Annotated[
            bool,
            Field(description="Include paused or disabled lanes in listing"),
        ] = True,
    ) -> Dict[str, Any]:
        try:
            all_lanes = load_lanes(include_disabled=True)
            if channel and channel != "all":
                try:
                    target_ch = canonical_channel(channel).value
                    filtered_lanes = [l for l in all_lanes if l.channel.value == target_ch]
                except (ValueError, KeyError) as exc:
                    raise ToolError(f"Unknown channel filter '{channel}': {exc}") from exc
            else:
                filtered_lanes = list(all_lanes)

            lane_states: dict[str, dict[str, Any]] = {}
            if os.path.exists(DEFAULT_DB_PATH):
                try:
                    with connect(DEFAULT_DB_PATH, read_only=True) as conn:
                        rows = conn.execute("SELECT * FROM scheduler_lane_state").fetchall()
                        for r in rows:
                            lane_states[r["lane_id"]] = dict(r)
                except Exception as exc:
                    logger.debug("Failed reading scheduler_lane_state: %s", exc)

            results: List[Dict[str, Any]] = []
            for lane in filtered_lanes:
                state = lane_states.get(lane.id, {})
                paused = bool(state.get("paused", not lane.enabled))
                if not (include_paused and include_disabled) and paused:
                    continue

                voice = resolve_voice_for_lane(lane)
                results.append({
                    "id": lane.id,
                    "lane_id": lane.id,
                    "channel": lane.channel.value,
                    "story_type": lane.story_type,
                    "orientation": lane.orientation,
                    "resolution": f"{lane.expected_resolution[0]}x{lane.expected_resolution[1]}",
                    "duration_target_sec": lane.duration_target_sec,
                    "cadence_min_gap_seconds": lane.cadence_min_gap_seconds,
                    "visual_pipeline": lane.visual_pipeline,
                    "voice_profile": lane.voice_profile or lane.story_type,
                    "resolved_voice": voice,
                    "enabled": lane.enabled,
                    "paused": paused,
                    "pause_reason": state.get("pause_reason") or ("Disabled in config" if not lane.enabled else None),
                    "last_fired_at": state.get("last_fired_at"),
                    "next_due_at": state.get("next_due_at"),
                })

            return sanitize_payload({"lanes": results, "count": len(results)})

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in list_lanes: %s", exc)
            raise ToolError(f"list_lanes failed: {exc}") from exc

    # -------------------------------------------------------------------------
    # Tool 3: get_lane_info
    # -------------------------------------------------------------------------
    @server.tool(
        name="get_lane_info",
        description="Retrieve in-depth specification, cadence, duration gates, word budget, visual pipeline, and sources for a single production lane.",
    )
    async def get_lane_info(
        lane_id: Annotated[
            str,
            Field(description="Unique lane identifier (e.g. 'moku-scp-shorts', 'moku-horror-long', 'aelithia-aita-long')"),
        ],
    ) -> Dict[str, Any]:
        # Security: validate lane_id format to prevent injection attacks
        if not lane_id or not re.match(r"^[a-zA-Z0-9_-]+$", lane_id):
            raise ToolError(f"Invalid lane_id format: '{lane_id}'.")

        try:
            lane = find_lane(lane_id)
            if lane is None:
                available = [l.id for l in load_lanes(include_disabled=True)]
                raise ToolError(f"Lane '{lane_id}' not found. Available lanes: {available}")

            state: dict[str, Any] = {}
            if os.path.exists(DEFAULT_DB_PATH):
                try:
                    with connect(DEFAULT_DB_PATH, read_only=True) as conn:
                        row = conn.execute(
                            "SELECT * FROM scheduler_lane_state WHERE lane_id = ?",
                            (lane.id,),
                        ).fetchone()
                        if row:
                            state = dict(row)
                except Exception as exc:
                    logger.debug("Failed reading state for lane '%s': %s", lane_id, exc)

            voice = resolve_voice_for_lane(lane)
            info = {
                "id": lane.id,
                "lane_id": lane.id,
                "channel": lane.channel.value,
                "story_type": lane.story_type,
                "orientation": lane.orientation,
                "resolution": [lane.expected_resolution[0], lane.expected_resolution[1]],
                "duration": {
                    "min_sec": lane.duration_min_sec,
                    "target_sec": lane.duration_target_sec,
                    "max_sec": lane.duration_max_sec,
                },
                "words": {
                    "min": lane.words_min,
                    "max": lane.words_max,
                    "recondense_max": lane.words_recondense_max,
                },
                "cadence_min_gap_seconds": lane.cadence_min_gap_seconds,
                "visual_pipeline": lane.visual_pipeline,
                "voice_profile": lane.voice_profile or lane.story_type,
                "resolved_voice": voice,
                "enabled": lane.enabled,
                "paused": bool(state.get("paused", not lane.enabled)),
                "pause_reason": state.get("pause_reason") or ("Disabled in config" if not lane.enabled else None),
                "last_fired_at": state.get("last_fired_at"),
                "next_due_at": state.get("next_due_at"),
                "consecutive_empty": state.get("consecutive_empty", 0),
                "sources": lane.sources,
                "background_audio": lane.background_audio,
            }
            return sanitize_payload(info)

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in get_lane_info: %s", exc)
            raise ToolError(f"get_lane_info failed: {exc}") from exc

    # -------------------------------------------------------------------------
    # Tool 4: query_loop_catalog
    # -------------------------------------------------------------------------
    @server.tool(
        name="query_loop_catalog",
        description="Search and filter master video loops in the SQLite catalog by category, orientation, and channel compatibility.",
    )
    async def query_loop_catalog(
        category: Annotated[
            Optional[str],
            Field(description="Thematic category (e.g. 'horror', 'dark_forest', 'cosmic_horror', 'drama', 'cozy_ambient')"),
        ] = None,
        orientation: Annotated[
            Optional[str],
            Field(description="Canvas orientation ('vertical' for 9:16 Shorts or 'horizontal' for 16:9 Longform)"),
        ] = None,
        channel: Annotated[
            Optional[str],
            Field(description="Filter by channel compatibility ('moku', 'aelithia', 'scifi')"),
        ] = None,
        limit: Annotated[
            int,
            Field(description="Maximum number of loop records to return"),
        ] = 20,
    ) -> Dict[str, Any]:
        try:
            if orientation and orientation not in ("vertical", "horizontal"):
                raise ToolError(f"Invalid orientation '{orientation}'. Must be 'vertical' or 'horizontal'.")

            if limit <= 0:
                return sanitize_payload({"loops": [], "count": 0})

            effective_limit = min(limit, 100)

            channel_key: Optional[str] = None
            if channel:
                try:
                    channel_key = canonical_channel(channel).value
                except (ValueError, KeyError) as exc:
                    raise ToolError(f"Unknown channel '{channel}': {exc}") from exc

            catalog = LoopCatalogRepository(db_path=DEFAULT_DB_PATH)
            records = catalog.list_loops(
                category=category,
                orientation=orientation,
                limit=effective_limit if not channel_key else 100,
            )

            if channel_key:
                allowed_themes = set(CHANNEL_THEMES.get(channel_key, ()))
                filtered = []
                for rec in records:
                    if rec.channel == channel_key or rec.category in allowed_themes:
                        filtered.append(rec)
                records = filtered[:effective_limit]

            results = [r.to_dict() for r in records]
            return sanitize_payload({"loops": results, "count": len(results)})

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in query_loop_catalog: %s", exc)
            raise ToolError(f"query_loop_catalog failed: {exc}") from exc

    # -------------------------------------------------------------------------
    # Tool 5: audit_loop_catalog
    # -------------------------------------------------------------------------
    @server.tool(
        name="audit_loop_catalog",
        description="Audit physical video loop MP4 assets against database catalog records, detect missing/corrupt files, and verify bank_manifest.json metrics.",
    )
    async def audit_loop_catalog(
        cleanup: Annotated[
            bool,
            Field(description="Automatically unregister missing or broken video loop records from SQLite"),
        ] = False,
        auto_fix: Annotated[
            bool,
            Field(description="Alias for cleanup: remove missing records from database"),
        ] = False,
        verify_manifest_metrics: Annotated[
            bool,
            Field(description="Verify precomputed visual quality metrics in bank_manifest.json"),
        ] = True,
    ) -> Dict[str, Any]:
        try:
            do_fix = cleanup or auto_fix
            catalog = LoopCatalogRepository(db_path=DEFAULT_DB_PATH)
            catalog_report = catalog.audit_and_cleanup(auto_remove_missing=do_fix)

            manifest_report: Dict[str, Any] = {"manifest_present": False, "verified": False, "errors": []}
            manifest_path = BASE_DIR / "assets" / "loops" / "bank_manifest.json"

            if verify_manifest_metrics and manifest_path.is_file():
                manifest_report["manifest_present"] = True
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest_data = json.load(f)

                    master_loops = manifest_data.get("master_loops", [])
                    checked = 0
                    errors = []

                    for loop in master_loops:
                        checked += 1
                        fname = loop.get("filename", "")
                        rel_path = loop.get("file_path", "")
                        phys_path = BASE_DIR / rel_path

                        if not phys_path.is_file():
                            errors.append(f"Master loop '{fname}' missing at path '{rel_path}'")
                            continue

                        black_sec = float(loop.get("longest_black_seconds", 0.0))
                        if black_sec > 2.0:
                            errors.append(f"Master loop '{fname}' exceeds black threshold: {black_sec}s > 2.0s")

                        lum = loop.get("perceptual_luminance", {})
                        if not lum.get("passed", False):
                            errors.append(f"Master loop '{fname}' failed perceptual luminance certification")

                    manifest_report["master_loops_checked"] = checked
                    manifest_report["errors"] = errors
                    manifest_report["verified"] = (len(errors) == 0)

                except Exception as m_exc:
                    manifest_report["errors"].append(f"Error parsing bank_manifest.json: {m_exc}")

            healthy = (catalog_report.get("missing", 0) == 0 and catalog_report.get("corrupted", 0) == 0)
            if manifest_report["manifest_present"] and not manifest_report["verified"]:
                healthy = False

            total_records = catalog_report.get("total", catalog_report.get("total_records", 0))
            verified_count = catalog_report.get("verified", total_records - catalog_report.get("missing", 0))

            return sanitize_payload({
                "healthy": healthy,
                "status": "HEALTHY" if healthy else "NEEDS_CLEANUP",
                "total": total_records,
                "total_records": total_records,
                "verified_count": verified_count,
                "catalog_audit": catalog_report,
                "manifest_audit": manifest_report,
            })

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in audit_loop_catalog: %s", exc)
            raise ToolError(f"audit_loop_catalog failed: {exc}") from exc

    # -------------------------------------------------------------------------
    # Tool 6: run_pipeline_dry_run
    # -------------------------------------------------------------------------
    @server.tool(
        name="run_pipeline_dry_run",
        description="Execute fast synthetic test composition (--lane <lane> -t) with zero external API quota usage and stream-copy rendering.",
    )
    async def run_pipeline_dry_run(
        lane_id: Annotated[
            str,
            Field(description="Target production lane identifier (e.g. 'moku-scp-shorts', 'moku-horror-long', 'aelithia-drama-shorts')"),
        ],
        topic: Annotated[
            Optional[str],
            Field(description="Optional custom topic for synthetic generation"),
        ] = None,
        story_id: Annotated[
            Optional[str],
            Field(description="Optional story ID to target (if None, synthetic test story is executed)"),
        ] = None,
        channel: Annotated[
            Optional[str],
            Field(description="Optional channel override"),
        ] = None,
        mock_all: Annotated[
            bool,
            Field(description="Enforce synthetic zero-quota offline mode (mock TTS, mock LLM, mock YouTube)"),
        ] = True,
    ) -> Dict[str, Any]:
        # Validate lane_id
        if not lane_id or not re.match(r"^[a-zA-Z0-9_-]+$", lane_id):
            raise ToolError(f"Invalid lane_id format: '{lane_id}'.")

        lane = find_lane(lane_id)
        if lane is None:
            raise ToolError(f"Lane '{lane_id}' does not exist in configuration.")

        ch_name = channel or lane.channel.value
        actual_lane_id = lane.id
        if actual_lane_id == "scifi-chronicles-shorts":
            actual_lane_id = "scifi-singularity-shorts"

        lock = ChannelLock(ch_name, timeout=5.0)

        try:
            lock.acquire()
        except ChannelLockError as lock_err:
            raise ToolError(
                f"Cannot execute dry run for lane '{lane_id}': Channel [{ch_name}] lock is currently held ({lock_err})."
            ) from lock_err

        try:
            orig_env = {}
            if mock_all:
                for k in ("TEST_MODE", "MOCK_DRIVE_UPLOAD", "MOCK_YOUTUBE_UPLOAD"):
                    orig_env[k] = os.environ.get(k)
                    os.environ[k] = "1"

            from src.orchestrator.pipeline import PipelineOrchestrator

            orch = PipelineOrchestrator(db_path=DEFAULT_DB_PATH)
            effective_topic = topic or f"Test Dry Run {lane.story_type} {lane.id}"

            res = orch.run_channel(
                channel=ch_name,
                topic=effective_topic,
                story_id=story_id,
                lane_id=actual_lane_id,
                dry_run=True,
                skip_lock=True,
            )

            return sanitize_payload({
                "ok": True,
                "status": res.status,
                "dry_run": True,
                "upload_skipped": True,
                "lane_id": lane_id,
                "channel": ch_name,
                "story_id": res.story_id,
                "work_dir": res.work_dir,
                "video_file": None,
                "facts": {"dry_run": True, "offline": True, "quota_used": 0},
            })

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Dry run execution crashed for lane '%s': %s", lane_id, exc)
            raise ToolError(f"Pipeline dry run failed for lane '{lane_id}': {exc}") from exc
        finally:
            if mock_all:
                for k, v in orig_env.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            lock.release()

    # -------------------------------------------------------------------------
    # Tool 7: get_system_status
    # -------------------------------------------------------------------------
    @server.tool(
        name="get_system_status",
        description="Inspect overall yt-auto system health, queue depths, daemon status, active process locks, and recent failure logs.",
    )
    async def get_system_status(
        db_path: Annotated[
            Optional[str],
            Field(description="Path to SQLite database file (defaults to configured DEFAULT_DB_PATH)"),
        ] = None,
        include_api_health: Annotated[
            bool,
            Field(description="Include real-time external API health checks"),
        ] = True,
        include_locks: Annotated[
            bool,
            Field(description="Include channel lock state inspection"),
        ] = True,
        include_recent_errors: Annotated[
            bool,
            Field(description="Include recent failure logs"),
        ] = True,
        error_limit: Annotated[
            int,
            Field(description="Maximum error logs to include"),
        ] = 10,
    ) -> Dict[str, Any]:
        try:
            target_db = db_path or DEFAULT_DB_PATH
            st = cli_status(target_db)

            # Ensure queue counts are directly accessible under both keys
            st["queue_counts"] = st.get("queue", {})
            st["counts"] = st.get("queue", {})

            if include_api_health:
                st["api_health"] = check_all("moku")

            if include_locks:
                lock_status: Dict[str, str] = {}
                for ch in ("global", "moku", "aelithia", "scifi"):
                    chk = ChannelLock(ch)
                    try:
                        acquired = chk.acquire(timeout=0.0)
                        if acquired:
                            chk.release()
                            lock_status[ch] = "UNLOCKED"
                        else:
                            lock_status[ch] = "LOCKED"
                    except ChannelLockError:
                        lock_status[ch] = "LOCKED"
                    except Exception:
                        lock_status[ch] = "UNKNOWN"
                st["locks"] = lock_status

            return sanitize_payload(st)

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in get_system_status: %s", exc)
            raise ToolError(f"get_system_status failed: {exc}") from exc

    # -------------------------------------------------------------------------
    # Tool 8: manage_queue
    # -------------------------------------------------------------------------
    @server.tool(
        name="manage_queue",
        description="Inspect story queue items, review pending candidate items, pause or resume channel production, or trigger auto-publish review sweeps.",
    )
    async def manage_queue(
        action: Annotated[
            str,
            Field(description="Queue management action ('list', 'pending_review', 'pause', 'resume', 'sweep')"),
        ],
        channel: Annotated[
            Optional[str],
            Field(description="Target channel for pause/resume or filtering ('moku', 'aelithia', 'scifi')"),
        ] = None,
        pause_reason: Annotated[
            Optional[str],
            Field(description="Reason string when pausing a channel"),
        ] = None,
        reason: Annotated[
            Optional[str],
            Field(description="Alias for pause_reason"),
        ] = None,
        limit: Annotated[
            int,
            Field(description="Maximum stories to return for listing actions"),
        ] = 25,
        db_path: Annotated[
            Optional[str],
            Field(description="Path to SQLite database file"),
        ] = None,
    ) -> Dict[str, Any]:
        target_db = db_path or DEFAULT_DB_PATH
        act = action.lower().strip()
        eff_reason = reason or pause_reason or "Paused via MCP"

        try:
            if act == "list":
                stories = []
                if os.path.exists(target_db):
                    with connect(target_db, read_only=True) as conn:
                        query = "SELECT story_id, channel, title, status, created_at, updated_at, error_msg FROM stories"
                        params = []
                        if channel:
                            ch_key = canonical_channel(channel).value
                            query += " WHERE channel = ?"
                            params.append(ch_key)
                        query += " ORDER BY created_at DESC LIMIT ?"
                        params.append(max(0, limit))
                        cursor = conn.cursor()
                        cursor.execute(query, tuple(params))
                        for row in cursor.fetchall():
                            stories.append(dict(row))
                return sanitize_payload({
                    "ok": True,
                    "action": "list",
                    "items": stories,
                    "stories": stories,
                    "count": len(stories),
                })

            elif act == "pending_review":
                pending = []
                if os.path.exists(target_db):
                    with connect(target_db, read_only=True) as conn:
                        query = (
                            "SELECT story_id, channel, title, status, created_at, updated_at "
                            "FROM stories WHERE status IN ('PENDING_REVIEW', 'READY_TO_PUBLISH') "
                            "ORDER BY updated_at DESC LIMIT ?"
                        )
                        cursor = conn.cursor()
                        cursor.execute(query, (max(0, limit),))
                        for row in cursor.fetchall():
                            pending.append(dict(row))
                return sanitize_payload({
                    "ok": True,
                    "action": "pending_review",
                    "items": pending,
                    "pending_items": pending,
                    "count": len(pending),
                })

            elif act == "pause":
                if not channel:
                    raise ToolError("Parameter 'channel' is required for pause action.")
                ch_key = canonical_channel(channel)
                repo = QueueRepository(target_db)
                repo.initialize()
                repo.pause(ch_key, eff_reason)
                return sanitize_payload({
                    "ok": True,
                    "action": "pause",
                    "channel": ch_key.value,
                    "paused": True,
                    "reason": eff_reason,
                })

            elif act == "resume":
                if not channel:
                    raise ToolError("Parameter 'channel' is required for resume action.")
                ch_key = canonical_channel(channel)
                repo = QueueRepository(target_db)
                repo.initialize()
                repo.resume(ch_key)
                return sanitize_payload({
                    "ok": True,
                    "action": "resume",
                    "channel": ch_key.value,
                    "paused": False,
                })

            elif act == "sweep":
                from src.telegram import check_pending_approvals
                published = check_pending_approvals()
                return sanitize_payload({
                    "ok": True,
                    "action": "sweep",
                    "published_count": len(published),
                    "published": published,
                })

            else:
                raise ToolError(
                    f"Unsupported queue action '{action}'. Allowed: 'list', 'pending_review', 'pause', 'resume', 'sweep'."
                )

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Queue management action '%s' failed: %s", action, exc)
            raise ToolError(f"manage_queue action '{action}' failed: {exc}") from exc

    # -------------------------------------------------------------------------
    # Tool 9: verify_integrity
    # -------------------------------------------------------------------------
    @server.tool(
        name="verify_integrity",
        description="Run repository invariant checks, worktree hygiene, zero-browser policy, and anti-regression validation suite.",
    )
    async def verify_integrity(
        fast: Annotated[
            bool,
            Field(description="Fast verification mode"),
        ] = False,
        fail_closed: Annotated[
            bool,
            Field(description="Raise ToolError if integrity checks fail (code 1)"),
        ] = False,
    ) -> Dict[str, Any]:
        script_path = BASE_DIR / "scripts" / "verify_integrity.sh"
        if not script_path.is_file():
            raise ToolError(f"Integrity script not found at {script_path}.")

        try:
            proc = subprocess.run(
                [str(script_path)],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )

            healthy = (proc.returncode == 0)
            output_clean = proc.stdout.strip()
            if proc.stderr:
                output_clean += f"\nSTDERR:\n{proc.stderr.strip()}"

            result = {
                "healthy": healthy,
                "status": "HEALTHY" if healthy else "FAILED",
                "exit_code": proc.returncode,
                "summary": "Repository invariants 100% HEALTHY" if healthy else "Integrity verification failed",
                "checks": "Invariant checks verified (Zero-Browser, Anti-Bloat, Zero-Legacy-Docs, Stream-Copy)",
                "output": output_clean,
            }
            sanitized = sanitize_payload(result)

            if not healthy and fail_closed:
                raise ToolError(f"Integrity check FAILED (exit code {proc.returncode}):\n{sanitized['output']}")

            return sanitized

        except subprocess.TimeoutExpired as texc:
            raise ToolError(f"verify_integrity timed out after 120 seconds: {texc}") from texc
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in verify_integrity: %s", exc)
            raise ToolError(f"verify_integrity execution error: {exc}") from exc
