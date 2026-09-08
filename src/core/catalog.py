"""
src/core/loop_catalog.py - SQLite-backed Catalog Repository for Web-Generated Video Loops.

Manages lightweight procedural video loops generated via HTML5/WebGL/Canvas/CSS,
indexing their thematic tags, dimensions, usage metrics, and SHA-256 digests.
Provides smart rotation (least-recently used / lowest usage count) and audit tools.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sqlite3
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.config import BASE_DIR, DEFAULT_DB_PATH
from src.core.repository import validate_db_path
from src.log import get_logger

logger = get_logger("loop_catalog")

__all__ = [
    "LoopRecord",
    "LoopCatalogRepository",
    "compute_file_sha256",
    "resolve_loop_file_path",
    "CHANNEL_CATEGORIES",
    "CHANNEL_THEMES",
    "SYNTHETIC_MONOCHROME_LOOP_IDS",
]

CHANNEL_THEMES: Dict[str, Tuple[str, ...]] = {
    "moku": ("horror", "moku_horror", "dark_ambient", "dark_forest", "cosmic_horror", "scp", "classified_terminal", "containment_chamber", "tactical_chamber"),
    "aelithia": ("drama", "aelithia_drama", "cozy_ambient", "nostalgia", "reddit_aita", "drama_aita", "cozy_hearth"),
    "scifi": ("scifi", "singularidad_scifi", "space_abyss", "cosmic_singularity", "synaptic_network", "deep_space"),
}

# Back-compat alias used by main CI / tier-2 fallback callers
CHANNEL_CATEGORIES: Dict[str, Tuple[str, ...]] = CHANNEL_THEMES

SYNTHETIC_MONOCHROME_LOOP_IDS: Set[str] = {
    "loop_maritime_lighthouse_h_544374",
    "loop_arctic_desolation_v_800210",
}

# Migration remap only: SQLite `video_loops.file_path` may still store absolute
# paths from prior host checkouts. These prefixes are NOT the live install root
# (that is YT_AUTO_ROOT on VPS/systemd, else BASE_DIR for the current checkout).
# Prefer repo-relative paths for new rows. Do not drop these until catalogs are
# rewritten, or resolution of existing loop assets breaks after moves/clones.
_LEGACY_CHECKOUT_PREFIXES = (
    "/home/moku/projects/yt-auto",
    "/srv/projects/yt-auto",
)


def _catalog_repo_root(repo_root: Path | None = None) -> Path:
    """Prefer explicit arg, then YT_AUTO_ROOT env, then BASE_DIR (repo-relative)."""
    if repo_root is not None:
        return Path(repo_root)
    env_root = os.environ.get("YT_AUTO_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser()
    return BASE_DIR


def resolve_loop_file_path(path: str | Path, repo_root: Path | None = None) -> Path:
    """Map a catalog path onto the current checkout.

    Order: existing file as stored → strip legacy host prefixes onto
    YT_AUTO_ROOT/BASE_DIR → join relative paths under that root.
    Never rewrite a missing path onto a foreign host root.
    """
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
    """Computes standard SHA-256 hexadecimal digest for a file."""
    p = Path(path)
    if not p.is_file():
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_video_metadata(file_path: Path) -> Optional[Tuple[int, int, float, int]]:
    """Extract width, height, duration_sec, fps using ffprobe.

    Returns (width, height, duration_sec, fps) if probe succeeds with valid
    dimensions and duration, or None if ffprobe fails, produces no valid video stream,
    or reports zero/negative dimensions.
    """
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


@dataclass
class LoopRecord:
    loop_id: str
    category: str
    technology: str
    orientation: str  # 'vertical' (9:16) or 'horizontal' (16:9)
    width: int
    height: int
    duration_sec: float
    fps: int
    file_path: str
    file_size_bytes: int
    sha256: str
    theme_tags: list[str] = field(default_factory=list)
    generator_params: dict[str, Any] = field(default_factory=dict)
    usage_count: int = 0
    last_used_at: Optional[str] = None
    created_at: Optional[str] = None
    id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @property
    def channel(self) -> Optional[str]:
        ch = self.generator_params.get("channel") if self.generator_params else None
        if ch:
            return ch
        for c in ("moku", "aelithia", "scifi"):
            if c in self.theme_tags or f"channel:{c}" in self.theme_tags:
                return c
            stem = Path(self.file_path).stem.lower()
            if stem.startswith(f"{c}_"):
                return c
        return None


class LoopCatalogRepository:
    """SQLite repository for indexing, querying, and rotating code-generated video loops."""

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS video_loops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loop_id TEXT UNIQUE NOT NULL,
        category TEXT NOT NULL,
        technology TEXT NOT NULL,
        theme_tags TEXT NOT NULL,
        orientation TEXT NOT NULL,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        duration_sec REAL NOT NULL,
        fps INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        file_size_bytes INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        generator_params_json TEXT NOT NULL,
        usage_count INTEGER DEFAULT 0,
        last_used_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_video_loops_cat_orient ON video_loops(category, orientation);
    CREATE INDEX IF NOT EXISTS idx_video_loops_usage ON video_loops(usage_count, last_used_at);
    CREATE INDEX IF NOT EXISTS idx_video_loops_sha ON video_loops(sha256);
    """

    CHANNEL_THEMES: Dict[str, Tuple[str, ...]] = {
        "moku": ("horror", "moku_horror", "dark_ambient", "dark_forest", "cosmic_horror", "scp", "classified_terminal", "containment_chamber", "tactical_chamber"),
        "aelithia": ("drama", "aelithia_drama", "cozy_ambient", "nostalgia", "reddit_aita", "drama_aita", "cozy_hearth"),
        "scifi": ("scifi", "singularidad_scifi", "space_abyss", "cosmic_singularity", "synaptic_network", "deep_space"),
    }

    DEFAULT_CATALOG_DB_PATH = str((BASE_DIR / "data" / "loop_catalog.db").resolve())

    def __init__(
        self,
        db_path: Optional[str] = None,
        auto_seed: Optional[bool] = None,
    ) -> None:
        if db_path is None or db_path == DEFAULT_DB_PATH:
            db_path = self.DEFAULT_CATALOG_DB_PATH if os.path.isfile(self.DEFAULT_CATALOG_DB_PATH) else DEFAULT_DB_PATH
        path_or_str = validate_db_path(db_path)
        self.db_path = ":memory:" if str(path_or_str) == ":memory:" else str(Path(path_or_str).expanduser().resolve())
        if auto_seed is not None:
            self.auto_seed = bool(auto_seed)
        else:
            is_test = os.environ.get("TEST_MODE") == "1"
            if not is_test:
                self.auto_seed = True
            elif os.environ.get("YT_AUTO_SEED_CATALOG") == "1":
                self.auto_seed = True
            elif "autoseed" in str(self.db_path).lower():
                self.auto_seed = True
            elif self.db_path == str(Path(DEFAULT_DB_PATH).expanduser().resolve()):
                self.auto_seed = True
            else:
                self.auto_seed = False
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=15.0)

        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=15000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _ensure_table(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(self.CREATE_TABLE_SQL)
            conn.commit()

        if getattr(self, "auto_seed", True):
            try:
                if self.count_loops() < 50:
                    assets_dir = _catalog_repo_root() / "assets" / "loops"
                    if assets_dir.is_dir():
                        logger.info("Auto-seeding loop catalog (count < 50)...")
                        self.sync_catalog_from_assets(assets_dir)
            except Exception as e:
                logger.warning("Auto-seeding loop catalog failed: %s", e)

    def _row_to_record(self, row: sqlite3.Row) -> LoopRecord:
        try:
            tags = json.loads(row["theme_tags"]) if row["theme_tags"] else []
        except Exception:
            tags = []
        try:
            params = json.loads(row["generator_params_json"]) if row["generator_params_json"] else {}
        except Exception:
            params = {}

        return LoopRecord(
            id=row["id"],
            loop_id=row["loop_id"],
            category=row["category"],
            technology=row["technology"],
            theme_tags=tags,
            orientation=row["orientation"],
            width=row["width"],
            height=row["height"],
            duration_sec=float(row["duration_sec"]),
            fps=int(row["fps"]),
            file_path=row["file_path"],
            file_size_bytes=int(row["file_size_bytes"]),
            sha256=row["sha256"],
            generator_params=params,
            usage_count=int(row["usage_count"] or 0),
            last_used_at=row["last_used_at"],
            created_at=row["created_at"],
        )

    def register_loop(self, loop: LoopRecord) -> bool:
        """Registers or updates a loop record in the database."""
        tags_json = json.dumps(loop.theme_tags, ensure_ascii=False)
        params_json = json.dumps(loop.generator_params, ensure_ascii=False)
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

        sql = """
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
        with self._get_connection() as conn:
            conn.execute(
                sql,
                (
                    loop.loop_id,
                    loop.category,
                    loop.technology,
                    tags_json,
                    loop.orientation,
                    loop.width,
                    loop.height,
                    loop.duration_sec,
                    loop.fps,
                    str(loop.file_path),
                    loop.file_size_bytes,
                    loop.sha256,
                    params_json,
                    loop.usage_count,
                    loop.last_used_at,
                    loop.created_at or now_iso,
                ),
            )
            conn.commit()
        logger.info("Registered loop '%s' (cat=%s, orient=%s, tech=%s)", loop.loop_id, loop.category, loop.orientation, loop.technology)
        return True


    def sync_catalog_from_assets(
        self,
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

                rel = file_p.relative_to(orient_dir)
                if len(rel.parts) > 1:
                    category = rel.parts[0].strip().lower().replace("-", "_")
                    if category == "atomic":
                        category = "general"
                else:
                    category = "general"

                is_atomic = "atomic" in rel.parts
                is_master = "_master_60s" in file_p.name
                stem = file_p.stem.lower()

                # Channel attribution
                channel = None
                for ch in ("moku", "aelithia", "scifi"):
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

                # Dimensions, duration, fps
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
                        continue
                    width, height, duration_sec, fps = meta
                    technology = "pre-rendered"

                # Relative file path when within repo root, else absolute
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

                rows_to_upsert.append((
                    loop_id, category, technology, tags_json,
                    orient, width, height, duration_sec, fps, stored_path,
                    file_size, sha256, gen_params, 0, None, now_iso,
                ))

        if rows_to_upsert:
            with self._get_connection() as conn:
                conn.executemany(upsert_sql, rows_to_upsert)
                conn.commit()
            logger.info("Successfully synced %d video loops from assets", len(rows_to_upsert))

        return len(rows_to_upsert)

    def purge_synthetic_monochrome_loops(self) -> int:
        """Purges synthetic monochrome loops from the database."""
        sql = """
        DELETE FROM video_loops
        WHERE loop_id IN ('loop_maritime_lighthouse_h_544374', 'loop_arctic_desolation_v_800210')
           OR (technology = 'ffmpeg_lavfi' AND sha256 = 'procedural')
        """
        with self._get_connection() as conn:
            cur = conn.execute(sql)
            deleted = cur.rowcount
            conn.commit()
        logger.info("Purged %d synthetic monochrome loops from catalog", deleted)
        return deleted

    def get_loop_by_id(self, loop_id: str) -> Optional[LoopRecord]:
        """Fetches a loop record by its unique ID."""
        sql = "SELECT * FROM video_loops WHERE loop_id = ? LIMIT 1"
        with self._get_connection() as conn:
            cur = conn.execute(sql, (loop_id,))
            row = cur.fetchone()
            if row:
                return self._row_to_record(row)
        return None

    def get_best_loop(
        self,
        category: str,
        orientation: str = "vertical",
        requested_tags: Optional[Sequence[str]] = None,
        seed: Any = None,
        exclude_loop_ids: Optional[Sequence[str]] = None,
        channel: Optional[str] = None,
    ) -> Optional[LoopRecord]:
        """
        Retrieves the optimal video loop matching category, orientation, and channel constraints.
        Applies 3-tier fallback, PR CHANNEL_THEMES isolation, exclude filters, path-dedup
        seeded rotation (multi-scene), and skips missing/synthetic media.
        """
        orient_clean = "horizontal" if orientation in ("horizontal", "16:9", "longform", (1920, 1080)) else "vertical"
        cat_clean = category.strip().lower().replace("-", "_").replace(" ", "_") if category else "dark_ambient"
        exclude_set = {str(e).strip() for e in (exclude_loop_ids or []) if e}
        for raw in list(exclude_set):
            p_ex = Path(raw)
            try:
                if p_ex.is_file():
                    st = p_ex.stat()
                    exclude_set.add(f"ino:{st.st_dev}:{st.st_ino}")
                    exclude_set.add(p_ex.name)
            except OSError:
                exclude_set.add(p_ex.name)

        # Deduce channel from explicit arg, requested_tags, or category (PR #69)
        eff_channel = channel.lower().strip() if channel else None
        if not eff_channel and requested_tags:
            for t in requested_tags:
                t_low = t.lower().strip()
                if t_low in self.CHANNEL_THEMES:
                    eff_channel = t_low
                    break
        if not eff_channel:
            for ch_name, themes in self.CHANNEL_THEMES.items():
                if cat_clean in themes:
                    eff_channel = ch_name
                    break

        def _is_foreign_channel(rec: LoopRecord) -> bool:
            if not eff_channel:
                return False
            rec_ch = rec.channel
            if rec_ch and rec_ch.lower() != eff_channel.lower():
                return True
            if not rec_ch and eff_channel in self.CHANNEL_THEMES:
                tags = {t.lower().strip() for t in rec.theme_tags}
                other_channels = {c for c in self.CHANNEL_THEMES if c != eff_channel}
                if any(oc in tags for oc in other_channels):
                    return True
                for oc, themes in self.CHANNEL_THEMES.items():
                    if oc != eff_channel and rec.category in themes:
                        return True
            return False

        def _filter_and_validate(rows: List[sqlite3.Row]) -> List[LoopRecord]:
            valid_recs: List[LoopRecord] = []
            for r in rows:
                rec = self._row_to_record(r)
                # Never select grey lavfi / synthetic monochrome as plane-0.
                is_synthetic_mono = (
                    rec.loop_id in SYNTHETIC_MONOCHROME_LOOP_IDS
                    or rec.category in ("maritime_lighthouse", "arctic_desolation")
                    or rec.technology == "synthetic_monochrome"
                    or (rec.technology == "ffmpeg_lavfi" and rec.sha256 == "procedural")
                )
                if is_synthetic_mono:
                    continue

                # Channel isolation: reject foreign channel
                if _is_foreign_channel(rec):
                    continue
                if (
                    rec.loop_id in exclude_set
                    or rec.file_path in exclude_set
                    or Path(rec.file_path).name in exclude_set
                    or str(resolve_loop_file_path(rec.file_path)) in exclude_set
                ):
                    continue
                p = resolve_loop_file_path(rec.file_path)
                if p.is_file() and p.stat().st_size >= 25_000:
                    st = p.stat()
                    if f"ino:{st.st_dev}:{st.st_ino}" in exclude_set:
                        continue
                    rec.file_path = str(p)
                    valid_recs.append(rec)
            return valid_recs

        # --- Tier 1: Exact category match ---
        sql_exact = """
        SELECT * FROM video_loops
        WHERE category = ? AND orientation = ?
        ORDER BY usage_count ASC, last_used_at ASC, id ASC
        """
        with self._get_connection() as conn:
            cur = conn.execute(sql_exact, (cat_clean, orient_clean))
            candidates = _filter_and_validate(cur.fetchall())

        # --- Tier 2: Same-channel compatible fallback / multi-scene expansion ---
        need_channel_pool = (
            (not candidates and eff_channel and eff_channel in self.CHANNEL_THEMES)
            or (
                seed is not None
                and eff_channel
                and eff_channel in self.CHANNEL_THEMES
                and len([c for c in candidates if c.category.strip().lower() == cat_clean]) <= 1
            )
        )
        if need_channel_pool and eff_channel and eff_channel in self.CHANNEL_THEMES:
            ch_cats = self.CHANNEL_THEMES[eff_channel]
            placeholders = ",".join("?" for _ in ch_cats)
            sql_ch = f"""
            SELECT *, (CASE WHEN category = ? THEN 0 ELSE 1 END) AS cat_priority
            FROM video_loops
            WHERE orientation = ? AND (theme_tags LIKE ? OR category IN ({placeholders}))
            ORDER BY cat_priority ASC, usage_count ASC, last_used_at ASC, id ASC
            """
            with self._get_connection() as conn:
                cur = conn.execute(sql_ch, (cat_clean, orient_clean, f'%"{eff_channel}"%', *ch_cats))
                channel_hits = _filter_and_validate(cur.fetchall())
            if not candidates:
                candidates = channel_hits
            else:
                seen_ids = {c.loop_id for c in candidates}
                for rec in channel_hits:
                    if rec.loop_id not in seen_ids:
                        candidates.append(rec)
                        seen_ids.add(rec.loop_id)

        # --- Tier 3: Generic orientation fallback (still channel-isolated via filter) ---
        if not candidates:
            sql_fb = """
            SELECT * FROM video_loops
            WHERE orientation = ?
            ORDER BY usage_count ASC, last_used_at ASC, id ASC
            """
            with self._get_connection() as conn:
                cur = conn.execute(sql_fb, (orient_clean,))
                candidates = _filter_and_validate(cur.fetchall())

        if not candidates:
            return None

        preferred = [
            c
            for c in candidates
            if (c.technology or "").strip().lower() not in ("ffmpeg_lavfi", "synthetic_monochrome")
        ]
        if preferred:
            candidates = preferred

        # Tag ranking with category priority
        if requested_tags:
            tag_set = {t.lower().strip() for t in requested_tags if t}

            def tag_score(rec: LoopRecord) -> Tuple[int, int, int, str]:
                cat_prio = 0 if rec.category.strip().lower() == cat_clean else 1
                rec_tags = {t.lower().strip() for t in rec.theme_tags}
                match_count = len(tag_set.intersection(rec_tags))
                return (cat_prio, -match_count, rec.usage_count, rec.last_used_at or "")

            candidates.sort(key=tag_score)

        # Deduplicate by physical filename for multi-scene seeded rotation (PR)
        seen_paths: set[str] = set()
        distinct_records: list[LoopRecord] = []
        for rec in candidates:
            norm_name = Path(rec.file_path).name
            if norm_name not in seen_paths:
                seen_paths.add(norm_name)
                distinct_records.append(rec)
        if not distinct_records:
            distinct_records = candidates

        matching_cat_records = [r for r in distinct_records if r.category.strip().lower() == cat_clean]
        if len(matching_cat_records) > 1:
            candidate_pool = matching_cat_records
        elif seed is not None and len(distinct_records) > 1:
            # PR multi-scene: rotate across channel pool when category has a single hit
            candidate_pool = distinct_records
        else:
            candidate_pool = matching_cat_records or distinct_records

        # Main: lowest usage_count strictly precedes seed randomization
        min_usage = min(r.usage_count for r in candidate_pool)
        tied = [r for r in candidate_pool if r.usage_count == min_usage]

        if seed is not None and len(tied) > 1:
            try:
                idx = int(seed)
                tied_sorted = sorted(tied, key=lambda r: r.loop_id)
                # Prefer stable idx modulo for multi-scene (PR); works for equal-usage banks too
                return tied_sorted[idx % len(tied_sorted)]
            except (ValueError, TypeError):
                return random.Random(seed).choice(sorted(tied, key=lambda r: r.loop_id))

        return tied[0]

    # Aliases
    get_loop_for_scene = get_best_loop

    def resolve_for_theme(
        self,
        theme: str,
        is_vertical: bool = True,
        **kwargs: Any,
    ) -> Optional[LoopRecord]:
        """Alias for thumbnail and procedural asset resolvers."""
        orientation = "vertical" if is_vertical else "horizontal"
        return self.get_best_loop(category=theme, orientation=orientation, **kwargs)

    def record_loop_usage(self, loop_id: str) -> None:
        """Increments usage counter and updates last_used_at timestamp."""
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        sql = """
        UPDATE video_loops
        SET usage_count = usage_count + 1,
            last_used_at = ?
        WHERE loop_id = ?
        """
        with self._get_connection() as conn:
            conn.execute(sql, (now_iso, loop_id))
            conn.commit()

    def count_loops(
        self,
        category: Optional[str] = None,
        orientation: Optional[str] = None,
    ) -> int:
        """Cheap SQL COUNT of catalog rows. Does not load LoopRecord rows into memory."""
        query = "SELECT COUNT(*) FROM video_loops WHERE 1=1"
        params: List[Any] = []
        if category:
            query += " AND category = ?"
            params.append(category.strip().lower().replace("-", "_").replace(" ", "_"))
        if orientation:
            orient_clean = "horizontal" if orientation in ("horizontal", "16:9", "longform", (1920, 1080)) else "vertical"
            query += " AND orientation = ?"
            params.append(orient_clean)

        with self._get_connection() as conn:
            row = conn.execute(query, params).fetchone()
            return int(row[0]) if row else 0

    def list_loops(
        self,
        category: Optional[str] = None,
        orientation: Optional[str] = None,
        limit: int = 100,
    ) -> List[LoopRecord]:
        """Lists registered video loops with optional category/orientation filters."""
        query = "SELECT * FROM video_loops WHERE 1=1"
        params: List[Any] = []
        if category:
            query += " AND category = ?"
            params.append(category.strip().lower().replace("-", "_").replace(" ", "_"))
        if orientation:
            orient_clean = "horizontal" if orientation in ("horizontal", "16:9") else "vertical"
            query += " AND orientation = ?"
            params.append(orient_clean)

        query += " ORDER BY category ASC, orientation ASC, usage_count ASC, id ASC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            return [self._row_to_record(r) for r in cur.fetchall()]

    def delete_loop(self, loop_id: str, delete_file: bool = False) -> bool:
        """Deletes a loop from catalog and optionally removes physical file."""
        rec = self.get_loop_by_id(loop_id)
        if not rec:
            return False

        if delete_file and rec.file_path:
            p = Path(rec.file_path)
            if p.is_file():
                try:
                    p.unlink()
                except OSError as e:
                    logger.warning("Could not unlink loop file %s: %s", p, e)

        sql = "DELETE FROM video_loops WHERE loop_id = ?"
        with self._get_connection() as conn:
            conn.execute(sql, (loop_id,))
            conn.commit()
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Returns overview statistics of the loop library."""
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM video_loops").fetchone()[0]
            by_cat = conn.execute("SELECT category, COUNT(*) FROM video_loops GROUP BY category").fetchall()
            by_orient = conn.execute("SELECT orientation, COUNT(*) FROM video_loops GROUP BY orientation").fetchall()
            by_tech = conn.execute("SELECT technology, COUNT(*) FROM video_loops GROUP BY technology").fetchall()

        return {
            "total_loops": total,
            "by_category": {r[0]: r[1] for r in by_cat},
            "by_orientation": {r[0]: r[1] for r in by_orient},
            "by_technology": {r[0]: r[1] for r in by_tech},
        }

    def audit_and_cleanup(self, auto_remove_missing: bool = False) -> Dict[str, Any]:
        """
        Audits physical file existence and SHA-256 integrity for all cataloged loops.
        Optionally removes database records pointing to missing files.
        """
        all_loops = self.list_loops(limit=10000)
        valid_count = 0
        missing_count = 0
        corrupted_count = 0
        removed_ids = []

        for rec in all_loops:
            p = Path(rec.file_path)
            if not p.is_file() or p.stat().st_size == 0:
                missing_count += 1
                if auto_remove_missing:
                    self.delete_loop(rec.loop_id, delete_file=False)
                    removed_ids.append(rec.loop_id)
                continue

            current_sha = compute_file_sha256(p)
            if current_sha != rec.sha256:
                corrupted_count += 1
                logger.warning("SHA mismatch for loop '%s': expected %s, got %s", rec.loop_id, rec.sha256, current_sha)
            else:
                valid_count += 1

        return {
            "total_checked": len(all_loops),
            "valid": valid_count,
            "missing": missing_count,
            "corrupted": corrupted_count,
            "removed_ids": removed_ids,
        }
