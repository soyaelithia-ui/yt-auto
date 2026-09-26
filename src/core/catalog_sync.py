"""
src/core/catalog_sync.py - Asset synchronization, hashing, and probing for video loops.

Scans filesystem assets under assets/loops/, extracts metadata via ffprobe,
calculates SHA-256 digests, and synchronizes records into LoopCatalogRepository.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple

from src.config import BASE_DIR
from src.log import get_logger

logger = get_logger("loop_catalog.sync")

_LEGACY_CHECKOUT_PREFIXES = tuple(
    p for p in (
        os.environ.get("YT_AUTO_LEGACY_PREFIX", "").strip(),
        "/srv/projects/yt-auto",
    ) if p
)


def _catalog_repo_root(repo_root: Path | None = None) -> Path:
    """Prefer explicit arg, then YT_AUTO_ROOT env, then BASE_DIR."""
    if repo_root is not None:
        return Path(repo_root)
    env_root = os.environ.get("YT_AUTO_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser()
    try:
        import src.core.catalog as cat
        return Path(getattr(cat, "BASE_DIR", BASE_DIR))
    except Exception:
        return BASE_DIR


def resolve_loop_file_path(path: str | Path, repo_root: Path | None = None) -> Path:
    """Map a catalog path onto the current checkout."""
    root = _catalog_repo_root(repo_root)
    p = Path(path)
    if p.is_file():
        return p
    text = str(p)
    for prefix in _LEGACY_CHECKOUT_PREFIXES:
        if text == prefix or text.startswith(prefix + "/"):
            alt = root / text[len(prefix):].lstrip("/")
            if alt.is_file():
                return alt
    if not p.is_absolute():
        alt = root / p
        if alt.is_file():
            return alt
    return p


def compute_file_sha256(path: str | Path) -> str:
    """Computes standard SHA-256 hexadecimal digest for a file using 64KB buffer chunks."""
    p = Path(path)
    if not p.is_file():
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_video_metadata(file_path: Path) -> Optional[Tuple[int, int, float, int]]:
    """Extract width, height, duration_sec, fps using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration",
        "-show_entries", "format=duration",
        "-of", "json", str(file_path)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode != 0 or not res.stdout:
            return None
        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        if not streams:
            return None
        stream = streams[0]
        fmt = data.get("format", {})
        w = int(stream.get("width") or 0)
        h = int(stream.get("height") or 0)
        if w <= 0 or h <= 0:
            return None
        dur = float(stream.get("duration") or fmt.get("duration") or 0.0)
        if dur <= 0.0:
            return None
        fps_str = stream.get("r_frame_rate", "24/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = round(float(num) / float(den)) if float(den) != 0 else 24
        else:
            fps = int(float(fps_str)) if fps_str else 24
        if fps <= 0:
            fps = 24
        return w, h, dur, fps
    except Exception:
        return None


def sync_catalog_from_assets(
    repo: Any,
    assets_dir: Optional[Path | str] = None,
    force_rescan: bool = False,
) -> int:
    """
    Enumerate all .mp4 and .webm in assets/loops/horizontal/ and vertical/ (including atomic/ subfolders),
    extract orientation, category, dimensions, duration, fps, technology, and SHA-256 digest,
    and upsert into the video_loops table idempotently.
    """
    repo_root = _catalog_repo_root()
    if assets_dir is None:
        loops_root = repo_root / "assets" / "loops"
    else:
        p = Path(assets_dir)
        if (p / "horizontal").is_dir() or (p / "vertical").is_dir():
            loops_root = p
        elif (p / "loops" / "horizontal").is_dir() or (p / "loops" / "vertical").is_dir():
            loops_root = p / "loops"
        else:
            loops_root = p

    if not loops_root.is_dir():
        logger.warning("Loops root directory not found: %s", loops_root)
        return 0

    upsert_sql = """
    INSERT INTO video_loops (
        loop_id, category, technology, theme_tags, orientation,
        width, height, duration_sec, fps, file_path,
        file_size_bytes, sha256, generator_params_json,
        usage_count, last_used_at, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(loop_id) DO UPDATE SET
        category = excluded.category,
        technology = excluded.technology,
        theme_tags = excluded.theme_tags,
        orientation = excluded.orientation,
        width = excluded.width,
        height = excluded.height,
        duration_sec = excluded.duration_sec,
        fps = excluded.fps,
        file_path = excluded.file_path,
        file_size_bytes = excluded.file_size_bytes,
        sha256 = excluded.sha256,
        generator_params_json = excluded.generator_params_json
    """

    rows_to_upsert: List[Tuple[Any, ...]] = []
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for orient in ("horizontal", "vertical"):
        orient_dir = loops_root / orient
        if not orient_dir.is_dir():
            continue

        candidates = sorted([
            f for f in orient_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in (".mp4", ".webm")
        ])

        for file_p in candidates:
            if file_p.name.startswith("."):
                continue
            try:
                file_size = file_p.stat().st_size
            except OSError:
                continue
            if file_size < 25_000:
                continue

            row = _build_asset_loop_row(file_p, orient, orient_dir, repo_root, now_iso)
            if row:
                rows_to_upsert.append(row)

    if rows_to_upsert:
        with repo._get_connection() as conn:
            conn.executemany(upsert_sql, rows_to_upsert)
            conn.commit()
        logger.info("Successfully synced %d video loops from assets", len(rows_to_upsert))

    return len(rows_to_upsert)


def _build_asset_loop_row(
    file_p: Path,
    orient: str,
    orient_dir: Path,
    repo_root: Path,
    now_iso: str,
) -> Optional[Tuple[Any, ...]]:
    """Helper to parse and construct a single video loop database row."""
    rel = file_p.relative_to(orient_dir)
    category = "general"
    if len(rel.parts) > 1:
        category = rel.parts[0].strip().lower().replace("-", "_")
        if category == "atomic":
            category = "general"

    is_atomic = "atomic" in rel.parts
    is_master = "_master_60s" in file_p.name
    stem = file_p.stem.lower()

    # Channel attribution
    channel = None
    from src.core.channel_profile import ChannelProfileRegistry
    for ch in ChannelProfileRegistry.list_active_channel_ids():
        if stem.startswith(f"{ch}_") or ch in rel.parts:
            channel = ch
            break

    # Extract theme tags
    tags = {category, orient}
    if channel:
        tags.add(channel)
        tags.add(f"channel:{channel}")
    if is_atomic:
        tags.add("atomic")
    if is_master:
        tags.add("master")
        tags.add("60s")

    tokens = [t.lower() for t in re.split(r"[_\W]+", stem) if t]
    ignored_tokens = {"mp4", "webm", "master", "60s", "moku", "aelithia", "scifi", "vertical", "horizontal", "short", "loop"}
    for t in tokens:
        if t not in ignored_tokens and len(t) > 1:
            tags.add(t)

    if is_master:
        duration_sec = 60.46
        fps = 24
        width, height = (1920, 1080) if orient == "horizontal" else (1080, 1920)
        technology = "cinematic_master"
    elif is_atomic:
        duration_sec = 6.04
        fps = 24
        width, height = (736, 400) if orient == "horizontal" else (400, 736)
        technology = "cinematic_atomic"
    else:
        meta = probe_video_metadata(file_p)
        if not meta or meta[0] <= 0 or meta[1] <= 0 or meta[2] <= 0:
            logger.warning("Skipping corrupt or unreadable video file: %s", file_p)
            return None
        width, height, duration_sec, fps = meta
        technology = "pre-rendered"

    try:
        stored_path = str(file_p.relative_to(repo_root))
    except ValueError:
        stored_path = str(file_p.resolve())

    loop_id = f"loop_{orient[:1]}_{category}_{file_p.stem}"
    sha256 = compute_file_sha256(file_p)
    gen_params = json.dumps(
        {"type": "atomic" if is_atomic else "master", "channel": channel, "source": "assets_dir"},
        ensure_ascii=False,
    )
    tags_json = json.dumps(sorted(list(tags)), ensure_ascii=False)

    return (
        loop_id, category, technology, tags_json,
        orient, width, height, duration_sec, fps, stored_path,
        file_p.stat().st_size, sha256, gen_params, 0, None, now_iso,
    )
