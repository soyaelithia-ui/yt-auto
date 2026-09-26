"""
src/core/catalog.py - SQLite-backed Catalog Repository for Video Loops.

Manages video loops and scenery assets (pre-rendered loops and cinematic masters),
indexing their thematic tags, dimensions, usage metrics, and SHA-256 digests.
Provides smart rotation (least-recently used / lowest usage count) and audit tools.
"""
from __future__ import annotations

import json
import os
import random
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.config import BASE_DIR, DEFAULT_DB_PATH
from src.core.catalog_audit import (
    SYNTHETIC_MONOCHROME_LOOP_IDS,
    audit_and_cleanup as audit_and_cleanup_func,
    purge_synthetic_monochrome_loops as purge_synthetic_monochrome_loops_func,
)
from src.core.catalog_sync import (
    _LEGACY_CHECKOUT_PREFIXES,
    _catalog_repo_root,
    compute_file_sha256,
    probe_video_metadata,
    resolve_loop_file_path,
    sync_catalog_from_assets as sync_catalog_from_assets_func,
)
from src.log import get_logger

logger = get_logger("loop_catalog")

__all__ = [
    "CHANNEL_CATEGORIES",
    "CHANNEL_THEMES",
    "LoopCatalogRepository",
    "LoopRecord",
    "SYNTHETIC_MONOCHROME_LOOP_IDS",
    "_LEGACY_CHECKOUT_PREFIXES",
    "compute_file_sha256",
    "probe_video_metadata",
    "resolve_loop_file_path",
]

CHANNEL_THEMES: Dict[str, Tuple[str, ...]] = {
    "horror": ("horror", "dark_ambient", "dark_forest", "cosmic_horror", "scp", "classified_terminal", "containment_chamber", "tactical_chamber"),
    "drama": ("drama", "cozy_ambient", "nostalgia", "reddit_aita", "drama_aita", "cozy_hearth"),
    "scifi": ("scifi", "singularidad_scifi", "space_abyss", "cosmic_singularity", "synaptic_network", "deep_space"),
}

CHANNEL_CATEGORIES: Dict[str, Tuple[str, ...]] = CHANNEL_THEMES


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
        return asdict(self)

    @property
    def channel(self) -> Optional[str]:
        ch = self.generator_params.get("channel") if self.generator_params else None
        if ch:
            return ch
        from src.core.channel_profile import ChannelProfileRegistry
        for c in ChannelProfileRegistry.list_active_channel_ids():
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

    CHANNEL_THEMES: Dict[str, Tuple[str, ...]] = CHANNEL_THEMES
    DEFAULT_CATALOG_DB_PATH = str((BASE_DIR / "data" / "loop_catalog.db").resolve())

    def __init__(
        self,
        db_path: Optional[str] = None,
        auto_seed: Optional[bool] = None,
    ) -> None:
        if db_path is None or db_path == DEFAULT_DB_PATH:
            db_path = self.DEFAULT_CATALOG_DB_PATH if os.path.isfile(self.DEFAULT_CATALOG_DB_PATH) else DEFAULT_DB_PATH
        from src.core.repository.migrations import validate_db_path

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
        """Delegates asset discovery and indexing to catalog_sync module."""
        return sync_catalog_from_assets_func(self, assets_dir=assets_dir, force_rescan=force_rescan)

    def purge_synthetic_monochrome_loops(self) -> int:
        """Delegates synthetic monochrome loop cleanup to catalog_audit module."""
        return purge_synthetic_monochrome_loops_func(self)

    def audit_and_cleanup(self, auto_remove_missing: bool = False) -> Dict[str, Any]:
        """Delegates catalog audit and orphan cleanup to catalog_audit module."""
        return audit_and_cleanup_func(self, auto_remove_missing=auto_remove_missing)

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
        motifs: Optional[Sequence[str]] = None,
        **kwargs: Any,
    ) -> Optional[LoopRecord]:
        """
        Retrieves optimal video loop matching category, orientation, motifs, and channel constraints.
        """
        orient_clean = "horizontal" if orientation in ("horizontal", "16:9", "longform", (1920, 1080)) else "vertical"
        cat_clean = category.strip().lower().replace("-", "_").replace(" ", "_") if category else "dark_ambient"
        exclude_set = self._build_exclude_set(exclude_loop_ids)
        eff_channel = self._resolve_effective_channel(channel, requested_tags, cat_clean)

        candidates = self._query_tier_candidates(
            orient_clean=orient_clean,
            cat_clean=cat_clean,
            eff_channel=eff_channel,
            motifs=motifs,
            exclude_set=exclude_set,
            seed=seed,
        )
        if not candidates:
            return None

        return self._rank_and_select_best(
            candidates=candidates,
            cat_clean=cat_clean,
            clean_motifs=[str(m).strip().lower() for m in (motifs or []) if str(m).strip()],
            requested_tags=requested_tags,
            seed=seed,
        )

    def _build_exclude_set(self, exclude_loop_ids: Optional[Sequence[str]]) -> Set[str]:
        """Helper to build normalized exclude set with dev/inode tracking."""
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
        return exclude_set

    def _resolve_effective_channel(
        self,
        channel: Optional[str],
        requested_tags: Optional[Sequence[str]],
        cat_clean: str,
    ) -> Optional[str]:
        """Deduce channel from explicit argument, requested tags, or category."""
        eff_channel = channel.lower().strip() if channel else None
        if not eff_channel and requested_tags:
            for t in requested_tags:
                t_low = t.lower().strip()
                if t_low in self.CHANNEL_THEMES:
                    return t_low
        if not eff_channel:
            for ch_name, themes in self.CHANNEL_THEMES.items():
                if cat_clean in themes:
                    return ch_name
        return eff_channel

    def _is_foreign_channel(self, rec: LoopRecord, eff_channel: Optional[str]) -> bool:
        """Determines if a loop belongs to a conflicting foreign channel."""
        if not eff_channel:
            return False
        from src.core.channel_profile import ChannelProfileRegistry
        eff_norm = ChannelProfileRegistry.normalize_channel_id(eff_channel)
        rec_ch = rec.channel
        if rec_ch:
            rec_norm = ChannelProfileRegistry.normalize_channel_id(rec_ch)
            if rec_norm != eff_norm:
                return True
        if not rec_ch and eff_channel in self.CHANNEL_THEMES:
            tags = {t.lower().strip() for t in rec.theme_tags}
            for oc in self.CHANNEL_THEMES:
                oc_norm = ChannelProfileRegistry.normalize_channel_id(oc)
                if oc_norm != eff_norm and (oc in tags or f"channel:{oc}" in tags):
                    return True
            for oc, themes in self.CHANNEL_THEMES.items():
                oc_norm = ChannelProfileRegistry.normalize_channel_id(oc)
                if oc_norm != eff_norm and rec.category in themes:
                    return True
        return False

    def _filter_and_validate(
        self,
        rows: List[sqlite3.Row],
        exclude_set: Set[str],
        eff_channel: Optional[str],
    ) -> List[LoopRecord]:
        """Filters out missing, corrupt, synthetic monochrome, and foreign channel loops."""
        valid_recs: List[LoopRecord] = []
        for r in rows:
            rec = self._row_to_record(r)
            is_synthetic_mono = (
                rec.loop_id in SYNTHETIC_MONOCHROME_LOOP_IDS
                or rec.category in ("maritime_lighthouse", "arctic_desolation")
                or rec.technology == "synthetic_monochrome"
                or (rec.technology == "ffmpeg_lavfi" and rec.sha256 == "procedural")
            )
            if is_synthetic_mono or self._is_foreign_channel(rec, eff_channel):
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

    def _query_tier_candidates(
        self,
        orient_clean: str,
        cat_clean: str,
        eff_channel: Optional[str],
        motifs: Optional[Sequence[str]],
        exclude_set: Set[str],
        seed: Any,
    ) -> List[LoopRecord]:
        """Queries database across Tier 0 (motifs), Tier 1 (exact), Tier 2 (channel fallback), Tier 3 (generic)."""
        clean_motifs = [str(m).strip().lower() for m in (motifs or []) if str(m).strip()]
        motif_hits: List[LoopRecord] = []
        if clean_motifs:
            motif_clauses = " OR ".join(["theme_tags LIKE ?" for _ in clean_motifs] + ["file_path LIKE ?" for _ in clean_motifs] + ["category LIKE ?" for _ in clean_motifs])
            sql_motifs = f"SELECT * FROM video_loops WHERE orientation = ? AND ({motif_clauses}) ORDER BY usage_count ASC, last_used_at ASC, id ASC"
            params = [orient_clean] + [f'%"{m}"%' for m in clean_motifs] + [f'%{m}%' for m in clean_motifs] + [f'%{m}%' for m in clean_motifs]
            with self._get_connection() as conn:
                cur = conn.execute(sql_motifs, params)
                motif_hits = self._filter_and_validate(cur.fetchall(), exclude_set, eff_channel)

        sql_exact = "SELECT * FROM video_loops WHERE category = ? AND orientation = ? ORDER BY usage_count ASC, last_used_at ASC, id ASC"
        with self._get_connection() as conn:
            cur = conn.execute(sql_exact, (cat_clean, orient_clean))
            candidates = self._filter_and_validate(cur.fetchall(), exclude_set, eff_channel)

        if motif_hits:
            seen_motif_ids = {c.loop_id for c in candidates}
            for mh in motif_hits:
                if mh.loop_id not in seen_motif_ids:
                    candidates.append(mh)
                    seen_motif_ids.add(mh.loop_id)

        # Tier 2: Channel compatible fallback
        from src.core.channel_profile import ChannelProfileRegistry
        ch_key = eff_channel if (eff_channel and eff_channel in self.CHANNEL_THEMES) else (
            ChannelProfileRegistry.normalize_channel_id(eff_channel) if eff_channel else None
        )
        need_channel_pool = (
            (not candidates and ch_key and ch_key in self.CHANNEL_THEMES)
            or (
                seed is not None
                and ch_key
                and ch_key in self.CHANNEL_THEMES
                and len([c for c in candidates if c.category.strip().lower() == cat_clean]) <= 1
            )
        )
        if need_channel_pool and ch_key and ch_key in self.CHANNEL_THEMES:
            ch_cats = self.CHANNEL_THEMES[ch_key]
            placeholders = ",".join("?" for _ in ch_cats)
            sql_ch = f"""
            SELECT *, (CASE WHEN category = ? THEN 0 ELSE 1 END) AS cat_priority
            FROM video_loops
            WHERE orientation = ? AND (theme_tags LIKE ? OR category IN ({placeholders}))
            ORDER BY cat_priority ASC, usage_count ASC, last_used_at ASC, id ASC
            """
            with self._get_connection() as conn:
                cur = conn.execute(sql_ch, (cat_clean, orient_clean, f'%"{eff_channel}"%', *ch_cats))
                channel_hits = self._filter_and_validate(cur.fetchall(), exclude_set, eff_channel)
            if not candidates:
                candidates = channel_hits
            else:
                seen_ids = {c.loop_id for c in candidates}
                for rec in channel_hits:
                    if rec.loop_id not in seen_ids:
                        candidates.append(rec)
                        seen_ids.add(rec.loop_id)

        # Tier 3: Generic fallback
        if not candidates:
            sql_fb = "SELECT * FROM video_loops WHERE orientation = ? ORDER BY usage_count ASC, last_used_at ASC, id ASC"
            with self._get_connection() as conn:
                cur = conn.execute(sql_fb, (orient_clean,))
                candidates = self._filter_and_validate(cur.fetchall(), exclude_set, eff_channel)

        preferred = [c for c in candidates if (c.technology or "").strip().lower() not in ("ffmpeg_lavfi", "synthetic_monochrome")]
        return preferred or candidates

    def _rank_and_select_best(
        self,
        candidates: List[LoopRecord],
        cat_clean: str,
        clean_motifs: List[str],
        requested_tags: Optional[Sequence[str]],
        seed: Any,
    ) -> LoopRecord:
        """Ranks candidates by semantic motifs, tags, and selects with seeded rotation."""
        def candidate_sort_key(rec: LoopRecord) -> Tuple[int, int, int, int, str]:
            m_score = 0
            if clean_motifs:
                rec_tags = {t.lower().strip() for t in rec.theme_tags}
                stem_tokens = set(re.split(r"[_\W]+", Path(rec.file_path).stem.lower()))
                for m in clean_motifs:
                    if m in rec_tags:
                        m_score += 4
                    if m in stem_tokens or m == rec.category.lower():
                        m_score += 3
                    elif any(m in t for t in rec_tags):
                        m_score += 1
            tag_matches = 0
            if requested_tags:
                tag_set = {t.lower().strip() for t in requested_tags if t}
                rec_tags = {t.lower().strip() for t in rec.theme_tags}
                tag_matches = len(tag_set.intersection(rec_tags))
            cat_prio = 0 if rec.category.strip().lower() == cat_clean else 1
            return (-m_score, cat_prio, -tag_matches, rec.usage_count, rec.last_used_at or "")

        candidates.sort(key=candidate_sort_key)

        # Deduplicate by physical filename
        seen_paths: set[str] = set()
        distinct_records: list[LoopRecord] = []
        for rec in candidates:
            norm_name = Path(rec.file_path).name
            if norm_name not in seen_paths:
                seen_paths.add(norm_name)
                distinct_records.append(rec)
        if not distinct_records:
            distinct_records = candidates

        matching_motif_records = [
            r for r in distinct_records
            if clean_motifs and any(
                m in {t.lower().strip() for t in r.theme_tags}
                or m in set(re.split(r"[_\W]+", Path(r.file_path).stem.lower()))
                or m in r.category.lower()
                for m in clean_motifs
            )
        ]
        if matching_motif_records:
            candidate_pool = matching_motif_records
        else:
            matching_cat_records = [r for r in distinct_records if r.category.strip().lower() == cat_clean]
            if len(matching_cat_records) > 1:
                candidate_pool = matching_cat_records
            elif seed is not None and len(distinct_records) > 1:
                candidate_pool = distinct_records
            else:
                candidate_pool = matching_cat_records or distinct_records

        min_usage = min(r.usage_count for r in candidate_pool)
        tied = [r for r in candidate_pool if r.usage_count == min_usage]

        if seed is not None and len(tied) > 1:
            try:
                idx = int(seed)
                tied_sorted = sorted(tied, key=lambda r: r.loop_id)
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
