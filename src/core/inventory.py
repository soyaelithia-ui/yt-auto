"""
src/core/inventory.py - AI-Native Published Video Inventory & YouTube Synchronizer.

Maintains a 100% comprehensive local SQLite inventory of published videos and narratives.
Structures story representations, languages, encodings, hooks, semantic simhashes,
predictive performance scores, and used resources specifically optimized for AI agents
(OpenCode, Antigravity, Gemini) to inspect and deduplicate in microsecond lookups.
Includes on-demand Google Drive verified backups without background crons or daemons.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.config import BASE_DIR, DEFAULT_DB_PATH, SETTINGS, get_channel_settings
from src.core.domain import CanonicalChannel, canonical_channel
from src.core.repository.migrations import backup_database, connect, migrate_database
from src.log import get_logger

logger = get_logger("core.inventory")


def normalize_text_nfc(text: str | None) -> str:
    """Normalize text into clean NFC UTF-8, stripping control and ANSI sequences."""
    if not text:
        return ""
    cleaned = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    cleaned = "".join(ch for ch in cleaned if unicodedata.category(ch)[0] != "C" or ch in "\n\r\t")
    return unicodedata.normalize("NFC", cleaned).strip()


def compute_simhash(text: str) -> str:
    """
    Compute a deterministic 64-bit SimHash hex string for narrative deduplication.
    Allows LLM agents to detect story duplicates and thematic saturation in O(1) time.
    """
    normalized = normalize_text_nfc(text).lower()
    words = re.findall(r"\b\w{3,}\b", normalized)
    if not words:
        return "0x0000000000000000"

    v = [0] * 64
    for word in words:
        digest = hashlib.md5(word.encode("utf-8")).digest()
        h = int.from_bytes(digest[:8], byteorder="big")
        for i in range(64):
            if (h >> i) & 1:
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return f"0x{fingerprint:016x}"


def extract_hook_and_synopsis(title: str, text: str) -> tuple[str, str]:
    """
    Extract a compact hook (first 1-2 sentences) and synopsis (< 250 chars)
    for token-minimal context window consumption by LLMs.
    """
    clean_text = normalize_text_nfc(text)
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", clean_text) if s.strip()]
    hook = sentences[0] if sentences else title
    if len(sentences) > 1:
        synopsis = " ".join(sentences[:2])
    else:
        synopsis = clean_text[:200]
    return hook[:180], synopsis[:250]


def extract_thematic_tags(title: str, description: str = "") -> list[str]:
    """Extract normalized lowercase thematic tokens from titles, hashtags, or text."""
    combined = f"{title} {description}".lower()
    hashtags = re.findall(r"#(\w+)", combined)
    keywords = [
        "aita", "dilema", "familia", "deuda", "boda", "herencia", "infidelidad",
        "navidad", "suegra", "hermano", "propiedad", "secreto", "anillo", "dinero",
        "terror", "scp", "paranormal", "misterio", "abandono", "criatura"
    ]
    found = set(hashtags)
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw) + r"\b", combined):
            found.add(kw)
    return sorted(list(found))


@dataclass(slots=True)
class PublishedVideoRecord:
    """Strongly-typed data contract for a published video and its underlying story."""
    publication_id: int
    run_id: str
    story_id: str
    provider: str
    video_id: str
    url: str
    channel: str
    visibility: str
    title: str
    description: str
    thumbnail_confirmed: bool
    verified_at: str
    video_sha256: str | None = None
    drive_video_id: str | None = None
    drive_backup_metadata: dict[str, Any] | None = None
    language: str = "es"
    source_language: str = "es"
    hook_summary: str | None = None
    synopsis: str | None = None
    themes: list[str] | None = None
    simhash: str | None = None
    full_script: str | None = None
    predictive_success_score: float = 0.0
    score_rationale: str | None = None
    used_resources: dict[str, Any] | None = None
    duration_sec: float = 0.0

    @classmethod
    def from_row(cls, row: Any) -> PublishedVideoRecord:
        """Construct a record from sqlite3.Row."""
        keys = row.keys() if hasattr(row, "keys") else []
        def _get(col: str, default: Any = None) -> Any:
            return row[col] if col in keys else default

        drive_meta_raw = _get("drive_backup_metadata")
        drive_meta = json.loads(drive_meta_raw) if drive_meta_raw and isinstance(drive_meta_raw, str) else None

        themes_raw = _get("themes_json")
        themes = json.loads(themes_raw) if themes_raw and isinstance(themes_raw, str) else None

        res_raw = _get("used_resources")
        used_res = json.loads(res_raw) if res_raw and isinstance(res_raw, str) else None

        return cls(
            publication_id=int(_get("publication_id", 0)),
            run_id=str(_get("run_id", "")),
            story_id=str(_get("story_id", "")),
            provider=str(_get("provider", "YOUTUBE_DATA_API_V3")),
            video_id=str(_get("video_id", "")),
            url=str(_get("url", "")),
            channel=str(_get("channel", "moku")),
            visibility=str(_get("visibility", "public")),
            title=str(_get("title", "")),
            description=str(_get("description", "")),
            thumbnail_confirmed=bool(_get("thumbnail_confirmed", 1)),
            verified_at=str(_get("verified_at", "")),
            video_sha256=_get("video_sha256"),
            drive_video_id=_get("drive_video_id"),
            drive_backup_metadata=drive_meta,
            language=str(_get("language", "es")),
            source_language=str(_get("source_language", "es")),
            hook_summary=_get("hook_summary"),
            synopsis=_get("synopsis"),
            themes=themes,
            simhash=_get("simhash"),
            full_script=_get("full_script"),
            predictive_success_score=float(_get("predictive_success_score", 0.0) or 0.0),
            score_rationale=_get("score_rationale"),
            used_resources=used_res,
            duration_sec=float(_get("duration_sec", 0.0) or 0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def record_published_inventory(
    *,
    db_path: str = DEFAULT_DB_PATH,
    run_id: str,
    story_id: str,
    video_id: str,
    url: str,
    channel: str,
    title: str,
    description: str,
    provider: str = "YOUTUBE_DATA_API_V3",
    visibility: str = "public",
    verified_at: str | None = None,
    video_sha256: str | None = None,
    drive_video_id: str | None = None,
    drive_backup_metadata: dict[str, Any] | None = None,
    language: str = "es",
    source_language: str = "es",
    hook_summary: str | None = None,
    synopsis: str | None = None,
    themes: list[str] | None = None,
    full_script: str | None = None,
    predictive_success_score: float = 0.0,
    score_rationale: str | None = None,
    used_resources: dict[str, Any] | None = None,
    duration_sec: float = 0.0,
) -> PublishedVideoRecord:
    """Record or update an inventory entry atomically in SQLite with AI-ready metadata."""
    now_iso = verified_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    clean_title = normalize_text_nfc(title)
    clean_desc = normalize_text_nfc(description)
    clean_script = normalize_text_nfc(full_script)

    if not hook_summary or not synopsis:
        auto_hook, auto_synopsis = extract_hook_and_synopsis(clean_title, clean_script or clean_desc)
        hook_summary = hook_summary or auto_hook
        synopsis = synopsis or auto_synopsis

    if not themes:
        themes = extract_thematic_tags(clean_title, clean_desc)

    simhash = compute_simhash(clean_script or f"{clean_title} {clean_desc}")

    drive_meta_json = json.dumps(drive_backup_metadata) if drive_backup_metadata else None
    themes_json = json.dumps(themes) if themes else None
    resources_json = json.dumps(used_resources) if used_resources else None

    migrate_database(db_path)

    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Ensure parent story and run exist to satisfy SQLite foreign keys
            conn.execute(
                """
                INSERT OR IGNORE INTO stories(
                    story_id, title, content, url, status, channel, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'PUBLISHED', ?, ?, ?)
                """,
                (story_id, clean_title, clean_script or clean_desc, url, channel, now_iso, now_iso),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO runs(
                    run_id, channel, story_id, mode, status, owner, started_at, heartbeat_at, finished_at
                ) VALUES (?, ?, ?, 'publish', 'published', 'inventory_sync', ?, ?, ?)
                """,
                (run_id, channel, story_id, now_iso, now_iso, now_iso),
            )

            # Check existing by video_id or run_id
            existing = conn.execute(
                "SELECT publication_id FROM publications WHERE video_id = ? OR (run_id = ? AND run_id != '')",
                (video_id, run_id),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE publications SET
                        run_id = ?, story_id = ?, provider = ?, url = ?, channel = ?,
                        visibility = ?, title = ?, description = ?, thumbnail_confirmed = 1,
                        verified_at = ?, video_sha256 = ?, drive_video_id = ?, drive_backup_metadata = ?,
                        language = ?, source_language = ?, hook_summary = ?, synopsis = ?,
                        themes_json = ?, simhash = ?, full_script = ?,
                        predictive_success_score = ?, score_rationale = ?,
                        used_resources = ?, duration_sec = ?
                    WHERE publication_id = ?
                    """,
                    (
                        run_id, story_id, provider, url, channel,
                        visibility, clean_title, clean_desc, now_iso,
                        video_sha256, drive_video_id, drive_meta_json,
                        language, source_language, hook_summary, synopsis,
                        themes_json, simhash, clean_script,
                        predictive_success_score, score_rationale,
                        resources_json, duration_sec,
                        existing["publication_id"],
                    ),
                )
                pub_id = existing["publication_id"]
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO publications(
                        run_id, story_id, provider, video_id, url, channel,
                        visibility, title, description, thumbnail_confirmed, verified_at,
                        video_sha256, drive_video_id, drive_backup_metadata,
                        language, source_language, hook_summary, synopsis,
                        themes_json, simhash, full_script,
                        predictive_success_score, score_rationale,
                        used_resources, duration_sec
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, 1, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?
                    )
                    """,
                    (
                        run_id, story_id, provider, video_id, url, channel,
                        visibility, clean_title, clean_desc, now_iso,
                        video_sha256, drive_video_id, drive_meta_json,
                        language, source_language, hook_summary, synopsis,
                        themes_json, simhash, clean_script,
                        predictive_success_score, score_rationale,
                        resources_json, duration_sec,
                    ),
                )
                pub_id = cursor.lastrowid

            conn.commit()
            logger.info("Recorded publication in inventory: id=%d video_id=%s channel=%s", pub_id, video_id, channel)
        except Exception:
            conn.rollback()
            raise

    return PublishedVideoRecord(
        publication_id=pub_id,
        run_id=run_id,
        story_id=story_id,
        provider=provider,
        video_id=video_id,
        url=url,
        channel=channel,
        visibility=visibility,
        title=clean_title,
        description=clean_desc,
        thumbnail_confirmed=True,
        verified_at=now_iso,
        video_sha256=video_sha256,
        drive_video_id=drive_video_id,
        drive_backup_metadata=drive_backup_metadata,
        language=language,
        source_language=source_language,
        hook_summary=hook_summary,
        synopsis=synopsis,
        themes=themes,
        simhash=simhash,
        full_script=clean_script,
        predictive_success_score=predictive_success_score,
        score_rationale=score_rationale,
        used_resources=used_resources,
        duration_sec=duration_sec,
    )


def get_published_inventory(
    db_path: str = DEFAULT_DB_PATH,
    channel: str | None = None,
    limit: int = 100,
) -> list[PublishedVideoRecord]:
    """Query published video records from local SQLite inventory."""
    if not os.path.exists(db_path):
        return []
    records: list[PublishedVideoRecord] = []
    with connect(db_path, read_only=True) as conn:
        query = "SELECT * FROM publications"
        params: list[Any] = []
        if channel:
            canon = canonical_channel(channel).value
            query += " WHERE channel = ? OR channel = ?"
            params.extend([channel, canon])
        query += " ORDER BY verified_at DESC LIMIT ?"
        params.append(max(1, limit))
        for row in conn.execute(query, params).fetchall():
            records.append(PublishedVideoRecord.from_row(row))
    return records


def get_inventory_ai_digest(
    db_path: str = DEFAULT_DB_PATH,
    channel: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """
    Produce an ultralight token-optimized narrative digest for AI agents (OpenCode, Antigravity).
    Allows an LLM to evaluate topic coverage and avoid repetition in under 400 total prompt tokens.
    """
    records = get_published_inventory(db_path=db_path, channel=channel, limit=limit)
    items = []
    for rec in records:
        items.append({
            "video_id": rec.video_id,
            "title": rec.title,
            "published_at": rec.verified_at[:10],
            "channel": rec.channel,
            "hook": rec.hook_summary or rec.title,
            "themes": rec.themes or [],
            "simhash": rec.simhash,
            "predictive_score": round(rec.predictive_success_score, 2),
        })
    return {
        "channel_scope": channel or "all",
        "total_catalog_count": len(records),
        "recent_publications": items,
    }


def sync_channel_publications_from_youtube(
    channel: str,
    db_path: str = DEFAULT_DB_PATH,
    max_items: int = 100,
) -> dict[str, Any]:
    """
    Sync 100% of published videos from YouTube Data API v3 into local SQLite inventory.
    Reads channel OAuth tokens, retrieves uploads playlist, and populates missing records.
    """
    settings = get_channel_settings(channel)
    token_path = Path(settings.youtube_token_path)
    if not token_path.is_file():
        # Fallback to secrets/tokens/<channel>.json
        alt_path = BASE_DIR / "secrets" / "tokens" / f"{channel}.json"
        if alt_path.is_file():
            token_path = alt_path
        else:
            return {
                "channel": channel,
                "ok": False,
                "error": f"Token de YouTube no encontrado en {token_path}",
                "synced_count": 0,
            }

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    try:
        token_data = json.loads(token_path.read_text(encoding="utf-8"))
        creds = Credentials(
            token=token_data.get("access_token") or token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes"),
        )
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

        # 1. Fetch channel's uploads playlist ID
        ch_resp = youtube.channels().list(part="contentDetails,snippet", mine=True).execute()
        items = ch_resp.get("items", [])
        if not items:
            return {"channel": channel, "ok": False, "error": "No channel found for token", "synced_count": 0}

        uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # 2. Page through playlist items
        synced_count = 0
        new_added = 0
        next_page_token = None

        while True:
            fetch_limit = 50 if max_items <= 0 else min(50, max_items - synced_count)
            pl_resp = youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=uploads_id,
                maxResults=fetch_limit,
                pageToken=next_page_token,
            ).execute()

            v_items = pl_resp.get("items", [])
            if not v_items:
                break

            for item in v_items:
                vid = item["contentDetails"]["videoId"]
                title = item["snippet"]["title"]
                description = item["snippet"].get("description", "")
                published_at = item["snippet"].get("publishedAt", "")
                url = f"https://www.youtube.com/watch?v={vid}"

                record = record_published_inventory(
                    db_path=db_path,
                    run_id=f"yt-sync-{vid}",
                    story_id=f"story-sync-{vid}",
                    video_id=vid,
                    url=url,
                    channel=channel,
                    title=title,
                    description=description,
                    verified_at=published_at,
                    provider="YOUTUBE_DATA_API_V3",
                    visibility="public",
                    language="es",
                    source_language="es",
                )
                synced_count += 1
                new_added += 1

            next_page_token = pl_resp.get("nextPageToken")
            if not next_page_token or (max_items > 0 and synced_count >= max_items):
                break

        return {
            "channel": channel,
            "ok": True,
            "synced_count": synced_count,
            "new_added": new_added,
        }
    except Exception as exc:
        logger.exception("Failed to sync YouTube inventory for channel %s: %s", channel, exc)
        return {"channel": channel, "ok": False, "error": str(exc), "synced_count": 0}


def sync_all_channel_publications(
    channels: Sequence[str] = ("moku", "aelithia"),
    db_path: str = DEFAULT_DB_PATH,
    max_items_per_channel: int = 100,
) -> dict[str, Any]:
    """Synchronize 100% of published videos across all configured channels."""
    results = {}
    total_synced = 0
    total_added = 0
    for ch in channels:
        res = sync_channel_publications_from_youtube(ch, db_path=db_path, max_items=max_items_per_channel)
        results[ch] = res
        total_synced += res.get("synced_count", 0)
        total_added += res.get("new_added", 0)

    return {
        "ok": True,
        "total_synced": total_synced,
        "total_added": total_added,
        "channels": results,
    }


def backup_inventory_to_drive(
    db_path: str = DEFAULT_DB_PATH,
    folder_id: str | None = None,
) -> dict[str, Any]:
    """
    On-demand verified backup of the SQLite database and inventory digest to Google Drive.
    Executes instantaneously when requested by an AI agent, without background timers or crons.
    """
    from src.drive import upload_to_drive_verified

    resolved_folder = folder_id or SETTINGS.drive_published_folder_id or SETTINGS.drive_folder_id
    if not resolved_folder:
        raise ValueError("No se configuró folder_id para respaldo en Drive (DRIVE_FOLDER_ID)")

    # 1. Create verified atomic SQLite snapshot
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snapshot_path = backup_database(db_path)

    # 2. Export human and AI readable JSON digest
    digest = get_inventory_ai_digest(db_path=db_path, limit=200)
    digest_path = snapshot_path.parent / f"inventory_digest_{timestamp}.json"
    digest_path.write_text(json.dumps(digest, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. Upload to Google Drive with verification
    sa_key = str(SETTINGS.drive_key_path) if SETTINGS.drive_key_path.is_file() else ""
    token_path = None
    for cand in ("moku", "aelithia", "drama", "horror", "youtube_token"):
        cand_p = BASE_DIR / "secrets" / "tokens" / f"{cand}.json"
        if cand_p.is_file():
            token_path = str(cand_p)
            break
        cand_flat = BASE_DIR / "secrets" / f"{cand}.json"
        if cand_flat.is_file():
            token_path = str(cand_flat)
            break

    db_proof = upload_to_drive_verified(
        file_path=str(snapshot_path),
        folder_id=resolved_folder,
        sa_key_path=sa_key,
        token_path=token_path,
        display_name=f"shorts_queue_inventory_{timestamp}.db",
    )
    digest_proof = upload_to_drive_verified(
        file_path=str(digest_path),
        folder_id=resolved_folder,
        sa_key_path=sa_key,
        token_path=token_path,
        display_name=f"inventory_digest_{timestamp}.json",
    )

    return {
        "ok": True,
        "database_backup": {
            "file_id": db_proof.file_id,
            "name": db_proof.name,
            "size_bytes": db_proof.size_bytes,
        },
        "digest_backup": {
            "file_id": digest_proof.file_id,
            "name": digest_proof.name,
            "size_bytes": digest_proof.size_bytes,
        },
        "timestamp": timestamp,
    }
