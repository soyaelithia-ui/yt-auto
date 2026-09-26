# Tasks: Agentic Harness & Local Text-Free Cover Standardization

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~850 - 1,100 lines (~400 lines deleted/sanitized, ~280 lines agentic harness, ~160 lines thumbnail hardening, ~200 lines tests) |
| 400-line budget risk | Medium |
| Decision needed before apply | No |
| Chained PRs recommended | No |
| Chain strategy | size-exception |
| Delivery strategy | single-pr |

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Zero Real-Time Graphics Eradication & Guardrails | PR 1 (Unit 1) | `.venv/bin/pytest tests/unit/test_zero_procedural_math_video_policy.py -v` | Filesystem & JSON schema validation runner | Restore `assets/svg_overlays`, `assets/overlays`, revert `schemas/` |
| 2 | Antigravity SDK Agentic Harness Implementation | PR 1 (Unit 2) | `.venv/bin/pytest tests/unit/test_agent_recovery_policy.py -v` | In-memory agent loop simulator with mocked NDJSON stream / SDK chat | Revert `src/agents/base_agent.py`, `tests/unit/test_agent_recovery_policy.py` |
| 3 | Creative Agent Refocusing & Diffusion Prompt Purge | PR 1 (Unit 3) | `.venv/bin/pytest tests/unit/test_atmospheric_director.py -v` | Script-to-atmosphere catalog evaluation harness | Revert `src/agents/atmospheric_director.py`, `src/agents/seo_optimizer.py`, `src/narrative/` |
| 4 | Text-Free Local Cover Bank & Thumbnail Engine Hardening | PR 1 (Unit 4) | `.venv/bin/pytest tests/unit/test_asset_only_pipeline.py -v` | Temporary image bank filesystem fixture with sidecar metadata | Revert `src/media/thumbnails/ai_bank.py`, `src/media/thumbnails/engine.py`, `src/media/thumbnail_engine.py` |
| 5 | End-to-End Verification, Guardrails & Integrity Audit | PR 1 (Unit 5) | `./scripts/verify_integrity.sh --fast && .venv/bin/pytest tests/unit/test_agent_recovery_policy.py tests/unit/test_zero_procedural_math_video_policy.py tests/unit/test_asset_only_pipeline.py -v` | Complete repository pre-commit integrity gate and operational budget validator | Revert commit range for change `agentic-harness-local-covers` |

---

## Phase 1: Zero Real-Time Graphics Eradication & Guardrails

- [x] Task 1.1: **[RED]** Extend `tests/unit/test_zero_procedural_math_video_policy.py` with overlay eradication and schema assertions:
  - Add assertion `assert not (REPO_ROOT / "assets" / "svg_overlays").exists()` asserting complete deletion of `assets/svg_overlays/`.
  - Add assertion `assert not (REPO_ROOT / "assets" / "overlays").exists()` asserting complete deletion of `assets/overlays/`.
  - Add test `test_zero_shader_remnants_in_schemas`: parse `schemas/art_director.schema.json` and `schemas/scene_planner.schema.json`, asserting absence of `image_prompts`, `archetype_id` (WGSL enum), `uniform_params`, and `shader_seed`.
  - Focused test command: `.venv/bin/pytest tests/unit/test_zero_procedural_math_video_policy.py -v` (Fails RED).
  - Concrete edit target: `tests/unit/test_zero_procedural_math_video_policy.py`.
  - Concrete inspection target: `schemas/art_director.schema.json` (read-only).

- [x] Task 1.2: **[GREEN]** Permanently delete obsolete graphics and overlay directories:
  - Remove directory `assets/svg_overlays/` (`biometric_wave.svg`, `hud_tactical_telemetry.svg`, `scp_classification_stamp.svg`).
  - Remove directory `assets/overlays/` (`motion/`, `static/`, `.gitkeep`).
  - Ensure zero residual SVG templates or overlay files remain staged or untracked in those directories.
  - Concrete edit targets: Filesystem removal of `assets/svg_overlays/` and `assets/overlays/`.

- [x] Task 1.3: **[GREEN]** Harden repository guardrails in `src/verification/guardrails.py`:
  - Update `check_zero_procedural_math(repo_root: Path, paths: Optional[List[str]] = None)`:
    - Add `assets/svg_overlays` and `assets/overlays` to forbidden directory list.
    - Check staged paths (when `paths is not None`) and disk directory existence (when `paths is None`).
    - Emit descriptive violation messages if any overlay directory or asset is present.
  - Concrete edit target: `src/verification/guardrails.py`.

- [x] Task 1.4: **[GREEN]** Sanitize active JSON schemas:
  - In `schemas/art_director.schema.json`:
    - Remove `image_prompts` (positive_prompt, negative_prompt) from `properties` and `required`.
    - Remove `archetype_id` WGSL enum and `uniform_params`.
    - Ensure schema enforces catalog `loop_category`, `audio_theme`, `mood_summary`, `accent_hex`, and `pacing` with `additionalProperties: false`.
  - In `schemas/scene_planner.schema.json`:
    - Remove `shader_seed` under visual asset properties.
    - Remove `shader` under `volumetric_lighting`.
    - Ensure procedural engine identifiers are purged from engine enum.
  - Concrete edit targets: `schemas/art_director.schema.json`, `schemas/scene_planner.schema.json`.

- [x] Task 1.5: **[VERIFY]** Run Phase 1 verification suite:
  - Command: `.venv/bin/pytest tests/unit/test_zero_procedural_math_video_policy.py -v`.
  - Command: `./scripts/verify_integrity.sh --fast`.
  - Assert 100% GREEN pass across all zero-graphics and procedural math invariants.

---

## Phase 2: Antigravity SDK Agentic Harness Implementation

- [x] Task 2.1: **[RED]** Extend `tests/unit/test_agent_recovery_policy.py` with comprehensive agentic harness contracts:
  - `test_recovery_decision_dataclass_attributes`: Verify `RecoveryDecision` slots/fields (`action`, `reason`, `attempt`, `correction_count`, `adjustments`, `rationale`, `timestamp`) and `as_trace_record(error)` serialization.
  - `test_recovery_policy_decide_routing`:
    - Transient transport failure -> `action="retry"`, `reason="transient_execution_failure"`.
    - First schema validation failure -> `action="correct"`, `reason="structured_output_validation"`.
    - Repeated validation failure with prior correction history -> `action="adjust"`, `reason="semantic_drift_adjustment"`, containing `adjustments={"temperature": 0.1, "reasoning_effort": "medium", "compact_context": True}`.
    - Saturation signal (`429`, `RESOURCE_EXHAUSTED`) -> `action="stop"`, `reason="provider_saturation"`.
    - Budget exhaustion (`attempt >= max_attempts` or `correction_count >= max_corrections`) -> `action="stop"`, `reason="recovery_budget_exhausted"`.
  - `test_agentic_self_adjustment_hyperparameter_adaptation`: Mock `_chat_cli_fallback` / `_chat_async` to simulate repeated validation failures, asserting that adjusted hyperparameters (`temperature=0.1`, `compact_context=True`) are applied to subsequent turns.
  - `test_agent_fail_closed_on_budget_exhaustion`: Assert that when `max_attempts` is exhausted, the harness records fail-closed evidence and raises `AIProviderChainExhausted`.
  - `test_decision_trace_telemetry_persisted_in_task_result`: Verify `task_result.json` contains `failure_evidence["decision_trace"]` list of structured trace records (`attempt`, `action`, `reason`, `error`, `adjustments`, `rationale`, `timestamp`) and `failure_evidence["recovered"]`.
  - `test_circuit_breaker_isolation_and_immediate_saturation_trip`: Verify `CircuitBreaker.get(instance_id)` provides strict instance isolation, and `record_failure("RESOURCE_EXHAUSTED")` opens immediately without waiting for `failure_threshold`.
  - Focused test command: `.venv/bin/pytest tests/unit/test_agent_recovery_policy.py -v` (Fails RED).
  - Concrete edit target: `tests/unit/test_agent_recovery_policy.py`.

- [x] Task 2.2: **[GREEN]** Implement enhanced `RecoveryDecision` and declarative `AgentRecoveryPolicy.decide()` in `src/agents/base_agent.py`:
  - Define `AIProviderChainExhausted(RuntimeError)` exception class.
  - Update `RecoveryDecision` dataclass:
    - Add `adjustments: dict[str, Any] = field(default_factory=dict)`.
    - Add `rationale: str = ""`.
    - Add `timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())`.
    - Implement `as_trace_record(self, error: str) -> dict[str, Any]`.
  - Update `AgentRecoveryPolicy.decide(self, error: str, *, attempt: int, correction_count: int, failure_history: Optional[list[dict[str, Any]]] = None) -> RecoveryDecision`:
    - Classify saturation signals (`is_saturation_text(detail)`): `action="stop"`, `reason="provider_saturation"`.
    - Classify attempt budget exhaustion (`attempt >= self.max_attempts`): `action="stop"`, `reason="recovery_budget_exhausted"`.
    - Classify validation errors (`detail.startswith("validation:")`):
      - If `correction_count >= self.max_corrections`: `action="stop"`, `reason="recovery_budget_exhausted"`.
      - If `failure_history` contains prior correction action: `action="adjust"`, `reason="semantic_drift_adjustment"`, `adjustments={"temperature": 0.1, "reasoning_effort": "medium", "compact_context": True}`.
      - Else: `action="correct"`, `reason="structured_output_validation"`.
    - Classify transient socket/network failures: `action="retry"`, `reason="transient_execution_failure"`.
  - Concrete edit target: `src/agents/base_agent.py`.

- [x] Task 2.3: **[GREEN]** Wire autonomous self-adjustment (`autoajustarse`) and multi-turn correction (`corregir fallos`) into `ProgrammaticAgent._run_async()`:
  - Initialize `decision_trace: list[dict[str, Any]] = []` and stateful runtime adjustments mapping.
  - On `decision.action == "adjust"`:
    - Update current hyperparameter overrides (e.g. `temperature = decision.adjustments.get("temperature", 0.1)`).
    - If `compact_context` is true, compact prompt payload before re-invoking.
    - Append decision trace record.
    - Increment `attempt += 1`.
  - On `decision.action == "correct"`:
    - Synthesize targeted correction prompt: `f"{task}\n\nCorrection required: the previous response failed the declared contract ({detail}). Return only a corrected response."`
    - Append decision trace record.
    - Increment `correction_count += 1`, `attempt += 1`.
  - On `decision.action == "retry"`:
    - Pause for `self.recovery_policy.retry_delay_seconds`.
    - Append decision trace record.
    - Increment `attempt += 1`.
  - On `decision.action == "stop"`:
    - Append decision trace record.
    - Trip circuit breaker if reason is `provider_saturation`.
    - If reason is `recovery_budget_exhausted` and error present, raise `AIProviderChainExhausted(detail)` or record fail-closed doc.
  - Concrete edit target: `src/agents/base_agent.py`.

- [x] Task 2.4: **[GREEN]** Persist complete decision trace telemetry in `task_result.json`:
  - Ensure `failure_evidence` dictionary contains:
    - `policy`: snapshot of active policy configuration (`max_attempts`, `max_corrections`, `retry_delay_seconds`).
    - `decision_trace`: full chronological list of records from `decision.as_trace_record(detail)`.
    - `attempts`: backward-compatible list of attempt records.
    - `recovered`: boolean flag (`True` if initial failures occurred and recovery succeeded, `False` otherwise).
  - Write `task_result.json` atomically via `_build_result()` and `self.task_result_path.write_text()`.
  - Concrete edit target: `src/agents/base_agent.py`.

- [x] Task 2.5: **[GREEN]** Harden instance-keyed `CircuitBreaker` saturation governance:
  - In `CircuitBreaker.record_failure(self, error_text: str = "")`:
    - Check `is_saturation_text(error_text)`.
    - If saturated, immediately set `self._open_until = time.time() + self.cooldown_seconds` without requiring $N$ failures.
  - Maintain thread safety with `_lock` and per-instance registry `_instances: dict[str, CircuitBreaker]`.
  - Implement `CircuitBreaker.reset_all()` to facilitate clean test isolation.
  - Concrete edit target: `src/agents/base_agent.py`.

- [x] Task 2.6: **[VERIFY]** Run Phase 2 agentic harness test suite:
  - Command: `.venv/bin/pytest tests/unit/test_agent_recovery_policy.py -v`.
  - Assert 100% GREEN pass across all recovery decision, self-adjustment, circuit breaker, and decision trace telemetry assertions.

---

## Phase 3: Creative Agent Refocusing & Diffusion Prompt Purge

- [x] Task 3.1: **[RED]** Create unit test suite for refocused creative agents and sanitized narrative engines in `tests/unit/test_creative_agents_refocus.py`:
  - `test_atmospheric_director_emits_pure_catalog_and_audio`: Verify `AtmosphericDirectorAgent.curate_atmosphere()` (or `plan_visuals()`) returns `loop_category`, `audio_theme`, `mood_summary`, `accent_hex`, and `pacing`, with zero `image_prompts`, zero `positive_prompt`, zero `negative_prompt`, zero `uniform_params`, and zero WGSL archetype names.
  - `test_seo_optimizer_emits_text_free_thumbnail_request`: Verify `SeoOptimizerAgent` emits `thumbnail_asset_request` with `text_free=True`, and zero typography layout, font, or badge properties.
  - `test_narrative_engine_emits_scenes_without_shader_sequence`: Verify `NarrativeEngine` presets and generated scene acts contain zero `shader_sequence`, `shader_id`, or `shader_params`.
  - Focused test command: `.venv/bin/pytest tests/unit/test_creative_agents_refocus.py -v` (Fails RED).
  - Concrete edit target: `tests/unit/test_creative_agents_refocus.py` (new test file).

- [x] Task 3.2: **[GREEN]** Purge diffusion prompts, WGSL archetypes, and uniform params from `src/agents/atmospheric_director.py`:
  - Remove `image_prompts` (`positive_prompt`, `negative_prompt`), camera lens parameters (`focal_length_mm`, `depth_of_field`), and `uniform_params` generation from `plan_visuals()`.
  - Remove `_resolve_canonical_archetype()` WGSL mapping function.
  - Refocus agent contract strictly on:
    - `loop_category`: curated catalog loop category (`cosmic_horror`, `dark_ambient`, `tactical_chamber`, `dramatic_interior`).
    - `audio_theme`: acoustic soundscape (`drone_abyss`, `dark_ambient`, `tension_pulse`).
    - `mood_summary`, `accent_hex`, and `pacing`.
  - Concrete edit target: `src/agents/atmospheric_director.py`.

- [x] Task 3.3: **[GREEN]** Enforce strictly text-free thumbnail metadata requests in `src/agents/seo_optimizer.py`:
  - Audit output schema and prompt instructions to guarantee `thumbnail_asset_request` contains only `bank`, `archetype`, `focal_subject`, `color_palette`, and `text_free: true`.
  - Forbid all typography formatting, headline positioning, subtitle styling, or badge text fields.
  - Concrete edit target: `src/agents/seo_optimizer.py`.

- [x] Task 3.4: **[GREEN]** Sanitize narrative engine presets, schemas, and scene generation:
  - In `src/narrative/archetypes.py`:
    - Remove `"shader_sequence"` lists from `SCP_DOCUMENTARY_V1`, `CREEPYPASTA_HORROR_V1`, and `COSMIC_VOID_V1`. Replace with clean editorial visual directives.
  - In `src/narrative/engine.py`:
    - Remove `shader_sequence` extraction, `shader_id` assignments, and procedural shader mappings from scene acts construction.
  - In `src/narrative/schema.py`:
    - Remove `shader_id` and `shader_params` fields from `NarrativeScene`, `SceneAct`, and `ActTimelineEntry` dataclasses.
  - In `src/narrative/schema.json`:
    - Remove `shader_id` and `shader_params` from schema properties and required lists.
  - Concrete edit targets: `src/narrative/archetypes.py`, `src/narrative/engine.py`, `src/narrative/schema.py`, `src/narrative/schema.json`.

- [x] Task 3.5: **[VERIFY]** Run Phase 3 creative agent and narrative verification:
  - Command: `.venv/bin/pytest tests/unit/test_creative_agents_refocus.py -v`.
  - Assert 100% GREEN pass across all creative agent and narrative sanitization tests.

---

## Phase 4: Text-Free Local Cover Bank & Thumbnail Engine Hardening

- [x] Task 4.1: **[RED]** Extend `tests/unit/test_asset_only_pipeline.py` with sidecar enforcement, token filtering, and text-free rendering contracts:
  - `test_local_ai_bank_rejects_missing_sidecar`: Assert that candidate image files lacking an adjacent `.json` sidecar are excluded by `LocalAIThumbnailBank.is_text_free()` and `candidates()`.
  - `test_local_ai_bank_rejects_forbidden_token_filenames`: Assert that filenames containing forbidden tokens (`text`, `title`, `caption`, `subtitle`, `badge`, `watermark`, `logo`, `overlay`) are excluded even if sidecars declare text_free: true.
  - `test_local_ai_bank_rejects_sidecar_with_text_free_false`: Assert that assets whose sidecar declares `{"text_free": false}` are excluded.
  - `test_local_ai_bank_path_traversal_prevention`: Assert that queries containing `../` traversal cannot escape `self.root`.
  - `test_thumbnail_engine_pure_text_free_rendering`: Assert that `ThumbnailEngine.generate()` and `ResilientThumbnailEngine.generate()` never perform text drawing, font loading, or badge rendering.
  - Focused test command: `.venv/bin/pytest tests/unit/test_asset_only_pipeline.py -v` (Fails RED).
  - Concrete edit target: `tests/unit/test_asset_only_pipeline.py`.

- [x] Task 4.2: **[GREEN]** Enforce mandatory sidecar verification and token filtering in `src/media/thumbnails/ai_bank.py`:
  - In `LocalAIThumbnailBank._name_is_clean(path: Path) -> bool`:
    - Check token set intersection against `_REJECTED_NAME_TOKENS`.
    - Check substring containment (`any(t in stem for t in _REJECTED_NAME_TOKENS)`) for defense-in-depth.
  - In `LocalAIThumbnailBank.is_text_free(path: Path) -> bool`:
    - Reject non-image extension or unclean filename.
    - Enforce sidecar `.json` existence: if sidecar does not exist on disk, return `False`.
    - Validate sidecar metadata: verify `metadata.get("text_free") is True`.
    - Verify image file integrity via `Image.open(path).verify()`.
  - In `LocalAIThumbnailBank.candidates(channel_id, archetype)`:
    - Protect against path traversal: verify all candidate paths are relative to `self.root.resolve()`.
  - In `LocalAIThumbnailBank.resolve(channel_id, archetype, selection_key)`:
    - Maintain deterministic SHA-256 hash selection.
  - Concrete edit target: `src/media/thumbnails/ai_bank.py`.

- [x] Task 4.3: **[GREEN]** Harden `ThumbnailEngine` in `src/media/thumbnails/engine.py`:
  - In `ThumbnailEngine.generate()`:
    - Assert `config.text_free is True`; raise `ValueError("ThumbnailConfig.text_free must remain true; printed cover text is retired")` otherwise.
    - Confirm zero font loading, zero `ImageDraw.Draw.text()`, and zero badge rendering.
    - Execute purely local asset resolution (`LocalAIThumbnailBank` -> fallback `ThematicAssetResolver`), Lanczos fitting to canvas, and `ChiaroscuroColorGrader` contrast/vignette grading.
  - Strip unused typography fields from `ThumbnailConfig` or mark them strictly ignored.
  - Concrete edit target: `src/media/thumbnails/engine.py`.

- [x] Task 4.4: **[GREEN]** Harden `ResilientThumbnailEngine` in `src/media/thumbnail_engine.py`:
  - Refactor `ResilientThumbnailEngine.generate()`:
    - Strip deprecated text parameters (`highlight_box`, `badge_text`, `subtitle_color`, `badge_color`, `custom_font_paths`).
    - Forward `title` as deterministic `selection_key` only.
    - Strictly delegate rendering to `self._engine.generate(ThumbnailConfig(..., text_free=True))`.
  - Concrete edit target: `src/media/thumbnail_engine.py`.

- [x] Task 4.5: **[VERIFY]** Run Phase 4 text-free thumbnail verification suite:
  - Command: `.venv/bin/pytest tests/unit/test_asset_only_pipeline.py -v`.
  - Assert 100% GREEN pass across all text-free bank and thumbnail engine tests.

---

## Phase 5: End-to-End Verification, Guardrails & Integrity Audit

- [x] Task 5.1: **[RED]** Extend anti-regression guardrail tests in `tests/unit/test_anti_regression_guardrails.py` (or `test_zero_procedural_math_video_policy.py`):
  - Add test asserting `assets/svg_overlays` and `assets/overlays` directories do not exist on disk.
  - Add test asserting `schemas/art_director.schema.json` and `schemas/scene_planner.schema.json` contain zero shader remnants.
  - Add test asserting `ProgrammaticAgent` records `decision_trace` in `task_result.json` and enforces bounded attempt ceilings.
  - Add test asserting `LocalAIThumbnailBank` excludes assets without sidecars.
  - Focused test command: `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py tests/unit/test_zero_procedural_math_video_policy.py -v`.
  - Concrete edit target: `tests/unit/test_anti_regression_guardrails.py` (or `tests/unit/test_zero_procedural_math_video_policy.py`).

- [x] Task 5.2: **[GREEN]** Validate resource budget compliance and stream-copy composition:
  - Verify `LoopVideoEngine` stream-copy (`-c:v copy`) assembly produces lossless video without video transcoding churn:
    - Peak CPU utilization $\le 2.0$ Cores ($\le 200\%$).
    - Resident memory (RSS) $\le 2.0$ GiB ($2,048$ MiB peak).
    - Subtitles soft-multiplexed as `-c:s mov_text`.
  - Concrete inspection targets: `src/media/loop_engine.py`, `src/media/loop/stream_copy.py`.

- [x] Task 5.3: **[GREEN]** Execute repository pre-commit integrity audit:
  - Run `./scripts/verify_integrity.sh --fast`.
  - Run `python3 -m src.verification.guardrails`.
  - Verify all invariant checks pass: Git worktree hygiene, architecture docs, zero legacy subsystems, zero browser policy, zero procedural math policy, anti-bloat, secret hygiene, and MCP sync.
  - Concrete command: `./scripts/verify_integrity.sh --fast`.

- [x] Task 5.4: **[VERIFY]** Run full test suite across all affected contracts:
  - Command: `.venv/bin/pytest tests/unit/test_agent_recovery_policy.py tests/unit/test_zero_procedural_math_video_policy.py tests/unit/test_asset_only_pipeline.py tests/unit/test_creative_agents_refocus.py -v`.
  - Assert 100% GREEN pass with zero regressions across the codebase.
