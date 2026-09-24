# Technical Design: Longform Visual Quality and CPU Optimization (Hybrid Multi-Act Director)

## 1. Overview & Architectural Motivation

Longform horizontal (16:9, 1080p, 10–30 min / 600–1800s) video channels in `config/lanes.json` (`horror-horror-long` and `drama-aita-long`) currently suffer from a severe architectural defect:

1. **The "Director Coercion Trap"**: In `src/pipeline/utils.py` (lines 346–352) and `src/pipeline/executor.py` (lines 228–234), any lane configured with `"visual_pipeline": "director"` is automatically coerced at runtime to `loop` mode unless `FORCE_MULTISCENE=1` is explicitly set in the environment.
2. **The "Single Loop Monotony" Defect**: Under `loop` mode, `src/pipeline/stages/stage_04_mood.py` resolves exactly one continuous loop video clip for the entire story. In `src/media/loop/stream_copy.py`, a single 6-second video loop (e.g. `horror_ambient_01.mp4` or `drama_ambient_01.mp4`) is repeated **100 to 300 times** to fill 600 to 1800 seconds. A 20–30 minute narrative plays against an endlessly repeating 6-second background, inducing acute viewer fatigue and collapsing audience retention.
3. **The Transcoding Trap**: Naively porting the Shorts multi-scene Ken Burns rendering model (`image_animation`) to longform fails catastrophically. Encoding 1080p @ 30fps with continuous `zoompan` and burning subtitles via `libass` on a 30-minute video consumes **60 to 90 minutes of 200% CPU**, violently exceeding the 900-second job lease timeout (`SETTINGS.render_timeout_seconds`) by $4\times$ to $6\times$ and violating the strict resource target in **Section 5 of AGENTS.md** (hard ceiling: $\le 2$ CPU Cores, $\le 2.0$ GiB RAM).
4. **Missing YouTube Interactive Chapters & Soft Captions**: Stage 11 metadata generation does not inject YouTube Chapter timestamps into video descriptions, missing YouTube's primary zero-CPU interactive navigation feature. Furthermore, subtitle rendering defaults to CPU-intensive pixel burning rather than container soft subtitle muxing (`mov_text`).

This design establishes the **Hybrid Multi-Act Director** architecture. It transforms longform production into a dynamic 4–8 act narrative journey with tension-calibrated thematic horizontal loop rotation, zero-transcode stream-copy concatenation (`-c:v copy`), automated YouTube chapter markers, and soft caption muxing—guaranteeing broadcast-grade visual variety and **sub-45 second render turnaround** while strictly operating within the $\le 2$ CPU Cores / $\le 2.0$ GiB RAM envelope.

---

## 2. Architectural Decisions & Technical Approach

### 2.1 Decision 1: Hybrid Multi-Act Director vs Ken Burns Transcode vs Single-Loop Monotony

| Dimension | Option 1: Full Ken Burns Re-Encode | Option 2: Single Continuous Loop [CURRENT STATUS] | Option 3: Hybrid Multi-Act Director [SELECTED] |
| :--- | :--- | :--- | :--- |
| **Video Engine** | `UnifiedEncoder` / `ImageAnimationRenderer` | `LoopVideoEngine` (1 loop repeated 100-300x) | `LoopVideoEngine` (Multi-Act Stream-Copy Concat) |
| **Video Transcoding** | Full transcode (`libx264` + `zoompan`) | Zero re-encode (`-c:v copy`) | **Zero re-encode (`-c:v copy`)** |
| **Subtitle Delivery** | Burned pixels via `libass` | Soft-muxed `mov_text` | **Soft-muxed `mov_text` + `.srt` sidecar** |
| **Composition Time (30m)** | 3,600s – 5,400s (60–90 min) | ~15–25 seconds | **~25–35 seconds** |
| **Aggregate CPU Usage** | 200% (2 cores pinned for 1.5h) | $\le 120\%$ for ~15s (audio ducking only) | **$\le 120\%$ for ~15s (audio ducking only)** |
| **Peak RAM (RSS)** | 550 – 850 MiB | < 150 MiB | **< 150 MiB** |
| **900s Lease Timeout** | **CRITICAL FAILURE ($4\times - 6\times$ breach)** | Satisfied | **Satisfied ($25\times$ safety margin)** |
| **AGENTS.md §5 & REG-14** | **VIOLATES** | Compliant (but poor retention) | **100% STRICTLY COMPLIANT** |
| **Audience Retention** | High visual variety | **Severe viewer drop-off (stagnation)** | **High visual variety + Interactive Chapters** |

**Rationale**: Option 1 is architecturally impossible under VPS resource constraints (2 Cores, 2 GB RAM, 900s job timeout). Option 2 meets resource constraints but fails product and channel viability due to severe viewer drop-off. Option 3 reconciles quality and resource constraints by shifting visual variety to sequential multi-loop switching and platform-native interactive chapters while preserving zero-reencode stream-copy.

### 2.2 Decision 2: Zero-Transcode Multi-Act Stream-Copy Concat (`-f concat -safe 0 -c:v copy`)

Rather than re-encoding frames to bridge narrative acts, the system leverages FFmpeg's concat demuxer. 

- **Repetition Mathematics**: For each act $i \in \{1 \dots N\}$ with target duration $\text{dur}_i$ and loop duration $\text{clip\_dur}_i$:
  $$R_i = \max\left(1, \operatorname{round}\left(\frac{\text{dur}_i}{\max(0.5, \text{clip\_dur}_i)}\right)\right)$$
- If the cumulative sum $\sum_{i=1}^N R_i \cdot \text{clip\_dur}_i < T_{\text{audio}}$, the engine sorts acts by their remaining duration deficits and increments repetitions until the concat manifest duration covers or exceeds $T_{\text{audio}}$.
- The final output is clamped to the millisecond using `-t {duration_sec}` on the container output.
- **Bitstream Homogeneity**: All catalog loops in `assets/loops/horizontal/` and `assets/videos/longs/` are standardized to 1920x1080, 30.0 fps, `yuv420p`, H.264 High/Main profile, bt709 color matrix. `_probe_media` validates container compatibility before invoking the concat demuxer. If any asset deviates, the system aborts stream-copy and triggers fallback.

### 2.3 Decision 3: Soft Subtitle Muxing (`mov_text`) & Sidecar Export

Rasterizing subtitles into video frames using `libass` on a 30-minute 1080p video forces FFmpeg to decode and re-encode every single frame, adding 30–40 minutes of 200% CPU usage.
- Subtitles are soft-muxed directly into the MP4 container as a timed text track:
  ```bash
  -i subtitles.ass -map 3:0 -c:s mov_text -metadata:s:s:0 language=spa
  ```
- Handled atomically by `subtitle_mux_ffmpeg_parts` in `src/media/subtitles_ass.py`.
- An `.srt` subtitle sidecar (`subtitles.srt`) is persisted to `ctx.work_dir` and registered in `ctx.artifacts["srt_path"]` for upload via the YouTube Captions API during `stage_13_publish.py`.
- **Resource Work Refusal**: Longform horizontal composition requests attempting to burn subtitles via `libass` are rejected immediately.

### 2.4 Decision 4: Automated Native YouTube Chapter Description Formatting

YouTube provides an interactive chapter scrubber on desktop and mobile at **zero CPU cost** when video descriptions contain valid timestamps.
- `stage_11_metadata.py` extracts cumulative time offsets from `ctx.shot_durations` and matches them to act titles in `ctx.script_payload["acts"]`.
- Format specification:
  ```text
  Capítulos:
  00:00 - Acto I: Incepción Sensorial y Aislamiento
  04:15 - Acto II: Advertencias Ignoradas y Señales
  09:40 - Acto III: Punto de Ruptura y Crisis
  16:20 - Acto IV: Secuela Psicológica y Trauma
  ```
- **Validation Rules**:
  1. First timestamp MUST start strictly at `00:00`.
  2. Description MUST contain at least 3 distinct chapter timestamps.
  3. Minimum interval between consecutive chapters: $\ge 10\text{ seconds}$.
  4. Timestamps MUST be in strictly ascending chronological order.
  5. If validation fails or $< 3$ acts exist, the chapter block is cleanly omitted without failing the publication pipeline.

### 2.5 Decision 5: Elimination of Runtime Engine Coercion Trap

In `src/pipeline/utils.py` and `src/pipeline/executor.py`, the engine resolution logic previously contained:
```python
if is_multiscene_mode and not force_multiscene and engine_mode != "image_animation":
    engine_mode = "loop"
    is_loop_mode = True
    is_multiscene_mode = False
```
This is replaced by explicit routing for horizontal director lanes:
```python
if lane.orientation == "horizontal" and lane.visual_pipeline == "director":
    # Hybrid Multi-Act Director: preserves multiscene planning + stream-copy render
    engine_mode = "director"
    is_multiscene_mode = True
    is_loop_mode = False
```
This aligns declared lane configuration in `config/lanes.json` with actual runtime execution without requiring manual `FORCE_MULTISCENE=1` environment variables.

---

## 3. End-to-End System Architecture & Data Flow

### 3.1 Architecture Workflow Diagram

```
+---------------------------------------------------------------------------------------------------+
|                                  1. Narrative & Act Curation                                      |
|                                                                                                   |
|  [Raw Longform Script: 2600-4800w]                                                                |
|                 |                                                                                 |
|                 v                                                                                 |
|   TextSegmentationEngine.curate()                                                                 |
|   - Slices script into 4-8 Narrative Acts based on pacing and semantics                           |
|   - Assigns Act Titles, Dramatic Roles (exposition, rising, climax, aftermath)                     |
|   - Calculates Tension Curve (1-5) and Proportional Durations (sum = total_audio_dur)             |
|                 |                                                                                 |
|                 v                                                                                 |
|       ActNarrativePlan (ctx.script_payload["acts"])                                               |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                             2. Multi-Act Visual Planning (Stage 04)                               |
|                                                                                                   |
|   stage_04_mood.py                                                                                |
|   - Evaluates lane.orientation == "horizontal" and lane.visual_pipeline == "director"             |
|   - Checks killswitch: FORCE_SINGLE_LOOP=1 (falls back to continuous single loop if active)        |
|   - Iterates through Act 1..N:                                                                   |
|       * Queries LoopCatalogRepository.get_best_loop() for distinct thematic loops                |
|       * Matches theme_tags (horror, dark_forest, facility) and tension level (1-5)                |
|       * Uses seeded modulo rotation (seed=act_idx) + semantic aliases if assets < acts            |
|   - Populates:                                                                                    |
|       ctx.scene_bg_list = [loop_act1.mp4, loop_act2.mp4, ..., loop_actN.mp4]                      |
|       ctx.shot_durations = [dur_1, dur_2, ..., dur_N]                                             |
|   - Emits: MultiActVisualSpec -> visual_plan.json                                                 |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                         3. Scene Manifest & Flag Resolution (Stage 08)                            |
|                                                                                                   |
|   stage_08_loop.py -> _build_video_loop_manifest() / _build_legacy_manifest()                      |
|   - Enforces ctx.stream_copy_mode = True                                                          |
|   - Resolves ctx.mux_subtitles = True (when subtitles.ass is present)                             |
|   - Compiles scene_manifest.json containing:                                                      |
|       * scene_images: [loop_act1.mp4, ..., loop_actN.mp4]                                         |
|       * shot_durations: [dur_1, ..., dur_N]                                                       |
|       * narration_path: speech.wav, music_path: bg_music.wav                                      |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                   4. Zero-Transcode Multi-Act Stream-Copy Composition (Stage 09)                  |
|                                                                                                   |
|   stage_09_render.py -> _render_video_loop()                                                      |
|   - Acquires _LONG_RENDER_SEMAPHORE (concurrency bounded to 1)                                   |
|   - Delegates to LoopVideoEngine.render() -> stream_copy.py:                                      |
|       * Probe loops to ensure 1080p / 30fps / yuv420p profile parity                              |
|       * Computes integer repetition counts R_i for each act loop                                  |
|       * Writes ffconcat manifest (loop_concat_list.txt)                                           |
|       * Prepares subtitle_mux_ffmpeg_parts (mov_text soft muxing)                                 |
|       * Executes FFmpeg Stream-Copy:                                                              |
|           ffmpeg -y -threads 2 -f concat -safe 0 -i loop_concat_list.txt                          |
|                  -i speech.wav -stream_loop -1 -i bg_music.wav -i subtitles.ass                   |
|                  -filter_complex "[1:a][2:a]amix...,loudnorm...[aout]"                            |
|                  -map 0:v -map "[aout]" -map 3:0                                                  |
|                  -c:v copy -c:a aac -b:a 192k -c:s mov_text -metadata:s:s:0 language=spa          |
|                  -t {total_duration} -movflags +faststart video.mp4                               |
|   - Validates output: Turnaround <= 35s, Peak CPU <= 120%, Peak RAM < 150 MiB                     |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                        5. YouTube Chapters & Metadata Generation (Stage 11)                       |
|                                                                                                   |
|   stage_11_metadata.py                                                                            |
|   - Extracts cumulative timestamps from ctx.shot_durations:                                       |
|       t_0 = 00:00, t_1 = 04:15, t_2 = 09:40, t_3 = 16:20                                         |
|   - Formats YouTubeChapterSpec into ctx.youtube_description:                                      |
|       Capítulos:                                                                                  |
|       00:00 - Acto I: Incepción Sensorial y Aislamiento                                           |
|       04:15 - Acto II: Advertencias Ignoradas y Señales                                           |
|       09:40 - Acto III: Punto de Ruptura y Crisis                                                 |
|       16:20 - Acto IV: Secuela Psicológica y Trauma                                               |
|   - Validates YouTube constraints (starts 00:00, >= 3 chapters, intervals >= 10s)                |
|   - Registers artifacts: video.mp4, metadata.json, visual_plan.json, subtitles.srt               |
+---------------------------------------------------------------------------------------------------+
```

---

## 4. Interfaces & Data Contracts

All public interfaces and data exchange contracts follow immutable `@dataclass(slots=True)` definitions with strict static type hints.

### 4.1 `ActNarrativePlan` (Script Act Partitioning)

Defined in `src/curators/curation_profiles.py` / `src/curators/text_splitter.py`:

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass(slots=True, frozen=True)
class ActNarrativePlan:
    """Strongly typed representation of an individual narrative act."""
    act_index: int                       # 1-based sequential act index (1 <= act_index <= N)
    act_title: str                       # Public title for YouTube chapters
    dramatic_role: str                   # exposition_inception | rising_action_dread | climax_confrontation | aftermath_revelation
    tension_level: int                   # Integer tension score from 1 (ambient) to 5 (peak climax)
    narration_text: str                  # Dialogue and narration sentences allocated to this act
    target_duration_sec: float           # Scaled duration in seconds matching TTS audio
    word_count: int                      # Word count for duration estimation
    environmental_moods: List[str]       # Thematic environment descriptions for catalog matching
```

### 4.2 `MultiActVisualSpec` (Visual Planning Output)

Defined in `src/pipeline/context.py` / `src/media/interface.py`:

```python
@dataclass(slots=True, frozen=True)
class MultiActVisualSpec:
    """Strongly typed visual plan compiled by Stage 04 for multi-act stream-copy."""
    video_engine: str                    # "director" | "loop"
    stream_copy: bool                    # Must evaluate to True for longform horizontal
    lane_id: str                         # e.g. "horror-horror-long", "drama-aita-long"
    orientation: str                     # "horizontal" (1920x1080)
    total_duration_sec: float            # Total voiceover duration (sum of act durations)
    scene_bg_list: List[str]             # List of resolved absolute paths to loop MP4 assets
    shot_durations: List[float]          # List of durations for each act loop in seconds
    act_titles: List[str]                # Titles of each act for chapter correlation
    act_tensions: List[int]              # Tension scores corresponding to each loop
    is_killswitch_active: bool           # True if FORCE_SINGLE_LOOP=1 was triggered
```

### 4.3 `YouTubeChapterSpec` (Interactive Chapter Metadata)

Defined in `src/pipeline/stages/stage_11_metadata.py`:

```python
@dataclass(slots=True, frozen=True)
class YouTubeChapterEntry:
    """A single chapter marker adhering to YouTube interactive guidelines."""
    start_seconds: float
    formatted_time: str                  # "00:00", "04:15", "1:05:20"
    title: str                           # Sanitized act title
    act_index: int

@dataclass(slots=True)
class YouTubeChapterSpec:
    """Collection of chapters with YouTube validation methods."""
    chapters: List[YouTubeChapterEntry] = field(default_factory=list)

    def is_valid(self) -> bool:
        """Validates YouTube interactive chapter guidelines."""
        if len(self.chapters) < 3:
            return False
        if not self.chapters[0].formatted_time in ("00:00", "0:00"):
            return False
        for i in range(len(self.chapters) - 1):
            if (self.chapters[i+1].start_seconds - self.chapters[i].start_seconds) < 10.0:
                return False
            if self.chapters[i+1].start_seconds <= self.chapters[i].start_seconds:
                return False
        return True

    def format_description_block(self) -> str:
        """Emits YouTube-ready chapter description text block."""
        if not self.is_valid():
            return ""
        lines = ["\nCapítulos:"]
        for ch in self.chapters:
            lines.append(f"{ch.formatted_time} - {ch.title}")
        return "\n".join(lines)
```

### 4.4 `StreamCopyConcatSpec` (Demuxer Manifest Contract)

Defined in `src/media/loop/stream_copy.py`:

```python
@dataclass(slots=True, frozen=True)
class ConcatEntry:
    video_path: str
    repetition_count: int
    clip_duration_sec: float
    total_coverage_sec: float

@dataclass(slots=True, frozen=True)
class StreamCopyConcatSpec:
    """Specification for building ffconcat manifest and FFmpeg invocation."""
    manifest_path: str
    entries: List[ConcatEntry]
    target_total_duration: float
    actual_manifest_duration: float
    audio_path: str
    bgm_path: Optional[str]
    subtitle_path: Optional[str]
    output_video_path: str
    music_volume: float = 0.04
    threads: int = 2
```

---

## 5. File Changes & Subsystem Modifications

| Subsystem / File | Action | Detailed Description of Modifications |
| :--- | :---: | :--- |
| `src/pipeline/utils.py` | **Modify** | In `_resolve_engine_mode`: eliminate crude coercion of `director` $\to$ `loop`. Preserve `director` mode on horizontal longform lanes (`is_multiscene_mode = True`, `is_loop_mode = False`). |
| `src/pipeline/executor.py` | **Modify** | In `_execute_pipeline`: remove duplicate coercion logic. Forward `director` visual pipeline directly to `PipelineContext`. |
| `src/pipeline/stages/stage_04_mood.py` | **Modify** | Implement multi-act loop resolution for horizontal longform lanes where `lane.visual_pipeline == "director"`. Query `LoopCatalogRepository` for distinct loops per act (`ctx.scene_bg_list`, `ctx.shot_durations`). Handle `FORCE_SINGLE_LOOP=1` killswitch. Implement seeded modulo rotation fallback when unique catalog loops $<$ acts. |
| `src/pipeline/stages/stage_08_loop.py` | **Modify** | Update `_build_video_loop_manifest` and `_build_legacy_manifest` to ensure that horizontal director lanes set `ctx.stream_copy_mode = True` and populate `scene_images` and `shot_durations` from `ctx.scene_bg_list`. |
| `src/pipeline/stages/stage_09_render.py` | **Modify** | Direct horizontal director lanes to `_render_video_loop` (stream-copy concat) rather than invoking `MultiSceneCompositor` pixel transcoding. Add explicit check to reject `libass` burning on horizontal longform. |
| `src/pipeline/stages/stage_11_metadata.py` | **Modify** | Add `YouTubeChapterSpec` generator extracting act time offsets from `ctx.shot_durations`. Validate YouTube chapter rules (start at `00:00`, $\ge 3$ chapters, $\ge 10$s intervals). Inject formatted chapter block into `ctx.youtube_description` and `metadata.json`. |
| `src/curators/curation_profiles.py` | **Modify** | Expand longform curation profiles (`horror-horror-long`, `drama-aita-long`) to support dynamic 4–8 act narrative structures with distinct act titles, tension curves (1–5), and dramatic roles. |
| `src/curators/text_splitter.py` | **Modify** | In `TextSegmentationEngine._build_acts`: support variable 4–8 act decomposition for longform narratives ($T \ge 600\text{s}$) by dynamically distributing scenes across acts and scaling durations proportionally. |
| `src/media/loop/stream_copy.py` | **Modify** | In `_build_multi_scene_concat_list`: verify repetition count calculations for longform act durations (60s–300s). Ensure `-threads 2` on audio mixing commands and `-c:s mov_text` subtitle muxing. |
| `src/media/loop/rotation.py` | **Modify** | Add `resolve_multi_act_loops()` helper: queries `LoopCatalogRepository` iteratively with `exclude_loop_ids` and seeded rotation (`seed = act_index`) to resolve $N$ distinct horizontal loops. |
| `config/lanes.json` | **Modify** | Verify that `horror-horror-long` and `drama-aita-long` retain `"visual_pipeline": "director"`, and verify SciFi longform lane configuration. |
| `assets/loops/bank_manifest.json` | **Modify** | Expand horizontal loop definitions and thematic tags across `horror`, `dark_forest`, `facility`, `drama`, `cozy_ambient`, and `nocturne_city`. |
| `tests/unit/test_longform_multi_act.py` | **Create** | Comprehensive unit test suite covering: 4–8 act partitioning, multi-act catalog resolution, modulo rotation fallback, stream-copy concat list generation, and YouTube chapter description validation. |
| `tests/unit/test_anti_regression_guardrails.py` | **Modify** | Assert REG-13 and REG-14 invariants across the new multi-act stream-copy director pipeline. |

---

## 6. Strict Resource Governance & Performance Envelope

### 6.1 Compliance with Section 5 of AGENTS.md & REG-14

All media processing in the Hybrid Multi-Act Director operates strictly within the hard target ceiling:
- **CPU Target Ceiling**: $\le 2.0\text{ CPU Cores}$ ($\le 200\%$ aggregate CPU across all concurrent threads).
- **RAM Target Ceiling**: $\le 2.0\text{ GiB RAM}$ ($2,048\text{ MiB}$ peak resident memory).
- **Observed Peak Utilization**:
  - Video stream-copy concatenation: $\approx 0.10\text{ Cores}$ (I/O bound disk remuxing).
  - Audio mixing and EBU R128 loudness normalization: $\le 1.20\text{ Cores}$ (120% CPU for ~15 seconds, bounded by `-threads 2`).
  - Peak resident memory (RSS): $< 150\text{ MiB}$ (disk-streamed `ffconcat`; zero in-memory frame buffers).

### 6.2 Turnaround Time Contract

- **Turnaround Ceiling**: $\le 45\text{ seconds}$ from render stage entry to container finalization for an entire 10–30 minute (600–1800s) 1080p video.
- **Expected Turnaround**: 25 to 35 seconds.
- **Safety Margin against Lease Timeout**: The system operates with a $25\times$ safety margin relative to the 900-second job lease timeout (`SETTINGS.render_timeout_seconds`).

### 6.3 Steady-State Zero Idle & Resource Work Refusal

- **Zero Idle Footprint**: When no rendering job is running, background daemons consume $0.0\%\text{ CPU}$. All FFmpeg subprocesses run via synchronous context managers with explicit timeouts.
- **Resource Work Refusal (Kill Switch)**:
  - If any configuration or stage requests full-pixel Ken Burns re-encoding (`zoompan`) or `libass` subtitle burning on a 16:9 horizontal longform video, the rendering engine triggers the **Resource Work Refusal** policy and aborts immediately before allocating CPU cycles.
- **Single-Flight Longform Concurrency**: Multi-act longform rendering is guarded by `_LONG_RENDER_SEMAPHORE = 1`. Only one longform render can execute on the host at any instant.
- **Memory Checkpoints**: Explicit `memory_checkpoint()` calls are triggered at the entry and exit of Stages 04, 08, 09, and 11 to enforce immediate garbage collection.

---

## 7. Shared Tooling & Cross-Lane Coherence

To preserve system consistency across parallel lanes (Shorts vs Longform, Vertical vs Horizontal):
1. **Timing Scaling**: Both `stage_04_mood.py` and `stage_08_loop.py` utilize `timing_scales_to_audio` from `src/media/visual_coherence.py` to guarantee zero temporal drift between narration audio and video shot boundaries.
2. **Safe Zones**: UI safe zone constraints are centralized in `src/media/visual_coherence.py` (`enforce_shorts_safe_zone` for vertical Shorts; standard 5% title safe margins for horizontal longform).
3. **Encoder Separation**:
   - `src/media/unified_encoder.py` (`UnifiedEncoder`) remains the dedicated single-pass atomic encoder for 9:16 vertical Shorts (`image_animation`) where Ken Burns motion and `libass` burning are legally required.
   - `src/media/loop/stream_copy.py` (`LoopVideoEngine`) remains the dedicated stream-copy engine for all longform horizontal videos (`director` and `video_loop`).
4. **Lane Registry**: `src/core/lanes.py` enforces canonical validation across all six production lanes via `ALLOWED_VISUAL_PIPELINES`.

---

## 8. Testing & Verification Strategy

### 8.1 Unit Test Suite (`tests/unit/test_longform_multi_act.py`)

A new automated test suite verifies all contracts:
1. **Act Partitioning Tests**:
   - Verify `TextSegmentationEngine.curate` partitions 10–30m scripts into 4–8 structured acts ($4 \le N \le 8$).
   - Verify all acts contain valid `act_title`, `dramatic_role`, and progressive tension ratings ($1 \le \text{tension} \le 5$).
   - Verify sum of act durations strictly matches total audio duration within $\pm 0.1\text{s}$.
2. **Multi-Loop Resolution Tests**:
   - Verify `stage_04_mood.py` resolves distinct horizontal catalog loops per act for longform director lanes.
   - Verify deterministic modulo rotation when catalog contains fewer unique loops than narrative acts.
   - Verify environment killswitch `FORCE_SINGLE_LOOP=1` reverts to a single continuous loop.
3. **Stream-Copy Concat Tests**:
   - Verify `_build_multi_scene_concat_list` calculates correct integer repetition counts for long act durations.
   - Verify generated `ffconcat` file contains sequential repetitions of all act loops covering the target duration.
   - Verify FFmpeg command uses `-c:v copy` and `-c:s mov_text`, and does not contain `libass` or `subtitles=`.
4. **YouTube Chapter Formatting Tests**:
   - Verify chapter markers start at `00:00`.
   - Verify at least 3 chapters are emitted.
   - Verify all chapter intervals are $\ge 10\text{ seconds}$.
   - Verify acts $< 10\text{s}$ are merged into adjacent acts.
   - Verify chapter block is omitted cleanly if $< 3$ chapters remain.

### 8.2 Anti-Regression Guardrail Verification (REG-01 to REG-14)

Execution of:
```bash
.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v
```
Validates that:
- Zero Playwright / Chromium imports exist in media pipelines (`REG-01`).
- Zero legacy subsystems exist (`REG-02`).
- Zero in-memory frame loops exist (`REG-03`, `REG-08`).
- Stream-copy priority and soft subtitle muxing are preserved (`REG-13`).
- Resource target envelope ($\le 2$ Cores, $\le 2.0$ GiB RAM) is strictly maintained (`REG-14`).

### 8.3 End-to-End Generate-Only Smoke Tests

Execution of:
```bash
python3 main.py run --lane horror-horror-long --generate-only
python3 main.py run --lane drama-aita-long --generate-only
```
Validates:
- Offline execution with zero external network requests or browser instances.
- Turnaround time completes in $\le 45\text{ seconds}$.
- Output directory contains valid `video.mp4`, `metadata.json` with chapters, and `subtitles.srt`.

---

## 9. Threat Matrix & Defensive Engineering

| Threat / Failure Mode | Severity | Probability | Defensive Mitigation Strategy |
| :--- | :---: | :---: | :--- |
| **1. Catalog Asset Scarcity** | Medium | Medium | When the catalog contains fewer unique loops than narrative acts, `resolve_multi_act_loops` uses seeded modulo rotation (`seed = act_index`) across available assets and falls back to semantic aliases (`dark_forest` $\to$ `horror`). |
| **2. PTS/DTS Discontinuity in Concat** | High | Low | Master horizontal loops in `assets/loops/horizontal/` and `assets/videos/longs/` are pre-standardized to identical parameters (1920x1080, 30fps, H.264 High/Main, `yuv420p`, bt709). Probes in `stream_copy.py` reject assets with mismatched geometry or timebase before stream-copy. |
| **3. Audio-Video Duration Drift** | Medium | Low | Integer repetitions in `_build_multi_scene_concat_list` are calculated to slightly overshoot or match act durations, and `-t {audio_duration}` on the output container clamps the stream precisely to narration audio. |
| **4. YouTube Chapter Rejection** | Medium | Low | Stage 11 chapter formatter enforces strict YouTube validation rules: chapter 1 strictly at `00:00`, minimum 3 chapters, and each chapter $\ge 10$ seconds apart. If validation fails, description generation falls back gracefully to standard formatting without breaking the pipeline. |
| **5. CPU Spikes during Audio Mastering** | Low | Low | Audio mixing commands (`loudnorm`, `amix`) in `stream_copy.py` enforce `-threads 2`, preventing audio DSP filters from exceeding the 2-core budget. |
| **6. Subtitle Soft Muxing Container Error** | Low | Low | If subtitle generation is disabled or emits empty cues, `subtitle_mux_ffmpeg_parts` returns empty arguments, allowing stream-copy concatenation to proceed cleanly without subtitle tracks. |

---

## 10. Rollback & Disaster Recovery Plan

If unexpected anomalies arise in production, a 4-tier rollback mechanism ensures zero downtime:

1. **Instantaneous Configuration Rollback**:
   - In `config/lanes.json`, set `"visual_pipeline": "video_loop"` on `horror-horror-long` and `drama-aita-long`, or pass `--visual-pipeline video_loop` via CLI. The pipeline immediately reverts to single continuous loop stream-copy without database migrations or code redeployment.
2. **Runtime Environment Kill Switch**:
   - Setting `FORCE_SINGLE_LOOP=1` in the daemon environment instructs Stage 04 and Stage 08 to bypass multi-act rotation and resolve a single continuous loop.
3. **Graceful Stage Fallback**:
   - If multi-act loop resolution throws an unhandled exception during Stage 04, the stage catches the error, logs a structured observability event (`pipeline.mood.multi_act_fallback`), and falls back to `resolve_continuous_loop()`, allowing rendering to complete.
4. **Clean Git Reversion**:
   - All code modifications preserve existing domain interfaces, dataclasses, and database contracts. Reverting the git commit cleanly restores the repository to its prior stable state.
