"""SQLite repository with versioned migrations, leases and publication proofs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from src.core.domain import (
    ALL_STATUSES,
    CanonicalChannel,
    JobStatus,
    PublicationProof,
    canonical_channel,
)


BUSY_TIMEOUT_MS = 15_000


def to_signed_64(val: int | None) -> int | None:
    if val is None:
        return None
    val = int(val) & 0xFFFFFFFFFFFFFFFF
    return val if val < (1 << 63) else val - (1 << 64)


def to_unsigned_64(val: int | None) -> int:
    if val is None:
        return 0
    return int(val) & 0xFFFFFFFFFFFFFFFF


def compute_simhash_64(text: str | None) -> int:
    """Compute a 64-bit SimHash over normalized text with word weights and bigrams."""
    if not text:
        return 0
    tokens = re.findall(r"\w+", text.lower(), re.UNICODE)
    if not tokens:
        return 0

    features: list[str] = []
    for token in tokens:
        weight = min(len(token), 4)
        features.extend([token] * weight)
    if len(tokens) >= 2:
        for i in range(len(tokens) - 1):
            features.append(f"{tokens[i]}_{tokens[i+1]}")

    v = [0] * 64
    for feature in features:
        h = int.from_bytes(hashlib.md5(feature.encode("utf-8")).digest()[:8], "big")
        for i in range(64):
            if (h >> i) & 1:
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def simhash_hamming_distance(h1: int | None, h2: int | None) -> int:
    """Compute Hamming distance (differing bits) between two 64-bit integers."""
    return (to_unsigned_64(h1) ^ to_unsigned_64(h2)).bit_count()


def is_simhash_duplicate(h1: int | None, h2: int | None, max_distance: int = 3) -> bool:
    """Return True if Hamming distance <= max_distance (default 3 bits)."""
    return simhash_hamming_distance(h1, h2) <= max_distance


def re_full_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


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
        channel TEXT NOT NULL CHECK(channel IN ('moku', 'aelithia')),
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


@dataclass(frozen=True)
class MigrationReport:
    dry_run: bool
    applied_versions: tuple[int, ...]
    legacy_before: dict[str, int]
    canonical_after: dict[str, int]
    changed_rows: int
    quick_check: str


@contextmanager
def connect(db_path: str | os.PathLike[str], *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    path = Path(db_path)
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000)
    else:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    if not read_only:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
    finally:
        conn.close()


def wal_checkpoint_passive(db_path: str | os.PathLike[str] | Path) -> tuple[int, int, int]:
    """Safely run PRAGMA wal_checkpoint(PASSIVE) without blocking concurrent readers/writers.

    Returns:
        tuple[int, int, int]: (busy, log_pages, checkpointed_pages) where busy is 0 if non-blocked.
    """
    path = Path(db_path)
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
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(stories)")}
    columns = {
        "run_id": "TEXT",
        "youtube_video_id": "TEXT",
        "publication_visibility": "TEXT",
        "publication_channel": "TEXT",
        "drive_file_id": "TEXT",
        "next_attempt_at": "INTEGER",
        "failure_code": "TEXT",
        "retry_count": "INTEGER NOT NULL DEFAULT 0",
        "score": "INTEGER NOT NULL DEFAULT 0",
        "upvote_ratio": "REAL NOT NULL DEFAULT 0",
        "num_comments": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, declaration in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE stories ADD COLUMN {name} {declaration}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_stories_channel_status "
        "ON stories(channel, status, created_at)"
    )


def _apply_migration_005(conn: sqlite3.Connection) -> None:
    """Apply v5 additively: CREATE IF NOT EXISTS + idempotent ADD COLUMN."""
    for statement in MIGRATION_005:
        text = " ".join(statement.split())
        if text.startswith("ALTER TABLE"):
            table = text.split()[2]
            column = text.split()[5]
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                conn.execute(statement)
            continue
        conn.execute(statement)


def _count_channels(conn: sqlite3.Connection, names: Sequence[str]) -> dict[str, int]:
    result = {name: 0 for name in names}
    placeholders = ",".join("?" for _ in names)
    for row in conn.execute(
        f"SELECT channel, COUNT(*) AS count FROM stories "
        f"WHERE channel IN ({placeholders}) GROUP BY channel",
        tuple(names),
    ):
        result[str(row["channel"])] = int(row["count"])
    return result


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
            conn.execute(MIGRATION_001[0])
            applied: list[int] = []
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

            _add_story_columns(conn)
            legacy_before = _count_channels(conn, ("terror", "soy_el_malo"))
            changed_rows = sum(legacy_before.values())
            conn.execute("UPDATE stories SET channel = 'moku' WHERE channel = 'terror'")
            conn.execute(
                "UPDATE stories SET channel = 'aelithia' WHERE channel = 'soy_el_malo'"
            )
            alias_statements = (
                "terror -> moku",
                "soy_el_malo -> aelithia",
            )
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

            m3_checksum = _migration_checksum("scene_assets_and_analytics", MIGRATION_003)
            legacy_m3_checksums = {
                m3_checksum,
                "78f637e3595bbdac7f29a4a7c3e909591f1d8ad1da9c4f03b75011552dbd882f",
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
            canonical_after = _count_channels(conn, ("moku", "aelithia"))
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
    backup_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Create and verify a consistent backup using SQLite's backup API."""
    source_path = Path(db_path)
    target_dir = Path(backup_dir) if backup_dir else source_path.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = target_dir / f"{source_path.stem}-{stamp}.sqlite3"
    with connect(source_path, read_only=True) as source:
        destination = sqlite3.connect(str(target), timeout=10.0)
        destination.execute("PRAGMA journal_mode=WAL;")
        destination.execute("PRAGMA busy_timeout=15000;")
        destination.execute("PRAGMA synchronous=NORMAL;")
        try:
            source.backup(destination)
            destination.commit()
        finally:
            destination.close()
    os.chmod(target, 0o600)
    with connect(target, read_only=True) as check:
        result = str(check.execute("PRAGMA quick_check").fetchone()[0])
    if result != "ok":
        raise RuntimeError(f"Backup SQLite inválido: {result}")
    return target


class QueueRepository:
    def __init__(self, db_path: str | os.PathLike[str]):
        self.db_path = str(db_path)

    def initialize(self) -> MigrationReport:
        return migrate_database(self.db_path)

    def wal_checkpoint_passive(self) -> tuple[int, int, int]:
        """Safely run PRAGMA wal_checkpoint(PASSIVE) for this repository's database."""
        return wal_checkpoint_passive(self.db_path)

    def checkpoint_wal(self, mode: str = "PASSIVE") -> tuple[int, int, int]:
        """Safely checkpoint WAL frames back to the database file without blocking writers."""
        valid_modes = {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}
        selected_mode = mode.upper() if mode.upper() in valid_modes else "PASSIVE"
        with connect(self.db_path) as conn:
            row = conn.execute(f"PRAGMA wal_checkpoint({selected_mode});").fetchone()
            if row is None:
                return (0, 0, 0)
            return (int(row[0]), int(row[1]), int(row[2]))

    @staticmethod
    def _holds_lease(
        conn: sqlite3.Connection,
        story_id: str,
        run_id: str,
        owner: str,
        *,
        now: int | None = None,
    ) -> bool:
        """True when a live lease for (story, run, owner) exists in either table."""
        current = int(time.time() if now is None else now)
        for table in ("leases", "lane_leases"):
            if conn.execute(
                f"SELECT 1 FROM {table} "
                "WHERE job_id = ? AND run_id = ? AND owner = ? AND expires_at > ?",
                (story_id, run_id, owner, current),
            ).fetchone():
                return True
        return False

    def enqueue(
        self,
        story_id: str,
        title: str,
        content: str,
        url: str,
        channel: str | CanonicalChannel,
        *,
        score: int = 0,
        upvote_ratio: float = 0.0,
        num_comments: int = 0,
        lane_id: str | None = None,
        source_license: str | None = None,
    ) -> bool:
        channel_key = canonical_channel(channel).value
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO stories("
                    "story_id, title, content, url, status, channel, "
                    "score, upvote_ratio, num_comments, lane_id, source_license"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        story_id,
                        title,
                        content,
                        url,
                        JobStatus.PENDING.value,
                        channel_key,
                        int(score),
                        float(upvote_ratio),
                        int(num_comments),
                        lane_id,
                        source_license,
                    ),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                conn.rollback()
                return False

    def claim(
        self,
        channel: str | CanonicalChannel,
        owner: str,
        *,
        lease_seconds: int = 900,
        mode: str = "publish",
        now: int | None = None,
    ) -> dict[str, Any] | None:
        channel_key = canonical_channel(channel).value
        if not owner.strip():
            raise ValueError("El propietario del lease es obligatorio")
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            paused = conn.execute(
                "SELECT paused FROM channel_controls WHERE channel = ?", (channel_key,)
            ).fetchone()
            if paused and paused["paused"]:
                conn.rollback()
                return None
            self._recover_expired_locked(conn, current)
            if conn.execute(
                "SELECT 1 FROM leases WHERE channel = ?", (channel_key,)
            ).fetchone() or conn.execute(
                "SELECT 1 FROM lane_leases WHERE channel = ?", (channel_key,)
            ).fetchone():
                conn.rollback()
                return None
            # QUEUE_RANK_BY_SCORE=0 opts out and restores the legacy FIFO ordering.
            order_by = (
                "score DESC, created_at, story_id"
                if os.environ.get("QUEUE_RANK_BY_SCORE", "") != "0"
                else "created_at, story_id"
            )
            row = conn.execute(
                f"""
                SELECT * FROM stories
                WHERE channel = ?
                  AND status IN (?, ?)
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY {order_by}
                LIMIT 1
                """,
                (
                    channel_key,
                    JobStatus.PENDING.value,
                    JobStatus.RETRYABLE_FAILED.value,
                    current,
                ),
            ).fetchone()
            if not row:
                conn.rollback()
                return None
            run_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO runs(
                    run_id, channel, story_id, mode, status, owner,
                    started_at, heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    channel_key,
                    row["story_id"],
                    mode,
                    JobStatus.PROCESSING.value,
                    owner,
                    _utc_now(),
                    _utc_now(),
                ),
            )
            conn.execute(
                """
                INSERT INTO leases(
                    job_id, channel, owner, run_id, acquired_at,
                    heartbeat_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    channel = excluded.channel,
                    owner = excluded.owner,
                    run_id = excluded.run_id,
                    acquired_at = excluded.acquired_at,
                    heartbeat_at = excluded.heartbeat_at,
                    expires_at = excluded.expires_at
                """,
                (
                    row["story_id"],
                    channel_key,
                    owner,
                    run_id,
                    current,
                    current,
                    current + lease_seconds,
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO run_stories(run_id, story_id, position) VALUES (?, ?, 0)",
                (run_id, row["story_id"]),
            )
            conn.execute(
                """
                UPDATE stories
                SET status = ?, run_id = ?, error_msg = NULL,
                    failure_code = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ?
                """,
                (JobStatus.PROCESSING.value, run_id, row["story_id"]),
            )
            conn.commit()
            result = dict(row)
            result.update(status=JobStatus.PROCESSING.value, run_id=run_id)
            return result

    def claim_exact(
        self,
        story_id: str,
        channel: str | CanonicalChannel,
        owner: str,
        *,
        lease_seconds: int = 900,
        mode: str = "directed-publish",
        now: int | None = None,
    ) -> dict[str, Any] | None:
        """Atomically claim one explicit story without recovering or touching others."""
        requested_id = str(story_id or "").strip()
        if not requested_id:
            raise ValueError("story_id es obligatorio para el claim dirigido")
        if not owner.strip():
            raise ValueError("El propietario del lease es obligatorio")
        channel_key = canonical_channel(channel).value
        current = int(time.time() if now is None else now)
        allowed = (
            JobStatus.PENDING.value,
            JobStatus.RETRYABLE_FAILED.value,
            JobStatus.WAITING_IMAGE_QUOTA.value,
            JobStatus.WAITING_LLM_QUOTA.value,
            JobStatus.WAITING_YOUTUBE_LIMIT.value,
        )
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            paused = conn.execute(
                "SELECT paused FROM channel_controls WHERE channel = ?", (channel_key,)
            ).fetchone()
            if paused and paused["paused"]:
                conn.rollback()
                return None
            self._recover_expired_exact_locked(
                conn, requested_id, channel_key, current
            )
            if conn.execute(
                "SELECT 1 FROM leases WHERE channel = ?", (channel_key,)
            ).fetchone() or conn.execute(
                "SELECT 1 FROM lane_leases WHERE channel = ?", (channel_key,)
            ).fetchone():
                conn.rollback()
                return None
            placeholders = ",".join("?" for _ in allowed)
            row = conn.execute(
                f"""
                SELECT * FROM stories
                WHERE story_id = ? AND channel = ?
                  AND status IN ({placeholders})
                  AND youtube_video_id IS NULL
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                """,
                (requested_id, channel_key, *allowed, current),
            ).fetchone()
            if not row:
                conn.rollback()
                return None
            run_id = uuid.uuid4().hex
            now_text = _utc_now()
            conn.execute(
                """
                INSERT INTO runs(
                    run_id, channel, story_id, mode, status, owner,
                    started_at, heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    channel_key,
                    requested_id,
                    mode,
                    JobStatus.PROCESSING.value,
                    owner,
                    now_text,
                    now_text,
                ),
            )
            conn.execute(
                """
                INSERT INTO leases(
                    job_id, channel, owner, run_id, acquired_at,
                    heartbeat_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    channel = excluded.channel,
                    owner = excluded.owner,
                    run_id = excluded.run_id,
                    acquired_at = excluded.acquired_at,
                    heartbeat_at = excluded.heartbeat_at,
                    expires_at = excluded.expires_at
                """,
                (
                    requested_id,
                    channel_key,
                    owner,
                    run_id,
                    current,
                    current,
                    current + lease_seconds,
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO run_stories(run_id, story_id, position) VALUES (?, ?, 0)",
                (run_id, requested_id),
            )
            updated = conn.execute(
                f"""
                UPDATE stories
                SET status = ?, run_id = ?, error_msg = NULL,
                    failure_code = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ? AND channel = ? AND status IN ({placeholders})
                """,
                (
                    JobStatus.PROCESSING.value,
                    run_id,
                    requested_id,
                    channel_key,
                    *allowed,
                ),
            )
            if updated.rowcount != 1:
                conn.rollback()
                return None
            conn.commit()
            result = dict(row)
            result.update(status=JobStatus.PROCESSING.value, run_id=run_id)
            return result

    def _recover_expired_exact_locked(
        self,
        conn: sqlite3.Connection,
        story_id: str,
        channel: str,
        now: int,
    ) -> int:
        expired = conn.execute(
            """
            SELECT job_id, run_id FROM leases
            WHERE job_id = ? AND channel = ? AND expires_at <= ?
            """,
            (story_id, channel, now),
        ).fetchall()
        for lease in expired:
            conn.execute(
                """
                UPDATE stories
                SET status = ?, run_id = NULL, failure_code = 'lease_expired',
                    error_msg = 'Lease dirigido expirado; trabajo reconciliado',
                    next_attempt_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ? AND run_id = ? AND status = ?
                """,
                (
                    JobStatus.RETRYABLE_FAILED.value,
                    lease["job_id"],
                    lease["run_id"],
                    JobStatus.PROCESSING.value,
                ),
            )
            conn.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, error_code = 'lease_expired'
                WHERE run_id = ? AND status = ?
                """,
                (
                    JobStatus.RETRYABLE_FAILED.value,
                    _utc_now(),
                    lease["run_id"],
                    JobStatus.PROCESSING.value,
                ),
            )
            conn.execute(
                "DELETE FROM leases WHERE job_id = ? AND run_id = ? AND expires_at <= ?",
                (lease["job_id"], lease["run_id"], now),
            )
        return len(expired)

    def recover_expired_exact(
        self,
        story_id: str,
        channel: str | CanonicalChannel,
        *,
        now: int | None = None,
    ) -> int:
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = self._recover_expired_exact_locked(
                conn,
                str(story_id or "").strip(),
                canonical_channel(channel).value,
                current,
            )
            conn.commit()
            return count

    def require_single_story_run(self, run_id: str, story_id: str) -> None:
        with connect(self.db_path, read_only=True) as conn:
            rows = conn.execute(
                "SELECT story_id, position FROM run_stories WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        if len(rows) != 1 or rows[0]["story_id"] != story_id or rows[0]["position"] != 0:
            raise RuntimeError(
                "El run dirigido debe contener exactamente una historia principal"
            )

    def _recover_expired_locked(self, conn: sqlite3.Connection, now: int) -> int:
        expired = conn.execute(
            "SELECT job_id, run_id FROM leases WHERE expires_at <= ?", (now,)
        ).fetchall()
        for lease in expired:
            conn.execute(
                """
                UPDATE stories
                SET status = ?, run_id = NULL, failure_code = 'lease_expired',
                    error_msg = 'Lease expirado; trabajo recuperado de forma segura',
                    updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ? AND run_id = ? AND status = ?
                """,
                (
                    JobStatus.RETRYABLE_FAILED.value,
                    lease["job_id"],
                    lease["run_id"],
                    JobStatus.PROCESSING.value,
                ),
            )
            conn.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, error_code = 'lease_expired'
                WHERE run_id = ?
                """,
                (JobStatus.RETRYABLE_FAILED.value, _utc_now(), lease["run_id"]),
            )
        conn.execute("DELETE FROM leases WHERE expires_at <= ?", (now,))
        return len(expired)

    def recover_expired_leases(self, *, now: int | None = None) -> int:
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = self._recover_expired_locked(conn, current)
            conn.commit()
            return count

    def heartbeat(
        self,
        run_id: str,
        owner: str,
        *,
        lease_seconds: int = 900,
        now: int | None = None,
    ) -> bool:
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                UPDATE leases SET heartbeat_at = ?, expires_at = ?
                WHERE run_id = ? AND owner = ? AND expires_at > ?
                """,
                (current, current + lease_seconds, run_id, owner, current),
            )
            if not cursor.rowcount:
                cursor = conn.execute(
                    """
                    UPDATE lane_leases SET heartbeat_at = ?, expires_at = ?
                    WHERE run_id = ? AND owner = ? AND expires_at > ?
                    """,
                    (current, current + lease_seconds, run_id, owner, current),
                )
            if cursor.rowcount:
                conn.execute(
                    "UPDATE runs SET heartbeat_at = ? WHERE run_id = ? AND owner = ?",
                    (_utc_now(), run_id, owner),
                )
            conn.commit()
            return bool(cursor.rowcount)

    def set_status(
        self,
        story_id: str,
        status: str | JobStatus,
        *,
        error_code: str | None = None,
        error_detail: str | None = None,
        retry_at: int | None = None,
        run_id: str | None = None,
        owner: str | None = None,
        now: int | None = None,
    ) -> bool:
        value = status.value if isinstance(status, JobStatus) else str(status)
        if value not in ALL_STATUSES:
            raise ValueError(f"Estado operativo inválido: {value}")
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT run_id, status FROM stories WHERE story_id = ?", (story_id,)
            ).fetchone()
            if not row:
                conn.rollback()
                raise KeyError(story_id)
            if row["status"] == JobStatus.PUBLISHED.value and value != JobStatus.PUBLISHED.value:
                conn.rollback()
                return False
            if (run_id is None) != (owner is None):
                conn.rollback()
                raise ValueError("run_id y owner deben proporcionarse juntos")
            active_run_id = row["run_id"]
            if run_id is not None:
                current = int(time.time() if now is None else now)
                lease = conn.execute(
                    """
                    SELECT 1 FROM leases
                    WHERE job_id = ? AND run_id = ? AND owner = ? AND expires_at > ?
                    """,
                    (story_id, run_id, owner, current),
                ).fetchone()
                if not lease:
                    lease = conn.execute(
                        """
                        SELECT 1 FROM lane_leases
                        WHERE job_id = ? AND run_id = ? AND owner = ? AND expires_at > ?
                        """,
                        (story_id, run_id, owner, current),
                    ).fetchone()
                if active_run_id != run_id or not lease:
                    conn.rollback()
                    return False
                active_run_id = run_id
            cursor = conn.execute(
                """
                UPDATE stories
                SET status = ?, failure_code = ?, error_msg = ?,
                    next_attempt_at = ?, retry_count = retry_count +
                        CASE WHEN ? = ? THEN 1 ELSE 0 END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ? AND status != ?
                """,
                (
                    value,
                    error_code,
                    error_detail,
                    retry_at,
                    value,
                    JobStatus.RETRYABLE_FAILED.value,
                    story_id,
                    JobStatus.PUBLISHED.value,
                ),
            )
            if not cursor.rowcount:
                conn.rollback()
                return False
            if active_run_id:
                release_states = {
                    JobStatus.PUBLISHED.value,
                    JobStatus.UPLOAD_UNCONFIRMED.value,
                    JobStatus.RETRYABLE_FAILED.value,
                    JobStatus.PERMANENT_FAILED.value,
                    JobStatus.WAITING_LLM_QUOTA.value,
                    JobStatus.WAITING_IMAGE_QUOTA.value,
                    JobStatus.WAITING_YOUTUBE_LIMIT.value,
                    "COMPLETED",
                    "FAILED",
                }
                finished = _utc_now() if value in release_states else None
                conn.execute(
                    """
                    UPDATE runs
                    SET status = ?, error_code = ?, error_detail = ?, finished_at = ?
                    WHERE run_id = ?
                    """,
                    (value, error_code, error_detail, finished, active_run_id),
                )
                if value in release_states:
                    conn.execute("DELETE FROM leases WHERE run_id = ?", (active_run_id,))
                    conn.execute("DELETE FROM lane_leases WHERE run_id = ?", (active_run_id,))
            conn.commit()
            return True

    def record_artifact(
        self,
        run_id: str,
        kind: str,
        *,
        local_path: str | None = None,
        remote_provider: str | None = None,
        remote_id: str | None = None,
        remote_name: str | None = None,
        size_bytes: int | None = None,
        sha256: str | None = None,
        verified: bool = False,
        story_key: str | None = None,
    ) -> None:
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Ensure a parent record exists in `runs` to satisfy foreign key constraint
                channel = "aelithia" if (story_key and "aelithia" in story_key) else "moku"
                now = _utc_now()
                conn.execute(
                    """
                    INSERT OR IGNORE INTO runs(
                        run_id, channel, story_id, mode, status, owner, started_at, heartbeat_at
                    ) VALUES (?, ?, NULL, 'publish', 'PROCESSING', 'checkpoint', ?, ?)
                    """,
                    (run_id, channel, now, now),
                )
                conn.execute(
                    """
                    INSERT INTO artifacts(
                        run_id, kind, local_path, remote_provider, remote_id,
                        remote_name, size_bytes, sha256, verified_at, created_at, story_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, kind, local_path) DO UPDATE SET
                        remote_provider = excluded.remote_provider,
                        remote_id = excluded.remote_id,
                        remote_name = excluded.remote_name,
                        size_bytes = excluded.size_bytes,
                        sha256 = excluded.sha256,
                        verified_at = excluded.verified_at,
                        story_key = excluded.story_key
                    """,
                    (
                        run_id,
                        kind,
                        local_path,
                        remote_provider,
                        remote_id,
                        remote_name,
                        size_bytes,
                        sha256,
                        now if verified else None,
                        now,
                        story_key,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def record_youtube_upload_id(
        self,
        story_id: str,
        run_id: str,
        video_id: str,
        *,
        owner: str | None = None,
    ) -> None:
        """Persist a returned YouTube ID before any later verification can fail."""
        remote_id = str(video_id or "").strip()
        if not remote_id:
            raise ValueError("YouTube no devolvió un video_id persistible")
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            story = conn.execute(
                "SELECT run_id FROM stories WHERE story_id = ?", (story_id,)
            ).fetchone()
            if not story or story["run_id"] != run_id:
                conn.rollback()
                raise RuntimeError("El video_id no pertenece al run activo")
            if owner is not None and not self._holds_lease(conn, story_id, run_id, owner):
                conn.rollback()
                raise RuntimeError("Se perdió ownership antes de persistir video_id")
            existing = conn.execute(
                "SELECT youtube_video_id FROM stories WHERE story_id = ?",
                (story_id,),
            ).fetchone()[0]
            if existing and existing != remote_id:
                conn.rollback()
                raise RuntimeError("La historia ya conserva otro video_id de YouTube")
            conn.execute(
                "UPDATE stories SET youtube_video_id = ? WHERE story_id = ?",
                (remote_id, story_id),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO artifacts(
                    run_id, kind, remote_provider, remote_id, verified_at, created_at
                ) VALUES (?, 'youtube_video', 'youtube', ?, NULL, ?)
                """,
                (run_id, remote_id, _utc_now()),
            )
            conn.commit()

    def record_drive_upload_id(
        self,
        story_id: str,
        run_id: str,
        file_id: str,
        *,
        owner: str | None = None,
    ) -> None:
        """Persist a Drive ID immediately while fencing the active worker."""
        remote_id = str(file_id or "").strip()
        if not remote_id:
            raise ValueError("Drive no devolvió un file_id persistible")
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            story = conn.execute(
                "SELECT run_id, drive_file_id FROM stories WHERE story_id = ?",
                (story_id,),
            ).fetchone()
            if not story or story["run_id"] != run_id:
                conn.rollback()
                raise RuntimeError("El file_id de Drive no pertenece al run activo")
            if owner is not None and not self._holds_lease(conn, story_id, run_id, owner):
                conn.rollback()
                raise RuntimeError("Se perdió ownership antes de persistir file_id")
            if story["drive_file_id"] and story["drive_file_id"] != remote_id:
                conn.rollback()
                raise RuntimeError("La historia ya conserva otro file_id de Drive")
            conn.execute(
                "UPDATE stories SET drive_file_id = ? WHERE story_id = ? AND run_id = ?",
                (remote_id, story_id, run_id),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO artifacts(
                    run_id, kind, remote_provider, remote_id, verified_at, created_at
                ) VALUES (?, 'drive_video_pending', 'drive', ?, NULL, ?)
                """,
                (run_id, remote_id, _utc_now()),
            )
            conn.commit()

    def record_fingerprint(
        self,
        run_id: str,
        story_id: str,
        channel: str | CanonicalChannel,
        kind: str,
        payload: str | bytes,
        *,
        normalized_text: str | None = None,
        simhash: int | None = None,
    ) -> bool:
        raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        digest = hashlib.sha256(raw).hexdigest()
        if simhash is None and isinstance(payload, str):
            simhash = compute_simhash_64(payload)
        elif simhash is None and normalized_text:
            simhash = compute_simhash_64(normalized_text)
        return self.record_fingerprint_digest(
            run_id,
            story_id,
            channel,
            kind,
            digest,
            normalized_text=normalized_text,
            simhash=simhash,
        )

    def record_fingerprint_digest(
        self,
        run_id: str,
        story_id: str,
        channel: str | CanonicalChannel,
        kind: str,
        digest: str,
        *,
        normalized_text: str | None = None,
        simhash: int | None = None,
    ) -> bool:
        if not re_full_sha256(digest):
            raise ValueError("Fingerprint SHA-256 inválido")
        channel_key = canonical_channel(channel).value
        calc_simhash = simhash
        if calc_simhash is None and normalized_text:
            calc_simhash = compute_simhash_64(normalized_text)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            now = _utc_now()
            conn.execute(
                """
                INSERT OR IGNORE INTO runs(
                    run_id, channel, story_id, mode, status, owner, started_at, heartbeat_at
                ) VALUES (?, ?, ?, 'publish', 'PROCESSING', 'fingerprint', ?, ?)
                """,
                (run_id, channel_key, story_id, now, now),
            )
            try:
                conn.execute(
                    """
                    INSERT INTO content_fingerprints(
                        run_id, story_id, channel, kind, sha256,
                        normalized_text, created_at, simhash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        story_id,
                        channel_key,
                        kind,
                        digest,
                        normalized_text,
                        now,
                        to_signed_64(calc_simhash),
                    ),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                conn.rollback()
                return False

    def has_near_duplicate(
        self,
        channel: str | CanonicalChannel,
        simhash_or_text: int | str,
        *,
        max_distance: int = 3,
    ) -> bool:
        channel_key = canonical_channel(channel).value
        target_simhash = (
            simhash_or_text
            if isinstance(simhash_or_text, int)
            else compute_simhash_64(simhash_or_text)
        )
        if target_simhash == 0:
            return False
        with connect(self.db_path, read_only=True) as conn:
            rows = conn.execute(
                """
                SELECT simhash
                FROM content_fingerprints
                WHERE channel = ? AND simhash IS NOT NULL
                """,
                (channel_key,),
            ).fetchall()
        for row in rows:
            existing = row["simhash"]
            if existing is not None and simhash_hamming_distance(target_simhash, existing) <= max_distance:
                return True
        return False

    def recent_published_texts(
        self,
        channel: str | CanonicalChannel,
        *,
        limit: int = 50,
    ) -> list[str]:
        channel_key = canonical_channel(channel).value
        with connect(self.db_path, read_only=True) as conn:
            return [
                str(row["normalized_text"])
                for row in conn.execute(
                    """
                    SELECT f.normalized_text
                    FROM content_fingerprints f
                    JOIN runs r ON r.run_id = f.run_id
                    WHERE f.channel = ? AND f.normalized_text IS NOT NULL
                      AND r.status = ?
                    ORDER BY f.created_at DESC LIMIT ?
                    """,
                    (channel_key, JobStatus.PUBLISHED.value, limit),
                )
            ]

    def has_published_fingerprint(
        self,
        channel: str | CanonicalChannel,
        kind: str,
        payload: str | bytes,
    ) -> bool:
        raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        digest = hashlib.sha256(raw).hexdigest()
        return self.has_published_digest(channel, kind, digest)

    def has_published_digest(
        self,
        channel: str | CanonicalChannel,
        kind: str,
        digest: str,
    ) -> bool:
        if not re_full_sha256(digest):
            raise ValueError("Fingerprint SHA-256 inválido")
        channel_key = canonical_channel(channel).value
        with connect(self.db_path, read_only=True) as conn:
            return (
                conn.execute(
                    """
                    SELECT 1
                    FROM content_fingerprints f
                    JOIN runs r ON r.run_id = f.run_id
                    WHERE f.channel = ? AND f.kind = ? AND f.sha256 = ?
                      AND r.status = ?
                    """,
                    (channel_key, kind, digest, JobStatus.PUBLISHED.value),
                ).fetchone()
                is not None
            )

    def record_provider_attempt(
        self,
        run_id: str,
        provider: str,
        operation: str,
        *,
        outcome: str,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                attempt_no = int(
                    conn.execute(
                        """
                        SELECT COALESCE(MAX(attempt_no), 0) + 1
                        FROM provider_attempts
                        WHERE run_id = ? AND provider = ? AND operation = ?
                        """,
                        (run_id, provider, operation),
                    ).fetchone()[0]
                )
                now = _utc_now()
                conn.execute(
                    """
                    INSERT INTO provider_attempts(
                        run_id, provider, operation, attempt_no, started_at,
                        finished_at, outcome, error_code, error_detail
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        provider,
                        operation,
                        attempt_no,
                        now,
                        now,
                        outcome,
                        error_code,
                        error_detail,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def finish_run(
        self,
        run_id: str,
        status: str | JobStatus,
        *,
        owner: str | None = None,
    ) -> bool:
        value = status.value if isinstance(status, JobStatus) else str(status)
        if value not in ALL_STATUSES:
            raise ValueError(f"Estado operativo inválido: {value}")
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if owner is not None and not (
                conn.execute(
                    "SELECT 1 FROM leases WHERE run_id = ? AND owner = ? AND expires_at > ?",
                    (run_id, owner, int(time.time())),
                ).fetchone()
                or conn.execute(
                    "SELECT 1 FROM lane_leases WHERE run_id = ? AND owner = ? AND expires_at > ?",
                    (run_id, owner, int(time.time())),
                ).fetchone()
            ):
                conn.rollback()
                return False
            cursor = conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ? AND status != ?",
                (value, _utc_now(), run_id, JobStatus.PUBLISHED.value),
            )
            if not cursor.rowcount:
                conn.rollback()
                return False
            conn.execute("DELETE FROM leases WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM lane_leases WHERE run_id = ?", (run_id,))
            conn.commit()
            return True

    def mark_published(
        self,
        story_id: str,
        run_id: str,
        proof: PublicationProof,
        *,
        provider: str,
        owner: str | None = None,
    ) -> None:
        proof.validate()
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            story = conn.execute(
                "SELECT channel, run_id FROM stories WHERE story_id = ?", (story_id,)
            ).fetchone()
            if not story or story["run_id"] != run_id:
                conn.rollback()
                raise RuntimeError("La publicación no pertenece al run activo")
            if owner is not None and not self._holds_lease(conn, story_id, run_id, owner):
                conn.rollback()
                raise RuntimeError("Se perdió ownership antes del commit de publicación")
            if canonical_channel(story["channel"]) != proof.channel:
                conn.rollback()
                raise RuntimeError("El canal confirmado no coincide con el trabajo")
            linked = conn.execute(
                "SELECT story_id, position FROM run_stories WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            if not linked:
                conn.execute(
                    "INSERT INTO run_stories(run_id, story_id, position) VALUES (?, ?, 0)",
                    (run_id, story_id),
                )
                linked = [{"story_id": story_id, "position": 0}]
            if (
                len(linked) != 1
                or linked[0]["story_id"] != story_id
                or linked[0]["position"] != 0
            ):
                conn.rollback()
                raise RuntimeError(
                    "La publicación exige run_stories con una única historia principal"
                )
            conn.execute(
                """
                INSERT INTO publications(
                    run_id, story_id, provider, video_id, url, channel,
                    visibility, title, description, thumbnail_confirmed, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    run_id,
                    story_id,
                    provider,
                    proof.video_id,
                    proof.url,
                    proof.channel.value,
                    proof.visibility,
                    proof.title,
                    proof.description,
                    _utc_now(),
                ),
            )
            conn.execute(
                """
                UPDATE stories
                SET status = ?, youtube_video_id = ?, youtube_url = ?,
                    publication_visibility = ?, publication_channel = ?,
                    run_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ?
                """,
                (
                    JobStatus.PUBLISHED.value,
                    proof.video_id,
                    proof.url,
                    proof.visibility,
                    proof.channel.value,
                    run_id,
                    story_id,
                ),
            )
            conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ?",
                (JobStatus.PUBLISHED.value, _utc_now(), run_id),
            )
            conn.execute("DELETE FROM leases WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM lane_leases WHERE run_id = ?", (run_id,))
            conn.commit()

    def pause(self, channel: str | CanonicalChannel, reason: str | None = None) -> None:
        self._set_paused(channel, True, reason)

    def resume(self, channel: str | CanonicalChannel) -> None:
        self._set_paused(channel, False, None)

    def _set_paused(
        self,
        channel: str | CanonicalChannel,
        paused: bool,
        reason: str | None,
    ) -> None:
        channel_key = canonical_channel(channel).value
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO channel_controls(channel, paused, reason, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(channel) DO UPDATE SET
                        paused = excluded.paused,
                        reason = excluded.reason,
                        updated_at = excluded.updated_at
                    """,
                    (channel_key, int(paused), reason, _utc_now()),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def queue_summary(self) -> dict[str, Any]:
        with connect(self.db_path, read_only=True) as conn:
            counts = {
                row["status"]: int(row["count"])
                for row in conn.execute(
                    "SELECT status, COUNT(*) AS count FROM stories GROUP BY status"
                )
            }
            leases = [dict(row) for row in conn.execute("SELECT * FROM leases")]
            controls = [
                dict(row)
                for row in conn.execute(
                    "SELECT channel, paused, reason, updated_at FROM channel_controls"
                )
            ]
        return {"counts": counts, "leases": leases, "controls": controls}

    def record_scene_assets(
        self,
        run_id: str,
        story_id: str,
        scene_assets: Sequence[dict[str, Any]],
    ) -> int:
        """Persist structured scene/shot asset lineage for a story run."""
        if not scene_assets:
            return 0
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for asset in scene_assets:
                    conn.execute(
                        """
                        INSERT INTO story_scene_assets(
                            run_id, story_id, scene_index, shot_index,
                            asset_source, source_url_or_path, framing_type,
                            prompt_used, dhash, duration_sec
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            story_id,
                            int(asset.get("scene_index", 0)),
                            int(asset.get("shot_index", 0)),
                            str(asset.get("asset_source", "local_bank")),
                            str(asset.get("source_url_or_path", asset.get("image_path", ""))),
                            str(asset.get("framing_type", "WIDE_ESTABLISHING")),
                            asset.get("prompt_used") or asset.get("prompt"),
                            asset.get("dhash"),
                            float(asset.get("duration_sec", 0.0)),
                        ),
                    )
                conn.commit()
                return len(scene_assets)
            except Exception:
                conn.rollback()
                raise

    def get_scene_assets(self, story_id: str) -> list[dict[str, Any]]:
        """Retrieve all recorded scene assets for a story ordered by scene and shot."""
        with connect(self.db_path, read_only=True) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM story_scene_assets
                    WHERE story_id = ?
                    ORDER BY scene_index, shot_index, scene_asset_id
                    """,
                    (story_id,),
                )
            ]

    def record_production_metrics(
        self,
        run_id: str,
        story_id: str,
        audio_duration_sec: float,
        render_time_sec: float,
        tts_time_sec: float | None = None,
        video_size_bytes: int = 0,
        integrated_lufs: float | None = None,
        qa_audit_passed: bool = True,
    ) -> bool:
        """Record pipeline execution telemetry for performance analysis."""
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO production_metrics(
                        run_id, story_id, audio_duration_sec, render_time_sec,
                        tts_time_sec, video_size_bytes, integrated_lufs,
                        qa_audit_passed, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        audio_duration_sec = excluded.audio_duration_sec,
                        render_time_sec = excluded.render_time_sec,
                        tts_time_sec = excluded.tts_time_sec,
                        video_size_bytes = excluded.video_size_bytes,
                        integrated_lufs = excluded.integrated_lufs,
                        qa_audit_passed = excluded.qa_audit_passed
                    """,
                    (
                        run_id,
                        story_id,
                        float(audio_duration_sec),
                        float(render_time_sec),
                        float(tts_time_sec) if tts_time_sec is not None else None,
                        int(video_size_bytes),
                        float(integrated_lufs) if integrated_lufs is not None else None,
                        1 if qa_audit_passed else 0,
                        _utc_now(),
                    ),
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def get_production_metrics(self, run_id: str) -> dict[str, Any] | None:
        """Retrieve production telemetry for a specific run."""
        with connect(self.db_path, read_only=True) as conn:
            row = conn.execute(
                "SELECT * FROM production_metrics WHERE run_id = ?", (run_id,)
            ).fetchone()
            return dict(row) if row else None

    def record_analytics_snapshot(
        self,
        video_id: str,
        story_id: str,
        channel: str | CanonicalChannel,
        view_count: int = 0,
        like_count: int = 0,
        comment_count: int = 0,
        avg_view_duration_sec: float | None = None,
        retention_rate_pct: float | None = None,
        snapshot_interval: str = "24h",
        recorded_at: str | None = None,
    ) -> bool:
        """Record a point-in-time YouTube engagement snapshot."""
        channel_key = canonical_channel(channel).value
        ts = recorded_at or _utc_now()
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO video_analytics_snapshots(
                        video_id, story_id, channel, view_count, like_count,
                        comment_count, avg_view_duration_sec, retention_rate_pct,
                        snapshot_interval, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        video_id,
                        story_id,
                        channel_key,
                        int(view_count),
                        int(like_count),
                        int(comment_count),
                        float(avg_view_duration_sec) if avg_view_duration_sec is not None else None,
                        float(retention_rate_pct) if retention_rate_pct is not None else None,
                        snapshot_interval,
                        ts,
                    ),
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def get_analytics_snapshots(self, story_id: str) -> list[dict[str, Any]]:
        """Retrieve all historical analytics snapshots for a story."""
        with connect(self.db_path, read_only=True) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM video_analytics_snapshots
                    WHERE story_id = ?
                    ORDER BY recorded_at ASC, snapshot_id ASC
                    """,
                    (story_id,),
                )
            ]

    # ------------------------------------------------------------------
    # Observability pipe (system_events, migration 004)
    # ------------------------------------------------------------------

    def record_system_event(
        self,
        event_type: str,
        *,
        level: str = "INFO",
        run_id: str | None = None,
        story_id: str | None = None,
        channel: str | None = None,
        component: str | None = None,
        stage: str | None = None,
        error_code: str | None = None,
        message: str | None = None,
        details: dict[str, Any] | Mapping[str, Any] | None = None,
    ) -> int:
        """Persist one observability event and return its row id."""
        allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized_level = str(level).upper()
        if normalized_level not in allowed_levels:
            raise ValueError(f"Nivel de evento inválido: {level}")
        payload = json.dumps(
            dict(details) if details else {},
            ensure_ascii=False,
            default=str,
        )
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO system_events(
                        ts, level, event_type, run_id, story_id, channel,
                        component, stage, error_code, message, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _utc_now(),
                        normalized_level,
                        str(event_type),
                        run_id,
                        story_id,
                        channel,
                        component,
                        stage,
                        error_code,
                        message,
                        payload,
                    ),
                )
                conn.commit()
                return int(cursor.lastrowid)
            except Exception:
                conn.rollback()
                raise

    def query_system_events(
        self,
        *,
        level: str | None = None,
        event_type: str | None = None,
        run_id: str | None = None,
        component: str | None = None,
        since_ts: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Query observability events, newest first (read-only)."""
        clauses: list[str] = []
        params: list[Any] = []
        if level:
            clauses.append("level = ?")
            params.append(str(level).upper())
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if component:
            clauses.append("component = ?")
            params.append(component)
        if since_ts:
            clauses.append("ts >= ?")
            params.append(since_ts)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, int(limit)))
        with connect(self.db_path, read_only=True) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT * FROM system_events {where}
                    ORDER BY event_id DESC LIMIT ?
                    """,
                    tuple(params),
                )
            ]

    def prune_system_events(
        self,
        *,
        retention_days: int = 30,
        max_rows: int = 50_000,
    ) -> int:
        """Delete events older than retention and cap table size; returns deleted count."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max(0, int(retention_days)))
        ).isoformat(timespec="seconds")
        deleted = 0
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    "DELETE FROM system_events WHERE ts < ?", (cutoff,)
                )
                deleted += int(cursor.rowcount)
                excess = conn.execute(
                    "SELECT COUNT(*) FROM system_events"
                ).fetchone()[0] - max(0, int(max_rows))
                if excess > 0:
                    cursor = conn.execute(
                        """
                        DELETE FROM system_events WHERE event_id IN (
                            SELECT event_id FROM system_events
                            ORDER BY event_id ASC LIMIT ?
                        )
                        """,
                        (int(excess),),
                    )
                    deleted += int(cursor.rowcount)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return deleted

    def recent_failed_runs(self, *, limit: int = 10) -> list[dict[str, Any]]:
        """Latest runs that did not finish cleanly, newest first."""
        with connect(self.db_path, read_only=True) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT run_id, channel, story_id, status, started_at,
                           finished_at, error_code, error_detail
                    FROM runs
                    WHERE status NOT IN ('PUBLISHED', 'COMPLETED')
                    ORDER BY started_at DESC LIMIT ?
                    """,
                    (max(1, int(limit)),),
                )
            ]

    def get_run_artifact(self, run_id: str, kind: str) -> dict[str, Any] | None:
        """Return one recorded artifact of a run by kind (e.g. 'video')."""
        with connect(self.db_path, read_only=True) as conn:
            row = conn.execute(
                """
                SELECT * FROM artifacts WHERE run_id = ? AND kind = ?
                ORDER BY artifact_id DESC LIMIT 1
                """,
                (run_id, kind),
            ).fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------
    # Production lanes (scheduler_lane_state + lane_leases)
    # ------------------------------------------------------------------

    def ensure_lane_rows(self, lane_ids: Sequence[str], *, now: int | None = None) -> None:
        """Seed scheduler state rows for the configured lanes (runtime, not SQL)."""
        stamp = _utc_now()
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            for lane_id in lane_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO scheduler_lane_state("
                    "lane_id, next_due_at, consecutive_empty, updated_at"
                    ") VALUES (?, ?, 0, ?)",
                    (lane_id, current, stamp),
                )
            conn.commit()

    def due_lanes(self, *, now: int | None = None) -> list[dict[str, Any]]:
        """Lanes whose cadence ceiling expired, most-overdue first."""
        current = int(time.time() if now is None else now)
        with connect(self.db_path, read_only=True) as conn:
            rows = conn.execute(
                "SELECT * FROM scheduler_lane_state "
                "WHERE paused = 0 AND next_due_at <= ? "
                "ORDER BY next_due_at ASC, lane_id ASC",
                (current,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_lane_fired(
        self,
        lane_id: str,
        *,
        fired_at: int,
        next_due_at: int,
        run_id: str | None = None,
        empty: bool = False,
    ) -> None:
        """Persist the post-fire cadence ceiling (never accumulates missed turns)."""
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if empty:
                conn.execute(
                    "UPDATE scheduler_lane_state SET next_due_at = ?, "
                    "consecutive_empty = consecutive_empty + 1, updated_at = ? "
                    "WHERE lane_id = ?",
                    (next_due_at, _utc_now(), lane_id),
                )
            else:
                conn.execute(
                    "UPDATE scheduler_lane_state SET next_due_at = ?, last_started_at = ?, "
                    "last_run_id = ?, consecutive_empty = 0, updated_at = ? WHERE lane_id = ?",
                    (next_due_at, fired_at, run_id, _utc_now(), lane_id),
                )
            conn.commit()

    def set_lane_paused(self, lane_id: str, paused: bool, reason: str | None = None) -> None:
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE scheduler_lane_state SET paused = ?, pause_reason = ?, updated_at = ? "
                "WHERE lane_id = ?",
                (1 if paused else 0, reason, _utc_now(), lane_id),
            )
            conn.commit()

    def get_lane_state(self, lane_id: str) -> dict[str, Any] | None:
        with connect(self.db_path, read_only=True) as conn:
            row = conn.execute(
                "SELECT * FROM scheduler_lane_state WHERE lane_id = ?", (lane_id,)
            ).fetchone()
        return dict(row) if row else None

    def claim_for_lane(
        self,
        lane_id: str,
        channel: str | CanonicalChannel,
        owner: str,
        *,
        lease_seconds: int = 900,
        mode: str = "publish",
        now: int | None = None,
    ) -> dict[str, Any] | None:
        """Claim one story for a lane using the parallel ``lane_leases`` table.

        Unlike ``claim`` this does NOT serialize production by channel: two lanes
        of the same channel may hold leases simultaneously (short + longform).
        Stories without a lane adopt whichever compatible lane claims them.
        """
        lane_key = str(lane_id or "").strip()
        if not lane_key:
            raise ValueError("lane_id es obligatorio para el claim por carril")
        channel_key = canonical_channel(channel).value
        if not owner.strip():
            raise ValueError("El propietario del lease es obligatorio")
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            paused = conn.execute(
                "SELECT paused FROM channel_controls WHERE channel = ?", (channel_key,)
            ).fetchone()
            if paused and paused["paused"]:
                conn.rollback()
                return None
            self._recover_expired_lanes_locked(conn, current)
            if conn.execute(
                "SELECT 1 FROM lane_leases WHERE lane_id = ?", (lane_key,)
            ).fetchone() or conn.execute(
                "SELECT 1 FROM leases WHERE channel = ?", (channel_key,)
            ).fetchone():
                conn.rollback()
                return None
            row = conn.execute(
                """
                SELECT * FROM stories
                WHERE channel = ?
                  AND status IN (?, ?)
                  AND (lane_id IS NULL OR lane_id = ?)
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY CASE WHEN lane_id = ? THEN 0 ELSE 1 END, created_at, story_id
                LIMIT 1
                """,
                (
                    channel_key,
                    JobStatus.PENDING.value,
                    JobStatus.RETRYABLE_FAILED.value,
                    lane_key,
                    current,
                    lane_key,
                ),
            ).fetchone()
            if not row:
                conn.rollback()
                return None
            run_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO runs(
                    run_id, channel, story_id, mode, status, owner,
                    started_at, heartbeat_at, lane_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    channel_key,
                    row["story_id"],
                    mode,
                    JobStatus.PROCESSING.value,
                    owner,
                    _utc_now(),
                    _utc_now(),
                    lane_key,
                ),
            )
            conn.execute(
                """
                INSERT INTO lane_leases(
                    job_id, lane_id, channel, owner, run_id, acquired_at,
                    heartbeat_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    lane_id = excluded.lane_id,
                    channel = excluded.channel,
                    owner = excluded.owner,
                    run_id = excluded.run_id,
                    acquired_at = excluded.acquired_at,
                    heartbeat_at = excluded.heartbeat_at,
                    expires_at = excluded.expires_at
                """,
                (
                    row["story_id"],
                    lane_key,
                    channel_key,
                    owner,
                    run_id,
                    current,
                    current,
                    current + lease_seconds,
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO run_stories(run_id, story_id, position) VALUES (?, ?, 0)",
                (run_id, row["story_id"]),
            )
            conn.execute(
                """
                UPDATE stories
                SET status = ?, run_id = ?, lane_id = ?, error_msg = NULL,
                    failure_code = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ?
                """,
                (JobStatus.PROCESSING.value, run_id, lane_key, row["story_id"]),
            )
            conn.commit()
            result = dict(row)
            result.update(status=JobStatus.PROCESSING.value, run_id=run_id)
            return result

    def claim_resumable(
        self,
        lane_id: str,
        channel: str | CanonicalChannel,
        owner: str,
        *,
        lease_seconds: int = 900,
        mode: str = "resume-publish",
        now: int | None = None,
    ) -> dict[str, Any] | None:
        """Re-claim a stuck story (RENDERED/DRIVE_BACKED_UP/UPLOAD_UNCONFIRMED).

        Only stories whose rendered video still exists on disk are returned so the
        pipeline can resume from delivery instead of re-rendering from scratch.
        """
        from src.core.checkpoints import resumable_video_for_story

        lane_key = str(lane_id or "").strip()
        if not lane_key:
            raise ValueError("lane_id es obligatorio para el claim de reanudación")
        channel_key = canonical_channel(channel).value
        if not owner.strip():
            raise ValueError("El propietario del lease es obligatorio")
        current = int(time.time() if now is None else now)
        resumable_states = (
            JobStatus.RENDERED.value,
            JobStatus.DRIVE_BACKED_UP.value,
            JobStatus.UPLOAD_UNCONFIRMED.value,
        )
        placeholders = ",".join("?" for _ in resumable_states)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            paused = conn.execute(
                "SELECT paused FROM channel_controls WHERE channel = ?", (channel_key,)
            ).fetchone()
            if paused and paused["paused"]:
                conn.rollback()
                return None
            self._recover_expired_lanes_locked(conn, current)
            if conn.execute(
                "SELECT 1 FROM lane_leases WHERE lane_id = ?", (lane_key,)
            ).fetchone() or conn.execute(
                "SELECT 1 FROM leases WHERE channel = ?", (channel_key,)
            ).fetchone():
                conn.rollback()
                return None
            rows = conn.execute(
                f"""
                SELECT s.*, r.run_id AS candidate_run_id FROM stories s
                JOIN runs r ON r.story_id = s.story_id AND r.lane_id = ?
                WHERE s.channel = ? AND s.status IN ({placeholders})
                  AND (s.next_attempt_at IS NULL OR s.next_attempt_at <= ?)
                ORDER BY r.started_at DESC
                LIMIT 5
                """,
                (lane_key, channel_key, *resumable_states, current),
            ).fetchall()
            chosen = None
            for row in rows:
                video = resumable_video_for_story(str(row["candidate_run_id"]), db_path=self.db_path)
                if video is not None:
                    chosen = (row, video)
                    break
            if chosen is None:
                conn.rollback()
                return None
            row, video_path = chosen
            run_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO runs(
                    run_id, channel, story_id, mode, status, owner,
                    started_at, heartbeat_at, lane_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    channel_key,
                    row["story_id"],
                    mode,
                    JobStatus.PROCESSING.value,
                    owner,
                    _utc_now(),
                    _utc_now(),
                    lane_key,
                ),
            )
            conn.execute(
                """
                INSERT INTO lane_leases(
                    job_id, lane_id, channel, owner, run_id, acquired_at,
                    heartbeat_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    lane_id = excluded.lane_id,
                    channel = excluded.channel,
                    owner = excluded.owner,
                    run_id = excluded.run_id,
                    acquired_at = excluded.acquired_at,
                    heartbeat_at = excluded.heartbeat_at,
                    expires_at = excluded.expires_at
                """,
                (
                    row["story_id"],
                    lane_key,
                    channel_key,
                    owner,
                    run_id,
                    current,
                    current,
                    current + lease_seconds,
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO run_stories(run_id, story_id, position) VALUES (?, ?, 0)",
                (run_id, row["story_id"]),
            )
            conn.execute(
                """
                UPDATE stories
                SET status = ?, run_id = ?, lane_id = ?, error_msg = NULL,
                    failure_code = 'resumable_delivery', updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ?
                """,
                (JobStatus.PROCESSING.value, run_id, lane_key, row["story_id"]),
            )
            conn.commit()
            result = dict(row)
            result.update(status=JobStatus.PROCESSING.value, run_id=run_id)
            result["resumable_video"] = str(video_path)
            result["previous_run_id"] = str(row["candidate_run_id"])
            return result

    def _recover_expired_lanes_locked(self, conn: sqlite3.Connection, now: int) -> int:
        """Expire lane leases back to RETRYABLE_FAILED (mirrors legacy recovery)."""
        expired = conn.execute(
            "SELECT job_id, lane_id, run_id FROM lane_leases WHERE expires_at <= ?", (now,)
        ).fetchall()
        for lease in expired:
            conn.execute(
                """
                UPDATE stories
                SET status = ?, run_id = NULL, failure_code = 'lease_expired',
                    error_msg = 'Lease de carril expirado; trabajo recuperado de forma segura',
                    updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ? AND run_id = ? AND status = ?
                """,
                (
                    JobStatus.RETRYABLE_FAILED.value,
                    lease["job_id"],
                    lease["run_id"],
                    JobStatus.PROCESSING.value,
                ),
            )
            conn.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, error_code = 'lease_expired'
                WHERE run_id = ?
                """,
                (JobStatus.RETRYABLE_FAILED.value, _utc_now(), lease["run_id"]),
            )
        conn.execute("DELETE FROM lane_leases WHERE expires_at <= ?", (now,))
        return len(expired)

    def recover_expired_lane_leases(self, *, now: int | None = None) -> int:
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = self._recover_expired_lanes_locked(conn, current)
            conn.commit()
            return count

    def heartbeat_lane_lease(
        self,
        run_id: str,
        owner: str,
        *,
        lease_seconds: int = 900,
        now: int | None = None,
    ) -> bool:
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                UPDATE lane_leases SET heartbeat_at = ?, expires_at = ?
                WHERE run_id = ? AND owner = ? AND expires_at > ?
                """,
                (current, current + lease_seconds, run_id, owner, current),
            )
            if cursor.rowcount:
                conn.execute(
                    "UPDATE runs SET heartbeat_at = ? WHERE run_id = ? AND owner = ?",
                    (_utc_now(), run_id, owner),
                )
            conn.commit()
            return bool(cursor.rowcount)

    def finish_lane_run(self, run_id: str, status: str | JobStatus, *, owner: str | None = None) -> bool:
        value = status.value if isinstance(status, JobStatus) else str(status)
        if value not in ALL_STATUSES:
            raise ValueError(f"Estado operativo inválido: {value}")
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if owner is not None and not conn.execute(
                "SELECT 1 FROM lane_leases WHERE run_id = ? AND owner = ? AND expires_at > ?",
                (run_id, owner, int(time.time())),
            ).fetchone():
                conn.rollback()
                return False
            cursor = conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ? AND status != ?",
                (value, _utc_now(), run_id, JobStatus.PUBLISHED.value),
            )
            if not cursor.rowcount:
                conn.rollback()
                return False
            conn.execute("DELETE FROM lane_leases WHERE run_id = ?", (run_id,))
            conn.commit()
            return True



def touch_daemon_liveness(db_path, *, now=None):
    """Record the daemon liveness heartbeat consumed by healthcheck.py (AUD-08)."""
    stamp = int(now) if now is not None else int(time.time())
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO daemon_liveness(id, heartbeat_at) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET heartbeat_at = excluded.heartbeat_at",
                (stamp,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def read_daemon_heartbeat(db_path):
    """Return the last daemon liveness epoch, or None when absent/never set."""
    with connect(db_path, read_only=True) as conn:
        row = conn.execute(
            "SELECT heartbeat_at FROM daemon_liveness WHERE id = 1"
        ).fetchone()
    return int(row[0]) if row and row[0] else None
