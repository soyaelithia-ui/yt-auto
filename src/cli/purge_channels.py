"""
src/cli/purge_channels.py - Safe Channel Video Purge and Audit CLI.

Provides dry-run catalog inspection, interactive affirmative confirmation ("DELETE"),
channel ownership verification, and paced deletion with HTTP 429 quota protection.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.core.domain import canonical_channel
from src.youtube.control import (
    _service_for_channel,
    expected_channel_id,
)

logger = logging.getLogger("purge_channels")


@dataclass
class PurgeItemResult:
    video_id: str
    title: str
    status: str  # "deleted" | "skipped" | "failed" | "dry_run"
    error: Optional[str] = None


@dataclass
class PurgeReport:
    channel: str
    total_found: int
    deleted_count: int
    skipped_count: int
    failed_count: int
    items: List[PurgeItemResult] = field(default_factory=list)


def _is_quota_error(exc: Exception) -> bool:
    """Detects HTTP 429 or quota exceeded errors from Google API."""
    try:
        from googleapiclient.errors import HttpError
        if isinstance(exc, HttpError):
            if hasattr(exc, "resp") and getattr(exc.resp, "status", None) == 429:
                return True
            if "quota" in str(exc).lower():
                return True
    except ImportError:
        pass
    err_str = str(exc).lower()
    return "quota" in err_str or "rate limit" in err_str or "429" in err_str


def _fetch_channel_videos(youtube: Any, channel: str) -> List[Dict[str, Any]]:
    """Retrieves all candidate videos uploaded for the canonical channel."""
    wanted_channel_id = expected_channel_id(channel)
    results: List[Dict[str, Any]] = []
    seen_ids = set()
    page_token: Optional[str] = None

    while True:
        search_kwargs: Dict[str, Any] = {
            "part": "snippet",
            "maxResults": 50,
            "type": "video",
        }
        if wanted_channel_id:
            search_kwargs["channelId"] = wanted_channel_id
        else:
            search_kwargs["forMine"] = True
        if page_token:
            search_kwargs["pageToken"] = page_token

        try:
            response = youtube.search().list(**search_kwargs).execute()
            items = response.get("items") or []
        except Exception as exc:
            logger.warning("YouTube search.list failed for channel %s: %s", channel, exc)
            if _is_quota_error(exc):
                raise
            break

        for item in items:
            vid_id = ""
            if isinstance(item.get("id"), dict):
                vid_id = item["id"].get("videoId", "")
            elif isinstance(item.get("id"), str):
                vid_id = item["id"]

            snippet = item.get("snippet") or {}
            title = snippet.get("title", "Untitled")
            ch_id = snippet.get("channelId", "")
            if vid_id and vid_id not in seen_ids:
                seen_ids.add(vid_id)
                results.append({
                    "video_id": vid_id,
                    "title": title,
                    "channel_id": ch_id,
                })

        page_token = response.get("nextPageToken")
        if not page_token or len(results) >= 500:
            break

    # Also inspect uploads playlist for non-search-indexed / private / unlisted videos
    try:
        uploads_playlist = None
        if hasattr(youtube, "channels"):
            ch_kwargs: Dict[str, Any] = {"part": "contentDetails"}
            if wanted_channel_id:
                ch_kwargs["id"] = wanted_channel_id
            else:
                ch_kwargs["mine"] = True
            ch_resp = youtube.channels().list(**ch_kwargs).execute()
            if isinstance(ch_resp, dict):
                ch_items = ch_resp.get("items") or []
                if ch_items and isinstance(ch_items, list) and isinstance(ch_items[0], dict):
                    uploads_playlist = (
                        ch_items[0]
                        .get("contentDetails", {})
                        .get("relatedPlaylists", {})
                        .get("uploads")
                    )
        if not uploads_playlist and wanted_channel_id and str(wanted_channel_id).startswith("UC"):
            uploads_playlist = "UU" + str(wanted_channel_id)[2:]

        if uploads_playlist and hasattr(youtube, "playlistItems"):
            pl_token = None
            for _ in range(20):  # safety bound to prevent infinite pagination
                pl_resp = youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=uploads_playlist,
                    maxResults=50,
                    pageToken=pl_token,
                ).execute()
                if not isinstance(pl_resp, dict):
                    break
                items = pl_resp.get("items")
                if not isinstance(items, list):
                    break
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    vid_id = (item.get("contentDetails") or {}).get("videoId")
                    snippet = item.get("snippet") or {}
                    title = snippet.get("title", "Untitled")
                    ch_id = snippet.get("channelId", wanted_channel_id or "")
                    if vid_id and vid_id not in seen_ids:
                        if title == "Deleted video":
                            continue
                        seen_ids.add(vid_id)
                        results.append({
                            "video_id": vid_id,
                            "title": title,
                            "channel_id": ch_id,
                        })
                pl_token = pl_resp.get("nextPageToken")
                if not isinstance(pl_token, str) or not pl_token.strip() or len(results) >= 500:
                    break
    except Exception as exc:
        logger.debug("Uploads playlist scan completed or skipped: %s", exc)

    return results


def purge_channel_videos(
    channel: str,
    dry_run: bool = True,
    force: bool = False,
    delay_sec: float = 0.5,
    confirm_input: Optional[Callable[[], str]] = None,
) -> PurgeReport:
    """
    Audits and purges videos for a specified channel with safety guards:
    - Dry-run by default
    - Explicit "DELETE" confirmation prompt
    - Channel ownership verification
    - Paced batch deletion (delay_sec >= 0.5s)
    - Circuit breaker on HTTP 429 quota exhaustion
    """
    ch_obj = canonical_channel(channel)
    channel_key = ch_obj.value if hasattr(ch_obj, "value") else str(ch_obj)
    youtube = _service_for_channel(channel_key)
    wanted_channel_id = expected_channel_id(ch_obj)

    candidates = _fetch_channel_videos(youtube, channel_key)
    total_found = len(candidates)

    if total_found == 0:
        logger.info("No se encontraron videos para el canal '%s'.", channel_key)
        return PurgeReport(
            channel=channel_key,
            total_found=0,
            deleted_count=0,
            skipped_count=0,
            failed_count=0,
            items=[],
        )

    # 1. Handle Dry-Run Mode
    if dry_run:
        logger.info("[DRY-RUN] Se encontraron %d videos candidatos en '%s'.", total_found, channel_key)
        items = [
            PurgeItemResult(
                video_id=c["video_id"],
                title=c["title"],
                status="dry_run",
            )
            for c in candidates
        ]
        return PurgeReport(
            channel=channel_key,
            total_found=total_found,
            deleted_count=0,
            skipped_count=0,
            failed_count=0,
            items=items,
        )

    # 2. Interactive Confirmation Prompt
    if not force:
        prompt_fn = confirm_input or input
        prompt_msg = (
            f"ADVERTENCIA: Va a eliminar permanentemente {total_found} videos del canal '{channel_key}'.\n"
            f"Escriba 'DELETE' para confirmar la eliminacion: "
        )
        token = prompt_fn(prompt_msg).strip()
        if token != "DELETE":
            logger.warning("Operacion de purga cancelada por el usuario.")
            items = [
                PurgeItemResult(
                    video_id=c["video_id"],
                    title=c["title"],
                    status="skipped",
                    error="Confirmacion cancelada por el usuario",
                )
                for c in candidates
            ]
            return PurgeReport(
                channel=channel_key,
                total_found=total_found,
                deleted_count=0,
                skipped_count=total_found,
                failed_count=0,
                items=items,
            )

    # 3. Live Deletion with Ownership & Quota Guards
    items = []
    deleted_count = 0
    skipped_count = 0
    failed_count = 0

    for idx, c in enumerate(candidates):
        vid = c["video_id"]
        title = c["title"]
        cand_channel_id = c.get("channel_id", "")

        # Verify Ownership
        if wanted_channel_id and cand_channel_id and cand_channel_id != wanted_channel_id:
            err_msg = (
                f"El video {vid} pertenece al canal {cand_channel_id}, "
                f"no al canal configurado '{channel_key}' ({wanted_channel_id})"
            )
            logger.error("Eliminacion rechazada por propiedad: %s", err_msg)
            items.append(PurgeItemResult(video_id=vid, title=title, status="skipped", error=err_msg))
            skipped_count += 1
            continue

        # Check ownership via videos().list if snippet wasn't complete
        if wanted_channel_id and not cand_channel_id:
            try:
                v_res = youtube.videos().list(part="snippet", id=vid).execute()
                v_items = v_res.get("items") or []
                if v_items:
                    actual_ch = (v_items[0].get("snippet") or {}).get("channelId", "")
                    if actual_ch != wanted_channel_id:
                        err_msg = (
                            f"El video {vid} pertenece al canal {actual_ch}, "
                            f"no al canal configurado '{channel_key}' ({wanted_channel_id})"
                        )
                        items.append(PurgeItemResult(video_id=vid, title=title, status="skipped", error=err_msg))
                        skipped_count += 1
                        continue
            except Exception as exc:
                if _is_quota_error(exc):
                    items.append(PurgeItemResult(video_id=vid, title=title, status="failed", error=str(exc)))
                    failed_count += 1
                    for rem in candidates[idx + 1:]:
                        items.append(PurgeItemResult(video_id=rem["video_id"], title=rem["title"], status="skipped", error="Quota exceeded"))
                        skipped_count += 1
                    break

        # Pacing Delay between consecutive deletions
        if idx > 0 and delay_sec > 0:
            time.sleep(delay_sec)

        try:
            youtube.videos().delete(id=vid).execute()
            logger.info("Video eliminado: %s (%s)", vid, title)
            items.append(PurgeItemResult(video_id=vid, title=title, status="deleted"))
            deleted_count += 1
        except Exception as exc:
            logger.error("Error al eliminar video %s: %s", vid, exc)
            items.append(PurgeItemResult(video_id=vid, title=title, status="failed", error=str(exc)))
            failed_count += 1

            if _is_quota_error(exc):
                logger.critical("Cuota de YouTube API agotada o HTTP 429. Abortando purga...")
                for rem in candidates[idx + 1:]:
                    items.append(
                        PurgeItemResult(
                            video_id=rem["video_id"],
                            title=rem["title"],
                            status="skipped",
                            error="Purga abortada por agotamiento de cuota API",
                        )
                    )
                    skipped_count += 1
                break

    return PurgeReport(
        channel=channel_key,
        total_found=total_found,
        deleted_count=deleted_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        items=items,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube Channel Video Purge Tool")
    parser.add_argument("-c", "--channel", type=str, required=True, help="Canonical channel identifier ('horror' / canal 1, 'drama' / canal 2, 'scifi')")
    parser.add_argument("--execute", action="store_true", default=False, help="Execute live video deletions (default: dry-run inspection mode)")
    parser.add_argument("--force", action="store_true", default=False, help="Bypass interactive 'DELETE' confirmation prompt")
    parser.add_argument("--delay", type=float, default=0.5, help="Pacing delay in seconds between deletions (default: 0.5s)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    report = purge_channel_videos(
        channel=args.channel,
        dry_run=not args.execute,
        force=args.force,
        delay_sec=args.delay,
    )

    print("\n" + "=" * 60)
    print(f"RESUMEN DE PURGA - CANAL: {report.channel.upper()}")
    print(f"Total encontrados: {report.total_found}")
    print(f"Eliminados:        {report.deleted_count}")
    print(f"Omitidos:          {report.skipped_count}")
    print(f"Fallidos:          {report.failed_count}")
    print("=" * 60)
    for item in report.items:
        err_info = f" ({item.error})" if item.error else ""
        print(f" - [{item.status.upper()}] {item.video_id}: {item.title}{err_info}")

    return 0 if report.failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
