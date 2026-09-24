# Tasks: Longform Visual Quality and CPU Optimization (Hybrid Multi-Act Director)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

## Review Workload Forecast & Suggested Work Units

| Work Unit / PR | Scope / Description | Edit Targets | Focused Test Command | Runtime Harness | Rollback Boundary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PR 1: Foundation & Act Narrative Contracts** | 4–8 act narrative script curation, dynamic act decomposition, progressive tension curves (1–5), proportional duration scaling with zero audio drift. | `src/curators/curation_profiles.py`<br>`src/curators/text_splitter.py`<br>`tests/unit/test_longform_multi_act.py` | `.venv/bin/pytest tests/unit/test_longform_multi_act.py -k "test_act_partitioning or test_proportional_duration" -v` | Offline Python / pytest | Revert to 4-fixed-act curation profiles in `curation_profiles.py` without dynamic act scaling. |
| **PR 2: Stage 04 Thematic Loop Resolution & Engine Routing** | Removal of crude director-to-loop engine coercion, multi-act catalog loop resolution with tension mapping, modulo rotation fallback, `FORCE_SINGLE_LOOP` killswitch. | `src/pipeline/utils.py`<br>`src/pipeline/executor.py`<br>`src/media/loop/rotation.py`<br>`src/pipeline/stages/stage_04_mood.py`<br>`assets/loops/bank_manifest.json`<br>`tests/unit/test_longform_multi_act.py` | `.venv/bin/pytest tests/unit/test_longform_multi_act.py -k "test_multi_loop or test_engine_mode or test_killswitch" -v` | `main.py run --lane horror-horror-long --generate-only` / pytest | Set `FORCE_SINGLE_LOOP=1` env var or configure `"visual_pipeline": "video_loop"` in `config/lanes.json`. |
| **PR 3: Stage 08 & Stage 09 Concat Assembly & Subtitle Muxing** | Multi-scene concat manifest generation, stream-copy (`-c:v copy`) concatenation assembly, soft subtitle muxing (`-c:s mov_text`), Resource Work Refusal on longform `libass`. | `src/pipeline/stages/stage_08_loop.py`<br>`src/pipeline/stages/stage_09_render.py`<br>`src/media/loop/stream_copy.py`<br>`tests/unit/test_longform_multi_act.py` | `.venv/bin/pytest tests/unit/test_longform_multi_act.py -k "test_concat or test_soft_subtitles or test_work_refusal" -v` | FFmpeg 6.1 stream-copy harness / pytest | Revert `stage_09_render.py` and `stage_08_loop.py` to single-loop stream-copy path. |
| **PR 4: Stage 11 YouTube Chapters Metadata & Sidecar** | Extract cumulative time offsets from act durations, format YouTube chapter markers in video description, validate YouTube interactive rules, register `.srt` sidecar. | `src/pipeline/stages/stage_11_metadata.py`<br>`tests/unit/test_longform_multi_act.py` | `.venv/bin/pytest tests/unit/test_longform_multi_act.py -k "test_youtube_chapters or test_srt_sidecar" -v` | Metadata generation harness / pytest | Omit chapter block from `ctx.youtube_description` if validation fails or fallback to synopsis. |
| **PR 5: Anti-Regression Verification, Guardrails & Offline Smoke Tests** | Assert REG-01 to REG-14 invariants, verify $\le 2$ Cores / $\le 2.0$ GiB RAM budget, verify offline network isolation, execute end-to-end generate-only smoke tests. | `tests/unit/test_anti_regression_guardrails.py`<br>`tests/unit/test_longform_multi_act.py` | `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v && ./scripts/verify_integrity.sh` | Full integrity runner / pytest | Revert test assertions to prior guardrail snapshot. |

---

## Phase 1: Foundation & Act Narrative Contracts

- **Primary Goal**: Establish 4–8 act narrative script partitioning, progressive tension curves (1–5), act role assignments, and audio-aligned proportional duration scaling with zero temporal drift.
- **Affected Subsystems**: `src/curators/`, `tests/unit/`
- **Resource Envelope**: In-memory text manipulation only; CPU consumption $\approx 0.05$ Cores, peak RAM $< 50\text{ MiB}$.

### Tasks

- [x] **1.1: [RED] Create multi-act script curation unit tests**
  - **File Target**: `tests/unit/test_longform_multi_act.py`
  - Write test `test_act_partitioning_4_to_8_acts`:
    - Provide a synthetic longform narrative (2,600 to 4,800 words, target duration 1,200s / 20 min).
    - Invoke `TextSegmentationEngine.curate` with `channel_lane="horror-horror-long"` and `channel_lane="drama-aita-long"`.
    - Assert output payload contains $N$ structured acts where $4 \le N \le 8$.
    - Assert each act contains non-empty `act_title`, `dramatic_role` (`exposition_inception`, `rising_action_dread`, `confrontation_crisis`, `climax_confrontation`, `aftermath_revelation`), and `tension_level` between 1 and 5.
    - Assert tension ratings culminate in peak tension ($\text{tension} \ge 4$) before resolving.
  - Write test `test_proportional_duration_scaling_zero_drift`:
    - Given total voiceover duration $T = 845.60\text{s}$, assert sum of calculated act durations equals $T \pm 0.1\text{s}$.
    - Assert every individual act duration satisfies $\text{target\_duration}_i \ge 30.0\text{s}$.
    - Assert the final act duration is clamped precisely so cumulative drift across all acts is strictly $0.0\text{s}$.
  - Write test `test_short_narrative_subdivision`:
    - Provide a narrative yielding only 3 raw sections.
    - Assert the curator subdivides the longest section at semantic paragraph breaks to emit at least 4 valid acts.
  - **Focused Test Command**: `.venv/bin/pytest tests/unit/test_longform_multi_act.py -k "test_act_partitioning or test_proportional_duration or test_short_narrative" -v`

- [x] **1.2: [GREEN] Expand narrative profiles in `curation_profiles.py`**
  - **File Target**: `src/curators/curation_profiles.py`
  - Update `horror-horror-long` configuration in `LANE_CURATION_CONFIGS`:
    - Expand act templates from 4 fixed acts to support dynamic 4–8 act structures with dramatic roles:
      1. Act I: *Incepción Sensorial y Aislamiento* (`exposition_inception`, tension 1–2)
      2. Act II: *Advertencias Ignoradas y Señales* (`rising_action_dread`, tension 2–3)
      3. Act III: *Escalada Inexorable de la Amenaza* (`rising_action_dread`, tension 3–4)
      4. Act IV: *Confrontación Inexplicable y Ruptura* (`climax_confrontation`, tension 4–5)
      5. Act V: *Clímax Crítico y Desesperación* (`climax_breaking_point`, tension 5)
      6. Act VI: *Secuela Psicológica y Trauma Permanente* (`aftermath_revelation`, tension 2–3)
  - Update `drama-aita-long` configuration in `LANE_CURATION_CONFIGS`:
    - Expand act templates to support dynamic 4–8 act structures:
      1. Act I: *El Dilema Moral y Contexto Familiar* (`exposition_inception`, tension 1–2)
      2. Act II: *Primeras Fricciones y Demandas Injustas* (`rising_action_dread`, tension 2–3)
      3. Act III: *El Detonante y Escalada del Conflicto* (`rising_action_dread`, tension 3–4)
      4. Act IV: *Punto de Ruptura y Confrontación Directa* (`climax_confrontation`, tension 4–5)
      5. Act V: *Juicio Social y Veredicto Comunitario* (`climax_confrontation`, tension 4–5)
      6. Act VI: *Reflexión Final y Actualización Posterior* (`aftermath_revelation`, tension 1–2)
  - Add strongly typed dataclass `ActNarrativePlan(slots=True, frozen=True)` to codify inter-stage act data transfer.

- [x] **1.3: [GREEN] Implement dynamic act building in `text_splitter.py`**
  - **File Target**: `src/curators/text_splitter.py`
  - In `TextSegmentationEngine._build_acts`:
    - Detect longform lanes ($T \ge 600\text{s}$ or `target_format == "longform"`).
    - Dynamically calculate the target act count $N \in [4, 8]$ based on `len(scene_texts)` and total estimated duration:
      $$N = \max(4, \min(8, \operatorname{round}(\text{total\_words} / 500)))$$
    - Distribute scenes across $N$ acts using `distribute_scenes_across_acts`.
    - Apply semantic paragraph subdivision when raw text yields fewer than 4 narrative chunks to guarantee $\ge 4$ acts.
    - Enforce proportional duration scaling: scale each act's `estimated_duration_sec` to match the target voiceover duration, clamping the final act to ensure total drift is $0.0\text{s}$.
  - Verify Draft-07 schema compliance (`schemas/script_curator.schema.json` `(read-only)`).

- [x] **1.4: [VERIFY] Run Phase 1 verification suite**
  - Execute: `.venv/bin/pytest tests/unit/test_longform_multi_act.py -k "test_act_partitioning or test_proportional_duration or test_short_narrative" -v`
  - Verify all tests pass with zero warnings.

---

## Phase 2: Stage 04 Thematic Loop Resolution & Engine Routing

- **Primary Goal**: Eliminate crude director-to-loop engine coercion, resolve distinct thematic horizontal catalog loops per narrative act based on dramatic role and tension (1–5), implement seeded modulo fallback, and provide a clean `FORCE_SINGLE_LOOP` killswitch.
- **Affected Subsystems**: `src/pipeline/`, `src/media/loop/`, `assets/loops/`, `tests/unit/`
- **Resource Envelope**: Catalog metadata query only; turnaround $< 0.1\text{s}$, CPU $< 0.05$ Cores, peak RAM $< 50\text{ MiB}$.

### Tasks

- [x] **2.1: [RED] Add engine routing and multi-loop resolution tests**
  - **File Target**: `tests/unit/test_longform_multi_act.py`
  - Write test `test_engine_resolution_director_mode`:
    - Given a lane with `orientation="horizontal"` and `visual_pipeline="director"` (`horror-horror-long` or `drama-aita-long`).
    - Invoke `_resolve_engine_mode(lane, video_engine="director", compositor=None)`.
    - Assert `engine_mode == "director"`, `is_multiscene_mode is True`, `is_loop_mode is False` without requiring `FORCE_MULTISCENE=1`.
  - Write test `test_resolve_multi_act_loops_thematic`:
    - Given a 5-act narrative with tension ratings $[1, 2, 3, 5, 2]$ for lane `horror-horror-long`.
    - Invoke `stage_04_mood_theme(ctx)`.
    - Assert `ctx.scene_bg_list` contains 5 valid horizontal video paths.
    - Assert at least 3 distinct video loops are assigned across the 5 acts.
    - Assert the loop assigned to Act 4 (tension 5) matches high-intensity tags (`containment`, `facility`, `emergency`).
    - Assert `ctx.shot_durations` contains 5 duration elements matching act durations.
  - Write test `test_catalog_shortage_modulo_fallback`:
    - Given a 6-act narrative and a mock catalog with only 2 matching horizontal loops.
    - Invoke `resolve_multi_act_loops`.
    - Assert no exception is raised; assert the engine cyclically rotates loops using seeded modulo (`seed = act_index`).
    - Assert consecutive acts do not share identical loops when $\ge 2$ catalog loops exist.
  - Write test `test_force_single_loop_killswitch`:
    - Set environment variable `FORCE_SINGLE_LOOP=1`.
    - Invoke `stage_04_mood_theme(ctx)` for a horizontal director lane.
    - Assert `ctx.scene_bg_list` contains exactly 1 loop and `ctx.shot_durations` has 1 element equal to total audio duration.
  - **Focused Test Command**: `.venv/bin/pytest tests/unit/test_longform_multi_act.py -k "test_engine_resolution or test_resolve_multi_act or test_catalog_shortage or test_force_single_loop" -v`

- [x] **2.2: [GREEN] Refactor engine mode resolution in `src/pipeline/utils.py` and `src/pipeline/executor.py`**
  - **File Targets**: `src/pipeline/utils.py`, `src/pipeline/executor.py`
  - In `src/pipeline/utils.py` (`_resolve_engine_mode`):
    - Replace crude coercion logic (lines 346–352) with explicit routing for horizontal director lanes:
      ```python
      if is_multiscene_mode and lane.orientation == "horizontal" and lane.visual_pipeline == "director":
          engine_mode = "director"
          is_multiscene_mode = True
          is_loop_mode = False
      elif is_multiscene_mode and not force_multiscene and engine_mode != "image_animation":
          logger.info("Coercing video_engine=%s to loop (set FORCE_MULTISCENE=1 to restore director)", engine_mode)
          engine_mode = "loop"
          is_loop_mode = True
          is_multiscene_mode = False
      ```
  - In `src/pipeline/executor.py` (`_execute_pipeline`):
    - Align engine resolution logic with `src/pipeline/utils.py`, eliminating duplicate coercion that degrades horizontal director lanes.

- [x] **2.3: [GREEN] Implement `resolve_multi_act_loops` in `src/media/loop/rotation.py`**
  - **File Target**: `src/media/loop/rotation.py`
  - Add method `resolve_multi_act_loops(self, acts: Sequence[dict], orientation: str, channel: str, category: str, allow_test_mock: bool = False) -> tuple[list[Path], list[float]]`:
    - Scan catalog loops in `assets/videos/longs/` and `assets/loops/horizontal/` matching `orientation == "horizontal"`.
    - For each act $i \in [0, N-1]$:
      - Match category, act dramatic role (`exposition_inception`, `climax_confrontation`, etc.), and `tension_level` (1–5).
      - Maintain `used_in_sequence` list to prevent immediate adjacent repetition.
      - If pool is exhausted or fewer unique assets exist than acts, apply deterministic seeded modulo indexing:
        $$\text{idx} = (\operatorname{seed} + i) \pmod{\text{pool\_size}}$$
      - Use semantic alias mapping (`dark_forest` $\to$ `horror`, `aita` $\to$ `drama`).
    - Return `(loop_paths, act_durations)`.
    - Ensure zero unhandled exceptions; fallback to `resolve_continuous_loop` if catalog scan returns empty.

- [x] **2.4: [GREEN] Upgrade Stage 04 Visual Planning in `src/pipeline/stages/stage_04_mood.py`**
  - **File Target**: `src/pipeline/stages/stage_04_mood.py`
  - In `stage_04_mood_theme`:
    - Check if `lane.orientation == "horizontal"` and `lane.visual_pipeline == "director"`:
      - Check killswitch: `if os.environ.get("FORCE_SINGLE_LOOP", "").strip().lower() in ("1", "true", "yes", "on"):` fall back to continuous single loop.
      - Extract narrative acts from `ctx.script_payload.get("acts", [])`.
      - Invoke `resolve_multi_act_loops` on `LoopVideoEngine` / `rotation.py`.
      - Populate `ctx.scene_bg_list = [str(p) for p in loop_paths]` and `ctx.shot_durations = act_durations`.
      - Build `MultiActVisualSpec` payload and serialize to `ctx.visual_plan_path` (`visual_plan.json`).
      - Include defensive `try/except Exception as exc:` block: if multi-act loop resolution fails, emit warning event `pipeline.mood.multi_act_fallback` and fall back cleanly to `resolve_continuous_loop()`.
  - In `assets/loops/bank_manifest.json`:
    - Register thematic horizontal master loops with appropriate tags (`horror`, `dark_forest`, `facility`, `emergency`, `drama`, `cozy_interiors`).

- [x] **2.5: [VERIFY] Run Phase 2 verification suite**
  - Execute: `.venv/bin/pytest tests/unit/test_longform_multi_act.py -k "test_engine_resolution or test_resolve_multi_act or test_catalog_shortage or test_force_single_loop" -v`
  - Verify all tests pass with zero warnings.

---

## Phase 3: Stage 09 Concat Assembly & Subtitle Muxing

- **Primary Goal**: Implement zero-transcode multi-act stream-copy concatenation (`-f concat -safe 0 -c:v copy`), soft subtitle container muxing (`-c:s mov_text`), `.srt` sidecar export, and strict Resource Work Refusal if full re-encoding or `libass` burning is requested for 16:9 longform.
- **Affected Subsystems**: `src/pipeline/stages/`, `src/media/loop/`, `tests/unit/`
- **Resource Envelope**: Stream-copy I/O bound demux/remux; turnaround $\le 45\text{s}$ (target 25–35s), aggregate CPU $\le 120\%$ (bounded by `-threads 2` on audio), peak RAM $< 150\text{ MiB}$.

### Tasks

- [x] **3.1: [RED] Add stream-copy concat and soft subtitle muxing unit tests**
  - **File Target**: `tests/unit/test_longform_multi_act.py`
  - Write test `test_build_multi_scene_concat_list_longform_durations`:
    - Given a 4-act longform narrative with act durations $[180.0, 240.0, 360.0, 120.0]$ and 6-second loop clips.
    - Invoke `_build_multi_scene_concat_list` in `src/media/loop/stream_copy.py`.
    - Assert calculated repetitions $R_i \approx \text{dur}_i / 6.04$ are strictly computed from explicit act durations rather than clamped 12.0s beats.
    - Assert generated `ffconcat` file contains entries sequentially grouped by act: all reps of Act 1, followed by Act 2, through Act 4.
    - Assert total manifest duration covers the target duration $900.0\text{s}$.
  - Write test `test_render_video_loop_stream_copy_director`:
    - Given a horizontal longform director run context.
    - Invoke `_render_video_loop(ctx, render_spec)`.
    - Assert FFmpeg invocation command contains `-f concat -safe 0` and `-c:v copy`.
    - Assert command does NOT contain `libx264`, `zoompan`, or video filterchains.
    - Assert command contains `-threads 2` for audio DSP and loudness normalization.
  - Write test `test_soft_subtitle_muxing_mov_text`:
    - Given subtitles are active and `subtitles.ass` is present in `ctx.work_dir`.
    - Assert composition command contains `-c:s mov_text` and `-metadata:s:s:0 language=spa`.
    - Assert command does NOT contain `libass` or `subtitles=` video filter clauses.
    - Assert `.srt` sidecar file exists in `ctx.work_dir`.
  - Write test `test_work_refusal_on_libass_horizontal_longform`:
    - Given a composition request for lane `horror-horror-long` with `libass` burning enabled or requested.
    - Assert the rendering stage triggers Resource Work Refusal and raises a descriptive `ValueError` or `RuntimeError` before launching FFmpeg.
  - **Focused Test Command**: `.venv/bin/pytest tests/unit/test_longform_multi_act.py -k "test_build_multi_scene_concat or test_render_video_loop or test_soft_subtitle or test_work_refusal" -v`

- [x] **3.2: [GREEN] Update manifest compilation in `stage_08_loop.py`**
  - **File Target**: `src/pipeline/stages/stage_08_loop.py`
  - In `_build_legacy_manifest` and `stage_08_loop_scene`:
    - Check if `lane.orientation == "horizontal"` and `lane.visual_pipeline == "director"`:
      - Enforce `ctx.stream_copy_mode = True`.
      - Resolve `ctx.mux_subtitles = bool(ctx.subtitles_active and ctx.ass_path and ctx.ass_path.is_file())`.
      - Populate manifest `scene_images = ctx.scene_bg_list` and `shot_durations = ctx.shot_durations`.
      - Build `scene_manifest.json` ensuring exact act durations are preserved to avoid fallback clamping.

- [x] **3.3: [GREEN] Update composition routing and guardrails in `stage_09_render.py`**
  - **File Target**: `src/pipeline/stages/stage_09_render.py`
  - In `stage_09_video_rendering`:
    - Route horizontal director lanes to `_render_video_loop(ctx, render_spec)` instead of falling through to `_render_legacy` / `MultiSceneCompositor` pixel transcoding.
    - Enforce single-flight concurrency: ensure `_LONG_RENDER_SEMAPHORE` is acquired for all longform rendering.
    - Add explicit Resource Work Refusal check:
      ```python
      if ctx.is_long_lane and ctx.lane.orientation == "horizontal":
          if render_spec.burn_subtitles or getattr(render_spec, "reencode", False):
              raise ValueError(
                  "RESOURCE WORK REFUSAL: Burning subtitles or re-encoding video on 16:9 horizontal "
                  "longform violates Section 5 of AGENTS.md and REG-14. Use stream-copy (-c:v copy) "
                  "and soft-muxing (-c:s mov_text)."
              )
      ```

- [x] **3.4: [GREEN] Verify and optimize `stream_copy.py` repetition math and muxing**
  - **File Target**: `src/media/loop/stream_copy.py`
  - In `_build_multi_scene_concat_list`:
    - When `valid_scenes` provides explicit act durations ($> 0$), use `base_durs` directly without clamping `default_beat` to 12.0s.
    - Calculate integer repetition counts:
      $$R_i = \max\left(1, \operatorname{round}\left(\frac{\text{dur}_i}{\max(0.5, \text{clip\_dur}_i)}\right)\right)$$
    - Increment repetitions by sorting remaining duration deficits until cumulative manifest duration covers or exceeds $T_{\text{audio}}$.
    - Ensure container output includes `-t {duration_sec}` to clamp final video length to audio narration.
    - In FFmpeg audio mixing commands, enforce `-threads 2` on `amix` and `loudnorm`.
    - Ensure `subtitle_mux_ffmpeg_parts` soft-muxes timed text via `-c:s mov_text` and registers Spanish language metadata.
    - Ensure `.srt` subtitle sidecar is emitted and registered in `ctx.artifacts["srt_path"]`.

- [x] **3.5: [VERIFY] Run Phase 3 verification suite**
  - Execute: `.venv/bin/pytest tests/unit/test_longform_multi_act.py -k "test_build_multi_scene_concat or test_render_video_loop or test_soft_subtitle or test_work_refusal" -v`
  - Verify all tests pass with zero warnings.

---

## Phase 4: Stage 11 YouTube Chapters Metadata

- **Primary Goal**: Extract cumulative time offsets from act durations, format YouTube-compliant clickable chapter markers in video descriptions, validate interactive chapter rules, and register the `.srt` sidecar in output artifacts.
- **Affected Subsystems**: `src/pipeline/stages/stage_11_metadata.py`, `tests/unit/`
- **Resource Envelope**: String parsing and formatting only; turnaround $< 0.05\text{s}$, CPU $< 0.02$ Cores, peak RAM $< 50\text{ MiB}$.

### Tasks

- [x] **4.1: [RED] Add YouTube chapter formatting unit tests**
  - **File Target**: `tests/unit/test_longform_multi_act.py`
  - Write test `test_youtube_chapters_generation_happy_path`:
    - Given 4 acts with durations $[255.0, 310.0, 480.0, 355.0]$ seconds.
    - Invoke chapter formatter in Stage 11.
    - Assert the description contains:
      ```text
      Capítulos:
      00:00 - Acto I: Incepción Sensorial y Aislamiento
      04:15 - Acto II: Advertencias Ignoradas y Señales
      09:25 - Acto III: Confrontación Inexplicable y Ruptura
      17:25 - Acto IV: Secuela Psicológica y Trauma
      ```
    - Assert chapter 1 timestamp is strictly `00:00`.
    - Assert total chapter count is 4 ($\ge 3$).
    - Assert every chapter interval is $\ge 10\text{s}$.
  - Write test `test_short_act_merging`:
    - Given an act sequence where Act 2 has duration $8.0\text{s}$ ($< 10\text{s}$).
    - Assert the formatter merges Act 2 into Act 1 and resulting chapters maintain compliance.
  - Write test `test_insufficient_chapters_suppressed`:
    - Given a narrative yielding only 2 valid acts.
    - Assert the chapter block is cleanly omitted from `ctx.youtube_description` without breaking metadata persistence or publication.
  - Write test `test_srt_artifact_registration`:
    - Assert `.srt` subtitle file is recorded in `ctx.repository` and registered in `metadata.json`.
  - **Focused Test Command**: `.venv/bin/pytest tests/unit/test_longform_multi_act.py -k "test_youtube_chapters or test_short_act or test_insufficient_chapters or test_srt_artifact" -v`

- [x] **4.2: [GREEN] Implement `YouTubeChapterSpec` in `stage_11_metadata.py`**
  - **File Target**: `src/pipeline/stages/stage_11_metadata.py`
  - Define `@dataclass(slots=True, frozen=True) class YouTubeChapterEntry`:
    - `start_seconds: float`, `formatted_time: str`, `title: str`, `act_index: int`.
  - Define `@dataclass(slots=True) class YouTubeChapterSpec`:
    - `chapters: list[YouTubeChapterEntry]`.
    - Method `is_valid() -> bool`:
      - Assert `len(self.chapters) >= 3`.
      - Assert `self.chapters[0].formatted_time in ("00:00", "0:00")`.
      - Assert consecutive chapters have interval $\ge 10.0\text{s}$ and are in strictly ascending order.
    - Method `format_description_block() -> str`:
      - Emit clean formatted block starting with `\nCapítulos:\n`.
      - Return empty string if `not self.is_valid()`.

- [x] **4.3: [GREEN] Wire chapter generation into `stage_11_thumbnail_metadata`**
  - **File Target**: `src/pipeline/stages/stage_11_metadata.py`
  - In `stage_11_thumbnail_metadata`:
    - If `ctx.is_long_lane` and `ctx.shot_durations` has $\ge 3$ entries:
      - Extract act titles from `ctx.script_payload.get("acts", [])` or `ctx.visual_plan_payload.get("act_titles", [])`.
      - Calculate cumulative offsets $t_k = \sum_{j=0}^{k-1} \text{shot\_durations}_j$.
      - Format timestamps (`MM:SS` for $< 3600\text{s}$, `HH:MM:SS` for $\ge 3600\text{s}$).
      - Merge any chapters with duration $< 10.0\text{s}$ into adjacent chapters.
      - Compile `YouTubeChapterSpec` and append `spec.format_description_block()` to `ctx.youtube_description`.
      - Save chapter list into `metadata.json` under `"chapters"`.
    - Ensure `.srt` subtitle sidecar is included in `required_artifacts` when `ctx.srt_path.is_file()`.

- [x] **4.4: [VERIFY] Run Phase 4 verification suite**
  - Execute: `.venv/bin/pytest tests/unit/test_longform_multi_act.py -k "test_youtube_chapters or test_short_act or test_insufficient_chapters or test_srt_artifact" -v`
  - Verify all tests pass with zero warnings.

---

## Phase 5: Anti-Regression Verification, Guardrails & Offline Smoke Tests

- **Primary Goal**: Validate strict compliance with Section 5 of `AGENTS.md` and REG-01 through REG-14, confirm zero external network requests or browser spawns, execute end-to-end generate-only offline smoke tests across longform director lanes, and perform mandatory cadence check.
- **Affected Subsystems**: `tests/unit/`, `scripts/`
- **Resource Envelope**: Multi-act stream-copy execution turnaround $\le 45\text{s}$ (target 25–35s), CPU $\le 120\%$ during audio, idle CPU $0.0\%$, peak RAM $< 150\text{ MiB}$.

### Tasks

- [x] **5.1: [RED] Expand anti-regression guardrail assertions**
  - **File Target**: `tests/unit/test_anti_regression_guardrails.py`
  - Under `TestStreamCopyAndEncodingGuardrails` (REG-13):
    - Add assertion that longform horizontal lanes (`horror-horror-long`, `drama-aita-long`) use stream-copy (`-c:v copy`) and soft subtitle muxing (`-c:s mov_text`).
    - Add assertion that `libass` subtitle burning is prohibited on 16:9 horizontal longform videos.
  - Under `TestResourceTargetGovernanceGuardrails` (REG-14):
    - Assert that Section 5 of `AGENTS.md` and `docs/FFMPEG_LOW_CPU.md` document the multi-act stream-copy turnaround ceiling ($\le 45\text{s}$) and resource envelope ($\le 2$ CPU Cores, $\le 2.0$ GiB RAM).
  - **Focused Test Command**: `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v`

- [x] **5.2: [GREEN] Execute comprehensive unit test suites**
  - **File Targets**: `tests/unit/test_anti_regression_guardrails.py`, `tests/unit/test_longform_multi_act.py`
  - Execute anti-regression suite:
    ```bash
    .venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v
    ```
    Assert 100% pass rate with zero violations.
  - Execute multi-act director suite:
    ```bash
    .venv/bin/pytest tests/unit/test_longform_multi_act.py -v
    ```
    Assert all tests pass.

- [x] **5.3: [GREEN] Execute end-to-end generate-only offline smoke tests**
  - Execute offline smoke test on horror longform lane:
    ```bash
    python3 main.py run --lane horror-horror-long --generate-only
    ```
    - Assert video is rendered via stream-copy in $\le 45\text{ seconds}$.
    - Assert output directory contains playable `video.mp4`, `metadata.json` with chapters, and `subtitles.srt`.
    - Assert zero external network connections or browser processes were spawned.
  - Execute offline smoke test on drama longform lane:
    ```bash
    python3 main.py run --lane drama-aita-long --generate-only
    ```
    - Assert video is rendered via stream-copy in $\le 45\text{ seconds}$.
    - Assert output directory contains playable `video.mp4`, `metadata.json` with chapters, and `subtitles.srt`.
    - Assert zero external network connections or browser processes were spawned.

- [x] **5.4: [VERIFY] Mandatory Cadence Integrity Check**
  - **File Target**: `scripts/verify_integrity.sh` `(read-only)`
  - Execute:
    ```bash
    ./scripts/verify_integrity.sh
    ```
  - Verify script exits with status 0 and zero integrity failures.
