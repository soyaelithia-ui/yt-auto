"""SQLite repository with versioned migrations, leases and publication proofs."""

from __future__ import annotations

import os
from typing import Any

from src.core.domain import (
    ALL_STATUSES,
    CanonicalChannel,
    JobStatus,
    PublicationProof,
    canonical_channel,
)
from src.core.repository.migrations import (
    BUSY_TIMEOUT_MS,
    MIGRATION_001,
    MIGRATION_003,
    MIGRATION_004,
    MIGRATION_005,
    MigrationReport,
    _add_story_columns,
    _apply_migration_005,
    _count_channels,
    _ensure_legacy_stories,
    _migration_checksum,
    _utc_now,
    backup_database,
    connect,
    migrate_database,
    validate_db_path,
    wal_checkpoint_passive,
)
from src.core.repository.leases import (
    LeaseOperationsMixin,
    read_daemon_heartbeat,
    touch_daemon_liveness,
)
from src.core.repository.queue import (
    QueueOperationsMixin,
    compute_simhash_64,
    hamming_distance_64,
    is_simhash_duplicate,
    re_full_sha256,
    simhash_hamming_distance,
    to_signed_64,
    to_unsigned_64,
)
from src.core.repository.catalog import (
    CHANNEL_CATEGORIES,
    CHANNEL_THEMES,
    SYNTHETIC_MONOCHROME_LOOP_IDS,
    LoopCatalogRepository,
    LoopRecord,
    audit_and_cleanup_catalog,
    compute_file_sha256,
    resolve_loop_file_path,
    sync_catalog_from_assets,
)


class QueueRepository(QueueOperationsMixin, LeaseOperationsMixin):
    """QueueRepository managing queue operations, leases, and database persistence."""

    def __init__(self, db_path: str | os.PathLike[str]):
        self.db_path = str(validate_db_path(db_path))

    def initialize(self) -> MigrationReport:
        return migrate_database(self.db_path)


__all__ = [
    "QueueRepository",
    "MigrationReport",
    "BUSY_TIMEOUT_MS",
    "validate_db_path",
    "connect",
    "wal_checkpoint_passive",
    "migrate_database",
    "backup_database",
    "touch_daemon_liveness",
    "read_daemon_heartbeat",
    "to_signed_64",
    "to_unsigned_64",
    "compute_simhash_64",
    "simhash_hamming_distance",
    "hamming_distance_64",
    "is_simhash_duplicate",
    "re_full_sha256",
    "ALL_STATUSES",
    "CanonicalChannel",
    "JobStatus",
    "PublicationProof",
    "canonical_channel",
    "MIGRATION_001",
    "MIGRATION_003",
    "MIGRATION_004",
    "MIGRATION_005",
    "_utc_now",
    "_migration_checksum",
    "_ensure_legacy_stories",
    "_add_story_columns",
    "_apply_migration_005",
    "_count_channels",
    "LoopRecord",
    "LoopCatalogRepository",
    "resolve_loop_file_path",
    "compute_file_sha256",
    "CHANNEL_CATEGORIES",
    "CHANNEL_THEMES",
    "SYNTHETIC_MONOCHROME_LOOP_IDS",
    "sync_catalog_from_assets",
    "audit_and_cleanup_catalog",
]
