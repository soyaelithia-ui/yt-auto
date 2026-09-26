"""SQLite migrations, connection management, and WAL pragmas."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

BUSY_TIMEOUT_MS = 15_000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _migration_checksum(name: str, statements: Sequence[str]) -> str:
    payload = name + "\n" + "\n".join(statements)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


MIGRATION_001 = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        checksum TEXT NOT NULL,
        applied_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        channel TEXT NOT NULL,
        story_id TEXT,
        mode TEXT NOT NULL DEFAULT 'publish',
        status TEXT NOT NULL,
        owner TEXT NOT NULL,
        started_at TEXT NOT NULL,
        heartbeat_at TEXT NOT NULL,
        finished_at TEXT,
        error_code TEXT,
        error_detail TEXT,
        FOREIGN KEY(story_id) REFERENCES stories(story_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS leases (
        job_id TEXT PRIMARY KEY,
        channel TEXT NOT NULL UNIQUE,
        owner TEXT NOT NULL,
        run_id TEXT NOT NULL UNIQUE,
        acquired_at INTEGER NOT NULL,
        heartbeat_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        FOREIGN KEY(job_id) REFERENCES stories(story_id) ON DELETE CASCADE,
        FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_stories (
        run_id TEXT NOT NULL,
        story_id TEXT NOT NULL,
        position INTEGER NOT NULL,
        PRIMARY KEY(run_id, story_id),
        FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
        FOREIGN KEY(story_id) REFERENCES stories(story_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stage_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        stage_name TEXT NOT NULL,
        status TEXT NOT NULL,
        detail TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        local_path TEXT,
        remote_provider TEXT,
        remote_id TEXT,
        remote_name TEXT,
        size_bytes INTEGER,
        sha256 TEXT,
        verified_at TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(run_id, kind, local_path),
        FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS provider_attempts (
        attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        operation TEXT NOT NULL,
        attempt_no INTEGER NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        outcome TEXT,
        error_code TEXT,
        error_detail TEXT,
        retry_after TEXT,
        UNIQUE(run_id, provider, operation, attempt_no),
        FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stories (
        story_id TEXT PRIMARY KEY,
        channel TEXT NOT NULL,
        source_id TEXT NOT NULL,
        title TEXT NOT NULL,
        raw_content TEXT NOT NULL,
        score REAL NOT NULL DEFAULT 0.0,
        status TEXT NOT NULL DEFAULT 'pending',
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        discovered_at TEXT NOT NULL,
        next_attempt_at INTEGER NOT NULL DEFAULT 0,
        UNIQUE(channel, source_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS metrics (
        metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        name TEXT NOT NULL,
        value REAL NOT NULL,
        unit TEXT,
        recorded_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS publications (
        publication_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL UNIQUE,
        story_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        video_id TEXT NOT NULL UNIQUE,
        url TEXT NOT NULL UNIQUE,
        channel TEXT NOT NULL,
        visibility TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        thumbnail_confirmed INTEGER NOT NULL CHECK(thumbnail_confirmed IN (0, 1)),
        verified_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(run_id),
        FOREIGN KEY(story_id) REFERENCES stories(story_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS content_fingerprints (
        fingerprint_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        story_id TEXT,
        channel TEXT NOT NULL,
        kind TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        normalized_text TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(channel, kind, sha256),
        FOREIGN KEY(run_id) REFERENCES runs(run_id),
        FOREIGN KEY(story_id) REFERENCES stories(story_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS channel_controls (
        channel TEXT PRIMARY KEY,
        paused INTEGER NOT NULL DEFAULT 0 CHECK(paused IN (0, 1)),
        reason TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scheduler_state (
        scheduler_id INTEGER PRIMARY KEY CHECK(scheduler_id = 1),
        next_channel TEXT NOT NULL,
        next_run_at INTEGER NOT NULL,
        last_run_at INTEGER,
        updated_at TEXT NOT NULL
    )
    """,
    """
    INSERT OR IGNORE INTO channel_controls(channel, paused, updated_at)
    VALUES ('moku', 0, CURRENT_TIMESTAMP), ('aelithia', 0, CURRENT_TIMESTAMP)
    """,
    """
    INSERT OR IGNORE INTO scheduler_state(
        scheduler_id, next_channel, next_run_at, updated_at
    ) VALUES (1, 'moku', 0, CURRENT_TIMESTAMP)
    """,
    """
    CREATE TABLE IF NOT EXISTS daemon_liveness (
        id INTEGER PRIMARY KEY CHECK(id = 1),
        heartbeat_at INTEGER NOT NULL
    )
    """,
    """
    INSERT OR IGNORE INTO daemon_liveness(id, heartbeat_at)
    VALUES (1, 0)
    """,
    """
    CREATE TABLE IF NOT EXISTS review_jobs (
        job_id TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        project TEXT NOT NULL DEFAULT 'YTShort',
        channel TEXT NOT NULL DEFAULT 'moku',
        content_type TEXT NOT NULL DEFAULT 'short',
        title TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        original_video_path TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        reviewed_at TEXT,
        telegram_chat_id INTEGER,
        telegram_message_id INTEGER,
        published_id TEXT,
        published_url TEXT,
        publication_consumed INTEGER NOT NULL DEFAULT 0,
        delivery_error TEXT,
        PRIMARY KEY (job_id, version)
    )
    """,
)

MIGRATION_003 = (
    """
    CREATE TABLE IF NOT EXISTS story_scene_assets (
        scene_asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        story_id TEXT NOT NULL,
        scene_index INTEGER NOT NULL,
        shot_index INTEGER NOT NULL,
        asset_source TEXT NOT NULL CHECK(asset_source IN ('local_bank', 'curated_web', 'ai_generated')),
        source_url_or_path TEXT NOT NULL,
        framing_type TEXT NOT NULL,
        prompt_used TEXT,
        dhash TEXT,
        duration_sec REAL NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
        FOREIGN KEY(story_id) REFERENCES stories(story_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_scene_assets_story ON story_scene_assets(story_id, scene_index, shot_index)
    """,
    """
    CREATE TABLE IF NOT EXISTS video_analytics_snapshots (
        snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT NOT NULL,
        story_id TEXT NOT NULL,
        channel TEXT NOT NULL CHECK(channel IN ('horror', 'drama', 'scifi', 'moku', 'aelithia')),
        view_count INTEGER NOT NULL DEFAULT 0,
        like_count INTEGER NOT NULL DEFAULT 0,
        comment_count INTEGER NOT NULL DEFAULT 0,
        avg_view_duration_sec REAL,
        retention_rate_pct REAL,
        snapshot_interval TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        FOREIGN KEY(story_id) REFERENCES stories(story_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_analytics_story_interval ON video_analytics_snapshots(story_id, snapshot_interval)
    """,
    """
    CREATE TABLE IF NOT EXISTS production_metrics (
        metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL UNIQUE,
        story_id TEXT NOT NULL,
        audio_duration_sec REAL NOT NULL,
        render_time_sec REAL NOT NULL,
        tts_time_sec REAL,
        video_size_bytes INTEGER NOT NULL,
        integrated_lufs REAL,
        qa_audit_passed INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
    )
    """,
)

MIGRATION_004 = (
    """
    CREATE TABLE IF NOT EXISTS system_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        level TEXT NOT NULL,
        event_type TEXT NOT NULL,
        run_id TEXT,
        story_id TEXT,
        channel TEXT,
        component TEXT,
        stage TEXT,
        error_code TEXT,
        message TEXT,
        details_json TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_ts ON system_events(ts)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_run ON system_events(run_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_type_level ON system_events(event_type, level)
    """,
)

MIGRATION_005 = (
    """
    CREATE TABLE IF NOT EXISTS scheduler_lane_state (
        lane_id TEXT PRIMARY KEY,
        next_due_at INTEGER NOT NULL,
        last_started_at INTEGER,
        last_run_id TEXT,
        consecutive_empty INTEGER NOT NULL DEFAULT 0,
        paused INTEGER NOT NULL DEFAULT 0,
        pause_reason TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lane_leases (
        job_id TEXT PRIMARY KEY,
        lane_id TEXT NOT NULL UNIQUE,
        channel TEXT NOT NULL,
        owner TEXT NOT NULL,
        run_id TEXT NOT NULL UNIQUE,
        acquired_at INTEGER NOT NULL,
        heartbeat_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        FOREIGN KEY(job_id) REFERENCES stories(story_id) ON DELETE CASCADE,
        FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_lane_leases_expiry ON lane_leases(expires_at)
    """,
    "ALTER TABLE runs ADD COLUMN lane_id TEXT",
    "ALTER TABLE stories ADD COLUMN lane_id TEXT",
    "ALTER TABLE stories ADD COLUMN source_license TEXT",
    "ALTER TABLE artifacts ADD COLUMN story_key TEXT",
    "ALTER TABLE content_fingerprints ADD COLUMN simhash INTEGER",
    """
    CREATE INDEX IF NOT EXISTS idx_artifacts_story_key ON artifacts(story_key, kind)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_stories_lane ON stories(channel, lane_id, status, next_attempt_at)
    """,
)

MIGRATION_006 = (
    "ALTER TABLE publications ADD COLUMN video_sha256 TEXT",
    "ALTER TABLE publications ADD COLUMN drive_video_id TEXT",
    "ALTER TABLE publications ADD COLUMN drive_backup_metadata TEXT",
    "ALTER TABLE publications ADD COLUMN language TEXT DEFAULT 'es'",
    "ALTER TABLE publications ADD COLUMN source_language TEXT DEFAULT 'es'",
    "ALTER TABLE publications ADD COLUMN hook_summary TEXT",
    "ALTER TABLE publications ADD COLUMN synopsis TEXT",
    "ALTER TABLE publications ADD COLUMN themes_json TEXT",
    "ALTER TABLE publications ADD COLUMN simhash TEXT",
    "ALTER TABLE publications ADD COLUMN full_script TEXT",
    "ALTER TABLE publications ADD COLUMN predictive_success_score REAL DEFAULT 0.0",
    "ALTER TABLE publications ADD COLUMN score_rationale TEXT",
    "ALTER TABLE publications ADD COLUMN used_resources TEXT",
    "ALTER TABLE publications ADD COLUMN duration_sec REAL DEFAULT 0.0",
    "CREATE INDEX IF NOT EXISTS idx_publications_channel ON publications(channel)",
    "CREATE INDEX IF NOT EXISTS idx_publications_verified_at ON publications(verified_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_publications_simhash ON publications(simhash)",
    "CREATE INDEX IF NOT EXISTS idx_publications_video_id ON publications(video_id)",
)

MIGRATION_007 = (
    "ALTER TABLE publications ADD COLUMN actual_success_score REAL NOT NULL DEFAULT 0.0",
    "ALTER TABLE publications ADD COLUMN music_track TEXT",
    "ALTER TABLE scheduler_state ADD COLUMN last_24h_sweep_at INTEGER",
    "CREATE INDEX IF NOT EXISTS idx_publications_score ON publications(channel, actual_success_score)",
    "CREATE INDEX IF NOT EXISTS idx_publications_sha256 ON publications(video_sha256)",
)

MIGRATION_008 = (
    "ALTER TABLE publications ADD COLUMN comment_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE publications ADD COLUMN view_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE publications ADD COLUMN like_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE publications ADD COLUMN comment_status TEXT DEFAULT 'none'",
    "ALTER TABLE publications ADD COLUMN comment_error TEXT",
    "ALTER TABLE publications ADD COLUMN pinned_comment TEXT",
    "CREATE INDEX IF NOT EXISTS idx_publications_comment_status ON publications(comment_status)",
    "CREATE INDEX IF NOT EXISTS idx_publications_comment_count ON publications(channel, comment_count)",
    "CREATE INDEX IF NOT EXISTS idx_publications_views ON publications(channel, view_count)",
)

MIGRATION_009 = (
    """
    CREATE TABLE IF NOT EXISTS video_analytics_snapshots_v9 (
        snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT NOT NULL,
        story_id TEXT NOT NULL,
        channel TEXT NOT NULL CHECK(channel IN ('horror', 'drama', 'scifi', 'moku', 'aelithia')),
        view_count INTEGER NOT NULL DEFAULT 0,
        like_count INTEGER NOT NULL DEFAULT 0,
        comment_count INTEGER NOT NULL DEFAULT 0,
        avg_view_duration_sec REAL,
        retention_rate_pct REAL,
        snapshot_interval TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        FOREIGN KEY(story_id) REFERENCES stories(story_id)
    )
    """,
    """
    INSERT OR IGNORE INTO video_analytics_snapshots_v9 (
        snapshot_id, video_id, story_id, channel, view_count, like_count, comment_count,
        avg_view_duration_sec, retention_rate_pct, snapshot_interval, recorded_at
    ) SELECT
        snapshot_id, video_id, story_id, channel, view_count, like_count, comment_count,
        avg_view_duration_sec, retention_rate_pct, snapshot_interval, recorded_at
    FROM video_analytics_snapshots
    """,
    "DROP TABLE video_analytics_snapshots",
    "ALTER TABLE video_analytics_snapshots_v9 RENAME TO video_analytics_snapshots",
    """
    CREATE INDEX IF NOT EXISTS idx_analytics_story_interval ON video_analytics_snapshots(story_id, snapshot_interval)
    """,
)


@dataclass(frozen=True)
class MigrationReport:
    dry_run: bool
    applied_versions: tuple[int, ...]
    legacy_before: dict[str, int]
    canonical_after: dict[str, int]
    changed_rows: int
    quick_check: str


def validate_db_path(db_path: Any) -> Path | str:
    """Validate database path argument before executing filesystem or SQLite operations."""
    if db_path is None:
        raise TypeError("db_path cannot be None")

    import unittest.mock
    if isinstance(db_path, unittest.mock.Base) or "mock" in type(db_path).__module__.lower():
        raise TypeError("Mock objects are not valid database paths")

    if not isinstance(db_path, (str, Path, os.PathLike)):
        raise TypeError("db_path must be str, Path, or os.PathLike")

    s = str(db_path).strip()
    if not s:
        raise ValueError("db_path cannot be empty string")

    if s.startswith(("<MagicMock", "<Mock")) or "MagicMock name=" in s:
        raise ValueError("Stringified mock representation detected in db_path")

    if s == ":memory:" or s.startswith("file::memory:"):
        return ":memory:"

    return Path(db_path)


@contextmanager
def connect(db_path: str | os.PathLike[str], *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    path_or_str = validate_db_path(db_path)
    if str(path_or_str) == ":memory:":
        conn = sqlite3.connect(":memory:", timeout=BUSY_TIMEOUT_MS / 1000)
    else:
        path = Path(path_or_str)
        if not read_only:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000)
        else:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-8000")
    if not read_only:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
    finally:
        conn.close()


def wal_checkpoint_passive(db_path: str | os.PathLike[str] | Path) -> tuple[int, int, int]:
    """Safely run PRAGMA wal_checkpoint(PASSIVE) without blocking concurrent readers/writers."""
    path_or_str = validate_db_path(db_path)
    if str(path_or_str) == ":memory:":
        return (0, 0, 0)
    path = Path(path_or_str)
    if not path.exists():
        return (0, 0, 0)
    with connect(path) as conn:
        row = conn.execute("PRAGMA wal_checkpoint(PASSIVE);").fetchone()
        if row is None:
            return (0, 0, 0)
        return (int(row[0]), int(row[1]), int(row[2]))


def _ensure_legacy_stories(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stories (
            story_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'PENDING',
            error_msg TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            channel TEXT DEFAULT 'moku',
            youtube_url TEXT
        )
        """
    )


def _add_story_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(stories)").fetchall()}
    statements = {
        "run_id": "ALTER TABLE stories ADD COLUMN run_id TEXT",
        "score": "ALTER TABLE stories ADD COLUMN score INTEGER NOT NULL DEFAULT 0",
        "upvote_ratio": "ALTER TABLE stories ADD COLUMN upvote_ratio REAL NOT NULL DEFAULT 0.0",
        "num_comments": "ALTER TABLE stories ADD COLUMN num_comments INTEGER NOT NULL DEFAULT 0",
        "retry_count": "ALTER TABLE stories ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
        "failure_code": "ALTER TABLE stories ADD COLUMN failure_code TEXT",
        "next_attempt_at": "ALTER TABLE stories ADD COLUMN next_attempt_at INTEGER",
        "youtube_video_id": "ALTER TABLE stories ADD COLUMN youtube_video_id TEXT",
        "publication_visibility": "ALTER TABLE stories ADD COLUMN publication_visibility TEXT",
        "publication_channel": "ALTER TABLE stories ADD COLUMN publication_channel TEXT",
        "drive_file_id": "ALTER TABLE stories ADD COLUMN drive_file_id TEXT",
        "lane_id": "ALTER TABLE stories ADD COLUMN lane_id TEXT",
        "source_license": "ALTER TABLE stories ADD COLUMN source_license TEXT",
    }
    for column, stmt in statements.items():
        if column not in existing:
            conn.execute(stmt)


def _apply_migration_005(conn: sqlite3.Connection) -> None:
    for statement in MIGRATION_005:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "duplicate column name" in msg:
                continue
            if "already exists" in msg:
                continue
            raise


def _apply_migration_006(conn: sqlite3.Connection) -> None:
    for statement in MIGRATION_006:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "duplicate column name" in msg:
                continue
            if "already exists" in msg:
                continue
            raise


def _apply_migration_007(conn: sqlite3.Connection) -> None:
    for statement in MIGRATION_007:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "duplicate column name" in msg:
                continue
            if "already exists" in msg:
                continue
            raise


def _apply_migration_008(conn: sqlite3.Connection) -> None:
    for statement in MIGRATION_008:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "duplicate column name" in msg:
                continue
            if "already exists" in msg:
                continue
            raise


def _apply_migration_009(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='video_analytics_snapshots'"
    ).fetchone()
    if row and "horror" in str(row[0]).lower():
        return

    conn.execute(MIGRATION_009[0])
    if row:
        conn.execute(MIGRATION_009[1])
        conn.execute(MIGRATION_009[2])
    conn.execute(MIGRATION_009[3])
    conn.execute(MIGRATION_009[4])


def _count_channels(conn: sqlite3.Connection, names: Sequence[str]) -> dict[str, int]:
    placeholders = ",".join("?" for _ in names)
    sql = f"""
    SELECT channel, COUNT(*) AS count
    FROM stories
    WHERE channel IN ({placeholders})
    GROUP BY channel
    """
    counts = {name: 0 for name in names}
    for row in conn.execute(sql, tuple(names)).fetchall():
        counts[row["channel"]] = int(row["count"])
    return counts


def _apply_v1_operational_core(conn: sqlite3.Connection, applied: list[int]) -> None:
    conn.execute(MIGRATION_001[0])
    existing = conn.execute(
        "SELECT checksum FROM schema_migrations WHERE version = 1"
    ).fetchone()
    checksum = _migration_checksum("operational_core", MIGRATION_001)
    if existing and existing["checksum"] != checksum:
        raise RuntimeError("Checksum de migración 1 no coincide")
    if not existing:
        for statement in MIGRATION_001[1:]:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
            "VALUES (1, 'operational_core', ?, ?)",
            (checksum, _utc_now()),
        )
        applied.append(1)


def _apply_v2_canonical_channels(conn: sqlite3.Connection, applied: list[int]) -> tuple[dict[str, int], int]:
    _add_story_columns(conn)
    legacy_before = _count_channels(conn, ("terror", "soy_el_malo"))
    changed_rows = sum(legacy_before.values())
    conn.execute("UPDATE stories SET channel = 'moku' WHERE channel = 'terror'")
    conn.execute("UPDATE stories SET channel = 'aelithia' WHERE channel = 'soy_el_malo'")
    alias_statements = ("terror -> moku", "soy_el_malo -> aelithia")
    alias_checksum = _migration_checksum("canonical_channels", alias_statements)
    existing_alias = conn.execute(
        "SELECT checksum FROM schema_migrations WHERE version = 2"
    ).fetchone()
    if existing_alias and existing_alias["checksum"] != alias_checksum:
        raise RuntimeError("Checksum de migración 2 no coincide")
    if not existing_alias:
        conn.execute(
            "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
            "VALUES (2, 'canonical_channels', ?, ?)",
            (alias_checksum, _utc_now()),
        )
        applied.append(2)
    return legacy_before, changed_rows


def _apply_v3_scene_assets(conn: sqlite3.Connection, applied: list[int]) -> None:
    m3_checksum = _migration_checksum("scene_assets_and_analytics", MIGRATION_003)
    legacy_m3_checksums = {
        m3_checksum,
        "78f637e3595bbdac7f29a4a7c3e909591f1d8ad1da9c4f03b75011552dbd882f",
        "01993a6db132c252ecaa4563873c67bfecdc2b958dbf272e0b1fa4a9f934d73d",
    }
    existing_m3 = conn.execute(
        "SELECT checksum FROM schema_migrations WHERE version = 3"
    ).fetchone()
    if existing_m3 and existing_m3["checksum"] not in legacy_m3_checksums:
        raise RuntimeError("Checksum de migración 3 no coincide")
    if not existing_m3 or existing_m3["checksum"] != m3_checksum:
        for statement in MIGRATION_003:
            conn.execute(statement)
        if not existing_m3:
            conn.execute(
                "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
                "VALUES (3, 'scene_assets_and_analytics', ?, ?)",
                (m3_checksum, _utc_now()),
            )
        else:
            conn.execute(
                "UPDATE schema_migrations SET name = 'scene_assets_and_analytics', checksum = ?, applied_at = ? WHERE version = 3",
                (m3_checksum, _utc_now()),
            )
        applied.append(3)


def _apply_v4_observability(conn: sqlite3.Connection, applied: list[int]) -> None:
    m4_checksum = _migration_checksum("observability_events", MIGRATION_004)
    existing_m4 = conn.execute(
        "SELECT checksum FROM schema_migrations WHERE version = 4"
    ).fetchone()
    if existing_m4 and existing_m4["checksum"] != m4_checksum:
        raise RuntimeError("Checksum de migración 4 no coincide")
    if not existing_m4:
        for statement in MIGRATION_004:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
            "VALUES (4, 'observability_events', ?, ?)",
            (m4_checksum, _utc_now()),
        )
        applied.append(4)


def _apply_v5_production_lanes(conn: sqlite3.Connection, applied: list[int]) -> None:
    m5_checksum = _migration_checksum("production_lanes", MIGRATION_005)
    existing_m5 = conn.execute(
        "SELECT checksum FROM schema_migrations WHERE version = 5"
    ).fetchone()
    if existing_m5 and existing_m5["checksum"] != m5_checksum:
        raise RuntimeError("Checksum de migración 5 no coincide")
    if not existing_m5:
        _apply_migration_005(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
            "VALUES (5, 'production_lanes', ?, ?)",
            (m5_checksum, _utc_now()),
        )
        applied.append(5)


def _apply_v6_publications_inventory(conn: sqlite3.Connection, applied: list[int]) -> None:
    m6_checksum = _migration_checksum("publications_inventory", MIGRATION_006)
    existing_m6 = conn.execute(
        "SELECT checksum FROM schema_migrations WHERE version = 6"
    ).fetchone()
    if existing_m6 and existing_m6["checksum"] != m6_checksum:
        raise RuntimeError("Checksum de migración 6 no coincide")
    if not existing_m6:
        _apply_migration_006(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
            "VALUES (6, 'publications_inventory', ?, ?)",
            (m6_checksum, _utc_now()),
        )
        applied.append(6)


def _apply_v7_performance_scoring(conn: sqlite3.Connection, applied: list[int]) -> None:
    m7_checksum = _migration_checksum("performance_scoring_and_cadence", MIGRATION_007)
    existing_m7 = conn.execute(
        "SELECT checksum FROM schema_migrations WHERE version = 7"
    ).fetchone()
    if existing_m7 and existing_m7["checksum"] != m7_checksum:
        raise RuntimeError("Checksum de migración 7 no coincide")
    if not existing_m7:
        _apply_migration_007(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
            "VALUES (7, 'performance_scoring_and_cadence', ?, ?)",
            (m7_checksum, _utc_now()),
        )
        applied.append(7)


def _apply_v8_comment_lifecycle_and_metrics(conn: sqlite3.Connection, applied: list[int]) -> None:
    m8_checksum = _migration_checksum("comment_lifecycle_and_metrics", MIGRATION_008)
    existing_m8 = conn.execute(
        "SELECT checksum FROM schema_migrations WHERE version = 8"
    ).fetchone()
    if existing_m8 and existing_m8["checksum"] != m8_checksum:
        raise RuntimeError("Checksum de migración 8 no coincide")
    if not existing_m8:
        _apply_migration_008(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
            "VALUES (8, 'comment_lifecycle_and_metrics', ?, ?)",
            (m8_checksum, _utc_now()),
        )
        applied.append(8)


def _apply_v9_canonical_channels_analytics(conn: sqlite3.Connection, applied: list[int]) -> None:
    m9_checksum = _migration_checksum("canonical_channels_analytics", MIGRATION_009)
    existing_m9 = conn.execute(
        "SELECT checksum FROM schema_migrations WHERE version = 9"
    ).fetchone()
    if existing_m9 and existing_m9["checksum"] != m9_checksum:
        raise RuntimeError("Checksum de migración 9 no coincide")
    if not existing_m9:
        _apply_migration_009(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
            "VALUES (9, 'canonical_channels_analytics', ?, ?)",
            (m9_checksum, _utc_now()),
        )
        applied.append(9)


def _ensure_performance_indexes(conn: sqlite3.Connection) -> None:
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_stories_queue_claim ON stories(channel, status, next_attempt_at, score)",
        "CREATE INDEX IF NOT EXISTS idx_runs_channel_status ON runs(channel, status)",
        "CREATE INDEX IF NOT EXISTS idx_runs_story ON runs(story_id)",
        "CREATE INDEX IF NOT EXISTS idx_leases_expires ON leases(expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_stage_logs_run ON stage_logs(run_id)",
    )
    for idx_sql in indexes:
        conn.execute(idx_sql)


def migrate_database(
    db_path: str | os.PathLike[str],
    *,
    dry_run: bool = False,
) -> MigrationReport:
    """Apply additive schema and canonical-channel migrations atomically."""
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _ensure_legacy_stories(conn)
            applied: list[int] = []
            _apply_v1_operational_core(conn, applied)
            legacy_before, changed_rows = _apply_v2_canonical_channels(conn, applied)
            _apply_v3_scene_assets(conn, applied)
            _apply_v4_observability(conn, applied)
            _apply_v5_production_lanes(conn, applied)
            _apply_v6_publications_inventory(conn, applied)
            _apply_v7_performance_scoring(conn, applied)
            _apply_v8_comment_lifecycle_and_metrics(conn, applied)
            _apply_v9_canonical_channels_analytics(conn, applied)
            _ensure_performance_indexes(conn)

            from src.core.channel_profile import ChannelProfileRegistry
            active_channel_ids = tuple(ChannelProfileRegistry.list_active_channel_ids())
            canonical_after = _count_channels(conn, active_channel_ids or ("moku", "aelithia"))
            quick_check = str(conn.execute("PRAGMA quick_check").fetchone()[0])
            if quick_check != "ok":
                raise RuntimeError(f"SQLite quick_check falló: {quick_check}")
            if dry_run:
                conn.rollback()
            else:
                conn.commit()
            return MigrationReport(
                dry_run=dry_run,
                applied_versions=tuple(applied),
                legacy_before=legacy_before,
                canonical_after=canonical_after,
                changed_rows=changed_rows,
                quick_check=quick_check,
            )
        except Exception:
            conn.rollback()
            raise


def backup_database(
    db_path: str | os.PathLike[str],
    target_path: str | os.PathLike[str] | None = None,
) -> Path:
    """Safely back up an active SQLite database to target_path using the SQLite Backup API."""
    source_path = validate_db_path(db_path)
    if str(source_path) == ":memory:":
        raise ValueError("No se puede hacer backup de una base de datos en memoria")
    src = Path(source_path)
    if not src.is_file():
        raise FileNotFoundError(f"Base de datos de origen no existe: {src}")

    if target_path is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        target = src.with_name(f"{src.stem}_backup_{timestamp}{src.suffix}")
    else:
        target = Path(validate_db_path(target_path))

    target.parent.mkdir(parents=True, exist_ok=True)
    with connect(src, read_only=True) as src_conn, connect(target) as dst_conn:
        src_conn.backup(dst_conn)

    with connect(target, read_only=True) as check_conn:
        result = check_conn.execute("PRAGMA quick_check;").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"Backup SQLite inválido: {result}")
    return target
