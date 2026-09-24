# Tasks: Purge Monoliths, Redundant Processes, and Fantasy Hardcoding

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~6,500 - 7,200 lines (decomposition and relocation of 6 monoliths [6,467L], net reduction >1,500L Python, >800L docs) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | 8 Chained PRs (or 8 discrete work units with independent review boundaries) |
| Delivery strategy | chained-prs |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Foundation, Documentation Purge & Migration Schema Relaxation | PR 1 | `.venv/bin/pytest tests/unit/test_architectural_specs.py tests/unit/test_repository_migration_003.py -v` | Headless doc audit & in-memory SQLite migration harness | Revert doc deletions and `src/core/repository/migrations.py` |
| 2 | Domain Identifier Inversion & Naming Normalization | PR 2 | `.venv/bin/pytest tests/unit/test_channel_domain_dynamic.py tests/unit/test_channels_lanes.py tests/unit/test_purge_channels.py -v && .venv/bin/python3 scripts/verify_mcp_sync.py` | Domain alias resolution test harness + MCP drift validator | Revert `src/core/domain.py`, `config/lanes.json`, `src/core/lanes.py`, `src/scene_manifest.py`, `src/daemon.py`, `src/cli/purge_channels.py` |
| 3 | Unit 4.1: YouTube Uploader Decomposition (`src/youtube/uploader.py` -> `src/youtube/uploader/`) | PR 3 | `.venv/bin/pytest tests/unit/test_youtube_uploader.py tests/unit/test_session_uploader_hybrid.py tests/unit/test_innertube_uploader.py -v` | Mocked Google Data API v3 client & Playwright test doubles | Revert `src/youtube/uploader.py` facade and delete `src/youtube/uploader/` subpackage |
| 4 | Unit 4.2: Script Curator Decomposition (`src/curators/text_splitter.py` -> `src/curators/`) | PR 4 | `.venv/bin/pytest tests/unit/test_script_curator.py tests/unit/test_narrative_curators.py -v` | Pure Python sentence splitting, scene slicing, and tension curve runner | Revert `src/curators/text_splitter.py` facade and delete extracted modules |
| 5 | Unit 4.3: Story Performance Scoring Decomposition (`src/core/scoring.py` -> `src/core/scoring/`) | PR 5 | `.venv/bin/pytest tests/unit/test_scoring.py tests/unit/test_analytics_scoring.py -v` | Fast heuristic regex runner & deterministic offline fallback evaluator | Revert `src/core/scoring.py` facade and delete `src/core/scoring/` subpackage |
| 6 | Unit 4.4: Loop Asset Catalog Decomposition (`src/core/catalog.py` -> `src/core/catalog/`) | PR 6 | `.venv/bin/pytest tests/unit/test_loop_catalog.py tests/unit/test_catalog_asset_only_composition.py -v` | In-memory SQLite loop catalog database & temp asset fixtures | Revert `src/core/catalog.py` facade and delete `src/core/catalog_sync.py`, `src/core/catalog_audit.py` |
| 7 | Unit 4.5: Media Hybrid Engine Decomposition (`src/media/hybrid_engine.py` -> `src/media/`) | PR 7 | `.venv/bin/pytest tests/unit/test_ken_burns_canonical.py tests/unit/test_hybrid_ffmpeg_camera_path.py -v` | FFmpeg argument builder synthesis & stream-copy validation harness | Revert `src/media/hybrid_engine.py` facade and delete `src/media/ken_burns.py`, `src/media/overlays.py` |
| 8 | Unit 4.6: Core Profiling Decomposition (`src/core/profiling.py` -> `src/core/profiling/`) & Full Integrity Gate | PR 8 | `.venv/bin/pytest tests/unit/test_profiling.py tests/unit/test_anti_regression_guardrails.py -v && ./scripts/verify_integrity.sh` | Linux `/proc` process metrics sampler & synthetic benchmark cycle runner | Revert `src/core/profiling.py` facade and delete `src/core/profiling/` subpackage |

---

## Phase 1: Test Harness & Foundation Setup (TDD)

- [x] 1.1 **[RED]** Create/update test cases in `tests/unit/test_architectural_specs.py` asserting that `docs/PLAN_ARQUITECTURA_V3_1.md` is purged, is absent from `EXPECTED_DOCS`, and that `docs/PLAN_MAESTRO_PIPELINE_VISUAL.md` contains all seven required technical section anchors.
- [x] 1.2 **[RED]** Add test cases in `tests/unit/test_repository_migration_003.py` asserting that `video_analytics_snapshots` accepts inserts with canonical channel identifiers (`"horror"`, `"drama"`, `"scifi"`) in addition to legacy fantasy identifiers (`"moku"`, `"aelithia"`) without violating table `CHECK` constraints.
- [x] 1.3 **[RED]** Add test cases in `tests/unit/test_channel_domain_dynamic.py` and `tests/unit/test_channels_lanes.py` asserting:
  - Canonical channel enum values: `CanonicalChannel.HORROR.value == "horror"`, `CanonicalChannel.DRAMA.value == "drama"`, `CanonicalChannel.SCIFI.value == "scifi"`.
  - Backward compatibility aliases: `CanonicalChannel.MOKU == CanonicalChannel.HORROR`, `CanonicalChannel.AELITHIA == CanonicalChannel.DRAMA`.
  - Bidirectional resolution: `canonical_channel("moku") == CanonicalChannel.HORROR` and `canonical_channel("horror") == CanonicalChannel.HORROR`.
  - Legacy lane IDs in `config/lanes.json` map cleanly to canonical thematic lane IDs via `LANE_ALIASES`.
- [x] 1.4 **[GREEN]** Relax `video_analytics_snapshots` table constraint in `src/core/repository/migrations.py` to `CHECK(channel IN ('horror', 'drama', 'scifi', 'moku', 'aelithia'))`.
- [x] 1.5 Verify foundation database migration tests pass: `.venv/bin/pytest tests/unit/test_repository_migration_003.py -v`.

---

## Phase 2: Obsolete Documentation Purge & Consolidation

- [x] 2.1 **[GREEN]** Permanently delete obsolete blueprint `docs/PLAN_ARQUITECTURA_V3_1.md` from the repository per AGENTS.md Rule 1 (Zero Resurrected Docs).
- [x] 2.2 **[GREEN]** Update `EXPECTED_DOCS` in `tests/unit/test_architectural_specs.py` by removing `"PLAN_ARQUITECTURA_V3_1.md"`.
- [x] 2.3 **[GREEN]** Update `docs/README.md` to remove references to `PLAN_ARQUITECTURA_V3_1.md` and synchronize the documentation index with canonical blueprints.
- [x] 2.4 **[GREEN]** Streamline `docs/PLAN_MAESTRO_PIPELINE_VISUAL.md`:
  - Excise dead-end audit logs and obsolete experiment post-mortems (skia-python, SwiftShader CPU saturation, ModernGL).
  - Summarize active production architecture (FFmpeg stream-copy `-c:v copy`, libass subtitles, single-pass EBU R128 audio mastering, volatile `/dev/shm` RAM temp audio storage).
  - Strictly preserve all seven required section headers asserted by `test_architectural_specs.py` (`Consolidación de Auditorías Previas`, `Diagnóstico del Workflow Actual`, `Matriz de Componentes`, `Estructura del Sistema`, `Auditoría y Plan de Saneamiento Documental`, `Checklist de Seguridad, Rendimiento`, `Hitos Estratégicos de Transición`).
  - Maintain total character length $> 1,000$ characters.
- [x] 2.5 **[GREEN]** Streamline `docs/PROPUESTA_EVOLUCION_PIPELINE_VISUAL.md`:
  - Remove duplicate retrospective crash logs from early 2025.
  - Consolidate active cinematic direction guidelines, 4-Act narrative pacing, and dynamic scene composition rules.
- [x] 2.6 Verify documentation test suite: `.venv/bin/pytest tests/unit/test_architectural_specs.py -v`.

---

## Phase 3: Domain Identifier Normalization

- [x] 3.1 **[GREEN]** Invert `CanonicalChannel` in `src/core/domain.py`:
  - Define `HORROR = "horror"`, `DRAMA = "drama"`, and `SCIFI = "scifi"` as canonical enum members.
  - Re-assign `CanonicalChannel.MOKU = CanonicalChannel.HORROR` and `CanonicalChannel.AELITHIA = CanonicalChannel.DRAMA`.
  - Update `_missing_` and `CHANNEL_ALIASES` for bidirectional string-to-enum resolution.
- [x] 3.2 **[GREEN]** Standardize canonical lane IDs in `config/lanes.json` to thematic naming:
  - `horror-scp-shorts` (channel: `"horror"`, orientation: `"vertical"`, 9:16).
  - `horror-horror-long` (channel: `"horror"`, orientation: `"horizontal"`, 16:9).
  - `drama-drama-shorts` (channel: `"drama"`, orientation: `"vertical"`, 9:16).
  - `drama-aita-long` (channel: `"drama"`, orientation: `"horizontal"`, 16:9).
  - `scifi-singularity-shorts` (channel: `"scifi"`, orientation: `"vertical"`, 9:16).
  - `scifi-singularity-long` (channel: `"scifi"`, orientation: `"horizontal"`, 16:9).
- [x] 3.3 **[GREEN]** Standardize `FALLBACK_LANE_DOCUMENTS` and invert `LANE_ALIASES` in `src/core/lanes.py` to map all legacy fantasy lane IDs (`moku-scp-shorts`, `moku-horror-long`, `aelithia-drama-shorts`, `aelithia-aita-long`) to canonical thematic lane IDs.
- [x] 3.4 **[GREEN]** Sanitize default parameter values in `src/scene_manifest.py`:
  - Change default `channel_name: str = "horror"` (eliminating `"moku"`).
  - Eliminate `stamp_text="[MOKU]"` default (defaulting to `None` or dynamic branding derived from lane/channel).
- [x] 3.5 **[GREEN]** Sanitize default channel arguments and friendly lane descriptions in `src/daemon.py`:
  - Update default parameter `channel: str = "horror"`.
  - Update continuous daemon cycle default channels list: `channels_to_process = ["horror", "drama"]`.
  - Update friendly lane description map with canonical thematic lane entries.
- [x] 3.6 **[GREEN]** Sanitize CLI argument default in `src/cli/purge_channels.py`:
  - Set default `--channel` argument to `"horror"`.
  - Resolve input channel through `canonical_channel()` for dry-run inspection and candidate querying.
- [x] 3.7 **[GREEN]** Update MCP tool parameter descriptions in `src/mcp/tools/*.py` (`list_lanes.py`, `system_preflight.py`, `query_loop_catalog.py`, `manage_queue.py`, etc.) and `docs/MCP.md` to reference canonical thematic channel names (`horror`, `drama`, `scifi`).
- [x] 3.8 Verify domain and lane unit tests: `.venv/bin/pytest tests/unit/test_channel_domain_dynamic.py tests/unit/test_channels_lanes.py tests/unit/test_purge_channels.py -v`.
- [x] 3.9 Verify MCP parity: `.venv/bin/python3 scripts/verify_mcp_sync.py`.

---

## Phase 4: Monolith Decomposition & Modularization (<100L Function Budget)

### Unit 4.1: `src/youtube/uploader.py` Decomposition (1,721L -> `src/youtube/uploader/`)

- [x] 4.1.1 **[RED]** Create/update tests in `tests/unit/test_youtube_uploader.py` and `tests/unit/test_session_uploader_hybrid.py` specifying:
  - YouTube Data API v3 client uploads, channel preflight, token resolution (`tokens/horror.json` with fallback to `tokens/moku.json`).
  - Playwright fallback upload lifecycle broken into 6 linear stages, asserting each stage handles DOM selectors and error conditions.
  - Publication gate 2PC atomic lease claim, verify, and consume.
  - Facade re-exports preserving contract compatibility markers (`PublicationGate`, `Publication gate requires job_id`, `single atomic publication claim`).
- [x] 4.1.2 **[GREEN]** Implement `src/youtube/uploader/api.py` (~220 lines):
  - `upload_video_via_api`: Google API client upload with resumable media chunking and retry handlers.
  - `_youtube_service`: OAuth credential resolution and discovery service builder.
  - `preflight_youtube_api`, `verify_youtube_credentials_preflight`, `verify_existing_video_via_api`, `_verify_uploaded_video`.
  - `resolve_channel_token_path`, `_save_refreshed_credentials`, and `validate_title_content_alignment`.
- [x] 4.1.3 **[GREEN]** Implement `src/youtube/uploader/session.py` (~380 lines):
  - Break down the 557-line `upload_video_via_playwright` into **6 linear, discrete stage functions** ($\le 100$ lines each):
    1. `_init_playwright_context(playwright, cookies_path, channel, headless)`
    2. `_navigate_and_check_auth(page, channel)`
    3. `_upload_file_payload(page, video_path)`
    4. `_fill_video_metadata(page, title, description, thumbnail_path, made_for_kids)`
    5. `_select_visibility_and_publish(page, visibility, schedule_time)`
    6. `_await_processing_and_extract_videoid(page, timeout_sec)`
  - Linear orchestrator `upload_video_via_playwright` in a safe `try...finally` block guaranteeing browser closing and PID reaping (`_get_playwright_pids`).
  - Helper routines: `format_cookies_for_playwright`, `_safe_preupload_failure`, `_click_dialog_button`, `click_next`, `click_done`, `upload_video_via_playwright_ts`.
  - Strictly observe Zero-Browser policy (restricted to `src/youtube/`).
- [x] 4.1.4 **[GREEN]** Implement `src/youtube/uploader/claim_gate.py` (~140 lines):
  - `_claim_publication_gate(job_id, story_id, channel, lane_id)`: Atomic 2PC lease acquisition from SQLite queue and review state databases.
  - `_consume_publication_claim(claim_token, video_id, status)`: Finalize publication state and release worker lease.
  - Failure reconciliation and gate release rollback handlers.
- [x] 4.1.5 **[GREEN]** Create `src/youtube/uploader/__init__.py` and refactor `src/youtube/uploader.py` facade (~180 lines):
  - High-level coordinator `upload_video()` orchestrating preflight -> claim gate lease -> API upload attempt -> Playwright session fallback on quota failure -> gate consumption.
  - `_normalize_upload_result(...)`.
  - Re-export all public symbols and error classes in `__all__`, preserving legacy compatibility markers.
- [x] 4.1.6 Verify uploader unit tests: `.venv/bin/pytest tests/unit/test_youtube_uploader.py tests/unit/test_session_uploader_hybrid.py tests/unit/test_innertube_uploader.py -v`.

---

### Unit 4.2: `src/curators/text_splitter.py` Decomposition (1,001L -> `src/curators/`)

- [x] 4.2.1 **[RED]** Create/update tests in `tests/unit/test_script_curator.py` and `tests/unit/test_narrative_curators.py` specifying:
  - Lane curation configs keyed by canonical thematic lanes with backward-compatible legacy lane alias resolution.
  - Algorithmic sentence splitting without false boundary breaks on abbreviations ("Dr.", "SCP-", "Sr.", "P.D.").
  - Progressive tension curve grading ($1-5$) and audio pacing cue resolution.
  - Facade backward compatibility for `TextSegmentationEngine` and `CinematicScriptCuratorAgent` alias.
- [x] 4.2.2 **[GREEN]** Implement `src/curators/curation_profiles.py` (~320 lines):
  - Declarative dictionary `LANE_CURATION_CONFIGS` keyed by canonical thematic lane IDs (`horror-scp-shorts`, `horror-horror-long`, `drama-drama-shorts`, `drama-aita-long`, `scifi-singularity-shorts`, `scifi-singularity-long`).
  - Explicit backward-compatibility alias resolution for legacy lane IDs.
  - Draft-07 JSON Schema validation path `SCHEMA_PATH` and `VALID_AUDIO_PACING_CUES` set.
  - Environmental mood dictionaries and scene transition templates.
- [x] 4.2.3 **[GREEN]** Implement `src/curators/segmentation.py` (~180 lines):
  - `split_into_sentences(text: str) -> list[str]`.
  - `sanitize_text(text: str) -> str`.
  - `slice_into_scenes(sentences, target_duration, wpm) -> list[dict]`.
  - `distribute_scenes_across_acts(scenes, act_count=4) -> list[dict]`.
- [x] 4.2.4 **[GREEN]** Implement `src/curators/tension.py` (~120 lines):
  - `interpolate_tension(scene_idx, total_scenes, tension_profile) -> int`.
  - `resolve_audio_pacing_cue(tension_level, act_role) -> str`.
- [x] 4.2.5 **[GREEN]** Refactor `src/curators/text_splitter.py` facade (~180 lines):
  - Maintain `TextSegmentationEngine` coordinating curation profiles, segmentation algorithms, and tension curves.
  - Retain `CinematicScriptCuratorAgent = TextSegmentationEngine` backwards-compatible alias.
  - Re-export `LANE_CURATION_CONFIGS`, `VALID_AUDIO_PACING_CUES`, and `SCHEMA_PATH` in `__all__`.
- [x] 4.2.6 Verify script curator unit tests: `.venv/bin/pytest tests/unit/test_script_curator.py tests/unit/test_narrative_curators.py -v`.

---

### Unit 4.3: `src/core/scoring.py` Decomposition (953L -> `src/core/scoring/`)

- [x] 4.3.1 **[RED]** Create/update tests in `tests/unit/test_scoring.py` and `tests/unit/test_analytics_scoring.py` specifying:
  - Strongly typed dataclass contracts (`HeuristicScoreReport`, `SemanticScoreReport`, `StoryScoringVerdict`).
  - Deterministic heuristics: hook strength detection, spoken seconds estimation, short-circuit fast reject gate ($< 2\text{ ms}$).
  - Semantic evaluation with deterministic offline fallback on LLM failure or timeout.
  - SQLite query index scan execution ($< 5\text{ ms}$) on `publications(actual_success_score)`.
- [x] 4.3.2 **[GREEN]** Implement `src/core/scoring/models.py` (~90 lines):
  - Strongly-typed `@dataclass(slots=True)` data contracts: `HeuristicScoreReport`, `SemanticScoreReport`, `StoryScoringVerdict`.
- [x] 4.3.3 **[GREEN]** Implement `src/core/scoring/heuristics.py` (~240 lines):
  - Fast, deterministic rule evaluation functions strictly $\le 100$ lines: `_strip_accents`, `_normalize_hook_text`, `estimate_spoken_seconds`, `first_spoken_hook`, `opening_hook_within_budget`, `detect_opening_hook_strength`, `evaluate_retention_length_score`, `evaluate_fast_heuristics`.
- [x] 4.3.4 **[GREEN]** Implement `src/core/scoring/semantic.py` (~220 lines):
  - LLM viral potential prompt building, JSON response parsing, and deterministic fallback evaluation: `_evaluate_semantic_deterministically`, `_build_semantic_eval_prompt`, `_parse_llm_json_response`, `_build_semantic_report_from_llm`, `evaluate_semantic_viral_potential`, `async_evaluate_semantic_viral_potential`.
- [x] 4.3.5 **[GREEN]** Create `src/core/scoring/__init__.py` and refactor `src/core/scoring.py` facade (~160 lines):
  - Master scoring coordinator: `compute_hybrid_story_score`, `filter_and_score_story`, `async_filter_and_score_story`.
  - Re-export all models and public functions in `__all__`.
- [x] 4.3.6 Verify scoring unit tests: `.venv/bin/pytest tests/unit/test_scoring.py tests/unit/test_analytics_scoring.py -v`.

---

### Unit 4.4: `src/core/catalog.py` Decomposition (943L -> `src/core/catalog/`)

- [x] 4.4.1 **[RED]** Create/update tests in `tests/unit/test_loop_catalog.py` and `tests/unit/test_catalog_asset_only_composition.py` specifying:
  - Filesystem asset scanning, FFprobe metadata extraction, and buffered 64KB chunk SHA256 hashing.
  - Catalog audit: orphan row pruning, SHA256 integrity verification, and synthetic monochrome placeholder pruning.
  - Core `LoopCatalogRepository` SQLite queries (`get_best_loop`, `record_loop_usage`) responding in $< 2\text{ ms}$.
- [x] 4.4.2 **[GREEN]** Implement `src/core/catalog_sync.py` (~180 lines):
  - `compute_file_sha256(file_path: Path) -> str`: Buffered 64KB digest calculation.
  - `probe_video_metadata(file_path: Path) -> tuple[float, int, int, str]`: FFprobe metadata extraction.
  - `resolve_loop_file_path(relative_or_abs_path) -> Path`: Asset root resolution.
  - `sync_catalog_from_assets(repo, assets_dir, force_rescan=False) -> dict`: Directory discovery, metadata probing, and tag registration.
- [x] 4.4.3 **[GREEN]** Implement `src/core/catalog_audit.py` (~160 lines):
  - `purge_synthetic_monochrome_loops(repo) -> int`: Flat monochrome placeholder detection and pruning.
  - `audit_and_cleanup(repo, assets_dir) -> dict`: SQLite vs. filesystem cross-referencing, orphan removal, hash verification.
- [x] 4.4.4 **[GREEN]** Refactor `src/core/catalog.py` facade (~320 lines):
  - Retain `LoopRecord` dataclass and focused `LoopCatalogRepository` SQL queries and usage tracking.
  - Implement delegation wrappers for `sync_catalog_from_assets()` and `audit_and_cleanup()` forwarding to `catalog_sync.py` and `catalog_audit.py`.
  - Re-export public symbols and helper functions in `__all__`.
- [x] 4.4.5 Verify catalog unit tests: `.venv/bin/pytest tests/unit/test_loop_catalog.py tests/unit/test_catalog_asset_only_composition.py -v`.

---

### Unit 4.5: `src/media/hybrid_engine.py` Decomposition (928L -> `src/media/`)

- [x] 4.5.1 **[RED]** Create/update tests in `tests/unit/test_ken_burns_canonical.py` and `tests/unit/test_hybrid_ffmpeg_camera_path.py` specifying:
  - Ken Burns zoompan filter generation emitting atomic single-pass filter complex strings without intermediate frame dumps.
  - Atmospheric overlay asset resolution and alpha opacity clamping ($0.05 - 0.25$).
  - Stream-copy preservation (`-c:v copy`) when subtitles are inactive and overlays are absent (satisfying REG-13).
  - Volatile `/dev/shm` RAM temp storage allocation for intermediate audio and single-pass EBU R128 audio mastering.
- [x] 4.5.2 **[GREEN]** Implement `src/media/ken_burns.py` (~150 lines):
  - `canonical_ken_burns_params(shot_type, duration_sec) -> dict`: Zoom start/end and pan coordinate generation.
  - `build_ken_burns_zoompan_filter(params, width, height, fps) -> str`: Single-pass atomic FFmpeg `zoompan` filter complex expression.
  - `plan_ken_burns_still_segments(scene_plan) -> list[dict]`: Timing and keyframe planning for still-image motion passes.
- [x] 4.5.3 **[GREEN]** Implement `src/media/overlays.py` (~160 lines):
  - `_hybrid_overlay_search_roots() -> list[Path]`: Overlay asset search directory discovery.
  - `resolve_hybrid_overlay_asset(mood, theme) -> Path | None`: Mood/thematic overlay resolution.
  - `clamp_atmospheric_overlay_opacity(opacity: float) -> float`: Opacity safe ceiling enforcement ($0.05 - 0.25$).
  - `is_motion_loop_path(path) -> bool` and `resolve_hybrid_motion_loop(theme, orientation) -> Path | None`.
- [x] 4.5.4 **[GREEN]** Refactor `src/media/hybrid_engine.py` facade (~350 lines):
  - Retain `HybridVideoEngine` orchestrating scene composition, stream-copy muxing (`-c:v copy`), and libass subtitle burning.
  - Retain `HybridVideoError`.
  - Maintain asynchronous stderr draining reader threads to prevent REG-06 pipe deadlocks.
  - Re-export public symbols in `__all__`.
- [x] 4.5.5 Verify hybrid engine and Ken Burns unit tests: `.venv/bin/pytest tests/unit/test_ken_burns_canonical.py tests/unit/test_hybrid_ffmpeg_camera_path.py -v`.

---

### Unit 4.6: `src/core/profiling.py` Decomposition (921L -> `src/core/profiling/`)

- [x] 4.6.1 **[RED]** Create/update tests in `tests/unit/test_profiling.py` specifying:
  - Low-level Linux `/proc/self/status` VmRSS and VmHWM memory reading and CPU clock time sampling.
  - Synthetic benchmark cycle execution harness asserting resource consumption stays within $\le 2\text{ Cores}$ and $\le 2.0\text{ GiB RAM}$ (satisfying REG-14).
  - Profiling context managers (`PhaseTimer`, `profile_phase`) and `PipelineProfiler` metrics aggregation across 13 stages.
- [x] 4.6.2 **[GREEN]** Implement `src/core/profiling/metrics_sampler.py` (~120 lines):
  - `_read_vm_rss_bytes() -> int`: Parse `/proc/self/status` for instantaneous VmRSS bytes.
  - `_get_peak_rss_bytes() -> int`: Parse VmHWM or fallback to `getrusage()`.
  - `_get_cpu_times() -> tuple[float, float]`: Read user and system CPU times.
  - `_sync_bytes_mb(bytes_val) -> float`: Format bytes to MiB with decimal precision.
  - `_utc_now_iso() -> str`: ISO-8601 UTC timestamp generator.
- [x] 4.6.3 **[GREEN]** Implement `src/core/profiling/benchmarking.py` (~140 lines):
  - `run_benchmark_cycle(iterations=5) -> dict`: Synthetic execution harness running end-to-end benchmark loops across pipeline stages, asserting resource budget adherence.
- [x] 4.6.4 **[GREEN]** Create `src/core/profiling/__init__.py` and refactor `src/core/profiling.py` facade (~280 lines):
  - Maintain `CanonicalStage` (stages 1 to 13), `PhaseMetrics`, `ProfilingSummary`, `PhaseTimer`, and `PipelineProfiler`.
  - Re-export all public classes, context managers, and functions in `__all__`.
- [x] 4.6.5 Verify profiling unit tests: `.venv/bin/pytest tests/unit/test_profiling.py -v`.

---

## Phase 5: Verification & Integrity Audit

- [x] 5.1 Run all targeted unit test suites across decomposed modules and sanitized subsystems:
  ```bash
  .venv/bin/pytest tests/unit/test_youtube_uploader.py \
                   tests/unit/test_script_curator.py \
                   tests/unit/test_scoring.py \
                   tests/unit/test_loop_catalog.py \
                   tests/unit/test_ken_burns_canonical.py \
                   tests/unit/test_profiling.py \
                   tests/unit/test_architectural_specs.py \
                   tests/unit/test_channels_lanes.py \
                   tests/unit/test_purge_channels.py -v
  ```
- [x] 5.2 Execute MCP tool synchronization check to assert 100% bidirectional parity across tools, resources, and prompts:
  ```bash
  .venv/bin/python3 scripts/verify_mcp_sync.py
  ```
- [x] 5.3 Execute anti-regression test suite to verify all 14 anti-regression invariants (REG-01 to REG-14):
  ```bash
  .venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v
  ```
- [x] 5.4 Execute offline stream-copy video generation smoke tests across all six canonical thematic lanes:
  ```bash
  python3 main.py run -c horror --lane horror-scp-shorts --generate-only
  python3 main.py run -c horror --lane horror-horror-long --generate-only
  python3 main.py run -c drama --lane drama-drama-shorts --generate-only
  python3 main.py run -c drama --lane drama-aita-long --generate-only
  python3 main.py run -c scifi --lane scifi-singularity-shorts --generate-only
  python3 main.py run -c scifi --lane scifi-singularity-long --generate-only
  ```
- [x] 5.5 Execute mandatory project integrity audit:
  ```bash
  ./scripts/verify_integrity.sh
  ```
- [x] 5.6 Audit codebase line reduction metrics and function granularity budget:
  - Verify net reduction $> 1,500$ lines in Python code and $> 800$ lines in documentation.
  - Audit function line lengths using AST inspection to ensure 100% of functions across decomposed modules adhere to $\le 100$ executable lines.

