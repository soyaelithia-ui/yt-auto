# Specification: Multi-Provider Token Tracking and Quota Observability

## Capability Overview
The `multi-provider-token-tracking` capability provides structured persistence, aggregation, and cost estimation for token and character consumption across all integrated AI providers (Antigravity Pro, Gemini REST, Grok, and TTS synthesis). It tracks prompt, completion, cached, and reasoning tokens, computes USD expenses via `CostCalculator`, indexes quota saturation events, and manages automated data retention pruning.

## Requirements

### Requirement 1: Token Burn Persistence Schema and Indexing (Migration 009)
The database migration layer MUST establish Migration 009 (`009_pipeline_telemetry_and_token_burn`) to provision the `token_burn_events` table and associated read performance indices in SQLite.

1. The `token_burn_events` table MUST contain the following columns:
   - `event_id` (TEXT PRIMARY KEY)
   - `ts` (TEXT NOT NULL, ISO-8601 UTC timestamp)
   - `run_id` (TEXT, foreign reference to execution run)
   - `story_id` (TEXT, associated story identifier)
   - `channel` (TEXT, canonical channel name)
   - `provider` (TEXT NOT NULL, e.g. `'antigravity_pro'`, `'gemini_rest'`, `'grok'`, `'edge_tts'`, `'elevenlabs'`, `'kokoro'`)
   - `model` (TEXT NOT NULL, e.g. `'gemini-2.5-pro'`, `'grok-2'`, `'es-ES-AlvaroNeural'`)
   - `prompt_tokens` (INTEGER NOT NULL DEFAULT 0)
   - `completion_tokens` (INTEGER NOT NULL DEFAULT 0)
   - `cached_tokens` (INTEGER NOT NULL DEFAULT 0)
   - `reasoning_tokens` (INTEGER NOT NULL DEFAULT 0)
   - `total_tokens` (INTEGER NOT NULL DEFAULT 0)
   - `cost_usd` (REAL NOT NULL DEFAULT 0.0)
   - `duration_seconds` (REAL NOT NULL DEFAULT 0.0)
   - `status` (TEXT NOT NULL DEFAULT 'success' CHECK(status IN ('success', 'failed', 'saturated')))
   - `created_at` (TEXT NOT NULL, default CURRENT_TIMESTAMP)
2. Migration 009 MUST create indices on:
   - `idx_token_burn_ts` ON `token_burn_events(ts)`
   - `idx_token_burn_run` ON `token_burn_events(run_id)`
   - `idx_token_burn_provider_model` ON `token_burn_events(provider, model)`
   - `idx_token_burn_channel` ON `token_burn_events(channel)`
3. All write operations to `token_burn_events` MUST be non-blocking and isolated in `try/except` blocks so persistence failures never disrupt pipeline rendering or publishing.

#### Scenario: Migration 009 applies cleanly and creates schema
- **Given** an initialized SQLite database at migration version 8
- **When** `apply_migrations()` is executed
- **Then** migration version 9 MUST be recorded in `schema_migrations`
- **And** `token_burn_events` table MUST exist with all 16 required columns
- **And** all 4 required read indices MUST exist.

---

### Requirement 2: Token and USD Cost Instrumentation Across Providers
All LLM agent invocations and TTS narration generation calls MUST record detailed token and duration metrics with computed USD costs into `token_burn_events`.

1. **Antigravity Pro (`ProgrammaticAgent` in `src/agents/base_agent.py`)**:
   - The agent MUST capture prompt tokens, completion tokens, cached tokens, and reasoning tokens returned in API response metadata.
   - The agent MUST compute the USD cost using `CostCalculator.calculate_cost(model, prompt_tokens, completion_tokens, cached_tokens)`.
   - The agent MUST persist the event with `provider = 'antigravity_pro'`.
2. **Gemini REST (`src/llm.py`)**:
   - Invocations of `_curate_with_gemini` MUST parse `usageMetadata` (`promptTokenCount`, `candidatesTokenCount`, `cachedContentTokenCount`), compute USD cost, and persist with `provider = 'gemini_rest'`.
3. **TTS Synthesis (`src/audio/tts_router.py`)**:
   - Narration synthesis calls MUST record synthesis duration in seconds, character count (mapped into `total_tokens` for character-based billing), provider (`'edge_tts'`, `'elevenlabs'`, `'kokoro'`), voice model, and estimated USD cost.

#### Scenario: Successful Antigravity Pro agent invocation with cached and reasoning tokens
- **Given** an execution of `ProgrammaticAgent.call()` returning 1,500 prompt tokens, 500 cached tokens, 200 reasoning tokens, and 600 completion tokens
- **When** the agent completion handler persists the usage event
- **Then** a row MUST be inserted into `token_burn_events`
- **And** `prompt_tokens` MUST equal 1500, `cached_tokens` MUST equal 500, `reasoning_tokens` MUST equal 200, and `completion_tokens` MUST equal 600
- **And** `cost_usd` MUST be strictly greater than $0.00$
- **And** `status` MUST be `'success'`.

#### Scenario: TTS narration audio generation persistence
- **Given** an audio synthesis task producing 1,200 characters of narration via `elevenlabs` in 3.4 seconds
- **When** `tts_router` finishes audio synthesis
- **Then** a row MUST be inserted into `token_burn_events` with `provider = 'elevenlabs'`
- **And** `duration_seconds` MUST reflect 3.4
- **And** `total_tokens` MUST reflect the synthesized character count.

---

### Requirement 3: Quota Saturation Interception and Backoff State Transitions
The system MUST detect provider rate limit and quota exhaustion errors, record saturation in `token_burn_events`, emit an operational incident into `system_events`, and transition job queues into backoff status.

1. When an invocation raises `AgentSaturationError`, HTTP 429 Too Many Requests, or quota exhaustion:
   - The caller MUST persist a row in `token_burn_events` with `status = 'saturated'`, capturing known prompt tokens and `cost_usd = 0.0`.
   - The caller MUST emit an event of type `'quota_saturation'` with level `'WARNING'` or `'ERROR'` into `system_events`.
2. When LLM provider quotas are exhausted, affected queue jobs MUST transition to `JobStatus.WAITING_LLM_QUOTA`.
3. When visual or image generation provider quotas are exhausted, affected queue jobs MUST transition to `JobStatus.WAITING_IMAGE_QUOTA`.
4. Jobs in `WAITING_LLM_QUOTA` or `WAITING_IMAGE_QUOTA` SHALL NOT be leased by workers until their cooldown window expires or operator intervention clears the state.

#### Scenario: Antigravity Pro provider returns quota saturation (HTTP 429)
- **Given** an agent invocation that encounters an `AgentSaturationError`
- **When** error handling executes
- **Then** a row in `token_burn_events` MUST be recorded with `status = 'saturated'`
- **And** an event with `event_type = 'quota_saturation'` MUST be inserted into `system_events`
- **And** the active job in `stories` MUST transition to `JobStatus.WAITING_LLM_QUOTA`
- **And** the lease MUST be released.

---

### Requirement 4: Token Burn Querying and Periodic Retention Pruning
The repository layer in `src/core/repository/queue.py` and quota module in `src/observability/quota.py` MUST provide methods to aggregate consumption and prune stale records.

1. `query_token_burn_summary(window_hours=24, channel=None, provider=None)` MUST calculate:
   - Aggregate prompt, completion, cached, reasoning, and total tokens.
   - Aggregate USD cost across all matching records within the specified time window.
   - Call count and saturation count.
   - Breakdown by provider and model.
2. `prune_token_burn_events(retention_days=30)` MUST delete records older than the specified retention threshold.
3. The automated 24-hour maintenance sweep loop MUST execute `prune_token_burn_events(retention_days=30)` during each daily maintenance cycle.

#### Scenario: Aggregating 24-hour token burn and costs
- **Given** 100 token burn records written over the preceding 24 hours totaling $1.45 USD and 250,000 tokens
- **When** `query_token_burn_summary(window_hours=24)` is called
- **Then** the returned summary MUST report `total_cost_usd` approximately equal to 1.45
- **And** `total_tokens` MUST equal 250,000
- **And** `breakdown_by_provider` MUST group tokens and costs by provider name.

#### Scenario: Pruning records older than 30-day retention threshold
- **Given** token burn events with timestamps from 40 days ago and timestamps from 5 days ago
- **When** `prune_token_burn_events(retention_days=30)` is executed
- **Then** all records older than 30 days MUST be deleted
- **And** records from 5 days ago MUST remain intact
- **And** the count of deleted rows MUST be returned.
