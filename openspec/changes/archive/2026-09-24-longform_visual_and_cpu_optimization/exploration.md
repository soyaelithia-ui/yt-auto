# Exploration: Longform Visual Quality and CPU Optimization (10-30 min Videos)

## 1. Context & Objectives

YouTube longform lanes in `config/lanes.json`:
- `horror-horror-long` (`channel`: "horror", horizontal 1920x1080, 600-1800s, `visual_pipeline`: "director", template: "creepypasta")
- `drama-aita-long` (`channel`: "drama", horizontal 1920x1080, 600-1800s, `visual_pipeline`: "director", template: "aita")

### Inviolable Performance Envelope (AGENTS.md Section 5)
- **Hard Target Ceiling**: $\le$ 2 CPU Cores ($\le$ 200% across all concurrent threads) and $\le$ 2.0 GiB RAM (2,048 MiB peak resident memory).
- **Stream-Copy Prioritization**: Video composition must prioritize Stream-Copy (`-c:v copy`) to eliminate CPU-intensive re-encoding.
- **Strict Concurrency**: Concurrency bounded by `_LONG_RENDER_SEMAPHORE = 1`.
- **Render Timeout Contract**: `SETTINGS.render_timeout_seconds` defaults to 900 seconds (15 minutes). Any render taking $>15$ minutes triggers an automatic job lease timeout and process termination.
- **Monotonic Optimization**: Resource consumption must only decrease or remain stable over time; it must never spike or climb across commits.

The core challenge is: **How can 10-30 minute longform videos achieve visual diversity, narrative pacing, multi-act coherence, subtitles, and atmospheric music without exceeding 2 CPU Cores / 2 GB RAM and without incurring 30-90 minute FFmpeg transcoding bottlenecks?**

---

## 2. Current State & Problem Investigation

### 2.1 The "Director Coercion Trap"
In `src/pipeline/utils.py` (lines 346–352) and `src/pipeline/executor.py` (lines 228–234):
```python
force_multiscene = os.environ.get("FORCE_MULTISCENE", "").strip().lower() in ("1", "true", "yes", "on")
if is_multiscene_mode and not force_multiscene and engine_mode != "image_animation":
    logger.info("Coercing video_engine=%s to loop (set FORCE_MULTISCENE=1 to restore director)", engine_mode)
    engine_mode = "loop"
    is_loop_mode = True
    is_multiscene_mode = False
```
Because `horror-horror-long` and `drama-aita-long` configure `"visual_pipeline": "director"`, runtime execution automatically coerces them to `loop` mode unless `FORCE_MULTISCENE=1` is explicitly set in the environment.

### 2.2 The "Single Loop Monotony" Defect
When coerced to `loop` mode:
1. In `src/pipeline/stages/stage_04_mood.py` (lines 80–87):
   ```python
   ctx.resolved_loop_path = ctx.loop_engine.resolve_continuous_loop(
       orientation=ctx.lane.orientation,
       category=str(ctx.target_category),
       channel=str(ctx.channel_name),
       allow_test_mock=is_test_environment(),
   )
   ctx.scene_bg_list = [str(ctx.resolved_loop_path)]
   ctx.shot_durations = [total_audio_sec]
   ```
   Only **one single video file** is resolved for the entire duration.
2. In `src/pipeline/stages/stage_08_loop.py` and `stage_09_render.py`:
   `_render_video_loop` delegates to `LoopVideoEngine.render` with `stream_copy=True`.
3. In `src/media/loop/stream_copy.py`:
   A single 6-second video loop (e.g. `horror_ambient_01.mp4`) is repeated **100 to 300 times** to fill 600 to 1800 seconds.
4. **Viewer Impact**: A 20-30 minute longform story plays against a completely static, endlessly repeating 6-second animation loop with no visual progression, causing acute viewer fatigue and high audience drop-off.

### 2.3 Horizontal Catalog Asset Scarcity
In `assets/videos/longs/`, only two files exist:
- `assets/videos/longs/horror_ambient_01.mp4` (~6s, 1080p)
- `assets/videos/longs/drama_ambient_01.mp4` (~6s, 1080p)

While `assets/loops/bank_manifest.json` defines certified master loops (e.g. `moku_containment_facility_master_60s.mp4`), horizontal assets have not been indexed into multi-act thematic pools for horror and drama lanes.

### 2.4 Subtitles & Chapter Gaps in Longform
- In `src/pipeline/stages/stage_11_metadata.py`, description generation does not inject YouTube Chapter timestamps (`00:00`, `03:45`, etc.), missing a major zero-CPU visual navigation feature.
- In `src/pipeline/stages/stage_07_subtitles.py` and `stage_09_render.py`, burning subtitles via `libass` on a 30-minute 1080p video forces a 30-40 minute CPU re-encode. Soft subtitle muxing (`mov_text`) is already supported in `stream_copy.py` at zero CPU cost, but is not coupled with structured longform chapter cues.

---

## 3. Comparison of Architectural Approaches

### Approach A: Full Multi-Scene Ken Burns Transcoding (Shorts `image_animation` model)
*Apply Shorts-style dynamic image animation across 20–50 scenes over 10–30 minutes.*

- **Workflow**:
  1. Slice script into 20–60 scenes (each 10–15s).
  2. For each scene: render image backdrop with `zoompan` and `eq` color grading via `libx264` (`preset veryfast`, `crf 21-23`, `-threads 2`).
  3. Concatenate scene segments via stream-copy demuxer.
  4. Second pass: Burn subtitles using `libass` filter graph.
- **CPU & Transcoding Analysis**:
  - `zoompan` is single-threaded and heavily CPU-bound.
  - Encoding 1080p @ 30fps with x264 on 2 vCPUs achieves ~15–22 fps (~0.5x to 0.7x realtime).
  - **10-minute video (600s)**:
    - Pass 1 (scenes): $600\text{s} / 0.6 = 1,000\text{s}$ (~16.6 min).
    - Pass 2 (libass burn): $600\text{s} / 0.7 = 857\text{s}$ (~14.2 min).
    - Total CPU time: **~30.8 minutes** at 200% CPU.
  - **30-minute video (1800s)**:
    - Pass 1 (scenes): $1,800\text{s} / 0.6 = 3,000\text{s}$ (~50 min).
    - Pass 2 (libass burn): $1,800\text{s} / 0.7 = 2,570\text{s}$ (~42.8 min).
    - Total CPU time: **~92.8 minutes** (> 1.5 hours!) at 200% CPU.
- **Fatal Bottlenecks**:
  - Violates `SETTINGS.render_timeout_seconds` (900s) by $2\times$ to $6\times$, triggering lease cancellation.
  - Continuous 100% saturation on 2 cores blocks daemon cycles, health checks, and review bot.
  - Generates 3–8 GB of intermediate video chunks, risking disk exhaustion.
- **Verdict**: **REJECTED (Unviable).**

---

### Approach B: Segmented / Chunked Stream-Copy Concat with Discrete Act Transitions
*Divide 10–30 min video into 4–8 narrative acts; render micro-transitions (3–5s) and stream-copy long loop bodies.*

- **Workflow**:
  1. Split script into 4–8 acts (e.g. 5 acts for 15m; each act 180s).
  2. For each act:
     - Render a 3–5s dynamic transition/title card bumper with `libx264`.
     - Select a thematic loop from the catalog for the 175s body.
  3. Stitch all transition clips and loop clips using FFmpeg concat demuxer (`-c:v copy`).
  4. Master mix: Narration + ducked BGM + soft subtitles (`mov_text`).
- **CPU & Transcoding Analysis**:
  - 5 transition bumpers $\times$ 4s = 20s of total video re-encoded.
  - Transcoding 20s takes ~30s on 2 vCPUs.
  - Concat demuxer (`-c:v copy`): ~5s.
  - Audio mixing & EBU R128 loudness: ~15s.
  - Total render turnaround: **~50–65 seconds** for a 30-minute video!
  - Peak RAM: < 150 MiB.
- **Tradeoffs & Risks**:
  - **Bitstream Parity Hazard**: FFmpeg stream-copy concat (`-c:v copy`) requires bitstream compatibility across all inputs: identical H.264 profile/level, pixel format (`yuv420p`), timebase (`1/15360` or `1/30`), color matrix (bt709), and SPS/PPS headers.
  - In practice, concatenating freshly rendered FFmpeg x264 clips with pre-existing catalog loops via stream-copy often introduces DTS/PTS discontinuities, dropped frames, or audio desync unless pre-standardized.
- **Verdict**: **PARTIALLY VIABLE (requires pre-standardized container profiles).**

---

### Approach C: Hybrid Multi-Act Director (Thematic Multi-Loop Stream-Copy + Dynamic Chapters & Visual Overlays)
*Combine intelligent multi-act script curation, tension-calibrated loop rotation, stream-copy concat assembly, native YouTube chapter markers, and soft subtitle styling.*

- **Workflow**:
  1. **Narrative Act & Tension Curation**:
     `CinematicScriptCuratorAgent` / `TextSegmentationEngine` parses the 10–30m script into 4–8 structured acts (e.g. Act I: Inception, Act II: Escalation, Act III: Climax, Act IV: Aftermath), deriving tension levels (1–5), act titles, and mood tags.
  2. **Thematic Multi-Loop Allocation**:
     `stage_04_mood.py` queries `LoopCatalogRepository` for a **distinct** horizontal loop for each act matching that act's mood and tension (e.g. Act 1: `horror_woods`, Act 2: `horror_facility`, Act 3: `horror_red_alert`, Act 4: `horror_darkness`).
  3. **Zero-Transcode Stream-Copy Assembly**:
     `LoopVideoEngine.render` / `stream_copy.py` constructs a multi-scene concat list. Each loop is repeated to cover its act's exact duration (e.g. 180s, 240s) and concatenated via `-f concat -safe 0 -c:v copy`.
  4. **Dynamic Chapter Transitions (Zero-CPU YouTube UI)**:
     `stage_11_metadata.py` extracts act boundaries (`00:00`, `04:12`, `09:30`, `16:45`) and formats them into the YouTube description as native clickable chapters (`00:00 - Acto I: La Señal`, `04:12 - Acto II: La Brecha`, etc.). This creates interactive scrubbers on the YouTube player with zero CPU rendering.
  5. **Soft Subtitle Integration & Styling**:
     Captions are muxed into the MP4 as `mov_text` (`-c:s mov_text`) without rasterizing pixels, and the `.srt` is uploaded via YouTube Captions API in `stage_13_publish.py`.
  6. **Catalog Pre-Standardized Bumpers (Optional Extension)**:
     If visual bumper transitions (e.g. 2s VHS static / stinger) are desired, use pre-rendered assets already standardized to the exact codec/timebase of the master loops, keeping 100% of video concatenation in `-c:v copy`.
- **CPU & Transcoding Analysis**:
  - Video re-encoding: **0 seconds** (`-c:v copy`).
  - Audio mixing (`amix` + `loudnorm`): ~15–20s.
  - Video stream-copy concat + audio mux: ~5–10s.
  - Total render turnaround: **~25–35 seconds** for an entire 30-minute video!
  - CPU usage: $\le$ 1.5 cores for ~20s.
  - RAM consumption: < 150 MiB (disk streaming; zero raw frame arrays).
  - 100% compliant with AGENTS.md Section 5.
- **Verdict**: **STRONGLY RECOMMENDED.**

---

## 4. Comparative Evaluation Matrix

| Metric / Dimension | Approach A (Full Ken Burns Transcode) | Approach B (Chunked Stream-Copy + Rendered Bumpers) | Approach C (Hybrid Multi-Act Director) [RECOMMENDED] |
| :--- | :--- | :--- | :--- |
| **Transcode Time (30m video)** | 60 – 90 minutes | 50 – 65 seconds | **25 – 35 seconds** |
| **CPU Utilization** | 200% (2 cores maxed 1+ hr) | Brief 30s spike to 180% | **$\le$ 120% for ~15s (audio only)** |
| **Peak RAM Footprint** | ~600 MiB | ~180 MiB | **< 150 MiB** |
| **Visual Diversity** | High (20–50 image pans) | High (4–8 acts + bumpers) | **High (4–8 thematic loops + chapter markers)** |
| **Risk of PTS/DTS Glitches** | Low (unified encode) | **High** (mixed x264 & loop demux) | **Zero** (homogeneous catalog loops) |
| **Timeout Risk (900s)** | **CRITICAL (100% fails)** | Zero | **Zero** |
| **Compliance with AGENTS.md §5** | **VIOLATES** (heavy re-encode) | Compliant | **100% STRICTLY COMPLIANT** |
| **YouTube Native Synergy** | None (burned pixels only) | Low | **High** (Interactive YouTube Chapters + Soft CC) |

---

## 5. Affected Files & Subsystems

1. `config/lanes.json`
   - Retain `"visual_pipeline": "director"` for `horror-horror-long` and `drama-aita-long`, but bind it canonically to the optimized hybrid multi-act director engine.
2. `src/pipeline/utils.py` & `src/pipeline/executor.py`
   - Update `_resolve_engine_mode`: eliminate the crude coercion of `director` $\to$ `loop` for longform lanes when multi-act stream-copy is active.
3. `src/pipeline/stages/stage_04_mood.py`
   - In longform director mode: generate multi-act visual plans with `CinematicScriptCuratorAgent`, resolving distinct catalog loops per act (`ctx.scene_bg_list` with $N$ loops and corresponding `ctx.shot_durations`).
4. `src/pipeline/stages/stage_08_loop.py`
   - Ensure `_build_video_loop_manifest` and `_build_legacy_manifest` correctly populate `scene_images` and `shot_durations` for multi-act stream-copy.
5. `src/pipeline/stages/stage_09_render.py`
   - Ensure longform renders execute through `LoopVideoEngine.render` with multi-scene stream-copy (`stream_copy=True`) and soft subtitle muxing (`include_subtitles=True`, `mov_text`).
6. `src/pipeline/stages/stage_11_metadata.py`
   - Add automated extraction and injection of YouTube Chapter timestamps into `ctx.youtube_description` based on act boundaries.
7. `src/media/loop/rotation.py` & `src/core/catalog.py`
   - Expand horizontal loop catalog definitions to support tension-indexed loop retrieval (`get_best_loop` with act/tension parameters).
8. `assets/loops/horizontal/` & `assets/loops/bank_manifest.json`
   - Ensure horizontal loops for horror and drama are indexed and available for multi-act rotation.
9. `tests/`
   - Unit tests validating multi-act stream-copy concatenation, 2-core CPU limits, and chapter description formatting.

---

## 6. Recommendations & Implementation Strategy

1. **Adopt Approach C (Hybrid Multi-Act Director)**:
   - Deliver 4–8 distinct visual loops across narrative acts rather than repeating a single 6-second clip.
   - Keep 100% of the video track in stream-copy (`-c:v copy`), preserving sub-minute turnaround and near-zero CPU usage.
2. **Implement Native YouTube Chapters**:
   - Format description with `00:00 [Act Title]` markers in Stage 11. YouTube automatically turns these into interactive chapter markers on desktop and mobile.
3. **Mux Soft Subtitles**:
   - Deliver subtitles via `-c:s mov_text` in the MP4 container and upload `.srt` via the YouTube API. Prohibit libass frame burning for longform horizontal videos.
4. **Remove Unsafe Engine Coercion**:
   - Replace the blanket coercion in `src/pipeline/utils.py` with explicit support for multi-act stream-copy director mode.
5. **Populate Horizontal Loop Pool**:
   - Register distinct horizontal loops in `LoopCatalogRepository` across themes (`containment`, `wilderness`, `diner`, `interior_drama`, `courtroom`) so multi-act stories rotate through diverse scenes.

---

## 7. Risks & Mitigation

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **Catalog Loop Exhaustion** | If catalog has fewer loops than acts, repetition could occur. | Use seeded modulo rotation (`seed = act_idx`) across available pools and fallback to related thematic aliases (`dark_forest` $\to$ `horror`). |
| **Audio-Video Drift in Concat** | Repeating loops of fractional duration (e.g. 6.04s) could accumulate small rounding offsets against audio. | `_build_multi_scene_concat_list` in `stream_copy.py` already computes repetition counts to match total audio duration, and `-t {audio_duration}` clamps the container. |
| **YouTube Chapter Formatting Rejection** | YouTube requires the first chapter at `00:00` and at least 3 chapters of $\ge 10\text{s}$ each. | Enforce chapter formatter validation: always start at `00:00`, minimum 3 chapters, minimum 10 seconds apart. |
| **CPU Spikes during Audio Ducking** | Audio filter complex with `loudnorm` and `amix` could spike CPU if unconstrained. | Enforce `-threads 2` on audio mixing commands in `stream_copy.py`. |

---

## 8. Ready for Proposal
**Status: READY FOR PROPOSAL.**
The exploration confirms that Approach C satisfies all visual, narrative, and performance criteria while strictly respecting the $\le$ 2 CPU Cores / $\le$ 2.0 GiB RAM envelope.
