# Specification: Database Backup and SQLite WAL Observability

## Capability Overview
The `database-backup-and-wal-observability` capability provides end-to-end telemetry for SQLite database resilience and storage health. It tracks automated and manual database backups (`backup_database()`, `manage.py backup`), records snapshot sizes and backup durations, monitors Write-Ahead Log (WAL) file growth and checkpoint status, verifies migration version parity, and surfaces `PRAGMA integrity_check` results.

## Requirements

### Requirement 1: Database Backup Lifecycle Tracking and Snapshot Metrics
The database backup operations in `src/core/repository/migrations.py` and `src/cli/handlers/backup.py` MUST record structured completion or failure events into `system_events`.

1. **Successful Backup (`database_backup_completed`)**:
   - Upon completing a snapshot via SQLite online backup API or file copy:
     - The backup handler MUST record a row in `system_events` with `event_type = 'database_backup_completed'` and `level = 'INFO'`.
     - `details_json` MUST contain the destination snapshot path, snapshot file size in bytes, and execution elapsed duration in milliseconds.
2. **Failed Backup (`database_backup_failed`)**:
   - If a backup operation fails due to filesystem exhaustion, permission errors, or database lock contention:
     - The backup handler MUST record a row in `system_events` with `event_type = 'database_backup_failed'` and `level = 'CRITICAL'`.
     - `details_json` MUST contain the error message, target path, and traceback.
3. The tube collector MUST track the age of the most recent successful database backup in hours, flagging backups older than 48 hours as `BACKUP_STALE_WARNING`.

#### Scenario: Successful database backup records snapshot metrics
- **Given** a call to `backup_database(db_path, backup_dir)`
- **When** the backup snapshot is written to `data/backups/db_backup_20260925.sqlite` with a size of 42.5 MiB in 180 ms
- **Then** an event `database_backup_completed` MUST be inserted into `system_events`
- **And** `details_json` MUST report `snapshot_size_bytes = 44564480` and `duration_ms` approximately 180.

#### Scenario: Backup failure generates critical incident
- **Given** a backup attempt where the target disk partition is read-only or full
- **When** the backup routine raises `OSError`
- **Then** an event `database_backup_failed` MUST be logged with `level = 'CRITICAL'`
- **And** the exception MUST be propagated or surfaced to the CLI.

---

### Requirement 2: SQLite Write-Ahead Log (WAL) Growth and Checkpoint Observability
The health checker and tube collector MUST inspect the SQLite database file and its companion WAL file (`.sqlite-wal`) to detect uncontrolled growth or stalled checkpoints.

1. The collector MUST measure the file size of the primary SQLite database (`.sqlite`) and its active WAL file (`.sqlite-wal`) in bytes and MiB.
2. If the WAL file size exceeds $50\text{ MiB}$ during passive operation, the collector MUST mark WAL status as `GROWTH_WARNING`.
3. If the WAL file size exceeds $200\text{ MiB}$, the collector MUST mark WAL status as `CRITICAL_WAL_BLOAT`.
4. The collector SHOULD run `PRAGMA wal_checkpoint(PASSIVE)` during telemetry collection to inspect the number of checkpointed frames without blocking active reader/writer connections.

#### Scenario: Inspecting healthy database and WAL file sizes
- **Given** an active database of size 12.0 MiB and a WAL file of 1.4 MiB
- **When** SQLite storage telemetry is sampled
- **Then** WAL status MUST report `OK`
- **And** `wal_size_mib` MUST report approximately 1.4.

#### Scenario: Detecting uncheckpointed WAL file bloat
- **Given** an active WAL file that has accumulated $68\text{ MiB}$ of uncheckpointed transaction frames
- **When** SQLite storage telemetry is sampled
- **Then** WAL status MUST report `GROWTH_WARNING`
- **And** the snapshot MUST include a diagnostic recommendation to execute `manage.py checkpoint` or `VACUUM`.

---

### Requirement 3: Migration Version Parity Verification
The system MUST verify that the applied schema migration version in SQLite matches the expected code migration version.

1. The collector MUST query the maximum version from `schema_migrations`.
2. The collector MUST compare the applied database version against `EXPECTED_MIGRATION_VERSION` defined in `src/core/repository/migrations.py` (version 9).
3. If the applied version is strictly less than the expected version, the collector MUST flag `migration_status = 'PENDING_MIGRATIONS'`.
4. If an unknown version higher than the code expectation is detected, the collector MUST flag `migration_status = 'FUTURE_VERSION_DRIFT'`.

#### Scenario: Verifying migration version parity at version 9
- **Given** an applied schema with migrations through version 9 recorded in `schema_migrations`
- **When** migration parity is checked
- **Then** `migration_parity` MUST be `True`
- **And** `current_version` MUST equal 9.

#### Scenario: Detecting unapplied migrations
- **Given** a database where the latest applied version is 8 while the code expects version 9
- **When** migration parity is checked
- **Then** `migration_parity` MUST be `False`
- **And** `migration_status` MUST report `'PENDING_MIGRATIONS'`.

---

### Requirement 4: Periodic Database Integrity Check Diagnostics
The health subsystem MUST support executing `PRAGMA integrity_check` to detect SQLite B-tree corruption or index misalignment.

1. Health checks MUST run `PRAGMA integrity_check(1)` or `PRAGMA quick_check(1)`.
2. If SQLite returns `"ok"`, the integrity status MUST report `HEALTHY`.
3. If SQLite returns any corruption message or error string, the integrity status MUST immediately report `CORRUPTED`, record a `CRITICAL` error in `system_events`, and notify the operator.

#### Scenario: Clean database integrity check (Happy Path)
- **Given** an uncorrupted SQLite database file
- **When** `PRAGMA quick_check(1)` is executed
- **Then** the check MUST return `"ok"`
- **And** database integrity status MUST be `HEALTHY`.
