# Tasks: Comprehensive Pipeline Telemetry & Observability Hub ('El Tubo')

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~1,850 - 2,350 lines (~1,150 lines source, ~950 lines tests, ~150 lines docs/mcp) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | 5 Chained PRs (discrete work units aligned with feature-branch-chain) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Database Migration 009 & Repository Persistence Layer | PR 1 | `.venv/bin/pytest tests/unit/test_token_burn_tracking.py -v` | SQLite in-memory / WAL database harness with test schema fixture | Revert `src/core/repository/migrations.py`, `src/core/repository/queue.py`, `src/core/repository/__init__.py` |
| 2 | Pipeline Interceptors & Operational Event Emission | PR 2 | `.venv/bin/pytest tests/unit/test_prompt_leak_telemetry.py tests/unit/test_cookie_lifecycle.py -v` | Pipeline interceptor mocks, simulated LLM/TTS callers, pre-TTS sanitizer harness | Revert `src/agents/base_agent.py`, `src/llm.py`, `src/audio/tts_router.py`, `src/sanitizer/security.py`, `src/sanitizer/tts.py`, `src/pipeline/stages/stage_13_publish.py`, `src/api_health.py` |
| 3 | Observability Hub & Collector Engine | PR 3 | `.venv/bin/pytest tests/unit/test_tube_telemetry.py -v` | In-process `/proc` resource mock, SQLite WAL query simulator, and MCP factory inspector | Revert `src/observability/quota.py`, `src/observability/mcp_health.py`, `src/observability/tube.py`, `src/observability/__init__.py` |
| 4 | Operational Surfaces: CLI Dashboard & MCP Protocol Interfaces | PR 4 | `.venv/bin/pytest tests/unit/test_mcp_tube.py -v && python scripts/verify_mcp_sync.py` | CLI ArgumentParser test runner, MCP JSON-RPC stdio transport harness, SSOT parity gate | Revert `src/cli/subparsers.py`, `src/cli/handlers/status.py`, `src/mcp/resources.py`, `src/mcp/tools/get_tube_status.py`, `src/mcp/tools/__init__.py`, `src/mcp/server.py`, `scripts/verify_mcp_sync.py`, `docs/MCP.md` |
| 5 | Automated Test Suite & Integrity Gate | PR 5 | `.venv/bin/pytest tests/unit/test_tube_telemetry.py tests/unit/test_token_burn_tracking.py tests/unit/test_mcp_tube.py tests/unit/test_prompt_leak_telemetry.py tests/unit/test_cookie_lifecycle.py -v && ./scripts/verify_integrity.sh` | End-to-end repository test suite and static integrity gate runner | Revert `tests/unit/test_tube_telemetry.py`, `tests/unit/test_token_burn_tracking.py`, `tests/unit/test_mcp_tube.py`, `tests/unit/test_prompt_leak_telemetry.py`, `tests/unit/test_cookie_lifecycle.py` |

---

## Phase 1: Database Migration & Repository Persistence

- [x] 1.1 **[RED]** Create new test module `tests/unit/test_token_burn_tracking.py` defining persistence and schema contracts:
  - `test_migration_009_schema_and_indices`: Assert `apply_migrations()` provisions `token_burn_events` table with 16 columns (`event_id`, `ts`, `run_id`, `story_id`, `channel`, `provider`, `model`, `prompt_tokens`, `completion_tokens`, `cached_tokens`, `reasoning_tokens`, `total_tokens`, `cost_usd`, `duration_seconds`, `status`, `created_at`) and 4 read indices (`idx_token_burn_ts`, `idx_token_burn_run`, `idx_token_burn_provider_model`, `idx_token_burn_channel`), plus performance index `idx_events_type_ts` on `system_events(event_type, ts)`.
  - `test_record_token_burn_persistence`: Validate `QueueRepository.record_token_burn()` writes LLM and TTS records with prompt, completion, cached, reasoning tokens, duration, and calculated USD cost.
  - `test_record_token_burn_fail_open_isolation`: Test that simulated SQLite write failures in `record_token_burn()` log debug messages without raising exceptions to callers.
  - `test_query_token_burn_summary_aggregations`: Assert `QueueRepository.query_token_burn_summary()` aggregates tokens and USD costs over selectable windows (e.g. 24h) grouped by provider and model.
  - `test_query_token_burn_summary_saturation_tally`: Assert records with `status = 'saturated'` increment the saturation counter without distorting total token metrics.
  - `test_prune_token_burn_events_retention`: Verify `QueueRepository.prune_token_burn_events(retention_days=30)` deletes stale records older than 30 days while preserving recent records, returning deleted row count.
  - Concrete edit target: `tests/unit/test_token_burn_tracking.py` (new test file).
  - Concrete inspection targets: `src/core/repository/migrations.py` (read-only), `src/core/repository/queue.py` (read-only).

- [x] 1.2 **[GREEN]** Implement SQLite Migration 009 in `src/core/repository/migrations.py`:
  - Define `MIGRATION_009` statement tuple creating:
    - `token_burn_events` table with `status IN ('success', 'failed', 'saturated')` CHECK constraint.
    - Read indices: `idx_token_burn_ts`, `idx_token_burn_run`, `idx_token_burn_provider_model`, `idx_token_burn_channel`.
    - Performance index: `idx_events_type_ts` on `system_events(event_type, ts)`.
  - Define `EXPECTED_MIGRATION_VERSION: Final[int] = 9`.
  - Implement `_apply_v9_token_burn_and_telemetry(conn: sqlite3.Connection, applied: list[int]) -> None`:
    - Compute migration checksum using `_migration_checksum("pipeline_telemetry_and_token_burn", MIGRATION_009)`.
    - Validate against existing checksum if version 9 was previously applied.
    - Execute statements, record version 9 into `schema_migrations`, and append 9 to `applied`.
  - Update `migrate_database()` to invoke `_apply_v9_token_burn_and_telemetry(conn, applied)`.
  - Update `src/core/repository/__init__.py` to re-export `MIGRATION_009` and `EXPECTED_MIGRATION_VERSION`.
  - Concrete edit targets: `src/core/repository/migrations.py`, `src/core/repository/__init__.py`.

- [x] 1.3 **[GREEN]** Implement Token Burn & Aggregation Methods in `src/core/repository/queue.py`:
  - Implement `record_token_burn(...)` in `QueueOperationsMixin`:
    - Accept `event_id`, `run_id`, `story_id`, `channel`, `provider`, `model`, `prompt_tokens`, `completion_tokens`, `cached_tokens`, `reasoning_tokens`, `total_tokens`, `cost_usd`, `duration_seconds`, `status`.
    - Generate UUID4 `event_id` and ISO-8601 UTC `ts` when omitted.
    - Execute `INSERT INTO token_burn_events (...)` wrapped in fail-open `try/except Exception: logger.debug(...)`.
  - Implement `query_token_burn_summary(...)` in `QueueOperationsMixin`:
    - Filter by `ts >= datetime.now(timezone.utc) - timedelta(hours=window_hours)` and optional `channel` / `provider`.
    - Aggregate `SUM(prompt_tokens)`, `SUM(completion_tokens)`, `SUM(cached_tokens)`, `SUM(reasoning_tokens)`, `SUM(total_tokens)`, `SUM(cost_usd)`, `COUNT(*)`, and `SUM(CASE WHEN status = 'saturated' THEN 1 ELSE 0 END)`.
    - Group by `provider` and `model` to return structured breakdown dictionaries.
  - Implement `prune_token_burn_events(...)` in `QueueOperationsMixin`:
    - Compute cutoff timestamp `datetime.now(timezone.utc) - timedelta(days=retention_days)`.
    - Execute `DELETE FROM token_burn_events WHERE ts < ?` and return `cursor.rowcount`.
  - Concrete edit targets: `src/core/repository/queue.py`.

- [x] 1.4 **[GREEN]** Implement Asset Rejections, Incident Queries & Channel Stoppages in `src/core/repository/queue.py`:
  - Implement `query_asset_rejection_counts(window_hours=24, channel=None)` in `QueueOperationsMixin`:
    - Query `system_events` for `event_type IN ('asset_rejection', 'review_rejection')` within the time window.
    - Aggregate automated QA rejections vs human Telegram review rejections (`review_jobs.status = 'REJECTED'`).
    - Classify counts across 6 standardized defect categories: `visual`, `audio`, `sync`, `luminance`, `pacing`, `editorial`.
    - Group by channel and extract top offending asset identifiers.
  - Implement `query_tube_incidents(window_hours=24, event_types=None, limit=50)` in `QueueOperationsMixin`:
    - Query `system_events` for recent operational incidents (`cookie_failure`, `cookie_warning`, `lease_recovered`, `audio_prompt_leak`, `quota_saturation`, `stage_error`, `youtube_quota_limit`, `database_backup_failed`).
    - Order chronologically descending (`ts DESC`) with limit.
    - Parse `details_json` and format structured incident dictionaries.
  - Implement `query_channel_stoppages()` in `QueueOperationsMixin`:
    - Query `channel_controls` where `paused = 1`, extracting `channel`, `reason`, `updated_at`.
    - Query active worker leases from `leases` and `lane_leases`, extracting `owner`, `run_id`, `lane_id` or `channel`, `acquired_at`, `expires_at`.
    - Identify expired/orphaned worker locks where `expires_at < current_epoch_seconds`.
  - Concrete edit targets: `src/core/repository/queue.py`.

- [x] 1.5 **[VERIFY]** Run Phase 1 persistence test suite:
  - Command: `.venv/bin/pytest tests/unit/test_token_burn_tracking.py -v`.
  - Assert 100% pass across all Migration 009 schema, persistence, summary query, and pruning assertions.

---

## Phase 2: Pipeline Interceptors & Event Emission

- [x] 2.1 **[RED]** Create new test modules for interceptors and event emissions:
  - Create `tests/unit/test_prompt_leak_telemetry.py`:
    - `test_pre_tts_taboo_phrase_interception`: Assert `validate_pre_tts_script()` intercepts taboo phrases, emits `audio_prompt_leak` event to `system_events`, and re-raises `PromptLeakError`.
    - `test_pre_tts_prompt_leak_pattern_interception`: Assert meta-cues ("como modelo de lenguaje", "aquí tienes tu guion") emit `audio_prompt_leak` with truncated snippet ($\le 120$ characters) and regex pattern name.
    - `test_prompt_leak_cluster_escalation`: Assert $>3$ prompt leaks for the same model/channel within 30 minutes triggers `send_operational_alert()`.
  - Create `tests/unit/test_cookie_lifecycle.py`:
    - `test_cookie_failure_event_emission`: Assert `SessionStatus.EXPIRED`, `SessionStatus.INCOMPLETE`, `SessionStatus.INVALID` emit `cookie_failure` (level `ERROR`) into `system_events`.
    - `test_cookie_warning_event_emission`: Assert `SessionStatus.EXPIRING_SOON` (< 48h remaining) emits `cookie_warning` (level `WARNING`) into `system_events`.
    - `test_cookie_incident_1hour_deduplication`: Assert multiple health checks within 1 hour for the same channel and status emit exactly 1 event.
    - `test_cookie_status_transition_bypasses_dedup`: Assert status transition (e.g. `EXPIRING_SOON` $\to$ `EXPIRED`) emits immediately without waiting for the 1-hour window.
  - Concrete edit targets: `tests/unit/test_prompt_leak_telemetry.py` (new file), `tests/unit/test_cookie_lifecycle.py` (new file).
  - Concrete inspection targets: `src/sanitizer/security.py`, `src/sanitizer/tts.py`, `src/core/cookies.py`, `src/api_health.py`.

- [x] 2.2 **[GREEN]** Hook Multi-Provider LLM & TTS Token Burn Interceptors:
  - In `src/agents/base_agent.py` (`ProgrammaticAgent`):
    - Extract usage dictionary (`prompt_tokens`, `completion_tokens`, `cached_tokens`, `reasoning_tokens`, `total_tokens`) from API / CLI response metadata.
    - Compute USD cost via `CostCalculator.calculate_cost(model, prompt_tokens, completion_tokens, cached_tokens)`.
    - Persist usage event via `QueueRepository.record_token_burn(...)` with `provider = 'antigravity_pro'`.
    - On `AgentSaturationError`: record `status = 'saturated'` in `token_burn_events`, emit `quota_saturation` event to `system_events` via `emit_event()`, and flag story for `JobStatus.WAITING_LLM_QUOTA`.
  - In `src/llm.py` (`_curate_with_gemini`):
    - Parse `resp.json()` for `usageMetadata` (`promptTokenCount`, `candidatesTokenCount`, `cachedContentTokenCount`).
    - Compute USD cost and record event via `record_token_burn(...)` with `provider = 'gemini_rest'`.
    - On HTTP 429 / quota failure: record `status = 'saturated'` in `token_burn_events` and emit `quota_saturation` to `system_events`.
  - In `src/audio/tts_router.py` (`TTSRouter.synthesize`):
    - Measure synthesis elapsed duration in seconds and character count (mapped to `total_tokens`).
    - Record event via `record_token_burn(...)` with `provider` (`'edge_tts'`, `'elevenlabs'`, `'kokoro'`), voice model, and estimated USD cost.
  - Concrete edit targets: `src/agents/base_agent.py`, `src/llm.py`, `src/audio/tts_router.py`.

- [x] 2.3 **[GREEN]** Hook Pre-TTS Semantic Barrier Prompt-Leak Interceptors:
  - In `src/sanitizer/security.py` (`validate_semantic_barrier`):
    - Intercept `PromptLeakError` raised when taboo patterns match.
    - Extract matched pattern name, truncated snippet ($\le 120$ characters), model, provider, channel, story context.
    - Emit structured `audio_prompt_leak` event (level `WARNING`) into `system_events` via non-blocking `emit_event()`.
    - Track short-window leak occurrences: if $> 3$ leaks occur within 30 minutes, invoke `send_operational_alert()`.
    - Re-raise `PromptLeakError` to guarantee invalid text never proceeds to synthesis.
  - In `src/sanitizer/tts.py` (`validate_pre_tts_script`):
    - Wrap pre-TTS validation rules (preambles, forbidden editorial elements, meta-introductions).
    - Upon `PromptLeakError`, emit structured `audio_prompt_leak` event to `system_events` before re-raising.
  - Concrete edit targets: `src/sanitizer/security.py`, `src/sanitizer/tts.py`.

- [x] 2.4 **[GREEN]** Hook YouTube Quotas, Upload Limits, Drafts & Ambiguous Uploads:
  - In `src/pipeline/stages/stage_13_publish.py` and `src/youtube/uploader/`:
    - Catch `YouTubeQuotaExceededError`: emit `youtube_quota_limit` (`reason: "quota_exceeded"`, estimated 1,600 units) to `system_events`, update story to `JobStatus.WAITING_YOUTUBE_LIMIT`, release worker lease, and set `next_attempt_at` to the next 08:00 UTC cycle.
    - Catch `YouTubeUploadLimitError`: emit `youtube_quota_limit` (`reason: "upload_limit_exceeded"`) to `system_events`, update story to `JobStatus.WAITING_YOUTUBE_LIMIT`, release lease, and set 12-hour backoff.
    - Staged publications: record `privacy_status` (`'draft'`, `'unlisted'`, `'public'`) in `publications` and `stories`.
    - Custom thumbnail verification: verify API returns HTTP 200 confirmation, setting `thumbnail_confirmed = 1` in `publications`.
    - Ambiguous upload safeguard (`UPLOAD_UNCONFIRMED`): upon network drop or unconfirmed response during video binary transmission, transition story to `JobStatus.UPLOAD_UNCONFIRMED`, emit `upload_unconfirmed` event to `system_events`, and require preflight check before any retry.
  - Concrete edit targets: `src/pipeline/stages/stage_13_publish.py`, `src/youtube/uploader/__init__.py`.

- [x] 2.5 **[GREEN]** Hook Cookie Lifecycle & Stateful 1-Hour Deduplication:
  - In `src/api_health.py` (`check_cookies`) and `src/core/cookies.py`:
    - Implement in-memory stateful deduplication registry `_COOKIE_INCIDENT_REGISTRY: Dict[Tuple[str, str], tuple[float, str]]`.
    - On `SessionStatus.EXPIRED`, `SessionStatus.INCOMPLETE`, `SessionStatus.INVALID`: check last emitted timestamp for `(channel, 'cookie_failure')`; emit `cookie_failure` (level `ERROR`) into `system_events` only if $> 3,600\text{s}$ elapsed or if status transitioned.
    - On `SessionStatus.EXPIRING_SOON` (< 48h remaining): check last emitted timestamp for `(channel, 'cookie_warning')`; emit `cookie_warning` (level `WARNING`) into `system_events` if $> 3,600\text{s}$ elapsed.
    - On status change (e.g. `EXPIRING_SOON` $\to$ `EXPIRED` or `EXPIRED` $\to$ `HEALTHY`): immediately bypass deduplication, emit event, and update registry.
  - In `src/youtube/session_uploader.py`: emit structured `cookie_failure` on preflight authentication drops or upload session timeouts.
  - Concrete edit targets: `src/api_health.py`, `src/core/cookies.py`, `src/youtube/session_uploader.py`.

- [x] 2.6 **[GREEN]** Hook Database Backup Lifecycle & Asset Rejection Analytics:
  - In `src/core/repository/migrations.py` (`backup_database`) and `src/cli/handlers/backup.py`:
    - On successful backup: emit `database_backup_completed` (level `INFO`) into `system_events` with target snapshot path, file size in bytes, and execution duration in ms.
    - On backup failure: emit `database_backup_failed` (level `CRITICAL`) with error message and traceback.
  - In `src/verification/technical_qa.py` and `src/agents/video_qa.py`:
    - On automated QA check failure (black frame threshold exceeded, luminance anomaly, A/V sync drift $> 100\text{ ms}$, audio clipping): emit `asset_rejection` (level `WARNING`) to `system_events` with defect category (`visual`, `audio`, `sync`, `luminance`, `pacing`), measured metric value, threshold, and asset/story ID.
  - In `src/orchestrator/scheduler.py` (Telegram human review lifecycle):
    - When `review_jobs` status is updated to `'REJECTED'`, emit `asset_rejection` event into `system_events` with defect category `'editorial'`.
  - Concrete edit targets: `src/core/repository/migrations.py`, `src/cli/handlers/backup.py`, `src/verification/technical_qa.py`, `src/agents/video_qa.py`, `src/orchestrator/scheduler.py`.

- [x] 2.7 **[VERIFY]** Run Phase 2 interceptor test suites:
  - Command: `.venv/bin/pytest tests/unit/test_prompt_leak_telemetry.py tests/unit/test_cookie_lifecycle.py -v`.
  - Assert 100% pass across prompt leak interception, cookie incident emission, and deduplication logic.

---

## Phase 3: Observability Hub & Collector Engine

- [x] 3.1 **[RED]** Create new test module `tests/unit/test_tube_telemetry.py` defining collector and domain contracts:
  - `test_host_resource_sampling_within_budget`: Verify host CPU percentage and process RSS memory in MiB/GiB sample in $< 2\text{ ms}$ without spawning subprocesses.
  - `test_host_resource_headroom_status_critical`: Assert process RSS $> 2048\text{ MiB}$ flags `ram_status = 'CRITICAL'`; disk free $< 2.0\text{ GiB}$ flags `disk_status = 'CRITICAL'`.
  - `test_daemon_liveness_heartbeat_states`: Assert heartbeat age $\le 60\text{s} \to \text{HEALTHY}$, $61–120\text{s} \to \text{DEGRADED}$, $> 120\text{s} \to \text{STALE}$, absent $\to \text{STOPPED}$.
  - `test_channel_stoppages_and_leases_aggregation`: Mock `channel_controls` and `leases`; assert paused channels, active worker locks, and expired locks compile accurately.
  - `test_sqlite_wal_storage_bloat_detection`: Assert WAL file $> 50\text{ MiB} \to \text{GROWTH_WARNING}$, $> 200\text{ MiB} \to \text{CRITICAL_WAL_BLOAT}$.
  - `test_migration_version_parity_evaluation`: Assert version 9 matches expected version; assert version 8 returns `migration_status = 'PENDING_MIGRATIONS'`.
  - `test_tube_collector_compile_snapshot_performance`: Assert compiling complete `TubeSnapshot` executes in $< 10\text{ ms}`.
  - Concrete edit target: `tests/unit/test_tube_telemetry.py` (new test file).
  - Concrete inspection targets: `src/core/repository/leases.py`, `src/core/repository/migrations.py`.

- [x] 3.2 **[GREEN]** Implement Quota Domain Engine in `src/observability/quota.py`:
  - Implement `QuotaMonitor`:
    - Define daily token budgets and quota thresholds per provider (Antigravity Pro, Gemini REST, Grok, TTS).
    - Track YouTube Data API v3 10,000 daily quota units (1,600 units/upload, 50 units/thumbnail, 50 units/metadata), resetting at 08:00 UTC (00:00 PST).
    - Track channel daily upload caps (5–10 uploads per rolling 24 hours).
    - Detect quota saturation conditions and determine backoff recommendation states (`WAITING_LLM_QUOTA`, `WAITING_IMAGE_QUOTA`, `WAITING_YOUTUBE_LIMIT`).
    - Produce `TokenBurnSummary` and `YouTubeQuotaMetrics` dataclasses.
  - Concrete edit target: `src/observability/quota.py` (new file).

- [x] 3.3 **[GREEN]** Implement MCP Health Checker in `src/observability/mcp_health.py`:
  - Implement `MCPHealthChecker`:
    - Factory importability check: verify `create_mcp_server()` from `src.mcp.server` imports and instantiates cleanly without exceptions.
    - Runtime tool error rate check: query `system_events` for `mcp_tool_failure` over the last 24 hours and compute failure percentage.
    - In-process programmatic SSOT drift check: invoke `verify_mcp_sync(repo_root)` in-process comparing registrations against `CANONICAL_TOOLS`, `CANONICAL_RESOURCES`, and `docs/MCP.md`.
    - Consolidated tri-state resolution:
      - `BROKEN`: Import fails, factory raises, or database inaccessible.
      - `DEGRADED`: SSOT drift detected or tool failure rate $> 20\%$.
      - `HEALTHY`: Clean import, nominal error rate, 100% parity.
    - Produce `MCPHealthMetrics` dataclass.
  - Concrete edit target: `src/observability/mcp_health.py` (new file).

- [x] 3.4 **[GREEN]** Implement Centralized Tube Collector Engine in `src/observability/tube.py`:
  - Define strongly-typed telemetry dataclasses:
    - `HostResourceMetrics`, `DaemonStoppageMetrics`, `TokenBurnSummary`, `YouTubeQuotaMetrics`, `CookieIncidentMetrics`, `PromptLeakMetrics`, `DatabaseHealthMetrics`, `MCPHealthMetrics`, `AssetRejectionSummary`, `TubeSnapshot`.
  - Implement `TubeCollector`:
    - `sample_host_resources()`: Read `/proc/stat` and `/proc/self/status` (or `psutil`) for CPU % and process RSS RAM MiB/GiB in $< 2\text{ ms}$; read disk free space via `os.statvfs()` asserting $\ge 2.0\text{ GiB}$ free space.
    - `sample_daemon_stoppages()`: Read `daemon_liveness` via `read_daemon_heartbeat()`, query `channel_controls` and `leases`/`lane_leases`, inspect circuit breakers.
    - `sample_database_health()`: Measure `.sqlite` and `.sqlite-wal` file sizes, run `PRAGMA wal_checkpoint(PASSIVE)`, verify migration version parity against expected version 9, query last backup event age from `system_events`.
    - `compile_snapshot(channel=None, window_hours=24)`: Consolidate host resources, stoppages, token burn, YouTube quotas, cookie health, prompt leaks, database health, MCP health, asset rejections, and recent incidents into `TubeSnapshot` in $< 10\text{ ms}`.
    - Hook critical conditions to `send_operational_alert()` in `src/observability/alerts.py` (quota saturation, stale heartbeat >120s, cookie expiration <48h, audio prompt leak clusters, backup failure).
  - Update `src/observability/__init__.py` to re-export `TubeCollector`, `TubeSnapshot`, `QuotaMonitor`, `MCPHealthChecker`, and all metrics dataclasses.
  - Concrete edit targets: `src/observability/tube.py` (new file), `src/observability/__init__.py`.

- [x] 3.5 **[VERIFY]** Run Phase 3 collector test suite:
  - Command: `.venv/bin/pytest tests/unit/test_tube_telemetry.py -v`.
  - Assert 100% pass across host resource sampling, daemon liveness, WAL bloat checks, and snapshot compilation.

---

## Phase 4: Operational Surfaces

- [x] 4.1 **[RED]** Create new test module `tests/unit/test_mcp_tube.py` defining CLI and MCP contracts:
  - `test_mcp_resource_system_tube`: Assert reading `system://tube` returns valid JSON matching `TubeSnapshot.to_dict()`.
  - `test_mcp_resource_system_quotas`: Assert reading `system://quotas` returns token burn and YouTube quota breakdown.
  - `test_mcp_resource_system_health_enrichment`: Assert enriched `system://health` includes daemon liveness, cookie status, WAL status, and MCP health.
  - `test_mcp_tool_get_tube_status_execution`: Assert executing `get_tube_status` with/without channel filter returns structured JSON in $< 50\text{ ms}$.
  - `test_mcp_health_checker_tri_state_resolution`: Assert `MCPHealthChecker` correctly identifies `HEALTHY`, `DEGRADED` (on SSOT drift), and `BROKEN` (on import failure).
  - `test_cli_tube_dashboard_rendering`: Assert `print_tube()` produces ANSI terminal gauges, tables, and incident timelines.
  - `test_cli_tube_json_mode`: Assert `main.py tube --json` outputs parseable JSON matching `TubeSnapshot`.
  - Concrete edit target: `tests/unit/test_mcp_tube.py` (new test file).
  - Concrete inspection targets: `src/mcp/server.py`, `src/cli/subparsers.py`.

- [x] 4.2 **[GREEN]** Implement CLI `tube` Subcommand & `status --tube` Flag:
  - In `src/cli/subparsers.py`:
    - Register `register_tube_subcommand(subparsers, parent)` with flags: `-j`/`--json`, `-c`/`--channel`, `-w`/`--window` (default 24), `--prune`.
    - Add `--tube` flag to `register_status_subcommand()`.
  - In `src/cli/handlers/status.py`:
    - Implement `cli_tube(args)` and `print_tube(snapshot, channel=None, json_output=False)`:
      - Section 1: System Gauges (Host CPU %, Process RSS RAM MiB / 2048 MiB budget, Disk Free GiB / 2.0 GiB minimum).
      - Section 2: Daemon & Concurrency (Heartbeat age, active lane leases, paused channels).
      - Section 3: Multi-Provider Token Burn & USD Costs (Breakdown by provider: Antigravity Pro, Gemini REST, Grok, TTS).
      - Section 4: YouTube Data API Quotas (10k daily units used/remaining, staged drafts, thumbnail confirmations).
      - Section 5: Security & Health (Pre-TTS prompt leaks, cookie decay status, WAL file size & checkpoint info, MCP health).
      - Section 6: Recent Incidents Timeline (Last 5–10 operational events).
    - If `--prune` is passed: invoke `QueueRepository.prune_token_burn_events(retention_days=30)` and print purged record count.
    - If `--json` is passed: print formatted JSON matching `TubeSnapshot.to_dict()` in $< 100\text{ ms}$.
    - If `status --tube` is invoked: render El Tubo dashboard alongside standard queue status.
  - Concrete edit targets: `src/cli/subparsers.py`, `src/cli/handlers/status.py`.

- [x] 4.3 **[GREEN]** Implement MCP Resources (`system://tube`, `system://quotas`, enriched `system://health`):
  - In `src/mcp/resources.py`:
    - Register `system://tube` resource: query `TubeCollector.compile_snapshot()` and return serialized JSON (`mime_type = "application/json"`).
    - Register `system://quotas` resource: query `QuotaMonitor` and return token burn and YouTube quotas JSON (`mime_type = "application/json"`).
    - Enrich `system://health` resource: include `daemon_liveness_status`, `heartbeat_age_seconds`, `mcp_health`, `cookie_health`, and `wal_status` in health payload.
  - Concrete edit targets: `src/mcp/resources.py`.

- [x] 4.4 **[GREEN]** Implement Canonical MCP Tool `get_tube_status`:
  - Create `src/mcp/tools/get_tube_status.py`:
    - Name: `get_tube_status`.
    - Description: "Inspect comprehensive pipeline operational telemetry ('El Tubo') including host CPU/RAM headroom, multi-provider token burn, YouTube quota limits, channel stoppages, and recent incidents."
    - Arguments: `channel: Optional[str] = None`, `window_hours: int = 24`, `include_incidents: bool = True`, `include_burn: bool = True`.
    - Execute telemetry query via `TubeCollector` and return formatted JSON string within 50 ms.
  - Re-export `get_tube_status` in `src/mcp/tools/__init__.py`.
  - Register `get_tube_status` on `MCPServer` in `src/mcp/server.py`.
  - Concrete edit targets: `src/mcp/tools/get_tube_status.py` (new file), `src/mcp/tools/__init__.py`, `src/mcp/server.py`.

- [x] 4.5 **[GREEN]** Update MCP SSOT Parity Gate and Documentation:
  - In `scripts/verify_mcp_sync.py`:
    - Add `"get_tube_status"` to `CANONICAL_TOOLS`.
    - Add `"system://tube"` and `"system://quotas"` to `CANONICAL_RESOURCES`.
  - In `docs/MCP.md`:
    - Document `get_tube_status` tool: schema, input arguments, descriptions, and example JSON response.
    - Document `system://tube` and `system://quotas` resources: URI patterns, description, MIME type, payload schemas.
    - Document enriched `system://health` keys.
  - Concrete edit targets: `scripts/verify_mcp_sync.py`, `docs/MCP.md`.

- [x] 4.6 **[VERIFY]** Run Phase 4 operational surface test suite & SSOT parity gate:
  - Command: `.venv/bin/pytest tests/unit/test_mcp_tube.py -v && python scripts/verify_mcp_sync.py`.
  - Assert 100% pass across MCP resources, tools, CLI output, and zero SSOT drift.

---

## Phase 5: Automated Testing & Verification

- [x] 5.1 **[RED]** Create Integration Test Modules for End-to-End Scenarios:
  - Create `tests/integration/test_tube_pipeline_integration.py`:
    - `test_database_backup_and_wal_observability`: Execute `backup_database()`, assert `database_backup_completed` event in `system_events` with file size and duration ms, and verify `PRAGMA wal_checkpoint(PASSIVE)` reports checkpointed frames.
    - `test_stage_13_youtube_quota_limit_transition`: Simulate Stage 13 publishing encountering `YouTubeQuotaExceededError`; verify transition to `JobStatus.WAITING_YOUTUBE_LIMIT`, lease release, and `youtube_quota_limit` event logging.
    - `test_stage_13_upload_unconfirmed_safeguard`: Simulate network dropout during video binary transmission; verify transition to `JobStatus.UPLOAD_UNCONFIRMED`, `upload_unconfirmed` event logging, and rejection of blind retry.
    - `test_full_tube_snapshot_integration`: Run offline pipeline turn; assert `TubeSnapshot` contains valid host metrics, token burn events, database health, and recent incidents without blocking.
  - Concrete edit targets: `tests/integration/test_tube_pipeline_integration.py` (new file).
  - Concrete inspection targets: `src/pipeline/stages/stage_13_publish.py`, `src/core/repository/migrations.py`.

- [x] 5.2 **[GREEN]** Implement Integration Test Scenarios & Wire Test Fixtures:
  - Implement test cases in `tests/integration/test_tube_pipeline_integration.py` with mock SQLite database fixtures.
  - Verify clean cleanup of temporary snapshot files and test databases.
  - Concrete edit targets: `tests/integration/test_tube_pipeline_integration.py`.

- [x] 5.3 **[VERIFY]** Run Comprehensive Unit & Integration Test Suites:
  - Run all El Tubo unit test modules:
    - `.venv/bin/pytest tests/unit/test_tube_telemetry.py tests/unit/test_token_burn_tracking.py tests/unit/test_mcp_tube.py tests/unit/test_prompt_leak_telemetry.py tests/unit/test_cookie_lifecycle.py tests/integration/test_tube_pipeline_integration.py -v`.
  - Assert 100% pass across all unit and integration test assertions with 0 failures.

- [x] 5.4 **[VERIFY]** Run MCP SSOT Parity Gate:
  - Command: `python scripts/verify_mcp_sync.py`.
  - Assert exit code 0 and output: `[STATUS: HEALTHY] 100% bidirectional parity verified with zero drift.`

- [x] 5.5 **[VERIFY]** Run Full Repository Integrity Verification Gate:
  - Command: `./scripts/verify_integrity.sh`.
  - Assert 0 lint errors, 0 type errors, 100% test suite pass, and zero regressions across the codebase.
