"""SQLite repository with versioned migrations, leases and publication proofs."""

from __future__ import annotations

import os

from src.core.domain import (
    ALL_STATUSES,
    CanonicalChannel,
    JobStatus,
    PublicationProof,
    canonical_channel,
)
from src.core.repository.migrations import (
    BUSY_TIMEOUT_MS,
    EXPECTED_MIGRATION_VERSION,
    MIGRATION_001,
    MIGRATION_003,
    MIGRATION_004,
    MIGRATION_005,
    MIGRATION_009,
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
    AssetRejectionSummary,
    DaemonStoppageMetrics,
    QueueOperationsMixin,
    TokenBurnSummary,
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

    def __init__(self, db_path: str | os.PathLike[str] | None = None):
        if db_path is None:
            resolved_db = os.environ.get("DEFAULT_DB_PATH")
            if not resolved_db:
                from src.config import DEFAULT_DB_PATH

                resolved_db = str(DEFAULT_DB_PATH)
            db_path = resolved_db
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
    "EXPECTED_MIGRATION_VERSION",
    "TokenBurnSummary",
    "AssetRejectionSummary",
    "DaemonStoppageMetrics",
    "MIGRATION_001",
    "MIGRATION_003",
    "MIGRATION_004",
    "MIGRATION_005",
    "MIGRATION_009",
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
