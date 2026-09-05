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
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.config import BASE_DIR, DEFAULT_DB_PATH
from src.core.repository import validate_db_path
from src.log import get_logger

logger = get_logger("loop_catalog")

__all__ = [
    "LoopRecord",
    "LoopCatalogRepository",
    "compute_file_sha256",
]

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

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        path_or_str = validate_db_path(db_path)
        self.db_path = ":memory:" if str(path_or_str) == ":memory:" else str(Path(path_or_str).expanduser().resolve())
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
    ) -> Optional[LoopRecord]:
        """
        Retrieves the optimal video loop matching category and orientation.
        Applies smart rotation (least recently used and lowest usage_count) to prevent visual repetition.
        """
        orient_clean = "horizontal" if orientation in ("horizontal", "16:9", "longform", (1920, 1080)) else "vertical"
        cat_clean = category.strip().lower().replace("-", "_").replace(" ", "_") if category else "dark_ambient"

        # Query active candidates
        sql = """
        SELECT * FROM video_loops
        WHERE category = ? AND orientation = ?
        ORDER BY usage_count ASC, last_used_at ASC, id ASC
        """
        with self._get_connection() as conn:
            cur = conn.execute(sql, (cat_clean, orient_clean))
            rows = cur.fetchall()

        if not rows:
            # Fallback across other categories for the same orientation
            sql_fb = """
            SELECT * FROM video_loops
            WHERE orientation = ?
            ORDER BY usage_count ASC, last_used_at ASC, id ASC
            """
            with self._get_connection() as conn:
                cur = conn.execute(sql_fb, (orient_clean,))
                rows = cur.fetchall()

        if not rows:
            return None

        records = [self._row_to_record(r) for r in rows]

        def _resolve_and_validate(rec: LoopRecord) -> Optional[LoopRecord]:
            p = resolve_loop_file_path(rec.file_path)
            if p.is_file() and p.stat().st_size >= 25_000:
                rec.file_path = str(p)
                return rec
            return None

        # Validating file existence on disk (minimum 25KB to exclude dummy/corrupt loops)
        valid_records = [r for rec in records if (r := _resolve_and_validate(rec)) is not None]
        if not valid_records:
            return None

        # Tag-based ranking if requested
        if requested_tags:
            tag_set = {t.lower().strip() for t in requested_tags if t}
            def score(rec: LoopRecord) -> Tuple[int, int, str]:
                rec_tags = {t.lower().strip() for t in rec.theme_tags}
                match_count = len(tag_set.intersection(rec_tags))
                return (-match_count, rec.usage_count, rec.last_used_at or "")

            valid_records.sort(key=score)

        return valid_records[0]

    # Alias for multi-scene engines
    get_loop_for_scene = get_best_loop

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
