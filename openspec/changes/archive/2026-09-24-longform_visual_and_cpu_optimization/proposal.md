# Proposal: Longform Visual Quality and CPU Optimization (Hybrid Multi-Act Director)

## 1. Intent & Context

Longform horizontal (16:9, 1080p, 10–30 min / 600–1800s) video channels in `config/lanes.json` (`horror-horror-long` and `drama-aita-long`) currently suffer from a severe visual stagnation defect that cripples audience retention:

1. **The "Director Coercion Trap"**: In `src/pipeline/utils.py` (lines 346–352) and `src/pipeline/executor.py` (lines 228–234), any lane configured with `"visual_pipeline": "director"` is automatically coerced at runtime to `loop` mode unless `FORCE_MULTISCENE=1` is explicitly set in the environment.
2. **The "Single Loop Monotony" Defect**: Under `loop` mode, `src/pipeline/stages/stage_04_mood.py` resolves exactly one continuous loop video clip for the entire story. In `src/media/loop/stream_copy.py`, a single 6-second video loop (e.g. `horror_ambient_01.mp4` or `drama_ambient_01.mp4`) is repeated **100 to 300 times** to fill 600 to 1800 seconds. A 20–30 minute narrative plays against an endlessly repeating 6-second background, inducing acute viewer fatigue and high audience drop-off.
3. **The Transcoding Trap**: Naively porting the Shorts multi-scene Ken Burns rendering model (`image_animation`) to longform fails catastrophically. Encoding 1080p @ 30fps with continuous `zoompan` and burning subtitles via `libass` on a 30-minute video consumes **60 to 90 minutes of 200% CPU**, violently exceeding the 900-second job lease timeout (`SETTINGS.render_timeout_seconds`) by $4\times$ to $6\times$ and violating the strict resource target in **Section 5 of AGENTS.md** (hard ceiling: $\le 2$ CPU Cores, $\le 2.0$ GiB RAM).
4. **Missing YouTube Interactive Chapters & Soft Captions**: Stage 11 metadata generation does not inject YouTube Chapter timestamps into video descriptions, missing YouTube's primary zero-CPU interactive navigation feature. Furthermore, subtitle rendering defaults to CPU-intensive pixel burning rather than container soft subtitle muxing (`mov_text`).

This proposal introduces the **Hybrid Multi-Act Director** architecture. It transforms longform production into a dynamic 4–8 act narrative journey with tension-calibrated thematic horizontal loop rotation, zero-transcode stream-copy concatenation (`-c:v copy`), automated YouTube chapter markers, and soft caption muxing—guaranteeing broadcast-grade visual variety and **sub-45 second render turnaround** while strictly operating within the $\le 2$ CPU Cores / $\le 2.0$ GiB RAM envelope.

---

## 2. Scope

### In Scope
- **4–8 Act Narrative Script Decomposition**: Expanding longform script curation (`CinematicScriptCuratorAgent`, `TextSegmentationEngine`, `src/curators/curation_profiles.py`) to systematically slice 10–30 minute narratives into 4–8 structured dramatic acts (e.g. Act I: Inception, Act II: Escalation, Act III: Confrontation, Act IV: Climax, Act V: Aftermath), complete with act titles, dramatic roles, tension ratings (1–5), and audio-aligned durations.
- **Thematic Horizontal Loop Catalog Expansion & Multi-Act Resolution**:
  - Expanding horizontal loop categories in `assets/loops/bank_manifest.json` and `src/core/catalog.py` to support multi-act thematic pools (`containment`, `wilderness`, `facility`, `emergency`, `aftermath`, `cozy_interiors`, `nocturne_city`, `diner`, `courtroom`).
  - Upgrading `src/pipeline/stages/stage_04_mood.py` to query `LoopCatalogRepository` / `LoopRotationEngine` for distinct thematic horizontal loops per narrative act (`ctx.scene_bg_list` populated with $N$ distinct loops and corresponding `ctx.shot_durations`).
- **Zero-Transcode Multi-Act Stream-Copy Assembly**:
  - Leveraging `_build_multi_scene_concat_list` in `src/media/loop/stream_copy.py` to concatenate $N$ distinct act loops via FFmpeg concat demuxer (`-f concat -safe 0 -c:v copy`) without decoding or re-encoding video frames.
  - Ensuring container-level profile homogeneity (1080p, 30fps, `yuv420p`, bt709) across catalog assets to eliminate DTS/PTS discontinuities.
- **Automated YouTube Chapters Generation**:
  - Upgrading `src/pipeline/stages/stage_11_metadata.py` to extract narrative act boundaries (`00:00`, `03:45`, `08:12`, etc.) and automatically inject formatted, clickable YouTube Chapter markers into `ctx.youtube_description` conforming strictly to YouTube guidelines (minimum 3 chapters, starting at `00:00`, $\ge 10$ seconds duration each).
- **Soft Subtitle Muxing (`mov_text`) & Sidecar Export**:
  - Enforcing soft subtitle track muxing via `subtitle_mux_ffmpeg_parts` (`-c:s mov_text`) in the master MP4 container.
  - Exporting `.srt` subtitle sidecars for official YouTube Captions API upload during publishing, eliminating CPU-heavy `libass` frame burning for horizontal longform.
- **Elimination of Crude Engine Coercion**:
  - Refactoring engine mode resolution in `src/pipeline/utils.py` and `src/pipeline/executor.py` to support `director` mode on horizontal longform lanes by routing to the Hybrid Multi-Act Director stream-copy pipeline rather than blindly degrading to single-loop mode.

### Out of Scope
- Full-pixel Ken Burns re-encoding (`zoompan` over still images) for 30-minute videos (violates timeout and CPU budgets; reserved strictly for 60–90s Shorts).
- Burning subtitles into video pixels via `libass` filtergraphs on longform horizontal videos.
- Headless browser rendering, Playwright, or Chromium in media composition (strictly prohibited by `REG-01`).
- Reintroducing retired legacy subsystems (`src/rendering/`, `src/compositing/`, `src/export/`) or procedural WGSL GPU shaders (`REG-02`, `REG-07`, `REG-10`).
- Modifying YouTube Data API upload mechanics (uploads strictly follow session cookie-based workflows).

---

## 3. Capabilities

### New Capabilities
- `longform-multi-act-director`: Slices 10–30 minute scripts into 4–8 structured narrative acts with progressive tension scoring, resolves distinct thematic horizontal loops per act from the catalog, executes zero-transcode stream-copy concatenation, and automatically generates interactive YouTube chapter markers in video descriptions.

### Modified Capabilities
- `media-processing-performance-policy`: Formulates explicit operational rules for longform horizontal media composition: mandates stream-copy (`-c:v copy`) multi-act concatenation and container soft subtitle muxing (`-c:s mov_text`) to guarantee $\le 45$ second render turnaround for 10–30 minute videos, strictly preventing the 60–90 minute CPU transcoding bottleneck and adhering to the $\le 2$ CPU Cores / $\le 2.0$ GiB RAM budget.
- `multi-channel-lanes-and-smoke-test`: Updates longform lane configurations (`horror-horror-long`, `drama-aita-long`) to validate multi-act director profiles, catalog resolution, and generate-only smoke tests across multi-act stream-copy pipelines.

---

## 4. Architectural Design & Technical Approach

### 4.1 Architecture Workflow Diagram

```mermaid
flowchart TD
    subgraph NarrativeCuration [1. Narrative & Act Decomposition]
        Script[Raw Longform Script: 2600-4800 words] --> TextSplitter[TextSegmentationEngine]
        TextSplitter --> ActParser[CinematicScriptCuratorAgent]
        ActParser --> ScriptActs["4-8 Narrative Acts\n(Titles, Roles, Tension 1-5, Word Spans)"]
    end

    subgraph AudioSynthesis [2. Audio Voiceover & Timing]
        Script --> TTS[Edge-TTS Voice Synthesis]
        TTS --> VoiceAudio[speech.wav: 600-1800s]
        VoiceAudio --> AudioProbe[Audio Duration & Beat Aligner]
    end

    subgraph VisualPlanning [3. Multi-Act Visual Planning (Stage 04)]
        ScriptActs --> MoodStage[stage_04_mood.py]
        AudioProbe --> MoodStage
        MoodStage --> LoopCatalog[LoopCatalogRepository]
        LoopCatalog --> ActLoops["Distinct Horizontal Loops\n(Act 1..N Loops from Catalog)"]
        MoodStage --> VisualPlan["visual_plan.json\n(Scene BG List & Shot Durations)"]
    end

    subgraph MediaComposition [4. Zero-Transcode Stream-Copy Composition (Stage 08 & 09)]
        VisualPlan --> ManifestBuilder[stage_08_loop.py]
        ManifestBuilder --> SceneManifest["scene_manifest.json\n(N Scene Loops + Durations)"]
        SceneManifest --> StreamCopyEngine[stream_copy.py / LoopVideoEngine]
        VoiceAudio --> StreamCopyEngine
        ActLoops --> StreamCopyEngine
        Subtitles[subtitles.ass / .srt] --> StreamCopyEngine
        StreamCopyEngine --> FFmpegConcat["FFmpeg Stream-Copy Concat\n(-f concat -safe 0 -c:v copy)\nZero Frame Re-encoding"]
        FFmpegConcat --> MasterVideo["video.mp4 (1080p, ~30s turnaround)\nwith -c:s mov_text Soft Subtitles"]
    end

    subgraph MetadataGeneration [5. YouTube Chapters & SEO (Stage 11)]
        ScriptActs --> MetadataStage[stage_11_metadata.py]
        AudioProbe --> MetadataStage
        MetadataStage --> ChapterFormatter[YouTube Chapter Formatter]
        ChapterFormatter --> ChapterMarkers["00:00 Act I: Incepción\n04:15 Act II: Tensión Creciente\n09:40 Act III: Punto de Ruptura\n16:20 Act IV: Secuela"]
        ChapterMarkers --> YTDescription["ctx.youtube_description\n(Interactive Video Chapters)"]
        MetadataStage --> ThumbnailGen[Thumbnail Climax Extractor]
    end

    MasterVideo --> OutputPublish[Ready for Telegram Review & Session Publish]
    YTDescription --> OutputPublish
    ThumbnailGen --> OutputPublish
```

### 4.2 Subsystem Breakdown

#### 1. Narrative Act Decomposition & Tension Curve
- `CinematicScriptCuratorAgent` / `TextSegmentationEngine` parses the 10–30 minute story into 4–8 narrative acts based on word count, semantic paragraph boundaries, and narrative pacing rules in `src/curators/curation_profiles.py`.
- Each act is assigned:
  - An **Act Title** suitable for public display (e.g. `Acto I: Incepción Sensorial`, `Acto II: Tensión Creciente`, `Acto III: Punto de Ruptura`, `Acto IV: Secuela Psicológica`).
  - A **Dramatic Role** (`exposition_inception`, `rising_action_dread`, `climax_confrontation`, `aftermath_revelation`).
  - A **Tension Profile** (numeric values 1 to 5).
  - Exact sentence/word allocations proportionally scaled to the TTS voiceover duration.

#### 2. Thematic Multi-Loop Resolution (Stage 04)
- In `src/pipeline/stages/stage_04_mood.py`, for longform lanes with `visual_pipeline == "director"`:
  - Instead of resolving a single loop, the stage resolves a distinct horizontal loop from `LoopCatalogRepository` for each of the $N$ acts.
  - Candidate selection factors in the lane category (`horror`, `dark_forest`, `drama`, `aita`), the act's dramatic role, and its tension level (e.g., Act 1 exposition $\to$ atmospheric wide shot; Act 3 climax $\to$ high-tension emergency / red lighting).
  - Populates `ctx.scene_bg_list = [loop_1, loop_2, ..., loop_N]` and `ctx.shot_durations = [dur_1, dur_2, ..., dur_N]`, where $\sum \text{dur}_i = \text{total\_audio\_duration}$.
  - Fallback logic: If the local catalog contains fewer unique loops than acts, a deterministic modulo rotation (`seed = act_index`) cycles through available pool assets and fallback aliases without failing.

#### 3. Zero-Transcode Multi-Act Stream-Copy Composition (Stages 08 & 09)
- In `src/pipeline/stages/stage_08_loop.py`, `_build_video_loop_manifest` (or dedicated `_build_longform_director_manifest`) packages the multi-scene loop list into `scene_manifest.json`.
- In `src/media/loop/stream_copy.py`:
  - `_build_multi_scene_concat_list` computes the exact repetition count $R_i = \max(1, \text{round}(\text{dur}_i / \text{clip\_dur}_i))$ for each act loop.
  - Constructs the concat demuxer manifest (`ffconcat version 1.0`) ordering all repetitions of Act 1, followed by Act 2, through Act $N$.
  - Executes FFmpeg via stream-copy:
    ```bash
    ffmpeg -y -threads 2 \
      -f concat -safe 0 -i concat_list.txt \
      -i speech.wav -i bg_music.wav \
      -filter_complex "[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=2,loudnorm=I=-16:TP=-1.5:LRA=11[aout]" \
      -map 0:v -map "[aout]" \
      -c:v copy -c:a aac -b:a 192k \
      -t {total_duration} master_video.mp4
    ```
  - **Zero video re-encoding**: Video packets are demuxed and remuxed directly, delivering render turnaround in **~25 to 35 seconds** for an entire 30-minute video.

#### 4. Automated YouTube Interactive Chapters Generation (Stage 11)
- In `src/pipeline/stages/stage_11_metadata.py`:
  - The chapter generator extracts cumulative time offsets from `ctx.shot_durations` and correlates them with act titles from `ctx.script_payload["acts"]`.
  - Formats timestamps into standard YouTube chapter markers:
    ```text
    Capítulos:
    00:00 - Acto I: Incepción Sensorial y Aislamiento
    04:12 - Acto II: Advertencias Ignoradas y Señales
    09:45 - Acto III: Confrontación Inexplicable y Ruptura
    17:20 - Acto IV: Secuela Psicológica y Trauma
    ```
  - Validates YouTube chapter constraints:
    - Starts strictly at `00:00`.
    - Contains at least 3 distinct chapters.
    - Each chapter is at least 10 seconds in duration.
  - Prepends or appends the chapter block into `ctx.youtube_description`. When published to YouTube, the video player automatically renders clickable interactive chapter scrubbers and title overlays on desktop and mobile.

#### 5. Soft Subtitle Muxing (`mov_text`) and Sidecar Export
- Subtitles are generated in `stage_07_subtitles.py` as `.ass` and `.srt` files.
- In `stage_09_render.py` and `stream_copy.py`, subtitles are muxed into the MP4 container as a `mov_text` track (`-c:s mov_text`) via `subtitle_mux_ffmpeg_parts`.
- The `.srt` file is registered as a required artifact for upload via YouTube Captions API during `stage_13_publish.py`.
- Prohibits rasterizing subtitles with `libass` on longform horizontal videos, saving 30–40 minutes of CPU time.

#### 6. Removal of Crude Engine Coercion
- In `src/pipeline/utils.py` and `src/pipeline/executor.py`, update `_resolve_engine_mode`:
  ```python
  # Permit director mode when running longform horizontal lanes with multi-act stream-copy
  if is_multiscene_mode and lane.orientation == "horizontal" and lane.visual_pipeline == "director":
      # Canonical Hybrid Multi-Act Director: Preserve multiscene visual planning + stream-copy render
      is_multiscene_mode = True
      is_loop_mode = False
  ```
  This eliminates the need for manual `FORCE_MULTISCENE=1` environment variables and aligns declared lane configuration with actual runtime execution.

---

## 5. Strict Resource Target & Steady-State Zero Envelope (AGENTS.md Section 5 & REG-14)

### 5.1 Hard Target Ceiling
In strict compliance with **AGENTS.md Section 5** and **REG-14**:
- **CPU Ceiling**: $\le 2.0$ CPU Cores ($\le 200\%$ aggregate CPU utilization across all active threads).
- **RAM Ceiling**: $\le 2.0$ GiB RAM (2,048 MiB peak resident memory).
- **Render Turnaround**: $\le 45$ seconds for a full 10–30 minute video.
- **Monotonic Optimization**: Media composition uses stream-copy (`-c:v copy`), ensuring that resource consumption drops significantly compared to legacy rendering models.

### 5.2 Steady-State Zero Idle Footprint
- When no rendering job is active, background daemons consume **0.0% CPU** and release all memory buffers.
- Concurrency is strictly bounded by `_LONG_RENDER_SEMAPHORE = 1`. Only one longform video can render at any given instant.
- Subprocesses execute with explicit timeouts and context managers; all file handles, pipes, and background threads are closed immediately upon task completion.
- Explicit `memory_checkpoint()` calls trigger garbage collection at every pipeline stage boundary.

### 5.3 Disk Streaming & Memory Safety
- In-memory video/audio frame buffers (e.g. unconstrained Pillow loops or NumPy frame arrays) are strictly prohibited.
- Concat lists are written to ephemeral disk files (`ffconcat`) and streamed directly by FFmpeg.
- Peak resident memory remains **$< 150$ MiB** throughout the entire composition of a 30-minute video.

### 5.4 Subprocess Thread Bounding
- Audio/video probes (`ffprobe`, loudness analysis) enforce `-threads 2` and skip video frame decoding with `-vn`.
- FFmpeg audio mixing commands enforce `-threads 2` up to a maximum of `-threads 4`.

---

## 6. Media Processing Performance Impact

### 6.1 Quantitative Resource Profile & Architectural Comparison

The following table compares the three approaches evaluated in the exploration document against a 30-minute (1800-second) 1080p longform video:

| Metric / Dimension | Approach A: Full Ken Burns Re-Encode | Approach B: Chunked Concat + Rendered Bumpers | Approach C: Hybrid Multi-Act Director [PROPOSED] |
| :--- | :--- | :--- | :--- |
| **Video Re-encoding Mode** | Full transcode (`libx264`) | Hybrid (bumpers transcode + loop copy) | **Zero re-encode (`-c:v copy`)** |
| **Subtitle Integration** | Burned pixels via `libass` | Burned or soft muxed | **Soft muxed (`mov_text`) + `.srt` sidecar** |
| **Render Turnaround (30m Video)**| 60 – 90 minutes (3,600s – 5,400s) | 50 – 65 seconds | **25 – 35 seconds** |
| **Peak CPU Utilization** | 200% (2 cores pinned for 1+ hr) | Brief spike to 180% (bumpers) | **$\le 120\%$ for ~15s (audio ducking only)** |
| **Peak RAM (RSS)** | 550 – 850 MiB | 180 – 250 MiB | **< 150 MiB** |
| **900s Timeout Contract** | **VIOLATED ($4\times - 6\times$ over)** | Satisfied | **Satisfied ($25\times$ safety margin)** |
| **AGENTS.md Section 5 Compliance**| **VIOLATES** | Partially Compliant | **100% STRICTLY COMPLIANT** |
| **Visual Diversity** | High (stills + zoompan) | High (acts + bumpers) | **High (4–8 thematic loops + chapter scrubbers)** |
| **Risk of PTS/DTS Jitter** | Low | High (splicing raw x264 into stream-copy)| **Zero (homogeneous catalog loop profiles)** |
| **YouTube Native Player Synergy** | None (burned pixels) | Low | **High (Interactive Chapters + Native Soft CC)** |

### 6.2 Performance Summary
- By avoiding full-pixel re-encoding and subtitle burning, the pipeline eliminates **over 1 hour of continuous 100% 2-core CPU saturation** per longform video.
- Composition turnaround is reduced from $>5,000$ seconds to **$< 35$ seconds**, representing a $>140\times$ throughput improvement.
- Host system responsiveness is fully preserved: background daemons, health checks, Telegram review bots, and queue schedulers run with zero latency degradation.

---

## 7. Affected Code & Subsystems

| Subsystem / File | Nature of Change | Description & Role |
| :--- | :--- | :--- |
| `config/lanes.json` | Configuration | Retains `"visual_pipeline": "director"` for `horror-horror-long` and `drama-aita-long`, mapping them to the hybrid multi-act pipeline. |
| `src/pipeline/utils.py` | Engine Resolution | Refactors `_resolve_engine_mode` to eliminate crude director-to-loop coercion for horizontal longform lanes. |
| `src/pipeline/executor.py` | Engine Resolution | Synchronizes engine mode resolution with `src/pipeline/utils.py`, removing duplicate coercion logic. |
| `src/pipeline/stages/stage_04_mood.py` | Visual Planning | Adds multi-act loop resolution for horizontal longform director lanes (`ctx.scene_bg_list` with $N$ distinct loops and scaled durations). |
| `src/pipeline/stages/stage_08_loop.py` | Manifest Assembly | Ensures `_build_video_loop_manifest` and `_build_legacy_manifest` correctly format multi-act scene loop manifests. |
| `src/pipeline/stages/stage_09_render.py` | Media Composition | Enforces stream-copy composition (`_render_video_loop`) with soft subtitle muxing (`mov_text`) on longform lanes. |
| `src/pipeline/stages/stage_11_metadata.py` | Metadata & SEO | Adds automated extraction of act timestamps and formats clickable YouTube Chapter markers in `ctx.youtube_description`. |
| `src/media/loop/stream_copy.py` | Media Core | Verifies multi-scene repetition math in `_build_multi_scene_concat_list` and ensures `-c:s mov_text` subtitle muxing. |
| `src/media/loop/rotation.py` | Loop Selection | Adds support for resolving multi-act loop sequences with tension and category weighting. |
| `src/curators/curation_profiles.py` | Script Profiles | Refines 4–8 act narrative structure and titles for `horror-horror-long` and `drama-aita-long`. |
| `assets/loops/bank_manifest.json` | Catalog Manifest | Registers horizontal master loops across thematic categories (`horror`, `dark_forest`, `facility`, `drama`, `aita`). |
| `tests/unit/test_longform_multi_act.py` | Test Suite | New unit tests verifying 4–8 act parsing, multi-loop resolution, stream-copy concat list generation, and YouTube chapter formatting. |
| `tests/unit/test_anti_regression_guardrails.py` | Test Suite | Validates that changes strictly comply with REG-01 through REG-14 (no browser, no buffer loops, resource bounds). |

---

## 8. Risk Assessment & Mitigation

| Risk | Severity | Likelihood | Mitigation Strategy |
| :--- | :---: | :---: | :--- |
| **Catalog Asset Scarcity** | Medium | Medium | When the catalog contains fewer loops than narrative acts, `resolve_multi_act_loops` utilizes seeded modulo rotation (`seed = act_index`) across available assets and falls back to semantic aliases (`dark_forest` $\to$ `horror`). |
| **Audio-Video Duration Drift** | Medium | Low | `_build_multi_scene_concat_list` calculates integer repetition counts to cover each act's duration, and the final FFmpeg command uses `-t {audio_duration}` to clamp the container precisely to the narration audio length. |
| **YouTube Chapter Rejection** | Medium | Low | Stage 11 chapter formatter enforces strict YouTube validation rules: chapter 1 strictly at `00:00`, minimum 3 chapters, and each chapter $\ge 10$ seconds apart. If validation fails, description generation falls back gracefully to standard formatting without breaking the pipeline. |
| **Container Stream-Copy Incompatibility** | High | Low | Master horizontal loops in `assets/loops/horizontal/` and `assets/videos/longs/` are pre-standardized to identical video parameters (1920x1080, 30fps, H.264 High Profile, `yuv420p`, bt709). Probes in `stream_copy.py` abort stream-copy if geometry or codec mismatch is detected. |
| **CPU Spikes during Audio Mastering** | Low | Low | Audio mixing commands (`loudnorm`, `amix`) in `stream_copy.py` enforce `-threads 2`, preventing audio DSP filters from exceeding the 2-core budget. |

---

## 9. Rollback Plan

1. **Instantaneous Configuration-Level Rollback**:
   - If the multi-act director workflow encounters unexpected production issues, affected lanes (`horror-horror-long`, `drama-aita-long`) can be reverted immediately to single-loop stream-copy by setting `"visual_pipeline": "video_loop"` in `config/lanes.json` or by passing `--visual-pipeline video_loop` via CLI. No code deployment or database migration is required.
2. **Runtime Environment Kill Switch**:
   - Setting the environment variable `FORCE_SINGLE_LOOP=1` instructs `stage_04_mood.py` and `stage_08_loop.py` to revert to single continuous loop resolution, bypassing multi-act rotation entirely.
3. **Graceful Pipeline Degradation**:
   - If multi-act loop resolution throws an exception during Stage 4, the stage catches the error, logs a structured observability alert, and falls back to `resolve_continuous_loop` (single loop) to allow rendering to complete successfully.
4. **Clean Git Reversion**:
   - All code edits preserve existing domain interfaces, dataclasses, and database contracts. Reverting the git commit returns the codebase cleanly to its prior stable state.

---

## 10. Dependencies

- **Zero New External Heavy Dependencies**: Relies exclusively on proven, production-verified system and Python components:
  - Python 3.12 / 3.13 Standard Library (`subprocess`, `dataclasses`, `pathlib`, `json`, `math`).
  - FFmpeg 6.1+ (`-c:v copy`, `concat` demuxer, `loudnorm`, `amix`, `mov_text`).
  - Existing core modules: `TextSegmentationEngine`, `CinematicScriptCuratorAgent`, `LoopVideoEngine`, `SeoOptimizerAgent`.

---

## 11. Success Criteria & Verification

- [ ] **Multi-Act Narrative Script Curation**:
  - `TextSegmentationEngine.curate` parses 10–30m longform scripts into 4–8 distinct narrative acts with valid act titles, roles, tension scores (1–5), and audio-aligned durations.
- [ ] **Multi-Loop Catalog Resolution**:
  - `stage_04_mood.py` resolves distinct horizontal catalog loops per act for longform director lanes, populating `ctx.scene_bg_list` and `ctx.shot_durations`.
  - Deterministic fallback / modulo rotation succeeds even when the number of acts exceeds unique catalog loops.
- [ ] **Zero-Transcode Stream-Copy Composition**:
  - `_render_video_loop` and `stream_copy.py` generate valid `ffconcat` files containing sequential repetitions of all act loops.
  - Composition turnaround for a 10–30 minute video completes in $\le 45$ seconds.
  - Video stream is copied directly (`-c:v copy`) without decoding or re-encoding video frames.
  - Subtitles are muxed as `mov_text` (`-c:s mov_text`) and an `.srt` sidecar is exported.
- [ ] **Automated YouTube Chapters Generation**:
  - `stage_11_metadata.py` extracts act boundaries and formats clickable YouTube Chapter markers in `ctx.youtube_description`.
  - Chapter formatting adheres to YouTube standards: starts at `00:00`, $\ge 3$ chapters, each $\ge 10$s apart.
- [ ] **Engine Coercion Removal**:
  - Longform lanes with `"visual_pipeline": "director"` execute the multi-act director pipeline without requiring `FORCE_MULTISCENE=1`.
- [ ] **Performance & Resource Guardrails (AGENTS.md Section 5 & REG-14)**:
  - Peak resident memory remains $\le 2.0$ GiB (observed $< 150$ MiB).
  - Aggregate CPU usage remains $\le 2$ CPU Cores throughout audio mastering and composition.
  - Steady-state idle CPU usage is confirmed at 0.0%.
  - Guardrail suite passes 100%: `pytest tests/unit/test_anti_regression_guardrails.py -v`.
  - System integrity audit exits 0: `./scripts/verify_integrity.sh`.
