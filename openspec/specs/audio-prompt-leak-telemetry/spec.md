# Specification: Audio Prompt Leak Telemetry

## Capability Overview
The `audio-prompt-leak-telemetry` capability intercepts prompt leaks, taboo instruction echoes, and meta-commentary detected by pre-TTS semantic barriers in `src/sanitizer/security.py` and `src/sanitizer/tts.py`. Whenever `PromptLeakError` is raised, this capability logs a structured `audio_prompt_leak` event to `system_events` capturing the offending snippet, matched pattern, AI model, and story/channel context, enabling automated frequency tracking across models and channels.

## Requirements

### Requirement 1: Interception of PromptLeakError in Pre-TTS Semantic Barrier
The pre-TTS script validation routines (`validate_pre_tts_script` in `src/sanitizer/tts.py` and `validate_semantic_barrier` in `src/sanitizer/security.py`) MUST intercept `PromptLeakError` before propagating it to the pipeline caller.

1. When a taboo barrier pattern (`TABOO_BARRIER_PATTERNS`) or prompt leak regex (`PROMPT_LEAK_PATTERNS`) matches inside candidate narration text:
   - The validator MUST extract the matched substring snippet (up to 120 characters) and the name or regex pattern that matched.
   - The validator MUST intercept the `PromptLeakError` to trigger incident logging.
   - The validator MUST re-raise the original `PromptLeakError` after logging so invalid text is never sent to audio synthesis engines.

#### Scenario: Script containing director meta-cue raises PromptLeakError
- **Given** candidate narration script containing `"Aquí tienes tu guion sin etiquetas para el locutor"`
- **When** `validate_pre_tts_script()` processes the text
- **Then** `PromptLeakError` MUST be raised
- **And** the matched pattern identifier and snippet MUST be extracted.

---

### Requirement 2: Structured Incident Emission (audio_prompt_leak)
Upon catching a `PromptLeakError`, the validator or pipeline stage wrapper MUST emit an `audio_prompt_leak` event into `system_events`.

1. The emitted record MUST have:
   - `event_type`: `'audio_prompt_leak'`
   - `level`: `'WARNING'`
   - `channel`: Canonical channel identifier of the active job
   - `story_id`: Active story ID (if available)
   - `run_id`: Active run ID (if available)
   - `stage`: Current stage identifier (`'stage_2_script'` or `'stage_4_audio'`)
   - `message`: Summary describing the detected leak pattern
   - `details_json`: Structured JSON containing:
     - `matched_pattern`: The regex or rule that triggered
     - `leak_snippet`: The offending text excerpt (truncated for security/log compactness)
     - `model`: AI model that generated the text (e.g. `'gemini-2.5-pro'`)
     - `provider`: AI provider identifier (e.g. `'antigravity_pro'`)
2. Logging MUST execute via non-blocking SQLite insertion with `try/except` guard to ensure database logging errors never mask the security exception.

#### Scenario: Emitting structured audio_prompt_leak event to system_events
- **Given** an AI script generator produces text matching `(?i)como modelo de lenguaje`
- **When** pre-TTS validation catches the violation during run `run-555` on channel `scifi`
- **Then** an event with `event_type = 'audio_prompt_leak'` MUST be written to `system_events`
- **And** `details_json` MUST contain the snippet `"como modelo de lenguaje"`
- **And** `channel` MUST equal `'scifi'`.

---

### Requirement 3: Multi-Dimensional Aggregation by Model, Provider, and Channel
The repository and telemetry collector MUST provide queries aggregating prompt-leak incidents over selectable timeframes.

1. The repository MUST support aggregating prompt-leak frequency grouped by:
   - Model name (`model`)
   - Provider (`provider`)
   - Channel (`channel`)
   - Matched leak category (`taboo_phrase`, `instruction_echo`, `reasoning_monologue`)
2. The tube collector MUST include the prompt leak count and recent leak snippets in the operational snapshot (`TubeSnapshot`).

#### Scenario: Aggregating prompt leak counts over a 24-hour observation window
- **Given** 4 prompt leak events recorded for `gemini-2.5-pro` and 1 for `grok-2` over the preceding 24 hours
- **When** `query_prompt_leak_summary(window_hours=24)` is executed
- **Then** total leaks MUST equal 5
- **And** the breakdown MUST identify 4 occurrences from `gemini-2.5-pro` and 1 from `grok-2`.

---

### Requirement 4: Operational Alert Escalation for Prompt Leak Clusters
When repeated prompt leaks occur within a short time window on the same channel or model, an operational alert MUST be triggered.

1. If $> 3$ prompt leaks are detected within a 30-minute window for a specific model or channel:
   - An operational warning MUST be dispatched to human operators via Telegram alerting (`send_operational_alert`).
   - The alert message MUST list the model, channel, and matched pattern snippets to indicate potential prompt drift or system prompt degradation.

#### Scenario: Leak cluster triggers Telegram operational alert
- **Given** 3 prompt leak events logged on channel `horror` within 15 minutes
- **When** the 4th prompt leak event is recorded within the same window
- **Then** `send_operational_alert()` MUST be invoked with an operational warning
- **And** the alert payload MUST include the leak frequency and affected model.
